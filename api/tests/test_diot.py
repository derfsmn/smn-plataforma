"""TD003 · DIOT: lectura, motor, layout y flujo completo por la API.

Todos los datos de estas pruebas son ficticios (RFC inventados con formato válido). La validación contra los archivos
reales de Fiscal está al final y solo corre si existe la carpeta de DIOT_ARCHIVOS_REALES (fuera del repositorio).
"""
import io
import os
import time
import zipfile
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from modulos.contraloria import diot_layout as layout
from modulos.contraloria import diot_lectura as lectura
from modulos.contraloria import diot_motor as motor

RFC_EMPRESA = "ODP160830242"  # la empresa sembrada en la migración 0025


# ---------------------------------------------------------------- documentos ficticios

def _xlsx(columnas, filas, titulo_arriba=False) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    if titulo_arriba:  # como los reportes que traen título antes de los encabezados
        ws.append(["Reporte de prueba"])
        ws.append([])
    ws.append(list(columnas))
    for f in filas:
        ws.append(list(f))
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _html(columnas, filas) -> bytes:
    def tr(celdas, tag="td"):
        return "<tr>" + "".join(f"<{tag}>{'' if c is None else c}</{tag}>" for c in celdas) + "</tr>"
    return ("<html><body><table>" + tr(columnas, "th") + "".join(tr(f) for f in filas)
            + "</table></body></html>").encode("utf-8")


def _csv(columnas, filas) -> bytes:
    lineas = [",".join(columnas)] + [",".join("" if c is None else str(c) for c in f) for f in filas]
    return ("\r\n".join(lineas) + "\r\n").encode("utf-8")


COL_TES = ("ID", "Mov", "MovID", "Concepto", "Referencia", "BeneficiarioNombre", "Contacto", "TipoCambio",
           "RFCReceptor", "Impuesto1", "Importe1", "SubTotal")
TESORERIA = [
    (1, "Pago", "1", "PAGO PROVEEDOR", "FACT 1", "Servicios Ficticios", "", 1, "CCC010101CCC", 16, 160, 1000),
    (2, "Abono Bancario", "2", "INTERESES", "", "Banco Ficticio", "", 1, "", "", "", 50),
    (3, "Pago", "3", "ANTICIPO SF PROVEEDOR", "", "Proveedor Anticipo", "", 1, "FFF010101FFF", 16, 80, 500),
    (4, "Pago", "4", "RETIRO CUOTAS", "", "INSTITUTO MEXICANO DEL SEGURO SOCIAL", "", 1, "", "", "", 5000),
    (5, "Pago", "5", "PAGO PROVEEDOR", "FACT 5", "Alimentos Ficticios", "", 1, "DDD010101DDD", 0, 0, 300),
    (6, "Pago", "6", "TRASPASO", "", "La propia empresa", "", 1, RFC_EMPRESA, 16, 16, 100),
    (7, "Pago", "7", "PAGO PROVEEDOR", "REEM CC 01", "Caja chica", "", 1, "", 16, 16, 100),
]
COL_APL = ("Movimiento", "Origen", "Impuesto1", "Importe1", "Importe2", "SubTotal", "Mov", "MovID", "RFC", "nombre")
APLICACIONES = [("Aplicacion 10", "Aplicacion", 16, 32, 0, 200, "Aplicacion", "10", "EEE010101EEE", "Proveedor E"),
                ("Anticipo 11", "Anticipo", 16, 16, 0, 100, "Anticipo", "11", "EEE010101EEE", "Proveedor E")]
COL_AUX = ("Movimiento", "Debe", "Haber", "Origen", "OrigenID", "OrigenTipoCambio")
AUXILIAR = [("Aplicacion 10", 32, 0, "Aplicacion", "10", 1), ("Gasto 5", 16, 0, "Gasto", "5", 1)]
COL_COM = ("Movimiento", "Acreedor", "Concepto", "Cantidad", "Precio", "TipoCambio", "% IVA", "Poliza", "PolizaID",
           "Estatus")
COMPROBANTES = [("Gasto 5", "A001", "PAPELERIA", 1, 100, 1, 16, "Gasto", "5", "CONCLUIDO"),
                ("Gasto 5", "A002", "AGUA DE GARRAFON", 2, 50, 1, 0, "Gasto", "5", "CONCLUIDO"),
                ("Gasto 6", "A001", "PAPELERIA", 1, 999, 1, 16, "Gasto", "6", "CONCLUIDO"),
                ("Gasto 7", "A001", "PAPELERIA", 1, 999, 1, 16, "Gasto", "5", "CANCELADO")]
COL_PROV = ("Clave", "Nombre", "RFC")
PROVEEDORES = [("A001", "Papelería Ficticia", "AAA010101AAA"), ("A002", "Agua Ficticia", "BBB010101BBB")]
COL_RET = ("Cuenta", "Movimiento", "Debe", "Haber")
RETENIDO = [("2500-002-007", "Gasto 5", 0, 10.67)]


def documentos() -> dict[str, tuple[str, bytes]]:
    return {
        "tesoreria": ("Reporte impuestos tesoreria.xls", _html(COL_TES, TESORERIA)),
        "aplicaciones": ("Rep apps cxp.csv", _csv(COL_APL, APLICACIONES)),
        "auxiliar_iva": ("Auxiliar IVA.xlsx", _xlsx(COL_AUX, AUXILIAR, titulo_arriba=True)),
        "comprobantes": ("Explorador.xlsx", _xlsx(COL_COM, COMPROBANTES)),
        "proveedores": ("Proveedores.xlsx", _xlsx(COL_PROV, PROVEEDORES)),
        "iva_retenido": ("Retenido.xlsx", _xlsx(COL_RET, RETENIDO)),
    }


def tablas(sin=()) -> dict[str, lectura.Tabla]:
    return {k: lectura.leer(n, c) for k, (n, c) in documentos().items() if k not in sin}


# ---------------------------------------------------------------- lectura

COL_BANCO = ("Cuenta", "Fecha Valor", "Folio Banco", "Transacción", "Tipo de Movimiento", "Importe", "Moneda",
             "Folio Aceptación", "Referencia", "Contrato", "Fecha Operación")


def _estado_cuenta(movs) -> bytes:
    """Un estado de cuenta ficticio con la forma del de BBVA (Cash Windows): tipo, importe y folio de Intelisis."""
    return _xlsx(COL_BANCO, [(None, "2099-01-05", "0001", "SPEI ENVIADO", tipo, imp, 2, folio, "REF", "0", "2099/01/05")
                             for tipo, imp, folio in movs])


def _auxiliar_intelisis(cuenta: str, nombre: str, movs) -> bytes:
    """Auxiliar como sale de Intelisis («Auxiliares - Contabilidad»): título, encabezado en el renglón 4, la cuenta
    en un renglón aparte y columnas sin nombre."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Auxiliares - Contabilidad", "Del 1 Enero 2099 al 31 Enero 2099", "EMPRESA FICTICIA"])
    ws.append(["Sucursal :", "", "(Todas)"])
    ws.append([])
    ws.append(["Sucursal", "Centro Costos", "Movimiento", None, None, None, "Origen", None, None, "Fecha", "Debe",
               "Haber", "Saldo"])
    ws.append([None, cuenta, nombre])
    for mov, debe, haber in movs:
        ws.append([2000, None, mov, "CONCEPTO", "GAS", "Gasto", "LAB1", "Pesos", 1, "2099-01-05", debe, haber, 0])
    ws.append([None, None, None, None, None, "Total", 0, 0, 0, 0, 99999])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_auxiliar_de_iva_retenido_como_sale_de_intelisis():
    """Fiscal entrega el auxiliar de la 2500-002-007 tal cual sale de Intelisis (ODP agosto 2026, archivo 06)."""
    t = lectura.leer("06.- CTA IVA RETENIDO.xlsx", _auxiliar_intelisis("2500-002-007", "IVA RETENIDO",
                                                                        [("Gasto 5", None, 10.67)]))
    assert t.tipo == "iva_retenido"
    mov = [f for f in t.filas if f["Movimiento"] == "Gasto 5"]
    assert len(mov) == 1 and mov[0]["Haber"] == 10.67
    # el mismo formato de otra cuenta no se toma por IVA retenido
    otra = lectura.leer("aux.xlsx", _auxiliar_intelisis("1190-001-001", "IVA ACREDITABLE", [("Gasto 5", 16, None)]))
    assert otra.tipo is None


def test_estado_de_cuenta_contra_tesoreria():
    from modulos.contraloria import diot_validacion as validacion

    col = ("Mov", "MovID", "CtaDinero", "BeneficiarioNombre", "FechaEmision", "Importe", "Impuesto1", "Importe1",
           "SubTotal", "ID", "Concepto", "Referencia", "Contacto", "TipoCambio", "RFCReceptor")
    filas = [("Cheque Electronico", "LAB1", "BCO1", "Proveedor A", "2099-01-05", 1160, 16, 160, 1000),
             ("Cheque Electronico", "LAB1", "BCO1", "Proveedor A", "2099-01-05", 1160, 0, 0, 0),  # 2º renglón de impuesto
             ("Cheque Electronico", "LAB2", "BCO1", "Proveedor B", "2099-01-06", 500, 16, 69, 431),
             ("Cheque Electronico", "LAB3", "BCO1", "Proveedor C", "2099-01-07", 300, 16, 41, 259),
             ("Cheque Electronico", "LAB4", "BCO1", "Proveedor D", "2099-01-08", 200, 16, 28, 172),
             ("Cheque Electronico", "LAB5", "BCO1", "Proveedor E", "2099-01-05", 700, 16, 97, 603),
             ("Abono Bancario", "LAB9", "BCO1", "Banco", "2099-01-09", 50, 0, 0, 50),
             ("Cargo Bancario", "LAB7", "BCO2", "Banco", "2099-01-09", 10, 0, 0, 10)]
    tes = lectura.leer("tes.xls", _html(col, [f + (k, "", "", "", 1, "") for k, f in enumerate(filas)]))
    assert tes.tipo == "tesoreria"
    banco = _estado_cuenta([("Cargo", 1000, "LAB1"), ("Cargo", "$160.00", "TR LAB1"),  # un pago en 2 cargos
                            ("Cargo", 500, "LAB2"), ("Cargo", 299, "LAB3"),  # LAB3 con otro importe; LAB4 no está
                            ("Cargo", 7000, "TR LAB50"), ("Abono", 50, "LAB9"),
                            ("Cargo", 700, "LAB500")])  # LAB5 con el folio mal escrito, mismo día e importe
    archivo = lectura.separar("04.- BANCO 31.xlsx", banco)
    assert [(a.clase, a.tipo) for a in archivo] == [("documento", "estado_cuenta")]
    r = validacion.comparar_banco(tes, [("04.- BANCO 31.xlsx", lectura.leer("b.xlsx", banco))])
    c = r["cuentas"][0]
    assert c["cuenta"] == "BCO1" and c["pagos"] == 5 and c["confirmados"] == 3
    assert [(x["movid"], x["folio_banco"]) for x in c["otro_folio"]] == [("LAB5", "LAB500")]
    assert [x["movid"] for x in c["diferencias"]] == ["LAB3"] and c["diferencias"][0]["banco"] == 299
    assert [x["movid"] for x in c["no_encontrados"]] == ["LAB4"]
    assert [x["folio"] for x in c["solo_banco"]] == ["LAB50"]
    assert r["sin_estado"] == [{"cuenta": "BCO2", "pagos": 1, "importe": 10.0}]


def test_archivos_del_mes_que_no_se_usan_dicen_que_son():
    visor = _xlsx(("UUID", "VersionCFDI", "Serie"), [("x", "4.0", "A")])
    wb = openpyxl.load_workbook(io.BytesIO(visor))
    wb.active.insert_rows(1, 3)
    wb.active["A1"] = "AAA010101AAA Visor de CFDI(s) de tipo Pago Recibidos"
    b = io.BytesIO()
    wb.save(b)
    monex = _xlsx(("Tipo de mov", "Divisa", "Descripción"), [("G", "MXP", "Retiro")])
    wb = openpyxl.load_workbook(io.BytesIO(monex))
    wb.active.insert_rows(1, 2)
    wb.active["B1"] = "EMPRESA FICTICIA (MONEX)"
    b2 = io.BytesIO()
    wb.save(b2)
    for nombre, contenido, texto in (("visor.xlsx", b.getvalue(), "Visor de CFDI"), ("monex.xlsx", b2.getvalue(), "MONEX")):
        a = lectura.separar(nombre, contenido)
        assert a[0].clase == "no_se_usa" and texto in a[0].mensaje, a[0].mensaje

def test_reconoce_cada_documento_por_sus_columnas_no_por_su_nombre():
    for tipo, (nombre, contenido) in documentos().items():
        t = lectura.leer("cualquier-nombre" + nombre[nombre.rfind("."):], contenido)
        assert t.tipo == tipo, (tipo, t.columnas)
    aux = lectura.leer("a.xlsx", documentos()["auxiliar_iva"][1])
    assert len(aux.filas) == 2 and aux.filas[0]["Movimiento"] == "Aplicacion 10"  # salta el título


def test_libro_de_varias_hojas():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Proveedores"
    ws.append(list(COL_PROV))
    for f in PROVEEDORES:
        ws.append(list(f))
    for hoja in ("ComprobantesExp", "Historico"):
        ws = wb.create_sheet(hoja)
        ws.append([*COL_COM, "Formula"])
        ws.append([*COMPROBANTES[0], "x"])
        for _ in range(5):  # fórmulas arrastradas sin datos
            ws.append([None] * len(COL_COM) + ["#N/A"])
    b = io.BytesIO()
    wb.save(b)
    assert lectura.leer("libro.xlsx", b.getvalue(), "proveedores").hoja == "Proveedores"
    t = lectura.leer("libro.xlsx", b.getvalue(), "comprobantes")  # la hoja con el nombre que usa Fiscal
    assert t.hoja == "ComprobantesExp" and len(t.filas) == 1  # sin los renglones de fórmulas vacías
    wb["ComprobantesExp"].title = "Otra"
    b = io.BytesIO()
    wb.save(b)
    with pytest.raises(lectura.ErrorLectura, match="2 hojas"):  # sin nombre conocido no se adivina
        lectura.leer("libro.xlsx", b.getvalue(), "comprobantes")


def _papel_de_trabajo() -> bytes:
    """Un papel de trabajo ficticio con la forma del de Fiscal: hojas crudas, hojas calculadas y fórmulas arrastradas."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Proveedores"
    ws.append(list(COL_PROV) + ["Tipo", "Categoria"])
    for f in PROVEEDORES:
        ws.append(list(f))
    ws = wb.create_sheet("ComprobantesExp")
    ws.append(list(COL_COM) + ["RFC"])
    for f in COMPROBANTES:
        ws.append(list(f) + ["#N/A"])
    for _ in range(20):
        ws.append([None] * len(COL_COM) + ["#N/A"])
    ws = wb.create_sheet("IVARetenidoD")  # histórico con la misma forma: no se lee
    ws.append(list(COL_COM))
    ws.append(["Gasto 1", "A001", "PAPELERIA", 1, 5, 1, 16, "Gasto", "1", "CONCLUIDO"])
    ws = wb.create_sheet("IVARetenido")
    ws.append(["Cuenta", "Descripcion", "Movimiento", "Debe", "Haber"])
    ws.append(["2500-002-007", "IVA RETENIDO", None, None, None])
    ws.append([None, None, "Gasto 5", 0, 10.67])
    ws = wb.create_sheet("RETENCIONES")
    ws.append(["Tipo de Operación ..."])
    ws.append([None, None, None, "TIPO DE OPERACIÓN"])
    ws.append(["CCC010101CCC", "Servicios", "HONORARIOS", "03"])
    ws = wb.create_sheet("DIOT AL PESO")  # el resultado de Fiscal: nunca se lee
    ws.append(["RFC", "TIPO DE OPERACIÓN"])
    ws.append(["CCC010101CCC", "85"])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_acepta_los_archivos_como_los_entrega_fiscal():
    layout_xlsx = openpyxl.Workbook()
    layout_xlsx.active.title = "DIOT"
    layout_xlsx.create_sheet("CLAVES TIPOS")
    b = io.BytesIO()
    layout_xlsx.save(b)
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("ODP/0199 DIOT ODP.xlsx", _papel_de_trabajo())
        zf.writestr("ODP/0199 LAYOUT DIOT ODP.xlsx", b.getvalue())
        zf.writestr("ODP/0199 CARGA DIOT ODP.txt", "04|02|CCC010101CCC|\r\n")
        for tipo in ("tesoreria", "aplicaciones", "auxiliar_iva"):
            zf.writestr("ODP/" + documentos()[tipo][0], documentos()[tipo][1])
    partes = lectura.separar("ODP.zip", z.getvalue())
    clases = {a.tipo or a.clase: a for a in partes}
    assert set(clases) == {"comprobantes", "proveedores", "iva_retenido", "tipos_operacion", "tesoreria", "aplicaciones",
                           "auxiliar_iva", "referencia", "no_se_usa"}
    docs = {a.tipo: lectura.leer(a.nombre, a.contenido, a.tipo) for a in partes if a.clase == "documento"}
    assert len(docs["comprobantes"].filas) == 4  # ni el histórico ni las fórmulas vacías
    assert len(docs["iva_retenido"].filas) == 1
    r = motor.procesar(docs, RFC_EMPRESA)
    assert not any(i.codigo == "ERROR-EXCEL" for i in r.incidencias)  # #N/A en columnas que no se usan
    t = _por_rfc(r)
    assert t["CCC010101CCC"].tipo_operacion == "03"  # de RETENCIONES, no de DIOT AL PESO
    assert t["AAA010101AAA"].redondeados["iva_retenido"] == 11


def test_rechaza_xls_binario_y_formatos_desconocidos():
    with pytest.raises(lectura.ErrorLectura, match="97-2003"):
        lectura.leer("viejo.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100)
    with pytest.raises(lectura.ErrorLectura):
        lectura.leer("foto.png", b"\x89PNG\r\n")
    assert lectura.leer("otro.csv", _csv(("A", "B"), [(1, 2)])).tipo is None


def test_los_errores_de_excel_no_se_vuelven_cero():
    assert lectura.decimal("1,234.50") == Decimal("1234.50")
    assert lectura.decimal("") is None
    with pytest.raises(ValueError):
        lectura.decimal("#N/A")
    t = tablas()
    t["tesoreria"].filas[0]["Importe1"] = "#N/A"
    r = motor.procesar(t, RFC_EMPRESA)
    assert any(i.codigo == "VALOR" and i.impacto == motor.POSIBLE for i in r.incidencias)
    assert any(i.codigo == "ERROR-EXCEL" for i in r.incidencias)


# ---------------------------------------------------------------- motor

def _por_rfc(r):
    return {t.rfc: t for t in r.terceros}


def test_motor_clasifica_cruza_y_consolida_por_rfc():
    r = motor.procesar(tablas(), RFC_EMPRESA)
    assert not r.faltantes
    reglas = {o.referencia: o.regla for o in r.operaciones if o.fuente == "tesoreria"}
    assert reglas == {"Pago 1": "TES-TASA", "Abono Bancario 2": "TES-BANCO", "Pago 3": "TES-ANTICIPO-SF",
                      "Pago 4": "TES-IMSS", "Pago 5": "TES-TASA", "Pago 6": "TES-PROPIA", "Pago 7": "TES-CAJA-CHICA"}
    t = _por_rfc(r)
    assert set(t) == {"AAA010101AAA", "BBB010101BBB", "CCC010101CCC", "DDD010101DDD", "EEE010101EEE",
                      motor.RFC_IMSS}
    assert t["CCC010101CCC"].redondeados["base16"] == 1000 and t["CCC010101CCC"].redondeados["iva16"] == 160
    assert t["DDD010101DDD"].redondeados["base0"] == 300
    assert t["EEE010101EEE"].redondeados["base16"] == 200  # solo la aplicación, no el anticipo
    assert t["AAA010101AAA"].redondeados["base16"] == 100  # la póliza 6 no está en el auxiliar; la 7 está cancelada
    assert t["AAA010101AAA"].redondeados["iva_retenido"] == 11
    assert t["BBB010101BBB"].redondeados["base0"] == 100  # agua de garrafón a tasa 0
    assert t[motor.RFC_IMSS].redondeados["no_objeto"] == 5000
    assert all(x.tipo_operacion == "02" for x in r.terceros)
    codigos = {i.codigo: i.impacto for i in r.incidencias}
    assert codigos["IMSS-INFONAVIT"] == motor.POSIBLE
    assert codigos["ANTICIPO-SF"] == motor.CONTROLADO
    assert codigos["SIN-TIPOS"] == motor.CONTROLADO


def test_devolucion_de_gasto_resta():
    """ODP agosto 2026: «Caja Chica LAB54» y su «Devolucion Gasto LAB23» se anulan (en el auxiliar, Debe y Haber)."""
    docs = tablas()
    extra = [("Caja Chica 8", "A001", "TORNILLOS 16%", 1, 194, 1, 16, "Gasto", "8", "CONCLUIDO"),
             ("Devolucion Gasto 9", "A001", "TORNILLOS 16%", 1, 194, 1, 16, "Gasto", "9", "CONCLUIDO")]
    docs["comprobantes"] = lectura.leer("e.xlsx", _xlsx(COL_COM, COMPROBANTES + extra))
    docs["auxiliar_iva"] = lectura.leer("a.xlsx", _xlsx(COL_AUX, AUXILIAR + [("Gasto 8", 31.04, 0, "Gasto", "8", 1),
                                                                              ("Gasto 9", 0, 31.04, "Gasto", "9", 1)]))
    r = motor.procesar(docs, RFC_EMPRESA)
    devolucion = next(o for o in r.operaciones if o.referencia.startswith("Devolucion Gasto 9"))
    assert devolucion.base16 == -194 and devolucion.iva16 < 0
    assert _por_rfc(r)["AAA010101AAA"].redondeados["base16"] == 100  # igual que sin los dos renglones


def test_faltantes_bloquean_y_opcionales_avisan():
    r = motor.procesar(tablas(sin=("comprobantes", "iva_retenido")), RFC_EMPRESA)
    assert r.bloqueado and any("Explorador" in f for f in r.faltantes) and not r.terceros
    r = motor.procesar(tablas(sin=("iva_retenido",)), RFC_EMPRESA)
    assert not r.bloqueado
    assert any(i.codigo == "SIN-RETENIDO" for i in r.incidencias)


def test_redondeo_al_peso_es_hacia_arriba_desde_medio_peso():
    assert motor.redondear(Decimal("0.5")) == 1
    assert motor.redondear(Decimal("2.5")) == 3
    assert motor.redondear(Decimal("2.49")) == 2


def test_ajustes_de_fiscal_quedan_trazados():
    ajustes = [{"rfc": "DDD010101DDD", "excluir": True, "motivo": "prueba"},
               {"rfc": "CCC010101CCC", "campo": "base16", "importe": Decimal("1"), "motivo": "prueba"},
               {"rfc": "XAXX010101000", "campo": "base16", "importe": Decimal("35"), "tipo_tercero": "15",
                "tipo_operacion": "85", "motivo": "prueba"}]
    t = _por_rfc(motor.procesar(tablas(), RFC_EMPRESA, ajustes))
    assert "DDD010101DDD" not in t
    assert t["CCC010101CCC"].redondeados["base16"] == 1001 and t["CCC010101CCC"].ajustes
    assert t["XAXX010101000"].tipo_tercero == "15" and t["XAXX010101000"].tipo_operacion == "85"


def test_tipos_de_operacion_por_rfc():
    docs = tablas()
    docs["tipos_operacion"] = lectura.leer("t.xlsx", _xlsx(("RFC", "Nombre", "TIPO DE OPERACIÓN"),
                                                           [("CCC010101CCC", "Servicios", 3)]))
    assert docs["tipos_operacion"].tipo == "tipos_operacion"
    assert _por_rfc(motor.procesar(docs, RFC_EMPRESA))["CCC010101CCC"].tipo_operacion == "03"


def test_tasa_8_bloquea_el_txt_hasta_confirmar_el_layout():
    docs = tablas()
    docs["tesoreria"].filas.append(dict(zip(COL_TES, (8, "Pago", "8", "PAGO", "F8", "Frontera", "", 1,
                                                      "GGG010101GGG", 8, 8, 100))))
    r = motor.procesar(docs, RFC_EMPRESA)
    assert _por_rfc(r)["GGG010101GGG"].estado == "revisar"
    with pytest.raises(layout.ErrorLayout):
        layout.generar(r.terceros)


# ---------------------------------------------------------------- layout

def test_txt_de_54_campos_con_crlf_y_comparacion():
    r = motor.procesar(tablas(), RFC_EMPRESA)
    txt = layout.generar(r.terceros)
    lineas = txt.split("\r\n")
    assert lineas[-1] == "" and len(lineas) - 1 == len(r.terceros)
    c = lineas[0].split("|")
    assert len(c) == 54 and c[0] == "04" and c[1] == "02" and c[53] == "01"
    txt.encode("ascii")
    ccc = next(x for x in lineas if "|CCC010101CCC|" in x).split("|")
    assert ccc[11] == "1000" and ccc[21] == "160" and ccc[50] == "0"
    referencia = txt.replace("|CCC010101CCC|" + "|" * 8 + "1000|", "|CCC010101CCC|" + "|" * 8 + "1001|")
    cmp = layout.comparar(txt, referencia)
    assert cmp["renglones_iguales"] == len(r.terceros) - 1 and cmp["formato_igual"]
    assert cmp["diferencias"] == [{"rfc": "CCC010101CCC", "campo": "12 · Base 16 %", "generado": "1000",
                                   "referencia": "1001"}]
    assert cmp["totales"]["Base 16 %"]["diferencia"] == -1


# ---------------------------------------------------------------- API

def _subir(admin, pid, nombre, contenido, tipo=None):
    datos = {"tipo": tipo} if tipo else None
    return admin.post(f"/api/contraloria/diot/periodos/{pid}/documentos", files={"archivo": (nombre, contenido)},
                      data=datos)


def _procesar(admin, pid):
    """«Procesar» arranca una corrida en segundo plano; se sigue como la pantalla hasta que termina."""
    base = "/api/contraloria/diot"
    p = admin.post(f"{base}/periodos/{pid}/procesar").json()
    cid, desde, lineas = p["corrida"]["id"], 0, []
    for _ in range(300):
        co = admin.get(f"{base}/corridas/{cid}", params={"desde": desde}).json()
        lineas += co["lineas"]
        desde = lineas[-1]["id"] if lineas else desde
        if co["estado"] != "en_curso":
            break
        time.sleep(0.1)
    assert co["estado"] in ("terminada", "detenida"), co
    assert [x["orden"] for x in co["pasos"]] == list(range(1, 9)) and lineas
    assert len({x["id"] for x in lineas}) == len(lineas)  # «desde» no repite renglones
    return admin.get(f"{base}/periodos/{pid}").json(), co, lineas


def test_flujo_completo_por_la_api(admin):
    base = "/api/contraloria/diot"
    cat = admin.get(f"{base}/catalogos").json()
    odp = next(e for e in cat["empresas"] if e["codigo"] == "ODP")
    assert {t["codigo"] for t in cat["tipos"]} >= {"tesoreria", "comprobantes", "proveedores"}

    p = admin.post(f"{base}/periodos", json={"empresa_id": odp["id"], "anio": 2099, "mes": 1}).json()
    pid = p["id"]
    assert len(p["faltan"]) == 5 and not p["puede_txt"]

    r = _subir(admin, pid, "foto.png", b"\x89PNG\r\n")
    assert r.status_code == 400
    docs = documentos()
    for tipo in ("tesoreria", "aplicaciones", "auxiliar_iva", "proveedores", "iva_retenido"):
        r = _subir(admin, pid, *docs[tipo])
        assert r.status_code == 200, r.text
    r = _subir(admin, pid, "explorador.xlsx", docs["comprobantes"][1], tipo="proveedores")
    # el tipo a mano se valida por columnas; si el archivo es de otro tipo, se dice cuál es
    assert r.status_code == 400 and "es «Explorador de gastos (DIOT) de Intelisis», no «Catálogo" in r.text
    # Estados de cuenta: uno por cuenta, se quedan los dos; no cuentan como faltantes ni entran al cálculo
    for nombre in ("Banco cuenta 1.xlsx", "Banco cuenta 2.xlsx"):
        r = _subir(admin, pid, nombre, _estado_cuenta([("Cargo", 100, "LAB1")]))
        assert r.status_code == 200 and r.json()["archivos"][0]["tipo"] == "estado_cuenta", r.text
    docs_banco = [d for d in r.json()["periodo"]["documentos"] if d["tipo"] == "estado_cuenta"]
    assert len(docs_banco) == 2
    # Un archivo conocido que no se usa, subido en un renglón, dice qué es (ODP agosto: el MONEX en «Tipos de operación»)
    monex = _xlsx(("Tipo de mov", "Divisa", "Descripción"), [("G", "MXP", "Retiro")])
    wb = openpyxl.load_workbook(io.BytesIO(monex))
    wb.active.insert_rows(1, 2)
    wb.active["B1"] = "EMPRESA FICTICIA (MONEX)"
    b = io.BytesIO()
    wb.save(b)
    r = _subir(admin, pid, "07.- (Tipo de operaciones) MONEX.xlsx", b.getvalue(), tipo="tipos_operacion")
    assert r.status_code == 400 and "no es «Tipos de operación por RFC». Es estado de cuenta de MONEX" in r.text, r.text
    # El papel de trabajo no trae las aplicaciones como salen de Intelisis: se dice así, no «le faltan columnas»
    r = _subir(admin, pid, "0899 DIOT ODP.xlsx", _papel_de_trabajo(), tipo="aplicaciones")
    assert r.status_code == 400 and "papel de trabajo" in r.text and "Sube ese reporte aparte" in r.text

    p, co, lineas = _procesar(admin, pid)
    assert p["estado"] == "abierto" and p["resumen"]["faltantes"]
    assert co["estado"] == "detenida" and co["pasos"][0]["estado"] == "detenido"
    assert all(x["estado"] == "no_ejecutado" for x in co["pasos"][1:])  # no se salta pasos: se detiene

    r = _subir(admin, pid, *docs["comprobantes"]).json()
    assert r["archivos"][0]["tipo"] == "comprobantes"
    p = r["periodo"]
    assert p["faltan"] == []
    p, co, lineas = _procesar(admin, pid)
    assert p["estado"] == "procesado" and p["terceros"] == 6
    assert [x["estado"] for x in co["pasos"][:3]] == ["ok"] * 3 and co["pasos"][5]["estado"] == "ok"
    assert co["pasos"][3]["estado"] == "aviso"  # el auxiliar ficticio no cuadra con todo: queda para Fiscal
    assert co["pasos"][6]["estado"] == "ok"  # las validaciones del TXT pasaron
    assert co["pasos"][7]["estado"] == "aviso"  # entrega detenida hasta revisar el IMSS
    assert {x["paso"] for x in lineas} == set(range(1, 9))
    assert not p["puede_txt"] and p["pendientes"] >= 1  # IMSS-INFONAVIT con posible impacto
    assert admin.get(f"{base}/periodos/{pid}/txt").status_code == 409

    ops = admin.get(f"{base}/periodos/{pid}/operaciones", params={"rfc": "CCC010101CCC"}).json()
    assert len(ops) == 1 and ops[0]["regla"] == "TES-TASA" and ops[0]["regla_texto"]

    incs = admin.get(f"{base}/periodos/{pid}/incidencias").json()
    imss = next(i for i in incs if i["codigo"] == "IMSS-INFONAVIT")
    r = admin.patch(f"{base}/incidencias/{imss['id']}", json={"estado": "revisada"})
    assert r.status_code == 400  # sin nota no se da por revisada
    for i in incs:
        if i["impacto"] == "posible_impacto":
            r = admin.patch(f"{base}/incidencias/{i['id']}", json={"estado": "revisada", "nota": "Revisado en prueba"})
            assert r.status_code == 200 and r.json()["estado"] == "revisada"

    r = admin.post(f"{base}/periodos/{pid}/ajustes", json={"rfc": "CCC010101CCC", "motivo": "x"})
    assert r.status_code == 422
    r = admin.post(f"{base}/periodos/{pid}/ajustes", json={"rfc": "CCC010101CCC", "motivo": "Sin cambio"})
    assert r.status_code == 400
    r = admin.post(f"{base}/periodos/{pid}/ajustes",
                   json={"rfc": "CCC010101CCC", "campo": "base16", "importe": "1", "motivo": "Redondeo de Fiscal"})
    assert r.status_code == 200 and len(r.json()) == 1
    p, co, _ = _procesar(admin, pid)
    assert co["estado"] == "terminada" and co["pasos"][7]["estado"] == "ok"
    assert p["puede_txt"], p["motivo_sin_txt"]  # la revisión se conserva al reprocesar
    ter = {t["rfc"]: t for t in admin.get(f"{base}/periodos/{pid}/terceros").json()}
    assert ter["CCC010101CCC"]["redondeados"]["base16"] == 1001 and ter["CCC010101CCC"]["ajustado"]

    r = admin.get(f"{base}/periodos/{pid}/txt")
    assert r.status_code == 200 and r.content.endswith(b"\r\n") and len(r.content.splitlines()) == 6
    generado = r.content

    ev = admin.get(f"{base}/periodos/{pid}/evidencia")
    assert ev.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(ev.content))
    assert {"Consolidado", "Operaciones", "Incidencias", "Ajustes de Fiscal", "Documentos", "Criterios", "Bitácora"} <= set(
        wb.sheetnames)

    p = admin.post(f"{base}/periodos/{pid}/referencia", files={"archivo": ("ref.txt", generado)}).json()
    assert p["comparacion"]["renglones_iguales"] == 6 and not p["comparacion"]["diferencias"]

    p = admin.patch(f"{base}/periodos/{pid}", json={"estado": "cerrado"}).json()
    assert p["estado"] == "cerrado"
    assert _subir(admin, pid, *docs["tesoreria"]).status_code == 409


def test_alta_de_empresa(admin):
    base = "/api/contraloria/diot"
    r = admin.post(f"{base}/empresas", json={"codigo": "PRUEBA99", "nombre": "Empresa   de prueba"})
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["codigo"] == "PRUEBA99" and e["nombre"] == "Empresa de prueba" and e["rfc"] is None
    assert any(x["id"] == e["id"] for x in admin.get(f"{base}/catalogos").json()["empresas"])
    assert admin.post(f"{base}/empresas", json={"codigo": "PRUEBA99", "nombre": "Otra"}).status_code == 409
    assert admin.post(f"{base}/empresas", json={"codigo": "X Y", "nombre": "Mala clave"}).status_code == 422
    assert admin.post(f"{base}/empresas", json={"codigo": "PRUEBA98", "nombre": "RFC malo", "rfc": "ABC"}).status_code == 422


def test_sin_permiso_no_entra(admin):
    from tests.conftest import alta_usuario

    _, otro, _ = alta_usuario(admin, rol="compras_consulta")
    assert otro.get("/api/contraloria/diot/catalogos").status_code == 403


# ---------------------------------------------------------------- validación con los archivos reales (fuera del repo)

REALES = Path(os.environ.get("DIOT_ARCHIVOS_REALES", "/mnt/project-files/td003/ODP/2026"))


@pytest.mark.parametrize("mes,renglones,iguales_minimo", [("8.- Agosto", 81, 77), ("9.- Septiembre", 69, 63)])
def test_validacion_con_los_archivos_de_fiscal(mes, renglones, iguales_minimo):
    carpeta = REALES / mes
    if not carpeta.is_dir():
        pytest.skip("Sin archivos reales de la DIOT en este equipo")
    # Los archivos tal como los entrega Fiscal (lo que venía en el zip), metidos en un .zip como los subiría.
    archivos = sorted(f for f in (carpeta / "Archivos").glob("*") if f.is_file())
    if not archivos:
        pytest.skip("Faltan documentos reales para validar")
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for f in archivos:
            z.write(f, f"ODP/{f.name}")
    partes = lectura.separar("ODP.zip", b.getvalue())
    docs = {a.tipo: lectura.leer(a.nombre, a.contenido, a.tipo) for a in partes if a.clase == "documento"}
    referencia = next((a.contenido for a in partes if a.clase == "referencia"), None)
    assert any(a.clase == "no_se_usa" and "LAYOUT" in a.nombre.upper() for a in partes)
    assert set(docs) == {k for k, t in lectura.TIPOS.items() if not t.comprobar} and referencia
    b = motor.Bitacora()
    r = motor.procesar(docs, RFC_EMPRESA, bitacora=b)
    estados = [b.pasos[n]["estado"] for n in range(1, 8)]
    assert estados[:2] == ["ok", "ok"] and estados[2] in ("ok", "aviso") and estados[3:] == ["ok"] * 4, estados
    assert b.pasos[4]["resumen"].startswith("Conciliación correcta")
    assert r.txt and all(v["ok"] for v in r.validaciones)  # conciliación correcta y 12 validaciones del TXT
    cmp = layout.comparar(layout.generar([t for t in r.terceros if t.estado == "ok"]),
                          referencia.decode("latin-1"))
    assert cmp["renglones_referencia"] == renglones
    assert cmp["renglones_iguales"] >= iguales_minimo
