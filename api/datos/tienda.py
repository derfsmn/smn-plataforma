"""Carga de la tienda en línea (Shopify) al catálogo de productos. Solo páginas públicas, sin llaves.

Igual que el proyecto Radar Precios:
1. Descubre los productos con /products.json (por páginas) y con el sitemap de productos.
2. Lee cada producto con /products/<handle>.js, que trae cada variante con SKU, código de barras,
   precio en centavos y disponibilidad. Una pausa entre peticiones para no saturar la tienda.
3. Cada variante con SKU se guarda como fuente TIENDA del producto con ese SKU.
4. Imagen: revisa si existe la foto <SKU>.jpg en el CDN de la tienda (cada 7 días por producto).
Solo si se leyeron todos los productos sin errores se marca como ausente lo que ya no está en la tienda.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree

from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session, selectinload

from core.config import configuracion
from datos import catalogo
from datos.catalogo import ErrorCarga
from datos.modelos import Carga, Producto
from nucleo.modelos import ahora

log = logging.getLogger("smn.datos.tienda")

PAUSA = 0.5  # segundos entre peticiones a las páginas de la tienda
PAUSA_IMAGEN = 0.15  # las fotos salen del CDN, que aguanta más
MAX_PAGINAS = 200
REVISAR_IMAGEN_CADA = timedelta(days=7)
REINTENTAR_IMAGEN_CON_ERROR = timedelta(hours=1)
AGENTE = "SMN-Transformacion-digital/1.0 (catalogo de productos; paginas publicas)"


class NoEncontrado(Exception):
    pass


_ultima = [0.0]
_turno = threading.Lock()


def _pedir(url: str, metodo: str = "GET", pausa: float = PAUSA) -> tuple[int, str, bytes]:
    """Petición pública con pausa y 3 intentos. Devuelve (estado, tipo de contenido, cuerpo)."""
    for intento in range(3):
        with _turno:
            espera = pausa - (time.monotonic() - _ultima[0])
            if espera > 0:
                time.sleep(espera)
            _ultima[0] = time.monotonic()
        try:
            peticion = urllib.request.Request(url, method=metodo, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(peticion, timeout=30) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read() if metodo == "GET" else b""
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                raise NoEncontrado(url) from e
            if (e.code < 500 and e.code != 429) or intento == 2:
                raise ErrorCarga(f"La tienda en línea respondió con error {e.code}.") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if intento == 2:
                raise ErrorCarga("No se pudo conectar con la tienda en línea.") from e
        time.sleep(2 + intento * 3)
    raise ErrorCarga("No se pudo conectar con la tienda en línea.")


def _json(url: str):
    try:
        return json.loads(_pedir(url)[2])
    except ValueError as e:
        raise ErrorCarga("La tienda en línea no respondió con datos válidos.") from e


def _absoluta(liga) -> str | None:
    if isinstance(liga, dict):
        liga = liga.get("src")
    if not isinstance(liga, str) or not liga:
        return None
    return "https:" + liga if liga.startswith("//") else liga


# ---------------------------------------------------------------- descubrimiento

def handles_products_json(base: str) -> list[str]:
    handles: list[str] = []
    for pagina in range(1, MAX_PAGINAS + 1):
        datos = _json(f"{base}/products.json?limit=250&page={pagina}")
        productos = datos.get("products") if isinstance(datos, dict) else None
        if not isinstance(productos, list):
            raise ErrorCarga("products.json de la tienda no trae la lista de productos.")
        if not productos:
            return handles
        handles += [str(p["handle"]) for p in productos if isinstance(p, dict) and p.get("handle")]
    raise ErrorCarga("products.json de la tienda tiene demasiadas páginas; la carga se detuvo.")


def handles_sitemap(base: str) -> list[str]:
    """Productos que no salen en products.json pero sí en el sitemap."""
    raiz = ElementTree.fromstring(_pedir(f"{base}/sitemap.xml")[2])
    mapas = [n.text.strip() for n in raiz.findall(".//{*}loc") if n.text and "sitemap_products" in n.text]
    handles: list[str] = []
    for mapa in mapas:
        if urlparse(mapa).hostname != urlparse(base).hostname:
            continue
        for url in ElementTree.fromstring(_pedir(mapa)[2]).findall(".//{*}url"):
            # Solo el <loc> directo de cada <url>; los <image:loc> anidados son fotos, no productos
            loc = next((c for c in url if c.tag.rsplit("}", 1)[-1] == "loc"), None)
            ruta = urlparse((loc.text or "").strip()).path if loc is not None else ""
            if "/products/" in ruta:
                handle = unquote(ruta.split("/products/", 1)[1].strip("/"))
                if handle and "/" not in handle:
                    handles.append(handle)
    return handles


# ---------------------------------------------------------------- productos

def variantes(base: str, producto: dict) -> list[dict]:
    """Un producto de /products/<handle>.js -> una fila por variante, con lo que el catálogo necesita."""
    handle = str(producto.get("handle") or "")
    lista = [v for v in (producto.get("variants") or []) if isinstance(v, dict)]
    portada = _absoluta(producto.get("featured_image")) or next(
        (_absoluta(i) for i in (producto.get("images") or []) if _absoluta(i)), None)
    filas = []
    for v in lista:
        liga = f"{base}/products/{quote(handle)}" + (f"?variant={v.get('id')}" if len(lista) > 1 else "")
        filas.append({
            "sku": v.get("sku"), "codigo_barras": v.get("barcode"), "precio_centavos": v.get("price"),
            "disponible": v.get("available"), "titulo": producto.get("title"), "variante": v.get("title"),
            "marca": producto.get("vendor"), "tipo": producto.get("type") or producto.get("product_type"),
            "liga": liga, "imagen": _absoluta(v.get("featured_image")) or portada,
            "producto_id": producto.get("id"), "variante_id": v.get("id"), "handle": handle,
        })
    return filas


def cargar_tienda(bd: Session, carga: Carga) -> Carga:
    base = configuracion().tienda_url.rstrip("/")
    try:
        if not base:
            raise ErrorCarga("Falta capturar en Configuración la dirección de la tienda en línea.")
        handles = list(dict.fromkeys(handles_products_json(base)))
        try:
            vistos_json = set(handles)
            handles += [h for h in dict.fromkeys(handles_sitemap(base)) if h not in vistos_json]
            sitemap_ok = True
        except (ErrorCarga, NoEncontrado, ElementTree.ParseError) as e:
            sitemap_ok = False
            log.warning("No se pudo leer el sitemap de la tienda: %s", e)
        carga.total_fuente = len(handles)
        bd.commit()

        vistos: set[str] = set()
        fallidos = 0
        for handle in handles:
            try:
                producto = _json(f"{base}/products/{quote(handle)}.js")
                if not isinstance(producto, dict) or not producto.get("id"):
                    raise ErrorCarga("Producto con datos inválidos")
            except NoEncontrado:
                carga.paginas += 1  # lo quitaron entre el listado y la lectura
                bd.commit()
                continue
            except ErrorCarga as e:
                fallidos += 1
                carga.paginas += 1
                bd.commit()
                log.info("No se pudo leer el producto %s de la tienda: %s", handle, e)
                continue
            catalogo.procesar(bd, carga, variantes(base, producto), vistos)  # suma 1 a paginas = productos leídos

        revisar_imagenes(bd, base)
        avisos = []
        if fallidos:
            avisos.append(f"{fallidos} productos de la tienda no se pudieron leer")
        if not sitemap_ok:
            avisos.append("no se pudo leer el sitemap")
        if avisos:
            carga.error = ("; ".join(avisos) + ". Por eso no se archivó nada en esta carga.")[:1000]
        else:
            carga.completa = True
            catalogo.marcar_ausentes(bd, carga)
        carga.estado = "completa"
    except Exception as e:  # noqa: BLE001 - toda falla queda registrada en la carga
        bd.rollback()
        carga = bd.get(Carga, carga.carga_id)
        carga.estado = "fallida"
        carga.error = (str(e) if isinstance(e, ErrorCarga) else f"Error inesperado: {type(e).__name__}")[:1000]
        if not isinstance(e, ErrorCarga):
            log.exception("La carga %s de la tienda falló", carga.carga_id)
    carga.fin_en = ahora()
    bd.commit()
    return carga


# ---------------------------------------------------------------- imágenes por SKU

def revisar_imagen(base: str, sku: str) -> tuple[str, str | None]:
    """¿Existe <base>/cdn/shop/files/<SKU>.jpg? -> (DISPONIBLE | NO_HAY | ERROR, liga)."""
    url = f"{base}/cdn/shop/files/{quote(sku, safe='')}.jpg"
    try:
        estado, tipo, _ = _pedir(url, "HEAD", PAUSA_IMAGEN)
    except NoEncontrado:
        return "NO_HAY", None
    except ErrorCarga:
        return "ERROR", None
    return ("DISPONIBLE", url) if 200 <= estado < 300 and tipo.lower().startswith("image/") else ("ERROR", None)


def revisar_imagenes(bd: Session, base: str) -> int:
    """Revisa la foto por SKU de los productos activos que no se han revisado en 7 días."""
    limite = ahora() - REVISAR_IMAGEN_CADA
    pendientes = bd.scalars(select(Producto).where(
        Producto.activo == true(), or_(Producto.imagen_revisada_en.is_(None), Producto.imagen_revisada_en < limite))
        .options(selectinload(Producto.fuentes))).all()
    if not pendientes:
        return 0
    with ThreadPoolExecutor(max_workers=4) as hilos:
        resultados = list(hilos.map(lambda p: revisar_imagen(base, p.sku), pendientes))
    for producto, (estado, liga) in zip(pendientes, resultados):
        if estado == "ERROR":
            # Una falla pasajera no borra una foto ya encontrada; se vuelve a intentar en una hora
            producto.imagen_revisada_en = ahora() - REVISAR_IMAGEN_CADA + REINTENTAR_IMAGEN_CON_ERROR
            continue
        producto.imagen_cdn, producto.imagen_revisada_en = liga, ahora()
        catalogo.resolver(bd, producto, None)
    bd.commit()
    return len(pendientes)
