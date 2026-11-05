"""Comité de producto nuevo: un ciclo completo con datos ficticios (plan aprobado por Diego, 2026-11-04).

Abrir reunión, subir con y sin proveedor actual, evaluar, pre-filtrar, registrar asistentes y peticiones, decidir
(incluido «En espera», que pasa a la siguiente reunión), revisiones después de aceptar y cerrar.
"""
import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from core.bd import motor
from modulos.compras.modelos_comite import ComiteReunion
from tests.conftest import alta_usuario
from tests.test_productos import catalogo_ficticio, sincrono  # noqa: F401  (fixture)
from tests.test_propuestas import PDF, adjuntar, codigo_nuevo, completas, lista_para_enviar

R = "/api/compras/comite"
P = "/api/compras/propuestas"


def cerrar_pendientes() -> None:
    """Una sola reunión sin cerrar a la vez: se cierran las que hayan dejado otras corridas."""
    with Session(motor()) as bd:
        bd.execute(update(ComiteReunion).where(ComiteReunion.estado != "cerrada").values(estado="cerrada"))
        bd.commit()


def proveedor_actual() -> str:
    from datos.modelos import Carga, Proveedor

    clave = f"CM{uuid.uuid4().hex[:6].upper()}"
    with Session(motor()) as bd:
        carga = Carga(fuente="SMNBI_PROVEEDORES", disparada_por="manual", estado="completa")
        bd.add(carga)
        bd.flush()
        bd.add(Proveedor(proveedor=clave, nombre=f"PROVEEDOR COMITE {clave}", estatus="ALTA", agente="AG1",
                         carga_id=carga.carga_id))
        bd.commit()
    return clave


def item_de(reunion: dict, **cual) -> dict:
    return next(i for i in reunion["productos"] if all(i[k] == v for k, v in cual.items()))


def test_ciclo_completo_del_comite(admin: TestClient, sincrono):  # noqa: F811
    cerrar_pendientes()
    depto, _ = catalogo_ficticio()
    _, kiosco, _ = alta_usuario(admin, rol="kiosco_tienda")
    assert kiosco.get(f"{R}/reuniones").status_code == 403
    assert kiosco.post(f"{R}/reuniones", json={"fecha": "2026-11-20"}).status_code == 403

    r = admin.post(f"{R}/reuniones", json={"fecha": "2026-11-20", "notas": "Reunión de prueba"})
    assert r.status_code == 201, r.text
    reunion = r.json()
    rid = reunion["id"]
    assert reunion["estado"] == "abierta"
    assert admin.post(f"{R}/reuniones", json={"fecha": "2026-11-27"}).status_code == 409  # una a la vez

    # Sin proveedor: una idea de Compras con costo estimado
    idea = admin.post("/api/compras/productos/ideas", json={
        "nombre": "Citrato de magnesio en polvo", "marca": "Marca Ficticia", "departamento": depto,
        "ingrediente": "Magnesio", "precio_visto": "150", "costo_estimado": "80"}).json()["sujeto"]["id"]
    reunion = admin.post(f"{R}/reuniones/{rid}/productos", json={"idea_id": idea}).json()
    i_idea = item_de(reunion, tipo="idea", sujeto_id=idea)
    assert i_idea["origen"] == "idea" and not i_idea["proveedor_actual"]
    assert i_idea["evaluacion"]["estado"] == "lista" and i_idea["evaluacion"]["modelo"] == "sin_proveedor"
    assert admin.post(f"{R}/reuniones/{rid}/productos", json={"idea_id": idea}).status_code == 409

    # Del portal, de un proveedor nuevo: llega durante el ciclo y entra sola; Compras la revisa y la manda evaluar
    _, prov, _ = alta_usuario(admin, tipo="externo", rol="proveedor")
    portal = lista_para_enviar(prov)["id"]
    assert prov.post(f"{P}/{portal}/enviar").status_code == 200
    reunion = admin.get(f"{R}/reuniones/{rid}").json()
    i_portal = item_de(reunion, tipo="propuesta", sujeto_id=portal)
    assert i_portal["llego_solo"] and i_portal["evaluacion"] is None and i_portal["estado_sujeto"] == "Recibida"
    assert admin.post(f"{R}/reuniones/{rid}/productos", json={"propuesta_id": portal}).status_code == 409
    reunion = admin.post(f"{R}/productos/{i_portal['id']}/evaluar").json()
    i_portal = item_de(reunion, tipo="propuesta", sujeto_id=portal)
    assert i_portal["origen"] == "propuesta" and i_portal["estado_sujeto"] == "Lista para evaluar"
    assert i_portal["evaluacion"]["estado"] == "lista" and i_portal["evaluacion"]["modelo"] == "sin_proveedor"
    assert i_portal["fotos"] == 2 and i_portal["precio"] is not None

    # Con proveedor actual: Compras lo captura desde el comité; se evalúa en cuanto se envía
    clave = proveedor_actual()
    captura = admin.post(f"{P}/captura", json={"proveedor_codigo": clave}).json()["id"]
    reunion = admin.post(f"{R}/reuniones/{rid}/productos", json={"propuesta_id": captura}).json()
    i_cap = item_de(reunion, tipo="propuesta", sujeto_id=captura)
    assert i_cap["origen"] == "captura" and i_cap["proveedor_actual"]
    assert i_cap["falta"] == "Falta terminar y enviar la captura." and i_cap["evaluacion"] is None
    assert admin.post(f"{R}/productos/{i_cap['id']}/evaluar").status_code == 409
    respuestas = completas(codigo_nuevo())
    respuestas["aviso"] = {}
    assert admin.put(f"{P}/{captura}", json={"respuestas": respuestas}).status_code == 200
    for tipo, etiqueta in (("imagen_producto", "Frente"), ("imagen_producto", "Reverso"),
                           ("imagen_etiquetado", "Tabla nutrimental"), ("imagen_etiquetado", "Ingredientes")):
        adjuntar(admin, captura, tipo, etiqueta)
    adjuntar(admin, captura, "ficha_tecnica", contenido=PDF, nombre="ficha.pdf")
    assert admin.post(f"{P}/{captura}/enviar").status_code == 200
    reunion = admin.get(f"{R}/reuniones/{rid}").json()
    i_cap = item_de(reunion, tipo="propuesta", sujeto_id=captura)
    assert i_cap["falta"] is None and i_cap["evaluacion"]["estado"] == "lista"
    assert i_cap["evaluacion"]["modelo"] == "con_proveedor"
    assert reunion["embudo"]["subidos"] == 3 and reunion["embudo"]["evaluados"] == 3
    assert admin.get(f"{R}/productos/{i_cap['id']}/fotos/0").status_code == 200
    assert admin.get(f"{R}/productos/{i_cap['id']}/fotos/9").status_code == 404

    # Pre-filtro: no antes de tiempo; al empezarlo ya no se suben productos
    cuerpo = {"resultado": "pasa", "motivo": "Buen margen", "criterios": [{"criterio": "Gusto del empaque", "valor": "bien"}]}
    assert admin.put(f"{R}/productos/{i_idea['id']}/prefiltro", json=cuerpo).status_code == 409
    assert admin.post(f"{R}/reuniones/{rid}/estado", json={"estado": "comite"}).status_code == 409
    assert admin.post(f"{R}/reuniones/{rid}/estado", json={"estado": "prefiltro"}).json()["estado"] == "prefiltro"
    otra = admin.post("/api/compras/productos/ideas", json={"nombre": "Otra idea de prueba"}).json()["sujeto"]["id"]
    assert admin.post(f"{R}/reuniones/{rid}/productos", json={"idea_id": otra}).status_code == 409
    assert admin.put(f"{R}/productos/{i_idea['id']}/prefiltro", json={**cuerpo, "motivo": " "}).status_code == 400
    reunion = admin.put(f"{R}/productos/{i_idea['id']}/prefiltro", json=cuerpo).json()
    assert item_de(reunion, id=i_idea["id"])["prefiltro_color"] == i_idea["evaluacion"]["color"]
    admin.put(f"{R}/productos/{i_portal['id']}/prefiltro", json={"resultado": "no_pasa", "motivo": "No va con el surtido"})
    admin.put(f"{R}/productos/{i_cap['id']}/prefiltro", json={"resultado": "pasa", "motivo": "Proveedor confiable"})
    assert "Gusto del empaque" in admin.get(f"{R}/criterios").json()["usados"]

    # Comité: asistentes con su puesto y peticiones
    assert admin.put(f"{R}/productos/{i_cap['id']}/decision", json={"decision": "aceptado", "motivo": "x"}).status_code == 409
    assert admin.post(f"{R}/reuniones/{rid}/estado", json={"estado": "comite"}).json()["estado"] == "comite"
    yo = admin.get("/api/auth/yo").json()["usuario"]["id"]
    reunion = admin.post(f"{R}/reuniones/{rid}/asistentes", json={"usuario_id": yo, "puesto": "Dirección de Compras"}).json()
    assert admin.post(f"{R}/reuniones/{rid}/asistentes", json={"usuario_id": yo}).status_code == 409
    reunion = admin.post(f"{R}/reuniones/{rid}/asistentes", json={"nombre": "Invitada externa", "puesto": "Regulación"}).json()
    assert [a["puesto"] for a in reunion["asistentes"]] == ["Dirección de Compras", "Regulación"]
    quien = reunion["asistentes"][1]["id"]
    reunion = admin.post(f"{R}/reuniones/{rid}/peticiones",
                         json={"texto": "Traer una muestra", "item_id": i_cap["id"], "asistente_id": quien}).json()
    peticion = reunion["peticiones"][0]
    assert peticion["asistente"] == "Invitada externa" and peticion["puesto"] == "Regulación" and peticion["estado"] == "abierta"

    # Lo que llega del portal ya en comité no entra a esta reunión: se considera en la siguiente
    tarde = lista_para_enviar(prov)["id"]
    assert prov.post(f"{P}/{tarde}/enviar").status_code == 200
    assert all(i["sujeto_id"] != tarde for i in admin.get(f"{R}/reuniones/{rid}").json()["productos"] if i["tipo"] == "propuesta")

    # Decisiones: solo sobre lo que pasó el pre-filtro; siempre con motivo
    assert admin.put(f"{R}/productos/{i_portal['id']}/decision", json={"decision": "aceptado", "motivo": "x"}).status_code == 409
    assert admin.post(f"{R}/reuniones/{rid}/estado", json={"estado": "cerrada"}).status_code == 409  # faltan decisiones
    reunion = admin.put(f"{R}/productos/{i_cap['id']}/decision", json={"decision": "aceptado", "motivo": "Se alinea al surtido"}).json()
    assert item_de(reunion, id=i_cap["id"])["decision_color"] == i_cap["evaluacion"]["color"]
    assert admin.post(f"{R}/reuniones/{rid}/estado", json={"estado": "prefiltro"}).status_code == 409  # ya hay decisiones
    admin.put(f"{R}/productos/{i_idea['id']}/decision", json={"decision": "en_espera", "motivo": "Ver en el siguiente ciclo"})
    reunion = admin.post(f"{R}/reuniones/{rid}/estado", json={"estado": "cerrada"}).json()
    assert reunion["estado"] == "cerrada" and reunion["cerrada_por"]
    assert reunion["embudo"] == {"subidos": 3, "evaluados": 3, "pasan": 2, "no_pasan": 1, "aceptados": 1, "denegados": 0,
                                 "en_espera": 1}

    # Cerrada: solo lectura, salvo «Qué aprendimos», las revisiones posteriores y las peticiones
    assert admin.patch(f"{R}/reuniones/{rid}", json={"fecha": "2026-11-21"}).status_code == 409
    assert admin.patch(f"{R}/reuniones/{rid}", json={"aprendizajes": "Pedir fotos del empaque"}).json()["aprendizajes"]
    assert admin.put(f"{R}/productos/{i_idea['id']}/revisiones/inventario", json={"resultado": "pendiente"}).status_code == 409
    admin.put(f"{R}/productos/{i_cap['id']}/revisiones/inventario", json={"resultado": "pendiente"})
    pendientes = admin.get("/api/nucleo/inicio").json()
    assert any(p["clave"] == "comite_revisiones" for p in pendientes["pendientes"])
    assert any(p["clave"] == "comite_peticiones" for p in pendientes["pendientes"])
    reunion = admin.put(f"{R}/productos/{i_cap['id']}/revisiones/regulacion", json={"resultado": "aprobada", "nota": "OK"}).json()
    assert [(x["tipo"], x["resultado"]) for x in item_de(reunion, id=i_cap["id"])["revisiones"]] == [
        ("inventario", "pendiente"), ("regulacion", "aprobada")]
    assert any(a["producto"]["id"] == i_cap["id"] for a in admin.get(f"{R}/aceptados").json())
    atendida = admin.patch(f"{R}/peticiones/{peticion['id']}", json={"estado": "atendida", "respuesta": "Llegó la muestra"}).json()
    assert atendida["estado"] == "atendida" and atendida["atendida_por"]
    assert all(p["id"] != peticion["id"] for p in admin.get(f"{R}/peticiones", params={"estado": "abierta"}).json())

    # Lo que quedó «En espera» entra solo a la siguiente reunión, ya pre-filtrado
    nueva = admin.post(f"{R}/reuniones", json={"fecha": str(date(2026, 12, 4))}).json()
    llevado = item_de(nueva, tipo="idea", sujeto_id=idea)
    assert llevado["origen"] == "espera" and llevado["prefiltro"] == "pasa" and llevado["viene_de_fecha"] == "2026-11-20"
    llegada = item_de(nueva, tipo="propuesta", sujeto_id=tarde)
    assert llegada["llego_solo"] and llegada["origen"] == "propuesta" and llegada["prefiltro"] is None
    assert len(nueva["productos"]) == 2
    cerrar_pendientes()
    # Y no se vuelve a llevar
    otra_mas = admin.post(f"{R}/reuniones", json={"fecha": "2026-12-11"}).json()
    assert otra_mas["productos"] == []
    cerrar_pendientes()


def test_captura_rapida_con_proveedor(admin: TestClient, sincrono):  # noqa: F811
    """Diego (2026-11-04): en este ciclo Compras sube productos con proveedor usando el cuestionario corto."""
    cerrar_pendientes()
    depto, _ = catalogo_ficticio()
    rid = admin.post(f"{R}/reuniones", json={"fecha": "2026-11-21"}).json()["id"]
    base = {"nombre": "Magnesio quelado en polvo", "departamento": depto, "ingrediente": "Magnesio",
            "precio_visto": "150", "costo_estimado": "80"}
    I = "/api/compras/productos/ideas"

    # El proveedor tiene que existir en Intelisis con agente; no se mandan los dos a la vez
    assert admin.post(I, json={**base, "proveedor_codigo": "NO-EXISTE"}).status_code == 400
    clave = proveedor_actual()
    assert admin.post(I, json={**base, "proveedor_codigo": clave, "proveedor_nuevo": "Otro"}).status_code == 400

    # Proveedor de Intelisis: se evalúa con el modelo «con proveedor» y el comité lo muestra como proveedor actual
    e = admin.post(I, json={**base, "proveedor_codigo": clave}).json()
    reunion = admin.post(f"{R}/reuniones/{rid}/productos", json={"idea_id": e["sujeto"]["id"]}).json()
    i = item_de(reunion, tipo="idea", sujeto_id=e["sujeto"]["id"])
    assert i["proveedor_actual"] and i["proveedor"] == f"PROVEEDOR COMITE {clave}"
    assert i["evaluacion"]["estado"] == "lista" and i["evaluacion"]["modelo"] == "con_proveedor"
    det = admin.get(f"/api/compras/productos/evaluaciones/{e['id']}").json()
    f_prov = next(f for f in det["factores"] if f["factor"] == "proveedor")
    assert clave in (f_prov["detalle"] or "") + (f_prov["valor"] or "") or "PROVEEDOR COMITE" in (f_prov["detalle"] or "")

    # Proveedor nuevo: queda anotado pero se evalúa como sin proveedor
    e2 = admin.post(I, json={**base, "nombre": "Té de moringa", "proveedor_nuevo": "Distribuidora Ficticia"}).json()
    reunion = admin.post(f"{R}/reuniones/{rid}/productos", json={"idea_id": e2["sujeto"]["id"]}).json()
    i2 = item_de(reunion, tipo="idea", sujeto_id=e2["sujeto"]["id"])
    assert not i2["proveedor_actual"] and i2["proveedor"] == "Distribuidora Ficticia"
    assert i2["evaluacion"]["modelo"] == "sin_proveedor"
    cerrar_pendientes()
