"""Radar de precios: la corrida, sin intervención de nadie.

1. Toma los productos vigilados (del catálogo del Centro de datos) con el precio que tienen hoy.
2. Coincidencia: si el producto ya tiene una vigente se reutiliza (no se paga de nuevo). Si no, se busca en
   Google Shopping primero por código de barras y, si no basta, por marca y descripción (coincidencia.py).
   Lo dudoso lo revisa la IA; si no queda segura, el producto queda "sin coincidencia" y no se compara.
3. Tiendas directas (Diego, 2026-10-20): cada producto se busca también en el sitio de Walmart, Chedraui, San Pablo y
   Soriana (tiendas.py); el producto se elige con las mismas reglas e IA. Su precio cuenta como un vendedor más y, si
   Google trae la misma tienda, se queda el del sitio.
4. Precios: DataForSEO Sellers trae el precio de cada vendedor. Cada precio se guarda una vez (solo inserción).
5. Comparación: nuestro precio lista y membresía con impuestos contra la mediana de la competencia
   (sin nuestra tienda, solo en pesos y disponibles).
6. Aviso en la campana si en algún producto estamos más caros que el mercado por más del % configurado.
Si una coincidencia se queda dos corridas seguidas sin precios, se invalida y la siguiente corrida busca de nuevo.
Una persona puede marcar "no es este producto": esa coincidencia nunca se vuelve a elegir.
"""
import json
import logging
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from statistics import median
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.config import configuracion
from datos.modelos import Producto, ProductoFuente
from ia import puerta
from modulos.compras import coincidencia as co
from modulos.compras import dataforseo as dfs
from modulos.compras import imagenes as img
from modulos.compras import tiendas as td
from modulos.compras.modelos_precios import (VIGENTES, PrecioCoincidencia, PrecioCorrida, PrecioCorridaProducto,
                                             PrecioObservacion, PrecioTiendaCoincidencia, PrecioVendedor, PrecioVigilado)
from nucleo.modelos import Modulo, Permiso, RolPermiso, Usuario, UsuarioRol, ahora
from nucleo.notificaciones import notificar

log = logging.getLogger("uvicorn.error")

VER = "compras.precios.ver"
ADMINISTRAR = "compras.precios.administrar"
TAREA_IA = "compras.precios_coincidencia"
TAREA_IMAGENES = "compras.precios_imagenes"
MAX_FOTOS = 6
FALLOS_PARA_INVALIDAR = 2
NO_DISPONIBLE = ("out of stock", "out_of_stock", "outofstock", "sold out", "sold_out", "discontinued", "agotado", "no disponible", "unavailable")
CENTAVO = Decimal("0.01")
MAX_IGUALES = 9  # otras publicaciones del mismo producto que se guardan
# Un vendedor fuera de este rango contra nuestro precio casi siempre vende otra presentación del mismo producto
# (Google agrupa variantes: caso de Diego, Birdman 510 g con vendedores de la de 34 g a 42-60 pesos)
PRECIO_RELATIVO_MINIMO, PRECIO_RELATIVO_MAXIMO = Decimal("0.35"), Decimal("3")


def zona() -> ZoneInfo:
    return ZoneInfo(configuracion().precios_zona_horaria or "America/Mexico_City")


def hoy_local() -> date:
    return datetime.now(zona()).date()


def _decimal(valor) -> Decimal | None:
    if isinstance(valor, dict):
        valor = valor.get("current") if valor.get("current") is not None else valor.get("value")
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor).replace(",", "")).quantize(CENTAVO)
    except (InvalidOperation, ValueError):
        return None


def limite(propio: Decimal | None) -> Decimal:
    """Límite del semáforo: el del producto vigilado o, si no tiene, el general de Configuración."""
    return propio if propio is not None else Decimal(str(configuracion().precios_alerta_pct))


def limites_por_producto(bd: Session) -> dict[int, Decimal]:
    return {pid: lim for pid, lim in bd.execute(select(PrecioVigilado.producto_id, PrecioVigilado.limite_pct)
                                                .where(PrecioVigilado.limite_pct.is_not(None)))}


def color(dif: Decimal | None, propio: Decimal | None = None) -> str | None:
    """Semáforo: verde = igual o más barato que la mediana; amarillo = más caro hasta el límite; rojo = arriba."""
    if dif is None:
        return None
    return "verde" if dif <= 0 else "amarillo" if dif <= limite(propio) else "rojo"


def nuestro(fila: PrecioCorridaProducto) -> tuple[Decimal | None, str | None]:
    """Nuestro precio para el semáforo: el precio lista con impuestos o, si el catálogo no lo tiene, el de la tienda en línea."""
    if fila.precio_lista is not None:
        return fila.precio_lista, "lista"
    if fila.precio_tienda is not None:
        return fila.precio_tienda, "tienda"
    return None, None


def dif_nuestro(fila: PrecioCorridaProducto) -> Decimal | None:
    """Diferencia de nuestro precio contra la mediana (también para corridas guardadas antes de usar la tienda)."""
    if fila.dif_lista_mediana_pct is not None:
        return fila.dif_lista_mediana_pct
    return diferencia_pct(nuestro(fila)[0], fila.mediana)


def diferencia_pct(nuestro: Decimal | None, mercado: Decimal | None) -> Decimal | None:
    """(nuestro / mercado - 1) × 100. Positivo = estamos más caros."""
    if nuestro is None or not mercado:
        return None
    return ((Decimal(nuestro) / Decimal(mercado) - 1) * 100).quantize(CENTAVO)


# ---------------------------------------------------------------- vendedores

def _clave(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()
    t = re.sub(r"^www\.", "", t)
    return " ".join(re.sub(r"[^a-z0-9.-]+", " ", t).split())


class Vendedores:
    """Une los nombres con que aparece cada vendedor (Amazon, amazon.com.mx, Amazon MX...)."""

    def __init__(self, bd: Session):
        self.alias: dict[str, PrecioVendedor] = {}
        for v in bd.scalars(select(PrecioVendedor).where(PrecioVendedor.activo == true())):
            for a in [v.nombre, *(v.alias or "").split(",")]:
                if a.strip():
                    self.alias[_clave(a)] = v
        self.dominios_propios = [d.strip().lower().removeprefix("www.")
                                 for d in configuracion().precios_dominios_propios.split(",") if d.strip()]

    def normalizar(self, nombre: str, dominio: str | None, liga: str | None) -> tuple[str, str | None, bool]:
        """(nombre normalizado, dominio, es propio)."""
        dominio = dominio or (urlparse(liga).netloc if liga else None)
        dominio = _clave(dominio) if dominio else None
        if dominio and re.match(r"(.+\.)?google\.", dominio):  # la liga de un resultado de búsqueda es de Google, no de la tienda
            dominio = None
        opciones = [_clave(nombre)] + ([dominio, dominio.split(".")[0]] if dominio else [])
        v = next((self.alias[o] for o in opciones if o in self.alias), None)
        normal = v.nombre if v else re.sub(r"\s+(mx|mexico|méxico)$", "", nombre.strip(), flags=re.IGNORECASE)
        propio = bool(v and v.es_propio) or bool(dominio and any(dominio == d or dominio.endswith("." + d) for d in self.dominios_propios))
        return normal[:200], dominio, propio


def tiendas_clave() -> list[str]:
    return [t.strip() for t in configuracion().precios_tiendas_clave.split(",") if t.strip()]


def tienda_clave(vendedor: str | None, dominio: str | None, claves: list[str] | None = None) -> str | None:
    """Cuál de las tiendas clave es este vendedor («San Pablo Farmacia», farmaciasanpablo.com.mx → San Pablo); None si ninguna."""
    texto = re.sub(r"[^a-z0-9]", "", _clave(f"{vendedor or ''} {dominio or ''}"))
    for t in claves if claves is not None else tiendas_clave():
        if (k := re.sub(r"[^a-z0-9]", "", _clave(t))) and k in texto:
            return t
    return None


def tiendas_directas() -> list[str]:
    """Las tiendas que se buscan en su propio sitio (Configuración), solo las que tienen conector."""
    return [t.strip() for t in configuracion().precios_tiendas_directas.split(",") if t.strip() in td.TIENDAS]


def tienda_vigente(bd: Session, producto_id: int, tienda: str) -> PrecioTiendaCoincidencia | None:
    return bd.scalar(select(PrecioTiendaCoincidencia).where(
        PrecioTiendaCoincidencia.producto_id == producto_id, PrecioTiendaCoincidencia.tienda == tienda,
        PrecioTiendaCoincidencia.estado.in_(VIGENTES)).order_by(PrecioTiendaCoincidencia.tienda_coincidencia_id.desc()))


def _rechazados_tienda(bd: Session, producto_id: int, tienda: str) -> set[str]:
    return set(bd.scalars(select(PrecioTiendaCoincidencia.clave).where(
        PrecioTiendaCoincidencia.producto_id == producto_id, PrecioTiendaCoincidencia.tienda == tienda,
        PrecioTiendaCoincidencia.estado == "rechazada")))


def de_tienda_que_cuenta():
    """Condición: la observación salió del sitio de una tienda y nadie dijo que ese no es el producto."""
    return PrecioObservacion.tienda_coincidencia_id.in_(
        select(PrecioTiendaCoincidencia.tienda_coincidencia_id).where(PrecioTiendaCoincidencia.estado != "rechazada"))


def del_renglon(coincidencia_id):
    """Condición para las observaciones de un renglón: las de su publicación de Google y las de los sitios de las tiendas."""
    return (PrecioObservacion.coincidencia_id == coincidencia_id) | de_tienda_que_cuenta()


def obs_tiendas(bd: Session, corrida_id: int, producto_ids) -> dict[int, list[PrecioObservacion]]:
    salida: dict[int, list[PrecioObservacion]] = {}
    for o in bd.scalars(select(PrecioObservacion).where(PrecioObservacion.corrida_id == corrida_id,
                                                        PrecioObservacion.producto_id.in_(list(producto_ids)),
                                                        de_tienda_que_cuenta())):
        salida.setdefault(o.producto_id, []).append(o)
    return salida


def _barras(v) -> str:
    return re.sub(r"\D", "", str(v or "")).lstrip("0")


def candidato_tienda(tienda: td.Tienda, r: td.Resultado, posicion: int) -> co.Candidato:
    return co.Candidato(r.clave, r.titulo, {"title": r.titulo, "price": str(r.precio) if r.precio else None, "currency": "MXN",
                                           "seller": tienda.nombre, "url": r.liga, "rank_absolute": posicion, "ean": r.ean})


@dataclass
class Trabajo:
    """Lo que necesita el hilo de una tienda para buscar un producto (sin tocar la base)."""
    producto_id: int
    descripcion: str | None
    marca: str | None
    barras: str
    consultas: list[tuple[str, str]]
    vigente: str | None  # clave del producto ya elegido en esa tienda
    rechazados: set[str]


FALLAS_PARA_PARAR = 3  # si una tienda falla tantas veces seguidas (bloqueo, caída), ya no se le pregunta en esta corrida


# ---------------------------------------------------------------- corrida

def _con_permiso(bd: Session, permiso: str) -> list[int]:
    return list(bd.scalars(
        select(Usuario.usuario_id).distinct()
        .join(UsuarioRol, UsuarioRol.usuario_id == Usuario.usuario_id)
        .join(RolPermiso, RolPermiso.rol_id == UsuarioRol.rol_id)
        .join(Permiso, Permiso.permiso_id == RolPermiso.permiso_id)
        .where(Permiso.codigo == permiso, Usuario.estatus == "activo")))


# Lo que hace cada corrida en este momento y las que una persona pidió detener (la API corre en un solo proceso)
FASE: dict[int, str] = {}
AVANCE: dict[int, dict] = {}  # paso de la corrida, cuántos van y en qué productos (Diego, 2026-10-26: que se vea en qué va)
DETENER: set[int] = set()
PASOS = ("Buscar cada producto en Google Shopping", "Buscar en los sitios de las tiendas",
         "Traer los precios de los vendedores", "Guardar resultados")


def _olvidar(corrida_id: int) -> None:
    FASE.pop(corrida_id, None)
    AVANCE.pop(corrida_id, None)


def _lista(nombres: list[str], maximo: int = 3) -> str:
    """«A», «B», «C» y 5 más."""
    vistos = [f"«{n[:50]}»" for n in nombres[:maximo]]
    resto = len(nombres) - len(vistos)
    return ", ".join(vistos) + (f" y {resto} más" if resto > 0 else "")
DETENIDA = "Detenida por"  # inicio del error de una corrida que alguien detuvo: no se reintenta sola


class Detenida(Exception):
    pass


def cerrar_huerfanas(bd: Session) -> int:
    """Al arrancar la API: una corrida «en curso» quedó a medias porque la plataforma se reinició."""
    abiertas = bd.scalars(select(PrecioCorrida).where(PrecioCorrida.estado == "en_curso")).all()
    for c in abiertas:
        _cerrar(bd, c, "La plataforma se reinició a media corrida. Lo que ya se pagó a DataForSEO quedó en «Corridas y gasto».")
    bd.commit()
    return len(abiertas)


def _cerrar(bd: Session, c: PrecioCorrida, motivo: str) -> None:
    bd.execute(update(PrecioCorridaProducto).where(PrecioCorridaProducto.corrida_id == c.corrida_id,
                                                   PrecioCorridaProducto.estado == "pendiente")
               .values(estado="fallido", mensaje="La corrida se detuvo"))
    c.estado, c.error, c.terminado_en = "fallida", motivo[:1000], ahora()
    _olvidar(c.corrida_id)


def detener(bd: Session, c: PrecioCorrida, quien: str) -> None:
    """Detiene una corrida en curso. Si sigue viva, se detiene en su siguiente revisión (a lo más unos segundos)."""
    DETENER.add(c.corrida_id)
    _cerrar(bd, c, f"{DETENIDA} {quien}.")
    bd.commit()


PRUEBA = "prueba"  # corrida con una lista de SKU de un Excel: no cuenta como la última del radar ni para el programa
PRODUCTO = "producto"  # búsqueda de un producto nuevo que lanzó el radar de productos: solo cuenta para el gasto
OPORTUNIDAD = "oportunidad"  # búsqueda de lo que vende la competencia («Buscar oportunidades»): solo cuenta para el gasto
REGULAR = PrecioCorrida.origen.not_in((PRUEBA, PRODUCTO, OPORTUNIDAD))


def en_curso(bd: Session) -> PrecioCorrida | None:
    return bd.scalar(select(PrecioCorrida).where(PrecioCorrida.estado == "en_curso",
                                                 PrecioCorrida.origen.not_in((PRODUCTO, OPORTUNIDAD)),
                                                 PrecioCorrida.iniciado_en > ahora() - timedelta(hours=4)))


def tomar_corrida(bd: Session, fecha: date, origen: str, usuario_id: int | None = None,
                  forzar: bool = False) -> PrecioCorrida | None:
    """Reserva una corrida. None si otra corre, o si la del día ya terminó y no se forzó.
    forzar («Correr ahora») siempre abre una corrida nueva con su propia hora (pedido de Diego, 2026-10-20: antes
    reescribía la del mismo día y no se sabía si ya se había corrido). Sin forzar (programador) se reintenta la
    última del día y solo se procesa lo que no consiguió precios o cuya coincidencia cambió una persona."""
    if en_curso(bd):
        return None
    existente = None if forzar else ultima_del_dia(bd, fecha)
    if not existente:
        c = PrecioCorrida(fecha=fecha, origen=origen, iniciado_por=usuario_id, estado="en_curso")
        bd.add(c)
        try:
            bd.commit()
        except IntegrityError:
            bd.rollback()
            return None
        return c
    if existente.estado == "completa":
        return None
    cambio = bd.execute(update(PrecioCorrida).where(
        PrecioCorrida.corrida_id == existente.corrida_id, PrecioCorrida.estado == existente.estado,
        PrecioCorrida.intentos == existente.intentos,
    ).values(estado="en_curso", origen=origen, iniciado_en=ahora(), terminado_en=None, iniciado_por=usuario_id,
             intentos=existente.intentos + 1, error=None))
    bd.commit()
    if cambio.rowcount != 1:
        return None
    bd.refresh(existente)
    return existente


def ultima_del_dia(bd: Session, fecha: date) -> PrecioCorrida | None:
    return bd.scalar(select(PrecioCorrida).where(PrecioCorrida.fecha == fecha, REGULAR).order_by(PrecioCorrida.corrida_id.desc()))


def de_lista(bd: Session, corrida: PrecioCorrida) -> list[tuple[PrecioVigilado, Producto]]:
    """Los productos de una prueba con Excel. Los que no se vigilan van con un vigilado sin guardar (sin búsqueda propia)."""
    ids = json.loads(corrida.lista or "{}").get("producto_ids", [])
    vigilados = {v.producto_id: v for v in bd.scalars(select(PrecioVigilado).where(PrecioVigilado.producto_id.in_(ids or [0])))}
    productos = {p.producto_id: p for p in bd.scalars(select(Producto).where(Producto.producto_id.in_(ids or [0])))}
    return [(vigilados.get(i) or PrecioVigilado(producto_id=i, activo=True), productos[i]) for i in ids if i in productos]


def _vigilados(bd: Session) -> list[tuple[PrecioVigilado, Producto]]:
    return list(bd.execute(select(PrecioVigilado, Producto).join(Producto, Producto.producto_id == PrecioVigilado.producto_id)
                           .where(PrecioVigilado.activo == true(), Producto.activo == true())
                           .order_by(Producto.descripcion)).all())


def vigente(bd: Session, producto_id: int) -> PrecioCoincidencia | None:
    return bd.scalar(select(PrecioCoincidencia).where(PrecioCoincidencia.producto_id == producto_id,
                                                      PrecioCoincidencia.estado.in_(VIGENTES))
                     .order_by(PrecioCoincidencia.coincidencia_id.desc()))


def _rechazados(bd: Session, producto_id: int) -> set[str]:
    return {g for g in bd.scalars(select(PrecioCoincidencia.google_id).where(
        PrecioCoincidencia.producto_id == producto_id,
        PrecioCoincidencia.estado.in_(("rechazada", "invalidada")))) if g}


def _marcas(bd: Session) -> set[str]:
    return {co.normalizar(co.marca_comercial(m)) for m in bd.scalars(select(Producto.marca).where(Producto.marca.is_not(None)).distinct())
            if m and len(co.normalizar(co.marca_comercial(m))) >= 3}


def nombre_tienda(bd: Session, producto_id: int) -> str | None:
    """Nombre con que la tienda en línea publica el producto (título y variante), si viene de la tienda."""
    datos = bd.scalar(select(ProductoFuente.datos).where(ProductoFuente.producto_id == producto_id, ProductoFuente.fuente == "TIENDA",
                                                         ProductoFuente.presente == true()).order_by(ProductoFuente.producto_fuente_id.desc()))
    try:
        d = json.loads(datos) if datos else {}
    except ValueError:
        return None
    titulo = " ".join(str(d.get("titulo") or "").split())
    variante = " ".join(str(d.get("variante") or "").split())
    if titulo and variante and variante.casefold() != "default title":
        titulo = f"{titulo} - {variante}"
    return titulo[:300] or None


def resumen_candidatos(cands, rechazados: set[str]) -> str:
    """Lo que regresó Google para un producto, ordenado por calificación, para mostrarlo y poder elegir a mano."""
    salida = []
    for c in sorted(cands, key=lambda c: -(c.evaluacion.calificacion if c.evaluacion else -1)):
        d, ev = c.datos, c.evaluacion
        salida.append({
            "clave": c.clave, "titulo": c.titulo[:300], "precio": d.get("price"), "moneda": d.get("currency"),
            "vendedor": d.get("seller"), "liga": d.get("shopping_url") or d.get("url"),
            "imagen": img.de_candidato(d) or d.get("thumbnail"), "posicion": d.get("rank_absolute"),
            "estrategias": sorted(c.estrategias), "product_id": d.get("product_id"), "data_docid": d.get("data_docid"),
            "calificacion": round(ev.calificacion, 1) if ev else None, "aceptada": bool(ev and ev.aceptada),
            "dudosa": bool(ev and ev.dudosa),
            "motivo": ev.motivo if ev else ("Una persona ya lo rechazó" if c.clave in rechazados else None)})
    return json.dumps(salida[:30], ensure_ascii=False, default=str)


def ultimos_candidatos(bd: Session, producto_id: int) -> tuple[list[dict], date | None]:
    fila = bd.execute(select(PrecioCorridaProducto.candidatos, PrecioCorrida.fecha)
                      .join(PrecioCorrida, PrecioCorrida.corrida_id == PrecioCorridaProducto.corrida_id)
                      .where(PrecioCorridaProducto.producto_id == producto_id, PrecioCorridaProducto.candidatos.is_not(None))
                      .order_by(PrecioCorridaProducto.corrida_producto_id.desc())).first()
    if not fila:
        return [], None
    try:
        return json.loads(fila[0]), fila[1]
    except ValueError:
        return [], fila[1]


def fuera_de_rango(o: PrecioObservacion, descripcion: str | None, base: Decimal | None) -> str | None:
    """Motivo para dejar fuera de la mediana la oferta de un vendedor que parece de otra presentación."""
    try:
        datos = json.loads(o.datos or "{}")
    except ValueError:
        datos = {}
    titulo = datos.get("title") or datos.get("product_title")
    if titulo and descripcion and (motivo := co.presentacion_distinta(descripcion, str(titulo)) or co.paquete(descripcion, str(titulo))):
        return motivo[0].upper() + motivo[1:]
    # En la lista de tiendas de Google el título es el nombre de la tienda; el tamaño viene en «details» o en la liga
    # (aceite-de-ajonjoli-extra-virgen-500-ml-san-lucas, corrida 2006)
    for extra in (datos.get("details"), re.sub(r"[-_/+]+", " ", urlparse(str(datos.get("url") or "")).path)):
        if extra and descripcion and (motivo := co.presentacion_distinta(descripcion, str(extra))):
            return motivo[0].upper() + motivo[1:]
    if base and o.precio_comparable is not None:
        if o.precio_comparable < base * PRECIO_RELATIVO_MINIMO:
            return "Precio demasiado bajo contra el nuestro: parece otra presentación"
        if o.precio_comparable > base * PRECIO_RELATIVO_MAXIMO:
            return "Precio demasiado alto contra el nuestro: parece otra presentación"
    return None


def ids_google(m: PrecioCoincidencia) -> dict[str, str]:
    """Identificadores para pedir vendedores. Como en el flujo de n8n de Diego, se manda product_id y
    data_docid juntos: con solo product_id Google a veces no regresa vendedores."""
    try:
        d = json.loads(m.candidato or "{}")
    except ValueError:
        d = {}
    salida = {k: str(d[k]) for k in ("product_id", "data_docid") if d.get(k)}
    if not salida and m.google_id:
        salida["product_id"] = m.google_id
    return salida


def iguales(m: PrecioCoincidencia) -> list[dict]:
    try:
        datos = json.loads(m.iguales or "[]")
    except ValueError:
        return []
    return [d for d in datos if isinstance(d, dict)] if isinstance(datos, list) else []


def publicaciones(m: PrecioCoincidencia, maximo: int) -> list[tuple[dict[str, str], str | None]]:
    """(identificadores, título) de cada publicación del producto en Google Shopping: la elegida y luego las iguales."""
    salida = [(ids_google(m), m.titulo)]
    for d in iguales(m):
        ids = {k: str(d[k]) for k in ("product_id", "data_docid") if d.get(k)} or ({"product_id": str(d["clave"])} if d.get("clave") else {})
        if ids and ids not in [i for i, _ in salida]:
            salida.append((ids, d.get("titulo")))
    return [(i, t) for i, t in salida if i][:max(1, maximo)]


def _igual(c: co.Candidato) -> dict:
    return {"clave": c.clave, "titulo": c.titulo, "vendedor": c.datos.get("seller"), "precio": c.datos.get("price"),
            "liga": c.datos.get("shopping_url") or c.datos.get("url"),
            **{k: str(c.datos[k]) for k in ("product_id", "data_docid") if c.datos.get(k)}}


def sin_repetir(observaciones: list[PrecioObservacion]) -> list[PrecioObservacion]:
    """Una tienda que aparece en varias publicaciones cuenta una vez, con su precio más bajo."""
    def orden(o: PrecioObservacion):  # primero lo disponible en pesos, luego lo más barato
        agotado = any(t in (o.disponibilidad or "").lower() for t in NO_DISPONIBLE)
        return (agotado or o.moneda != "MXN", o.precio_comparable)

    def claves(o: PrecioObservacion) -> set[str]:
        # Por nombre y por dominio: en la búsqueda viene «Mercado Libre» sin dominio y en vendedores mercadolibre.com.mx
        nombre = _clave(o.vendedor)
        c = {nombre, nombre.replace(" ", "")}
        if o.dominio:
            c |= {o.dominio, o.dominio.split(".")[0]}
        return c

    mejor: list[PrecioObservacion] = []
    indice: dict[str, int] = {}
    for o in observaciones:
        ks = claves(o)
        i = next((indice[k] for k in ks if k in indice), None)
        if i is None:
            i = len(mejor)
            mejor.append(o)
        elif orden(o) < orden(mejor[i]):
            mejor[i] = o
        for k in ks | claves(mejor[i]):
            indice.setdefault(k, i)
    return mejor


class Corrida:
    def __init__(self, bd: Session, corrida: PrecioCorrida):
        self.bd, self.c = bd, corrida
        self.cfg = configuracion()
        self.avisos: list[str] = []
        self.sin_presupuesto: str | None = None
        # Resultados de la búsqueda que son el mismo producto: cada uno trae tienda y precio (como n8n y Radar Precios)
        self.de_busqueda: dict[int, list[dict]] = {}
        self.variante_dudosa: set[int] = set()  # Google trajo varias variantes y no se supo cuál es la nuestra
        self.sin_tamano: dict[int, set[str]] = {}  # publicaciones que la IA no vio porque no dicen nuestra presentación

    # ---- coincidencia

    def _guardar_coincidencia(self, producto_id: int, cand: co.Candidato, estado: str, motivo: str,
                              confianza: float | None, iguales: list[co.Candidato] = ()) -> PrecioCoincidencia:
        d = cand.datos
        otras = [_igual(c) for c in iguales][:MAX_IGUALES]
        m = PrecioCoincidencia(
            producto_id=producto_id, google_id=cand.clave[:80], titulo=cand.titulo[:400],
            liga=(d.get("shopping_url") or d.get("url") or "")[:800] or None,
            imagen=(img.de_candidato(d) or d.get("thumbnail") or "")[:800] or None,
            estado=estado, confianza=Decimal(str(round(confianza, 2))) if confianza is not None else None,
            motivo=motivo[:600], estrategia=",".join(sorted(cand.estrategias))[:40],
            candidato=json.dumps(d, ensure_ascii=False, default=str),
            iguales=json.dumps(otras, ensure_ascii=False, default=str) if otras else None, verificado_en=ahora())
        self.bd.add(m)
        self.bd.flush()
        return m

    def _resolver(self, producto_id: int, cand: co.Candidato, estado: str, motivo: str, confianza: float | None,
                  iguales: list[co.Candidato], candidatos: dict[str, co.Candidato]) -> PrecioCoincidencia:
        """Guarda lo que se eligió en esta búsqueda. Si es la misma publicación que ya estaba, o la vigente la eligió
        una persona, se conserva y solo se actualizan las iguales."""
        m = vigente(self.bd, producto_id)
        if m and (m.google_id == cand.clave or m.estado == "persona"):
            otras = [c for c in [cand, *iguales] if c.clave != m.google_id]
            m.iguales = json.dumps([_igual(c) for c in otras][:MAX_IGUALES], ensure_ascii=False, default=str) or None
            m.verificado_en = ahora()
            principal = candidatos.get(m.google_id)
        else:
            if m:
                m.estado = "invalidada"
                m.motivo = ("En la búsqueda de esta corrida se eligió otra publicación. " + (m.motivo or ""))[:600]
            m = self._guardar_coincidencia(producto_id, cand, estado, motivo, confianza, iguales)
            principal, otras = cand, iguales
        self.de_busqueda[producto_id] = [{**c.datos, "_publicacion": c.titulo} for c in ([principal] if principal else []) + list(otras)]
        return m

    def _buscar(self, ronda: dict[int, tuple[str, str]], candidatos: dict[int, dict[str, co.Candidato]]) -> dict[int, str]:
        """Manda una búsqueda por producto. Junta candidatos; regresa {producto_id: error} de las que fallaron."""
        if not ronda:
            return {}
        tareas = [{"keyword": texto, "depth": self.cfg.precios_profundidad, "tag": f"{pid}"} for pid, (_, texto) in ronda.items()]
        self.revisar()
        ids = dfs.enviar(self.bd, self.c, "productos", tareas)
        errores = {pid: "DataForSEO no aceptó la búsqueda" for pid in ronda if str(pid) not in ids}
        nombres = {tag: self.nombre(int(tag)) for tag in ids}

        def esperando(faltan: set[str]) -> None:
            listas = len(ids) - len(faltan)
            self.fase(f"Google Shopping (DataForSEO) ya contestó {listas} de {len(ids)} búsquedas. Faltan: "
                      + _lista(sorted(nombres[x] for x in faltan)), listas, len(ids))

        esperando(set(ids))
        recogidas = dfs.recoger("productos", ids, self.detenida, esperando)
        self.revisar()
        for tag, items in recogidas.items():
            pid = int(tag)
            if isinstance(items, str):
                errores[pid] = items
                continue
            estrategia = ronda[pid][0]
            for item in items:
                cand = co.candidato_de(item)
                if cand:
                    previo = candidatos[pid].setdefault(cand.clave, cand)
                    previo.estrategias.add(estrategia)
        return errores

    def fase(self, texto: str, hechos: int | None = None, total: int | None = None, conserva: bool = False) -> None:
        """Lo que se ve en pantalla mientras corre. conserva=True deja la cuenta de hechos/total del momento."""
        FASE[self.c.corrida_id] = texto
        previo = AVANCE.get(self.c.corrida_id, {})
        if conserva:
            hechos, total = previo.get("hechos"), previo.get("total")
        AVANCE[self.c.corrida_id] = {"paso": previo.get("paso"), "pasos": len(PASOS), "titulo": previo.get("titulo"),
                                     "texto": texto, "hechos": hechos, "total": total}

    def paso(self, n: int, extra: str = "") -> None:
        AVANCE[self.c.corrida_id] = {**AVANCE.get(self.c.corrida_id, {}), "paso": n, "titulo": PASOS[n - 1] + extra}

    def nombre(self, producto_id: int) -> str:
        p = self.bd.get(Producto, producto_id)
        return (p.descripcion or p.sku) if p else str(producto_id)

    def detenida(self) -> bool:
        return self.c.corrida_id in DETENER

    def revisar(self) -> None:
        if self.detenida():
            raise Detenida()

    def _revisar_con_ia(self, producto: Producto, dudosos: list[co.Candidato], siempre: bool = False,
                        tienda: str | None = None, precio: Decimal | None = None, busqueda: str | None = None
                        ) -> tuple[co.Candidato | None, float, str, bool, list[co.Candidato]]:
        """(elegido, confianza, motivo, la IA contestó, otras publicaciones del mismo producto).
        Con siempre=True la IA elige entre todos los resultados y marca todas las que son el mismo producto."""
        self.revisar()
        que = "elige entre los resultados" if siempre else "revisa candidatos dudosos"
        self.fase(f"La IA {que} de «{(producto.descripcion or producto.sku)[:60]}»", conserva=True)
        try:
            r = puerta.ejecutar(self.bd, TAREA_IA, usuario_id=None,
                                instrucciones=co.INSTRUCCIONES_IA_ELEGIR if siempre else co.INSTRUCCIONES_IA,
                                mensaje=co.mensaje_ia(producto.descripcion, producto.marca, dudosos, tienda if siempre else None,
                                                      precio if siempre else None, busqueda if siempre else None,
                                                      self._confirmada(producto.producto_id) if siempre else None),
                                max_tokens=400, esfuerzo="low")
        except puerta.ErrorIA as e:
            return None, 0, f"No se pudo usar la IA ({e})", False, []
        try:
            elegido, confianza, motivo = co.leer_respuesta_ia(r.texto, dudosos)
        except (ValueError, TypeError):
            return None, 0, "La IA no respondió en el formato esperado", False, []
        return elegido, confianza, motivo, True, co.iguales_ia(r.texto, dudosos, elegido) if elegido else []

    def _por_fotos(self, producto: Producto, revisables: list[co.Candidato]
                   ) -> tuple[co.Candidato | None, list[co.Candidato], str]:
        """Google trajo varias variantes y el texto no dice cuál es la nuestra: la IA compara la foto de nuestro producto
        con las de los resultados (idea de Diego, 2026-10-20). (elegido, iguales, motivo o problema)."""
        if not self.cfg.precios_comparar_imagenes:
            return None, [], "comparar fotos está apagado en Configuración"
        nuestra = img.bajar(producto.imagen_cdn) or img.bajar(producto.liga_imagen)
        if not nuestra:
            return None, [], "no hay foto de nuestro producto para compararla"
        con_foto: list[tuple[co.Candidato, str]] = []
        for c in revisables:
            if len(con_foto) >= MAX_FOTOS:
                break
            if foto := img.bajar(img.de_candidato(c.datos)):
                con_foto.append((c, foto))
        if not con_foto:
            return None, [], "Google no trajo fotos que se pudieran bajar"
        self.revisar()
        self.fase(f"La IA compara fotos de «{(producto.descripcion or producto.sku)[:60]}»", conserva=True)
        mensaje = json.dumps({"producto": {"descripcion": producto.descripcion, "marca": co.marca_comercial(producto.marca)},
                              "candidatos": [{"imagen": i + 2, "clave": c.clave, "titulo": c.titulo}
                                             for i, (c, _) in enumerate(con_foto)]}, ensure_ascii=False)
        try:
            r = puerta.ejecutar(self.bd, TAREA_IMAGENES, usuario_id=None, instrucciones=co.INSTRUCCIONES_IA_IMAGENES,
                                mensaje=mensaje, max_tokens=300, imagenes=[nuestra] + [f for _, f in con_foto])
            datos = co._json_ia(r.texto)
        except puerta.ErrorIA as e:
            return None, [], f"no se pudieron comparar las fotos ({e})"
        except ValueError:
            return None, [], "la IA no respondió la comparación de fotos en el formato esperado"
        por_clave = {c.clave: c for c, _ in con_foto}
        iguales = [por_clave[str(k)] for k in datos.get("claves") or [] if str(k) in por_clave]
        if not iguales:
            return None, [], "en las fotos la IA no vio el mismo producto"
        # Lo que leyó en nuestro empaque, o la única variante entre los que eligió; si eligió de varias, no se adivina
        referencia = str(datos.get("variante") or "") or " ".join(sorted(set().union(*(co.variantes(c.titulo) for c in iguales))))
        elegido, otras, problema = co.cuidar_variante(iguales[0], iguales[1:], [referencia], revisables)
        if problema or (elegido and len(co.variantes(referencia)) > 1):
            return None, [], problema or "en las fotos la IA juntó varias variantes"
        return elegido, otras, f"Elegido por la IA comparando fotos: {str(datos.get('motivo') or '')[:300]}"

    def _confirmada(self, producto_id: int) -> str | None:
        """Título de la publicación que eligió una persona: le dice a la IA qué variante es la nuestra (caso Demograss
        clásico, 2026-10-20: la IA juntó Premier y clásico)."""
        m = vigente(self.bd, producto_id)
        return m.titulo if m and m.estado == "persona" else None

    def coincidencias(self, pendientes: list[tuple[PrecioVigilado, Producto]], filas: dict[int, PrecioCorridaProducto]) -> None:
        tiendas = {p.producto_id: nombre_tienda(self.bd, p.producto_id) for _, p in pendientes}
        busquedas = {p.producto_id: (v.consulta or "").strip() or None for v, p in pendientes}
        planes = {p.producto_id: co.consultas(p.descripcion, p.marca, p.codigo_barras, v.consulta, tiendas[p.producto_id])
                  for v, p in pendientes}
        productos = {p.producto_id: p for _, p in pendientes}
        candidatos: dict[int, dict[str, co.Candidato]] = {pid: {} for pid in planes}
        marcas = _marcas(self.bd)
        sin_resolver = {pid for pid, plan in planes.items() if plan}
        for pid in set(planes) - sin_resolver:
            filas[pid].estado, filas[pid].mensaje = "sin_coincidencia", "El producto no tiene descripción ni código de barras para buscarlo"
        rondas = max((len(pl) for pl in planes.values()), default=0)
        for ronda_n in range(rondas):
            ronda = {pid: planes[pid][ronda_n] for pid in sin_resolver if len(planes[pid]) > ronda_n}
            if not ronda:
                break
            if rondas > 1:
                self.paso(1, f" · intento {ronda_n + 1} de {rondas}" + (
                    " (otra forma de buscar los que no se encontraron)" if ronda_n else ""))
            try:
                errores = self._buscar(ronda, candidatos)
            except dfs.SinPresupuesto as e:
                self.sin_presupuesto = str(e)
                break
            for n_rev, pid in enumerate(ronda, 1):
                p, fila = productos[pid], filas[pid]
                self.fase(f"Revisando los resultados de «{(p.descripcion or p.sku)[:60]}» ({n_rev} de {len(ronda)})",
                          n_rev - 1, len(ronda))
                rechazados = _rechazados(self.bd, pid)
                dec = co.decidir(p.descripcion, p.marca, list(candidatos[pid].values()), self.cfg.precios_umbral, marcas, rechazados)
                fila.candidatos = resumen_candidatos(candidatos[pid].values(), rechazados)
                ultima = ronda_n == len(planes[pid]) - 1
                if self.cfg.precios_ia_siempre:
                    # La IA elige entre los resultados; las reglas solo quitan otra marca, otra presentación y paquetes.
                    # Si la IA no contesta (Ollama apagado y sin API), deciden las reglas como antes.
                    revisables = co.para_ia(list(candidatos[pid].values()), rechazados, descripcion=p.descripcion)
                    todas = co.para_ia(list(candidatos[pid].values()), rechazados, maximo=len(candidatos[pid]))
                    self.sin_tamano[pid] = {c.clave for c in todas} - {c.clave for c in co.con_presentacion(todas, p.descripcion)}
                    if revisables:
                        elegido, confianza, motivo, contesto, iguales = self._revisar_con_ia(
                            p, revisables, siempre=True, tienda=tiendas.get(pid), precio=nuestro(fila)[0],
                            busqueda=busquedas.get(pid))
                        referencias = [busquedas.get(pid), self._confirmada(pid), p.descripcion]
                        sin_variante = not any(co.variantes(r) for r in referencias if r)
                        varias = len(set().union(*(co.variantes(c.titulo) for c in revisables))) >= 2
                        problema = None
                        if elegido:
                            # Lo que las reglas aceptan solas (mismo nombre, marca y presentación) también es el mismo
                            # producto aunque la IA no lo haya marcado (caso Belabear: Tiendaestrella quedó fuera, 2026-10-20)
                            iguales += [c for c in revisables if c is not elegido and c not in iguales
                                        and c.evaluacion.aceptada]
                            elegido, iguales, problema = co.cuidar_variante(elegido, iguales, referencias, revisables)
                        elif contesto and sin_variante and varias:
                            # La IA no eligió porque hay varias variantes (corrida 1004, Demograss): también las fotos
                            problema = f"La IA no encontró el mismo producto: {motivo}"
                        if problema and sin_variante:
                            # No sabemos cuál variante es la nuestra: se decide con las fotos
                            elegido, iguales, por_foto = self._por_fotos(p, revisables)
                            if elegido:
                                motivo, confianza, problema = por_foto, max(confianza, 80), None
                            else:
                                problema += f" (fotos: {por_foto})"
                        if problema:
                            fila.estado, fila.mensaje = "sin_coincidencia", problema[:400]
                            self.variante_dudosa.add(pid)
                            if ultima:
                                sin_resolver.discard(pid)
                            continue
                        if elegido:
                            texto = motivo if motivo.startswith("Elegido por la IA") else "Elegido por la IA: " + motivo
                            m = self._resolver(pid, elegido, "ia", texto, confianza, iguales, candidatos[pid])
                            fila.coincidencia_id, fila.estado, fila.mensaje = m.coincidencia_id, "pendiente", None
                            sin_resolver.discard(pid)
                            continue
                        if contesto:
                            fila.estado, fila.mensaje = "sin_coincidencia", f"La IA no encontró el mismo producto: {motivo}"[:400]
                            if ultima:
                                sin_resolver.discard(pid)
                            continue
                        aviso = f"{motivo}; se decidió con las reglas."
                        if aviso not in self.avisos:
                            self.avisos.append(aviso)
                if dec.elegido:
                    # Las demás publicaciones que las reglas también aceptan son el mismo producto: cuentan sus precios
                    iguales = [c for c in candidatos[pid].values() if c is not dec.elegido and c.clave not in rechazados
                               and c.evaluacion and c.evaluacion.aceptada and co.pasa_reglas(c)]
                    m = self._resolver(pid, dec.elegido, "automatica", dec.motivo, dec.elegido.evaluacion.calificacion,
                                       iguales, candidatos[pid])
                    fila.coincidencia_id, fila.estado, fila.mensaje = m.coincidencia_id, "pendiente", None
                    sin_resolver.discard(pid)
                elif dec.dudosos and ultima:
                    elegido, confianza, motivo, _, _ = self._revisar_con_ia(p, dec.dudosos)
                    if elegido:
                        iguales = [c for c in dec.dudosos if c is not elegido and c.evaluacion.aceptada and co.pasa_reglas(c)]
                        m = self._resolver(pid, elegido, "ia", "Revisado por la IA: " + motivo, confianza, iguales, candidatos[pid])
                        fila.coincidencia_id, fila.estado, fila.mensaje = m.coincidencia_id, "pendiente", None
                    else:
                        fila.estado, fila.mensaje = "sin_coincidencia", motivo[:400]
                    sin_resolver.discard(pid)
                else:
                    fila.estado = "sin_coincidencia"
                    fila.mensaje = (errores.get(pid) or dec.motivo)[:400]
            self.bd.commit()
        # Si la búsqueda de hoy no encontró nada seguro pero ya había una coincidencia, se siguen pidiendo sus vendedores
        for pid in planes:
            fila, m = filas[pid], vigente(self.bd, pid)
            if fila.estado == "sin_coincidencia" and m and pid in self.variante_dudosa and m.estado != "persona":
                # La vigente puede ser justo la variante equivocada (caso Demograss): no se sigue usando
                m.estado = "invalidada"
                m.motivo = ("Google trae varias variantes y no se sabe cuál es la nuestra. " + (m.motivo or ""))[:600]
                fila.coincidencia_id = None
                continue
            if fila.estado == "sin_coincidencia" and m and m.estado != "persona" and m.google_id in self.sin_tamano.get(pid, set()):
                # Su título no dice la presentación y hay publicaciones que sí: era la de 500 ml (Ajonjolí 250 ml, corrida 2008)
                m.estado = "invalidada"
                m.motivo = ("Su título no dice la presentación y hay publicaciones que sí la traen. " + (m.motivo or ""))[:600]
                fila.coincidencia_id = None
                continue
            if fila.estado == "sin_coincidencia" and m:
                fila.coincidencia_id, fila.estado = m.coincidencia_id, "pendiente"
                fila.mensaje = None
        self.bd.commit()

    # ---- tiendas directas (Walmart, Chedraui, San Pablo, Soriana)

    def _buscar_en(self, tienda: td.Tienda, trabajos: list[Trabajo], marcas: set[str], avance: dict[str, str]
                   ) -> dict[int, tuple[dict[str, tuple[co.Candidato, td.Resultado]], str | None]]:
        """Corre en su propio hilo: solo consultas al sitio y reglas, nada de base ni IA. Para cada producto busca con
        la consulta de Compras o la descripción y, si no quedó claro, con el código de barras."""
        salida: dict[int, tuple[dict[str, tuple[co.Candidato, td.Resultado]], str | None]] = {}
        ultima, fallas = [0.0], 0
        for n, t in enumerate(trabajos):
            if self.detenida():
                break
            avance[tienda.nombre] = (n, len(trabajos), t.descripcion or "")
            if fallas >= FALLAS_PARA_PARAR:
                salida[t.producto_id] = ({}, f"No se buscó: {tienda.nombre} falló {FALLAS_PARA_PARAR} veces seguidas en esta corrida")
                continue
            cands: dict[str, tuple[co.Candidato, td.Resultado]] = {}
            error = None
            for estrategia, texto in t.consultas:
                try:
                    resultados = td.buscar_con_pausa(tienda, texto, ultima)
                    fallas = 0
                except td.ErrorTienda as e:
                    error, fallas = f"{tienda.nombre} {e}", fallas + 1
                    break
                except Exception:  # noqa: BLE001 - una tienda no detiene la corrida
                    log.exception("Falló la búsqueda en %s", tienda.nombre)
                    error, fallas = f"{tienda.nombre}: error inesperado al leer sus resultados", fallas + 1
                    break
                for i, r in enumerate(resultados):
                    if r.clave not in cands:
                        cands[r.clave] = (candidato_tienda(tienda, r, i + 1), r)
                    cands[r.clave][0].estrategias.add(estrategia)
                if t.vigente in cands or (t.barras and any(_barras(r.ean) == t.barras for _, r in cands.values())):
                    break
                if co.decidir(t.descripcion, t.marca, [c for c, _ in cands.values()], self.cfg.precios_umbral, marcas,
                              t.rechazados).elegido:
                    break
            salida[t.producto_id] = (cands, error if not cands else None)
        avance.pop(tienda.nombre, None)
        return salida

    def _elegir_en_tienda(self, p: Producto, consulta: str | None, cands: dict[str, tuple[co.Candidato, td.Resultado]],
                          vig: PrecioTiendaCoincidencia | None, rechazados: set[str], marcas: set[str]
                          ) -> tuple[co.Candidato | None, str, str]:
        """(elegido, estado, motivo). Estado: automatica / ia / persona (el elegido) o no_lo_tiene / dudoso."""
        lista = [c for c, _ in cands.values()]
        if not lista:
            return None, "no_lo_tiene", "No salió en su buscador"
        if vig and vig.clave in cands:
            c = cands[vig.clave][0]
            barras_iguales = bool(_barras(p.codigo_barras)) and _barras(c.datos.get("ean")) == _barras(p.codigo_barras)
            # Lo que eligieron las reglas se vuelve a revisar con las reglas de hoy: si ya no lo aceptan, se deja
            # (corrida 2004: «Aceite de oliva» había entrado por «Aceite de ajo»). Lo de la IA o una persona se respeta.
            variante = None if vig.estado == "persona" or barras_iguales else self._otra_variante(p, c.titulo)
            if not variante and (vig.estado != "automatica" or barras_iguales or co.evaluar(
                    p.descripcion, p.marca, c.titulo, self.cfg.precios_umbral, marcas, c.datos.get("rank_absolute")).aceptada):
                return c, vig.estado, vig.motivo or "El mismo de la vez anterior"
            vig.estado = "invalidada"
            vig.motivo = ((variante or "Las reglas actuales ya no lo aceptan.") + " " + (vig.motivo or ""))[:600]
            lista = [x for x in lista if x.clave != vig.clave]
            if not lista:
                return None, "no_lo_tiene", "Lo que salió en su buscador no es el mismo producto"
        if vig and vig.estado == "persona":
            return None, "no_lo_tiene", "El producto que eligió una persona no salió hoy en su buscador"
        dec = co.decidir(p.descripcion, p.marca, lista, self.cfg.precios_umbral, marcas, rechazados)
        barras = _barras(p.codigo_barras)
        por_ean = [c for c in lista if barras and _barras(c.datos.get("ean")) == barras and c.clave not in rechazados
                   and c.evaluacion and c.evaluacion.marca is not False]
        if por_ean:
            return por_ean[0], "automatica", "Mismo código de barras"
        referencias = [consulta, self._confirmada(p.producto_id), p.descripcion]
        revisables = co.para_ia(lista, rechazados)
        elegido, estado, motivo = None, "dudoso", dec.motivo
        if dec.elegido:
            elegido, estado, motivo = dec.elegido, "automatica", dec.motivo
        elif dec.dudosos:
            elegido, _, motivo, _, _ = self._revisar_con_ia(p, dec.dudosos)
            estado, motivo = ("ia", "Revisado por la IA: " + motivo) if elegido else ("dudoso", motivo)
        else:
            return None, "no_lo_tiene", dec.motivo.replace("Google Shopping", "Su buscador")
        if elegido:
            elegido, _, problema = co.cuidar_variante(elegido, [], referencias, revisables)
            problema = problema or (self._otra_variante(p, elegido.titulo) if elegido else None)
            if problema:
                return None, "dudoso", problema
        return elegido, estado, motivo

    def _otra_variante(self, p: Producto, titulo: str) -> str | None:
        """La publicación que confirmó una persona no dice variante y la de la tienda sí: es otra (Walmart aceptaba
        Demograss Plus por «Demograss 30 Cápsulas», corrida 2008)."""
        confirmada = self._confirmada(p.producto_id)
        if confirmada and co.variantes(titulo) and not co.variantes(confirmada) and not co.variantes(p.descripcion):
            return (f"«{titulo}» es la variante {', '.join(sorted(co.variantes(titulo)))}; la publicación que elegiste "
                    "no dice variante")
        return None

    def _guardar_tienda(self, producto_id: int, tienda: str, c: co.Candidato, r: td.Resultado, estado: str, motivo: str,
                        vig: PrecioTiendaCoincidencia | None) -> PrecioTiendaCoincidencia:
        if vig and vig.clave == c.clave:
            vig.titulo, vig.liga, vig.imagen, vig.verificado_en = r.titulo[:400], (r.liga or "")[:800] or vig.liga, \
                (r.imagen or "")[:800] or vig.imagen, ahora()
            return vig
        if vig:
            vig.estado = "invalidada"
            vig.motivo = ("En esta corrida se eligió otro producto de la tienda. " + (vig.motivo or ""))[:600]
        m = PrecioTiendaCoincidencia(producto_id=producto_id, tienda=tienda, clave=c.clave[:120], titulo=r.titulo[:400],
                                     liga=(r.liga or "")[:800] or None, imagen=(r.imagen or "")[:800] or None,
                                     ean=(r.ean or "")[:20] or None, estado=estado, motivo=motivo[:600], verificado_en=ahora())
        self.bd.add(m)
        self.bd.flush()
        return m

    def tiendas(self, procesados: list[tuple[PrecioVigilado, Producto]], filas: dict[int, PrecioCorridaProducto]) -> None:
        """Busca cada producto en el sitio de cada tienda directa. Una tienda por hilo (cada una con su pausa); las
        decisiones con IA y lo que se guarda, aquí."""
        conectores = td.conectores(tiendas_directas())
        if not conectores or not procesados:
            return
        bd = self.bd
        ya = set(bd.scalars(select(PrecioObservacion.producto_id).distinct().where(
            PrecioObservacion.corrida_id == self.c.corrida_id, PrecioObservacion.tienda_coincidencia_id.is_not(None))))
        procesados = [(v, p) for v, p in procesados if p.producto_id not in ya]  # reintento del mismo día: ya se buscaron
        if not procesados:
            return
        marcas = _marcas(bd)
        vigentes = {(p.producto_id, t.nombre): tienda_vigente(bd, p.producto_id, t.nombre) for _, p in procesados for t in conectores}
        rechazados = {(p.producto_id, t.nombre): _rechazados_tienda(bd, p.producto_id, t.nombre) for _, p in procesados for t in conectores}
        planes = {}
        for v, p in procesados:
            plan = co.consultas(p.descripcion, p.marca, p.codigo_barras, v.consulta)
            texto = [x for x in plan if x[0] in ("consulta", "descripcion")][:1]
            # Los buscadores de las tiendas fallan con la presentación pegada («Aceite de ajo 500 ml»): si con el texto
            # completo no sale, se busca sin ella y luego sin la marca, como san_pablo_definitivo.py (corridas 2004 y 2005)
            corto, vistas = [], {co.normalizar(texto[0][1])} if texto else set()
            for x in ([("sin_presentacion", co.sin_presentacion(texto[0][1])),
                       ("producto_solo", co.sin_presentacion(p.descripcion))] if texto else []):
                if x[1] and co.normalizar(x[1]) not in vistas:
                    vistas.add(co.normalizar(x[1]))
                    corto.append(x)
            planes[p.producto_id] = texto + corto + [x for x in plan if x[0] == "codigo_barras"]
        avance: dict[str, tuple[int, int, str]] = {}
        self.paso(2)
        total = len(conectores) * len(procesados)
        hechos_tienda: dict[str, int] = {}
        with ThreadPoolExecutor(max_workers=len(conectores), thread_name_prefix="precios-tienda") as ex:
            futuros = {t.nombre: ex.submit(self._buscar_en, t, [
                Trabajo(p.producto_id, p.descripcion, p.marca, _barras(p.codigo_barras), planes[p.producto_id],
                        getattr(vigentes[(p.producto_id, t.nombre)], "clave", None),
                        rechazados[(p.producto_id, t.nombre)]) for _, p in procesados], marcas, avance)
                for t in conectores}
            while True:
                hechos, pendientes = wait(futuros.values(), timeout=2)
                for nombre, (n, _, _) in avance.items():
                    hechos_tienda[nombre] = n
                for nombre, f in futuros.items():
                    if f.done():
                        hechos_tienda[nombre] = len(procesados)
                self.fase("; ".join(f"{nombre} {n + 1} de {de}: «{d[:45]}»" for nombre, (n, de, d) in avance.items())
                          or "Terminando", sum(hechos_tienda.values()), total)
                if not pendientes:
                    break
        self.revisar()
        resultados = {}
        for nombre, f in futuros.items():
            try:
                resultados[nombre] = f.result()
            except Exception:  # noqa: BLE001
                log.exception("Falló la búsqueda en %s", nombre)
                resultados[nombre] = {}
        vendedores = Vendedores(bd)
        for v, p in procesados:
            pid, estados = p.producto_id, {}
            for t in conectores:
                cands, error = resultados[t.nombre].get(pid, ({}, f"No se buscó en {t.nombre}"))
                if error:
                    estados[t.nombre] = {"estado": "error", "mensaje": error[:300]}
                    continue
                vig = vigentes[(pid, t.nombre)]
                elegido, estado, motivo = self._elegir_en_tienda(p, v.consulta, cands, vig, rechazados[(pid, t.nombre)], marcas)
                if not elegido:
                    estados[t.nombre] = {"estado": estado, "mensaje": motivo[:300]}
                    continue
                r = cands[elegido.clave][1]
                m = self._guardar_tienda(pid, t.nombre, elegido, r, estado, motivo, vig)
                estados[t.nombre] = {"estado": "encontrado", "mensaje": motivo[:300], "titulo": r.titulo, "liga": r.liga,
                                     "precio": str(r.precio) if r.precio else None, "id": m.tienda_coincidencia_id}
                if not r.precio:
                    estados[t.nombre]["estado"], estados[t.nombre]["mensaje"] = "sin_precio", "Lo tiene, pero su página no mostró precio"
                    continue
                nombre, dominio, propio = vendedores.normalizar(t.nombre, t.dominio, r.liga)
                original = t.nombre + (f" (vende {r.datos['vendedor']})" if r.datos.get("vendedor")
                                       and t.nombre.lower() not in str(r.datos["vendedor"]).lower() else "")
                bd.add(PrecioObservacion(
                    corrida_id=self.c.corrida_id, producto_id=pid, coincidencia_id=None, tienda_coincidencia_id=m.tienda_coincidencia_id,
                    vendedor=nombre, vendedor_original=original[:200], dominio=(dominio or t.dominio)[:200], liga=(r.liga or "")[:800] or None,
                    precio=r.precio, precio_comparable=r.precio, moneda="MXN",
                    disponibilidad="agotado" if r.disponible is False else None, es_propia=propio,
                    datos=json.dumps({"title": r.titulo, "_publicacion": f"Sitio de {t.nombre}", "_tienda_directa": t.nombre,
                                      "clave": r.clave, "ean": r.ean, **r.datos}, ensure_ascii=False, default=str)))
            filas[pid].tiendas = json.dumps(estados, ensure_ascii=False)
            bd.commit()

    # ---- precios

    def _observacion(self, producto_id: int, m: PrecioCoincidencia, fila: PrecioCorridaProducto, item: dict,
                     vendedores: Vendedores) -> PrecioObservacion | None:
        envio = _decimal(item.get("shipping_price"))
        precio = _decimal(item.get("base_price") if item.get("base_price") is not None else item.get("price"))
        multiplicador = _decimal(item.get("price_multiplier"))
        total = _decimal(item.get("total_price"))
        if multiplicador is not None and multiplicador > 1:  # paquete de varias piezas: igual que Radar Precios
            comparable = total - envio if total is not None and envio is not None else total
        else:
            comparable = precio
        if comparable is None or comparable <= 0:
            return None
        original = str(item.get("seller_name") or item.get("seller") or item.get("source") or "Vendedor desconocido")[:200]
        liga = item.get("url") or item.get("seller_url")
        nombre, dominio, propio = vendedores.normalizar(original, item.get("domain"), liga)
        o = PrecioObservacion(
            corrida_id=self.c.corrida_id, producto_id=producto_id, coincidencia_id=m.coincidencia_id,
            vendedor=nombre, vendedor_original=original, dominio=(dominio or "")[:200] or None, liga=(liga or "")[:800] or None,
            precio=precio, envio=envio, total=total, precio_comparable=comparable,
            moneda=str(item.get("currency") or "MXN").upper()[:5],
            disponibilidad=(str(item.get("product_availability") or item.get("availability") or "")[:120] or None),
            es_propia=propio, datos=json.dumps(item, ensure_ascii=False, default=str))
        return o

    @staticmethod
    def calcular(fila: PrecioCorridaProducto, observaciones: list[PrecioObservacion], descripcion: str | None = None) -> None:
        validas = [o for o in observaciones if not o.es_propia and o.moneda == "MXN"
                   and not any(t in (o.disponibilidad or "").lower() for t in NO_DISPONIBLE)]
        precios = sorted(o.precio_comparable for o in validas if not fuera_de_rango(o, descripcion, nuestro(fila)[0]))
        fila.vendedores = len(precios)
        if not precios:
            fila.estado, fila.mensaje = "sin_precios", (
                "Los vendedores que dio Google parecen ser de otra presentación (precio o tamaño muy distinto al nuestro)"
                if validas else "Ningún vendedor de la competencia con precio en pesos y disponible")
            return
        fila.minimo, fila.maximo = precios[0], precios[-1]
        fila.promedio = (sum(precios) / len(precios)).quantize(CENTAVO)
        fila.mediana = Decimal(str(median(precios))).quantize(CENTAVO)
        base = nuestro(fila)[0]
        fila.dif_lista_mediana_pct = diferencia_pct(base, fila.mediana)
        fila.dif_membresia_mediana_pct = diferencia_pct(fila.precio_membresia, fila.mediana)
        fila.dif_lista_minimo_pct = diferencia_pct(base, fila.minimo)
        fila.estado = "con_precios"
        fila.mensaje = None if base is not None else "No tenemos precio lista ni de la tienda en línea para comparar"

    def precios(self, filas: dict[int, PrecioCorridaProducto]) -> None:
        # Con coincidencia en Google, o sin ella pero con precios de los sitios de las tiendas
        directas = obs_tiendas(self.bd, self.c.corrida_id, [pid for pid, f in filas.items()
                                                            if f.estado in ("pendiente", "sin_coincidencia")]) if filas else {}
        listas = {pid: f for pid, f in filas.items()
                  if (f.estado == "pendiente" and f.coincidencia_id) or (f.estado in ("pendiente", "sin_coincidencia") and pid in directas)}
        if not listas:
            return
        coincid = {pid: self.bd.get(PrecioCoincidencia, f.coincidencia_id) if f.coincidencia_id else None for pid, f in listas.items()}
        # Una consulta de vendedores por cada publicación del mismo producto: la elegida y las iguales
        pubs = {pid: publicaciones(m, self.cfg.precios_max_publicaciones) for pid, m in coincid.items() if m}
        tareas = [{**ids, "depth": 10, "tag": f"{pid}~{n}"} for pid in pubs for n, (ids, _) in enumerate(pubs[pid])]
        ids = {}
        if tareas and not self.sin_presupuesto:
            self.revisar()
            try:
                ids = dfs.enviar(self.bd, self.c, "vendedores", tareas)
            except dfs.SinPresupuesto as e:
                self.sin_presupuesto = str(e)
        self.paso(3)
        nombres = {tag: self.nombre(int(tag.split("~")[0])) for tag in ids}

        def esperando(faltan: set[str]) -> None:
            listas = len(ids) - len(faltan)
            productos_faltan = sorted({nombres[x] for x in faltan})
            self.fase(f"DataForSEO ya mandó los vendedores de {listas} de {len(ids)} publicaciones ({len(pubs)} productos). "
                      "Faltan: " + _lista(productos_faltan), listas, len(ids))

        if ids:
            esperando(set(ids))
        resultados = dfs.recoger("vendedores", ids, self.detenida, esperando) if ids else {}
        self.revisar()
        por_producto: dict[int, list[list[dict] | str]] = {}
        for tag, items in resultados.items():
            pid, n = (int(x) for x in tag.split("~"))
            if isinstance(items, list):  # de qué publicación de Google salió cada precio, para la tabla
                items = [{**i, "_publicacion": pubs[pid][n][1]} for i in items]
            por_producto.setdefault(pid, []).append(items)
        for pid, items in (self.de_busqueda.items() if self.cfg.precios_buscar_siempre else ()):  # los resultados de la búsqueda como precios
            if pid in listas and coincid.get(pid) and items:
                por_producto.setdefault(pid, []).append(items)
        vendedores = Vendedores(self.bd)
        for pid, fila in listas.items():
            m = coincid[pid]
            respuestas = por_producto.get(pid) or []
            propias = directas.get(pid, [])
            if not respuestas and not propias:
                fila.estado = "sin_presupuesto" if self.sin_presupuesto else "fallido"
                fila.mensaje = (self.sin_presupuesto or "DataForSEO no aceptó la consulta de vendedores")[:400]
                continue
            de_google = [o for items in respuestas if isinstance(items, list) for item in items
                         for o in [self._observacion(pid, m, fila, item, vendedores)] if o] if m else []
            # Si Google trae una tienda que ya se leyó en su propio sitio, se queda el precio del sitio
            leidas = [o.vendedor for o in propias]
            de_google = [o for o in de_google if not tienda_clave(o.vendedor, o.dominio, leidas)]
            observaciones = sin_repetir(propias + de_google)
            nuevas = [o for o in observaciones if o.observacion_id is None]
            if observaciones:
                self.bd.add_all(nuevas)
                self.bd.flush()
                if m and nuevas:
                    m.fallos_seguidos, m.verificado_en = 0, ahora()
                producto = self.bd.get(Producto, pid)
                self.calcular(fila, observaciones, producto.descripcion if producto else None)
                if not m and fila.estado == "con_precios":
                    fila.mensaje = "Sin coincidencia en Google: solo cuentan los precios de los sitios de las tiendas"
                if m and respuestas and not nuevas:
                    self._sin_precios_google(m)
                continue
            fila.estado = "sin_precios"
            error = next((r for r in respuestas if isinstance(r, str)), None)
            fila.mensaje = (error or "Google Shopping no mostró vendedores para este producto")[:400]
            if m:
                self._sin_precios_google(m)
        self.bd.commit()

    @staticmethod
    def _sin_precios_google(m: PrecioCoincidencia) -> None:
        m.fallos_seguidos += 1
        if m.fallos_seguidos >= FALLOS_PARA_INVALIDAR and m.estado != "persona":
            m.estado = "invalidada"
            m.motivo = (f"Sin precios en {m.fallos_seguidos} corridas seguidas; se buscará de nuevo. " + (m.motivo or ""))[:600]

    # ---- todo

    def correr(self) -> PrecioCorrida:
        bd, c = self.bd, self.c
        c.tope_usd = Decimal(str(self.cfg.precios_tope_corrida_usd)) if self.cfg.precios_tope_corrida_usd else None
        vigilados = de_lista(bd, c) if c.origen == PRUEBA else _vigilados(bd)
        filas: dict[int, PrecioCorridaProducto] = {
            f.producto_id: f for f in bd.scalars(select(PrecioCorridaProducto).where(PrecioCorridaProducto.corrida_id == c.corrida_id))}
        pendientes, procesados = [], []
        for v, p in vigilados:
            fila = filas.get(p.producto_id)
            m = vigente(bd, p.producto_id)
            if fila and fila.estado == "con_precios" and m and fila.coincidencia_id == m.coincidencia_id:
                continue  # reintento del mismo día: ya tiene precios y nadie cambió su coincidencia
            if not fila:
                fila = PrecioCorridaProducto(corrida_id=c.corrida_id, producto_id=p.producto_id)
                bd.add(fila)
                filas[p.producto_id] = fila
            procesados.append((v, p))
            fila.estado, fila.mensaje, fila.coincidencia_id = "pendiente", None, None
            fila.precio_lista, fila.precio_membresia = p.precio_lista_con_impuestos, p.precio_membresia_con_impuestos
            fila.precio_tienda = p.precio_tienda_en_linea
            if m:
                fila.coincidencia_id = m.coincidencia_id
            if not m or self.cfg.precios_buscar_siempre:
                pendientes.append((v, p))
        bd.commit()
        ya = len(procesados) - len(pendientes)
        self.paso(1)
        self.fase(f"Preparando {len(procesados)} productos: {len(pendientes)} se buscan en Google Shopping"
                  + (f" y {ya} ya tienen su publicación de Google de corridas anteriores" if ya else ""), 0, len(pendientes) or None)
        if pendientes:
            self.coincidencias(pendientes, filas)
        self.tiendas(procesados, filas)  # sin costo: también corre si se acabó el presupuesto de DataForSEO
        self.precios({p.producto_id: filas[p.producto_id] for _, p in procesados})
        self.paso(4)
        self.fase("Calculando la diferencia contra la mediana y guardando los resultados")
        for fila in filas.values():
            if fila.estado == "pendiente":
                fila.estado = "sin_presupuesto" if self.sin_presupuesto else "fallido"
                fila.mensaje = (self.sin_presupuesto or "No se completó")[:400]
        if self.sin_presupuesto:
            self.avisos.append(self.sin_presupuesto + " Los productos que faltaron quedan para la siguiente corrida.")
        self.terminar(filas)
        return c

    def terminar(self, filas: dict[int, PrecioCorridaProducto]) -> None:
        self.revisar()
        _olvidar(self.c.corrida_id)
        bd, c, cfg = self.bd, self.c, self.cfg
        caros = contar(bd, c, list(filas.values()))
        c.avisos = json.dumps(self.avisos, ensure_ascii=False) if self.avisos else None
        c.terminado_en = ahora()
        bd.commit()
        if c.origen == PRUEBA:  # la prueba la sigue quien la lanzó; no se avisa a todo Compras
            return
        modulo = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "compras"))
        if caros:
            for uid in _con_permiso(bd, VER):
                notificar(bd, uid, "Radar de precios: productos en rojo",
                          f"En {len(caros)} productos nuestro precio lista está arriba de la mediana del mercado por más de su "
                          f"límite (corrida del {c.fecha:%d/%m/%Y}).", liga="/compras/precios?grupo=rojo",
                          modulo_id=modulo, clave=f"precios-caros:{c.corrida_id}:{c.intentos}")
        if c.estado != "completa":
            for uid in _con_permiso(bd, ADMINISTRAR):
                notificar(bd, uid, "Radar de precios: corrida incompleta",
                          f"La corrida del {c.fecha:%d/%m/%Y} terminó {c.estado}: {c.fallidos} de {c.productos} productos sin precios. "
                          + (self.avisos[0] if self.avisos else ""), liga="/compras/precios/corridas", modulo_id=modulo,
                          clave=f"precios-incompleta:{c.corrida_id}:{c.intentos}")
        bd.commit()


def contar(bd: Session, c: PrecioCorrida, filas: list[PrecioCorridaProducto]) -> list[PrecioCorridaProducto]:
    """Totales y estado de la corrida según sus renglones. Regresa los que quedaron en rojo."""
    estados = [f.estado for f in filas]
    c.productos = len(estados)
    c.con_coincidencia = sum(1 for f in filas if f.coincidencia_id)
    c.sin_coincidencia = estados.count("sin_coincidencia")
    c.con_precios = estados.count("con_precios")
    c.fallidos = estados.count("fallido") + estados.count("sin_presupuesto")
    limites = limites_por_producto(bd)
    caros = [f for f in filas if color(f.dif_lista_mediana_pct, limites.get(f.producto_id)) == "rojo"]
    c.alertas = len(caros)
    c.estado = "fallida" if c.productos and c.fallidos == c.productos else ("parcial" if c.fallidos else "completa")
    return caros


# ---------------------------------------------------------------- un producto, al momento

ACTUALIZANDO = "Trayendo los precios de la publicación elegida"


def preparar_actualizacion(bd: Session, producto_id: int) -> int | None:
    """Tras «Usar este» (Diego, 2026-10-20: «¿apoco debo esperar hasta que se corra todo?»): deja el renglón del
    producto en la última corrida esperando los vendedores de la publicación elegida. Regresa la corrida a
    actualizar, o None si no se puede ahora (otra corrida corre o todavía no hay ninguna): se hará en la siguiente."""
    if en_curso(bd):
        return None
    c = bd.scalar(select(PrecioCorrida).where(REGULAR).order_by(PrecioCorrida.fecha.desc(), PrecioCorrida.corrida_id.desc()))
    m, p = vigente(bd, producto_id), bd.get(Producto, producto_id)
    if not c or not m or not p:
        return None
    fila = bd.scalar(select(PrecioCorridaProducto).where(PrecioCorridaProducto.corrida_id == c.corrida_id,
                                                         PrecioCorridaProducto.producto_id == producto_id))
    if not fila:
        fila = PrecioCorridaProducto(corrida_id=c.corrida_id, producto_id=producto_id)
        bd.add(fila)
    if fila.estado == "pendiente" and fila.mensaje == ACTUALIZANDO:
        return None  # ya se están trayendo
    fila.estado, fila.mensaje, fila.coincidencia_id, fila.vendedores = "pendiente", ACTUALIZANDO, m.coincidencia_id, 0
    fila.minimo = fila.maximo = fila.promedio = fila.mediana = None
    fila.dif_lista_mediana_pct = fila.dif_membresia_mediana_pct = fila.dif_lista_minimo_pct = None
    fila.precio_lista, fila.precio_membresia = p.precio_lista_con_impuestos, p.precio_membresia_con_impuestos
    fila.precio_tienda = p.precio_tienda_en_linea
    bd.commit()
    return c.corrida_id


def actualizar_producto(bd: Session, corrida_id: int, producto_id: int) -> None:
    """Pide a DataForSEO los vendedores de la coincidencia del producto y recalcula su renglón. Nunca lanza."""
    c = bd.get(PrecioCorrida, corrida_id)
    fila = bd.scalar(select(PrecioCorridaProducto).where(PrecioCorridaProducto.corrida_id == corrida_id,
                                                         PrecioCorridaProducto.producto_id == producto_id))
    if not c or not fila:
        return
    try:
        Corrida(bd, c).precios({producto_id: fila})
    except Exception as e:  # noqa: BLE001 - corre aparte; el error queda en el renglón
        if not isinstance(e, dfs.ErrorDataForSEO):
            log.exception("Falló la actualización de un producto del radar de precios")
        bd.rollback()
        bd.expire_all()
        fila = bd.scalar(select(PrecioCorridaProducto).where(PrecioCorridaProducto.corrida_id == corrida_id,
                                                             PrecioCorridaProducto.producto_id == producto_id))
        fila.estado, fila.mensaje = "fallido", (str(e) if isinstance(e, dfs.ErrorDataForSEO) else "No se pudieron traer los precios")[:400]
    finally:
        _olvidar(corrida_id)
    if fila.estado == "pendiente":
        fila.estado, fila.mensaje = "fallido", "No se pudieron traer los precios"
    c = bd.get(PrecioCorrida, corrida_id)
    contar(bd, c, list(bd.scalars(select(PrecioCorridaProducto).where(PrecioCorridaProducto.corrida_id == corrida_id))))
    bd.commit()


def recalcular(bd: Session, producto_id: int) -> None:
    """Vuelve a sacar la mediana del renglón del producto en la última corrida con los precios que siguen contando
    (p. ej. después de «no es este producto» en una tienda). No pide nada a nadie."""
    if en_curso(bd):
        return
    fila = bd.scalar(select(PrecioCorridaProducto).join(PrecioCorrida, PrecioCorrida.corrida_id == PrecioCorridaProducto.corrida_id)
                     .where(PrecioCorridaProducto.producto_id == producto_id, REGULAR)
                     .order_by(PrecioCorrida.fecha.desc(), PrecioCorrida.corrida_id.desc()))
    if not fila or fila.estado not in ("con_precios", "sin_precios"):
        return
    obs = list(bd.scalars(select(PrecioObservacion).where(PrecioObservacion.corrida_id == fila.corrida_id,
                                                          PrecioObservacion.producto_id == producto_id,
                                                          del_renglon(fila.coincidencia_id))))
    fila.minimo = fila.maximo = fila.promedio = fila.mediana = None
    fila.dif_lista_mediana_pct = fila.dif_membresia_mediana_pct = fila.dif_lista_minimo_pct = None
    p = bd.get(Producto, producto_id)
    Corrida.calcular(fila, sin_repetir(obs), p.descripcion if p else None)
    if not fila.coincidencia_id and fila.estado == "sin_precios":
        fila.estado, fila.mensaje = "sin_coincidencia", "Sin coincidencia en Google y sin precios de los sitios de las tiendas"
    contar(bd, bd.get(PrecioCorrida, fila.corrida_id),
           list(bd.scalars(select(PrecioCorridaProducto).where(PrecioCorridaProducto.corrida_id == fila.corrida_id))))
    bd.commit()


def actualizar_aparte(corrida_id: int, producto_id: int) -> None:
    def tarea():
        from core.bd import _fabrica

        with _fabrica()() as bd:
            actualizar_producto(bd, corrida_id, producto_id)

    threading.Thread(target=tarea, name=f"precios-{corrida_id}-{producto_id}", daemon=True).start()


def correr(bd: Session, corrida: PrecioCorrida) -> PrecioCorrida:
    """Nunca lanza: los errores quedan en la corrida."""
    try:
        return Corrida(bd, corrida).correr()
    except Detenida:  # una persona la detuvo: ya quedó cerrada, no se toca
        bd.rollback()
        bd.expire_all()  # la cerró otra sesión
        return bd.get(PrecioCorrida, corrida.corrida_id)
    except Exception as e:  # noqa: BLE001 - la corrida automática no debe tumbar la API
        if not isinstance(e, dfs.ErrorDataForSEO):
            log.exception("Falló el radar de precios")
        bd.rollback()
        bd.expire_all()
        corrida = bd.get(PrecioCorrida, corrida.corrida_id)
        if corrida.estado != "en_curso":  # la detuvieron mientras fallaba
            return corrida
        _cerrar(bd, corrida, str(e) if isinstance(e, dfs.ErrorDataForSEO) else f"Error inesperado: {e.__class__.__name__}")
        modulo = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "compras"))
        for uid in _con_permiso(bd, ADMINISTRAR):
            notificar(bd, uid, "Falló el Radar de precios", f"La corrida del {corrida.fecha:%d/%m/%Y} falló: {corrida.error[:300]}",
                      liga="/compras/precios/corridas", modulo_id=modulo, clave=f"precios-error:{corrida.corrida_id}:{corrida.intentos}")
        bd.commit()
        return corrida


def correr_aparte(corrida_id: int) -> None:
    def tarea():
        from core.bd import _fabrica

        with _fabrica()() as bd:
            corrida = bd.get(PrecioCorrida, corrida_id)
            if corrida:
                try:
                    correr(bd, corrida)
                finally:
                    _olvidar(corrida_id)
                    DETENER.discard(corrida_id)

    threading.Thread(target=tarea, name=f"precios-{corrida_id}", daemon=True).start()


# ---------------------------------------------------------------- programación

MAX_INTENTOS = 3


def _dias_semana() -> set[int]:
    return {int(d) for d in (configuracion().precios_dias_semana or "").split(",") if d.strip().isdigit()} or set(range(1, 8))


def _ultima(bd: Session) -> date | None:
    return bd.scalar(select(func.max(PrecioCorrida.fecha)).where(PrecioCorrida.estado.in_(("completa", "parcial")), REGULAR))


def toca(bd: Session, fecha: date, ultima: date | None = None) -> bool:
    cfg = configuracion()
    if cfg.precios_frecuencia == "dias":
        return fecha.isoweekday() in _dias_semana()
    if cfg.precios_frecuencia == "cada_n":
        ultima = ultima if ultima is not None else _ultima(bd)
        return ultima is None or ultima >= fecha or (fecha - ultima).days >= max(cfg.precios_cada_dias, 1)
    return True


DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def texto_frecuencia() -> str:
    cfg = configuracion()
    if cfg.precios_frecuencia == "dias":
        dias = sorted(_dias_semana())
        if len(dias) == 7:
            return "Todos los días"
        if dias == [1, 2, 3, 4, 5]:
            return "De lunes a viernes"
        return "Cada " + ", ".join(DIAS[d - 1] for d in dias)
    if cfg.precios_frecuencia == "cada_n":
        return f"Cada {cfg.precios_cada_dias} días"
    return "Todos los días"


def proxima(bd: Session) -> datetime | None:
    cfg = configuracion()
    if not cfg.precios_activo:
        return None
    ahora_local = datetime.now(zona())
    hora = ahora_local.replace(hour=cfg.precios_hora, minute=0, second=0, microsecond=0)
    ultima = _ultima(bd)
    ya_hoy = bd.scalar(select(PrecioCorrida.corrida_id).where(PrecioCorrida.fecha == ahora_local.date())) is not None
    for n in range(0, 90):
        dia = hora + timedelta(days=n)
        if n == 0 and ya_hoy:
            continue
        if toca(bd, dia.date(), ultima):
            return dia
    return None


def revisar_programa(bd: Session) -> PrecioCorrida | None:
    """Lo llama el programador cada minuto. Si la plataforma estuvo apagada a la hora, corre al volver (tardía).
    Si falla, reintenta cada 30 minutos hasta 3 veces. Sin credenciales, tope o productos vigilados no hace nada."""
    cfg = configuracion()
    if not cfg.precios_activo or dfs.configurado():
        return None
    ahora_local = datetime.now(zona())
    if ahora_local.hour < cfg.precios_hora:
        return None
    fecha = ahora_local.date()
    existente = ultima_del_dia(bd, fecha)
    if existente:
        if existente.estado != "fallida" or existente.intentos >= MAX_INTENTOS:
            return None
        if (existente.error or "").startswith(DETENIDA):  # una persona la detuvo
            return None
        if (existente.terminado_en or ahora()) > ahora() - timedelta(minutes=30):
            return None
    elif not toca(bd, fecha):
        return None
    if not bd.scalar(select(func.count()).select_from(PrecioVigilado).where(PrecioVigilado.activo == true())):
        return None
    origen = "programado" if ahora_local.hour == cfg.precios_hora else "tardio"
    corrida = tomar_corrida(bd, fecha, origen)
    if not corrida:
        return None
    log.info("Radar de precios: corrida %s del %s", origen, fecha)
    correr_aparte(corrida.corrida_id)
    return corrida


def estimado(bd: Session, pares: list[tuple[PrecioVigilado, Producto]] | None = None) -> Decimal:
    """Lo más que costaría una corrida hoy: productos sin coincidencia pagan sus búsquedas; todos, vendedores."""
    total = Decimal("0")
    for v, p in (_vigilados(bd) if pares is None else pares):
        m = vigente(bd, p.producto_id)
        busquedas = 0 if m and not configuracion().precios_buscar_siempre else len(co.consultas(p.descripcion, p.marca, p.codigo_barras, v.consulta))
        maximo = configuracion().precios_max_publicaciones
        total += dfs.maximo_producto(busquedas, len(publicaciones(m, maximo)) if m else maximo)
    return total


def olvidar_producto(bd: Session, producto_id: int) -> None:
    """Quitar la vigilancia no borra nada: las coincidencias y precios quedan para el histórico."""
    bd.execute(delete(PrecioVigilado).where(PrecioVigilado.producto_id == producto_id))
