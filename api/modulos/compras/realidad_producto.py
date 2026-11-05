"""Datos reales de SMNBI para el semáforo de productos (pedido de Diego, 2026-10-26: «que se cruce con la información
del ETL»): venta de los parecidos, margen real de la subcategoría, días de inventario y cumplimiento del proveedor.

Reglas:
- La ventana de venta termina en la última semana cargada (no en hoy): los datos de SMNBI llegan con retraso.
- Venta de tiendas: se quitan los almacenes de mayoreo (tblAlmacenes.Categoria = MAY) si ya se cargaron las tiendas.
- Piezas netas = vendidas menos devueltas. Margen real = (importe sin IVA − costo) / importe, de la venta de SMNBI.
- Los productos se cruzan con la venta por SKU con un JOIN, no con listas: SQL Server acepta a lo más 2,100 parámetros.
"""
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select, true
from sqlalchemy.orm import Session

from datos.modelos import CompraOrden, Inventario, Producto, Proveedor, Tienda, VentaSemanal
from nucleo.calendario import dias_habiles

SEMANAS = 26
SEMANAS_TENDENCIA = 13
SEMANAS_MES = 4.345
MESES_COMPRAS = 12
MAYOREO = "MAY"


@dataclass
class Ventana:
    desde: date
    fin: date  # lunes de la última semana cargada
    mayoreo: set[str]  # almacenes que no cuentan como tienda

    @property
    def hasta(self) -> date:
        return self.fin + timedelta(days=6)

    def filtro(self):
        f = [VentaSemanal.semana >= self.desde, VentaSemanal.semana <= self.fin]
        if self.mayoreo:
            f.append(VentaSemanal.tienda.not_in(self.mayoreo))
        return f

    def texto(self) -> str:
        sin = ", sin mayoreo" if self.mayoreo else ", con mayoreo porque faltan las tiendas"
        return f"venta de SMNBI del {self.desde:%d/%m/%Y} al {self.hasta:%d/%m/%Y}{sin}"


def ventana(bd: Session, semanas: int = SEMANAS) -> Ventana | None:
    fin = bd.scalar(select(func.max(VentaSemanal.semana)))
    if not fin:
        return None
    mayoreo = set(bd.scalars(select(Tienda.almacen).where(Tienda.categoria == MAYOREO)).all())
    return Ventana(desde=fin - timedelta(weeks=semanas - 1), fin=fin, mayoreo=mayoreo)


NETAS = VentaSemanal.piezas - VentaSemanal.piezas_devueltas


@dataclass
class VentaSku:
    piezas: float  # netas en la ventana
    tiendas: int
    semanas: int
    recientes: float  # últimas 13 semanas
    anteriores: float

    @property
    def por_tienda_mes(self) -> float:
        return self.piezas / max(1, self.tiendas) / max(1, self.semanas) * SEMANAS_MES

    @property
    def al_mes(self) -> float:
        return self.piezas / max(1, self.semanas) * SEMANAS_MES


def venta_por_sku(bd: Session, v: Ventana, skus: list[str] | None = None, departamento: str | None = None
                  ) -> dict[str, VentaSku]:
    """Por SKU: de los indicados (pocos) o de todo el departamento."""
    mitad = v.fin - timedelta(weeks=SEMANAS_TENDENCIA)
    q = select(VentaSemanal.sku, func.sum(NETAS), func.count(VentaSemanal.tienda.distinct()),
               func.count(VentaSemanal.semana.distinct()),
               func.sum(case((VentaSemanal.semana > mitad, NETAS), else_=0)),
               func.sum(case((VentaSemanal.semana <= mitad, NETAS), else_=0))).where(*v.filtro())
    if skus is not None:
        if not skus:
            return {}
        q = q.where(VentaSemanal.sku.in_(skus))
    if departamento:
        q = q.join(Producto, Producto.sku == VentaSemanal.sku).where(Producto.departamento == departamento)
    return {sku: VentaSku(float(p), t, s, float(r or 0), float(a or 0))
            for sku, p, t, s, r, a in bd.execute(q.group_by(VentaSemanal.sku)) if p and p > 0}


def tiendas_con_venta(bd: Session, v: Ventana, skus: list[str]) -> tuple[int, int]:
    """(tiendas donde se vendió alguno de los SKU, tiendas con venta en la ventana)."""
    total = bd.scalar(select(func.count(VentaSemanal.tienda.distinct())).where(*v.filtro())) or 0
    con = bd.scalar(select(func.count(VentaSemanal.tienda.distinct())).where(
        *v.filtro(), VentaSemanal.sku.in_(skus or [""]), NETAS > 0)) or 0
    return con, total


def margen_real(bd: Session, v: Ventana, subcategoria: str) -> tuple[Decimal, int] | None:
    """Margen real de la subcategoría en la ventana y cuántos SKU lo forman."""
    importe, costo, n = bd.execute(
        select(func.sum(VentaSemanal.importe), func.sum(VentaSemanal.costo), func.count(VentaSemanal.sku.distinct()))
        .join(Producto, Producto.sku == VentaSemanal.sku)
        .where(*v.filtro(), Producto.subcategoria == subcategoria, VentaSemanal.costo.is_not(None))).one()
    if not importe or importe <= 0 or not costo or costo <= 0:
        return None
    return ((importe - costo) / importe * 100).quantize(Decimal("0.1")), n


def margen_sku(bd: Session, v: Ventana, sku: str) -> Decimal | None:
    """Margen real de un SKU en la ventana."""
    importe, costo = bd.execute(select(func.sum(VentaSemanal.importe), func.sum(VentaSemanal.costo)).where(
        *v.filtro(), VentaSemanal.sku == sku, VentaSemanal.costo.is_not(None))).one()
    if not importe or importe <= 0 or not costo or costo <= 0:
        return None
    return ((importe - costo) / importe * 100).quantize(Decimal("0.1"))


def dias_inventario(bd: Session, v: Ventana, subcategoria: str) -> tuple[float, date, int] | None:
    """Días que alcanza la existencia de la subcategoría (todos los almacenes) al ritmo de venta de las últimas
    13 semanas. (días, fecha del corte, SKU con existencia)."""
    corte = bd.scalar(select(func.max(Inventario.fecha_corte)))
    if not corte:
        return None
    existencia, n = bd.execute(
        select(func.sum(Inventario.existencia), func.count(Inventario.sku.distinct()))
        .join(Producto, Producto.sku == Inventario.sku)
        .where(Inventario.fecha_corte == corte, Producto.subcategoria == subcategoria, Inventario.existencia > 0)).one()
    desde = v.fin - timedelta(weeks=SEMANAS_TENDENCIA - 1)
    vendidas = bd.scalar(select(func.sum(NETAS)).join(Producto, Producto.sku == VentaSemanal.sku).where(
        VentaSemanal.semana >= desde, VentaSemanal.semana <= v.fin, Producto.subcategoria == subcategoria))
    if not existencia or not vendidas or vendidas <= 0:
        return None
    return float(existencia) / (float(vendidas) / (SEMANAS_TENDENCIA * 7)), corte, n


# ---------------------------------------------------------------- proveedor

SOCIEDAD = re.compile(r"\b(s\s*a\s*p\s*i|s\s*a\s*b|s\s*de\s*r\s*l|s\s*a|s\s*c|de\s*c\s*v|de|cv)\b")


def _nombre(texto: str | None) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return " ".join(SOCIEDAD.sub(" ", t).split())


@dataclass
class ProveedorReal:
    codigo: str
    nombre: str | None
    como: str  # cómo se supo que es este proveedor


def proveedor_de(bd: Session, nombres: list[str], marca: str | None, parecidos: list[Producto]) -> ProveedorReal | None:
    """El proveedor en Intelisis: por el nombre que escribió el proveedor, o el que ya nos surte esa marca."""
    buscados = {n for n in (_nombre(x) for x in nombres) if len(n) >= 4}
    if buscados:
        for codigo, nombre in bd.execute(select(Proveedor.proveedor, Proveedor.nombre)):
            if _nombre(nombre) in buscados:
                return ProveedorReal(codigo, nombre, "por su nombre en Intelisis")
    if marca:
        m = _nombre(marca)
        codigos = Counter(p.codigo_proveedor for p in parecidos if p.codigo_proveedor and m and _nombre(p.marca) == m)
        if not codigos:
            codigos = Counter(bd.scalars(select(Producto.codigo_proveedor).where(
                Producto.activo == true(), Producto.codigo_proveedor.is_not(None), Producto.marca == marca)).all())
        if codigos:
            codigo = codigos.most_common(1)[0][0]
            return ProveedorReal(codigo, bd.scalar(select(Proveedor.nombre).where(Proveedor.proveedor == codigo)),
                                 f"es quien ya nos surte la marca {marca}")
    return None


@dataclass
class Cumplimiento:
    ordenes: int
    surtido_pct: float  # piezas recibidas / pedidas
    perdidas_pct: float
    rechazadas_pct: float
    dias_reales: float | None  # promedio de días hábiles de la orden a la primera entrada
    dias_prometidos: int | None
    desde: date


def cumplimiento(bd: Session, codigo: str) -> Cumplimiento | None:
    ultima = bd.scalar(select(func.max(CompraOrden.fecha_orden)))
    if not ultima:
        return None
    desde = ultima - timedelta(days=365 * MESES_COMPRAS // 12)
    ordenes = bd.scalars(select(CompraOrden).where(CompraOrden.proveedor == codigo, CompraOrden.fecha_orden >= desde,
                                                   CompraOrden.piezas_pedidas > 0)).all()
    if not ordenes:
        return None
    pedidas = float(sum(o.piezas_pedidas for o in ordenes))
    dias = [dias_habiles(o.fecha_orden, o.primera_entrada) for o in ordenes if o.primera_entrada]  # lo prometido es en hábiles
    return Cumplimiento(
        ordenes=len(ordenes), surtido_pct=min(100.0, float(sum(o.piezas_recibidas for o in ordenes)) / pedidas * 100),
        perdidas_pct=float(sum(o.piezas_perdidas for o in ordenes)) / pedidas * 100,
        rechazadas_pct=float(sum(o.piezas_rechazadas for o in ordenes)) / pedidas * 100,
        dias_reales=sum(dias) / len(dias) if dias else None,
        dias_prometidos=bd.scalar(select(Proveedor.dias_entrega).where(Proveedor.proveedor == codigo)), desde=desde)
