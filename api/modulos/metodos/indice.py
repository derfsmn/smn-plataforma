"""Partir los documentos en fragmentos, ocultar datos personales, sacar su huella de significado y buscar.

La búsqueda junta dos listas: por palabras (BM25, sin acentos y sin palabras vacías) y por significado (coseno contra
la huella de Ollama). Si Ollama está apagado, solo busca por palabras. Solo se buscan fragmentos de documentos
vigentes que la persona puede ver (roles del documento y, para los que vienen de Compras o Fiscal, su permiso).
"""
import json
import threading
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.seguridad import Contexto
from modulos.metodos.modelos import Documento, Fragmento
from nucleo import busqueda
from nucleo.busqueda import (LARGO_FRAGMENTO, OCULTO, PERSONALES, TANDA_HUELLAS, VACIAS, Hallazgo, Pieza,  # noqa: F401
                             ocultar_personales, palabras, partir, sin_acentos)
from nucleo.busqueda import desempacar as _desempacar
from nucleo.busqueda import empacar as _empacar  # noqa: F401
from nucleo.busqueda import raiz as _raiz  # noqa: F401
from nucleo.lectura import Bloque

TAREA_HUELLA = "metodos.huella"
# Umbrales de «sí hay de dónde contestar»; se ajustan con la prueba de las 40 preguntas
COSENO_MINIMO = 0.50
CUBRE_MINIMO = 0.5  # parte de la pregunta (por peso de cada palabra) que debe aparecer en el fragmento
VER_TODO = "metodos.aprobar"


def indexar(bd: Session, doc: Documento, bloques: list[Bloque], *, usuario_id: int | None = None) -> dict:
    """Vuelve a escribir los fragmentos del documento con los datos personales ocultos y, si se puede, su huella."""
    bd.query(Fragmento).filter(Fragmento.documento_id == doc.documento_id).delete(synchronize_session=False)
    total: Counter = Counter()
    nuevos = []
    for n, p in enumerate(partir(bloques)):
        texto, cuenta = ocultar_personales(p.texto)
        seccion, cuenta_s = ocultar_personales(p.seccion) if p.seccion else (None, Counter())
        total.update(cuenta)
        total.update(cuenta_s)
        nuevos.append(Fragmento(documento_id=doc.documento_id, orden=n, seccion=seccion, pagina=p.pagina, texto=texto))
    bd.add_all(nuevos)
    # el texto completo queda en Markdown (títulos con «#») y sin datos personales: es lo que lee la IA al redactar
    doc.texto = "\n\n".join(("#" * b.nivel + " " if b.nivel else "") + ocultar_personales(b.texto.strip())[0]
                              for b in bloques if b.texto.strip()) or None
    avisos = {k: v for k, v in total.items()}
    doc.avisos = json.dumps(avisos) if avisos else None
    bd.flush()
    con_huella = poner_huellas(bd, nuevos, usuario_id=usuario_id)
    olvidar_cache()
    return {"fragmentos": len(nuevos), "con_huella": con_huella, "datos_personales": avisos}


def _texto_para_huella(f: Fragmento, titulo: str) -> str:
    return f"{titulo}. {f.seccion or ''}\n{f.texto}"[:4000]


def poner_huellas(bd: Session, fragmentos: list[Fragmento], *, usuario_id: int | None = None) -> int:
    """Huella de cada fragmento. Si Ollama no está, se quedan sin huella (la búsqueda por palabras sigue)."""
    modelo, vectores = busqueda.huellas(
        bd, TAREA_HUELLA, [_texto_para_huella(f, f.documento.titulo if f.documento else "") for f in fragmentos],
        usuario_id=usuario_id)
    hechos = 0
    for f, v in zip(fragmentos, vectores):
        if v is not None:
            f.vector, f.modelo_vector = v, modelo
            hechos += 1
    bd.flush()
    return hechos


def huella_pregunta(bd: Session, texto: str, usuario_id: int | None) -> tuple[str, tuple[float, ...]] | None:
    return busqueda.huella_texto(bd, TAREA_HUELLA, texto, usuario_id)


# ---------------------------------------------------------------- índice en memoria

@dataclass
class Entrada:
    fragmento_id: int
    documento_id: int
    seccion: str | None
    pagina: int | None
    texto: str
    terminos: Counter
    vector: tuple[float, ...] | None
    modelo: str | None
    roles: set[str]
    permiso: str | None


@dataclass
class Indice:
    firma: tuple
    entradas: list[Entrada] = field(default_factory=list)
    df: Counter = field(default_factory=Counter)
    largo_promedio: float = 1.0


_cache: Indice | None = None
_cache_lock = threading.Lock()


def olvidar_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def _firma(bd: Session) -> tuple:
    fila = bd.execute(
        select(func.count(Fragmento.fragmento_id), func.max(Fragmento.fragmento_id),
               func.count(Fragmento.vector), func.count(func.distinct(Documento.documento_id)),
               func.max(Documento.documento_id))
        .join(Documento, Documento.documento_id == Fragmento.documento_id)
        .where(Documento.estado == "vigente")).one()
    roles = bd.scalar(select(func.checksum_agg(func.binary_checksum(Documento.roles, Documento.permiso)))
                      .where(Documento.estado == "vigente"))
    return tuple(fila) + (roles,)


def indice(bd: Session) -> Indice:
    global _cache
    firma = _firma(bd)
    with _cache_lock:
        if _cache and _cache.firma == firma:
            return _cache
    nuevo = Indice(firma)
    filas = bd.execute(
        select(Fragmento.fragmento_id, Fragmento.documento_id, Fragmento.seccion, Fragmento.pagina, Fragmento.texto,
               Fragmento.vector, Fragmento.modelo_vector, Documento.titulo, Documento.roles, Documento.permiso)
        .join(Documento, Documento.documento_id == Fragmento.documento_id)
        .where(Documento.estado == "vigente"))
    total = 0
    for fid, did, seccion, pagina, texto, vector, modelo, titulo, roles, permiso in filas:
        # el título y la sección cuentan dos veces: dicen de qué trata el fragmento
        terminos = Counter(palabras(texto) + palabras(f"{titulo} {seccion or ''}") * 2)
        total += sum(terminos.values())
        nuevo.df.update(terminos.keys())
        nuevo.entradas.append(Entrada(fid, did, seccion, pagina, texto, terminos,
                                      _desempacar(vector) if vector else None, modelo,
                                      set(json.loads(roles)) if roles else set(), permiso))
    nuevo.largo_promedio = total / len(nuevo.entradas) if nuevo.entradas else 1.0
    with _cache_lock:
        _cache = nuevo
    return nuevo


# ---------------------------------------------------------------- búsqueda

def roles_de(bd: Session, ctx: Contexto) -> set[str]:
    return {r.codigo for r in ctx.usuario.roles}


def puede_ver(e_roles: set[str], e_permiso: str | None, ctx: Contexto, mis_roles: set[str]) -> bool:
    if ctx.puede(VER_TODO) or ctx.puede("nucleo.modulos.administrar"):
        return e_permiso is None or ctx.puede(e_permiso) or ctx.puede("nucleo.modulos.administrar")
    if e_roles and not (e_roles & mis_roles):
        return False
    return e_permiso is None or ctx.puede(e_permiso)


def _en_el_vocabulario(terminos: list[str], ind: Indice) -> list[str]:
    return busqueda.en_el_vocabulario(terminos, ind.df)


def buscar(bd: Session, ctx: Contexto, pregunta: str, *, limite: int = 6, con_significado: bool = True,
           solo_documentos: set[int] | None = None) -> tuple[list[Hallazgo], bool]:
    """Fragmentos más parecidos a la pregunta. Devuelve (hallazgos, si se usó la huella de significado)."""
    ind = indice(bd)
    mis_roles = roles_de(bd, ctx)
    visibles = [e for e in ind.entradas if puede_ver(e.roles, e.permiso, ctx, mis_roles)
                and (solo_documentos is None or e.documento_id in solo_documentos)]
    if not visibles:
        return [], False
    huella = None
    if con_significado and any(e.vector for e in visibles):
        huella = huella_pregunta(bd, pregunta, ctx.usuario.usuario_id)
    salida = busqueda.puntuar(visibles, pregunta, df=ind.df, n=len(ind.entradas), largo_promedio=ind.largo_promedio,
                              huella=huella, limite=limite)
    return salida, huella is not None


def hay_respaldo(hallazgos: list[Hallazgo]) -> bool:
    """Si lo encontrado parece hablar de la pregunta (por palabras o por significado)."""
    return busqueda.hay_respaldo(hallazgos, coseno_minimo=COSENO_MINIMO, cubre_minimo=CUBRE_MINIMO)
