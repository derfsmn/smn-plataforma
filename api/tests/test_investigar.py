"""Investigar afuera con IA local: Google (simulado), páginas (simuladas) y la IA FALSA. Solo cuenta lo que trae cita
de la página."""
import json
from decimal import Decimal

from sqlalchemy.orm import Session

from core.bd import motor
from ia import puerta
from modulos.compras import investigar as iv
from modulos.compras import mercado_producto as mp
from modulos.compras import radar_productos as rp

PAGINA = """<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",
"name":"Wonu Creatina + Inositol 30 sobres","offers":{"@type":"Offer","price":"649.00","priceCurrency":"MXN"}}</script>
</head><body><nav>Menú</nav><h1>Wonu Creatina + Inositol</h1><p>Caja con 30 sobres de 7.6 g.</p>
<p>Cada sobre aporta 5 g de creatina monohidratada y 2 g de myo-inositol.</p>
<p>Apoya la energía y el rendimiento físico.</p><script>var x = 1;</script></body></html>"""


def _resp(d: dict) -> puerta.Respuesta:
    return puerta.Respuesta(json.dumps(d, ensure_ascii=False), "ollama", "falso", 1, 1, Decimal(0), 1, True, 0)


def test_consultas_y_texto_de_la_pagina():
    c = iv.consultas("Creatina + Inositol", "Wonu", "30 sobres", "creatina", "sobre", "7503053821217")
    assert 4 <= len(c) <= 6 and "7503053821217" in c and c[0] == "Wonu Creatina + Inositol precio"
    t = iv.texto_de(PAGINA)
    assert "Menú" not in t and "var x" not in t and "5 g de creatina" in t
    assert iv._precio_jsonld(iv._productos_jsonld(PAGINA)[0]) == Decimal("649.00")


def test_investigar_solo_con_citas(base_de_pruebas, monkeypatch):
    monkeypatch.setattr(iv, "_google", lambda bd, inv, ref: [
        {"url": "https://tienda-ejemplo.mx/wonu", "titulo": "Wonu Creatina", "descripcion": "", "consulta": inv.consultas[0]},
        {"url": "https://www.youtube.com/watch?v=1", "titulo": "Video", "descripcion": "", "consulta": inv.consultas[0]},
        {"url": "https://otra-ejemplo.mx/x", "titulo": "Otra", "descripcion": "", "consulta": inv.consultas[1]},
    ])
    monkeypatch.setattr(iv, "bajar", lambda url: PAGINA if "tienda-ejemplo" in url else None)

    def ia(bd, tarea, **k):
        assert tarea == iv.TAREA
        return _resp({"tipo": "mismo", "producto": "Wonu Creatina + Inositol",
                      "presentacion": {"valor": "30 sobres de 7.6 g", "cita": "Caja con 30 sobres de 7.6 g"},
                      "dosis": {"valor": "5 g de creatina", "cita": "aporta 5 g de creatina monohidratada"},
                      "afirmaciones": [{"texto": "energía", "cita": "Apoya la energía y el rendimiento físico"},
                                       {"texto": "quema grasa", "cita": "quema grasa en 7 días"}]})  # inventada

    monkeypatch.setattr(puerta, "ejecutar", ia)
    with Session(motor()) as bd:
        inv = iv.investigar(bd, nombre="Creatina + Inositol", marca="Wonu", contenido="30 sobres", ingrediente="Creatina",
                            forma="Sobre", codigo_barras=None, referencia="prueba")
    assert len(inv.hallazgos) == 1  # YouTube no se lee; la otra página no dejó leer
    h = inv.hallazgos[0]
    assert h.tipo == "mismo" and h.precio == 649.0 and h.de == "datos" and h.dominio == "tienda-ejemplo.mx"
    assert h.presentacion == "30 sobres de 7.6 g" and h.dosis == "5 g de creatina"
    assert h.afirmaciones == ["Apoya la energía y el rendimiento físico"]
    assert any("otra-ejemplo.mx" in n for n in inv.notas)
    otra = iv.Investigacion.de_json(inv.a_json())
    assert otra.hallazgos[0].precio == 649.0 and otra.vigente(inv.clave)

    m = rp.con_web(mp.Mercado(precios=[{"precio": 653.0, "vendedor": "Chedraui", "fuente": "sitio", "titulo": "x",
                                       "liga": None}]), inv)
    assert [p["vendedor"] for p in m.precios] == ["Chedraui", "tienda-ejemplo.mx"]
    assert m.mediana() == Decimal("651")


def test_el_envio_de_google_organico_se_puede_guardar():
    """La base aceptaba solo «productos» y «vendedores» (Wonu, 17 nov 2026: tronaba al reservar la búsqueda)."""
    from decimal import Decimal

    from sqlalchemy.orm import Session

    from core.bd import motor
    from modulos.compras.modelos_precios import PrecioEnvio

    with Session(motor()) as bd:
        bd.add(PrecioEnvio(tipo="organico", tareas=6, estimado_usd=Decimal("0.0036")))
        bd.flush()
        bd.rollback()


def test_por_titulo_reconoce_la_marca_sin_ia():
    from modulos.compras import investigar as iv

    h = iv.Hallazgo(url="https://wonu.mx/p", dominio="wonu.mx", titulo="Wonu Creatina con Inositol 30 sobres – WONU")
    assert iv.por_titulo(h, "Creatina + Inositol", "WONU") == "mismo"
    h2 = iv.Hallazgo(url="https://wonu.mx/c", dominio="wonu.mx", titulo="Wonu Colágeno hidrolizado")
    assert iv.por_titulo(h2, "Creatina + Inositol", "WONU") == "misma_marca"
    h3 = iv.Hallazgo(url="https://x.mx", dominio="x.mx", titulo="Creatina monohidratada 300 g")
    assert iv.por_titulo(h3, "Creatina + Inositol", "WONU") == "otro"
