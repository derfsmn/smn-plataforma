"""Radar de tendencias: corrida completa con RSS e IA simulados (nunca sale a internet ni a la API real)."""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from core.bd import motor
from core.config import configuracion
from ia import puerta
from modulos.compras import radar
from modulos.compras.modelos import (RadarAccion, RadarDestinatario, RadarArticulo, RadarHallazgo, RadarReporte, RadarSenal,
                                     RadarSenalArticulo)
from tests.conftest import alta_usuario


def _hoy() -> date:
    return radar.hoy_local()


def _respuesta(texto: str, citas=None) -> puerta.Respuesta:
    from decimal import Decimal
    return puerta.Respuesta(texto, "api", "modelo-prueba", 10, 10, Decimal(0), 5, True, 0, citas or [])


@pytest.fixture
def limpio(base_de_pruebas):
    with Session(motor()) as bd:
        for t in (RadarAccion, RadarHallazgo, RadarSenalArticulo, RadarSenal, RadarArticulo, RadarReporte):
            bd.execute(delete(t))
        bd.commit()


@pytest.fixture
def simulado(monkeypatch, limpio):
    """RSS falso para todas las fuentes con RSS e IA falsa que responde según la tarea."""
    cfg = configuracion()
    monkeypatch.setattr(cfg, "radar_busquedas_por_dia", 2)
    monkeypatch.setattr("ia.puerta.motivos_api_apagada", lambda bd: [])
    hoy, viejo = _hoy(), _hoy() - timedelta(days=40)
    rss = [
        {"url": "https://www.nutraingredients.com/articulo/ashwagandha?utm_source=rss", "titulo": "Ashwagandha gana terreno en EUA",
         "extracto": "Lanzamientos con ashwagandha crecen.", "publicado_en": hoy},
        {"url": "https://www.nutraingredients.com/articulo/nota-vieja", "titulo": "Nota de hace mes y medio",
         "extracto": "Vieja.", "publicado_en": viejo},
        {"url": "https://www.nutraingredients.com/articulo/autos", "titulo": "Venta de autos sube",
         "extracto": "Nada que ver.", "publicado_en": hoy},
    ]
    monkeypatch.setattr(radar, "leer_rss", lambda direccion: rss if "nutraingredients" in direccion else [])
    llamadas = []

    def ejecutar(bd, tarea, **k):
        llamadas.append(tarea)
        if tarea == "compras.radar_buscar":
            notas = [{"titulo": "Ashwagandha llega a tiendas en México", "url": "https://www.gob.mx/cofepris/ashwagandha",
                      "fecha": hoy.isoformat(), "resumen": "Nota en México.", "pais": "MX"},
                     {"titulo": "Liga inventada", "url": "https://inventada.com/x", "fecha": hoy.isoformat(),
                      "resumen": "No salió de la búsqueda.", "pais": "MX"}]
            return _respuesta(json.dumps({"notas": notas}), [{"url": "https://gob.mx/cofepris/ashwagandha/"}])
        if tarea == "compras.radar_clasificar":
            ids = [n["id"] for n in json.loads(k["mensaje"])]
            notas = []
            for n in json.loads(k["mensaje"]):
                relevante = "autos" not in n["titulo"].lower()
                notas.append({"id": n["id"], "relevante": relevante, "categoria": "INGREDIENTE", "nivel": "MEDIA",
                              "area": "Herbolaria", "pais": "MX" if "méxico" in n["titulo"].lower() else "EUA",
                              "por_que": "Ingrediente en crecimiento."})
            assert ids
            return _respuesta(json.dumps({"notas": notas}))
        if tarea == "compras.radar_resumen":
            datos = json.loads(k["mensaje"].split("\n\nBase de conocimiento")[0])
            ids = [n["id"] for n in datos["notas"]]
            return _respuesta(json.dumps({
                "resumen": "La ashwagandha sigue creciendo.",
                "hallazgos": [{"titulo": "Ashwagandha en EUA y México", "por_que": "Aparece en ambos mercados.",
                               "categoria": "INGREDIENTE", "nivel": "ALTA", "area": "Herbolaria", "senal_id": None,
                               "notas": ids},
                              {"titulo": "Hallazgo sin notas", "por_que": "No debe salir.", "nivel": "ALTA", "notas": [999999]}],
                "radar_ejecutivo": ["Los adaptógenos siguen subiendo."]}))
        raise AssertionError(tarea)

    monkeypatch.setattr("ia.puerta.ejecutar", ejecutar)
    correos = []
    monkeypatch.setattr(radar, "enviar", lambda para, asunto, *a, **k: correos.append((para, asunto, k)) or True)
    return SimpleNamespace(llamadas=llamadas, correos=correos)


def test_corrida_completa(admin: TestClient, simulado):
    assert admin.post("/api/compras/radar/destinatarios",
                      json={"nombre": "Compras", "correo": f"compras-{_hoy():%j}@ejemplo.mx", "area": "Compras"}).status_code in (201, 409)
    with Session(motor()) as bd:
        reporte = radar.tomar_reporte(bd, _hoy(), "programado")
        radar.correr(bd, reporte)
        assert reporte.estado == "listo", reporte.error
        arts = bd.scalars(select(RadarArticulo).where(RadarArticulo.reporte_id == reporte.reporte_id)).all()
        titulos = {a.titulo: a for a in arts}
        # la liga inventada no se guardó; la vieja se guardó fuera de ventana; utm se quitó para comparar
        assert "Liga inventada" not in titulos
        assert titulos["Nota de hace mes y medio"].en_ventana is False
        assert titulos["Nota de hace mes y medio"].clasificado_en is None
        assert titulos["Venta de autos sube"].relevante is False
        assert reporte.articulos_relevantes == 2
        assert len(reporte.hallazgos) == 1
        h = reporte.hallazgos[0]
        assert h.tipo == "tendencia"  # dos sitios distintos (y EUA + MX): lo decide la regla, no la IA
        assert reporte.busquedas == 2
        enviados = reporte.correos_enviados
    assert enviados >= 1
    para, asunto, k = simulado.correos[0]
    assert "Radar de tendencias" in asunto and "Abrir iniciativa" in k["cuerpo_html"]
    assert "nutraingredients.com/articulo/ashwagandha" in k["cuerpo_html"]

    # El mismo día ya no corre otra vez solo; con forzar sí, y no repite notas
    with Session(motor()) as bd:
        assert radar.tomar_reporte(bd, _hoy(), "programado") is None
        reporte = radar.tomar_reporte(bd, _hoy(), "manual", forzar=True)
        radar.correr(bd, reporte, enviar_correo=False)
        assert reporte.intentos == 2
        assert bd.query(RadarArticulo).filter(RadarArticulo.titulo == "Ashwagandha gana terreno en EUA").count() == 1

    detalle = admin.get(f"/api/compras/radar/reportes/{_hoy().isoformat()}").json()
    assert detalle["detalle_hallazgos"][0]["articulos"]
    assert admin.get("/api/compras/radar/reportes/ultimo").json()["fecha"] == _hoy().isoformat()


def test_decisiones_y_permisos(admin: TestClient, simulado):
    with Session(motor()) as bd:
        radar.correr(bd, radar.tomar_reporte(bd, _hoy(), "manual", forzar=True), enviar_correo=False)
        senal_id = bd.scalar(select(RadarSenal.senal_id))
    # Otras pruebas cambian los permisos de este rol; aquí se dejan como vienen en el catálogo
    assert admin.put("/api/nucleo/roles/compras_consulta/permisos",
                     json={"permisos": ["compras.solicitud.ver", "compras.radar.ver"]}).status_code == 200
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    assert consulta.get("/api/compras/radar/senales").status_code == 200
    assert consulta.post(f"/api/compras/radar/senales/{senal_id}/accion", json={"accion": "vigilar"}).status_code == 403
    assert consulta.get("/api/compras/radar/destinatarios").status_code == 403
    assert consulta.post("/api/compras/radar/correr", json={}).status_code == 403

    _, responsable, _ = alta_usuario(admin, rol="compras_responsable")
    r = responsable.post(f"/api/compras/radar/senales/{senal_id}/accion", json={"accion": "descartar"})
    assert r.status_code == 400  # descartar pide motivo
    r = responsable.post(f"/api/compras/radar/senales/{senal_id}/accion", json={"accion": "iniciativa", "motivo": "Probar en 3 tiendas"})
    assert r.status_code == 200 and r.json()["estado"] == "iniciativa"
    d = admin.get(f"/api/compras/radar/senales/{senal_id}").json()
    assert d["acciones"][0]["motivo"] == "Probar en 3 tiendas"


def test_sin_ia_el_reporte_lo_dice(admin: TestClient, limpio, monkeypatch):
    monkeypatch.setattr(radar, "leer_rss", lambda d: [{"url": "https://ejemplo.mx/n1", "titulo": "Nota uno",
                                                      "extracto": None, "publicado_en": _hoy()}] if "fda" in d else [])
    monkeypatch.setattr(radar, "enviar", lambda *a, **k: True)
    with Session(motor()) as bd:
        reporte = radar.correr(bd, radar.tomar_reporte(bd, _hoy(), "programado"), enviar_correo=False)
        assert reporte.estado == "listo"
        avisos = json.loads(reporte.avisos)
        assert any("apagada" in a for a in avisos)  # sin llave no hay búsqueda abierta
        assert not reporte.hallazgos and reporte.articulos_nuevos == 1


def test_programa_respeta_la_hora_y_reintenta(limpio, monkeypatch):
    cfg = configuracion()
    monkeypatch.setattr(cfg, "radar_hora", 0)
    corridas = []
    monkeypatch.setattr(radar, "correr", lambda bd, r, enviar_correo=True: corridas.append(r.origen) or r)
    with Session(motor()) as bd:
        assert radar.revisar_programa(bd) is not None
        assert radar.revisar_programa(bd) is None  # ya hay una en curso
        r = bd.scalar(select(RadarReporte))
        r.estado, r.terminado_en = "error", radar.ahora()
        bd.commit()
        assert radar.revisar_programa(bd) is None  # espera 30 minutos para reintentar
        r.terminado_en = radar.ahora() - timedelta(minutes=31)
        bd.commit()
        assert radar.revisar_programa(bd) is not None
    monkeypatch.setattr(cfg, "radar_activo", False)
    assert len(corridas) == 2


def test_fuentes_temas_y_destinatarios(admin: TestClient, limpio):
    r = admin.post("/api/compras/radar/fuentes", json={"nombre": "Sitio X", "liga": "https://www.sitiox.com", "tipo": "negocios",
                                                       "pais": "MX", "idioma": "es", "metodo": "busqueda"})
    assert r.status_code == 201 and r.json()["lectura"] == "sitiox.com"
    r = admin.post("/api/compras/radar/fuentes", json={"nombre": "Sin feed", "liga": "https://a.com", "tipo": "negocios",
                                                       "pais": "MX", "idioma": "es", "metodo": "rss"})
    assert r.status_code == 400
    assert admin.post("/api/compras/radar/temas", json={"nombre": "Colágeno", "descripcion": "Colágeno en México"}).status_code == 201
    correo = f"dup-{_hoy():%j}@ejemplo.mx"
    admin.post("/api/compras/radar/destinatarios", json={"nombre": "Ana", "correo": correo})
    assert admin.post("/api/compras/radar/destinatarios", json={"nombre": "Beto", "correo": correo.upper()}).status_code == 409


def test_openai_lee_texto_citas_y_cobra_busquedas(monkeypatch):
    cfg = configuracion()
    monkeypatch.setattr(cfg, "ia_proveedor_externo", "openai")
    monkeypatch.setattr(cfg, "openai_api_key", "llave")
    monkeypatch.setattr(cfg, "ia_precio_busqueda_usd", 0.01)
    monkeypatch.setattr(cfg, "ia_precio_entrada_usd_mtok", 1.0)
    monkeypatch.setattr(cfg, "ia_precio_salida_usd_mtok", 1.0)
    monkeypatch.setattr(cfg, "ia_tipo_cambio_mxn", 20.0)
    pedido = {}

    class Falso:
        def __init__(self, **k):
            self.responses = self

        def create(self, **k):
            pedido.update(k)
            busqueda = SimpleNamespace(type="web_search_call", action=SimpleNamespace(
                sources=[SimpleNamespace(url="https://a.com/1")], url=None))
            mensaje = SimpleNamespace(type="message", content=[SimpleNamespace(
                type="output_text", text="hola", annotations=[SimpleNamespace(type="url_citation", url="https://b.com/2", title="B")])])
            return SimpleNamespace(output=[busqueda, busqueda, mensaje], model="gpt-prueba", status="completed",
                                   incomplete_details=None, usage=SimpleNamespace(input_tokens=1000, output_tokens=0))

    monkeypatch.setattr("ia.puerta.openai.OpenAI", Falso)
    r = puerta._llamar_api("gpt-prueba", "inst", "msj", 100, "low", True, ["gob.mx"])
    assert r["texto"] == "hola" and r["busquedas"] == 2
    assert {c["url"] for c in r["citas"]} == {"https://a.com/1", "https://b.com/2"}
    assert pedido["tools"][0]["filters"] == {"allowed_domains": ["gob.mx"]}
    # 1000 tokens × 1 USD/M = 0.001 + 2 búsquedas × 0.01 = 0.021 USD × 20 = 0.42 MXN
    assert str(puerta.costo_mxn(r)) == "0.4200"
    with pytest.raises(puerta.ErrorIA):
        monkeypatch.setattr(cfg, "ia_proveedor_externo", "anthropic")
        puerta._llamar_api("m", "i", "m", 10, "low", True)


def test_ejecutar_pasa_busqueda_y_dominios(base_de_pruebas, monkeypatch):
    """La firma real de la puerta acepta lo que manda el radar (las demás pruebas simulan ejecutar)."""
    recibido = {}
    monkeypatch.setattr("ia.puerta._por_api", lambda bd, tarea, *a: recibido.update(args=a) or _respuesta("{}"))
    with Session(motor()) as bd:
        puerta.ejecutar(bd, "compras.radar_buscar", usuario_id=None, instrucciones="i", mensaje="m",
                        max_tokens=10, esfuerzo="low", busqueda_web=True, dominios=["gob.mx"])
    assert recibido["args"][-2:] == (True, ["gob.mx"])


def test_frecuencia_dias_y_cada_n(limpio, monkeypatch):
    cfg = configuracion()
    monkeypatch.setattr(cfg, "radar_hora", 0)
    monkeypatch.setattr(radar, "correr", lambda bd, r, enviar_correo=True: r)
    hoy = _hoy()
    with Session(motor()) as bd:
        # Días de la semana: hoy no toca → no corre y la próxima es otro día
        monkeypatch.setattr(cfg, "radar_frecuencia", "dias")
        monkeypatch.setattr(cfg, "radar_dias_semana", str((hoy.isoweekday() % 7) + 1))  # solo mañana
        assert radar.revisar_programa(bd) is None
        assert radar.proxima_corrida(bd).date() == hoy + timedelta(days=1)
        monkeypatch.setattr(cfg, "radar_dias_semana", str(hoy.isoweekday()))
        assert radar.revisar_programa(bd) is not None
        assert radar.proxima_corrida(bd).date() == hoy + timedelta(days=7)  # hoy ya corrió
        # Cada N días: se cuenta desde la última corrida buena
        bd.execute(delete(RadarReporte))
        bd.add(RadarReporte(fecha=hoy - timedelta(days=1), estado="listo", origen="programado"))
        bd.commit()
        monkeypatch.setattr(cfg, "radar_frecuencia", "cada_n")
        monkeypatch.setattr(cfg, "radar_cada_dias", 3)
        assert radar.revisar_programa(bd) is None
        assert radar.proxima_corrida(bd).date() == hoy + timedelta(days=2)
        assert radar.texto_frecuencia() == "Cada 3 días"
        monkeypatch.setattr(cfg, "radar_cada_dias", 2)
        assert radar.proxima_corrida(bd).date() == hoy + timedelta(days=1)


def test_ajuste_dias_valida():
    from core.ajustes import POR_CLAVE, convertir
    a = POR_CLAVE["radar_dias_semana"]
    assert convertir(a, "5,1,3,1") == "1,3,5"
    for malo in ("", "0", "8", "lun"):
        with pytest.raises(ValueError):
            convertir(a, malo)


def test_resumen_ve_decisiones_de_compras(admin: TestClient, simulado, monkeypatch):
    with Session(motor()) as bd:
        bd.add(RadarSenal(titulo="Colágeno marino en polvo", nivel="MEDIA", primera_vez=_hoy(), ultima_vez=_hoy(),
                          estado="nueva"))
        bd.commit()
        senal_id = bd.scalar(select(RadarSenal.senal_id).where(RadarSenal.titulo == "Colágeno marino en polvo"))
    r = admin.post(f"/api/compras/radar/senales/{senal_id}/accion", json={"accion": "descartar", "motivo": "Ya lo vendemos"})
    assert r.status_code == 200, r.text
    vistos = []
    original = puerta.ejecutar

    def espia(bd, tarea, **k):
        if tarea == "compras.radar_resumen":
            vistos.append(json.loads(k["mensaje"].split("\n\nBase de conocimiento")[0]))
        return original(bd, tarea, **k)

    monkeypatch.setattr("ia.puerta.ejecutar", espia)
    with Session(motor()) as bd:
        radar.correr(bd, radar.tomar_reporte(bd, _hoy(), "manual", forzar=True), enviar_correo=False)
    assert {"titulo": "Colágeno marino en polvo", "motivo": "Ya lo vendemos"} in vistos[0]["descartadas_por_compras"]
    assert all(s["senal_id"] != senal_id for s in vistos[0]["senales_existentes"])
    assert "descartadas_por_compras" in radar.instrucciones_resumen(5)


def test_enviar_a_destinatarios(admin: TestClient, simulado, monkeypatch):
    monkeypatch.setattr(configuracion(), "smtp_servidor", "localhost")
    admin.post("/api/compras/radar/destinatarios", json={"nombre": "Compras", "correo": f"envio-{_hoy():%j}@ejemplo.mx"})
    with Session(motor()) as bd:
        reporte = radar.correr(bd, radar.tomar_reporte(bd, _hoy(), "manual", forzar=True), enviar_correo=False)
        antes = reporte.correos_enviados or 0
        activos = bd.scalar(select(func.count()).select_from(RadarDestinatario).where(RadarDestinatario.activo))
    r = admin.post(f"/api/compras/radar/reportes/{_hoy().isoformat()}/enviar-destinatarios").json()
    assert r["enviado"] is True and "Enviado a" in r["mensaje"]
    assert len(simulado.correos) == activos
    with Session(motor()) as bd:
        assert bd.scalar(select(RadarReporte.correos_enviados).where(RadarReporte.fecha == _hoy())) == antes + activos
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    assert consulta.post(f"/api/compras/radar/reportes/{_hoy().isoformat()}/enviar-destinatarios").status_code == 403


def test_correo_informativo_sin_botones(admin: TestClient, simulado, monkeypatch):
    monkeypatch.setattr(configuracion(), "smtp_servidor", "localhost")
    with Session(motor()) as bd:
        bd.execute(delete(RadarDestinatario))
        bd.commit()
    dia = f"{_hoy():%j}"
    assert admin.post("/api/compras/radar/destinatarios",
                      json={"nombre": "Dirección", "correo": f"info-{dia}@ejemplo.mx", "tipo_correo": "informativo"}).status_code == 201
    r = admin.post("/api/compras/radar/destinatarios", json={"nombre": "Compras", "correo": f"decide-{dia}@ejemplo.mx"})
    assert r.json()["tipo_correo"] == "decision"
    assert admin.post("/api/compras/radar/destinatarios",
                      json={"nombre": "X", "correo": f"x-{dia}@ejemplo.mx", "tipo_correo": "otro"}).status_code == 422
    with Session(motor()) as bd:
        reporte = radar.correr(bd, radar.tomar_reporte(bd, _hoy(), "manual", forzar=True), enviar_correo=False)
        assert radar.enviar_reporte(bd, reporte) == (2, 0)
    cuerpos = {para: k["cuerpo_html"] for para, _, k in simulado.correos}
    assert "Abrir iniciativa" not in cuerpos[f"info-{dia}@ejemplo.mx"] and "Ashwagandha" in cuerpos[f"info-{dia}@ejemplo.mx"]
    assert "Ver en la plataforma" not in cuerpos[f"info-{dia}@ejemplo.mx"]
    assert "Abrir iniciativa" in cuerpos[f"decide-{dia}@ejemplo.mx"]


def test_json_mal_formado_reintenta_y_sin_ia_no_manda_correo(admin: TestClient, simulado, monkeypatch):
    assert admin.post("/api/compras/radar/destinatarios",
                      json={"nombre": "Compras", "correo": f"compras-{_hoy():%j}@ejemplo.mx", "area": "Compras"}).status_code in (201, 409)
    from ia import puerta
    original = puerta.ejecutar
    tamanos = []

    def con_fallas(bd, tarea, **k):
        if tarea == "compras.radar_clasificar":
            lote = json.loads(k["mensaje"])
            tamanos.append(len(lote))
            if len(lote) > 1:
                return _respuesta('{"notas": [{"id": 1 "relevante": true}]}')  # le falta una coma
        if tarea == "compras.radar_resumen":
            raise radar.puerta.ErrorIA("Se alcanzó el tope mensual de la plataforma.")
        return original(bd, tarea, **k)

    monkeypatch.setattr("ia.puerta.ejecutar", con_fallas)
    with Session(motor()) as bd:
        reporte = radar.correr(bd, radar.tomar_reporte(bd, _hoy(), "manual", forzar=True))
        assert reporte.estado == "listo"
        avisos = json.loads(reporte.avisos)
        assert not any("clasificar" in a for a in avisos)  # se partió en lotes de uno y salieron todas
        assert tamanos[0] > 1 and 1 in tamanos
        assert any("No se pudo armar el reporte" in a for a in avisos)
    assert not simulado.correos  # sin IA no se manda el correo a los destinatarios
