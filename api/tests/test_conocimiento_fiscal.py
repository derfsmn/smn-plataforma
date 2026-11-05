"""Base de conocimiento fiscal de la DIOT (TD003): criterios con versión y aprobación, catálogos y layout con vigencia,
documentos de soporte y «Probar con un periodo». Datos ficticios; los archivos reales viven fuera del repositorio."""
import copy

from decimal import Decimal

from modulos.contraloria import diot_criterios as crit
from modulos.contraloria import diot_layout as layout
from modulos.contraloria import diot_motor as motor
from tests.test_diot import COL_TES, RFC_EMPRESA, _procesar, _subir, documentos, tablas

BASE = "/api/contraloria/conocimiento"
DIOT = "/api/contraloria/diot"


def _por_rfc(r):
    return {t.rfc: t for t in r.terceros}


def _pago(docs, n, concepto, nombre, rfc, tasa, iva, subtotal, referencia=""):
    docs["tesoreria"].filas.append(dict(zip(COL_TES, (n, "Pago", str(n), concepto, referencia, nombre, "", 1, rfc,
                                                      tasa, iva, subtotal))))


def _cfg(**cambios) -> crit.Config:
    """Todo aprobado, con parámetros cambiados: {"TER-REDONDEO": {"metodo": "art20"}}."""
    c = crit.todo_aprobado()
    for clave, params in cambios.items():
        c.criterios[clave].parametros.update(params)
    return c


# ---------------------------------------------------------------- motor con criterios

def test_carga_inicial_es_como_trabaja_fiscal_hoy():
    c = crit.inicial()
    pendientes = {k for k, x in c.criterios.items() if x.estado != crit.APROBADO}
    # Las dos contradicciones que siguen abiertas: 50 centavos exactos y 02 contra 85
    assert pendientes == {"TER-REDONDEO", "TER-TIPO-OPERACION"}
    assert c.p("TER-REDONDEO", "metodo") == "mitad_arriba" and c.p("TER-TIPO-OPERACION", "omision") == "02"
    assert c.p("TES-IMSS", "tratamiento") == "no_objeto"
    assert set(c.tipos_tercero) == {"04", "05", "15"} and "85" in c.tipos_operacion
    assert all(d.contradiccion for d in crit.SISTEMA if d.estado == crit.PENDIENTE)


def test_redondeo_segun_el_criterio():
    assert motor.redondear(Decimal("10452.50")) == 10453  # como se presentó
    assert motor.redondear(Decimal("10452.50"), "art20") == 10452  # art. 20 CFF: 50 centavos bajan
    assert motor.redondear(Decimal("10452.51"), "art20") == 10453
    assert motor.redondear(Decimal("10452.01"), "art20") == 10452
    docs = tablas()
    _pago(docs, 20, "PAGO PROVEEDOR", "Medio Peso", "MMM010101MMM", 16, Decimal("16.08"), Decimal("100.50"))
    # base 16 % = 16.08 / 0.16 = 100.50 exactos
    r = motor.procesar(docs, RFC_EMPRESA, cfg=_cfg(**{"TER-REDONDEO": {"metodo": "art20"}}))
    assert _por_rfc(r)["MMM010101MMM"].redondeados["base16"] == 100
    r = motor.procesar(docs, RFC_EMPRESA)  # carga inicial: 50 centavos suben y el criterio está pendiente
    assert _por_rfc(r)["MMM010101MMM"].redondeados["base16"] == 101
    pend = [i for i in r.incidencias if i.codigo == "CRITERIO-PENDIENTE" and "TER-REDONDEO" in i.mensaje]
    assert len(pend) == 1 and pend[0].impacto == motor.POSIBLE and "MMM010101MMM" in pend[0].mensaje
    # sin importes de 50 centavos exactos, el criterio pendiente no estorba
    assert not any("TER-REDONDEO" in i.mensaje for i in motor.procesar(tablas(), RFC_EMPRESA).incidencias)


def test_tipo_de_operacion_por_omision_y_su_contradiccion():
    r = motor.procesar(tablas(), RFC_EMPRESA)
    assert all(t.tipo_operacion == "02" for t in r.terceros)
    assert any("TER-TIPO-OPERACION" in i.mensaje for i in r.incidencias if i.codigo == "CRITERIO-PENDIENTE")
    r = motor.procesar(tablas(), RFC_EMPRESA, cfg=_cfg(**{"TER-TIPO-OPERACION": {"omision": "85"}}))
    assert all(t.tipo_operacion == "85" for t in r.terceros)
    assert not any(i.codigo == "CRITERIO-PENDIENTE" for i in r.incidencias)


def test_tipos_de_tercero_y_tope_del_global():
    docs = tablas()
    _pago(docs, 21, "PAGO", "Proveedor del extranjero", "XEXX010101000", 16, 16, 100)
    _pago(docs, 22, "PAGO", "Mal capturado", "ABC12345", 16, 16, 100)
    _pago(docs, 23, "PAGO", "Público en general", "XAXX010101000", 16, 1600, 10000)
    r = motor.procesar(docs, RFC_EMPRESA, cfg=crit.todo_aprobado())
    t = _por_rfc(r)
    assert (t["XEXX010101000"].tipo_tercero, t["XEXX010101000"].tipo_operacion) == ("05", "07")
    assert (t["XAXX010101000"].tipo_tercero, t["XAXX010101000"].tipo_operacion) == ("15", "85")
    # un RFC mal escrito no se vuelve extranjero: queda sin tipo y por revisar
    assert t["ABC12345"].tipo_tercero == "" and t["ABC12345"].estado == "revisar"
    assert any(i.codigo == "RFC-INVALIDO" and i.rfc == "ABC12345" for i in r.incidencias)
    tope = [i for i in r.incidencias if i.codigo == "TOPE-GLOBAL"]
    assert len(tope) == 1 and tope[0].impacto == motor.POSIBLE  # 10,000 de ~17,000 pasa del 10 %
    r = motor.procesar(docs, RFC_EMPRESA, cfg=_cfg(**{"TER-TIPO-TERCERO": {"tope_global": "90"}}))
    assert not any(i.codigo == "TOPE-GLOBAL" for i in r.incidencias)


def test_imss_infonavit_nomina_y_agua_segun_fiscal():
    docs = tablas()
    _pago(docs, 24, "IMPUESTO SOBRE NOMINA SEP", "Gobierno del Estado", "GEM850101AAA", "", "", 3000)
    r = motor.procesar(docs, RFC_EMPRESA)
    regla = {o.referencia: o.regla for o in r.operaciones}
    assert regla["Pago 24"] == "TES-NOMINA"  # el impuesto sobre nómina no se declara
    assert _por_rfc(r)[motor.RFC_IMSS].redondeados["no_objeto"] == 5000
    inf = next(i for i in r.incidencias if i.codigo == "IMSS-INFONAVIT")
    assert "no se declara" in inf.mensaje  # el INFONAVIT se descarta
    r = motor.procesar(tablas(), RFC_EMPRESA, cfg=_cfg(**{"TES-IMSS": {"tratamiento": "excluir"}}))
    assert motor.RFC_IMSS not in _por_rfc(r)
    docs = tablas()
    docs["comprobantes"].filas.append({"Movimiento": "Gasto 5", "Acreedor": "A001", "Concepto": "AGUA POTABLE",
                                       "Cantidad": 1, "Precio": 80, "TipoCambio": 1, "% IVA": 0, "Poliza": "Gasto",
                                       "PolizaID": "5", "Estatus": "CONCLUIDO"})
    r = motor.procesar(docs, RFC_EMPRESA)
    agua = [i for i in r.incidencias if i.codigo == "DEBERIA-IVA"]
    assert len(agua) == 1 and agua[0].impacto == motor.POSIBLE  # debería traer 16 % (8 % en frontera)


def test_criterios_propios_solo_aprobados():
    docs = tablas()
    _pago(docs, 25, "PREDIAL 2026", "Municipio", "MUN010101AAA", "", "", 2000)
    propio = crit.Criterio("PROPIO-001", "Predial como no objeto", crit.PENDIENTE, {}, tipo="propio",
                           condicion={"fuente": "tesoreria", "campo": "concepto", "operador": "empieza",
                                      "valor": "predial"}, accion={"accion": "no_objeto"})
    cfg = crit.todo_aprobado()
    cfg.criterios[propio.clave] = propio
    r = motor.procesar(docs, RFC_EMPRESA, cfg=cfg)
    assert {o.referencia: o.regla for o in r.operaciones}["Pago 25"] == "TES-SIN-TASA"  # pendiente: no se aplica
    propio.estado = crit.APROBADO
    r = motor.procesar(docs, RFC_EMPRESA, cfg=cfg)
    op = next(o for o in r.operaciones if o.referencia == "Pago 25")
    assert op.regla == "PROPIO-001" and op.incluida and op.no_objeto == 2000
    assert _por_rfc(r)["MUN010101AAA"].redondeados["no_objeto"] == 2000
    cfg.criterios["PROPIO-002"] = crit.Criterio(
        "PROPIO-002", "Servicios profesionales", crit.APROBADO, {}, tipo="propio",
        condicion={"fuente": "cualquiera", "campo": "rfc", "operador": "igual", "valor": "CCC010101CCC"},
        accion={"accion": "tipo_operacion", "tipo_operacion": "03"})
    assert _por_rfc(motor.procesar(docs, RFC_EMPRESA, cfg=cfg))["CCC010101CCC"].tipo_operacion == "03"


def test_layout_configurable():
    docs = tablas()
    _pago(docs, 26, "PAGO", "Frontera", "GGG010101GGG", 8, 8, 100)
    r = motor.procesar(docs, RFC_EMPRESA, cfg=crit.todo_aprobado())
    assert _por_rfc(r)["GGG010101GGG"].estado == "revisar" and r.txt is None  # el 8 % no tiene campo
    cfg = crit.todo_aprobado()
    cfg.mapa.update({13: "base8", 23: "iva8"})
    r = motor.procesar(docs, RFC_EMPRESA, cfg=cfg)
    assert r.txt and all(v["ok"] for v in r.validaciones)
    g = next(x for x in r.txt.split("\r\n") if "|GGG010101GGG|" in x).split("|")
    assert g[12] == "100" and g[22] == "8" and len(g) == 54
    otro = copy.deepcopy(cfg)
    otro.campos_layout = 55
    assert not next(v for v in layout.validar(r.txt, r.terceros, otro) if v["verificacion"] == "Número de campos")["ok"]


# ---------------------------------------------------------------- API

def _criterio(base, clave):
    return next(c for c in base["criterios"] if c["clave"] == clave)


def test_base_de_conocimiento_por_la_api(admin):
    b = admin.get(BASE).json()
    assert len([c for c in b["criterios"] if c["tipo"] == "sistema"]) == len(crit.SISTEMA)
    assert b["resumen"]["pendientes"] >= 2 and b["resumen"]["contradicciones"] >= 2
    red = _criterio(b, "TER-REDONDEO")
    assert red["ultima"]["estado"] == "pendiente" and red["contradiccion"] and red["campos"][0]["tipo"] == "opcion"
    assert red["documento"] == crit.DOC_SAT
    assert {c["clave"] for c in b["catalogos"] if c["catalogo"] == "tipo_tercero"} == {"04", "05", "15"}
    assert any(d["titulo"] == crit.DOC_RESPUESTAS for d in b["documentos"])

    # Cambiar un parámetro crea una versión nueva, pendiente, desde la fecha que se elija
    r = admin.post(f"{BASE}/criterios/TER-TIPO-OPERACION/versiones",
                   json={"parametros": {"omision": "85"}, "vigente_desde": "2099-05-01", "motivo": "x"})
    assert r.status_code == 422  # motivo muy corto
    r = admin.post(f"{BASE}/criterios/TER-TIPO-OPERACION/versiones",
                   json={"parametros": {"omision": "ochenta"}, "vigente_desde": "2099-05-01", "motivo": "Prueba"})
    assert r.status_code == 422
    r = admin.post(f"{BASE}/criterios/TER-TIPO-OPERACION/versiones",
                   json={"parametros": {"omision": "85"}, "vigente_desde": "2099-05-01",
                         "motivo": "Fiscal confirma 85 para compras"})
    assert r.status_code == 200, r.text
    t = _criterio(r.json(), "TER-TIPO-OPERACION")
    assert t["ultima"]["version"] == 2 and t["ultima"]["estado"] == "pendiente"
    assert t["vigente"]["version"] == 1  # hoy sigue la versión 1; la 2 empieza en 2099

    # Probar con un periodo: corre sin guardar y compara contra lo último procesado
    odp = next(e for e in admin.get(f"{DIOT}/catalogos").json()["empresas"] if e["codigo"] == "ODP")
    pid = admin.post(f"{DIOT}/periodos", json={"empresa_id": odp["id"], "anio": 2099, "mes": 5}).json()["id"]
    for nombre, contenido in documentos().values():
        assert _subir(admin, pid, nombre, contenido).status_code == 200
    p, co, _ = _procesar(admin, pid)
    assert all(t["tipo_operacion"] == "85" for t in admin.get(f"{DIOT}/periodos/{pid}/terceros").json())
    incs = admin.get(f"{DIOT}/periodos/{pid}/incidencias").json()
    assert any(i["codigo"] == "CRITERIO-PENDIENTE" and "TER-TIPO-OPERACION" in i["mensaje"] for i in incs)

    r = admin.post(f"{BASE}/criterios/TER-TIPO-OPERACION/versiones",
                   json={"parametros": {"omision": "02"}, "vigente_desde": "2099-05-01", "motivo": "Probar regreso",
                         "borrador": True}).json()
    v3 = _criterio(r, "TER-TIPO-OPERACION")["ultima"]
    assert v3["estado"] == "borrador"
    prueba = admin.post(f"{BASE}/probar", json={"periodo_id": pid, "criterio_id": v3["id"]}).json()
    assert prueba["procesado"] and prueba["cambios"]
    assert all(c["que"] == "Tipo de operación" and (c["antes"], c["despues"]) == ("85", "02")
               for c in prueba["cambios"])
    assert not any("TER-TIPO-OPERACION" in m for m in prueba["criterios_pendientes"])

    # Aprobar: borrador -> pendiente -> aprobado, con historial
    r = admin.post(f"{BASE}/criterios/version/{v3['id']}/estado", json={"accion": "regresar", "nota": "x"})
    assert r.status_code == 422  # solo se regresa uno pendiente
    assert admin.post(f"{BASE}/criterios/version/{v3['id']}/estado", json={"accion": "enviar"}).status_code == 200
    r = admin.post(f"{BASE}/criterios/version/{v3['id']}/estado", json={"accion": "aprobar", "nota": "Fiscal: 02"})
    assert _criterio(r.json(), "TER-TIPO-OPERACION")["ultima"]["estado"] == "aprobado"
    h = admin.get(f"{BASE}/criterios/TER-TIPO-OPERACION/historial").json()
    assert [x["accion"] for x in h[:4]] == ["aprobado", "enviado", "editado", "editado"]
    assert h[-1]["usuario"] == "Carga inicial"
    p, co, _ = _procesar(admin, pid)
    incs = admin.get(f"{DIOT}/periodos/{pid}/incidencias").json()
    assert not any("TER-TIPO-OPERACION" in i["mensaje"] for i in incs)
    from sqlalchemy.orm import Session

    from core.bd import motor as motor_bd
    from modulos.contraloria.modelos_diot import DiotCorrida
    with Session(motor_bd()) as bd:  # la corrida guarda qué versión de cada criterio usó
        import json
        usado = json.loads(bd.get(DiotCorrida, co["id"]).criterios)
        assert usado["criterios"]["TER-TIPO-OPERACION"] == {"version": 3, "estado": "aprobado"}


def test_criterios_propios_catalogos_y_documentos_por_la_api(admin):
    nuevo = {"titulo": "Donativos fuera", "condicion": {"fuente": "comprobantes", "campo": "concepto",
                                                        "operador": "contiene", "valor": "DONATIVO"},
             "accion": {"accion": "excluir"}, "vigente_desde": "2099-06-01", "motivo": "Prueba"}
    r = admin.post(f"{BASE}/criterios", json={**nuevo, "accion": {"accion": "tipo_operacion", "tipo_operacion": "03"}})
    assert r.status_code == 422  # tipo de operación solo con «RFC es igual a»
    r = admin.post(f"{BASE}/criterios", json=nuevo)
    assert r.status_code == 200, r.text
    propio = next(c for c in r.json()["criterios"] if c["tipo"] == "propio" and c["titulo"] == "Donativos fuera")
    assert propio["ultima"]["estado"] == "pendiente" and "no se aplica" in propio["si_pendiente"]
    vid = propio["ultima"]["id"]
    assert admin.post(f"{BASE}/criterios/version/{vid}/estado", json={"accion": "retirar"}).status_code == 422
    r = admin.post(f"{BASE}/criterios/version/{vid}/estado", json={"accion": "retirar", "nota": "Ya no aplica"})
    assert r.status_code == 200
    r = admin.post(f"{BASE}/criterios/TES-BANCO/versiones", json={})
    assert r.status_code == 422
    r = admin.post(f"{BASE}/criterios/version/{_criterio(admin.get(BASE).json(), 'TES-BANCO')['ultima']['id']}/estado",
                   json={"accion": "retirar", "nota": "No"})
    assert r.status_code == 422  # los del sistema no se retiran: se cambian

    # Layout: el campo del 8 % se registra con vigencia
    r = admin.post(f"{BASE}/catalogos", json={"catalogo": "layout", "clave": "13", "valor": "nada",
                                              "vigente_desde": "2099-06-01"})
    assert r.status_code == 422
    r = admin.post(f"{BASE}/catalogos", json={"catalogo": "layout", "clave": "13", "valor": "base8",
                                              "descripcion": "Base 8 %", "vigente_desde": "2099-06-01"})
    assert r.status_code == 200
    from sqlalchemy.orm import Session

    from core.bd import motor as motor_bd
    from modulos.contraloria import conocimiento_fiscal as conocimiento
    from datetime import date
    with Session(motor_bd()) as bd:
        assert conocimiento.config(bd, date(2099, 6, 1)).mapa[13] == "base8"
        assert 13 not in conocimiento.config(bd, date(2026, 8, 1)).mapa  # agosto sigue con su layout
    cat = next(c for c in r.json()["catalogos"] if c["catalogo"] == "layout" and c["clave"] == "13")
    r = admin.post(f"{BASE}/catalogos/{cat['id']}/baja", json={"vigente_hasta": "2099-05-01"})
    assert r.status_code == 422  # antes de que empezara
    assert admin.post(f"{BASE}/catalogos/{cat['id']}/baja", json={"vigente_hasta": "2099-06-30"}).status_code == 200

    # Documentos con archivo, huella y versión que reemplaza a la anterior
    r = admin.post(f"{BASE}/documentos", data={"titulo": "Matriz de prueba", "tipo": "matriz", "version": "1"},
                   files={"archivo": ("matriz.docx", b"contenido ficticio")})
    assert r.status_code == 200
    d1 = next(d for d in r.json()["documentos"] if d["titulo"] == "Matriz de prueba")
    assert len(d1["sha256"]) == 64
    assert admin.get(f"{BASE}/documentos/{d1['id']}/archivo").content == b"contenido ficticio"
    r = admin.post(f"{BASE}/documentos", data={"titulo": "Matriz de prueba", "tipo": "matriz", "version": "2",
                                                "reemplaza": str(d1["id"])},
                   files={"archivo": ("matriz v2.docx", b"otra")})
    docs = {d["id"]: d for d in r.json()["documentos"]}
    assert not docs[d1["id"]]["activo"] and any(d["reemplaza_a"] == d1["id"] for d in docs.values())


def test_sin_permiso_no_ve_la_base(admin):
    from tests.conftest import alta_usuario

    _, otro, _ = alta_usuario(admin, rol="compras_consulta")
    assert otro.get(BASE).status_code == 403
    assert otro.post(f"{BASE}/probar", json={"periodo_id": 1}).status_code == 403
