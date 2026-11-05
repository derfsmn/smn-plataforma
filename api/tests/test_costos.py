"""Costo real de OpenAI: API de costos simulada (nunca sale a internet)."""
import io
import urllib.error
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.bd import motor
from core.config import configuracion
from ia import costos
from nucleo.modelos import IaCostoReal, IaLlamada, IaTarea, ahora


_ORIGINAL = costos._pedir


def _ts(d) -> int:
    return int(datetime.combine(d, datetime.min.time(), UTC).timestamp())


@pytest.fixture
def openai(monkeypatch, base_de_pruebas):
    cfg = configuracion()
    monkeypatch.setattr(cfg, "ia_proveedor_externo", "openai")
    monkeypatch.setattr(cfg, "openai_admin_key", "sk-admin-prueba")
    monkeypatch.setattr(cfg, "openai_proyecto_id", "proj_prueba")
    monkeypatch.setattr(cfg, "ia_tipo_cambio_mxn", 20.0)
    monkeypatch.setitem(costos.ESTADO, "ultimo_intento", None)
    with Session(motor()) as bd:
        bd.execute(delete(IaCostoReal))
        bd.execute(delete(IaLlamada))
        bd.commit()
    hoy = ahora().date()
    ayer, antier = hoy - timedelta(days=1), hoy - timedelta(days=2)
    pedidos = []
    paginas = {
        None: {"data": [{"start_time": _ts(antier), "end_time": _ts(ayer),
                         "results": [{"amount": {"value": 0.25, "currency": "usd"}},
                                     {"amount": {"value": 0.24, "currency": "usd"}}]}],
               "has_more": True, "next_page": "p2"},
        "p2": {"data": [{"start_time": _ts(ayer), "end_time": _ts(hoy), "results": [{"amount": {"value": 1.5}}]},
                        {"start_time": _ts(hoy), "end_time": _ts(hoy + timedelta(days=1)),
                         "results": [{"amount": {"value": 9.0}}]}],
               "has_more": False, "next_page": None},
    }

    def pedir(params):
        pedidos.append(dict(params))
        return paginas[params.get("page")]

    monkeypatch.setattr(costos, "_pedir", pedir)
    return {"pedidos": pedidos, "hoy": hoy, "ayer": ayer, "antier": antier}


def test_baja_costos_por_dia_sin_el_dia_abierto(openai):
    with Session(motor()) as bd:
        assert costos.sincronizar(bd) == 2
        filas = {f.fecha: f for f in bd.query(IaCostoReal).all()}
    assert filas[openai["antier"]].costo_usd == Decimal("0.4900")
    assert filas[openai["antier"]].costo_mxn == Decimal("9.8000")
    assert filas[openai["ayer"]].costo_usd == Decimal("1.5000")
    assert openai["hoy"] not in filas  # el día de hoy no ha cerrado
    assert openai["pedidos"][0]["project_ids"] == ["proj_prueba"] and openai["pedidos"][0]["bucket_width"] == "1d"
    assert openai["pedidos"][1]["page"] == "p2"


def test_tope_usa_real_en_dias_cerrados_y_estimado_hoy(openai):
    with Session(motor()) as bd:
        tarea = bd.query(IaTarea).first()
        for cuando, costo in ((datetime.combine(openai["antier"], datetime.min.time()) + timedelta(hours=3), "50"),
                              (ahora(), "2.5")):
            bd.add(IaLlamada(tarea_id=tarea.tarea_id, proveedor_ia="api", costo_mxn=Decimal(costo),
                             resultado="ok", ocurrido_en=cuando))
        bd.commit()
        desde = datetime.combine(openai["antier"], datetime.min.time())
        assert costos.gasto_plataforma(bd, desde) == Decimal("52.5")  # sin sincronizar: todo estimado
        costos.sincronizar(bd)
        # antier real 9.80 (en vez de 50 estimado) + ayer real 30.00 + hoy estimado 2.5
        assert costos.gasto_plataforma(bd, desde) == Decimal("42.3")


def test_llave_rechazada_y_pantalla(openai, admin: TestClient, monkeypatch):
    def rechazo(*_a, **_k):
        raise urllib.error.HTTPError(costos.URL_COSTOS, 401, "no", {}, io.BytesIO(b""))

    monkeypatch.setattr(costos, "_pedir", _ORIGINAL)
    monkeypatch.setattr(costos.urllib.request, "urlopen", rechazo)
    r = admin.post("/api/ia/costos-reales/sincronizar")
    assert r.status_code == 400 and "Admin key" in r.json()["detail"]
    datos = admin.get("/api/ia/costos-reales").json()
    assert datos["activo"] is True and datos["error"] and len(datos["dias"]) == 14
    assert admin.get("/api/ia/estado").json()["costo_real_activo"] is True
    monkeypatch.setattr(configuracion(), "openai_admin_key", "")
    assert "llave de administrador" in admin.get("/api/ia/costos-reales").json()["motivo"]
