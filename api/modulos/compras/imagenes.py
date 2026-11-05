"""Radar de precios: bajar fotos de productos para que la IA las compare (caso Demograss Premier / clásico, 2026-10-20).

Solo https, solo de Google Shopping o de nuestra tienda en línea, sin seguir redirecciones y con tamaño máximo."""
import base64
import ipaddress
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

from core.config import configuracion

MAX_BYTES = 3 * 1024 * 1024
HOSTS = ("gstatic.com", "googleusercontent.com", "shopify.com")


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_abridor = urllib.request.build_opener(_SinRedirecciones)


def permitida(url: str | None) -> bool:
    u = urlparse(url or "")
    host = (u.hostname or "").lower()
    tienda = (urlparse(configuracion().tienda_url or "").hostname or "").lower()
    permitidos = HOSTS + ((tienda,) if tienda else ())
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in permitidos)


def bajar(url: str | None) -> str | None:
    """La imagen en base64 (como la pide Ollama) o None si no se pudo o no es una imagen."""
    if not permitida(url):
        return None
    try:
        with _abridor.open(urllib.request.Request(url, headers={"User-Agent": "SMN-Plataforma", "Accept": "image/jpeg,image/png"}), timeout=8) as r:
            if not (r.headers.get("Content-Type") or "").startswith("image/"):
                return None
            datos = r.read(MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    if not datos or len(datos) > MAX_BYTES:
        return None
    if not datos.startswith((b"\xff\xd8\xff", b"\x89PNG")):  # solo JPEG y PNG, que Ollama lee seguro (error 400 en la corrida 1005)
        return None
    return base64.b64encode(datos).decode()


def de_candidato(datos: dict) -> str | None:
    """Primera foto de un resultado de Google Shopping."""
    for u in datos.get("product_images") or []:
        if isinstance(u, str) and u:
            return u
    return datos.get("image_url") if isinstance(datos.get("image_url"), str) else None


MAX_PAGINA = 1024 * 1024
_META = re.compile(r"<meta\b[^>]*>", re.I)
_ATRIBUTO = re.compile(r"""(\w[\w:-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def _host_publico(host: str) -> bool:
    """Que el nombre apunte solo a direcciones públicas de internet (nunca a la red interna)."""
    try:
        ipaddress.ip_address(host)
        return False  # una IP escrita a mano no; solo nombres
    except ValueError:
        pass
    try:
        direcciones = {i[4][0] for i in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)}
    except OSError:
        return False
    return bool(direcciones) and all(ipaddress.ip_address(d.split("%")[0]).is_global for d in direcciones)


def de_pagina(url: str | None) -> str | None:
    """La foto que la página de un producto dice que es la suya (og:image o twitter:image), para mostrarla en Buscar
    oportunidades (Diego, 2026-10-28). Solo https a sitios públicos, sin seguir redirecciones y con tamaño máximo; si la
    tienda no deja leer la página, None."""
    u = urlparse(url or "")
    if u.scheme != "https" or not u.hostname or not _host_publico(u.hostname):
        return None
    try:
        peticion = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; SMN-Plataforma)",
                                                        "Accept": "text/html", "Accept-Language": "es-MX,es"})
        with _abridor.open(peticion, timeout=8) as r:
            if "html" not in (r.headers.get("Content-Type") or ""):
                return None
            html = r.read(MAX_PAGINA).decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    encontradas = {}
    for meta in _META.findall(html):
        attrs = {k.lower(): (a or b) for k, a, b in _ATRIBUTO.findall(meta)}
        nombre = (attrs.get("property") or attrs.get("name") or "").lower()
        if nombre in ("og:image:secure_url", "og:image", "twitter:image") and attrs.get("content"):
            encontradas.setdefault(nombre, attrs["content"].strip())
    for nombre in ("og:image:secure_url", "og:image", "twitter:image"):
        foto = encontradas.get(nombre, "")
        if foto.startswith("//"):
            foto = "https:" + foto
        if foto.startswith("https://") and len(foto) <= 800:
            return foto
    return None
