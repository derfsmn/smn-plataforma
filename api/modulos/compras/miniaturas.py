"""Fotos de productos en tamaño de pantalla (Diego, 11 nov 2026: la vista del comité estaba «muy, muy lenta» porque
bajaba cada foto original, de varios MB, por la VPN).

Con `ancho`, la foto se reduce a ese ancho en JPEG y se guarda junto al almacén (carpeta .miniaturas) para no volver
a hacerla. Las respuestas se guardan 1 día en el navegador: la misma foto no se vuelve a bajar en cada recarga."""
import logging
from pathlib import Path

from fastapi.responses import FileResponse

log = logging.getLogger("smn.compras.miniaturas")

CACHE = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=86400"}
ANCHOS = (160, 400, 800)  # los que pide la pantalla; otro ancho se ajusta al siguiente


def _ancho(pedido: int) -> int:
    return next((a for a in ANCHOS if pedido <= a), ANCHOS[-1])


def miniatura(raiz: Path, ruta: Path, ancho: int) -> Path | None:
    """La foto reducida (la hace la primera vez). None si no se pudo: entonces se manda la original."""
    ancho = _ancho(ancho)
    destino = raiz / ".miniaturas" / str(ancho) / (ruta.relative_to(raiz).as_posix().replace("/", "_") + ".jpg")
    try:
        if destino.is_file() and destino.stat().st_mtime >= ruta.stat().st_mtime:
            return destino
        from PIL import Image, ImageOps

        destino.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(ruta) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((ancho, ancho * 2))
            if img.mode not in ("RGB", "L"):
                fondo = Image.new("RGB", img.size, "white")
                fondo.paste(img, mask=img.convert("RGBA").split()[-1])
                img = fondo
            temporal = destino.with_suffix(".tmp")
            img.save(temporal, "JPEG", quality=82, optimize=True)
            temporal.replace(destino)
        return destino
    except Exception as e:  # noqa: BLE001 — una foto rara no debe romper la pantalla
        log.info("No se pudo reducir %s: %s", ruta, e)
        return None


def responder(raiz: Path, ruta: Path, tipo: str | None, nombre: str | None, ancho: int | None,
              inline: bool = True) -> FileResponse:
    if ancho and (tipo or "").startswith("image/") and (chica := miniatura(raiz, ruta, ancho)):
        return FileResponse(chica, media_type="image/jpeg", headers=CACHE)
    extra = {"content_disposition_type": "inline"} if inline else {}
    return FileResponse(ruta, media_type=tipo, filename=nombre, headers=CACHE, **extra)
