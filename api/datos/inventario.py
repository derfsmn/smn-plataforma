"""Datos → Salud de inventario (Diego eligió «Salud de inventario», 2026-10-29).

Cruza la foto de inventario más reciente con la venta de las últimas 13 semanas de cada tienda y producto:
- **Sin venta:** tiene existencia y no vendió ni una pieza en 13 semanas (dinero detenido).
- **Exceso:** le alcanza para más de 180 días al ritmo de las últimas 13 semanas.
- **En cero:** vende al menos una pieza por semana y en la foto no tenía existencia (posible faltante).

Reglas:
- Solo cuentan las tiendas que vendieron en la ventana; mayoreo (MAY) y los almacenes sin venta (CEDIS u otros) se
  muestran aparte con su valor, no como «sin venta».
- Valor = existencia × costo promedio de la foto de inventario; si no trae, el último costo de compra.
- La foto y la venta pueden ser de fechas distintas: la pantalla dice de cuándo es cada una.
- Todo se suma en SQL Server (son cientos de miles de renglones) y se cruza con JOIN, no con listas de parámetros.
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Float, and_, case, cast, func, literal, select
from sqlalchemy.orm import Session

from datos.modelos import CostoArticulo, Inventario, Producto, Tienda, VentaSemanal
from modulos.compras import realidad_producto as rr

SEMANAS = 13
DIAS = SEMANAS * 7
DIAS_EXCESO = 180
MIN_PIEZAS_FALTANTE = SEMANAS  # una pieza por semana
TIPOS = ("sin_venta", "exceso", "en_cero")


@dataclass
class Base:
    corte: date
    ventana: rr.Ventana
    tabla: object  # subconsulta con tienda, sku, existencia, costo, piezas, importe, valor, dias, estado


def base(bd: Session) -> Base | None:
    corte = bd.scalar(select(func.max(Inventario.fecha_corte)))
    v = rr.ventana(bd, SEMANAS)
    if not corte or not v:
        return None
    inv = (select(Inventario.almacen.label("tienda"), Inventario.sku, func.sum(Inventario.existencia).label("ex"),
                  func.max(Inventario.costo_promedio).label("cp"))
           .where(Inventario.fecha_corte == corte).group_by(Inventario.almacen, Inventario.sku).subquery())
    ven = (select(VentaSemanal.tienda, VentaSemanal.sku, func.sum(rr.NETAS).label("pz"),
                  func.sum(VentaSemanal.importe).label("imp"))
           .where(*v.filtro()).group_by(VentaSemanal.tienda, VentaSemanal.sku).subquery())
    activas = select(VentaSemanal.tienda).where(*v.filtro()).distinct().subquery()
    tienda = func.coalesce(inv.c.tienda, ven.c.tienda)
    sku = func.coalesce(inv.c.sku, ven.c.sku)
    unido = (select(tienda.label("tienda"), sku.label("sku"), func.coalesce(inv.c.ex, 0).label("ex"),
                    func.coalesce(inv.c.cp, CostoArticulo.costo_ultimo).label("costo"),
                    func.coalesce(ven.c.pz, 0).label("pz"), func.coalesce(ven.c.imp, 0).label("imp"))
             .select_from(inv.join(ven, and_(inv.c.tienda == ven.c.tienda, inv.c.sku == ven.c.sku), full=True))
             .outerjoin(CostoArticulo, CostoArticulo.sku == sku)
             .where(tienda.in_(select(activas.c.tienda))).subquery())
    ex, pz = unido.c.ex, unido.c.pz
    dias = case((and_(ex > 0, pz > 0), cast(ex, Float) * DIAS / cast(func.nullif(pz, 0), Float)), else_=None)
    estado = case((and_(ex > 0, pz <= 0), literal("sin_venta")),
                  (and_(ex > 0, ex * DIAS > pz * DIAS_EXCESO), literal("exceso")),
                  (and_(ex <= 0, pz >= MIN_PIEZAS_FALTANTE), literal("en_cero")),
                  (ex > 0, literal("sano")), else_=literal("sin_existencia"))
    tabla = select(unido.c.tienda, unido.c.sku, ex.label("existencia"), unido.c.costo, pz.label("piezas"),
                   unido.c.imp.label("importe"),
                   case((ex > 0, ex * func.coalesce(unido.c.costo, 0)), else_=0).label("valor"),
                   dias.label("dias"), estado.label("estado")).subquery()
    return Base(corte=corte, ventana=v, tabla=tabla)


def _sumas(t):
    valor = func.sum(t.c.valor)
    return [valor.label("valor"),
            func.sum(case((t.c.estado == "sin_venta", t.c.valor), else_=0)).label("valor_sin_venta"),
            func.sum(case((t.c.estado == "exceso", t.c.valor), else_=0)).label("valor_exceso"),
            func.sum(case((t.c.existencia > 0, t.c.existencia), else_=0)).label("existencia"),
            func.sum(t.c.piezas).label("piezas"),
            func.sum(case((t.c.estado == "sin_venta", 1), else_=0)).label("n_sin_venta"),
            func.sum(case((t.c.estado == "exceso", 1), else_=0)).label("n_exceso"),
            func.sum(case((t.c.estado == "en_cero", 1), else_=0)).label("n_en_cero"),
            func.sum(case((t.c.existencia > 0, 1), else_=0)).label("n_con_existencia")]


class _Suma:
    CAMPOS = ("valor", "valor_sin_venta", "valor_exceso", "existencia", "piezas", "n_sin_venta", "n_exceso",
              "n_en_cero", "n_con_existencia")

    def __init__(self):
        for c in self.CAMPOS:
            setattr(self, c, 0.0)

    def mas(self, r) -> None:
        for c in self.CAMPOS:
            setattr(self, c, getattr(self, c) + float(getattr(r, c) or 0))


def _fila(r) -> dict:
    existencia, piezas = float(r.existencia or 0), float(r.piezas or 0)
    return {"valor": float(r.valor or 0), "valor_sin_venta": float(r.valor_sin_venta or 0),
            "valor_exceso": float(r.valor_exceso or 0), "existencia": existencia, "piezas": piezas,
            "dias": round(existencia / (piezas / DIAS)) if piezas > 0 and existencia > 0 else None,
            "sin_venta": int(r.n_sin_venta or 0), "exceso": int(r.n_exceso or 0), "en_cero": int(r.n_en_cero or 0),
            "con_existencia": int(r.n_con_existencia or 0)}


def _filtros(t, tienda: str | None, departamento: str | None):
    f = []
    if tienda:
        f.append(t.c.tienda == tienda)
    if departamento:
        f.append(func.coalesce(Producto.departamento, "Sin departamento") == departamento)
    return f


def resumen(bd: Session, tienda: str | None = None, departamento: str | None = None) -> dict | None:
    b = base(bd)
    if not b:
        return None
    t = b.tabla
    desde = t.outerjoin(Producto, Producto.sku == t.c.sku)
    f = _filtros(t, tienda, departamento)
    # Una sola pasada por tienda y departamento (la consulta pesada); los totales se suman aquí
    tiendas = {a: (n, c) for a, n, c in bd.execute(select(Tienda.almacen, Tienda.nombre, Tienda.categoria))}
    cubo = bd.execute(select(t.c.tienda, Producto.departamento.label("d"), *_sumas(t)).select_from(desde).where(*f)
                      .group_by(t.c.tienda, Producto.departamento)).all()
    total, por_t, por_d = _Suma(), {}, {}
    for r in cubo:
        total.mas(r)
        por_t.setdefault(r.tienda, _Suma()).mas(r)
        por_d.setdefault(r.d or "Sin departamento", _Suma()).mas(r)
    por_tienda = [{"almacen": k, "nombre": tiendas.get(k, (k, None))[0], "categoria": tiendas.get(k, (None, None))[1]}
                  | _fila(v) for k, v in por_t.items()]
    por_departamento = [{"departamento": k} | _fila(v) for k, v in por_d.items()]
    # Almacenes con inventario que no venden en la ventana (CEDIS, mayoreo u otros): solo su valor
    vendieron = select(VentaSemanal.tienda).where(*b.ventana.filtro()).distinct().subquery()
    costo = func.coalesce(Inventario.costo_promedio, CostoArticulo.costo_ultimo, 0)
    otros = [{"almacen": a, "nombre": tiendas.get(a, (a, None))[0], "categoria": tiendas.get(a, (None, None))[1],
              "valor": float(val or 0), "existencia": float(ex or 0)}
             for a, val, ex in bd.execute(
                 select(Inventario.almacen, func.sum(Inventario.existencia * costo), func.sum(Inventario.existencia))
                 .outerjoin(CostoArticulo, CostoArticulo.sku == Inventario.sku)
                 .where(Inventario.fecha_corte == b.corte, Inventario.existencia > 0,
                        Inventario.almacen.not_in(select(vendieron.c.tienda)))
                 .group_by(Inventario.almacen))]
    return {"corte": b.corte, "venta": {"desde": b.ventana.desde, "hasta": b.ventana.hasta, "texto": b.ventana.texto()},
            "reglas": {"semanas": SEMANAS, "dias_exceso": DIAS_EXCESO, "min_piezas_faltante": MIN_PIEZAS_FALTANTE},
            "total": _fila(total), "por_tienda": sorted(por_tienda, key=lambda x: -x["valor_sin_venta"]),
            "por_departamento": sorted(por_departamento, key=lambda x: -x["valor_sin_venta"]),
            "otros_almacenes": sorted(otros, key=lambda x: -x["valor"])}


def productos(bd: Session, tipo: str, tienda: str | None = None, departamento: str | None = None,
              limite: int = 200) -> list[dict]:
    """Renglones tienda-producto de un tipo: sin venta y exceso por valor; en cero por lo que vendían."""
    b = base(bd)
    if not b or tipo not in TIPOS:
        return []
    t = b.tabla
    orden = t.c.piezas.desc() if tipo == "en_cero" else t.c.valor.desc()
    tiendas = dict(bd.execute(select(Tienda.almacen, Tienda.nombre)).all())
    q = (select(t, Producto.descripcion, Producto.departamento, Producto.nombre_proveedor)
         .outerjoin(Producto, Producto.sku == t.c.sku)
         .where(t.c.estado == tipo, *_filtros(t, tienda, departamento)).order_by(orden).limit(limite))
    salida = []
    for r in bd.execute(q):
        salida.append({"almacen": r.tienda, "tienda": tiendas.get(r.tienda, r.tienda), "sku": r.sku,
                       "descripcion": r.descripcion, "departamento": r.departamento, "proveedor": r.nombre_proveedor,
                       "existencia": float(r.existencia or 0), "costo": float(r.costo) if r.costo is not None else None,
                       "valor": float(r.valor or 0), "piezas": float(r.piezas or 0),
                       "por_semana": round(float(r.piezas or 0) / SEMANAS, 2),
                       "dias": round(float(r.dias)) if r.dias is not None else None})
    # A dónde moverlo: tiendas donde ese mismo producto vende y está en cero (≤ 200 SKU: cabe en parámetros)
    if tipo != "en_cero" and salida:
        donde: dict[str, list[str]] = {}
        for sku, alm in bd.execute(select(t.c.sku, t.c.tienda).where(t.c.estado == "en_cero",
                                                                  t.c.sku.in_({x["sku"] for x in salida}))
                                   .order_by(t.c.piezas.desc())):
            donde.setdefault(sku, []).append(tiendas.get(alm, alm))
        for x in salida:
            x["en_cero_en"] = donde.get(x["sku"], [])
    return salida
