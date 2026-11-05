"""Puerta de IA: el único lugar desde donde la plataforma llama a una IA.

- Cada módulo declara sus tareas en nucleo.ia_tarea (`<modulo>.<tarea>`) con su proveedor:
  `ollama` (local, sin costo), `api` (externa, con tope) u `ollama_y_api_respaldo`.
- La API externa (Anthropic u OpenAI, según Configuración) solo se usa si hay llave del proveedor elegido,
  tipo de cambio y tope mensual de plataforma.
- Con `busqueda_web=True` la IA busca en internet (solo OpenAI por ahora). La respuesta trae las ligas
  que citó (`citas`) y cada búsqueda se suma al costo.
- Antes de cada llamada externa se revisan los topes (plataforma y módulo por mes, usuario por día).
  Al llegar al tope se rechaza o se usa Ollama, según el presupuesto. Una llamada puede pasar el tope
  por poco, porque su costo se conoce hasta que termina.
- Al pasar el porcentaje de aviso (80 % por omisión) se avisa en la campana a quien administra la IA.
- Toda llamada (buena, con error o rechazada) queda en nucleo.ia_llamada. La puerta hace commit de ese registro.
"""
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, time as hora
from decimal import ROUND_HALF_UP, Decimal

import anthropic
import openai
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import configuracion
from ia import costos
from nucleo.modelos import IaLlamada, IaPresupuesto, IaTarea, Permiso, RolPermiso, Usuario, UsuarioRol, ahora
from nucleo.notificaciones import notificar

ADMINISTRAR_IA = "nucleo.ia.administrar"
BETA_RESPALDO = "server-side-fallback-2026-07-01"


class ErrorIA(Exception):
    """Error con mensaje para la persona usuaria."""


class TopeAlcanzado(ErrorIA):
    pass


@dataclass
class Respuesta:
    texto: str
    proveedor: str
    modelo: str
    tokens_entrada: int
    tokens_salida: int
    costo_mxn: Decimal
    duracion_ms: int
    completa: bool
    llamada_id: int
    citas: list[dict] = field(default_factory=list)  # [{"url", "titulo"}] cuando hubo búsqueda web


# ---------------------------------------------------------------- proveedores

def _llamar_ollama(modelo: str, instrucciones: str, mensaje: str, max_tokens: int,
                   imagenes: list[str] | None = None, con_think: bool = True, contexto: int | None = None) -> dict:
    cfg = configuracion()
    usuario = {"role": "user", "content": mensaje, **({"images": imagenes} if imagenes else {})}  # base64; modelo con visión
    cuerpo = json.dumps({
        # Sin razonamiento: en modelos que piensan (qwen3, gpt-oss) se comería los tokens antes de contestar
        "model": modelo, "stream": False, **({"think": False} if con_think else {}),
        "options": {"num_predict": max_tokens, **({"num_ctx": contexto} if contexto else {})},
        "messages": [{"role": "system", "content": instrucciones}, usuario],
    }).encode()
    peticion = urllib.request.Request(f"{cfg.ollama_url.rstrip('/')}/api/chat", data=cuerpo,
                                      headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=180) as r:
            datos = json.load(r)
    except urllib.error.HTTPError as e:
        try:  # Ollama dice la causa en el cuerpo («does not support images», «model not found»...)
            causa = (json.loads(e.read() or b"{}").get("error") or "").strip()[:200]
        except (ValueError, OSError, AttributeError):
            causa = ""
        if con_think and e.code == 400 and "think" in causa.lower():
            # Modelos sin razonamiento (p. ej. qwen3-vl instruct) pueden rechazar el campo «think»: se reintenta sin él
            return _llamar_ollama(modelo, instrucciones, mensaje, max_tokens, imagenes, con_think=False, contexto=contexto)
        raise ErrorIA(f"Ollama respondió con error {e.code}" + (f": {causa}" if causa else "")
                      + f". Revisa que el modelo «{modelo}» esté descargado.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErrorIA(f"No hay conexión con Ollama en {cfg.ollama_url}.") from e
    return {
        "texto": re.sub(r"<think>.*?</think>", "", datos.get("message", {}).get("content", ""), flags=re.DOTALL).strip(),
        "modelo": modelo,
        "tokens_entrada": datos.get("prompt_eval_count") or 0,
        "tokens_salida": datos.get("eval_count") or 0,
        "completa": datos.get("done_reason", "stop") != "length",
        "rechazo": False,
        "detalle": None,
    }


def _llamar_api(modelo: str, instrucciones: str, mensaje: str, max_tokens: int, esfuerzo: str,
                busqueda_web: bool = False, dominios: list[str] | None = None) -> dict:
    if configuracion().ia_proveedor_externo == "openai":
        return _llamar_openai(modelo, instrucciones, mensaje, max_tokens, esfuerzo, busqueda_web, dominios)
    if busqueda_web:
        raise ErrorIA("La búsqueda web por ahora solo funciona con OpenAI como proveedor (Administración > Configuración).")
    return _llamar_anthropic(modelo, instrucciones, mensaje, max_tokens, esfuerzo)


def _llamar_openai(modelo: str, instrucciones: str, mensaje: str, max_tokens: int, esfuerzo: str,
                   busqueda_web: bool, dominios: list[str] | None) -> dict:
    cfg = configuracion()
    cliente = openai.OpenAI(api_key=cfg.openai_api_key, timeout=300, max_retries=2)
    extra = {}
    if busqueda_web:
        herramienta = {"type": "web_search"}
        if dominios:
            herramienta["filters"] = {"allowed_domains": dominios[:100]}
        # Pide también todas las páginas consultadas, para comprobar que una liga sí salió de la búsqueda
        extra = {"tools": [herramienta], "include": ["web_search_call.action.sources"]}
    try:
        r = cliente.responses.create(
            model=modelo, instructions=instrucciones, input=mensaje, max_output_tokens=max_tokens,
            reasoning={"effort": esfuerzo}, **extra,
        )
    except openai.AuthenticationError as e:
        raise ErrorIA("La llave de OpenAI no es válida.") from e
    except openai.PermissionDeniedError as e:
        raise ErrorIA("La llave de OpenAI no tiene permiso para este modelo.") from e
    except openai.RateLimitError as e:
        raise ErrorIA("OpenAI está saturada o la cuenta se quedó sin saldo o límite. Revisa tu cuenta de OpenAI.") from e
    except openai.BadRequestError as e:
        raise ErrorIA(f"OpenAI rechazó la solicitud: {e.message}") from e
    except openai.APIStatusError as e:
        raise ErrorIA(f"OpenAI respondió con error {e.status_code}.") from e
    except openai.APIConnectionError as e:
        raise ErrorIA("No hay conexión con OpenAI.") from e

    textos, citas, rechazo, busquedas = [], [], False, 0
    for item in r.output:
        if item.type == "web_search_call":
            busquedas += 1
            accion = getattr(item, "action", None)
            for fuente in getattr(accion, "sources", None) or []:
                if getattr(fuente, "url", None):
                    citas.append({"url": fuente.url, "titulo": None})
            if getattr(accion, "url", None):  # página abierta o búsqueda dentro de una página
                citas.append({"url": accion.url, "titulo": None})
        elif item.type == "message":
            for c in item.content:
                if c.type == "refusal":
                    rechazo = True
                elif c.type == "output_text":
                    textos.append(c.text)
                    for a in c.annotations or []:
                        if a.type == "url_citation":
                            citas.append({"url": a.url, "titulo": a.title})
    u = r.usage
    incompleta = r.status == "incomplete" and getattr(r.incomplete_details, "reason", None) == "max_output_tokens"
    return {
        "texto": "" if rechazo else "".join(textos),
        "modelo": r.model,
        "tokens_entrada": (u.input_tokens if u else 0) or 0,
        "tokens_salida": (u.output_tokens if u else 0) or 0,
        "busquedas": busquedas,
        "citas": citas,
        "completa": not incompleta,
        "rechazo": rechazo,
        "detalle": f"{busquedas} búsquedas web." if busquedas else None,
    }


def _llamar_anthropic(modelo: str, instrucciones: str, mensaje: str, max_tokens: int, esfuerzo: str) -> dict:
    cfg = configuracion()
    cliente = anthropic.Anthropic(api_key=cfg.anthropic_api_key, timeout=180, max_retries=2)
    try:
        # fallbacks="default": si el modelo declina por sus filtros de seguridad, Anthropic reintenta
        # con su modelo de respaldo recomendado dentro de la misma llamada.
        r = cliente.beta.messages.create(
            model=modelo, max_tokens=max_tokens, system=instrucciones,
            messages=[{"role": "user", "content": mensaje}],
            output_config={"effort": esfuerzo},
            betas=[BETA_RESPALDO], fallbacks="default",
        )
    except anthropic.AuthenticationError as e:
        raise ErrorIA("La llave de la API externa no es válida.") from e
    except anthropic.PermissionDeniedError as e:
        raise ErrorIA("La llave de la API externa no tiene permiso para este modelo.") from e
    except anthropic.RateLimitError as e:
        raise ErrorIA("La API externa está saturada o se pasó el límite de la cuenta. Intenta en un momento.") from e
    except anthropic.BadRequestError as e:
        raise ErrorIA(f"La API externa rechazó la solicitud: {e.message}") from e
    except anthropic.APIStatusError as e:
        raise ErrorIA(f"La API externa respondió con error {e.status_code}.") from e
    except anthropic.APIConnectionError as e:
        raise ErrorIA("No hay conexión con la API externa.") from e

    u = r.usage
    rechazo = r.stop_reason == "refusal"
    detalle = None
    if r.model != modelo:
        detalle = f"Respondió {r.model} (respaldo); costo estimado con los precios de {modelo}."
    if rechazo and getattr(r, "stop_details", None):
        detalle = f"El modelo declinó ({r.stop_details.category or 'sin categoría'})."
    return {
        "texto": "" if rechazo else "".join(b.text for b in r.content if b.type == "text"),
        "modelo": r.model,
        "tokens_entrada": u.input_tokens or 0,
        "tokens_salida": u.output_tokens or 0,
        "tokens_cache_escritura": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "tokens_cache_lectura": getattr(u, "cache_read_input_tokens", 0) or 0,
        "completa": r.stop_reason != "max_tokens",
        "rechazo": rechazo,
        "detalle": detalle,
    }


# ---------------------------------------------------------------- dinero y topes

def costo_mxn(r: dict) -> Decimal:
    cfg = configuracion()
    entrada, salida = cfg.ia_precio_entrada_usd_mtok, cfg.ia_precio_salida_usd_mtok
    usd = (r["tokens_entrada"] * entrada + r["tokens_salida"] * salida
           + r.get("tokens_cache_escritura", 0) * entrada * 1.25 + r.get("tokens_cache_lectura", 0) * entrada * 0.1) / 1_000_000
    usd += r.get("busquedas", 0) * (cfg.ia_precio_busqueda_usd or 0)
    return (Decimal(str(usd)) * Decimal(str(cfg.ia_tipo_cambio_mxn or 0))).quantize(Decimal("0.0001"), ROUND_HALF_UP)


def inicio_de_mes() -> datetime:
    hoy = ahora().date()
    return datetime.combine(hoy.replace(day=1), hora.min)


def inicio_de_dia() -> datetime:
    return datetime.combine(ahora().date(), hora.min)


def gasto(bd: Session, desde: datetime, *, modulo_id: int | None = None, usuario_id: int | None = None) -> Decimal:
    q = select(func.coalesce(func.sum(IaLlamada.costo_mxn), 0)).where(
        IaLlamada.proveedor_ia == "api", IaLlamada.ocurrido_en >= desde)
    if modulo_id is not None:
        q = q.join(IaTarea, IaTarea.tarea_id == IaLlamada.tarea_id).where(IaTarea.modulo_id == modulo_id)
    if usuario_id is not None:
        q = q.where(IaLlamada.usuario_id == usuario_id)
    return Decimal(bd.scalar(q))


def presupuesto(bd: Session, alcance: str, modulo_id: int | None = None) -> IaPresupuesto | None:
    q = select(IaPresupuesto).where(IaPresupuesto.alcance == alcance, IaPresupuesto.vigente_desde <= date.today())
    q = q.where(IaPresupuesto.modulo_id == modulo_id) if modulo_id else q.where(IaPresupuesto.modulo_id.is_(None))
    return bd.scalar(q)


def motivos_api_apagada(bd: Session) -> list[str]:
    cfg = configuracion()
    motivos = []
    llave = cfg.openai_api_key if cfg.ia_proveedor_externo == "openai" else cfg.anthropic_api_key
    if not llave:
        nombre = "OpenAI" if cfg.ia_proveedor_externo == "openai" else "Anthropic"
        motivos.append(f"Falta la llave de {nombre} (Administración > Configuración).")
    if not cfg.ia_tipo_cambio_mxn:
        motivos.append("Falta el tipo de cambio (Administración > Configuración).")
    if not presupuesto(bd, "plataforma"):
        motivos.append("Falta el tope mensual de la plataforma (Administración > Inteligencia artificial, Topes de gasto).")
    return motivos


def _topes_que_aplican(bd: Session, tarea: IaTarea, usuario_id: int | None) -> list[tuple[IaPresupuesto, Decimal, str]]:
    """(presupuesto, gasto en su periodo, clave del periodo) de cada tope que aplica a esta llamada."""
    mes, dia = inicio_de_mes(), inicio_de_dia()
    salida = []
    if p := presupuesto(bd, "plataforma"):
        salida.append((p, costos.gasto_plataforma(bd, mes), f"plataforma:{mes:%Y-%m}"))
    if tarea.modulo_id and (p := presupuesto(bd, "modulo", tarea.modulo_id)):
        salida.append((p, gasto(bd, mes, modulo_id=tarea.modulo_id), f"modulo{tarea.modulo_id}:{mes:%Y-%m}"))
    if usuario_id and (p := presupuesto(bd, "usuario_dia")):
        salida.append((p, gasto(bd, dia, usuario_id=usuario_id), f"usuario{usuario_id}:{dia:%Y-%m-%d}"))
    return salida


def _nombre_tope(p: IaPresupuesto) -> str:
    if p.alcance == "plataforma":
        return "el tope mensual de la plataforma"
    if p.alcance == "modulo":
        return f"el tope mensual de {p.modulo.area if p.modulo else 'un módulo'}"
    return "el tope diario por persona"


def _administradores_ia(bd: Session) -> list[int]:
    return list(bd.scalars(
        select(Usuario.usuario_id).distinct()
        .join(UsuarioRol, UsuarioRol.usuario_id == Usuario.usuario_id)
        .join(RolPermiso, RolPermiso.rol_id == UsuarioRol.rol_id)
        .join(Permiso, Permiso.permiso_id == RolPermiso.permiso_id)
        .where(Permiso.codigo == ADMINISTRAR_IA, Usuario.estatus == "activo")
    ))


def _avisar_consumo(bd: Session, tarea: IaTarea, usuario_id: int | None) -> None:
    for p, gastado, clave in _topes_que_aplican(bd, tarea, usuario_id):
        if p.alcance == "usuario_dia" or p.tope_mxn <= 0:
            continue  # el tope por persona no avisa a los administradores
        pct = int(gastado / p.tope_mxn * 100)
        nivel = 100 if pct >= 100 else p.aviso_pct if pct >= p.aviso_pct else None
        if nivel is None:
            continue
        titulo = "Se alcanzó un tope de IA" if nivel == 100 else f"La IA va en {pct} % de su tope"
        mensaje = (f"Se lleva ${gastado:,.2f} MXN de ${p.tope_mxn:,.2f} MXN en {_nombre_tope(p)}."
                   + (" Las llamadas a la API externa se están rechazando o pasando a Ollama." if nivel == 100 else ""))
        for admin in _administradores_ia(bd):
            notificar(bd, admin, titulo, mensaje, liga="/admin/ia", clave=f"ia:{nivel}:{clave}")


# ---------------------------------------------------------------- registro y ejecución

def _registrar(bd: Session, tarea: IaTarea, usuario_id: int | None, proveedor: str, modelo: str | None,
               resultado: str, inicio: float, r: dict | None = None, costo: Decimal = Decimal(0),
               detalle: str | None = None) -> IaLlamada:
    texto = detalle or (r or {}).get("detalle")
    llamada = IaLlamada(
        tarea_id=tarea.tarea_id, usuario_id=usuario_id, proveedor_ia=proveedor, modelo=(r or {}).get("modelo", modelo),
        tokens_entrada=(r or {}).get("tokens_entrada", 0), tokens_salida=(r or {}).get("tokens_salida", 0),
        costo_mxn=costo, duracion_ms=int((time.monotonic() - inicio) * 1000), resultado=resultado,
        detalle=texto[:500] if texto else None,
    )
    bd.add(llamada)
    bd.commit()
    return llamada


def _por_ollama(bd: Session, tarea: IaTarea, usuario_id, instrucciones, mensaje, max_tokens,
                imagenes: list[str] | None = None, contexto: int | None = None) -> Respuesta:
    cfg = configuracion()
    modelo = (tarea.modelo if tarea.proveedor_ia == "ollama" else None) or cfg.ollama_modelo
    if not modelo:
        raise ErrorIA("Ollama no tiene modelo configurado (Administración > Configuración).")
    inicio = time.monotonic()
    try:
        r = _llamar_ollama(modelo, instrucciones, mensaje, max_tokens, **({"imagenes": imagenes} if imagenes else {}),
                           **({"contexto": contexto} if contexto else {}))
    except ErrorIA as e:
        _registrar(bd, tarea, usuario_id, "ollama", modelo, "error", inicio, detalle=str(e))
        raise
    llamada = _registrar(bd, tarea, usuario_id, "ollama", modelo, "ok", inicio, r)
    return Respuesta(r["texto"], "ollama", r["modelo"], r["tokens_entrada"], r["tokens_salida"], Decimal(0),
                     llamada.duracion_ms, r["completa"], llamada.llamada_id)


def _por_api(bd: Session, tarea: IaTarea, usuario_id, instrucciones, mensaje, max_tokens, esfuerzo,
             busqueda_web: bool = False, dominios: list[str] | None = None) -> Respuesta:
    cfg = configuracion()
    modelo = (tarea.modelo if tarea.proveedor_ia != "ollama" else None) or cfg.ia_modelo_externo
    if motivos := motivos_api_apagada(bd):
        raise ErrorIA("La API externa está apagada. " + " ".join(motivos))

    inicio = time.monotonic()
    for p, gastado, _ in _topes_que_aplican(bd, tarea, usuario_id):
        if gastado >= p.tope_mxn:
            aviso = f"Se alcanzó {_nombre_tope(p)} (${p.tope_mxn:,.2f} MXN)."
            _registrar(bd, tarea, usuario_id, "api", modelo, "rechazada_por_tope", inicio, detalle=aviso)
            _avisar_consumo(bd, tarea, usuario_id)
            bd.commit()
            if p.al_superar == "usar_ollama" and cfg.ollama_modelo and not busqueda_web:
                return _por_ollama(bd, tarea, usuario_id, instrucciones, mensaje, max_tokens)
            raise TopeAlcanzado(aviso + " Pide a quien administra la IA que lo revise.")

    try:
        r = _llamar_api(modelo, instrucciones, mensaje, max_tokens, esfuerzo, busqueda_web, dominios)
    except ErrorIA as e:
        _registrar(bd, tarea, usuario_id, "api", modelo, "error", inicio, detalle=str(e))
        raise
    costo = costo_mxn(r)
    llamada = _registrar(bd, tarea, usuario_id, "api", modelo, "rechazada_por_modelo" if r["rechazo"] else "ok",
                         inicio, r, costo)
    _avisar_consumo(bd, tarea, usuario_id)
    bd.commit()
    if r["rechazo"]:
        raise ErrorIA("El modelo no quiso responder esta solicitud. Revisa el texto e intenta de otra forma.")
    return Respuesta(r["texto"], "api", r["modelo"], r["tokens_entrada"], r["tokens_salida"], costo,
                     llamada.duracion_ms, r["completa"], llamada.llamada_id, r.get("citas", []))


def ejecutar(bd: Session, tarea_codigo: str, *, usuario_id: int | None, instrucciones: str, mensaje: str,
             max_tokens: int = 1024, esfuerzo: str = "medium", proveedor: str | None = None,
             busqueda_web: bool = False, dominios: list[str] | None = None,
             imagenes: list[str] | None = None, contexto: int | None = None) -> Respuesta:
    """Corre una tarea de IA. `proveedor` solo lo usa la pantalla de prueba para forzar uno.
    `contexto` (tokens) agranda la ventana de Ollama para textos largos; sin él, Ollama usa la suya (2,048 a 4,096).
    Con `busqueda_web` siempre va a la API externa (Ollama no busca en internet).
    Con `imagenes` (base64) solo va a Ollama, con el modelo de la tarea, que debe tener visión."""
    tarea = bd.scalar(select(IaTarea).where(IaTarea.codigo == tarea_codigo))
    if not tarea or not tarea.activa:
        raise ErrorIA(f"La tarea de IA «{tarea_codigo}» no existe o está apagada.")
    plan = proveedor or tarea.proveedor_ia
    if imagenes:
        if plan == "api":
            raise ErrorIA("Comparar imágenes por ahora solo funciona con Ollama.")
        return _por_ollama(bd, tarea, usuario_id, instrucciones, mensaje, max_tokens, imagenes)
    if busqueda_web:
        return _por_api(bd, tarea, usuario_id, instrucciones, mensaje, max_tokens, esfuerzo, True, dominios)
    if plan == "ollama":
        return _por_ollama(bd, tarea, usuario_id, instrucciones, mensaje, max_tokens, contexto=contexto)
    if plan == "api":
        return _por_api(bd, tarea, usuario_id, instrucciones, mensaje, max_tokens, esfuerzo)
    try:  # ollama_y_api_respaldo
        return _por_ollama(bd, tarea, usuario_id, instrucciones, mensaje, max_tokens, contexto=contexto)
    except ErrorIA:
        return _por_api(bd, tarea, usuario_id, instrucciones, mensaje, max_tokens, esfuerzo)


def vectores(bd: Session, tarea_codigo: str, textos: list[str], *, usuario_id: int | None = None) -> tuple[str, list[list[float]]]:
    """Huella de significado (embedding) de cada texto, con Ollama local (`/api/embed`). Devuelve (modelo, vectores).
    Solo Ollama: las tareas de huella nunca van a la API externa. Una llamada registrada por tanda."""
    tarea = bd.scalar(select(IaTarea).where(IaTarea.codigo == tarea_codigo))
    if not tarea or not tarea.activa:
        raise ErrorIA(f"La tarea de IA «{tarea_codigo}» no existe o está apagada.")
    modelo = tarea.modelo
    if not modelo:
        raise ErrorIA(f"La tarea «{tarea_codigo}» no tiene modelo de huella (Administración > Inteligencia artificial).")
    cfg = configuracion()
    inicio = time.monotonic()
    peticion = urllib.request.Request(f"{cfg.ollama_url.rstrip('/')}/api/embed",
                                      data=json.dumps({"model": modelo, "input": textos}).encode(),
                                      headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=300) as r:
            datos = json.load(r)
    except urllib.error.HTTPError as e:
        aviso = f"Ollama respondió con error {e.code}. Revisa que el modelo «{modelo}» esté descargado."
        _registrar(bd, tarea, usuario_id, "ollama", modelo, "error", inicio, detalle=aviso)
        raise ErrorIA(aviso) from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        aviso = f"No hay conexión con Ollama en {cfg.ollama_url}."
        _registrar(bd, tarea, usuario_id, "ollama", modelo, "error", inicio, detalle=aviso)
        raise ErrorIA(aviso) from e
    salida = datos.get("embeddings") or []
    if len(salida) != len(textos):
        aviso = "Ollama no regresó una huella por cada texto."
        _registrar(bd, tarea, usuario_id, "ollama", modelo, "error", inicio, detalle=aviso)
        raise ErrorIA(aviso)
    _registrar(bd, tarea, usuario_id, "ollama", modelo, "ok", inicio,
               {"modelo": modelo, "tokens_entrada": datos.get("prompt_eval_count") or 0, "tokens_salida": 0,
                "detalle": f"{len(textos)} huellas."})
    return modelo, salida


def estado_ollama() -> dict:
    cfg = configuracion()
    try:
        with urllib.request.urlopen(f"{cfg.ollama_url.rstrip('/')}/api/tags", timeout=2) as r:
            modelos = [m.get("name") for m in json.load(r).get("models", [])]
        return {"disponible": True, "modelos": modelos}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return {"disponible": False, "modelos": []}
