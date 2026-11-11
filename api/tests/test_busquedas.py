"""Búsqueda de proveedor (pedido de Diego, 2026-11-09): lo bien evaluado sin proveedor les llega a quienes buscan
proveedores, lo toman, registran contactos y lo cierran con o sin proveedor. Datos ficticios."""
from fastapi.testclient import TestClient

from tests.conftest import alta_usuario
from tests.test_comite import proveedor_actual
from tests.test_productos import catalogo_ficticio, sincrono  # noqa: F401  (fixture)

R = "/api/compras/busquedas"
P = "/api/compras/productos"


def idea_nueva(admin: TestClient, depto: str, nombre: str) -> tuple[int, int]:
    r = admin.post(f"{P}/ideas", json={"nombre": nombre, "marca": "Marca Ficticia", "departamento": depto,
                                       "ingrediente": "Magnesio", "precio_visto": "150"})
    assert r.status_code == 201, r.text
    return r.json()["sujeto"]["id"], r.json()["id"]


def avisos(c: TestClient) -> list[dict]:
    return c.get("/api/notificaciones").json()["notificaciones"]


def test_de_verde_a_proveedor_encontrado(admin: TestClient, sincrono):  # noqa: F811
    depto, _ = catalogo_ficticio()
    _, buscador, buscador_id = alta_usuario(admin, rol="compras_responsable")
    # Otras pruebas cambian los permisos de este rol: se dejan como los pone la semilla
    assert admin.put("/api/nucleo/roles/compras_consulta/permisos", json={"permisos": [
        "compras.productos.ver", "compras.busquedas.ver", "compras.comite.ver"]}).status_code == 200
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    _, kiosco, _ = alta_usuario(admin, rol="kiosco_tienda")
    idea, ev = idea_nueva(admin, depto, "Magnesio en gomitas ficticio")
    assert kiosco.get(R).status_code == 403

    # Compras lo deja en verde: como no tiene proveedor, se abre sola la búsqueda y le llega a quien busca proveedores
    r = admin.post(f"{P}/evaluaciones/{ev}/color", json={"color": "verde", "motivo": "Lo pidió el comité de prueba"})
    assert r.status_code == 200, r.text
    b = admin.get(f"{R}/idea/{idea}").json()
    assert b and b["estado"] == "sin_tomar" and b["origen"] == "automatica" and b["color"] == "verde"
    assert b["puertas"] == ["captura"]  # la capturó Compras, no vino de «Buscar oportunidades»
    bid = b["id"]
    aviso = next(a for a in avisos(buscador) if a["liga"] == f"/compras/propuestas/busquedas/{bid}")
    assert "Magnesio en gomitas ficticio" in aviso["titulo"]
    assert not any(a["liga"] == f"/compras/propuestas/busquedas/{bid}" for a in avisos(consulta))  # solo ve
    pend = {p["clave"]: p for p in buscador.get("/api/nucleo/inicio").json()["pendientes"]}
    assert pend["busquedas_sin_tomar"]["cantidad"] >= 1
    # Volver a ponerlo verde no abre otra
    admin.post(f"{P}/evaluaciones/{ev}/color", json={"color": "amarillo", "motivo": "Lo revisamos de nuevo hoy"})
    admin.post(f"{P}/evaluaciones/{ev}/color", json={"color": "verde", "motivo": "Lo revisamos de nuevo hoy"})
    assert admin.get(f"{R}/idea/{idea}").json()["id"] == bid
    assert admin.get(f"{P}/evaluaciones/{ev}").json()["sujeto"]["estado"] == "buscar_proveedor"

    lista = buscador.get(R).json()
    assert any(x["id"] == bid for x in lista["busquedas"]) and "verde" in lista["colores_automaticos"]
    assert consulta.get(f"{R}/{bid}").status_code == 200
    assert consulta.post(f"{R}/{bid}/tomar").status_code == 403

    # Registrar un contacto la toma; luego otro contacto
    r = buscador.post(f"{R}/{bid}/avances", json={"texto": "Le marqué", "resultado": "interesado"})
    assert r.status_code == 400  # falta a quién
    d = buscador.post(f"{R}/{bid}/avances", json={"texto": "Le marqué y pidió la ficha", "proveedor": "Distribuidora Uno",
                                                    "resultado": "interesado"}).json()
    assert d["estado"] == "buscando" and d["responsable"]["id"] == buscador_id and d["contactos"] == 1
    d = buscador.post(f"{R}/{bid}/avances", json={"texto": "No lo maneja", "proveedor": "Distribuidora Dos",
                                                    "resultado": "no_surte"}).json()
    assert d["contactos"] == 2 and d["avances"][0]["resultado_texto"] == "No lo surte"

    # Encontrado con un proveedor de Intelisis y su costo: la idea se vuelve a evaluar con él
    clave = proveedor_actual()
    assert buscador.post(f"{R}/{bid}/encontrado", json={"proveedor_codigo": clave, "proveedor_nuevo": "Otro"}).status_code == 400
    assert buscador.post(f"{R}/{bid}/encontrado", json={"proveedor_codigo": "NOEXISTE"}).status_code == 400
    d = buscador.post(f"{R}/{bid}/encontrado", json={"proveedor_codigo": clave, "costo": "70",
                                                      "nota": "Entrega en 10 días"}).json()
    assert d["estado"] == "encontrado" and clave in d["proveedor"] and d["costo"] == "70.00"
    assert d["semaforo"]["estado"] == "lista" and d["semaforo"]["modelo"] == "con_proveedor"
    assert d["semaforo"]["evaluacion_id"] != ev
    nueva = admin.get(f"{P}/evaluaciones/{d['semaforo']['evaluacion_id']}").json()
    rent = next(f for f in nueva["factores"] if f["factor"] == "rentabilidad")
    assert rent["puntaje"] is not None
    assert nueva["sujeto"]["estado"] == "nueva"
    assert buscador.post(f"{R}/{bid}/avances", json={"texto": "Algo más", "proveedor": "X"}).status_code == 409
    assert buscador.post(f"{R}/{bid}/reabrir").status_code == 409
    assert admin.post(R, json={"idea_id": idea}).status_code == 409  # ya tiene proveedor


def test_a_mano_sin_proveedor_y_descartar(admin: TestClient, sincrono):  # noqa: F811
    depto, _ = catalogo_ficticio()
    _, buscador, _ = alta_usuario(admin, rol="compras_responsable")
    idea, ev = idea_nueva(admin, depto, "Cloruro de magnesio ficticio")
    b = admin.get(f"{R}/idea/{idea}").json()
    if b:  # el semáforo la pudo sacar verde sola; se cancela para probar la vía a mano
        admin.post(f"{R}/{b['id']}/cerrar", json={"estado": "cancelada", "motivo": "Prueba de la vía a mano"})
    d = admin.post(R, json={"idea_id": idea, "nota": "Nos interesa aunque salga amarillo"})
    assert d.status_code == 201, d.text
    d = d.json()
    assert d["origen"] == "compras" and d["nota"] == "Nos interesa aunque salga amarillo"
    assert admin.post(R, json={"idea_id": idea}).json()["id"] == d["id"]  # no duplica
    bid = d["id"]
    assert buscador.post(f"{R}/{bid}/tomar").json()["estado"] == "buscando"
    assert buscador.post(f"{R}/{bid}/cerrar", json={"estado": "sin_proveedor", "motivo": "corto"}).status_code == 400
    d = buscador.post(f"{R}/{bid}/cerrar", json={"estado": "sin_proveedor",
                                                  "motivo": "Ningún distribuidor lo trae a México"}).json()
    assert d["estado"] == "sin_proveedor" and d["cerrada_en"]
    assert admin.get(f"{P}/evaluaciones/{ev}").json()["sujeto"]["estado"] == "vigilar"
    assert any(x["id"] == bid for x in buscador.get(f"{R}?vista=cerradas").json()["busquedas"])
    d = buscador.post(f"{R}/{bid}/reabrir").json()
    assert d["estado"] == "buscando" and d["motivo_cierre"] is None

    # Descartar la idea en el radar cancela su búsqueda abierta; marcarla «Buscar proveedor» la vuelve a abrir
    assert admin.patch(f"{P}/ideas/{idea}/estado", json={"estado": "descartada"}).status_code == 200
    assert admin.get(f"{R}/{bid}").json()["estado"] == "cancelada"
    assert admin.post(R, json={"idea_id": idea}).status_code == 409
    assert admin.patch(f"{P}/ideas/{idea}/estado", json={"estado": "buscar_proveedor"}).status_code == 200
    otra = admin.get(f"{R}/idea/{idea}").json()
    assert otra["id"] != bid and otra["estado"] == "sin_tomar" and otra["origen"] == "compras"
