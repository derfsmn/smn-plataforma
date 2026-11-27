"""Pantalla del comité de producto nuevo (plan aprobado por Diego el 20 nov 2026, bocetos de 4 niveles).

Arma, sin IA y sin escribir en la base, todo lo que enseña la pantalla de un producto evaluado:
- Nivel 1, ¿cómo salió?: foto, semáforo, anillo de aporte, las 4 donas (Demanda 50, Categoría 25, Rentabilidad 12.5,
  Precio 12.5, pesos de Dirección), cifras con porciones, venta a 3 meses y clase esperada.
- Nivel 2, ¿por qué?: por factor, el titular, a favor y en contra; en Demanda los 3 escenarios a 3 meses (pesimista,
  esperado y optimista) en piezas, venta y utilidad con su clase AA–E; en Precio quién lo vende afuera y el precio por
  porción contra los parecidos.
- Nivel 3, ¿cómo se calculó?: los pasos con sus números y dónde quedó entre los lanzamientos de 2026.
- Nivel 4, ¿con qué datos?: los parecidos con foto, venta, porciones y si cuentan; la venta por mes de cada uno.
Todo sale de la evaluación guardada y de SMNBI; lo que no se sabe se deja vacío, no se supone.
"""
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from decimal import Decimal
from statistics import median

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from datos import fichas as fi
from datos.modelos import IdeaFicha, Producto
from modulos.compras import mercado_producto as mp
from modulos.compras import pronostico as pn
from modulos.compras import radar_productos as rp
from modulos.compras import realidad_producto as rr
from modulos.compras import reporte_producto as rpt
from modulos.compras import senal_venta as sv
from modulos.compras import validacion_demanda as vd
from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea

log = logging.getLogger("smn.compras.pantalla_comite")

IVA = Decimal("1.16")
CUATRO = ("demanda", "categoria", "rentabilidad", "precio")
# Diego, 25 nov 2026: el Precio en dos temas (anaquel y afuera), cada uno con la mitad. Las evaluaciones de antes siguen
# con los cuatro hasta que se recalculen
CINCO = ("demanda", "categoria", "rentabilidad", "precio_anaquel", "precio_afuera")
TRAMOS = ("4", "8", "12")  # mes 1, 2 y 3 del pronóstico
ESCENARIOS = (("pesimista", "Pesimista"), ("esperado", "Esperado"), ("optimista", "Optimista"))
MAX_PARECIDOS = 10


def _f(x) -> float | None:
    return None if x is None else round(float(x), 2)


def _n(x: float | Decimal | None, d: int = 1) -> str:
    return "—" if x is None else rp._n(x, d)


def _pesos(x: Decimal | float | None) -> str:
    return "—" if x is None else f"${float(x):,.2f}"


def _miles(x: float | None) -> str:
    if x is None:
        return "—"
    return f"${x / 1000:,.0f} mil" if abs(x) >= 10_000 else f"${x:,.0f}"


def color_de(p: int | None) -> str | None:
    return None if p is None else "verde" if p > 80 else "amarillo" if p >= 60 else "rojo"


def ficha_guardada(bd: Session, e: ProductoEvaluacion) -> fi.Ficha | None:
    """La ficha del producto nuevo que ya se leyó al evaluar (sin volver a llamar a la IA)."""
    origen, oid = ("propuesta", e.propuesta_id) if e.propuesta_id else ("idea", e.idea_id)
    return fi.a_ficha(bd.scalar(select(IdeaFicha).where(IdeaFicha.origen == origen, IdeaFicha.origen_id == oid)))


def porciones_de(f: fi.Ficha | None) -> int | None:
    return rp.porciones_de(f)


def _de_valor(valor: str | None, sin: str = "Sin datos") -> dict:
    """Titular a partir del valor del factor: lo de antes de «:» resaltado y el resto normal."""
    if not valor:
        return {"antes": "", "resaltado": sin, "despues": ""}
    cabeza, _, resto = valor.partition(": ")
    return {"antes": "", "resaltado": cabeza, "despues": f": {resto}." if resto else "."}


def _frases(texto: str | None) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=\.)\s+", rpt._sin_metodo(texto)) if x.strip()]


# ---------------------------------------------------------------- piezas

def _escenarios(pron: pn.Pronostico | None, tiendas: int | None, precio: Decimal | None, margen: Decimal | None
                ) -> list[dict]:
    """Pesimista, esperado y optimista a 3 meses: mes 1, 2 y 3 con el pronóstico a 4, 8 y 12 semanas."""
    if not pron or not pron.rango(12) or not tiendas:
        return []
    base = float(precio / IVA) if precio else None
    salida = []
    for i, (clave, nombre) in enumerate(ESCENARIOS):
        por_mes = [float((pron.rango(int(t)) or pron.rango(12))[i]) for t in TRAMOS]
        piezas = [x * tiendas for x in por_mes]
        acumulado, suma = [], 0.0
        for x in piezas:
            suma += x * base if base else 0
            acumulado.append(round(suma) if base else None)
        venta = sum(piezas) * base if base else None
        salida.append({"clave": clave, "nombre": nombre, "por_tienda": round(por_mes[-1], 2),
                       "piezas": round(sum(piezas)), "venta": round(venta) if venta else None,
                       "utilidad": round(venta * float(margen) / 100) if venta and margen is not None else None,
                       "clase": vd.clase(por_mes[-1]), "acumulado": acumulado,
                       "piezas_mes": [round(x) for x in piezas]})
    return salida


def _venta(bd: Session, v: rr.Ventana | None, skus: list[str]) -> tuple[dict, dict]:
    if not v or not skus:
        return {}, {}
    return rr.venta_por_sku(bd, v, skus), rpt.venta_skus(bd, v, skus)


def _meses(bd: Session, v: rr.Ventana | None, sku: str) -> list[dict]:
    return [{"mes": f"{m:%Y-%m}", "etiqueta": rpt.MESES[m.month - 1], "piezas": round(p)} for m, p in rr.venta_por_mes(bd, v, sku)]


def _parecidos(bd: Session, e: ProductoEvaluacion, s: rp.Sujeto, v: rr.Ventana | None) -> tuple[list[dict], list[Producto]]:
    filas = sorted(e.comparables, key=lambda c: c.rango)[:MAX_PARECIDOS]
    productos = [p for p in (bd.get(Producto, c.producto_id) for c in filas) if p]
    rp.cargar_fichas(bd, productos)
    con_sim = [(p, next(c.similitud for c in filas if c.producto_id == p.producto_id)) for p in productos]
    mismo = next((p for p, sim in con_sim if sim == 1), None)
    usados = {p.producto_id for p in rp.parecidos_para_demanda(s, con_sim, mismo)}
    venta, cobrado = _venta(bd, v, [p.sku for p in productos])
    salida = []
    for p in productos:
        cuenta, por_que = (True, "Ya lo vendemos: es el mismo producto") if mismo is p else rp.razon_cercano(s, p)
        if cuenta and p.producto_id not in usados:  # ninguno era de precio cercano: se usaron todos
            por_que = "Ninguno tiene precio cercano: se usan todos"
        cuenta = p.producto_id in usados
        salida.append({**_de_catalogo(bd, v, p, venta, cobrado), "cuenta": cuenta, "por_que": por_que,
                       "similitud": _f(con_sim[productos.index(p)][1])})
    return salida, productos


def _de_catalogo(bd: Session, v: rr.Ventana | None, p: Producto, venta: dict, cobrado: dict) -> dict:
    """Lo que se enseña de un producto que ya vendemos al picarlo en cualquier lista de la pantalla."""
    x, c = venta.get(p.sku), cobrado.get(p.sku) or {}
    f = rp.ficha_de(p)
    porciones = porciones_de(f)
    precio = c.get("precio") or p.precio_lista_con_impuestos
    tam = rp.tamano_de(p)
    return {
        "producto_id": p.producto_id, "sku": p.sku, "descripcion": rp.con_marca(p), "marca": p.marca,
        "imagen": p.liga_imagen or p.imagen_cdn, "clasificacion": p.clasificacion,
        "departamento": p.departamento, "subcategoria": p.subcategoria, "forma": f.forma if f else None,
        "formato": rp.formato_de(p),
        "al_mes": _f(x.al_mes) if x else None, "tiendas": x.tiendas if x else None,
        "por_tienda": _f(x.por_tienda_mes) if x else None, "clase": vd.clase(x.por_tienda_mes) if x else "",
        "cambio": round((x.recientes / x.anteriores - 1) * 100) if x and x.anteriores > 0 else None,
        "precio": _f(precio), "precio_lista": _f(p.precio_lista_con_impuestos), "margen": _f(c.get("margen")),
        "tamano": " · ".join(f"{q.normalize():f} {d}" for d, q in tam.items()) if tam else None,
        "porciones": porciones, "por_porcion": _f(precio / porciones) if precio and porciones else None,
        "cuenta": None, "por_que": None, "similitud": None,
        "meses": _meses(bd, v, p.sku),
    }


def _catalogo(bd: Session, v: rr.Ventana | None, parecidos: list[dict], skus: list[str]) -> dict[str, dict]:
    """Todos los productos que menciona la pantalla, por SKU, para que cada lista se pueda picar (Diego, 22 nov 2026:
    «en donde mencionamos productos sería preferible que sea una lista y que le puedas picar al producto»)."""
    salida = {x["sku"]: x for x in parecidos}
    faltan = [s for s in dict.fromkeys(skus) if s and s not in salida]
    if faltan:
        productos = bd.scalars(select(Producto).where(Producto.sku.in_(faltan))).all()
        rp.cargar_fichas(bd, list(productos))
        venta, cobrado = _venta(bd, v, [p.sku for p in productos])
        for p in productos:
            salida[p.sku] = _de_catalogo(bd, v, p, venta, cobrado)
    return salida


def _bloqueadas(m: "mp.Mercado | None") -> set[str]:
    """Tiendas clave que no dejaron consultar su sitio en esta búsqueda (Walmart pide verificar identidad, San Pablo
    contesta 403)."""
    return {n.split(":", 1)[0] for n in (m.notas if m else []) if ": bloqueó la consulta automática" in n}


def _tienda_de(p: dict) -> str | None:
    from modulos.compras import precios as pc

    return pc.tienda_clave(p.get("vendedor"), p.get("liga"))


def _afuera(e: ProductoEvaluacion, s: rp.Sujeto, porciones: int | None) -> list[dict]:
    """Quién lo vende afuera: la búsqueda de mercado (mismo producto) y lo que vio Compras o dijo el proveedor."""
    m = mp.Mercado.de_json(e.mercado)
    por_liga = {x.liga: x for x in sv.de_lista(m.senales if m else []) if x.liga}
    bloqueadas = _bloqueadas(m)
    salida = []
    for p in sorted(m.precios if m else [], key=lambda p: float(p["precio"])):
        precio = Decimal(str(p["precio"]))
        liga = p.get("liga") or ""
        vendedor = p.get("vendedor") or "—"
        senal = por_liga.get(liga) if liga else None
        if not senal and isinstance(p.get("venta"), dict):
            senal = sv.de_precios([p])[0] if sv.de_precios([p]) else None
        de_marca = rp.es_de_la_marca(p, s.marca)
        salida.append({"titulo": p.get("titulo") or s.nombre, "vendedor": vendedor, "precio": _f(precio),
                       "liga": liga or None, "fuente": "marca" if de_marca else p.get("fuente") or "google",
                       "cuenta": not de_marca,
                       "mercado_libre": "mercado libre" in rp._norm(vendedor) or "mercadolibre" in liga.lower(),
                       "por_porcion": _f(precio / porciones) if porciones else None,
                       "venta": senal.texto() if senal else None, "venta_fuerte": bool(senal and senal.puntos() == sv.FUERTE),
                       # Su sitio no deja consultarlo, pero su precio llegó por Google Shopping (26 nov 2026)
                       "nota": "visto en Google" if p.get("fuente") == "google_sitio"
                       else "visto en Google Shopping" if (p.get("fuente") or "google") == "google"
                       and _tienda_de(p) in bloqueadas else None})
    # El mismo producto, pero su publicación no dice el tamaño: se enseña con su precio y no califica (26 nov 2026)
    for v in (m.vistos if m else []):
        precio = Decimal(str(v["precio"]))
        salida.append({"titulo": v.get("titulo") or s.nombre, "vendedor": v.get("vendedor") or "—", "precio": _f(precio),
                       "liga": v.get("liga"), "fuente": "google", "cuenta": False,
                       "mercado_libre": "mercado libre" in rp._norm(v.get("vendedor")),
                       "por_porcion": _f(precio / porciones) if porciones else None, "venta": None,
                       "venta_fuerte": False, "nota": "tamaño sin confirmar, no cuenta para la calificación"})
    for precio, donde in s.mercado:
        salida.append({"titulo": s.nombre, "vendedor": donde, "precio": _f(precio), "liga": None,
                       "fuente": "compras" if s.tipo == "idea" else "proveedor", "cuenta": s.tipo != "idea",
                       "mercado_libre": "mercado libre" in rp._norm(donde),
                       "por_porcion": _f(precio / porciones) if porciones else None})
    return salida


# ---------------------------------------------------------------- por factor

def _contra(bd: Session, pron: pn.Pronostico, depto: str | None) -> tuple[list[float], bool]:
    """Los lanzamientos guardados en la evaluación; si es vieja, los del modelo de hoy solo si ya está medido (medirlo
    recorre toda la venta y tarda minutos con los datos reales: la pantalla se quedaba cargando, Diego 22 nov 2026)."""
    if pron.contra:
        return pron.contra, pron.contra_depto
    if pn.modelo_de_hoy() is not None:
        return pn.lanzamientos_contra(bd, depto)
    return [], False


def _demanda(bd: Session, e: ProductoEvaluacion, s: rp.Sujeto, v: rr.Ventana | None, fila, tend, parecidos: list[dict],
             pron: pn.Pronostico | None, escenarios: list[dict], tiendas: int | None) -> dict:
    depto = e.departamento or s.departamento
    rango = pron.rango(12) if pron else None
    usados = [p for p in parecidos if p["cuenta"]]
    lanz, del_depto = _contra(bd, pron, depto) if rango else ([], False)
    lugar = round(vd.lugar_en(rango[1], lanz)) if rango and len(lanz) >= pn.MIN_LANZAMIENTOS else None
    smn = rp.tendencia_smn(bd, v, e.subcategoria)
    m = mp.Mercado.de_json(e.mercado)
    venta = sv.de_lista(m.senales if m else [])
    puntos, por = rp.ajuste_tendencia(smn, tend, venta)
    sub = (e.subcategoria or "su subcategoría").lower()
    a_favor, en_contra = [], []
    # La tendencia solo va a favor o en contra si de verdad movió la calificación (Wonu 22 nov 2026: «creatina crece
    # 3 %» salía a favor y no sumaba nada porque el corte es ±10 %)
    if smn is not None and abs(smn) > rp.CORTE_SMN:
        (a_favor if smn > 0 else en_contra).append(
            f"{sub.capitalize()} {'crece' if smn > 0 else 'cae'} {abs(smn):,.0f} % en SMN (13 semanas contra las 13 "
            f"anteriores): {'suma' if smn > 0 else 'resta'} 5")
    if tend is not None and tend.puntaje in rp.POR_SENAL and tend.valor:
        a_favor.append(f"{tend.valor}: suma {rp.POR_SENAL[tend.puntaje]}")
    n_venta, mejor = sv.nivel(venta)
    if n_venta:
        a_favor.append(f"Se vende afuera: {sv.frase(mejor)}: suma {n_venta}")
    misma = pron.misma_sub if pron else []
    if rango and misma:
        mas = [x for x in misma if x["por_tienda"] > rango[1]]
        menos = [x for x in misma if x["por_tienda"] <= rango[1]]
        if menos:
            a_favor.append(f"Vendería más que {len(menos)} de los {len(misma)} lanzamientos de {sub} en 2026: "
                           + "; ".join(f"{x['descripcion']} {x['por_tienda']:,.1f}" for x in menos[:3]))
        if mas:
            en_contra.append(f"{len(mas)} de los {len(misma)} lanzamientos de {sub} en 2026 vendieron más: "
                             + "; ".join(f"{x['descripcion']} {x['por_tienda']:,.1f}" for x in mas[:3]))
    familia = pron.familia if pron else []
    if familia and pron.base:
        # 26 nov 2026: se mide contra todo su tipo de producto (los colágenos en polvo), no contra los de precio cercano
        (a_favor if rango and pron.base >= rango[1] else en_contra).append(
            f"Los {pron.base_de} venden en promedio {_n(pron.base)} piezas por tienda al mes")
    elif usados:
        venden = " y ".join(f"{_n(p['por_tienda'])}" for p in usados[:3] if p["por_tienda"] is not None)
        if venden:
            (a_favor if rango and min(p["por_tienda"] or 0 for p in usados) >= rango[1] else en_contra).append(
                f"Sus parecidos de precio cercano venden {venden} piezas por tienda al mes")
    if lugar is not None and lugar >= 60:
        a_favor.append(f"Vendería más que {lugar} de cada 100 productos nuevos de 2026")
    pasos = []
    if familia:
        pasos.append({"titulo": "Con qué se compara", "pregunta": "¿Con qué productos que ya vendemos se compara?",
                      "cifra": pron.base_de.split(" ", 1)[0], "sub": pron.base_de.split(" ", 1)[-1],
                      "puntos": [f"{x['descripcion']} · {_n(x['por_tienda'])} pzas/tienda" for x in familia]
                      + ["Todos los de su mismo tipo, sin filtrar por precio: si es caro, eso lo castiga el factor Precio"]})
    elif usados:
        pasos.append({"titulo": "Parecidos", "pregunta": "¿Con qué productos que ya vendemos se compara?",
                      "cifra": str(len(usados)), "sub": "de precio cercano" if len(usados) < len(parecidos) else "parecidos",
                      "puntos": [f"{p['descripcion']} · {_n(p['por_tienda'])} pzas/tienda" for p in usados[:3]]
                      + (["Los demás parecidos tienen un precio muy distinto"] if len(usados) < len(parecidos) else [])})
    if rango:
        pasos.append({"titulo": "Pronóstico", "pregunta": "¿Cuánto vendería en sus primeras 12 semanas?",
                      "cifra": _n(rango[1]), "sub": f"piezas por tienda al mes, entre {_n(rango[0])} y {_n(rango[2])}",
                      "puntos": [f"Parte de {pron.base_de or 'lo que venden sus parecidos'}",
                                 "Lo ajusta con cómo arrancaron los productos nuevos de 2026 contra sus parecidos"]})
    if lugar is not None:
        pasos.append({"titulo": "Comparación", "pregunta": "¿Es mucho o poco para un producto nuevo?",
                      "cifra": f"{lugar} de 100", "sub": f"de {len(lanz)} lanzamientos de 2026 "
                      f"{'del departamento' if del_depto else 'de toda la cadena'} vendieron igual o menos",
                      "puntos": ["Todos medidos igual: piezas entre las tiendas que ya lo habían vendido",
                                 "De su departamento si hay 20 o más; si no, de toda la cadena"]})
    if fila.puntaje is not None:
        # La base sale de la calificación guardada menos la tendencia (el lugar exacto lleva decimales; con el lugar
        # redondeado la cuenta podía no cuadrar: Wonu 22 nov, «= 19» con calificación 21 y +3 de tendencia).
        base = fila.puntaje - (puntos or 0)
        igual = "=" if lugar is not None and vd.calificacion(lugar) == base else "≈"
        formula = (f"50 + ({lugar} − 50) × {_n(rp.ESTIRA_DEMANDA)} {igual} {base}"
                   + (f"; {'+' if puntos > 0 else '−'}{abs(puntos)} de tendencia = {fila.puntaje}" if puntos else "")
                   if lugar is not None else None)
        pasos.append({"titulo": "Puntaje", "pregunta": "¿Cómo se vuelve calificación?", "cifra": str(fila.puntaje),
                      "sub": formula or "", "puntos": ["El lanzamiento típico (50 de 100) saca 50",
                                                      f"Cada lugar arriba o abajo mueve {_n(rp.ESTIRA_DEMANDA)} puntos"]
                      + ([f"Tendencia: {'; '.join(por)} (tope ±{rp.TOPE_TENDENCIA})"] if puntos else
                         ["Tendencia: no movió la calificación"])})
    esperado = next((x for x in escenarios if x["clave"] == "esperado"), None)
    if rango:
        resaltado = f"{_n(rango[1])} piezas por tienda al mes"
        if misma:
            xs = [x["por_tienda"] for x in misma]
            despues = (f". El único lanzamiento de {sub} en 2026 vendió {_n(xs[0])}." if len(xs) == 1 else
                       f". Los {len(xs)} lanzamientos de {sub} en 2026 vendieron entre {_n(min(xs))} y {_n(max(xs))}.")
        elif lugar is not None:
            despues = f". De cada 100 productos nuevos de 2026, {100 - lugar} vendieron más al arrancar."
        else:
            despues = "."
        titular = {"antes": "Vendería ", "resaltado": resaltado, "despues": despues}
    else:
        titular = _de_valor(fila.valor, "Sin pronóstico")
    return {"titular": titular, "rango": [_f(x) for x in rango] if rango else None, "tiendas": tiendas,
            "escenarios": escenarios, "a_favor": a_favor, "en_contra": en_contra, "subiria": fila.mejora,
            "pasos": pasos, "lugar": lugar, "lanzamientos": sorted(round(x, 2) for x in lanz), "del_depto": del_depto,
            "misma_sub": misma, "tendencia": {"smn": smn, "senal": tend.valor if tend is not None else None,
                                              "puntos": puntos, "por": por},
            "venta_afuera": [{"fuente": x.fuente, "vendedor": x.vendedor, "texto": x.texto(), "liga": x.liga,
                              "puntos": x.puntos()} for x in venta if x.texto()],
            "prueba": (pron.examen or {}).get("prueba") if pron else None,
            "venta_3m": esperado["venta"] if esperado else None}


def _mitad(f: rp.Factor | None, precio: Decimal | None) -> dict | None:
    if f is None:
        return None
    pct = round(float((precio / f.meta - 1) * 100)) if f.puntaje is not None and precio and f.meta else None
    return {"puntaje": f.puntaje, "color": color_de(f.puntaje), "valor": f.valor, "detalle": rpt._sin_metodo(f.detalle),
            "diferencia_pct": pct, "referencia": _f(f.meta), "por_unidad": f.por_unidad, "provisional": f.provisional}


def _mitades(e: ProductoEvaluacion, s: rp.Sujeto, productos: list[Producto], parecidos: list[dict]) -> dict:
    """Las dos mitades del Precio (Dirección, 22 nov 2026), calculadas igual que al evaluar."""
    con_sim = [(p, Decimal(str(x["similitud"] or 0))) for p, x in zip(productos, parecidos)]
    mismo = next((p for p, x in zip(productos, parecidos) if (x["similitud"] or 0) >= 1), None)
    internet = mp.Mercado.de_json(e.mercado)
    afuera = rp.precio_afuera(s, con_sim, internet, mismo)
    anaquel = rp.precio_anaquel(s, con_sim) if not mismo else None
    m = rp.lado_membresia(s, con_sim, internet, mismo)
    # 22 nov 2026: también con el precio de membresía (mitad y mitad en la calificación)
    membresia = ({"precio": _f(m.precio), "calculado": s.membresia_calculada and not mismo,
                  "puntaje": m.junto.puntaje, "color": color_de(m.junto.puntaje), "valor": m.junto.valor,
                  "afuera": _mitad(m.afuera, m.precio), "anaquel": _mitad(m.anaquel, m.precio)} if m else None)
    return {"afuera": _mitad(afuera, s.precio), "anaquel": _mitad(anaquel, s.precio), "membresia": membresia}


def _nota_ml(e: ProductoEvaluacion, afuera: list[dict]) -> str | None:
    """Qué pasó con Mercado Libre, sin suponer: «no apareció» solo si de verdad se buscó (Wonu 22 nov 2026: lo decía
    sin tener la aplicación conectada)."""
    if any(a["mercado_libre"] for a in afuera):
        return None
    m = mp.Mercado.de_json(e.mercado)
    nota = next((x for x in (m.notas if m else []) if x.startswith("Mercado Libre")), None)
    # En pantalla solo lo que dice algo del mercado, en una línea de negocio. Las fallas de conexión o de llave se quedan
    # en la nota guardada para quien administra (criterio de Diego: nada de método ni «no se pudo» para Compras y
    # Dirección; revisión de usabilidad, 26 nov 2026)
    if nota and ("no regresó resultados" in nota or "ningún resultado" in nota):
        return "Mercado Libre: no tiene publicado este mismo producto."
    return None


def _relevante(titulo: str, s: "rp.Sujeto | None") -> bool:
    """¿El resultado es de esta marca o de su ingrediente principal? Lo demás no se enseña uno por uno."""
    if s is None:
        return True
    t = rp._norm(titulo)
    compacto = re.sub(r"[^a-z0-9]", "", t)
    marca = re.sub(r"[^a-z0-9]", "", rp._norm(s.marca))
    if len(marca) >= 3 and marca in compacto:
        return True
    ingrediente = s.ingrediente or (s.ficha.ingrediente_principal if getattr(s, "ficha", None) else None)
    raices = [w[:6] for w in rp._norm(ingrediente).split() if len(w) >= 4]
    if not raices:
        try:
            raices = rp._candidatas_ingrediente(s)[:1]
        except Exception:  # noqa: BLE001 - solo decide qué se enseña
            raices = []
    return any(r and r in t for r in raices)


_POR_QUE = (("presentación distinta", "dice otra presentación"), ("marca distinta", "es otra marca"),
            ("presentación no comprobada", "no dice el tamaño"), ("parece paquete", "parece un paquete o kit"))


def _por_que_no(motivo: str) -> str:
    """De «calificación 68; nombre 100; marca coincide; presentación no comprobada» a «no dice el tamaño»."""
    razones = [texto for clave, texto in _POR_QUE if clave in motivo]
    if (falta := re.search(r"el título no trae ((?:«[^»]+»(?:, )?)+)", motivo)):
        razones.insert(0, "no menciona " + re.sub(r"«([^»]+)»", lambda x: x.group(1).lower(), falta.group(1)))
    return ", ".join(razones) or "no es claramente el mismo producto"


def _nota_de_negocio(nota: str, s: "rp.Sujeto | None") -> str | None:
    """La nota guardada (completa, para diagnóstico y el Excel de la prueba) en palabras de negocio para la pantalla:
    sin calificaciones internas ni la lista de resultados que no tienen que ver (Diego, 26 nov 2026)."""
    if nota.startswith("Google Shopping, lo más parecido: "):
        partes = []
        for item in nota.split(": ", 1)[1].split(" | "):
            if (x := re.match(r"«(.+?)» \((.*)\)$", item.strip())) and _relevante(x.group(1), s):
                partes.append(f"«{x.group(1)}» ({_por_que_no(x.group(2))})")
        return ("Lo más parecido en Google Shopping, que no se tomó: " + "; ".join(partes[:2]) + ".") if partes else None
    if (x := re.match(r"Google Shopping regresó (\d+): (.*)$", nota)):
        # Los títulos se guardaron recortados a 60 letras: el corte se marca para que no parezca un error
        titulos = [(t.strip("«» ") + "…") if len(t.strip("«» ")) >= 60 else t.strip("«» ") for t in x.group(2).split(" · ")]
        suyos = [t for t in titulos if _relevante(t, s)]
        if not suyos:
            return f"Google Shopping regresó {x.group(1)} resultados; ninguno era de esta marca ni de su ingrediente."
        return f"Google Shopping regresó {x.group(1)} resultados; de esta marca o ingrediente: " + " · ".join(
            f"«{t}»" for t in suyos[:5]) + "."
    if nota.startswith("Google Shopping, se buscó: "):
        return "Se buscó en Google Shopping: " + nota.split(": ", 1)[1].replace(" · ", ", ") + "."
    if nota.startswith("Google Shopping no aceptó la búsqueda"):
        return re.sub(r"\s*\([^)]*\)\.?$", ".", nota)
    return nota


def _notas_busqueda(e: ProductoEvaluacion, s: "rp.Sujeto | None" = None) -> list[str]:
    """Qué se buscó afuera y por qué no se tomó nada (Google, tiendas), para verlo en pantalla sin consultar la base
    (BDM Life, 25 nov 2026). Mercado Libre va aparte."""
    m = mp.Mercado.de_json(e.mercado)
    bloqueadas = _bloqueadas(m)
    notas = [n for x in (m.notas if m else []) if not x.startswith("Mercado Libre")
             and x.split(":", 1)[0] not in bloqueadas and (n := _nota_de_negocio(x, s))]
    notas = list(dict.fromkeys(notas))[:12]
    # El bloqueo de una tienda va al final y en palabras de negocio, no como falla (Diego, 26 nov 2026: «si Walmart no
    # da, ¿cómo lo solucionamos?»): su precio se toma de Google Shopping cuando lo publica ahí
    for t in sorted(bloqueadas):
        suyos = [p for p in (m.precios if m else []) if (p.get("fuente") or "google") in ("google", "google_sitio")
                 and _tienda_de(p) == t]
        # Lo que dijo la búsqueda en Google limitada a su sitio (si se hizo): «sí lo vende, sin precio» o «no aparece»
        de_google = [x.split(":", 1)[1].strip() for x in (m.notas if m else [])
                     if x.startswith(f"{t}:") and ("Google" in x) and not x.startswith(f"{t}: bloqueó")]
        vistos = [v for v in (m.vistos if m else []) if _tienda_de(v) == t]
        if suyos:
            precio = min(float(p["precio"]) for p in suyos)
            notas.append(f"{t} no deja consultar su sitio; su precio se tomó de Google (${precio:,.2f}).")
        elif vistos:
            precio = min(float(v["precio"]) for v in vistos)
            notas.append(f"{t} no deja consultar su sitio; en Google Shopping lo vimos a ${precio:,.2f}, sin el tamaño "
                         "confirmado.")
        elif de_google:
            notas.append(f"{t} no deja consultar su sitio; {de_google[0][0].lower() + de_google[0][1:]}")
        else:
            notas.append(f"{t} no deja consultar su sitio y no publicó este producto en Google Shopping.")
    return notas


def _precio(e: ProductoEvaluacion, s: rp.Sujeto, r: rpt.Reporte, fila, afuera: list[dict], parecidos: list[dict],
            porciones: int | None, mitades: dict | None = None) -> dict:
    usados = [p for p in parecidos if p["cuenta"]]
    mitades = mitades or {"afuera": None, "anaquel": None, "membresia": None}
    # Con quién va a competir en el anaquel: los parecidos de precio cercano y del mismo formato (polvo, cápsula,
    # sobre…) que más venden. Es la misma lista para el «se lleva» y las barras por porción (Wonu 22 nov 2026: había
    # tres listas distintas de con quién compite)
    formato = rp.formato_sujeto(s)
    mismo_formato = [p for p in usados if formato and p["formato"] == formato]
    compite = sorted(mismo_formato or usados, key=lambda p: -(p["por_tienda"] or 0))[:3]
    referencia = r.referencia
    pct = round(float((s.precio / referencia - 1) * 100)) if s.precio and referencia else None
    fuera = mitades.get("afuera")
    if fuera and fuera["diferencia_pct"] is not None and fuera["referencia"]:
        # La cifra que se dice es la misma con que se califica la mitad de afuera (Wonu 22 nov: el titular decía
        # $626 y la mitad calificaba contra $599)
        referencia, pct = Decimal(str(fuera["referencia"])), fuera["diferencia_pct"]
    por_porcion = _f(s.precio / porciones) if s.precio and porciones else None
    con_porcion = ([p for p in compite if p["por_porcion"]] or [p for p in usados if p["por_porcion"]]
                   or [p for p in parecidos if p["por_porcion"]])
    veces = (round(por_porcion / median(p["por_porcion"] for p in con_porcion), 1)
             if por_porcion and con_porcion else None)
    # Por porciones solo si al menos la mitad de con quién compite dicen sus porciones (BDM Life, 25 nov 2026: de 7
    # berberinas solo Altus las dice y el cuadro comparaba contra ella sola); si no, por cápsula, gramo o mililitro
    base_porcion = compite or usados
    con_dato = len([p for p in base_porcion if p["por_porcion"]])
    porciones_alcanzan = con_dato >= max(2, (len(base_porcion) + 1) // 2)
    barras_nota = (f"Precio por porción: solo {con_dato} de {len(base_porcion)} con los que compite traen sus porciones "
                   "en la ficha; no alcanza para comparar por porción." if por_porcion and not porciones_alcanzan else None)
    # Barras de precio por porción: nosotros, afuera (el más barato y el más caro) y los parecidos
    barras = []
    if por_porcion and porciones_alcanzan:
        barras.append({"nombre": f"{s.marca or s.nombre} con nosotros", "valor": por_porcion, "tipo": "nuevo"})
        con_afuera = [a for a in afuera if a["por_porcion"]]
        for a in ([con_afuera[0], con_afuera[-1]] if len(con_afuera) > 1 else con_afuera):
            barras.append({"nombre": f"En {a['vendedor']}", "valor": a["por_porcion"], "tipo": "afuera"})
    for p in (con_porcion[:4] if barras else []):
        barras.append({"nombre": p["descripcion"], "valor": p["por_porcion"], "tipo": "parecido", "sku": p["sku"],
                       "imagen": p["imagen"]})
    # Con nuestro precio, cuántas porciones (o gramos) se lleva el cliente de cada uno
    se_lleva = None
    if s.precio and porciones and con_porcion and porciones_alcanzan:
        se_lleva = {"monto": _f(s.precio), "unidad": "porciones", "filas": [
            {"nombre": s.marca or s.nombre, "cantidad": porciones, "tipo": "nuevo"}]
            + [{"nombre": p["descripcion"], "cantidad": round(float(s.precio) / p["por_porcion"]), "tipo": "parecido",
                "sku": p["sku"], "imagen": p["imagen"]} for p in con_porcion[:4]]}
    else:
        tam = rp.solo_piezas(rp.tamano(s.contenido, s.nombre) or (s.ficha.tamano() if s.ficha else {}), rp.formato_sujeto(s))
        dim = next((d for d in ("g", "ml", "pz") if d in tam), None)  # cápsulas: por pieza (25 nov 2026)
        otros = [(p, t[dim]) for p in (compite or usados) if dim and p["precio"] and dim in (t := rp.tamano(p["descripcion"]))]
        if s.precio and dim and otros:
            unidad = {"g": "gramos", "ml": "mililitros", "pz": "piezas"}[dim]
            se_lleva = {"monto": _f(s.precio), "unidad": unidad, "filas": [
                {"nombre": s.marca or s.nombre, "cantidad": float(tam[dim]), "tipo": "nuevo"}]
                + [{"nombre": p["descripcion"], "cantidad": round(float(s.precio) / p["precio"] * float(q)), "tipo": "parecido",
                    "sku": p["sku"], "imagen": p["imagen"]} for p, q in otros[:4]]}
    a_favor, en_contra = [], []
    if pct is not None:
        (a_favor if pct <= 0 else en_contra).append(
            f"{abs(pct)} % {'abajo' if pct <= 0 else 'arriba'} del precio de en medio del mercado ({_pesos(referencia)})")
    for a in [a for a in afuera if a.get("cuenta", True)][:6]:
        if s.precio and a["precio"] and abs(a["precio"] - float(s.precio)) < 1:
            a_favor.append(f"Igual al precio de {a['vendedor']} ({_pesos(a['precio'])})")
            break
    con_anaquel = bool(mitades.get("anaquel") and mitades["anaquel"]["diferencia_pct"] is not None)
    if con_anaquel:
        pass  # la comparación por porción ya va en la mitad del anaquel
    elif veces and veces >= 1.5:
        en_contra.append(f"Por porción cuesta unas {_n(veces)} veces lo que "
                         + " o ".join(p["descripcion"] for p in con_porcion[:2]))
    elif veces and veces <= 0.8:
        a_favor.append(f"Por porción cuesta {_n(veces)} veces lo que sus parecidos: le rinde más al cliente")
    if se_lleva and se_lleva["unidad"] == "porciones":
        mas = [f for f in se_lleva["filas"][1:] if f["cantidad"] > porciones]
        if mas:
            en_contra.append(f"{porciones} porciones: con el mismo dinero, {mas[0]['nombre']} rinde {mas[0]['cantidad']}")
    ana = mitades.get("anaquel")
    if ana and ana["diferencia_pct"] is not None:
        d = ana["diferencia_pct"]
        pu = ana.get("por_unidad")
        texto = (f"{abs(d)} % {'abajo' if d <= 0 else 'arriba'} de nuestro anaquel"
                 + (f", por {pu['unidad']}: {_por_unidad(pu)}" if pu else f" ({_pesos(ana['referencia'])} en medio)"))
        (a_favor if d <= 0 else en_contra).append(texto[0].upper() + texto[1:])
    if pct is not None:
        resaltado = f"{abs(pct)} % más {'barato' if pct < 0 else 'caro'}" if pct else "al mismo precio"
        antes = "Contra afuera está " if ana and ana["diferencia_pct"] is not None else "Está "
        despues = f" que el precio de en medio del mercado ({_pesos(referencia)})"
        if ana and ana["diferencia_pct"] is not None:  # la porción ya va en la mitad del anaquel
            d = ana["diferencia_pct"]
            despues += (f"; contra nuestro anaquel, {abs(d)} % más {'barato' if d < 0 else 'caro'}." if d else
                        "; contra nuestro anaquel, igual.")
        elif veces and con_porcion:
            despues += (f", pero cada porción cuesta {_pesos(por_porcion)}: unas {_n(veces)} veces lo que "
                        f"{con_porcion[0]['descripcion']}." if veces >= 1.5 else f"; cada porción cuesta {_pesos(por_porcion)}.")
        else:
            despues += "."
        titular = {"antes": antes, "resaltado": resaltado, "despues": despues}
    else:
        titular = _de_valor(fila.valor, "Sin precios para comparar")
    return {"titular": titular, "referencia": _f(referencia), "diferencia_pct": pct, "afuera": afuera[:10],
            "mitades": mitades, "membresia": mitades.get("membresia"), "compite": [{**{k: p[k] for k in ("sku", "descripcion", "imagen", "clase", "clasificacion", "por_tienda",
                                                                   "por_porcion", "tamano")},
                                     # precio de lista con IVA, igual que el nuestro (no el precio promedio vendido)
                                     "precio": p["precio_lista"] or p["precio"]} for p in compite],
            "mercado_libre": [a for a in afuera if a["mercado_libre"]], "mercado_libre_nota": _nota_ml(e, afuera),
            "busqueda_notas": _notas_busqueda(e, s),
            "por_porcion": por_porcion, "porciones": porciones, "veces": veces, "barras": barras, "barras_nota": barras_nota,
            "se_lleva": se_lleva,
            "a_favor": a_favor, "en_contra": en_contra, "subiria": fila.mejora,
            "pasos": [{"titulo": f"Paso {i}", "texto": t} for i, t in enumerate(_frases(fila.calculo), 1)]}


def _por_unidad(pu: dict) -> str:
    """«$3.82 contra $5.22 en medio» (25 nov 2026: decía «contra $626.00 de referencia», el total de 120 cápsulas)."""
    return f"{_pesos(Decimal(str(pu['propio'])))} contra {_pesos(Decimal(str(pu['medio'])))} en medio"


def _temas_precio(precio: dict, anaquel, afuera) -> dict:
    """Los dos temas del Precio que se pican por separado (Diego, 25 nov 2026), cada uno con su titular, a favor,
    en contra, qué lo subiría y sus pasos. Sale de lo mismo que el Precio junto."""
    mitades = precio.get("mitades") or {}
    ana, fue = mitades.get("anaquel"), mitades.get("afuera")
    comun = {k: precio[k] for k in ("mitades", "membresia", "compite", "afuera", "mercado_libre", "mercado_libre_nota",
                                     "por_porcion", "porciones", "barras", "barras_nota", "se_lleva", "veces")}

    def pasos(fila) -> list[dict]:
        return [{"titulo": f"Paso {i}", "texto": t} for i, t in enumerate(_frases(fila.calculo), 1)]

    # Contra nuestro anaquel
    a_favor, en_contra = [], []
    if ana and ana["diferencia_pct"] is not None:
        d, pu = ana["diferencia_pct"], ana.get("por_unidad")
        texto = (f"{abs(d)} % {'abajo' if d <= 0 else 'arriba'} de nuestro anaquel"
                 + (f", por {pu['unidad']}: {_por_unidad(pu)}" if pu else f" ({_pesos(Decimal(str(ana['referencia'])))} en medio)"))
        (a_favor if d <= 0 else en_contra).append(texto[0].upper() + texto[1:])
        toma = (pu or {}).get("toma")
        if toma and toma["si_de_1_pct"]:
            t = (f"Se toma de {_n(toma['piezas'])} {pu['unidad']}s ({_pesos(Decimal(str(toma['por_toma'])))} por toma): si "
                 f"las demás se toman de 1, sale {abs(toma['si_de_1_pct'])} % más "
                 f"{'caro' if toma['si_de_1_pct'] > 0 else 'barato'} por toma. Falta la toma en sus fichas")
            (en_contra if toma["si_de_1_pct"] > 0 else a_favor).append(t)
        resaltado = f"{abs(d)} % más {'barato' if d < 0 else 'caro'}" if d else "al mismo precio"
        despues = (f" por {pu['unidad']}: {_por_unidad(pu)}." if pu else
                   f" que el precio de en medio de nuestros parecidos ({_pesos(Decimal(str(ana['referencia'])))}).")
        titular = {"antes": "Contra nuestro anaquel está ", "resaltado": resaltado, "despues": despues}
    else:
        titular = _de_valor(anaquel.valor, "Sin con qué compararlo en nuestro anaquel")
    en_contra += [x for x in precio["en_contra"] if "porciones: con el mismo dinero" in x or x.startswith("Por porción")]
    a_favor += [x for x in precio["a_favor"] if x.startswith("Por porción")]
    t_anaquel = {**comun, "lado": "anaquel", "titular": titular, "a_favor": a_favor, "en_contra": en_contra,
                 "subiria": anaquel.mejora, "pasos": pasos(anaquel), "provisional": bool(anaquel.provisional)}

    # Contra afuera
    a_favor = [x for x in precio["a_favor"] if "mercado" in x or x.startswith("Igual al precio de")]
    en_contra = [x for x in precio["en_contra"] if "mercado" in x]
    if fue and fue["diferencia_pct"] is not None:
        d = fue["diferencia_pct"]
        titular = {"antes": "Contra afuera está ",
                   "resaltado": f"{abs(d)} % más {'barato' if d < 0 else 'caro'}" if d else "al mismo precio",
                   "despues": f" que el precio de en medio del mercado ({_pesos(Decimal(str(fue['referencia'])))})."}
    else:
        titular = {"antes": "", "resaltado": "Sin precios de afuera",
                   "despues": ": el radar de precios no lo encontró a la venta en internet. No cuenta; su peso pasa a "
                              "nuestro anaquel."}
    t_afuera = {**comun, "lado": "afuera", "titular": titular, "a_favor": a_favor, "en_contra": en_contra,
                "subiria": afuera.mejora, "pasos": pasos(afuera), "provisional": bool(afuera.provisional)}
    return {"precio_anaquel": t_anaquel, "precio_afuera": t_afuera}


def _categoria(bd: Session, e: ProductoEvaluacion, s: rp.Sujeto, v: rr.Ventana | None, fila, parecidos: list[dict]) -> dict:
    from modulos.compras import asistente_comite as ac

    n = tipica = dias = None
    if e.subcategoria:
        n = bd.scalar(select(func.count()).select_from(Producto).where(
            Producto.activo == true(), Producto.subcategoria == e.subcategoria))
        tipica = round(rp._tamano_tipico(bd))
        if v and (inv := rr.dias_inventario(bd, v, e.subcategoria)):
            dias = round(inv[0])
    mas_vendidos = []
    if e.subcategoria:
        try:
            mas_vendidos = [{"sku": x.producto.sku, "descripcion": rp.con_marca(x.producto), "al_mes": _f(x.al_mes),
                             "por_tienda": _f(x.por_tienda_mes), "imagen": x.producto.liga_imagen or x.producto.imagen_cdn}
                            for x in ac.lo_que_mas_se_vende(bd, e.subcategoria, set(), n=6)]
        except Exception as ex:  # noqa: BLE001 - la gráfica es complemento
            log.warning("Pantalla del comité: no se pudieron leer los más vendidos de %s: %s", e.subcategoria, ex)
    a_favor, en_contra = [], []
    if n is not None and tipica:
        (a_favor if n <= tipica else en_contra).append(
            f"{n} productos activos en {e.subcategoria.lower()}; una subcategoría normal tiene unos {tipica}")
    # El −5 de «ya vendemos uno de la misma marca y línea» se dice con el producto que lo causó (Wonu 22 nov 2026: restaba
    # y no se veía en la pantalla)
    linea = [p for p in parecidos if (p["similitud"] or 0) >= 0.8 and p["al_mes"] and s.marca and p["marca"]
             and re.sub(r"[^a-z0-9]", "", rp._norm(p["marca"])) == re.sub(r"[^a-z0-9]", "", rp._norm(s.marca))]
    if linea:
        en_contra.append(f"Ya vendemos uno de la misma marca y línea: {linea[0]['descripcion']} "
                         f"({_n(linea[0]['al_mes'], 0)} pzas al mes): resta 5")
    if dias is not None:
        if dias > 180:
            en_contra.append(f"Lo que hay en tiendas de la subcategoría alcanza para {dias} días de venta")
        elif dias < 45:
            a_favor.append(f"La subcategoría tiene inventario para solo {dias} días: se vende rápido")
    canibal = [p for p in parecidos if (p["similitud"] or 0) >= 0.5 and p["al_mes"] and p not in linea]
    if canibal:
        en_contra.append("Podría quitarle venta a " + "; ".join(f"{p['descripcion']} ({_n(p['al_mes'], 0)} pzas al mes)"
                                                                 for p in canibal[:2]))
    return {"titular": _de_valor(fila.valor), "productos": n,
            "tipica": tipica, "dias_inventario": dias, "mas_vendidos": mas_vendidos, "a_favor": a_favor,
            "en_contra": en_contra, "subiria": fila.mejora, "detalle": rpt._sin_metodo(fila.detalle),
            "pasos": [{"titulo": f"Paso {i}", "texto": t} for i, t in enumerate(_frases(fila.calculo), 1)]}


def _rentabilidad(bd: Session, e: ProductoEvaluacion, s: rp.Sujeto, r: rpt.Reporte, fila) -> dict:
    utilidad_pieza = float(s.precio / IVA - s.costo) if s.precio and s.costo else None
    if utilidad_pieza is None and s.precio and s.margen is not None:
        utilidad_pieza = float(s.precio / IVA * s.margen / 100)
    a_favor, en_contra = [], []
    if r.margen is not None:
        (a_favor if r.margen >= r.minimo else en_contra).append(
            f"Margen de {_n(r.margen)} % contra el mínimo de {_n(r.minimo)} %")
    if r.margen_membresia is not None and r.minimo_membresia is not None:
        (a_favor if r.margen_membresia >= r.minimo_membresia else en_contra).append(
            f"Con membresía ({_pesos(r.precio_membresia)}) deja {_n(r.margen_membresia)} % contra el mínimo de "
            f"{_n(r.minimo_membresia)} %")
    if r.margen is not None and r.margen_sub is not None:
        (a_favor if r.margen >= r.margen_sub else en_contra).append(
            f"{(e.subcategoria or 'Su subcategoría').capitalize()} deja {_n(r.margen_sub)} % en SMN")
    if fila.puntaje is None:
        titular = _de_valor(fila.valor, "Sin costo todavía")
    else:
        titular = {"antes": "Deja ", "resaltado": f"{_n(r.margen)} % de margen" if r.margen is not None else "—",
                   "despues": f" (mínimo {_n(r.minimo)} %)" + (f": {_pesos(utilidad_pieza)} por pieza." if utilidad_pieza else ".")}
    return {"titular": titular, "margen": _f(r.margen), "minimo": _f(r.minimo), "margen_sub": _f(r.margen_sub),
            "lista": r.lista, "membresia": ({"precio": _f(r.precio_membresia), "calculado": r.membresia_calculada,
                                             "margen": _f(r.margen_membresia), "minimo": _f(r.minimo_membresia)}
                                            if r.margen_membresia is not None else None),
            "utilidad_pieza": _f(utilidad_pieza),
            "escenarios": [{"nombre": n, "precio": _f(p), "costo": _f(c), "margen": _f(m)} for n, p, c, m in r.escenarios],
            "a_favor": a_favor, "en_contra": en_contra, "subiria": fila.mejora, "detalle": rpt._sin_metodo(fila.detalle),
            "pasos": [{"titulo": f"Paso {i}", "texto": t} for i, t in enumerate(_frases(fila.calculo), 1)]}


# ---------------------------------------------------------------- la pantalla

# Plan aprobado por Diego (22 nov 2026): la pantalla se arma una sola vez, al terminar cada evaluación, y se guarda en la
# evaluación (migración 0053). Abrirla solo la lee. Si después se carga venta nueva, se enseña la guardada diciendo con
# qué venta se armó y se vuelve a armar aparte; si alguien cambió la evaluación (color final, recalcular), se rearma ya.
# En memoria se guarda además la ya leída para que pasar de un producto a otro en la presentación sea inmediato.
_GUARDADAS: dict[tuple, dict] = {}
_MAX_GUARDADAS = 300
_REARMANDO: set[int] = set()
_candado = threading.Lock()


def _firma(e: ProductoEvaluacion) -> str:
    """Lo que, si cambia, obliga a volver a armar la pantalla aunque la venta sea la misma."""
    return f"{e.estado}|{e.cambiado_en:%Y%m%d%H%M%S}" if e.cambiado_en else (e.estado or "")


def guardar(bd: Session, e: ProductoEvaluacion, v: rr.Ventana | None = None) -> dict:
    """Arma la pantalla de la evaluación y la deja guardada en la base."""
    inicio = time.monotonic()
    salida = _armar(bd, e, None, v)
    salida["firma"] = _firma(e)
    e.pantalla, e.pantalla_venta = json.dumps(salida, ensure_ascii=False), salida["ventana"]
    bd.commit()
    log.info("Pantalla de la evaluación %s armada y guardada en %.1f s", e.evaluacion_id, time.monotonic() - inicio)
    return salida


def _rearmar_aparte(evaluacion_id: int) -> None:
    with _candado:
        if evaluacion_id in _REARMANDO:
            return
        _REARMANDO.add(evaluacion_id)

    def trabajo():
        try:
            with rp._sesion() as bd2:
                if (e2 := bd2.get(ProductoEvaluacion, evaluacion_id)) and e2.estado == "lista":
                    guardar(bd2, e2)
        except Exception:  # noqa: BLE001
            log.exception("No se pudo volver a armar la pantalla de la evaluación %s", evaluacion_id)
        finally:
            with _candado:
                _REARMANDO.discard(evaluacion_id)

    threading.Thread(target=trabajo, daemon=True, name=f"pantalla-{evaluacion_id}").start()


def _leer(e: ProductoEvaluacion) -> dict | None:
    if not e.pantalla:
        return None
    try:
        salida = json.loads(e.pantalla)
    except ValueError:
        return None
    return salida if salida.get("firma") == _firma(e) else None


def armar(bd: Session, e: ProductoEvaluacion, fotos: list[str] | None = None, aparte: bool = True) -> dict:
    v = rr.ventana(bd)
    texto = v.texto() if v else None
    clave = (e.evaluacion_id, _firma(e), e.pantalla_venta, texto)
    salida = _GUARDADAS.get(clave)
    if salida is None:
        salida = _leer(e)
        if salida is None or e.estado != "lista":
            salida = guardar(bd, e, v) if e.estado == "lista" else _armar(bd, e, None, v)
        elif salida.get("ventana") != texto:
            # Venta nueva: se enseña la guardada diciendo con qué venta se armó y se rearma aparte
            salida = {**salida, "venta_al": salida.get("hasta")}
            if aparte:
                _rearmar_aparte(e.evaluacion_id)
        if len(_GUARDADAS) >= _MAX_GUARDADAS:
            _GUARDADAS.clear()
        _GUARDADAS[clave] = salida
    return {**salida, "producto": {**salida["producto"], "fotos": fotos or []}}


def preparar(bd: Session, avance: Callable[[int, int], None] | None = None) -> dict:
    """Arma y guarda la pantalla de todas las evaluaciones vigentes que no la tienen o la tienen con otra venta."""
    v = rr.ventana(bd)
    texto = v.texto() if v else None
    ids = bd.scalars(select(ProductoEvaluacion.evaluacion_id).where(
        ProductoEvaluacion.vigente == true(), ProductoEvaluacion.estado == "lista")
        .order_by(ProductoEvaluacion.evaluacion_id)).all()
    hechas = fallidas = ya = 0
    for n, i in enumerate(ids, 1):
        e = bd.get(ProductoEvaluacion, i)
        if e.pantalla_venta == texto and _leer(e) is not None:
            ya += 1
        else:
            try:
                guardar(bd, e, v)
                hechas += 1
            except Exception:  # noqa: BLE001
                bd.rollback()
                log.exception("No se pudo armar la pantalla de la evaluación %s", i)
                fallidas += 1
        if avance:
            avance(n, len(ids))
    return {"total": len(ids), "armadas": hechas, "ya_estaban": ya, "fallidas": fallidas}


def _armar(bd: Session, e: ProductoEvaluacion, fotos: list[str] | None = None, v: rr.Ventana | None = None) -> dict:
    r = rpt.armar(bd, e, con_fotos=False)
    s, proveedor, _ = rpt._sujeto(bd, e)
    s.ficha = ficha_guardada(bd, e)
    if s.ficha:
        s.contenido = s.contenido or s.ficha.contenido_texto()
        s.forma = s.forma or s.ficha.forma
        s.ingrediente = s.ingrediente or s.ficha.ingrediente_principal
    porciones = porciones_de(s.ficha)
    if not porciones and e.idea_id and (i := bd.get(ProductoIdea, e.idea_id)) and i.porciones:
        porciones = int(i.porciones)
    v = v or rr.ventana(bd)
    filas = {f.factor: f for f in e.factores}
    try:
        pron = pn.Pronostico.de_json(e.pronostico)
    except (ValueError, TypeError, KeyError):
        pron = None
    direccion = e.pesos_origen == "direccion"
    temas = CINCO if "precio_anaquel" in filas else CUATRO
    peso = {f: (filas[f].peso if f in filas else rp.PESOS_DIRECCION[f]) for f in temas}
    cubierto = sum((peso[f] for f in temas if f in filas and filas[f].puntaje is not None), Decimal(0)) or Decimal(1)
    factores = []
    for f in temas:
        x = filas.get(f)
        p = x.puntaje if x else None
        factores.append({"factor": f, "nombre": rp.NOMBRES[f], "peso": _f(peso[f]), "puntaje": p, "color": color_de(p),
                         "de": _f(peso[f] * 100 / cubierto) if p is not None else None,
                         "aporte": _f(peso[f] * p / cubierto) if p is not None else None,
                         "valor": x.valor if x else None, "detalle": rpt._sin_metodo(x.detalle) if x else None,
                         "calculo": x.calculo if x else None, "mejora": x.mejora if x else None,
                         "provisional": bool(x and x.provisional)})
    parecidos, productos = _parecidos(bd, e, s, v)
    afuera = _afuera(e, s, porciones)
    # La venta que se presenta es la de la prueba en 10 tiendas, que es lo que aprueba el comité; la de toda la cadena
    # se dice aparte (Wonu 22 nov 2026: los $244 mil eran con 187 tiendas)
    cadena = r.estimado["tiendas"] if r.estimado else None
    tiendas = min(rpt.TIENDAS_PRUEBA, cadena) if cadena else None
    escenarios = _escenarios(pron, tiendas, s.precio, r.margen)
    en_cadena = _escenarios(pron, cadena, s.precio, r.margen) if cadena and cadena > (tiendas or 0) else []
    vacio = rp.Factor(None, None, "")
    demanda = _demanda(bd, e, s, v, filas.get("demanda") or vacio, filas.get("tendencia"), parecidos, pron,
                       escenarios, tiendas)
    cad_esperado = next((x for x in en_cadena if x["clave"] == "esperado"), None)
    demanda["cadena"] = ({"tiendas": cadena, "venta": cad_esperado["venta"], "piezas": cad_esperado["piezas"],
                          "utilidad": cad_esperado["utilidad"]} if cad_esperado else None)
    precio = _precio(e, s, r, filas.get("precio") or vacio, afuera, parecidos, porciones,
                     _mitades(e, s, productos, parecidos))
    temas_precio = _temas_precio(precio, filas.get("precio_anaquel") or vacio, filas.get("precio_afuera") or vacio)
    prov = filas.get("proveedor")
    esperado = next((x for x in escenarios if x["clave"] == "esperado"), None)
    color = e.color_final or e.color
    categoria = _categoria(bd, e, s, v, filas.get("categoria") or vacio, parecidos)
    catalogo = _catalogo(bd, v, parecidos, [x["sku"] for x in categoria["mas_vendidos"]]
                         + [x["sku"] for x in demanda["misma_sub"] if x.get("sku")])
    return {
        "evaluacion_id": e.evaluacion_id,
        "catalogo": catalogo,
        "producto": {"nombre": s.nombre, "marca": s.marca, "presentacion": r.presentacion, "proveedor": proveedor,
                     "clasificacion": r.clasificacion, "departamento": e.departamento or s.departamento,
                     "subcategoria": e.subcategoria, "tipo": s.tipo, "codigo_barras": s.codigo_barras,
                     "forma": s.forma, "contenido": s.contenido, "fotos": fotos or []},
        "puntaje": e.puntaje, "color": color, "color_radar": e.color, "confianza": e.confianza,
        "veredicto": r.veredicto, "dictamen": r.dictamen, "pesos_direccion": direccion,
        "cifras": {"precio": _f(s.precio), "costo": _f(s.costo), "margen": _f(r.margen), "minimo": _f(r.minimo),
                   "precio_membresia": _f(r.precio_membresia), "margen_membresia": _f(r.margen_membresia),
                   "lista": r.lista,
                   "porciones": porciones, "por_porcion": _f(s.precio / porciones) if s.precio and porciones else None,
                   "venta_3m": esperado["venta"] if esperado else None, "venta_3m_texto": _miles(esperado["venta"]) if esperado and esperado["venta"] else None,
                   "clase_esperada": esperado["clase"] if esperado else None, "tiendas": tiendas,
                   "venta_cadena_texto": _miles(cad_esperado["venta"]) if cad_esperado and cad_esperado["venta"] else None,
                   "tiendas_cadena": cadena if cad_esperado else None},
        "factores": factores,
        "proveedor": {"nombre": proveedor, "valor": prov.valor if prov else None,
                      "puntaje": prov.puntaje if prov else None, "detalle": prov.detalle if prov else None},
        "demanda": demanda,
        "precio": precio,
        **temas_precio,
        "categoria": categoria,
        "rentabilidad": _rentabilidad(bd, e, s, r, filas.get("rentabilidad") or vacio),
        "parecidos": parecidos,
        "nuevo": {"descripcion": " ".join(x for x in (s.marca, s.nombre) if x), "precio": _f(s.precio),
                  "porciones": porciones, "por_porcion": _f(s.precio / porciones) if s.precio and porciones else None,
                  "por_tienda": demanda["rango"][1] if demanda["rango"] else None,
                  "clase": esperado["clase"] if esperado else None},
        "ventana": v.texto() if v else None,
        "desde": f"{v.desde:%d/%m/%Y}" if v else None, "hasta": f"{v.hasta:%d/%m/%Y}" if v else None,
        "fuentes": r.fuentes,
    }
