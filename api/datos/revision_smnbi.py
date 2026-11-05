"""¿Hay cambios en SMNBI? (pedido de Diego, 2026-11-03: «necesitamos revisar la base de datos para actualizar si es necesario»).

Una sola consulta para SSMS saca una «huella» de cada tabla que usa la plataforma (cuántas filas, fechas más recientes y,
en la venta, piezas e importe de cada mes con las mismas reglas del ETL). La plataforma calcula lo mismo con lo que tiene
cargado y dice qué hay que volver a cargar. SOLO LEE: no toca SMNBI ni lo que está cargado.
"""

import csv
import io
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from datos import etl
from datos.modelos import CompraOrden, CostoArticulo, Inventario, Producto, ProductoFuente, Proveedor, Tienda, VentaSemanal

COLUMNAS = ("fuente", "clave", "empresa", "filas", "piezas", "importe", "fecha")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre")


class ErrorRevision(ValueError):
    pass


def consulta() -> str:
    """El archivo para SSMS. Las fechas salen como AAAA-MM-DD (CONVERT 23) para no depender del idioma del servidor."""
    signo = f"CASE WHEN v.TipoMov IN ({etl._lista(etl.DEVOLUCIONES)}) THEN -1 ELSE 1 END"
    importe = f"{signo} * ({etl._dev('d.Cantidad * d.Precio')} - {etl._dev(etl.DESCUENTO)})"
    piezas = f"{signo} * {etl._dev('d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1)')}"
    return f"""-- ¿Hay cambios en SMNBI? Revisión para Centro de datos -> ETL -> «Revisar si hay cambios».
-- SOLO LEE. Corre todo, guarda el resultado como CSV (clic derecho en la tabla > «Guardar resultados como...») y
-- súbelo en la plataforma. Tarda lo que tarda sumar la venta de todos los meses.
-- Archivo generado por api/datos/revision_smnbi.py: si cambian las reglas del ETL, se vuelve a descargar.

USE SMNBI;
SET NOCOUNT ON;

SELECT 'articulos' AS fuente, 'total' AS clave, '' AS empresa, COUNT(*) AS filas, NULL AS piezas, NULL AS importe,
       NULL AS fecha
FROM dbo.tblArticulos
UNION ALL
SELECT 'articulos', 'alta', '', COUNT(*), NULL, NULL, NULL FROM dbo.tblArticulos WHERE Estatus = 'ALTA'
UNION ALL
SELECT 'tiendas', 'total', '', COUNT(*), NULL, NULL, NULL FROM dbo.tblAlmacenes
UNION ALL
SELECT 'proveedores', 'total', '', COUNT(*), NULL, NULL, NULL FROM dbo.tblProveedores
UNION ALL
SELECT 'compras', 'ordenes', '', COUNT(*), NULL, NULL, CONVERT(char(10), MAX(FechaMov), 23)
FROM dbo.tblCompra WHERE TipoMov = 'Orden Compra' AND Estatus IN ('CONCLUIDO', 'PENDIENTE')
UNION ALL
SELECT 'compras', 'pendientes', '', COUNT(*), NULL, NULL, NULL
FROM dbo.tblCompra WHERE TipoMov = 'Orden Compra' AND Estatus = 'PENDIENTE'
UNION ALL
SELECT 'compras', 'entradas', '', COUNT(*), NULL, NULL, CONVERT(char(10), MAX(FechaMov), 23)
FROM dbo.tblCompra WHERE TipoMov = 'Entrada Compra' AND Origen = 'Orden Compra' AND Estatus = 'CONCLUIDO'
UNION ALL
SELECT 'costos', 'total', '', COUNT(DISTINCT d.Articulo), NULL, NULL, CONVERT(char(10), MAX(c.FechaMov), 23)
FROM dbo.tblCompra c JOIN dbo.tblCompraD d ON d.ID = c.ID
WHERE c.TipoMov = 'Entrada Compra' AND c.Estatus = 'CONCLUIDO' AND d.Cantidad > 0 AND d.Costo > 0
UNION ALL
SELECT 'inventario', 'corte', '', COUNT(*), NULL, NULL, CONVERT(char(10), MAX(FechaCorte), 23)
FROM dbo.tblInventario WHERE FechaCorte = (SELECT MAX(FechaCorte) FROM dbo.tblInventario)
UNION ALL
-- Venta de cada mes por empresa, con las mismas reglas que la carga (devoluciones restan, descuentos en %)
SELECT 'venta', CONVERT(char(10), DATEFROMPARTS(YEAR(v.FechaMov), MONTH(v.FechaMov), 1), 23), v.Empresa, COUNT(*),
       SUM({piezas}), SUM({importe}), CONVERT(char(10), MAX(v.FechaMov), 23)
FROM dbo.tblVenta v
JOIN dbo.tblVentaD d ON d.ID = v.ID
JOIN dbo.tblArticulos a ON a.Articulo = d.Articulo
WHERE {etl._filtro_sin_fecha()} AND v.Estatus = 'CONCLUIDO'
GROUP BY DATEFROMPARTS(YEAR(v.FechaMov), MONTH(v.FechaMov), 1), v.Empresa
ORDER BY 1, 2, 3;
"""


# ---------------------------------------------------------------- lectura del resultado

@dataclass
class Huella:
    fuente: str
    clave: str
    empresa: str
    filas: int | None
    piezas: Decimal | None
    importe: Decimal | None
    fecha: date | None


def _vacio(v: str | None) -> bool:
    return v is None or v.strip() == "" or v.strip().upper() == "NULL"


def _num(v: str | None) -> Decimal | None:
    if _vacio(v):
        return None
    try:
        t = v.strip()
        if "," in t and "." not in t:
            t = t.replace(",", ".")  # coma decimal (archivo con punto y coma o tabulador)
        return Decimal(t)
    except InvalidOperation:
        raise ErrorRevision(f"«{v}» no es un número.") from None


def _fecha(v: str | None) -> date | None:
    if _vacio(v):
        return None
    try:
        return date.fromisoformat(v.strip()[:10])
    except ValueError:
        raise ErrorRevision(f"«{v}» no es una fecha AAAA-MM-DD. Usa la consulta que descargaste de la plataforma.") from None


def leer(contenido: bytes) -> list[Huella]:
    if contenido[:2] in (b"\xff\xfe", b"\xfe\xff"):  # SSMS puede guardar en «Unicode» (UTF-16)
        texto = contenido.decode("utf-16")
    else:
        try:
            texto = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = contenido.decode("latin-1")
    separador = max((",", ";", "\t"), key=texto[:4096].count)
    salida = []
    for fila in csv.reader(io.StringIO(texto), delimiter=separador):
        if not fila or not any(c.strip() for c in fila):
            continue
        if fila[0].strip().lower() == "fuente":
            continue  # encabezados
        if len(fila) != len(COLUMNAS):
            raise ErrorRevision(f"Cada renglón debe traer {len(COLUMNAS)} columnas ({', '.join(COLUMNAS)}); uno trae "
                                f"{len(fila)}. Sube el resultado de la consulta «Revisar si hay cambios».")
        f, clave, empresa, filas, piezas, importe, fecha = (c.strip() for c in fila)
        n = _num(filas)
        salida.append(Huella(f.lower(), clave, "" if _vacio(empresa) else empresa, int(n) if n is not None else None,
                             _num(piezas), _num(importe), _fecha(fecha)))
    if not salida:
        raise ErrorRevision("El archivo no trae renglones.")
    if not any(h.fuente == "articulos" for h in salida):
        raise ErrorRevision("No parece el resultado de «Revisar si hay cambios»: falta el renglón de artículos.")
    return salida


# ---------------------------------------------------------------- comparación

@dataclass
class Renglon:
    fuente: str  # articulos, tiendas, ... venta
    que: str  # en palabras
    smnbi: str
    plataforma: str
    estado: str  # igual / cambio / nuevo / sobra
    accion: str | None


def _n(x: int | Decimal | None, d: int = 0) -> str:
    if x is None:
        return "—"
    return f"{x:,.{d}f}"


def _f(x: date | None) -> str:
    return x.strftime("%d/%m/%Y") if x else "—"


def _renglones(n: int | None) -> str:
    return f"{_n(n)} {'renglón' if n == 1 else 'renglones'}"


def _mes(x: date) -> str:
    return f"{MESES[x.month - 1].capitalize()} {x.year}"


def comparar(bd: Session, huellas: list[Huella]) -> list[Renglon]:
    h = {(x.fuente, x.clave, x.empresa): x for x in huellas}
    salida: list[Renglon] = []

    def conteo(fuente: str, clave: str, que: str, aqui: int, accion: str) -> None:
        x = h.get((fuente, clave, ""))
        if not x:
            return
        igual = x.filas == aqui
        salida.append(Renglon(fuente, que, _n(x.filas), _n(aqui), "igual" if igual else "cambio",
                              None if igual else accion))

    articulos = bd.scalar(select(func.count()).select_from(ProductoFuente).where(
        ProductoFuente.fuente == "ETL", ProductoFuente.presente == true())) or 0
    alta = bd.scalar(select(func.count()).select_from(Producto).join(
        ProductoFuente, (ProductoFuente.producto_id == Producto.producto_id) & (ProductoFuente.fuente == "ETL")
        & (ProductoFuente.presente == true())).where(Producto.estatus_erp == "ALTA")) or 0
    conteo("articulos", "total", "Artículos", articulos, "Volver a cargar Artículos")
    conteo("articulos", "alta", "Artículos en ALTA", alta, "Volver a cargar Artículos (cambió el estatus de algunos)")
    conteo("tiendas", "total", "Tiendas y almacenes", bd.scalar(select(func.count()).select_from(Tienda)) or 0,
           "Volver a cargar Tiendas y almacenes")
    conteo("proveedores", "total", "Proveedores", bd.scalar(select(func.count()).select_from(Proveedor)) or 0,
           "Volver a cargar Proveedores")

    ordenes, ultima_orden, ultima_entrada = bd.execute(select(
        func.count(), func.max(CompraOrden.fecha_orden), func.max(CompraOrden.ultima_entrada))).one()
    pendientes = bd.scalar(select(func.count()).select_from(CompraOrden).where(CompraOrden.estatus == "PENDIENTE")) or 0
    if x := h.get(("compras", "ordenes", "")):
        igual = x.filas == ordenes and x.fecha == ultima_orden
        salida.append(Renglon("compras", "Órdenes de compra (la más reciente)", f"{_n(x.filas)} ({_f(x.fecha)})",
                              f"{_n(ordenes)} ({_f(ultima_orden)})", "igual" if igual else "cambio",
                              None if igual else "Volver a cargar Compras por orden"))
    conteo("compras", "pendientes", "Órdenes todavía pendientes", pendientes,
           "Volver a cargar Compras por orden")
    if x := h.get(("compras", "entradas", "")):
        igual = not x.fecha or (ultima_entrada is not None and x.fecha <= ultima_entrada)
        salida.append(Renglon("compras", "Última entrada de mercancía", _f(x.fecha), _f(ultima_entrada),
                              "igual" if igual else "cambio", None if igual else "Volver a cargar Compras por orden"))

    costos, ultimo_costo = bd.execute(select(func.count(), func.max(CostoArticulo.fecha_ultima))).one()
    if x := h.get(("costos", "total", "")):
        igual = x.filas == costos and x.fecha == ultimo_costo
        salida.append(Renglon("costos", "Artículos con costo (última compra)", f"{_n(x.filas)} ({_f(x.fecha)})",
                              f"{_n(costos)} ({_f(ultimo_costo)})", "igual" if igual else "cambio",
                              None if igual else "Volver a cargar Costo de compra por artículo"))

    corte = bd.scalar(select(func.max(Inventario.fecha_corte)))
    en_corte = bd.scalar(select(func.count()).select_from(Inventario).where(Inventario.fecha_corte == corte)) if corte else 0
    if x := h.get(("inventario", "corte", "")):
        if x.fecha and (not corte or x.fecha > corte):
            salida.append(Renglon("inventario", "Corte de inventario", f"{_f(x.fecha)} ({_renglones(x.filas)})",
                                  f"{_f(corte)} ({_renglones(en_corte)})" if corte else "Sin cargar", "nuevo",
                                  "Cargar Inventario: hay un corte más nuevo (el anterior se conserva)"))
        else:
            igual = x.fecha == corte and x.filas == en_corte
            salida.append(Renglon("inventario", "Corte de inventario", f"{_f(x.fecha)} ({_renglones(x.filas)})",
                                  f"{_f(corte)} ({_renglones(en_corte)})", "igual" if igual else "cambio",
                                  None if igual else "Volver a cargar Inventario de ese corte"))

    # Venta: cada mes y empresa contra lo cargado, con la misma tolerancia del cuadre del ETL
    venta = {}
    for x in huellas:
        if x.fuente == "venta":
            venta.setdefault(_fecha(x.clave), {})[x.empresa] = x
    cargado = {m: etl._totales_cargados(bd, m) for m in
               set(bd.scalars(select(VentaSemanal.mes).distinct())) | set(venta)}
    for mes in sorted(cargado):
        origen, aqui = venta.get(mes, {}), cargado[mes]
        if not origen and not aqui:
            continue
        if not aqui:
            dias = max((x.fecha for x in origen.values() if x.fecha), default=None)
            salida.append(Renglon("venta", f"Venta de {_mes(mes)}",
                                  f"${_n(sum(x.importe or 0 for x in origen.values()))}" + (f" (hasta {_f(dias)})" if dias else ""),
                                  "Sin cargar", "nuevo", f"Cargar la venta de {_mes(mes)}"))
            continue
        if not origen:
            salida.append(Renglon("venta", f"Venta de {_mes(mes)}", "Sin venta", f"${_n(sum(i for i, _ in aqui.values()))}",
                                  "sobra", "Preguntar a Sistemas: en SMNBI ya no aparece la venta de ese mes"))
            continue
        empresas = sorted(set(origen) | set(aqui))
        difieren = [e for e in empresas if not (
            etl._cuadra(origen[e].importe or Decimal(0) if e in origen else Decimal(0), aqui.get(e, (Decimal(0), Decimal(0)))[0])
            and etl._cuadra(origen[e].piezas or Decimal(0) if e in origen else Decimal(0), aqui.get(e, (Decimal(0), Decimal(0)))[1]))]
        imp_o = sum((origen[e].importe or Decimal(0) for e in origen), Decimal(0))
        imp_c = sum((aqui[e][0] for e in aqui), Decimal(0))
        salida.append(Renglon("venta", f"Venta de {_mes(mes)}", f"${_n(imp_o)}", f"${_n(imp_c)}",
                              "cambio" if difieren else "igual",
                              f"Volver a cargar la venta de {_mes(mes)} (cambió en {', '.join(difieren)})" if difieren else None))
    return salida


def resumen(renglones: list[Renglon]) -> str:
    pendientes = [r for r in renglones if r.estado != "igual"]
    if not pendientes:
        return "Todo está igual que en SMNBI: no hay nada que volver a cargar."
    n = len(pendientes)
    return f"{n} {'cosa cambió' if n == 1 else 'cosas cambiaron'} en SMNBI desde la última carga."


def a_dict(renglones: list[Renglon]) -> list[dict]:
    return [asdict(r) for r in renglones]
