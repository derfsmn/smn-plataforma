"""Correo, notificaciones, archivos, bitácora y puerta de IA (sin llamar a ninguna IA real)."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from core.config import configuracion
from tests.conftest import ADMIN, alta_usuario, correo_nuevo


@pytest.fixture
def buzon(monkeypatch):
    """Atrapa los correos en una lista en vez de enviarlos."""
    enviados = []

    def falso(para, asunto, titulo, parrafos, boton=None, nota=None):
        enviados.append({"para": para, "asunto": asunto, "boton": boton})
        return True

    monkeypatch.setattr("nucleo.notificaciones.enviar", falso)
    return enviados


# ---------------------------------------------------------------- correo y notificaciones

def test_invitacion_llega_por_correo_y_avisa_al_aceptar(admin: TestClient, cliente: TestClient, buzon):
    correo = correo_nuevo()
    r = admin.post("/api/nucleo/usuarios/invitar",
                   json={"tipo": "interno", "nombre": "Persona Correo", "correo": correo, "rol": "compras_consulta"})
    assert r.status_code == 201 and r.json()["correo_enviado"] is True
    assert buzon[-1]["para"] == correo and buzon[-1]["boton"][1] == r.json()["liga"]

    antes = admin.get("/api/notificaciones").json()["no_leidas"]
    token = r.json()["liga"].rsplit("/", 1)[1]
    assert cliente.post(f"/api/auth/invitacion/{token}", json={"contrasena": "Clave-Segura-123"}).status_code == 200
    bandeja = admin.get("/api/notificaciones").json()
    assert bandeja["no_leidas"] == antes + 1
    assert bandeja["notificaciones"][0]["titulo"] == "Invitación aceptada"

    assert admin.post(f"/api/notificaciones/{bandeja['notificaciones'][0]['id']}/leer").status_code == 204
    assert admin.get("/api/notificaciones").json()["no_leidas"] == antes
    # Nadie marca como leída la notificación de otro
    assert cliente.post(f"/api/notificaciones/{bandeja['notificaciones'][0]['id']}/leer").status_code == 404


def test_recuperacion_y_cambio_de_contrasena_por_correo(admin: TestClient, cliente: TestClient, buzon):
    correo, sesion, _ = alta_usuario(admin)
    assert cliente.post("/api/auth/recuperar", json={"correo": correo}).status_code == 200
    assert buzon[-1]["asunto"] == "Recupera tu contraseña"
    token = buzon[-1]["boton"][1].rsplit("/", 1)[1]
    assert cliente.post(f"/api/auth/restablecer/{token}", json={"contrasena": "Otra-Clave-456"}).status_code == 200
    assert buzon[-1]["asunto"] == "Tu contraseña cambió"
    # Correo que no existe: misma respuesta y ningún correo
    total = len(buzon)
    assert cliente.post("/api/auth/recuperar", json={"correo": correo_nuevo()}).status_code == 200
    assert len(buzon) == total

    assert cliente.post("/api/auth/iniciar", json={"correo": correo, "contrasena": "Otra-Clave-456"}).status_code == 200
    avisos = cliente.get("/api/notificaciones").json()["notificaciones"]
    assert any(n["titulo"] == "Tu contraseña cambió" for n in avisos)


def test_sin_smtp_la_liga_se_comparte_a_mano(admin: TestClient):
    r = admin.post("/api/nucleo/usuarios/invitar",
                   json={"tipo": "interno", "nombre": "Sin Correo", "correo": correo_nuevo(), "rol": "compras_consulta"})
    assert r.status_code == 201 and r.json()["correo_enviado"] is False


# ---------------------------------------------------------------- archivos

def test_subir_y_descargar_archivo(admin: TestClient):
    _, otro, _ = alta_usuario(admin)
    pdf = b"%PDF-1.4\n% prueba\n"
    r = otro.post("/api/archivos", files={"archivo": ("ficha técnica.pdf", pdf, "application/pdf")},
                  data={"modulo": "compras", "entidad": "solicitud", "entidad_id": "1"})
    assert r.status_code == 201, r.text
    datos = r.json()
    assert datos["nombre"] == "ficha técnica.pdf" and datos["tamano_bytes"] == len(pdf)
    assert otro.get(f"/api/archivos/{datos['id']}").content == pdf
    assert any(a["id"] == datos["id"] for a in otro.get("/api/archivos/mios").json())
    # El admin de usuarios lo puede ver; otra persona no
    assert admin.get(f"/api/archivos/{datos['id']}").status_code == 200
    _, tercero, _ = alta_usuario(admin)
    assert tercero.get(f"/api/archivos/{datos['id']}").status_code == 404


def test_archivo_rechazado_por_tipo_contenido_o_tamano(admin: TestClient, monkeypatch):
    assert admin.post("/api/archivos", files={"archivo": ("virus.exe", b"MZ", "application/octet-stream")}).status_code == 400
    assert admin.post("/api/archivos", files={"archivo": ("falso.pdf", b"no soy pdf", "application/pdf")}).status_code == 400
    monkeypatch.setattr(configuracion(), "archivos_mb_maximo", 1)
    grande = b"%PDF" + b"0" * (1024 * 1024 + 10)
    assert admin.post("/api/archivos", files={"archivo": ("grande.pdf", grande, "application/pdf")}).status_code == 413


# ---------------------------------------------------------------- bitácora

def test_bitacora_solo_con_permiso(admin: TestClient):
    r = admin.get("/api/nucleo/bitacora", params={"accion": "login"})
    assert r.status_code == 200
    assert r.json()["total"] >= 1 and all(x["accion"] == "login" for x in r.json()["renglones"])
    assert "login" in admin.get("/api/nucleo/bitacora/acciones").json()
    _, consulta, _ = alta_usuario(admin)
    assert consulta.get("/api/nucleo/bitacora").status_code == 403


# ---------------------------------------------------------------- puerta de IA

def _respuesta_api(**extra):
    return {"texto": "Hola desde la API", "modelo": "claude-opus-5-5", "tokens_entrada": 1000, "tokens_salida": 500,
            "completa": True, "rechazo": False, "detalle": None, **extra}


@pytest.fixture
def api_encendida(admin: TestClient, monkeypatch):
    cfg = configuracion()
    monkeypatch.setattr(cfg, "anthropic_api_key", "llave-de-prueba")
    monkeypatch.setattr(cfg, "ia_tipo_cambio_mxn", 20.0)
    llamadas = []

    def falsa(modelo, instrucciones, mensaje, max_tokens, esfuerzo, *resto):
        llamadas.append(modelo)
        return _respuesta_api()

    monkeypatch.setattr("ia.puerta._llamar_api", falsa)
    yield llamadas
    admin.put("/api/ia/topes", json=[])


def test_api_externa_apagada_sin_llave_tipo_de_cambio_ni_tope(admin: TestClient):
    estado = admin.get("/api/ia/estado").json()
    assert estado["api_encendida"] is False and len(estado["api_motivos"]) == 3
    r = admin.post("/api/ia/probar", json={"mensaje": "hola", "proveedor": "api"})
    assert r.status_code == 502 and "apagada" in r.json()["detail"]


def test_llamada_externa_registra_costo_y_respeta_el_tope(admin: TestClient, api_encendida):
    # Costo esperado: (1000 × 4 + 500 × 20) / 1e6 USD = 0.014 USD × 20 = 0.28 MXN.
    # El tope es lo ya gastado en el mes (por otras pruebas) más 0.50.
    previo = Decimal(admin.get("/api/ia/estado").json()["gastos"][0]["gastado_mxn"])
    assert admin.put("/api/ia/topes", json=[{"alcance": "plataforma", "tope_mxn": str(previo + Decimal("0.50"))}]).status_code == 200
    assert admin.get("/api/ia/estado").json()["api_encendida"] is True

    r = admin.post("/api/ia/probar", json={"mensaje": "hola", "proveedor": "api"})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["costo_mxn"]) == Decimal("0.28")
    # 0.28 de 0.50 = 56 %: sin aviso todavía. La segunda llamada pasa (gasto 0.28 < 0.50) y llega a 112 %
    assert admin.post("/api/ia/probar", json={"mensaje": "hola", "proveedor": "api"}).status_code == 200
    avisos = [n["titulo"] for n in admin.get("/api/notificaciones").json()["notificaciones"]]
    assert "Se alcanzó un tope de IA" in avisos

    r = admin.post("/api/ia/probar", json={"mensaje": "hola", "proveedor": "api"})
    assert r.status_code == 409 and "tope" in r.json()["detail"]
    assert len(api_encendida) == 2  # la tercera ni siquiera salió
    resultados = [l["resultado"] for l in admin.get("/api/ia/llamadas").json()[:3]]
    assert resultados == ["rechazada_por_tope", "ok", "ok"]
    # El aviso del tope no se repite
    admin.post("/api/ia/probar", json={"mensaje": "hola", "proveedor": "api"})
    avisos = [n["titulo"] for n in admin.get("/api/notificaciones").json()["notificaciones"]]
    assert avisos.count("Se alcanzó un tope de IA") == 1


def test_al_superar_tope_puede_pasar_a_ollama(admin: TestClient, api_encendida, monkeypatch):
    monkeypatch.setattr(configuracion(), "ollama_modelo", "modelo-local")
    monkeypatch.setattr("ia.puerta._llamar_ollama", lambda modelo, i, m, t: {
        "texto": "Hola desde Ollama", "modelo": modelo, "tokens_entrada": 10, "tokens_salida": 5,
        "completa": True, "rechazo": False, "detalle": None})
    admin.put("/api/ia/topes", json=[{"alcance": "plataforma", "tope_mxn": "0", "al_superar": "usar_ollama"}])
    r = admin.post("/api/ia/probar", json={"mensaje": "hola", "proveedor": "api"})
    assert r.status_code == 200 and r.json()["proveedor"] == "ollama" and Decimal(r.json()["costo_mxn"]) == 0
    assert api_encendida == []


def test_rechazo_del_modelo(admin: TestClient, api_encendida, monkeypatch):
    admin.put("/api/ia/topes", json=[{"alcance": "plataforma", "tope_mxn": "100"}])
    monkeypatch.setattr("ia.puerta._llamar_api", lambda *a: _respuesta_api(texto="", rechazo=True))
    r = admin.post("/api/ia/probar", json={"mensaje": "hola", "proveedor": "api"})
    assert r.status_code == 502 and "no quiso" in r.json()["detail"]
    assert admin.get("/api/ia/llamadas").json()[0]["resultado"] == "rechazada_por_modelo"


def test_tope_diario_por_persona(admin: TestClient, api_encendida):
    admin.put("/api/ia/topes", json=[{"alcance": "plataforma", "tope_mxn": "100"},
                                     {"alcance": "usuario_dia", "tope_mxn": "0.20"}])
    _, otro_admin, _ = alta_usuario(admin, rol="admin")  # sin gasto previo hoy
    assert otro_admin.post("/api/ia/probar", json={"mensaje": "hola", "proveedor": "api"}).status_code == 200
    assert otro_admin.post("/api/ia/probar", json={"mensaje": "hola", "proveedor": "api"}).status_code == 409


def test_ia_solo_para_quien_la_administra(admin: TestClient):
    _, consulta, _ = alta_usuario(admin)
    assert consulta.get("/api/ia/estado").status_code == 403
    assert consulta.post("/api/ia/probar", json={"mensaje": "hola", "proveedor": "ollama"}).status_code == 403


# ---------------------------------------------------------------- configuración

def test_configuracion_desde_la_pantalla(admin: TestClient, buzon):
    cfg = configuracion()
    grupos = admin.get("/api/nucleo/configuracion").json()
    claves = {a["clave"]: a for g in grupos for a in g["ajustes"]}
    assert "smtp_servidor" in claves and "mssql_sa_password" not in claves
    assert claves["anthropic_api_key"]["valor"] is None

    try:
        r = admin.put("/api/nucleo/configuracion", json={"cambios": {
            "archivos_mb_maximo": "5", "smtp_tls": True, "anthropic_api_key": "sk-prueba-1234567890-abcd"}})
        assert r.status_code == 200, r.text
        claves = {a["clave"]: a for g in r.json() for a in g["ajustes"]}
        assert claves["archivos_mb_maximo"]["valor"] == 5 and claves["archivos_mb_maximo"]["origen"] == "pantalla"
        assert claves["anthropic_api_key"]["valor"] is None and claves["anthropic_api_key"]["pista"] == "abcd"
        assert cfg.archivos_mb_maximo == 5 and cfg.smtp_tls is True and cfg.anthropic_api_key == "sk-prueba-1234567890-abcd"

        # El secreto queda cifrado en la base y fuera de la bitácora
        from sqlalchemy.orm import Session
        from core.bd import motor
        from nucleo.modelos import ConfiguracionAjuste
        with Session(motor()) as bd:
            assert "sk-prueba" not in bd.get(ConfiguracionAjuste, "anthropic_api_key").valor
        ultima = admin.get("/api/nucleo/bitacora", params={"buscar": "anthropic_api_key"}).json()["renglones"][0]
        assert "sk-prueba" not in str(ultima["detalle"])

        assert admin.put("/api/nucleo/configuracion", json={"cambios": {"sesion_horas": 99}}).status_code == 400
        assert admin.put("/api/nucleo/configuracion", json={"cambios": {"web_url": "sin-protocolo"}}).status_code == 400
        assert admin.put("/api/nucleo/configuracion", json={"cambios": {"bd_servidor": "otro"}}).status_code == 400
    finally:
        # Volver al .env
        r = admin.put("/api/nucleo/configuracion", json={"cambios": {
            "archivos_mb_maximo": None, "smtp_tls": None, "anthropic_api_key": None}})
        assert r.status_code == 200
    assert cfg.archivos_mb_maximo == 10 and cfg.smtp_tls is False and cfg.anthropic_api_key == ""

    _, consulta, _ = alta_usuario(admin)
    assert consulta.get("/api/nucleo/configuracion").status_code == 403


def test_probar_correo(admin: TestClient, monkeypatch):
    assert admin.post("/api/nucleo/configuracion/probar-correo").json()["enviado"] is False
    monkeypatch.setattr(configuracion(), "smtp_servidor", "correo")
    monkeypatch.setattr("nucleo.configuracion.enviar", lambda *a, **k: True)
    r = admin.post("/api/nucleo/configuracion/probar-correo").json()
    assert r["enviado"] is True and ADMIN["correo"] in r["mensaje"]
