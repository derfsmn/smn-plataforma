"""Motor de búsqueda compartido: texto sin acentos, partición en secciones, huellas de significado y puntaje.

Salió de modulos/metodos/indice.py (2026-11-22) para que Métodos y procedimientos (TD004) e Innovación Vidanat (TD005)
usen el mismo motor. Cada módulo arma su propio índice y su filtro de acceso; aquí no se sabe quién puede ver qué:
quien llama pasa solo las entradas visibles.

Puntaje: dos listas, por palabras (BM25, sin acentos ni palabras vacías) y por significado (coseno contra la huella
de Ollama), que se juntan por rango recíproco. Si Ollama está apagado, solo por palabras.
"""
import math
import re
import struct
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from ia import puerta
from nucleo.lectura import Bloque

LARGO_FRAGMENTO = 1200  # caracteres; una sección más larga se parte en varios fragmentos
TANDA_HUELLAS = 32

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


def raiz(palabra: str) -> str:
    """Raíz sencilla para que «proveedores» encuentre «proveedor», «devoluciones» a «devolución» y «recibo» a
    «recibir». No es perfecta; basta con que la pregunta y el texto queden igual."""
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
    return [raiz(p) for p in re.findall(r"[a-z0-9ñ]+", sin_acentos(texto)) if len(p) > 1 and p not in VACIAS]


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


def partir(bloques: list[Bloque], largo: int = LARGO_FRAGMENTO, *, por_pagina: bool = False) -> list[Pieza]:
    """Un fragmento por sección (título y lo que sigue); una sección larga se parte por párrafos. Con `por_pagina`,
    un cambio de página también cierra el fragmento, para citar la página exacta."""
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
        if actual and (sum(len(t) for t in actual) + len(texto) > largo
                       or (por_pagina and b.pagina is not None and b.pagina != pagina)):
            cerrar()
        if pagina is None:
            pagina = b.pagina
        actual.append(texto[:largo * 3])
    cerrar()
    return piezas


# ---------------------------------------------------------------- huellas

def empacar(v: list[float]) -> bytes:
    norma = math.sqrt(sum(x * x for x in v)) or 1.0
    return struct.pack(f"{len(v)}f", *(x / norma for x in v))


def desempacar(b: bytes) -> tuple[float, ...]:
    return struct.unpack(f"{len(b) // 4}f", b)


def huellas(bd: Session, tarea: str, textos: list[str], *, usuario_id: int | None = None) -> tuple[str | None, list[bytes | None]]:
    """Huella empacada de cada texto, por tandas. Si Ollama falla a la mitad, las que faltan quedan en None."""
    salida: list[bytes | None] = [None] * len(textos)
    modelo = None
    for i in range(0, len(textos), TANDA_HUELLAS):
        try:
            modelo, vectores = puerta.vectores(bd, tarea, textos[i:i + TANDA_HUELLAS], usuario_id=usuario_id)
        except puerta.ErrorIA:
            break
        for j, v in enumerate(vectores):
            salida[i + j] = empacar(v)
    return modelo, salida


def huella_texto(bd: Session, tarea: str, texto: str, usuario_id: int | None) -> tuple[str, tuple[float, ...]] | None:
    try:
        modelo, vectores = puerta.vectores(bd, tarea, [texto], usuario_id=usuario_id)
    except puerta.ErrorIA:
        return None
    return modelo, desempacar(empacar(vectores[0]))


# ---------------------------------------------------------------- puntaje

class EntradaBuscable(Protocol):
    fragmento_id: int
    terminos: Counter
    vector: tuple[float, ...] | None
    modelo: str | None


@dataclass
class Hallazgo:
    entrada: object
    puntos: float
    bm25: float
    coseno: float | None
    cubre: float  # parte de las palabras de la pregunta (por peso) que aparecen


def en_el_vocabulario(terminos: list[str], df: Counter) -> list[str]:
    """Una palabra que ningún texto tiene se cambia por la más común que empieza igual («devolver» → «devolución»)."""
    salida = []
    for t in terminos:
        if t in df or len(t) < 5:
            salida.append(t)
            continue
        parecidas = [v for v in df if v[:5] == t[:5]]
        salida.append(max(parecidas, key=df.get) if parecidas else t)
    return salida


def frecuencias(entradas: list[EntradaBuscable]) -> tuple[Counter, float]:
    """En cuántas entradas aparece cada palabra y el largo promedio, para el BM25."""
    df: Counter = Counter()
    total = 0
    for e in entradas:
        df.update(e.terminos.keys())
        total += sum(e.terminos.values())
    return df, (total / len(entradas) if entradas else 1.0)


def puntuar(visibles: list[EntradaBuscable], pregunta: str, *, df: Counter, n: int, largo_promedio: float,
            huella: tuple[str, tuple[float, ...]] | None, limite: int = 6) -> list[Hallazgo]:
    """Ordena las entradas visibles. `df`, `n` y `largo_promedio` son del conjunto contra el que se calcula la rareza
    de cada palabra (Métodos usa todo su índice; Innovación, solo lo que la persona puede ver)."""
    if not visibles:
        return []
    consulta = list(dict.fromkeys(en_el_vocabulario(palabras(pregunta), df)))
    k1, b = 1.4, 0.75
    bm25: dict[int, float] = {}
    cubre: dict[int, float] = {}
    # una palabra rara pesa más: si la pregunta habla de «vacaciones» y ningún texto la tiene, no basta con «días»
    idf = {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in consulta}
    peso_total = sum(idf.values()) or 1
    for e in visibles:
        largo = sum(e.terminos.values()) or 1
        puntos, presentes = 0.0, 0.0
        for t in consulta:
            tf = e.terminos.get(t, 0)
            if not tf:
                continue
            presentes += idf[t]
            puntos += idf[t] * tf * (k1 + 1) / (tf + k1 * (1 - b + b * largo / largo_promedio))
        if puntos:
            bm25[e.fragmento_id] = puntos
            cubre[e.fragmento_id] = presentes / peso_total

    cosenos: dict[int, float] = {}
    if huella:
        modelo, q = huella
        for e in visibles:
            if e.vector and e.modelo == modelo and len(e.vector) == len(q):
                cosenos[e.fragmento_id] = sum(x * y for x, y in zip(e.vector, q))

    # Rango recíproco: junta las dos listas sin tener que comparar puntos de escalas distintas
    puntos_rrf: Counter = Counter()
    for lista in (bm25, {k: v for k, v in cosenos.items() if v > 0.2}):
        for rango, fid in enumerate(sorted(lista, key=lista.get, reverse=True)[:50]):
            puntos_rrf[fid] += 1 / (60 + rango)
    por_id = {e.fragmento_id: e for e in visibles}
    return [Hallazgo(por_id[fid], p, bm25.get(fid, 0.0), cosenos.get(fid), cubre.get(fid, 0.0))
            for fid, p in puntos_rrf.most_common(limite)]


def hay_respaldo(hallazgos: list[Hallazgo], *, coseno_minimo: float, cubre_minimo: float) -> bool:
    """Si lo encontrado parece hablar de la pregunta (por palabras o por significado)."""
    return any((h.coseno is not None and h.coseno >= coseno_minimo) or h.cubre >= cubre_minimo for h in hallazgos)
