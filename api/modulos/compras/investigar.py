"""Investigar afuera con IA local (plan del radar inteligente, aprobado por Diego el 2026-11-17).

Diego: «tengo que gastar muy poco… la IA local no puede investigar eso conectándose a internet?». Así se hace:
1. Google normal (DataForSEO, búsqueda orgánica): de 4 a 6 búsquedas por producto. Cuesta del orden de US$0.0006 cada
   una; cuenta para el tope del radar de precios y además tiene su propio tope al mes (`TOPE_MES_USD`).
2. El código baja las páginas que salieron (solo https a sitios públicos, tamaño máximo, sin redes sociales) y saca lo
   que la página declara en datos estructurados (JSON-LD de producto: nombre, precio, marca).
3. La IA local (Ollama, tarea `compras.productos_investigar`, nunca la API externa) lee el texto de cada página y dice
   si es el mismo producto, otro de la misma marca, un sustituto u otra cosa, con precio, presentación, dosis y lo que
   promete. Cada dato vale solo si trae la cita de la página y esa cita está de verdad en la página.
4. Lo encontrado se guarda en la evaluación y se reusa 7 días; los precios del mismo producto se suman a los de Google
   Shopping y las tiendas clave.
"""
import html as html_mod
import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ia import puerta
from modulos.compras import dataforseo as dfs
from modulos.compras import precios as pc
from modulos.compras.imagenes import _host_publico
from modulos.compras.modelos_precios import PrecioCorrida
from nucleo.modelos import ahora

log = logging.getLogger("smn.compras.investigar")

TAREA = "compras.productos_investigar"
TOPE_MES_USD = Decimal("5.50")  # unos $100 MXN al mes solo para investigar (Diego, 17 nov 2026)
DIAS_VIGENCIA = 7
MAX_CONSULTAS = 6
MAX_PAGINAS = 8
MAX_BYTES = 1536 * 1024
MAX_TEXTO_IA = 5000
OMITIR = ("youtube.", "facebook.", "instagram.", "tiktok.", "pinterest.", "twitter.", "x.com", "reddit.",
          "wikipedia.", "linkedin.")
TIPOS = ("mismo", "misma_marca", "sustituto", "otro")


@dataclass
class Hallazgo:
    url: str
    dominio: str
    titulo: str
    tipo: str = "otro"  # mismo / misma_marca / sustituto / otro
    producto: str | None = None  # cómo se llama en la página
    precio: float | None = None  # con impuestos, en pesos
    presentacion: str | None = None
    dosis: str | None = None
    afirmaciones: list[str] = field(default_factory=list)
    citas: dict[str, str] = field(default_factory=dict)
    de: str = "ia"  # ia / datos (JSON-LD de la página)


@dataclass
class Investigacion:
    hallazgos: list[Hallazgo] = field(default_factory=list)
    consultas: list[str] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    costo_usd: Decimal = Decimal("0")
    buscado_en: str | None = None
    clave: str = ""

    def a_json(self) -> str:
        return json.dumps({"hallazgos": [asdict(h) for h in self.hallazgos], "consultas": self.consultas,
                           "notas": self.notas, "costo_usd": str(self.costo_usd), "buscado_en": self.buscado_en,
                           "clave": self.clave}, ensure_ascii=False)

    @classmethod
    def de_json(cls, texto: str | None) -> "Investigacion | None":
        if not texto:
            return None
        d = json.loads(texto)
        return cls(hallazgos=[Hallazgo(**h) for h in d.get("hallazgos") or []], consultas=d.get("consultas") or [],
                   notas=d.get("notas") or [], costo_usd=Decimal(d.get("costo_usd") or "0"),
                   buscado_en=d.get("buscado_en"), clave=d.get("clave") or "")

    def vigente(self, clave: str) -> bool:
        if self.clave != clave or not self.buscado_en or not any(h.tipo != "otro" for h in self.hallazgos):
            return False  # sin hallazgos (falló Google o la IA) se vuelve a intentar al recalcular
        return (ahora() - datetime.fromisoformat(self.buscado_en)).days < DIAS_VIGENCIA

    def precios_mismo(self) -> list[dict]:
        """Precios del mismo producto, en la forma de mercado_producto.Mercado.precios."""
        return [{"precio": h.precio, "vendedor": h.dominio, "fuente": "web", "titulo": (h.producto or h.titulo)[:200],
                 "liga": h.url[:500]} for h in self.hallazgos if h.tipo == "mismo" and h.precio]


# ---------------------------------------------------------------- consultas

def _limpio(texto: str | None) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9ñ.,%/$]+", " ", t).strip()


def clave_de(nombre: str, marca: str | None, contenido: str | None) -> str:
    return "|".join(_limpio(x) for x in (nombre, marca, contenido))


def consultas(nombre: str, marca: str | None, contenido: str | None, ingrediente: str | None, forma: str | None,
              codigo_barras: str | None) -> list[str]:
    """De 4 a 6 búsquedas: el producto con su precio, con su presentación, el código de barras, opiniones y lo que
    se vende parecido (para conocer sustitutos y su precio)."""
    con_marca = nombre if not marca or _limpio(marca) in _limpio(nombre) else f"{marca} {nombre}"
    salida = [f"{con_marca} precio", f"{con_marca} {contenido or ''} comprar México".replace("  ", " "),
              f"{con_marca} opiniones"]
    if codigo_barras and re.fullmatch(r"\d{8,14}", codigo_barras):
        salida.append(codigo_barras)
    if ingrediente or forma:
        salida.append(f"{ingrediente or nombre} {forma or ''} precio México".replace("  ", " "))
    salida.append(f"{con_marca} ingredientes dosis")
    vistas, unicas = set(), []
    for c in salida:
        if (k := _limpio(c)) and k not in vistas:
            vistas.add(k)
            unicas.append(c.strip())
    return unicas[:MAX_CONSULTAS]


# ---------------------------------------------------------------- páginas

class _Redirecciones(urllib.request.HTTPRedirectHandler):
    """Sigue hasta 3 redirecciones, solo a https y a sitios públicos."""
    max_redirections = 3

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlparse(newurl)
        if u.scheme != "https" or not u.hostname or not _host_publico(u.hostname):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_abridor = urllib.request.build_opener(_Redirecciones)


def bajar(url: str) -> str | None:
    """El HTML de la página o None. Solo https a sitios públicos y hasta 1.5 MB."""
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname or not _host_publico(u.hostname):
        return None
    try:
        peticion = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; SMN-Plataforma)",
                                                        "Accept": "text/html", "Accept-Language": "es-MX,es"})
        with _abridor.open(peticion, timeout=10) as r:
            if "html" not in (r.headers.get("Content-Type") or ""):
                return None
            return r.read(MAX_BYTES).decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


_JSONLD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)


def _productos_jsonld(html: str) -> list[dict]:
    """Lo que la página declara de sí misma como producto (schema.org Product)."""
    salida = []

    def recorrer(x):
        if isinstance(x, list):
            for y in x:
                recorrer(y)
        elif isinstance(x, dict):
            tipo = x.get("@type")
            if tipo == "Product" or (isinstance(tipo, list) and "Product" in tipo):
                salida.append(x)
            for k in ("@graph", "itemListElement", "item", "mainEntity"):
                if k in x:
                    recorrer(x[k])

    for bloque in _JSONLD.findall(html):
        try:
            recorrer(json.loads(bloque.strip()))
        except ValueError:
            continue
    return salida


def _precio_jsonld(p: dict) -> Decimal | None:
    ofertas = p.get("offers")
    for o in ofertas if isinstance(ofertas, list) else [ofertas]:
        if not isinstance(o, dict):
            continue
        if (o.get("priceCurrency") or "MXN").upper() != "MXN":
            continue
        for k in ("price", "lowPrice"):
            try:
                v = Decimal(str(o.get(k)).replace(",", ""))
            except (InvalidOperation, TypeError):
                continue
            if v > 0:
                return v
    return None


def texto_de(html: str) -> str:
    """Texto legible de la página (sin scripts, estilos ni menús)."""
    t = re.sub(r"<(script|style|noscript|svg|nav|footer|header)\b.*?</\1>", " ", html, flags=re.I | re.S)
    t = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", t, flags=re.I)
    t = html_mod.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def _recorte(texto: str, palabras: set[str]) -> str:
    """Lo más útil de la página para la IA: los párrafos que mencionan el producto, hasta MAX_TEXTO_IA letras."""
    if len(texto) <= MAX_TEXTO_IA:
        return texto
    lineas = texto.split("\n")
    marcadas = [i for i, linea in enumerate(lineas) if palabras & set(_limpio(linea).split())]
    elegidas: list[int] = []
    for i in marcadas:
        elegidas += [j for j in range(max(0, i - 1), min(len(lineas), i + 3)) if j not in elegidas]
    salida = "\n".join(lineas[i] for i in elegidas) or texto
    return salida[:MAX_TEXTO_IA]


# ---------------------------------------------------------------- IA local

INSTRUCCIONES = """Eres investigador de mercado de una cadena de tiendas naturistas en México.
Te doy un producto que estamos evaluando y el texto de una página de internet. Contesta solo con lo que dice la página.
- tipo: "mismo" si la página vende o describe ESTE producto (misma marca y mismo producto; puede ser otro tamaño),
  "misma_marca" si es otro producto de la misma marca, "sustituto" si es otro producto que sirve para lo mismo,
  "otro" si no tiene que ver.
- producto: cómo se llama el producto en la página.
- precio: precio en pesos mexicanos tal como aparece, con "cita" (el pedazo exacto de la página donde está).
- presentacion: contenido o tamaño (ej. "300 g", "60 cápsulas"), con "cita".
- dosis: dosis o porción, con "cita".
- afirmaciones: hasta 4 cosas que la página dice que hace el producto, cada una con su "cita" exacta.
Copia las citas EXACTAS (de 2 a 15 palabras, sin cambiar letras). Si algo no está en la página, no lo pongas.
Contesta SOLO un JSON así: {"tipo": "mismo", "producto": "...", "precio": {"valor": 599, "cita": "..."},
"presentacion": {"valor": "...", "cita": "..."}, "dosis": {"valor": "...", "cita": "..."},
"afirmaciones": [{"texto": "...", "cita": "..."}]}"""


def _cita_ok(cita: str, pagina_limpia: str) -> bool:
    c = _limpio(cita)
    return len(c) >= 3 and c in pagina_limpia


def _numero_en(n: Decimal, cita: str) -> bool:
    for x in re.findall(r"\d[\d,]*(?:\.\d+)?", cita):
        try:
            if Decimal(x.replace(",", "")) == n:
                return True
        except InvalidOperation:
            continue
    return False


def leer_pagina(bd: Session, producto: dict, h: Hallazgo, texto: str) -> None:
    """La IA local lee la página y llena el hallazgo; solo queda lo que trae cita que está en la página."""
    palabras = set(_limpio(" ".join(str(v) for v in producto.values() if v)).split())
    pagina = _recorte(texto, {p for p in palabras if len(p) > 3})
    mensaje = json.dumps({"producto": producto, "pagina": {"sitio": h.dominio, "titulo": h.titulo, "texto": pagina}},
                         ensure_ascii=False)
    r = puerta.ejecutar(bd, TAREA, usuario_id=None, instrucciones=INSTRUCCIONES, mensaje=mensaje, max_tokens=700,
                        esfuerzo="low", contexto=puerta.ventana(INSTRUCCIONES, mensaje, salida=700))
    d = json.loads(r.texto[r.texto.find("{"):r.texto.rfind("}") + 1])
    if not isinstance(d, dict):
        return
    limpia = _limpio(texto)
    if d.get("tipo") in TIPOS:
        h.tipo = d["tipo"]
    if isinstance(d.get("producto"), str) and _limpio(d["producto"]) in limpia:
        h.producto = d["producto"][:200]
    precio = d.get("precio")
    if h.precio is None and isinstance(precio, dict) and _cita_ok(str(precio.get("cita") or ""), limpia):
        try:
            v = Decimal(str(precio.get("valor")).replace(",", "").replace("$", ""))
        except InvalidOperation:
            v = None
        if v and v > 0 and _numero_en(v, str(precio["cita"])):
            h.precio, h.citas["precio"] = float(v), str(precio["cita"])[:200]
    for campo in ("presentacion", "dosis"):
        x = d.get(campo)
        if isinstance(x, dict) and x.get("valor") and _cita_ok(str(x.get("cita") or ""), limpia):
            setattr(h, campo, str(x["valor"])[:80])
            h.citas[campo] = str(x["cita"])[:200]
    for a in (d.get("afirmaciones") or [])[:4]:
        if isinstance(a, dict) and a.get("texto") and _cita_ok(str(a.get("cita") or ""), limpia):
            h.afirmaciones.append(str(a["cita"])[:200])


# ---------------------------------------------------------------- todo junto

def _google(bd: Session, inv: Investigacion, referencia: str) -> list[dict]:
    """Resultados orgánicos de Google de cada consulta: [{url, titulo, descripcion, consulta}]."""
    if falta := dfs.configurado():
        inv.notas.append("No se buscó en Google: falta " + ", ".join(falta) + " en Configuración.")
        return []
    maximo = dfs.maximo_tarea("organico", 10) * len(inv.consultas)
    if dfs.gasto_mes_tipo(bd, "organico") + maximo > TOPE_MES_USD:
        inv.notas.append(f"No se buscó en Google: se llegó al tope del mes para investigar (US$ {TOPE_MES_USD}).")
        return []
    corrida = PrecioCorrida(fecha=pc.hoy_local(), origen=pc.PRODUCTO, estado="en_curso", productos=1,
                            lista=json.dumps({"investigar": referencia}, ensure_ascii=False))
    bd.add(corrida)
    bd.commit()
    salida: list[dict] = []
    try:
        ids = dfs.enviar(bd, corrida, "organico", [{"keyword": c, "depth": 10, "tag": str(i)}
                                                   for i, c in enumerate(inv.consultas)])
        for tag, items in dfs.recoger("organico", ids).items():
            if isinstance(items, str):
                inv.notas.append(f"Google: {items}.")
                continue
            for it in items:
                if it.get("type") == "organic" and it.get("url"):
                    salida.append({"url": str(it["url"]), "titulo": str(it.get("title") or "")[:200],
                                   "descripcion": str(it.get("description") or "")[:400],
                                   "consulta": inv.consultas[int(tag)]})
        corrida.estado = "completa"
    except dfs.ErrorDataForSEO as e:
        inv.notas.append(f"Google: {e}")
        corrida.estado, corrida.error = "fallida", str(e)[:1000]
    corrida.terminado_en = ahora()
    inv.costo_usd += corrida.costo_usd or Decimal("0")
    bd.commit()
    return salida


def _elegir_paginas(resultados: list[dict]) -> list[dict]:
    """Hasta 8 páginas, de sitios distintos y en el orden en que Google las dio por consulta."""
    vistos, elegidas = set(), []
    por_consulta: dict[str, list[dict]] = {}
    for r in resultados:
        por_consulta.setdefault(r["consulta"], []).append(r)
    rondas = max((len(v) for v in por_consulta.values()), default=0)
    for i in range(rondas):
        for lista in por_consulta.values():
            if i >= len(lista):
                continue
            r = lista[i]
            u = urlparse(r["url"])
            host = (u.hostname or "").lower().removeprefix("www.")
            if u.scheme != "https" or not host or host in vistos or any(o in host for o in OMITIR):
                continue
            vistos.add(host)
            elegidas.append({**r, "dominio": host})
            if len(elegidas) >= MAX_PAGINAS:
                return elegidas
    return elegidas


def investigar(bd: Session, *, nombre: str, marca: str | None, contenido: str | None, ingrediente: str | None,
               forma: str | None, codigo_barras: str | None, referencia: str) -> Investigacion:
    """Busca el producto en Google, lee las páginas y deja lo que se pudo probar. Nunca lanza."""
    inv = Investigacion(buscado_en=ahora().isoformat(), clave=clave_de(nombre, marca, contenido),
                        consultas=consultas(nombre, marca, contenido, ingrediente, forma, codigo_barras))
    producto = {"nombre": nombre, "marca": marca, "contenido": contenido, "ingrediente": ingrediente, "forma": forma}
    for r in _elegir_paginas(_google(bd, inv, referencia)):
        h = Hallazgo(url=r["url"], dominio=r["dominio"], titulo=r["titulo"])
        html = bajar(r["url"])
        if not html:
            inv.notas.append(f"{r['dominio']}: no dejó leer la página.")
            continue
        for p in _productos_jsonld(html)[:1]:
            if (precio := _precio_jsonld(p)) is not None:
                h.precio, h.de = float(precio), "datos"
                h.citas["precio"] = f"{p.get('name') or ''} ${precio}".strip()
                h.producto = str(p.get("name") or "")[:200] or None
        try:
            leer_pagina(bd, producto, h, texto_de(html))
        except (puerta.ErrorIA, ValueError, AttributeError) as e:
            inv.notas.append(f"{r['dominio']}: la IA local no pudo leer la página ({str(e)[:80]}).")
            if h.de != "datos":
                continue
        if h.tipo == "otro":
            h.tipo = por_titulo(h, nombre, marca)
        if h.de == "datos" and h.tipo == "otro":
            h.precio = None  # un precio de la página que la IA no reconoce como el producto no cuenta
        inv.hallazgos.append(h)
    otros = [h.dominio for h in inv.hallazgos if h.tipo == "otro"]
    if otros:
        inv.notas.append(f"Leímos {len(otros)} página(s) que no hablan de este producto ni de un sustituto: "
                         + ", ".join(otros[:6]) + ".")
    if not inv.hallazgos and not inv.notas:
        inv.notas.append("Google no regresó páginas que se pudieran leer.")
    return inv


_VACIAS = {"con", "de", "del", "la", "el", "en", "para", "y", "sin", "por", "mas", "plus"}


def por_titulo(h: Hallazgo, nombre: str, marca: str | None) -> str:
    """Si la IA dijo «otro» pero el título o el nombre de la página trae la marca, se reconoce sin IA: con todas las
    palabras del nombre es el mismo producto; si no, otro de la misma marca (Wonu, 17 nov 2026: la IA local no
    reconocía «Wonu Creatina con Inositol» como «Creatina + Inositol»)."""
    m = _limpio(marca)
    texto = f" {_limpio(h.titulo)} {_limpio(h.producto)} "
    if not m or f" {m} " not in texto:
        return "otro"
    palabras = [w for w in _limpio(nombre).split() if len(w) > 2 and w not in _VACIAS]
    tipo = "mismo" if palabras and all(w[:6] in texto for w in palabras) else "misma_marca"
    h.citas.setdefault("tipo", (h.producto or h.titulo)[:200])
    h.producto = h.producto or h.titulo[:200]
    return tipo


def resumen_para_ia(inv: Investigacion | None) -> list[dict]:
    """Lo encontrado afuera para el asistente: cada dato con su sitio y su cita."""
    if not inv:
        return []
    salida = []
    for h in inv.hallazgos:
        if h.tipo == "otro":
            continue
        d = {"sitio": h.dominio, "liga": h.url, "es": {"mismo": "el mismo producto", "misma_marca": "otro de la misma marca",
                                                         "sustituto": "un sustituto"}[h.tipo]}
        if h.producto:
            d["producto"] = h.producto
        if h.precio:
            d["precio"] = f"${h.precio:,.2f}"
        for c in ("presentacion", "dosis"):
            if getattr(h, c):
                d[c] = getattr(h, c)
        if h.afirmaciones:
            d["dice"] = h.afirmaciones
        salida.append(d)
    return salida
