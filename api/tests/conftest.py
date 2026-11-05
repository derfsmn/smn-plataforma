"""Pruebas contra un SQL Server real, en una base aparte (smn_td_pruebas) que se crea sola.

Si no hay SQL Server disponible, las pruebas que lo necesitan se omiten.
"""
import os
import uuid

os.environ["BD_NOMBRE"] = "smn_td_pruebas"
os.environ.setdefault("API_ENTORNO", "desarrollo")
os.environ["SMTP_SERVIDOR"] = ""  # las pruebas atrapan los correos sin enviarlos
os.environ["ARCHIVOS_RUTA"] = os.path.join(os.path.dirname(__file__), "..", ".pruebas-archivos")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["IA_TIPO_CAMBIO_MXN"] = ""
os.environ["OLLAMA_MODELO"] = ""
os.environ["PROGRAMADOR_ACTIVO"] = "false"
os.environ["OPENAI_API_KEY"] = ""
os.environ["RADAR_PRODUCTOS_BUSCAR_MERCADO"] = "false"  # las pruebas que lo usan ponen tiendas ficticias

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from core.bd import bd_disponible, motor  # noqa: E402
from core.config import configuracion  # noqa: E402

ADMIN = {"correo": "admin-pruebas@ejemplo.mx", "contrasena": "Admin-Pruebas-2026"}


@pytest.fixture(scope="session")
def base_de_pruebas():
    cfg = configuracion()
    try:
        maestro = create_engine(cfg.url_bd("master"), isolation_level="AUTOCOMMIT")
        with maestro.connect() as c:
            c.execute(text(f"IF DB_ID('{cfg.bd_nombre}') IS NOT NULL BEGIN "
                           f"ALTER DATABASE [{cfg.bd_nombre}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
                           f"DROP DATABASE [{cfg.bd_nombre}] END"))
            c.execute(text(f"CREATE DATABASE [{cfg.bd_nombre}]"))
    except Exception:
        pytest.skip("SQL Server no disponible")
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini")), "head")
    from scripts.crear_admin import crear
    from scripts.semilla import sembrar

    with Session(motor()) as bd:
        sembrar(bd)
        crear(bd, "Admin de pruebas", ADMIN["correo"], ADMIN["contrasena"])
    assert bd_disponible()
    yield


@pytest.fixture
def cliente(base_de_pruebas):
    from main import app

    return TestClient(app)


@pytest.fixture
def admin(base_de_pruebas):
    from main import app

    c = TestClient(app)
    assert c.post("/api/auth/iniciar", json=ADMIN).status_code == 200
    return c


def correo_nuevo() -> str:
    return f"p-{uuid.uuid4().hex[:10]}@ejemplo.mx"


def alta_usuario(admin: TestClient, tipo: str = "interno", rol: str = "compras_consulta", contrasena="Clave-Segura-123"):
    """Invita y acepta; devuelve (correo, cliente con sesión iniciada, id)."""
    from main import app

    correo = correo_nuevo()
    datos = {"tipo": tipo, "nombre": "Persona de prueba", "correo": correo, "rol": rol}
    if tipo == "externo":
        datos["empresa"] = "Proveedor de Prueba S.A."
    r = admin.post("/api/nucleo/usuarios/invitar", json=datos)
    assert r.status_code == 201, r.text
    token = r.json()["liga"].rsplit("/", 1)[1]
    c = TestClient(app)
    r = c.post(f"/api/auth/invitacion/{token}", json={"contrasena": contrasena, "acepta_aviso_privacidad": True})
    assert r.status_code == 200, r.text
    return correo, c, r.json()["usuario"]["id"]
