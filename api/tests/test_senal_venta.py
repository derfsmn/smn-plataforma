"""Precio por dos lados y señal de venta en internet (plan aprobado por Diego el 22 nov 2026). Datos FICTICIOS."""
from decimal import Decimal

from core.config import configuracion
from modulos.compras import coincidencia as co
from modulos.compras import radar_productos as rp
from modulos.compras import senal_venta as sv
from modulos.compras.tiendas import venta_walmart


def test_niveles_de_la_senal():
    assert sv.Senal("Amazon", mas_vendido=True).puntos() == 5
    assert sv.Senal("Mercado Libre", lugar=7).puntos() == 5 and sv.Senal("Mercado Libre", lugar=15).puntos() == 3
    assert sv.Senal("Walmart", vendidos=1000, mes=True).puntos() == 5
    assert sv.Senal("Walmart", vendidos=300).puntos() == 3 and sv.Senal("Google Shopping", resenas=650).puntos() == 3
    assert sv.Senal("Google Shopping", resenas=40, calificacion=4.8).puntos() == 0
    puntos, mejor = sv.nivel([sv.Senal("Google Shopping", resenas=650), sv.Senal("Amazon", vendidos=2000, mes=True)])
    assert puntos == 5 and mejor.fuente == "Amazon"
    assert sv.nivel([]) == (0, None)
    s = sv.Senal("Mercado Libre", vendedor="TIENDA X", lugar=3, categoria="Creatinas", resenas=1200, calificacion=4.7)
    assert sv.frase(s) == "Mercado Libre (TIENDA X): lugar 3 en los más vendidos de Creatinas · 1,200 reseñas (4.7 de 5)"
    assert sv.de_lista(sv.a_dicts([s]))[0] == s


def test_senal_de_walmart_y_google():
    assert venta_walmart({"numberOfReviews": 80, "badge": "Comprado +1 mil veces el mes pasado"}) == {
        "resenas": 80, "vendidos": 1000, "mes": True, "texto": "Comprado +1 mil veces el mes pasado"}
    assert sv.venta_google({"product_rating": {"value": 4.55, "votes_count": 812}}) == {"resenas": 812, "calificacion": 4.5}
    precios = [{"precio": 200, "vendedor": "Walmart", "fuente": "sitio", "venta": {"vendidos": 1000, "mes": True}},
               {"precio": 210, "vendedor": "Otra", "fuente": "google"}]
    senales = sv.de_precios(precios)
    assert len(senales) == 1 and senales[0].fuente == "Walmart" and senales[0].puntos() == 5


def test_la_senal_suma_dentro_de_la_demanda():
    venta = [sv.Senal("Amazon", mas_vendido=True)]
    puntos, por = rp.ajuste_tendencia(None, None, venta)
    assert puntos == 5 and "se vende afuera (Amazon: Más vendido)" in por[0]
    alta = rp.Factor(100, "x", "")
    assert rp.ajuste_tendencia(12.0, alta, venta)[0] == 10  # el tope ±10 no se mueve
    d = rp.con_tendencia(rp.Factor(40, "v", "Detalle.", calculo="Calificación: 40."), None, None, venta)
    assert d.puntaje == 45 and "Amazon" in d.calculo


def _producto(sku, desc, precio, porciones=None):
    p = rp.Producto(sku=sku, descripcion=desc, precio_lista_con_impuestos=Decimal(precio))
    p._ficha = rp.fi.Ficha(porciones=porciones) if porciones else None
    return p


def test_precio_en_dos_mitades():
    s = rp.Sujeto(tipo="idea", nombre="Colágeno en polvo", precio=Decimal("600"), contenido="300 g", porciones=30)
    parecidos = [(_producto("1", "COLAGENO A 300 G", "540", 30), Decimal("0.8")),
                 (_producto("2", "COLAGENO B 300 G", "560", 30), Decimal("0.7"))]
    anaquel = rp.precio_anaquel(s, parecidos)
    # $20 por porción contra $18.33 en medio: 9 % más caro → 66
    assert anaquel.puntaje == 66 and "por porción" in anaquel.detalle and anaquel.meta == Decimal("550.00")
    internet = rp.mp.Mercado(precios=[{"precio": 650, "vendedor": "Walmart", "fuente": "sitio"}])
    f = rp.f_precio(s, parecidos, internet)
    assert f.puntaje == round((83 + 66) / 2) and "Contra afuera" in f.detalle and "nuestro anaquel" in f.detalle
    assert "(83 + 66) / 2" in f.calculo and f.meta == Decimal("650")
    # Sin precios de afuera cuenta solo el anaquel; ya lo vendemos: solo afuera
    solo = rp.f_precio(s, parecidos, None)
    assert solo.puntaje == 66 and "Solo cuenta nuestro anaquel" in solo.calculo
    mismo = _producto("9", "COLAGENO EL MISMO", "600", 30)
    ya = rp.f_precio(s, [(mismo, Decimal(1))], internet, mismo)
    assert ya.puntaje is not None and "Ya lo vendemos" in ya.detalle and "anaquel" not in ya.detalle


def test_mercado_libre_y_amazon(monkeypatch):
    cfg = configuracion()
    monkeypatch.setattr(cfg, "mercado_libre_app_id", "")
    assert "sin conectar" in sv.mercado_libre(None, "X", None, [("texto", "x")], lambda c: (None, []))[1][0]
    monkeypatch.setattr(cfg, "mercado_libre_app_id", "123")
    monkeypatch.setattr(cfg, "mercado_libre_clave", "secreto")
    sv._TOKEN.update(valor=None)
    pedidas = []

    def pedir(url, token=None, datos=None):
        pedidas.append(url)
        if "oauth" in url:
            return {"access_token": "t", "expires_in": 21600}
        if "/sites/MLM/search" in url:
            return {"results": [{"id": "MLM1", "title": "Marca Colágeno 300 g", "price": 599, "currency_id": "MXN",
                                 "permalink": "https://articulo.mercadolibre.com.mx/MLM1", "seller": {"nickname": "TIENDA X"},
                                 "category_id": "MLM9", "catalog_product_id": "MLM77", "sold_quantity": 150}]}
        if "/highlights/" in url:
            return {"content": [{"id": "MLM5", "position": 1, "type": "ITEM"}, {"id": "MLM77", "position": 4, "type": "PRODUCT"}]}
        if "/categories/" in url:
            return {"name": "Colágeno"}
        return {}

    monkeypatch.setattr(sv, "_pedir_ml", pedir)
    senales, notas, elegidos = sv.mercado_libre(None, "Colágeno", "Marca", [("texto", "Marca Colágeno 300 g")],
                                                lambda c: (c[0], []))
    assert not notas and len(elegidos) == 1
    x = senales[0]
    assert (x.vendedor, x.lugar, x.categoria, x.vendidos, x.puntos()) == ("TIENDA X", 4, "Colágeno", 150, 5)

    from modulos.compras import dataforseo as dfs
    monkeypatch.setattr(cfg, "radar_productos_amazon", True)
    monkeypatch.setattr(dfs, "configurado", lambda: [])
    item = {"type": "amazon_serp", "data_asin": "B01", "title": "Marca Colágeno 300 g", "price_from": 620, "currency": "MXN",
            "url": "https://www.amazon.com.mx/dp/B01", "rating": {"value": 4.6, "votes_count": 900},
            "is_best_seller": True, "bought_past_month": 2000}
    monkeypatch.setattr(dfs, "enviar", lambda bd, corrida, tipo, tareas: {"0": "id"} if tipo == "amazon" and
                        tareas[0]["se_domain"] == "amazon.com.mx" else {})
    monkeypatch.setattr(dfs, "recoger", lambda tipo, ids: {"0": [item]})

    class Bd:
        def add(self, x):
            self.x = x

        def commit(self):
            pass

    senales, notas, elegidos, _ = sv.amazon(Bd(), "Colágeno", "Marca", [("texto", "Marca Colágeno 300 g")],
                                            lambda c: (c[0], []), "idea 1")
    a = senales[0]
    assert a.mas_vendido and a.vendidos == 2000 and a.mes and a.resenas == 900 and isinstance(elegidos[0], co.Candidato)


def test_la_base_acepta_envios_de_amazon(base_de_pruebas):
    """22 nov 2026: la evaluación tronaba con ck_precio_envio_tipo al buscar en Amazon (faltaba la migración 0054)."""
    pytest = __import__("pytest")
    from sqlalchemy import text

    from modulos.compras import radar_productos as rp

    try:
        with rp._sesion() as bd:
            definicion = bd.execute(text("SELECT definition FROM sys.check_constraints WHERE name = 'ck_precio_envio_tipo'")).scalar()
    except Exception:  # noqa: BLE001
        pytest.skip("sin SQL Server")
    assert definicion and "amazon" in definicion
