"""Conexión a SQL Server."""
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

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


@lru_cache
def _fabrica() -> sessionmaker[Session]:
    return sessionmaker(bind=motor(), expire_on_commit=False)


def obtener_bd() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión de base por petición."""
    bd = _fabrica()()
    try:
        yield bd
    finally:
        bd.close()
