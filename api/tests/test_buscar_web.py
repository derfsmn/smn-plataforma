"""Buscar en internet sin API externa (18 nov 2026): Google por DataForSEO (simulado) + IA local (falsa)."""
import json
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from core.config import configuracion
from ia import puerta
from modulos.compras import buscar_web as bw
from modulos.compras import dataforseo as dfs
from modulos.compras import radar
from modulos.compras.modelos_precios import PrecioCorrida, PrecioEnvio


def _resp(d: dict) -> puerta.Respuesta:
    return puerta.Respuesta(json.dumps(d, ensure_ascii=False), "ollama", "falso", 1, 1, Decimal(0), 1, True, 0)


def test_google_guarda_corrida_web_y_respeta_su_tope(base_de_pruebas, monkeypatch):
    cfg = configuracion()
    monkeypatch.setattr(dfs, "configurado", lambda: [])
    monkeypatch.setattr(cfg, "precios_tope_mensual_usd", 1000.0)
    enviadas = []

    def enviar(bd, corrida, tipo, tareas):
        enviadas.append((tipo, [t["keyword"] for t in tareas]))
        bd.add(PrecioEnvio(corrida_id=corrida.corrida_id, tipo=tipo, tareas=len(tareas), estado="confirmado",
                           estimado_usd=Decimal("0.0012"), costo_usd=Decimal("0.0012")))
        corrida.costo_usd = Decimal("0.0012")
        bd.commit()
        return {t["tag"]: f"id{t['tag']}" for t in tareas}

    monkeypatch.setattr(dfs, "enviar", enviar)
    monkeypatch.setattr(dfs, "recoger", lambda tipo, ids: {
        "0": [{"type": "news_search", "url": "https://www.gob.mx/cofepris/nota", "title": "Cofepris avisa",
               "snippet": "Aviso sobre suplementos", "timestamp": "2026-11-17 10:00:00 +00:00"},
              {"type": "top_stories", "url": "https://otro.mx/x", "title": "No es nota"}],
        "1": "La tarea no terminó a tiempo en DataForSEO"})
    monkeypatch.setattr(cfg, "busqueda_web_tope_usd", 2.0)
    with Session(motor()) as bd:
        antes = bw.gasto_mes(bd)
        b = bw.google(bd, ["cofepris suplementos", "cofepris suplementos ", "alertas sanitarias"], "noticias", "prueba")
        assert enviadas == [("noticias", ["cofepris suplementos", "alertas sanitarias"])]  # sin repetidas
        assert [r.url for r in b.resultados] == ["https://www.gob.mx/cofepris/nota"]
        r = b.resultados[0]
        assert r.fecha.isoformat() == "2026-11-17" and r.dominio == "gob.mx" and r.descripcion == "Aviso sobre suplementos"
        assert any("no terminó a tiempo" in n for n in b.notas)
        c = bd.scalar(select(PrecioCorrida).order_by(PrecioCorrida.corrida_id.desc()))
        assert c.origen == "web" and c.estado == "completa"
        assert bw.gasto_mes(bd) - antes == Decimal("0.0012")
        # Con el tope propio ya gastado, ni se envía
        monkeypatch.setattr(cfg, "busqueda_web_tope_usd", float(bw.gasto_mes(bd)))
        b = bw.google(bd, ["otra búsqueda"], "organico", "prueba")
        assert not b.resultados and "tope del mes para buscar en internet" in b.notas[0] and len(enviadas) == 1


def test_sin_dataforseo_lo_dice(base_de_pruebas, monkeypatch):
    monkeypatch.setattr(dfs, "configurado", lambda: ["usuario de DataForSEO"])
    with Session(motor()) as bd:
        b = bw.google(bd, ["x"], "organico", "prueba")
    assert not b.resultados and "falta usuario de DataForSEO" in b.notas[0]


def test_radar_busca_notas_con_fecha_y_del_sitio(base_de_pruebas, monkeypatch):
    hoy = radar.hoy_local()
    pedidas = []

    def google(bd, consultas, tipo, referencia, profundidad=10):
        pedidas.append((tipo, consultas))
        return bw.Busqueda(resultados=[
            bw.Resultado("https://www.gob.mx/cofepris/a?utm_source=x", "Nota buena", "Resumen", consultas[0], hoy, "gob.mx"),
            bw.Resultado("https://www.gob.mx/cofepris/a", "Repetida", "", consultas[0], hoy, "gob.mx"),
            bw.Resultado("https://www.gob.mx/cofepris/vieja", "Vieja", "", consultas[0], hoy - timedelta(days=60), "gob.mx"),
            bw.Resultado("https://www.gob.mx/cofepris/sin-fecha", "Sin fecha", "", consultas[0], None, "gob.mx"),
            bw.Resultado("https://otro.mx/nota", "De otro sitio", "", consultas[0], hoy, "otro.mx")])

    monkeypatch.setattr(bw, "google", google)
    monkeypatch.setattr(puerta, "ejecutar", lambda bd, tarea, **k: _resp({"busquedas": ["alertas sanitarias suplementos"]}))
    with Session(motor()) as bd:
        notas, descartadas = radar.buscar_en_web(bd, "Notas de dependencias oficiales", hoy - timedelta(days=7), ["gob.mx"])
    assert [n["titulo"] for n in notas] == ["Nota buena"] and descartadas == 3
    assert notas[0]["publicado_en"] == hoy and notas[0]["extracto"] == "Resumen"
    assert pedidas == [("noticias", ["(site:gob.mx) alertas sanitarias suplementos"])]


def test_si_la_ia_no_propone_busquedas_se_usan_las_fijas(base_de_pruebas, monkeypatch):
    monkeypatch.setattr(puerta, "ejecutar", lambda *a, **k: (_ for _ in ()).throw(puerta.ErrorIA("sin Ollama")))
    with Session(motor()) as bd:
        assert bw.frases(bd, "compras.radar_buscar", "x", ["a", "b", "c", "d"]) == ["a", "b", "c"]


def test_cita_debe_estar_en_la_pagina():
    texto = bw.iv.texto_de("<p>Más de 5,000 vendidos</p><p>Envío gratis</p>")
    assert bw.cita_ok("mas de 5,000 vendidos", texto) and not bw.cita_ok("10 mil vendidos", texto)
    assert not bw.cita_ok("", texto) and not bw.cita_ok(None, texto)


def test_las_tareas_de_internet_quedan_en_ia_local(base_de_pruebas):
    from nucleo.modelos import IaTarea

    with Session(motor()) as bd:
        for codigo in ("compras.radar_buscar", "compras.oportunidades_novedades"):
            t = bd.scalar(select(IaTarea).where(IaTarea.codigo == codigo))
            assert t.proveedor_ia == "ollama" and t.modelo == "qwen3:8b" and bw.usar_web(bd, codigo)
        bd.add_all([PrecioCorrida(fecha=radar.hoy_local(), origen="web", estado="completa"),
                    PrecioEnvio(tipo="noticias", tareas=1, estimado_usd=Decimal("0.0006"))])
        bd.flush()  # la base acepta el origen «web» y el envío «noticias»
        bd.rollback()


def test_nuestra_tienda_no_cuenta_como_mas_vendido(base_de_pruebas, monkeypatch):
    """Diego, 18 nov 2026: Google regresó páginas de supernaturista.com como «más vendido en internet»."""
    enviadas = []
    monkeypatch.setattr(dfs, "configurado", lambda: [])
    monkeypatch.setattr(dfs, "enviar", lambda bd, corrida, tipo, tareas: enviadas.append(tareas) or ["t"])
    monkeypatch.setattr(dfs, "recoger", lambda tipo, ids: {"0": [
        {"type": "organic", "url": "https://www.supernaturista.com/citrato-magnesio", "title": "Más vendido"},
        {"type": "organic", "url": "https://tienda.supernaturista.com.mx/x", "title": "Más vendido"},
        {"type": "organic", "url": "https://otra.mx/mas-vendidos", "title": "Lo más vendido"}]})
    with Session(motor()) as bd:
        b = bw.google(bd, ["suplementos más vendidos"], "organico", "prueba")
    assert [r.dominio for r in b.resultados] == ["otra.mx"]
    assert "-site:supernaturista.com" in enviadas[0][0]["keyword"]
    assert bw.es_propio("supernaturista.com") and bw.es_propio("blog.supernaturista.com") and not bw.es_propio("otra.mx")


def test_el_nombre_propuesto_debe_ser_el_de_la_prueba_de_venta():
    from modulos.compras import oportunidades as op

    assert not op._mismo_nombre("Vitamina D liposomal 30 cap", "CITRATO DE MAGNESIO CON ZINC 60 TAB")
    assert op._mismo_nombre("Citrato de magnesio con zinc", "CITRATO DE MAGNESIO CON ZINC 60 TAB")
    assert op._mismo_nombre("Colágeno hidrolizado", "Colageno Hidrolizado en polvo 500 g sabor fresa")


def test_la_cita_perdona_signos_y_alguna_palabra_cambiada():
    """Diego, 18 nov 2026: con la comparación exacta se quitaron casi todos los productos."""
    texto = bw.iv.texto_de("<li>#1 Más vendido en Suplementos</li><li>Magnesio Citrato 4.6 de 5 estrellas 12,345 calificaciones</li>")
    assert bw.cita_ok("«#1 Más vendido en Suplementos.»", texto)
    assert bw.cita_ok("4.6 de 5 estrellas, 12,345 calificaciones", texto)
    assert bw.cita_ok("Magnesio Citrato 4.6 de 5 estrellas 12,345 reseñas", texto)  # una palabra cambiada
    assert not bw.cita_ok("el más vendido de todo México en farmacias", texto)
