"""Casos reales: los 100 productos del comité del 12 nov 2026 (tests/casos/comite_12nov.json, revisados a mano).
Si un cambio al radar mueve uno de estos resultados, la prueba dice cuál y cómo."""
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from modulos.compras import radar_productos as rp
from modulos.compras import rutas_comite as rc

CASOS = json.loads((Path(__file__).parent / "casos" / "comite_12nov.json").read_text(encoding="utf-8"))["productos"]


def _item(x: dict) -> rc.ItemSalida:
    return rc.ItemSalida(id=x["orden"], tipo="idea", sujeto_id=x["orden"], nombre=x["nombre"], marca=x["marca"],
                         departamento=None, folio=None, proveedor=None, proveedor_actual=False, origen="nuevo",
                         viene_de_fecha=None, presentacion=x["contenido"], descripcion=None,
                         precio=Decimal(x["precio"]) if x["precio"] else None, costo=None, margen=None, fotos=0,
                         foto_externa=None, estado_sujeto="x", falta=None, evaluacion=None, prefiltro=None,
                         prefiltro_motivo=None, criterios=[], prefiltro_color=None, prefiltro_por=None, prefiltro_en=None,
                         decision=None, decision_motivo=None, decision_color=None, decision_por=None, decision_en=None,
                         revisiones=[], agregado_por=None, agregado_en=datetime(2026, 11, 12))


@pytest.mark.parametrize("x", CASOS, ids=lambda x: f"{x['orden']}-{x['nombre'][:30]}")
def test_tamano_de_los_100(x):
    leido = {k: float(v) for k, v in rp.tamano(x["contenido"], x["nombre"]).items()}
    assert leido == x["tamano"], f"«{x['contenido']}» / «{x['nombre']}»"


def test_repetidos_de_los_100():
    items = [_item(x) for x in CASOS]
    rc._marcar_duplicados(items)
    marcados = {i.id for i in items if i.duplicado}
    esperados = {x["orden"] for x in CASOS if x["repetido"]}
    assert marcados == esperados, f"de más: {sorted(marcados - esperados)}, faltan: {sorted(esperados - marcados)}"
    # Cada aviso nombra a los de su mismo grupo y a ninguno de otro
    grupo = {x["orden"]: x["repetido"] for x in CASOS}
    nombre = {x["orden"]: x["nombre"] for x in CASOS}
    for i in items:
        if i.duplicado:
            for otro, g in grupo.items():
                if otro != i.id and g == grupo[i.id]:
                    assert f"«{nombre[otro]}»" in i.duplicado


def test_proteina_nuba_dice_cual_conviene_por_gramo():
    """1 kg a $800 ($0.80 por gramo) conviene más que 500 g a $550 y 250 g a $299."""
    items = [_item(x) for x in CASOS if x["repetido"] == "proteina-nuba"]
    rc._marcar_duplicados(items)
    por_orden = {i.id: i.duplicado for i in items}
    assert "es el que más conviene" in por_orden[50]
    assert "hay otro que conviene más" in por_orden[51] and "hay otro que conviene más" in por_orden[52]


# ---------------------------------------------------------------- v0.4: la IA revisa los parecidos

def _p(sku, desc, sub=None, precio="80"):
    from datos.modelos import Producto
    return Producto(sku=sku, descripcion=desc, subcategoria=sub, precio_lista_con_impuestos=Decimal(precio))


class _IA:
    """IA de mentira: contesta lo que se le diga y cuenta cuántas veces la llamaron."""
    def __init__(self, respuesta):
        self.respuesta, self.llamadas, self.mensajes = respuesta, 0, []

    def __call__(self, bd, tarea, **k):
        from ia import puerta
        self.llamadas += 1
        self.mensajes.append(json.loads(k["mensaje"]))
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return puerta.Respuesta(self.respuesta, "ollama", "x", 0, 0, Decimal(0), 0, True, 0)


def _ia(monkeypatch, respuesta):
    ia = _IA(respuesta)
    monkeypatch.setattr(rp.puerta, "ejecutar", ia)
    return ia


def test_ia_quita_la_muneca_de_la_cinta(monkeypatch):
    """Caso 1 de los 100: la cinta Go Plus se comparaba contra una muñequera elástica de $78."""
    s = rp.Sujeto(tipo="idea", nombre="Cinta Kinesiológica Azul Go Plus 5m Pre-cortada", marca="Go Plus", contenido="5M")
    munequera, cinta = _p("1", "MUÑEQUERA ELASTICA CRUZADA", "MUÑEQUERA", "78"), _p("2", "CINTA KINESIOLOGICA 5 M", "VENDAS")
    ia = _ia(monkeypatch, 'Listo: {"revision": [{"n": 1, "mismo_tipo": false, "motivo": "se pone, no se pega"},'
                          ' {"n": 2, "mismo_tipo": true}]}')
    quedan, quitados = rp.revisar_parecidos(None, s, [(munequera, Decimal("0.4")), (cinta, Decimal("0.6"))])
    assert [p.sku for p, _ in quedan] == ["2"] and quitados == [(munequera, "se pone, no se pega")]
    assert ia.mensajes[0]["lista"][0]["producto"] == "MUÑEQUERA ELASTICA CRUZADA"
    assert "MUÑEQUERA ELASTICA CRUZADA (se pone, no se pega)" in rp.nota_quitados(quitados)
    assert rp.nota_quitados([]) == ""


def test_ia_nunca_quita_el_mismo_producto_y_no_repregunta(monkeypatch):
    s = rp.Sujeto(tipo="idea", nombre="Orégano", marca="Sazónarte", contenido="14 g")
    mismo, capsulas = _p("1", "OREGANO SAZONARTE 14 G"), _p("2", "OREGANO 60 CAPSULAS", "AUXILIAR EN LA DIGESTION")
    ia = _ia(monkeypatch, '{"revision": [{"n": 1, "mismo_tipo": false, "motivo": "suplemento"}]}')
    vistos = {}
    quedan, quitados = rp.revisar_parecidos(None, s, [(mismo, Decimal(1)), (capsulas, Decimal("0.5"))], vistos)
    assert [p.sku for p, _ in quedan] == ["1"] and [p.sku for p, _ in quitados] == ["2"]
    assert len(ia.mensajes[0]["lista"]) == 1  # al mismo producto ni se le pregunta
    rp.revisar_parecidos(None, s, [(capsulas, Decimal("0.5"))], vistos)
    assert ia.llamadas == 1  # ya lo había revisado en esta evaluación


def test_si_la_ia_falla_o_contesta_mal_se_quedan_todos(monkeypatch):
    from ia import puerta
    s = rp.Sujeto(tipo="idea", nombre="Shampoo anticaida y crecimiento", marca="Eco Nutree")
    lista = [(_p("1", "SHAMPOO ANTICAIDA 400 ML"), Decimal("0.6")), (_p("2", "SHAMPOO CEBOLLA 550 ML"), Decimal("0.5"))]
    for respuesta in (puerta.ErrorIA("sin Ollama"), "no sé", '{"revision": [{"n": 7, "mismo_tipo": false},'
                                                            ' {"n": "1", "mismo_tipo": "no"}]}'):
        _ia(monkeypatch, respuesta)
        quedan, quitados = rp.revisar_parecidos(None, s, lista)
        assert quedan == lista and quitados == []


def test_tabla_de_precio_por_gramo_del_krystal():
    """Caso 10 de los 100 (maqueta aprobada por Diego, 12 nov 2026): Krystal Stone Sólido 120 g a $184 contra los
    desodorantes de 55 g (menos de la mitad del tamaño: no cuentan) y el de 71 g (sí cuenta)."""
    def par(n, desc, precio):
        return rc.ParecidoSalida(producto_id=n, sku=str(n), descripcion=desc, marca=None, imagen=None,
                                 precio=Decimal(precio), al_mes=None, tiendas=None, por_tienda_mes=None, cambio=None)
    d = rc.Parecidos(ventana=None, productos=[par(1, "DESODORANTE EN BARRA LAVANDA 55 G", "131.50"),
                                              par(2, "DESODORANTE VAINILLA Y LAVANDA 71G", "127.00"),
                                              par(3, "DESODORANTE SIN TAMAÑO", "90")])
    rc._por_unidad_parecidos(d, "120 G", "Krystal Stone Sólido 120g", Decimal("184"))
    assert d.unidad == "gramo" and d.este_tamano == "120 g" and round(d.este_por_unidad, 2) == Decimal("1.53")
    lavanda, vainilla, sin = d.productos
    assert lavanda.cuenta is False and lavanda.tamano == "55 g" and round(lavanda.por_unidad, 2) == Decimal("2.39")
    assert vainilla.cuenta is True and round(vainilla.por_unidad, 2) == Decimal("1.79")
    assert sin.cuenta is None and sin.por_unidad is None
    otra = rc.Parecidos(ventana=None, productos=[par(1, "CREMA 50 ML", "80")])
    rc._por_unidad_parecidos(otra, "1 PIEZA", "Corrector de postura", Decimal("500"))
    assert otra.unidad is None and otra.productos[0].por_unidad is None
