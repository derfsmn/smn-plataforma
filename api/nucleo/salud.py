"""Ruta de salud: confirma que la API corre y si alcanza la base de datos."""
from fastapi import APIRouter

from core.bd import bd_disponible
from core.config import configuracion

router = APIRouter(prefix="/api", tags=["nucleo"])


@router.get("/salud")
def salud() -> dict:
    return {
        "plataforma": "SMN - Transformación digital",
        "api": "ok",
        "base_de_datos": "ok" if bd_disponible() else "sin conexión",
        "entorno": configuracion().api_entorno,
    }
