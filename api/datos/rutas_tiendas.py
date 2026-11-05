"""Datos → Mapa de tiendas (/api/datos/tiendas): cada almacén de tblAlmacenes con su ubicación y su venta reciente.

La ubicación sale de MapaLatitud y MapaLongitud de tblAlmacenes. Si falta o cae fuera de México, la tienda se lista
como «sin ubicación» para que Sistemas la corrija; no se adivina.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, requiere
from datos.modelos import Producto, Tienda, VentaSemanal

router = APIRouter(prefix="/api/datos/tiendas", tags=["datos · tiendas"])
VER = requiere("datos.tiendas.ver")
SEMANAS = 13
# Caja de México (con un margen): una coordenada fuera de aquí es un error de captura
LAT = (14.0, 33.5)
LON = (-118.5, -86.0)


def ubicacion(t: Tienda) -> str:
    """ok, falta o fuera."""
    if t.latitud is None or t.longitud is None or (t.latitud == 0 and t.longitud == 0):
        return "falta"
    if LAT[0] <= t.latitud <= LAT[1] and LON[0] <= t.longitud <= LON[1]:
        return "ok"
    return "fuera"


def _ventana(bd: Session) -> tuple[date, date, date] | None:
    """(inicio de las 13 semanas anteriores, inicio de las últimas 13, última semana) o None si no hay venta."""
    ultima = bd.scalar(select(func.max(VentaSemanal.semana)))
    if not ultima:
        return None
    inicio = ultima - timedelta(weeks=SEMANAS - 1)
    return inicio - timedelta(weeks=SEMANAS), inicio, ultima


def _datos(t: Tienda) -> dict:
    return {"almacen": t.almacen, "nombre": t.nombre, "poblacion": t.poblacion, "estado": t.estado,
            "codigo_postal": t.codigo_postal, "region": t.region, "categoria": t.categoria, "grupo": t.grupo,
            "ruta": t.ruta, "estatus": t.estatus, "fecha_apertura": t.fecha_apertura, "latitud": t.latitud,
            "longitud": t.longitud, "ubicacion": ubicacion(t)}


@router.get("")
def lista(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> dict:
    v = _ventana(bd)
    actual, anterior = {}, {}
    if v:
        antes, inicio, ultima = v
        for destino, desde, hasta in ((anterior, antes, inicio - timedelta(days=1)), (actual, inicio, ultima)):
            for tienda, importe, piezas, tickets in bd.execute(
                    select(VentaSemanal.tienda, func.sum(VentaSemanal.importe), func.sum(VentaSemanal.piezas),
                           func.sum(VentaSemanal.tickets))
                    .where(VentaSemanal.semana >= desde, VentaSemanal.semana <= hasta).group_by(VentaSemanal.tienda)):
                destino[tienda] = (float(importe or 0), float(piezas or 0), int(tickets or 0))
    tiendas = []
    for t in bd.scalars(select(Tienda).order_by(Tienda.nombre)):
        a = actual.get(t.almacen)
        b = anterior.get(t.almacen)
        tiendas.append(_datos(t) | {
            "venta": a[0] if a else None, "piezas": a[1] if a else None, "tickets": a[2] if a else None,
            "cambio_pct": round((a[0] / b[0] - 1) * 100, 1) if a and b and b[0] > 0 else None})
    return {"tiendas": tiendas,
            "periodo": {"desde": v[1], "hasta": v[2] + timedelta(days=6), "semanas": SEMANAS} if v else None}


@router.get("/{almacen}")
def ficha(almacen: str, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> dict:
    t = bd.get(Tienda, almacen)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese almacén.")
    por_mes = [{"mes": m, "venta": float(i or 0), "piezas": float(p or 0)} for m, i, p in bd.execute(
        select(VentaSemanal.mes, func.sum(VentaSemanal.importe), func.sum(VentaSemanal.piezas))
        .where(VentaSemanal.tienda == almacen).group_by(VentaSemanal.mes).order_by(VentaSemanal.mes))]
    productos = []
    if v := _ventana(bd):
        productos = [{"sku": sku, "descripcion": d, "departamento": dep, "venta": float(i or 0), "piezas": float(p or 0)}
                     for sku, d, dep, i, p in bd.execute(
                         select(VentaSemanal.sku, Producto.descripcion, Producto.departamento,
                                func.sum(VentaSemanal.importe).label("i"), func.sum(VentaSemanal.piezas))
                         .outerjoin(Producto, Producto.sku == VentaSemanal.sku)
                         .where(VentaSemanal.tienda == almacen, VentaSemanal.semana >= v[1])
                         .group_by(VentaSemanal.sku, Producto.descripcion, Producto.departamento)
                         .order_by(func.sum(VentaSemanal.importe).desc()).limit(10))]
    return _datos(t) | {"por_mes": por_mes, "productos": productos}
