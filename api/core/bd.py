"""Conexión a SQL Server."""
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from core.config import configuracion


# 26 nov 2026 (la plataforma se pasmó: «QueuePool limit of size 5 overflow 10 reached»): con el Monitor, la bitácora y
# «Recalcular todas» a la vez, 15 conexiones no alcanzaban. Hay hasta 40 peticiones a la vez (hilos de FastAPI) más los
# trabajos en segundo plano.
CONEXIONES, EXTRA = 10, 30


_avisado = [0.0]


def _vigilar(m: Engine) -> None:
    """Deja un aviso en la bitácora (y en el Monitor) cuando se usa el 80 % de las conexiones, una vez por minuto."""
    import logging
    import time

    @event.listens_for(m, "checkout")
    def _al_tomar(*_):
        uso = m.pool.checkedout()
        if uso >= (CONEXIONES + EXTRA) * 0.8 and time.monotonic() - _avisado[0] > 60:
            _avisado[0] = time.monotonic()
            logging.getLogger("core.bd").warning("Conexiones a la base casi agotadas: %s de %s en uso", uso,
                                                 CONEXIONES + EXTRA)


@lru_cache
def motor() -> Engine:
    m = create_engine(configuracion().url_bd(), pool_pre_ping=True, pool_size=CONEXIONES, max_overflow=EXTRA,
                      pool_timeout=20, pool_recycle=1800)
    _vigilar(m)
    return m


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


def obtener_bd_ligera() -> Iterator[Session]:
    """Para pantallas que se consultan solas cada pocos segundos (Monitor, bitácora en vivo): si una fila está bloqueada
    por un trabajo largo, se rinde a los 2 segundos en vez de quedarse esperando con la conexión tomada. La sesión va
    sobre una sola conexión para que el límite valga en todas sus consultas, aunque haga rollback entre una y otra."""
    with motor().connect() as conexion:
        conexion.exec_driver_sql("SET LOCK_TIMEOUT 2000")
        conexion.commit()
        bd = Session(bind=conexion, expire_on_commit=False)
        try:
            yield bd
        finally:
            bd.close()
            try:
                conexion.rollback()
                conexion.exec_driver_sql("SET LOCK_TIMEOUT -1")  # regresa a la bolsa como estaba
                conexion.commit()
            except Exception:  # noqa: BLE001 - si la conexión quedó mala, pool_pre_ping la descarta
                conexion.invalidate()


def obtener_bd() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión de base por petición."""
    bd = _fabrica()()
    try:
        yield bd
    finally:
        bd.close()
