"""Reporte a Excel del Radar de precios con la selección de quien lo baja: productos sueltos, marcas y categorías
completas, sin repetir (Diego, 2026-11-17). Hojas a elegir: resumen por marca y categoría, precio por tienda con liga,
qué conviene hacer y margen, historial de las últimas 8 semanas. Sin notas de método (regla de reportes para Compras).
"""
import io
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from modulos.compras import precios
from modulos.compras.excel_precios import NARANJA, SEMAFORO
from modulos.compras.modelos_precios import PrecioCorrida, PrecioCorridaProducto
from modulos.compras.tablero_precios import Renglon

HOJAS = ("resumen", "tiendas", "accion", "historial")
POR_OMISION = ("resumen", "tiendas", "accion")
COLOR_TEXTO = {"rojo": "Más caro", "amarillo": "Un poco más caro", "verde": "Igual o más barato", None: "Sin referencia"}
LIGA = Font(color="0563C1", underline="single")
NEGRITA = Font(bold=True)


def _limpio(v):
    """Texto sin los caracteres de control que Excel no acepta (vienen en algunas descripciones del catálogo)."""
    return ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v


def _agregar(h, fila: list) -> None:
    h.append([_limpio(v) for v in fila])


def _f(v):
    return float(v) if isinstance(v, Decimal) else v


def _pct(v: Decimal | None) -> float | None:
    return None if v is None else float(v) / 100


def _hoja(libro: Workbook, titulo: str, encabezados: list[str], anchos: list[int]):
    h = libro.create_sheet(titulo)
    _agregar(h, encabezados)
    for c in h[1]:
        c.font = Font(bold=True, color="222221")
        c.fill = PatternFill("solid", fgColor=NARANJA)
        c.alignment = Alignment(vertical="center", wrap_text=True)
    h.row_dimensions[1].height = 32
    for i, a in enumerate(anchos, 1):
        h.column_dimensions[get_column_letter(i)].width = a
    h.freeze_panes = "C2"
    return h


def _cerrar(h) -> None:
    if h.max_row > 1:
        h.auto_filter.ref = h.dimensions


def _pintar(celda, color: str | None) -> None:
    if color in SEMAFORO:
        celda.fill = PatternFill("solid", fgColor=SEMAFORO[color])


def _formatos(h, columnas: dict[int, str]) -> None:
    for fila in h.iter_rows(min_row=2):
        for col, fmt in columnas.items():
            fila[col - 1].number_format = fmt


PESOS, PCT = '"$"#,##0.00', "0.0%"


def resumen(libro: Workbook, rs: list[Renglon]) -> None:
    for titulo, llave in (("Resumen por marca", lambda r: r.producto.marca or "Sin marca"),
                          ("Resumen por categoría", lambda r: r.producto.subcategoria or "Sin categoría")):
        grupos: dict[str, list[Renglon]] = defaultdict(list)
        for r in rs:
            grupos[llave(r)].append(r)
        h = _hoja(libro, titulo, [titulo.split(" por ")[1].capitalize(), "Productos", "Con referencia", "Más caros",
                                  "Un poco más caros", "Igual o más baratos", "Sin referencia", "Índice promedio",
                                  "Por bajar o negociar", "Por revisar si se suben", "Venta 26 semanas",
                                  "Más caros con membresía", "Un poco más caros con membresía",
                                  "Igual o más baratos con membresía"],
                  [34, 11, 13, 11, 13, 13, 12, 12, 14, 14, 16, 14, 14, 14])
        h.freeze_panes = "B2"
        for nombre, g in sorted(grupos.items(), key=lambda kv: -sum(r.evaluacion.venta_importe for r in kv[1])):
            con = [r for r in g if r.evaluacion.indice is not None]
            _agregar(h, [nombre, len(g), len(con), sum(r.color == "rojo" for r in g), sum(r.color == "amarillo" for r in g),
                      sum(r.color == "verde" for r in g), len(g) - len(con),
                      (sum(float(r.evaluacion.indice) for r in con) / len(con) / 100) if con else None,
                      sum(r.evaluacion.accion in ("bajar", "negociar", "bajar_y_negociar") for r in g),
                      sum(r.evaluacion.accion == "subir" for r in g), _f(sum(r.evaluacion.venta_importe for r in g)),
                      sum(r.color_membresia == "rojo" for r in g), sum(r.color_membresia == "amarillo" for r in g),
                      sum(r.color_membresia == "verde" for r in g)])
        _formatos(h, {8: PCT, 11: PESOS})
        _cerrar(h)


def tiendas(libro: Workbook, rs: list[Renglon]) -> None:
    claves = precios.tiendas_clave()
    encabezados = ["SKU", "Producto", "Marca", "Categoría", "Clase", "Nuestro precio", "Mediana del mercado", "Diferencia",
                   "Cómo estamos", "Precio membresía", "Diferencia membresía", "Cómo estamos con membresía"]
    anchos = [11, 42, 18, 20, 7, 12, 12, 11, 17, 12, 12, 17]
    t0 = len(encabezados) + 1  # primera columna de las tiendas
    for t in claves:
        encabezados += [t, f"{t} liga"]
        anchos += [11, 9]
    encabezados += ["Otras tiendas (más barata)", "Precio", "Liga", "Tiendas que cuentan"]
    anchos += [24, 11, 9, 10]
    h = _hoja(libro, "Precio por tienda", encabezados, anchos)
    for r in sorted(rs, key=lambda r: -r.evaluacion.venta_importe):
        p = r.producto
        fila = [p.sku, p.descripcion, p.marca, p.subcategoria, r.evaluacion.clase, _f(r.base),
                _f(r.mediana) if r.color else None, _pct(r.dif), COLOR_TEXTO[r.color],
                _f(r.membresia), _pct(r.dif_membresia), COLOR_TEXTO[r.color_membresia]]
        for t in claves:
            precio, liga = r.tiendas.get(t, (None, None))
            fila += [_f(precio), "Ver" if liga else None]
        otra = r.otras[0] if r.otras else (None, None, None)
        fila += [otra[0], _f(otra[1]), "Ver" if otra[2] else None, len(r.tiendas) + len(r.otras)]
        _agregar(h, fila)
        n = h.max_row
        _pintar(h.cell(n, 9), r.color)
        _pintar(h.cell(n, 12), r.color_membresia)
        for i, t in enumerate(claves):
            col = t0 + i * 2
            precio, liga = r.tiendas.get(t, (None, None))
            if liga:
                h.cell(n, col + 1).hyperlink, h.cell(n, col + 1).font = liga, LIGA
            if precio and r.base and r.base > precio * Decimal("1.02"):
                h.cell(n, col).fill = PatternFill("solid", fgColor=SEMAFORO["rojo"])
        if otra[2]:
            c = h.cell(n, t0 + len(claves) * 2 + 2)
            c.hyperlink, c.font = otra[2], LIGA
    fmt = {6: PESOS, 7: PESOS, 8: PCT, 10: PESOS, 11: PCT}
    for i in range(len(claves)):
        fmt[t0 + i * 2] = PESOS
    fmt[t0 + len(claves) * 2 + 1] = PESOS
    _formatos(h, fmt)
    _cerrar(h)


def accion(libro: Workbook, rs: list[Renglon]) -> None:
    h = _hoja(libro, "Qué conviene", ["SKU", "Producto", "Marca", "Clase", "Qué conviene", "Por qué", "Precio sugerido",
                                      "Nuestro precio", "Mediana", "Diferencia", "Margen hoy", "Margen mínimo",
                                      "Último costo", "Costo meta", "Venta 26 semanas", "Piezas 26 semanas", "Mercado",
                                      "Precio membresía", "Diferencia membresía"],
              [11, 40, 18, 7, 22, 52, 12, 12, 12, 11, 10, 10, 11, 11, 14, 11, 12, 12, 12])
    orden = {"bajar": 0, "bajar_y_negociar": 0, "negociar": 1, "subir": 2, "mantener": 3, "sin_referencia": 4}
    for r in sorted(rs, key=lambda r: (orden.get(r.evaluacion.accion, 9), -r.evaluacion.venta_importe)):
        e = r.evaluacion
        tendencia = ("Estable" if e.tendencia == "estable" else
                     f"{'Sube' if e.tendencia == 'sube' else 'Baja'} {e.tendencia_pct:+}%" if e.tendencia else "")
        _agregar(h, [r.producto.sku, r.producto.descripcion, r.producto.marca, e.clase, e.accion_texto, e.detalle,
                  _f(e.precio_sugerido), _f(r.base), _f(r.mediana) if r.color else None, _pct(r.dif), _pct(e.margen),
                  _pct(e.margen_minimo), _f(e.costo), _f(e.costo_meta), _f(e.venta_importe), _f(e.venta_piezas), tendencia,
                  _f(r.membresia), _pct(r.dif_membresia)])
        n = h.max_row
        _pintar(h.cell(n, 5), r.color)
        if e.margen is not None and e.margen < e.margen_minimo:
            h.cell(n, 11).font = Font(color="9C0006")
    _formatos(h, {7: PESOS, 8: PESOS, 9: PESOS, 10: PCT, 11: PCT, 12: PCT, 13: PESOS, 14: PESOS, 15: PESOS, 16: "#,##0", 18: PESOS, 19: PCT})
    _cerrar(h)


def historial(libro: Workbook, bd: Session, rs: list[Renglon], hasta: date) -> None:
    """Mediana del mercado y nuestro precio por semana (lunes), las últimas 8."""
    lunes = hasta - timedelta(days=hasta.weekday())
    semanas = [lunes - timedelta(weeks=i) for i in range(7, -1, -1)]
    ids = [r.producto.producto_id for r in rs]
    datos: dict[int, dict[date, tuple]] = defaultdict(dict)
    for i in range(0, len(ids), 1500):
        q = (select(PrecioCorridaProducto.producto_id, PrecioCorrida.fecha, PrecioCorridaProducto.mediana,
                    PrecioCorridaProducto.precio_lista)
             .join(PrecioCorrida, PrecioCorrida.corrida_id == PrecioCorridaProducto.corrida_id)
             .where(precios.REGULAR, PrecioCorridaProducto.estado == "con_precios",
                    PrecioCorrida.fecha >= semanas[0], PrecioCorrida.fecha <= hasta,
                    PrecioCorridaProducto.producto_id.in_(ids[i:i + 1500]))
             .order_by(PrecioCorridaProducto.corrida_producto_id))
        for pid, fecha, mediana, lista in bd.execute(q):
            datos[pid][fecha - timedelta(days=fecha.weekday())] = (mediana, lista)  # la última de la semana
    encabezados = ["SKU", "Producto", "Marca"] + [f"Mercado {s:%d/%m}" for s in semanas] + ["Nuestro precio hoy", "Cambio del mercado"]
    h = _hoja(libro, "Historial 8 semanas", encabezados, [11, 40, 18] + [12] * 8 + [13, 12])
    for r in rs:
        serie = [datos[r.producto.producto_id].get(s, (None, None))[0] for s in semanas]
        hay = [v for v in serie if v]
        cambio = ((hay[-1] - hay[0]) / hay[0]) if len(hay) >= 2 and hay[0] else None
        _agregar(h, [r.producto.sku, r.producto.descripcion, r.producto.marca] + [_f(v) for v in serie] + [_f(r.base), _f(cambio)])
    _formatos(h, {**{4 + i: PESOS for i in range(9)}, 13: PCT})
    _cerrar(h)


def armar(bd: Session, rs: list[Renglon], hojas: list[str], hasta: date, titulo: str) -> bytes:
    libro = Workbook()
    portada = libro.active
    portada.title = "Portada"
    portada["A1"], portada["A1"].font = "Radar de precios", Font(bold=True, size=18)
    portada["A2"] = titulo
    portada["A3"] = f"Precios al {hasta:%d/%m/%Y}"
    cuenta = [("Productos", len(rs)), ("Más caros que el mercado", sum(r.color == "rojo" for r in rs)),
              ("Un poco más caros", sum(r.color == "amarillo" for r in rs)),
              ("Igual o más baratos", sum(r.color == "verde" for r in rs)),
              ("Sin referencia", sum(r.color is None for r in rs)),
              ("Conviene bajar o negociar costo", sum(r.evaluacion.accion in ("bajar", "negociar", "bajar_y_negociar") for r in rs)),
              ("Se podrían subir", sum(r.evaluacion.accion == "subir" for r in rs))]
    for i, (k, v) in enumerate(cuenta, 5):
        portada.cell(i, 1, k).font = NEGRITA if i == 5 else Font()
        portada.cell(i, 2, _limpio(v))
        _pintar(portada.cell(i, 1), {6: "rojo", 7: "amarillo", 8: "verde"}.get(i))
    portada.column_dimensions["A"].width, portada.column_dimensions["B"].width = 36, 12
    if "resumen" in hojas:
        resumen(libro, rs)
    if "tiendas" in hojas:
        tiendas(libro, rs)
    if "accion" in hojas:
        accion(libro, rs)
    if "historial" in hojas:
        historial(libro, bd, rs, hasta)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()
