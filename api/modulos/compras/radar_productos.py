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
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Callable

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from core.config import configuracion
from datos.modelos import Producto, Proveedor
from ia import puerta
from modulos.compras import mercado_producto as mp
from modulos.compras import politicas_producto as pp
from modulos.compras import realidad_producto as rr
from modulos.compras import propuestas as pr
from modulos.compras.modelos import RadarSenal
from modulos.compras.modelos_conocimiento import ConocimientoPeso, ConocimientoRegla
from modulos.compras.modelos_productos import (
    EvaluacionComparable, EvaluacionFactor, Oportunidad, ProductoEvaluacion, ProductoIdea,
)
from modulos.compras.modelos_propuestas import Propuesta
from nucleo.modelos import OrganizacionExterna, ahora

log = logging.getLogger("smn.compras.radar_productos")

FACTORES = ("demanda", "rentabilidad", "precio", "tendencia", "categoria", "proveedor")
NOMBRES = {"demanda": "Demanda", "rentabilidad": "Rentabilidad", "precio": "Precio", "tendencia": "Tendencia",
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
    "polvo", "liquido", "gomitas", "sobres", "natural", "naturales", "plus", "premium",
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


def palabras(*textos: str | None) -> set[str]:
    """Palabras que distinguen un producto: sin acentos, sin números ni palabras vacías."""
    salida: set[str] = set()
    for t in textos:
        for p in re.findall(r"[a-zñ]{3,}", _norm(t)):
            if p not in PALABRAS_VACIAS:
                salida.add(p)
    return salida


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

    def texto(self) -> set[str]:
        return palabras(self.nombre, self.ingrediente, self.descripcion if not self.ingrediente else None)


def sujeto_de_propuesta(p: Propuesta) -> Sujeto:
    r = pr.Respuestas.model_validate_json(p.respuestas)
    principal = next((x for x in r.presentaciones if x.pvp_sugerido or x.costo_neto_sin_iva), r.presentaciones[0])
    mercado = [(precio, c.comercio or "sin comercio") for c in r.mercado.competidores
               if (precio := pr.numero(c.precio)) and precio > 0]
    forma = principal.forma_otro if principal.forma == "Otro" else principal.forma
    return Sujeto(tipo="propuesta", nombre=p.producto or principal.descripcion or "Sin nombre", marca=p.marca,
                  departamento=p.departamento or r.general.departamento, descripcion=principal.descripcion,
                  ingrediente=principal.ingrediente_principal, forma=forma, precio=pr.numero(principal.pvp_sugerido),
                  margen=pr.margen(principal), mercado=mercado, proveedor_smn=r.proveedor.es_proveedor_smn,
                  inscrito_gs1=r.proveedor.inscrito_gs1, apoyos=len([a for a in r.lanzamiento.apoyos if a.tipo]),
                  registro_sanitario=bool(principal.registro_sanitario), codigo_barras=principal.codigo_barras or None,
                  contenido=principal.contenido_neto or None,
                  proveedor_nombres=[x for x in (r.proveedor.razon_social, r.proveedor.nombre_comercial) if x])


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
    return Sujeto(tipo="idea", nombre=i.nombre, marca=i.marca, departamento=i.departamento, descripcion=i.descripcion,
                  ingrediente=i.ingrediente, forma=i.forma, precio=precio, margen=margen, costo=i.costo_estimado,
                  margen_nota=nota, proveedor_intelisis=i.proveedor_intelisis, mercado=mercado,
                  contenido=i.contenido or None, codigo_barras=i.codigo_barras or None, activo_g=activo,
                  proveedor_nombres=[i.proveedor_nuevo] if i.proveedor_nuevo else [])


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
                            mensaje=mensaje, max_tokens=300, esfuerzo="low",
                            contexto=puerta.ventana(INSTRUCCIONES_CLASIFICAR, mensaje, salida=300))
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


def mismo_de(s: Sujeto, parecidos: list[tuple[Producto, Decimal]]) -> Producto | None:
    """El producto del catálogo que es este mismo producto: misma marca, nombre y presentación."""
    return next((p for p, _ in parecidos if es_mismo(s, p)), None)


def raices(ps: set[str]) -> set[str]:
    """Las primeras 6 letras de cada palabra: «creatina» y «creatine», «magnesio» y «magnesium» cuentan como la misma
    (13 nov 2026: Birdman Creatine for Women no salía como parecido de una creatina)."""
    return {p[:6] for p in ps}


# Formato del producto (13 nov 2026, plan del reporte por producto aprobado por Diego: «sobre contra sobre»). Los del
# mismo grupo se comparan (un sobre de creatina y un bote de creatina en polvo sí; orégano seco y cápsulas de orégano no)
_FORMATOS = (
    ("sobre", {"sobre", "sobres", "sob", "stick", "sticks", "sachet", "sachets"}),
    ("capsula", {"cap", "caps", "capsula", "capsulas", "softgel", "softgels", "perlas"}),
    ("tableta", {"tab", "tabs", "tableta", "tabletas", "comprimidos", "grageas", "pastillas", "efervescentes"}),
    ("gomita", {"gomita", "gomitas", "gomas"}),
    ("polvo", {"polvo"}),
    ("liquido", {"liquido", "jarabe", "gotas", "bebida", "shot", "shots"}),
)
GRUPO_FORMATO = {"sobre": "polvo", "polvo": "polvo", "capsula": "solido", "tableta": "solido", "gomita": "gomita",
                 "liquido": "liquido"}
NOMBRE_FORMATO = {"sobre": "sobre", "polvo": "polvo", "capsula": "cápsulas", "tableta": "tabletas", "gomita": "gomitas",
                  "liquido": "líquido"}


def formato(*textos: str | None) -> str | None:
    """sobre, polvo, cápsula, tableta, gomita o líquido; el primer texto que lo diga (por palabra o, si no, por la
    unidad: solo mililitros es líquido y solo gramos es polvo)."""
    for texto in textos:
        if not texto:
            continue
        ps = set(re.findall(r"[a-zñ]+", _norm(texto)))
        for nombre, claves in _FORMATOS:
            if ps & claves:
                return nombre
        tam = tamano(texto)
        if set(tam) == {"ml"}:
            return "liquido"
        if set(tam) == {"g"}:
            return "polvo"
    return None


def formato_sujeto(s: Sujeto) -> str | None:
    return formato(s.forma, s.contenido, s.nombre)


def _con_precio(p: Producto) -> bool:
    return bool(p.precio_lista_con_impuestos) and p.precio_lista_con_impuestos >= PRECIO_MINIMO_PARECIDO


def buscar_parecidos(bd: Session, s: Sujeto, subcategoria: str | None, rama: str | None = None
                     ) -> list[tuple[Producto, Decimal]]:
    """Productos activos del catálogo que más se parecen.

    Busca en todo el catálogo, no solo en el departamento capturado (el departamento puede venir distinto). Lo que más
    pesa son las palabras del nombre que aparecen en la descripción del producto; la descripción larga de una idea solo
    suma un poco, para que no diluya el parecido. Suben la misma marca, la misma subcategoría, el mismo departamento y
    la misma forma. Al final se ordena por presentación (Plus 30 cápsulas antes que Plus 90 cápsulas) y el que es el
    mismo producto queda con 1.0.

    Desde el 11 nov 2026: debe compartir al menos una palabra del nombre; sin precio de lista (o de menos de $5) no
    cuenta como parecido; si se sabe la subcategoría, solo entran los de esa subcategoría (y, si son menos de 3, los de
    su misma rama); la misma descripción no se repite."""
    nombre = raices(palabras(s.nombre))
    clave = _clave_sujeto(s)
    todas = raices(s.texto())
    if not todas:
        return []
    marca = raices(palabras(s.marca))
    depto, forma = _norm(s.departamento).strip(), _norm(s.forma)
    medidas = set(tamano(s.contenido, s.nombre))
    suyo_formato = formato_sujeto(s)
    calificados = []
    for p in bd.scalars(select(Producto).where(Producto.activo == true())):
        otras = raices(palabras(p.descripcion))
        if not otras:
            continue
        mismo = es_mismo(s, p)
        # La marca del catálogo cuenta como parte del nombre («Krystal Stone» viene en la marca, no en la descripción);
        # de su misma subcategoría entra aunque no comparta palabras (un desodorante en barra de otra marca)
        su_sub = bool(subcategoria) and p.subcategoria == subcategoria
        misma_marca = bool(marca) and (marca <= raices(palabras(p.marca)) or marca <= otras)
        if not mismo and (not _con_precio(p) or (nombre and not su_sub and not nombre & (otras | raices(palabras(p.marca))))):
            continue
        cobertura = Decimal(len(nombre & otras)) / Decimal(len(nombre)) if nombre else Decimal(0)
        jaccard = Decimal(len(todas & otras)) / Decimal(len(todas | otras))
        sim = cobertura * Decimal("0.6") + jaccard * Decimal("0.4")
        if sim == 0 and not su_sub and not misma_marca:
            continue
        if misma_marca:
            sim += Decimal("0.2")
        if subcategoria and p.subcategoria == subcategoria:
            sim += Decimal("0.15")
        if depto and _norm(p.departamento).strip() == depto:
            sim += Decimal("0.05")
        if forma and forma in _norm(p.descripcion):
            sim += Decimal("0.05")
        if mismo:
            calificados.append((p, Decimal("1.000")))
            continue
        suya = _clave_producto(p)
        if clave:  # nombre y presentación completos, con números: separa variantes de la misma marca
            sim += Decimal(len(clave & suya)) / Decimal(len(clave | suya)) * Decimal("0.25")
        su_formato = formato(p.descripcion) if suyo_formato else None
        mismo_grupo = bool(su_formato) and GRUPO_FORMATO[suyo_formato] == GRUPO_FORMATO[su_formato]
        if su_formato == suyo_formato and su_formato:
            sim += Decimal("0.05")  # mismo formato, sobre contra sobre (13 nov 2026)
        # Del mismo grupo de formato no se descarta por la unidad: «30 sobres» y «sobre 5 g» o un bote de 348 g son la
        # misma forma de producto (13 nov 2026, caso Wonu: se quedaba sin parecidos)
        if not mismo_grupo and medidas and (suyas := set(tamano(p.descripcion))) and not medidas & suyas:
            if not (su_sub or misma_marca):
                continue  # otra forma de producto: orégano de 14 g no se parece a cápsulas de orégano (11 nov 2026)
            sim /= 2
        if sim >= MIN_SIMILITUD:
            calificados.append((p, min(sim, Decimal("0.99")).quantize(Decimal("0.001"))))
    calificados.sort(key=lambda x: (-x[1], x[0].sku))
    return _depurar(calificados, subcategoria, rama)[:MAX_COMPARABLES]


def _depurar(calificados: list[tuple[Producto, Decimal]], subcategoria: str | None,
             rama: str | None) -> list[tuple[Producto, Decimal]]:
    """Con subcategoría conocida se quedan los de esa subcategoría; si son menos de 3, se completan con los de la misma
    rama (o, sin rama, con los que no tienen subcategoría). Sin repetir la misma descripción."""
    vistos, unicos = set(), []
    for p, sim in calificados:
        llave = " ".join(sorted(presentacion(p.descripcion)))
        if llave not in vistos:
            vistos.add(llave)
            unicos.append((p, sim))
    if not subcategoria:
        return unicos
    propios = [(p, sim) for p, sim in unicos if sim == 1 or p.subcategoria == subcategoria]
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
                      vistos: dict[str, tuple[bool, str]] | None = None
                      ) -> tuple[list[tuple[Producto, Decimal]], list[tuple[Producto, str]]]:
    """La IA local revisa si cada parecido es de verdad el mismo tipo de producto y quita los que no (Diego eligió
    «Solo revisar parecidos», 12 nov 2026). Devuelve (los que quedan, los quitados con su motivo). El mismo producto
    (similitud 1) nunca se quita. Si la IA falla o contesta algo que no se entiende, se quedan todos, como antes.
    `vistos` guarda lo ya revisado por SKU para no volver a preguntar en la misma evaluación."""
    vistos = {} if vistos is None else vistos
    nuevos = [p for p, sim in parecidos if sim < 1 and p.sku not in vistos]
    if nuevos:
        mensaje = json.dumps({
            "producto": s.nombre, "marca": s.marca, "contenido": s.contenido, "forma": s.forma,
            "departamento": s.departamento, "descripcion": (s.descripcion or "")[:400] or None,
            "lista": [{"n": i, "producto": p.descripcion, "subcategoria": p.subcategoria}
                      for i, p in enumerate(nuevos, 1)],
        }, ensure_ascii=False)
        try:
            r = puerta.ejecutar(bd, TAREA_PARECIDOS, usuario_id=None, instrucciones=INSTRUCCIONES_PARECIDOS,
                                mensaje=mensaje, max_tokens=60 + 40 * len(nuevos), esfuerzo="low",
                                contexto=puerta.ventana(INSTRUCCIONES_PARECIDOS, mensaje, salida=60 + 40 * len(nuevos)))
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
        if sim >= 1 or si:
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
    minimo, provisional = margen_minimo(bd, s.departamento)
    # En el mínimo vale 60 (amarillo); cada punto arriba suma 8/3 hasta 100 a los 15 puntos. Abajo del mínimo baja
    # parejo hasta 0 en 15 % de margen (Diego, 11 nov 2026: con 6 por punto, 30.4 % contra 31 % ya casi no valía nada)
    dif = float(s.margen - minimo)
    abajo = 60 / float(minimo - PISO_MARGEN) if minimo > PISO_MARGEN else 6.0
    puntaje = 60 + dif * 40 / 15 if dif >= 0 else 60 + dif * abajo
    base = _acotar(puntaje)
    origen = ("provisional: Compras todavía no define el suyo" if provisional
              else "el que definió Compras en su Base de conocimiento")
    nota = f" ({s.margen_nota})" if s.margen_nota else ""
    minimo_texto = f"{minimo:.0f}" if minimo == minimo.to_integral_value() else f"{minimo:.1f}"
    detalle = (f"De cada $100 que se vende quedan ${_n(s.margen)} después de pagar el producto{nota}. Compras pide al "
               f"menos {minimo_texto} % ({origen}).")
    piso = (f"baja parejo hasta 0 con {_n(PISO_MARGEN)} % de margen" if minimo > PISO_MARGEN
            else "cada punto abajo resta 6")
    calculo = (f"Si deja justo el mínimo ({minimo_texto} %) saca 60. Cada punto de margen arriba del mínimo suma 2.7 "
               f"(con 15 puntos arriba llega a 100); abajo del mínimo {piso}. Este queda {_n(abs(dif))} puntos "
               f"{'arriba' if dif >= 0 else 'abajo'} del mínimo: {base}.")
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
    if final <= 80:
        meta = minimo + Decimal("7.6")
        mejora = (f"Para que este factor salga arriba de 80 tendría que dejar al menos {_n(meta)} % de margen (hoy {_n(s.margen)} %): con un precio "
                  "de venta más alto o un costo más bajo.")
        if dif < 0 and (lectura := _para_llegar(s, minimo, tope)):
            mejora = lectura
    if dif >= 0:
        valor = f"Deja {_n(s.margen)} % de margen, {_n(dif)} puntos arriba del mínimo ({minimo_texto} %)"
    else:
        valor = f"Margen bajo: deja {_n(s.margen)} %, {_n(-dif)} puntos abajo del mínimo ({minimo_texto} %)"
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


UNIDADES = {"kg": ("g", 1000), "kilo": ("g", 1000), "kilos": ("g", 1000), "g": ("g", 1), "gr": ("g", 1),
            "grs": ("g", 1), "gramos": ("g", 1), "l": ("ml", 1000), "lt": ("ml", 1000), "lts": ("ml", 1000),
            "litro": ("ml", 1000), "litros": ("ml", 1000), "ml": ("ml", 1), "mililitros": ("ml", 1),
            "m": ("m", 1), "metros": ("m", 1)}
UNIDADES.update({u: ("pz", 1) for u in (
    "cap", "caps", "capsula", "capsulas", "softgel", "softgels", "tab", "tabs", "tableta", "tabletas", "comprimidos",
    "sob", "sobre", "sobres", "pz", "pza", "pzas", "pzs", "pieza", "piezas", "tiras", "varitas", "toallitas",
    "gomita", "gomitas", "gomas", "perlas", "grageas", "pastillas")})
_CAPSULAS = {"cap", "caps", "capsula", "capsulas", "softgel", "softgels", "perlas"}  # ninguna pesa 3 g o más
NOMBRE_UNIDAD = {"g": "gramo", "ml": "mililitro", "pz": "pieza", "m": "metro"}
_TAMANO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(" + "|".join(sorted(UNIDADES, key=len, reverse=True)) + r")\b")


def tamano(*textos: str | None) -> dict[str, Decimal]:
    """Tamaño de la presentación por unidad: {"g": 120} para «120 g», {"pz": 15, "g": 79.5} para «15 tabletas de
    5.3 g c/u». Toma el primer texto que diga algo (el contenido antes que el nombre). Los mg no cuentan: son dosis."""
    for texto in textos:
        t = _norm(texto)
        salida: dict[str, Decimal] = {}
        unidad_pz = None
        for numero, unidad in _TAMANO.findall(t):
            dim, factor = UNIDADES[unidad]
            if dim == "pz" and "pz" not in salida:
                unidad_pz = unidad
            cantidad = Decimal(numero.replace(",", ".")) * factor
            if cantidad > 0 and dim not in salida:
                salida[dim] = cantidad
        cada = "c/u" in t or " cada" in t or re.search(r"\d\s*[a-z]+\s+(?:de|con|x)\s+\d", t)
        if "pz" in salida and cada:  # 15 tabletas de 5.3 g c/u = 79.5 g; 8 piezas de 100 g = 800 g
            if unidad_pz in _CAPSULAS and salida.get("g", 0) >= 3:
                salida.pop("g")  # «30 cápsulas de 346 g» es un error de captura (eran mg): solo cuentan las piezas
            for dim in ("g", "ml"):
                if dim in salida:
                    salida[dim] *= salida["pz"]
        if salida:
            return salida
    return {}


def _por_unidad(s: Sujeto, parecidos: list[tuple[Producto, Decimal]]
                ) -> tuple[str, Decimal, list[tuple[Producto, Decimal]]] | None:
    """Precio por gramo, mililitro o pieza del producto y de los parecidos que dicen su tamaño en la misma unidad.
    Se usa la unidad que comparten más parecidos. Si hay parecidos de tamaño cercano (de la mitad al doble) solo se
    usan esos: un bote de 2 kg siempre sale más barato por gramo que uno de 250 g (Diego, 11 nov 2026)."""
    suyo = tamano(s.contenido, s.nombre, s.descripcion)
    if not suyo or not s.precio:
        return None
    mejores = None
    for dim, cantidad in suyo.items():
        con_tam = [(p, tam[dim]) for p, _ in parecidos
                   if p.precio_lista_con_impuestos and dim in (tam := tamano(p.descripcion))]
        cercanos = [(p, x) for p, x in con_tam if cantidad / 2 <= x <= cantidad * 2]
        lista = [(p, p.precio_lista_con_impuestos / x) for p, x in (cercanos or con_tam)]
        if lista and (mejores is None or len(lista) > len(mejores[2])):
            mejores = (dim, s.precio / cantidad, lista)
    return mejores


def _precio_unidad(x: Decimal, dim: str) -> str:
    return f"${x:,.2f} por {NOMBRE_UNIDAD[dim]}" if x >= Decimal("0.1") else f"${x * 100:,.2f} por 100 {dim}"


def f_precio(s: Sujeto, parecidos: list[tuple[Producto, Decimal]], internet: mp.Mercado | None = None,
             mismo: Producto | None = None) -> Factor:
    """Contra lo que encontró el radar de precios en internet; si no encontró nada, contra lo que reportó el
    proveedor y, al final, contra el precio de lista de los parecidos que ya vendemos. Si ya lo vendemos, se compara
    nuestro precio contra el mercado (internet y el precio que se vio)."""
    nuestro = mismo.precio_lista_con_impuestos if mismo else None
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
    if s.mercado:
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
    if s.mercado:  # los que reportó el proveedor o, en una idea, el que se vio afuera (13 nov 2026)
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
    if not nuestros:
        return Factor(None, None, "Sin datos: no hay precios de la competencia ni de productos parecidos en SMN.")
    sin = "El radar de precios no lo encontró en internet. " if internet else ""
    if unidad := _por_unidad(s, parecidos):  # 11 nov 2026: 120 g a $184 no se compara contra 60 g a $131
        dim, propio, lista = unidad
        en_rango = [(p, x) for p, x in lista if RANGO_PRECIO[0] <= propio / x <= RANGO_PRECIO[1]]
        dentro = [x for _, x in en_rango]
        if dentro:
            med = Decimal(str(median(dentro)))
            ratio = propio / med
            cantidad = tamano(s.contenido, s.nombre, s.descripcion)[dim]
            contra = "; ".join(f"{p.descripcion} {_pesos(p.precio_lista_con_impuestos)} ({_precio_unidad(x, dim)})"
                               for p, x in en_rango[:4])
            return Factor(_por_precio(ratio), _precio_valor(ratio, f"nuestros parecidos, por {NOMBRE_UNIDAD[dim]}"),
                          f"{que} {_pesos(s.precio)} por {_n(cantidad)} {dim}: sale a {_precio_unidad(propio, dim)}. "
                          f"Nuestros parecidos salen, en medio, a {_precio_unidad(med, dim)}: {contra}. {sin}"
                          "No es precio de la competencia.", True,
                          *_precio_explicado(ratio, med * cantidad, f"nuestros parecidos por {NOMBRE_UNIDAD[dim]}"), meta=med * cantidad)
    comparables = [p for p in nuestros if RANGO_PRECIO[0] <= s.precio / p <= RANGO_PRECIO[1]]
    contra = "; ".join(f"{p.descripcion} {_pesos(p.precio_lista_con_impuestos)}" for p, _ in parecidos
                       if p.precio_lista_con_impuestos in comparables[:4])
    if not comparables:
        return Factor(None, None, f"Sin datos: no hay precios de internet y nuestros parecidos cuestan muy distinto "
                      f"({_pesos(min(nuestros))} a {_pesos(max(nuestros))} contra {_pesos(s.precio)}); no parecen la "
                      "misma presentación, así que no se comparan.")
    nuestros = comparables
    med = Decimal(str(median(nuestros)))
    ratio = s.precio / med
    return Factor(_por_precio(ratio), _precio_valor(ratio, "nuestros parecidos"),
                  f"{que} {_pesos(s.precio)} contra {_pesos(med)}, el precio de en medio de nuestros parecidos: "
                  f"{contra}. {sin}No es precio de la competencia.", True,
                  *_precio_explicado(ratio, med, "nuestros parecidos"), meta=med)


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
    }


def mercado_de(bd: Session, e: ProductoEvaluacion, s: Sujeto) -> mp.Mercado | None:
    """Busca el producto en internet, o reusa lo que encontró una evaluación de la última semana."""
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
                            max_tokens=300, esfuerzo="low",
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
    return Factor(puntaje, f"{'Una señal' if len(con) == 1 else f'{len(con)} señales'} en internet; la más fuerte, "
                  f"{mejor.nivel.lower()}",
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
    iguales = [p for p, sim in parecidos if sim >= Decimal("0.8")]
    cercanos = [p for p, sim in parecidos if sim >= Decimal("0.5")]
    venta = rr.venta_por_sku(bd, v, [p.sku for p in cercanos]) if v and cercanos else {}
    if iguales:
        detalle += " Parece que ya vendemos este producto o uno de la misma línea: " + ", ".join(f"{p.sku} {p.descripcion}" for p in iguales[:3]) + "."
        if any(p.sku in venta for p in iguales):
            puntaje -= 5
            calculo += " Resta 5 porque ya vendemos uno igual o de la misma línea."
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

def f_demanda(bd: Session, s: Sujeto, parecidos: list[tuple[Producto, Decimal]], v: rr.Ventana | None,
              mismo: Producto | None = None) -> Factor:
    if not v:
        return Factor(None, None, "Sin datos: todavía no hay ventas cargadas de SMNBI.")
    depto = (mismo.departamento if mismo else None) or s.departamento
    ritmo = {sku: x.por_tienda_mes for sku, x in rr.venta_por_sku(bd, v, departamento=depto).items()}
    if depto and len(ritmo) < 5:  # el departamento capturado casi no tiene venta: se compara contra toda la cadena
        depto = None
        ritmo = {sku: x.por_tienda_mes for sku, x in rr.venta_por_sku(bd, v).items()}
    suyos = rr.venta_por_sku(bd, v, [p.sku for p, _ in parecidos])
    # Si ya lo vendemos, cuenta su propia venta y no el promedio de la línea
    propio = mismo is not None and mismo.sku in suyos
    if propio:
        suyos = {mismo.sku: suyos[mismo.sku]}
    if not suyos:
        return Factor(None, None, f"Sin datos: los productos parecidos no tienen venta en la {v.texto()}.")
    if len(ritmo) < 5:
        return Factor(None, None, f"Sin datos: hay muy pocos productos con venta para comparar en la {v.texto()}.")
    promedio = sum(x.por_tienda_mes for x in suyos.values()) / len(suyos)
    percentil = sum(1 for r in ritmo.values() if r <= promedio) / len(ritmo) * 100
    con, total = rr.tiendas_con_venta(bd, v, list(suyos))
    quien = (f"Ya vendemos este mismo producto ({mismo.sku} {mismo.descripcion}): en la {v.texto()}"
             if propio else f"Promedio de {len(suyos)} parecido(s) en la {v.texto()}:")
    detalle = (f"{quien} se vende{'n' if not propio else ''} en {con} de {total} tiendas, con {promedio:,.1f} piezas por "
               f"tienda al mes, y vende{'n' if not propio else ''} más que el {percentil:.0f} % de los {len(ritmo)} "
               f"productos con venta{' del departamento' if depto else ' de toda la cadena'}.")
    # Tendencia de los parecidos: últimas 13 semanas contra las 13 anteriores, ±10 puntos a lo más
    recientes, anteriores = sum(x.recientes for x in suyos.values()), sum(x.anteriores for x in suyos.values())
    # La escala se abre alrededor de 50 (recalibración del 9 nov 2026: los más vendidos casi no se separaban del resto)
    puntaje = 50 + (percentil - 50) * ESTIRA_DEMANDA
    donde = "del departamento" if depto else "de toda la cadena"
    calculo = (f"La calificación es qué tan arriba quedan en la lista de venta: venden más que {percentil:.0f} de cada "
               f"100 productos {donde}. La escala se abre alrededor de la mitad (50 + la distancia a 50 por "
               f"{_n(ESTIRA_DEMANDA)}), así que empieza en {_acotar(puntaje)}.")
    if anteriores > 0:
        cambio = (recientes / anteriores - 1) * 100
        ajuste = max(-10.0, min(10.0, cambio / 3))
        puntaje += ajuste
        detalle += f" Sus últimas {rr.SEMANAS_TENDENCIA} semanas van {cambio:+.0f} % contra las {rr.SEMANAS_TENDENCIA} anteriores."
        calculo += (f" Luego se ajusta por cómo va su venta, 1 punto por cada 3 % de cambio y máximo 10: {cambio:+.0f} % "
                    f"da {ajuste:+.0f}.")
    final = _acotar(puntaje)
    quienes = "este producto" if propio else "sus parecidos"
    mejora = None if final > 80 else (f"Para que este factor salga arriba de 80, {quienes} tendría"
                                      f"{'n' if not propio else ''} que vender más que {_percentil_para(81)} de cada 100 productos {donde}, "
                                      "o venir creciendo.")
    nivel = ("Se vende muy bien" if percentil >= 80 else "Se vende bien" if percentil >= 60
             else "Venta media" if percentil >= 40 else "Se vende poco")
    return Factor(final, f"{nivel}: {'vende' if propio else 'sus parecidos venden'} más que {percentil:.0f} de cada "
                  f"100 productos ({promedio:,.1f} piezas por tienda al mes)", detalle, False,
                  f"{calculo} Calificación: {final}.",
                  mejora)

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

def pesos(bd: Session) -> tuple[dict[str, Decimal], str]:
    filas = {p.factor: p.puntos for p in bd.scalars(select(ConocimientoPeso))}
    if set(filas) == set(FACTORES) and sum(filas.values()) == 100:
        return {f: Decimal(filas[f]) for f in FACTORES}, "compras"
    igual = (Decimal(100) / len(FACTORES)).quantize(Decimal("0.01"))
    return {f: igual for f in FACTORES}, "iguales"


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
    cubierto = sum((peso[f] for f in con_datos), Decimal(0))
    total = sum((p for f, p in peso.items() if f not in fuera), Decimal(0))
    parte = cubierto / total if total else Decimal(0)
    confianza = "alta" if parte >= Decimal("0.8") else "media" if parte >= Decimal("0.5") else "baja"
    if not cubierto:
        return None, "baja"
    return _entero(sum(peso[f] * x.puntaje for f, x in con_datos.items()) / cubierto), confianza


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
    if clasificacion is not None:
        e.rama, e.subcategoria, e.segmento = clasificacion
        e.clasificacion_origen = "compras"
    elif anterior and anterior.clasificacion_origen == "compras":
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

    try:
        paso(1, "clasificando el producto")
        if e.propuesta_id:
            p = bd.get(Propuesta, e.propuesta_id)
            s = sujeto_de_propuesta(p)
            s.proveedor_intelisis = bd.scalar(select(OrganizacionExterna.proveedor_intelisis).where(
                OrganizacionExterna.organizacion_id == p.organizacion_id))
        else:
            s = sujeto_de_idea(bd.get(ProductoIdea, e.idea_id))
        e.departamento = s.departamento
        fijados = bool(e.comparables)
        vistos: dict[str, tuple[bool, str]] = {}
        quitados: list[tuple[Producto, str]] = []
        if e.clasificacion_origen != "compras":
            # Se clasifica con los parecidos que la IA ya revisó (v0.4)
            sin_sub, _ = revisar_parecidos(bd, s, buscar_parecidos(bd, s, None), vistos) if not fijados else (None, [])
            e.rama, e.subcategoria, e.segmento = clasificar(bd, s, sin_sub)
            e.clasificacion_origen = "ia" if e.subcategoria else "sin_clasificar"

        paso(2, "buscando productos parecidos en el catálogo y revisándolos con la IA")
        if fijados:  # Compras los fijó: no se revisan
            parecidos = [(bd.get(Producto, c.producto_id), c.similitud) for c in e.comparables]
        else:
            parecidos, quitados = revisar_parecidos(bd, s, buscar_parecidos(bd, s, e.subcategoria, e.rama), vistos)
        mismo = mismo_de(s, parecidos)
        if not e.subcategoria and e.clasificacion_origen != "compras":
            if fuente := mismo or subcategoria_de_parecidos(parecidos):
                e.rama, e.subcategoria, e.segmento = fuente.rama, fuente.subcategoria, fuente.segmento
                e.clasificacion_origen = "parecidos"
                if not fijados:  # ya con subcategoría, se quitan los de otra (11 nov 2026)
                    parecidos = _depurar(parecidos, e.subcategoria, e.rama)
        if not fijados:
            for i, (p, sim) in enumerate(parecidos, 1):
                e.comparables.append(EvaluacionComparable(producto_id=p.producto_id, rango=i, similitud=sim, origen="sistema"))
        for c in e.comparables:
            if mismo and c.producto_id == mismo.producto_id:
                c.similitud = Decimal(1)  # así la pantalla lo muestra como «Ya lo vendemos»

        paso(3, "buscando precios en internet y en las tiendas")
        internet = mercado_de(bd, e, s)
        if internet:
            e.mercado = internet.a_json()
        paso(4, "calculando demanda, margen, precio, surtido y proveedor con la venta de SMNBI")
        v = rr.ventana(bd)
        precio = f_precio(s, parecidos, internet, mismo)
        factores = {
            "demanda": f_demanda(bd, s, parecidos, v, mismo),
            "rentabilidad": f_rentabilidad(bd, s, e.subcategoria, v, mismo, precio.meta),
            "precio": precio,
            "categoria": f_categoria(bd, s, e.subcategoria, parecidos, v, mismo),
            "proveedor": f_proveedor(bd, s, parecidos),
        }
        paso(5, "revisando las tendencias de internet")
        factores["tendencia"] = f_tendencia(bd, s, hoy, e.subcategoria)
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
        e.explicacion = (dictamen(s, e.color, factores, parecidos, margen_minimo(bd, s.departamento)[0],
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
        if not revision.rechazo and revision.avisos:
            titulos = ", ".join(f"«{x['titulo']}»" for x in revision.avisos[:2])
            e.explicacion = (f"Aviso: podría caer en la regla {titulos} de Compras, pero no hay un dato del producto que "
                             f"lo pruebe. No cambia el color; que Compras lo confirme.\n\n{e.explicacion}")
        e.estado, e.avance = "lista", None
    except Exception as ex:  # noqa: BLE001
        log.exception("Radar de productos: falló la evaluación %s", evaluacion_id)
        bd.rollback()
        e = bd.get(ProductoEvaluacion, evaluacion_id)
        e.estado, e.avance, e.error = "fallida", None, f"No se pudo evaluar: {str(ex)[:900]}"
    e.terminada_en = ahora()
    bd.commit()
    if e.estado == "lista":  # una idea sin proveedor que salió bien se vuelve búsqueda de proveedor (2026-11-09)
        from modulos.compras import busquedas

        busquedas.despues_de_evaluar(bd, e)
    return e


DICTAMEN = "Dictamen: "


def dictamen(s: Sujeto, color: str, factores: dict[str, Factor], parecidos: list[tuple[Producto, Decimal]],
             minimo: Decimal | None, rechazo: dict | None = None) -> str:
    """Lectura de comprador en una línea: meter, negociar o no meter, con el precio o costo meta y contra qué se compara.
    Sale de los números del semáforo, no de la IA (Diego, 11 nov 2026: «que actúe como experto en compras»)."""
    if rechazo:
        return f"{DICTAMEN}No meter: cae en la regla «{rechazo.get('titulo')}» de Compras."
    pts = {f: x.puntaje for f, x in factores.items()}
    demanda, precio, rent = pts.get("demanda"), pts.get("precio"), pts.get("rentabilidad")
    bajo_margen = s.margen is not None and minimo is not None and s.margen < minimo
    partes = []
    if color == "verde":
        veredicto = "Meter"
    elif demanda is not None and demanda < 40 and color == "rojo":
        veredicto = "No meter: lo parecido casi no se vende en nuestras tiendas"
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
        ref = factores["precio"].meta if "precio" in factores else None
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
    elif precio is not None and precio < 60 and (m := factores.get("precio")) and m.meta and s.precio:
        partes.append(f"para competir tendría que venderse en unos {_pesos(m.meta)} (hoy {_pesos(s.precio)})")
    con_precio = [(p, sim) for p, sim in parecidos if p.precio_lista_con_impuestos][:2]
    if con_precio:
        partes.append("se compara con " + " y ".join(f"{p.descripcion} ({_pesos(p.precio_lista_con_impuestos)})"
                                                     for p, _ in con_precio))
    resto = "; ".join(partes)
    if partes and ":" in veredicto:  # «No meter: lo parecido casi no se vende. Pedir costo…» (con mayúscula)
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
