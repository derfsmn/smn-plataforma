"""Revisión de seguridad 2026-11-22: límites de intentos (M3, B7), llave de cifrado (A2), texto protegido (A3),
costos en el buscador (B1), resumen para proveedores (B6) y sitios públicos (B2)."""
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core import ajustes, cifrado
from core.bd import motor
from core.config import configuracion
from nucleo.modelos import RestablecimientoContrasena, Usuario
from tests.conftest import ADMIN, alta_usuario, correo_nuevo
from tests.test_innovacion import equipo, fuente, ia  # noqa: F401  (fixtures)


# ---------------------------------------------------------------- M3 / B7 · límites

def test_bloqueo_igual_exista_o_no_la_cuenta(cliente: TestClient, admin: TestClient):
    real, _, _ = alta_usuario(admin)
    inventado = correo_nuevo()
    for correo in (real, inventado):
        for _ in range(5):
            assert cliente.post("/api/auth/iniciar", json={"correo": correo, "contrasena": "mala-clave-123"}).status_code == 401
    a = cliente.post("/api/auth/iniciar", json={"correo": real, "contrasena": "Clave-Segura-123"})
    b = cliente.post("/api/auth/iniciar", json={"correo": inventado, "contrasena": "Clave-Segura-123"})
    assert a.status_code == b.status_code == 423 and a.json() == b.json()


def test_limite_de_fallas_por_ip(cliente: TestClient):
    from nucleo.autenticacion import FALLAS_POR_IP

    for _ in range(FALLAS_POR_IP):
        r = cliente.post("/api/auth/iniciar", json={"correo": correo_nuevo(), "contrasena": "mala-clave-123"})
        assert r.status_code == 401
    r = cliente.post("/api/auth/iniciar", json=ADMIN)  # ni con la contraseña correcta, desde ese equipo
    assert r.status_code == 429 and r.headers["retry-after"]


def test_recuperar_con_tope_por_correo_y_por_ip(cliente: TestClient):
    from nucleo.autenticacion import RECUPERAR_POR_CORREO, RECUPERAR_POR_IP

    respuestas = {cliente.post("/api/auth/recuperar", json={"correo": ADMIN["correo"]}).json()["mensaje"] for _ in range(5)}
    assert len(respuestas) == 1  # siempre la misma respuesta
    with Session(motor()) as bd:
        uid = bd.scalar(select(Usuario.usuario_id).where(Usuario.correo == ADMIN["correo"]))
        ligas = bd.scalars(select(RestablecimientoContrasena).where(RestablecimientoContrasena.usuario_id == uid)
                           .order_by(RestablecimientoContrasena.restablecimiento_id.desc()).limit(10)).all()
        recientes = [x for x in ligas if x.solicitado_desde_ip == "testclient"]
    assert len(recientes) >= RECUPERAR_POR_CORREO
    from core import limites
    assert limites.excedido("recuperar_correo", ADMIN["correo"], RECUPERAR_POR_CORREO, 3600)
    for _ in range(RECUPERAR_POR_IP - 5):
        assert cliente.post("/api/auth/recuperar", json={"correo": correo_nuevo()}).status_code == 200
    assert cliente.post("/api/auth/recuperar", json={"correo": correo_nuevo()}).status_code == 429


# ---------------------------------------------------------------- A3 · texto protegido

def test_texto_de_fuentes_cifrado_en_la_base(fuente):
    with Session(motor()) as bd:
        crudos = bd.execute(text("SELECT texto FROM innovacion.fragmento WHERE version_id = :v"),
                            {"v": fuente.version_id}).scalars().all()
    assert crudos and all(t.startswith("cif1:") for t in crudos)
    assert not any("bisglicinato" in t for t in crudos)


# ---------------------------------------------------------------- A2 · rotar la llave

def test_rotar_llave_sin_perder_nada(admin: TestClient, fuente):
    from scripts import rotar_llave

    r = admin.put("/api/nucleo/configuracion", json={"cambios": {"smtp_contrasena": "secreto-de-prueba-123"}})
    assert r.status_code == 200, r.text
    with Session(motor()) as bd:  # un texto viejo, guardado antes de cifrarse
        bd.execute(text("UPDATE innovacion.fragmento SET texto = N'texto viejo sin cifrar' WHERE fragmento_id = "
                        "(SELECT MIN(fragmento_id) FROM innovacion.fragmento WHERE version_id = :v)"), {"v": fuente.version_id})
        bd.commit()
    cfg = configuracion()
    assert not cifrado.usa_llave_propia()
    assert rotar_llave.main(["--aplicar"]) == 2  # sin CLAVE_CIFRADO no hace nada
    cfg.clave_cifrado = "llave-nueva-de-prueba-0123456789"
    try:
        # con la llave nueva puesta, lo viejo se sigue leyendo
        assert ajustes.descifrar(Session(motor()).scalar(text(
            "SELECT valor FROM nucleo.configuracion WHERE clave = 'smtp_contrasena'"))) == "secreto-de-prueba-123"
        rotar_llave.main(["--aplicar"])
        with Session(motor()) as bd:
            despues = rotar_llave.revisar(bd, False)
            assert all(c.pendientes == 0 for c in despues), [c.linea() for c in despues]
            valor = bd.scalar(text("SELECT valor FROM nucleo.configuracion WHERE clave = 'smtp_contrasena'"))
            assert cifrado.solo_vigente(cifrado.AJUSTES).decrypt(valor.encode()).decode() == "secreto-de-prueba-123"
            crudo = bd.scalar(text("SELECT MIN(texto) FROM innovacion.fragmento WHERE version_id = :v AND texto NOT LIKE 'cif1:%'"),
                              {"v": fuente.version_id})
            assert crudo is None  # el texto viejo quedó cifrado
    finally:
        # regresar a la llave de las demás pruebas, con la misma herramienta
        cfg.clave_cifrado_anterior, cfg.clave_cifrado = cfg.clave_cifrado, ""
        with Session(motor()) as bd:
            rotar_llave.revisar(bd, True)
            bd.commit()
        cfg.clave_cifrado_anterior = ""
        admin.put("/api/nucleo/configuracion", json={"cambios": {"smtp_contrasena": ""}})


# ---------------------------------------------------------------- B6 · resumen

def test_resumen_sin_conteos_para_proveedor(admin: TestClient):
    _, prov, _ = alta_usuario(admin, tipo="externo", rol="proveedor")
    r = prov.get("/api/nucleo/resumen").json()
    assert r["usuarios_activos"] == r["proveedores"] == 0
    assert admin.get("/api/nucleo/resumen").json()["usuarios_activos"] > 0


# ---------------------------------------------------------------- B2 · solo sitios públicos

def test_rss_y_robots_no_tocan_la_red_interna():
    import pytest

    from modulos.compras import radar
    from modulos.innovacion import fuentes_externas

    for interna in ("http://127.0.0.1:8025/api/v1/messages", "http://correo:8025/", "http://169.254.169.254/metadata"):
        with pytest.raises(radar.ErrorRadar):
            radar.leer_rss(interna)
    assert fuentes_externas.permitido_por_robots("https://localhost/robots") is False
