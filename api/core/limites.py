"""Límites de intentos en memoria (por IP o por correo), para frenar a quien prueba contraseñas o inunda de correos.

Revisión de seguridad 2026-11-22, hallazgo M3. Viven en la memoria de la API: con un solo proceso (como en el servidor)
basta; al reiniciar la API se vacían, lo cual está bien para límites de minutos.
"""
import threading
import time
from collections import deque

_lock = threading.Lock()
_registro: dict[tuple[str, str], deque] = {}
_MAX_LLAVES = 50_000  # tope de memoria: si alguien manda muchísimas IP o correos distintos, se limpia lo viejo


def _vigentes(llave: tuple[str, str], segundos: int, ahora: float) -> deque:
    marcas = _registro.setdefault(llave, deque())
    while marcas and marcas[0] <= ahora - segundos:
        marcas.popleft()
    return marcas


def excedido(tipo: str, quien: str | None, maximo: int, segundos: int) -> bool:
    """¿Ya hubo `maximo` registros de `tipo` para `quien` en los últimos `segundos`? No registra nada."""
    if not quien:
        return False
    with _lock:
        return len(_vigentes((tipo, quien), segundos, time.monotonic())) >= maximo


def anotar(tipo: str, quien: str | None, segundos: int) -> None:
    if not quien:
        return
    ahora = time.monotonic()
    with _lock:
        if len(_registro) > _MAX_LLAVES:
            for k in [k for k, v in _registro.items() if not v or v[-1] <= ahora - 3600]:
                del _registro[k]
        _vigentes((tipo, quien), segundos, ahora).append(ahora)


def olvidar(tipo: str, quien: str | None) -> None:
    with _lock:
        _registro.pop((tipo, quien or ""), None)


def reiniciar() -> None:
    """Para las pruebas."""
    with _lock:
        _registro.clear()
