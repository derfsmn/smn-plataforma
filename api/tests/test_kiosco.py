"""Kiosco Digital: Naturi (ElevenLabs simulado, nunca se llama de verdad) y la herramienta de productos."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from core.config import configuracion
from datos.modelos import Producto
from modulos.kiosco import naturi
from modulos.kiosco import productos as catalogo
from nucleo.modelos import Bitacora
from tests.conftest import alta_usuario

AGENTE = "agent_ejemplo_kiosco"
FIRMADA = f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={AGENTE}&conversation_signature=firma-ej&conversation_id=c-ej"


class ElevenLabsSimulado:
    def __init__(self):
        self.widget = {"terms_text": "Términos de ejemplo", "supports_text_only": False, "file_input_config": {"enabled": True}}
        self.agente = {"conversation_config": {"conversation": {"text_only": True, "client_events": ["agent_response"]}}}
        self.firmada = FIRMADA
        self.caido = False
        self.llamadas: list[str] = []

    def __call__(self, ruta, params=None):
        self.llamadas.append(ruta)
        if self.caido:
            raise OSError("sin conexión")
        if ruta.endswith("/widget"):
            return {"widget_config": self.widget}
        if ruta.startswith("/agents/"):
            return self.agente
        if ruta == "/conversation/get-signed-url":
            assert params == {"agent_id": AGENTE, "include_conversation_id": "true"}
            return {"signed_url": self.firmada}
        raise AssertionError(ruta)


@pytest.fixture
def eleven(base_de_pruebas, monkeypatch):
    cfg = configuracion()
    monkeypatch.setattr(cfg, "elevenlabs_api_key", "llave-ej")
    monkeypatch.setattr(cfg, "kiosco_agente_id", AGENTE)
    monkeypatch.setattr(cfg, "kiosco_limite_usuario_hora", 30)
    monkeypatch.setattr(cfg, "kiosco_limite_hora", 120)
    simulado = ElevenLabsSimulado()
    monkeypatch.setattr(naturi, "_get", simulado)
    naturi.olvidar_configuracion()
    naturi._inicios.clear()
    yield simulado
    naturi.olvidar_configuracion()
    naturi._inicios.clear()


def test_sin_llave_es_vista_previa_y_pide_permiso(admin, cliente, monkeypatch):
    monkeypatch.setattr(configuracion(), "elevenlabs_api_key", "")
    naturi.olvidar_configuracion()
    r = admin.get("/api/kiosco/configuracion")
    assert r.status_code == 200 and r.json()["disponible"] is False and r.headers["cache-control"] == "no-store"
    assert admin.post("/api/kiosco/sesion", json={"modo": "voz"}).status_code == 503
    assert cliente.get("/api/kiosco/configuracion").status_code == 401
    _, otro, _ = alta_usuario(admin, rol="compras_consulta")
    assert otro.get("/api/kiosco/configuracion").status_code == 403
    _, kiosco, _ = alta_usuario(admin, rol="kiosco_tienda")
    assert kiosco.get("/api/kiosco/configuracion").status_code == 200


def test_sesion_con_terminos_y_liga_firmada(admin, eleven):
    c = admin.get("/api/kiosco/configuracion").json()
    assert c["disponible"] and c["terminos"] == "Términos de ejemplo" and c["texto"] and c["fotos"]
    version = c["version_terminos"]
    # Sin aceptar los términos vigentes no se conversa
    assert admin.post("/api/kiosco/sesion", json={"modo": "voz"}).status_code == 409
    assert admin.post("/api/kiosco/sesion", json={"modo": "voz", "acepta_terminos": True, "version_terminos": "otra"}).status_code == 409
    # Campos de más se rechazan (no se acepta un agente o destino del navegador)
    assert admin.post("/api/kiosco/sesion", json={"modo": "voz", "agent_id": "otro"}).status_code == 422
    r = admin.post("/api/kiosco/sesion", json={"modo": "texto", "acepta_terminos": True, "version_terminos": version})
    assert r.status_code == 200 and r.json() == {"signed_url": FIRMADA, "modo": "texto"}
    assert r.headers["cache-control"] == "no-store"
    with Session(motor()) as bd:
        b = bd.scalars(select(Bitacora).where(Bitacora.accion == "kiosco_conversacion").order_by(Bitacora.bitacora_id.desc())).first()
        assert b and "firma" not in (b.detalle or "")
    # La configuración se guarda 5 minutos: no se vuelve a pedir el widget
    assert eleven.llamadas.count(f"/agents/{AGENTE}/widget") == 1


def test_texto_sin_permiso_del_agente_y_destino_ajeno(admin, eleven):
    eleven.agente = {"conversation_config": {"conversation": {"text_only": False}}}
    version = admin.get("/api/kiosco/configuracion").json()["version_terminos"]
    pide = {"acepta_terminos": True, "version_terminos": version}
    assert admin.post("/api/kiosco/sesion", json={"modo": "texto", **pide}).status_code == 409
    # Una liga firmada que no va al servidor de ElevenLabs o a otro agente no se entrega
    for mala in ("wss://otro.ejemplo.mx/v1/convai/conversation?agent_id=agent_ejemplo_kiosco&conversation_signature=x",
                 "wss://api.elevenlabs.io/v1/convai/conversation?agent_id=otro&conversation_signature=x",
                 "https://api.elevenlabs.io/v1/convai/conversation?agent_id=agent_ejemplo_kiosco&conversation_signature=x"):
        eleven.firmada = mala
        r = admin.post("/api/kiosco/sesion", json={"modo": "voz", **pide})
        assert r.status_code == 503 and "otro" not in r.text and "firma" not in r.text


def test_falla_cerrado_y_limite_por_hora(admin, eleven, monkeypatch):
    eleven.caido = True
    assert admin.get("/api/kiosco/configuracion").status_code == 503
    eleven.caido = False
    monkeypatch.setattr(configuracion(), "kiosco_limite_usuario_hora", 2)
    version = admin.get("/api/kiosco/configuracion").json()["version_terminos"]
    pide = {"modo": "voz", "acepta_terminos": True, "version_terminos": version}
    assert [admin.post("/api/kiosco/sesion", json=pide).status_code for _ in range(3)] == [200, 200, 429]


# ---------------------------------------------------------------- herramienta de productos

MARCA = "EJKIOSCO"


@pytest.fixture
def catalogo_ej(base_de_pruebas, monkeypatch):
    monkeypatch.setattr(configuracion(), "kiosco_token_herramienta", "token-ej")
    sufijo = uuid.uuid4().hex[:6].upper()
    filas = [("000123" + sufijo, f"OMEGA 3 {sufijo} 60 CAPSULAS", "120.5", "110"),
             ("A" + sufijo, f"COLAGENO {sufijo} POLVO 500 G", "300", "280"),
             ("B" + sufijo, f"OMEGA 3 {sufijo} LIQUIDO 250 ML", "95", None),
             ("C" + sufijo, f"OMEGA 3 {sufijo} ARCHIVADO", "50", "45")]
    with Session(motor()) as bd:
        for sku, nombre, lista, mem in filas:
            bd.add(Producto(sku=sku, descripcion=nombre, marca=MARCA, origen="API", activo=not nombre.endswith("ARCHIVADO"),
                            precio_lista=Decimal(lista), precio_membresia=Decimal(mem) if mem else None))
        bd.commit()
    catalogo.olvidar()
    yield sufijo
    catalogo.olvidar()


def test_productos_pide_token(cliente, catalogo_ej, monkeypatch):
    assert cliente.get("/api/kiosco/productos", params={"consulta": "omega"}).status_code == 401
    assert cliente.get("/api/kiosco/productos", params={"consulta": "omega"},
                       headers={"Authorization": "Bearer otro"}).status_code == 401
    monkeypatch.setattr(configuracion(), "kiosco_token_herramienta", "")
    assert cliente.get("/api/kiosco/productos", params={"consulta": "omega"},
                       headers={"Authorization": "Bearer "}).status_code == 401


def test_productos_busca_en_el_catalogo(cliente, catalogo_ej):
    s, h = catalogo_ej, {"Authorization": "Bearer token-ej"}

    def buscar(**p):
        r = cliente.get("/api/kiosco/productos", params=p, headers=h)
        assert r.status_code == 200, r.text
        return r.json()

    d = buscar(consulta=f"omega {s}")
    assert d["total_coincidencias"] == 2 and d["moneda"] == "MXN" and d["impuestos_incluidos"] is False
    assert {r["sku"] for r in d["resultados"]} == {"000123" + s, "B" + s}  # el archivado no sale
    omega = next(r for r in d["resultados"] if r["sku"] == "000123" + s)
    assert omega["precio_lista"] == "120.50" and omega["precio_membresia"] == "110.00" and omega["marca"] == MARCA
    # SKU exacto con ceros iniciales primero
    assert buscar(consulta="000123" + s)["resultados"][0]["sku"] == "000123" + s
    assert [r["sku"] for r in buscar(consulta=s, presentacion="liquido")["resultados"]] == ["B" + s]
    assert [r["sku"] for r in buscar(consulta=s, precio_maximo="100")["resultados"]] == ["B" + s]
    assert [r["sku"] for r in buscar(consulta=s, orden="precio_asc")["resultados"]] == ["B" + s, "000123" + s, "A" + s]
    assert [r["sku"] for r in buscar(consulta=s, excluir_skus=f"B{s},A{s}")["resultados"]] == ["000123" + s]
    p = buscar(consulta=s, limite=1)
    assert p["hay_mas"] and p["siguiente_desplazamiento"] == 1
    for malo in ({"consulta": "x"}, {"consulta": s, "otro": "1"}, {"consulta": s, "precio_maximo": "-5"}):
        assert cliente.get("/api/kiosco/productos", params=malo, headers=h).status_code == 422
