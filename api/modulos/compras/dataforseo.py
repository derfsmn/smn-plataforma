"""Cliente de DataForSEO (Google Shopping) para el Radar de precios.

Igual que el proyecto Radar Precios:
- Products busca el producto (por código de barras o por texto); Sellers trae el precio de cada vendedor.
- Son tareas: se envían (POST, se cobra), se espera a que estén listas y se recogen (GET, gratis).
- Antes de cada envío se calcula el máximo que puede costar y se revisan los topes (mes y corrida).
  El envío se guarda como "reservado" ANTES de mandarlo; si no hay respuesta clara queda "incierto" y
  NUNCA se repite, para no pagar dos veces. Un envío incierto cuenta con su máximo en el gasto del mes.
Usuario y contraseña se capturan en Configuración; nunca salen de la API.
"""
import base64
import contextvars
import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import configuracion
from modulos.compras.modelos_precios import PrecioCorrida, PrecioEnvio
from nucleo import actividad
from nucleo.modelos import ahora

log = logging.getLogger("smn.compras.precios")

POR_ENVIO = 100  # DataForSEO acepta hasta 100 tareas por POST
ESPERA = 10  # segundos entre revisiones de tareas listas
# Prioridad de las tareas: 1 normal (la cola barata; puede tardar minutos) o 2 alta (contesta en segundos, cuesta el
# doble). La evaluación de un producto la sube a 2 (26 nov 2026: frente a Dirección se evalúa en vivo; en la laptop la
# cola normal tardó 634 s en contestar una búsqueda). Las corridas del radar de precios siguen en 1.
PRIORIDAD: contextvars.ContextVar[int] = contextvars.ContextVar("prioridad_dataforseo", default=1)
POR_PRIORIDAD = {1: 1, 2: 2}
LIMITE = 900  # segundos máximos esperando resultados
RUTA = {"productos": "merchant/google/products", "vendedores": "merchant/google/sellers",
        "organico": "serp/google/organic",  # organico: búsqueda normal de Google para investigar afuera (17 nov 2026)
        "noticias": "serp/google/news",  # Google Noticias para el radar de noticias (18 nov 2026)
        "amazon": "merchant/amazon/products"}  # amazon: más vendidos y compras del mes en Amazon México (22 nov 2026)
BLOQUE = {"productos": 40, "vendedores": 10, "organico": 10, "noticias": 10, "amazon": 100}  # se cobra por cada bloque de resultados
# USD por bloque; las demás usan la tarifa de Configuración. Amazon: US$0.0015 por página en prioridad normal
# (dataforseo.com/amazon-product-api, revisado el 22 nov 2026)
TARIFA = {"organico": Decimal("0.0006"), "noticias": Decimal("0.0006"), "amazon": Decimal("0.0015")}


class ErrorDataForSEO(Exception):
    """Error con mensaje para la persona."""


class SinPresupuesto(ErrorDataForSEO):
    pass


class EnvioIncierto(ErrorDataForSEO):
    pass


def configurado() -> list[str]:
    cfg = configuracion()
    falta = []
    if not cfg.dataforseo_usuario:
        falta.append("usuario de DataForSEO")
    if not cfg.dataforseo_contrasena:
        falta.append("contraseña de DataForSEO")
    if not cfg.precios_tope_mensual_usd:
        falta.append("tope de gasto al mes")
    return falta


def _peticion(metodo: str, ruta: str, cuerpo=None) -> dict:
    cfg = configuracion()
    llave = base64.b64encode(f"{cfg.dataforseo_usuario}:{cfg.dataforseo_contrasena}".encode()).decode()
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    intentos = 1 if metodo == "POST" else 3  # un POST sin respuesta pudo haberse cobrado: no se repite
    ultimo: Exception | None = None
    for intento in range(intentos):
        peticion = urllib.request.Request(f"{cfg.dataforseo_url.rstrip('/')}{ruta}", data=datos, method=metodo,
                                          headers={"Authorization": f"Basic {llave}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(peticion, timeout=60) as r:
                respuesta = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise ErrorDataForSEO("DataForSEO rechazó el usuario o la contraseña. Revísalos en Configuración.") from e
            if e.code < 500 and e.code != 429:
                raise ErrorDataForSEO(f"DataForSEO respondió con error {e.code}.") from e
            ultimo = e
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            ultimo = e
        else:
            codigo = int(respuesta.get("status_code") or 20000)
            if codigo in (40100, 40101, 40102, 40103, 40104):
                raise ErrorDataForSEO("DataForSEO rechazó el usuario o la contraseña. Revísalos en Configuración.")
            if codigo == 40200 or codigo == 40210:
                raise ErrorDataForSEO("La cuenta de DataForSEO no tiene saldo suficiente.")
            if codigo >= 40000:
                raise ErrorDataForSEO(f"DataForSEO: {respuesta.get('status_message') or codigo}")
            return respuesta
        if intento < intentos - 1:
            time.sleep(2 + intento * 3)
    if metodo == "POST":
        raise EnvioIncierto("No hubo respuesta clara de DataForSEO al enviar; no se repitió para no pagar dos veces.") from ultimo
    raise ErrorDataForSEO("No se pudo conectar con DataForSEO.") from ultimo


# ---------------------------------------------------------------- gasto

# DataForSEO cobra 5 veces la búsqueda normal de Google si lleva operadores como «site:» (medido el 26 nov 2026:
# US$0.003 por bloque de 10 contra US$0.0006 sin operador). Sin esto el estimado y el tope se quedaban cortos.
POR_OPERADOR = 5


def con_operadores(keyword: str | None) -> bool:
    return bool(re.search(r"(^|\s)(site|intitle|inurl|allintitle|related):", keyword or ""))


def maximo_tarea(tipo: str, profundidad: int, operadores: bool = False) -> Decimal:
    tarifa = TARIFA.get(tipo) or Decimal(str(configuracion().precios_tarifa_usd))
    bloques = (profundidad + BLOQUE[tipo] - 1) // BLOQUE[tipo]
    return tarifa * bloques * (POR_OPERADOR if operadores and tipo in ("organico", "noticias") else 1)


def maximo_producto(busquedas: int, publicaciones: int = 1) -> Decimal:
    """Lo más que cuesta un producto en una corrida: sus búsquedas más una consulta de vendedores por publicación."""
    cfg = configuracion()
    return maximo_tarea("productos", cfg.precios_profundidad) * busquedas + maximo_tarea("vendedores", 10) * publicaciones


def inicio_de_mes() -> datetime:
    hoy = ahora()
    return datetime(hoy.year, hoy.month, 1)


def _gastado(bd: Session, filtro) -> Decimal:
    """Confirmado = lo cobrado; reservado o incierto = su máximo (puede haberse cobrado)."""
    valor = func.coalesce(func.sum(
        func.iif(PrecioEnvio.estado.in_(("reservado", "incierto")), PrecioEnvio.estimado_usd,
                 func.coalesce(PrecioEnvio.costo_usd, 0))), 0)
    return Decimal(str(bd.scalar(select(valor).where(filtro)) or 0))


def gasto_mes(bd: Session) -> Decimal:
    return _gastado(bd, PrecioEnvio.creado_en >= inicio_de_mes())


def gasto_mes_tipo(bd: Session, tipo: str) -> Decimal:
    return _gastado(bd, (PrecioEnvio.creado_en >= inicio_de_mes()) & (PrecioEnvio.tipo == tipo))


def gasto_corrida(bd: Session, corrida_id: int) -> Decimal:
    return _gastado(bd, PrecioEnvio.corrida_id == corrida_id)


def _revisar_topes(bd: Session, corrida: PrecioCorrida, estimado: Decimal) -> None:
    cfg = configuracion()
    tope_mes = Decimal(str(cfg.precios_tope_mensual_usd))
    if gasto_mes(bd) + estimado > tope_mes:
        raise SinPresupuesto(f"Se llegó al tope de gasto del mes (USD {tope_mes:.2f}).")
    if corrida.tope_usd is not None and gasto_corrida(bd, corrida.corrida_id) + estimado > corrida.tope_usd:
        raise SinPresupuesto(f"Se llegó al tope de gasto por corrida (USD {corrida.tope_usd:.2f}).")


def queda(bd: Session, corrida: PrecioCorrida) -> Decimal:
    """Lo que todavía se puede gastar en esta corrida: lo menor entre lo que queda del mes y lo que queda de su tope."""
    libre = Decimal(str(configuracion().precios_tope_mensual_usd)) - gasto_mes(bd)
    if corrida.tope_usd is not None:
        libre = min(libre, corrida.tope_usd - gasto_corrida(bd, corrida.corrida_id))
    return libre


def motivo_tope(bd: Session, corrida: PrecioCorrida) -> str:
    """Cuál de los dos topes es el que ya no deja gastar."""
    tope_mes = Decimal(str(configuracion().precios_tope_mensual_usd))
    if corrida.tope_usd is not None and corrida.tope_usd - gasto_corrida(bd, corrida.corrida_id) <= tope_mes - gasto_mes(bd):
        return f"Se llegó al tope de gasto por corrida (USD {corrida.tope_usd:.2f})."
    return f"Se llegó al tope de gasto del mes (USD {tope_mes:.2f})."


class Enviadas(dict):
    """{tag: id de la tarea}. Con «parcial», si el presupuesto no alcanzó para todas: el motivo y las que no salieron."""
    sin_presupuesto: str | None = None
    sin_enviar: tuple[str, ...] = ()


# ---------------------------------------------------------------- tareas

# Amazon usa sus propios idiomas: «Spanish» lo rechazaba con «Invalid Field: 'language_name'» y la búsqueda en Amazon
# México nunca corría (revisión del 26 nov 2026; catálogo gratis /v3/merchant/amazon/languages: «Spanish (Mexico)»)
IDIOMA_AMAZON = {"Spanish": "Spanish (Mexico)", "English": "English (United States)"}


def idioma(tipo: str, idioma_cfg: str) -> str:
    return IDIOMA_AMAZON.get(idioma_cfg, idioma_cfg) if tipo == "amazon" else idioma_cfg


def enviar(bd: Session, corrida: PrecioCorrida, tipo: str, tareas: list[dict], reserva: Decimal = Decimal("0"),
           parcial: bool = False) -> Enviadas:
    """Envía tareas (cada una con su "tag"). Devuelve {tag: id de la tarea}. Las que DataForSEO rechazó no salen.
    Lanza SinPresupuesto antes de enviar un lote que no cabe; los lotes ya enviados se conservan.
    «reserva»: dinero que debe quedar libre después de este envío para lo que falta de la corrida (27 nov 2026: una
    corrida gastó todo en búsquedas y no le alcanzó para traer los precios). «parcial»: si no cabe todo, manda las
    que sí caben (en orden) y lo dice en el resultado en vez de lanzar el error."""
    cfg = configuracion()
    ids = Enviadas()
    for inicio in range(0, len(tareas), POR_ENVIO):
        prioridad = PRIORIDAD.get()
        costo_de = lambda t: (maximo_tarea(tipo, int(t.get("depth") or BLOQUE[tipo]), con_operadores(t.get("keyword")))  # noqa: E731
                              * POR_PRIORIDAD.get(prioridad, 1))
        crudas = tareas[inicio:inicio + POR_ENVIO]
        try:
            _revisar_topes(bd, corrida, sum((costo_de(t) for t in crudas), Decimal("0")) + reserva)
        except SinPresupuesto as e:
            if not parcial:
                raise
            libre, n, suma = queda(bd, corrida) - reserva, 0, Decimal("0")
            for t in crudas:
                if suma + costo_de(t) > libre:
                    break
                suma, n = suma + costo_de(t), n + 1
            ids.sin_presupuesto = str(e)
            ids.sin_enviar = tuple(str(t.get("tag") or "") for t in tareas[inicio + n:])
            crudas = crudas[:n]
            if not crudas:
                return ids
        lote = [{**t, "location_name": cfg.precios_ubicacion, "language_name": idioma(tipo, cfg.precios_idioma), "priority": prioridad}
                for t in crudas]
        estimado = sum((costo_de(t) for t in crudas), Decimal("0"))
        envio = PrecioEnvio(corrida_id=corrida.corrida_id, tipo=tipo, tareas=len(lote), estado="reservado", estimado_usd=estimado)
        bd.add(envio)
        bd.commit()
        try:
            respuesta = _peticion("POST", f"/v3/{RUTA[tipo]}/task_post", lote)
        except EnvioIncierto:
            envio.estado = "incierto"
            bd.commit()
            raise
        except ErrorDataForSEO:
            envio.estado, envio.costo_usd = "rechazado", Decimal("0")
            bd.commit()
            raise
        actividad.contar(len(lote))  # gráfica en vivo del Monitor
        costo = Decimal("0")
        guardadas = []
        for t in respuesta.get("tasks") or []:
            costo += Decimal(str(t.get("cost") or 0))
            tag = str((t.get("data") or {}).get("tag") or "")
            if t.get("id") and int(t.get("status_code") or 0) < 40000 and tag:
                ids[tag] = str(t["id"])
            guardadas.append({"id": t.get("id"), "tag": tag, "estado": t.get("status_code"), "mensaje": t.get("status_message")})
        envio.estado, envio.costo_usd, envio.confirmado_en = "confirmado", costo, ahora()
        envio.respuesta = json.dumps(guardadas, ensure_ascii=False)
        corrida.costo_usd = (corrida.costo_usd or Decimal("0")) + costo
        bd.commit()
        if ids.sin_presupuesto:
            break
    return ids


def _ids_listos(tipo: str) -> set[str]:
    datos = _peticion("GET", f"/v3/{RUTA[tipo]}/tasks_ready")
    return {str(r.get("id")) for t in datos.get("tasks") or [] for r in (t.get("result") or []) if isinstance(r, dict) and r.get("id")}


def recoger(tipo: str, ids: dict[str, str], detenida: Callable[[], bool] = lambda: False,
            avance: Callable[[set[str]], None] | None = None) -> dict[str, list[dict] | str]:
    """Espera a que las tareas estén listas. Devuelve {tag: lista de resultados} o {tag: mensaje de error}.
    Recoger no cuesta. Si una tarea no termina a tiempo, regresa el error y no se vuelve a pagar.
    avance recibe los tags que siguen sin contestar, cada vez que se revisa."""
    pendientes = {id_: tag for tag, id_ in ids.items()}
    salida: dict[str, list[dict] | str] = {}
    limite = time.monotonic() + LIMITE
    directo = 0.0
    while pendientes and time.monotonic() < limite:
        if detenida():
            break
        try:
            listos = _ids_listos(tipo) & set(pendientes)
        except ErrorDataForSEO as e:
            log.warning("No se pudo revisar qué tareas están listas: %s", e)
            listos = set()
        if time.monotonic() >= directo:  # cada 30 s se piden todas por si tasks_ready ya no las lista
            listos, directo = set(pendientes), time.monotonic() + 30
        for id_ in listos:
            try:
                datos = _peticion("GET", f"/v3/{RUTA[tipo]}/task_get/advanced/{id_}")
            except ErrorDataForSEO as e:
                if "error 404" in str(e) or "40400" in str(e):
                    continue
                log.warning("No se pudo recoger la tarea %s: %s", id_, e)
                continue
            tarea = (datos.get("tasks") or [{}])[0]
            codigo = int(tarea.get("status_code") or 0)
            if codigo in (20100, 40601, 40602) or codigo == 0:  # sigue en proceso
                continue
            tag = pendientes.pop(id_)
            if codigo >= 40000:
                salida[tag] = str(tarea.get("status_message") or f"Error {codigo}")
                continue
            salida[tag] = [i for r in tarea.get("result") or [] if isinstance(r, dict)
                           for i in r.get("items") or [] if isinstance(i, dict)]
        if avance:
            avance(set(pendientes.values()))
        if pendientes:
            time.sleep(ESPERA)
    for tag in pendientes.values():
        salida[tag] = "La tarea no terminó a tiempo en DataForSEO"
    return salida
