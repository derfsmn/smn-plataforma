"""Qué está corriendo ahora y bitácora en vivo de la API, para verlo en Estado del sistema sin entrar al servidor
(Diego, 26 nov 2026: «podemos tener un log visible en el sitio para ver qué se está corriendo»).

- La bitácora en vivo guarda en memoria las últimas líneas que escribe la API (sin las consultas de las pantallas).
  Se pierde al reiniciar, como `docker logs` de un contenedor nuevo.
- «Qué está corriendo» junta los procesos pesados que comparten el servidor (DataForSEO, tiendas, IA local).
"""
import logging
import threading
from collections import deque
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, requiere
from nucleo.modelos import ahora

router = APIRouter(prefix="/api/nucleo/en-vivo", tags=["sistema"])
VER = "nucleo.bitacora.ver"
LINEAS = 300
# Minutos a partir de los cuales un proceso sale en ámbar
LENTO = {"evaluacion": 10, "precios": 60, "tendencias": 30, "oportunidades": 30, "examen": 180, "prueba": 90}
NIVELES = {"DEBUG": "detalle", "INFO": "info", "WARNING": "aviso", "ERROR": "error", "CRITICAL": "error"}


class _Memoria(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lineas: deque[dict] = deque(maxlen=LINEAS)
        self._n = 0
        self._candado = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name.startswith("uvicorn.access"):
                return
            mensaje = record.getMessage()
            if record.exc_info and record.levelno >= logging.ERROR:
                mensaje += f" — {record.exc_info[1]}"
            with self._candado:
                self._n += 1
                self.lineas.append({"n": self._n, "hora": datetime.fromtimestamp(record.created, UTC).isoformat(),
                                    "nivel": NIVELES.get(record.levelname, "info"), "origen": _origen(record.name),
                                    "mensaje": mensaje[:2000]})
        except Exception:  # noqa: BLE001 - la bitácora nunca tira la API
            pass

    def desde(self, n: int) -> list[dict]:
        with self._candado:
            return [x for x in self.lineas if x["n"] > n]


def _origen(nombre: str) -> str:
    partes = nombre.split(".")
    return partes[-1].replace("_", " ") if nombre.startswith("smn") else ("API" if nombre.startswith("uvicorn") else partes[0])


MEMORIA = _Memoria()


def instalar() -> None:
    """Se llama al arrancar: escucha a la raíz y a uvicorn (que no se propaga), y deja pasar los INFO de «smn»."""
    for nombre in ("", "uvicorn.error"):
        lg = logging.getLogger(nombre)
        if MEMORIA not in lg.handlers:
            lg.addHandler(MEMORIA)
    logging.getLogger("smn").setLevel(logging.INFO)


def _minutos(desde: datetime | None) -> int | None:
    return int((ahora() - desde).total_seconds() // 60) if desde else None


def _proceso(tipo: str, nombre: str, detalle: str | None, desde: datetime | None) -> dict:
    m = _minutos(desde)
    return {"tipo": tipo, "nombre": nombre, "detalle": detalle, "minutos": m,
            "lento": m is not None and m >= LENTO.get(tipo, 30)}


def procesos(bd: Session) -> list[dict]:
    salida: list[dict] = []
    # Cada fuente por separado: si una tabla falta en una base vieja, las demás se ven igual
    try:
        from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
        from modulos.compras.modelos_propuestas import Propuesta

        q = (select(ProductoEvaluacion, ProductoIdea.nombre, Propuesta.producto)
             .outerjoin(ProductoIdea, ProductoIdea.idea_id == ProductoEvaluacion.idea_id)
             .outerjoin(Propuesta, Propuesta.propuesta_id == ProductoEvaluacion.propuesta_id)
             .where(ProductoEvaluacion.estado == "en_curso").order_by(ProductoEvaluacion.creada_en))
        for e, idea, propuesta in bd.execute(q):
            salida.append(_proceso("evaluacion", f"Radar de productos: {idea or propuesta or f'evaluación {e.evaluacion_id}'}",
                                   e.avance or "empezando", e.creada_en))
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras.modelos_precios import PrecioCorrida

        nombres = {"programado": "Radar de precios (programado)", "tardio": "Radar de precios (programado)",
                   "manual": "Radar de precios («Correr ahora»)", "prueba": "Radar de precios (prueba con Excel)",
                   "producto": "Precios de afuera de un producto nuevo", "oportunidad": "Buscar oportunidades (precios)",
                   "nocturna": "Radar de precios (lote de noche)"}
        for c in bd.scalars(select(PrecioCorrida).where(PrecioCorrida.estado == "en_curso").order_by(PrecioCorrida.iniciado_en)):
            salida.append(_proceso("precios", nombres.get(c.origen, f"Radar de precios ({c.origen})"),
                                   f"{c.productos or 0} producto(s)", c.iniciado_en))
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras.modelos import RadarReporte

        for r in bd.scalars(select(RadarReporte).where(RadarReporte.estado == "en_curso")):
            salida.append(_proceso("tendencias", "Radar de tendencias", f"corrida {r.origen} del {r.fecha:%d/%m}", r.iniciado_en))
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras.modelos_productos import OportunidadCorrida

        for o in bd.scalars(select(OportunidadCorrida).where(OportunidadCorrida.estado == "en_curso")):
            salida.append(_proceso("oportunidades", "Buscar oportunidades", None, getattr(o, "creada_en", None)
                                   or getattr(o, "iniciada_en", None)))
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras import examen_clasificacion as ex

        est = ex.estado()
        if est.get("corriendo"):
            a = est.get("avance") or {}
            salida.append(_proceso("examen", f"Examen de clasificación ({est.get('clasificador')})",
                                   f"corrida {a.get('corrida')}: {a.get('hechos', 0)} de {a.get('total', 0)}", None))
    except Exception:  # noqa: BLE001
        pass
    try:
        from modulos.compras import prueba_afuera as pa

        est = pa.estado()
        if est.get("corriendo"):
            a = est.get("avance") or {}
            salida.append(_proceso("prueba", "Prueba por lote de precios de afuera",
                                   f"{a.get('hechos', 0)} de {a.get('total', 0)} productos", None))
    except Exception:  # noqa: BLE001
        pass
    return salida


@router.get("")
def en_vivo(desde: int = 0, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> dict:
    """Procesos que están corriendo y líneas nuevas de la bitácora (después de la línea `desde`)."""
    return {"procesos": procesos(bd), "bitacora": MEMORIA.desde(desde), "ahora": ahora().replace(tzinfo=UTC).isoformat(),
            "guarda": LINEAS, "ultima": MEMORIA._n}
