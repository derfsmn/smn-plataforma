"""¿Se vende afuera? Señal de venta en internet del producto nuevo (plan aprobado por Diego el 22 nov 2026).

Junta, siempre con su liga, lo que prueba que el producto se vende en internet:
- Mercado Libre (API oficial, con la aplicación que registra SMN): quién lo vende, su precio y si está en los más
  vendidos de su categoría (lugar 1 a 20).
- Amazon México (DataForSEO, cuenta para el tope del mes): «Más vendido», «Amazon's Choice», compras del mes pasado y
  reseñas.
- Walmart (ya se lee su sitio) y Google Shopping (ya se paga): reseñas, calificación y «Comprado +X veces».
Lo que no se encuentra se deja vacío y no resta. La señal suma dentro de la Demanda: fuerte +5, media +3 (con el tope
de ±10 del ajuste por tendencia).
"""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from core.config import configuracion
from modulos.compras import coincidencia as co

log = logging.getLogger("smn.compras.senal_venta")

FUERTE, MEDIA = 5, 3
VENDIDOS_FUERTE, VENDIDOS_MEDIA, RESENAS_MEDIA, TOP = 1000, 100, 500, 10
ML_API = "https://api.mercadolibre.com"
TIEMPO = 20


@dataclass
class Senal:
    fuente: str  # Mercado Libre / Amazon / Walmart / Google Shopping
    vendedor: str | None = None
    titulo: str | None = None
    liga: str | None = None
    precio: float | None = None
    mas_vendido: bool = False  # etiqueta «Más vendido» o lugar 1 de su categoría
    eleccion: bool = False  # «Amazon's Choice»
    lugar: int | None = None  # lugar en los más vendidos de su categoría
    categoria: str | None = None
    vendidos: int | None = None  # lo que dice la página (mínimo de «+5 mil»)
    mes: bool = False  # los vendidos son del último mes
    resenas: int | None = None
    calificacion: float | None = None

    def puntos(self) -> int:
        if self.mas_vendido or (self.lugar and self.lugar <= TOP) or (self.vendidos or 0) >= VENDIDOS_FUERTE:
            return FUERTE
        if (self.vendidos or 0) >= VENDIDOS_MEDIA or (self.resenas or 0) >= RESENAS_MEDIA or self.lugar:
            return MEDIA
        return 0

    def texto(self) -> str:
        partes = []
        if self.mas_vendido:
            partes.append("Más vendido")
        if self.lugar:
            partes.append(f"lugar {self.lugar} en los más vendidos" + (f" de {self.categoria}" if self.categoria else ""))
        if self.eleccion:
            partes.append("Amazon's Choice")
        if self.vendidos:
            partes.append(f"+{self.vendidos:,} {'comprados el mes pasado' if self.mes else 'vendidos'}")
        if self.resenas:
            partes.append(f"{self.resenas:,} reseñas" + (f" ({self.calificacion:.1f} de 5)" if self.calificacion else ""))
        return " · ".join(partes)

    @classmethod
    def de_dict(cls, d: dict) -> "Senal":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def de_lista(lista: list[dict] | None) -> list[Senal]:
    return [Senal.de_dict(d) for d in lista or [] if isinstance(d, dict)]


def nivel(senales: list[Senal]) -> tuple[int, Senal | None]:
    """Puntos que suma a la Demanda (la señal más fuerte) y cuál fue."""
    con = [s for s in senales if s.puntos()]
    if not con:
        return 0, None
    mejor = max(con, key=lambda s: (s.puntos(), s.vendidos or 0, s.resenas or 0))
    return mejor.puntos(), mejor


def frase(s: Senal) -> str:
    return f"{s.fuente}{f' ({s.vendedor})' if s.vendedor and s.vendedor != s.fuente else ''}: {s.texto()}"


# ---------------------------------------------------------------- de lo que ya se lee (Walmart y Google Shopping)

def venta_google(item: dict) -> dict | None:
    r = item.get("product_rating") if isinstance(item.get("product_rating"), dict) else item.get("rating")
    venta = {}
    if isinstance(r, dict):
        if isinstance(r.get("votes_count"), (int, float)) and r["votes_count"] > 0:
            venta["resenas"] = int(r["votes_count"])
        if isinstance(r.get("value"), (int, float)) and r["value"] > 0:
            venta["calificacion"] = round(float(r["value"]), 1)
    if "resenas" not in venta and isinstance(item.get("reviews_count"), (int, float)) and item["reviews_count"] > 0:
        venta["resenas"] = int(item["reviews_count"])
    return venta or None


def de_precios(precios: list[dict]) -> list[Senal]:
    """Las señales que ya trae cada precio (reseñas y comprados de Walmart y Google Shopping)."""
    salida = []
    for p in precios:
        v = p.get("venta")
        if not isinstance(v, dict) or p.get("fuente") in ("mercadolibre", "amazon"):
            continue
        fuente = "Google Shopping" if p.get("fuente") == "google" else str(p.get("vendedor") or "Tienda")
        salida.append(Senal(fuente=fuente, vendedor=p.get("vendedor"), titulo=p.get("titulo"), liga=p.get("liga"),
                            precio=p.get("precio"), vendidos=v.get("vendidos"), mes=bool(v.get("mes")),
                            resenas=v.get("resenas"), calificacion=v.get("calificacion")))
    return salida


# ---------------------------------------------------------------- Mercado Libre (API oficial)

_TOKEN: dict = {"valor": None, "vence": 0.0, "app": None}


class ErrorML(Exception):
    pass


def _pedir_ml(url: str, token: str | None = None, datos: bytes | None = None) -> dict:
    encabezados = {"Accept": "application/json"}
    if token:
        encabezados["Authorization"] = f"Bearer {token}"
    if datos is not None:
        encabezados["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=datos, headers=encabezados), timeout=TIEMPO) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ErrorML("Mercado Libre rechazó la aplicación; revisa el App ID y la clave secreta en Configuración") from e
        if e.code == 404:
            return {}
        raise ErrorML(f"Mercado Libre respondió con error {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise ErrorML("no se pudo conectar con Mercado Libre") from e


def _token_ml() -> str:
    cfg = configuracion()
    if _TOKEN["valor"] and _TOKEN["app"] == cfg.mercado_libre_app_id and time.monotonic() < _TOKEN["vence"]:
        return _TOKEN["valor"]
    cuerpo = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": cfg.mercado_libre_app_id,
                                     "client_secret": cfg.mercado_libre_clave}).encode()
    r = _pedir_ml(f"{ML_API}/oauth/token", datos=cuerpo)
    if not r.get("access_token"):
        raise ErrorML("Mercado Libre no dio permiso a la aplicación")
    _TOKEN.update(valor=r["access_token"], app=cfg.mercado_libre_app_id,
                  vence=time.monotonic() + max(60, int(r.get("expires_in") or 21600) - 300))
    return _TOKEN["valor"]


def _lugar_ml(token: str, categoria_id: str, ids: set[str]) -> int | None:
    datos = _pedir_ml(f"{ML_API}/highlights/MLM/category/{urllib.parse.quote(categoria_id)}", token)
    for c in datos.get("content") or []:
        if isinstance(c, dict) and str(c.get("id")) in ids:
            return int(c.get("position") or 0) or None
    return None


def mercado_libre(bd: Session, nombre: str, marca: str | None, consultas: list[tuple[str, str]], elegir) -> tuple[list[Senal], list[str], list]:
    """Busca el producto en Mercado Libre México. Regresa señales, notas y los candidatos elegidos (para sumar su precio)."""
    cfg = configuracion()
    if not cfg.mercado_libre_app_id or not cfg.mercado_libre_clave:
        return [], ["Mercado Libre: sin conectar (falta registrar la aplicación en Configuración)."], []
    try:
        token = _token_ml()
        cands: dict[str, co.Candidato] = {}
        for estrategia, texto in consultas:
            datos = _pedir_ml(f"{ML_API}/sites/MLM/search?{urllib.parse.urlencode({'q': texto, 'limit': 20})}", token)
            for i, r in enumerate(datos.get("results") or []):
                if not isinstance(r, dict) or not r.get("id") or not r.get("title"):
                    continue
                vendedor = (r.get("seller") or {}).get("nickname") if isinstance(r.get("seller"), dict) else None
                c = cands.setdefault(str(r["id"]), co.Candidato(str(r["id"]), str(r["title"]), {
                    "title": r["title"], "price": str(r.get("price")) if r.get("price") else None,
                    "currency": r.get("currency_id") or "MXN", "seller": f"Mercado Libre · {vendedor}" if vendedor else "Mercado Libre",
                    "url": r.get("permalink"), "rank_absolute": i + 1, "ml": r}))
                c.estrategias.add(estrategia)
        if not cands:
            return [], ["Mercado Libre: no regresó resultados."], []
        elegido, iguales = elegir(list(cands.values()))
        if not elegido:
            return [], ["Mercado Libre: ningún resultado es claramente el mismo producto."], []
        senales = []
        nombres_cat: dict[str, str | None] = {}
        for c in [elegido, *iguales][:5]:
            r = c.datos["ml"]
            lugar = None
            cat = r.get("category_id")
            if cat:
                ids = {str(r["id"])} | ({str(r["catalog_product_id"])} if r.get("catalog_product_id") else set())
                lugar = _lugar_ml(token, str(cat), ids)
                if lugar and cat not in nombres_cat:
                    nombres_cat[cat] = _pedir_ml(f"{ML_API}/categories/{urllib.parse.quote(str(cat))}", token).get("name")
            vendidos = r.get("sold_quantity") if isinstance(r.get("sold_quantity"), int) and r["sold_quantity"] > 0 else None
            vendedor = c.datos["seller"].replace("Mercado Libre · ", "")
            senales.append(Senal(fuente="Mercado Libre", vendedor=vendedor, titulo=c.titulo[:200], liga=r.get("permalink"),
                                 precio=float(r["price"]) if r.get("price") else None, mas_vendido=lugar == 1, lugar=lugar,
                                 categoria=nombres_cat.get(cat), vendidos=vendidos))
        return senales, [], [elegido, *iguales]
    except ErrorML as e:
        return [], [f"Mercado Libre: {e}."], []
    except Exception:  # noqa: BLE001 - Mercado Libre nunca detiene la evaluación
        log.exception("Señal de venta: falló Mercado Libre para «%s»", nombre)
        return [], ["Mercado Libre: no se pudo leer su respuesta."], []


# ---------------------------------------------------------------- Amazon México (DataForSEO)

def amazon(bd: Session, nombre: str, marca: str | None, consultas: list[tuple[str, str]], elegir, referencia: str
           ) -> tuple[list[Senal], list[str], list, Decimal]:
    from modulos.compras import dataforseo as dfs
    from modulos.compras import precios as pc
    from modulos.compras.modelos_precios import PrecioCorrida
    from nucleo.modelos import ahora

    if not configuracion().radar_productos_amazon:
        return [], [], [], Decimal(0)
    if falta := dfs.configurado():
        return [], ["Amazon: no se buscó, falta " + ", ".join(falta) + " en Configuración."], [], Decimal(0)
    texto = next((t for e, t in consultas if e != "barras"), consultas[0][1])
    corrida = PrecioCorrida(fecha=pc.hoy_local(), origen=pc.PRODUCTO, estado="en_curso", productos=1,
                            lista=json.dumps({"radar_productos": referencia, "amazon": True}, ensure_ascii=False))
    bd.add(corrida)
    bd.commit()
    senales, notas, elegidos = [], [], []
    try:
        ids = dfs.enviar(bd, corrida, "amazon", [{"keyword": texto, "depth": 40, "se_domain": "amazon.com.mx", "tag": "0"}])
        for items in dfs.recoger("amazon", ids).values():
            if isinstance(items, str):
                notas.append(f"Amazon: {items}.")
                continue
            cands = []
            for it in items:
                if it.get("type") not in ("amazon_serp", "amazon_paid") or not it.get("data_asin") or not it.get("title"):
                    continue
                cands.append(co.Candidato(str(it["data_asin"]), str(it["title"]), {
                    "title": it["title"], "price": str(it.get("price_from")) if it.get("price_from") else None,
                    "currency": it.get("currency") or "MXN", "seller": "Amazon", "url": it.get("url"),
                    "rank_absolute": it.get("rank_absolute"), "amazon": it}))
            elegido, iguales = elegir(cands) if cands else (None, [])
            if not elegido:
                notas.append("Amazon: ningún resultado es claramente el mismo producto." if cands else "Amazon no regresó resultados.")
                continue
            for c in [elegido, *iguales][:3]:
                it = c.datos["amazon"]
                r = it.get("rating") if isinstance(it.get("rating"), dict) else {}
                comprados = it.get("bought_past_month")
                senales.append(Senal(fuente="Amazon", vendedor="Amazon", titulo=c.titulo[:200], liga=it.get("url"),
                                     precio=float(it["price_from"]) if it.get("price_from") else None,
                                     mas_vendido=bool(it.get("is_best_seller")), eleccion=bool(it.get("is_amazon_choice")),
                                     vendidos=int(comprados) if isinstance(comprados, (int, float)) and comprados > 0 else None,
                                     mes=isinstance(comprados, (int, float)) and comprados > 0,
                                     resenas=int(r["votes_count"]) if isinstance(r.get("votes_count"), (int, float)) and r["votes_count"] else None,
                                     calificacion=round(float(r["value"]), 1) if isinstance(r.get("value"), (int, float)) and r["value"] else None))
            elegidos = [elegido, *iguales]
        corrida.estado = "completa"
    except dfs.ErrorDataForSEO as e:
        notas.append(f"Amazon: no se buscó, {e}")
        corrida.estado, corrida.error = "fallida", str(e)[:1000]
    corrida.terminado_en = ahora()
    bd.commit()
    return senales, notas, elegidos, corrida.costo_usd or Decimal(0)


def a_dicts(senales: list[Senal]) -> list[dict]:
    return [{k: v for k, v in asdict(s).items() if v not in (None, False)} for s in senales]

