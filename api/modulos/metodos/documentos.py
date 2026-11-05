"""Alta de documentos y versiones, y traer a la búsqueda los documentos que ya viven en otras bases (Compras y Fiscal).

Los de otras bases se siguen cargando donde hoy; aquí solo se copian su texto y su permiso para poder citarlos.
"""
import json
import tempfile
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from modulos.metodos import indice
from modulos.metodos.modelos import Documento
from nucleo.archivos import _raiz
from nucleo.lectura import Bloque, bloques_de_texto, extraer_bloques
from nucleo.modelos import Archivo, ahora

TIPOS = {"manual": "Manual de procedimientos", "politica": "Política", "instructivo": "Instructivo o paso a paso",
         "formato": "Formato o plantilla", "preguntas": "Preguntas frecuentes", "otro": "Otro"}
AVISO_PERSONALES = {"correo": "correos", "telefono": "teléfonos", "rfc": "RFC", "curp": "CURP"}
VIEJO_DIAS = 730  # sin fecha de revisión, un manual con más de dos años se avisa como viejo


class ErrorDocumento(Exception):
    pass


def bloques_de_archivo(a: Archivo) -> list[Bloque]:
    return extraer_bloques(_raiz() / a.ruta_almacenamiento, a.tipo_contenido)


def avisos_en_palabras(doc: Documento) -> list[str]:
    salida = []
    if doc.avisos:
        cuenta = json.loads(doc.avisos)
        partes = [f"{n} {AVISO_PERSONALES.get(k, k)}" for k, n in cuenta.items()]
        salida.append("Se encontraron datos de personas (" + ", ".join(partes) + "). Se ocultaron para contestar, "
                      "pero el archivo original los tiene: si no deben estar, carga una versión sin ellos.")
    if doc.origen in ("cargado", "ia") and doc.estado == "vigente" and not doc.texto:
        salida.append("No se pudo leer texto de este archivo (¿es un PDF escaneado?). No se usa para contestar.")
    return salida


def viejo(doc: Documento, hoy: date | None = None) -> str | None:
    """Por qué un manual vigente necesita revisión, o None."""
    hoy = hoy or date.today()
    if doc.revisar_antes and doc.revisar_antes < hoy:
        return f"Su fecha de revisión era el {doc.revisar_antes:%d/%m/%Y}."
    if not doc.revisar_antes and doc.vigente_desde and (hoy - doc.vigente_desde).days > VIEJO_DIAS:
        return f"Está vigente desde el {doc.vigente_desde:%d/%m/%Y} y no tiene fecha de revisión."
    return None


def cargar(bd: Session, *, archivo: Archivo, titulo: str, tipo: str, area: str, version: str,
           vigente_desde: date | None, revisar_antes: date | None, clave: str | None, sistema: str | None,
           roles: list[str], usuario_id: int, reemplaza: Documento | None = None) -> tuple[Documento, dict]:
    bloques = bloques_de_archivo(archivo)
    doc = Documento(clave=clave, titulo=titulo, tipo=tipo, area=area, version=version, vigente_desde=vigente_desde,
                    revisar_antes=revisar_antes, sistema=sistema, roles=json.dumps(sorted(set(roles))) if roles else None,
                    estado="vigente", origen="cargado", archivo_id=archivo.archivo_id,
                    reemplaza_a=reemplaza.documento_id if reemplaza else None, cargado_por=usuario_id,
                    aprobado_por=usuario_id, aprobado_en=ahora())
    bd.add(doc)
    bd.flush()
    resumen = indice.indexar(bd, doc, bloques, usuario_id=usuario_id)
    if reemplaza:
        reemplaza.estado = "reemplazado"
    return doc, resumen


def publicar_texto(bd: Session, *, titulo: str, tipo: str, area: str, version: str, texto: str, usuario_id: int,
                   aprobado_por: int, reemplaza: Documento | None, roles: str | None, clave: str | None,
                   sistema: str | None, flujo: str | None = None) -> Documento:
    """Documento hecho por la IA y aprobado por el área: vale desde hoy y reemplaza al anterior, si hay."""
    doc = Documento(clave=clave, titulo=titulo, tipo=tipo, area=area, version=version, vigente_desde=date.today(),
                    sistema=sistema, roles=roles, estado="vigente", origen="ia",
                    reemplaza_a=reemplaza.documento_id if reemplaza else None, cargado_por=usuario_id,
                    aprobado_por=aprobado_por, aprobado_en=ahora(), flujo=flujo)
    bd.add(doc)
    bd.flush()
    indice.indexar(bd, doc, bloques_de_texto(texto), usuario_id=aprobado_por)
    if reemplaza:
        reemplaza.estado = "reemplazado"
    return doc


def siguiente_version(version: str | None) -> str:
    """«1.0» → «2.0», «3» → «4»; si no es número, agrega «.1»."""
    if not version:
        return "1.0"
    base = version.strip().lstrip("vV")
    entero = base.split(".")[0]
    if entero.isdigit():
        return f"{int(entero) + 1}.0" if "." in base else str(int(entero) + 1)
    return f"{version}.1"


# ---------------------------------------------------------------- otras bases

def _sincronizar_uno(bd: Session, origen: str, origen_id: int, *, titulo: str, area: str, version: str,
                     vigente_desde: date | None, permiso: str, activo: bool, bloques_fn) -> str:
    doc = bd.scalar(select(Documento).where(Documento.origen == origen, Documento.origen_id == origen_id))
    if not activo:
        if doc and doc.estado == "vigente":
            doc.estado = "retirado"
            indice.olvidar_cache()
            return "retirado"
        return "igual"
    if doc and doc.titulo == titulo and doc.version == version and doc.estado == "vigente" and doc.texto is not None:
        return "igual"
    nuevo = doc is None
    if nuevo:
        doc = Documento(origen=origen, origen_id=origen_id, tipo="otro", cargado_en=ahora())
        bd.add(doc)
    doc.titulo, doc.area, doc.version, doc.vigente_desde = titulo[:300], area, version[:30], vigente_desde
    doc.permiso, doc.estado = permiso, "vigente"
    bd.flush()
    indice.indexar(bd, doc, bloques_fn())
    return "nuevo" if nuevo else "actualizado"


def sincronizar_otras_bases(bd: Session) -> dict:
    """Trae los documentos de la Base de conocimiento de Compras (radar) y los de soporte de la Base fiscal."""
    from modulos.compras.modelos import RadarDocumento
    from modulos.contraloria.modelos_diot import FiscalDocumento

    cuenta: dict[str, int] = {}
    for d in bd.scalars(select(RadarDocumento)):
        r = _sincronizar_uno(bd, "compras", d.documento_id, titulo=d.titulo, area="Compras", version="1",
                             vigente_desde=d.subido_en.date() if d.subido_en else None, permiso="compras.radar.ver",
                             activo=d.activo and bool(d.texto), bloques_fn=lambda d=d: bloques_de_texto(d.texto or ""))
        cuenta[r] = cuenta.get(r, 0) + 1

    def bloques_fiscal(f: FiscalDocumento) -> list[Bloque]:
        extension = Path(f.nombre_archivo or "").suffix.lower()
        tipo = {".pdf": "application/pdf", ".csv": "text/csv",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}.get(extension)
        if not tipo or not f.contenido:
            return []
        with tempfile.NamedTemporaryFile(suffix=extension) as t:
            t.write(f.contenido)
            t.flush()
            return extraer_bloques(Path(t.name), tipo)

    for f in bd.scalars(select(FiscalDocumento)):
        r = _sincronizar_uno(bd, "fiscal", f.documento_id, titulo=f.titulo, area="Contraloría / Fiscal",
                             version=f.version or "1", vigente_desde=f.vigente_desde, permiso="contraloria.diot.ver",
                             activo=f.activo and bool(f.contenido), bloques_fn=lambda f=f: bloques_fiscal(f))
        cuenta[r] = cuenta.get(r, 0) + 1
    bd.commit()
    return cuenta


def reindexar(bd: Session, doc: Documento, usuario_id: int | None) -> dict:
    """Vuelve a partir y a sacar la huella (por ejemplo, después de prender Ollama)."""
    if doc.origen == "ia":
        return indice.indexar(bd, doc, bloques_de_texto(doc.texto or ""), usuario_id=usuario_id)
    if doc.archivo_id:
        return indice.indexar(bd, doc, bloques_de_archivo(bd.get(Archivo, doc.archivo_id)), usuario_id=usuario_id)
    raise ErrorDocumento("Este documento viene de otra base; usa «Traer de Compras y Fiscal».")
