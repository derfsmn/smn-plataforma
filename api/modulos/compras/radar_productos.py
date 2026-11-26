"""Radar de productos, fase 1: evalúa un producto nuevo y le da un semáforo con explicación.

Plan del radar de productos (2026-10-26). Califica una propuesta de proveedor («Lista para evaluar») o una idea que
capturó Compras. Pasos: clasificación (la IA sugiere, Compras confirma), productos parecidos del catálogo, 6 factores de
0 a 100, suma con los pesos de Compras, confianza según los datos que hubo y explicación redactada por la IA.

Reglas de la fase 1, aprobadas en el plan:
- Cortes del semáforo (Diego, 2026-10-12): verde arriba de 80, amarillo de 60 a 80, rojo 59 o menos.
- Si faltan datos (confianza baja) el resultado no puede ser verde.
- Sin pesos completos de Compras, los 6 factores pesan igual. Sin umbral de margen de Compras se usa el provisional
  de Configuración. Todo lo provisional queda marcado en el factor.
- Rechazo directo (2026-10-26): la IA revisa el producto contra las políticas vigentes y las reglas de rechazo y umbral
  de la Base de conocimiento (politicas_producto); si cae en una regla de rechazo, queda en rojo con ese motivo.
  Desde el 11 nov 2026 solo con el dato que lo prueba y si la regla habla de su tipo de producto; si no, es un aviso.
- Ajustes del 11 nov 2026 (aprobados por Diego): margen abajo del mínimo baja poco a poco hasta 0 en 15 %; parecidos
  sin colores ni palabras sueltas, de la misma subcategoría cuando se sabe y solo con precio de $5 o más; el precio
  contra los parecidos se compara por gramo, mililitro o pieza cuando se sabe el tamaño.
"""
import json
import logging
import math
import re
import threading
import unicodedata
from collections import Counter
from contextvars import ContextVar
import dataclasses
from dataclasses import dataclass, field
from urllib.parse import urlparse
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from statistics import median
from typing import Callable

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from core.config import configuracion
from datos import fichas as fi
from datos.fichas import COMO_V053, GRUPO_FORMATO, NOMBRE_FORMATO, NOMBRE_UNIDAD, UNIDADES, formato, tamano  # noqa: F401
from datos.modelos import Producto, Proveedor
from ia import puerta
from modulos.compras import investigar as inv_mod
from modulos.compras import mercado_producto as mp
from modulos.compras import politicas_producto as pp
from modulos.compras import pronostico as pn
from modulos.compras import realidad_producto as rr
from modulos.compras import senal_venta as sv
from modulos.compras import propuestas as pr
from modulos.compras.modelos import RadarSenal
from modulos.compras.modelos_conocimiento import ConocimientoRegla
from modulos.compras.modelos_productos import (
    EvaluacionComparable, EvaluacionFactor, Oportunidad, ProductoEvaluacion, ProductoIdea, ProductoIdeaFoto,
)
from modulos.compras.modelos_propuestas import Propuesta
from nucleo.modelos import Archivo, OrganizacionExterna, ahora

log = logging.getLogger("smn.compras.radar_productos")

# Diego (25 nov 2026): el Precio en dos temas, cada uno con la mitad de su peso: contra nuestro anaquel y contra
# afuera (radar de precios). «precio» se sigue guardando (el promedio de los dos) para el dictamen y lo anterior, sin peso.
FACTORES = ("demanda", "rentabilidad", "precio", "precio_anaquel", "precio_afuera", "tendencia", "categoria", "proveedor")
NOMBRES = {"demanda": "Demanda", "rentabilidad": "Rentabilidad", "precio": "Precio",
           "precio_anaquel": "Precio contra anaquel", "precio_afuera": "Precio contra afuera", "tendencia": "Tendencia",
           "categoria": "Categoría", "proveedor": "Proveedor"}
TAREA_CLASIFICAR = "compras.productos_clasificar"
TAREA_PARECIDOS = "compras.productos_parecidos"
TAREA_TENDENCIA = "compras.productos_tendencia"
MAX_COMPARABLES = 10
MIN_SIMILITUD = Decimal("0.15")
DIAS_SENALES = 180
NIVEL_SENAL = {"ALTA": 100, "MEDIA": 80, "TEMPRANA": 65}
# Nada habla de este producto: el factor no cuenta ni baja la confianza (recalibración del 9 nov 2026: con 60 fijo
# jalaba hacia amarillo a casi todos; antes, con 35, los hundía)
SIN_SENAL = "Nadie habla de él en internet"
ESTIRA_DEMANDA = 1.3


def _percentil_para(meta: int) -> int:
    """Lugar en la lista de venta que hace falta para que la demanda (sin ajuste por tendencia) llegue a `meta`."""
    return min(100, math.ceil(50 + (meta - 50) / ESTIRA_DEMANDA))


CALC_TENDENCIA = ("Toma la señal más fuerte del radar de tendencias que habla del producto: alta = 100, media = 80, "
                  "temprana = 65. Si ninguna habla de él, no cuenta: ni sube ni baja la calificación.")
IVA_SUPUESTO = Decimal("16")  # solo para ideas con costo estimado; se dice en el detalle
PALABRAS_VACIAS = {
    "de", "del", "la", "el", "los", "las", "con", "sin", "para", "por", "en", "y", "o", "un", "una", "al", "a",
    "mg", "gr", "g", "ml", "kg", "lt", "pza", "pzas", "piezas", "caps", "capsulas", "tabs", "tabletas", "frasco",
    "polvo", "liquido", "gomitas", "sobres", "sobre", "natural", "naturales", "plus", "premium",
    # 11 nov 2026: colores y palabras sueltas que juntaban productos que no se parecen («cinta azul» con «pre workout
    # frambuesa azul», «pre-cortada» con pre-entrenos, «sólido» con shampoo sólido)
    "azul", "azules", "rojo", "roja", "rosa", "rosado", "morado", "morada", "gris", "amarillo", "amarilla", "negro",
    "negra", "blanco", "blanca", "dorado", "plateado", "pre", "cortada", "precortada", "solido", "solida", "sabor",
    "sabores", "sab", "set", "kit", "pieza", "efecto", "tipo", "nuevo", "nueva", "extra", "ultra", "max", "mini",
    "pack", "paquete", "diseno", "azucar", "lactosa", "grasa", "gluten", "libre", "cada",
}
PISO_MARGEN = Decimal("15")  # con este margen o menos, Rentabilidad vale 0
PRECIO_MINIMO_PARECIDO = Decimal("5")  # menos que esto es un regalo o un error de captura, no un precio de venta
MIN_MISMA_SUBCATEGORIA = 3  # con menos parecidos de su subcategoría se completa con los de su rama


class ErrorEvaluacion(Exception):
    pass


# ---------------------------------------------------------------- utilidades

def _norm(texto: str | None) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _compacta(texto: str | None) -> str:
    return re.sub(r"[^a-z0-9ñ]", "", _norm(texto))


def producto_de_la_marca(marca: str | None, p: Producto) -> bool:
    """Si el producto es de la marca: la marca completa, sin espacios ni guiones, igual a su marca o como palabras
    seguidas en su descripción. Antes bastaba una palabra («B-FIT» se quedaba en «fit» y sacaba los panecillos SALUD FIT
    como de la misma marca, 26 nov 2026)."""
    c = _compacta(marca)
    if len(c) < 3:
        return False
    if c == _compacta(p.marca):
        return True
    partes = re.findall(r"[a-z0-9ñ]+", _norm(marca))
    patron = r"(?<![a-z0-9ñ])" + r"[\s\-./&]*".join(map(re.escape, partes)) + r"(?![a-z0-9ñ])"
    return bool(re.search(patron, _norm(p.marca))) or bool(re.search(patron, _norm(p.descripcion)))


def palabras(*textos: str | None) -> set[str]:
    """Palabras que distinguen un producto: sin acentos, sin números ni palabras vacías."""
    salida: set[str] = set()
    for t in textos:
        for p in re.findall(r"[a-zñ]{3,}", _norm(t)):
            if p not in PALABRAS_VACIAS:
                salida.add(p)
    return salida


# 18 nov 2026 (Hybrix 5 en tres sabores salió con tres subcategorías y parecidos distintos: la vainilla se comparó con
# proteínas vegetales de vainilla y el cookies & cream con whey cookies and cream). El sabor no cambia qué es el producto:
# se quita lo que va después de «sabor» o «sab» hasta el siguiente número o el final.
_SABOR = re.compile(r"\b(?:sabor(?:es)?|sab)\b\.?[^\d]*", re.IGNORECASE)


def sin_sabor(texto: str | None) -> str | None:
    return _SABOR.sub(" ", texto) if texto else texto


def _entero(v: float | Decimal) -> int:
    return int(Decimal(str(v)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _acotar(v: float) -> int:
    return max(0, min(100, _entero(v)))


def _pesos(n: Decimal | None) -> str:
    return "—" if n is None else f"${n:,.2f}"


def color_de(puntaje: int | None, confianza: str) -> str:
    if puntaje is None:
        return "amarillo"
    color = "verde" if puntaje > 80 else "amarillo" if puntaje >= 60 else "rojo"
    return "amarillo" if color == "verde" and confianza == "baja" else color


# ---------------------------------------------------------------- lo que se evalúa

@dataclass
class Sujeto:
    tipo: str  # propuesta / idea
    nombre: str
    marca: str | None = None
    departamento: str | None = None
    descripcion: str | None = None
    ingrediente: str | None = None
    forma: str | None = None
    precio: Decimal | None = None  # al que se vendería o se vio, con impuestos
    margen: Decimal | None = None  # %
    costo: Decimal | None = None  # solo ideas: costo estimado
    margen_nota: str | None = None
    mercado: list[tuple[Decimal, str]] = field(default_factory=list)  # los que reportó el proveedor, con impuestos
    codigo_barras: str | None = None
    proveedor_nombres: list[str] = field(default_factory=list)  # razón social y nombre comercial
    contenido: str | None = None  # 300 g, 60 cápsulas…
    proveedor_smn: str | None = None
    inscrito_gs1: str | None = None
    apoyos: int = 0
    registro_sanitario: bool = False
    proveedor_intelisis: str | None = None  # clave en Intelisis si la empresa ya es proveedor nuestro
    activo_g: Decimal | None = None  # gramos del activo principal en todo el envase (por porción × porciones)
    piezas_caja: int | None = None  # piezas por caja master (solo propuestas)
    ficha: fi.Ficha | None = None  # ficha técnica estándar (migración 0047)
    porciones: int | None = None  # las que capturó Compras en la idea
    # Migración 0055 (22 nov 2026): tipo de producto (lista de márgenes A–F) y precio de membresía con IVA; si Compras
    # no lo captura, se calcula con la regla de la lista (`membresia_calculada`)
    lista: str | None = None
    precio_membresia: Decimal | None = None
    membresia_calculada: bool = False
    # 26 nov 2026: los productos de su mismo ingrediente y forma (los colágenos en polvo) para el precio contra anaquel;
    # se llena con `poner_familia`
    familia: list = field(default_factory=list)

    @property
    def margen_membresia(self) -> Decimal | None:
        """Margen al precio de membresía con el mismo costo: 1 − (1 − margen de lista) × lista / membresía."""
        if self.margen is None or not self.precio or not self.precio_membresia or self.precio_membresia <= 0:
            return None
        return ((1 - (1 - self.margen / 100) * self.precio / self.precio_membresia) * 100).quantize(Decimal("0.01"))

    def texto(self) -> set[str]:
        return palabras(sin_sabor(self.nombre), self.ingrediente,
                        sin_sabor(self.descripcion) if not self.ingrediente else None)


@dataclass(frozen=True)
class Lista:
    clave: str
    nombre: str
    lista: Decimal  # margen mínimo sobre el precio de lista, %
    membresia: Decimal  # sobre el precio de membresía, %

    def texto(self) -> str:
        return f"lista {self.clave}, {self.nombre}"


NOMBRES_LISTA = {"A": "Autoservicio (renombre)", "B": "Margen general", "C": "80/20 (revisar con gerencia)",
                 "D": "Nutrición deportiva nacional", "E": "Nutrición deportiva importación", "F": "Margen específico"}
LISTA_OMISION = "A"  # sin tipo de producto (Diego, 29 oct 2026: «ahorita todos entran en la A»)


def listas() -> dict[str, Lista]:
    """Las 6 listas de «MARGENES PARA CALCULO DE PRECIOS.xlsx» (Compras, 29 oct 2026), editables en Configuración con el
    formato «A=31/28; B=45/35…». Lo que no se entienda se queda con el valor del Excel."""
    def leer(texto: str) -> dict[str, tuple[Decimal, Decimal]]:
        salida = {}
        for parte in (texto or "").replace(",", ";").split(";"):
            m = re.fullmatch(r"\s*([A-Fa-f])\s*=\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*", parte)
            if m and 0 < Decimal(m[2]) < 100 and 0 < Decimal(m[3]) < 100:
                salida[m[1].upper()] = (Decimal(m[2]), Decimal(m[3]))
        return salida
    base = leer("A=31/28; B=45/35; C=39/31; D=36/31; E=31/26; F=41/34")
    base.update(leer(configuracion().radar_productos_listas_margen))
    return {k: Lista(k, NOMBRES_LISTA[k], *v) for k, v in base.items()}


def membresia_de(precio: Decimal | None, lista: Lista) -> Decimal | None:
    """Precio de membresía con la regla del Excel: lista = costo / (1 − margen lista) y membresía = costo / (1 − margen
    membresía), así que membresía = lista × (1 − margen lista) / (1 − margen membresía)."""
    if not precio:
        return None
    return (precio * (1 - lista.lista / 100) / (1 - lista.membresia / 100)).quantize(Decimal("0.01"))


def _con_lista(s: Sujeto, clave: str | None, membresia: Decimal | None) -> Sujeto:
    s.lista = clave if clave in NOMBRES_LISTA else None
    if membresia and membresia > 0:
        s.precio_membresia = membresia
    elif s.precio:
        s.precio_membresia = membresia_de(s.precio, listas()[s.lista or LISTA_OMISION])
        s.membresia_calculada = True
    return s


def sujeto_de_propuesta(p: Propuesta) -> Sujeto:
    r = pr.Respuestas.model_validate_json(p.respuestas)
    principal = next((x for x in r.presentaciones if x.pvp_sugerido or x.costo_neto_sin_iva), r.presentaciones[0])
    mercado = [(precio, c.comercio or "sin comercio") for c in r.mercado.competidores
               if (precio := pr.numero(c.precio)) and precio > 0]
    forma = principal.forma_otro if principal.forma == "Otro" else principal.forma
    return _con_lista(Sujeto(tipo="propuesta", nombre=p.producto or principal.descripcion or "Sin nombre", marca=p.marca,
                  departamento=p.departamento or r.general.departamento, descripcion=principal.descripcion,
                  ingrediente=principal.ingrediente_principal, forma=forma, precio=pr.numero(principal.pvp_sugerido),
                  margen=pr.margen(principal), mercado=mercado, proveedor_smn=r.proveedor.es_proveedor_smn,
                  inscrito_gs1=r.proveedor.inscrito_gs1, apoyos=len([a for a in r.lanzamiento.apoyos if a.tipo]),
                  registro_sanitario=bool(principal.registro_sanitario), codigo_barras=principal.codigo_barras or None,
                  contenido=principal.contenido_neto or None, piezas_caja=pr.entero(principal.piezas_caja_master),
                  proveedor_nombres=[x for x in (r.proveedor.razon_social, r.proveedor.nombre_comercial) if x]),
                      p.lista_margen, p.precio_membresia)


def sujeto_de_idea(i: ProductoIdea) -> Sujeto:
    """Desde la migración 0046 la idea trae «nuestro precio» aparte del precio que se vio afuera (Diego, 13 nov 2026:
    en la captura rápida el precio visto se usaba como nuestro precio final). Sin nuestro precio, el visto sigue
    contando como nuestro precio, como antes; con los dos, el visto es un precio del mercado."""
    precio = i.precio_nuestro or i.precio_visto
    margen, nota = None, None
    if i.costo_estimado and precio:
        base = precio / (1 + IVA_SUPUESTO / 100)
        margen = ((base - i.costo_estimado) / base * 100).quantize(Decimal("0.01"))
        nota = ("con el costo estimado y nuestro precio" if i.precio_nuestro else
                "con el costo estimado y el precio visto") + ", suponiendo IVA de 16 %"
    mercado = ([(i.precio_visto, i.donde_se_vio or "donde se vio")]
               if i.precio_nuestro and i.precio_visto and i.precio_visto > 0 else [])
    activo = (i.activo_g_porcion * i.porciones) if i.activo_g_porcion and i.porciones else None
    return _con_lista(Sujeto(tipo="idea", nombre=i.nombre, marca=i.marca, departamento=i.departamento, descripcion=i.descripcion,
                  ingrediente=i.ingrediente, forma=i.forma, precio=precio, margen=margen, costo=i.costo_estimado,
                  margen_nota=nota, proveedor_intelisis=i.proveedor_intelisis, mercado=mercado,
                  contenido=i.contenido or None, codigo_barras=i.codigo_barras or None, activo_g=activo,
                  porciones=int(i.porciones) if i.porciones else None,
                  proveedor_nombres=[i.proveedor_nuevo] if i.proveedor_nuevo else []),
                      i.lista_margen, i.precio_membresia)


# ---------------------------------------------------------------- clasificación y parecidos

INSTRUCCIONES_CLASIFICAR = """Eres analista de Compras de una cadena de tiendas naturistas en México.
Te doy un producto nuevo y la lista de ramas, subcategorías y segmentos que ya existen en el catálogo.
Elige la combinación que mejor le queda, copiándola EXACTAMENTE de la lista. Si ninguna le queda, contesta nulos.
Fíjate en QUÉ ES el producto y cómo se usa, no en una palabra suelta: orégano seco para cocinar es un condimento, no un
suplemento digestivo; un vaso mezclador (shaker) es un accesorio, no una proteína; una cinta kinesiológica no es una
muñequera. En "ejemplos" van productos del catálogo que se le parecen por nombre: úsalos solo si son el mismo tipo.
Contesta solo JSON: {"rama": "...", "subcategoria": "...", "segmento": "..."}"""


def opciones_clasificacion(bd: Session, departamento: str | None) -> list[tuple[str, str, str]]:
    q = (select(Producto.rama, Producto.subcategoria, Producto.segmento).distinct()
         .where(Producto.activo == true(), Producto.subcategoria.is_not(None)))
    filas = bd.execute(q.where(Producto.departamento == departamento).limit(300)).all() if departamento else []
    if not filas:  # el departamento no tiene subcategorías (o no hay departamento): las de todo el catálogo
        filas = bd.execute(q.limit(300)).all()
    return [(r or "", s or "", g or "") for r, s, g in filas]


def clasificar(bd: Session, s: Sujeto, parecidos: list[tuple[Producto, Decimal]] | None = None
               ) -> tuple[str | None, str | None, str | None]:
    """La IA sugiere rama, subcategoría y segmento de entre los que existen. Si falla, queda sin clasificar."""
    # 11 nov 2026: el departamento que captura Compras («SUPLEMENTOS», «DEPORTES») muchas veces no existe en el
    # catálogo y entonces salían 300 opciones al azar; ahora van también las de los productos que más se le parecen
    # (v0.4: los que ya revisó la IA, para que el orégano no tome la subcategoría de unas cápsulas)
    if parecidos is None:
        parecidos = buscar_parecidos(bd, s, None)
    cercanos = [p for p, _ in parecidos if p.subcategoria]
    propias = [(p.rama or "", p.subcategoria or "", p.segmento or "") for p in cercanos]
    con_depto = bd.execute(select(Producto.rama, Producto.subcategoria, Producto.segmento).distinct().where(
        Producto.activo == true(), Producto.subcategoria.is_not(None), Producto.departamento == s.departamento)
        .limit(300)).all() if s.departamento else []
    opciones = list(dict.fromkeys(propias + [(r or "", c or "", g or "") for r, c, g in con_depto]))
    if not opciones:
        opciones = opciones_clasificacion(bd, s.departamento)
    if not opciones:
        return None, None, None
    mensaje = json.dumps({
        "producto": s.nombre, "marca": s.marca, "departamento": s.departamento, "descripcion": s.descripcion,
        "ingrediente_principal": s.ingrediente, "forma": s.forma, "contenido": s.contenido,
        "ejemplos": [f"{p.descripcion} → {p.subcategoria}" for p in cercanos[:8]],
        "opciones": [{"rama": r, "subcategoria": c, "segmento": g} for r, c, g in opciones],
    }, ensure_ascii=False)
    try:
        r = puerta.ejecutar(bd, TAREA_CLASIFICAR, usuario_id=None, instrucciones=INSTRUCCIONES_CLASIFICAR,
                            mensaje=mensaje, max_tokens=600, esfuerzo="low", formato="json",
                            contexto=puerta.ventana(INSTRUCCIONES_CLASIFICAR, mensaje, salida=600))
        datos = json.loads(r.texto[r.texto.find("{"):r.texto.rfind("}") + 1])
    except (puerta.ErrorIA, ValueError) as e:
        log.warning("Radar de productos: no se pudo clasificar «%s»: %s", s.nombre, e)
        return None, None, None
    elegida = (datos.get("rama") or "", datos.get("subcategoria") or "", datos.get("segmento") or "")
    if elegida not in opciones:  # la IA solo puede elegir de la lista
        return None, None, None
    return tuple(v or None for v in elegida)


SINONIMOS = {"capsulas": "cap", "capsula": "cap", "caps": "cap", "tabletas": "tab", "tableta": "tab", "tabs": "tab",
             "comprimidos": "tab", "gramos": "g", "gr": "g", "grs": "g", "mililitros": "ml", "piezas": "pz", "pzas": "pz",
             "pza": "pz", "sobres": "sob", "sobre": "sob", "softgels": "softgel", "kilo": "kg"}
CONECTORES = {"de", "del", "con", "c", "x", "y", "en", "el", "la", "los", "las", "para"}


def presentacion(*textos: str | None) -> frozenset[str]:
    """Todas las palabras y números del nombre, con unidades normalizadas: «Demograss Plus 30 Cápsulas» y
    «DEMOGRASS PLUS C/30 CAPS» dan lo mismo. Sirve para reconocer el mismo producto y su presentación."""
    salida = set()
    for t in textos:
        for p in re.findall(r"\d+(?:[.,]\d+)?|[a-zñ]+", _norm(t)):
            p = SINONIMOS.get(p, p).replace(",", ".")
            if p not in CONECTORES:
                salida.add(p)
    return frozenset(salida)


def _clave_sujeto(s: Sujeto) -> frozenset[str]:
    return presentacion(s.marca, s.nombre, s.contenido)


def _clave_producto(p: Producto) -> frozenset[str]:
    return presentacion(p.marca, p.descripcion)


# Palabras que Compras escribe al describir y el catálogo no: no cambian el producto ni la presentación
GENERICAS = {"bebida", "hidratante", "sabor", "suplemento", "alimenticio", "alimento", "producto", "natural",
             "naturales", "botella", "frasco", "bote", "caja", "presentacion", "contenido", "neto", "polvo", "liquido"}


TIPO_GENERICAS = GENERICAS | {"complemento", "complementos", "suplementos", "alimenticios", "auxiliar", "capsulas",
                               "tabletas", "gomitas"}


def _numero(p: str) -> bool:
    return p[0].isdigit()


def es_mismo(s: Sujeto, p: Producto) -> bool:
    """Mismo producto y presentación. La marca puede venir distinta en el catálogo (a veces es el proveedor): se
    comparan el nombre y la presentación sin las palabras de las marcas, y la marca del sujeto debe aparecer en el
    producto. Todas las palabras del catálogo deben estar en lo que capturó Compras, con los mismos números
    (355 ml no es 630 ml); lo que Compras escribió de más solo puede ser genérico («Bebida hidratante … sabor …»)."""
    marca_s, marca_p = presentacion(s.marca), presentacion(p.marca)
    desc = presentacion(p.descripcion)
    if marca_s and not marca_s <= (desc | marca_p):
        return False
    quitar = marca_s | marca_p
    suya = desc - quitar
    if len([x for x in suya if not _numero(x)]) < 2 and len(suya) < 3:
        return False
    for clave in (presentacion(s.nombre, s.contenido) - quitar, presentacion(s.nombre) - quitar):
        numeros = {x for x in clave if _numero(x)}
        if suya <= clave and numeros == {x for x in suya if _numero(x)} and clave - suya <= GENERICAS:
            return True
    return False


def subcategoria_de_parecidos(parecidos: list[tuple[Producto, Decimal]]) -> Producto | None:
    """Sin clasificación: la subcategoría que tienen al menos 60 % de los parecidos cercanos (similitud ≥ 0.5)."""
    cercanos = [p for p, sim in parecidos if sim >= Decimal("0.5") and p.subcategoria]
    if len(cercanos) < 2:
        return None
    sub, n = Counter(p.subcategoria for p in cercanos).most_common(1)[0]
    return next(p for p in cercanos if p.subcategoria == sub) if n / len(cercanos) >= 0.6 else None


# Ingrediente principal (Diego, 24 nov 2026, caso BDM Life Berberina): la IA lo clasificó en «Plantas › Hierbas suecas» y
# dejó fuera las 11 berberinas que ya vendemos (todas en «Sistema hepático › Auxiliar en la diabetes»); se quedó sin
# parecidos y la Demanda salió en 0. Si varios productos del catálogo llevan en el nombre el ingrediente principal y casi
# todos están en la misma subcategoría, la subcategoría sale de ellos y nunca se quedan fuera de los parecidos.
MIN_POR_INGREDIENTE = 3  # productos activos con el ingrediente en el nombre para que cuenten
ACUERDO_INGREDIENTE = 0.6  # parte de esos productos que debe estar en la misma subcategoría
LETRAS_INGREDIENTE = 5  # palabras más cortas («life», «plus») no se usan como ingrediente


@dataclass
class PorIngrediente:
    palabra: str  # la raíz con que se encontraron («berber»)
    productos: list[Producto]
    rama: str | None
    subcategoria: str | None
    segmento: str | None
    de_acuerdo: int  # cuántos están en esa subcategoría

    @property
    def ids(self) -> set[int]:
        return {p.producto_id for p in self.productos}


def _candidatas_ingrediente(s: Sujeto) -> list[str]:
    """Raíces que pueden ser el ingrediente principal, en orden: primero las del ingrediente capturado o de la ficha que
    también salen en el nombre, después las del nombre. Sin la marca ni palabras genéricas."""
    fuera = raices(palabras(s.marca)) | raices(GENERICAS)
    def orden(texto: str | None) -> list[str]:
        vistas = []
        for p in re.findall(r"[a-zñ]{3,}", _norm(sin_sabor(texto))):
            if p in PALABRAS_VACIAS or p in GENERICAS or len(p) < LETRAS_INGREDIENTE:
                continue
            r = p[:6]
            if r not in fuera and r not in vistas:
                vistas.append(r)
        return vistas
    del_nombre = orden(s.nombre)
    del_ingrediente = [r for r in orden(s.ingrediente) if r in del_nombre]
    return list(dict.fromkeys(del_ingrediente + del_nombre))


def por_ingrediente(s: Sujeto, activos: list[Producto]) -> PorIngrediente | None:
    """Los productos activos con precio que llevan en la descripción el ingrediente principal del producto nuevo, si son
    al menos 3 y al menos 60 % comparten subcategoría. Se prueba palabra por palabra en el orden de
    `_candidatas_ingrediente`; la primera que cumple gana («Berberina + Piperina + Omega 9»: berberina antes que omega)."""
    candidatas = _candidatas_ingrediente(s)
    if not candidatas:
        return None
    raices_de = {p.producto_id: raices(palabras(sin_sabor(p.descripcion))) for p in activos}
    for r in candidatas:
        con = [p for p in activos if r in raices_de[p.producto_id] and _con_precio(p) and not es_mismo(s, p)]
        con_sub = [p for p in con if p.subcategoria]
        if len(con_sub) < MIN_POR_INGREDIENTE:
            continue
        sub, n = Counter(p.subcategoria for p in con_sub).most_common(1)[0]
        if n / len(con_sub) < ACUERDO_INGREDIENTE:
            continue
        guia = next(p for p in con_sub if p.subcategoria == sub)
        return PorIngrediente(r, con, guia.rama, sub, guia.segmento, n)
    return None


def ingrediente_de(bd: Session, s: Sujeto) -> PorIngrediente | None:
    return por_ingrediente(s, catalogo_activo(bd))


MAX_PARTE_INGREDIENTE = 0.08  # una palabra que sale en más del 8 % del catálogo no es un ingrediente («hidrolizado»)


def del_ingrediente(s: Sujeto, activos: list[Producto]) -> tuple[str, set[int]] | None:
    """Los productos que llevan en la descripción el ingrediente principal, estén en la subcategoría que estén (Diego,
    26 nov 2026: «tenemos muchos colágenos… por qué no sale»). A diferencia de `por_ingrediente`, no pide que la mayoría
    esté en una sola subcategoría: eso sirve para clasificar, no para decidir quién se le parece. Los colágenos están en
    belleza, articulaciones y proteína, y con esa regla se tiraban todos y la idea se quedaba sin parecidos.
    La primera palabra de `_candidatas_ingrediente` con al menos 3 productos gana. (raíz, ids) o None."""
    fuera = raices(TIPO_GENERICAS)
    # En un catálogo chico (pruebas) no hay tope; en el de verdad (miles) se descartan las palabras de todos lados
    tope = int(len(activos) * MAX_PARTE_INGREDIENTE) if len(activos) >= 200 else len(activos)
    raices_de = {p.producto_id: raices(palabras(sin_sabor(p.descripcion))) for p in activos}
    for r in _candidatas_ingrediente(s):
        if r in fuera:
            continue
        ids = {p.producto_id for p in activos if r in raices_de[p.producto_id] and _con_precio(p) and not es_mismo(s, p)}
        if MIN_POR_INGREDIENTE <= len(ids) <= tope:
            return r, ids
    return None


# Examen de clasificación (plan aprobado por Diego el 24 nov 2026): para calificar un producto que ya vendemos «como si
# fuera nuevo», el examen lo esconde del catálogo junto con sus otros sabores y presentaciones, y reusa el catálogo ya
# leído para no consultarlo miles de veces. En la operación normal estas dos variables están vacías.
CATALOGO_FIJO: ContextVar[list[Producto] | None] = ContextVar("radar_catalogo_fijo", default=None)
OCULTOS: ContextVar[frozenset[int]] = ContextVar("radar_ocultos", default=frozenset())


def catalogo_activo(bd: Session) -> list[Producto]:
    base = CATALOGO_FIJO.get()
    if base is None:
        base = list(bd.scalars(select(Producto).where(Producto.activo == true())))
    fuera = OCULTOS.get()
    return [p for p in base if p.producto_id not in fuera] if fuera else base


def mismo_de(s: Sujeto, parecidos: list[tuple[Producto, Decimal]]) -> Producto | None:
    """El producto del catálogo que es este mismo producto: misma marca, nombre y presentación."""
    return next((p for p, _ in parecidos if es_mismo(s, p)), None)


def raices(ps: set[str]) -> set[str]:
    """Las primeras 6 letras de cada palabra: «creatina» y «creatine», «magnesio» y «magnesium» cuentan como la misma
    (13 nov 2026: Birdman Creatine for Women no salía como parecido de una creatina)."""
    return {p[:6] for p in ps}


# Formato del producto (13 nov 2026, plan del reporte por producto aprobado por Diego: «sobre contra sobre»). Los del
# mismo grupo se comparan (un sobre de creatina y un bote de creatina en polvo sí; orégano seco y cápsulas de orégano no)
def formato_sujeto(s: Sujeto) -> str | None:
    return formato(s.forma, s.contenido, s.nombre) or (formato(s.ficha.forma) if s.ficha else None)


# ---------------------------------------------------------------- ficha contra ficha (17 nov 2026)

def _primera_foto(bd: Session, idea_id: int | None) -> bytes | None:
    """La primera foto de la idea (JPEG o PNG de hasta 3 MB), para que la IA lea la etiqueta."""
    if not idea_id:
        return None
    a = bd.scalar(select(Archivo).join(ProductoIdeaFoto, ProductoIdeaFoto.archivo_id == Archivo.archivo_id).where(
        ProductoIdeaFoto.idea_id == idea_id, Archivo.tipo_contenido.in_(("image/jpeg", "image/png")),
        Archivo.tamano_bytes <= 3_000_000).order_by(Archivo.archivo_id))
    if a is None:
        return None
    from nucleo.archivos import _raiz

    raiz = _raiz()
    ruta = (raiz / a.ruta_almacenamiento).resolve()
    return ruta.read_bytes() if raiz in ruta.parents and ruta.is_file() else None


def texto_sujeto(s: Sujeto) -> str:
    return "\n".join(x for x in (s.nombre, s.marca and f"Marca: {s.marca}", s.contenido and f"Contenido: {s.contenido}",
                                 s.forma and f"Forma: {s.forma}", s.ingrediente and f"Ingrediente: {s.ingrediente}",
                                 s.descripcion) if x)


def ficha_sujeto(bd: Session, e: ProductoEvaluacion, s: Sujeto) -> None:
    """Lee (o reusa) la ficha técnica del producto nuevo y llena con ella lo que Compras no capturó: contenido, forma,
    ingrediente y gramos del activo. Lo capturado por Compras siempre gana. Si falla, se sigue sin ficha."""
    origen, oid = ("propuesta", e.propuesta_id) if e.propuesta_id else ("idea", e.idea_id)
    try:
        s.ficha = fi.de_idea(bd, origen, oid, texto_sujeto(s), _primera_foto(bd, e.idea_id))
    except Exception as ex:  # noqa: BLE001 - sin ficha se evalúa como antes
        log.warning("Radar de productos: no se pudo leer la ficha de %s %s: %s", origen, oid, ex)
        s.ficha = None
    f = s.ficha
    if f is None:
        return
    s.contenido = s.contenido or f.contenido_texto()
    s.forma = s.forma or f.forma
    s.ingrediente = s.ingrediente or f.ingrediente_principal
    s.activo_g = s.activo_g or f.activo_total_g()


def cargar_fichas(bd: Session, productos: list[Producto]) -> None:
    """Pega a cada producto del catálogo su ficha técnica (si ya se leyó y se puede usar), para comparar ficha contra
    ficha. Sin ficha se sigue leyendo la descripción, como antes."""
    faltan = [p for p in productos if not hasattr(p, "_ficha")]
    fichas = fi.de_productos(bd, [p.producto_id for p in faltan])
    for p in faltan:
        p._ficha = fichas.get(p.producto_id)


def ficha_de(p: Producto) -> fi.Ficha | None:
    return getattr(p, "_ficha", None)


def tamano_de(p: Producto) -> dict[str, Decimal]:
    """Tamaño del producto del catálogo: de su ficha y, si no tiene, de la descripción."""
    return (f.tamano() if (f := ficha_de(p)) else {}) or tamano(p.descripcion)


def solo_piezas(tam: dict[str, Decimal], forma: str | None) -> dict[str, Decimal]:
    """En cápsulas, tabletas y gomitas se compara por pieza: los gramos de «120 CAP DE 1.2G» son lo que pesa cada
    cápsula (con aceite y relleno), no el ingrediente, y no se pueden poner contra los gramos de otra ficha (caso BDM Life
    Berberina, 25 nov 2026: por gramo salían «muy distintas» todas las berberinas menos una)."""
    if forma and GRUPO_FORMATO.get(forma) in ("solido", "gomita") and "pz" in tam:
        return {"pz": tam["pz"]}
    return tam


def solo_principal(nombre: str) -> str:
    """«Berberina + Piperina» → «Berberina»: los gramos de activo de la ficha son del primero (la piperina va en mg para
    que se absorba mejor; BDM Life, 25 nov 2026)."""
    return re.split(r"\s*(?:\+|,|/|\by\b|\bcon\b)\s*", nombre.strip())[0] or nombre


def tamano_para_precio_de(p: Producto) -> dict[str, Decimal]:
    """Tamaño para comparar precio. En cápsulas, tabletas y gomitas, si la ficha no dice cuántas piezas trae, se toman de
    la descripción (BDM Life, 25 nov 2026: las fichas de las berberinas decían solo gramos y por cápsula quedaba solo
    4 Health, la única con piezas en su ficha: «57 % más caro»)."""
    tam, forma = tamano_de(p), formato_de(p)
    if "pz" not in tam and forma and GRUPO_FORMATO.get(forma) in ("solido", "gomita"):
        if pz := tamano(p.descripcion).get("pz"):
            tam = {**tam, "pz": pz}
    return solo_piezas(tam, forma)


def formato_de(p: Producto) -> str | None:
    return formato(p.descripcion) or (formato(f.forma) if (f := ficha_de(p)) else None)


def mismo_tipo(a: fi.Ficha | None, b: fi.Ficha | None) -> bool | None:
    """¿Las dos fichas dicen el mismo tipo de producto? None si alguna no lo dice."""
    if not a or not b:
        return None
    # Con el mismo ingrediente principal es el mismo tipo, diga lo que diga el texto libre del tipo (BDM Life, 25 nov
    # 2026: «suplemento» contra «complemento auxiliar en la diabetes» descartaba 5 de 7 berberinas)
    ia = {r for r in raices(palabras(solo_principal(a.ingrediente_principal or ""))) if len(r) >= LETRAS_INGREDIENTE}
    ib = raices(palabras(b.ingrediente_principal))
    if ia and ia & ib:
        return True
    if not a.tipo or not b.tipo:
        return None
    # las genéricas se quitan antes de recortar: «suplem» no es «suplemento» y no se quitaba
    pa, pb = raices(palabras(a.tipo) - TIPO_GENERICAS), raices(palabras(b.tipo) - TIPO_GENERICAS)
    if not pa or not pb:
        return None
    return bool(pa & pb)


def _con_precio(p: Producto) -> bool:
    return bool(p.precio_lista_con_impuestos) and p.precio_lista_con_impuestos >= PRECIO_MINIMO_PARECIDO


def buscar_parecidos(bd: Session, s: Sujeto, subcategoria: str | None, rama: str | None = None,
                     conservar: set[int] | frozenset[int] = frozenset()) -> list[tuple[Producto, Decimal]]:
    """Productos activos del catálogo que más se parecen.

    Busca en todo el catálogo, no solo en el departamento capturado (el departamento puede venir distinto). Lo que más
    pesa son las palabras del nombre que aparecen en la descripción del producto; la descripción larga de una idea solo
    suma un poco, para que no diluya el parecido. Suben la misma marca, la misma subcategoría, el mismo departamento y
    la misma forma. Al final se ordena por presentación (Plus 30 cápsulas antes que Plus 90 cápsulas) y el que es el
    mismo producto queda con 1.0.

    Desde el 11 nov 2026: debe compartir al menos una palabra del nombre; sin precio de lista (o de menos de $5) no
    cuenta como parecido; si se sabe la subcategoría, solo entran los de esa subcategoría (y, si son menos de 3, los de
    su misma rama); la misma descripción no se repite."""
    nombre = raices(palabras(sin_sabor(s.nombre)))
    clave = presentacion(s.marca, sin_sabor(s.nombre), s.contenido)
    todas = raices(s.texto())
    if not todas:
        return []
    depto, forma = _norm(s.departamento).strip(), _norm(s.forma)
    medidas = set(tamano(s.contenido, s.nombre) or (s.ficha.tamano() if s.ficha else {}))
    suyo_formato = formato_sujeto(s)
    calificados, crudo, otras_formas = [], {}, set()
    activos = catalogo_activo(bd)
    cargar_fichas(bd, activos)
    for p in activos:
        otras = raices(palabras(sin_sabor(p.descripcion)))
        if not otras:
            continue
        mismo = es_mismo(s, p)
        # La marca del catálogo cuenta como parte del nombre («Krystal Stone» viene en la marca, no en la descripción);
        # de su misma subcategoría entra aunque no comparta palabras (un desodorante en barra de otra marca)
        su_sub = bool(subcategoria) and p.subcategoria == subcategoria
        misma_marca = producto_de_la_marca(s.marca, p)
        if not mismo and (not _con_precio(p) or (nombre and not su_sub and not nombre & (otras | raices(palabras(p.marca))))):
            continue
        cobertura = Decimal(len(nombre & otras)) / Decimal(len(nombre)) if nombre else Decimal(0)
        jaccard = Decimal(len(todas & otras)) / Decimal(len(todas | otras))
        sim = cobertura * Decimal("0.6") + jaccard * Decimal("0.4")
        if sim == 0 and not su_sub and not misma_marca:
            continue
        # 24 nov 2026 (plan de clasificación automática): la marca ya no suma; lo de la misma marca se enseña aparte
        if misma_marca and COMO_V053.get():
            sim += Decimal("0.2")  # así sumaba en la v0.5.3 (solo para compararla)
        if subcategoria and p.subcategoria == subcategoria:
            sim += Decimal("0.15")
        if depto and _norm(p.departamento).strip() == depto:
            sim += Decimal("0.05")
        if forma and forma in _norm(p.descripcion):
            sim += Decimal("0.05")
        if mismo:
            calificados.append((p, Decimal("1.000")))
            continue
        suya = presentacion(p.marca, sin_sabor(p.descripcion))
        if clave:  # nombre y presentación completos, con números: separa variantes de la misma marca
            sim += Decimal(len(clave & suya)) / Decimal(len(clave | suya)) * Decimal("0.25")
        su_formato = formato_de(p) if suyo_formato else None
        mismo_grupo = bool(su_formato) and GRUPO_FORMATO[suyo_formato] == GRUPO_FORMATO[su_formato]
        otra_forma = bool(su_formato) and not mismo_grupo and not COMO_V053.get()
        if otra_forma:
            sim /= 2  # otra forma (cápsulas contra gotas, crema contra polvo): solo si no hay de su forma (24 nov 2026)
        if su_formato == suyo_formato and su_formato:
            sim += Decimal("0.05")  # mismo formato, sobre contra sobre (13 nov 2026)
        # Del mismo grupo de formato no se descarta por la unidad: «30 sobres» y «sobre 5 g» o un bote de 348 g son la
        # misma forma de producto (13 nov 2026, caso Wonu: se quedaba sin parecidos)
        # Ficha contra ficha (17 nov 2026): el mismo tipo de producto sube; otro tipo baja a la mitad
        tipo = mismo_tipo(s.ficha, ficha_de(p))
        if tipo is True:
            sim += Decimal("0.1")
        elif tipo is False and not su_sub:
            sim /= 2
        del_suyo = p.producto_id in conservar
        if not mismo_grupo and medidas and (suyas := set(tamano_de(p))) and not medidas & suyas:
            if not (su_sub or misma_marca or del_suyo):
                continue  # otra forma de producto: orégano de 14 g no se parece a cápsulas de orégano (11 nov 2026)
            sim /= 2
        if del_suyo:  # lleva su ingrediente principal: entra aunque quede abajo del mínimo (26 nov 2026, colágenos)
            sim = max(sim, MIN_SIMILITUD)
        if sim >= MIN_SIMILITUD:
            crudo[p.producto_id] = sim  # para ordenar: dos de 0.99 no empatan (18 nov 2026)
            if otra_forma:
                otras_formas.add(p.producto_id)
            calificados.append((p, min(sim, Decimal("0.99")).quantize(Decimal("0.001"))))
    calificados += sustitutos_por_funcion(bd, s, activos, {p.producto_id for p, _ in calificados})
    # Con 3 o más de su misma forma, los de otra forma salen; con menos, se quedan a la mitad para no dejarlo sin
    # parecidos (caso BDM Life: sin parecidos la Demanda sale de lo típico de la subcategoría)
    if sum(1 for p, _ in calificados if p.producto_id not in otras_formas) >= MIN_MISMA_SUBCATEGORIA:
        calificados = [(p, x) for p, x in calificados if p.producto_id not in otras_formas]
    calificados.sort(key=lambda x: (-x[1], -crudo.get(x[0].producto_id, x[1]), x[0].sku))
    return _depurar(calificados, subcategoria, rama, conservar)[:MAX_COMPARABLES]


def sustitutos_por_funcion(bd: Session, s: Sujeto, activos: list[Producto], ya: set[int]
                           ) -> list[tuple[Producto, Decimal]]:
    """Sustitutos que no comparten palabras pero hacen lo mismo, por el significado de su ficha (bge-m3 en Ollama;
    17 nov 2026). Entran con un parecido de 0.2 a 0.7 según qué tan cerca están; después la IA los revisa como a los
    demás parecidos. Sin ficha, huellas u Ollama no agrega nada."""
    por_id = {p.producto_id: p for p in activos}
    salida = []
    for pid, cos in fi.cercanos_por_funcion(bd, s.ficha):
        p = por_id.get(pid)
        if p is None or pid in ya or not _con_precio(p) or es_mismo(s, p):
            continue
        sim = Decimal(str(round(min(max((cos - 0.5) * 2, 0.2), 0.7), 3)))
        p._por_funcion = True
        salida.append((p, sim))
    return salida


def _depurar(calificados: list[tuple[Producto, Decimal]], subcategoria: str | None,
             rama: str | None, conservar: set[int] | frozenset[int] = frozenset()) -> list[tuple[Producto, Decimal]]:
    """Con subcategoría conocida se quedan los de esa subcategoría; si son menos de 3, se completan con los de la misma
    rama (o, sin rama, con los que no tienen subcategoría). Sin repetir la misma descripción. Los de `conservar` (llevan
    el ingrediente principal, 24 nov 2026) se quedan aunque estén en otra subcategoría."""
    vistos, unicos = set(), []
    for p, sim in calificados:
        llave = " ".join(sorted(presentacion(p.descripcion)))
        if llave not in vistos:
            vistos.add(llave)
            unicos.append((p, sim))
    if not subcategoria:
        return unicos
    propios = [(p, sim) for p, sim in unicos
               if sim == 1 or p.subcategoria == subcategoria or p.producto_id in conservar]
    if len(propios) >= MIN_MISMA_SUBCATEGORIA:
        return propios
    if rama:
        cercanos = [(p, sim) for p, sim in unicos if (p, sim) not in propios and p.rama == rama]
    else:
        cercanos = [(p, sim) for p, sim in unicos if (p, sim) not in propios and not p.subcategoria]
    return propios + cercanos


INSTRUCCIONES_PARECIDOS = """Eres comprador de una cadena de tiendas naturistas en México.
Te doy un producto nuevo y una lista numerada de productos que ya vendemos. Para cada uno decide si es el MISMO TIPO de
producto: un cliente lo vería como alternativa en el anaquel (sirve para lo mismo y se usa igual). La marca, el sabor,
el color y el tamaño NO importan. Una palabra en común no basta.
Ejemplos: cinta kinesiológica vs muñequera elástica = no (una se pega, la otra se pone); orégano seco para cocinar vs
cápsulas de orégano = no (condimento vs suplemento); shaker vs proteína = no; desodorante en barra de otra marca = sí;
proteína en polvo de 1 kg vs proteína en polvo de 500 g = sí.
Contesta SOLO un JSON así: {"revision": [{"n": 1, "mismo_tipo": true, "motivo": "pocas palabras"}, ...]}, uno por
cada número de la lista."""


def revisar_parecidos(bd: Session, s: Sujeto, parecidos: list[tuple[Producto, Decimal]],
                      vistos: dict[str, tuple[bool, str]] | None = None,
                      conservar: set[int] | frozenset[int] = frozenset()
                      ) -> tuple[list[tuple[Producto, Decimal]], list[tuple[Producto, str]]]:
    """La IA local revisa si cada parecido es de verdad el mismo tipo de producto y quita los que no (Diego eligió
    «Solo revisar parecidos», 12 nov 2026). Devuelve (los que quedan, los quitados con su motivo). El mismo producto
    (similitud 1) nunca se quita. Si la IA falla o contesta algo que no se entiende, se quedan todos, como antes.
    `vistos` guarda lo ya revisado por SKU para no volver a preguntar en la misma evaluación."""
    vistos = {} if vistos is None else vistos
    # Los que llevan el ingrediente principal no se le preguntan a la IA: se quedan (24 nov 2026)
    nuevos = [p for p, sim in parecidos if sim < 1 and p.sku not in vistos and p.producto_id not in conservar]
    if nuevos:
        mensaje = json.dumps({
            "producto": s.nombre, "marca": s.marca, "contenido": s.contenido, "forma": s.forma,
            "departamento": s.departamento, "descripcion": (s.descripcion or "")[:400] or None,
            "lista": [{"n": i, "producto": p.descripcion, "subcategoria": p.subcategoria}
                      for i, p in enumerate(nuevos, 1)],
        }, ensure_ascii=False)
        # 22 nov 2026: con 40 tokens por renglón la respuesta salía cortada (el modelo la escribe con sangrías)
        tope = 150 + 80 * len(nuevos)
        try:
            r = puerta.ejecutar(bd, TAREA_PARECIDOS, usuario_id=None, instrucciones=INSTRUCCIONES_PARECIDOS,
                                mensaje=mensaje, max_tokens=tope, esfuerzo="low", formato="json",
                                contexto=puerta.ventana(INSTRUCCIONES_PARECIDOS, mensaje, salida=tope))
            datos = json.loads(r.texto[r.texto.find("{"):r.texto.rfind("}") + 1])
            for x in datos.get("revision") or []:
                n = x.get("n") if isinstance(x, dict) else None
                if isinstance(n, int) and 1 <= n <= len(nuevos) and isinstance(x.get("mismo_tipo"), bool):
                    vistos[nuevos[n - 1].sku] = (x["mismo_tipo"], str(x.get("motivo") or "")[:120])
        except (puerta.ErrorIA, ValueError, AttributeError) as e:
            log.warning("Radar de productos: la IA no pudo revisar los parecidos de «%s»: %s", s.nombre, e)
    quedan, quitados = [], []
    for p, sim in parecidos:
        si, motivo = vistos.get(p.sku, (True, ""))
        if sim >= 1 or si or p.producto_id in conservar:
            quedan.append((p, sim))
        else:
            quitados.append((p, motivo))
    return quedan, quitados


def nota_quitados(quitados: list[tuple[Producto, str]]) -> str:
    if not quitados:
        return ""
    lista = "; ".join(f"{p.descripcion}" + (f" ({m})" if m else "") for p, m in quitados[:5])
    return f"\n\nNo se comparó contra (la IA vio que no es el mismo tipo de producto): {lista}."


# ---------------------------------------------------------------- factores

@dataclass
class Factor:
    puntaje: int | None
    valor: str | None
    detalle: str  # qué encontramos
    provisional: bool = False
    calculo: str | None = None  # cómo se llegó a la calificación, con sus números
    mejora: str | None = None  # qué tendría que pasar para que suba (o qué significa)
    meta: Decimal | None = None  # Precio: el precio de referencia (total) contra el que se comparó
    competir: Decimal | None = None  # Precio: el precio más alto con el que deja de salir en rojo (las dos mitades)
    # Precio contra anaquel por unidad (25 nov 2026): {"propio", "medio", "unidad", "toma": {...}} para que la pantalla
    # diga «$3.82 por cápsula contra $5.22 en medio» y no el total de referencia
    por_unidad: dict | None = None


def _n(x: float | Decimal, d: int = 1) -> str:
    """Número para leer: sin decimales si es entero, con coma de miles."""
    x = float(x)
    return f"{x:,.0f}" if abs(x - round(x)) < 0.05 else f"{x:,.{d}f}"


def margen_minimo(bd: Session, departamento: str | None) -> tuple[Decimal, bool]:
    """Umbral de margen de la base de conocimiento (del departamento o general); si no hay, el provisional."""
    reglas = bd.scalars(select(ConocimientoRegla).where(
        ConocimientoRegla.tipo == "umbral", ConocimientoRegla.activa == true(),
        ConocimientoRegla.minimo.is_not(None))).all()
    margen = [r for r in reglas if "margen" in _norm(r.criterio)]
    propia = next((r for r in margen if departamento and r.departamento == departamento), None)
    general = next((r for r in margen if not r.departamento), None)
    if regla := propia or general:
        return Decimal(regla.minimo), False
    return Decimal(str(configuracion().radar_productos_margen_minimo)), True


@dataclass
class Minimos:
    lista: Decimal
    membresia: Decimal | None
    origen: str  # de dónde sale, en palabras
    provisional: bool
    de_lista: Lista | None = None  # la lista A–F con que se evaluó (por omisión, la A)


def minimos(bd: Session, s: Sujeto) -> Minimos:
    """Margen mínimo al precio de lista y al de membresía. Con tipo de producto, los de su lista (Diego, 22 nov 2026);
    sin él, el de la Base de conocimiento (hoy la lista A) para el de lista y el de membresía de la lista A."""
    todas = listas()
    if s.lista and (l_ := todas.get(s.lista)):
        return Minimos(l_.lista, l_.membresia, f"{l_.texto()}, de la tabla de márgenes de Compras", False, l_)
    minimo, provisional = margen_minimo(bd, s.departamento)
    a = todas.get(LISTA_OMISION)
    origen = ("provisional: Compras todavía no define el suyo" if provisional
              else "el que definió Compras en su Base de conocimiento")
    return Minimos(minimo, a.membresia if a else None,
                   origen + "; falta el tipo de producto, se toma la lista A por omisión", provisional, a)


def _puntos_margen(margen: Decimal, minimo: Decimal) -> float:
    # En el mínimo vale 60 (amarillo); cada punto arriba suma 8/3 hasta 100 a los 15 puntos. Abajo del mínimo baja
    # parejo hasta 0 en 15 % de margen (Diego, 11 nov 2026: con 6 por punto, 30.4 % contra 31 % ya casi no valía nada)
    dif = float(margen - minimo)
    abajo = 60 / float(minimo - PISO_MARGEN) if minimo > PISO_MARGEN else 6.0
    return 60 + dif * 40 / 15 if dif >= 0 else 60 + dif * abajo


def _pct(x: Decimal) -> str:
    return f"{x:.0f}" if x == x.to_integral_value() else f"{x:.1f}"


def f_rentabilidad(bd: Session, s: Sujeto, subcategoria: str | None = None, v: rr.Ventana | None = None,
                   mismo: Producto | None = None, tope: Decimal | None = None) -> Factor:
    """`tope`: el precio del mercado (la referencia del factor Precio). El precio meta nunca se propone arriba de él."""
    if mismo and v and (real := rr.margen_sku(bd, v, mismo.sku)):
        # Ya lo vendemos: cuenta su margen real, no el estimado (el precio visto suele ser el de la competencia)
        capturado = f"; con lo capturado daría {s.margen} %" if s.margen is not None else ""
        s = Sujeto(**{**s.__dict__, "margen": real, "margen_nota": f"margen real del mismo producto que ya vendemos, "
                      f"{mismo.sku}, en la {v.texto()}{capturado}"})
    if s.margen is None:
        if s.tipo == "propuesta":
            falta = "el costo y el precio sugerido"
        else:
            falta = " y ".join(x for x, hay in (("el costo estimado", s.costo), ("nuestro precio", s.precio)) if not hay)
        return Factor(None, None, f"Sin datos: falta {falta}. Con los dos se calcula el margen.")
    m = minimos(bd, s)
    minimo, provisional = m.lista, m.provisional
    dif = float(s.margen - minimo)
    puntaje = _puntos_margen(s.margen, minimo)
    base = _acotar(puntaje)
    nota = f" ({s.margen_nota})" if s.margen_nota else ""
    minimo_texto = _pct(minimo)
    detalle = (f"Al precio de lista, de cada $100 que se vende quedan ${_n(s.margen)} después de pagar el producto{nota}. "
               f"Compras pide al menos {minimo_texto} % ({m.origen}).")
    piso = (f"baja parejo hasta 0 con {_n(PISO_MARGEN)} % de margen" if minimo > PISO_MARGEN
            else "cada punto abajo resta 6")
    calculo = (f"Si deja justo el mínimo ({minimo_texto} %) saca 60. Cada punto de margen arriba del mínimo suma 2.7 "
               f"(con 15 puntos arriba llega a 100); abajo del mínimo {piso}. Al precio de lista queda {_n(abs(dif))} "
               f"puntos {'arriba' if dif >= 0 else 'abajo'} del mínimo: {base}.")
    # Precio de membresía (Diego, 22 nov 2026): se mide igual contra su mínimo y cuenta el más bajo de los dos. Si ya lo
    # vendemos, el margen real ya trae lo que se vendió a socios
    mm = s.margen_membresia if not mismo else None
    dif_m = float(mm - m.membresia) if mm is not None and m.membresia is not None else None
    base_m = 100
    if dif_m is not None:
        base_m = _acotar(_puntos_margen(mm, m.membresia))
        como = ("calculado con la regla de su lista" if s.membresia_calculada else "el que capturó Compras")
        detalle += (f" Al precio de membresía ({_pesos(s.precio_membresia)}, {como}) quedan ${_n(mm)} y pide al menos "
                    f"{_pct(m.membresia)} %.")
        calculo += (f" Al precio de membresía queda {_n(abs(dif_m))} puntos {'arriba' if dif_m >= 0 else 'abajo'} de su "
                    f"mínimo ({_pct(m.membresia)} %): {base_m}. " + (
                        "Como se calculó con la regla de la lista, cuenta el de lista." if s.membresia_calculada
                        else f"Cuenta el más bajo de los dos: {min(base, base_m)}."))
    # Calculado con la regla de la lista, el de membresía sale igual al de lista (solo cambia la escala abajo del mínimo):
    # cuenta solo si Compras lo capturó
    por_membresia = dif_m is not None and base_m < base and not s.membresia_calculada
    if por_membresia:
        puntaje, base, dif = _puntos_margen(mm, m.membresia), base_m, dif_m
    ajuste = ""
    # Contra lo que de verdad deja la subcategoría: 5 puntos menos si queda 5 o más abajo, 5 más si queda 5 o más arriba
    if subcategoria and v and (real := rr.margen_real(bd, v, subcategoria)):
        margen_sub, n = real
        if s.margen <= margen_sub - 5:
            puntaje -= 5
            ajuste = f" Resta 5 porque deja 5 puntos o más por debajo de lo que deja su subcategoría ({margen_sub} %)."
        elif s.margen >= margen_sub + 5:
            puntaje += 5
            ajuste = f" Suma 5 porque deja 5 puntos o más por arriba de lo que deja su subcategoría ({margen_sub} %)."
        detalle += (f" Lo que ya vendemos de «{subcategoria.capitalize()}» ({n} productos) deja {_n(margen_sub)} %.")
    final = _acotar(puntaje)
    mejora = None
    cual, hoy, min_cual = (("con membresía", mm, m.membresia) if por_membresia else ("", s.margen, minimo))
    if final <= 80:
        meta = min_cual + Decimal("7.6")
        mejora = (f"Para que este factor salga arriba de 80 tendría que dejar al menos {_n(meta)} % de margen"
                  f"{' ' + cual if cual else ''} (hoy {_n(hoy)} %): con un precio de venta más alto o un costo más bajo.")
        if not por_membresia and dif < 0 and (lectura := _para_llegar(s, minimo, tope)):
            mejora = lectura
    extra = (f"; con membresía deja {_n(mm)} % (mínimo {_pct(m.membresia)} %)"
             if mm is not None and not por_membresia and not s.membresia_calculada
             else f"; al precio de lista deja {_n(s.margen)} % (mínimo {minimo_texto} %)" if por_membresia else "")
    if dif >= 0:
        valor = (f"Deja {_n(hoy)} % de margen{' ' + cual if cual else ''}, {_n(dif)} puntos arriba del mínimo "
                 f"({_pct(min_cual)} %){extra}")
    else:
        valor = (f"Margen bajo{' ' + cual if cual else ''}: deja {_n(hoy)} %, {_n(-dif)} puntos abajo del mínimo "
                 f"({_pct(min_cual)} %){extra}")
    return Factor(final, valor, detalle, provisional,
                  calculo + (f"{ajuste} Calificación: {final}." if ajuste else ""), mejora)

def metas(s: Sujeto, minimo: Decimal, tope: Decimal | None = None) -> tuple[Decimal, Decimal, Decimal, bool] | None:
    """(costo actual, precio meta, costo meta, el precio meta pasa del mercado) para dejar el margen mínimo. El costo meta
    se calcula con nuestro precio o, si nuestro precio está arriba del mercado, con el del mercado (13 nov 2026: el radar
    proponía vender Wonu en $840.58 cuando afuera está en $599 a $660)."""
    if not s.precio or s.margen is None or minimo >= 100:
        return None
    base = s.precio / (1 + IVA_SUPUESTO / 100)
    costo = s.costo or base * (1 - s.margen / 100)
    if costo <= 0:
        return None
    precio_meta = costo / (1 - minimo / 100) * (1 + IVA_SUPUESTO / 100)
    venta = min(s.precio, tope) if tope else s.precio
    costo_meta = venta / (1 + IVA_SUPUESTO / 100) * (1 - minimo / 100)
    return costo, precio_meta, costo_meta, bool(tope) and precio_meta > tope


def _para_llegar(s: Sujeto, minimo: Decimal, tope: Decimal | None = None) -> str | None:
    """Lectura de comprador: a qué precio venderlo o a qué costo conseguirlo para dejar el margen mínimo. Nunca propone
    un precio arriba del mercado: si con el precio no alcanza, la salida es el costo."""
    if not (m := metas(s, minimo, tope)):
        return None
    costo, precio_meta, costo_meta, pasa = m
    baja = (1 - costo_meta / costo) * 100
    if pasa:
        return (f"Subirle el precio no funciona: para dejar {_n(minimo)} % tendría que venderse en {_pesos(precio_meta)} "
                f"y el mercado está en {_pesos(tope)}. La salida es el costo: conseguirlo en {_pesos(costo_meta)} sin IVA "
                f"({_n(baja)} % menos que hoy).")
    sube = (precio_meta / s.precio - 1) * 100
    return (f"Para dejar el mínimo de {_n(minimo)} %: venderlo en {_pesos(precio_meta)} ({_n(sube)} % más) o "
            f"conseguirlo en {_pesos(costo_meta)} de costo sin IVA ({_n(baja)} % menos). Con el precio de venta, revisa "
            "en Precio si así sigue siendo competitivo.")


def _por_precio(ratio: Decimal) -> int:
    # Igual al mercado vale 75; cada 1 % más caro resta 1 punto y cada 1 % más barato suma 1 (recalibración del
    # 9 nov 2026: con 70 y 2 puntos por 1 % casi ningún producto salía en verde)
    return _acotar(75 - float(ratio - 1) * 100)


def _precio_valor(ratio: Decimal, contra: str) -> str:
    pct = float(ratio - 1) * 100
    nivel = ("Buen precio" if pct <= -5 else "En precio" if pct <= 5 else "Algo caro" if pct <= 15 else "Caro")
    if round(pct) == 0:
        return f"{nivel}: igual que {contra}"
    return f"{nivel}: {abs(pct):.0f} % {'más caro' if pct > 0 else 'más barato'} que {contra}"


def _precio_explicado(ratio: Decimal, referencia: Decimal, contra: str) -> tuple[str, str | None]:
    """Cómo se calificó el precio y qué precio haría falta para verde."""
    pct = float(ratio - 1) * 100
    if round(pct) == 0:
        donde = "Está prácticamente igual"
    else:
        donde = f"Está {abs(pct):.0f} % {'más caro' if pct > 0 else 'más barato'}"
    calculo = (f"Si cuesta lo mismo que {contra} saca 75. Cada 1 % más caro resta 1 punto y cada 1 % más barato suma "
               f"1. {donde}: {_por_precio(ratio)}.")
    mejora = None
    if _por_precio(ratio) <= 80:
        mejora = (f"Para que este factor salga arriba de 80 tendría que venderse en "
                  f"{_pesos(referencia * Decimal('0.94'))} o menos, es decir, "
                  f"al menos 6 % abajo de {contra}.")
    return calculo, mejora


def _vendedores(nombres: list[str], n: int = 4) -> str:
    unicos = list(dict.fromkeys(nombres))
    return ", ".join(unicos[:n]) + (f" y {len(unicos) - n} más" if len(unicos) > n else "")


RANGO_PRECIO = (Decimal("0.4"), Decimal("2.5"))  # fuera de esto contra la referencia, no es el mismo producto o presentación


def _en_rango(internet: mp.Mercado | None, referencia: Decimal | None) -> tuple[mp.Mercado | None, list[dict]]:
    """Quita los precios de internet que no pueden ser el mismo producto: menos de 0.4 o más de 2.5 veces la
    referencia (nuestro precio o el que se vio). Regresa el mercado filtrado y los descartados."""
    if not internet or not internet.precios or not referencia:
        return internet, []
    bajo, alto = referencia * RANGO_PRECIO[0], referencia * RANGO_PRECIO[1]
    dentro = [p for p in internet.precios if bajo <= Decimal(str(p["precio"])) <= alto]
    fuera = [p for p in internet.precios if p not in dentro]
    return mp.Mercado(**{**internet.__dict__, "precios": dentro}), fuera


def _fuera_texto(fuera: list[dict]) -> str:
    if not fuera:
        return ""
    lista = ", ".join(f"{p['vendedor']} {_pesos(Decimal(str(p['precio'])))}" for p in fuera[:3])
    return f" Se descartaron {len(fuera)} precio(s) de internet fuera de rango ({lista}): no parecen la misma presentación."


def _por_unidad(s: Sujeto, parecidos: list[tuple[Producto, Decimal]], campo: str = "precio_lista_con_impuestos",
                todos: bool = False) -> tuple[str, Decimal, list[tuple[Producto, Decimal]]] | None:
    """Precio por gramo, mililitro o pieza del producto y de los parecidos que dicen su tamaño en la misma unidad.
    Se usa la unidad que comparten más parecidos. Si hay parecidos de tamaño cercano (de la mitad al doble) solo se
    usan esos: un bote de 2 kg siempre sale más barato por gramo que uno de 250 g (Diego, 11 nov 2026)."""
    suyo = solo_piezas(tamano(s.contenido, s.nombre, s.descripcion), formato_sujeto(s))
    if not suyo or not s.precio:
        return None
    mejores = None
    for dim, cantidad in suyo.items():
        con_tam = [(p, tam[dim]) for p, _ in parecidos
                   if getattr(p, campo) and dim in (tam := tamano_para_precio_de(p))]
        # `todos` (Diego, 25 nov 2026: «el precio es si es más barato que lo que da lo mismo»): por cápsula contra todos
        # los de su mismo ingrediente, del tamaño que sean. En gramos y mililitros sigue la regla del 11 nov.
        cercanos = [] if todos and dim == "pz" else [(p, x) for p, x in con_tam if cantidad / 2 <= x <= cantidad * 2]
        lista = [(p, getattr(p, campo) / x) for p, x in (cercanos or con_tam)]
        if lista and (mejores is None or len(lista) > len(mejores[2])):
            mejores = (dim, s.precio / cantidad, lista)
    return mejores


def _precio_unidad(x: Decimal, dim: str) -> str:
    return f"${x:,.2f} por {NOMBRE_UNIDAD[dim]}" if x >= Decimal("0.1") else f"${x * 100:,.2f} por 100 {dim}"


_SUFIJOS_SITIO = ("tiendaoficial", "oficial", "commx", "com", "mx", "store", "shop", "tienda")


def es_de_la_marca(p: dict, marca: str | None) -> bool:
    """El precio viene de la página o la tienda oficial de la propia marca (Wonu en wonu.mx). No es competencia: es el
    precio que sugiere la marca (Diego, 22 nov 2026: «Wonu.mx al mismo precio» contaba como afuera)."""
    m = re.sub(r"[^a-z0-9]", "", _norm(marca))
    if len(m) < 3:
        return False
    vendedor = re.sub(r"[^a-z0-9]", "", _norm(p.get("vendedor")))
    for suf in _SUFIJOS_SITIO:
        if vendedor.endswith(suf) and len(vendedor) > len(suf):
            vendedor = vendedor[: -len(suf)]
    host = (urlparse(p.get("liga") or "").hostname or "").lower().removeprefix("www.")
    return vendedor == m or (bool(host) and re.sub(r"[^a-z0-9]", "", host.split(".")[0]) == m)


def sin_la_marca(internet: mp.Mercado | None, marca: str | None) -> tuple[mp.Mercado | None, list[dict]]:
    """Separa los precios de la propia marca de los de la competencia."""
    if not internet or not internet.precios:
        return internet, []
    de_marca = [p for p in internet.precios if es_de_la_marca(p, marca)]
    if not de_marca:
        return internet, []
    return mp.Mercado(**{**internet.__dict__, "precios": [p for p in internet.precios if p not in de_marca]}), de_marca


def _marca_texto(de_marca: list[dict]) -> str:
    if not de_marca:
        return ""
    p = min(de_marca, key=lambda p: float(p["precio"]))
    return (f" La marca lo vende en su página ({p.get('vendedor') or 'su sitio'}) en {_pesos(Decimal(str(p['precio'])))}: "
            "es su precio sugerido, no cuenta como competencia.")


def _visto_texto(s: Sujeto) -> str:
    """Lo que capturó Compras en una idea («Precio visto afuera») se enseña pero no cuenta (Diego, 22 nov 2026)."""
    if s.tipo == "propuesta" or not s.mercado:
        return ""
    return " Compras lo vio en " + "; ".join(f"{d} en {_pesos(x)}" for x, d in s.mercado) + " (de referencia, no cuenta)."


def precio_afuera(s: Sujeto, parecidos: list[tuple[Producto, Decimal]], internet: mp.Mercado | None = None,
                  mismo: Producto | None = None, campo: str = "precio_lista_con_impuestos") -> Factor:
    """Mitad «contra afuera»: lo que encontró el radar de precios en internet y las tiendas, sin la página de la propia
    marca; si no encontró nada, lo que reportó el proveedor. Lo que vio Compras en una idea solo se enseña (Diego,
    22 nov 2026). Si ya lo vendemos, nuestro precio contra el mercado."""
    internet, de_marca = sin_la_marca(internet, s.marca)
    f = _precio_afuera(s, parecidos, internet, mismo, campo)
    nota = _marca_texto(de_marca) + _visto_texto(s)
    return dataclasses.replace(f, detalle=f.detalle + nota) if nota else f


def _precio_afuera(s: Sujeto, parecidos: list[tuple[Producto, Decimal]], internet: mp.Mercado | None,
                   mismo: Producto | None, campo: str = "precio_lista_con_impuestos") -> Factor:
    nuestro = getattr(mismo, campo) if mismo else None
    if nuestro:
        internet, fuera = _en_rango(internet, nuestro)
        mercado = [Decimal(str(p["precio"])) for p in (internet.precios if internet else [])]
        visto = s.precio if s.precio and RANGO_PRECIO[0] <= s.precio / nuestro <= RANGO_PRECIO[1] else None
        if visto:
            mercado.append(visto)
        if not mercado:
            return Factor(None, None, f"Ya lo vendemos ({mismo.sku}) a {_pesos(nuestro)}, pero no hay precios del mercado "
                          f"para compararlo.{_fuera_texto(fuera)}")
        med = Decimal(str(median(mercado)))
        ratio = nuestro / med
        donde = [f"{len(internet.precios)} de internet" if internet and internet.precios else "",
                 f"lo que se vio, {_pesos(visto)}" if visto else ""]
        return Factor(_por_precio(ratio), _precio_valor(ratio, "el mercado") + " (nuestro precio)",
                      f"Ya lo vendemos ({mismo.sku}) a {_pesos(nuestro)}. El precio de en medio del mercado es "
                      f"{_pesos(med)} ({' y '.join(x for x in donde if x)}).{_fuera_texto(fuera)}", False,
                      *_precio_explicado(ratio, med, "el precio de en medio del mercado"), meta=med)
    if s.precio is None or s.precio <= 0:
        return Factor(None, None, "Sin datos: falta el precio de venta." if s.tipo == "propuesta"
                      else "Sin datos: falta nuestro precio.")
    que = "Precio sugerido" if s.tipo == "propuesta" else "Nuestro precio"
    nuestros = [p.precio_lista_con_impuestos for p, _ in parecidos if p.precio_lista_con_impuestos]
    contexto = []
    if s.mercado and s.tipo == "propuesta":
        contexto.append(f"el proveedor reportó un precio de en medio de "
                        f"{_pesos(Decimal(str(median([p for p, _ in s.mercado]))))}")
    if nuestros:
        contexto.append(f"nuestros parecidos tienen un precio de lista de en medio de "
                        f"{_pesos(Decimal(str(median(nuestros))))}")
    extra = f" Como referencia, {' y '.join(contexto)}." if contexto else ""

    nuestros_med = Decimal(str(median(nuestros))) if nuestros else None
    # Contra el precio que se vio (es del mismo producto); los parecidos pueden ser otra presentación y antes tiraban
    # precios buenos de la competencia (11 nov 2026)
    internet, fuera = _en_rango(internet, s.precio or nuestros_med)
    extra += _fuera_texto(fuera)
    if internet and internet.precios:
        med = internet.mediana()
        ratio = s.precio / med
        # Quién lo vende y en cuánto (Diego, 11 nov 2026: «información genérica y no específica»)
        lista = "; ".join(f"{p['vendedor']} {_pesos(Decimal(str(p['precio'])))}"
                          for p in sorted(internet.precios, key=lambda p: float(p["precio"]))[:6])
        mas = f" y {len(internet.precios) - 6} más" if len(internet.precios) > 6 else ""
        return Factor(_por_precio(ratio), _precio_valor(ratio, "en internet"),
                      f"{que} {_pesos(s.precio)} contra {_pesos(med)}, el precio de en medio de la competencia en "
                      f"internet: {lista}{mas}.{extra}", False,
                      *_precio_explicado(ratio, med, "el precio de en medio de internet"), meta=med)
    if s.mercado and s.tipo == "propuesta":  # los que reportó el proveedor (en una idea, lo visto ya no cuenta)
        med = Decimal(str(median([p for p, _ in s.mercado])))
        ratio = s.precio / med
        donde = ", ".join(sorted({c for _, c in s.mercado}))
        sin = " El radar de precios no lo encontró en internet." if internet else ""
        quien = "que reportó el proveedor" if s.tipo == "propuesta" else "que se vio"
        return Factor(_por_precio(ratio), _precio_valor(ratio, "la competencia " + quien),
                      f"{'Precio sugerido' if s.tipo == 'propuesta' else 'Nuestro precio'} {_pesos(s.precio)} contra "
                      f"{_pesos(med)}, el precio de en medio de {len(s.mercado)} precio(s) {quien} ({donde}); no está "
                      f"confirmado.{sin}", True,
                      *_precio_explicado(ratio, med, "el precio de en medio de la competencia"), meta=med)
    sin = " El radar de precios no lo encontró en internet." if internet else ""
    return Factor(None, None, f"Sin precios de afuera para compararlo.{sin}{extra}")


def porciones_de(f: fi.Ficha | None) -> int | None:
    """Porciones por envase: las de la ficha o, si dice contenido en gramos y gramos de activo por porción, la división."""
    if not f:
        return None
    if f.porciones:
        return int(f.porciones)
    if f.contenido_cantidad and f.contenido_unidad == "g" and f.activo_g_porcion and f.activo_g_porcion > 0:
        return int(Decimal(f.contenido_cantidad) / Decimal(f.activo_g_porcion)) or None
    return None


def porciones_sujeto(s: Sujeto) -> int | None:
    return porciones_de(s.ficha) or s.porciones


def _por_activo(s: Sujeto, usados: list[Producto], campo: str, todos: bool = False
                ) -> tuple[Decimal, Decimal, list[tuple[Producto, Decimal]], str] | None:
    """Precio por gramo del ingrediente principal, cuando la ficha del nuevo y la de sus parecidos dicen cuánto traen y es
    el mismo ingrediente. (gramos del nuevo, su precio por gramo, parecidos en rango con el suyo, nombre)."""
    f = s.ficha
    gramos = f.activo_total_g() if f else None
    nombre = (f.ingrediente_principal if f else None) or s.ingrediente
    if not gramos or gramos <= 0 or not nombre or not s.precio:
        return None
    suyas = {r for r in raices(palabras(nombre)) if len(r) >= 4}
    propio = s.precio / gramos
    lista = []
    for p in usados:
        g = ficha_de(p)
        total = g.activo_total_g() if g else None
        if not total or total <= 0 or not getattr(p, campo) or not g.ingrediente_principal:
            continue
        if suyas & raices(palabras(g.ingrediente_principal)):
            lista.append((p, getattr(p, campo) / total, total))
    # Como en `_por_unidad`: si hay de tamaño cercano (de la mitad al doble de su ingrediente), solo esos
    # salvo `todos` (25 nov 2026): por gramo de su mismo ingrediente se compara contra todos, del tamaño que sean
    cercanos = [] if todos else [x for x in lista if gramos / 2 <= x[2] <= gramos * 2]
    dentro = [(p, x) for p, x, _ in (cercanos or lista) if todos or RANGO_PRECIO[0] <= propio / x <= RANGO_PRECIO[1]]
    return (gramos, propio, dentro, solo_principal(nombre).lower()) if dentro else None


def mismo_activo(s: Sujeto, parecidos: list[tuple[Producto, Decimal]]) -> list[Producto]:
    """Los parecidos que dan lo mismo: su mismo ingrediente principal en su misma forma (Diego, 25 nov 2026: BDM
    Berberina se comparaba solo contra 4 Health; «el precio es si es más barato que lo que da lo mismo»)."""
    nombre = (s.ficha.ingrediente_principal if s.ficha else None) or s.ingrediente
    if not nombre:
        return []
    suyas = {r for r in raices(palabras(solo_principal(nombre))) if len(r) >= LETRAS_INGREDIENTE} - raices(GENERICAS)
    if not suyas:
        return []
    grupo = GRUPO_FORMATO.get(formato_sujeto(s) or "")
    salida = []
    for p, _ in parecidos:
        g = ficha_de(p)
        otras = raices(palabras(sin_sabor(p.descripcion), g.ingrediente_principal if g else None))
        su_grupo = GRUPO_FORMATO.get(formato_de(p) or "")
        if suyas & otras and not (grupo and su_grupo and grupo != su_grupo):
            salida.append(p)
    return salida


def _lugar(propio: Decimal, xs: list[Decimal]) -> str:
    """«Más barato que 6 de los 7», para que se vea contra todos y no solo contra el de en medio."""
    baratos = sum(1 for x in xs if propio < x)
    if baratos == len(xs):
        return f" Es el más barato de los {len(xs) + 1}."
    if baratos == 0:
        return f" Es el más caro de los {len(xs) + 1}."
    return f" Es más barato que {baratos} de los {len(xs)}."


def _alcanza(con_dato: list, base: list, mismos: list) -> bool:
    """Contra los de su mismo ingrediente, comparar por toma o por gramo solo si al menos la mitad (y 2 o más) lo dicen
    en su ficha: con uno solo no se sabe si es caro o barato (BDM Life, 25 nov 2026: de 7 berberinas solo Altus dice
    sus tomas)."""
    return not mismos or len(con_dato) >= max(2, (len(base) + 1) // 2)


def precio_anaquel(s: Sujeto, parecidos: list[tuple[Producto, Decimal]],
                   campo: str = "precio_lista_con_impuestos") -> Factor:
    """Mitad «contra nuestro anaquel» (Dirección, 22 nov 2026): contra los productos que ya vendemos y con los que va a
    competir, los mismos parecidos de precio cercano que usa la Demanda. Por porción si las dos fichas lo dicen; si no,
    por gramo o mililitro de tamaño parecido; si no, por pieza. `campo`: el precio de los parecidos con que se compara
    (el de membresía para la mitad de membresía, 22 nov 2026)."""
    if s.precio is None or s.precio <= 0:
        return Factor(None, None, "Sin datos: falta nuestro precio.")
    usados = parecidos_para_demanda(s, parecidos, None)
    mismos = mismo_activo(s, parecidos)  # 25 nov 2026: contra todos los que dan lo mismo, sin importar el tamaño
    if len(s.familia) >= MIN_FAMILIA:  # 26 nov 2026: contra su mismo ingrediente y forma del catálogo, no solo los parecidos
        vistos = {p.producto_id for p in mismos}
        mismos = mismos + [p for p in s.familia if p.producto_id not in vistos]
    base = mismos or usados
    que = "Precio sugerido" if s.tipo == "propuesta" else "Nuestro precio"
    # Diego, 25 nov 2026: «debe ser cuánto alcanza cada presentación»: primero el costo por toma (una berberina se toma
    # de 1 cápsula y otra de 2), luego por gramo de su ingrediente y al final por cápsula
    porciones = porciones_sujeto(s)
    toma = "toma" if GRUPO_FORMATO.get(formato_sujeto(s) or "") in ("solido", "gomita") else "porción"
    if porciones:
        lista = [(p, getattr(p, campo) / n) for p in base
                 if getattr(p, campo) and (n := porciones_de(ficha_de(p)))]
        propio = s.precio / porciones
        # Con los de su mismo ingrediente no se quita ninguno por precio: son lo que da lo mismo (25 nov 2026)
        dentro = [(p, x) for p, x in lista if mismos or RANGO_PRECIO[0] <= propio / x <= RANGO_PRECIO[1]]
        if dentro and _alcanza(dentro, base, mismos):
            med = Decimal(str(median([x for _, x in dentro])))
            ratio = propio / med
            contra = "; ".join(f"{con_marca(p)} {_pesos(getattr(p, campo))} ({_pesos(x)} por {toma})"
                               for p, x in sorted(dentro, key=lambda d: d[1]))
            return Factor(_por_precio(ratio), _precio_valor(ratio, f"nuestro anaquel, por {toma}"),
                          f"{que} {_pesos(s.precio)} por {porciones} {toma + 's' if toma == 'toma' else 'porciones'}: sale a {_pesos(propio)} por {toma}. "
                          f"Nuestros parecidos salen, en medio, a {_pesos(med)} por {toma}: {contra}."
                          f"{_lugar(propio, [x for _, x in dentro])}", False,
                          *_precio_explicado(ratio, med * porciones, f"nuestros parecidos por {toma}"),
                          meta=(med * porciones).quantize(Decimal("0.01")),
                          por_unidad={"propio": float(propio), "medio": float(med), "unidad": toma})
    if (activo := _por_activo(s, base, campo, todos=bool(mismos))) and _alcanza(activo[2], base, mismos):  # 25 nov 2026 (BDM Life): por gramo de su ingrediente, si las fichas lo dicen
        gramos, propio, dentro, nombre = activo
        med = Decimal(str(median([x for _, x in dentro])))
        ratio = propio / med
        contra = "; ".join(f"{con_marca(p)} {_pesos(getattr(p, campo))} ({_pesos(x)} por gramo de {nombre})"
                           for p, x in sorted(dentro, key=lambda d: d[1]))
        return Factor(_por_precio(ratio), _precio_valor(ratio, f"nuestro anaquel, por gramo de {nombre}"),
                      f"{que} {_pesos(s.precio)} con {_n(gramos)} g de {nombre}: sale a {_pesos(propio)} por gramo. "
                      f"{_lugar(propio, [x for _, x in dentro])} Nuestros parecidos salen, en medio, a {_pesos(med)} por gramo: "
                      f"{contra}.", False,
                      *_precio_explicado(ratio, med * gramos, f"nuestros parecidos por gramo de {nombre}"),
                      meta=(med * gramos).quantize(Decimal("0.01")),
                      por_unidad={"propio": float(propio), "medio": float(med), "unidad": f"gramo de {nombre}"})
    if unidad := _por_unidad(s, [(p, Decimal(0)) for p in base], campo, todos=bool(mismos)):
        dim, propio, lista = unidad
        en_rango = [(p, x) for p, x in lista if mismos or RANGO_PRECIO[0] <= propio / x <= RANGO_PRECIO[1]]
        if en_rango:
            med = Decimal(str(median([x for _, x in en_rango])))
            ratio = propio / med
            cantidad = tamano(s.contenido, s.nombre, s.descripcion)[dim]
            pieza = {"capsula": "cápsula", "tableta": "tableta", "gomita": "gomita"}.get(formato_sujeto(s) or "")
            un = pieza if dim == "pz" and pieza else NOMBRE_UNIDAD[dim]  # «por cápsula», no «por pieza» (25 nov 2026)
            contra = "; ".join(f"{con_marca(p)} {_pesos(getattr(p, campo))} ({_pesos(x) if pieza and dim == 'pz' else _precio_unidad(x, dim)}{' por ' + un if pieza and dim == 'pz' else ''})"
                               for p, x in sorted(en_rango, key=lambda d: d[1]))
            aviso, toma_info = "", None
            if dim == "pz" and pieza and porciones and cantidad / porciones > 1:
                # Por cápsula sin saber cuántas por toma llevan los demás (Diego, 25 nov 2026: «puede que tengas una
                # berberina que tomes una cápsula y ya, pero esta ocupas dos»): se dice la otra cuenta y queda provisional
                por_toma = s.precio / porciones
                otra = float(por_toma / med - 1) * 100
                aviso = (f" Ojo: se toma de {_n(cantidad / porciones)} {un}s ({porciones} tomas, {_pesos(por_toma)} por "
                         f"toma) y no sabemos cuántas por toma llevan los demás; si se toman de 1, sale "
                         f"{abs(otra):.0f} % más {'caro' if otra > 0 else 'barato'} por toma. Falta la toma en sus fichas.")
                toma_info = {"piezas": float(cantidad / porciones), "tomas": porciones, "por_toma": float(por_toma),
                             "si_de_1_pct": round(otra)}
            return Factor(_por_precio(ratio), _precio_valor(ratio, f"nuestro anaquel, por {un}"),
                          f"{que} {_pesos(s.precio)} por {_n(cantidad)} {un + 's' if un != NOMBRE_UNIDAD[dim] else dim}: sale a "
                          f"{_pesos(propio) + ' por ' + un if un != NOMBRE_UNIDAD[dim] else _precio_unidad(propio, dim)}."
                          f"{_lugar(propio, [x for _, x in en_rango])}{aviso} "  # antes de la lista: el detalle se guarda en 1,000 letras
                          f"Nuestros parecidos salen, en medio, a "
                          f"{_pesos(med) + ' por ' + un if un != NOMBRE_UNIDAD[dim] else _precio_unidad(med, dim)}: {contra}."
                          , bool(aviso),
                          *_precio_explicado(ratio, med * cantidad, f"nuestros parecidos por {un}"),
                          meta=(med * cantidad).quantize(Decimal("0.01")),
                          por_unidad={"propio": float(propio), "medio": float(med),
                                      "unidad": un if un != NOMBRE_UNIDAD[dim] else dim, "toma": toma_info})
    precios = [(p, getattr(p, campo)) for p in usados if getattr(p, campo)]
    if not precios:
        return Factor(None, None, "Sin datos: no hay productos parecidos con precio en nuestro catálogo.")
    comparables = [(p, x) for p, x in precios if RANGO_PRECIO[0] <= s.precio / x <= RANGO_PRECIO[1]]
    if not comparables:
        xs = [x for _, x in precios]
        return Factor(None, None, f"Sin datos: nuestros parecidos cuestan muy distinto ({_pesos(min(xs))} a "
                      f"{_pesos(max(xs))} contra {_pesos(s.precio)}); no parecen la misma presentación.")
    med = Decimal(str(median([x for _, x in comparables])))
    ratio = s.precio / med
    contra = "; ".join(f"{con_marca(p)} {_pesos(x)}" for p, x in comparables[:4])
    return Factor(_por_precio(ratio), _precio_valor(ratio, "nuestro anaquel"),
                  f"{que} {_pesos(s.precio)} contra {_pesos(med)}, el precio de en medio de nuestros parecidos: {contra}.",
                  False, *_precio_explicado(ratio, med, "nuestros parecidos"), meta=med)


def f_precio(s: Sujeto, parecidos: list[tuple[Producto, Decimal]], internet: mp.Mercado | None = None,
             mismo: Producto | None = None) -> Factor:
    """Precio en dos mitades (Dirección, 22 nov 2026): contra afuera y contra nuestro anaquel, cada una con la misma
    regla (igual vale 75, ±1 por cada 1 %); la calificación es el promedio. Si falta una, cuenta la otra sola. Si ya lo
    vendemos, solo contra afuera (el anaquel es él mismo)."""
    afuera = precio_afuera(s, parecidos, internet, mismo)
    anaquel = precio_anaquel(s, parecidos) if not mismo else None
    lista = juntar_precio(afuera, anaquel, s.precio)
    return con_membresia(lista, lado_membresia(s, parecidos, internet, mismo))


def precios_por_lado(s: Sujeto, parecidos: list[tuple[Producto, Decimal]], internet: mp.Mercado | None = None,
                     mismo: Producto | None = None) -> dict[str, Factor]:
    """Los dos temas del Precio (Diego, 25 nov 2026): contra nuestro anaquel y contra afuera, cada uno mitad precio de
    lista y mitad precio de membresía. Sin datos de un lado, ese tema no cuenta."""
    afuera = precio_afuera(s, parecidos, internet, mismo)
    anaquel = precio_anaquel(s, parecidos) if not mismo else None
    m = lado_membresia(s, parecidos, internet, mismo)

    def lado(lista: Factor, de_membresia: Factor | None) -> Factor:
        junto = con_membresia(lista, LadoMembresia(m.precio, m.afuera, m.anaquel, de_membresia)
                              if m and de_membresia is not None else None)
        if junto.puntaje is not None and junto.puntaje < 60 and s.precio and lista.meta:
            junto = dataclasses.replace(junto, competir=_precio_para(s.precio, [lista.meta], 59))
        return junto

    salida = {"precio_afuera": lado(afuera, m.afuera if m else None)}
    if salida["precio_afuera"].puntaje is None:  # la tarjeta decía solo «Sin datos» (BDM Life, 25 nov 2026)
        salida["precio_afuera"] = dataclasses.replace(
            salida["precio_afuera"], valor="No cuenta: no se encontró a la venta afuera; su peso se reparte")
    if anaquel is None:
        salida["precio_anaquel"] = Factor(None, "Ya lo vendemos", "Ya vendemos este mismo producto: el anaquel es él "
                                          "mismo, así que solo cuenta el precio contra afuera.")
    else:
        salida["precio_anaquel"] = lado(anaquel, m.anaquel if m else None)
    return salida


MEMBRESIA = "precio_membresia_con_impuestos"


@dataclass
class LadoMembresia:
    precio: Decimal
    afuera: Factor
    anaquel: Factor | None
    junto: Factor


def lado_membresia(s: Sujeto, parecidos: list[tuple[Producto, Decimal]], internet: mp.Mercado | None = None,
                   mismo: Producto | None = None) -> LadoMembresia | None:
    """El Precio con el precio de membresía (Diego, 22 nov 2026: «hay que considerar el precio de lista y el precio de
    membresía»): contra afuera y contra el precio de membresía de nuestros parecidos, con las mismas reglas."""
    if mismo:
        precio = getattr(mismo, MEMBRESIA)
        if not precio:
            return None
        afuera = precio_afuera(s, parecidos, internet, mismo, MEMBRESIA)
        return LadoMembresia(precio, afuera, None, juntar_precio(afuera, None, precio))
    if not s.precio_membresia:
        return None
    sm = dataclasses.replace(s, precio=s.precio_membresia, mercado=[])
    afuera = precio_afuera(sm, parecidos, internet, None)
    anaquel = precio_anaquel(sm, parecidos, MEMBRESIA)
    return LadoMembresia(s.precio_membresia, afuera, anaquel, juntar_precio(afuera, anaquel, s.precio_membresia))


def con_membresia(lista: Factor, m: LadoMembresia | None) -> Factor:
    """Mitad precio de lista y mitad precio de membresía: hoy no se sabe cuánto se vende a socios (la venta de SMNBI no
    los distingue). Si falta uno, cuenta el otro solo."""
    if m is None or m.junto is None or m.junto.puntaje is None:
        return lista
    b = m.junto.puntaje
    resumen = f"Con precio de membresía ({_pesos(m.precio)}): {m.junto.valor[0].lower()}{m.junto.valor[1:]} ({b})."
    if lista.puntaje is None:
        return dataclasses.replace(m.junto, detalle=f"{resumen} Con precio de lista: {lista.detalle}")
    a = lista.puntaje
    final = round((a + b) / 2)
    pct = 75 - final
    nivel = "Buen precio" if pct <= -5 else "En precio" if pct <= 5 else "Algo caro" if pct <= 15 else "Caro"
    sin_nivel = (lambda v: v.split(": ", 1)[1] if ": " in v else v)
    return dataclasses.replace(
        lista, puntaje=final,
        valor=f"{nivel}: con precio de lista {sin_nivel(lista.valor)}; con membresía {sin_nivel(m.junto.valor)}",
        detalle=f"{resumen} Con precio de lista: {lista.detalle}",
        calculo=(f"Precio = mitad con precio de lista y mitad con precio de membresía (no se sabe cuánto se vende a "
                 f"socios). Con precio de lista {a}: {lista.calculo} Con membresía {b}. ({a} + {b}) / 2 = {final}."))


def _precio_para(precio: Decimal, refs: list[Decimal], mas_de: int = 80) -> Decimal | None:
    """El precio más alto (sin pasar del de hoy) con el que el promedio de las mitades sale arriba de `mas_de` (cada
    mitad topa en 0 y 100, así que se busca en lugar de despejar)."""
    refs = [r for r in refs if r]
    if not refs:
        return None

    def calif(x: Decimal) -> int:
        return round(sum(_por_precio(x / r) for r in refs) / len(refs))

    bajo, alto = Decimal(0), precio
    if calif(alto) > mas_de:
        return None
    for _ in range(40):
        medio = (bajo + alto) / 2
        bajo, alto = (medio, alto) if calif(medio) > mas_de else (bajo, medio)
    return bajo.quantize(Decimal("0.01"), rounding=ROUND_DOWN) if bajo > 0 else None


def _mejora_promedio(precio: Decimal | None, afuera: Factor, anaquel: Factor, final: int) -> str | None:
    """Qué lo subiría, con el precio que de verdad lleva el promedio a verde (Wonu 22 nov 2026: decía $563.06, el que
    pide la mitad de afuera sola; con ese precio el promedio solo llegaba a 41)."""
    if final > 80 or not precio or not afuera.meta or not anaquel.meta:
        return afuera.mejora or anaquel.mejora
    meta = _precio_para(precio, [afuera.meta, anaquel.meta])
    if meta is None:
        return afuera.mejora or anaquel.mejora
    baja = (1 - meta / precio) * 100
    return (f"Para que Precio salga arriba de 80 tendría que venderse en {_pesos(meta)} o menos ({_n(baja)} % menos "
            f"que hoy): así queda {_por_precio(meta / afuera.meta)} contra afuera y {_por_precio(meta / anaquel.meta)} "
            "contra nuestro anaquel.")


def juntar_precio(afuera: Factor, anaquel: Factor | None, precio: Decimal | None = None) -> Factor:
    f = _juntar_precio(afuera, anaquel, precio)
    if f.puntaje is not None and f.puntaje < 60 and precio:
        refs = [x.meta for x in (afuera, anaquel) if x and x.puntaje is not None and x.meta]
        f.competir = _precio_para(precio, refs, 59)
    return f


def _juntar_precio(afuera: Factor, anaquel: Factor | None, precio: Decimal | None) -> Factor:
    a, b = afuera.puntaje, anaquel.puntaje if anaquel else None
    if a is None and b is None:
        detalle = afuera.detalle + (f" Contra nuestro anaquel: {anaquel.detalle}" if anaquel else "")
        return Factor(None, None, detalle)
    if b is None:
        nota = f" Contra nuestro anaquel: {anaquel.detalle[0].lower()}{anaquel.detalle[1:]}" if anaquel else ""
        return Factor(a, afuera.valor, afuera.detalle + nota, afuera.provisional,
                      (afuera.calculo or "") + (" Solo cuenta afuera: no hay con qué compararlo en nuestro anaquel." if anaquel else ""),
                      afuera.mejora, afuera.meta)
    if a is None:
        return Factor(b, anaquel.valor, f"{anaquel.detalle} Afuera: {afuera.detalle[0].lower()}{afuera.detalle[1:]}",
                      anaquel.provisional, (anaquel.calculo or "") + " Solo cuenta nuestro anaquel: no hay precios de afuera.",
                      anaquel.mejora, anaquel.meta)
    final = round((a + b) / 2)
    pct = 75 - final  # el nivel del promedio, con los mismos cortes de cada mitad
    nivel = "Buen precio" if pct <= -5 else "En precio" if pct <= 5 else "Algo caro" if pct <= 15 else "Caro"

    def sin_nivel(v: str) -> str:
        return v.split(": ", 1)[1] if ": " in v else v

    return Factor(final, f"{nivel}: {sin_nivel(afuera.valor)}; {sin_nivel(anaquel.valor)}",
                  f"Contra afuera: {afuera.detalle} Contra nuestro anaquel: {anaquel.detalle}",
                  afuera.provisional or anaquel.provisional,
                  f"Precio = promedio de dos mitades. Contra afuera {a}: {afuera.calculo} Contra nuestro anaquel {b}: "
                  f"{anaquel.calculo} ({a} + {b}) / 2 = {final}.",
                  _mejora_promedio(precio, afuera, anaquel, final), afuera.meta)


def datos_para_politicas(s: Sujeto, e: ProductoEvaluacion, factores: dict[str, Factor],
                         internet: mp.Mercado | None) -> dict:
    """Lo que sabemos del producto, para que la IA lo revise contra las políticas sin suponer nada más."""
    return {
        "tipo": "propuesta de proveedor" if s.tipo == "propuesta" else "idea de Compras", "nombre": s.nombre,
        "marca": s.marca, "departamento": s.departamento, "subcategoria": e.subcategoria, "descripcion": s.descripcion,
        "ingrediente": s.ingrediente, "forma": s.forma, "contenido": s.contenido, "codigo_barras": s.codigo_barras,
        "precio_venta_con_impuestos": s.precio, "margen_pct": s.margen, "costo_sin_iva": s.costo,
        "registro_sanitario": s.registro_sanitario if s.tipo == "propuesta" else None,
        "ya_es_proveedor_smn": s.proveedor_smn, "inscrito_gs1": s.inscrito_gs1,
        "mediana_precio_internet": internet.mediana() if internet else None,
        "factores": {NOMBRES[f]: {"puntaje": x.puntaje, "dato": x.valor, "detalle": x.detalle} for f, x in factores.items()},
        "piezas_por_caja": s.piezas_caja,
        "venta_esperada": venta_esperada(e),
    }


def venta_esperada(e: ProductoEvaluacion) -> dict | None:
    """Piezas por tienda al mes que se esperan: el pronóstico a 12 semanas (rango medio) o, sin él, lo que venden los
    parecidos. Para que las reglas de piezas las calcule el sistema y no la IA."""
    try:
        p = pn.Pronostico.de_json(e.pronostico)
    except (ValueError, TypeError, KeyError):
        p = None
    if p and (r := p.rango(12)):
        return {"piezas_por_tienda_mes": r[1], "de": "el pronóstico a 12 semanas"}
    if p and p.base:
        return {"piezas_por_tienda_mes": round(p.base, 2), "de": p.base_de or "sus parecidos"}
    return None


# Para comparar versiones con los mismos datos de internet (v0.5.4): la comparación fija aquí el mercado y la
# investigación que ya tenía guardados la evaluación, y así no sale a internet ni cambia por una búsqueda nueva.
MERCADO_FIJO: ContextVar[tuple[str | None, str | None] | None] = ContextVar("radar_mercado_fijo", default=None)


def mercado_de(bd: Session, e: ProductoEvaluacion, s: Sujeto) -> mp.Mercado | None:
    """Busca el producto en internet, o reusa lo que encontró una evaluación de la última semana."""
    if (fijo := MERCADO_FIJO.get()) is not None:
        return mp.Mercado.de_json(fijo[0]) if fijo[0] else None
    if not configuracion().radar_productos_buscar_mercado:
        return None
    nombre = s.nombre if not s.contenido or _norm(s.contenido) in _norm(s.nombre) else f"{s.nombre} {s.contenido}"
    clave = mp.clave_de(nombre, s.marca, s.codigo_barras)
    q = select(ProductoEvaluacion.mercado).where(ProductoEvaluacion.evaluacion_id != e.evaluacion_id,
                                                 ProductoEvaluacion.mercado.is_not(None))
    q = q.where(ProductoEvaluacion.propuesta_id == e.propuesta_id) if e.propuesta_id else q.where(ProductoEvaluacion.idea_id == e.idea_id)
    if (previo := mp.Mercado.de_json(bd.scalar(q.order_by(ProductoEvaluacion.evaluacion_id.desc())))) and previo.vigente(clave):
        return previo
    referencia = f"propuesta {e.propuesta_id}" if e.propuesta_id else f"idea {e.idea_id}"
    return mp.buscar(bd, nombre, s.marca, s.codigo_barras, referencia)


MIN_FAMILIA = 3
NOMBRE_GRUPO = {"polvo": "en polvo", "solido": "en cápsulas o tabletas", "gomita": "en gomitas", "liquido": "líquidos",
                "topico": "en crema"}


def familia_para_demanda(s: Sujeto, activos: list[Producto]) -> tuple[str, list[Producto]] | None:
    """Con quién se mide la Demanda de una idea que no vendemos (Diego, 26 nov 2026, Colágeno + Inositol B-FIT $749:
    salía «se vende poco» porque solo se comparaba con 3 o 4 parecidos de precio cercano, unas creatinas con colágeno
    que casi no se venden, y nunca con los colágenos en polvo que sí vendemos). Son todos los productos con su
    ingrediente principal en el nombre y de su misma forma (polvo con polvo, cápsulas con tabletas), sin filtrar por
    precio: si es caro, eso lo castiga el factor Precio, no la Demanda. (cómo se llaman, productos) o None."""
    suyo = del_ingrediente(s, activos)
    if not suyo:
        return None
    raiz, ids = suyo
    prods = [p for p in activos if p.producto_id in ids]
    palabra = next((w for w in sorted(palabras(sin_sabor(s.nombre), s.ingrediente)) if w[:6] == raiz), raiz)
    nombre = palabra
    grupo = GRUPO_FORMATO.get(formato_sujeto(s) or "")
    if grupo:
        misma = [p for p in prods if GRUPO_FORMATO.get(formato(p.descripcion) or "") == grupo]
        if len(misma) >= MIN_FAMILIA:
            prods, nombre = misma, f"{palabra} {NOMBRE_GRUPO.get(grupo, '')}".strip()
    return (nombre, prods) if len(prods) >= MIN_FAMILIA else None


MAX_FAMILIA_PRECIO = 15


def poner_familia(bd: Session, s: Sujeto) -> Sujeto:
    """Llena `s.familia` con los de su mismo ingrediente y forma, los más cercanos en tamaño (hasta 15), para comparar
    el precio por gramo contra ellos aunque la IA no los haya dejado entre sus parecidos (Diego, 26 nov 2026: el
    Colágeno + Inositol salía «Precio contra anaquel: sin datos» con más de 200 colágenos en el catálogo)."""
    try:
        fam = familia_para_demanda(s, catalogo_activo(bd))
    except Exception:  # noqa: BLE001 - sin familia se compara como antes
        fam = None
    grupo = GRUPO_FORMATO.get(formato_sujeto(s) or "")
    if not fam or not grupo:
        return s
    prods = [p for p in fam[1] if GRUPO_FORMATO.get(formato(p.descripcion) or "") == grupo]
    if len(prods) < MIN_FAMILIA:
        return s
    suyo = tamano(s.contenido, s.nombre, s.descripcion)
    dim = next((d for d in ("g", "ml", "pz") if d in suyo), None)
    if dim:
        def distancia(p: Producto) -> float:
            t = tamano(p.descripcion).get(dim)
            return abs(math.log(float(t) / float(suyo[dim]))) if t else 99.0
        prods = sorted(prods, key=distancia)
    s.familia = prods[:MAX_FAMILIA_PRECIO]
    return s


def skus_para_pronostico(s: Sujeto, parecidos: list[tuple[Producto, Decimal]], mismo: Producto | None) -> list[str]:
    """Los mismos parecidos que usa Demanda: de precio cercano si los hay; si ya lo vendemos, ese mismo."""
    return [p.sku for p in parecidos_para_demanda(s, parecidos, mismo)]


def investigacion_de(bd: Session, e: ProductoEvaluacion, s: Sujeto) -> inv_mod.Investigacion | None:
    """Investiga afuera con Google y la IA local, o reusa lo de una evaluación de la última semana (17 nov 2026)."""
    if (fijo := MERCADO_FIJO.get()) is not None:
        return inv_mod.Investigacion.de_json(fijo[1]) if fijo[1] else None
    if not configuracion().radar_productos_buscar_mercado:
        return None
    clave = inv_mod.clave_de(s.nombre, s.marca, s.contenido)
    q = select(ProductoEvaluacion.investigacion).where(ProductoEvaluacion.evaluacion_id != e.evaluacion_id,
                                                       ProductoEvaluacion.investigacion.is_not(None))
    q = q.where(ProductoEvaluacion.propuesta_id == e.propuesta_id) if e.propuesta_id else q.where(ProductoEvaluacion.idea_id == e.idea_id)
    try:
        if (previo := inv_mod.Investigacion.de_json(bd.scalar(q.order_by(ProductoEvaluacion.evaluacion_id.desc())))) \
                and previo.vigente(clave):
            return previo
    except (ValueError, TypeError):
        pass
    referencia = f"propuesta {e.propuesta_id}" if e.propuesta_id else f"idea {e.idea_id}"
    try:
        return inv_mod.investigar(bd, nombre=s.nombre, marca=s.marca, contenido=s.contenido, ingrediente=s.ingrediente,
                                  forma=s.forma, codigo_barras=s.codigo_barras, referencia=referencia)
    except Exception as ex:  # noqa: BLE001 - investigar nunca detiene la evaluación
        log.warning("Radar de productos: no se pudo investigar afuera %s: %s", referencia, ex)
        return None


def con_web(internet: mp.Mercado | None, inv: inv_mod.Investigacion | None) -> mp.Mercado | None:
    """Suma a los precios de Google Shopping y las tiendas clave los del mismo producto que la IA local encontró en
    páginas de internet (con cita de la página)."""
    extra = inv.precios_mismo() if inv else []
    if not extra:
        return internet
    m = internet or mp.Mercado(buscado_en=inv.buscado_en, clave="")
    vistos = {(p["vendedor"], p["precio"]) for p in m.precios}
    nuevos = [p for p in extra if (p["vendedor"], p["precio"]) not in vistos]
    if nuevos:
        m.precios = [*m.precios, *nuevos][:mp.MAX_PRECIOS + len(nuevos)]
        m.notas = [*m.notas, f"{len(nuevos)} precio(s) más de páginas de internet que leyó la IA local."]
    return m


INSTRUCCIONES_TENDENCIA = """Eres analista de Compras de una cadena de tiendas naturistas en México.
Te doy un producto nuevo y señales del radar de tendencias. Elige SOLO las señales que hablan de este producto, de su
ingrediente principal o del mismo uso (por ejemplo, control de peso para un quemador de grasa). Una señal general de
bienestar, o de otro uso (sueño, belleza, salud femenina), NO cuenta. No basta con que compartan una palabra.
Si ninguna, lista vacía.
Contesta solo JSON: {"senales": [12, 30]}"""
MAX_SENALES_IA = 40


def _senales_ia(bd: Session, s: Sujeto, senales: list[RadarSenal], subcategoria: str | None = None) -> list[RadarSenal] | None:
    """Las señales que la IA dice que hablan del producto; None si la IA no contestó."""
    clave = s.texto() | palabras(s.forma)
    candidatas = sorted(senales, key=lambda x: (-len(clave & palabras(x.titulo, x.descripcion)),
                                                -NIVEL_SENAL.get(x.nivel, 50)))[:MAX_SENALES_IA]
    mensaje = json.dumps({"producto": {"nombre": s.nombre, "marca": s.marca, "ingrediente": s.ingrediente,
                                       "forma": s.forma, "descripcion": s.descripcion, "subcategoria": subcategoria},
                          "senales": [{"id": x.senal_id, "titulo": x.titulo, "descripcion": (x.descripcion or "")[:300]}
                                      for x in candidatas]}, ensure_ascii=False)
    try:
        r = puerta.ejecutar(bd, TAREA_TENDENCIA, usuario_id=None, instrucciones=INSTRUCCIONES_TENDENCIA, mensaje=mensaje,
                            max_tokens=300, esfuerzo="low", formato="json",
                            contexto=puerta.ventana(INSTRUCCIONES_TENDENCIA, mensaje, salida=300))
        ids = {int(x) for x in json.loads(r.texto[r.texto.find("{"):r.texto.rfind("}") + 1]).get("senales") or []}
    except (puerta.ErrorIA, ValueError, TypeError, AttributeError) as e:
        log.info("Radar de productos: la IA no eligió señales para «%s»: %s", s.nombre, e)
        return None
    return [x for x in candidatas if x.senal_id in ids]


def f_tendencia(bd: Session, s: Sujeto, hoy: date, subcategoria: str | None = None) -> Factor:
    senales = bd.scalars(select(RadarSenal).where(RadarSenal.estado != "descartada",
                                                  RadarSenal.ultima_vez >= hoy - timedelta(days=DIAS_SENALES))).all()
    if not senales:
        return Factor(None, None, "Sin datos: el radar de tendencias no tiene señales de los últimos 6 meses.")
    con = _senales_ia(bd, s, list(senales), subcategoria)
    como = "La IA eligió las señales que hablan del producto."
    if con:
        # La IA a veces elige una señal que no habla del producto (13 nov 2026: Wonu Creatina + Inositol sacó 100 por
        # «Menos azúcar y más nutrición… snacks»). Solo cuenta si comparte una palabra propia del producto.
        suyas = raices(palabras(s.ingrediente, s.nombre, subcategoria) - GENERICAS - presentacion(s.marca))
        con = [x for x in con if suyas & raices(palabras(x.titulo, x.descripcion))]
    if con is None:
        clave = palabras(s.ingrediente) or palabras(s.nombre)
        con = [x for x in senales if clave & palabras(x.titulo, x.descripcion)]
        como = "Sin IA: se tomaron las señales con palabras en común."
    if not con:
        return Factor(None, SIN_SENAL, f"Ninguna de las {len(senales)} señales del radar de tendencias de los "
                      f"últimos 6 meses habla de este producto o su ingrediente; no cuenta ni baja la confianza. {como}", True,
                      CALC_TENDENCIA, "Subiría si el radar de tendencias detecta que se habla de este producto o de su "
                      "ingrediente (una señal media da 80; una alta, 100).")
    mejor = max(con, key=lambda x: (NIVEL_SENAL.get(x.nivel, 50), x.veces_reportada))
    puntaje = NIVEL_SENAL.get(mejor.nivel, 50)
    mejora = None if puntaje > 80 else ("Para que este factor salga arriba de 80 la señal tendría que ser alta: que "
                                        "el tema se vea más seguido y en más fuentes.")
    # Con su nombre (Diego, 22 nov 2026: «una señal en internet; la más fuerte, media» no decía cuál)
    return Factor(puntaje, f"Señal {mejor.nivel.lower()} en el radar de tendencias: «{mejor.titulo}»"
                  + (f" y {len(con) - 1} más" if len(con) > 1 else ""),
                  f"Señal más fuerte: «{mejor.titulo}» ({mejor.tipo}, nivel {mejor.nivel.lower()}, vista por última vez "
                  f"el {mejor.ultima_vez:%d/%m/%Y}). {como}", True, CALC_TENDENCIA, mejora)

def _tamano_tipico(bd: Session) -> float:
    """Tamaño de la subcategoría en la que está el producto típico del catálogo: la mediana por producto, no por
    subcategoría (hay muchas subcategorías de 1 a 3 productos y casi todo se vende en las grandes; calibración del
    27 oct)."""
    conteos = bd.scalars(select(func.count()).select_from(Producto).where(
        Producto.activo == true(), Producto.subcategoria.is_not(None)).group_by(Producto.subcategoria)).all()
    por_producto = sorted(c for c in conteos for _ in range(c))
    return float(median(por_producto)) if por_producto else 0.0


def misma_linea(s: Sujeto, parecidos: list[tuple[Producto, Decimal]]) -> list[Producto]:
    """Los parecidos muy cercanos (similitud 0.8 o más) de la misma marca. Antes bastaba la similitud y restaba por
    productos de otra marca (Wonu 22 nov 2026: UP Creatina Colágeno Inositol le quitaba 5 a Wonu)."""
    marca = re.sub(r"[^a-z0-9]", "", _norm(s.marca))
    if not marca:
        return []
    return [p for p, sim in parecidos if sim >= Decimal("0.8") and re.sub(r"[^a-z0-9]", "", _norm(p.marca)) == marca]


def f_categoria(bd: Session, s: Sujeto, subcategoria: str | None, parecidos: list[tuple[Producto, Decimal]],
                v: rr.Ventana | None = None, mismo: Producto | None = None) -> Factor:
    if mismo:
        venta = rr.venta_por_sku(bd, v, [mismo.sku]) if v else {}
        al_mes = f", con {venta[mismo.sku].al_mes:,.0f} piezas al mes" if mismo.sku in venta else ""
        return Factor(10, "Ya lo vendemos",
                      f"Este mismo producto ya está en el catálogo: {mismo.sku} {mismo.descripcion}{al_mes}. No llena un "
                      "hueco del surtido; solo tendría sentido como otro proveedor o una mejor condición.", True,
                      "Si ya lo vendemos, saca 10: no aporta nada nuevo al surtido.")
    if subcategoria:
        n = bd.scalar(select(func.count()).select_from(Producto).where(
            Producto.activo == true(), Producto.subcategoria == subcategoria))
        tipica = _tamano_tipico(bd)
        r = n / tipica if tipica else 1
        # Contra el tamaño típico de una subcategoría del catálogo (calibración del 27 oct: las reales casi siempre
        # pasan de 15 productos y con la escala fija todo salía en 15-25)
        # Recalibración del 9 nov 2026: una subcategoría de tamaño típico vale 80 (antes 70)
        puntaje = 90 if r <= 0.25 else 85 if r <= 0.5 else 80 if r <= 1 else 75 if r <= 2 else 65 if r <= 4 else 55
        detalle = (f"En «{subcategoria.capitalize()}» tenemos {n} producto{'' if n == 1 else 's'} activo"
                   f"{'' if n == 1 else 's'}; una subcategoría normal tiene unos {tipica:.0f}.")
        calculo = (f"Compara cuántos productos hay en su subcategoría contra una típica ({tipica:.0f}): la cuarta parte o "
                   "menos = 90, la mitad o menos = 85, lo mismo o menos = 80, hasta el doble = 75, hasta 4 veces = 65, "
                   f"más = 55. Aquí hay {n}: {puntaje}.")
    else:
        n = len([1 for _, sim in parecidos if sim >= Decimal("0.3")])
        puntaje = 90 if n == 0 else 75 if n <= 3 else 65 if n <= 7 else 55
        detalle = f"Tenemos {n} producto(s) muy parecido(s); todavía no tiene subcategoría confirmada."
        calculo = (f"Sin subcategoría, cuenta los productos muy parecidos: ninguno = 90, hasta 3 = 75, hasta 7 = 65, más "
                   f"= 55. Aquí hay {n}: {puntaje}.")
    # Inventario: más de 180 días de existencia resta 5 (la subcategoría ya está llena); menos de 45 suma 5
    if subcategoria and v and (inv := rr.dias_inventario(bd, v, subcategoria)):
        dias, corte, con_existencia = inv
        if dias > 180:
            puntaje -= 5
            calculo += f" Resta 5 porque la subcategoría tiene inventario para más de 180 días ({dias:,.0f})."
        elif dias < 45:
            puntaje += 5
            calculo += f" Suma 5 porque la subcategoría tiene inventario para menos de 45 días ({dias:,.0f})."
        detalle += (f" Lo que hay en tiendas de esa subcategoría alcanza para {dias:,.0f} días de venta "
                    f"(inventario del {corte:%d/%m/%Y}).")
    iguales = misma_linea(s, parecidos)
    cercanos = [p for p, sim in parecidos if sim >= Decimal("0.5")]
    venta = rr.venta_por_sku(bd, v, [p.sku for p in set(cercanos) | set(iguales)]) if v and (cercanos or iguales) else {}
    if iguales:
        detalle += " Ya vendemos uno de la misma marca y línea: " + ", ".join(f"{p.sku} {con_marca(p)}" for p in iguales[:3]) + "."
        if con_venta := [p for p in iguales if p.sku in venta]:
            puntaje -= 5
            calculo += f" Resta 5 porque ya vendemos uno de la misma marca y línea ({con_marca(con_venta[0])})."
    if canibal := [p for p in cercanos if p.sku in venta]:
        detalle += " Podría quitarle venta a: " + ", ".join(
            f"{p.sku} {p.descripcion} ({venta[p.sku].al_mes:,.0f} piezas al mes)" for p in canibal[:3]) + "."
    final = _acotar(puntaje)
    nivel = ("Hay hueco en el surtido" if final >= 85 else "Surtido normal" if final >= 75
             else "Ya tenemos bastantes" if final >= 60 else "Surtido lleno")
    cuantos = f"{n} producto{'' if n == 1 else 's'}"
    valor = (f"{nivel}: {cuantos} en su subcategoría, una normal tiene {tipica:.0f}" if subcategoria
             else f"{nivel}: {cuantos} muy parecido{'' if n == 1 else 's'} en el catálogo")
    return Factor(final, valor, detalle, True,
                  f"Alto quiere decir que llena un hueco del surtido; bajo, que ya tenemos muchos parecidos. {calculo} "
                  f"Escala provisional hasta que Compras defina cuántos productos caben. Calificación: {final}.")

def razon_cercano(s: Sujeto, p: Producto) -> tuple[bool, str]:
    """¿Sirve la venta en piezas de `p` para decir cuánto venderá `s`?, y por qué en palabras. Precio por pieza de 0.4 a
    2.5 veces (un sobre de $25 no dice cuánto venderá una caja de $599) y, si los dos dicen su tamaño en la misma unidad,
    también el precio por gramo, mililitro o pieza en ese rango (plan de Demanda, 19 nov 2026)."""
    precio = p.precio_lista_con_impuestos
    if not s.precio or not precio:
        return False, "Sin precio para comparar"
    r = s.precio / precio
    if r > RANGO_PRECIO[1]:
        return False, f"El nuevo cuesta {_n(r)} veces su precio"
    if r < RANGO_PRECIO[0]:
        return False, f"Cuesta {_n(1 / r)} veces más que el nuevo"
    if mismo_tipo(s.ficha, ficha_de(p)) is False:  # otro tipo de producto (galletas de proteína contra creatina)
        return False, "Otro tipo de producto según su ficha"
    suyo = solo_piezas(tamano(s.contenido, s.nombre) or (s.ficha.tamano() if s.ficha else {}), formato_sujeto(s))
    otro = tamano_para_precio_de(p)
    for dim in ("g", "ml", "pz"):
        if suyo.get(dim) and otro.get(dim):
            if RANGO_PRECIO[0] <= (s.precio / suyo[dim]) / (precio / otro[dim]) <= RANGO_PRECIO[1]:
                return True, "Precio cercano, por pieza y por " + NOMBRE_UNIDAD[dim]
            return False, f"Por {NOMBRE_UNIDAD[dim]}, muy distinto"
    return True, "Precio cercano"


def precio_cercano(s: Sujeto, p: Producto) -> bool:
    return razon_cercano(s, p)[0]


def parecidos_para_demanda(s: Sujeto, parecidos: list[tuple[Producto, Decimal]], mismo: Producto | None
                           ) -> list[Producto]:
    """Los que usan Demanda y el pronóstico: si ya lo vendemos, ese mismo; si no, los de precio cercano (si ninguno lo
    es, todos)."""
    if mismo:
        return [mismo]
    todos = [p for p, _ in parecidos]
    return [p for p in todos if precio_cercano(s, p)] or todos


def lanzamientos_de_su_tipo(s: Sujeto, misma: list[dict]) -> list[dict]:
    """De los lanzamientos de 2026 de su subcategoría, solo los que son de su mismo tipo: comparten una palabra del
    nombre (su ingrediente; sin marca ni palabras genéricas) y, si se sabe, la misma forma. Diego, 25 nov 2026: la BDM
    Berberina se comparaba contra una canela de Ceylán por estar en la misma subcategoría. Si no queda ninguno, el
    radar no pone otro producto: dice dónde queda entre todos los lanzamientos (el cálculo no cambia, ya usaba los
    parecidos y el arranque de todos los lanzamientos)."""
    marca = raices(palabras(s.marca))
    suyas = {r for r in raices(palabras(sin_sabor(s.nombre), s.ingrediente)) - marca - raices(GENERICAS)
             if len(r) >= LETRAS_INGREDIENTE}
    grupo = GRUPO_FORMATO.get(formato_sujeto(s) or "")
    salida = []
    for x in misma or []:
        otras = raices(palabras(sin_sabor(x.get("descripcion"))))
        su_grupo = GRUPO_FORMATO.get(formato(x.get("descripcion")) or "")
        if suyas & otras and not (grupo and su_grupo and grupo != su_grupo):
            salida.append(x)
    return salida


def _rango_subcategoria(misma: list[dict]) -> str:
    """«los 8 lanzamientos de su subcategoría en 2026 vendieron entre 0.9 y 2.0» (Diego, 20 nov 2026: «74 de cada
    100» era muy general; se compara contra productos reales de su misma subcategoría, con nombre)."""
    xs = [x["por_tienda"] for x in misma]
    if len(xs) == 1:
        return f"el único lanzamiento de su subcategoría en 2026 vendió {xs[0]:,.1f}"
    return f"los {len(xs)} lanzamientos de su subcategoría en 2026 vendieron entre {min(xs):,.1f} y {max(xs):,.1f}"


def _contra_su_subcategoria(valor: float, misma: list[dict]) -> str | None:
    if not misma:
        return None
    mas = sum(1 for x in misma if x["por_tienda"] > valor)
    nombres = "; ".join(f"{x['descripcion']} {x['por_tienda']:,.1f}" for x in misma[:5])
    resto = f" y {len(misma) - 5} más" if len(misma) > 5 else ""
    donde = ("quedaría como el más bajo" if mas == len(misma) else "quedaría como el más alto" if mas == 0
             else f"{mas} de {len(misma)} vendieron más")
    return (f"Contra los lanzamientos de 2026 de su misma subcategoría ({nombres}{resto}, piezas por tienda al mes en "
            f"sus semanas 9 a 12): {donde}.")


def _prueba_texto(prueba: dict | None) -> str | None:
    if not prueba or not prueba.get("probados"):
        return None
    return (f"Qué tan seguido atina: a {prueba['probados']} productos que lanzamos en 2026 se les pronosticó como si "
            f"fueran nuevos y atinó el color de la Demanda en {prueba['color']} y la clase AA–E en {prueba['clase']}.")


def f_demanda(bd: Session, s: Sujeto, parecidos: list[tuple[Producto, Decimal]], v: rr.Ventana | None,
              mismo: Producto | None = None, pron: pn.Pronostico | None = None) -> Factor:
    """Plan de Demanda aprobado por Diego (19 nov 2026): una sola cifra en todo el radar. La calificación sale del
    pronóstico a 12 semanas (cómo arrancaron los lanzamientos de 2026, a partir de lo que venden sus parecidos)
    comparado contra lo que vendieron esos lanzamientos. Sin pronóstico, se usa la venta de los parecidos contra la de
    los productos del departamento. Sin ajuste por tendencia: eso es del factor Tendencia."""
    if not v:
        return Factor(None, None, "Sin datos: todavía no hay ventas cargadas de SMNBI.")
    depto = (mismo.departamento if mismo else None) or s.departamento
    usados = parecidos_para_demanda(s, parecidos, mismo)
    suyos = rr.venta_por_sku(bd, v, [p.sku for p in usados])
    propio = mismo is not None and mismo.sku in suyos
    rango = pron.rango(12) if pron and not propio else None
    lugar = pn.lugar_entre_lanzamientos(bd, rango[1], depto) if rango else None
    if lugar:
        percentil, n, del_depto = lugar
        valor = rango[1]
        donde = "lanzados en 2026 en el departamento" if del_depto else "lanzados en 2026 en toda la cadena"
        detalle = (f"Pronóstico a 12 semanas: {valor:,.1f} piezas por tienda al mes (entre {rango[0]:,.1f} y "
                   f"{rango[2]:,.1f}), a partir de {pron.base_de or 'sus parecidos'}. Vendería más que {percentil:.0f} de "
                   f"cada 100 de los {n} productos {donde} en sus primeras 12 semanas.")
        if sub := _contra_su_subcategoria(valor, pron.misma_sub):
            detalle += f" {sub}"
        if prueba := _prueba_texto(pron.examen.get("prueba")):
            detalle += f" {prueba}"
        contra = f"productos {donde}"
    else:
        ritmo = {sku: x.por_tienda_mes for sku, x in rr.venta_por_sku(bd, v, departamento=depto).items()}
        if depto and len(ritmo) < 5:  # el departamento capturado casi no tiene venta: contra toda la cadena
            depto = None
            ritmo = {sku: x.por_tienda_mes for sku, x in rr.venta_por_sku(bd, v).items()}
        if not suyos:
            return Factor(None, None, f"Sin datos: los productos parecidos no tienen venta en la {v.texto()}.")
        if len(ritmo) < 5:
            return Factor(None, None, f"Sin datos: hay muy pocos productos con venta para comparar en la {v.texto()}.")
        valor = sum(x.por_tienda_mes for x in suyos.values()) / len(suyos)
        percentil = sum(1 for r in ritmo.values() if r <= valor) / len(ritmo) * 100
        con, total = rr.tiendas_con_venta(bd, v, list(suyos))
        quien = (f"Ya vendemos este mismo producto ({mismo.sku} {mismo.descripcion}): en la {v.texto()}"
                 if propio else f"Promedio de {len(suyos)} parecido(s) de precio cercano en la {v.texto()}:")
        donde = "del departamento" if depto else "de toda la cadena"
        detalle = (f"{quien} se vende{'n' if not propio else ''} en {con} de {total} tiendas, con {valor:,.1f} piezas "
                   f"por tienda al mes (contando las tiendas donde estuvo y las semanas desde su primera venta), y "
                   f"vende{'n' if not propio else ''} más que el {percentil:.0f} % de los {len(ritmo)} productos con "
                   f"venta {donde}.")
        contra = f"productos {donde}"
    puntaje = 50 + (percentil - 50) * ESTIRA_DEMANDA
    final = _acotar(puntaje)
    calculo = (f"La calificación es qué tan arriba queda: más que {percentil:.0f} de cada 100 {contra}. La escala se "
               f"abre alrededor de la mitad (50 + la distancia a 50 por {_n(ESTIRA_DEMANDA)}). Calificación: {final}.")
    quienes = "este producto" if propio else "su pronóstico" if lugar else "sus parecidos"
    mejora = None if final > 80 else (f"Para que este factor salga arriba de 80, {quienes} tendría que vender más que "
                                      f"{_percentil_para(81)} de cada 100 {contra}.")
    nivel = ("Se vende muy bien" if percentil >= 80 else "Se vende bien" if percentil >= 60
             else "Venta media" if percentil >= 40 else "Se vende poco")
    if lugar and pron.misma_sub:
        valor_txt = f"{nivel}: vendería {valor:,.1f} piezas por tienda al mes; {_rango_subcategoria(pron.misma_sub)}"
    elif lugar:
        valor_txt = f"{nivel}: vendería {valor:,.1f} piezas por tienda al mes, más que {percentil:.0f} de cada 100 lanzamientos"
    else:
        valor_txt = (f"{nivel}: {'vende' if propio else 'sus parecidos venden'} más que {percentil:.0f} de cada 100 "
                     f"productos ({valor:,.1f} piezas por tienda al mes)")
    return Factor(final, valor_txt, detalle, False, calculo, mejora)


def _cumplimiento_texto(c: rr.Cumplimiento) -> str:
    partes = [f"{c.ordenes} orden(es) desde el {c.desde:%d/%m/%Y}", f"surtió {c.surtido_pct:.0f} % de las piezas"]
    if c.dias_reales is not None:
        promesa = f" (promete {c.dias_prometidos})" if c.dias_prometidos else ""
        partes.append(f"tarda {c.dias_reales:.0f} días hábiles en entregar{promesa}")
    if c.perdidas_pct >= 1 or c.rechazadas_pct >= 1:
        partes.append(f"{c.perdidas_pct:.0f} % compra perdida y {c.rechazadas_pct:.0f} % rechazada")
    return ", ".join(partes)


def _por_cumplimiento(c: rr.Cumplimiento) -> float:
    # Surtir todo vale 90 y cada punto que falta resta 1; entregar más de 3 días tarde de lo prometido resta 10
    puntaje = 90 - (100 - c.surtido_pct) - c.rechazadas_pct
    if c.dias_reales is not None and c.dias_prometidos and c.dias_reales > c.dias_prometidos + 3:
        puntaje -= 10
    return puntaje


CALC_CUMPLIMIENTO = ("Con su historial de compras: surtir todo lo pedido vale 90; cada punto que no surte resta 1, "
                     "igual que cada punto de mercancía rechazada, y tardar más de 3 días de lo que promete resta 10.")
CALC_CALIFICACION = ("Usa su calificación de Datos → Proveedores (cumplimiento, desempeño comercial, costo e "
                     "inventario, de 0 a 100) y suma 5 por cada apoyo de lanzamiento, máximo 10.")


def _faltantes_proveedor(s: Sujeto) -> str | None:
    falta = [x for x, hay in (("inscripción en GS1", s.inscrito_gs1 == "si"),
                              ("registro sanitario", bool(s.registro_sanitario)),
                              ("apoyos de lanzamiento", bool(s.apoyos))) if not hay]
    return f"Subiría con {', '.join(falta[:-1]) + ' y ' + falta[-1] if len(falta) > 1 else falta[0]}." if falta else None


def f_proveedor(bd: Session, s: Sujeto, parecidos: list[tuple[Producto, Decimal]]) -> Factor:
    from datos import proveedores as pv

    if s.proveedor_intelisis:  # se eligió al capturar: se usa esa clave, sin adivinar
        real = rr.ProveedorReal(s.proveedor_intelisis, bd.scalar(select(Proveedor.nombre).where(
            Proveedor.proveedor == s.proveedor_intelisis)), "elegido al capturar")
    else:
        real = rr.proveedor_de(bd, s.proveedor_nombres, s.marca, [p for p, _ in parecidos])
    lo_surte = s.tipo == "idea" and bool(s.proveedor_intelisis)
    hechos = rr.cumplimiento(bd, real.codigo) if real else None
    historial = (f" En Intelisis es {real.nombre or real.codigo} ({real.como}): {_cumplimiento_texto(hechos)}."
                 if real and hechos else "")
    # Si ya tiene calificación en Datos → Proveedores (cumplimiento, comercial, costo e inventario), se usa esa
    cal = pv.calificacion_de(bd, real.codigo) if real else None
    if cal and cal.puntaje is not None:
        texto = (f"{real.nombre or real.codigo} ({real.como}) tiene {cal.puntaje}/100 en Datos → Proveedores "
                 f"(confianza {cal.confianza}).")
        if s.tipo == "idea":
            return Factor(cal.puntaje, f"Proveedor {cal.puntaje}/100",
                          (f"Lo surtiría un proveedor actual: {texto}" if lo_surte else
                           f"La idea todavía no tiene proveedor, pero {texto}") + " Escalas provisionales.", True,
                          "Toma la calificación de 0 a 100 que ese proveedor tiene en Datos → Proveedores.")
        puntaje, partes = float(cal.puntaje), ["ya es proveedor de SMN", f"calificación {cal.puntaje}/100"]
        if s.inscrito_gs1 == "si":
            partes.append("inscrito en GS1")
        if s.registro_sanitario:
            partes.append("con registro sanitario")
        if s.apoyos:
            puntaje += min(10, 5 * s.apoyos)
            partes.append(f"{s.apoyos} apoyo(s) de lanzamiento")
        return Factor(_acotar(puntaje), ", ".join(partes).capitalize(),
                      f"Con su calificación de proveedor: {texto}{historial} Escalas provisionales hasta que Compras "
                      "defina las suyas.", True, f"{CALC_CALIFICACION} Calificación: {_acotar(puntaje)}.",
                      None if s.apoyos >= 2 else "Subiría con apoyos de lanzamiento (5 puntos cada uno, máximo 10) o "
                      "si mejora su calificación de proveedor.")
    if s.tipo == "idea":
        if not hechos:
            return Factor(None, None, f"Sin datos: {real.nombre or real.codigo} todavía no tiene compras cargadas ni "
                                      "calificación en Datos → Proveedores." if lo_surte else "Sin datos: todavía no hay proveedor.")
        return Factor(_acotar(_por_cumplimiento(hechos)), f"Surte {hechos.surtido_pct:.0f} %",
                      ("Lo surtiría un proveedor actual: " if lo_surte else "La idea todavía no tiene proveedor, pero ")
                      + f"{real.nombre or real.codigo} {real.como}: "
                      f"{_cumplimiento_texto(hechos)}. Escala provisional hasta que Compras defina la suya.", True,
                      f"{CALC_CUMPLIMIENTO} Calificación: {_acotar(_por_cumplimiento(hechos))}.")
    puntaje = _por_cumplimiento(hechos) if hechos else 65 if s.proveedor_smn == "si" else 50
    partes = ["ya es proveedor de SMN" if s.proveedor_smn == "si" or real else "proveedor nuevo"]
    if hechos:
        partes.append(f"surte {hechos.surtido_pct:.0f} %")
    if s.inscrito_gs1 == "si":
        puntaje += 10
        partes.append("inscrito en GS1")
    if s.registro_sanitario:
        puntaje += 10
        partes.append("con registro sanitario")
    if s.apoyos:
        puntaje += min(15, 5 * s.apoyos)
        partes.append(f"{s.apoyos} apoyo(s) de lanzamiento")
    if hechos:
        calculo = f"{CALC_CUMPLIMIENTO} Suma 10 con GS1, 10 con registro sanitario y 5 por apoyo (máximo 15)."
    else:
        calculo = ("Un proveedor sin historial empieza en " + ("65 porque dice que ya es de SMN" if s.proveedor_smn == "si"
                                                               else "50") +
                   "; suma 10 si está inscrito en GS1, 10 si tiene registro sanitario y 5 por cada apoyo de "
                   "lanzamiento, máximo 15.")
    calculo += f" Calificación: {_acotar(puntaje)}."
    if hechos:
        detalle = f"Con su historial real de compras.{historial} Escala provisional hasta que Compras defina la suya."
    elif s.proveedor_smn == "si":
        detalle = ("Dice que ya es proveedor de SMN, pero no se encontró en los proveedores ni en las compras de SMNBI "
                   "(o todavía no se cargan). Calificación provisional con lo que dice la propuesta.")
    else:
        detalle = "Proveedor nuevo: calificación provisional con lo que dice la propuesta."
    return Factor(_acotar(puntaje), ", ".join(partes).capitalize(), detalle, True, calculo, _faltantes_proveedor(s))

# ---------------------------------------------------------------- suma, confianza y explicación

# Dirección fijó los factores para el comité (20 nov 2026): Demanda 50, Categoría 25, Rentabilidad 12.5, Precio 12.5.
# Tendencia entra dentro de Demanda (±10) y Proveedor queda solo como contexto: los dos pesan 0.
# 25 nov 2026 (Diego): los 12.5 del Precio se parten en 6.25 contra anaquel y 6.25 contra afuera. Si a uno le faltan
# datos no cuenta y su peso se reparte (igual que antes dentro del Precio: contaba la mitad que había).
PESOS_DIRECCION = {"demanda": Decimal("50"), "rentabilidad": Decimal("12.5"), "precio": Decimal("0"),
                   "precio_anaquel": Decimal("6.25"), "precio_afuera": Decimal("6.25"),
                   "tendencia": Decimal("0"), "categoria": Decimal("25"), "proveedor": Decimal("0")}
CUENTAN = tuple(f for f in FACTORES if PESOS_DIRECCION[f])


def pesos(bd: Session) -> tuple[dict[str, Decimal], str]:  # noqa: ARG001 - antes leía los pesos de Compras
    return dict(PESOS_DIRECCION), "direccion"


# ---------------------------------------------------------------- tendencia dentro de la Demanda (20 nov 2026)

TOPE_TENDENCIA = 10
CORTE_SMN = 10.0  # % de cambio de la subcategoría en SMN (13 semanas contra las 13 anteriores) para sumar o restar 5
POR_SENAL = {100: 5, 80: 3}  # señal alta +5, media +3; temprana o ninguna, nada


def tendencia_smn(bd: Session, v: rr.Ventana | None, subcategoria: str | None) -> float | None:
    """Cambio % de la venta de la subcategoría en SMN: últimas 13 semanas contra las 13 anteriores."""
    if not v or not subcategoria or not (t := rr.tendencia_subcategoria(bd, v, subcategoria)):
        return None
    return round((t[0] / t[1] - 1) * 100, 1)


def ajuste_tendencia(smn: float | None, senal: Factor | None, venta: list[sv.Senal] | None = None
                     ) -> tuple[int, list[str]]:
    """Puntos que suma o resta la tendencia a la Demanda (tope ±10) y por qué, en palabras. Desde el 22 nov 2026 también
    suma la señal de venta en internet: +5 fuerte (más vendido, top 10 o +1,000 vendidos), +3 media."""
    puntos, por = 0, []
    n, mejor = sv.nivel(venta or [])
    if n:
        puntos += n
        por.append(f"suma {n} porque se vende afuera ({sv.frase(mejor)})")
    if smn is not None and abs(smn) > CORTE_SMN:
        puntos += 5 if smn > 0 else -5
        por.append(f"{'suma' if smn > 0 else 'resta'} 5 porque su subcategoría {'crece' if smn > 0 else 'cae'} "
                   f"{abs(smn):,.0f} % en SMN (13 semanas contra las 13 anteriores)")
    if senal and senal.puntaje in POR_SENAL:
        n = POR_SENAL[senal.puntaje]
        puntos += n
        por.append(f"suma {n} por la {senal.valor[0].lower()}{senal.valor[1:]}" if senal.valor else
                   f"suma {n} por una señal {'alta' if senal.puntaje == 100 else 'media'} en internet")
    return max(-TOPE_TENDENCIA, min(TOPE_TENDENCIA, puntos)), por


def con_tendencia(demanda: Factor, smn: float | None, senal: Factor | None, venta: list[sv.Senal] | None = None
                  ) -> Factor:
    if demanda.puntaje is None:
        return demanda
    puntos, por = ajuste_tendencia(smn, senal, venta)
    cambio = (f" La subcategoría {'crece' if smn > 0 else 'cae'} {abs(smn):,.0f} % en SMN (13 semanas contra las 13 "
              "anteriores)." if smn is not None and abs(smn) >= 1 else "")
    if not puntos:
        calc = (f"{demanda.calculo or ''} Tendencia: no mueve la calificación (cambio de la subcategoría en SMN dentro "
                f"de ±{CORTE_SMN:.0f} % y sin señal media o alta en internet ni de venta afuera).").strip()
        return Factor(demanda.puntaje, demanda.valor, demanda.detalle + cambio, demanda.provisional, calc[:1000],
                      demanda.mejora, demanda.meta)
    final = _acotar(demanda.puntaje + puntos)
    calc = f"{demanda.calculo or ''} Tendencia: {'; '.join(por)}. Con la tendencia: {final}.".strip()
    return Factor(final, demanda.valor, demanda.detalle + cambio, demanda.provisional, calc[:1000], demanda.mejora,
                  demanda.meta)


# Una oportunidad (de «Buscar oportunidades») todavía no tiene proveedor ni costo: se califica con lo que se puede saber
# antes de buscarle proveedor, y la confianza se mide sobre eso (Diego, 2 nov 2026: «esta en desventaja porque no tiene
# proveedor ni precio de nosotros»). Si Compras ya capturó costo o proveedor, ese factor cuenta como siempre.
AL_CONSEGUIR_PROVEEDOR = ("rentabilidad", "proveedor")


def por_conseguir(factores: dict[str, Factor]) -> set[str]:
    return {f for f in AL_CONSEGUIR_PROVEEDOR if f in factores and factores[f].puntaje is None}


def marcar_oportunidad(factores: dict[str, Factor], por: str = "Es una oportunidad: todavía no se le busca proveedor"
                       ) -> set[str]:
    """Rentabilidad y Proveedor sin datos se marcan «al conseguir proveedor» y no bajan la confianza."""
    fuera = por_conseguir(factores)
    for f in fuera:
        antes = factores[f]
        factores[f] = Factor(None, "Se califica al conseguir proveedor",
                             f"{por}, así que no cuenta ni baja la confianza. "
                             f"Cuando Compras capture {'el costo' if f == 'rentabilidad' else 'el proveedor'} y se vuelva "
                             f"a evaluar, se califica. ({antes.detalle})", antes.provisional)
    return fuera


def sin_senal(factores: dict[str, Factor]) -> set[str]:
    """Tendencia sin ninguna señal que hable del producto: no cuenta ni baja la confianza."""
    x = factores.get("tendencia")
    return {"tendencia"} if x is not None and x.puntaje is None and x.valor == SIN_SENAL else set()


def sumar(factores: dict[str, Factor], peso: dict[str, Decimal], fuera: set[str] | frozenset[str] = frozenset()
          ) -> tuple[int | None, str]:
    con_datos = {f: x for f, x in factores.items() if x.puntaje is not None}
    cubierto = sum((peso.get(f, Decimal(0)) for f in con_datos), Decimal(0))
    total = sum((p for f, p in peso.items() if f not in fuera), Decimal(0))
    parte = cubierto / total if total else Decimal(0)
    confianza = "alta" if parte >= Decimal("0.8") else "media" if parte >= Decimal("0.5") else "baja"
    if not cubierto:
        return None, "baja"
    return _entero(sum(peso.get(f, Decimal(0)) * x.puntaje for f, x in con_datos.items()) / cubierto), confianza


def _faltan(puntaje: int, color: str) -> str:
    if color == "verde":
        return ""
    if puntaje > 80:
        return " Por puntos sería verde, pero con confianza baja no puede salir verde: faltan datos."
    def pts(n: int) -> str:
        return f"{n} punto" if n == 1 else f"{n} puntos"
    if puntaje >= 60:
        return f" Le {'falta' if 81 - puntaje == 1 else 'faltan'} {pts(81 - puntaje)} para verde."
    return f" Le faltan {pts(60 - puntaje)} para amarillo y {pts(81 - puntaje)} para verde."


def explicacion_simple(s: Sujeto, puntaje: int | None, color: str, confianza: str, factores: dict[str, Factor],
                       peso: dict[str, Decimal] | None = None, fuera: set[str] | frozenset[str] = frozenset(),
                       oportunidad: bool = True) -> str:
    peso = peso or {f: Decimal(1) for f in factores}
    factores = {f: x for f, x in factores.items() if peso.get(f, 1)}  # Tendencia y Proveedor ya no pesan (20 nov 2026)
    fuera = {f for f in fuera if f in factores}
    con = sorted(((f, x) for f, x in factores.items() if x.puntaje is not None), key=lambda t: -t[1].puntaje)
    sin = [NOMBRES[f].lower() for f, x in factores.items() if x.puntaje is None and f not in fuera]
    if puntaje is None:
        return "No hubo datos suficientes para calificar este producto. Faltan: " + ", ".join(sin) + "."
    partes = [f"**Resultado:** {puntaje} de 100, {color}. Verde es más de 80, amarillo de 60 a 80 y rojo 59 o menos."
              + _faltan(puntaje, color) + f" Confianza {confianza}: se calificó con {len(con)} de "
              f"{len(factores) - len(fuera)} factores."]
    al_conseguir = [f for f in FACTORES if f in fuera and f in AL_CONSEGUIR_PROVEEDOR]
    if al_conseguir:
        nombres = " y ".join(NOMBRES[f].lower() for f in al_conseguir)
        inicio = ("**Es una oportunidad:** la pregunta es si vale la pena buscarle proveedor." if oportunidad else
                  "**Sin proveedor actual:** se califica con el semáforo para productos sin proveedor.")
        partes.insert(0, f"{inicio} {nombres.capitalize()} se califican al conseguirlo y no bajan la confianza.")
    if "tendencia" in fuera:
        partes.append("**Tendencia:** nadie habla de él en internet, así que no cuenta: ni lo sube ni lo baja.")
    def lista(items) -> str:
        return "; ".join(f"{NOMBRES[f].lower()} ({x.puntaje})" + (f": {x.valor[0].lower()}{x.valor[1:]}" if x.valor else "")
                         for f, x in items) + "."
    sube = [(f, x) for f, x in con if x.puntaje >= 70][:2]
    if sube:
        partes.append("**Lo que lo sube:** " + lista(sube))
    baja = [(f, x) for f, x in reversed(con) if x.puntaje < 60][:2]
    if baja:
        partes.append("**Lo que lo baja:** " + lista(baja))
    elif len(con) > 1 and con[-1] not in sube:
        partes.append("**Lo que menos ayuda:** " + lista([con[-1]]))
    # Lo que más puntos podría ganar: el factor que más pesa y más abajo está, con algo que lo mejore
    margen = sorted(((f, x) for f, x in con if x.mejora and x.puntaje <= 80),
                    key=lambda t: -float(peso.get(t[0], 1)) * (100 - t[1].puntaje))
    cambio = [f"{NOMBRES[f]}: {x.mejora[0].lower()}{x.mejora[1:]}" for f, x in margen[:2]]
    if sin:
        lista = ", ".join(sin[:-1]) + " y " + sin[-1] if len(sin) > 1 else sin[0]
        cambio.append(f"Faltan datos de {lista}; con ellos sube la confianza.")
    if cambio:
        titulo = "Qué lo subiría más" if color == "verde" else "Qué lo haría cambiar"
        partes.append(f"**{titulo}:** " + " ".join(cambio))
    return "\n\n".join(partes)


def con_proveedor_actual(bd: Session, s: Sujeto) -> bool:
    """Una propuesta cuya empresa ya está ligada a Intelisis, o cuyo nombre es el de un proveedor de Intelisis; lo mismo
    para una idea capturada con proveedor (captura corta, 2026-11-04). Una idea sin proveedor no lo tiene. No se infiere
    por la marca: eso diría quién surte la marca, no quién propone."""
    return bool(s.proveedor_intelisis) or rr.proveedor_de(bd, s.proveedor_nombres, None, []) is not None


# ---------------------------------------------------------------- correr una evaluación

def _llave_variante(marca: str | None, nombre: str | None) -> tuple[str, frozenset[str]] | None:
    marca, nombre = _norm(marca).strip(), raices(palabras(sin_sabor(nombre)))
    return (marca, frozenset(nombre)) if marca and nombre else None


def clasificacion_de_variante(bd: Session, e: ProductoEvaluacion, s: Sujeto) -> ProductoEvaluacion | None:
    """El mismo producto en otro sabor que ya tiene subcategoría (18 nov 2026, Hybrix 5): se usa la misma, para que los
    sabores de un producto no queden en subcategorías distintas. Gana la que confirmó Compras; si no, la más reciente."""
    llave = _llave_variante(s.marca, s.nombre)
    if llave is None:
        return None
    candidatas = []
    ideas = bd.execute(select(ProductoEvaluacion, ProductoIdea.marca, ProductoIdea.nombre).join(
        ProductoIdea, ProductoIdea.idea_id == ProductoEvaluacion.idea_id).where(
        ProductoEvaluacion.vigente == true(), ProductoEvaluacion.subcategoria.is_not(None),
        ProductoEvaluacion.evaluacion_id != e.evaluacion_id)).all()
    propuestas = bd.execute(select(ProductoEvaluacion, Propuesta.marca, Propuesta.producto).join(
        Propuesta, Propuesta.propuesta_id == ProductoEvaluacion.propuesta_id).where(
        ProductoEvaluacion.vigente == true(), ProductoEvaluacion.subcategoria.is_not(None),
        ProductoEvaluacion.evaluacion_id != e.evaluacion_id)).all()
    for otra, marca, nombre in [*ideas, *propuestas]:
        if (otra.idea_id and otra.idea_id == e.idea_id) or (otra.propuesta_id and otra.propuesta_id == e.propuesta_id):
            continue
        if _llave_variante(marca, nombre) == llave:
            candidatas.append(otra)
    candidatas.sort(key=lambda x: (x.clasificacion_origen != "compras", -x.evaluacion_id))
    return candidatas[0] if candidatas else None


def clasificar_sujeto(bd: Session, s: Sujeto, usar_ia: bool = True, revisar: bool = True):
    """Clasificación automática por votación (v0.5.4, plan aprobado por Diego el 24 nov 2026): devuelve un
    `clasificador.Clasificacion`. La usan la evaluación, la reclasificación de cada noche y el examen, para que el examen
    califique exactamente lo mismo que corre en el radar. Con `COMO_V053` clasifica como la v0.5.3 (ingrediente principal
    y si no, la IA entre las subcategorías), solo para compararlas."""
    from modulos.compras import clasificador

    if not COMO_V053.get():
        return clasificador.clasificar(bd, s, usar_ia)
    c = clasificador.Clasificacion()
    if ingrediente := ingrediente_de(bd, s):
        c.rama, c.subcategoria, c.segmento = ingrediente.rama, ingrediente.subcategoria, ingrediente.segmento
        c.origen, c.seguridad, c.conservar, c.ingrediente = "ingrediente", "segura", set(ingrediente.ids), ingrediente.palabra
        return c
    if usar_ia:
        sin_sub, _ = revisar_parecidos(bd, s, buscar_parecidos(bd, s, None), {}) if revisar else (None, [])
        c.rama, c.subcategoria, c.segmento = clasificar(bd, s, sin_sub)
        if c.subcategoria:
            c.origen, c.seguridad = "ia", "dudosa"
    return c


def parecidos_sujeto(bd: Session, s: Sujeto, subcategoria: str | None, rama: str | None, conservar: set[int],
                     vistos: dict[str, tuple[bool, str]], ingrediente: set[int] | frozenset[int] = frozenset()
                     ) -> tuple[list[tuple[Producto, Decimal]], list[tuple[Producto, str]]]:
    """Parecidos ya revisados por la IA (los quitados, con su motivo). Misma función para la evaluación y el examen.
    `ingrediente`: los que llevan su ingrediente principal (`del_ingrediente`); no se tiran por subcategoría ni tamaño,
    pero la IA sí los revisa (26 nov 2026: entraba un jabón de colágeno como parecido de un colágeno en polvo)."""
    juntos = set(conservar) | set(ingrediente)
    return revisar_parecidos(bd, s, buscar_parecidos(bd, s, subcategoria, rama, juntos), vistos, conservar)


def clasificacion_de_parecidos(parecidos: list[tuple[Producto, Decimal]], mismo: Producto | None) -> Producto | None:
    """Sin clasificación: la del mismo producto o la que comparten casi todos los parecidos."""
    return mismo or subcategoria_de_parecidos(parecidos)


def vigente(bd: Session, *, propuesta_id: int | None = None, idea_id: int | None = None) -> ProductoEvaluacion | None:
    q = select(ProductoEvaluacion).where(ProductoEvaluacion.vigente == true())
    q = q.where(ProductoEvaluacion.propuesta_id == propuesta_id) if propuesta_id else q.where(ProductoEvaluacion.idea_id == idea_id)
    return bd.scalar(q.order_by(ProductoEvaluacion.evaluacion_id.desc()))


def iniciar(bd: Session, *, propuesta_id: int | None = None, idea_id: int | None = None, usuario_id: int | None = None,
            clasificacion: tuple[str | None, str | None, str | None] | None = None,
            comparables: list[int] | None = None) -> ProductoEvaluacion:
    """Crea la evaluación en curso. Lo que Compras confirmó antes (clasificación y parecidos) se conserva.

    comparables: None = heredar los que fijó Compras; lista vacía = que el sistema vuelva a buscar."""
    anterior = vigente(bd, propuesta_id=propuesta_id, idea_id=idea_id)
    e = ProductoEvaluacion(propuesta_id=propuesta_id, idea_id=idea_id, estado="en_curso", vigente=True,
                           disparada_por=usuario_id, creada_en=ahora())
    # v0.5.4: la clasificación es automática; ya no se toma ni se hereda la que confirmaba Compras (`clasificacion` se
    # ignora, se deja para no romper a quien la mande). Como la v0.5.3 (solo para compararla) sí se hereda.
    if COMO_V053.get() and anterior and anterior.clasificacion_origen == "compras":
        e.rama, e.subcategoria, e.segmento, e.clasificacion_origen = (anterior.rama, anterior.subcategoria,
                                                                      anterior.segmento, "compras")
    fijos = comparables
    if fijos is None and anterior and any(c.origen == "compras" for c in anterior.comparables):
        fijos = [c.producto_id for c in anterior.comparables]
    if anterior:
        anterior.vigente = False
    bd.add(e)
    bd.flush()
    if fijos:
        for i, pid in enumerate(dict.fromkeys(fijos), 1):
            e.comparables.append(EvaluacionComparable(producto_id=pid, rango=i, similitud=Decimal(0), origen="compras"))
    bd.commit()
    return e


PASOS = 6


def evaluar(bd: Session, evaluacion_id: int, hoy: date | None = None) -> ProductoEvaluacion:
    e = bd.get(ProductoEvaluacion, evaluacion_id)
    hoy = hoy or date.today()

    def paso(n: int, texto: str) -> None:
        # Se guarda en cada paso para que la pantalla diga en cuál va y no se quede esperando a que todo termine
        e.avance = f"Paso {n} de {PASOS}: {texto}"
        bd.commit()
        # También al log, para ver en el servidor en qué paso va cada evaluación (Diego, 26 nov 2026)
        log.info("Radar de productos: evaluación %s, %s", evaluacion_id, e.avance)

    try:
        paso(1, "leyendo la ficha técnica y clasificando el producto")
        if e.propuesta_id:
            p = bd.get(Propuesta, e.propuesta_id)
            s = sujeto_de_propuesta(p)
            s.proveedor_intelisis = bd.scalar(select(OrganizacionExterna.proveedor_intelisis).where(
                OrganizacionExterna.organizacion_id == p.organizacion_id))
        else:
            s = sujeto_de_idea(bd.get(ProductoIdea, e.idea_id))
        ficha_sujeto(bd, e, s)
        poner_familia(bd, s)
        e.departamento = s.departamento
        fijados = bool(e.comparables)
        vistos: dict[str, tuple[bool, str]] = {}
        quitados: list[tuple[Producto, str]] = []
        if e.clasificacion_origen != "compras" and (otra := clasificacion_de_variante(bd, e, s)):
            e.rama, e.subcategoria, e.segmento = otra.rama, otra.subcategoria, otra.segmento
            e.clasificacion_origen = "variante"
        conservar: set[int] = set()
        clasif = None
        if e.clasificacion_origen not in ("variante", "compras"):  # nadie la confirma a mano desde la v0.5.4
            clasif = clasificar_sujeto(bd, s, revisar=not fijados)
            e.rama, e.subcategoria, e.segmento, e.clasificacion_origen = (clasif.rama, clasif.subcategoria,
                                                                          clasif.segmento, clasif.origen)
            conservar = clasif.conservar
        elif ingrediente := ingrediente_de(bd, s):  # otro sabor: los de su ingrediente se quedan, como en la v0.5.3
            conservar = set(ingrediente.ids)
        # 26 nov 2026: los de su ingrediente no se tiran por subcategoría ni tamaño (la IA sí revisa que sean de su tipo)
        suyo = del_ingrediente(s, catalogo_activo(bd))
        del_suyo = suyo[1] if suyo else set()

        paso(2, "buscando productos parecidos en el catálogo y revisándolos con la IA")
        if fijados:  # Compras los fijó: no se revisan
            parecidos = [(bd.get(Producto, c.producto_id), c.similitud) for c in e.comparables]
            cargar_fichas(bd, [p for p, _ in parecidos])
        else:
            parecidos, quitados = parecidos_sujeto(bd, s, e.subcategoria, e.rama, conservar, vistos, del_suyo)
        mismo = mismo_de(s, parecidos)
        if not e.subcategoria and e.clasificacion_origen not in ("variante", "compras"):
            if fuente := clasificacion_de_parecidos(parecidos, mismo):
                e.rama, e.subcategoria, e.segmento = fuente.rama, fuente.subcategoria, fuente.segmento
                e.clasificacion_origen = "parecidos"
                if not fijados:  # ya con subcategoría, se quitan los de otra (11 nov 2026)
                    parecidos = _depurar(parecidos, e.subcategoria, e.rama, set(conservar) | del_suyo)
        if not fijados:
            for i, (p, sim) in enumerate(parecidos, 1):
                e.comparables.append(EvaluacionComparable(producto_id=p.producto_id, rango=i, similitud=sim, origen="sistema"))
        for c in e.comparables:
            if mismo and c.producto_id == mismo.producto_id:
                c.similitud = Decimal(1)  # así la pantalla lo muestra como «Ya lo vendemos»

        paso(3, "buscando precios en internet y en las tiendas, y leyendo páginas con la IA local")
        internet = mercado_de(bd, e, s)
        investigacion = investigacion_de(bd, e, s)
        if investigacion:
            e.investigacion = investigacion.a_json()
        internet = con_web(internet, investigacion)
        if internet:
            e.mercado = internet.a_json()
        paso(4, "calculando demanda, margen, precio, surtido y proveedor con la venta de SMNBI")
        v = rr.ventana(bd)
        precio = f_precio(s, parecidos, internet, mismo)
        pron = None
        try:  # pronóstico por grupo de tiendas (17 nov 2026); de él sale la Demanda (19 nov). Si falla, sigue
            skus, nombre_base, fam = skus_para_pronostico(s, parecidos, mismo), None, None
            if not mismo and v and (fam := familia_para_demanda(s, catalogo_activo(bd))):
                con_venta = rr.venta_por_sku(bd, v, [p.sku for p in fam[1]])
                if len(con_venta) >= MIN_FAMILIA:  # se mide contra todo su tipo de producto, no solo los de precio cercano
                    skus, nombre_base = list(con_venta), f"productos de {fam[0]}"
                    nombres = {p.sku: p.descripcion for p in fam[1]}
                    mejores = sorted(con_venta.items(), key=lambda x: -x[1].por_tienda_mes)[:3]
                    familia = [{"sku": k, "descripcion": nombres.get(k) or k, "por_tienda": round(x.por_tienda_mes, 2)}
                               for k, x in mejores]
            pron = pn.pronosticar(bd, skus, e.subcategoria, nombre_base)
            if nombre_base:
                pron.familia, pron.familia_de = familia, nombre_base
            pron.misma_sub = lanzamientos_de_su_tipo(s, pron.misma_sub)
            # se guardan los lanzamientos contra los que se califica para que la pantalla del comité no los vuelva a medir
            contra, pron.contra_depto = pn.lanzamientos_contra(bd, (mismo.departamento if mismo else None) or s.departamento)
            pron.contra = [round(x, 3) for x in contra]
            e.pronostico = pron.a_json()
        except Exception as ex:  # noqa: BLE001
            log.warning("Radar de productos: no se pudo pronosticar la evaluación %s: %s", evaluacion_id, ex)
        factores = {
            "demanda": f_demanda(bd, s, parecidos, v, mismo, pron),
            "rentabilidad": f_rentabilidad(bd, s, e.subcategoria, v, mismo, precio.meta),
            "precio": precio,
            **precios_por_lado(s, parecidos, internet, mismo),
            "categoria": f_categoria(bd, s, e.subcategoria, parecidos, v, mismo),
            "proveedor": f_proveedor(bd, s, parecidos),
        }
        paso(5, "revisando las tendencias de internet")
        factores["tendencia"] = f_tendencia(bd, s, hoy, e.subcategoria)
        factores["demanda"] = con_tendencia(factores["demanda"], tendencia_smn(bd, v, e.subcategoria),
                                            factores["tendencia"], sv.de_lista(internet.senales) if internet else [])
        factores = {f: factores[f] for f in FACTORES}
        peso, e.pesos_origen = pesos(bd)
        oportunidad = bool(e.idea_id) and bd.scalar(select(Oportunidad.oportunidad_id).where(Oportunidad.idea_id == e.idea_id))
        # Con proveedor actual (ya está en Intelisis) se usan los 6 factores; sin él, Rentabilidad y Proveedor cuentan
        # solo si ya hay datos (plan del Comité de producto nuevo, aprobado por Diego el 2026-11-04)
        e.modelo = "con_proveedor" if con_proveedor_actual(bd, s) else "sin_proveedor"
        if oportunidad:
            fuera = marcar_oportunidad(factores)
        elif e.modelo == "sin_proveedor":
            fuera = marcar_oportunidad(factores, "Todavía no tiene un proveedor que ya nos surta")
        else:
            fuera = set()
        fuera |= sin_senal(factores)
        e.puntaje, e.confianza = sumar(factores, peso, fuera)
        e.color = color_de(e.puntaje, e.confianza)
        e.factores = [EvaluacionFactor(factor=f, peso=peso[f], puntaje=x.puntaje, valor=x.valor, detalle=x.detalle[:1000],
                                       provisional=x.provisional, calculo=(x.calculo or None) and x.calculo[:1000],
                                       mejora=(x.mejora or None) and x.mejora[:600])
                      for f, x in factores.items()]
        paso(6, "revisando las políticas y reglas de Compras")
        revision = pp.revisar(bd, s.departamento, s.texto(), datos_para_politicas(s, e, factores, internet))
        e.politicas = revision.a_json()
        if revision.rechazo:
            e.color = "rojo"
        # El resumen se arma con los números de cada factor, no lo redacta la IA: así no se sale de los datos
        # (Diego, 29 oct: con la IA «dice cosas muy genéricas»)
        e.explicacion, e.explicacion_ia = explicacion_simple(s, e.puntaje, e.color, e.confianza, factores, peso, fuera,
                                                                    bool(oportunidad)), False
        e.explicacion = (dictamen(s, e.color, factores, parecidos, minimos(bd, s).lista,
                                  revision.rechazo) + "\n\n" + e.explicacion)
        if mismo:
            e.explicacion = (f"Ojo: ya vendemos este mismo producto ({mismo.sku} {mismo.descripcion}). Los números son los de "
                             f"ese producto.\n\n{e.explicacion}")
        if r := revision.rechazo:
            e.explicacion = (f"Rechazo directo por la regla «{r['titulo']}» de Compras: {r['motivo']} (dato: "
                             f"{r.get('dato')})\n\n{e.explicacion}")
        # Lo que ya decidió el comité con un producto parecido (no con este mismo)
        if (caso := next((c for c in revision.casos if c.get("similitud", 0) >= 0.4
                          and _norm(c.get("producto")).strip() != _norm(s.nombre).strip()), None)):
            e.explicacion += (f"\n\nAntecedente: «{caso['producto']}» quedó {caso['decision']}"
                              + (f" ({caso['motivo']})" if caso.get("motivo") else "") + ".")
        e.explicacion += nota_quitados(quitados)
        if clasif is not None and not COMO_V053.get():
            e.explicacion += f"\n\n{clasif.texto()}"
        if not revision.rechazo and revision.avisos:
            titulos = ", ".join(f"«{x['titulo']}»" for x in revision.avisos[:2])
            e.explicacion = (f"Aviso: podría caer en la regla {titulos} de Compras, pero no hay un dato del producto que "
                             f"lo pruebe. No cambia el color; que Compras lo confirme.\n\n{e.explicacion}")
        e.estado, e.avance = "lista", None
        log.info("Radar de productos: evaluación %s lista", evaluacion_id)
    except Exception as ex:  # noqa: BLE001
        log.exception("Radar de productos: falló la evaluación %s", evaluacion_id)
        bd.rollback()
        e = bd.get(ProductoEvaluacion, evaluacion_id)
        e.estado, e.avance, e.error = "fallida", None, f"No se pudo evaluar: {str(ex)[:900]}"
    e.terminada_en = ahora()
    bd.commit()
    if e.estado == "lista":
        # La pantalla por niveles se arma aquí una sola vez y se guarda (plan de Diego, 22 nov 2026); si falla, la
        # evaluación queda igual y la pantalla se arma al abrirla
        from modulos.compras import pantalla_comite

        try:
            pantalla_comite.guardar(bd, e)
        except Exception:  # noqa: BLE001
            bd.rollback()
            log.exception("Radar de productos: no se pudo guardar la pantalla de la evaluación %s", evaluacion_id)
            e = bd.get(ProductoEvaluacion, evaluacion_id)
    if e.estado == "lista" and MERCADO_FIJO.get() is None:  # (en una comparación no se abre nada)
        # una idea sin proveedor que salió bien se vuelve búsqueda de proveedor (2026-11-09)
        from modulos.compras import busquedas

        busquedas.despues_de_evaluar(bd, e)
    return e


DICTAMEN = "Dictamen: "
# Marcas de SMN (25 nov 2026): en el dictamen se avisa cuando el producto nuevo competiría con una de ellas
MARCAS_PROPIAS = {"vidanat"}


def con_marca(p: Producto) -> str:
    """La descripción con la marca al frente si no la trae (en SMNBI muchas descripciones vienen sin marca)."""
    desc = p.descripcion or ""
    if p.marca and not raices(palabras(p.marca)) <= raices(palabras(desc)):
        return f"{p.marca} {desc}"
    return desc


def dictamen(s: Sujeto, color: str, factores: dict[str, Factor], parecidos: list[tuple[Producto, Decimal]],
             minimo: Decimal | None, rechazo: dict | None = None) -> str:
    """Lectura de comprador en una línea: meter, negociar o no meter, con el precio o costo meta y contra qué se compara.
    Sale de los números del semáforo, no de la IA (Diego, 11 nov 2026: «que actúe como experto en compras»)."""
    if rechazo:
        return f"{DICTAMEN}No meter: cae en la regla «{rechazo.get('titulo')}» de Compras."
    pts = {f: x.puntaje for f, x in factores.items() if f in CUENTAN}
    demanda, rent = pts.get("demanda"), pts.get("rentabilidad")
    # el Precio junto (promedio de anaquel y afuera) ya no pesa por sí solo desde el 25 nov 2026, pero manda en el dictamen
    precio = factores["precio"].puntaje if "precio" in factores else None
    bajo_margen = s.margen is not None and minimo is not None and s.margen < minimo
    partes = []
    if color == "verde":
        veredicto = "Meter"
    elif demanda is not None and demanda < 40 and color == "rojo":
        veredicto = "No meter: vendería poco en nuestras tiendas"
    elif bajo_margen or (precio is not None and precio < 60):
        veredicto = "Negociar"
    elif color == "rojo":
        debiles = [NOMBRES[f].lower() for f, p in sorted(pts.items(), key=lambda x: x[1] if x[1] is not None else 101)
                   if p is not None and p < 60][:2]
        veredicto = "No meter por ahora" + (f": débil en {' y '.join(debiles)}" if debiles else "")
    else:
        veredicto = "Se puede meter, a prueba"
    if bajo_margen and s.precio and s.margen is not None:
        base = s.precio / (1 + IVA_SUPUESTO / 100)
        costo = s.costo or base * (1 - s.margen / 100)
        costo_meta = base * (1 - minimo / 100)
        precio_meta = costo / (1 - minimo / 100) * (1 + IVA_SUPUESTO / 100)
        ref = (factores["precio"].competir or factores["precio"].meta) if "precio" in factores else None
        if precio is not None and precio < 60 and ref:
            # Ya está caro: el precio tiene que bajar a lo que cuestan los demás y el costo, con ese precio, dar el mínimo
            costo_ref = ref / (1 + IVA_SUPUESTO / 100) * (1 - minimo / 100)
            partes.append(f"para competir tendría que venderse en unos {_pesos(ref)} (hoy {_pesos(s.precio)}), y con ese "
                          f"precio el costo tendría que bajar a {_pesos(costo_ref)} sin IVA (hoy {_pesos(costo)}) para "
                          f"dejar {_n(minimo)} %")
        elif precio is not None and precio < 60:
            partes.append(f"pedir costo de {_pesos(costo_meta)} sin IVA (hoy {_pesos(costo)}); subirle el precio no "
                          "conviene porque ya está caro")
        elif ref and precio_meta > ref:
            # Nunca un precio arriba del mercado (13 nov 2026): la salida es el costo
            costo_ref = min(s.precio, ref) / (1 + IVA_SUPUESTO / 100) * (1 - minimo / 100)
            partes.append(f"la salida es el costo: pedirlo en {_pesos(costo_ref)} sin IVA (hoy {_pesos(costo)}); "
                          f"subirle el precio no funciona porque para dejar {_n(minimo)} % tendría que venderse en "
                          f"{_pesos(precio_meta)} y el mercado está en {_pesos(ref)}")
        else:
            partes.append(f"pedir costo de {_pesos(costo_meta)} sin IVA (hoy {_pesos(costo)}) o venderlo en "
                          f"{_pesos(precio_meta)} para dejar {_n(minimo)} %")
    elif precio is not None and precio < 60 and (m := factores.get("precio")) and (ref := m.competir or m.meta) \
            and s.precio and ref < s.precio - 1:
        # El precio con el que las dos mitades juntas dejan el rojo (Wonu 22 nov 2026: decía «$599 (hoy $599)»
        # porque usaba solo la referencia de afuera, igual a nuestro precio)
        partes.append(f"para competir tendría que venderse en unos {_pesos(ref)} (hoy {_pesos(s.precio)})")
    # Contra los mismos parecidos que usa la Demanda (20 nov 2026: el dictamen nombraba a los más parecidos por nombre,
    # aunque la Demanda usara otros de precio cercano)
    usados = {p.producto_id for p in parecidos_para_demanda(s, parecidos, mismo_de(s, parecidos))}
    con_precio = [(p, sim) for p, sim in parecidos if p.precio_lista_con_impuestos and p.producto_id in usados][:2]
    if con_precio:
        partes.append("se compara con " + " y ".join(f"{con_marca(p)} ({_pesos(p.precio_lista_con_impuestos)})"
                                                     for p, _ in con_precio))
    # 25 nov 2026 (BDM Life Berberina): si da lo mismo que un producto de marca propia, se dice; le quitaría venta a lo
    # que más margen deja
    propios = [p for p in (mismo_activo(s, parecidos) or [p for p, _ in parecidos if p.producto_id in usados])
               if _norm(p.marca or "").split("/")[0].strip() in MARCAS_PROPIAS
               and _norm(s.marca or "").split("/")[0].strip() not in MARCAS_PROPIAS]
    if propios:
        partes.append(f"ojo: competiría con nuestra marca propia {con_marca(propios[0])}"
                      + (f" ({_pesos(propios[0].precio_lista_con_impuestos)})" if propios[0].precio_lista_con_impuestos else ""))
    resto = "; ".join(partes)
    if partes and ":" in veredicto:  # «No meter: vendería poco… Se compara con…» (con mayúscula)
        resto = resto[0].upper() + resto[1:]
    texto = veredicto + (": " if partes and ":" not in veredicto else ". " if partes else "") + resto
    return f"{DICTAMEN}{texto.rstrip('.')}."


def _sesion() -> Session:
    from core.bd import _fabrica

    return _fabrica()()


def en_hilo(evaluacion_id: int, trabajo: Callable[[Session, int], object] = evaluar) -> None:
    def correr():
        with _sesion() as bd:
            trabajo(bd, evaluacion_id)

    threading.Thread(target=correr, daemon=True, name=f"radar-productos-{evaluacion_id}").start()


def cerrar_huerfanas(bd: Session) -> int:
    """Al arrancar: las evaluaciones que quedaron en curso (la API se reinició) se marcan fallidas."""
    filas = bd.scalars(select(ProductoEvaluacion).where(ProductoEvaluacion.estado == "en_curso")).all()
    for e in filas:
        e.estado, e.error, e.terminada_en = "fallida", "La plataforma se reinició a media evaluación. Recalcúlala.", ahora()
    bd.commit()
    return len(filas)
