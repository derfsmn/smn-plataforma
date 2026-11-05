"""Herramienta `buscar_productos_smn` de Naturi: busca en el catálogo de productos del Centro de datos.

Mismas reglas que la herramienta del proyecto SMN_Direccion (que leía el mismo API de artículos): solo datos
públicos del producto, SKU como texto, precios del catálogo sin impuestos y sin existencias.
"""
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from datos.modelos import Producto

CAMPOS = ("sku", "nombre", "marca", "departamento", "rama", "subcategoria", "segmento")
PRESENTACIONES = {
    "capsulas": r"(?<![a-z])(?:capsulas?|caps|cap)(?![a-z])",
    "tabletas": r"(?<![a-z])(?:tabletas?|tablets?|tabs?|comprimidos?)(?![a-z])",
    "polvo": r"\bpolvo\b",
    "gomitas": r"\b(?:gomitas?|gummies)\b",
    "liquido": r"\b(?:liquid[oa]s?|jarabes?|tinturas?|gotas?|aceites?)\b",
}
VIGENCIA_S = 300

_lock = threading.Lock()
_foto: dict | None = None
_foto_hasta = 0.0


def normalizar(valor: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", valor.casefold()) if not unicodedata.combining(c))


def clave_marca(valor: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", normalizar(valor)))


def es_vidanat(valor: str) -> bool:
    return clave_marca(valor).split(" ", 1)[0] == "vidanat"


def es_presentacion(nombre: str, forma: str) -> bool:
    texto = normalizar(nombre)
    if forma == "liquido" and any(re.search(PRESENTACIONES[k], texto) for k in ("capsulas", "tabletas", "gomitas")):
        return False
    return bool(re.search(PRESENTACIONES[forma], texto))


def importe(valor) -> str | None:
    """Importe positivo como texto con dos decimales; None si no es válido."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        d = Decimal(str(valor).strip())
    except Exception:
        return None
    if not d.is_finite() or d <= 0 or d > 1_000_000_000:
        return None
    return str(d.quantize(Decimal("0.01")))


def olvidar() -> None:
    global _foto, _foto_hasta
    with _lock:
        _foto, _foto_hasta = None, 0.0


def _catalogo(bd: Session) -> dict:
    """Productos activos del catálogo, guardados 5 minutos en memoria."""
    global _foto, _foto_hasta
    with _lock:
        if _foto is not None and time.monotonic() < _foto_hasta:
            return _foto
        filas = []
        for p in bd.scalars(select(Producto).where(Producto.activo == true())):
            if not p.sku or not (p.descripcion or "").strip():
                continue
            filas.append({"sku": p.sku, "nombre": p.descripcion.strip(), "marca": p.marca or "",
                          "departamento": p.departamento or "", "rama": p.rama or "",
                          "subcategoria": p.subcategoria or "", "segmento": p.segmento or "",
                          "precio_lista": importe(p.precio_lista), "precio_membresia": importe(p.precio_membresia)})
        _foto = {"actualizado_en": datetime.now(timezone.utc).isoformat(), "resultados": filas}
        _foto_hasta = time.monotonic() + VIGENCIA_S
        return _foto


def buscar(bd: Session, consulta: str, limite: int, *, desplazamiento: int = 0, excluir: tuple[str, ...] = (),
           presentacion: str | None = None, marca: str | None = None, maximo: Decimal | None = None,
           menor_que: Decimal | None = None, tipo_precio: str = "lista", orden: str = "relevancia") -> dict:
    foto = _catalogo(bd)
    filas = foto["resultados"]
    consulta_n = normalizar(consulta)
    terminos = consulta_n.split()
    marcas_consulta = " " + clave_marca(consulta) + " "
    pedidas = {m for m in {clave_marca(r["marca"]) for r in filas}
               if len(m) >= 2 and m.split(" ", 1)[0] != "vidanat" and " " + m + " " in marcas_consulta}
    campo_precio = "precio_" + ("lista" if tipo_precio == "lista" else "membresia")
    hallados = []
    for r in filas:
        if r["sku"] in excluir:
            continue
        if presentacion and not es_presentacion(r["nombre"], presentacion):
            continue
        if marca and not (clave_marca(r["marca"]) == clave_marca(marca)
                          or clave_marca(r["marca"]).startswith(clave_marca(marca) + " ")):
            continue
        if maximo is not None or menor_que is not None or orden == "precio_asc":
            if r[campo_precio] is None:
                continue
            valor = Decimal(r[campo_precio])
            if (maximo is not None and valor > maximo) or (menor_que is not None and valor >= menor_que):
                continue
        valores = {k: normalizar(r[k]) for k in CAMPOS}
        exacto = valores["sku"] == consulta_n
        texto = " ".join(valores.values())
        if not exacto and not all(t in texto for t in terminos):
            continue
        puntos = 10000 if exacto else sum(30 if t in valores["nombre"] else 20 if t in valores["marca"] else 1
                                          for t in terminos)
        hallados.append((puntos, r))
    hay_sku = any(normalizar(r["sku"]) == consulta_n for _, r in hallados)

    def rango(item):
        puntos, r = item
        return (-int(normalizar(r["sku"]) == consulta_n),
                -int(not hay_sku and clave_marca(r["marca"]) in pedidas),
                -int(not hay_sku and not pedidas and es_vidanat(r["marca"])),  # prioridad Vidanat, como el original
                -puntos, r["nombre"], r["sku"])

    if orden == "precio_asc":
        hallados.sort(key=lambda i: (Decimal(i[1][campo_precio]), rango(i)))
    else:
        hallados.sort(key=rango)
    siguiente = desplazamiento + min(limite, max(0, len(hallados) - desplazamiento))
    return {"consulta": consulta, "total_coincidencias": len(hallados), "catalogo_actualizado_en": foto["actualizado_en"],
            "resultados": [r for _, r in hallados[desplazamiento:desplazamiento + limite]],
            "disponibilidad_sucursal": None, "precios_habilitados": True, "moneda": "MXN", "impuestos_incluidos": False,
            "desplazamiento": desplazamiento, "hay_mas": siguiente < len(hallados),
            "siguiente_desplazamiento": siguiente if siguiente < len(hallados) else None,
            "filtros": {"marca": marca, "presentacion": presentacion, "tipo_precio": tipo_precio, "orden": orden,
                        "precio_maximo": str(maximo) if maximo is not None else None,
                        "precio_menor_que": str(menor_que) if menor_que is not None else None,
                        "excluir_skus": list(excluir)}}
