"""DIOT: lectura de los documentos que entrega Fiscal y reconocimiento de su tipo por sus columnas, no por su nombre.

Los reportes del portal de SM (smnportal.com) se descargan como «.xls» pero son una tabla HTML; el explorador de
Intelisis y los catálogos llegan en Excel. Cada documento se reconoce por las columnas que trae.
"""
import csv
import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

import openpyxl

ERRORES_EXCEL = ("#N/A", "#N/D", "#DIV/0!", "#REF!", "#VALUE!", "#VALOR!", "#NAME?", "#¿NOMBRE?", "#NUM!", "#NULL!")


class ErrorLectura(Exception):
    pass


@dataclass(frozen=True)
class TipoDocumento:
    codigo: str
    nombre: str
    columnas: tuple[str, ...]  # las que debe traer; con ellas se reconoce
    obligatorio: bool
    para_que: str
    comprobar: bool = False  # no entra al cálculo: solo sirve para una comprobación (el banco)
    varios: bool = False  # se puede subir más de uno (un estado de cuenta por cuenta de banco)


TIPOS: dict[str, TipoDocumento] = {t.codigo: t for t in (
    TipoDocumento("tesoreria", "Reporte impuestos tesorería",
                  ("ID", "Mov", "MovID", "Concepto", "Referencia", "BeneficiarioNombre", "Contacto", "TipoCambio",
                   "RFCReceptor", "Impuesto1", "Importe1", "SubTotal"),
                  True, "Pagos del mes con su tasa de IVA (gastos pagados por bancos)."),
    TipoDocumento("aplicaciones", "Rep apps cuentas por pagar",
                  ("Movimiento", "Origen", "Impuesto1", "Importe1", "Importe2", "SubTotal", "Mov", "MovID", "RFC",
                   "nombre"),
                  True, "Aplicaciones de anticipos a facturas de proveedor."),
    TipoDocumento("auxiliar_iva", "Reporte auxiliar IVA acreditable",
                  ("Movimiento", "Debe", "Haber", "Origen", "OrigenID", "OrigenTipoCambio"),
                  True, "Pólizas de IVA acreditable: dicen qué comprobantes cuentan y su tipo de cambio; cuadre final."),
    TipoDocumento("comprobantes", "Explorador de gastos (DIOT) de Intelisis",
                  ("Movimiento", "Acreedor", "Concepto", "Cantidad", "Precio", "TipoCambio", "% IVA", "Poliza",
                   "PolizaID", "Estatus"),
                  True, "Gastos comprobados y caja chica, renglón por renglón, con el proveedor real."),
    TipoDocumento("proveedores", "Catálogo de proveedores",
                  ("Clave", "Nombre", "RFC"),
                  True, "RFC de cada clave de proveedor o acreedor."),
    # Sin «Cuenta»: el auxiliar de Intelisis («Auxiliares - Contabilidad») trae la cuenta en un renglón aparte y la
    # hoja del papel de trabajo en su columna; se confirma que sea la 2500-002-007 en `_es_iva_retenido`.
    TipoDocumento("iva_retenido", "Auxiliar IVA retenido (2500-002-007)",
                  ("Movimiento", "Debe", "Haber"),
                  False, "IVA retenido a terceros en el mes."),
    TipoDocumento("tipos_operacion", "Tipos de operación por RFC",
                  ("RFC", "TIPO DE OPERACIÓN"),
                  False, "Proveedores que no son enajenación de bienes (servicios profesionales, arrendamiento, otros)."),
    TipoDocumento("estado_cuenta", "Estado de cuenta bancario",
                  ("Tipo de Movimiento", "Importe", "Folio Aceptación"),
                  False, "Movimientos del banco (BBVA, un archivo por cuenta). Sirven para confirmar que cada pago de "
                         "tesorería salió del banco; no cambian el cálculo.", comprobar=True, varios=True),
    TipoDocumento("cfdi_sat", "Facturas del SAT (Visor de CFDI)",
                  ("UUID", "TipoDeComprobante", "EmisorRFC", "EstadoComprobante", "TotalTrasladosImpuestoIVA16"),
                  False, "Facturas, notas de crédito y complementos de pago recibidos, como los tiene el SAT (un "
                         "archivo por tipo). Sirven para confirmar el IVA de cada proveedor; no cambian el cálculo.",
                  comprobar=True, varios=True),
)}
CUENTA_IVA_RETENIDO = "2500-002-007"


@dataclass
class Tabla:
    tipo: str | None
    columnas: list[str]
    filas: list[dict]
    hoja: str | None = None
    avisos: list[str] = field(default_factory=list)


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _clave(s) -> str:
    return _norm(s).upper()


# ---------------------------------------------------------------- HTML del portal

class _Html(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tablas: list[list[list[str]]] = []
        self._fila: list[str] | None = None
        self._celda: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tablas.append([])
        elif tag == "tr" and self.tablas:
            self._fila = []
        elif tag in ("td", "th") and self._fila is not None:
            self._celda = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._celda is not None and self._fila is not None:
            self._fila.append(_norm("".join(self._celda)))
            self._celda = None
        elif tag == "tr" and self._fila is not None and self.tablas:
            self.tablas[-1].append(self._fila)
            self._fila = None

    def handle_data(self, data):
        if self._celda is not None:
            self._celda.append(data)


def _texto(contenido: bytes) -> str:
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return contenido.decode(cod)
        except UnicodeDecodeError:
            continue
    return contenido.decode("latin-1", errors="replace")


def _de_html(contenido: bytes) -> list[list]:
    p = _Html()
    p.feed(_texto(contenido))
    tablas = [t for t in p.tablas if t]
    if not tablas:
        raise ErrorLectura("El archivo no trae ninguna tabla.")
    return max(tablas, key=len)


def _de_excel(contenido: bytes) -> list[tuple[str, list[list]]]:
    try:
        wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001 - el archivo viene del usuario
        raise ErrorLectura(f"No se pudo abrir el Excel ({e.__class__.__name__}).") from None
    hojas = []
    for ws in wb.worksheets:
        filas = [list(r) for r in ws.iter_rows(values_only=True)]
        hojas.append((ws.title, filas))
    wb.close()
    return hojas


def _de_csv(contenido: bytes) -> list[list]:
    texto = _texto(contenido)
    muestra = texto[:4000]
    sep = max((",", ";", "\t", "|"), key=muestra.count)
    return [r for r in csv.reader(io.StringIO(texto), delimiter=sep)]


def _encabezado(filas: list[list]) -> tuple[int, str | None]:
    """El renglón de encabezados (entre los primeros 15) y el tipo que reconoce."""
    mejor = (0, None, 0)
    for i, f in enumerate(filas[:15]):
        nombres = {_clave(x) for x in f if x not in (None, "")}
        for t in TIPOS.values():
            tiene = sum(1 for c in t.columnas if _clave(c) in nombres)
            if tiene == len(t.columnas) and tiene > mejor[2]:
                mejor = (i, t.codigo, tiene)
    if mejor[1]:
        return mejor[0], mejor[1]
    # sin tipo: el primer renglón con más textos
    i = max(range(min(15, len(filas))), key=lambda k: sum(1 for x in filas[k] if isinstance(x, str) and x.strip()),
            default=0)
    return i, None


def _es_iva_retenido(filas: list[list], i: int) -> bool:
    """Que el auxiliar sea de la cuenta de IVA retenido: la cuenta viene en el título, en un renglón o en su columna."""
    for f in filas[: i + 3]:
        for x in f:
            if isinstance(x, str) and (CUENTA_IVA_RETENIDO in x or "IVA RETENIDO" in _clave(x)):
                return True
    return False


def _sin_repetir(columnas: list[str]) -> list[str]:
    """Si un encabezado se repite, vale el primero y los demás se renombran («Movimiento (2)»). El explorador de
    Intelisis trae dos «Movimiento»: el primero con folio («Caja Chica LAB53») y el segundo sin él («Caja Chica»)."""
    vistos: dict[str, int] = {}
    salida = []
    for c in columnas:
        k = _clave(c)
        if c and k in vistos:
            vistos[k] += 1
            c = f"{c} ({vistos[k]})"
        elif c:
            vistos[k] = 1
        salida.append(c)
    return salida


def _tabla(filas: list[list], hoja: str | None) -> Tabla:
    i, tipo = _encabezado(filas)
    if tipo == "iva_retenido" and not _es_iva_retenido(filas, i):
        tipo = None
    columnas = _sin_repetir([_norm(x) for x in (filas[i] if filas else [])])
    # Con tipo reconocido, un renglón cuenta solo si trae algo en las columnas del tipo: las hojas de trabajo arrastran
    # fórmulas hacia abajo (#N/A, ceros) en renglones que no tienen datos.
    clave = {_clave(c) for c in TIPOS[tipo].columnas} if tipo else None
    datos = []
    for f in filas[i + 1:]:
        if not any(x not in (None, "") and (clave is None or _clave(columnas[k] if k < len(columnas) else "") in clave)
                   for k, x in enumerate(f) if not (isinstance(x, str) and not x.strip())):
            continue
        datos.append({c: (f[k] if k < len(f) else None) for k, c in enumerate(columnas) if c})
    return Tabla(tipo=tipo, columnas=[c for c in columnas if c], filas=datos, hoja=hoja)


def leer(nombre: str, contenido: bytes, tipo: str | None = None) -> Tabla:
    """Lee un documento y reconoce su tipo. Si no lo reconoce, la tabla sale con tipo None.

    En un Excel de varias hojas se toma la hoja del `tipo` pedido si es una sola; si varias hojas parecen de ese tipo
    (el papel de trabajo completo trae copias e históricos), no se adivina: se pide subir solo la hoja correcta. Sin
    tipo pedido, la hoja reconocida con más renglones.
    """
    inicio = contenido[:600].lstrip().lower()
    n = nombre.lower()
    if inicio.startswith(b"pk"):
        hojas = _de_excel(contenido)
        tablas = [_tabla(f, h) for h, f in hojas if f]
        reconocidas = [t for t in tablas if t.tipo]
        if not tablas:
            raise ErrorLectura("El Excel no trae datos.")
        del_tipo = [t for t in reconocidas if t.tipo == tipo and t.filas]
        if len(del_tipo) > 1 and tipo in HOJAS_PAPEL:  # papel de trabajo de Fiscal: su hoja tiene nombre conocido
            del_tipo = [t for t in del_tipo if (t.hoja or "").strip().upper() == HOJAS_PAPEL[tipo][0].upper()] or del_tipo
        if len(del_tipo) > 1:
            hojas_tipo = ", ".join(f"«{t.hoja}»" for t in del_tipo)
            raise ErrorLectura(f"Este Excel tiene {len(del_tipo)} hojas que parecen «{TIPOS[tipo].nombre}» ({hojas_tipo}). "
                               "Sube un archivo solo con la hoja correcta, como sale de Intelisis.")
        return max(del_tipo or reconocidas or tablas, key=lambda t: len(t.filas))
    if b"<table" in contenido[:20000].lower() or inicio.startswith((b"<", b"\xef\xbb\xbf<")):
        return _tabla(_de_html(contenido), None)
    if n.endswith((".csv", ".txt")):
        return _tabla(_de_csv(contenido), None)
    if contenido[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ErrorLectura("Es un Excel 97-2003 (.xls binario). Ábrelo y guárdalo como .xlsx.")
    raise ErrorLectura("No se reconoce el formato. Sube el reporte como lo descargas (Excel, CSV o el .xls del portal).")


# ---------------------------------------------------------------- archivos como los entrega Fiscal

# Hojas del papel de trabajo de la DIOT de Fiscal («MMAA DIOT <EMPRESA>.xlsx») que son reportes pegados tal como salen
# de Intelisis, sin columnas calculadas: (hoja, columnas crudas desde la A, renglón del encabezado). Las demás hojas
# (IVAC, AMARRE, DIOT AL PESO…) ya traen cálculos o el resultado y nunca se leen.
HOJAS_PAPEL = {
    "comprobantes": ("ComprobantesExp", 25, 1),  # Movimiento … Estatus
    "proveedores": ("Proveedores", 5, 1),  # Clave, Nombre, Tipo, RFC, Categoria
    "iva_retenido": ("IVARetenido", 13, 1),  # Cuenta … Saldo
    "tipos_operacion": ("RETENCIONES", 4, 2),  # RFC, nombre, descripción, tipo (encabezado partido en 2 renglones)
}
ENCABEZADO_TIPOS = ["RFC", "Nombre", "Descripcion", "TIPO DE OPERACIÓN"]
MAX_ZIP_ARCHIVOS, MAX_ZIP_MB = 40, 300


@dataclass
class Archivo:
    """Lo que salió de un archivo subido: un documento para el proceso, el TXT presentado, o algo que no se usa."""
    nombre: str
    clase: str  # documento / referencia / no_se_usa / error
    contenido: bytes = b""
    tipo: str | None = None
    mensaje: str = ""


def _hojas(contenido: bytes) -> list[str]:
    try:
        wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True)
    except Exception:  # noqa: BLE001
        return []
    nombres = list(wb.sheetnames)
    wb.close()
    return nombres


def _xlsx(filas: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for f in filas:
        ws.append(f)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _del_papel(nombre: str, contenido: bytes, hojas: list[str]) -> list[Archivo]:
    """Saca del papel de trabajo las hojas crudas, cada una como un documento aparte."""
    por_nombre = {h.strip().upper(): h for h in hojas}
    wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    salida = []
    try:
        for tipo, (hoja, ncols, encabezado) in HOJAS_PAPEL.items():
            h = por_nombre.get(hoja.upper())
            if not h:
                continue
            filas = [list(r[:ncols]) for r in wb[h].iter_rows(min_row=encabezado, values_only=True)]
            if tipo == "tipos_operacion":
                filas = [ENCABEZADO_TIPOS] + [f for f in filas[1:] if texto(f[0] if f else None)]
            datos = [f for f in filas[1:] if any(x not in (None, "") and not (isinstance(x, str) and not x.strip())
                                                  for x in f)]
            if tipo == "iva_retenido":  # el renglón de la cuenta y los vacíos no son movimientos
                datos = [f for f in datos if len(f) > 2 and texto(f[2])]
            salida.append(Archivo(f"{os.path.splitext(nombre)[0]} · hoja {h}.xlsx", "documento",
                                  _xlsx([filas[0]] + datos), tipo, f"hoja «{h}» del papel de trabajo"))
    finally:
        wb.close()
    return salida


def separar(nombre: str, contenido: bytes, dentro_de_zip: bool = False) -> list[Archivo]:
    """Recibe un archivo como lo entrega Fiscal (reporte, papel de trabajo completo, TXT presentado o un .zip con todo)
    y regresa los documentos que sirven al proceso. No lanza error: cada archivo dice qué pasó con él."""
    base = os.path.basename(nombre.replace("\\", "/"))
    n = base.lower()
    if contenido[:4] == b"PK\x03\x04" and n.endswith(".zip"):
        if dentro_de_zip:
            return [Archivo(base, "no_se_usa", mensaje="Un .zip dentro de otro no se abre.")]
        try:
            z = zipfile.ZipFile(io.BytesIO(contenido))
        except zipfile.BadZipFile:
            return [Archivo(base, "error", mensaje="El .zip está dañado.")]
        miembros = [i for i in z.infolist() if not i.is_dir() and "__MACOSX" not in i.filename
                    and not os.path.basename(i.filename).startswith(("~$", "."))]
        if len(miembros) > MAX_ZIP_ARCHIVOS or sum(i.file_size for i in miembros) > MAX_ZIP_MB * 1024 * 1024:
            return [Archivo(base, "error", mensaje=f"El .zip pasa de {MAX_ZIP_ARCHIVOS} archivos o {MAX_ZIP_MB} MB.")]
        salida = []
        for i in miembros:
            salida += separar(i.filename, z.read(i), dentro_de_zip=True)
        return salida or [Archivo(base, "error", mensaje="El .zip está vacío.")]
    if n.endswith(".txt") and b"|" in contenido[:5000]:
        return [Archivo(base, "referencia", contenido, mensaje="TXT ya presentado: solo se usa para comparar.")]
    if contenido[:2] == b"PK":
        hojas = _hojas(contenido)
        claves = {h.strip().upper() for h in hojas}
        if "CLAVES TIPOS" in claves or "LAYOUT" in n.upper():
            return [Archivo(base, "no_se_usa", mensaje="Es el layout ya llenado con el resultado; no se usa como fuente.")]
        if {"COMPROBANTESEXP", "PROVEEDORES"} <= claves:
            try:
                return _del_papel(base, contenido, hojas)
            except Exception as e:  # noqa: BLE001 - el archivo viene del usuario
                return [Archivo(base, "error", mensaje=f"No se pudo leer el papel de trabajo ({e.__class__.__name__}).")]
    try:
        t = leer(base, contenido)
    except ErrorLectura as e:
        return [Archivo(base, "error", mensaje=str(e))]
    if not t.tipo:
        otro = _conocido(contenido)
        if otro:
            return [Archivo(base, "no_se_usa", mensaje=otro)]
        return [Archivo(base, "error", mensaje="No se reconoció qué reporte es por sus columnas.")]
    return [Archivo(base, "documento", contenido, t.tipo)]


def _conocido(contenido: bytes) -> str | None:
    """Archivos que Fiscal junta con los del mes pero que la DIOT todavía no lee: se dice qué son en vez de un error."""
    if contenido[:2] != b"PK":
        return None
    try:
        hojas = _de_excel(contenido)
    except ErrorLectura:
        return None
    textos = " ".join(str(x) for _, filas in hojas for f in filas[:10] for x in f if isinstance(x, str)).upper()
    if "MONEX" in textos:
        return ("Estado de cuenta de MONEX: este formato todavía no se lee. No cambia el cálculo de la DIOT; "
                "los pagos a proveedores salen del reporte de tesorería.")
    return None


# ---------------------------------------------------------------- valores

def es_error(v) -> bool:
    return isinstance(v, str) and v.strip().upper() in ERRORES_EXCEL


def decimal(v) -> Decimal | None:
    """Número o None si está vacío. Lanza ValueError si trae un error de Excel o texto que no es número."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError(str(v))
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    s = str(v).strip().replace(",", "").replace("$", "")
    if s == "":
        return None
    if es_error(s):
        raise ValueError(s)
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(s) from None


def texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, datetime):
        return v.isoformat()
    return _norm(v)
