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


# Los reportes del portal en .xlsx cierran con un renglón de totales (solo Debe y Haber, sin póliza): no es un
# movimiento. Un renglón cuenta solo si trae la columna que lo identifica.
IDENTIFICA = {"auxiliar_iva": "Movimiento", "tesoreria": "Mov", "aplicaciones": "Movimiento"}
CARGOS_BANCARIOS = "REPORTE CARGOS BANCARIOS"


def _titulo(filas: list[list], i: int) -> str:
    return " ".join(_clave(x) for f in filas[:i] for x in f if isinstance(x, str))


CUENTA_IVA_ACREDITABLE = "1300-001-000"
# Auxiliar de Intelisis («Auxiliares - Contabilidad»): columnas fijas, varias sin nombre en el encabezado.
COLUMNAS_AUXILIAR_INTELISIS = {2: "Movimiento", 3: "Concepto", 4: "OrigenTipo", 5: "Origen", 6: "OrigenID",
                               7: "OrigenMoneda", 8: "OrigenTipoCambio", 9: "FechaContable", 10: "Debe", 11: "Haber"}


def _auxiliar_contable(filas: list[list]) -> Tabla | None:
    """El auxiliar contable de la cuenta de IVA acreditable como sale de Intelisis (PS septiembre 2026 lo entregó así
    en vez del reporte del portal). Trae lo mismo que el del portal: póliza, origen, tipo de cambio, debe y haber."""
    titulo = " ".join(_clave(x) for f in filas[:3] for x in f if isinstance(x, str))
    if "AUXILIARES - CONTABILIDAD" not in titulo:
        return None
    i = next((k for k, f in enumerate(filas[:15]) if [_clave(x) for x in f[:3]] == ["SUCURSAL", "CENTRO COSTOS",
                                                                                   "MOVIMIENTO"]), None)
    if i is None or not any(isinstance(x, str) and CUENTA_IVA_ACREDITABLE in x for f in filas[i:i + 3] for x in f):
        return None
    datos = []
    for f in filas[i + 1:]:
        mov = _norm(f[2]) if len(f) > 2 else ""
        if not mov or _clave(mov) in ("MOVIMIENTO", "IVA ACREDITABLE") or not str(mov)[:1].isalpha():
            continue
        fila = {c: (f[k] if k < len(f) else None) for k, c in COLUMNAS_AUXILIAR_INTELISIS.items()}
        fila["Referencia"] = f"{_norm(fila['Origen'])} {_norm(fila['OrigenID'])}".strip() or _norm(fila["Concepto"])
        datos.append(fila)
    columnas = list(COLUMNAS_AUXILIAR_INTELISIS.values()) + ["Referencia"]
    return Tabla(tipo="auxiliar_iva", columnas=columnas, filas=datos,
                 avisos=["Auxiliar contable de Intelisis (cuenta 1300-001-000), leído como el reporte del portal."])


def _cfdi_descarga(filas: list[list]) -> Tabla | None:
    """CFDI recibidos de la descarga masiva que usa Fiscal en PS («Reporte octubre 2026 recibidos / EGRESOS / Pagos»,
    columnas «RFC emisor», «CP Expedicion», «Estado»): se pasan a las columnas del Visor de CFDI para que todo lo demás
    funcione igual. En el de Pagos cada renglón es un documento relacionado y el total del pago se repite: se toma
    una vez por UUID."""
    if not filas:
        return None
    h = [_norm(x) for x in filas[0]]
    k = {_clave(x).replace(" ", ""): i for i, x in enumerate(h) if x}
    if not {"UUID", "RFCEMISOR", "CPEXPEDICION", "ESTADO"} <= set(k):
        return None
    pagos = "FECHAPAGO" in k

    def v(f, col):
        i = k.get(_clave(col).replace(" ", ""))
        return f[i] if i is not None and i < len(f) else None

    def anio_mes(x):
        t = texto(x)
        return (t[:4], str(int(t[5:7]))) if len(t) >= 7 and t[:4].isdigit() and t[5:7].isdigit() else (None, None)

    def num(x):
        try:
            return decimal(x) or Decimal(0)
        except ValueError:
            return Decimal(0)

    emisores = {texto(v(f, "RFC emisor")).upper() for f in filas[1:] if texto(v(f, "UUID"))}
    receptores = {texto(v(f, "RFC receptor")).upper() for f in filas[1:] if texto(v(f, "UUID"))}
    if len(emisores) == 1 and (len(receptores) > 1 or receptores <= {"XAXX010101000"}):
        # «Reporte … EGRESOS» de PS octubre 2026: notas de crédito que emite la propia empresa a público general.
        return Tabla(None, h, [], avisos=["Son CFDI que emitió la empresa (no recibidos): no van en la DIOT. Sube "
                                          "los recibidos y los complementos de pago."])
    datos, vistos = [], set()
    for f in filas[1:]:
        uuid = texto(v(f, "UUID")).upper()
        if not uuid or (pagos and uuid in vistos):
            continue
        vistos.add(uuid)
        if pagos:
            tc = num(v(f, "TipoCambioP")) if "->" not in texto(v(f, "MonedaP")) and texto(v(f, "MonedaP")) not in ("", "MXN") else Decimal(1)
            iva16, iva8 = num(v(f, "TrasladosImpuestoIVA16 - pago")) * (tc or 1), num(v(f, "TrasladosImpuestoIVA8 - pago")) * (tc or 1)
            base8 = num(v(f, "TrasladosBaseIVA8 - pago")) * (tc or 1)
            tipo, metodo = "P", ""
        else:
            iva16, iva8 = num(v(f, "IVA Trasladado 16%")), num(v(f, "IVA Trasladado 8%"))
            base8 = (iva8 / Decimal("0.08")).quantize(Decimal("0.01")) if iva8 else Decimal(0)
            tipo, metodo = texto(v(f, "Tipo"))[:1].upper(), texto(v(f, "Metodo pago"))[:3].upper()
        ej, per = anio_mes(v(f, "Fecha emision"))
        ejp, perp = anio_mes(v(f, "Fecha pago")) if pagos else (None, None)
        datos.append({"UUID": uuid, "TipoDeComprobante": tipo, "EmisorRFC": texto(v(f, "RFC emisor")).upper(),
                      "EmisorNombre": texto(v(f, "Razon emisor")), "EstadoComprobante": texto(v(f, "Estado")).upper(),
                      "MetodoDePago": metodo, "EjercicioCFDI": ej, "PeriodoCFDI": per, "EjercicioPago": ejp,
                      "PeriodoPago": perp, "LugarExpedicion": texto(v(f, "CP Expedicion")),
                      "TotalTrasladosImpuestoIVA16": iva16, "TotalTrasladosImpuestoIVA8": iva8,
                      "TotalTrasladosBaseIVA8": base8, "Total": num(v(f, "Total"))})
    columnas = list(datos[0]) if datos else ["UUID", "TipoDeComprobante", "EmisorRFC", "EstadoComprobante"]
    return Tabla("cfdi_sat", columnas, datos, avisos=["CFDI de la descarga masiva; se leyeron como el Visor de CFDI."])


def _estado_monex(filas: list[list]) -> Tabla | None:
    """Estado de cuenta de Monex («Movimientos del Contrato…»): importe con signo y, después de la columna «Mov», el
    folio de Intelisis que le pone Fiscal («Cheque Electronico LAB759»). Se lee como el de BBVA: cargo o abono, importe
    y folio (ODP octubre 2026, cuenta en dólares)."""
    if not any(isinstance(x, str) and "MOVIMIENTOS DEL CONTRATO" in _clave(x) for f in filas[:8] for x in f):
        return None
    i = next((k for k, f in enumerate(filas[:15]) if [_clave(x) for x in f[:2]] == ["TIPO DE MOV", "DIVISA"]), None)
    if i is None:
        return None
    pos = {_clave(x): k for k, x in enumerate(filas[i]) if isinstance(x, str)}
    if "IMPORTE" not in pos or "MOV" not in pos:
        return None
    datos = []
    for f in filas[i + 1:]:
        imp = f[pos["IMPORTE"]] if pos["IMPORTE"] < len(f) else None
        if not isinstance(imp, (int, float, Decimal)) or isinstance(imp, bool) or not imp:
            continue
        cel = lambda c: f[pos[c]] if c in pos and pos[c] < len(f) else None  # noqa: E731
        folio = " ".join(_norm(x) for x in f[pos["MOV"] + 1:] if x not in (None, ""))
        datos.append({"Tipo de Movimiento": "Cargo" if imp < 0 else "Abono", "Importe": abs(imp),
                      "Folio Aceptación": folio, "Transacción": _norm(cel("DESCRIPCIÓN") or cel("DESCRIPCION")),
                      "Referencia": _norm(cel("REFERENCIA")), "Moneda": _norm(cel("DIVISA")),
                      "Fecha Operación": cel("FECHA OPERACIÓN") or cel("FECHA OPERACION")})
    columnas = ["Tipo de Movimiento", "Importe", "Folio Aceptación", "Transacción", "Referencia", "Moneda",
                "Fecha Operación"]
    return Tabla(tipo="estado_cuenta", columnas=columnas, filas=datos,
                 avisos=["Estado de cuenta de Monex, leído como el de BBVA (cargo o abono, importe y folio)."])


MESES_CORTOS = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10,
                "NOV": 11, "DIC": 12}
_MONEX_FECHA = re.compile(r"^\s*(\d{2})/([A-Za-z]{3})\b")
_MONEX_IMPORTES = re.compile(r"(\d{5,})\s+(-?[\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})(?:\s+-?[\d,]+\.\d{2}){4}\s*$")
_MONEX_BENEFICIARIO = re.compile(r"Nombre Beneficiario:\s*(.+?)\s*(?:Clave de|Referencia Num|Concepto del|$)")


def _texto_pdf(contenido: bytes) -> str:
    from pypdf import PdfReader  # solo se carga si llega un PDF

    try:
        paginas = PdfReader(io.BytesIO(contenido)).pages
        # Un PDF que es imagen («Imprimir como PDF») no trae texto en ninguna página: se ve en las primeras sin recorrer
        # las cientos de páginas de un estado de cuenta de BBVA.
        if not any((p.extract_text() or "").strip() for p in paginas[:3]):
            return ""
        return "\n".join(p.extract_text() or "" for p in paginas)
    except Exception as e:  # noqa: BLE001 (PDF dañado o cifrado)
        raise ErrorLectura(f"No se pudo abrir el PDF: {e}") from e


def _estado_monex_pdf(texto: str) -> Tabla | None:
    """Estado de cuenta de Monex en PDF (como lo descarga Fiscal): cada movimiento empieza con «dd/Mmm» y termina en
    el renglón «referencia abonos cargos … saldo». No trae el folio de Intelisis: se empata por fecha e importe."""
    if "Estado de Cuenta" not in texto or "CONTRATO" not in texto.upper() or "MONEX" not in texto.upper():
        return None
    m = re.search(r"PERIODO:\s*Del\s+\d+\s+\w+\s+(\d{4})", texto)
    anio = int(m.group(1)) if m else None
    moneda, datos, bloque, fecha = "", [], [], None
    for linea in texto.splitlines():
        u = linea.strip().upper()
        if u.startswith("ANEXO INVERSIONES") or u.startswith("RESUMEN DE INVERSIONES"):
            break
        if re.match(r"^PESO MEXICANO AL \d", u):
            moneda = "MXN"
        elif re.match(r"^D[ÓO]LAR AMERICANO AL \d", u) or u.endswith("EN DÓLAR AMERICANO"):
            moneda = "USD"
        f = _MONEX_FECHA.match(linea)
        if f and f.group(2).upper()[:3] in MESES_CORTOS:
            bloque, fecha = [], f"{anio or 0:04d}-{MESES_CORTOS[f.group(2).upper()[:3]]:02d}-{f.group(1)}"
            linea = linea[f.end():]
        if fecha is None:
            continue
        i = _MONEX_IMPORTES.search(linea)
        if not i:
            bloque.append(linea)
            continue
        bloque.append(linea[:i.start()])
        desc = _norm(" ".join(bloque))
        abono, cargo = (Decimal(x.replace(",", "")) for x in (i.group(2), i.group(3)))
        if abono or cargo:
            b = _MONEX_BENEFICIARIO.search(desc)
            datos.append({"Tipo de Movimiento": "Cargo" if cargo else "Abono", "Importe": cargo or abono,
                          "Folio Aceptación": "", "Transacción": desc[:300], "Referencia": i.group(1),
                          "Moneda": moneda, "Fecha Operación": fecha, "Beneficiario": b.group(1) if b else ""})
        bloque, fecha = [], None
    if not datos:
        return None
    columnas = ["Tipo de Movimiento", "Importe", "Folio Aceptación", "Transacción", "Referencia", "Moneda",
                "Fecha Operación", "Beneficiario"]
    return Tabla(tipo="estado_cuenta", columnas=columnas, filas=datos,
                 avisos=["Estado de cuenta de Monex en PDF: sin folio de Intelisis, se empata por fecha e importe."])


def _tabla(filas: list[list], hoja: str | None, nombre: str = "") -> Tabla:
    contable = _auxiliar_contable(filas) or _estado_monex(filas) or _cfdi_descarga(filas)
    if contable:
        contable.hoja = hoja
        return contable
    i, tipo = _encabezado(filas)
    avisos = []
    if tipo == "iva_retenido" and not _es_iva_retenido(filas, i):
        # Un auxiliar sin movimientos no trae el renglón de la cuenta: se acepta si el archivo se llama «…retenido…».
        vacio = not any(isinstance(x, (int, float, Decimal)) and not isinstance(x, bool) and x != 0
                        for f in filas[i + 1:] for x in f)
        if vacio and "RETENID" in _clave(nombre):
            avisos.append("El auxiliar de IVA retenido viene sin movimientos: el IVA retenido del mes es cero.")
            filas = filas[: i + 1]
        else:
            tipo = None
    if tipo == "auxiliar_iva" and CARGOS_BANCARIOS in _titulo(filas, i):
        tipo = None  # mismas columnas que el auxiliar de IVA, pero es otro reporte del portal
    columnas = _sin_repetir([_norm(x) for x in (filas[i] if filas else [])])
    # Con tipo reconocido, un renglón cuenta solo si trae algo en las columnas del tipo: las hojas de trabajo arrastran
    # fórmulas hacia abajo (#N/A, ceros) en renglones que no tienen datos.
    clave = {_clave(c) for c in TIPOS[tipo].columnas} if tipo else None
    datos = []
    for f in filas[i + 1:]:
        if not any(x not in (None, "") and (clave is None or _clave(columnas[k] if k < len(columnas) else "") in clave)
                   for k, x in enumerate(f) if not (isinstance(x, str) and not x.strip())):
            continue
        fila = {c: (f[k] if k < len(f) else None) for k, c in enumerate(columnas) if c}
        if tipo in IDENTIFICA and not _norm(fila.get(IDENTIFICA[tipo])):
            continue
        datos.append(fila)
    return Tabla(tipo=tipo, columnas=[c for c in columnas if c], filas=datos, hoja=hoja, avisos=avisos)


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
        tablas = [_tabla(f, h, nombre) for h, f in hojas if f]
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
    if inicio.startswith(b"%pdf"):
        texto = _texto_pdf(contenido)
        if not texto.strip():
            raise ErrorLectura("El PDF no trae texto (es una imagen, por ejemplo de «Imprimir como PDF»). Descárgalo "
                               "directo del portal del banco.")
        t = _estado_monex_pdf(texto)
        if t:
            return t
        raise ErrorLectura("Este PDF no es un estado de cuenta que se sepa leer (por ahora, Monex).")
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
    if CARGOS_BANCARIOS in textos:
        return ("Reporte de cargos bancarios del portal (comisiones de bancos y plataformas): todavía no entra al "
                "cálculo de la DIOT. Falta que Fiscal diga cómo se declaran; no es el auxiliar de IVA acreditable.")
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
