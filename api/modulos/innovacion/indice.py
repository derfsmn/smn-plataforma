"""Índice en memoria de las secciones de las fuentes de Vidanat y búsqueda con filtro de acceso.

Cada sección guarda la clasificación y el folio de su fuente. El índice se separa por clasificación y solo se
consulta lo que la persona puede ver: el filtro va ANTES del puntaje, y la rareza de cada palabra (BM25) se calcula
solo con lo visible, para que lo oculto no cambie ni el orden ni el total.
"""
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from modulos.innovacion.acceso import Acceso
from modulos.innovacion.modelos import Seccion, Recurso, RecursoVersion, Vinculo
from nucleo import busqueda

TAREA_HUELLA = "innovacion.huella"
COSENO_MINIMO = 0.50
CUBRE_MINIMO = 0.5


@dataclass
class Entrada:
    fragmento_id: int
    version_id: int
    recurso_id: int
    numero: int
    titulo: str
    tipo: str
    estado: str  # de la versión: pendiente / revisado / sustituido
    clasificacion: str
    expediente_id: int | None
    seccion: str | None
    pagina: int | None
    texto: str
    terminos: Counter
    vector: tuple[float, ...] | None
    modelo: str | None
    vigente_hasta: date | None
    ingredientes: set[int] = field(default_factory=set)
    categorias: set[str] = field(default_factory=set)
    folios: set[int] = field(default_factory=set)


@dataclass
class Indice:
    firma: tuple
    entradas: list[Entrada] = field(default_factory=list)


_cache: Indice | None = None
_lock = threading.Lock()


def olvidar() -> None:
    global _cache
    with _lock:
        _cache = None


def _firma(bd: Session) -> tuple:
    f = bd.execute(select(func.count(Seccion.fragmento_id), func.max(Seccion.fragmento_id),
                          func.count(Seccion.vector))).one()
    v = bd.execute(select(func.checksum_agg(func.binary_checksum(RecursoVersion.version_id, RecursoVersion.estado,
                                                                 RecursoVersion.vigente_hasta)))).scalar()
    r = bd.execute(select(func.checksum_agg(func.binary_checksum(Recurso.recurso_id, Recurso.clasificacion,
                                                                 Recurso.expediente_id, Recurso.estado, Recurso.titulo)))).scalar()
    k = bd.execute(select(func.count(Vinculo.vinculo_id), func.max(Vinculo.vinculo_id))).one()
    return tuple(f) + (v, r) + tuple(k)


def indice(bd: Session) -> Indice:
    global _cache
    firma = _firma(bd)
    with _lock:
        if _cache and _cache.firma == firma:
            return _cache
    nuevo = Indice(firma)
    vinculos: dict[int, list[Vinculo]] = {}
    for v in bd.scalars(select(Vinculo)):
        vinculos.setdefault(v.version_id, []).append(v)
    filas = bd.execute(
        select(Seccion.fragmento_id, Seccion.version_id, Seccion.seccion, Seccion.pagina, Seccion.texto,
               Seccion.vector, Seccion.modelo_vector, RecursoVersion.recurso_id, RecursoVersion.numero,
               RecursoVersion.estado, RecursoVersion.vigente_hasta, Recurso.titulo, Recurso.tipo,
               Recurso.clasificacion, Recurso.expediente_id)
        .join(RecursoVersion, RecursoVersion.version_id == Seccion.version_id)
        .join(Recurso, Recurso.recurso_id == RecursoVersion.recurso_id)
        .where(Recurso.estado == "activo"))
    for (fid, vid, seccion, pagina, texto, vector, modelo, rid, numero, estado, hasta, titulo, tipo, clas,
         exp) in filas:
        terminos = Counter(busqueda.palabras(texto) + busqueda.palabras(f"{titulo} {seccion or ''}") * 2)
        vs = vinculos.get(vid, [])
        nuevo.entradas.append(Entrada(
            fid, vid, rid, numero, titulo, tipo, estado, clas, exp, seccion, pagina, texto, terminos,
            busqueda.desempacar(vector) if vector else None, modelo, hasta,
            {v.ingrediente_id for v in vs if v.ingrediente_id}, {v.categoria for v in vs if v.categoria},
            {v.expediente_id for v in vs if v.expediente_id}))
    with _lock:
        _cache = nuevo
    return nuevo


def visibles(bd: Session, acc: Acceso) -> list[Entrada]:
    return [e for e in indice(bd).entradas if acc.ve(e.clasificacion, e.expediente_id)]


@dataclass
class Filtros:
    tipo: str | None = None
    ingrediente_id: int | None = None
    categoria: str | None = None
    estado: str | None = None  # pendiente / revisado / sustituido; por omisión no se muestran las sustituidas
    vigente: bool | None = None
    expediente_id: int | None = None
    solo_revisadas: bool = False


def _pasa(e: Entrada, f: Filtros, hoy: date) -> bool:
    if f.tipo and e.tipo != f.tipo:
        return False
    if f.ingrediente_id and f.ingrediente_id not in e.ingredientes:
        return False
    if f.categoria and f.categoria not in e.categorias:
        return False
    if f.estado and e.estado != f.estado:
        return False
    if not f.estado and e.estado == "sustituido":
        return False
    if f.solo_revisadas and e.estado != "revisado":
        return False
    if f.vigente is True and e.vigente_hasta and e.vigente_hasta < hoy:
        return False
    if f.expediente_id and f.expediente_id not in e.folios and e.expediente_id != f.expediente_id:
        return False
    return True


def buscar(bd: Session, acc: Acceso, texto: str, filtros: Filtros | None = None, *, limite: int = 20,
           con_significado: bool = True) -> tuple[list[busqueda.Hallazgo], bool]:
    """Secciones más parecidas, solo entre lo visible y lo que pasa los filtros."""
    f = filtros or Filtros()
    hoy = date.today()
    lista = [e for e in visibles(bd, acc) if _pasa(e, f, hoy)]
    if not lista or not texto.strip():
        return [], False
    df, largo = busqueda.frecuencias(lista)
    huella = None
    if con_significado and any(e.vector for e in lista):
        huella = busqueda.huella_texto(bd, TAREA_HUELLA, texto, acc.usuario_id)
    return busqueda.puntuar(lista, texto, df=df, n=len(lista), largo_promedio=largo, huella=huella,
                            limite=limite), huella is not None


def hay_respaldo(hallazgos) -> bool:
    return busqueda.hay_respaldo(hallazgos, coseno_minimo=COSENO_MINIMO, cubre_minimo=CUBRE_MINIMO)
