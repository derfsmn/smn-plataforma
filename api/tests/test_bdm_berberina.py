"""Caso BDM Life Berberina + Piperina + Omega 9 (Diego, 25 nov 2026): el Precio decía «57 % más caro, por pieza» y el
dictamen «véndelo en $336.87», porque los gramos de «120 CAP DE 1.2G» (lo que pesa cada cápsula) se comparaban contra
los gramos de las fichas de las otras berberinas y todas menos una salían «muy distintas»; y la Demanda se comparaba
contra una canela de Ceylán por ser el único lanzamiento de 2026 de su subcategoría."""
from decimal import Decimal as D
from decimal import Decimal

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


def test_precio_por_toma_cuando_las_fichas_lo_dicen(catalogo):
    """Diego, 25 nov 2026: «debe ser cuánto alcanza cada presentación». BDM se toma de 2 cápsulas: 60 tomas, $7.65 por
    toma. Las demás (1 cápsula por toma): 4 Health $2.56, Blife $4.51, Birdman $5.97, Ypenza $6.83, Nutravia $7.82; en
    medio $5.97: 28 % más caro por toma = 47."""
    f = rp.precio_anaquel(bdm(True), [(p, D("0.5")) for p in catalogo])
    assert "por toma" in f.valor and "más caro" in f.valor and "$7.65 por toma" in f.detalle and "YPENZA" in f.detalle
    assert "más barato que 1 de los 5" in f.detalle
    assert f.puntaje == 47


def test_por_capsula_avisa_si_no_sabemos_la_toma_de_los_demas(catalogo, monkeypatch):
    monkeypatch.setattr(rp, "ficha_de", lambda p: None)
    f = rp.precio_anaquel(bdm(True), [(p, D("0.5")) for p in catalogo])
    assert "por cápsula" in f.valor and f.provisional
    assert "se toma de 2 cápsulas" in f.detalle and "si se toman de 1, sale 28 % más caro por toma" in f.detalle


def test_por_capsula_contra_todas_las_berberinas_y_sin_las_faciales_de_la_marca(monkeypatch):
    """El caso real del 25 nov 2026: 7 berberinas (3 de 30 cápsulas) y faciales de Juveternal entre los parecidos."""
    lista = BERBERINAS + [("60416", "ALTUS NATURA BERBERINA ACIDO ALFA LIPOICO CANELA 30 CAP", "143.56", 30),
                          ("79653", "NATURAL WISDOM BERBERINA COMPLEX 30 CAP", "173.61", 30),
                          ("10853", "JUVETERNAL VITAMINA E FACIAL 90 CAP", "195.67", 90)]
    ps = [Producto(sku=a, descripcion=b, precio_lista_con_impuestos=D(c)) for a, b, c, _ in lista]
    monkeypatch.setattr(rp, "ficha_de", lambda p: None)
    f = rp.precio_anaquel(bdm(False), [(p, D("0.5")) for p in ps])
    assert "ALTUS" in f.detalle and "NATURAL WISDOM" in f.detalle and "FACIAL" not in f.detalle
    assert "más barato que 6 de los 7" in f.detalle and f.puntaje == 100


def test_lanzamientos_solo_de_su_mismo_tipo():
    misma = [{"sku": "1", "descripcion": "JOY NATURA CANELA DE CEYLAN 60 CAP", "por_tienda": 2.5},
             {"sku": "2", "descripcion": "NUTRAVIA BERBERINA HCI 60 CAP", "por_tienda": 1.1},
             {"sku": "3", "descripcion": "BERBERINA GOTAS 30 ML", "por_tienda": 3.0}]
    assert [x["sku"] for x in rp.lanzamientos_de_su_tipo(bdm(False), misma)] == ["2"]
    assert rp.lanzamientos_de_su_tipo(bdm(False), misma[:1]) == []


def test_fichas_sin_piezas_toman_las_capsulas_de_la_descripcion(catalogo, monkeypatch):
    """Así vienen en el servidor: la ficha dice gramos y no piezas; solo 4 Health trae piezas. Antes: 57 % más caro."""
    fichas = {p.sku: fi.Ficha(tipo="suplemento", forma="cápsulas", contenido_cantidad=D(n) / 2, contenido_unidad="g",
                              piezas=(n if p.sku == "55039" else None), ingrediente_principal="Berberina")
              for p, (_, _, _, n) in zip(catalogo, BERBERINAS)}
    monkeypatch.setattr(rp, "ficha_de", lambda p: fichas.get(p.sku))
    s = bdm(False)
    f = rp.precio_anaquel(s, [(p, D("0.5")) for p in catalogo])
    assert "por cápsula" in f.valor and "más barato" in f.valor, f.valor
    for marca in ("BLIFE", "BIRDMAN", "NUTRAVIA"):
        assert marca in f.detalle


def test_fichas_del_servidor_una_sola_con_tomas_no_manda(monkeypatch):
    """Fichas reales del servidor (25 nov 2026): piezas sí, tomas solo Altus, mg nadie. Con una sola que dice sus tomas
    no se compara por toma: se compara por cápsula contra las 7 y se avisa la otra cuenta."""
    lista = [("13898", "BERBERINA MAS CANELA 30 CAP", "206.50", 30, None), ("55039", "BERBERINA 180 CAP", "437.50", 180, None),
             ("60416", "BERBERINA ACIDO ALFA LIPOICO CANELA 30 CAP", "156.50", 30, 30),
             ("79653", "BERBERINA COMPLEX 30 CAP", "200.50", 30, None), ("82094", "BERBERINA HCL 90 CAP", "545.00", 90, None),
             ("83570", "PURE BERBERINE 180 CAP", "712.00", 180, None), ("90509", "BERBERINA HCI 60 CAP", "469.00", 60, None)]
    ps = [Producto(sku=a, descripcion=b, precio_lista_con_impuestos=D(c)) for a, b, c, _, _ in lista]
    fichas = {a: fi.Ficha(tipo="suplemento", forma="cápsulas", contenido_cantidad=D(n), contenido_unidad="pz", piezas=n,
                          porciones=po, ingrediente_principal="berberina") for a, _, _, n, po in lista}
    monkeypatch.setattr(rp, "ficha_de", lambda p: fichas.get(p.sku))
    f = rp.precio_anaquel(bdm(True), [(p, D("0.5")) for p in ps])
    assert "por cápsula" in f.valor and "más barato que 6 de los 7" in f.detalle and f.provisional
    assert "26 % más caro por toma" in f.detalle and f.puntaje == 100


def test_tipo_de_la_ficha_no_descarta_su_mismo_ingrediente(monkeypatch):
    """Tipos reales del servidor (25 nov 2026): BDM «suplemento» contra «complemento auxiliar en la diabetes»; antes
    salían «Otro tipo de producto» y la calificación quedaba contra 4 Health sola (57 % más caro)."""
    tipos = {"13898": "complemento auxiliar en la diabetes", "55039": "suplemento de berberina",
             "82094": "complemento auxiliar en la diabetes", "83570": "complemento alimenticio",
             "90509": "complemento auxiliar en la diabetes"}
    ps = [Producto(sku=a, descripcion=b, precio_lista_con_impuestos=D(c)) for a, b, c, _ in BERBERINAS]
    fichas = {p.sku: fi.Ficha(tipo=tipos[p.sku], forma="cápsulas", contenido_cantidad=D(n), contenido_unidad="pz",
                              piezas=n, ingrediente_principal="berberina") for p, (_, _, _, n) in zip(ps, BERBERINAS)}
    monkeypatch.setattr(rp, "ficha_de", lambda p: fichas.get(p.sku))
    s = bdm(False)
    s.ficha = fi.Ficha(tipo="suplemento", forma="cápsulas", contenido_cantidad=D("144"), contenido_unidad="g",
                       piezas=120, ingrediente_principal="BERBERINA + PIPERINA")
    assert all(rp.precio_cercano(s, p) for p in ps)
    f = rp.precio_anaquel(s, [(p, D("0.5")) for p in ps])
    assert "más barato" in f.valor and "por cápsula" in f.valor


def test_precio_en_dos_temas_sin_afuera_pesa_todo_el_anaquel():
    """Diego, 25 nov 2026: Precio contra anaquel y contra afuera, cada uno la mitad. Sin precios de afuera, ese tema no
    cuenta y su peso se reparte como el de cualquier factor sin datos."""
    peso = rp.PESOS_DIRECCION
    base = {"demanda": rp.Factor(80, "x", ""), "categoria": rp.Factor(80, "x", ""), "rentabilidad": rp.Factor(45, "x", "")}
    junto = {**base, "precio": rp.Factor(100, "x", "")}
    viejo = {**{f: peso[f] for f in base}, "precio": Decimal("12.5")}
    dos = {**base, "precio": rp.Factor(100, "x", ""), "precio_anaquel": rp.Factor(100, "x", ""),
           "precio_afuera": rp.Factor(None, None, "Sin precios de afuera")}
    # Antes la mitad que faltaba la tomaba el anaquel (78); ahora el tema sin datos reparte su peso entre todos (77)
    assert rp.sumar(junto, viejo)[0] == 78 and rp.sumar(dos, peso)[0] == 77
    con_afuera = {**dos, "precio_afuera": rp.Factor(50, "x", "")}
    assert rp.sumar(con_afuera, peso)[0] == round((40 + 20 + 45 * 0.125 + 100 * 0.0625 + 50 * 0.0625))


def test_dictamen_avisa_marca_propia():
    s = rp.Sujeto(tipo="idea", nombre="BDM Life Berberina + Piperina", marca="JUVETERNAL", precio=Decimal("459"),
                  costo=Decimal("236.55"), margen=Decimal("40.2"), ingrediente="Berberina", forma="Cápsula",
                  contenido="120 CAP DE 1.2G")
    vidanat = Producto(producto_id=1, sku="80565", descripcion="BERBERINA 60 CAP", marca="VIDANAT/VITAMINAS",
                       precio_lista_con_impuestos=Decimal("200"), activo=True)
    f = {"demanda": rp.Factor(80, "", ""), "precio": rp.Factor(100, "", "")}
    texto = rp.dictamen(s, "amarillo", f, [(vidanat, Decimal("0.6"))], Decimal(45))
    assert "marca propia" in texto and "BERBERINA 60 CAP" in texto


def test_google_acepta_la_linea_de_la_marca():
    """25 nov 2026: BDM Life es la línea de JUVETERNAL; «BDM» es otra marca del catálogo y Google lo rechazaba."""
    from modulos.compras import coincidencia as co

    d = "BDM Life Berberina + Piperina + Omega 9 – Metabolismo 120 CAP DE 1.2G"
    e = co.evaluar(d, "JUVETERNAL", "BDM Life Berberina + Piperina + Omega 9 120 Cápsulas", 70, {"bdm", "4 health"})
    assert e.marca is True and e.aceptada
    otra = co.evaluar(d, "JUVETERNAL", "4 Health Berberina 120 Cápsulas", 70, {"bdm", "4 health"})
    assert otra.marca is False and not otra.aceptada


def test_busqueda_sin_precios_con_regla_vieja_se_repite():
    from modulos.compras import mercado_producto as mp

    viejo = mp.Mercado.de_json('{"precios": [], "buscado_en": "' + mp.ahora().isoformat() + '", "clave": "x"}')
    assert viejo.regla == 1 and not viejo.vigente("x")
    nuevo = mp.Mercado.de_json(mp.Mercado(buscado_en=mp.ahora().isoformat(), clave="x").a_json())
    assert nuevo.vigente("x")
