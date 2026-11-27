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


def test_mercado_libre_dice_la_causa_verdadera(monkeypatch):
    """Revisión del 26 nov 2026 (Diego capturó la aplicación y seguía viendo «sin conectar» o «rechazó la aplicación»):
    cada falla dice su causa. Pedir permiso no es lo mismo que una búsqueda negada; una clave que no se puede leer no es
    lo mismo que no haberla capturado. Datos FICTICIOS."""
    import io
    import json
    import urllib.error

    from core import ajustes

    cfg = configuracion()
    # 1) Capturada pero no se puede leer (cifrada con otra llave): la configuración en memoria queda vacía
    monkeypatch.setattr(cfg, "mercado_libre_app_id", "")
    monkeypatch.setattr(cfg, "mercado_libre_clave", "")
    monkeypatch.setattr(ajustes, "guardados", lambda bd: {"mercado_libre_app_id": "123", "mercado_libre_clave": "x"})
    monkeypatch.setattr(ajustes, "descifrar", lambda texto: None)
    nota = sv.mercado_libre(object(), "X", None, [("texto", "x")], lambda c: (None, []))[1][0]
    assert "no se puede leer" in nota and "vuelve a capturarla" in nota
    monkeypatch.setattr(ajustes, "guardados", lambda bd: {"mercado_libre_app_id": "123"})
    assert "falta la clave secreta" in sv.mercado_libre(object(), "X", None, [("texto", "x")], lambda c: (None, []))[1][0]
    monkeypatch.setattr(ajustes, "guardados", lambda bd: {})
    assert "falta registrar" in sv.mercado_libre(object(), "X", None, [("texto", "x")], lambda c: (None, []))[1][0]

    # 2) Con la aplicación: cada error HTTP según el paso
    monkeypatch.setattr(cfg, "mercado_libre_app_id", "123")
    monkeypatch.setattr(cfg, "mercado_libre_clave", "secreto")

    def contesta(token_codigo=None, busqueda_codigo=None):
        def abrir(peticion, timeout=None):
            url = peticion.full_url
            codigo = token_codigo if url.endswith("/oauth/token") else busqueda_codigo
            if codigo:
                cuerpo = json.dumps({"error": "forbidden", "message": "mensaje de prueba"}).encode()
                raise urllib.error.HTTPError(url, codigo, "x", {}, io.BytesIO(cuerpo))
            return io.BytesIO(json.dumps({"access_token": "t", "expires_in": 21600} if url.endswith("/oauth/token")
                                         else {"results": []}).encode())
        return abrir

    def nota_con(**codigos):
        sv._TOKEN.update(valor=None)
        monkeypatch.setattr(sv.urllib.request, "urlopen", contesta(**codigos))
        return sv.mercado_libre(None, "X", None, [("texto", "x")], lambda c: (None, []))[1][0]

    n = nota_con(token_codigo=401)
    assert "rechazó la aplicación al pedir permiso (error 401: forbidden mensaje de prueba)" in n
    n = nota_con(busqueda_codigo=403)
    assert "sí dio permiso" in n and "error 403: forbidden mensaje de prueba" in n and "rechazó la aplicación" not in n
    n = nota_con(busqueda_codigo=401)
    assert "no aceptó el permiso" in n and sv._TOKEN["valor"] is None  # se pedirá uno nuevo
    assert nota_con(busqueda_codigo=500).startswith("Mercado Libre: Mercado Libre respondió con error 500")
    assert nota_con() == "Mercado Libre: no regresó resultados."


def test_busqueda_reusada_vuelve_a_preguntar_solo_a_mercado_libre(monkeypatch):
    """Revisión del 26 nov 2026: Diego capturó la aplicación de Mercado Libre y al recalcular seguía «sin conectar»,
    porque la búsqueda de afuera se reusa 7 días con sus notas. Ahora, si se hizo sin la aplicación y ya está, se le
    pregunta solo a Mercado Libre (sin DataForSEO); Google, tiendas y Amazon se quedan. Datos FICTICIOS."""
    from modulos.compras import mercado_producto as mp

    cfg = configuracion()
    previo = mp.Mercado(buscado_en="2026-11-26T10:00:00", clave="x", notas=[
        "Walmart: bloqueó la consulta automática: pidió verificar identidad",
        "Mercado Libre: sin conectar (falta registrar la aplicación en Configuración)."],
        precios=[{"precio": 300.0, "vendedor": "Chedraui", "fuente": "sitio", "titulo": "Marca Colágeno 300 g", "liga": "x"}],
        senales=[{"fuente": "Amazon", "titulo": "Marca Colágeno", "mas_vendido": True}])
    monkeypatch.setattr(cfg, "mercado_libre_app_id", "")
    assert not mp.ml_pendiente(previo)  # sin aplicación no hay nada que volver a preguntar
    monkeypatch.setattr(cfg, "mercado_libre_app_id", "123")
    monkeypatch.setattr(cfg, "mercado_libre_clave", "secreto")
    assert mp.ml_pendiente(previo)

    monkeypatch.setattr(mp.pc, "_marcas", lambda bd: set())
    ml = sv.Senal(fuente="Mercado Libre", vendedor="TIENDA X", titulo="Marca Colágeno 300 g", lugar=3)
    candidato = co.Candidato("MLM1", "Marca Colágeno 300 g", {"title": "Marca Colágeno 300 g", "price": "310",
                                                             "currency": "MXN", "seller": "Mercado Libre · TIENDA X",
                                                             "url": "https://articulo.mercadolibre.com.mx/MLM1"})
    monkeypatch.setattr(mp.sv, "mercado_libre", lambda bd, nombre, marca, consultas, elegir: ([ml], [], [candidato]))
    m = mp.refrescar_mercado_libre(None, previo, "Colágeno 300 g", "Marca", None)
    assert not any(n.startswith("Mercado Libre") for n in m.notas) and m.notas[0].startswith("Walmart")
    assert [(p["vendedor"], p["fuente"]) for p in m.precios] == [("Chedraui", "sitio"), ("Mercado Libre · TIENDA X", "mercadolibre")]
    assert {x["fuente"] for x in m.senales} == {"Amazon", "Mercado Libre"}
    assert not mp.ml_pendiente(m)


def test_amazon_se_pide_con_su_idioma():
    """26 nov 2026: DataForSEO rechazaba cada búsqueda de Amazon con «Invalid Field: 'language_name'» («Spanish»); Amazon
    México se llama «Spanish (Mexico)». Las demás búsquedas siguen con el idioma de Configuración."""
    from modulos.compras import dataforseo as dfs

    assert dfs.idioma("amazon", "Spanish") == "Spanish (Mexico)"
    assert dfs.idioma("productos", "Spanish") == "Spanish"
    assert dfs.idioma("organico", "Spanish") == "Spanish"
