"""Números capturados a mano o pegados de Excel, con las mismas reglas que web/lib/numeros.ts (revisión de formularios,
26 nov 2026). Estilo México: punto decimal y coma de miles, sin cambiar en silencio lo que se quiso decir:
«1,234.50» → 1234.50, «1234,50» → 1234.50, «1.234,50» → 1234.50, «$459» → 459, «459.» → 459, «.5» → 0.5."""
import re
from decimal import Decimal

_MILES = re.compile(r"^\d{1,3}([,.]\d{3})+$")
NO_SE_ENTIENDE = "No se entiende el número; escríbelo como 1,234.50."


def leer_numero(valor) -> Decimal | None:
    """Regresa el número o None si viene vacío; lanza ValueError con el motivo en palabras de negocio."""
    if valor is None or isinstance(valor, (int, float, Decimal)):
        return None if valor is None else Decimal(str(valor))
    t = re.sub(r"[\s $%]|MXN", "", str(valor), flags=re.IGNORECASE)
    if not t:
        return None
    if re.search(r"e[+-]?\d", t, re.IGNORECASE):
        raise ValueError("Se pegó como número de Excel (con «E+»); escríbelo completo.")
    if re.search(r"[^\d.,]", t):
        raise ValueError("Escribe solo números, por ejemplo 1,234.50.")
    comas, puntos = t.count(","), t.count(".")
    if comas and puntos:
        decimal = "." if t.rfind(".") > t.rfind(",") else ","
        miles = "," if decimal == "." else "."
        partes = t.split(decimal)
        entero = partes[0]
        if len(partes) != 2 or (miles in entero and not _MILES.match(entero.replace(miles, ","))):
            raise ValueError(NO_SE_ENTIENDE)
        t = entero.replace(miles, "") + "." + partes[1]
    elif comas:
        if _MILES.match(t):
            t = t.replace(",", "")
        elif comas == 1:
            t = t.replace(",", ".")
        else:
            raise ValueError(NO_SE_ENTIENDE)
    elif puntos > 1:
        if _MILES.match(t):
            t = t.replace(".", "")
        else:
            raise ValueError(NO_SE_ENTIENDE)
    if t.startswith("."):
        t = "0" + t
    t = t.rstrip(".") if t.endswith(".") else t
    if not re.fullmatch(r"\d+(\.\d+)?", t):
        raise ValueError("Escribe solo números, por ejemplo 1,234.50.")
    return Decimal(t)
