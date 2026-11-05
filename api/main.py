"""API de SMN - Transformación digital.

Núcleo (cascarón) + puerta de IA + módulos. Ver AGENTS.md, sección 4.
"""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from core import ajustes
from core.bd import motor
from core.config import configuracion
from ia import rutas as ia_rutas
from nucleo import administracion, archivos, autenticacion, notificaciones, pendientes, salud, visor_bitacora
from nucleo import configuracion as configuracion_rutas
from datos import etl, smnbi
from datos import rutas as datos_rutas
from datos import proveedores as datos_proveedores
from datos import grupos_tiendas, rutas_centro, rutas_etl, rutas_grupos_tiendas, rutas_inventario, rutas_proveedores, rutas_tiendas
from modulos.compras import (
    oportunidades, precios, radar_productos, rutas_comite, rutas_conocimiento, rutas_oportunidades, rutas_precios, rutas_productos,
    rutas_propuestas, rutas_radar,
)
from modulos.contraloria import diot, rutas_conocimiento_fiscal, rutas_diot
from modulos.metodos import rutas as metodos_rutas
from modulos.kiosco import rutas as kiosco_rutas

log = logging.getLogger("uvicorn.error")


def _revisar_radar() -> None:
    from core.bd import _fabrica
    from modulos.compras.radar import revisar_programa

    with _fabrica()() as bd:
        revisar_programa(bd)


def _revisar_catalogo() -> None:
    from core.bd import _fabrica
    from datos.catalogo import revisar_programa

    with _fabrica()() as bd:
        revisar_programa(bd)


def _revisar_precios() -> None:
    from core.bd import _fabrica
    from modulos.compras.precios import revisar_programa

    with _fabrica()() as bd:
        revisar_programa(bd)


def _revisar_etl() -> None:
    from core.bd import _fabrica

    with _fabrica()() as bd:
        etl.revisar_programa(bd)


def _revisar_costos() -> None:
    from core.bd import _fabrica
    from ia.costos import revisar

    with _fabrica()() as bd:
        revisar(bd)


async def programador() -> None:
    """Corre solo lo programado (Radar de tendencias, carga del catálogo, Radar de precios, ETL de ventas y costo real de la IA). Revisa cada minuto si ya toca.
    Vive dentro de la API, así que no depende de nadie: en el servidor corre mientras la API esté arriba."""
    while True:
        for tarea in (_revisar_radar, _revisar_catalogo, _revisar_precios, _revisar_etl, _revisar_costos):
            try:
                await asyncio.to_thread(tarea)
            except Exception:  # noqa: BLE001 - un error no debe detener el programador
                log.exception("El programador falló en %s; se reintenta en un minuto", tarea.__name__)
        await asyncio.sleep(60)


@asynccontextmanager
async def arranque(_: FastAPI):
    # Aplica los ajustes guardados en Administración > Configuración (si la base está lista)
    try:
        with Session(motor()) as bd:
            ajustes.aplicar(bd)
    except Exception as e:  # sin base o sin la tabla todavía: se usan los del .env
        log.warning("No se cargaron los ajustes guardados: %s", e)
    # Una corrida del Radar de precios que quedó «en curso» murió con el reinicio
    try:
        with Session(motor()) as bd:
            if n := precios.cerrar_huerfanas(bd):
                log.warning("Se cerraron %s corridas del Radar de precios que quedaron a medias", n)
            if n := etl.cerrar_huerfanas(bd):
                log.warning("Se cerraron %s cargas del ETL de ventas que quedaron a medias", n)
            if n := smnbi.cerrar_huerfanas(bd):
                log.warning("Se cerraron %s cargas de tablas de SMNBI que quedaron a medias", n)
            if n := radar_productos.cerrar_huerfanas(bd):
                log.warning("Se cerraron %s evaluaciones del Radar de productos que quedaron a medias", n)
            if n := oportunidades.cerrar_huerfanas(bd):
                log.warning("Se cerraron %s búsquedas de oportunidades que quedaron a medias", n)
            if n := datos_proveedores.cerrar_huerfanas(bd):
                log.warning("Se cerraron %s evaluaciones de proveedores que quedaron a medias", n)
            if n := grupos_tiendas.cerrar_huerfanas(bd):
                log.warning("Se cerraron %s cálculos de grupos de tiendas que quedaron a medias", n)
            if n := diot.cerrar_huerfanas(bd):
                log.warning("Se cerraron %s corridas de la DIOT que quedaron a medias", n)
    except Exception as e:  # noqa: BLE001
        log.warning("No se revisaron corridas a medias: %s", e)
    tarea = asyncio.create_task(programador()) if configuracion().programador_activo else None
    yield
    if tarea:
        tarea.cancel()
        with suppress(asyncio.CancelledError):
            await tarea


app = FastAPI(title="SMN - Transformación digital", version="0.1.0", lifespan=arranque)

app.add_middleware(
    CORSMiddleware,
    allow_origins=configuracion().origenes,
    # En desarrollo se acepta la web en el puerto 3000 desde cualquier dirección
    # (localhost, 127.0.0.1 o la IP del equipo para probar desde el celular)
    allow_origin_regex=r"https?://[^/]+:3000" if configuracion().es_desarrollo else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(salud.router)
app.include_router(autenticacion.router)
app.include_router(administracion.router)
app.include_router(pendientes.router)
app.include_router(visor_bitacora.router)
app.include_router(notificaciones.router)
app.include_router(archivos.router)
app.include_router(ia_rutas.router)
app.include_router(configuracion_rutas.router)
# Centro de datos (catálogos comunes, esquema datos)
app.include_router(rutas_etl.router)
app.include_router(datos_rutas.router)
app.include_router(rutas_proveedores.router)
app.include_router(rutas_centro.router)
app.include_router(rutas_tiendas.router)
app.include_router(rutas_inventario.router)
app.include_router(rutas_grupos_tiendas.router)
# Módulos (api/modulos/<nombre>)
app.include_router(rutas_radar.router)
app.include_router(rutas_precios.router)
app.include_router(rutas_conocimiento.router)
app.include_router(rutas_propuestas.router)
app.include_router(rutas_productos.router)
app.include_router(rutas_oportunidades.router)
app.include_router(rutas_comite.router)
app.include_router(kiosco_rutas.router)
app.include_router(rutas_diot.router)
app.include_router(rutas_conocimiento_fiscal.router)
app.include_router(metodos_rutas.router)
