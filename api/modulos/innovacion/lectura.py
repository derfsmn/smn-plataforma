"""Leer una fuente de Vidanat: PDF (con OCR local cuando una página no trae texto), Word, Excel, CSV, PowerPoint y texto.

El OCR usa Tesseract (español e inglés) y pdftoppm, que van en la imagen de la API. Si no están, la página escaneada
queda sin texto y la fuente avisa «no se pudo leer»; nunca tumba la carga.
"""
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from nucleo.lectura import Bloque, bloques_de_texto, extraer_bloques

PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
MINIMO_TEXTO_PAGINA = 40  # caracteres; menos que eso en una página de PDF se considera escaneada
MAXIMO_PAGINAS_OCR = 200


def hay_ocr() -> bool:
    return bool(shutil.which("tesseract") and shutil.which("pdftoppm"))


def _ocr_imagen(ruta: Path) -> str:
    r = subprocess.run(["tesseract", str(ruta), "stdout", "-l", "spa+eng", "--psm", "3"],
                       capture_output=True, timeout=180, check=False)
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""


def _ocr_pagina(pdf: Path, pagina: int, carpeta: Path) -> str:
    base = carpeta / f"p{pagina}"
    r = subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", "-f", str(pagina), "-l", str(pagina), str(pdf), str(base)],
                       capture_output=True, timeout=180, check=False)
    if r.returncode != 0:
        return ""
    imagenes = sorted(carpeta.glob(f"p{pagina}*.png"))
    texto = "\n".join(_ocr_imagen(i) for i in imagenes)
    for i in imagenes:
        i.unlink(missing_ok=True)
    return texto


def _parrafos(texto: str, pagina: int) -> list[Bloque]:
    salida = []
    for p in re.split(r"\n\s*\n", texto):
        limpio = " ".join(p.split())
        if limpio:
            salida.append(Bloque(limpio, 0, pagina))
    return salida


def _pdf(ruta: Path) -> tuple[list[Bloque], int]:
    """Bloques del PDF y cuántas páginas pasaron por OCR."""
    from pypdf import PdfReader

    bloques = extraer_bloques(ruta, "application/pdf")
    try:
        total = len(PdfReader(str(ruta)).pages)
    except Exception:  # noqa: BLE001 - PDF dañado
        return bloques, 0
    con_texto: dict[int, int] = {}
    for b in bloques:
        if b.pagina:
            con_texto[b.pagina] = con_texto.get(b.pagina, 0) + len(b.texto)
    escaneadas = [n for n in range(1, min(total, MAXIMO_PAGINAS_OCR) + 1) if con_texto.get(n, 0) < MINIMO_TEXTO_PAGINA]
    if not escaneadas or not hay_ocr():
        return bloques, 0
    nuevos: dict[int, list[Bloque]] = {}
    with tempfile.TemporaryDirectory(prefix="ocr-") as carpeta:
        for n in escaneadas:
            if texto := _ocr_pagina(ruta, n, Path(carpeta)).strip():
                nuevos[n] = _parrafos(texto, n)
    if not nuevos:
        return bloques, 0
    salida = [b for b in bloques if b.pagina not in nuevos]
    for n, bs in nuevos.items():
        salida += bs
    salida.sort(key=lambda b: b.pagina or 0)  # sort estable: conserva el orden dentro de cada página
    return salida, len(nuevos)


def _pptx(ruta: Path) -> list[Bloque]:
    bloques = []
    with zipfile.ZipFile(ruta) as z:
        laminas = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                         key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        for numero, nombre in enumerate(laminas, start=1):
            raiz = ElementTree.fromstring(z.read(nombre))
            parrafos = ["".join(t.text or "" for t in p.iter(f"{A}t")).strip() for p in raiz.iter(f"{A}p")]
            parrafos = [p for p in parrafos if p]
            if not parrafos:
                continue
            bloques.append(Bloque(f"Lámina {numero}: {parrafos[0][:140]}", 1, numero))
            bloques += [Bloque(p, 0, numero) for p in parrafos[1:]]
    return bloques


def leer(ruta: Path, tipo: str) -> tuple[list[Bloque], dict]:
    """Bloques y un resumen de cómo se leyó: {"ocr_paginas": n, "imagen": bool}."""
    try:
        if tipo == "application/pdf":
            bloques, ocr = _pdf(ruta)
            return bloques, {"ocr_paginas": ocr}
        if tipo == PPTX:
            return _pptx(ruta), {}
        if tipo == "text/plain":
            return bloques_de_texto(ruta.read_text(encoding="utf-8", errors="replace")), {}
        if tipo.startswith("image/"):
            texto = _ocr_imagen(ruta).strip() if shutil.which("tesseract") else ""
            return (_parrafos(texto, 1) if texto else []), {"imagen": True, "ocr_paginas": 1 if texto else 0}
    except Exception:  # noqa: BLE001 - un archivo dañado no debe tumbar el procesamiento
        return [], {}
    return extraer_bloques(ruta, tipo), {}
