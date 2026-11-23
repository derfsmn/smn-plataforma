"""Evaluación de cada producto del Radar de precios (plan aprobado por Diego, 2026-11-17): qué tan caro estamos, cuánto
ganamos, cuánto vende, hacia dónde va el mercado y qué conviene hacer. Sin IA: son cuentas.

- Índice = nuestro precio / mediana del mercado × 100 (100 = parejos).
- Margen = (precio lista sin IVA − último costo de compra sin IVA) / precio lista sin IVA, contra el mínimo de la Base de
  conocimiento (31 % lista A) o el provisional.
- Venta: importe y piezas de las últimas 26 semanas cargadas de SMNBI (sin mayoreo); clase AA–E del catálogo.
- Tendencia: mediana del mercado en las últimas corridas (hasta 8, con al menos 2): sube, baja o estable (±3 %).
- Acción sugerida:
  · Más caros que el límite: «Bajar a $X» (la mediana) si con eso el margen no baja del mínimo; si no alcanza, bajar
    hasta el precio que deja el mínimo y «Negociar costo» a $Y; si ni eso, solo «Negociar costo».
  · Más de 10 % abajo del mercado con margen bajo el mínimo: «Revisar si se sube» hasta la mediana.
  · Sin precios validados de la competencia: «Sin referencia». Lo demás: «Mantener».
El semáforo y su corte (5 % por omisión o el del producto) no cambian.
"""
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from datos.modelos import CostoArticulo, Producto, VentaSemanal
from modulos.compras import precios
from modulos.compras import realidad_producto as rp
from modulos.compras.modelos_precios import PrecioCorrida, PrecioCorridaProducto
from modulos.compras.radar_productos import margen_minimo

ABAJO_PARA_SUBIR = Decimal("-10")
ESTABLE = Decimal("3")
TENDENCIA_CORRIDAS = 8
CIEN = Decimal("100")


@dataclass
class Evaluacion:
    indice: Decimal | None
    margen: Decimal | None
    margen_minimo: Decimal
    costo: Decimal | None
    venta_importe: Decimal
    venta_piezas: Decimal
    clase: str | None
    tendencia: str | None  # sube / baja / estable / None (pocas corridas)
    tendencia_pct: Decimal | None
    accion: str  # bajar / negociar / bajar_y_negociar / subir / mantener / sin_referencia
    accion_texto: str
    detalle: str
    precio_sugerido: Decimal | None
    costo_meta: Decimal | None


def _peso(v: Decimal) -> str:
    return f"${v:,.2f}"


def _num(v: Decimal) -> str:
    """31.0000 → «31»; 30.50 → «30.5»."""
    return format(Decimal(v).normalize(), "f")


def _redondear(v: Decimal) -> Decimal:
    """Precio de anaquel: a peso cerrado hacia abajo con ,.90 (149.90)."""
    entero = v.to_integral_value(rounding=ROUND_DOWN)
    return entero - Decimal("0.10") if v - entero < Decimal("0.90") else entero + Decimal("0.90")


_VENTAS: dict = {"llave": None, "datos": {}, "hora": 0.0}  # venta de todo el catálogo, 1 hora o hasta otra semana (6 s en producción)


def ventas(bd: Session, skus: list[str]) -> dict[str, tuple[Decimal, Decimal]]:
    """{sku: (importe, piezas netas)} en las 26 semanas que terminan en la última semana cargada."""
    v = rp.ventana(bd)
    if not v or not skus:
        return {}
    from sqlalchemy import func
    q = (select(VentaSemanal.sku, func.sum(VentaSemanal.importe), func.sum(rp.NETAS)).where(*v.filtro())
         .group_by(VentaSemanal.sku))
    if len(skus) < 300:  # pocos: directo
        q = q.where(VentaSemanal.sku.in_(skus))
        return {s: (Decimal(i or 0), Decimal(p or 0)) for s, i, p in bd.execute(q)}
    import time
    llave = (v.desde, v.fin, tuple(sorted(v.mayoreo)))
    if _VENTAS["llave"] != llave or time.monotonic() - _VENTAS["hora"] > 3600:
        _VENTAS.update(llave=llave, datos={s: (Decimal(i or 0), Decimal(p or 0)) for s, i, p in bd.execute(q)},
                       hora=time.monotonic())
    todas = _VENTAS["datos"]
    return {s: todas[s] for s in skus if s in todas}


def costos(bd: Session, skus: list[str]) -> dict[str, Decimal]:
    q = select(CostoArticulo.sku, CostoArticulo.costo_ultimo).where(CostoArticulo.costo_ultimo > 0)
    if len(skus) < 1500:
        q = q.where(CostoArticulo.sku.in_(skus or [""]))
    return {s: Decimal(c) for s, c in bd.execute(q)}


def tendencias(bd: Session, producto_ids: list[int]) -> dict[int, list[Decimal]]:
    """{producto: medianas de la más vieja a la más nueva} de sus últimas corridas con precios."""
    q = (select(PrecioCorridaProducto.producto_id, PrecioCorridaProducto.mediana)
         .join(PrecioCorrida, PrecioCorrida.corrida_id == PrecioCorridaProducto.corrida_id)
         .where(precios.REGULAR, PrecioCorridaProducto.estado == "con_precios", PrecioCorridaProducto.mediana.is_not(None))
         .order_by(PrecioCorridaProducto.corrida_producto_id.desc()))
    if len(producto_ids) < 1500:
        q = q.where(PrecioCorridaProducto.producto_id.in_(producto_ids or [0]))
    salida: dict[int, list[Decimal]] = {}
    for pid, m in bd.execute(q):
        lista = salida.setdefault(pid, [])
        if len(lista) < TENDENCIA_CORRIDAS:
            lista.append(m)
    return {pid: list(reversed(v)) for pid, v in salida.items()}


class Evaluador:
    """Evalúa muchos productos con pocas consultas."""

    def __init__(self, bd: Session, productos: list[Producto]):
        self.bd = bd
        skus = [p.sku for p in productos]
        self.ventas = ventas(bd, skus)
        self.costos = costos(bd, skus)
        self.medianas = tendencias(bd, [p.producto_id for p in productos])
        self.minimos: dict[str | None, Decimal] = {}

    def minimo(self, departamento: str | None) -> Decimal:
        if departamento not in self.minimos:
            self.minimos[departamento] = margen_minimo(self.bd, departamento)[0]
        return self.minimos[departamento]

    def evaluar(self, p: Producto, f: PrecioCorridaProducto | None, limite: Decimal | None = None) -> Evaluacion:
        e = self._evaluar(p, f, limite)
        if e.accion == "sin_referencia" or not f or f.precio_membresia is None or not f.mediana:
            return e
        # Segunda comparación (Diego, 2026-11-17): el precio membresía contra el mismo mercado
        dif = precios.diferencia_pct(f.precio_membresia, f.mediana)
        if dif is not None:
            como = (f"{dif:.0f} % más caro" if dif > 0 else "igual que el mercado" if dif == 0 else f"{abs(dif):.0f} % abajo")
            e.detalle = f"{e.detalle}. Con membresía ({_peso(Decimal(f.precio_membresia))}) quedamos {como}"
        return e

    def _evaluar(self, p: Producto, f: PrecioCorridaProducto | None, limite: Decimal | None = None) -> Evaluacion:
        minimo = self.minimo(p.departamento)
        pct_min = _num(minimo)
        importe, piezas = self.ventas.get(p.sku, (Decimal(0), Decimal(0)))
        costo = self.costos.get(p.sku)
        factor = (Decimal(p.precio_lista_con_impuestos) / Decimal(p.precio_lista)
                  if p.precio_lista and p.precio_lista_con_impuestos and p.precio_lista > 0 else None)
        margen = ((Decimal(p.precio_lista) - costo) / Decimal(p.precio_lista) * CIEN).quantize(Decimal("0.1")) \
            if costo and p.precio_lista and p.precio_lista > 0 else None
        hist = self.medianas.get(p.producto_id, [])
        tendencia = tendencia_pct = None
        if len(hist) >= 2 and hist[0]:
            tendencia_pct = ((hist[-1] - hist[0]) / hist[0] * CIEN).quantize(Decimal("0.1"))
            tendencia = "sube" if tendencia_pct > ESTABLE else "baja" if tendencia_pct < -ESTABLE else "estable"
        base = precios.nuestro(f)[0] if f else None
        mediana = f.mediana if f and f.estado == "con_precios" else None
        comun = dict(margen=margen, margen_minimo=minimo, costo=costo, venta_importe=importe, venta_piezas=piezas,
                     clase=(p.clasificacion or "").strip().upper() or None, tendencia=tendencia, tendencia_pct=tendencia_pct)
        if not mediana or not base:
            return Evaluacion(indice=None, **comun, accion="sin_referencia", accion_texto="Sin referencia",
                              detalle="Nadie más lo vende o no se pudo confirmar que sea el mismo producto",
                              precio_sugerido=None, costo_meta=None)
        indice = (base / mediana * CIEN).quantize(Decimal("0.1"))
        dif = precios.dif_nuestro(f)
        color = precios.color(dif, limite)
        evaluacion = dict(indice=indice, **comun)
        # Precio más bajo que deja el margen mínimo (con impuestos)
        piso = (costo / (1 - minimo / CIEN) * factor).quantize(Decimal("0.01")) if costo and factor else None
        if color == "rojo":
            meta = _redondear(mediana)
            if piso is None:
                return Evaluacion(**evaluacion, accion="bajar", accion_texto=f"Bajar a {_peso(meta)}",
                                  detalle="Sin costo de compra para revisar el margen", precio_sugerido=meta, costo_meta=None)
            costo_meta = (mediana / factor * (1 - minimo / CIEN)).quantize(Decimal("0.01"))
            if piso <= meta:
                margen_meta = ((meta / factor - costo) / (meta / factor) * CIEN).quantize(Decimal("0.1"))
                return Evaluacion(**evaluacion, accion="bajar", accion_texto=f"Bajar a {_peso(meta)}",
                                  detalle=f"Queda en la mediana; el margen baja a {margen_meta} % (mínimo {pct_min} %)",
                                  precio_sugerido=meta, costo_meta=None)
            if piso < base:
                return Evaluacion(**evaluacion, accion="bajar_y_negociar", accion_texto=f"Bajar a {_peso(piso)} y negociar costo",
                                  detalle=f"Más abajo pierde el margen de {pct_min} %. Para quedar en la mediana, "
                                          f"negociar costo a {_peso(costo_meta)} (hoy {_peso(costo)})",
                                  precio_sugerido=piso, costo_meta=costo_meta)
            return Evaluacion(**evaluacion, accion="negociar", accion_texto=f"Negociar costo a {_peso(costo_meta)}",
                              detalle=f"Hoy cuesta {_peso(costo)} y el margen es de {margen} %: no hay espacio para bajar",
                              precio_sugerido=None, costo_meta=costo_meta)
        if dif is not None and dif <= ABAJO_PARA_SUBIR and margen is not None and margen < minimo:
            meta = _redondear(mediana)
            return Evaluacion(**evaluacion, accion="subir", accion_texto="Revisar si se sube",
                              detalle=f"Estamos {abs(dif):.0f} % abajo del mercado con margen de {margen} %; "
                                      f"la mediana es {_peso(meta)}", precio_sugerido=meta, costo_meta=None)
        detalle = ("Un poco más caro, dentro del límite" if color == "amarillo"
                   else "En o abajo de la mediana" + (f" con margen de {margen} %" if margen is not None else ""))
        return Evaluacion(**evaluacion, accion="mantener", accion_texto="Mantener", detalle=detalle,
                          precio_sugerido=None, costo_meta=None)
