"""Gráfica en vivo del Monitor (Diego, 26 nov 2026: «que se vea el movimiento con una gráfica que se está moviendo»).

Cada 2 segundos toma una muestra y guarda las últimas 150 (5 minutos) en memoria:
- procesador: uso real del servidor, de la diferencia entre dos lecturas de /proc/stat;
- ia: con nvidia-smi, el uso de la tarjeta de video; sin él (el contenedor de la API no ve la tarjeta), qué parte de
  esos 2 segundos hubo al menos una llamada a Ollama en curso;
- busquedas: búsquedas afuera (tareas de DataForSEO, páginas de tiendas y Mercado Libre) en el último minuto.

No usa la base ni importa nada de la plataforma, para que cualquier módulo pueda avisar sin ciclos de importación.
"""
import shutil
import subprocess
import threading
import time
from collections import deque
from contextlib import contextmanager

CADA = 2.0
PUNTOS = 150

_candado = threading.Lock()
_muestras: deque[dict] = deque(maxlen=PUNTOS)
_busquedas: deque[tuple[float, int]] = deque()  # (momento, cuántas)
_ia_en_curso = 0
_ia_desde: float | None = None  # desde cuándo hay alguna llamada en curso
_ia_acumulado = 0.0  # segundos ocupados dentro de la muestra actual
_hilo: threading.Thread | None = None
_cpu_antes: tuple[int, int] | None = None


def contar(cuantas: int = 1) -> None:
    """Una o más búsquedas afuera que acaban de salir."""
    if cuantas > 0:
        with _candado:
            _busquedas.append((time.monotonic(), cuantas))


@contextmanager
def ia_ocupada():
    """Envuelve una llamada a Ollama para saber cuánto tiempo estuvo trabajando la IA local."""
    global _ia_en_curso, _ia_desde, _ia_acumulado
    with _candado:
        if _ia_en_curso == 0:
            _ia_desde = time.monotonic()
        _ia_en_curso += 1
    try:
        yield
    finally:
        with _candado:
            _ia_en_curso -= 1
            if _ia_en_curso == 0 and _ia_desde is not None:
                _ia_acumulado += time.monotonic() - _ia_desde
                _ia_desde = None


def _leer_cpu() -> tuple[int, int] | None:
    try:
        with open("/proc/stat") as f:
            campos = [int(x) for x in f.readline().split()[1:]]
        ocioso = campos[3] + (campos[4] if len(campos) > 4 else 0)
        return sum(campos), ocioso
    except (OSError, ValueError, IndexError):
        return None


def _cpu_pct() -> float | None:
    global _cpu_antes
    ahora = _leer_cpu()
    antes, _cpu_antes = _cpu_antes, ahora
    if not ahora or not antes or ahora[0] <= antes[0]:
        return None
    total, ocioso = ahora[0] - antes[0], ahora[1] - antes[1]
    return round(100 * (total - ocioso) / total, 1)


def _gpu_pct() -> float | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=2)
        usos = [int(x) for x in r.stdout.split()]
        return float(max(usos)) if usos else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def muestra(ahora: float | None = None, gpu: float | None = None) -> dict:
    """Toma una muestra y la guarda. `ahora` y `gpu` solo se pasan en las pruebas."""
    global _ia_desde, _ia_acumulado
    t = time.monotonic() if ahora is None else ahora
    with _candado:
        ocupado = _ia_acumulado
        if _ia_desde is not None:  # sigue trabajando: cuenta hasta ahora y vuelve a empezar desde aquí
            ocupado += max(0.0, t - _ia_desde)
            _ia_desde = t
        _ia_acumulado = 0.0
        while _busquedas and _busquedas[0][0] < t - 60:
            _busquedas.popleft()
        por_minuto = sum(n for _, n in _busquedas)
    ia = gpu if gpu is not None else _gpu_pct()
    fuente = "tarjeta" if ia is not None else "llamadas"
    if ia is None:
        ia = round(min(100.0, 100 * ocupado / CADA), 1)
    m = {"t": round(time.time(), 1), "cpu": _cpu_pct(), "ia": ia, "ia_fuente": fuente, "busquedas": por_minuto}
    with _candado:
        _muestras.append(m)
    return m


def serie() -> list[dict]:
    with _candado:
        return list(_muestras)


def _bucle() -> None:
    while True:
        try:
            muestra()
        except Exception:  # noqa: BLE001 - la gráfica nunca tira la API
            pass
        time.sleep(CADA)


def iniciar() -> None:
    """Se llama al arrancar la API; un solo hilo aunque se llame dos veces."""
    global _hilo
    if _hilo and _hilo.is_alive():
        return
    _hilo = threading.Thread(target=_bucle, daemon=True, name="monitor-muestras")
    _hilo.start()
