"""Costo real de la IA externa: lo que el proveedor cobró por día.

OpenAI lo da en su API de costos de la organización (`/v1/organization/costs`), que pide una llave de
administrador (la llave normal no tiene el permiso api.usage.read). El dato es por día en UTC y llega con
algunas horas de retraso, así que se vuelve a bajar los últimos días en cada sincronización.
El tope mensual de plataforma usa este costo en los días cerrados; la estimación por llamada sigue sirviendo
para frenar antes de gastar (el costo real llega después).
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from core.config import configuracion
from nucleo.modelos import IaCostoReal, IaLlamada, ahora

log = logging.getLogger("smn.ia.costos")
URL_COSTOS = "https://api.openai.com/v1/organization/costs"
CADA = timedelta(hours=6)  # cada cuánto se vuelve a bajar
DIAS_HACIA_ATRAS = 10

# Último intento, para mostrarlo en la pantalla (vive en memoria del proceso)
ESTADO: dict = {"ultimo_intento": None, "error": None}


class ErrorCostos(Exception):
    pass


def activo() -> bool:
    cfg = configuracion()
    return cfg.ia_proveedor_externo == "openai" and bool(cfg.openai_admin_key)


def _pedir(params: dict) -> dict:
    cfg = configuracion()
    url = f"{URL_COSTOS}?{urllib.parse.urlencode(params, doseq=True)}"
    peticion = urllib.request.Request(url, headers={"Authorization": f"Bearer {cfg.openai_admin_key}",
                                                    "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ErrorCostos("OpenAI rechazó la llave de administrador: revisa que sea una Admin key de la organización.") from e
        raise ErrorCostos(f"OpenAI respondió con error {e.code} al pedir los costos.") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise ErrorCostos("No se pudo conectar con OpenAI para pedir los costos.") from e


def costos_openai(desde: date, hasta: datetime) -> dict[date, Decimal]:
    """Costo en USD por día (UTC) de los días que ya cerraron entre `desde` y `hasta`."""
    cfg = configuracion()
    inicio = int(datetime.combine(desde, datetime.min.time(), UTC).timestamp())
    fin = int(hasta.replace(tzinfo=UTC).timestamp()) if hasta.tzinfo is None else int(hasta.timestamp())
    params: dict = {"start_time": inicio, "end_time": fin, "bucket_width": "1d", "limit": 31}
    if cfg.openai_proyecto_id:
        params["project_ids"] = [cfg.openai_proyecto_id]
    por_dia: dict[date, Decimal] = {}
    for _ in range(20):  # páginas
        datos = _pedir(params)
        for cubeta in datos.get("data") or []:
            if int(cubeta.get("end_time", 0)) > fin:
                continue  # el día de hoy todavía no cierra
            dia = datetime.fromtimestamp(int(cubeta["start_time"]), UTC).date()
            total = sum((Decimal(str((r.get("amount") or {}).get("value") or 0)) for r in cubeta.get("results") or []),
                        Decimal(0))
            por_dia[dia] = por_dia.get(dia, Decimal(0)) + total
        if not datos.get("has_more") or not datos.get("next_page"):
            break
        params["page"] = datos["next_page"]
    return por_dia


def sincronizar(bd: Session) -> int:
    """Baja el costo real de los últimos días y lo guarda. Devuelve cuántos días guardó."""
    cfg = configuracion()
    ESTADO["ultimo_intento"] = ahora()
    if not activo():
        raise ErrorCostos("Falta la llave de administrador de OpenAI (Administración > Configuración).")
    if not cfg.ia_tipo_cambio_mxn:
        ESTADO["error"] = "Falta el tipo de cambio (Administración > Configuración)."
        raise ErrorCostos(ESTADO["error"])
    try:
        por_dia = costos_openai(ahora().date() - timedelta(days=DIAS_HACIA_ATRAS), ahora())
    except ErrorCostos as e:
        ESTADO["error"] = str(e)
        raise
    tc = Decimal(str(cfg.ia_tipo_cambio_mxn))
    for dia, usd in por_dia.items():
        fila = bd.get(IaCostoReal, (dia, "openai")) or IaCostoReal(fecha=dia, proveedor="openai")
        fila.costo_usd, fila.tipo_cambio = usd, tc
        fila.costo_mxn = (usd * tc).quantize(Decimal("0.0001"))
        fila.obtenido_en = ahora()
        bd.add(fila)
    bd.commit()
    ESTADO["error"] = None
    return len(por_dia)


def revisar(bd: Session) -> None:
    """Lo llama el programador cada minuto; baja los costos si ya pasó el intervalo."""
    if not activo():
        return
    ultimo = ESTADO["ultimo_intento"]
    if ultimo and ahora() - ultimo < CADA:
        return
    try:
        sincronizar(bd)
    except ErrorCostos as e:
        log.warning("No se pudo bajar el costo real de OpenAI: %s", e)


def estimado_por_dia(bd: Session, desde: date) -> dict[date, Decimal]:
    dia = cast(IaLlamada.ocurrido_en, Date)
    filas = bd.execute(select(dia, func.sum(IaLlamada.costo_mxn)).where(
        IaLlamada.proveedor_ia == "api", IaLlamada.ocurrido_en >= datetime.combine(desde, datetime.min.time()))
        .group_by(dia)).all()
    return {f[0]: Decimal(f[1] or 0) for f in filas}


def gasto_plataforma(bd: Session, desde: datetime) -> Decimal:
    """Gasto de la plataforma desde una fecha: costo real en los días que ya lo tienen, estimado en los demás."""
    estimados = estimado_por_dia(bd, desde.date())
    if not activo():
        return sum(estimados.values(), Decimal(0))
    reales = {f.fecha: f.costo_mxn for f in bd.scalars(select(IaCostoReal).where(
        IaCostoReal.proveedor == "openai", IaCostoReal.fecha >= desde.date(), IaCostoReal.fecha < ahora().date()))}
    total = sum(reales.values(), Decimal(0))
    total += sum((v for d, v in estimados.items() if d not in reales), Decimal(0))
    return total
