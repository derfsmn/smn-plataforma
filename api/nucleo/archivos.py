"""Archivos subidos a la plataforma.

Se guardan en ARCHIVOS_RUTA (carpeta local o volumen) con un nombre aleatorio; en la base queda
el nombre original, tipo, tamaño y SHA-256. Solo se aceptan tipos de la lista y hasta ARCHIVOS_MB_MAXIMO.
Por ahora puede descargar quien lo subió o un administrador de usuarios; cada módulo agregará sus reglas.
"""
import hashlib
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.config import configuracion
from core.seguridad import Contexto, ip_de, usuario_actual
from nucleo.bitacora import registrar
from nucleo.modelos import Archivo, Modulo, ahora

router = APIRouter(prefix="/api/archivos", tags=["archivos"])

# extensión: (tipo de contenido, firma de los primeros bytes o None)
TIPOS = {
    ".pdf": ("application/pdf", b"%PDF"),
    ".png": ("image/png", b"\x89PNG"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".webp": ("image/webp", b"RIFF"),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK\x03\x04"),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK\x03\x04"),
    ".csv": ("text/csv", None),
}
BLOQUE = 1024 * 1024


class ArchivoSalida(BaseModel):
    id: int
    nombre: str
    tipo: str
    tamano_bytes: int
    subido_en: datetime
    modulo: str | None
    entidad: str | None
    entidad_id: str | None

    @classmethod
    def de(cls, a: Archivo, modulo: str | None = None) -> "ArchivoSalida":
        return cls(id=a.archivo_id, nombre=a.nombre_original, tipo=a.tipo_contenido, tamano_bytes=a.tamano_bytes,
                   subido_en=a.subido_en, modulo=modulo, entidad=a.entidad, entidad_id=a.entidad_id)


def _raiz() -> Path:
    raiz = Path(configuracion().archivos_ruta).resolve()
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz


def _nombre_seguro(nombre: str) -> str:
    nombre = os.path.basename(nombre.replace("\\", "/")).strip() or "archivo"
    return "".join(c for c in nombre if c.isprintable())[:255]


@router.post("", response_model=ArchivoSalida, status_code=status.HTTP_201_CREATED)
async def subir(
    request: Request,
    archivo: UploadFile = File(...),
    modulo: str | None = Form(None, max_length=40),
    entidad: str | None = Form(None, max_length=60),
    entidad_id: str | None = Form(None, max_length=60),
    ctx: Contexto = Depends(usuario_actual),
    bd: Session = Depends(obtener_bd),
) -> ArchivoSalida:
    cfg = configuracion()
    nombre = _nombre_seguro(archivo.filename or "")
    extension = Path(nombre).suffix.lower()
    if extension not in TIPOS:
        permitidos = ", ".join(sorted({e.lstrip(".").upper() for e in TIPOS}))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Ese tipo de archivo no se acepta. Se aceptan: {permitidos}.")
    tipo, firma = TIPOS[extension]

    modulo_obj = None
    if modulo:
        modulo_obj = bd.scalar(select(Modulo).where(Modulo.codigo == modulo))
        if not modulo_obj:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ese módulo no existe.")

    maximo = cfg.archivos_mb_maximo * BLOQUE
    relativa = Path(ahora().strftime("%Y/%m")) / f"{uuid.uuid4().hex}{extension}"
    destino = _raiz() / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    sha, tamano, inicio = hashlib.sha256(), 0, b""
    try:
        with destino.open("wb") as salida:
            while bloque := await archivo.read(BLOQUE):
                if not inicio:
                    inicio = bloque[:16]
                tamano += len(bloque)
                if tamano > maximo:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                        f"El archivo pasa de {cfg.archivos_mb_maximo} MB.")
                sha.update(bloque)
                salida.write(bloque)
        if tamano == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo está vacío.")
        if firma and not inicio.startswith(firma):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El contenido no corresponde a la extensión del archivo.")
    except BaseException:
        destino.unlink(missing_ok=True)
        raise

    a = Archivo(modulo_id=modulo_obj.modulo_id if modulo_obj else None, entidad=entidad, entidad_id=entidad_id,
                nombre_original=nombre, tipo_contenido=tipo, tamano_bytes=tamano, sha256=sha.hexdigest(),
                ruta_almacenamiento=relativa.as_posix(), subido_por=ctx.usuario.usuario_id)
    bd.add(a)
    bd.flush()
    registrar(bd, "subir_archivo", usuario_id=ctx.usuario.usuario_id, modulo_id=a.modulo_id, entidad="archivo",
              entidad_id=a.archivo_id, detalle={"nombre": nombre, "bytes": tamano}, ip=ip_de(request))
    bd.commit()
    return ArchivoSalida.de(a, modulo)


@router.get("/mios", response_model=list[ArchivoSalida])
def mios(ctx: Contexto = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> list[ArchivoSalida]:
    filas = bd.execute(select(Archivo, Modulo.codigo).outerjoin(Modulo, Modulo.modulo_id == Archivo.modulo_id)
                       .where(Archivo.subido_por == ctx.usuario.usuario_id)
                       .order_by(Archivo.archivo_id.desc()).limit(20))
    return [ArchivoSalida.de(a, m) for a, m in filas]


@router.get("/{archivo_id}")
def descargar(archivo_id: int, ctx: Contexto = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> FileResponse:
    a = bd.get(Archivo, archivo_id)
    if not a or not (a.subido_por == ctx.usuario.usuario_id or ctx.puede("nucleo.usuarios.administrar")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese archivo.")
    raiz = _raiz()
    ruta = (raiz / a.ruta_almacenamiento).resolve()
    if raiz not in ruta.parents or not ruta.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El archivo ya no está en el almacén.")
    return FileResponse(ruta, media_type=a.tipo_contenido, filename=a.nombre_original,
                        headers={"X-Content-Type-Options": "nosniff"})
