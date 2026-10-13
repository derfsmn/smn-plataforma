from fastapi.testclient import TestClient

from main import app


def test_salud_responde_aunque_no_haya_base():
    respuesta = TestClient(app).get("/api/salud")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["api"] == "ok"
    assert datos["base_de_datos"] in {"ok", "sin conexión"}
