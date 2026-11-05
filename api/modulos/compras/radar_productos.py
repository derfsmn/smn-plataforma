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
"""
import json
import logging
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
TAREA_TENDENCIA = "compras.productos_tendencia"
MAX_COMPARABLES = 10
MIN_SIMILITUD = Decimal("0.15")
DIAS_SENALES = 180
NIVEL_SENAL = {"ALTA": 100, "MEDIA": 80, "TEMPRANA": 65}
SIN_SENAL = 60  # nada habla de este producto: no suma ni resta (calibración del 27 oct: con 35 hundía a casi todos)
CALC_TENDENCIA = ("Toma la señal más fuerte del radar de tendencias que habla del producto: alta = 100, media = 80, "
                  "temprana = 65. Si ninguna habla de él, saca 60: no suma ni resta.")
IVA_SUPUESTO = Decimal("16")  # solo para ideas con costo estimado; se dice en el detalle
PALABRAS_VACIAS = {
    "de", "del", "la", "el", "los", "las", "con", "sin", "para", "por", "en", "y", "o", "un", "una", "al", "a",
    "mg", "gr", "g", "ml", "kg", "lt", "pza", "pzas", "piezas", "caps", "capsulas", "tabs", "tabletas", "frasco",
    "polvo", "liquido", "gomitas", "sobres", "natural", "naturales", "plus", "premium",
}


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
    margen, nota = None, None
    if i.costo_estimado and i.precio_visto:
        base = i.precio_visto / (1 + IVA_SUPUESTO / 100)
        margen = ((base - i.costo_estimado) / base * 100).quantize(Decimal("0.01"))
        nota = "con el costo estimado y el precio visto, suponiendo IVA de 16 %"
    return Sujeto(tipo="idea", nombre=i.nombre, marca=i.marca, departamento=i.departamento, descripcion=i.descripcion,
                  ingrediente=i.ingrediente, forma=i.forma, precio=i.precio_visto, margen=margen, costo=i.costo_estimado,
                  margen_nota=nota, proveedor_intelisis=i.proveedor_intelisis,
                  proveedor_nombres=[i.proveedor_nuevo] if i.proveedor_nuevo else [])


# ---------------------------------------------------------------- clasificación y parecidos

INSTRUCCIONES_CLASIFICAR = """Eres analista de Compras de una cadena de tiendas naturistas en México.
Te doy un producto nuevo y la lista de ramas, subcategorías y segmentos que ya existen en el catálogo.
Elige la combinación que mejor le queda, copiándola EXACTAMENTE de la lista. Si ninguna le queda, contesta nulos.
Contesta solo JSON: {"rama": "...", "subcategoria": "...", "segmento": "..."}"""


def opciones_clasificacion(bd: Session, departamento: str | None) -> list[tuple[str, str, str]]:
    q = (select(Producto.rama, Producto.subcategoria, Producto.segmento).distinct()
         .where(Producto.activo == true(), Producto.subcategoria.is_not(None)))
    filas = bd.execute(q.where(Producto.departamento == departamento).limit(300)).all() if departamento else []
    if not filas:  # el departamento no tiene subcategorías (o no hay departamento): las de todo el catálogo
        filas = bd.execute(q.limit(300)).all()
    return [(r or "", s or "", g or "") for r, s, g in filas]


def clasificar(bd: Session, s: Sujeto) -> tuple[str | None, str | None, str | None]:
    """La IA sugiere rama, subcategoría y segmento de entre los que existen. Si falla, queda sin clasificar."""
    opciones = opciones_clasificacion(bd, s.departamento)
    if not opciones:
        return None, None, None
    mensaje = json.dumps({
        "producto": s.nombre, "marca": s.marca, "departamento": s.departamento, "descripcion": s.descripcion,
        "ingrediente_principal": s.ingrediente, "forma": s.forma,
        "opciones": [{"rama": r, "subcategoria": c, "segmento": g} for r, c, g in opciones],
    }, ensure_ascii=False)
    try:
        r = puerta.ejecutar(bd, TAREA_CLASIFICAR, usuario_id=None, instrucciones=INSTRUCCIONES_CLASIFICAR,
                            mensaje=mensaje, max_tokens=300, esfuerzo="low")
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


def buscar_parecidos(bd: Session, s: Sujeto, subcategoria: str | None) -> list[tuple[Producto, Decimal]]:
    """Productos activos del catálogo que más se parecen.

    Busca en todo el catálogo, no solo en el departamento capturado (el departamento puede venir distinto). Lo que más
    pesa son las palabras del nombre que aparecen en la descripción del producto; la descripción larga de una idea solo
    suma un poco, para que no diluya el parecido. Suben la misma marca, la misma subcategoría, el mismo departamento y
    la misma forma. Al final se ordena por presentación (Plus 30 cápsulas antes que Plus 90 cápsulas) y el que es el
    mismo producto queda con 1.0."""
    nombre = palabras(s.nombre)
    clave = _clave_sujeto(s)
    todas = s.texto()
    if not todas:
        return []
    marca = palabras(s.marca)
    depto, forma = _norm(s.departamento).strip(), _norm(s.forma)
    calificados = []
    for p in bd.scalars(select(Producto).where(Producto.activo == true())):
        otras = palabras(p.descripcion)
        if not otras:
            continue
        cobertura = Decimal(len(nombre & otras)) / Decimal(len(nombre)) if nombre else Decimal(0)
        jaccard = Decimal(len(todas & otras)) / Decimal(len(todas | otras))
        sim = cobertura * Decimal("0.6") + jaccard * Decimal("0.4")
        if sim == 0:
            continue
        if marca and (marca <= palabras(p.marca) or marca <= otras):
            sim += Decimal("0.2")
        if subcategoria and p.subcategoria == subcategoria:
            sim += Decimal("0.15")
        if depto and _norm(p.departamento).strip() == depto:
            sim += Decimal("0.05")
        if forma and forma in _norm(p.descripcion):
            sim += Decimal("0.05")
        if es_mismo(s, p):
            calificados.append((p, Decimal("1.000")))
            continue
        suya = _clave_producto(p)
        if clave:  # nombre y presentación completos, con números: separa variantes de la misma marca
            sim += Decimal(len(clave & suya)) / Decimal(len(clave | suya)) * Decimal("0.25")
        if sim >= MIN_SIMILITUD:
            calificados.append((p, min(sim, Decimal("0.99")).quantize(Decimal("0.001"))))
    calificados.sort(key=lambda x: (-x[1], x[0].sku))
    return calificados[:MAX_COMPARABLES]


# ---------------------------------------------------------------- factores

@dataclass
class Factor:
    puntaje: int | None
    valor: str | None
    detalle: str  # qué encontramos
    provisional: bool = False
    calculo: str | None = None  # cómo se llegó a la calificación, con sus números
    mejora: str | None = None  # qué tendría que pasar para que suba (o qué significa)


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
                   mismo: Producto | None = None) -> Factor:
    if mismo and v and (real := rr.margen_sku(bd, v, mismo.sku)):
        # Ya lo vendemos: cuenta su margen real, no el estimado (el precio visto suele ser el de la competencia)
        capturado = f"; con lo capturado daría {s.margen} %" if s.margen is not None else ""
        s = Sujeto(**{**s.__dict__, "margen": real, "margen_nota": f"margen real del mismo producto que ya vendemos, "
                      f"{mismo.sku}, en la {v.texto()}{capturado}"})
    if s.margen is None:
        if s.tipo == "propuesta":
            falta = "el costo y el precio sugerido"
        else:
            falta = " y ".join(x for x, hay in (("el costo estimado", s.costo), ("el precio que se vio", s.precio)) if not hay)
        return Factor(None, None, f"Sin datos: falta {falta}. Con los dos se calcula el margen.")
    minimo, provisional = margen_minimo(bd, s.departamento)
    # En el mínimo vale 60 (amarillo); cada punto arriba suma 8/3 hasta 100 a los 15 puntos; cada punto abajo resta 6
    dif = float(s.margen - minimo)
    puntaje = 60 + dif * 40 / 15 if dif >= 0 else 60 + dif * 6
    base = _acotar(puntaje)
    origen = ("provisional: Compras todavía no define el suyo" if provisional
              else "el que definió Compras en su Base de conocimiento")
    nota = f" ({s.margen_nota})" if s.margen_nota else ""
    minimo_texto = f"{minimo:.0f}" if minimo == minimo.to_integral_value() else f"{minimo:.1f}"
    detalle = (f"Deja {_n(s.margen)} % de margen{nota}: de cada $100 que se vende, ${_n(s.margen)} quedan después de "
               f"pagar el producto. El mínimo es {minimo_texto} % ({origen}).")
    calculo = (f"Si deja justo el mínimo ({minimo_texto} %) saca 60. Cada punto de margen arriba del mínimo suma 2.7 "
               f"(con 15 puntos arriba llega a 100) y cada punto abajo resta 6. Este queda {_n(dif)} puntos "
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
        detalle += (f" Los {n} productos de la subcategoría «{subcategoria}» dejan en realidad {margen_sub} % "
                    f"({v.texto()}); este producto queda {float(s.margen - margen_sub):+.1f} puntos.")
    final = _acotar(puntaje)
    mejora = None
    if final <= 80:
        meta = minimo + Decimal("7.6")
        mejora = (f"Para que este factor salga arriba de 80 tendría que dejar al menos {_n(meta)} % de margen (hoy {_n(s.margen)} %): con un precio "
                  "de venta más alto o un costo más bajo.")
    return Factor(final, f"Deja {_n(s.margen)} % de margen (mínimo {minimo_texto} %)", detalle, provisional,
                  calculo + (f"{ajuste} Calificación: {final}." if ajuste else ""), mejora)

def _por_precio(ratio: Decimal) -> int:
    # Igual al mercado vale 70; cada 1 % más caro resta 2 puntos y cada 1 % más barato suma 2
    return _acotar(70 - float(ratio - 1) * 200)


def _precio_valor(ratio: Decimal, contra: str) -> str:
    pct = float(ratio - 1) * 100
    if round(pct) == 0:
        return f"Igual que {contra}"
    return f"{abs(pct):.0f} % {'más caro' if pct > 0 else 'más barato'} que {contra}"


def _precio_explicado(ratio: Decimal, referencia: Decimal, contra: str) -> tuple[str, str | None]:
    """Cómo se calificó el precio y qué precio haría falta para verde."""
    pct = float(ratio - 1) * 100
    if round(pct) == 0:
        donde = "Está prácticamente igual"
    else:
        donde = f"Está {abs(pct):.0f} % {'más caro' if pct > 0 else 'más barato'}"
    calculo = (f"Si cuesta lo mismo que {contra} saca 70. Cada 1 % más caro resta 2 puntos y cada 1 % más barato suma "
               f"2. {donde}: {_por_precio(ratio)}.")
    mejora = None
    if _por_precio(ratio) <= 80:
        mejora = (f"Para que este factor salga arriba de 80 tendría que venderse en "
                  f"{_pesos(referencia * Decimal('0.949'))} o menos, es decir, "
                  f"al menos 5 % abajo de {contra}.")
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
        return Factor(_por_precio(ratio), "Nuestro precio: " + _precio_valor(ratio, "el mercado").lower(),
                      f"Ya lo vendemos ({mismo.sku}) a {_pesos(nuestro)}. El precio de en medio del mercado es "
                      f"{_pesos(med)} ({' y '.join(x for x in donde if x)}).{_fuera_texto(fuera)}", False,
                      *_precio_explicado(ratio, med, "el precio de en medio del mercado"))
    if s.precio is None or s.precio <= 0:
        return Factor(None, None, "Sin datos: falta el precio de venta." if s.tipo == "propuesta"
                      else "Sin datos: falta el precio que se vio.")
    que = "Precio sugerido" if s.tipo == "propuesta" else "Precio visto"
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
    internet, fuera = _en_rango(internet, nuestros_med or s.precio)
    extra += _fuera_texto(fuera)
    if internet and internet.precios:
        med = internet.mediana()
        ratio = s.precio / med
        google = [p["vendedor"] for p in internet.precios if p["fuente"] == "google"]
        sitios = [p["vendedor"] for p in internet.precios if p["fuente"] == "sitio"]
        donde = "; ".join(x for x in (f"Google Shopping: {_vendedores(google)}" if google else "",
                                       f"sitio de {_vendedores(sitios)}" if sitios else "") if x)
        return Factor(_por_precio(ratio), _precio_valor(ratio, "en internet"),
                      f"{que} {_pesos(s.precio)} contra {_pesos(med)}, el precio de en medio de {len(internet.precios)} "
                      f"precio(s) que encontró el radar de precios ({donde}).{extra}", False,
                      *_precio_explicado(ratio, med, "el precio de en medio de internet"))
    if s.tipo == "propuesta" and s.mercado:
        med = Decimal(str(median([p for p, _ in s.mercado])))
        ratio = s.precio / med
        donde = ", ".join(sorted({c for _, c in s.mercado}))
        sin = " El radar de precios no lo encontró en internet." if internet else ""
        return Factor(_por_precio(ratio), _precio_valor(ratio, "la competencia que reportó el proveedor"),
                      f"Precio sugerido {_pesos(s.precio)} contra {_pesos(med)}, el precio de en medio de "
                      f"{len(s.mercado)} precio(s) que reportó el proveedor ({donde}); no está confirmado.{sin}", True,
                      *_precio_explicado(ratio, med, "el precio de en medio de la competencia"))
    if not nuestros:
        return Factor(None, None, "Sin datos: no hay precios de la competencia ni de productos parecidos en SMN.")
    comparables = [p for p in nuestros if RANGO_PRECIO[0] <= s.precio / p <= RANGO_PRECIO[1]]
    if not comparables:
        return Factor(None, None, f"Sin datos: no hay precios de internet y nuestros parecidos cuestan muy distinto "
                      f"({_pesos(min(nuestros))} a {_pesos(max(nuestros))} contra {_pesos(s.precio)}); no parecen la "
                      "misma presentación, así que no se comparan.")
    nuestros = comparables
    med = Decimal(str(median(nuestros)))
    ratio = s.precio / med
    sin = "El radar de precios no lo encontró en internet. " if internet else ""
    return Factor(_por_precio(ratio), _precio_valor(ratio, "nuestros parecidos"),
                  f"{que} {_pesos(s.precio)} contra {_pesos(med)}, el precio de lista de en medio de {len(nuestros)} "
                  f"producto(s) parecido(s) que ya vendemos. {sin}No es precio de la competencia.", True,
                  *_precio_explicado(ratio, med, "nuestros parecidos"))


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
                            max_tokens=300, esfuerzo="low")
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
        return Factor(SIN_SENAL, "Nadie habla de él en internet", f"Ninguna de las {len(senales)} señales del radar de tendencias de los "
                      f"últimos 6 meses habla de este producto o su ingrediente; no suma ni resta. {como}", True,
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
        puntaje = 90 if r <= 0.25 else 80 if r <= 0.5 else 70 if r <= 1 else 60 if r <= 2 else 45 if r <= 4 else 35
        detalle = (f"Hay {n} producto(s) activos en la subcategoría «{subcategoria}»; una subcategoría típica del catálogo "
                   f"tiene {tipica:.0f}. Menos productos, más hueco en el surtido (escala provisional hasta que Compras "
                   "defina cuántos caben).")
        calculo = (f"Compara cuántos productos hay en su subcategoría contra una típica ({tipica:.0f}): la cuarta parte o "
                   "menos = 90, la mitad o menos = 80, lo mismo o menos = 70, hasta el doble = 60, hasta 4 veces = 45, "
                   f"más = 35. Aquí hay {n}: {puntaje}.")
    else:
        n = len([1 for _, sim in parecidos if sim >= Decimal("0.3")])
        puntaje = 90 if n == 0 else 75 if n <= 3 else 65 if n <= 7 else 55
        detalle = (f"Hay {n} producto(s) activos muy parecidos (sin subcategoría confirmada). Menos productos, más hueco "
                   "en el surtido (escala provisional hasta que Compras defina cuántos caben).")
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
        detalle += (f" Con el inventario del {corte:%d/%m/%Y} la subcategoría tiene para {dias:,.0f} días de venta "
                    f"({con_existencia} productos con existencia).")
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
    valor = (f"{n} productos en su subcategoría (una típica tiene {tipica:.0f})" if subcategoria
             else f"{n} productos muy parecidos en el catálogo")
    return Factor(final, valor, detalle, True,
                  f"Alto quiere decir que llena un hueco del surtido; bajo, que ya tenemos muchos parecidos. {calculo} "
                  f"Calificación: {final}.")

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
    puntaje = percentil
    donde = "del departamento" if depto else "de toda la cadena"
    calculo = (f"La calificación es qué tan arriba quedan en la lista de venta: venden más que {percentil:.0f} de cada "
               f"100 productos {donde}, así que empieza en {percentil:.0f}.")
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
                                      f"{'n' if not propio else ''} que vender más que 8 de cada 10 productos {donde}, "
                                      "o venir creciendo.")
    return Factor(final, f"{'Vende' if propio else 'Sus parecidos venden'} {promedio:,.1f} piezas por tienda al mes; más "
                  f"que {percentil:.0f} de cada 100 productos", detalle, False, f"{calculo} Calificación: {final}.",
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
    if fuera:
        nombres = " y ".join(NOMBRES[f].lower() for f in FACTORES if f in fuera)
        inicio = ("**Es una oportunidad:** la pregunta es si vale la pena buscarle proveedor." if oportunidad else
                  "**Sin proveedor actual:** se califica con el semáforo para productos sin proveedor.")
        partes.insert(0, f"{inicio} {nombres.capitalize()} se califican al conseguirlo y no bajan la confianza.")
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
        if e.clasificacion_origen != "compras":
            e.rama, e.subcategoria, e.segmento = clasificar(bd, s)
            e.clasificacion_origen = "ia" if e.subcategoria else "sin_clasificar"

        paso(2, "buscando productos parecidos en el catálogo")
        if e.comparables:  # Compras los fijó
            parecidos = [(bd.get(Producto, c.producto_id), c.similitud) for c in e.comparables]
        else:
            parecidos = buscar_parecidos(bd, s, e.subcategoria)
            for i, (p, sim) in enumerate(parecidos, 1):
                e.comparables.append(EvaluacionComparable(producto_id=p.producto_id, rango=i, similitud=sim, origen="sistema"))
        mismo = mismo_de(s, parecidos)
        for c in e.comparables:
            if mismo and c.producto_id == mismo.producto_id:
                c.similitud = Decimal(1)  # así la pantalla lo muestra como «Ya lo vendemos»
        if not e.subcategoria and e.clasificacion_origen != "compras":
            if fuente := mismo or subcategoria_de_parecidos(parecidos):
                e.rama, e.subcategoria, e.segmento = fuente.rama, fuente.subcategoria, fuente.segmento
                e.clasificacion_origen = "parecidos"

        paso(3, "buscando precios en internet y en las tiendas")
        internet = mercado_de(bd, e, s)
        if internet:
            e.mercado = internet.a_json()
        paso(4, "calculando demanda, margen, precio, surtido y proveedor con la venta de SMNBI")
        v = rr.ventana(bd)
        factores = {
            "demanda": f_demanda(bd, s, parecidos, v, mismo),
            "rentabilidad": f_rentabilidad(bd, s, e.subcategoria, v, mismo),
            "precio": f_precio(s, parecidos, internet, mismo),
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
        if mismo:
            e.explicacion = (f"Ojo: ya vendemos este mismo producto ({mismo.sku} {mismo.descripcion}). Los números son los de "
                             f"ese producto.\n\n{e.explicacion}")
        if r := revision.rechazo:
            e.explicacion = f"Rechazo directo por la regla «{r['titulo']}» de Compras: {r['motivo']}\n\n{e.explicacion}"
        e.estado, e.avance = "lista", None
    except Exception as ex:  # noqa: BLE001
        log.exception("Radar de productos: falló la evaluación %s", evaluacion_id)
        bd.rollback()
        e = bd.get(ProductoEvaluacion, evaluacion_id)
        e.estado, e.avance, e.error = "fallida", None, f"No se pudo evaluar: {str(ex)[:900]}"
    e.terminada_en = ahora()
    bd.commit()
    return e


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
