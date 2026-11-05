"""Lectura de los buscadores de Walmart, Chedraui, San Pablo y Soriana. Las respuestas son ficticias, con la forma que
leen los scripts de Diego (Codex); nunca se llama a los sitios reales."""
import json
from decimal import Decimal

import pytest

from modulos.compras import tiendas as td


@pytest.fixture
def pedir(monkeypatch):
    llamadas = []

    def falso(url, encabezados):
        llamadas.append(url)
        return falso.respuesta
    monkeypatch.setattr(td, "_pedir", falso)
    falso.llamadas = llamadas
    return falso


def test_chedraui(pedir):
    pedir.respuesta = json.dumps({"catalog": {}, "content": {"products": [
        {"productId": "C1", "nameComplete": "Naturej Moringa EJ 100 cápsulas", "sellingPrice": 129.5, "ean": "7500000000017",
         "brand": "Naturej", "url": "/moringa-ej/p", "images": [{"url": "https://img.ej/c1.jpg"}]},
        {"productId": "C2", "name": "Sin precio EJ"}]}})
    r = td.Chedraui().buscar("moringa ej")
    assert [x.clave for x in r] == ["C1", "C2"] and r[0].precio == Decimal("129.50") and r[0].ean == "7500000000017"
    assert r[0].liga == "https://www.chedraui.com.mx/moringa-ej/p" and r[1].precio is None
    assert "query=moringa+ej" in pedir.llamadas[0] and "instance=chedraui" in pedir.llamadas[0]


def test_chedraui_con_productos_dentro_de_otra_seccion(pedir):
    """Corrida 2004: Empathy regresa los productos dentro de «catalog»; antes salía vacío en todos."""
    pedir.respuesta = json.dumps({"catalog": {"numFound": 1, "content": [
        {"productId": "C9", "nameComplete": "Aceite de Ajo San Lucas 500 ml", "price": {"value": 79.0}}]}})
    r = td.Chedraui().buscar("san lucas aceite de ajo")
    assert [x.clave for x in r] == ["C9"] and r[0].precio == Decimal("79.00")


def test_soriana(pedir):
    pedir.respuesta = json.dumps({"response": {"results": [
        {"value": "Naturej Moringa EJ 100 caps", "data": {"id": "S1", "price": "$135.00", "url": "/moringa-ej-s1.html",
                                                          "image_url": "https://img.ej/s1.jpg", "brand": "Naturej"}}]}})
    r = td.Soriana().buscar("moringa ej")
    assert r[0].clave == "S1" and r[0].precio == Decimal("135.00") and r[0].liga == "https://www.soriana.com/moringa-ej-s1.html"
    assert pedir.llamadas[0].startswith("https://ac.cnstrc.com/v1/search/moringa%20ej?")


def test_san_pablo(pedir):
    pedir.respuesta = json.dumps({"products": [
        {"code": "SP1", "name": "Moringa EJ 100 cápsulas", "url": "/moringa/p/SP1", "price": {"value": 1150.0},
         "images": [{"format": "thumbnail", "url": "/img/t.jpg"}, {"format": "product", "url": "/img/p.jpg"}],
         "stock": {"stockLevelStatus": "outOfStock"}}]})
    r = td.SanPablo().buscar("moringa")
    assert r[0].precio == Decimal("1150.00") and r[0].imagen == "https://www.farmaciasanpablo.com.mx/img/p.jpg"
    assert r[0].disponible is False


def test_walmart_y_bloqueo(pedir):
    datos = {"props": {"pageProps": {"initialData": {"searchResult": {"itemStacks": [{"items": [
        {"usItemId": "W1", "name": "Naturej Moringa EJ 100 cápsulas", "priceInfo": {"currentPrice": {"price": 118}},
         "canonicalUrl": "/ip/moringa-ej/W1", "image": "https://img.ej/w1.jpg", "sellerName": "Vendedor EJ"},
        {"usItemId": "0", "name": "Anuncio", "canonicalUrl": "/ip/x/0"},
        {"usItemId": "W2", "name": "Sin liga de producto", "canonicalUrl": "/browse/x"}]}]}}}}}
    pedir.respuesta = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(datos)}</script></html>'
    r = td.Walmart().buscar("moringa ej")
    assert [x.clave for x in r] == ["W1"] and r[0].precio == Decimal("118.00") and r[0].datos == {"vendedor": "Vendedor EJ"}
    pedir.respuesta = "<html>Please verify you are human</html>"
    with pytest.raises(td.ErrorTienda, match="bloqueó"):
        td.Walmart().buscar("moringa ej")


def test_precios_con_formato():
    assert td._decimal("$1,234.50") == Decimal("1234.50") and td._decimal("99,90") == Decimal("99.90")
    assert td._decimal("1,234") == Decimal("1234.00") and td._decimal(0) is None and td._decimal(True) is None
