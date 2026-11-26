"""Reporte de producto nuevo en PDF, uno por producto evaluado, para mandarlo a Compras (pedido de Diego, 2026-11-13:
«este reporte ayudaría mucho a entregarlo para cada producto validado»; aprobó el plan con «a ver dale, empecemos»).
Mismo formato que el reporte de Wonu Creatina + Inositol que se armó a mano ese día: semáforo con el número al inicio,
dictamen, cuatro cifras, las 8 preguntas que hace el comité (qué es, cuánto ganamos, a cuánto se vende afuera, qué
vendemos hoy parecido, marca y proveedor, regulación, tendencia, cuánto venderá) y lo que se propone a Compras.

Sale de la evaluación vigente del radar y de la venta de SMNBI, sin IA: los mismos números que ve Compras en pantalla.
Reglas de Diego para lo que va a Compras: sin notas de método ni pendientes; las limitaciones solo si cambian una
decisión, en una línea; muchas recomendaciones concretas; diseño cuidado con los colores de la marca.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from statistics import median
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Circle, Drawing, Rect
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from datos.modelos import Producto, Proveedor, Tienda, VentaSemanal
from modulos.compras import mercado_producto as mp
from modulos.compras import politicas_producto as pp
from modulos.compras import radar_productos as rp
from modulos.compras import realidad_producto as rr
from modulos.compras import senal_venta as sv
from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
from modulos.compras.modelos_propuestas import Propuesta
from modulos.metodos import diagrama
from nucleo.modelos import Archivo, OrganizacionExterna

log = logging.getLogger("smn.compras.reporte_producto")

L, LB = diagrama.LETRA, diagrama.LETRA_NEGRITA
NEGRO, GRIS, NARANJA = HexColor("#1D1D1B"), HexColor("#555555"), HexColor("#F5A01A")
LINEA, FONDO, CREMA = HexColor("#E3E3E3"), HexColor("#F3F3F3"), HexColor("#FFF7E8")
ROJO, AMARILLO, VERDE = "#D93025", "#F5A01A", "#1E8E3E"
COLOR = {"rojo": ROJO, "amarillo": AMARILLO, "verde": VERDE}
COLOR_TEXTO = {"rojo": "#B3261E", "amarillo": "#B06F00", "verde": "#1E8E3E"}
LOGO = Path(__file__).resolve().parents[2] / "recursos" / "logo-reporte.png"
ANCHO, ALTO = letter
MARGEN = 40
UTIL = ANCHO - 2 * MARGEN
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
TIENDAS_PRUEBA = 10
SEMANAS_REVISION = 8
IVA = Decimal("1.16")

E = {
    "titulo": ParagraphStyle("titulo", fontName=LB, fontSize=16, leading=19, textColor=NEGRO),
    "sub": ParagraphStyle("sub", fontName=L, fontSize=8.5, leading=11, textColor=GRIS),
    "h2": ParagraphStyle("h2", fontName=LB, fontSize=10.5, leading=13, textColor=NEGRO),
    "p": ParagraphStyle("p", fontName=L, fontSize=8.6, leading=11, textColor=NEGRO),
    "c": ParagraphStyle("c", fontName=L, fontSize=8, leading=10, textColor=NEGRO),
    "cn": ParagraphStyle("cn", fontName=L, fontSize=8, leading=10, textColor=NEGRO, alignment=2),
    "cab": ParagraphStyle("cab", fontName=LB, fontSize=7.8, leading=9.5, textColor=NEGRO),
    "cabn": ParagraphStyle("cabn", fontName=LB, fontSize=7.8, leading=9.5, textColor=NEGRO, alignment=2),
    "gris": ParagraphStyle("gris", fontName=L, fontSize=7.6, leading=9.5, textColor=GRIS),
    "tag": ParagraphStyle("tag", fontName=LB, fontSize=10.5, leading=13, textColor=HexColor("#FFFFFF")),
    "kpi": ParagraphStyle("kpi", fontName=LB, fontSize=13, leading=15, textColor=NEGRO),
    "num": ParagraphStyle("num", fontName=LB, fontSize=30, leading=31, textColor=NEGRO),
}


def _t(x) -> str:
    return escape(str(x)) if x not in (None, "") else ""


def _pesos(x: Decimal | float | None) -> str:
    return "—" if x is None else f"${float(x):,.2f}"


def _pct(x: Decimal | float | None) -> str:
    return "—" if x is None else f"{float(x):.1f} %"


def _n(x: float | Decimal) -> str:
    x = float(x)
    return f"{x:,.0f}" if abs(x) >= 100 or abs(x - round(x)) < 0.05 else f"{x:,.1f}"


def _fecha(f) -> str:
    return f"{f.day} {MESES[f.month - 1]} {f.year}"


def margen_de(precio: Decimal | None, costo: Decimal | None) -> Decimal | None:
    """(precio ÷ 1.16 − costo) ÷ (precio ÷ 1.16), en %. Igual que el radar."""
    if not precio or not costo or precio <= 0:
        return None
    base = precio / IVA
    return ((base - costo) / base * 100).quantize(Decimal("0.1"))


# ---------------------------------------------------------------- datos

@dataclass
class Fila:
    sku: str
    descripcion: str
    clasificacion: str | None
    al_mes: float | None
    tiendas: int | None
    por_tienda: float | None
    precio: Decimal | None  # promedio cobrado, con IVA
    margen: Decimal | None
    etiqueta: str = ""  # «misma marca», «mismo formato»…


@dataclass
class Reporte:
    nombre: str
    marca: str | None
    presentacion: str
    clasificacion: str | None
    codigo_barras: str | None
    proveedor: str | None
    tipo: str  # idea / propuesta
    fecha: datetime
    puntaje: int | None
    color: str
    confianza: str | None
    veredicto: str
    dictamen: str
    precio: Decimal | None
    costo: Decimal | None
    margen: Decimal | None
    minimo: Decimal
    margen_sub: Decimal | None
    referencia: Decimal | None  # precio de en medio del mercado
    precio_unidad: str | None  # nuestro precio por gramo (o por gramo de activo)
    escenarios: list[tuple[str, Decimal | None, Decimal | None, Decimal | None]]
    mercado: list[tuple[str, str, Decimal, str | None]]  # producto, dónde, precio, por unidad
    parecidos: list[Fila]
    de_marca: list[Fila]
    factores: list[tuple[str, Decimal, int | None, str | None]]
    kpis: list[tuple[str, str, bool]]
    preguntas: dict[str, list[str]]
    estimado: dict | None
    acciones: list[tuple[str, str]]
    fuentes: list[str]
    fotos: list[bytes] = field(default_factory=list)
    ventana: str | None = None
    # 22 nov 2026: tipo de producto (lista A–F) y el precio de membresía con su margen y su mínimo
    lista: str | None = None  # «lista D, Nutrición deportiva nacional»; None si va por omisión
    precio_membresia: Decimal | None = None
    membresia_calculada: bool = False
    margen_membresia: Decimal | None = None
    minimo_membresia: Decimal | None = None
    anaquel: float | None = None  # % de nuestro precio contra los parecidos que ya vendemos


def _sujeto(bd: Session, e: ProductoEvaluacion) -> tuple[rp.Sujeto, str | None, list[int]]:
    """El producto evaluado, quién lo surtiría y sus fotos."""
    if e.propuesta_id:
        p = bd.get(Propuesta, e.propuesta_id)
        s = rp.sujeto_de_propuesta(p)
        org = bd.get(OrganizacionExterna, p.organizacion_id) if p.organizacion_id else None
        s.proveedor_intelisis = org.proveedor_intelisis if org else None
        proveedor = (s.proveedor_nombres or [None])[0] or (org.nombre if org and hasattr(org, "nombre") else None)
        from modulos.compras.rutas_comite import _fotos_propuesta

        return rp.poner_familia(bd, s), proveedor, _fotos_propuesta(p)
    i = bd.get(ProductoIdea, e.idea_id)
    s = rp.sujeto_de_idea(i)
    proveedor = i.proveedor_nuevo
    if i.proveedor_intelisis:
        proveedor = bd.scalar(select(Proveedor.nombre).where(Proveedor.proveedor == i.proveedor_intelisis)) or i.proveedor_intelisis
    return rp.poner_familia(bd, s), proveedor, [f.archivo_id for f in i.fotos]


def _fotos(bd: Session, ids: list[int]) -> list[bytes]:
    """Hasta 2 fotos, reducidas a JPG para que el PDF pese poco (el de Wonu pesaba 19 MB con las fotos originales)."""
    from PIL import Image as PILImage

    from nucleo.archivos import _raiz

    salida = []
    raiz = _raiz()
    for fid in ids[:2]:
        a = bd.get(Archivo, fid)
        ruta = (raiz / a.ruta_almacenamiento).resolve() if a else None
        if not ruta or raiz not in ruta.parents or not ruta.is_file():
            continue
        try:
            with PILImage.open(ruta) as im:
                im = im.convert("RGB")
                im.thumbnail((360, 560))
                b = BytesIO()
                im.save(b, "JPEG", quality=78)
                salida.append(b.getvalue())
        except Exception:  # noqa: BLE001 - una foto que no se lee no detiene el reporte
            log.warning("Reporte de producto: no se pudo leer la foto %s", fid)
    return salida


def venta_skus(bd: Session, v: rr.Ventana, skus: list[str]) -> dict[str, dict]:
    """Por SKU, en la ventana: piezas al mes, tiendas, piezas por tienda al mes, precio promedio cobrado con IVA y margen."""
    if not skus:
        return {}
    q = (select(VentaSemanal.sku, func.sum(rr.NETAS), func.count(VentaSemanal.tienda.distinct()),
                func.count(VentaSemanal.semana.distinct()), func.sum(VentaSemanal.importe), func.sum(VentaSemanal.costo))
         .where(*v.filtro(), VentaSemanal.sku.in_(skus)).group_by(VentaSemanal.sku))
    salida = {}
    for sku, piezas, tiendas, semanas, importe, costo in bd.execute(q):
        if not piezas or piezas <= 0:
            continue
        x = rr.VentaSku(float(piezas), tiendas, semanas, 0, 0)
        precio = (Decimal(importe) / Decimal(piezas) * IVA).quantize(Decimal("0.01")) if importe else None
        margen = ((importe - costo) / importe * 100).quantize(Decimal("0.1")) if importe and costo and importe > 0 else None
        salida[sku] = {"al_mes": x.al_mes, "tiendas": tiendas, "por_tienda": x.por_tienda_mes, "precio": precio,
                       "margen": margen}
    return salida


_METODO = ("La IA eligió", "Sin IA:", "se tomaron las señales", "provisional", "Provisional")


def _sin_metodo(texto: str | None) -> str:
    """Quita las frases que explican cómo se calculó (lo que va a Compras no lleva notas de método)."""
    partes = re.split(r"(?<=[.;])\s+", (texto or "").strip())
    return " ".join(x for x in partes if not any(m in x for m in _METODO)).rstrip(" .;:")


def _fila(p: Producto, venta: dict, etiqueta: str = "") -> Fila:
    x = venta.get(p.sku) or {}
    return Fila(p.sku, rp.con_marca(p), p.clasificacion, x.get("al_mes"), x.get("tiendas"), x.get("por_tienda"),
                x.get("precio") or p.precio_lista_con_impuestos, x.get("margen"), etiqueta)


def de_la_marca(bd: Session, marca: str | None, fuera: set[str]) -> list[Producto]:
    """Lo que ya vendemos de la misma marca, aunque sea otro tipo de producto (Wonu: su colágeno en sobre)."""
    if len(rp._compacta(marca)) < 3:
        return []
    return [p for p in bd.scalars(select(Producto).where(Producto.activo == true()))
            if p.sku not in fuera and rp.producto_de_la_marca(marca, p)]


def tendencia_subcategoria(bd: Session, v: rr.Ventana, subcategoria: str) -> tuple[float, float, int] | None:
    return rr.tendencia_subcategoria(bd, v, subcategoria)


def categorias_tienda(bd: Session, v: rr.Ventana, skus: list[str]) -> list[str]:
    """Las categorías de tienda (AA, A, B…) donde más se venden los parecidos, de la que más a la que menos."""
    if not skus:
        return []
    filas = bd.execute(select(Tienda.categoria, func.sum(rr.NETAS)).join(Tienda, Tienda.almacen == VentaSemanal.tienda)
                       .where(*v.filtro(), VentaSemanal.sku.in_(skus), Tienda.categoria.is_not(None),
                              Tienda.categoria != rr.MAYOREO)
                       .group_by(Tienda.categoria).order_by(func.sum(rr.NETAS).desc())).all()
    return [c for c, piezas in filas if piezas and piezas > 0]


def _estimado(s: rp.Sujeto, parecidos: list[Fila], prueba: bool, margen: Decimal | None,
              pronostico: list[float] | None = None, usados: set[str] | None = None) -> dict | None:
    """Piezas por tienda al mes × número de tiendas. Desde el 19 nov 2026 (plan de Demanda: una sola cifra) sale del
    pronóstico a 12 semanas, la misma que califica la Demanda; sin pronóstico, de los parecidos de precio parecido (los
    de precio muy distinto, un sobre de $25 contra una caja de $599, solo cuentan si no hay otros)."""
    con = [f for f in parecidos if f.por_tienda]
    if not con and not pronostico:
        return None
    # Los mismos parecidos que usan la Demanda y el pronóstico (precio cercano por pieza y por unidad, 19 nov 2026)
    cerca = ([f for f in con if f.sku in usados] if usados is not None else
             [f for f in con if s.precio and f.precio and rp.RANGO_PRECIO[0] <= s.precio / f.precio <= rp.RANGO_PRECIO[1]])
    base = cerca or con
    por_tienda = float(pronostico[1]) if pronostico else float(median([f.por_tienda for f in base]))
    tiendas = TIENDAS_PRUEBA if prueba else max(TIENDAS_PRUEBA, int(median([f.tiendas for f in base if f.tiendas] or [0])))
    piezas = por_tienda * tiendas
    venta = float(s.precio / IVA) * piezas if s.precio else None
    cercanos = sorted(base, key=lambda f: abs(f.por_tienda - por_tienda))
    return {"por_tienda": por_tienda, "tiendas": tiendas, "piezas": piezas, "venta": venta,
            "margen": venta * float(margen) / 100 if venta and margen is not None else None,
            "como": [f.descripcion for f in cercanos[:2]], "prueba": prueba, "rango": pronostico}


def _veredicto(dictamen: str, color: str) -> tuple[str, bool]:
    """La etiqueta corta del dictamen y si es una prueba en pocas tiendas."""
    t = dictamen.removeprefix(rp.DICTAMEN).lower()
    if t.startswith("no meter"):
        return "NO METER", False
    if t.startswith("negociar"):
        return "NEGOCIAR ANTES DE METER", True
    if t.startswith("meter"):
        return "METER", False
    if t.startswith("se puede meter"):
        return f"PROBAR EN {TIENDAS_PRUEBA} TIENDAS", True
    return {"verde": "METER", "amarillo": f"PROBAR EN {TIENDAS_PRUEBA} TIENDAS", "rojo": "NO METER"}[color], color == "amarillo"


def armar(bd: Session, e: ProductoEvaluacion, ahora: datetime | None = None, con_fotos: bool = True) -> Reporte:
    s, proveedor, foto_ids = _sujeto(bd, e)
    ahora = ahora or datetime.now()
    color = e.color_final or e.color or "amarillo"
    v = rr.ventana(bd)
    mins = rp.minimos(bd, s)
    minimo = mins.lista
    factores = {f.factor: f for f in e.factores}
    lineas = (e.explicacion or "").split("\n\n")
    dictamen = next((x for x in lineas if x.startswith(rp.DICTAMEN)), "")
    veredicto, prueba = _veredicto(dictamen, color)
    mercado_ = mp.Mercado.de_json(e.mercado)
    # El mismo precio de mercado con que se califica la mitad de afuera: sin la página de la marca ni lo que vio Compras
    # (Wonu 22 nov 2026: Rentabilidad usaba $626 con Chedraui y Precio $599)
    con_sim = [(p, c.similitud) for c in e.comparables if (p := bd.get(Producto, c.producto_id))]
    mismo = next((p for p, sim in con_sim if sim == 1), None)
    referencia = rp.precio_afuera(s, con_sim, mercado_, mismo).meta
    margen = s.margen
    margen_sub = None
    if v and e.subcategoria and (real := rr.margen_real(bd, v, e.subcategoria)):
        margen_sub = real[0]
    if mismo:  # ya lo vendemos: la membresía es la de su SKU
        s.precio_membresia, s.membresia_calculada = mismo.precio_membresia_con_impuestos, False

    # 1. Qué es
    tam = rp.tamano(s.contenido, s.nombre, s.descripcion)
    formato = rp.formato_sujeto(s)
    presentacion = " · ".join(x for x in (s.contenido, s.forma if s.forma and rp._norm(s.forma) not in rp._norm(s.contenido)
                                                              else None) if x) or (rp.NOMBRE_FORMATO.get(formato) or "")
    clasificacion = " › ".join(x.capitalize() for x in (e.rama, e.subcategoria, e.segmento) if x) or None
    unidad = None
    # Cápsulas, tabletas y gomitas: por pieza, que es como se compara el Precio (25 nov 2026, BDM Life: decía solo
    # «$9.56 por gramo de berberina» y el factor iba por cápsula)
    pieza = {"capsula": "cápsula", "tableta": "tableta", "gomita": "gomita"}.get(formato or "")
    pz = rp.solo_piezas(tam, formato).get("pz") if tam and pieza else None
    if s.precio and pz:
        unidad = f"{_pesos(s.precio / pz)} por {pieza}"
        if s.activo_g:
            unidad += (f" ({_pesos(s.precio / s.activo_g)} por gramo de "
                       f"{rp.solo_principal(s.ingrediente).lower() if s.ingrediente else 'activo'})")
    elif s.precio and s.activo_g:
        unidad = f"{_pesos(s.precio / s.activo_g)} por gramo de {rp.solo_principal(s.ingrediente).lower() if s.ingrediente else 'activo'}"
    elif s.precio and tam:
        dim = "g" if "g" in tam else "ml" if "ml" in tam else "pz"
        unidad = rp._precio_unidad(s.precio / tam[dim], dim)

    # 4. Parecidos y lo de la marca
    productos = [bd.get(Producto, c.producto_id) for c in e.comparables]
    productos = [p for p in productos if p]
    skus = {p.sku for p in productos}
    marca = de_la_marca(bd, s.marca, skus)
    venta = venta_skus(bd, v, [p.sku for p in productos + marca]) if v else {}
    filas = []
    for p in productos:
        su = rp.formato(p.descripcion)
        etiqueta = ("ya lo vendemos" if any(c.similitud == 1 and c.producto_id == p.producto_id for c in e.comparables)
                    else "mismo formato" if su and su == formato else "")
        filas.append(_fila(p, venta, etiqueta))
    # Los dos con los que se compara en el dictamen van primero; luego los de precio cercano (los que usan la Demanda y
    # el pronóstico, para que el reporte enseñe los productos que cita), y al final los demás; cada grupo de más a
    # menos venta (19 nov 2026: BASMAC salía en el pronóstico y no en la tabla, la tapaban los más vendidos)
    citados = [f for f, p in zip(filas, productos) if p.precio_lista_con_impuestos][:2]
    usados = {p.sku for p in rp.parecidos_para_demanda(s, [(p, Decimal(0)) for p in productos], None)}
    cercanos = {id(f) for f, p in zip(filas, productos) if p.sku in usados and len(usados) < len(productos)}
    filas = citados + sorted((f for f in filas if f not in citados),
                             key=lambda f: (id(f) not in cercanos, -(f.al_mes or 0)))
    filas_marca = sorted((_fila(p, venta, "misma marca") for p in marca), key=lambda f: -(f.al_mes or 0))
    filas_marca = [f for f in filas_marca if f.al_mes][:4]

    # 2. Cuánto ganamos
    escenarios = []
    if s.precio:
        escenarios.append(("Nuestro precio", s.precio, s.costo, margen))
    if referencia and s.costo and (not s.precio or abs(referencia - s.precio) >= 1):
        escenarios.append(("Al precio de en medio del mercado", referencia, s.costo, margen_de(referencia, s.costo)))
    metas = rp.metas(s, minimo, referencia)
    if metas:
        costo, precio_meta, costo_meta, pasa = metas
        if not pasa:
            escenarios.append((f"Precio mínimo para el {_n(minimo)} %", precio_meta.quantize(Decimal("0.01")), costo, minimo))
        if margen is not None and margen < minimo:
            escenarios.append((f"Costo meta para el {_n(minimo)} %", min(s.precio, referencia) if referencia else s.precio,
                               costo_meta.quantize(Decimal("0.01")), minimo))

    # 3. Afuera
    afuera = []
    dim = next((d for d in ("g", "ml", "pz") if d in tam), None)
    for p in sorted(mercado_.precios if mercado_ else [], key=lambda p: float(p["precio"]))[:8]:
        precio = Decimal(str(p["precio"]))
        suyo = rp.tamano(p.get("titulo"))
        por = rp._precio_unidad(precio / suyo[dim], dim) if dim and dim in suyo and suyo[dim] else None
        donde = p.get("vendedor") or "—"
        if rp.es_de_la_marca(p, s.marca):  # no es competencia: es lo que sugiere la marca (22 nov 2026)
            donde = f"{donde} (precio sugerido de la marca)"
        afuera.append((p.get("titulo") or s.nombre, donde, precio, por))
    for precio, donde in s.mercado:
        if s.activo_g:  # es el mismo producto que vio Compras: mismo contenido
            por = f"{_pesos(precio / s.activo_g)} por gramo de {rp.solo_principal(s.ingrediente).lower() if s.ingrediente else 'activo'}"
        elif dim:
            por = rp._precio_unidad(precio / tam[dim], dim)
        else:
            por = None
        afuera.append((s.nombre, f"{donde} (lo vio Compras)" if s.tipo == "idea" else donde, precio, por))

    # Factores y cifras
    peso, _ = rp.pesos(bd)
    # Evaluaciones de antes del 25 nov 2026 no traen los dos temas del Precio: se enseña el Precio con su peso guardado
    lista_f = [(rp.NOMBRES[f], factores[f].peso if f in factores else peso[f], factores[f].puntaje if f in factores else None,
                _valor_tema(f, factores[f]) if f in factores else None)
               for f in rp.FACTORES if f in factores or not factores]
    # Solo los que pesan (Dirección, 20 nov 2026: Tendencia va dentro de la Demanda y Proveedor es contexto), del que
    # más pesa al que menos
    lista_f = sorted((x for x in lista_f if x[1]), key=lambda x: -x[1])
    tend = tendencia_subcategoria(bd, v, e.subcategoria) if v and e.subcategoria else None
    try:
        from modulos.compras import pronostico as pn

        pron = pn.Pronostico.de_json(e.pronostico)
    except (ValueError, TypeError, KeyError):
        pron = None
    estimado = _estimado(s, filas, prueba, margen, pron.rango(12) if pron else None, usados)
    kpis = []
    if margen is not None:
        kpis.append((_pct(margen), f"margen a {_pesos(s.precio)} con costo {_pesos(s.costo)} (mínimo {_n(minimo)} %"
                     + (f"; {e.subcategoria.lower()} en SMN {_pct(margen_sub)})" if margen_sub else ")"), margen < minimo))
        if (mm := s.margen_membresia) is not None and not mismo and mins.membresia is not None:
            kpis.append((_pct(mm), f"margen con membresía a {_pesos(s.precio_membresia)}"
                         + (", calculada con su lista" if s.membresia_calculada else "") + f" (mínimo {_n(mins.membresia)} %)",
                         mm < mins.membresia))
    if tend:
        cambio = (tend[0] / tend[1] - 1) * 100
        kpis.append((f"{cambio:+.0f} %", f"piezas de {e.subcategoria.lower()} en SMN, últimas 13 semanas contra las 13 "
                     "anteriores", cambio < 0))
    if estimado:
        kpis.append((f"~{_n(estimado['piezas'])}", f"piezas al mes esperadas en {estimado['tiendas']} tiendas "
                     f"(~{_n(estimado['por_tienda'])} por tienda"
                     + (", según el pronóstico)" if estimado["rango"] else ", como sus parecidos)"), False))
    # Precio contra nuestro anaquel (Dirección, 22 nov 2026): la misma mitad que usa la calificación
    anaquel = None
    if s.precio and productos and not any(c.similitud == 1 for c in e.comparables):
        rp.cargar_fichas(bd, productos)
        sims = {c.producto_id: c.similitud for c in e.comparables}
        f_an = rp.precio_anaquel(s, [(p, sims.get(p.producto_id) or Decimal(0)) for p in productos])
        if f_an.puntaje is not None and f_an.meta:
            anaquel = (s.precio / f_an.meta - 1) * 100
    if referencia and s.precio:
        dif = (s.precio / referencia - 1) * 100
        kpis.append((f"{dif:+.0f} %", f"nuestro precio contra el de en medio del mercado ({_pesos(referencia)})"
                     + (f"; contra nuestro anaquel {anaquel:+.0f} %" if anaquel is not None else ""), dif > 5))
    elif anaquel is not None:
        kpis.append((f"{anaquel:+.0f} %", "nuestro precio contra los parecidos que ya vendemos", anaquel > 5))
    elif unidad:
        kpis.append((unidad.split(" por ")[0], "por " + unidad.split(" por ", 1)[1], False))

    # Preguntas 5 a 8, con lo que encontró el radar
    q: dict[str, list[str]] = {}
    prov = factores.get("proveedor")
    q["proveedor"] = []
    if proveedor:
        q["proveedor"].append(f"Lo surtiría <b>{_t(proveedor)}</b>.")
    if prov and prov.puntaje is not None and prov.valor and not prov.valor.startswith("Lo surtir"):
        if prov.valor.startswith("Proveedor "):
            q["proveedor"].append(f"Su calificación como proveedor es <b>{prov.puntaje} de 100</b> (cumplimiento, venta, "
                                  "costo e inventario de lo que ya nos surte).")
        elif prov.valor.startswith("Surte "):
            q["proveedor"].append(f"{_t(prov.valor)} de las piezas que se le piden: califica <b>{prov.puntaje} de 100</b>.")
        else:
            q["proveedor"].append(f"{_t(prov.valor)}: califica <b>{prov.puntaje} de 100</b>.")
    elif not proveedor:
        q["proveedor"].append("Todavía no tiene proveedor: hay que conseguirlo antes del alta.")
    if filas_marca:
        q["proveedor"].append("De la marca ya vendemos: " + "; ".join(
            f"{_t(f.descripcion)} ({f.clasificacion or 'sin clasificación'}, {_n(f.al_mes)} piezas al mes)" for f in filas_marca[:3]) + ".")
    rev = pp.Revision.de_json(e.politicas)
    q["regulacion"] = []
    if rev and rev.rechazo:
        q["regulacion"].append(f"<b>No pasa</b> la regla «{_t(rev.rechazo.get('titulo'))}» de Compras: {_t(rev.rechazo.get('motivo'))}")
    for a in (rev.avisos if rev else [])[:3]:
        q["regulacion"].append(f"<b>Aviso:</b> podría caer en «{_t(a.get('titulo'))}». {_t(a.get('motivo'))}")
    if rev and not rev.rechazo and not rev.avisos:
        q["regulacion"].append("No cae en ninguna regla de rechazo ni de umbral de Compras.")
    if s.registro_sanitario:
        q["regulacion"].append("El proveedor dice que tiene registro sanitario.")
    t = factores.get("tendencia")
    q["tendencia"] = []
    if tend:
        cambio = (tend[0] / tend[1] - 1) * 100
        q["tendencia"].append(f"En SMN: {e.subcategoria.lower()} vendió {_n(tend[0])} piezas en las últimas 13 semanas, "
                              f"{abs(cambio):.0f} % {'más' if cambio >= 0 else 'menos'} que en las 13 anteriores, con "
                              f"{tend[2]} productos con venta.")
    if t and t.puntaje is not None:
        q["tendencia"].append(f"Afuera: {_t(_sin_metodo(t.detalle))}")
    elif t:
        q["tendencia"].append("Afuera: el radar de tendencias no tiene señales que hablen de este producto.")
    for x in sorted(sv.de_lista(mercado_.senales if mercado_ else []), key=lambda x: -x.puntos())[:3]:
        if x.texto():
            q["tendencia"].append(f"Se vende afuera: <b>{_t(sv.frase(x))}</b>.")
    d = factores.get("demanda")
    if d and d.valor:
        q["tendencia"].append(f"Demanda: {_t(d.valor[0].lower() + d.valor[1:])}.")
    q["venta"] = []
    if estimado:
        como = " y ".join(_t(x) for x in estimado["como"])
        if r12 := estimado["rango"]:
            texto = (f"Unas <b>{_n(r12[1])} piezas por tienda al mes</b> en sus primeras 12 semanas, entre {_n(r12[0])} y "
                     f"{_n(r12[2])}, según cómo arrancaron los productos nuevos de 2026" + (f" y lo que venden {como}" if como else ""))
        else:
            texto = f"Unas <b>{_n(estimado['por_tienda'])} piezas por tienda al mes</b>, como {como}"
        q["venta"].append(f"{texto}. En {estimado['tiendas']} tiendas: <b>~{_n(estimado['piezas'])} piezas al mes</b>"
                          + (f", unos {_pesos(estimado['venta'])[:-3]} de venta sin IVA" if estimado["venta"] else "")
                          + (f" y {_pesos(estimado['margen'])[:-3]} de margen." if estimado["margen"] else "."))
    if pron and pron.rango(12):
        if pron.misma_sub:  # contra productos reales de su subcategoría (Diego, 20 nov 2026)
            q["venta"].append("Lanzamientos de 2026 de su misma subcategoría, piezas por tienda al mes en sus semanas 9 a "
                              "12: " + "; ".join(f"{_t(x['descripcion'])} {_n(x['por_tienda'])}" for x in pron.misma_sub[:6])
                              + (f" y {len(pron.misma_sub) - 6} más" if len(pron.misma_sub) > 6 else "") + ".")
        if (pr := pron.examen.get("prueba")) and pr.get("probados"):
            q["venta"].append(f"Qué tan seguido atina: a {pr['probados']} productos que lanzamos en 2026 se les pronosticó "
                              f"como si fueran nuevos y atinó el color de la Demanda en {pr['color']} y la clase AA–E en "
                              f"{pr['clase']}.")
        if pron.grupos:
            mejores = sorted(pron.grupos, key=lambda g: -g.medio)[:3]
            q["venta"].append("Donde más venderá: " + "; ".join(
                f"{_t(g.nombre)} ({_n(g.medio)} por tienda)" for g in mejores) + ".")
    cats = categorias_tienda(bd, v, [f.sku for f in filas if f.al_mes]) if v else []
    if cats:
        q["venta"].append(f"Tiendas: las de categoría {' y '.join(cats[:2])}, donde más se venden sus parecidos.")

    acciones = _acciones(s, veredicto, prueba, minimo, margen, referencia, metas, filas, filas_marca, proveedor,
                         estimado, cats, rev, factores)
    fuentes = []
    if v:
        fuentes.append(f"SMNBI, venta de mostrador del {_fecha(v.desde)} al {_fecha(v.hasta)}")
    if mercado_ and mercado_.precios:
        fuentes.append("precios públicos" + (f" del {_fecha(datetime.fromisoformat(mercado_.buscado_en))}" if mercado_.buscado_en else "")
                       + ": " + ", ".join(dict.fromkeys(p["vendedor"] for p in mercado_.precios[:6])))
    fuentes.append("captura de Compras" if s.tipo == "idea" else "cuestionario del proveedor")
    if t and t.puntaje is not None:
        fuentes.append("radar de tendencias")
    return Reporte(
        nombre=s.nombre, marca=s.marca, presentacion=presentacion, clasificacion=clasificacion,
        codigo_barras=s.codigo_barras, proveedor=proveedor, tipo=s.tipo, fecha=ahora, puntaje=e.puntaje, color=color,
        confianza=e.confianza, veredicto=veredicto, dictamen=dictamen.removeprefix(rp.DICTAMEN), precio=s.precio,
        costo=s.costo, margen=margen, minimo=minimo, margen_sub=margen_sub, referencia=referencia,
        lista=mins.de_lista.texto() if s.lista and mins.de_lista else None, precio_membresia=s.precio_membresia,
        membresia_calculada=s.membresia_calculada, margen_membresia=s.margen_membresia if not mismo else None,
        minimo_membresia=mins.membresia, anaquel=float(anaquel) if anaquel is not None else None,
        precio_unidad=unidad, escenarios=escenarios, mercado=afuera, parecidos=filas[:7], de_marca=filas_marca,
        factores=lista_f, kpis=kpis[:4], preguntas=q, estimado=estimado, acciones=acciones, fuentes=fuentes,
        fotos=_fotos(bd, foto_ids) if con_fotos else [], ventana=v.texto() if v else None)


def _acciones(s, veredicto, prueba, minimo, margen, referencia, metas, filas, filas_marca, proveedor, estimado, cats,
              rev, factores) -> list[tuple[str, str]]:
    """Lo que se propone a Compras, en orden: alta o negociación, precio, prueba, exhibición, revisión y cuidados."""
    a = []
    if veredicto == "NO METER":
        motivo = "" if not rev or not rev.rechazo else f" (regla «{rev.rechazo.get('titulo')}»)"
        a.append((f"No darlo de alta por ahora{motivo}; volver a evaluarlo si cambia el costo o el precio.", "Compras"))
    elif margen is not None and margen < minimo and metas:
        costo, precio_meta, costo_meta, pasa = metas
        if pasa:
            a.append((f"Negociar costo de {_pesos(costo_meta)} sin IVA o menos (hoy {_pesos(costo)}). Subirle el precio no "
                      f"funciona: tendría que venderse en {_pesos(precio_meta)} y el mercado está en {_pesos(referencia)}.",
                      "Compras"))
        else:
            a.append((f"Negociar costo de {_pesos(costo_meta)} sin IVA (hoy {_pesos(costo)}) o venderlo en "
                      f"{_pesos(precio_meta)} para dejar {_n(minimo)} %.", "Compras"))
    elif s.precio:
        piso = f" (no bajar de {_pesos(metas[1])})" if metas and not metas[3] else ""
        costo = f" con costo de {_pesos(s.costo)} sin IVA" if s.costo else ""
        a.append((f"Darlo de alta{costo} y precio de {_pesos(s.precio)}{piso}.", "Compras"))
    if referencia and s.precio and s.precio > referencia * Decimal("1.05"):
        a.append((f"Revisar el precio: está {float((s.precio / referencia - 1) * 100):.0f} % arriba del de en medio del "
                  f"mercado ({_pesos(referencia)}).", "Compras"))
    if veredicto != "NO METER":
        if prueba:
            donde = f" de categoría {' y '.join(cats[:2])}" if cats else ""
            a.append((f"Prueba en {TIENDAS_PRUEBA} tiendas{donde}, con devolución de lo no vendido acordada con el "
                      "proveedor.", "Comité / Compras"))
        vecinos = [f.descripcion for f in filas if f.al_mes][:2]
        if vecinos:
            a.append(("Exhibirlo junto a " + " y ".join(vecinos) + ", que ya se venden.", "Compras / Tiendas"))
        if estimado:
            a.append((f"A las {SEMANAS_REVISION} semanas: ampliar si pasa de {_n(estimado['por_tienda'])} piezas por tienda "
                      f"al mes; retirar si queda en menos de {_n(estimado['por_tienda'] / 2)}.", "Comité"))
    if filas_marca and proveedor:
        a.append((f"Negociar con {proveedor} junto con lo que ya vendemos de la marca ({filas_marca[0].descripcion}).",
                  "Compras"))
    for x in (rev.avisos if rev else [])[:1]:
        a.append((f"Revisar el aviso «{x.get('titulo')}» antes de exhibirlo.", "Compras / Regulación"))
    if (p := factores.get("proveedor")) and p.mejora:
        a.append((p.mejora, "Proveedor"))
    return a[:7]


# ---------------------------------------------------------------- PDF

# Los mismos colores y la misma regla que la pantalla del comité (web/lib/pantalla.ts)
HEX_FACTOR = {"verde": "#2E8B57", "amarillo": "#D99A1B", "rojo": "#C8412F"}
SIN_COLOR, PISTA = "#9B9B96", "#ECECEA"


def _color_puntaje(p: int | None) -> str | None:
    return None if p is None else "verde" if p > 80 else "amarillo" if p >= 60 else "rojo"


def _arco(c, cx: float, cy: float, r: float, desde: float, grados: float, ancho: float, color: str, redondo: bool = False):
    """Arco en el sentido del reloj; `desde` en grados contados desde las 12."""
    if grados <= 0:
        return
    c.setStrokeColor(HexColor(color))
    c.setLineWidth(ancho)
    c.setLineCap(1 if redondo else 0)
    if grados >= 359.9:
        c.circle(cx, cy, r, stroke=1, fill=0)
        return
    c.arc(cx - r, cy - r, cx + r, cy + r, startAng=90 - desde, extent=-grados)


class Anillo(Flowable):
    """Anillo de aporte, como en la pantalla del comité: cada factor ocupa lo que aporta a la calificación, con el color
    de su calificación; en medio el número y el color."""

    def __init__(self, puntaje: int | None, color: str, partes: list[tuple[float, str | None]], tam: float = 128):
        super().__init__()
        self.puntaje, self.color, self.partes, self.tam = puntaje, color, partes, tam
        self.width = self.height = tam

    def draw(self):
        c, t = self.canv, self.tam
        cx = cy = t / 2
        grueso = t * 0.085
        r = t / 2 - grueso / 2 - 1
        _arco(c, cx, cy, r, 0, 360, grueso, PISTA)
        con = [(a, col) for a, col in self.partes if a > 0]
        hueco = 2.2 if len(con) > 1 else 0
        inicio = 0.0
        for aporte, col in con:
            g = max(0.0, aporte / 100 * 360 - hueco)
            _arco(c, cx, cy, r, inicio, g, grueso, HEX_FACTOR.get(col or "", SIN_COLOR))
            inicio += g + hueco
        c.setFillColor(NEGRO)
        c.setFont(LB, t * 0.27)
        c.drawCentredString(cx, cy + t * 0.03, str(self.puntaje) if self.puntaje is not None else "—")
        c.setFillColor(GRIS)
        c.setFont(L, t * 0.075)
        c.drawCentredString(cx, cy - t * 0.07, "de 100")
        # Píldora del color
        texto = self.color.upper()
        c.setFont(LB, t * 0.068)
        w = c.stringWidth(texto, LB, t * 0.068) + t * 0.12
        h = t * 0.11
        base = HexColor(HEX_FACTOR.get(self.color, SIN_COLOR))
        c.setFillColor(Color(base.red, base.green, base.blue, alpha=0.14))
        c.setStrokeColor(base)
        c.setLineWidth(0.6)
        c.roundRect(cx - w / 2, cy - t * 0.215, w, h, h / 2, stroke=1, fill=1)
        c.setFillColor(HexColor(COLOR_TEXTO.get(self.color, "#555555")))
        c.drawCentredString(cx, cy - t * 0.215 + h * 0.3, texto)


class Dona(Flowable):
    """Dona del factor, como en la pantalla del comité: el anillo de afuera es lo que pesa; el de adentro, su
    calificación; la marca es el corte de verde (80)."""

    def __init__(self, puntaje: int | None, peso: float, tam: float = 62):
        super().__init__()
        self.puntaje, self.peso, self.tam = puntaje, peso, tam
        self.width = self.height = tam

    def draw(self):
        c, t = self.canv, self.tam
        cx = cy = t / 2
        r1, r2 = t * 0.46, t * 0.37
        _arco(c, cx, cy, r1, 0, 360, t * 0.02, PISTA)
        _arco(c, cx, cy, r1, 0, self.peso / 100 * 360, t * 0.02, "#6B6B67", True)
        _arco(c, cx, cy, r2, 0, 360, t * 0.09, PISTA)
        if self.puntaje is not None:
            col = HEX_FACTOR[_color_puntaje(self.puntaje)]
            _arco(c, cx, cy, r2, 0, self.puntaje / 100 * 360, t * 0.09, col, True)
        import math
        a = math.radians(90 - 0.8 * 360)
        c.setStrokeColor(NEGRO)
        c.setLineWidth(0.8)
        c.setLineCap(0)
        c.line(cx + (r2 - t * 0.07) * math.cos(a), cy + (r2 - t * 0.07) * math.sin(a),
               cx + (r2 + t * 0.07) * math.cos(a), cy + (r2 + t * 0.07) * math.sin(a))
        c.setFillColor(NEGRO)
        c.setFont(LB, t * 0.26)
        c.drawCentredString(cx, cy - t * 0.02, str(self.puntaje) if self.puntaje is not None else "—")
        c.setFillColor(GRIS)
        c.setFont(L, t * 0.1)
        c.drawCentredString(cx, cy - t * 0.17, "de 100" if self.puntaje is not None else "sin datos")


# Un tema del Precio sin datos no cuenta y su peso se reparte (25 nov 2026)
SIN_TEMA_PRECIO = {"precio_afuera": "No cuenta: el radar de precios no lo encontró a la venta afuera.",
                   "precio_anaquel": "No cuenta: no hay con qué compararlo en nuestro anaquel."}


def _valor_tema(f: str, x) -> str | None:
    if x.puntaje is None and f in SIN_TEMA_PRECIO:
        return SIN_TEMA_PRECIO[f]
    return (("Provisional. " if x.provisional and f.startswith("precio") else "") + (x.valor or "")) or None


def _corto(x: str | None, largo: int = 95) -> str:
    """La primera idea del porqué, como en la tarjeta de la pantalla."""
    if not x:
        return "Sin datos todavía."
    t = re.split(r"(?<=[^0-9])\. |; ", x, maxsplit=1)[0].rstrip(".")
    return t + "." if len(t) <= largo else t[: largo - 1].rsplit(" ", 1)[0].rstrip(",;(") + "…"


def _semaforo(color: str) -> Drawing:
    d = Drawing(34, 92)
    d.add(Rect(0, 0, 34, 92, rx=15, ry=15, fillColor=NEGRO, strokeColor=None))
    for i, c in enumerate(("rojo", "amarillo", "verde")):
        base = HexColor(COLOR[c])
        prendido = c == color
        if prendido:
            d.add(Circle(17, 74 - i * 28, 14.5, fillColor=Color(base.red, base.green, base.blue, alpha=0.35), strokeColor=None))
        d.add(Circle(17, 74 - i * 28, 11, strokeColor=None,
                     fillColor=base if prendido else Color(base.red, base.green, base.blue, alpha=0.28)))
    return d


def _h2(texto: str) -> Table:
    t = Table([[Paragraph(texto, E["h2"])]], colWidths=[UTIL])
    t.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, 0), 4, NARANJA), ("LEFTPADDING", (0, 0), (-1, -1), 7),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    return t


def _tabla(filas: list[list], anchos: list[float], resaltar: set[int] = frozenset()) -> Table:
    t = Table(filas, colWidths=anchos, repeatRows=1)
    estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, 0), FONDO),
              ("LINEBELOW", (0, 0), (-1, -1), 0.6, LINEA),
              ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
              ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    estilo += [("BACKGROUND", (0, r), (-1, r), CREMA) for r in resaltar]
    t.setStyle(TableStyle(estilo))
    return t


def _caja(contenido: list, ancho: float, fondo=None, borde=LINEA, grueso: float = 0.8) -> Table:
    t = Table([[contenido]], colWidths=[ancho])
    estilo = [("BOX", (0, 0), (-1, -1), grueso, borde), ("LEFTPADDING", (0, 0), (-1, -1), 9),
              ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 7),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("ROUNDEDCORNERS", [8, 8, 8, 8])]
    if fondo is not None:
        estilo.append(("BACKGROUND", (0, 0), (-1, -1), fondo))
    t.setStyle(TableStyle(estilo))
    return t


def _p(x: str, e: str = "c") -> Paragraph:
    return Paragraph(x, E[e])


def _dif(x: float) -> str:
    return "igual" if abs(x) < 1 else f"{abs(x):.0f} % {'más caro' if x > 0 else 'más barato'}"


def _contra(precio: Decimal, ref: Decimal) -> str:
    d = float((precio / ref - 1) * 100)
    return "igual que el" if abs(d) < 1 else f"{abs(d):.0f} % {'arriba' if d > 0 else 'abajo'} del"


def generar(r: Reporte) -> bytes:
    hay: list = []
    sub = [x for x in (_t(r.presentacion), f"Proveedor: {_t(r.proveedor)}" if r.proveedor else None,
                       f"Código de barras {_t(r.codigo_barras)}" if r.codigo_barras else None) if x]
    hay += [Paragraph(_t(r.nombre) + (f" <font color='#555555'>· {_t(r.marca)}</font>" if r.marca and
                                         rp._norm(r.marca) not in rp._norm(r.nombre) else ""), E["titulo"]),
            Spacer(1, 2), Paragraph(" · ".join(sub), E["sub"]), Spacer(1, 7)]

    # Semáforo + dictamen
    color_txt = COLOR_TEXTO.get(r.color, "#555555")
    # Lo que aporta cada factor, con la misma cuenta que la pantalla: sobre el peso de los que tienen datos
    cubierto = sum(float(b) for _, b, c_, _ in r.factores if c_ is not None) or 1.0
    partes = [(float(b) * c_ / cubierto, _color_puntaje(c_)) for _, b, c_, _ in r.factores if c_ is not None]
    leyenda = " · ".join(f"<font color='{HEX_FACTOR.get(_color_puntaje(c_) or '', SIN_COLOR)}'><b>{_t(a)}</b></font>"
                         for a, _, c_, _ in r.factores)
    sem = Table([[Anillo(r.puntaje, r.color, partes, 118)], [Paragraph(leyenda, E["gris"])],
                 [Paragraph("Verde: más de 80<br/>Amarillo: 60 a 80 · Rojo: menos de 60", E["gris"])]], colWidths=[128])
    sem.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    sem = _caja([sem], 146)
    tag = Table([[Paragraph(r.veredicto, E["tag"])]])
    tag.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NEGRO), ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    tag.hAlign = "LEFT"
    texto = r.dictamen[0].upper() + r.dictamen[1:] if r.dictamen else ""
    confianza = f"Confianza {r.confianza}." if r.confianza else ""
    fotos_ancho = 52 * len(r.fotos) + (6 if r.fotos else 0)
    ancho_dict = UTIL - 146 - 8 - fotos_ancho
    dic = _caja([tag, Spacer(1, 5), _p(_t(texto), "p"), Spacer(1, 3), _p(confianza, "gris")], ancho_dict, CREMA, NEGRO, 1.6)
    celdas, anchos = [sem], [146 + 8]
    if r.fotos:
        celdas.append([Image(BytesIO(f), width=48, height=76, kind="proportional") for f in r.fotos])
        anchos.append(fotos_ancho)
        fotos = Table([celdas[-1]], colWidths=[52] * len(r.fotos))
        fotos.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        celdas[-1] = fotos
    celdas.append(dic)
    anchos.append(ancho_dict)
    arriba = Table([celdas], colWidths=anchos)
    arriba.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    hay.append(arriba)

    # Las 4 donas, del factor que más pesa al que menos (Nivel 1 de la pantalla del comité)
    if r.factores:
        n = 2  # dos por renglón, como la pantalla en anchos medianos
        ancho = (UTIL - 6 * (n - 1)) / n
        cajas = []
        for a, b, c_, d in r.factores:
            de = float(b) * 100 / cubierto if c_ is not None else None
            aporta = (f"aporta {float(b) * c_ / cubierto:.1f} de {de:.1f} puntos" if c_ is not None else "no cuenta todavía")
            texto = Table([[Paragraph(f"<b>{_t(a)}</b> <font color='#777777'>{_n(b)} %</font>", E["p"])],
                           [_p(aporta, "gris")], [_p(_t(_corto(d, 150)), "c")]], colWidths=[ancho - 74])
            texto.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                       ("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5)]))
            fila = Table([[Dona(c_, float(b), 56), texto]], colWidths=[62, ancho - 74])
            fila.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                      ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
            cajas.append(_caja([fila], ancho))
        renglones = [cajas[i:i + n] + [""] * (n - len(cajas[i:i + n])) for i in range(0, len(cajas), n)]
        k = Table(renglones, colWidths=[ancho + 6] * n)
        k.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        hay += [Spacer(1, 7), k]

    # Cuatro cifras
    if r.kpis:
        ancho = (UTIL - 6 * (len(r.kpis) - 1)) / len(r.kpis)
        cajas = []
        for cifra, texto, malo in r.kpis:
            estilo = ParagraphStyle("k", parent=E["kpi"], textColor=HexColor("#B3261E") if malo else NEGRO)
            cajas.append(_caja([Paragraph(_t(cifra), estilo), _p(_t(texto), "gris")], ancho))
        k = Table([cajas], colWidths=[ancho + 6] * len(cajas))
        k.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        hay += [Spacer(1, 7), k]

    # 1. Qué es
    hay += [Spacer(1, 8), _h2("1. ¿Qué es exactamente?"), Spacer(1, 3)]
    datos = [["Producto", _t(r.nombre)], ["Marca", _t(r.marca) or "—"], ["Presentación", _t(r.presentacion) or "—"]]
    if r.precio_unidad:
        datos.append(["Precio por unidad", _t(r.precio_unidad)])
    if r.clasificacion:
        datos.append(["Dónde iría", _t(r.clasificacion)])
    datos.append(["Tipo de producto", (f"{_t(r.lista)[0].upper()}{_t(r.lista)[1:]}" if r.lista else
                                       "Sin elegir: se evaluó con la lista A")])
    if r.codigo_barras:
        datos.append(["Código de barras", _t(r.codigo_barras)])
    hay.append(_tabla([[_p("Dato", "cab"), _p("Valor", "cab")]] + [[_p(f"<b>{a}</b>"), _p(b)] for a, b in datos],
                      [UTIL * 0.22, UTIL * 0.78]))

    # 2. Cuánto ganamos
    if r.escenarios:
        hay += [Spacer(1, 6), _h2("2. ¿Cuánto ganamos?"), Spacer(1, 3)]
        filas = [[_p("Escenario", "cab"), _p("Precio con IVA", "cabn"), _p("Costo sin IVA", "cabn"), _p("Margen", "cabn")]]
        filas += [[_p(_t(a)), _p(_pesos(b), "cn"), _p(_pesos(c), "cn"), _p(_pct(m), "cn")] for a, b, c, m in r.escenarios]
        if r.precio_membresia and r.margen_membresia is not None:
            que = ("Precio de membresía (con la regla de su lista)" if r.membresia_calculada else "Precio de membresía")
            filas.insert(2, [_p(que), _p(_pesos(r.precio_membresia), "cn"), _p(_pesos(r.costo), "cn"),
                             _p(_pct(r.margen_membresia), "cn")])
        if r.margen_sub is not None:
            filas.append([_p("Lo que deja hoy su subcategoría en SMN"), _p("—", "cn"), _p("—", "cn"), _p(_pct(r.margen_sub), "cn")])
        hay.append(_tabla(filas, [UTIL * 0.49, UTIL * 0.17, UTIL * 0.17, UTIL * 0.17], {1}))
        minimos = f"{_n(r.minimo)} % al precio de lista"
        if r.minimo_membresia is not None:
            minimos += f" y {_n(r.minimo_membresia)} % al de membresía"
        tipo = f" ({_t(r.lista)})" if r.lista else " (lista A, falta elegir el tipo de producto)"
        hay.append(_p(f"Margen = (precio ÷ 1.16 − costo) ÷ (precio ÷ 1.16). Mínimo de Compras{tipo}: {minimos}.", "gris"))

    # 3. Afuera
    hay += [Spacer(1, 6), _h2("3. ¿A cuánto se vende afuera?"), Spacer(1, 3)]
    if r.mercado:
        filas = [[_p("Producto", "cab"), _p("Dónde", "cab"), _p("Precio", "cabn"), _p("Por unidad", "cabn")]]
        filas += [[_p(_t(a)), _p(_t(b)), _p(_pesos(c), "cn"), _p(_t(d) or "—", "cn")] for a, b, c, d in r.mercado]
        hay.append(_tabla(filas, [UTIL * 0.46, UTIL * 0.22, UTIL * 0.12, UTIL * 0.2]))
        if r.referencia and r.precio:
            hay.append(_p(f"<b>Lectura:</b> nuestro precio de lista de {_pesos(r.precio)} queda {_contra(r.precio, r.referencia)} "
                          f"precio de en medio del mercado ({_pesos(r.referencia)})"
                          + (f"; contra lo parecido que ya vendemos, {_dif(r.anaquel)}" if r.anaquel is not None else "")
                          + ".", "p"))
            if r.precio_membresia:
                hay.append(_p(f"Con membresía ({_pesos(r.precio_membresia)}"
                              + (", con la regla de su lista" if r.membresia_calculada else "")
                              + f") queda {_contra(r.precio_membresia, r.referencia)} precio de en medio del mercado.", "p"))
        elif r.precio and r.anaquel is not None:
            hay.append(_p(f"<b>Lectura:</b> ninguna tienda en línea lo tiene a la venta; nuestro precio de lista de "
                          f"{_pesos(r.precio)} queda {_dif(r.anaquel)} que lo parecido que ya vendemos.", "p"))
        if any("(lo vio Compras)" in b for _, b, _, _ in r.mercado):
            hay.append(_p("Lo que vio Compras se enseña como referencia; no entra en la calificación.", "gris"))
        if any("precio sugerido de la marca" in b for _, b, _, _ in r.mercado):
            hay.append(_p("El precio de la página de la propia marca se enseña como precio sugerido; no cuenta como "
                          "competencia.", "gris"))
    else:
        hay.append(_p("No se encontró a la venta en las tiendas en línea que revisa el radar de precios: se compara contra "
                      "lo que ya vendemos"
                      + (f" (nuestro precio de lista queda {_dif(r.anaquel)} contra lo parecido)" if r.anaquel is not None else "")
                      + ".", "p"))

    # 4. Parecidos
    titulo = "4. ¿Qué vendemos hoy parecido?" + (" (SMNBI)" if r.ventana else "")
    bloque = [Spacer(1, 6), _h2(titulo), Spacer(1, 3)]
    def tabla(lista):
        filas = [[_p(x, "cab") for x in ("SKU", "Producto", "Clas. catálogo")] +
                 [_p(x, "cabn") for x in ("Piezas al mes", "Tiendas", "Pzas por tienda al mes", "Precio prom. con IVA", "Margen")]]
        for f in lista:
            nota = f" <font color='#777777'>({f.etiqueta})</font>" if f.etiqueta and f.etiqueta != "misma marca" else ""
            filas.append([_p(_t(f.sku)), _p(_t(f.descripcion) + nota), _p(_t(f.clasificacion) or "—"),
                          _p(_n(f.al_mes) if f.al_mes else "sin venta", "cn"), _p(str(f.tiendas) if f.tiendas else "—", "cn"),
                          _p(_n(f.por_tienda) if f.por_tienda else "—", "cn"), _p(_pesos(f.precio), "cn"), _p(_pct(f.margen), "cn")])
        return _tabla(filas, [UTIL * x for x in (0.09, 0.37, 0.06, 0.1, 0.08, 0.11, 0.11, 0.08)])

    # 25 nov 2026 (Diego, BDM Life Berberina): lo de la misma marca va aparte; no es contra lo que se compara
    if r.parecidos:
        bloque.append(tabla(r.parecidos))
    else:
        bloque.append(_p("No vendemos nada parecido: sería un producto nuevo para el surtido.", "p"))
    if r.de_marca:
        bloque += [Spacer(1, 4), _p("<b>De la misma marca</b> (solo para negociar con el proveedor; no se compara contra "
                                    "ellos):", "p"), Spacer(1, 2), tabla(r.de_marca)]
    hay += bloque

    # 5 a 8
    for n, (clave, titulo) in enumerate((("proveedor", "¿La marca y el proveedor son confiables?"),
                                          ("regulacion", "¿Cumple con las reglas de Compras y regulación?"),
                                          ("tendencia", "¿Está en tendencia?"),
                                          ("venta", "¿Cuánto venderá y dónde?")), start=5):
        lineas = r.preguntas.get(clave) or []
        if lineas:
            hay.append(KeepTogether([Spacer(1, 6), _h2(f"{n}. {titulo}"), Spacer(1, 2)] +
                                    [_p("• " + x, "p") for x in lineas]))

    # Calificación
    filas = [[_p("Factor", "cab"), _p("Peso", "cabn"), _p("Puntos", "cabn"), _p("Aporta", "cabn"), _p("Por qué", "cab")]]
    for a, b, c, d in r.factores:
        aporta = f"{float(c) * float(b) / 100:.1f}" if c is not None else "—"
        filas.append([_p(f"<b>{_t(a)}</b>"), _p(f"{_n(b)} %", "cn"), _p(str(c) if c is not None else "—", "cn"),
                      _p(aporta, "cn"), _p(_t(d) or "sin datos", "gris")])
    filas.append([_p("<b>Total</b>"), _p("100 %", "cn"), _p("", "cn"),
                  _p(f"<b>{r.puntaje if r.puntaje is not None else '—'}</b>", "cn"),
                  _p(f"<font color='{color_txt}'><b>{r.color.capitalize()}</b></font>")])
    hay.append(KeepTogether([Spacer(1, 6), _h2(f"Calificación del radar: {r.puntaje if r.puntaje is not None else '—'} de 100, "
                                               f"{r.color}"), Spacer(1, 3),
                             _tabla(filas, [UTIL * x for x in (0.15, 0.09, 0.09, 0.09, 0.58)])]))

    # Acciones
    if r.acciones:
        filas = [[_p("#", "cab"), _p("Acción", "cab"), _p("Responsable", "cab")]]
        filas += [[_p(str(i)), _p(_t(a)), _p(_t(b))] for i, (a, b) in enumerate(r.acciones, start=1)]
        hay.append(KeepTogether([Spacer(1, 6), _h2("Lo que proponemos a Compras"), Spacer(1, 3),
                                 _tabla(filas, [UTIL * 0.05, UTIL * 0.75, UTIL * 0.2])]))
    hay += [Spacer(1, 8), _p("Elaboró: Innovación y Transformación Digital, con el radar de productos. Fuentes: "
                            + _t("; ".join(r.fuentes)) + ".", "gris")]

    fecha = f"Evaluación del {_fecha(r.fecha)}"

    def pagina(c, doc):
        c.saveState()
        if LOGO.is_file():
            c.drawImage(str(LOGO), MARGEN, ALTO - 44, width=150, height=150 * 114 / 800, mask="auto")
        c.setFillColor(GRIS)
        c.setFont(LB, 8.2)
        c.drawRightString(ANCHO - MARGEN, ALTO - 30, "Radar de producto nuevo · Compras")
        c.setFont(L, 8)
        c.drawRightString(ANCHO - MARGEN, ALTO - 41, fecha if doc.page == 1 else f"{r.nombre[:70]} · página {doc.page}")
        c.setStrokeColor(NARANJA)
        c.setLineWidth(3)
        c.line(MARGEN, ALTO - 50, ANCHO - MARGEN, ALTO - 50)
        c.restoreState()

    salida = BytesIO()
    doc = SimpleDocTemplate(salida, pagesize=letter, leftMargin=MARGEN, rightMargin=MARGEN, topMargin=60,
                            bottomMargin=36, title=f"Radar de producto nuevo - {r.nombre}", author="Súper Mayoreo Naturista")
    doc.build(hay, onFirstPage=pagina, onLaterPages=pagina)
    return salida.getvalue()


def nombre_archivo(r: Reporte) -> str:
    limpio = "".join(c for c in r.nombre if c.isalnum() or c in " -+.")[:80].strip()
    return f"Radar producto nuevo - {limpio} {r.fecha:%Y-%m-%d}.pdf"


def pdf_de(bd: Session, e: ProductoEvaluacion, ahora: datetime | None = None) -> tuple[bytes, str]:
    r = armar(bd, e, ahora)
    return generar(r), nombre_archivo(r)


def guardar(bd: Session, pdf: bytes, nombre: str, usuario_id: int, item_id: int) -> Archivo:
    """Guarda el PDF como archivo de la plataforma, ligado al producto del comité (no hace commit)."""
    import hashlib
    import uuid

    from nucleo.archivos import _raiz
    from nucleo.modelos import ahora as _ahora

    relativa = Path(_ahora().strftime("%Y/%m")) / f"{uuid.uuid4().hex}.pdf"
    destino = _raiz() / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(pdf)
    a = Archivo(entidad="comite_producto", entidad_id=str(item_id), nombre_original=nombre[:255],
                tipo_contenido="application/pdf", tamano_bytes=len(pdf), sha256=hashlib.sha256(pdf).hexdigest(),
                ruta_almacenamiento=relativa.as_posix(), subido_por=usuario_id)
    bd.add(a)
    bd.flush()
    return a
