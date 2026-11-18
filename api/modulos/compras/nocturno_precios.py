"""Radar de precios de noche, por lotes (Diego, 2026-11-17: «a partir de las 6 de la tarde hasta las 6 de la mañana
ejecutemos diario el proceso hasta llegar a tener todos»; «vamos a empezar con la categoría AA»).

- Cada minuto el programador revisa: si es de noche, no corre otra corrida y no se acabó el presupuesto de DataForSEO,
  arranca un lote (corrida con origen «nocturna») con los productos que tocan.
- Orden del lote: primero lo que nunca se ha validado, por clase (AA, A, B, C, D, E, sin clase) y por venta de 26
  semanas; luego lo que ya le toca por rotación (AA cada semana, lo demás cada 12 días) o lo dudoso de ayer.
- Ya no empieza lotes después de la hora de fin; el que va corriendo termina. Si un lote se queda sin presupuesto,
  no empieza otro esa noche.
- Con «Revisar todo el catálogo activo» los productos activos entran solos (vigilado con origen «nocturna»). Esos no
  entran al botón «Correr ahora», que sigue con la lista elegida a mano.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, or_, select, true
from sqlalchemy.orm import Session

from core.config import configuracion
from datos.modelos import Producto, VentaSemanal
from modulos.compras import dataforseo as dfs
from modulos.compras import precios
from modulos.compras import realidad_producto as rp
from modulos.compras.modelos_precios import PrecioCorrida, PrecioCorridaProducto, PrecioVigilado
from nucleo.modelos import ahora

log = logging.getLogger("uvicorn.error")

ORIGEN = "nocturna"
CLASES = ("AA", "A", "B", "C", "D", "E")


def en_ventana(hora: int, desde: int, hasta: int) -> bool:
    if desde == hasta:
        return False
    return desde <= hora or hora < hasta if desde > hasta else desde <= hora < hasta


def inicio_noche(local: datetime, desde: int) -> datetime:
    """Inicio de la noche en curso (hora local) en UTC sin zona, como se guardan las fechas."""
    base = local.replace(hour=desde, minute=0, second=0, microsecond=0)
    if local.hour < desde:
        base -= timedelta(days=1)
    return base.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _rango_clase():
    c = func.upper(func.ltrim(func.rtrim(Producto.clasificacion)))
    return case(*[(c == k, n) for n, k in enumerate(CLASES)], else_=len(CLASES))


def _universo(cfg):
    """Condición de qué productos entran a la noche."""
    vigilado = (PrecioVigilado.activo == true())
    if cfg.precios_nocturno_catalogo:
        return (Producto.activo == true()) & or_(PrecioVigilado.vigilado_id.is_(None), vigilado)
    return vigilado & (Producto.activo == true())


def candidatos(bd: Session, limite: int) -> list[int]:
    cfg = configuracion()
    v = rp.ventana(bd)
    venta = None
    if v:
        venta = (select(VentaSemanal.sku.label("sku"), func.sum(VentaSemanal.importe).label("importe"))
                 .where(*v.filtro()).group_by(VentaSemanal.sku).subquery())
    q = (select(Producto.producto_id).select_from(Producto)
         .outerjoin(PrecioVigilado, PrecioVigilado.producto_id == Producto.producto_id)
         .where(_universo(cfg), or_(PrecioVigilado.proxima_revision.is_(None), PrecioVigilado.proxima_revision <= ahora())))
    orden = [case((PrecioVigilado.validado_en.is_(None), 0), else_=1), _rango_clase()]
    if venta is not None:
        q = q.outerjoin(venta, venta.c.sku == Producto.sku)
        orden.append(func.coalesce(venta.c.importe, 0).desc())
    orden.append(Producto.producto_id)
    return list(bd.scalars(q.order_by(*orden).limit(limite)))


def _vigilar(bd: Session, ids: list[int]) -> None:
    ya = set(bd.scalars(select(PrecioVigilado.producto_id).where(PrecioVigilado.producto_id.in_(ids or [0]))))
    for pid in ids:
        if pid not in ya:
            bd.add(PrecioVigilado(producto_id=pid, activo=True, origen=ORIGEN))
    bd.commit()


def _sin_presupuesto_esta_noche(bd: Session, desde_utc: datetime) -> bool:
    ids = list(bd.scalars(select(PrecioCorrida.corrida_id).where(PrecioCorrida.origen == ORIGEN,
                                                                 PrecioCorrida.iniciado_en >= desde_utc)))
    if not ids:
        return False
    return bool(bd.scalar(select(func.count()).select_from(PrecioCorridaProducto).where(
        PrecioCorridaProducto.corrida_id.in_(ids), PrecioCorridaProducto.estado == "sin_presupuesto")))


def revisar_nocturno(bd: Session) -> PrecioCorrida | None:
    """Lo llama el programador cada minuto. Regresa la corrida que arrancó, o None."""
    cfg = configuracion()
    if not cfg.precios_nocturno_activo or dfs.configurado():
        return None
    local = datetime.now(precios.zona())
    if not en_ventana(local.hour, cfg.precios_nocturno_desde, cfg.precios_nocturno_hasta):
        return None
    if precios.en_curso(bd):
        return None
    noche = inicio_noche(local, cfg.precios_nocturno_desde)
    if _sin_presupuesto_esta_noche(bd, noche):
        return None
    ultima = bd.scalar(select(PrecioCorrida).where(PrecioCorrida.origen == ORIGEN).order_by(PrecioCorrida.corrida_id.desc()))
    if ultima and ultima.estado == "fallida" and (ultima.terminado_en or ahora()) > ahora() - timedelta(minutes=30):
        return None  # falló hace poco: se espera media hora
    ids = candidatos(bd, cfg.precios_nocturno_lote)
    if not ids:
        return None
    _vigilar(bd, ids)
    c = precios.tomar_corrida(bd, local.date(), ORIGEN, forzar=True)
    if not c:
        return None
    c.lista = json.dumps({"producto_ids": ids, "lote": True}, ensure_ascii=False)
    bd.commit()
    log.info("Radar de precios: lote nocturno %s con %s productos", c.corrida_id, len(ids))
    precios.correr_aparte(c.corrida_id)
    return c


# ---------------------------------------------------------------- avance (banda de la pantalla)

@dataclass
class Avance:
    total: int
    validados: int
    dudosos: int
    sin_referencia: int
    sin_revisar: int
    al_dia: int  # validados cuya próxima revisión todavía no llega
    por_clase: dict[str, dict[str, int]]  # {AA: {total, validados}}
    ritmo_noche: int  # productos revisados la última noche
    noches_faltan: int | None
    activo: bool
    desde: int
    hasta: int
    lote: int


def avance(bd: Session) -> Avance:
    cfg = configuracion()
    clase = Producto.clasificacion
    filas = bd.execute(select(clase, PrecioVigilado.validacion, func.count(),
                              func.sum(case((PrecioVigilado.proxima_revision > ahora(), 1), else_=0)))
                       .select_from(Producto)
                       .outerjoin(PrecioVigilado, PrecioVigilado.producto_id == Producto.producto_id)
                       .where(_universo(cfg)).group_by(clase, PrecioVigilado.validacion)).all()
    total = validados = dudosos = sin_ref = sin_rev = al_dia = 0
    por_clase: dict[str, dict[str, int]] = {}
    for k, estado, n, vigentes in filas:
        k = (k or "").strip().upper()
        k = k if k in CLASES else "Sin clase"
        d = por_clase.setdefault(k, {"total": 0, "validados": 0})
        d["total"] += n
        total += n
        if estado == "validado":
            validados += n
            d["validados"] += n
            al_dia += vigentes or 0
        elif estado == "dudoso":
            dudosos += n
        elif estado == "sin_referencia":
            sin_ref += n
        else:
            sin_rev += n
    # Ritmo: productos que revisaron los lotes en las últimas 24 horas
    ritmo = bd.scalar(select(func.sum(PrecioCorrida.productos)).where(
        PrecioCorrida.origen == ORIGEN, PrecioCorrida.iniciado_en >= ahora() - timedelta(hours=24))) or 0
    faltan = sin_rev + dudosos
    orden = sorted(por_clase.items(), key=lambda kv: CLASES.index(kv[0]) if kv[0] in CLASES else 99)
    return Avance(total=total, validados=validados, dudosos=dudosos, sin_referencia=sin_ref, sin_revisar=sin_rev,
                  al_dia=al_dia, por_clase=dict(orden), ritmo_noche=int(ritmo),
                  noches_faltan=(-(-faltan // ritmo) if ritmo else None) if faltan else 0,
                  activo=cfg.precios_nocturno_activo, desde=cfg.precios_nocturno_desde, hasta=cfg.precios_nocturno_hasta,
                  lote=cfg.precios_nocturno_lote)
