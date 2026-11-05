"""Propuestas de productos nuevos: reglas del cuestionario, portal del proveedor, bandeja de Compras e invitaciones."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.bd import motor
from datos.modelos import Producto
from modulos.compras import propuestas as pr
from tests.conftest import alta_usuario, correo_nuevo

R = "/api/compras/propuestas"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
PDF = b"%PDF-1.4 ficticio de pruebas"


def ean13(base12: str) -> str:
    suma = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(base12))
    return base12 + str((10 - suma % 10) % 10)


def codigo_nuevo() -> str:
    return ean13("750" + str(uuid.uuid4().int)[:9])


def completas(codigo: str) -> dict:
    """Respuestas que cumplen todo el cuestionario (datos ficticios de prueba)."""
    return {
        "aviso": {"acepta_aviso_privacidad": True, "declara_veracidad": True},
        "proveedor": {
            "marca": "Marca Ficticia", "razon_social": "Proveedor de Prueba S.A.", "rfc": "PPR010101AB1",
            "es_proveedor_smn": "no", "publico_objetivo": ["general"], "inscrito_gs1": "no", "cuenta_registro_marca": "no",
            "contacto_nombre": "Persona Ficticia", "contacto_cargo": "Ventas", "contacto_correo": "ventas@ejemplo.mx",
            "contacto_telefono": "55 1234 5678", "contacto_alterno_nombre": "Otra Persona",
            "contacto_alterno_telefono": "5598765432", "contacto_alterno_correo": "otra@ejemplo.mx",
        },
        "general": {"fabricante": "Fábrica Ficticia", "pais_origen": "México", "diferenciador": "Precio",
                    "necesidad_atendida": "Ampliar variedad", "departamento": "Suplementos"},
        "presentaciones": [{
            "codigo_barras": codigo, "registro_sanitario": "123ABC", "forma": "Cápsula", "ingrediente_principal": "Magnesio",
            "descripcion": "Magnesio 60 cápsulas", "contenido_neto": "60", "unidad_medida": "piezas", "piezas_caja_master": "24",
            "costo_neto_sin_iva": "50", "pvp_sugerido": "116", "tasa_iva": "16", "tasa_ieps": "0",
        }],
        "mercado": {"canal_actual": "no_se_comercializa", "sin_comparables": True, "similares_en_smn": "no"},
        "logistica": {"manejo_especial": ["no_requiere"], "vida_util_total_dias": "730", "vida_util_minima_dias": "365"},
        "lanzamiento": {"apoyos": [{"tipo": "muestras", "detalle": "200 muestras"}], "argumento_principal": "Precio competitivo",
                        "sustento": "Dato ficticio de prueba"},
    }


def subir(c: TestClient, nombre: str, contenido: bytes) -> int:
    r = c.post("/api/archivos", files={"archivo": (nombre, contenido)}, data={"modulo": "compras", "entidad": "propuesta"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def adjuntar(c: TestClient, pid: int, tipo: str, etiqueta: str | None = None, contenido: bytes = PNG, nombre: str = "foto.png"):
    r = c.post(f"{R}/{pid}/adjuntos", json={"archivo_id": subir(c, nombre, contenido), "tipo": tipo, "etiqueta": etiqueta})
    assert r.status_code == 201, r.text
    return r.json()


def lista_para_enviar(c: TestClient, codigo: str | None = None) -> dict:
    p = c.post(R).json()
    pid = p["id"]
    assert c.put(f"{R}/{pid}", json={"respuestas": completas(codigo or codigo_nuevo())}).status_code == 200
    adjuntar(c, pid, "imagen_producto", "Frente")
    adjuntar(c, pid, "imagen_producto", "Reverso")
    adjuntar(c, pid, "imagen_etiquetado", "Tabla nutrimental")
    adjuntar(c, pid, "imagen_etiquetado", "Ingredientes")
    return adjuntar(c, pid, "ficha_tecnica", contenido=PDF, nombre="ficha.pdf")


def permisos_de_compras(admin: TestClient) -> None:
    """Otras pruebas cambian los permisos de estos roles; aquí se dejan como los da el catálogo."""
    for rol, permisos in (("compras_consulta", ["compras.solicitud.ver", "compras.propuestas.ver"]),
                          ("compras_comite", ["compras.solicitud.ver", "compras.propuestas.ver", "compras.proveedores.invitar"])):
        assert admin.put(f"/api/nucleo/roles/{rol}/permisos", json={"permisos": permisos}).status_code == 200


# ---------------------------------------------------------------- reglas

def test_codigo_de_barras_y_margen():
    assert pr.codigo_valido("7501055300075") and not pr.codigo_valido("7501055300076")
    assert not pr.codigo_valido("12345") and pr.codigo_valido(ean13("750100000001"))
    # 116 con IVA 16 % son 100 sin impuestos; con costo 50 el margen es 50 %
    assert pr.margen(pr.Presentacion(costo_neto_sin_iva="50", pvp_sugerido="116", tasa_iva="16", tasa_ieps="0")) == 50
    # El IEPS va antes del IVA: 100 × 1.08 × 1.16 = 125.28
    assert pr.margen(pr.Presentacion(costo_neto_sin_iva="80", pvp_sugerido="125.28", tasa_iva="16", tasa_ieps="8")) == 20
    assert pr.margen(pr.Presentacion(costo_neto_sin_iva="50")) is None


def test_normalizar_y_rfc():
    r = pr.Respuestas.model_validate({
        "proveedor": {"rfc": " abc-010203 xy9 ", "contacto_correo": " Ventas@Ejemplo.MX ", "contacto_telefono": "(55) 1234-5678",
                      "razon_social": "  Naturales   Ficticios  "},
        "presentaciones": [{"codigo_barras": "750 1055 300075", "costo_neto_sin_iva": "$1,250.50", "registro_sanitario": " 123abc ",
                            "tasa_ieps": "8 %"}],
        "logistica": {"vida_util_total_dias": "1,095"},
    })
    pr.normalizar(r)
    assert (r.proveedor.rfc, r.proveedor.contacto_correo, r.proveedor.contacto_telefono, r.proveedor.razon_social) == (
        "ABC010203XY9", "ventas@ejemplo.mx", "5512345678", "Naturales Ficticios")
    x = r.presentaciones[0]
    assert (x.codigo_barras, x.costo_neto_sin_iva, x.registro_sanitario, x.tasa_ieps) == ("7501055300075", "1250.50", "123ABC", "8")
    assert r.logistica.vida_util_total_dias == "1095"
    assert pr.rfc_valido("ABC010203XY9") and pr.rfc_valido("ABCD010203XY9")
    assert not pr.rfc_valido("ABC011303XY9") and not pr.rfc_valido("ABC010200XY9")


def test_reglas_del_cuestionario():
    r = pr.Respuestas.model_validate(completas(ean13("750100000001")))
    adjuntos = [("imagen_producto", "Frente"), ("imagen_producto", "Reverso"), ("imagen_etiquetado", "Otra"),
                ("imagen_etiquetado", "Otra"), ("ficha_tecnica", None)]
    assert pr.faltantes(r, adjuntos) == []
    campos = lambda r, a=adjuntos: {f.campo for f in pr.faltantes(r, a)}  # noqa: E731

    # Vida útil (ajuste aprobado): la mínima no pasa de la total, o «No aplica»
    r.logistica.vida_util_minima_dias = "800"
    assert "logistica.vida_util_minima_dias" in campos(r)
    r.logistica.vida_util_minima_no_aplica = True
    assert "logistica.vida_util_minima_dias" not in campos(r)

    # Código de barras por presentación, con dígito verificador y sin repetirse
    r.presentaciones.append(r.presentaciones[0].model_copy())
    assert "presentaciones.1.codigo_barras" in campos(r)
    r.presentaciones[1].codigo_barras = "7501000000012"
    assert "presentaciones.1.codigo_barras" in campos(r)

    # Condicionales: carta GS1, comercios y «Otro»
    r = pr.Respuestas.model_validate(completas(ean13("750100000001")))
    r.proveedor.inscrito_gs1 = "si"
    r.mercado.canal_actual = "ambos"
    r.general.pais_origen = "Otro"
    assert {"adjunto.carta_gs1", "mercado.comercios_actuales", "general.pais_origen_otro"} <= campos(r)
    # Las fotos del producto necesitan Frente y Reverso
    assert "adjunto.imagen_producto" in campos(r, [("imagen_producto", "Frente"), ("imagen_producto", "Otra")])


# ---------------------------------------------------------------- flujo completo

def test_proveedor_envia_y_compras_revisa(admin: TestClient):
    permisos_de_compras(admin)
    _, prov, _ = alta_usuario(admin, tipo="externo", rol="proveedor")
    _, otro, _ = alta_usuario(admin, tipo="externo", rol="proveedor")
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")

    p = prov.post(R).json()
    pid = p["id"]
    assert p["estado"] == "borrador" and p["folio"] is None and p["editable"]
    assert p["respuestas"]["proveedor"]["razon_social"] == "Proveedor de Prueba S.A."  # sale de la invitación
    assert p["faltantes"] and prov.post(f"{R}/{pid}/enviar").status_code == 400
    assert prov.put(f"{R}/{pid}", json={"respuestas": {"general": {"fabricante": "X"}}}).json()["respuestas"]["general"]["fabricante"] == "X"
    prov.delete(f"{R}/{pid}")

    p = lista_para_enviar(prov)
    pid = p["id"]
    assert p["faltantes"] == [], p["faltantes"]
    # Otro proveedor y Compras no ven un borrador
    assert otro.get(f"{R}/{pid}").status_code == 404 and admin.get(f"{R}/{pid}").status_code == 404

    p = prov.post(f"{R}/{pid}/enviar").json()
    assert p["estado"] == "recibida" and p["folio"].startswith("PN-") and not p["editable"]
    folio = p["folio"]
    assert prov.put(f"{R}/{pid}", json={"respuestas": completas(codigo_nuevo())}).status_code == 409
    assert prov.delete(f"{R}/{pid}").status_code == 409
    assert [x["folio"] for x in prov.get(f"{R}/mias").json()] == [folio]
    assert otro.get(f"{R}/mias").json() == []

    # Bandeja de Compras: consulta ve, pero no decide
    assert folio in [x["folio"] for x in consulta.get(R).json()["propuestas"]]
    detalle = consulta.get(f"{R}/{pid}").json()
    assert any("margen de 50.00 %" in x["texto"] for x in detalle["revisiones"])
    assert consulta.post(f"{R}/{pid}/estado", json={"estado": "lista"}).status_code == 403
    assert prov.get(R).status_code == 403
    # Los archivos los abre Compras y el proveedor dueño; nadie más
    adjunto = detalle["adjuntos"][0]["id"]
    assert consulta.get(f"{R}/{pid}/adjuntos/{adjunto}").status_code == 200
    assert otro.get(f"{R}/{pid}/adjuntos/{adjunto}").status_code == 404

    # Regresar al proveedor pide motivo; él corrige y reenvía con el mismo folio
    assert admin.post(f"{R}/{pid}/estado", json={"estado": "devuelta"}).status_code == 400
    p = admin.post(f"{R}/{pid}/estado", json={"estado": "devuelta", "comentario": "Falta la tabla nutrimental legible"}).json()
    assert p["estado"] == "devuelta"
    vista = prov.get(f"{R}/{pid}").json()
    assert vista["editable"] and vista["comentario"] == "Falta la tabla nutrimental legible"
    assert vista["revisiones"] == []  # las revisiones automáticas son de Compras
    assert prov.post(f"{R}/{pid}/enviar").json()["folio"] == folio
    assert admin.post(f"{R}/{pid}/estado", json={"estado": "lista"}).json()["estado"] == "lista"
    eventos = admin.get(f"{R}/{pid}").json()["eventos"]
    assert [e["estado_despues"] for e in eventos] == ["recibida", "devuelta", "recibida", "lista"]
    assert admin.post(f"{R}/{pid}/estado", json={"estado": "lista"}).status_code == 409
    avisos = prov.get("/api/notificaciones").json()["notificaciones"]
    assert any(folio in n["mensaje"] for n in avisos)


def test_datos_del_proveedor_una_sola_vez_y_duplicar(admin: TestClient):
    _, prov, _ = alta_usuario(admin, tipo="externo", rol="proveedor")
    p = lista_para_enviar(prov)
    adjuntar(prov, p["id"], "documento_adicional", contenido=PDF, nombre="ventas.pdf")
    prov.put(f"{R}/{p['id']}", json={"respuestas": {**completas(codigo_nuevo()),
                                                    "proveedor": {**completas("")["proveedor"], "inscrito_gs1": "si"}}})
    adjuntar(prov, p["id"], "carta_gs1", contenido=PDF, nombre="gs1.pdf")
    # Un documento único se reemplaza en vez de acumularse
    adjuntar(prov, p["id"], "carta_gs1", contenido=PDF, nombre="gs1-nueva.pdf")
    assert [a["nombre"] for a in prov.get(f"{R}/{p['id']}").json()["adjuntos"] if a["tipo"] == "carta_gs1"] == ["gs1-nueva.pdf"]

    nueva = prov.post(R).json()
    assert nueva["respuestas"]["proveedor"]["marca"] == "Marca Ficticia"
    assert [a["tipo"] for a in nueva["adjuntos"]] == ["carta_gs1"]  # las fotos son de otro producto
    copia = prov.post(f"{R}/{p['id']}/duplicar").json()
    assert copia["respuestas"]["general"]["fabricante"] == "Fábrica Ficticia"
    assert copia["respuestas"]["aviso"]["acepta_aviso_privacidad"] is False
    assert {a["tipo"] for a in copia["adjuntos"]} == {"carta_gs1"}


def test_adjuntos_validan_formato_y_dueno(admin: TestClient):
    _, prov, _ = alta_usuario(admin, tipo="externo", rol="proveedor")
    _, otro, _ = alta_usuario(admin, tipo="externo", rol="proveedor")
    pid = prov.post(R).json()["id"]
    pdf = subir(prov, "ficha.pdf", PDF)
    assert prov.post(f"{R}/{pid}/adjuntos", json={"archivo_id": pdf, "tipo": "imagen_producto"}).status_code == 400
    assert prov.post(f"{R}/{pid}/adjuntos", json={"archivo_id": subir(prov, "f.png", PNG), "tipo": "ficha_tecnica"}).status_code == 400
    assert prov.post(f"{R}/{pid}/adjuntos", json={"archivo_id": pdf, "tipo": "inventado"}).status_code == 400
    # Un archivo de otra persona no se puede ligar
    assert prov.post(f"{R}/{pid}/adjuntos", json={"archivo_id": subir(otro, "f.png", PNG), "tipo": "imagen_producto"}).status_code == 404
    foto = adjuntar(prov, pid, "imagen_producto")["adjuntos"][0]
    assert foto["etiqueta"] == "Otra"
    assert prov.patch(f"{R}/{pid}/adjuntos/{foto['id']}", json={"etiqueta": "Frente"}).json()["adjuntos"][0]["etiqueta"] == "Frente"
    assert prov.patch(f"{R}/{pid}/adjuntos/{foto['id']}", json={"etiqueta": "Inventada"}).status_code == 400
    assert prov.delete(f"{R}/{pid}/adjuntos/{foto['id']}").json()["adjuntos"] == []


def test_revisiones_automaticas_codigo_en_catalogo_y_repetido(admin: TestClient):
    codigo = codigo_nuevo()
    sku = f"PRUEBA-{uuid.uuid4().hex[:8]}"
    with Session(motor()) as bd:
        bd.add(Producto(sku=sku, descripcion="Producto ficticio de pruebas", codigo_barras=codigo, origen="API"))
        bd.commit()
    try:
        _, prov, _ = alta_usuario(admin, tipo="externo", rol="proveedor")
        a = prov.post(f"{R}/{lista_para_enviar(prov, codigo)['id']}/enviar").json()
        b = prov.post(f"{R}/{lista_para_enviar(prov, codigo)['id']}/enviar").json()
        textos = [x["texto"] for x in admin.get(f"{R}/{b['id']}").json()["revisiones"]]
        assert any(sku in t for t in textos) and any(a["folio"] in t for t in textos)
        assert admin.get(f"{R}/{b['id']}").json()["filas"][0]["ya_en_catalogo"] is True
        assert admin.get(R, params={"q": b["folio"]}).json()["propuestas"][0]["alertas"] >= 2
    finally:
        with Session(motor()) as bd:
            bd.execute(delete(Producto).where(Producto.sku == sku))
            bd.commit()


def test_invitar_proveedor_desde_compras(admin: TestClient):
    permisos_de_compras(admin)
    _, comite, _ = alta_usuario(admin, rol="compras_comite")
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    datos = {"nombre": "Proveedora Ficticia", "correo": correo_nuevo(), "empresa": "Empresa Ficticia S.A.", "rfc": "EFI010101AA1"}
    assert consulta.post("/api/compras/proveedores/invitar", json=datos).status_code == 403
    assert comite.post("/api/compras/proveedores/invitar", json={**datos, "rfc": "MAL"}).status_code == 400
    r = comite.post("/api/compras/proveedores/invitar", json=datos)
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["proveedor"]["estatus"] == "invitado" and "/invitacion/" in inv["liga"]
    assert comite.post("/api/compras/proveedores/invitar", json=datos).status_code == 409
    assert inv["proveedor"]["correo"] in [p["correo"] for p in consulta.get("/api/compras/proveedores").json()]
    reenvio = comite.post(f"/api/compras/proveedores/{inv['proveedor']['id']}/reenviar")
    assert reenvio.status_code == 200

    # Con la liga crea su contraseña y ya puede proponer
    from main import app

    nuevo = TestClient(app)
    token = reenvio.json()["liga"].rsplit("/", 1)[1]  # la liga nueva anula la anterior
    assert nuevo.post(f"/api/auth/invitacion/{token}", json={"contrasena": "Clave-Segura-123", "acepta_aviso_privacidad": True}).status_code == 200
    p = nuevo.post(R).json()
    assert p["respuestas"]["proveedor"]["rfc"] == "EFI010101AA1"
    # Un interno no puede crear propuestas
    assert comite.post(R).status_code == 403


def test_compras_captura_con_proveedor_actual_o_nuevo(admin: TestClient):
    """Diego, 2026-11-03: el producto nuevo puede venir de un proveedor actual o de uno nuevo, todavía sin contactos."""
    from datos.modelos import Carga, Proveedor

    clave = f"PT{uuid.uuid4().hex[:6].upper()}"
    with Session(motor()) as bd:
        carga = Carga(fuente="SMNBI_PROVEEDORES", disparada_por="manual", estado="completa")
        bd.add(carga)
        bd.flush()
        bd.add(Proveedor(proveedor=clave, nombre=f"PROVEEDOR ACTUAL {clave}", estatus="ALTA", agente="AG1",
                         carga_id=carga.carga_id))
        bd.add(Proveedor(proveedor=f"{clave}X", nombre=None, estatus=None, agente="AG2",  # en Intelisis hay claves sin nombre
                         carga_id=carga.carga_id))
        bd.add(Proveedor(proveedor=f"{clave}S", nombre="SIN AGENTE", estatus="ALTA", agente=None, carga_id=carga.carga_id))
        bd.commit()
    # Solo aparecen los que tienen agente (Diego, 2026-11-03)
    encontrados = admin.get("/api/compras/proveedores/intelisis", params={"q": clave}).json()
    assert [x["codigo"] for x in encontrados] == [clave, f"{clave}X"]  # los que no tienen nombre van al final
    assert encontrados[1]["nombre"] == f"Proveedor {clave}X"
    assert admin.post(f"{R}/captura", json={"proveedor_codigo": f"{clave}X"}).status_code == 201
    assert admin.post(f"{R}/captura", json={"proveedor_codigo": f"{clave}S"}).status_code == 400

    # Proveedor actual: queda ligado a su clave de Intelisis y marcado como proveedor de SMN
    p = admin.post(f"{R}/captura", json={"proveedor_codigo": clave})
    assert p.status_code == 201, p.text
    p = p.json()
    assert p["capturada_por_compras"] and p["editable"] and p["empresa"] == f"PROVEEDOR ACTUAL {clave}"
    assert p["respuestas"]["proveedor"]["es_proveedor_smn"] == "si"
    # Sin contactos, sin RFC y sin aviso de privacidad se puede enviar
    respuestas = completas(codigo_nuevo())
    respuestas["aviso"] = {}
    respuestas["proveedor"].update({k: None for k in respuestas["proveedor"] if k.startswith("contacto")}, rfc=None)
    pid = p["id"]
    assert admin.put(f"{R}/{pid}", json={"respuestas": respuestas}).status_code == 200
    for tipo, etiqueta in (("imagen_producto", "Frente"), ("imagen_producto", "Reverso"),
                           ("imagen_etiquetado", "Tabla nutrimental"), ("imagen_etiquetado", "Ingredientes")):
        adjuntar(admin, pid, tipo, etiqueta)
    p = adjuntar(admin, pid, "ficha_tecnica", contenido=PDF, nombre="ficha.pdf")
    assert p["faltantes"] == [], p["faltantes"]
    assert any(x["id"] == pid for x in admin.get(R, params={"estado": "borrador"}).json()["propuestas"])
    p = admin.post(f"{R}/{pid}/enviar").json()
    assert p["estado"] == "recibida" and p["folio"].startswith("PN-")
    # Un correo mal escrito sí se marca aunque sea opcional
    otra = admin.post(f"{R}/{pid}/duplicar").json()
    respuestas["proveedor"]["contacto_correo"] = "no-es-correo"
    otra = admin.put(f"{R}/{otra['id']}", json={"respuestas": respuestas}).json()
    assert any(f["campo"] == "proveedor.contacto_correo" for f in otra["faltantes"])
    assert admin.delete(f"{R}/{otra['id']}").status_code == 204
    # La misma clave reusa la empresa
    again = admin.post(f"{R}/captura", json={"proveedor_codigo": clave}).json()
    assert again["empresa"] == p["empresa"]
    admin.delete(f"{R}/{again['id']}")

    # Proveedor nuevo: razón social y RFC opcional
    assert admin.post(f"{R}/captura", json={"nombre": "X"}).status_code == 400
    assert admin.post(f"{R}/captura", json={"nombre": "Nuevo Ficticio", "rfc": "MAL"}).status_code == 400
    nuevo = admin.post(f"{R}/captura", json={"nombre": f"Proveedor Nuevo {clave}"}).json()
    assert nuevo["respuestas"]["proveedor"]["es_proveedor_smn"] == "no" and nuevo["respuestas"]["proveedor"]["rfc"] is None
    assert admin.post(f"{R}/captura", json={"proveedor_codigo": "NO-EXISTE"}).status_code == 404

    # Compras no edita lo que capturó un proveedor en el portal
    _, prov, _ = alta_usuario(admin, tipo="externo", rol="proveedor")
    del_portal = prov.post(f"{lista_para_enviar(prov)['id']}/enviar".join([f"{R}/", ""])).json()
    assert admin.put(f"{R}/{del_portal['id']}", json={"respuestas": completas(codigo_nuevo())}).status_code in (403, 409)
    # Quien solo consulta no captura
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    assert consulta.post(f"{R}/captura", json={"nombre": "Otro Ficticio"}).status_code == 403
