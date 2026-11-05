"""Días hábiles para tiempos de entrega de proveedores."""
from datetime import date

from nucleo.calendario import dias_habiles, festivos


def test_dias_habiles_sin_fines_de_semana_ni_festivos():
    assert dias_habiles(date(2026, 10, 30), date(2026, 11, 3)) == 2  # viernes → martes
    assert dias_habiles(date(2026, 11, 3), date(2026, 11, 3)) == 0
    assert dias_habiles(date(2026, 11, 2), date(2026, 11, 30)) == 19  # 20 hábiles menos el 16 de noviembre (tercer lunes)
    assert dias_habiles(date(2026, 12, 24), date(2027, 1, 4)) == 5  # sin el 25 de diciembre ni el 1 de enero
    assert dias_habiles(date(2026, 1, 1), date(2026, 12, 31)) == 261 - 7  # 7 festivos en día hábil en 2026


def test_festivos_de_la_ley_federal_del_trabajo():
    assert festivos(2026) == {date(2026, 1, 1), date(2026, 2, 2), date(2026, 3, 16), date(2026, 5, 1), date(2026, 9, 16),
                              date(2026, 11, 16), date(2026, 12, 25)}
    assert date(2030, 10, 1) in festivos(2030) and date(2024, 10, 1) in festivos(2024)
