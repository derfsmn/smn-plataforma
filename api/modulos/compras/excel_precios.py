"""Radar de precios con Excel (pedido de Diego, 2026-10-26): leer la lista de SKU de una prueba y armar el Excel de salida.

Entrada: un .xlsx o .csv con una columna «SKU» (o, si no tiene encabezado, los SKU en la primera columna). Cada valor
se busca como SKU del catálogo y, si no, como código de barras. Salida: un .xlsx con un renglón por producto y el precio
de cada tienda (pedido de Diego, 2026-10-28), el resumen, cada precio encontrado y los SKU que no estaban en el catálogo.
"""
import csv
import io
import json
import unicodedata
from decimal import Decimal

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from datos.modelos import Producto

MAX_SKUS = 300
ENCABEZADOS = {"sku", "skus", "codigo", "clave", "articulo", "codigo articulo", "codigo de articulo", "codigo barras",
               "codigo de barras"}
NARANJA = "DE951B"
SEMAFORO = {"verde": "C6EFCE", "amarillo": "FFEB9C", "rojo": "FFC7CE"}


class ErrorArchivo(ValueError):
    pass


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto).strip().lower())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).replace("_", " ").split())


def _valor(v) -> str:
    """Un SKU como texto: 1234.0 de Excel vuelve a «1234»."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _renglones(nombre: str, contenido: bytes) -> list[list]:
    if nombre.lower().endswith(".csv"):
        try:
            texto = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = contenido.decode("latin-1")
        separador = ";" if texto.count(";") > texto.count(",") else ","
        return [r for r in csv.reader(io.StringIO(texto), delimiter=separador)]
    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001 - cualquier cosa que no se pueda abrir como Excel
        raise ErrorArchivo("No se pudo abrir el archivo. Súbelo como Excel (.xlsx) o CSV.") from e
    hoja = libro.worksheets[0]
    return [list(r) for r in hoja.iter_rows(values_only=True)]


def leer_skus(nombre: str, contenido: bytes) -> list[str]:
    """Los SKU del archivo, sin repetir y en su orden."""
    renglones = [r for r in _renglones(nombre, contenido) if any(_valor(v) for v in r)]
    if not renglones:
        raise ErrorArchivo("El archivo está vacío.")
    columna, inicio = 0, 0
    for i, r in enumerate(renglones[:10]):  # el encabezado puede no estar en el primer renglón
        idx = next((j for j, v in enumerate(r) if _norm(_valor(v)) in ENCABEZADOS), None)
        if idx is not None:
            columna, inicio = idx, i + 1
            break
    skus = [_valor(r[columna]) for r in renglones[inicio:] if columna < len(r)]
    skus = list(dict.fromkeys(s for s in skus if s))
    if not skus:
        raise ErrorArchivo("No encontré SKU. Pon una columna con el encabezado «SKU».")
    if len(skus) > MAX_SKUS:
        raise ErrorArchivo(f"El archivo trae {len(skus)} SKU; el máximo por prueba es {MAX_SKUS}.")
    return skus


def buscar(bd: Session, skus: list[str]) -> tuple[list[Producto], list[str]]:
    """Productos del catálogo por SKU (también sin ceros a la izquierda, que Excel suele quitar) o código de barras."""
    sin_ceros = {s.lstrip("0") or s: s for s in skus}
    candidatos = list(bd.scalars(select(Producto).where(
        (Producto.sku.in_(skus)) | (Producto.codigo_barras.in_(skus)))))
    por_sku = {p.sku: p for p in candidatos}
    por_barras = {p.codigo_barras: p for p in candidatos if p.codigo_barras}
    faltan = [s for s in skus if s not in por_sku and s not in por_barras]
    if faltan:  # «00123» en el catálogo llega como «123» desde Excel
        for p in bd.scalars(select(Producto).where(Producto.sku.like("0%"))):
            if (p.sku.lstrip("0") or p.sku) in sin_ceros:
                por_sku.setdefault(sin_ceros[p.sku.lstrip("0") or p.sku], p)
    encontrados, no_encontrados, vistos = [], [], set()
    for s in skus:
        p = por_sku.get(s) or por_barras.get(s)
        if not p:
            no_encontrados.append(s)
        elif p.producto_id not in vistos:
            vistos.add(p.producto_id)
            encontrados.append(p)
    return encontrados, no_encontrados


# ---------------------------------------------------------------- salida

def _hoja(libro: Workbook, titulo: str, encabezados: list[str], renglones: list[list], anchos: list[int]):
    h = libro.create_sheet(titulo)
    h.append(encabezados)
    for celda in h[1]:
        celda.font = Font(bold=True, color="222221")
        celda.fill = PatternFill("solid", fgColor=NARANJA)
        celda.alignment = Alignment(vertical="center", wrap_text=True)
    for r in renglones:
        h.append([float(v) if isinstance(v, Decimal) else v for v in r])
    for i, ancho in enumerate(anchos, 1):
        h.column_dimensions[get_column_letter(i)].width = ancho
    h.freeze_panes = "A2"
    if renglones:
        h.auto_filter.ref = h.dimensions
    return h


def _pct(v: Decimal | None) -> float | None:
    return None if v is None else float(v) / 100


ESTADOS = {"con_precios": "Con precios", "sin_precios": "Sin precios", "sin_coincidencia": "Sin coincidencia en Google",
           "fallido": "Falló", "sin_presupuesto": "Sin presupuesto", "pendiente": "Pendiente"}
COINCIDENCIA = {"automatica": "Automática", "ia": "La eligió la IA", "persona": "La eligió una persona"}
# Orden de Diego (2026-10-28); después, las demás tiendas que encontró Google
TIENDAS = ("Walmart", "San Pablo", "Chedraui", "Soriana")
AZUL = Font(color="0563C1", underline="single")
ROJO_SUAVE = PatternFill("solid", fgColor="FCE4E4")  # semáforo rojo discreto: estamos más caros que la tienda
ROJO_TEXTO = Font(color="9C0006")
POR_TIENDA = ("Precio", "Dif. vs lista", "Dif. vs membresía", "URL")


def _dif(nuestro: Decimal | None, tienda: Decimal | None) -> float | None:
    """nuestro / tienda - 1, como en el radar. Positivo = estamos más caros."""
    if nuestro is None or not tienda:
        return None
    return round(float(Decimal(nuestro) / Decimal(tienda) - 1), 4)


def _por_tienda(filas: list, precios_: list) -> tuple[list[str], list[list]]:
    """Un renglón por SKU: nuestros precios, las 4 tiendas clave y luego cada tienda que encontró Google; por tienda,
    precio, diferencia contra nuestro precio lista y membresía, y liga. Va el precio más bajo de los que cuentan (mismo
    producto y presentación, en pesos)."""
    mejor: dict[int, dict[str, tuple]] = {}
    for r in precios_:
        if not r.cuenta:
            continue
        tienda = r.tienda_clave if r.tienda_clave in TIENDAS else r.vendedor
        actual = mejor.setdefault(r.producto_id, {}).get(tienda)
        if actual is None or r.precio < actual[0]:
            mejor[r.producto_id][tienda] = (r.precio, r.liga)
    veces: dict[str, int] = {}
    for tiendas in mejor.values():
        for t in tiendas:
            if t not in TIENDAS:
                veces[t] = veces.get(t, 0) + 1
    otras = sorted(veces, key=lambda t: (-veces[t], t.lower()))  # las que salen en más productos, primero
    encabezados = ["SKU", "Descripción", "Precio lista", "Precio membresía"]
    for t in [*TIENDAS, *otras]:
        encabezados += [f"{x} {t}" for x in POR_TIENDA]
    renglones = []
    for f in filas:
        tiendas = mejor.get(f.producto_id, {})
        r = [f.sku, f.descripcion, f.precio_lista, f.precio_membresia]
        for t in [*TIENDAS, *otras]:
            precio, liga = tiendas.get(t, (None, None))
            r += [precio, _dif(f.precio_lista, precio), _dif(f.precio_membresia, precio), liga]
        renglones.append(r)
    return encabezados, renglones


def _hoja_tiendas(libro: Workbook, filas: list, precios_: list) -> None:
    encabezados, renglones = _por_tienda(filas, precios_)
    tiendas = (len(encabezados) - 4) // len(POR_TIENDA)
    h = _hoja(libro, "Precios por tienda", encabezados, renglones, [14, 44, 13, 13] + [12, 10, 12, 7] * tiendas)
    h.freeze_panes = "C2"  # SKU y descripción siempre a la vista
    for fila in h.iter_rows(min_row=2):
        for i, c in enumerate(fila):
            k = (i - 4) % len(POR_TIENDA)
            if i in (2, 3) or (i >= 4 and k == 0):
                c.number_format = '"$"#,##0.00'
            elif i >= 4 and k in (1, 2):
                c.number_format = "0.0%"
                if c.value is not None and c.value > 0:
                    c.fill, c.font = ROJO_SUAVE, ROJO_TEXTO
            elif i >= 4 and c.value:  # la liga se abre con clic sin mostrar toda la URL
                c.hyperlink, c.value, c.font = c.value, "Ver", AZUL


def armar(corrida: dict, filas: list, precios_: list, publicaciones: dict[int, tuple[str | None, str | None]],
          no_encontrados: list[str]) -> bytes:
    """filas: Fila de rutas_precios; precios_: RenglonTabla; publicaciones: {producto_id: (título, liga) de Google}."""
    libro = Workbook()
    libro.remove(libro.active)
    _hoja_tiendas(libro, filas, precios_)
    resumen = _hoja(libro, "Resumen", [
        "SKU", "Descripción", "Marca", "Estado", "Nota", "Nuestro precio (con impuestos)", "Se comparó", "Vendedores",
        "Mínimo", "Mediana", "Máximo", "Diferencia contra la mediana", "Límite", "Semáforo", "Coincidencia",
        "Publicación de Google", "Liga",
    ], [[
        f.sku, f.descripcion, f.marca, ESTADOS.get(f.estado, f.estado), f.mensaje,
        f.precio_lista if f.base != "tienda" else f.precio_tienda,
        {"lista": "Precio lista", "tienda": "Tienda en línea"}.get(f.base or "", None), f.vendedores,
        f.minimo, f.mediana, f.maximo, _pct(f.dif_lista_mediana_pct), _pct(f.limite_pct),
        (f.color or "").capitalize() or None, COINCIDENCIA.get(f.coincidencia or "", None),
        *publicaciones.get(f.producto_id, (None, None)),
    ] for f in filas], [14, 44, 18, 22, 36, 14, 14, 11, 12, 12, 12, 14, 10, 11, 20, 44, 30])
    for fila in resumen.iter_rows(min_row=2):
        for c in (fila[5], fila[8], fila[9], fila[10]):
            c.number_format = '"$"#,##0.00'
        for c in (fila[11], fila[12]):
            c.number_format = "0.0%"
        if (color := (fila[13].value or "").lower()) in SEMAFORO:
            fila[13].fill = PatternFill("solid", fgColor=SEMAFORO[color])
        if fila[16].value:
            fila[16].hyperlink = fila[16].value
            fila[16].font = Font(color="0563C1", underline="single")

    detalle = _hoja(libro, "Precios", [
        "SKU", "Descripción", "Vendedor", "Publicación", "Precio", "Envío", "Moneda", "Disponibilidad",
        "Diferencia contra nuestro precio", "¿Cuenta?", "Por qué no cuenta", "Liga",
    ], [[
        r.sku, r.descripcion, r.vendedor, r.publicacion, r.precio, r.envio, r.moneda, r.disponibilidad,
        _pct(r.dif_pct), "Sí" if r.cuenta else "No", r.motivo, r.liga,
    ] for r in precios_], [14, 40, 24, 40, 12, 10, 8, 16, 14, 9, 26, 30])
    for fila in detalle.iter_rows(min_row=2):
        for c in (fila[4], fila[5]):
            c.number_format = '"$"#,##0.00'
        fila[8].number_format = "0.0%"
        if fila[11].value:
            fila[11].hyperlink = fila[11].value
            fila[11].font = Font(color="0563C1", underline="single")

    if no_encontrados:
        _hoja(libro, "No encontrados", ["SKU", "Nota"],
              [[s, "No está en el catálogo (ni como SKU ni como código de barras)"] for s in no_encontrados], [18, 60])

    info = _hoja(libro, "Corrida", ["Dato", "Valor"], [[k, v] for k, v in corrida.items()], [28, 60])
    info.auto_filter.ref = None
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def plantilla() -> bytes:
    libro = Workbook()
    h = libro.active
    h.title = "SKU"
    h.append(["SKU"])
    h["A1"].font = Font(bold=True)
    h["A1"].fill = PatternFill("solid", fgColor=NARANJA)
    h.column_dimensions["A"].width = 20
    h["C1"] = "Un SKU por renglón (o código de barras). Máximo " + str(MAX_SKUS) + "."
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def datos_lista(corrida_lista: str | None) -> dict:
    return json.loads(corrida_lista) if corrida_lista else {}


def nombre_archivo(fecha, corrida_id: int, prueba: bool) -> str:
    return f"radar-precios-{'prueba-' if prueba else ''}{fecha}-{corrida_id}.xlsx"
