"""Archivos de Innovación Vidanat: se guardan en el mismo almacén de la plataforma (nucleo.archivo), pero solo se
descargan por la ruta del módulo, que revisa el filtro de acceso. Los de clasificación «fórmula» se guardan cifrados
(Fernet con CLAVE_CIFRADO) y no se abren fuera de la plataforma. Los PDF restringidos salen con marca de agua.
"""
import hashlib
import io
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from core import cifrado
from core.config import configuracion
from nucleo.archivos import TIPOS, _nombre_seguro, _raiz
from nucleo.modelos import Archivo, Modulo, ahora

MODULO = "innovacion"
# Además de los tipos de la plataforma: presentaciones y texto
TIPOS_INNOVACION = {**TIPOS,
                    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", b"PK\x03\x04"),
                    ".txt": ("text/plain", None)}
IMAGENES = {"image/png", "image/jpeg", "image/webp"}


class ArchivoInvalido(ValueError):
    pass


def _fernet():
    return cifrado.fernet(cifrado.INNOVACION)


def cifrar(datos: bytes) -> bytes:
    return _fernet().encrypt(datos)


def descifrar(datos: bytes) -> bytes:
    try:
        return _fernet().decrypt(datos)
    except InvalidToken as e:
        raise ArchivoInvalido("No se pudo descifrar: la llave de cifrado (CLAVE_CIFRADO) cambió.") from e


MAX_MB = 40  # artículos y libros escaneados pesan más que los archivos de otros módulos


def guardar(bd: Session, nombre: str, contenido: bytes, *, usuario_id: int, cifrado: bool, maximo_mb: int | None = None) -> Archivo:
    nombre = _nombre_seguro(nombre)
    extension = Path(nombre).suffix.lower()
    if extension not in TIPOS_INNOVACION:
        permitidos = ", ".join(sorted({e.lstrip(".").upper() for e in TIPOS_INNOVACION}))
        raise ArchivoInvalido(f"«{nombre}»: ese tipo de archivo no se acepta. Se aceptan: {permitidos}.")
    tipo, firma = TIPOS_INNOVACION[extension]
    if not contenido:
        raise ArchivoInvalido(f"«{nombre}» está vacío.")
    if firma and not contenido.startswith(firma):
        raise ArchivoInvalido(f"«{nombre}»: el contenido no corresponde a la extensión.")
    maximo = (maximo_mb or max(MAX_MB, configuracion().archivos_mb_maximo)) * 1024 * 1024
    if len(contenido) > maximo:
        raise ArchivoInvalido(f"«{nombre}» pasa de {maximo // (1024 * 1024)} MB.")
    relativa = Path(ahora().strftime("%Y/%m")) / f"{uuid.uuid4().hex}{extension}{'.cif' if cifrado else ''}"
    destino = _raiz() / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(cifrar(contenido) if cifrado else contenido)
    modulo_id = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == MODULO))
    a = Archivo(modulo_id=modulo_id, entidad="recurso_version", nombre_original=nombre, tipo_contenido=tipo,
                tamano_bytes=len(contenido), sha256=hashlib.sha256(contenido).hexdigest(),
                ruta_almacenamiento=relativa.as_posix(), subido_por=usuario_id)
    bd.add(a)
    bd.flush()
    return a


def leer(a: Archivo, cifrado: bool) -> bytes:
    raiz = _raiz()
    ruta = (raiz / a.ruta_almacenamiento).resolve()
    if raiz not in ruta.parents or not ruta.is_file():
        raise ArchivoInvalido("El archivo ya no está en el almacén.")
    datos = ruta.read_bytes()
    return descifrar(datos) if cifrado else datos


@contextmanager
def en_disco(a: Archivo, cifrado: bool):
    """Ruta legible del archivo. Si está cifrado, se descifra en un temporal que se borra al terminar."""
    if not cifrado:
        yield (_raiz() / a.ruta_almacenamiento).resolve()
        return
    with tempfile.TemporaryDirectory(prefix="innovacion-") as carpeta:
        ruta = Path(carpeta) / f"archivo{Path(a.nombre_original).suffix.lower()}"
        ruta.write_bytes(leer(a, True))
        yield ruta


def marca_de_agua(pdf: bytes, texto: str) -> bytes:
    """Pone el texto en diagonal en cada página (nombre de quien descarga y fecha)."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.colors import Color
    from reportlab.pdfgen import canvas

    lector = PdfReader(io.BytesIO(pdf))
    escritor = PdfWriter()
    for pagina in lector.pages:
        ancho, alto = float(pagina.mediabox.width), float(pagina.mediabox.height)
        capa = io.BytesIO()
        c = canvas.Canvas(capa, pagesize=(ancho, alto))
        c.setFillColor(Color(0.85, 0.2, 0.15, alpha=0.18))
        c.setFont("Helvetica-Bold", 22)
        c.translate(ancho / 2, alto / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, texto)
        c.setFont("Helvetica", 9)
        c.drawCentredString(0, -18, "Documento restringido · Súper Naturista · Vidanat")
        c.save()
        capa.seek(0)
        pagina.merge_page(PdfReader(capa).pages[0])
        escritor.add_page(pagina)
    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()
