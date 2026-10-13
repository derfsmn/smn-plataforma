from fastapi.testclient import TestClient

from tests.conftest import ADMIN, alta_usuario, correo_nuevo


def test_inicio_de_sesion_y_yo(cliente: TestClient):
    assert cliente.get("/api/auth/yo").status_code == 401
    assert cliente.post("/api/auth/iniciar", json={**ADMIN, "contrasena": "equivocada-123"}).status_code == 401
    r = cliente.post("/api/auth/iniciar", json=ADMIN)
    assert r.status_code == 200
    assert "smn_td_sesion" in r.cookies
    yo = cliente.get("/api/auth/yo").json()
    assert "nucleo.usuarios.administrar" in yo["permisos"]
    assert {m["codigo"] for m in yo["modulos"]} >= {"compras", "rrhh"}
    cliente.post("/api/auth/salir")
    assert cliente.get("/api/auth/yo").status_code == 401


def test_correo_inexistente_da_el_mismo_mensaje(cliente: TestClient):
    a = cliente.post("/api/auth/iniciar", json={"correo": correo_nuevo(), "contrasena": "x" * 12})
    b = cliente.post("/api/auth/iniciar", json={**ADMIN, "contrasena": "x" * 12})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_bloqueo_tras_cinco_intentos(admin: TestClient, cliente: TestClient):
    correo, _, _ = alta_usuario(admin)
    for _ in range(5):
        assert cliente.post("/api/auth/iniciar", json={"correo": correo, "contrasena": "mala-clave-123"}).status_code == 401
    r = cliente.post("/api/auth/iniciar", json={"correo": correo, "contrasena": "Clave-Segura-123"})
    assert r.status_code == 423


def test_invitacion_de_proveedor(admin: TestClient, cliente: TestClient):
    correo = correo_nuevo()
    r = admin.post("/api/nucleo/usuarios/invitar", json={
        "tipo": "externo", "nombre": "Contacto", "correo": correo, "rol": "proveedor", "empresa": "Prov S.A.", "rfc": "AAA010101AAA",
    })
    assert r.status_code == 201
    assert r.json()["usuario"]["estatus"] == "invitado"
    token = r.json()["liga"].rsplit("/", 1)[1]
    assert cliente.get(f"/api/auth/invitacion/{token}").json()["empresa"] == "Prov S.A."
    # sin aceptar el aviso de privacidad no entra; contraseña corta tampoco
    assert cliente.post(f"/api/auth/invitacion/{token}", json={"contrasena": "Clave-Segura-123"}).status_code == 400
    assert cliente.post(f"/api/auth/invitacion/{token}", json={"contrasena": "corta", "acepta_aviso_privacidad": True}).status_code == 400
    r = cliente.post(f"/api/auth/invitacion/{token}", json={"contrasena": "Clave-Segura-123", "acepta_aviso_privacidad": True})
    assert r.status_code == 200
    assert r.json()["usuario"]["tipo"] == "externo"
    assert r.json()["modulos"] == []
    # la liga es de un solo uso y el proveedor no administra
    assert cliente.get(f"/api/auth/invitacion/{token}").status_code == 404
    assert cliente.get("/api/nucleo/usuarios").status_code == 403


def test_correo_repetido_y_rol_de_otro_tipo(admin: TestClient):
    r = admin.post("/api/nucleo/usuarios/invitar", json={"tipo": "interno", "nombre": "Xavier", "correo": ADMIN["correo"], "rol": "compras_consulta"})
    assert r.status_code == 409
    r = admin.post("/api/nucleo/usuarios/invitar", json={"tipo": "interno", "nombre": "Xavier", "correo": correo_nuevo(), "rol": "proveedor"})
    assert r.status_code == 400


def test_liga_de_contrasena_generada_por_admin(admin: TestClient, cliente: TestClient):
    correo, sesion_vieja, uid = alta_usuario(admin)
    liga = admin.post(f"/api/nucleo/usuarios/{uid}/liga-contrasena").json()["liga"]
    token = liga.rsplit("/", 1)[1]
    assert cliente.post(f"/api/auth/restablecer/{token}", json={"contrasena": "Otra-Clave-Nueva-1"}).status_code == 200
    assert cliente.post(f"/api/auth/restablecer/{token}", json={"contrasena": "Otra-Clave-Nueva-2"}).status_code == 404
    assert sesion_vieja.get("/api/auth/yo").status_code == 401  # se cierran sus sesiones
    assert cliente.post("/api/auth/iniciar", json={"correo": correo, "contrasena": "Clave-Segura-123"}).status_code == 401
    assert cliente.post("/api/auth/iniciar", json={"correo": correo, "contrasena": "Otra-Clave-Nueva-1"}).status_code == 200


def test_recuperar_siempre_responde_igual(cliente: TestClient):
    a = cliente.post("/api/auth/recuperar", json={"correo": ADMIN["correo"]})
    b = cliente.post("/api/auth/recuperar", json={"correo": correo_nuevo()})
    assert a.status_code == b.status_code == 200 and a.json() == b.json()


def test_cambiar_contrasena(admin: TestClient):
    correo, c, _ = alta_usuario(admin)
    assert c.post("/api/auth/cambiar-contrasena", json={"actual": "mal-12345678", "nueva": "Nueva-Clave-2026"}).status_code == 400
    assert c.post("/api/auth/cambiar-contrasena", json={"actual": "Clave-Segura-123", "nueva": "corta"}).status_code == 400
    assert c.post("/api/auth/cambiar-contrasena", json={"actual": "Clave-Segura-123", "nueva": "Nueva-Clave-2026"}).status_code == 200
    assert c.get("/api/auth/yo").status_code == 200


def test_desactivar_cierra_sesion_y_protecciones_del_admin(admin: TestClient):
    _, c, uid = alta_usuario(admin)
    assert admin.patch(f"/api/nucleo/usuarios/{uid}", json={"estatus": "inactivo"}).json()["estatus"] == "inactivo"
    assert c.get("/api/auth/yo").status_code == 401
    yo = admin.get("/api/auth/yo").json()["usuario"]["id"]
    assert admin.patch(f"/api/nucleo/usuarios/{yo}", json={"estatus": "inactivo"}).status_code == 400
    assert admin.patch(f"/api/nucleo/usuarios/{yo}", json={"roles": ["compras_consulta"]}).status_code == 400


def test_permisos_de_roles_y_modulos_visibles(admin: TestClient):
    _, c, _ = alta_usuario(admin, rol="compras_consulta")
    assert c.get("/api/auth/yo").json()["modulos"] == []  # compras está en diseño
    assert admin.patch("/api/nucleo/modulos/compras", json={"estado": "piloto"}).status_code == 200
    assert [m["codigo"] for m in c.get("/api/auth/yo").json()["modulos"]] == ["compras"]
    admin.patch("/api/nucleo/modulos/compras", json={"estado": "en_diseno"})

    r = admin.put("/api/nucleo/roles/admin/permisos", json={"permisos": ["nucleo.modulos.administrar"]})
    assert r.status_code == 400
    r = admin.put("/api/nucleo/roles/compras_consulta/permisos", json={"permisos": ["compras.solicitud.ver", "compras.comite.decidir"]})
    assert r.status_code == 200 and "compras.comite.decidir" in r.json()["permisos"]
    assert "compras.comite.decidir" in c.get("/api/auth/yo").json()["permisos"]
    admin.put("/api/nucleo/roles/compras_consulta/permisos", json={"permisos": ["compras.solicitud.ver"]})
    assert c.get("/api/nucleo/usuarios").status_code == 403
    assert c.put("/api/nucleo/roles/compras_consulta/permisos", json={"permisos": []}).status_code == 403
