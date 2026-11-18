"""Validación automática de cada precio del Radar de precios (Diego, 2026-11-17: «no quiero que se valide nada, ellos solo
se informan y deberían marcar algún producto mal ... ellos son los usuarios finales»).

Cada precio observado pasa 6 comprobaciones de identidad y un sello de precio. Solo cuenta para la mediana lo que queda
«validado». Lo «dudoso» no cuenta y el producto se vuelve a revisar la noche siguiente. Lo que se contradice («no
cuenta») tampoco, con su motivo. Compras solo marca «Está mal» con motivo: ese precio sale al momento y nunca vuelve.

Comprobaciones (cada una ok / no / sin_dato / no_aplica):
1. codigo: el código de barras de la tienda es el nuestro.
2. marca: el título trae nuestra marca (o sus siglas) y no otra marca conocida.
3. variante: misma línea (Premier, Plus…) y mismo sabor.
4. contenido: misma presentación (450 g, 60 cápsulas…).
5. piezas: no es paquete, kit ni varias piezas.
6. foto: Ollama compara la foto de la tienda con la nuestra; solo en lo que quedaría dudoso y una vez por foto.

Validado si: lo eligió una persona; o el código es el nuestro; o marca, variante, contenido y piezas están bien; o marca
y foto están bien sin contradicción. Además el sello: con liga, disponible, en pesos y sin brincar más del % configurado
contra el último precio de esa misma tienda (si brinca, esa noche no cuenta; si a la noche siguiente sigue igual, cuenta).
"""
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import configuracion
from datos.modelos import Producto
from ia import puerta
from modulos.compras import coincidencia as co
from modulos.compras import imagenes as img
from modulos.compras.modelos_precios import (PrecioCoincidencia, PrecioCorrida, PrecioMarcaMal, PrecioObservacion,
                                             PrecioTiendaCoincidencia, PrecioValidacion, PrecioVigilado)
from nucleo.modelos import ahora

log = logging.getLogger(__name__)

TAREA_FOTO = "compras.precios_imagenes"
VALIDADO, DUDOSO, NO_CUENTA = "validado", "dudoso", "no_cuenta"
COMPROBACIONES = ("codigo", "marca", "variante", "contenido", "piezas", "foto")
NOMBRES = {"codigo": "Código de barras", "marca": "Marca", "variante": "Variante y sabor", "contenido": "Contenido",
           "piezas": "Piezas", "foto": "Foto"}
MOTIVOS_MAL = {"otro_sabor": "Es otro sabor", "otro_tamano": "Es otro tamaño", "otro_producto": "Es otro producto",
               "precio_equivocado": "El precio está equivocado", "otro": "Otro motivo"}
SABORES = ("chocolate", "vainilla", "fresa", "cookies", "galleta", "mango", "limon", "naranja", "coco", "capuchino", "cafe",
           "moka", "pina", "platano", "frutos rojos", "uva", "mora", "cereza", "manzana", "durazno", "sandia", "horchata",
           "mazapan", "caramelo", "menta", "natural", "sin sabor", "neutro", "tamarindo", "jamaica", "maracuya")
BASE = {"clasico"}
MARKETPLACES = ("mercado libre", "mercadolibre", "amazon", "linio", "claro shop", "claroshop", "shein", "temu", "ebay",
                "walmart marketplace", "liverpool marketplace", "coppel")
NO_DISPONIBLE = ("out of stock", "out_of_stock", "outofstock", "sold out", "sold_out", "discontinued", "agotado",
                 "no disponible", "unavailable")
FOTO_IGUAL = """Eres un verificador de productos para retail mexicano (suplementos y naturistas).
La primera imagen es NUESTRO producto y la segunda es la que publica una tienda. Di si son exactamente el mismo producto:
misma marca, misma línea o variante, mismo sabor y mismo tamaño de empaque. Si la foto no se ve clara, contesta null.
Responde solo con este JSON: {"igual": true | false | null, "motivo": "<una frase en español>"}"""


def _ok(texto: str) -> dict:
    return {"estado": "ok", "texto": texto}


def _no(texto: str) -> dict:
    return {"estado": "no", "texto": texto}


def _sin(texto: str) -> dict:
    return {"estado": "sin_dato", "texto": texto}


def _na(texto: str) -> dict:
    return {"estado": "no_aplica", "texto": texto}


def _digitos(v) -> str:
    return re.sub(r"\D", "", str(v or "")).lstrip("0")


def _datos(o: PrecioObservacion) -> dict:
    try:
        d = json.loads(o.datos or "{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def sabores(texto: str | None) -> set[str]:
    t = f" {co.normalizar(texto)} "
    return {s for s in SABORES if f" {s} " in t}


def clave_vendedor(vendedor: str | None, dominio: str | None) -> str:
    return (dominio or "").lower().removeprefix("www.") or co.normalizar(vendedor)


@dataclass
class Identidad:
    """Lo que dice la tienda del producto del que sale este precio."""
    titulo: str | None
    extra: list[str]  # «details» y la liga de Google: a veces ahí viene el tamaño
    ean: str | None
    imagen: str | None
    origen: str  # tienda / google
    persona: bool  # lo eligió una persona en la plataforma
    ia: str | None = None  # lo que dijo la IA al elegir, si aplica


def identidad(bd: Session, o: PrecioObservacion, cache: dict) -> Identidad:
    d = _datos(o)
    extra = [str(d["details"])] if d.get("details") else []
    if o.liga:
        extra.append(re.sub(r"[-_/+]+", " ", urlparse(o.liga).path))
    if d.get("_tienda_directa") or o.tienda_coincidencia_id:
        t = cache.setdefault(("t", o.tienda_coincidencia_id),
                             bd.get(PrecioTiendaCoincidencia, o.tienda_coincidencia_id) if o.tienda_coincidencia_id else None)
        return Identidad(titulo=d.get("title") or (t.titulo if t else None), extra=extra,
                         ean=d.get("ean") or (t.ean if t else None), imagen=(t.imagen if t else None) or d.get("image"),
                         origen="tienda", persona=bool(t and t.estado == "persona"), ia=t.motivo if t and t.estado == "ia" else None)
    m = cache.setdefault(("g", o.coincidencia_id), bd.get(PrecioCoincidencia, o.coincidencia_id) if o.coincidencia_id else None)
    # Un vendedor de una publicación de Google: el título del producto es el de la publicación (el suyo es el de la tienda)
    titulo = d.get("_publicacion") if d.get("_publicacion") and not str(d["_publicacion"]).startswith("Sitio de ") else None
    titulo = titulo or d.get("product_title") or d.get("title") or (m.titulo if m else None)
    ean = d.get("gtin") or d.get("ean")
    return Identidad(titulo=titulo, extra=extra, ean=str(ean) if ean else None,
                     imagen=img.de_candidato(d) or (m.imagen if m else None), origen="google",
                     persona=bool(m and m.estado == "persona"), ia=m.motivo if m and m.estado == "ia" else None)


def huella(i: Identidad) -> str:
    return hashlib.sha256(f"{co.normalizar(i.titulo)}|{_digitos(i.ean)}|{i.imagen or ''}".encode()).hexdigest()


def comprobar(p: Producto, i: Identidad, marcas: set[str]) -> dict[str, dict]:
    """Las 5 comprobaciones de texto (la foto va aparte)."""
    titulo = i.titulo or ""
    desc = p.descripcion or ""
    textos = [titulo] + i.extra
    r: dict[str, dict] = {}
    nuestro, suyo = _digitos(p.codigo_barras), _digitos(i.ean)
    if nuestro and suyo:
        r["codigo"] = _ok("Mismo código de barras") if nuestro == suyo else _no(f"Otro código de barras ({i.ean})")
    elif not nuestro:
        r["codigo"] = _na("No tenemos código de barras")
    else:
        r["codigo"] = _sin("La tienda no muestra el código de barras")

    t = co.normalizar(titulo)
    marca = co.normalizar(co.marca_comercial(p.marca))
    if not marca:
        r["marca"] = _na("Nuestro producto no tiene marca en el catálogo")
    elif any(re.search(rf"\b{re.escape(f)}\b", t) for f in co.formas_marca(marca)):
        r["marca"] = _ok(f"Dice {co.marca_comercial(p.marca)}")
    else:
        otra = next((m for m in sorted(marcas, key=len, reverse=True)
                     if m and m != marca and len(m) > 3 and re.search(rf"\b{re.escape(m)}\b", t)), None)
        r["marca"] = _no(f"Es de otra marca ({otra})") if otra else _sin("El título no dice la marca")

    # «Clásico» es la línea base: si nuestra descripción no dice variante, cuenta como la misma (Demograss, 2026-10-20)
    nv, sv = co.variantes(desc), set().union(*(co.variantes(x) for x in textos))
    if not nv:
        sv -= BASE
    ns, ss = sabores(desc), sabores(titulo)
    if nv and sv and not nv & sv:
        r["variante"] = _no(f"Otra variante ({', '.join(sorted(sv))})")
    elif ns and ss and not ns & ss:
        r["variante"] = _no(f"Otro sabor ({', '.join(sorted(ss))})")
    elif (sv and not nv) or (nv and not sv):
        r["variante"] = _sin("No se puede saber si es la misma variante")
    elif ss and not ns:
        r["variante"] = _sin(f"La tienda dice sabor {', '.join(sorted(ss))} y nuestra descripción no dice sabor")
    elif ns and not ss:
        r["variante"] = _sin("La tienda no dice el sabor")
    else:
        r["variante"] = _ok("Misma variante y sabor" if (nv or ns) else "Sin variante ni sabor de por medio")

    if not co.presentaciones(desc):
        r["contenido"] = _na("Nuestra descripción no dice el contenido")
    else:
        distinta = next((m for x in textos if (m := co.presentacion_distinta(desc, x))), None)
        if distinta:
            r["contenido"] = _no(distinta[0].upper() + distinta[1:])
        elif any(co.presentaciones(desc) & co.presentaciones(x) for x in textos):
            r["contenido"] = _ok("Mismo contenido")
        else:
            r["contenido"] = _sin("La tienda no dice el contenido")

    pq = co.paquete(desc, titulo)
    r["piezas"] = _no(pq[0].upper() + pq[1:]) if pq else _ok("Una pieza, no es paquete")
    return r


def _bien(c: dict) -> bool:
    return c["estado"] in ("ok", "no_aplica")


def decidir(c: dict[str, dict], persona: bool) -> tuple[str, str]:
    """(resultado, motivo) con las comprobaciones (la foto puede faltar)."""
    for k in COMPROBACIONES:
        if k in c and c[k]["estado"] == "no":
            return NO_CUENTA, c[k]["texto"]
    if persona:
        return VALIDADO, "Lo eligió una persona"
    if c["codigo"]["estado"] == "ok":
        return VALIDADO, "Mismo código de barras"
    texto = all(_bien(c[k]) for k in ("marca", "variante", "contenido", "piezas"))
    if texto and not all(c[k]["estado"] == "no_aplica" for k in ("marca", "contenido")):
        return VALIDADO, "Misma marca, variante, contenido y piezas"
    if c.get("foto", {}).get("estado") == "ok" and _bien(c["marca"]) and c["variante"]["estado"] != "no":
        return VALIDADO, "La foto es la misma y el texto no se contradice"
    faltan = [NOMBRES[k].lower() for k in ("marca", "variante", "contenido") if c[k]["estado"] == "sin_dato"]
    return DUDOSO, "No se pudo confirmar " + (", ".join(faltan) if faltan else "que sea el mismo producto")


def tipo_vendedor(o: PrecioObservacion, p: Producto) -> str:
    v = co.normalizar(f"{o.vendedor} {o.vendedor_original or ''} {o.dominio or ''}")
    marca = co.normalizar(co.marca_comercial(p.marca)).replace(" ", "")
    if marca and len(marca) > 3 and marca in v.replace(" ", ""):
        return "oficial"
    if any(m.replace(" ", "") in v.replace(" ", "") for m in MARKETPLACES) or "vende " in co.normalizar(o.vendedor_original):
        return "marketplace"
    return "tienda"


def promocion(d: dict) -> bool:
    for k in ("old_price", "price_regular", "regular_price", "precio_regular", "compare_at_price"):
        if d.get(k):
            return True
    return bool(re.search(r"\b(oferta|promo|descuento|rebaja)\b", co.normalizar(str(d.get("tags") or d.get("promo") or ""))))


@dataclass
class Validador:
    """Valida los precios de una corrida. Guarda un PrecioValidacion por observación."""
    bd: Session
    corrida: PrecioCorrida
    fotos: int = field(default_factory=lambda: configuracion().precios_fotos_por_lote)
    _marcas: set[str] | None = None
    _cache: dict = field(default_factory=dict)
    _nuestras: dict = field(default_factory=dict)
    _malas: dict = field(default_factory=dict)

    def marcas(self) -> set[str]:
        if self._marcas is None:
            self._marcas = {co.normalizar(co.marca_comercial(m)) for m in self.bd.scalars(select(Producto.marca).distinct()) if m}
        return self._marcas

    def _foto_previa(self, producto_id: int, h: str) -> dict | None:
        prev = self.bd.scalars(select(PrecioValidacion).where(PrecioValidacion.producto_id == producto_id,
                                                              PrecioValidacion.huella == h)
                               .order_by(PrecioValidacion.creado_en.desc()).limit(5)).all()
        for v in prev:
            foto = (json.loads(v.comprobaciones or "{}") or {}).get("foto")
            if foto and foto.get("estado") in ("ok", "no"):
                return {**foto, "texto": foto["texto"] + " (revisada antes, la foto no cambió)"}
        return None

    def _foto(self, p: Producto, i: Identidad) -> dict:
        if self.fotos <= 0 or not configuracion().precios_comparar_imagenes:
            return _sin("No se comparó la foto")
        if not i.imagen:
            return _sin("La tienda no muestra foto")
        if p.producto_id not in self._nuestras:
            self._nuestras[p.producto_id] = img.bajar(p.imagen_cdn) or img.bajar(p.liga_imagen)
        nuestra = self._nuestras[p.producto_id]
        if not nuestra:
            return _sin("No hay foto de nuestro producto")
        suya = img.bajar(i.imagen)
        if not suya:
            return _sin("No se pudo bajar la foto de la tienda")
        self.fotos -= 1
        try:
            r = puerta.ejecutar(self.bd, TAREA_FOTO, usuario_id=None, instrucciones=FOTO_IGUAL,
                                mensaje=json.dumps({"nuestro": p.descripcion, "tienda": i.titulo}, ensure_ascii=False),
                                max_tokens=200, imagenes=[nuestra, suya])
            datos = co._json_ia(r.texto)
        except (puerta.ErrorIA, ValueError) as e:
            return _sin(f"No se pudo comparar la foto ({str(e)[:80]})")
        motivo = str(datos.get("motivo") or "")[:160]
        if datos.get("igual") is True:
            return _ok(f"La IA ve el mismo empaque. {motivo}".strip())
        if datos.get("igual") is False:
            return _no(f"La IA ve otro producto en la foto. {motivo}".strip())
        return _sin(f"La foto no se ve clara. {motivo}".strip())

    def _anterior(self, o: PrecioObservacion) -> Decimal | None:
        """Último precio de esa misma tienda para el producto en una corrida anterior (validado o no)."""
        clave = clave_vendedor(o.vendedor, o.dominio)
        filas = self.bd.execute(select(PrecioObservacion.vendedor, PrecioObservacion.dominio, PrecioObservacion.precio_comparable)
                                .join(PrecioValidacion, PrecioValidacion.observacion_id == PrecioObservacion.observacion_id)
                                .where(PrecioObservacion.producto_id == o.producto_id,
                                       PrecioObservacion.corrida_id != o.corrida_id,
                                       PrecioValidacion.resultado != NO_CUENTA)
                                .order_by(PrecioObservacion.observacion_id.desc()).limit(60)).all()
        return next((precio for v, d, precio in filas if clave_vendedor(v, d) == clave), None)

    def sello(self, o: PrecioObservacion, p: Producto) -> tuple[dict, str | None, str | None]:
        """(sello, resultado forzado, motivo). Lo forzado manda sobre la identidad."""
        d = _datos(o)
        agotado = any(t in (o.disponibilidad or "").lower() for t in NO_DISPONIBLE)
        s = {"liga": bool(o.liga), "disponible": not agotado, "moneda": o.moneda, "promocion": promocion(d),
             "vendedor": tipo_vendedor(o, p), "salto_pct": None, "anterior": None}
        if o.moneda != "MXN":
            return s, NO_CUENTA, f"Precio en {o.moneda}, no en pesos"
        if agotado:
            return s, NO_CUENTA, "Agotado"
        anterior = self._anterior(o)
        if anterior and anterior > 0:
            salto = ((o.precio_comparable - anterior) / anterior * 100).quantize(Decimal("0.1"))
            s["anterior"], s["salto_pct"] = str(anterior), str(salto)
            if abs(salto) > Decimal(str(configuracion().precios_salto_pct)):
                return s, DUDOSO, (f"El precio brincó {salto:+}% contra el anterior de esta tienda (${anterior:,.2f}); "
                                   "se confirma la noche siguiente")
        if not o.liga:
            return s, DUDOSO, "Sin liga para comprobarlo"
        return s, None, None

    def evaluar(self, p: Producto, o: PrecioObservacion) -> tuple[str, str, dict, dict, str]:
        """(resultado, motivo, comprobaciones, sello, huella) de un precio, sin guardar nada."""
        if o.es_propia:
            return NO_CUENTA, "Es nuestra tienda", {}, {}, ""
        i = identidad(self.bd, o, self._cache)
        h = huella(i)
        c = comprobar(p, i, self.marcas())
        resultado, motivo = decidir(c, i.persona)
        if resultado == DUDOSO:
            c["foto"] = self._foto_previa(p.producto_id, h) or self._foto(p, i)
            resultado, motivo = decidir(c, i.persona)
        else:
            c["foto"] = (_na("No hizo falta: ya se confirmó con lo demás") if resultado == VALIDADO
                         else _na("No hizo falta: el texto ya se contradice"))
        s, forzado, porque = self.sello(o, p)
        if forzado and resultado != NO_CUENTA:
            resultado, motivo = forzado, porque
        if p.producto_id not in self._malas:
            self._malas[p.producto_id] = marcas_mal(self.bd, p.producto_id)
        if (mal := es_mal(o, i.titulo, self._malas[p.producto_id])):
            resultado, motivo = NO_CUENTA, f"Compras lo marcó: {MOTIVOS_MAL.get(mal.motivo, mal.motivo)}" + (
                f" ({mal.nota})" if mal.nota else "")
        return resultado, motivo or "", c, s, h

    def guardar(self, o: PrecioObservacion, e: tuple[str, str, dict, dict, str]) -> PrecioValidacion | None:
        if o.es_propia or not o.observacion_id:
            return None
        resultado, motivo, c, s, h = e
        v = self.bd.get(PrecioValidacion, o.observacion_id) or PrecioValidacion(observacion_id=o.observacion_id)
        v.corrida_id, v.producto_id, v.resultado, v.motivo = o.corrida_id, o.producto_id, resultado, motivo[:400]
        v.comprobaciones, v.sello = json.dumps(c, ensure_ascii=False), json.dumps(s, ensure_ascii=False)
        v.huella, v.creado_en = h, ahora()
        self.bd.add(v)
        return v


# ---------------------------------------------------------------- «Está mal»

def marcas_mal(bd: Session, producto_id: int) -> list[PrecioMarcaMal]:
    return list(bd.scalars(select(PrecioMarcaMal).where(PrecioMarcaMal.producto_id == producto_id, PrecioMarcaMal.activo)))


def es_mal(o: PrecioObservacion, titulo: str | None, malas: list[PrecioMarcaMal]) -> PrecioMarcaMal | None:
    """La misma liga, o la misma tienda con el mismo título de producto. Nunca vuelve a contar."""
    for m in malas:
        if m.liga and o.liga and m.liga.split("?")[0] == o.liga.split("?")[0]:
            return m
        if clave_vendedor(m.vendedor, m.dominio) == clave_vendedor(o.vendedor, o.dominio) and (
                not m.titulo or co.normalizar(m.titulo) == co.normalizar(titulo)):
            return m
    return None


def cuentan(bd: Session, observaciones: list[PrecioObservacion]) -> list[PrecioObservacion]:
    """Para recalcular: solo lo validado (lo que no tiene validación es de antes y cuenta como antes) y nada marcado mal."""
    if not observaciones:
        return []
    ids = [o.observacion_id for o in observaciones if o.observacion_id]
    vals = {v.observacion_id: v for v in bd.scalars(select(PrecioValidacion).where(PrecioValidacion.observacion_id.in_(ids or [0])))}
    malas = marcas_mal(bd, observaciones[0].producto_id)
    cache: dict = {}
    salida = []
    for o in observaciones:
        v = vals.get(o.observacion_id)
        if v and v.resultado != VALIDADO:
            continue
        if malas and es_mal(o, identidad(bd, o, cache).titulo, malas):
            continue
        salida.append(o)
    return salida


# ---------------------------------------------------------------- estado del producto

def proxima(p: Producto, dias_normal: int | None = None) -> timedelta:
    cfg = configuracion()
    return timedelta(days=cfg.precios_rotacion_aa_dias if (p.clasificacion or "").strip().upper() == "AA"
                     else (dias_normal or cfg.precios_rotacion_dias))


def actualizar_producto(bd: Session, p: Producto, estado_fila: str, validados: int, vistos: int) -> None:
    """Deja en el vigilado cómo quedó la validación y cuándo se vuelve a revisar."""
    v = bd.scalar(select(PrecioVigilado).where(PrecioVigilado.producto_id == p.producto_id))
    if not v or estado_fila in ("fallido", "sin_presupuesto", "pendiente"):
        return  # no se revisó de verdad: se queda en la fila para la siguiente noche
    ya = ahora()
    v.revisado_en = ya
    if validados:
        v.validacion, v.validado_en, v.noches_sin_validar = "validado", ya, 0
        v.proxima_revision = ya + proxima(p)
        return
    v.noches_sin_validar = (v.noches_sin_validar or 0) + 1
    v.validacion = "dudoso" if vistos else "sin_referencia"
    # Lo dudoso se reintenta la noche siguiente; sin referencia dos noches seguidas, ya hasta la rotación
    if v.validacion == "dudoso" and v.noches_sin_validar < 4:
        v.proxima_revision = ya + timedelta(hours=12)
    elif v.validacion == "sin_referencia" and v.noches_sin_validar < 2:
        v.proxima_revision = ya + timedelta(hours=12)
    else:
        v.proxima_revision = ya + proxima(p)
