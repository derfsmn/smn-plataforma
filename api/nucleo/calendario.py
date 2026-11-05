"""Días hábiles para medir tiempos de entrega (Diego, 2026-11-04: los días que promete el proveedor son hábiles, de
lunes a viernes).

Se quitan sábados, domingos y los días de descanso obligatorio del artículo 74 de la Ley Federal del Trabajo. No se
quitan los días de jornada electoral (dependen de cada estado) ni Jueves y Viernes Santo (no son de descanso
obligatorio por ley).
"""
from datetime import date, datetime, timedelta
from functools import lru_cache


def _lunes(anio: int, mes: int, n: int) -> date:
    """El n-ésimo lunes del mes."""
    d = date(anio, mes, 1)
    return d + timedelta(days=(7 - d.weekday()) % 7 + 7 * (n - 1))


@lru_cache(maxsize=64)
def festivos(anio: int) -> frozenset[date]:
    dias = {
        date(anio, 1, 1),
        _lunes(anio, 2, 1),  # 5 de febrero, Constitución
        _lunes(anio, 3, 3),  # 21 de marzo, Benito Juárez
        date(anio, 5, 1),
        date(anio, 9, 16),
        _lunes(anio, 11, 3),  # 20 de noviembre, Revolución
        date(anio, 12, 25),
    }
    if anio >= 2024 and (anio - 2024) % 6 == 0:  # transmisión del Poder Ejecutivo Federal (desde 2024, el 1 de octubre)
        dias.add(date(anio, 10, 1))
    if anio < 2024 and (anio - 2018) % 6 == 0:  # antes de 2024 era el 1 de diciembre
        dias.add(date(anio, 12, 1))
    return frozenset(dias)


def es_habil(d: date) -> bool:
    return d.weekday() < 5 and d not in festivos(d.year)


def dias_habiles(desde: date | datetime, hasta: date | datetime) -> int:
    """Días hábiles después de `desde` y hasta `hasta` (incluido). Pedido el viernes y entregado el martes = 2."""
    a = desde.date() if isinstance(desde, datetime) else desde
    b = hasta.date() if isinstance(hasta, datetime) else hasta
    if b <= a:
        return 0
    semanas, resto = divmod((b - a).days, 7)
    total = semanas * 5 + sum(1 for k in range(1, resto + 1) if (a + timedelta(days=k)).weekday() < 5)
    total -= sum(1 for y in range(a.year, b.year + 1) for f in festivos(y) if a < f <= b and f.weekday() < 5)
    return total
