"""Catálogo de productos del Centro de datos. El API de artículos y la tienda en línea se simulan: nunca se llama a los reales.
Todos los artículos son ficticios (SKU con prefijo EJ)."""
import json
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from core.config import configuracion
from datos import catalogo, tienda
from datos.modelos import Carga, Producto, ProductoPrecioHistorial
from tests.conftest import alta_usuario

BASE = "https://articulos.ejemplo.mx/api/articulos"  # Configuración la guarda sin "/" final


def articulo(sku, precio="100", mem="90", iva="16", ieps="0", marca="Marca EJ", **extra):
    return {"articulo": sku, "descripcion1": f"Producto de ejemplo {sku}", "departamento": "Suplementos EJ",
            "rama": "Rama EJ", "marca": marca, "subcategoria": None, "segmento": None, "clasificacion": "A",
            "proveedor": "P-EJ", "nombre": "Proveedor de ejemplo", "preciolista": precio, "preciomem": mem,
            "iva": iva, "ieps": ieps, **extra}


@pytest.fixture
def api_simulada(base_de_pruebas, monkeypatch):
    """Pone dirección y credenciales ficticias y reemplaza la petición HTTP por páginas en memoria."""
    paginas: dict[str, dict] = {}
    monkeypatch.setattr(catalogo, "_pedir", lambda url: json.loads(json.dumps(paginas[url])))
    cfg = configuracion()
    monkeypatch.setattr(cfg, "catalogo_api_url", BASE)
    monkeypatch.setattr(cfg, "catalogo_api_usuario", "usuario-ej")
    monkeypatch.setattr(cfg, "catalogo_api_contrasena", "contrasena-ej")
    return paginas


def _cargar() -> Carga:
    with Session(motor(), expire_on_commit=False) as bd:
        carga = catalogo.iniciar(bd, "API", "manual")
        assert carga
        return catalogo.ejecutar(bd, carga)


def _ejecutar(carga_id: int) -> None:
    with Session(motor()) as bd:
        catalogo.ejecutar(bd, bd.get(Carga, carga_id))


def _producto(sku) -> Producto:
    with Session(motor(), expire_on_commit=False) as bd:
        return bd.scalar(select(Producto).where(Producto.sku == sku))


def test_carga_paginada_precios_e_historial(api_simulada):
    api_simulada[BASE] = {"count": 3, "next": BASE + "/?page=2",
                          "results": [articulo("EJ-0001"), articulo("EJ-0002", ieps="8"), {"articulo": ""}]}
    api_simulada[BASE + "/?page=2"] = {"count": 3, "next": None, "results": [articulo("EJ-0003", iva=None)]}
    c = _cargar()
    assert c.estado == "completa" and c.completa and c.paginas == 2
    assert (c.creados, c.invalidos, c.total_fuente) == (3, 1, 3)

    p = _producto("EJ-0002")
    assert p.origen == "API" and p.activo and not p.datos_incompletos
    # 100 + 8 % IEPS = 108; + 16 % IVA = 125.28
    assert p.precio_lista_con_impuestos == Decimal("125.28")
    assert _producto("EJ-0003").precio_lista_con_impuestos is None  # sin IVA no se calcula

    # Segunda carga: un precio cambia, uno igual y uno desaparece
    api_simulada[BASE] = {"count": 2, "next": None, "results": [articulo("EJ-0001", precio="110"), articulo("EJ-0002", ieps="8")]}
    c = _cargar()
    assert (c.actualizados, c.sin_cambios, c.precios_cambiados, c.ausentes) == (1, 1, 1, 1)
    assert _producto("EJ-0001").precio_lista == Decimal("110")
    archivado = _producto("EJ-0003")
    assert not archivado.activo and archivado.origen == "ARCHIVADO" and archivado.descripcion  # conserva sus datos
    with Session(motor()) as bd:
        uno = _producto("EJ-0001").producto_id
        precios = bd.scalars(select(ProductoPrecioHistorial.precio_lista).where(ProductoPrecioHistorial.producto_id == uno)
                             .order_by(ProductoPrecioHistorial.historial_id)).all()
    assert precios == [Decimal("100"), Decimal("110")]

    # Vuelve a aparecer
    api_simulada[BASE] = {"count": 3, "next": None,
                          "results": [articulo("EJ-0001", precio="110"), articulo("EJ-0002", ieps="8"), articulo("EJ-0003", iva=None)]}
    c = _cargar()
    assert c.ausentes == 0 and _producto("EJ-0003").activo


def test_ieps_vacio_cuenta_como_cero(api_simulada):
    # Así llegó el 19331 (DEMOGRASS): IEPS null e IVA 16
    api_simulada[BASE] = {"count": 2, "next": None, "results": [
        articulo("EJ-0201", precio="71.5517", mem="63.7931", ieps=None),
        articulo("EJ-0202", iva=None)]}
    assert _cargar().estado == "completa"
    p = _producto("EJ-0201")
    assert p.precio_lista_con_impuestos == Decimal("83.00")
    assert p.precio_membresia_con_impuestos == Decimal("74.00")
    # Sin IVA sigue sin calcularse
    assert _producto("EJ-0202").precio_lista_con_impuestos is None


def test_carga_que_falla_no_archiva(api_simulada):
    api_simulada[BASE] = {"count": 1, "next": None, "results": [articulo("EJ-0101")]}
    assert _cargar().estado == "completa"
    # La primera página llega pero la segunda falla: nada se marca como ausente
    api_simulada[BASE] = {"count": 2, "next": BASE + "?page=2", "results": []}
    c = _cargar()
    assert c.estado == "fallida" and not c.completa and "results" not in (c.error or "")
    assert _producto("EJ-0101").activo

    # La paginación no puede salir de la dirección capturada
    api_simulada[BASE] = {"count": 1, "next": "https://otro.ejemplo.mx/robar", "results": []}
    c = _cargar()
    assert c.estado == "fallida" and "fuera de la dirección" in c.error


def test_rutas_y_permisos(admin, api_simulada, monkeypatch):
    api_simulada[BASE] = {"count": 2, "next": None,
                          "results": [articulo("EJ-0201", marca="Marca Uno EJ"), articulo("EJ-0202", marca="Marca Dos EJ")]}
    # Sin hilo aparte en la prueba: corre en el momento
    monkeypatch.setattr(catalogo, "ejecutar_aparte", lambda carga_id: _ejecutar(carga_id))
    r = admin.post("/api/datos/catalogo/cargar")
    assert r.status_code == 202, r.text
    estado = admin.get("/api/datos/catalogo").json()
    assert estado["falta_configurar"] == [] and estado["en_curso"] is None
    assert estado["cargas"][0]["estado"] == "completa" and estado["totales"]["activos"] >= 2

    lista = admin.get("/api/datos/productos", params={"q": "EJ-0201"}).json()
    assert lista["total"] == 1 and lista["productos"][0]["marca"] == "Marca Uno EJ"
    assert "Marca Dos EJ" in admin.get("/api/datos/productos/filtros").json()["marcas"]
    detalle = admin.get(f"/api/datos/productos/{lista['productos'][0]['id']}").json()
    assert detalle["fuentes"][0]["fuente"] == "API" and detalle["de_donde"]["marca"] == "API"
    assert detalle["historial"][0]["precio_lista"] == "100.0000"

    # Sin permisos del Centro de datos no se ve ni se carga
    _, otro, _ = alta_usuario(admin, rol="compras_consulta")
    assert otro.get("/api/datos/productos").status_code == 403
    assert otro.post("/api/datos/catalogo/cargar").status_code == 403


def test_sin_configurar(admin, base_de_pruebas):
    r = admin.post("/api/datos/catalogo/cargar")
    assert r.status_code == 400 and "dirección del API" in r.json()["detail"]
    assert "contraseña del API de artículos" in admin.get("/api/datos/catalogo").json()["falta_configurar"]


TIENDA = "https://tienda.ejemplo.mx"


def producto_js(handle, *variantes, vendor="Marca EJ", imagen=None):
    return {"id": abs(hash(handle)) % 10**8, "handle": handle, "title": f"Nombre comercial {handle}", "vendor": vendor,
            "type": "Tipo EJ", "featured_image": imagen, "images": [imagen] if imagen else [],
            "variants": [{"id": i + 1, "title": "Default Title", **v} for i, v in enumerate(variantes)]}


@pytest.fixture
def tienda_simulada(api_simulada, monkeypatch):
    """Tienda en línea ficticia en memoria: products.json, sitemap, productos .js y fotos del CDN."""
    respuestas: dict[str, object] = {}

    def pedir(url, metodo="GET", pausa=0):
        if url not in respuestas:
            raise tienda.NoEncontrado(url)
        r = respuestas[url]
        if isinstance(r, Exception):
            raise r
        if metodo == "HEAD":
            return 200, "image/jpeg", b""
        return 200, "application/json", r if isinstance(r, bytes) else json.dumps(r).encode()

    monkeypatch.setattr(tienda, "_pedir", pedir)
    monkeypatch.setattr(configuracion(), "tienda_url", TIENDA)
    return respuestas


def _cargar_tienda() -> Carga:
    with Session(motor(), expire_on_commit=False) as bd:
        carga = catalogo.iniciar(bd, "TIENDA", "manual")
        assert carga
        return catalogo.ejecutar(bd, carga)


def test_tienda_en_linea_codigo_de_barras_precio_e_imagen(api_simulada, tienda_simulada):
    api_simulada[BASE] = {"count": 2, "next": None, "results": [articulo("EJ-0301"), articulo("EJ-0302")]}
    assert _cargar().estado == "completa"

    t = tienda_simulada
    t[f"{TIENDA}/products.json?limit=250&page=1"] = {"products": [{"handle": "uno"}, {"handle": "dos"}]}
    t[f"{TIENDA}/products.json?limit=250&page=2"] = {"products": []}
    t[f"{TIENDA}/sitemap.xml"] = (b'<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                  b'<sitemap><loc>' + TIENDA.encode() + b'/sitemap_products_1.xml</loc></sitemap></sitemapindex>')
    t[f"{TIENDA}/sitemap_products_1.xml"] = (
        b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        b'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
        b'<url><loc>' + TIENDA.encode() + b'/products/uno</loc><image:image><image:loc>https://cdn.ejemplo.mx/x.jpg</image:loc></image:image></url>'
        b'<url><loc>' + TIENDA.encode() + b'/products/tres</loc></url></urlset>')
    t[f"{TIENDA}/products/uno.js"] = producto_js("uno", {"sku": "EJ-0301", "barcode": "7500000000011", "price": 12990,
                                                         "available": True}, vendor="Otra Marca EJ", imagen="//cdn.ejemplo.mx/uno.jpg")
    t[f"{TIENDA}/products/dos.js"] = producto_js("dos", {"sku": "EJ-0399", "price": 5000, "available": False},
                                                 {"sku": None, "price": 5000, "available": True})
    # tres sale en el sitemap pero ya no existe (404): se ignora
    t[f"{TIENDA}/cdn/shop/files/EJ-0302.jpg"] = b""

    c = _cargar_tienda()
    assert c.estado == "completa" and c.completa and c.error is None, c.error
    assert (c.total_fuente, c.paginas, c.invalidos) == (3, 3, 1)

    ambos = _producto("EJ-0301")
    assert ambos.origen == "AMBOS" and ambos.codigo_barras == "7500000000011"
    assert ambos.precio_tienda_en_linea == Decimal("129.90") and ambos.disponible_en_linea
    assert ambos.descripcion == "Producto de ejemplo EJ-0301"  # el API manda sobre el nombre de la tienda
    assert ambos.liga_imagen == "https://cdn.ejemplo.mx/uno.jpg" and ambos.liga_producto == f"{TIENDA}/products/uno"
    assert ambos.con_diferencias  # la marca no coincide entre API y tienda
    solo_tienda = _producto("EJ-0399")
    assert solo_tienda.origen == "TIENDA" and solo_tienda.precio_lista is None and not solo_tienda.disponible_en_linea
    assert _producto("EJ-0302").liga_imagen == f"{TIENDA}/cdn/shop/files/EJ-0302.jpg"  # foto por SKU

    # Si un producto no se puede leer, no se archiva nada
    t[f"{TIENDA}/products/dos.js"] = catalogo.ErrorCarga("caída")
    c = _cargar_tienda()
    assert c.estado == "completa" and not c.completa and "no se pudieron leer" in c.error
    assert _producto("EJ-0399").activo

    # Con la tienda completa otra vez y sin "dos", EJ-0399 se archiva
    t[f"{TIENDA}/products.json?limit=250&page=1"] = {"products": [{"handle": "uno"}]}
    del t[f"{TIENDA}/products/dos.js"]
    c = _cargar_tienda()
    assert c.completa and c.ausentes == 1 and not _producto("EJ-0399").activo
    assert _producto("EJ-0301").activo


def test_una_carga_a_la_vez(admin, tienda_simulada, monkeypatch):
    monkeypatch.setattr(catalogo, "ejecutar_aparte", lambda carga_id: None)  # se queda "en curso"
    assert admin.post("/api/datos/catalogo/cargar", params={"fuente": "TIENDA"}).status_code == 202
    r = admin.post("/api/datos/catalogo/cargar", params={"fuente": "API"})
    assert r.status_code == 409
    assert admin.get("/api/datos/catalogo").json()["en_curso"]["fuente"] == "TIENDA"
    with Session(motor()) as bd:
        for c in bd.scalars(select(Carga).where(Carga.estado == "en_curso")):
            c.estado = "fallida"
        bd.commit()
