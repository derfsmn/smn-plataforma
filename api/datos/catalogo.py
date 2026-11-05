"""Carga del catálogo de productos (esquema datos).

Fuentes, de mayor a menor prioridad: ETL de la base de Sistemas en Azure (después), API de artículos de SMN
(smnapps) y tienda en línea (Shopify, `datos/tienda.py`). Lo que llega de cada fuente se guarda tal cual en
producto_fuente; la fila de producto toma cada campo de la fuente con más prioridad que lo traiga.

Reglas que vienen del proyecto Radar Precios:
- El SKU es texto y se respeta tal cual (ceros iniciales).
- El API da precio lista y membresía SIN impuestos; las tasas de IVA e IEPS vienen en porcentaje (16 = 16 %).
  El precio con impuestos es base + IEPS y luego IVA sobre esa suma. Si falta el IVA no se calcula;
  si el IEPS viene vacío se toma como 0 % (así llega en productos sin IEPS, p. ej. 19331).
- Solo una carga que recorrió toda la fuente puede marcar productos como ausentes. Nunca se borra un producto.
- Historial de precios: una fila solo cuando algún precio o tasa cambia.
- Imagen: primero la foto publicada en el CDN de la tienda con el SKU como nombre; si no hay, la del producto en la tienda.
- Solo corre una carga a la vez (de cualquier fuente), porque todas escriben en las mismas filas.
"""
import base64
import hashlib
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, select, true
from sqlalchemy.orm import Session, selectinload

from core.config import configuracion
from datos.modelos import Carga, Producto, ProductoFuente, ProductoPrecioHistorial
from nucleo.modelos import ahora

log = logging.getLogger("smn.datos.catalogo")

# SMNBI (fuente ETL, tblArticulos) va al final: solo completa lo que el API y la tienda no traen. Su Marca y
# Departamento vienen cortados a 20 caracteres, y su IVA no se usa (los precios con impuestos son del API).
PRIORIDAD = ("API", "TIENDA", "ETL")
FUENTES = ("API", "TIENDA")  # cargas del catálogo; el ETL de ventas usa ETL_VENTAS
MAX_PAGINAS = 10000
MAX_INTENTOS_DIA = 3
CARGA_COLGADA = timedelta(hours=2)  # una carga en curso más vieja que esto se dio por perdida (se reinició la API)

# Campo del producto -> (campo del API, largo máximo)
CAMPOS_API = {
    "descripcion": ("descripcion1", 1000), "departamento": ("departamento", 300), "rama": ("rama", 300),
    "marca": ("marca", 300), "subcategoria": ("subcategoria", 300), "segmento": ("segmento", 300),
    "clasificacion": ("clasificacion", 100), "codigo_proveedor": ("proveedor", 150), "nombre_proveedor": ("nombre", 500),
}
NUMERICOS_API = {"precio_lista": "preciolista", "precio_membresia": "preciomem", "iva_pct": "iva", "ieps_pct": "ieps"}

CAMPOS_ETL = ("categoria", "fabricante", "tipo_compra", "estatus_erp")  # solo los trae SMNBI
CAMPOS_TEXTO = (*CAMPOS_API, "codigo_barras", "liga_producto", "liga_imagen", *CAMPOS_ETL)
CAMPOS_NUMERO = (*NUMERICOS_API, "precio_tienda_en_linea")
CAMPOS_PRECIO = ("precio_lista", "precio_membresia", "iva_pct", "ieps_pct", "precio_tienda_en_linea")
# Sin estos el producto se marca con datos incompletos
REQUERIDOS = ("descripcion", "marca", "precio_lista")
# Campos que se comparan entre fuentes para marcar diferencias. La descripción no: en la tienda el nombre es
# comercial y casi nunca coincide con la descripción del API.
COMPARABLES = ("marca",)


class ErrorCarga(Exception):
    pass


# ---------------------------------------------------------------- normalización

def _numero(valor, campo: str) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        if isinstance(valor, bool):
            raise ValueError
        n = Decimal(str(valor))
        if not n.is_finite() or n < 0 or n > Decimal("9999999999"):
            raise ValueError
        return n.quantize(Decimal("0.0001"))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Valor numérico inválido en {campo}") from None


def normalizar_api(fila) -> tuple[str, dict]:
    """Un artículo del API -> (sku, valores con los nombres del producto). ValueError si no sirve."""
    if not isinstance(fila, dict):
        raise ValueError("El registro no es un objeto")
    sku = str(fila.get("articulo") or "").strip()
    if not sku or len(sku) > 80:
        raise ValueError("SKU vacío o demasiado largo")
    valores: dict = {}
    for campo, (clave, largo) in CAMPOS_API.items():
        v = fila.get(clave)
        v = None if v is None else " ".join(str(v).split()) or None
        if v and len(v) > largo:
            raise ValueError(f"{clave} demasiado largo en el SKU {sku}")
        valores[campo] = v
    for campo, clave in NUMERICOS_API.items():
        valores[campo] = _numero(fila.get(clave), clave)
    return sku, valores


def normalizar_tienda(fila) -> tuple[str, dict]:
    """Una variante de la tienda en línea, ya armada por datos/tienda.py -> (sku, valores)."""
    if not isinstance(fila, dict):
        raise ValueError("El registro no es un objeto")
    sku = str(fila.get("sku") or "").strip()
    if not sku or len(sku) > 80:
        raise ValueError("Variante sin SKU")
    titulo = " ".join(str(fila.get("titulo") or "").split()) or None
    variante = " ".join(str(fila.get("variante") or "").split())
    if titulo and variante and variante.casefold() != "default title":
        titulo = f"{titulo} - {variante}"
    centavos = fila.get("precio_centavos")
    precio = None if centavos in (None, "") else (_numero(centavos, "price") / 100).quantize(Decimal("0.01"))
    def texto(clave: str, largo: int) -> str | None:
        return " ".join(str(fila.get(clave) or "").split())[:largo] or None

    return sku, {
        "descripcion": titulo[:1000] if titulo else None, "marca": texto("marca", 300),
        "codigo_barras": texto("codigo_barras", 60), "precio_tienda_en_linea": precio,
        "disponible_en_linea": None if fila.get("disponible") is None else bool(fila["disponible"]),
        "liga_producto": texto("liga", 600), "liga_imagen": texto("imagen", 600),
    }


# Columnas de tblArticulos en el orden de la consulta de SMNBI (datos/smnbi.py) -> campo del producto y largo
COLUMNAS_ETL = (("sku", 80), ("descripcion", 1000), ("departamento", 300), ("rama", 300), ("categoria", 300),
                ("subcategoria", 300), ("segmento", 300), ("fabricante", 300), ("codigo_proveedor", 150), ("marca", 300),
                ("tipo_compra", 100), ("clasificacion", 100), ("estatus_erp", 30), ("codigo_barras", 60))


def normalizar_etl(fila) -> tuple[str, dict]:
    """Un artículo de tblArticulos (lista en el orden de COLUMNAS_ETL, o dict) -> (sku, valores)."""
    if isinstance(fila, (list, tuple)):
        fila = dict(zip((c for c, _ in COLUMNAS_ETL), fila))
    if not isinstance(fila, dict):
        raise ValueError("El registro no es una fila")
    valores = {}
    for campo, largo in COLUMNAS_ETL:
        v = fila.get(campo)
        v = None if v is None else " ".join(str(v).split()) or None
        if v and v.upper() == "NULL":
            v = None
        valores[campo] = v[:largo] if v else None
    sku = valores.pop("sku") or ""
    if not sku:
        raise ValueError("Artículo sin clave")
    return sku, valores


NORMALIZADORES = {"API": normalizar_api, "TIENDA": normalizar_tienda, "ETL": normalizar_etl}


def con_impuestos(base: Decimal | None, iva: Decimal | None, ieps: Decimal | None) -> Decimal | None:
    if base is None or iva is None:
        return None
    total = base * (1 + (ieps or Decimal(0)) / 100) * (1 + iva / 100)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _comparable(v) -> str:
    return " ".join(str(v).casefold().split())


# ---------------------------------------------------------------- consolidación

def resolver(bd: Session, producto: Producto, carga: Carga | None) -> bool:
    """Arma la fila del producto a partir de sus fuentes presentes. Devuelve True si cambió algún precio."""
    presentes = sorted((f for f in producto.fuentes if f.presente and f.fuente in NORMALIZADORES),
                       key=lambda f: PRIORIDAD.index(f.fuente))
    if not presentes:
        # Ya no viene en ninguna fuente: se archiva con sus últimos valores
        producto.origen, producto.activo = "ARCHIVADO", False
        producto.actualizado_en = ahora()
        return False

    por_fuente = {f.fuente: NORMALIZADORES[f.fuente](json.loads(f.datos))[1] for f in presentes}
    antes = tuple(getattr(producto, c) for c in CAMPOS_PRECIO)
    de_donde: dict[str, str] = {}
    for campo in (*CAMPOS_TEXTO, *CAMPOS_NUMERO, "disponible_en_linea"):
        valor, fuente = None, None
        for f in presentes:
            v = por_fuente[f.fuente].get(campo)
            if v is not None:
                valor, fuente = v, f.fuente
                break
        setattr(producto, campo, valor)
        if fuente:
            de_donde[campo] = fuente

    if producto.imagen_cdn:
        producto.liga_imagen, de_donde["liga_imagen"] = producto.imagen_cdn, "CDN"

    diferencias = []
    for campo in COMPARABLES:
        vistos = {f: v for f, vals in por_fuente.items() if (v := vals.get(campo))}
        if len({_comparable(v) for v in vistos.values()}) > 1:
            diferencias.append({"campo": campo, "valores": vistos})

    producto.precio_lista_con_impuestos = con_impuestos(producto.precio_lista, producto.iva_pct, producto.ieps_pct)
    producto.precio_membresia_con_impuestos = con_impuestos(producto.precio_membresia, producto.iva_pct, producto.ieps_pct)
    fuentes = set(por_fuente)
    producto.origen = "AMBOS" if {"API", "TIENDA"} <= fuentes else presentes[0].fuente
    # Solo en SMNBI y descontinuado: queda para ligar ventas viejas, pero no cuenta como activo
    producto.activo = not (fuentes == {"ETL"} and (producto.estatus_erp or "").upper() == "DESCONTINUADO")
    producto.con_diferencias = bool(diferencias)
    producto.datos_incompletos = any(getattr(producto, c) is None for c in REQUERIDOS)
    producto.diferencias = json.dumps({"de_donde": de_donde, "diferencias": diferencias}, ensure_ascii=False, default=str)
    producto.actualizado_en = ahora()

    despues = tuple(getattr(producto, c) for c in CAMPOS_PRECIO)
    hay_historial = producto.producto_id and bd.scalar(
        select(ProductoPrecioHistorial.historial_id).where(ProductoPrecioHistorial.producto_id == producto.producto_id).limit(1))
    if hay_historial and _iguales(antes, despues):
        return False
    bd.flush()
    bd.add(ProductoPrecioHistorial(producto_id=producto.producto_id, carga_id=carga.carga_id if carga else None,
                                   **dict(zip(CAMPOS_PRECIO, despues))))
    # Cuenta como "precio nuevo" solo si cambió un precio que ya existía (no cuando una fuente lo trae por primera vez)
    return bool(hay_historial) and any(x is not None and not _iguales((x,), (y,)) for x, y in zip(antes, despues))


def _iguales(a: tuple, b: tuple) -> bool:
    return all((x is None and y is None) or (x is not None and y is not None and Decimal(x) == Decimal(y)) for x, y in zip(a, b))


def _huella(fila) -> tuple[str, str]:
    texto = json.dumps(fila, sort_keys=True, ensure_ascii=False, default=str)
    return texto, hashlib.sha256(texto.encode()).hexdigest()


def procesar(bd: Session, carga: Carga, filas: list, vistos: set[str], fuente_producto: str | None = None) -> None:
    """Guarda una página de la fuente de la carga y la confirma junto con los contadores.
    fuente_producto: con qué nombre se guarda la fuente del producto (los artículos de SMNBI se guardan como ETL)."""
    origen = fuente_producto or carga.fuente
    validas: dict[str, object] = {}
    for fila in filas:
        try:
            sku, _ = NORMALIZADORES[origen](fila)
        except ValueError as e:
            carga.invalidos += 1
            log.info("Registro inválido en la carga %s: %s", carga.carga_id, e)
            continue
        if sku in vistos or sku in validas:
            carga.invalidos += 1  # SKU repetido en la misma fuente: se queda el primero
            continue
        validas[sku] = fila
    existentes = {p.sku: p for p in bd.scalars(
        select(Producto).where(Producto.sku.in_(list(validas))).options(selectinload(Producto.fuentes)))} if validas else {}
    momento = ahora()
    for sku, fila in validas.items():
        vistos.add(sku)
        carga.leidos += 1
        texto, huella = _huella(fila)
        producto = existentes.get(sku)
        nuevo = producto is None
        if nuevo:
            producto = Producto(sku=sku, origen=origen, creado_en=momento)
            producto.fuentes = []
            bd.add(producto)
        fuente = next((f for f in producto.fuentes if f.fuente == origen and f.clave_externa == ""), None)
        if fuente and fuente.huella == huella and fuente.presente:
            fuente.visto_por_ultima_vez_en = momento
            carga.sin_cambios += 1
            continue
        if fuente is None:
            fuente = ProductoFuente(fuente=origen, clave_externa="")
            producto.fuentes.append(fuente)
        fuente.datos, fuente.huella, fuente.presente, fuente.visto_por_ultima_vez_en = texto, huella, True, momento
        bd.flush()
        if resolver(bd, producto, carga):
            carga.precios_cambiados += 1
        if nuevo:
            carga.creados += 1
        else:
            carga.actualizados += 1
    carga.paginas += 1
    bd.commit()


def marcar_ausentes(bd: Session, carga: Carga, fuente_producto: str | None = None) -> None:
    """Solo después de recorrer toda la fuente: lo que no vino en esta carga queda como ausente."""
    faltantes = bd.scalars(select(ProductoFuente).where(
        ProductoFuente.fuente == (fuente_producto or carga.fuente), ProductoFuente.presente == true(),
        ProductoFuente.visto_por_ultima_vez_en < carga.inicio_en).options(selectinload(ProductoFuente.producto))).all()
    for f in faltantes:
        f.presente = False
        bd.flush()
        bd.refresh(f.producto, ["fuentes"])
        resolver(bd, f.producto, carga)
        carga.ausentes += 1
    bd.commit()


# ---------------------------------------------------------------- API de artículos de SMN

def api_configurada() -> list[str]:
    """Lo que falta capturar en Configuración para poder cargar del API (vacío = lista)."""
    cfg = configuracion()
    falta = []
    if not cfg.catalogo_api_url:
        falta.append("dirección del API de artículos")
    if not cfg.catalogo_api_usuario:
        falta.append("usuario del API de artículos")
    if not cfg.catalogo_api_contrasena:
        falta.append("contraseña del API de artículos")
    return falta


def _liga_segura(base: str, liga: str) -> str:
    """La paginación solo puede seguir en el mismo servidor y la misma ruta que la dirección capturada."""
    origen, destino = urlparse(base), urlparse(urljoin(base, liga))
    # Configuración guarda la dirección sin "/" final; el API puede paginar con ella
    if (destino.hostname != origen.hostname or destino.path.rstrip("/") != origen.path.rstrip("/")
            or destino.scheme not in ("http", "https")):
        raise ErrorCarga("La paginación del API apunta fuera de la dirección autorizada.")
    return urlunparse(destino._replace(scheme=origen.scheme))


def _pedir(url: str) -> dict:
    """Una página del API con usuario y contraseña (autenticación básica). Reintenta errores pasajeros."""
    cfg = configuracion()
    credencial = base64.b64encode(f"{cfg.catalogo_api_usuario}:{cfg.catalogo_api_contrasena}".encode()).decode()
    peticion = urllib.request.Request(url, headers={"Authorization": f"Basic {credencial}", "Accept": "application/json"})
    for intento in range(3):
        try:
            with urllib.request.urlopen(peticion, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise ErrorCarga("El API de artículos rechazó el usuario o la contraseña.") from e
            if (e.code < 500 and e.code != 429) or intento == 2:
                raise ErrorCarga(f"El API de artículos respondió con error {e.code}.") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if intento == 2:
                raise ErrorCarga("No se pudo conectar con el API de artículos.") from e
        except ValueError as e:
            raise ErrorCarga("El API de artículos no respondió con datos válidos.") from e
        time.sleep(1 + intento * 2)
    raise ErrorCarga("No se pudo conectar con el API de artículos.")


def _pagina(base: str, url: str) -> dict:
    datos = _pedir(url)
    if not isinstance(datos, dict) or not isinstance(datos.get("results"), list):
        raise ErrorCarga("La respuesta del API no trae la lista de artículos (results).")
    siguiente = datos.get("next")
    if siguiente is not None and (not isinstance(siguiente, str) or not siguiente):
        raise ErrorCarga("La respuesta del API trae una página siguiente inválida.")
    datos["next"] = _liga_segura(base, siguiente) if siguiente else None
    return datos


def cargar_api(bd: Session, carga: Carga) -> Carga:
    base = configuracion().catalogo_api_url
    try:
        if falta := api_configurada():
            raise ErrorCarga("Falta capturar en Configuración: " + ", ".join(falta) + ".")
        url, pedidas, vistos = base, set(), set()
        while url:
            if url in pedidas or len(pedidas) >= MAX_PAGINAS:
                raise ErrorCarga("La paginación del API se repite; la carga se detuvo para no ciclarse.")
            pedidas.add(url)
            datos = _pagina(base, url)
            if isinstance(datos.get("count"), int) and not isinstance(datos["count"], bool):
                carga.total_fuente = datos["count"]
            procesar(bd, carga, datos["results"], vistos)
            url = datos["next"]
        carga.completa = True
        marcar_ausentes(bd, carga)
        carga.estado = "completa"
    except Exception as e:  # noqa: BLE001 - toda falla queda registrada en la carga
        bd.rollback()
        carga = bd.get(Carga, carga.carga_id)
        carga.estado = "fallida"
        carga.error = (str(e) if isinstance(e, ErrorCarga) else f"Error inesperado: {type(e).__name__}")[:1000]
        if not isinstance(e, ErrorCarga):
            log.exception("La carga %s del catálogo falló", carga.carga_id)
    carga.fin_en = ahora()
    bd.commit()
    return carga


def _cargador(fuente: str):
    if fuente == "TIENDA":
        from datos.tienda import cargar_tienda

        return cargar_tienda
    return cargar_api


# ---------------------------------------------------------------- corridas

def en_curso(bd: Session) -> Carga | None:
    """La carga del catálogo que está corriendo, de cualquier fuente (las del ETL de ventas van aparte)."""
    for c in bd.scalars(select(Carga).where(Carga.estado == "en_curso", Carga.fuente.in_(FUENTES))):
        if c.inicio_en < ahora() - CARGA_COLGADA:
            c.estado, c.error, c.fin_en = "fallida", "Se interrumpió (la plataforma se reinició durante la carga).", ahora()
            bd.commit()
            continue
        return c
    return None


def iniciar(bd: Session, fuente: str, disparada_por: str, usuario_id: int | None = None) -> Carga | None:
    """Registra una carga nueva; None si ya hay una en curso (de cualquier fuente)."""
    if en_curso(bd):
        return None
    carga = Carga(fuente=fuente, disparada_por=disparada_por, usuario_id=usuario_id, estado="en_curso", inicio_en=ahora())
    bd.add(carga)
    bd.commit()
    return carga


def ejecutar(bd: Session, carga: Carga) -> Carga:
    log.info("Catálogo: carga %s de %s (%s)", carga.carga_id, carga.fuente, carga.disparada_por)
    return _cargador(carga.fuente)(bd, carga)


def ejecutar_aparte(carga_id: int) -> None:
    """Corre la carga en su propio hilo, para no detener al programador ni a la pantalla."""
    from core.bd import _fabrica

    def correr():
        with _fabrica()() as bd:
            if carga := bd.get(Carga, carga_id):
                ejecutar(bd, carga)

    threading.Thread(target=correr, daemon=True, name=f"carga-{carga_id}").start()


def tienda_configurada() -> list[str]:
    return [] if configuracion().tienda_url else ["dirección de la tienda en línea"]


FALTA = {"API": api_configurada, "TIENDA": tienda_configurada}


def zona() -> ZoneInfo:
    return ZoneInfo(configuracion().catalogo_zona_horaria)


def revisar_programa(bd: Session) -> Carga | None:
    """Lo llama el programador cada minuto. En los días y la hora elegidos carga una vez cada fuente configurada:
    primero el API de artículos y luego la tienda en línea (una a la vez). Si una falla, reintenta cada 30 minutos
    hasta 3 veces ese día. La carga corre en su propio hilo."""
    cfg = configuracion()
    if not cfg.catalogo_activo or en_curso(bd):
        return None
    local = datetime.now(zona())
    dias = {d.strip() for d in cfg.catalogo_dias_semana.split(",")}
    if local.hour < cfg.catalogo_hora or str(local.isoweekday()) not in dias:
        return None
    inicio_dia = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    for fuente in ("API", "TIENDA"):
        if FALTA[fuente]():
            continue
        hoy = bd.scalars(select(Carga).where(Carga.fuente == fuente, Carga.disparada_por == "programador",
                                             Carga.inicio_en >= inicio_dia).order_by(Carga.inicio_en)).all()
        if any(c.estado == "completa" for c in hoy) or len(hoy) >= MAX_INTENTOS_DIA:
            continue
        if hoy and (hoy[-1].fin_en or ahora()) > ahora() - timedelta(minutes=30):
            return None  # espera para reintentar esta fuente antes de pasar a la siguiente
        if carga := iniciar(bd, fuente, "programador"):
            ejecutar_aparte(carga.carga_id)
        return carga
    return None


def totales(bd: Session) -> dict:
    def contar(*condiciones):
        return func.sum(case((and_(Producto.activo == true(), *condiciones), 1), else_=0))

    fila = bd.execute(select(
        func.count(Producto.producto_id), contar(),
        contar(Producto.con_diferencias == true()), contar(Producto.datos_incompletos == true()),
        contar(Producto.origen.in_(("TIENDA", "AMBOS"))), contar(Producto.origen.in_(("API", "AMBOS"))),
        contar(Producto.liga_imagen.is_not(None)),
    )).one()
    total, activos = fila[0] or 0, int(fila[1] or 0)
    return {"productos": total, "activos": activos, "archivados": total - activos,
            "con_diferencias": int(fila[2] or 0), "incompletos": int(fila[3] or 0),
            "en_tienda": int(fila[4] or 0), "en_api": int(fila[5] or 0), "con_imagen": int(fila[6] or 0)}
