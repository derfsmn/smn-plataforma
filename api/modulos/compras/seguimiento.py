"""Revisión a 4, 8 y 12 semanas de lo que aceptó el comité (plan del radar inteligente, 17 nov 2026).

Compara lo pronosticado (rango bajo / medio / alto de piezas por tienda al mes) contra lo vendido en SMNBI y avisa al
comité si va arriba, en línea o abajo. En los «Aceptado a prueba» cuenta solo la venta de las tiendas de la prueba y
propone ampliar, mantener o retirar. El SKU se toma del que capturó Compras al darlo de alta o, si no, del código de
barras de la idea o propuesta en el catálogo. Sin IA.
"""
import json
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datos.modelos import Producto, VentaSemanal
from modulos.compras import pronostico as pn
from modulos.compras import propuestas as pr
from modulos.compras import realidad_producto as rr
from modulos.compras.modelos_comite import ComiteProducto, ProductoSeguimiento
from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
from modulos.compras.modelos_propuestas import Propuesta
from nucleo.modelos import ahora
from nucleo.notificaciones import notificar

log = logging.getLogger("smn.compras.seguimiento")

ACEPTADOS = ("aceptado", "a_prueba")
RESULTADO = {"arriba": "va arriba del pronóstico", "en_linea": "va en línea con el pronóstico",
             "abajo": "va abajo del pronóstico", "sin_venta": "no tiene venta todavía",
             "sin_sku": "no se puede revisar: falta el SKU con que se dio de alta"}
_ULTIMO: dict = {}


def nombre_de(bd: Session, i: ComiteProducto) -> str:
    if i.propuesta_id:
        return bd.get(Propuesta, i.propuesta_id).producto or "Producto sin nombre"
    return bd.get(ProductoIdea, i.idea_id).nombre


def sku_de(bd: Session, i: ComiteProducto) -> str | None:
    if i.sku:
        return i.sku
    codigo = None
    if i.idea_id:
        codigo = bd.get(ProductoIdea, i.idea_id).codigo_barras
    elif i.propuesta_id:
        try:
            r = pr.Respuestas.model_validate_json(bd.get(Propuesta, i.propuesta_id).respuestas)
            codigo = next((x.codigo_barras for x in r.presentaciones if x.codigo_barras), None)
        except (ValueError, TypeError):
            codigo = None
    if not codigo:
        return None
    return bd.scalar(select(Producto.sku).where(Producto.codigo_barras == codigo).order_by(Producto.activo.desc()))


def _pronostico(bd: Session, i: ComiteProducto) -> pn.Pronostico | None:
    q = select(ProductoEvaluacion.pronostico).where(ProductoEvaluacion.pronostico.is_not(None),
                                                    ProductoEvaluacion.estado == "lista")
    q = q.where(ProductoEvaluacion.propuesta_id == i.propuesta_id) if i.propuesta_id else q.where(
        ProductoEvaluacion.idea_id == i.idea_id)
    if i.decision_en:
        q = q.where(ProductoEvaluacion.creada_en <= i.decision_en)
    try:
        return pn.Pronostico.de_json(bd.scalar(q.order_by(ProductoEvaluacion.evaluacion_id.desc())))
    except (ValueError, TypeError):
        return None


def _real(bd: Session, sku: str, desde: date, hasta: date, tiendas: list[str] | None, mayoreo: set[str]
          ) -> tuple[float | None, int]:
    q = select(func.sum(rr.NETAS), func.count(VentaSemanal.tienda.distinct())).where(
        VentaSemanal.sku == sku, VentaSemanal.semana >= desde, VentaSemanal.semana <= hasta)
    if tiendas:
        q = q.where(VentaSemanal.tienda.in_(tiendas))
    elif mayoreo:
        q = q.where(VentaSemanal.tienda.not_in(mayoreo))
    piezas, n = bd.execute(q).one()
    if not piezas or piezas <= 0:
        return None, 0
    semanas = (hasta - desde).days // 7 + 1
    return float(piezas) / max(1, n) / semanas * rr.SEMANAS_MES, n


def revisar(bd: Session) -> int:
    """Crea las revisiones que ya tocan y avisa a quien registró la decisión. Devuelve cuántas creó."""
    v = rr.ventana(bd)
    hechas = 0
    for i in bd.scalars(select(ComiteProducto).where(ComiteProducto.decision.in_(ACEPTADOS),
                                                     ComiteProducto.decision_en.is_not(None))):
        ya = {s.semana for s in bd.scalars(select(ProductoSeguimiento).where(ProductoSeguimiento.item_id == i.item_id))}
        if len(ya) == 3:
            continue
        sku = sku_de(bd, i)
        decidido = i.decision_en.date()
        if not sku:
            if 4 not in ya and ahora().date() >= decidido + timedelta(weeks=5):
                _guardar(bd, i, 4, None, None, 0, "sin_sku", None)
                hechas += 1
            continue
        if not v:
            continue
        inicio = bd.scalar(select(func.min(VentaSemanal.semana)).where(
            VentaSemanal.sku == sku, VentaSemanal.semana >= decidido - timedelta(days=6)))
        tiendas = json.loads(i.prueba_tiendas or "[]") if i.decision == "a_prueba" else None
        p = _pronostico(bd, i)
        for tramo in pn.TRAMOS:
            if tramo in ya:
                continue
            if inicio is None:
                if ahora().date() >= decidido + timedelta(weeks=tramo + 1) and v.fin >= decidido + timedelta(weeks=tramo):
                    _guardar(bd, i, tramo, p, None, 0, "sin_venta", "retirar" if tramo == 12 and tiendas else None)
                    hechas += 1
                continue
            desde, hasta = inicio + timedelta(weeks=tramo - 4), inicio + timedelta(weeks=tramo - 1)
            if hasta > v.fin:
                break  # todavía no hay venta cargada de esas semanas
            real, n = _real(bd, sku, desde, hasta, tiendas, v.mayoreo)
            rango = p.rango(tramo) if p else None
            if real is None:
                resultado = "sin_venta"
            elif rango is None:
                resultado = "en_linea"
            else:
                resultado = "arriba" if real > rango[2] else "abajo" if real < rango[0] else "en_linea"
            propuesta = None
            if tiendas:
                if tramo < 12:
                    propuesta = "retirar" if resultado == "sin_venta" and tramo == 8 else "mantener"
                else:
                    propuesta = {"arriba": "ampliar", "en_linea": "ampliar"}.get(resultado, "retirar")
            _guardar(bd, i, tramo, p, real, n, resultado, propuesta)
            hechas += 1
    bd.commit()
    return hechas


def _guardar(bd: Session, i: ComiteProducto, tramo: int, p: pn.Pronostico | None, real: float | None, tiendas: int,
             resultado: str, propuesta: str | None) -> None:
    rango = p.rango(tramo) if p else None
    nombre = nombre_de(bd, i)
    texto = f"«{nombre}» a {tramo} semanas {RESULTADO[resultado]}"
    if real is not None:
        texto += f": {real:,.1f} piezas por tienda al mes en {tiendas} tienda(s)"
        if rango:
            texto += f" (pronóstico de {rango[0]:,.1f} a {rango[2]:,.1f})"
    texto += "."
    if propuesta:
        texto += {"ampliar": " Se propone ampliarlo a más tiendas.", "mantener": " Se propone mantenerlo y volver a revisar.",
                  "retirar": " Se propone retirarlo y aplicar la condición con el proveedor."}[propuesta]
    bd.add(ProductoSeguimiento(item_id=i.item_id, semana=tramo, fecha=ahora().date(), real=real, tiendas=tiendas or None,
                               pronostico_bajo=rango[0] if rango else None, pronostico_medio=rango[1] if rango else None,
                               pronostico_alto=rango[2] if rango else None, resultado=resultado, propuesta=propuesta,
                               texto=texto[:1000]))
    if i.decision_por:
        notificar(bd, i.decision_por, f"Revisión a {tramo} semanas: {nombre}"[:200], texto,
                  liga="/compras/propuestas/comite?vista=aceptados", clave=f"seguimiento-{i.item_id}-{tramo}")


def revisar_programa(bd: Session) -> None:
    """Una vez al día, desde el programador de la API."""
    hoy = datetime.now().date()
    if _ULTIMO.get("dia") == hoy:
        return
    _ULTIMO["dia"] = hoy
    try:
        if n := revisar(bd):
            log.info("Seguimiento de productos aceptados: %s revisiones nuevas", n)
    except Exception:  # noqa: BLE001
        log.exception("Seguimiento de productos aceptados falló")
