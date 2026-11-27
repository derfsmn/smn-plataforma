"""Reclasificación automática de las evaluaciones vigentes, cada noche (plan aprobado por Diego el 24 nov 2026).

Cuando cambia el clasificador o el catálogo, las evaluaciones viejas ya no se quedan con la subcategoría de antes: cada
noche, entre la 1 y las 5 de la mañana (hora de México), se vuelve a clasificar cada evaluación vigente sin salir a
internet. Solo las que cambian de subcategoría se recalculan completas; la nueva dice en su explicación qué tenía antes y
qué tiene ahora. La anterior queda guardada (ya no vigente) como historial.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from modulos.compras import radar_productos as rp
from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
from modulos.compras.modelos_propuestas import Propuesta

log = logging.getLogger(__name__)
ZONA = ZoneInfo("America/Mexico_City")
HORA_INICIO, HORA_FIN = 1, 5
_corriendo = threading.Event()
ESTADO: dict = {"dia": None, "revisadas": 0, "cambiaron": 0, "fallaron": 0}


def _n(t: str | None) -> str:
    return rp._norm(t).strip()


def sujeto_de(bd: Session, e: ProductoEvaluacion) -> rp.Sujeto:
    s = (rp.sujeto_de_propuesta(bd.get(Propuesta, e.propuesta_id)) if e.propuesta_id
         else rp.sujeto_de_idea(bd.get(ProductoIdea, e.idea_id)))
    rp.ficha_sujeto(bd, e, s)  # reusa la ficha ya leída
    return s


def revisar(bd: Session, aplicar: bool = True, limite: int | None = None, avance=None) -> list[dict]:
    """Clasifica de nuevo cada evaluación vigente y lista ya hecha. Con `aplicar`, recalcula las que cambian."""
    vigentes = list(bd.scalars(select(ProductoEvaluacion).where(
        ProductoEvaluacion.vigente == true(), ProductoEvaluacion.estado == "lista").order_by(ProductoEvaluacion.evaluacion_id)))
    if limite:
        vigentes = vigentes[:limite]
    cambios = []
    for i, e in enumerate(vigentes, 1):
        if avance:
            avance(i, len(vigentes))
        if e.clasificacion_origen == "variante":
            continue  # la decide otro sabor del mismo producto, que también se revisa
        try:
            s = sujeto_de(bd, e)
            c = rp.clasificar_sujeto(bd, s)
        except Exception as ex:  # noqa: BLE001 - una evaluación no detiene a las demás
            bd.rollback()
            log.warning("Reclasificar %s: %s", e.evaluacion_id, ex)
            ESTADO["fallaron"] = ESTADO.get("fallaron", 0) + 1
            continue
        ESTADO["revisadas"] = ESTADO.get("revisadas", 0) + 1
        if _n(c.subcategoria) == _n(e.subcategoria):
            continue
        fila = {"evaluacion": e.evaluacion_id, "producto": s.nombre, "antes": e.subcategoria,
                "origen_antes": e.clasificacion_origen, "ahora": c.subcategoria, "seguridad": c.seguridad,
                "por": c.texto()}
        cambios.append(fila)
        if not aplicar:
            continue
        antes, origen_antes = e.subcategoria, e.clasificacion_origen
        nueva = rp.iniciar(bd, propuesta_id=e.propuesta_id, idea_id=e.idea_id)
        nueva = rp.evaluar(bd, nueva.evaluacion_id, rapido=False)
        cuando = datetime.now(ZONA).strftime("%d/%m/%Y")
        nueva.explicacion = (f"Se reclasificó sola el {cuando}: antes «{antes or 'sin subcategoría'}» "
                             f"({origen_antes or 'sin origen'}), ahora «{nueva.subcategoria or 'sin subcategoría'}».\n\n"
                             + (nueva.explicacion or ""))
        bd.commit()
        fila["nueva"] = nueva.evaluacion_id
        ESTADO["cambiaron"] = ESTADO.get("cambiaron", 0) + 1
    return cambios


def comparacion_lista() -> bool:
    """No se reclasifica ninguna evaluación hasta que exista la comparación v0.5.3 contra esta versión, para que cada
    cambio esté explicado antes de que pase (Diego, 24 nov 2026: «revisa bien todo»)."""
    from modulos.compras import examen_clasificacion as ex

    version = ex.clave()
    return bool(version) and ex.ruta(version, "comparacion", "json").exists()


def en_horario(momento: datetime | None = None) -> bool:
    h = (momento or datetime.now(ZONA)).astimezone(ZONA).hour
    return HORA_INICIO <= h < HORA_FIN


def revisar_programa(bd: Session) -> None:  # noqa: ARG001 - el programador pasa su sesión; el trabajo abre la suya
    """Lo llama el programador cada minuto: una vez por noche arranca la reclasificación en su propio hilo."""
    hoy = datetime.now(ZONA).date()
    if _corriendo.is_set() or not en_horario() or ESTADO.get("dia") == hoy or not comparacion_lista():
        return
    ESTADO.update(dia=hoy, revisadas=0, cambiaron=0, fallaron=0)

    def trabajo() -> None:
        from core.bd import _fabrica

        try:
            with _fabrica()() as s:
                cambios = revisar(s)
                log.info("Reclasificación nocturna: %s revisadas, %s cambiaron", ESTADO["revisadas"], len(cambios))
        except Exception:  # noqa: BLE001
            log.exception("Reclasificación nocturna falló")
        finally:
            _corriendo.clear()

    _corriendo.set()
    threading.Thread(target=trabajo, daemon=True, name="reclasificar").start()
