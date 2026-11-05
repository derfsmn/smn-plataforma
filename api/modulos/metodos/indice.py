"""Partir los documentos en fragmentos, ocultar datos personales, sacar su huella de significado y buscar.

La búsqueda junta dos listas: por palabras (BM25, sin acentos y sin palabras vacías) y por significado (coseno contra
la huella de Ollama). Si Ollama está apagado, solo busca por palabras. Solo se buscan fragmentos de documentos
vigentes que la persona puede ver (roles del documento y, para los que vienen de Compras o Fiscal, su permiso).
"""
import json
import math
import re
import struct
import threading
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.seguridad import Contexto
from ia import puerta
from modulos.metodos.modelos import Documento, Fragmento
from nucleo.lectura import Bloque

TAREA_HUELLA = "metodos.huella"
LARGO_FRAGMENTO = 1200  # caracteres; una sección más larga se parte en varios fragmentos
TANDA_HUELLAS = 32
# Umbrales de «sí hay de dónde contestar»; se ajustan con la prueba de las 40 preguntas
COSENO_MINIMO = 0.50
CUBRE_MINIMO = 0.5  # parte de la pregunta (por peso de cada palabra) que debe aparecer en el fragmento
VER_TODO = "metodos.aprobar"

VACIAS = set("""a al algo algun alguna algunas alguno algunos ante antes aqui asi aun cada como con contra cual cuales
cuando de del desde donde dos el ella ellas ellos en entre era es esa esas ese eso esos esta estan estas este esto estos
fue ha hace hacer hago hay la las le les lo los mas me mi mis mucho muy nada ni no nos o otra otro para pero poco por
porque puede pueden puedo que quien se segun ser si sin sobre son su sus tal tambien tanto te tiene tienen todo todos
tu un una uno unos y ya yo debo debe deben deber tengo tener tiene hago hace hacer hasta necesito necesita quiero
cual cuanto cuantos cuanta pasa sirve dar doy""".split())

PERSONALES = {
    "correo": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "curp": re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b"),
    "rfc": re.compile(r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b"),
    "telefono": re.compile(r"(?<![\d$])(?<!\d[.,])(?:\+?52[\s-]?)?(?:\(?\d{2,3}\)?[\s.-]?\d{3,4}[\s.-]\d{4}|\d{10})(?!\d|[.,]\d)"),
}
OCULTO = {"correo": "[correo oculto]", "curp": "[CURP oculta]", "rfc": "[RFC oculto]", "telefono": "[teléfono oculto]"}


# ---------------------------------------------------------------- texto

def sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def _raiz(palabra: str) -> str:
    """Raíz sencilla para que «proveedores» encuentre «proveedor», «devoluciones» a «devolución» y «recibo» a
    «recibir». No es perfecta; basta con que la pregunta y el manual queden igual."""
    palabra = re.sub(r"(?<=[aei]r)(la|lo|le|las|los|les|se)$", "", palabra)  # «recibirla» → «recibir»
    if palabra.endswith(("ciones", "siones")):
        palabra = palabra[:-2]
    elif len(palabra) > 4 and palabra.endswith("es") and palabra[-3] in "rlndzj":
        palabra = palabra[:-2]
    elif len(palabra) > 3 and palabra.endswith("s"):
        palabra = palabra[:-1]
    if len(palabra) > 5 and palabra[-2:] in ("ar", "er", "ir", "an", "en"):
        return palabra[:-2]
    if len(palabra) > 4 and palabra[-1] in "aeo":
        return palabra[:-1]
    return palabra


def palabras(texto: str) -> list[str]:
    return [_raiz(p) for p in re.findall(r"[a-z0-9ñ]+", sin_acentos(texto)) if len(p) > 1 and p not in VACIAS]


def ocultar_personales(texto: str) -> tuple[str, Counter]:
    """Cambia correos, CURP, RFC y teléfonos por una marca. Devuelve el texto y cuántos hubo de cada uno."""
    cuenta: Counter = Counter()
    for tipo, patron in PERSONALES.items():
        texto, n = patron.subn(OCULTO[tipo], texto)
        if n:
            cuenta[tipo] += n
    return texto, cuenta


# ---------------------------------------------------------------- fragmentos

@dataclass
class Pieza:
    seccion: str | None
    pagina: int | None
    texto: str


def partir(bloques: list[Bloque]) -> list[Pieza]:
    """Un fragmento por sección (título y lo que sigue); una sección larga se parte por párrafos."""
    ruta: list[str] = []
    piezas: list[Pieza] = []
    actual: list[str] = []
    pagina: int | None = None

    def cerrar():
        nonlocal actual, pagina
        texto = "\n".join(actual).strip()
        if texto:
            piezas.append(Pieza(" > ".join(ruta)[:400] or None, pagina, texto))
        actual, pagina = [], None

    for b in bloques:
        texto = b.texto.strip()
        if not texto:
            continue
        if b.nivel:
            cerrar()
            ruta[:] = ruta[:b.nivel - 1] + [texto[:150]]
            continue
        if actual and sum(len(t) for t in actual) + len(texto) > LARGO_FRAGMENTO:
            cerrar()
        if pagina is None:
            pagina = b.pagina
        actual.append(texto[:LARGO_FRAGMENTO * 3])
    cerrar()
    return piezas


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


def _empacar(v: list[float]) -> bytes:
    norma = math.sqrt(sum(x * x for x in v)) or 1.0
    return struct.pack(f"{len(v)}f", *(x / norma for x in v))


def _desempacar(b: bytes) -> tuple[float, ...]:
    return struct.unpack(f"{len(b) // 4}f", b)


def _texto_para_huella(f: Fragmento, titulo: str) -> str:
    return f"{titulo}. {f.seccion or ''}\n{f.texto}"[:4000]


def poner_huellas(bd: Session, fragmentos: list[Fragmento], *, usuario_id: int | None = None) -> int:
    """Huella de cada fragmento. Si Ollama no está, se quedan sin huella (la búsqueda por palabras sigue)."""
    hechos = 0
    for i in range(0, len(fragmentos), TANDA_HUELLAS):
        tanda = fragmentos[i:i + TANDA_HUELLAS]
        try:
            modelo, vectores = puerta.vectores(
                bd, TAREA_HUELLA, [_texto_para_huella(f, f.documento.titulo if f.documento else "") for f in tanda],
                usuario_id=usuario_id)
        except puerta.ErrorIA:
            break
        for f, v in zip(tanda, vectores):
            f.vector, f.modelo_vector = _empacar(v), modelo
            hechos += 1
    bd.flush()
    return hechos


def huella_pregunta(bd: Session, texto: str, usuario_id: int | None) -> tuple[str, tuple[float, ...]] | None:
    try:
        modelo, vectores = puerta.vectores(bd, TAREA_HUELLA, [texto], usuario_id=usuario_id)
    except puerta.ErrorIA:
        return None
    return modelo, _desempacar(_empacar(vectores[0]))


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
    """Una palabra que ningún manual tiene se cambia por la más común que empieza igual («devolver» → «devolución»)."""
    salida = []
    for t in terminos:
        if t in ind.df or len(t) < 5:
            salida.append(t)
            continue
        parecidas = [v for v in ind.df if v[:5] == t[:5]]
        salida.append(max(parecidas, key=ind.df.get) if parecidas else t)
    return salida


@dataclass
class Hallazgo:
    entrada: Entrada
    puntos: float
    bm25: float
    coseno: float | None
    cubre: float  # parte de las palabras de la pregunta que aparecen


def buscar(bd: Session, ctx: Contexto, pregunta: str, *, limite: int = 6, con_significado: bool = True,
           solo_documentos: set[int] | None = None) -> tuple[list[Hallazgo], bool]:
    """Fragmentos más parecidos a la pregunta. Devuelve (hallazgos, si se usó la huella de significado)."""
    ind = indice(bd)
    mis_roles = roles_de(bd, ctx)
    visibles = [e for e in ind.entradas if puede_ver(e.roles, e.permiso, ctx, mis_roles)
                and (solo_documentos is None or e.documento_id in solo_documentos)]
    if not visibles:
        return [], False
    consulta = list(dict.fromkeys(_en_el_vocabulario(palabras(pregunta), ind)))
    n = len(ind.entradas)
    k1, b = 1.4, 0.75
    bm25: dict[int, float] = {}
    cubre: dict[int, float] = {}
    # una palabra rara pesa más: si la pregunta habla de «vacaciones» y ningún manual la tiene, no basta con «días»
    idf = {t: math.log(1 + (n - ind.df[t] + 0.5) / (ind.df[t] + 0.5)) for t in consulta}
    peso_total = sum(idf.values()) or 1
    for e in visibles:
        largo = sum(e.terminos.values()) or 1
        puntos, presentes = 0.0, 0.0
        for t in consulta:
            tf = e.terminos.get(t, 0)
            if not tf:
                continue
            presentes += idf[t]
            puntos += idf[t] * tf * (k1 + 1) / (tf + k1 * (1 - b + b * largo / ind.largo_promedio))
        if puntos:
            bm25[e.fragmento_id] = puntos
            cubre[e.fragmento_id] = presentes / peso_total

    cosenos: dict[int, float] = {}
    usada = False
    if con_significado and any(e.vector for e in visibles):
        if h := huella_pregunta(bd, pregunta, ctx.usuario.usuario_id):
            modelo, q = h
            usada = True
            for e in visibles:
                if e.vector and e.modelo == modelo and len(e.vector) == len(q):
                    cosenos[e.fragmento_id] = sum(x * y for x, y in zip(e.vector, q))

    # Rango recíproco: junta las dos listas sin tener que comparar puntos de escalas distintas
    puntos: Counter = Counter()
    for lista in (bm25, {k: v for k, v in cosenos.items() if v > 0.2}):
        for rango, fid in enumerate(sorted(lista, key=lista.get, reverse=True)[:50]):
            puntos[fid] += 1 / (60 + rango)
    por_id = {e.fragmento_id: e for e in visibles}
    salida = [Hallazgo(por_id[fid], p, bm25.get(fid, 0.0), cosenos.get(fid), cubre.get(fid, 0.0))
              for fid, p in puntos.most_common(limite)]
    return salida, usada


def hay_respaldo(hallazgos: list[Hallazgo]) -> bool:
    """Si lo encontrado parece hablar de la pregunta (por palabras o por significado)."""
    return any((h.coseno is not None and h.coseno >= COSENO_MINIMO) or h.cubre >= CUBRE_MINIMO for h in hallazgos)
