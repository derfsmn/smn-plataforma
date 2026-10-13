"""Conexión a SQL Server."""
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from core.config import configuracion


@lru_cache
def motor() -> Engine:
    return create_engine(configuracion().url_bd(), pool_pre_ping=True)


def bd_disponible() -> bool:
    try:
        with motor().connect() as conexion:
            conexion.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
