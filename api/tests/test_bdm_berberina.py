"""Caso BDM Life Berberina + Piperina + Omega 9 (Diego, 25 nov 2026): el Precio decía «57 % más caro, por pieza» y el
dictamen «véndelo en $336.87», porque los gramos de «120 CAP DE 1.2G» (lo que pesa cada cápsula) se comparaban contra
los gramos de las fichas de las otras berberinas y todas menos una salían «muy distintas»; y la Demanda se comparaba
contra una canela de Ceylán por ser el único lanzamiento de 2026 de su subcategoría."""
from decimal import Decimal as D

import pytest

from datos import fichas as fi
from datos.modelos import Producto
from modulos.compras import radar_productos as rp

BERBERINAS = [("55039", "4 HEALTH BERBERINA 180 CAP", "460.34", 180), ("83570", "BLIFE PURE BERBERINE 180 CAP", "811.70", 180),
              ("82094", "BIRDMAN BERBERINA HCL 90 CAP", "536.95", 90), ("90509", "NUTRAVIA BERBERINA HCI 60 CAP", "469.00", 60),
              ("13898", "YPENZA SILVER BERBERINA MAS CANELA 30 CAP", "204.75", 30)]


@pytest.fixture
def catalogo(monkeypatch):
    ps = [Producto(sku=a, descripcion=b, precio_lista_con_impuestos=D(c)) for a, b, c, _ in BERBERINAS]
    # Fichas como las del servidor: contenido en gramos de berberina (500 mg por cápsula) y cápsulas aparte
    fichas = {p.sku: fi.Ficha(tipo="suplemento", forma="cápsulas", contenido_cantidad=D(n) / 2, contenido_unidad="g",
                              piezas=n, porciones=n, ingrediente_principal="Berberina", activo_g_porcion=D("0.5"))
              for p, (_, _, _, n) in zip(ps, BERBERINAS)}
    monkeypatch.setattr(rp, "ficha_de", lambda p: fichas.get(p.sku))
    return ps


def bdm(con_ficha: bool) -> rp.Sujeto:
    s = rp.Sujeto(tipo="idea", nombre="BDM Life Berberina + Piperina + Omega 9 – Metabolismo", marca="JUVETERNAL",
                  contenido="120 CAP DE 1.2G", precio=D("459"), ingrediente="Berberina")
    if con_ficha:  # la etiqueta: 2 cápsulas por porción, 60 porciones, 800 mg de berberina por porción
        s.ficha = fi.Ficha(tipo="suplemento", forma="cápsulas", contenido_cantidad=D("144"), contenido_unidad="g",
                           piezas=120, porciones=60, ingrediente_principal="Berberina", activo_g_porcion=D("0.8"))
    return s


def test_las_berberinas_en_capsula_cuentan_como_precio_cercano(catalogo):
    s = bdm(False)
    assert all(rp.precio_cercano(s, p) for p in catalogo)  # antes, con las fichas en gramos, solo una

def test_precio_por_capsula_sin_dosis(catalogo, monkeypatch):
    s = bdm(False)
    monkeypatch.setattr(rp, "ficha_de", lambda p: None)
    f = rp.precio_anaquel(s, [(p, D("0.5")) for p in catalogo])
    assert f.puntaje == 100 and "más barato" in f.valor and "por cápsula" in f.valor
    assert "$3.82 por cápsula" in f.detalle


def test_precio_por_gramo_de_berberina_con_dosis(catalogo):
    s = bdm(True)
    f = rp.precio_anaquel(s, [(p, D("0.5")) for p in catalogo])
    # 459 / 48 g = $9.56 por gramo; las de tamaño cercano (24 a 96 g de berberina): 4 Health $5.11, Blife $9.02,
    # Birdman $11.93 y Nutravia $15.63 por gramo; en medio $10.48: 9 % más barato = 84
    assert "por gramo de berberina" in f.valor and "$9.56 por gramo" in f.detalle and "YPENZA" not in f.detalle
    assert f.puntaje == 84


def test_lanzamientos_solo_de_su_mismo_tipo():
    misma = [{"sku": "1", "descripcion": "JOY NATURA CANELA DE CEYLAN 60 CAP", "por_tienda": 2.5},
             {"sku": "2", "descripcion": "NUTRAVIA BERBERINA HCI 60 CAP", "por_tienda": 1.1},
             {"sku": "3", "descripcion": "BERBERINA GOTAS 30 ML", "por_tienda": 3.0}]
    assert [x["sku"] for x in rp.lanzamientos_de_su_tipo(bdm(False), misma)] == ["2"]
    assert rp.lanzamientos_de_su_tipo(bdm(False), misma[:1]) == []
