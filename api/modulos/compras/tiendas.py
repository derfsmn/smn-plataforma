"""Radar de precios: búsqueda directa en Walmart, Chedraui, San Pablo y Soriana (Diego, 2026-10-20).

Cada tienda se consulta con el mismo buscador que usa su página web, como en las pruebas que Diego hizo con Codex
(carpetas Waltmart, Chedraui, San Pablo y Soriana en Documentos/SMN). Aquí solo se buscan y se leen los resultados;
decidir cuál es nuestro producto lo hace el radar con sus reglas e IA, igual que con Google.
Sin DataForSEO: no cuesta créditos. Se espera entre consultas para no saturar sus sitios."""
import json
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, quote_plus, urlencode, urljoin

NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
ESPERA = 1.0  # segundos entre consultas a la misma tienda
TIEMPO = 25


class ErrorTienda(Exception):
    """La tienda no contestó, bloqueó la consulta o cambió su formato."""


@dataclass
class Resultado:
    clave: str  # id del producto en la tienda
    titulo: str
    precio: Decimal | None
    liga: str | None = None
    imagen: str | None = None
    ean: str | None = None
    marca: str | None = None
    disponible: bool | None = None
    datos: dict = field(default_factory=dict)


def _decimal(v) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        d = Decimal(str(v))
    else:
        s = re.sub(r"[^\d.,-]", "", str(v))
        if "," in s and "." in s:
            s = s.replace(",", "")
        elif "," in s:
            partes = s.split(",")
            s = "".join(partes) if len(partes[-1]) == 3 else s.replace(",", ".")
        try:
            d = Decimal(s)
        except InvalidOperation:
            return None
    return d.quantize(Decimal("0.01")) if d > 0 else None


def _texto(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


def _primero(obj: dict, rutas: list[tuple[str, ...]]):
    for ruta in rutas:
        cur = obj
        for k in ruta:
            cur = cur.get(k) if isinstance(cur, dict) else None
        if cur not in (None, "", [], {}):
            return cur
    return None


def _liga(v, base: str) -> str | None:
    u = _texto(v)
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return urljoin(base, u)
    return u if u.startswith("http") else None


def _pedir(url: str, encabezados: dict[str, str]) -> str:
    peticion = urllib.request.Request(url, headers={"User-Agent": NAVEGADOR, "Accept-Language": "es-MX,es;q=0.9", **encabezados})
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO) as r:
            return r.read(8 * 1024 * 1024).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise ErrorTienda(f"respondió con error {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErrorTienda("no contestó") from e


def _json(texto: str) -> dict:
    try:
        datos = json.loads(texto)
    except ValueError as e:
        raise ErrorTienda("no regresó datos legibles") from e
    return datos if isinstance(datos, dict) else {}


class Tienda:
    nombre = ""
    dominio = ""
    base = ""

    def buscar(self, texto: str) -> list[Resultado]:
        raise NotImplementedError


class Chedraui(Tienda):
    """Buscador de chedraui.com.mx (Empathy), como chedraui_v4_deterministico.py."""
    nombre, dominio, base = "Chedraui", "chedraui.com.mx", "https://www.chedraui.com.mx"
    URL = "https://api.empathy.co/search/v1/query/chedraui/search"

    def buscar(self, texto: str) -> list[Resultado]:
        params = {"internal": "true", "origin": "url:url_history_pdp", "start": 0, "rows": 24, "instance": "chedraui",
                  "lang": "es-MX", "scope": "desktop", "isSpa": "true", "query": texto}
        datos = _json(_pedir(f"{self.URL}?{urlencode(params)}", {"Accept": "application/json, text/plain, */*",
                                                                   "Referer": self.base + "/", "Origin": self.base}))
        claves = ("content", "results", "products", "items")
        items = []
        for k in claves:
            v = datos.get(k)
            if isinstance(v, list):
                items = v
                break
            if isinstance(v, dict):
                items = next((v[s] for s in claves if isinstance(v.get(s), list)), [])
                if items:
                    break
        if not items:
            # Empathy los regresa dentro de otra sección («catalog»: {«content»: [...]}), como lo lee el script de Diego;
            # sin esto Chedraui salía vacío en todos los productos (corrida 2004)
            items = next((v[s] for v in datos.values() if isinstance(v, dict) for s in claves if isinstance(v.get(s), list)), [])
        salida = []
        for it in items:
            if not isinstance(it, dict):
                continue
            precio = None
            for k in ("sellingPrice", "price", "bestPrice", "salePrice", "Price"):
                v = it.get(k)
                precio = _decimal(_primero(v, [("value",), ("amount",), ("price",)]) if isinstance(v, dict) else v)
                if precio:
                    break
            clave = _texto(_primero(it, [("productId",), ("productID",), ("id",), ("sku",), ("skuId",)]))
            titulo = _texto(_primero(it, [("nameComplete",), ("productName",), ("name",), ("title",)]))
            if not clave or not titulo:
                continue
            imagen = _primero(it, [("image",), ("imageUrl",), ("images",)])
            if isinstance(imagen, list):
                imagen = imagen[0] if imagen else None
            if isinstance(imagen, dict):
                imagen = _primero(imagen, [("url",), ("imageUrl",), ("src",)])
            salida.append(Resultado(clave, titulo, precio, _liga(_primero(it, [("url",), ("link",), ("productUrl",), ("href",)]), self.base),
                                    _liga(imagen, self.base), _texto(_primero(it, [("ean",), ("EAN",), ("gtin",), ("GTIN",)])) or None,
                                    _texto(_primero(it, [("brand",), ("Brand",), ("brandName",)])) or None))
        return salida


class Soriana(Tienda):
    """Buscador de soriana.com (Constructor.io), como soriana_v3_2_deterministico.py.
    La llave es la pública que usa la página de Soriana en el navegador."""
    nombre, dominio, base = "Soriana", "soriana.com", "https://www.soriana.com"
    URL = "https://ac.cnstrc.com/v1/search"
    LLAVE = "key_dDoNxIfuzA64wKGI"

    def __init__(self):
        self.cliente = str(uuid.uuid4())

    def buscar(self, texto: str) -> list[Resultado]:
        params = {"key": self.LLAVE, "section": "Products", "num_results_per_page": 50, "page": 1, "lang": "es",
                  "origin_referrer": self.base + "/buscar", "c": "ciojs-2.1473.0", "i": self.cliente, "s": 1}
        datos = _json(_pedir(f"{self.URL}/{quote(texto, safe='')}?{urlencode(params)}",
                             {"Accept": "application/json, text/plain, */*", "Referer": self.base + "/"}))
        items = next((v for v in (_primero(datos, [("response", "results")]), datos.get("results"),
                                  _primero(datos, [("response", "sections", "Products", "results")])) if isinstance(v, list)), [])
        salida = []
        for it in items:
            if not isinstance(it, dict):
                continue
            d = it.get("data") if isinstance(it.get("data"), dict) else {}
            precio = next((p for p in (_decimal(v) for v in (it.get("price"), d.get("price"), d.get("selling_price"),
                                                                d.get("sellingPrice"), d.get("sale_price"), d.get("salePrice"))) if p), None)
            clave = _texto(_primero(it, [("item_id",), ("itemId",), ("id",)]) or _primero(d, [("id",), ("item_id",), ("sku",)]))
            titulo = _texto(_primero(it, [("value",), ("name",), ("title",)]) or _primero(d, [("name",), ("title",)]))
            if not clave or not titulo:
                continue
            salida.append(Resultado(clave, titulo, precio, _liga(it.get("url") or _primero(d, [("url",), ("product_url",)]), self.base),
                                    _liga(_primero(d, [("image_url",), ("imageUrl",), ("image",)]), self.base), None,
                                    _texto(_primero(d, [("brand",), ("brand_name",), ("marca",)])) or None))
        return salida


class SanPablo(Tienda):
    """API de farmaciasanpablo.com.mx, como san_pablo_definitivo.py."""
    nombre, dominio, base = "San Pablo", "farmaciasanpablo.com.mx", "https://www.farmaciasanpablo.com.mx"
    URL = "https://api.farmaciasanpablo.com.mx/rest/v2/fsp/products/search-sponsored"
    CAMPOS = ("FULL,products(code,name,url,summary,price(FULL),basePrice(FULL),images(FULL),stock(FULL),categories(FULL),"
              "additionalDescription,fspMetaTitle,fspMetaDescription),pagination(DEFAULT),freeTextSearch,currentQuery,keywordRedirectUrl")

    def buscar(self, texto: str) -> list[Resultado]:
        params = {"fields": self.CAMPOS, "query": texto, "pageSize": 48, "anonymousToken": str(uuid.uuid4()), "lang": "es_MX", "curr": "MXN"}
        datos = _json(_pedir(f"{self.URL}?{urlencode(params)}", {"Accept": "application/json, text/plain, */*",
                                                                   "Origin": self.base, "Referer": self.base + "/"}))
        salida = []
        for it in datos.get("products") or []:
            if not isinstance(it, dict) or not _texto(it.get("name")):
                continue
            precio = it.get("price")
            precio = _decimal(_primero(precio, [("value",), ("price",)]) if isinstance(precio, dict) else precio)
            imagenes = [i for i in it.get("images") or [] if isinstance(i, dict)]
            imagen = next((i.get("url") or i.get("imageUrl") for p in ("product", "zoom", "thumbnail") for i in imagenes
                           if p in _texto(i.get("format") or i.get("formatType")).lower()), None)
            stock = it.get("stock") if isinstance(it.get("stock"), dict) else {}
            estado = _texto(stock.get("stockLevelStatus") or stock.get("status")).lower()
            salida.append(Resultado(_texto(it.get("code")) or _texto(it.get("name")), _texto(it.get("name")), precio,
                                    _liga(it.get("url"), self.base), _liga(imagen, self.base), None, None,
                                    False if "outofstock" in estado.replace("_", "") else (True if estado else None)))
        return salida


class Walmart(Tienda):
    """Página de resultados de walmart.com.mx (datos de __NEXT_DATA__), como walmart_ollama_vision_v6.py.
    Walmart a veces bloquea consultas automáticas: entonces se reporta y no se reintenta sin fin."""
    nombre, dominio, base = "Walmart", "walmart.com.mx", "https://www.walmart.com.mx"

    def buscar(self, texto: str) -> list[Resultado]:
        html = _pedir(f"{self.base}/search?q={quote_plus(texto)}", {"Accept": "text/html,application/xhtml+xml"})
        bajo = html.lower()
        if "/blocked" in bajo or "verify you are human" in bajo:
            raise ErrorTienda("bloqueó la consulta automática")
        m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not m:
            raise ErrorTienda("cambió el formato de su página de resultados")
        datos = _json(m.group(1))
        pilas = _primero(datos, [("props", "pageProps", "initialData", "searchResult", "itemStacks")]) or []
        salida, vistos = [], set()
        for pila in pilas if isinstance(pilas, list) else []:
            for it in (pila.get("items") or []) if isinstance(pila, dict) else []:
                if not isinstance(it, dict):
                    continue
                titulo = _primero(it, [("name",), ("title",), ("productName",), ("displayName",)])
                precio = _primero(it, [("priceInfo", "currentPrice", "price"), ("priceInfo", "currentPrice", "priceString"),
                                       ("currentPrice",), ("salesPrice",), ("offerPrice",), ("price",)])
                if isinstance(precio, dict):
                    precio = _primero(precio, [("price",), ("value",), ("amount",)])
                clave = _texto(_primero(it, [("usItemId",), ("itemId",), ("productId",), ("offerId",), ("id",)]))
                liga = _liga(_primero(it, [("canonicalUrl",), ("productPageUrl",), ("productUrl",), ("url",)]), self.base)
                if not isinstance(titulo, str) or not clave or clave == "0" or clave in vistos or not liga or "/ip/" not in liga.lower():
                    continue
                vistos.add(clave)
                imagen = _primero(it, [("image",), ("imageUrl",), ("thumbnailUrl",), ("imageInfo", "thumbnailUrl")])
                if isinstance(imagen, dict):
                    imagen = _primero(imagen, [("url",), ("src",)])
                vendedor = _primero(it, [("sellerName",), ("sellerDisplayName",), ("seller", "displayName"), ("seller", "name")])
                marca = _primero(it, [("brand",), ("brandName",)])
                salida.append(Resultado(clave, _texto(titulo), _decimal(precio), liga, _liga(imagen, self.base) if isinstance(imagen, str) else None,
                                        None, _texto(marca) if isinstance(marca, str) else None, None,
                                        {"vendedor": _texto(vendedor)} if vendedor else {}))
        return salida


TIENDAS: dict[str, type[Tienda]] = {"Walmart": Walmart, "Chedraui": Chedraui, "San Pablo": SanPablo, "Soriana": Soriana}


def conectores(nombres: list[str]) -> list[Tienda]:
    """Las tiendas con búsqueda directa entre las pedidas (las demás se quedan solo con lo que traiga Google)."""
    return [TIENDAS[n]() for n in nombres if n in TIENDAS]


def buscar_con_pausa(tienda: Tienda, texto: str, ultima: list[float]) -> list[Resultado]:
    """Espera ESPERA segundos desde la consulta anterior a la misma tienda."""
    falta = ESPERA - (time.monotonic() - ultima[0])
    if falta > 0:
        time.sleep(falta)
    try:
        return tienda.buscar(texto)
    finally:
        ultima[0] = time.monotonic()
