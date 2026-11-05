"""Ruta de salud: confirma que la API corre y si alcanza la base de datos y el correo."""
import socket

from fastapi import APIRouter

from core.bd import bd_disponible
from core.config import configuracion

router = APIRouter(prefix="/api", tags=["nucleo"])


def _correo() -> str:
    cfg = configuracion()
    if not cfg.smtp_servidor:
        return "sin configurar"
    try:
        socket.create_connection((cfg.smtp_servidor, cfg.smtp_puerto), timeout=1).close()
        return "ok"
    except OSError:
        return "sin conexión"


@router.get("/salud")
def salud() -> dict:
    return {
        "plataforma": "SMN - Transformación digital",
        "api": "ok",
        "base_de_datos": "ok" if bd_disponible() else "sin conexión",
        "correo": _correo(),
        "entorno": configuracion().api_entorno,
        "version": configuracion().plataforma_version,
    }
