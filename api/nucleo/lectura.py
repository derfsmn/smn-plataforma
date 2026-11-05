"""Sacar el texto de un archivo (PDF, Word, Excel, CSV) para que la plataforma lo lea.

`extraer_bloques` conserva la forma del documento (títulos con su nivel y página) para partirlo por sección;
`extraer_texto` da todo junto, para usarlo como contexto. Un archivo dañado regresa vacío, nunca tumba la subida.
Un PDF escaneado (solo imágenes) también regresa vacío: quien lo carga recibe el aviso de que no se pudo leer.
"""
import csv
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

PDF = "application/pdf"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# Estilos de título de Word en inglés y en español («Heading1», «Ttulo1», «Título 1»)
ESTILO_TITULO = re.compile(r"^(heading|t[ií]?tulo)\s*(\d)$", re.IGNORECASE)
# Títulos en PDF: «1. Objetivo», «4.2 Recepción», «CAPÍTULO 3», o una línea corta en mayúsculas
TITULO_NUMERADO = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-ZÁÉÍÓÚÑ][^.:;]{2,90})$")
TITULO_MAYUSCULAS = re.compile(r"^[A-ZÁÉÍÓÚÑ0-9 ,()/-]{4,80}$")


@dataclass
class Bloque:
    texto: str
    nivel: int = 0  # 0 = párrafo; 1, 2, 3 = título de ese nivel
    pagina: int | None = None


def _pdf(ruta: Path) -> list[Bloque]:
    from pypdf import PdfReader

    bloques = []
    for n, pagina in enumerate(PdfReader(str(ruta)).pages[:500], start=1):
        parrafo: list[str] = []
        for linea in (pagina.extract_text() or "").splitlines():
            limpia = linea.strip()
            if not limpia:
                if parrafo:
                    bloques.append(Bloque(" ".join(parrafo), 0, n))
                    parrafo = []
                continue
            if m := TITULO_NUMERADO.match(limpia):
                nivel = min(m.group(1).count(".") + 1, 3)
            elif TITULO_MAYUSCULAS.match(limpia) and any(c.isalpha() for c in limpia) and len(limpia.split()) <= 10:
                nivel = 1
            else:
                parrafo.append(limpia)
                continue
            if parrafo:
                bloques.append(Bloque(" ".join(parrafo), 0, n))
                parrafo = []
            bloques.append(Bloque(limpia, nivel, n))
        if parrafo:
            bloques.append(Bloque(" ".join(parrafo), 0, n))
    return bloques


def _word(ruta: Path) -> list[Bloque]:
    with zipfile.ZipFile(ruta) as z:
        raiz = ElementTree.fromstring(z.read("word/document.xml"))
    cuerpo = raiz.find(f"{W}body")
    bloques = []
    for nodo in (cuerpo if cuerpo is not None else []):
        if nodo.tag == f"{W}p":
            texto = "".join(t.text or "" for t in nodo.iter(f"{W}t")).strip()
            if not texto:
                continue
            estilo = nodo.find(f"{W}pPr/{W}pStyle")
            nombre = (estilo.get(f"{W}val") if estilo is not None else "") or ""
            m = ESTILO_TITULO.match(nombre.replace("í", "i").strip())
            nivel = min(int(m.group(2)), 3) if m else 0
            if nombre.lower() in ("title", "titulo", "título"):
                nivel = 1
            con_lista = nodo.find(f"{W}pPr/{W}numPr") is not None
            bloques.append(Bloque(("- " if con_lista and not nivel else "") + texto, nivel))
        elif nodo.tag == f"{W}tbl":
            for fila in nodo.iter(f"{W}tr"):
                celdas = ["".join(t.text or "" for t in c.iter(f"{W}t")).strip() for c in fila.iter(f"{W}tc")]
                if any(celdas):
                    bloques.append(Bloque(" | ".join(celdas)))
    return bloques


def _excel(ruta: Path) -> list[Bloque]:
    from openpyxl import load_workbook

    libro = load_workbook(ruta, read_only=True, data_only=True)
    bloques = []
    try:
        for hoja in libro.worksheets:
            bloques.append(Bloque(hoja.title, 1))
            for fila in hoja.iter_rows(values_only=True, max_row=5000):
                celdas = ["" if v is None else str(v).strip() for v in fila]
                if any(celdas):
                    bloques.append(Bloque(" | ".join(c for c in celdas if c)))
    finally:
        libro.close()
    return bloques


def _csv(ruta: Path) -> list[Bloque]:
    texto = ruta.read_text(encoding="utf-8-sig", errors="replace")
    return [Bloque(" | ".join(c.strip() for c in fila if c.strip()))
            for fila in csv.reader(io.StringIO(texto)) if any(c.strip() for c in fila)]


def bloques_de_texto(texto: str) -> list[Bloque]:
    """Texto con títulos al estilo Markdown («# Título», «## Subtítulo») en bloques; así se guardan los borradores."""
    bloques, parrafo = [], []
    for linea in texto.splitlines():
        limpia = linea.strip()
        m = re.match(r"^(#{1,6})\s+(.+)$", limpia)
        if m or not limpia:
            if parrafo:
                bloques.append(Bloque(" ".join(parrafo)))
                parrafo = []
            if m:
                bloques.append(Bloque(m.group(2).strip(), min(len(m.group(1)), 3)))
            continue
        if re.match(r"^([-*•]|\d+[.)])\s+", limpia):  # cada viñeta o paso es su propio párrafo
            if parrafo:
                bloques.append(Bloque(" ".join(parrafo)))
                parrafo = []
            bloques.append(Bloque(limpia))
            continue
        parrafo.append(limpia)
    if parrafo:
        bloques.append(Bloque(" ".join(parrafo)))
    return bloques


def extraer_bloques(ruta: Path, tipo: str) -> list[Bloque]:
    try:
        if tipo == PDF:
            return _pdf(ruta)
        if tipo.endswith("wordprocessingml.document"):
            return _word(ruta)
        if tipo.endswith("spreadsheetml.sheet"):
            return _excel(ruta)
        if tipo == "text/csv":
            return _csv(ruta)
    except Exception:  # noqa: BLE001 - un archivo dañado no debe tumbar la subida
        return []
    return []


def extraer_texto(ruta: Path, tipo: str) -> str:
    """Texto de un PDF, Word, Excel o CSV, todo junto."""
    return "\n".join(b.texto for b in extraer_bloques(ruta, tipo))
