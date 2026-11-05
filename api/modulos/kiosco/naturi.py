"""Conversaciones con Naturi (ElevenLabs), tomado de la vista Naturi-react del proyecto SMN_Direccion.

La llave de ElevenLabs solo vive en el servidor (Configuración, cifrada). El navegador recibe una liga firmada de
un solo uso para conectarse; nunca la llave. Si ElevenLabs no responde, falla cerrado: no se conversa sin términos.
"""
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import HTTPException

from core.config import configuracion

API = "https://api.elevenlabs.io/v1/convai"
HOST_WSS = "api.elevenlabs.io"

_config_lock = threading.Lock()
_config: dict | None = None
_config_hasta = 0.0
_config_de = ""  # agente y llave con que se armó la configuración guardada
_limite_lock = threading.Lock()
_inicios: deque[tuple[float, int]] = deque()


class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # nunca se sigue una redirección con la llave
        return None


_abridor = urllib.request.build_opener(_SinRedireccion)


class _TextoPlano(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes: list[str] = []

    def handle_data(self, data):
        self.partes.append(data)


def disponible() -> bool:
    cfg = configuracion()
    return bool(cfg.elevenlabs_api_key and cfg.kiosco_agente_id)


def _get(ruta: str, params: dict | None = None) -> dict:
    cfg = configuracion()
    url = f"{API}{ruta}" + (f"?{urlencode(params)}" if params else "")
    peticion = urllib.request.Request(url, headers={"xi-api-key": cfg.elevenlabs_api_key, "Accept": "application/json"})
    with _abridor.open(peticion, timeout=8) as r:
        if r.status != 200:
            raise ValueError("Respuesta inesperada")
        return json.load(r)


def olvidar_configuracion() -> None:
    global _config, _config_hasta
    with _config_lock:
        _config, _config_hasta = None, 0.0


def configuracion_agente() -> dict:
    """Términos y capacidades del agente, guardados 5 minutos. Sin respuesta de ElevenLabs no se conversa."""
    global _config, _config_hasta, _config_de
    cfg = configuracion()
    huella = hashlib.sha256(f"{cfg.kiosco_agente_id}:{cfg.elevenlabs_api_key}".encode()).hexdigest()
    with _config_lock:
        if _config is not None and time.monotonic() < _config_hasta and _config_de == huella:
            return _config
        try:
            agente = cfg.kiosco_agente_id
            widget = _get(f"/agents/{agente}/widget")["widget_config"]
            texto = bool(widget.get("supports_text_only") or widget.get("text_only"))
            if not texto:  # el chat del SDK puede estar permitido aunque el del widget esté apagado
                try:
                    datos = _get(f"/agents/{agente}")
                    conversacion = (datos.get("conversation_config") or {}).get("conversation") or {}
                    cambios = (((datos.get("platform_settings") or {}).get("overrides") or {})
                               .get("conversation_config_override") or {})
                    texto = bool(conversacion.get("text_only") or (cambios.get("conversation") or {}).get("text_only"))
                    texto = texto and "agent_response" in conversacion.get("client_events", [])
                except Exception:
                    texto = False  # sin permiso de lectura del agente, la voz sigue funcionando
            terminos = widget.get("terms_text") or ""
            if not terminos and widget.get("terms_html"):
                lector = _TextoPlano()
                lector.feed(widget["terms_html"])
                terminos = "\n".join(lector.partes)
            if not isinstance(terminos, str) or len(terminos) > 30000:
                raise ValueError("Términos inválidos")
            _config = {"terminos": terminos, "version_terminos": hashlib.sha256(terminos.encode()).hexdigest(),
                       "texto": texto, "fotos": bool((widget.get("file_input_config") or {}).get("enabled"))}
            _config_hasta, _config_de = time.monotonic() + 300, huella
            return _config
        except Exception:
            raise HTTPException(503, "No se pudo preparar la conversación. Intenta más tarde.") from None


def admitir(usuario_id: int) -> None:
    """Límite de conversaciones por persona y en total, por hora (en memoria de este proceso)."""
    cfg = configuracion()
    with _limite_lock:
        corte = time.monotonic() - 3600
        while _inicios and _inicios[0][0] < corte:
            _inicios.popleft()
        if (len(_inicios) >= cfg.kiosco_limite_hora
                or sum(u == usuario_id for _, u in _inicios) >= cfg.kiosco_limite_usuario_hora):
            raise HTTPException(429, "Se llegó al límite de conversaciones. Intenta más tarde.",
                                headers={"Retry-After": "3600"})
        _inicios.append((time.monotonic(), usuario_id))


def liga_firmada() -> str:
    """Pide a ElevenLabs una liga de un solo uso y revisa que apunte a su servidor y a nuestro agente."""
    agente = configuracion().kiosco_agente_id
    try:
        firmada = _get("/conversation/get-signed-url", {"agent_id": agente, "include_conversation_id": "true"})["signed_url"]
        p = urlsplit(firmada)
        q = parse_qs(p.query)
        if (p.scheme != "wss" or p.hostname != HOST_WSS or p.port not in (None, 443) or p.username or p.password
                or p.fragment or p.path != "/v1/convai/conversation" or q.get("agent_id") != [agente]
                or not q.get("conversation_signature")):
            raise ValueError("Destino inválido")
        return firmada
    except Exception:
        # Nunca se regresa ni se registra lo que contestó ElevenLabs, la llave o la liga firmada.
        raise HTTPException(503, "No se pudo iniciar la conversación. Intenta de nuevo.") from None
