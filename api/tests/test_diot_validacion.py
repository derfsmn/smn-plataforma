"""TD003 · DIOT: las 7 comprobaciones para validar el TXT, la muestra, los motivos de diferencia y las dos firmas.

Solo datos ficticios (los mismos documentos de prueba de test_diot.py)."""

import io

import openpyxl

from modulos.contraloria import diot_validacion as validacion
from tests.conftest import alta_usuario
from tests.test_diot import _procesar, _subir, documentos

BASE = "/api/contraloria/diot"
CLAVES = ["contabilidad", "pagos", "declaracion", "muestra", "banco", "sat", "mes_anterior", "formato", "presentado"]


def _mes_listo(admin, mes):
    """Un periodo procesado, con las decisiones resueltas y TXT."""
    odp = next(e for e in admin.get(f"{BASE}/catalogos").json()["empresas"] if e["codigo"] == "ODP")
    pid = admin.post(f"{BASE}/periodos", json={"empresa_id": odp["id"], "anio": 2098, "mes": mes}).json()["id"]
    for tipo, (nombre, contenido) in documentos().items():
        assert _subir(admin, pid, nombre, contenido).status_code == 200
    _procesar(admin, pid)
    c = admin.get(f"{BASE}/periodos/{pid}/comprobaciones").json()
    assert c["paso"] == 2 and c["pendientes"] >= 1  # IMSS-INFONAVIT necesita una decisión
    for i in admin.get(f"{BASE}/periodos/{pid}/incidencias").json():
        if i["impacto"] == "posible_impacto":
            admin.patch(f"{BASE}/incidencias/{i['id']}", json={"estado": "revisada", "nota": "Revisado en prueba"})
    p, _, _ = _procesar(admin, pid)
    assert p["puede_txt"], p["motivo_sin_txt"]
    return pid


def test_comprobaciones_en_palabras(admin):
    pid = _mes_listo(admin, 3)
    c = admin.get(f"{BASE}/periodos/{pid}/comprobaciones").json()
    assert [x["clave"] for x in c["comprobaciones"]] == CLAVES
    assert all(x["frase"] and x["pregunta"] and x["estado"] in ("ok", "revisar", "falla", "sin_datos", "info")
               for x in c["comprobaciones"])
    por = {x["clave"]: x for x in c["comprobaciones"]}
    assert c["pendientes"] == 0 and c["proveedores"] == 6 and c["frase"]
    assert por["formato"]["estado"] == "ok" and len(por["formato"]["detalle"]["verificaciones"]) == 12
    assert por["declaracion"]["estado"] == "sin_datos" and por["presentado"]["estado"] == "sin_datos"
    assert por["mes_anterior"]["estado"] in ("info", "sin_datos")
    assert por["banco"]["estado"] == "sin_datos"  # sin estado de cuenta no se compara (es opcional)
    assert por["sat"]["estado"] == "sin_datos"  # sin archivos del SAT no se compara (es opcional)

    # embudo: cada renglón leído cae en un grupo y los grupos suman lo del reporte
    for r in por["pagos"]["detalle"]["embudo"]:
        assert sum(g["renglones"] for g in r["grupos"]) == r["renglones"]
        assert {g["tipo"] for g in r["grupos"]} <= {"entra", "sin_explicar", "no_entra"}

    # declaración: igual al IVA del TXT queda bien; distinta pide revisar; vacía vuelve a «sin datos»
    r = admin.put(f"{BASE}/periodos/{pid}/iva-declarado", json={"importe": str(round(c["iva"])), "nota": "Prueba"})
    assert r.status_code == 200
    assert next(x for x in r.json()["comprobaciones"] if x["clave"] == "declaracion")["estado"] == "ok"
    r = admin.put(f"{BASE}/periodos/{pid}/iva-declarado", json={"importe": str(round(c["iva"]) + 5000)})
    assert next(x for x in r.json()["comprobaciones"] if x["clave"] == "declaracion")["estado"] == "revisar"
    assert admin.put(f"{BASE}/periodos/{pid}/iva-declarado", json={"importe": "-1"}).status_code == 422
    r = admin.put(f"{BASE}/periodos/{pid}/iva-declarado", json={"importe": None})
    assert next(x for x in r.json()["comprobaciones"] if x["clave"] == "declaracion")["estado"] == "sin_datos"

    # muestra: todos los proveedores ficticios entran (son menos de 15); se marcan uno por uno
    muestra = por["muestra"]["detalle"]["muestra"]
    assert len(muestra) == 6 and por["muestra"]["estado"] == "revisar"
    assert admin.post(f"{BASE}/periodos/{pid}/muestra/NOEXISTE0101", json={"revisado": True}).status_code == 404
    for m in muestra:
        r = admin.post(f"{BASE}/periodos/{pid}/muestra/{m['rfc']}", json={"revisado": True, "nota": "Cuadra"})
        assert r.status_code == 200
    por = {x["clave"]: x for x in r.json()["comprobaciones"]}
    assert por["muestra"]["estado"] == "ok" and all(m["revisado"] for m in por["muestra"]["detalle"]["muestra"])
    r = admin.post(f"{BASE}/periodos/{pid}/muestra/{muestra[0]['rfc']}", json={"revisado": False})
    assert next(x for x in r.json()["comprobaciones"] if x["clave"] == "muestra")["estado"] == "revisar"


def test_diferencias_contra_lo_presentado_piden_motivo(admin):
    pid = _mes_listo(admin, 4)
    txt = admin.get(f"{BASE}/periodos/{pid}/txt").content.decode("latin-1").split("\r\n")
    campos = txt[0].split("|")
    rfc = campos[2]
    campos[7] = str(int(campos[7] or 0) + 100)  # el presentado trae otra base para el primer proveedor
    txt[0] = "|".join(campos)
    referencia = "\r\n".join(txt).encode("latin-1")
    p = admin.post(f"{BASE}/periodos/{pid}/referencia", files={"archivo": ("presentado.txt", referencia)}).json()
    assert p["comparacion"]["diferencias"]

    c = admin.get(f"{BASE}/periodos/{pid}/comprobaciones").json()
    pres = next(x for x in c["comprobaciones"] if x["clave"] == "presentado")
    assert pres["estado"] == "revisar"
    d = next(x for x in pres["detalle"]["diferencias"] if x["rfc"] == rfc)
    assert d["que"] and d["campos"] and d["motivo"] is None

    assert admin.post(f"{BASE}/periodos/{pid}/diferencias/{rfc}", json={"motivo": "inventado"}).status_code == 422
    assert admin.post(f"{BASE}/periodos/{pid}/diferencias/{rfc}", json={"motivo": "otro"}).status_code == 400
    assert admin.post(f"{BASE}/periodos/{pid}/diferencias/NOEXISTE0101", json={"motivo": "criterio"}).status_code == 404
    r = admin.post(f"{BASE}/periodos/{pid}/diferencias/{rfc}", json={"motivo": "ajuste_fiscal", "nota": "Redondeo"})
    assert r.status_code == 200
    pres = next(x for x in r.json()["comprobaciones"] if x["clave"] == "presentado")
    assert pres["estado"] == "ok"
    assert next(x for x in pres["detalle"]["diferencias"] if x["rfc"] == rfc)["motivo"] == "ajuste_fiscal"


def test_dos_firmas_de_personas_distintas_y_valen_para_ese_txt(admin, monkeypatch):
    pid = _mes_listo(admin, 5)
    c = admin.get(f"{BASE}/periodos/{pid}/comprobaciones").json()
    assert not c["firmas"]["revision"]["firmada"] and not c["firmas_obligatorias"]
    forzado = not c["puede_firmar_revision"]
    if forzado:  # con el auxiliar ficticio puede quedar algo en amarillo o rojo
        assert admin.post(f"{BASE}/periodos/{pid}/firmas", json={"tipo": "revision"}).status_code == 409
        original = validacion.comprobaciones
        monkeypatch.setattr(validacion, "comprobaciones", lambda bd, p: {**original(bd, p), "puede_firmar_revision": True})

    assert admin.post(f"{BASE}/periodos/{pid}/firmas", json={"tipo": "fiscal"}).status_code == 409  # falta la revisión
    r = admin.post(f"{BASE}/periodos/{pid}/firmas", json={"tipo": "revision", "nota": "Todo revisado"})
    assert r.status_code == 200 and r.json()["firmas"]["revision"]["firmada"]
    assert admin.post(f"{BASE}/periodos/{pid}/firmas", json={"tipo": "fiscal"}).status_code == 409  # misma persona

    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    assert consulta.post(f"{BASE}/periodos/{pid}/firmas", json={"tipo": "fiscal"}).status_code == 403
    _, fiscal, _ = alta_usuario(admin, rol="contraloria_fiscal")
    r = fiscal.post(f"{BASE}/periodos/{pid}/firmas", json={"tipo": "fiscal", "nota": "Visto bueno"})
    assert r.status_code == 200, r.text
    f = r.json()["firmas"]
    assert f["revision"]["firmada"] and f["fiscal"]["firmada"] and f["fiscal"]["por"]
    assert r.json()["paso"] == (3 if forzado else 5)  # con todo en verde y las dos firmas, el mes queda listo

    ev = openpyxl.load_workbook(io.BytesIO(admin.get(f"{BASE}/periodos/{pid}/evidencia").content))
    assert ev.sheetnames[0] == "Resumen"
    texto = " ".join(str(v) for fila in ev["Resumen"].iter_rows(values_only=True) for v in fila if v)
    assert "Contabilidad" in texto or "contabilidad" in texto
    assert "Visto bueno" in texto

    # si el TXT cambia al volver a procesar, las firmas ya no valen
    ter = admin.get(f"{BASE}/periodos/{pid}/terceros").json()
    admin.post(f"{BASE}/periodos/{pid}/ajustes",
               json={"rfc": ter[0]["rfc"], "campo": "base16", "importe": "10", "motivo": "Ajuste de prueba"})
    _procesar(admin, pid)
    f = admin.get(f"{BASE}/periodos/{pid}/comprobaciones").json()["firmas"]
    assert not f["revision"]["firmada"] and f["revision"]["anterior_invalida"] and not f["fiscal"]["firmada"]

    # quitar la firma de revisión quita también la de Fiscal
    admin.post(f"{BASE}/periodos/{pid}/firmas", json={"tipo": "revision"})
    fiscal.post(f"{BASE}/periodos/{pid}/firmas", json={"tipo": "fiscal"})
    f = admin.delete(f"{BASE}/periodos/{pid}/firmas/revision").json()["firmas"]
    assert not f["revision"]["firmada"] and not f["fiscal"]["firmada"]


def test_borrar_un_periodo(admin):
    pid = _mes_listo(admin, 6)
    admin.put(f"{BASE}/periodos/{pid}/iva-declarado", json={"importe": "1"})
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    assert consulta.delete(f"{BASE}/periodos/{pid}").status_code == 403
    admin.patch(f"{BASE}/periodos/{pid}", json={"estado": "cerrado"})
    assert admin.delete(f"{BASE}/periodos/{pid}").status_code == 409  # cerrado: primero se reabre
    admin.patch(f"{BASE}/periodos/{pid}", json={"estado": "procesado"})
    assert admin.delete(f"{BASE}/periodos/{pid}").status_code == 204
    assert admin.get(f"{BASE}/periodos/{pid}").status_code == 404
    assert pid not in [x["id"] for x in admin.get(f"{BASE}/periodos").json()]
    # el mismo mes se puede volver a abrir
    odp = next(e for e in admin.get(f"{BASE}/catalogos").json()["empresas"] if e["codigo"] == "ODP")
    assert admin.post(f"{BASE}/periodos", json={"empresa_id": odp["id"], "anio": 2098, "mes": 6}).status_code == 200


def test_tres_empresas_y_el_rfc_se_captura(admin):
    emp = {e["codigo"]: e for e in admin.get(f"{BASE}/catalogos").json()["empresas"]}
    assert {"SMN", "ODP", "PS"} <= set(emp) and emp["ODP"]["rfc"]
    ps = emp["PS"]
    pid = admin.post(f"{BASE}/periodos", json={"empresa_id": ps["id"], "anio": 2097, "mes": 1}).json()["id"]
    if not ps["rfc"]:
        assert admin.post(f"{BASE}/periodos/{pid}/procesar").status_code == 409  # sin RFC no se procesa
    assert admin.patch(f"{BASE}/empresas/{ps['id']}", json={"rfc": "NO-ES-RFC"}).status_code == 422
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    assert consulta.patch(f"{BASE}/empresas/{ps['id']}", json={"rfc": "AAA010101AAA"}).status_code == 403
    r = admin.patch(f"{BASE}/empresas/{ps['id']}", json={"rfc": "AAA010101AAA"})
    assert r.status_code == 200 and r.json()["rfc"] == "AAA010101AAA"


def test_lista_de_tipos_con_nombre_en_vez_de_clave():
    """La lista de Fiscal puede traer «ARRENDAMIENTO» en vez de «06»: se lee con el catálogo; lo que no se reconoce
    no se guarda (antes truncaba a «AR» y tronaba) y queda como incidencia."""
    from modulos.contraloria import diot_criterios as crit
    from modulos.contraloria import diot_motor as motor
    from modulos.contraloria.diot_lectura import Tabla

    cat = crit.TIPOS_OPERACION
    assert [motor._clave_tipo(v, cat) for v in ("6", "06", "Arrendamiento", "SERVICIOS PROFESIONALES", "AR", "XYZW")] \
        == ["06", "06", "06", "03", None, None]
    docs = {"tipos_operacion": Tabla("tipos_operacion", ["RFC", "TIPO DE OPERACIÓN"], [
        {"RFC": "AAA010101AAA", "TIPO DE OPERACIÓN": "ARRENDAMIENTO"},
        {"RFC": "BBB010101BBB", "TIPO DE OPERACIÓN": "HONORARIOS DIVERSOS"}])}
    tipos, no_leidos = motor._tipos_operacion(docs, cat)
    assert tipos == {"AAA010101AAA": "06"} and no_leidos == {"BBB010101BBB": "HONORARIOS DIVERSOS"}


def test_decidir_pendientes_en_bloque(admin):
    odp = next(e for e in admin.get(f"{BASE}/catalogos").json()["empresas"] if e["codigo"] == "ODP")
    pid = admin.post(f"{BASE}/periodos", json={"empresa_id": odp["id"], "anio": 2097, "mes": 2}).json()["id"]
    for _, (nombre, contenido) in documentos().items():
        _subir(admin, pid, nombre, contenido)
    _procesar(admin, pid)
    ids = [i["id"] for i in admin.get(f"{BASE}/periodos/{pid}/incidencias").json() if i["impacto"] == "posible_impacto"]
    assert ids
    url = f"{BASE}/periodos/{pid}/incidencias/lote"
    assert admin.post(url, json={"ids": ids, "estado": "revisada"}).status_code == 400  # sin nota no
    assert admin.post(url, json={"ids": ids + [999999], "estado": "revisada", "nota": "x"}).status_code == 404
    r = admin.post(url, json={"ids": ids, "estado": "pendiente", "nota": "En espera de Fiscal: todas"})
    assert r.status_code == 200 and r.json()["actualizadas"] == len(ids)
    r = admin.post(url, json={"ids": ids, "estado": "revisada", "nota": "Revisadas en bloque"})
    assert r.status_code == 200
    incs = {i["id"]: i for i in admin.get(f"{BASE}/periodos/{pid}/incidencias").json()}
    assert all(incs[i]["estado"] == "revisada" and incs[i]["nota_revision"] == "Revisadas en bloque" for i in ids)
    assert admin.get(f"{BASE}/periodos/{pid}/comprobaciones").json()["pendientes"] == 0
