"""Buscador de productos de Compras y ficha completa de cada artículo (pedido de Diego, 22 nov 2026: «necesito un
buscador de productos»; eligió la opción con ficha completa).

- Busca por nombre, SKU, código de barras, marca o proveedor, sin importar acentos ni mayúsculas. Cada palabra tiene
  que aparecer en alguno de esos campos («magnesio 60» encuentra «Citrato de Magnesio 60 cápsulas»).
- Busca en el catálogo (datos.producto) y también en las ideas y propuestas del radar de productos.
- La ficha junta en una pantalla lo que antes estaba en cuatro: precio y membresía, venta de SMNBI, inventario del
  último corte, costo y margen, proveedor con su calificación, nuestro precio contra el mercado y, si el mismo
  código de barras está en una idea o propuesta, su semáforo.
- Solo consulta: aquí no se cambia nada.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, case, func, or_, select, true
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, usuario_actual
from datos.modelos import (CostoArticulo, Inventario, Producto, Proveedor, ProveedorCalificacion, ProveedorEvaluacion, Tienda,
                           VentaSemanal)
from modulos.compras import precios
from modulos.compras import realidad_producto as rp
from modulos.compras.modelos_precios import PrecioCorrida, PrecioCorridaProducto, PrecioVigilado
from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
from modulos.compras.modelos_propuestas import Propuesta, PropuestaPresentacion as Presentacion

router = APIRouter(prefix="/api/compras/buscador", tags=["compras · buscador de productos"])

PERMISOS = ("compras.productos.ver", "compras.precios.ver", "compras.propuestas.ver", "datos.productos.ver")
# Costo y margen solo para quien tiene este permiso (revisión de seguridad 2026-11-22, B1)
VER_COSTOS = "compras.costos.ver"
SIN_ACENTOS = "Latin1_General_CI_AI"
SEMANAS = 26


def acceso(ctx: Contexto = Depends(usuario_actual)) -> Contexto:
    if not any(ctx.puede(p) for p in PERMISOS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para buscar productos.")
    return ctx


def _palabras(q: str) -> list[str]:
    # Los comodines de LIKE se escapan para que «50%» busque «50%» y no «50 y lo que sea»
    limpias = [p.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]") for p in q.strip().split()]
    return [p for p in limpias if p][:6]


def _todas(palabras: list[str], columnas) -> list:
    """Cada palabra en alguna de las columnas, sin importar acentos."""
    return [or_(*(func.coalesce(c, "").collate(SIN_ACENTOS).like(f"%{p}%") for c in columnas)) for p in palabras]


# ---------------------------------------------------------------- búsqueda

class Resultado(BaseModel):
    tipo: str  # catalogo / idea / propuesta
    id: int  # producto_id, evaluacion_id (idea) o propuesta_id
    titulo: str
    detalle: str
    imagen: str | None = None
    precio: Decimal | None = None
    color: str | None = None
    activo: bool = True


class Busqueda(BaseModel):
    q: str
    catalogo: list[Resultado]
    catalogo_total: int
    nuevos: list[Resultado]


def _detalle(*partes: str | None) -> str:
    return " · ".join(p for p in partes if p)


@router.get("", response_model=Busqueda)
def buscar(q: str = Query("", max_length=120), limite: int = Query(20, ge=1, le=50), ctx: Contexto = Depends(acceso),
           bd: Session = Depends(obtener_bd)) -> Busqueda:
    palabras = _palabras(q)
    if not palabras or len(q.strip()) < 2:
        return Busqueda(q=q, catalogo=[], catalogo_total=0, nuevos=[])
    texto = q.strip()

    # Catálogo: lo exacto primero (SKU o código de barras igual), luego los activos, luego por nombre
    filtro = and_(*_todas(palabras, (Producto.sku, Producto.descripcion, Producto.marca, Producto.codigo_barras,
                                     Producto.nombre_proveedor)))
    total = bd.scalar(select(func.count()).select_from(Producto).where(filtro)) or 0
    exacto = case((or_(Producto.sku == texto, Producto.codigo_barras == texto), 0), else_=1)
    filas = bd.scalars(select(Producto).where(filtro)
                       .order_by(exacto, case((Producto.activo == true(), 0), else_=1), Producto.descripcion)
                       .limit(limite)).all()
    catalogo = [Resultado(tipo="catalogo", id=p.producto_id, titulo=p.descripcion or p.sku,
                          detalle=_detalle(p.sku, p.marca, p.departamento),
                          imagen=p.liga_imagen or p.imagen_cdn, precio=p.precio_lista_con_impuestos, activo=p.activo)
                for p in filas]

    nuevos: list[Resultado] = []
    if ctx.puede("compras.productos.ver"):
        ideas = bd.execute(
            select(ProductoIdea.idea_id, ProductoIdea.nombre, ProductoIdea.marca, ProductoIdea.departamento,
                   ProductoEvaluacion.evaluacion_id, ProductoEvaluacion.color, ProductoEvaluacion.color_final)
            .join(ProductoEvaluacion, and_(ProductoEvaluacion.idea_id == ProductoIdea.idea_id,
                                           ProductoEvaluacion.vigente == true()))
            .where(*_todas(palabras, (ProductoIdea.nombre, ProductoIdea.marca, ProductoIdea.codigo_barras,
                                      ProductoIdea.proveedor_nuevo)))
            .order_by(ProductoIdea.creada_en.desc()).limit(10)).all()
        nuevos += [Resultado(tipo="idea", id=ev, titulo=nombre, detalle=_detalle("Idea de Compras", marca, depto),
                             color=final or color) for _, nombre, marca, depto, ev, color, final in ideas]
    if ctx.puede("compras.propuestas.ver"):
        con_barras = select(Presentacion.propuesta_id).where(
            *_todas(palabras, (Presentacion.codigo_barras, Presentacion.descripcion)))
        props = bd.execute(
            select(Propuesta.propuesta_id, Propuesta.folio, Propuesta.producto, Propuesta.marca, Propuesta.estado,
                   ProductoEvaluacion.color, ProductoEvaluacion.color_final)
            .outerjoin(ProductoEvaluacion, and_(ProductoEvaluacion.propuesta_id == Propuesta.propuesta_id,
                                                ProductoEvaluacion.vigente == true()))
            .where(Propuesta.estado != "borrador",
                   or_(and_(*_todas(palabras, (Propuesta.producto, Propuesta.marca, Propuesta.folio))),
                       Propuesta.propuesta_id.in_(con_barras)))
            .order_by(Propuesta.creada_en.desc()).limit(10)).all()
        nuevos += [Resultado(tipo="propuesta", id=pid, titulo=producto or folio or f"Propuesta {pid}",
                             detalle=_detalle(f"Propuesta {folio}" if folio else "Propuesta", marca), color=final or color)
                   for pid, folio, producto, marca, _, color, final in props]
    return Busqueda(q=q, catalogo=catalogo, catalogo_total=total, nuevos=nuevos)


# ---------------------------------------------------------------- ficha

class Semana(BaseModel):
    semana: date
    piezas: float
    importe: float


class TiendaVenta(BaseModel):
    almacen: str
    nombre: str
    piezas: float


class Venta(BaseModel):
    desde: date
    hasta: date
    nota: str
    semanas: list[Semana]
    piezas: float
    importe: float
    al_mes: float | None
    recientes: float
    anteriores: float
    tendencia_pct: float | None
    tiendas: int
    margen_real_pct: float | None
    mejores: list[TiendaVenta]


class TiendaExistencia(BaseModel):
    almacen: str
    nombre: str
    existencia: float


class InventarioFicha(BaseModel):
    corte: date
    existencia: float
    tiendas_con: int
    tiendas_en_cero: int  # tiendas que lo vendieron en la ventana y hoy no tienen
    dias: float | None  # existencia ÷ venta diaria de las últimas 13 semanas
    mayores: list[TiendaExistencia]


class Costo(BaseModel):
    ultimo: Decimal | None
    fecha_ultima: date | None
    promedio_12m: Decimal | None
    piezas_12m: Decimal | None
    margen_pct: float | None  # contra el precio de lista sin impuestos, con el último costo


class ProveedorFicha(BaseModel):
    codigo: str
    nombre: str | None
    dias_entrega: int | None
    condicion: str | None
    puntaje: int | None
    color: str | None
    surtido_pct: float | None
    dias_reales: float | None


class Mercado(BaseModel):
    fecha: date
    mediana: Decimal | None
    minimo: Decimal | None
    maximo: Decimal | None
    vendedores: int
    diferencia_pct: Decimal | None
    color: str | None
    vigilado: bool


class Relacionado(BaseModel):
    tipo: str  # idea / propuesta
    id: int
    titulo: str
    color: str | None
    puntaje: int | None


class Ficha(BaseModel):
    id: int
    sku: str
    descripcion: str | None
    marca: str | None
    departamento: str | None
    rama: str | None
    subcategoria: str | None
    clasificacion: str | None
    codigo_barras: str | None
    imagen: str | None
    liga_producto: str | None
    activo: bool
    precio_lista: Decimal | None  # con impuestos
    precio_membresia: Decimal | None  # con impuestos
    precio_tienda_en_linea: Decimal | None
    iva_pct: Decimal | None
    venta: Venta | None
    inventario: InventarioFicha | None
    costo: Costo | None
    proveedor: ProveedorFicha | None
    mercado: Mercado | None
    relacionados: list[Relacionado]


def _nombres_tienda(bd: Session, almacenes: list[str]) -> dict[str, str]:
    if not almacenes:
        return {}
    return dict(bd.execute(select(Tienda.almacen, Tienda.nombre).where(Tienda.almacen.in_(almacenes))).all())


def _venta(bd: Session, sku: str) -> Venta | None:
    v = rp.ventana(bd, SEMANAS)
    if not v:
        return None
    filas = bd.execute(select(VentaSemanal.semana, func.sum(rp.NETAS), func.sum(VentaSemanal.importe))
                       .where(VentaSemanal.sku == sku, *v.filtro()).group_by(VentaSemanal.semana)).all()
    por_semana = {s: (float(p or 0), float(i or 0)) for s, p, i in filas}
    semanas = [Semana(semana=v.desde + timedelta(weeks=k), piezas=por_semana.get(v.desde + timedelta(weeks=k), (0, 0))[0],
                      importe=por_semana.get(v.desde + timedelta(weeks=k), (0, 0))[1]) for k in range(SEMANAS)]
    piezas = sum(s.piezas for s in semanas)
    importe = sum(s.importe for s in semanas)
    datos = rp.venta_por_sku(bd, v, [sku]).get(sku)
    recientes = datos.recientes if datos else 0.0
    anteriores = datos.anteriores if datos else 0.0
    mejores = bd.execute(select(VentaSemanal.tienda, func.sum(rp.NETAS).label("p"))
                         .where(VentaSemanal.sku == sku, *v.filtro()).group_by(VentaSemanal.tienda)
                         .having(func.sum(rp.NETAS) > 0).order_by(func.sum(rp.NETAS).desc()).limit(8)).all()
    nombres = _nombres_tienda(bd, [t for t, _ in mejores])
    margen = rp.margen_sku(bd, v, sku)
    return Venta(desde=v.desde, hasta=v.hasta, nota=v.texto(), semanas=semanas, piezas=piezas, importe=importe,
                 al_mes=datos.al_mes if datos else None, recientes=recientes, anteriores=anteriores,
                 tendencia_pct=(recientes / anteriores - 1) * 100 if anteriores > 0 else None,
                 tiendas=datos.tiendas if datos else 0, margen_real_pct=float(margen) if margen is not None else None,
                 mejores=[TiendaVenta(almacen=t, nombre=nombres.get(t, t), piezas=float(p)) for t, p in mejores])


def _inventario(bd: Session, sku: str, venta: Venta | None) -> InventarioFicha | None:
    corte = bd.scalar(select(func.max(Inventario.fecha_corte)))
    if not corte:
        return None
    filas = bd.execute(select(Inventario.almacen, func.sum(Inventario.existencia))
                       .where(Inventario.fecha_corte == corte, Inventario.sku == sku)
                       .group_by(Inventario.almacen)).all()
    existencias = {a: float(e or 0) for a, e in filas}
    total = sum(e for e in existencias.values() if e > 0)
    con = [a for a, e in existencias.items() if e > 0]
    vendieron = {t.almacen for t in venta.mejores} if venta else set()
    if venta:
        v = rp.ventana(bd, SEMANAS)
        vendieron = set(bd.scalars(select(VentaSemanal.tienda).where(VentaSemanal.sku == sku, *v.filtro(), rp.NETAS > 0)
                                   .distinct()).all()) if v else vendieron
    diaria = venta.recientes / (rp.SEMANAS_TENDENCIA * 7) if venta and venta.recientes > 0 else None
    mayores = sorted(con, key=lambda a: -existencias[a])[:8]
    nombres = _nombres_tienda(bd, mayores)
    return InventarioFicha(corte=corte, existencia=total, tiendas_con=len(con),
                           tiendas_en_cero=len([t for t in vendieron if existencias.get(t, 0) <= 0]),
                           dias=total / diaria if diaria else None,
                           mayores=[TiendaExistencia(almacen=a, nombre=nombres.get(a, a), existencia=existencias[a])
                                    for a in mayores])


def _proveedor(bd: Session, codigo: str | None, nombre: str | None) -> ProveedorFicha | None:
    prov = bd.get(Proveedor, codigo) if codigo else None
    if not prov and not codigo:
        return None
    ultima = bd.scalar(select(ProveedorEvaluacion.evaluacion_id).where(ProveedorEvaluacion.estado == "completa")
                       .order_by(ProveedorEvaluacion.evaluacion_id.desc()).limit(1))
    cal = bd.get(ProveedorCalificacion, (ultima, codigo)) if ultima and codigo else None
    cumple = rp.cumplimiento(bd, codigo) if codigo else None
    return ProveedorFicha(codigo=codigo, nombre=(prov.nombre if prov else None) or nombre,
                          dias_entrega=prov.dias_entrega if prov else None, condicion=prov.condicion if prov else None,
                          puntaje=cal.puntaje if cal else None, color=cal.color if cal else None,
                          surtido_pct=cumple.surtido_pct if cumple else None, dias_reales=cumple.dias_reales if cumple else None)


def _mercado(bd: Session, producto_id: int) -> Mercado | None:
    fila = bd.execute(select(PrecioCorridaProducto, PrecioCorrida.fecha)
                      .join(PrecioCorrida, PrecioCorrida.corrida_id == PrecioCorridaProducto.corrida_id)
                      .where(PrecioCorridaProducto.producto_id == producto_id, PrecioCorridaProducto.mediana.is_not(None))
                      .order_by(PrecioCorridaProducto.corrida_id.desc()).limit(1)).first()
    if not fila:
        return None
    f, fecha = fila
    dif = precios.dif_nuestro(f)
    limite = bd.scalar(select(PrecioVigilado.limite_pct).where(PrecioVigilado.producto_id == producto_id))
    vigilado = bool(bd.scalar(select(PrecioVigilado.activo).where(PrecioVigilado.producto_id == producto_id)))
    return Mercado(fecha=fecha.date() if isinstance(fecha, datetime) else fecha, mediana=f.mediana, minimo=f.minimo,
                   maximo=f.maximo, vendedores=f.vendedores, diferencia_pct=dif, color=precios.color(dif, limite),
                   vigilado=vigilado)


def _relacionados(bd: Session, ctx: Contexto, codigo_barras: str | None) -> list[Relacionado]:
    if not codigo_barras or not ctx.puede("compras.productos.ver"):
        return []
    salida = []
    for ev, nombre, color, final, puntaje in bd.execute(
            select(ProductoEvaluacion.evaluacion_id, ProductoIdea.nombre, ProductoEvaluacion.color,
                   ProductoEvaluacion.color_final, ProductoEvaluacion.puntaje)
            .join(ProductoIdea, ProductoIdea.idea_id == ProductoEvaluacion.idea_id)
            .where(ProductoEvaluacion.vigente == true(), ProductoIdea.codigo_barras == codigo_barras)).all():
        salida.append(Relacionado(tipo="idea", id=ev, titulo=nombre, color=final or color, puntaje=puntaje))
    if ctx.puede("compras.propuestas.ver"):
        for pid, producto, color, final, puntaje in bd.execute(
                select(Propuesta.propuesta_id, Propuesta.producto, ProductoEvaluacion.color, ProductoEvaluacion.color_final,
                       ProductoEvaluacion.puntaje)
                .join(Presentacion, Presentacion.propuesta_id == Propuesta.propuesta_id)
                .outerjoin(ProductoEvaluacion, and_(ProductoEvaluacion.propuesta_id == Propuesta.propuesta_id,
                                                    ProductoEvaluacion.vigente == true()))
                .where(Presentacion.codigo_barras == codigo_barras, Propuesta.estado != "borrador").distinct()).all():
            salida.append(Relacionado(tipo="propuesta", id=pid, titulo=producto or f"Propuesta {pid}", color=final or color,
                                      puntaje=puntaje))
    return salida


@router.get("/producto/{producto_id}", response_model=Ficha)
def ficha(producto_id: int, ctx: Contexto = Depends(acceso), bd: Session = Depends(obtener_bd)) -> Ficha:
    p = bd.get(Producto, producto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese producto no existe.")
    c = bd.get(CostoArticulo, p.sku)
    sin_iva = p.precio_lista
    if not ctx.puede(VER_COSTOS):
        c = None
    margen = (float((sin_iva - c.costo_ultimo) / sin_iva) * 100
              if c and c.costo_ultimo is not None and sin_iva else None)
    venta = _venta(bd, p.sku)
    if venta and not ctx.puede(VER_COSTOS):
        venta.margen_real_pct = None
    return Ficha(
        id=p.producto_id, sku=p.sku, descripcion=p.descripcion, marca=p.marca, departamento=p.departamento, rama=p.rama,
        subcategoria=p.subcategoria, clasificacion=p.clasificacion, codigo_barras=p.codigo_barras,
        imagen=p.liga_imagen or p.imagen_cdn, liga_producto=p.liga_producto, activo=p.activo,
        precio_lista=p.precio_lista_con_impuestos, precio_membresia=p.precio_membresia_con_impuestos,
        precio_tienda_en_linea=p.precio_tienda_en_linea, iva_pct=p.iva_pct,
        venta=venta,
        inventario=_inventario(bd, p.sku, venta),
        costo=Costo(ultimo=c.costo_ultimo, fecha_ultima=c.fecha_ultima, promedio_12m=c.costo_12m, piezas_12m=c.piezas_12m,
                    margen_pct=margen) if c else None,
        proveedor=_proveedor(bd, (c.proveedor if c else None) or p.codigo_proveedor, p.nombre_proveedor),
        mercado=_mercado(bd, p.producto_id),
        relacionados=_relacionados(bd, ctx, p.codigo_barras),
    )
