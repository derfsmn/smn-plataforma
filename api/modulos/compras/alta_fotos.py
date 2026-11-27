"""Alta con fotos (Diego, 26 nov 2026: «que solo suba las fotos de un producto y de ahí desmenucemos todo en la ficha»).

La IA local (la misma de la ficha técnica, modelo con visión) lee la etiqueta y propone los datos del alta rápida. Solo
prellena: la persona revisa y guarda. Cada dato debe venir con la cita exacta de lo que se leyó en la foto; si no, se deja
vacío. El código de barras además tiene que pasar su dígito verificador. Detrás del ajuste «Alta con fotos» (apagado).
"""
import base64
import json
import logging
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from datos import fichas as fi
from ia import puerta

log = logging.getLogger("smn.compras.alta_fotos")
TAREA = fi.TAREA  # «Ficha técnica estándar», solo IA local
MAX_FOTOS = 4

INSTRUCCIONES = """Eres capturista de productos de una cadena de tiendas naturistas en México. Te doy la foto de la
etiqueta de un producto (frente, tabla nutrimental o código de barras). Primero copia en "etiqueta" todo el texto que se
lee en la foto, tal cual. Después llena SOLO con lo que copiaste; cada campo con "cita" = el pedazo exacto de lo que
copiaste que lo prueba. Si la foto no lo dice, no pongas el campo. No adivines ni completes con lo que sabes.
Campos:
- marca: la marca del producto como aparece en el empaque (no el fabricante ni el distribuidor).
- nombre: qué es el producto como lo dice el frente, sin la marca y sin el contenido (ej. "Citrato de magnesio en polvo").
- forma: una de: Cápsula, Tableta, Capleta, Líquido, Polvo, Gomita, Pieza, Sobres.
- contenido_cantidad y contenido_unidad: contenido neto del envase; unidad g, ml, kg, l, cápsulas, tabletas, gomitas,
  sobres o piezas.
- ingrediente: el ingrediente activo principal (ej. "Magnesio", "Colágeno hidrolizado").
- porciones: porciones por envase.
- codigo_barras: los números impresos bajo el código de barras, sin espacios.
Contesta SOLO un JSON así: {"etiqueta": "texto leído", "marca": {"valor": "...", "cita": "..."}, "nombre": {...},
"forma": {...}, "contenido_cantidad": {"valor": 300, "cita": "..."}, "contenido_unidad": {...}, "ingrediente": {...},
"porciones": {...}, "codigo_barras": {...}}"""

FORMAS = ("Cápsula", "Tableta", "Capleta", "Líquido", "Polvo", "Gomita", "Pieza", "Sobres")
_FORMA_DE = {"capsula": "Cápsula", "capsulas": "Cápsula", "softgel": "Cápsula", "softgels": "Cápsula", "perla": "Cápsula",
             "tableta": "Tableta", "tabletas": "Tableta", "comprimido": "Tableta", "capleta": "Capleta",
             "capletas": "Capleta", "liquido": "Líquido", "jarabe": "Líquido", "gotas": "Líquido", "polvo": "Polvo",
             "gomita": "Gomita", "gomitas": "Gomita", "pieza": "Pieza", "piezas": "Pieza", "sobre": "Sobres",
             "sobres": "Sobres"}
_UNIDAD = {"g": "g", "gr": "g", "gramos": "g", "kg": "kg", "ml": "ml", "l": "l", "lt": "l", "litro": "l",
           "capsulas": "cápsulas", "capsula": "cápsulas", "caps": "cápsulas", "softgels": "cápsulas",
           "tabletas": "tabletas", "tableta": "tabletas", "tabs": "tabletas", "gomitas": "gomitas",
           "sobres": "sobres", "piezas": "piezas", "pz": "piezas"}
CAMPOS = ("nombre", "marca", "forma", "contenido", "ingrediente", "porciones", "codigo_barras")


@dataclass
class Lectura:
    campos: dict[str, str] = field(default_factory=dict)  # lo que se pudo leer, listo para el formulario
    citas: dict[str, str] = field(default_factory=dict)
    segundos: float = 0.0
    fotos: int = 0
    nota: str | None = None  # por qué no se leyó algo, en palabras de negocio


def _norm(t) -> str:
    return re.sub(r"[^a-z0-9ñ.,%/]+", " ", fi._norm(str(t or ""))).strip()


def gtin_valido(codigo: str) -> bool:
    """Dígito verificador de un código de barras GTIN (EAN-8, UPC-A, EAN-13, GTIN-14)."""
    if not re.fullmatch(r"\d{8}|\d{12,14}", codigo or ""):
        return False
    digitos = [int(d) for d in codigo]
    cuerpo, verificador = digitos[:-1], digitos[-1]
    suma = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(cuerpo)))
    return (10 - suma % 10) % 10 == verificador


def de_respuesta(datos: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Del JSON de la IA, solo lo que trae su cita dentro de lo que copió de la etiqueta."""
    etiqueta = _norm(datos.get("etiqueta"))
    campos, citas = {}, {}

    def dato(clave):
        x = datos.get(clave)
        if not isinstance(x, dict):
            return None, None
        valor, cita = x.get("valor"), str(x.get("cita") or "").strip()
        if valor in (None, "") or len(cita) < 2 or _norm(cita) not in etiqueta:
            return None, None
        return valor, cita

    for clave in ("marca", "nombre", "ingrediente"):
        valor, cita = dato(clave)
        if valor is not None:
            campos[clave], citas[clave] = re.sub(r"\s+", " ", str(valor)).strip()[:200], cita[:200]
    valor, cita = dato("forma")
    if valor is not None and (f := _FORMA_DE.get(fi._norm(str(valor)).strip().split(" ")[0])):
        campos["forma"], citas["forma"] = f, cita[:200]
    cantidad, cita_c = dato("contenido_cantidad")
    unidad, _ = dato("contenido_unidad")
    n = fi._numero(cantidad)
    u = _UNIDAD.get(fi._norm(str(unidad or "")).strip())
    if n is not None and u and fi._en_cita(n, cita_c or ""):
        if u in ("kg", "l") and n >= 50:  # la IA a veces da 1000 con «kg» por «1 kg» (NÜD 1 kg, 26 nov 2026)
            n = n / 1000
        campos["contenido"] = f"{n.normalize():f} {u}"
        citas["contenido"] = cita_c[:200]
    valor, cita = dato("porciones")
    p = fi._numero(valor)
    if p is not None and p == p.to_integral_value() and p <= 10000 and fi._en_cita(p, cita or ""):
        campos["porciones"], citas["porciones"] = str(int(p)), cita[:200]
    valor, cita = dato("codigo_barras")
    codigo = re.sub(r"\D", "", str(valor or ""))
    if codigo and gtin_valido(codigo) and codigo in re.sub(r"\D", "", cita or ""):
        campos["codigo_barras"], citas["codigo_barras"] = codigo, cita[:200]
    return campos, citas


def leer(bd: Session, fotos: list[bytes]) -> Lectura:
    """Lee hasta 4 fotos, una por una; lo primero que se lee bien de cada campo se queda. Nunca lanza."""
    lectura = Lectura(fotos=min(len(fotos), MAX_FOTOS))
    inicio = time.monotonic()
    fallas = []
    for foto in fotos[:MAX_FOTOS]:
        try:
            with puerta.temperatura(0):
                r = puerta.ejecutar(bd, TAREA, usuario_id=None, instrucciones=INSTRUCCIONES,
                                    mensaje="Lee esta foto de la etiqueta.", max_tokens=1200, esfuerzo="low",
                                    imagenes=[base64.b64encode(foto).decode()])
            datos = json.loads(r.texto[r.texto.find("{"):r.texto.rfind("}") + 1])
        except puerta.ErrorIA as e:
            fallas.append(str(e))
            continue
        except (ValueError, AttributeError):
            fallas.append("no se pudo leer su respuesta")
            continue
        if not isinstance(datos, dict):
            continue
        campos, citas = de_respuesta(datos)
        for k, v in campos.items():
            if k not in lectura.campos:
                lectura.campos[k], lectura.citas[k] = v, citas[k]
    lectura.segundos = round(time.monotonic() - inicio, 1)
    if fallas and not lectura.campos:
        ocupada = any("ocupada" in f for f in fallas)
        lectura.nota = ("La IA local está ocupada; intenta en un momento o captura a mano." if ocupada
                        else "No se pudo leer la etiqueta; captura los datos a mano.")
        log.info("Alta con fotos: %s", "; ".join(fallas)[:300])
    elif not lectura.campos:
        lectura.nota = "No se alcanzó a leer ningún dato en las fotos; captura los datos a mano."
    return lectura
