"""Examen de la clasificación y los parecidos del radar de productos contra nuestro propio catálogo.

Plan aprobado por Diego el 24 nov 2026 («a ver dale»): antes de enseñarle un cambio, se mide cuánto acierta. A cada
producto activo con venta se le esconde del catálogo (con sus otros sabores y presentaciones), se le clasifica como si
fuera nuevo, con lo que Compras capturaría (nombre, marca, departamento, precio y su ficha si existe), y se compara contra
la subcategoría que ya tiene en SMNBI. Nadie valida a mano: la respuesta correcta es el catálogo.

No escribe en la base. Usa exactamente las mismas funciones que la evaluación (`rp.clasificar_sujeto`,
`rp.parecidos_sujeto`), así que mide lo que de verdad corre en el radar.
"""
from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

import json as _json
from pathlib import Path as _Path

from sqlalchemy import select, true
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from datos import fichas as fi
from datos.modelos import Producto
from modulos.compras import pronostico as pn
from modulos.compras import radar_productos as rp
from modulos.compras import realidad_producto as rr

# Umbral para entregar (plan, sección 5; recomendaciones que Diego no cambió)
UMBRAL = {
    "subcategoria": 90.0,  # % de productos del catálogo con la subcategoría correcta
    "rama": 97.0,
    "departamento_minimo": 80.0,  # ningún departamento (con 10 o más productos) por debajo
    "lanzamientos": 90.0,
    "casos": 100.0,
    "sin_parecidos": 0,  # productos sin ningún parecido teniendo vecinos en su subcategoría real
    "otra_forma_top5": 0,  # productos con un parecido de otra forma entre sus 5 primeros
    "parecidos_misma_sub": 80.0,  # promedio de parecidos que son de su subcategoría real
}
MIN_DEPTO = 10

# Casos reales que ya fallaron y su respuesta conocida (se buscan por palabras del nombre entre las evaluaciones)
CASOS = [
    {"caso": "BDM Life Berberina + Piperina + Omega 9", "palabras": ("berberina", "piperina"),
     "subcategoria": "AUXILIAR EN LA DIABETES"},
]


def _n(t: str | None) -> str:
    return rp._norm(t).strip()


def huella_nombre(p: Producto) -> frozenset[str]:
    """Palabras del nombre sin marca, sabor, números ni unidades: el mismo producto en otro sabor o tamaño da lo mismo."""
    return frozenset(rp.raices(rp.palabras(rp.sin_sabor(p.descripcion))) - rp.raices(rp.palabras(p.marca)))


def sujeto_de_producto(p: Producto) -> rp.Sujeto:
    f = rp.ficha_de(p)
    return rp.Sujeto(tipo="idea", nombre=p.descripcion or p.sku, marca=p.marca, departamento=p.departamento,
                     precio=p.precio_lista_con_impuestos, ficha=f,
                     ingrediente=f.ingrediente_principal if f else None, forma=f.forma if f else None)


def ocultos_de(p: Producto, catalogo: list[Producto], por_huella: dict) -> frozenset[int]:
    """El producto, sus otros sabores y presentaciones (misma marca y mismo nombre) y lo que se reconoce como él mismo."""
    s = sujeto_de_producto(p)
    llave = (_n(p.marca), huella_nombre(p))
    ids = {p.producto_id} | {q.producto_id for q in por_huella.get(llave, [])}
    ids |= {q.producto_id for q in catalogo if q.producto_id not in ids and rp.es_mismo(s, q)}
    return frozenset(ids)


def grupo_forma(x: str | None) -> str | None:
    return fi.GRUPO_FORMATO.get(x) if x else None


@dataclass
class Resultado:
    sku: str
    descripcion: str
    departamento: str | None
    rama_real: str | None
    sub_real: str | None
    rama: str | None = None
    sub: str | None = None
    origen: str = ""
    lanzamiento: bool = False
    forma: str | None = None
    parecidos: list[tuple[Producto, Decimal]] = field(default_factory=list)
    quitados: int = 0
    vecinos_reales: int = 0  # productos activos de su subcategoría real (sin él)
    ingrediente: str | None = None  # raíz usada como ingrediente
    seguridad: str = ""
    parte: float | None = None
    finalistas: str = ""
    por: str = ""
    sospechoso: bool = False  # su subcategoría en el catálogo contradice a los de su ingrediente y forma
    sospecha_sub: str | None = None  # dónde están casi todos los de su ingrediente
    error: str | None = None

    @property
    def bien_sub(self) -> bool:
        return bool(self.sub) and _n(self.sub) == _n(self.sub_real)

    @property
    def bien_rama(self) -> bool:
        return bool(self.rama) and _n(self.rama) == _n(self.rama_real)

    @property
    def misma_sub_pct(self) -> float | None:
        if not self.parecidos:
            return None
        return sum(1 for q, _ in self.parecidos if _n(q.subcategoria) == _n(self.sub_real)) / len(self.parecidos) * 100

    def otra_forma_top5(self) -> list[Producto]:
        g = grupo_forma(self.forma)
        if not g:
            return []
        return [q for q, _ in self.parecidos[:5] if (h := grupo_forma(rp.formato_de(q))) and h != g]

    @property
    def posible_error_catalogo(self) -> bool:
        """Casi todos los productos con su mismo ingrediente y forma están en otra subcategoría (no cuenta como falla)."""
        return self.sospechoso


def universo(bd: Session) -> tuple[list[Producto], list[Producto], set[str]]:
    """(catálogo activo, los que se examinan: activos con subcategoría, precio y venta; SKU lanzados en 2026)."""
    catalogo = list(bd.scalars(select(Producto).where(Producto.activo == true())))
    v = rr.ventana(bd)
    con_venta = set(rr.venta_por_sku(bd, v)) if v else set()
    examinables = [p for p in catalogo if p.subcategoria and rp._con_precio(p) and p.sku in con_venta]
    try:
        lanzados = {x.sku for x in pn.entrenar(bd).lanzamientos}
    except Exception:  # noqa: BLE001 - sin pronóstico se examina igual
        lanzados = set()
    return catalogo, examinables, lanzados


def muestra(examinables: list[Producto], lanzados: set[str], n: int | None, semilla: int = 2026) -> list[Producto]:
    """Todos si n es None; si no, n repartidos por departamento en proporción, más todos los lanzamientos de 2026."""
    if n is None or n >= len(examinables):
        return list(examinables)
    azar = random.Random(semilla)
    por_depto: dict[str, list[Producto]] = defaultdict(list)
    for p in examinables:
        por_depto[p.departamento or ""].append(p)
    elegidos = {p.producto_id: p for p in examinables if p.sku in lanzados}
    for _, ps in sorted(por_depto.items()):
        k = max(1, round(n * len(ps) / len(examinables)))
        for p in azar.sample(ps, min(k, len(ps))):
            elegidos[p.producto_id] = p
    return sorted(elegidos.values(), key=lambda p: p.sku)


def examinar_uno(bd: Session, p: Producto, catalogo: list[Producto], por_huella: dict, por_sub: Counter,
                 lanzados: set[str]) -> Resultado:
    r = Resultado(p.sku, p.descripcion or "", p.departamento, p.rama, p.subcategoria, lanzamiento=p.sku in lanzados)
    ocultos = ocultos_de(p, catalogo, por_huella)
    r.vecinos_reales = por_sub[_n(p.subcategoria)] - sum(
        1 for q in catalogo if q.producto_id in ocultos and _n(q.subcategoria) == _n(p.subcategoria))
    s = sujeto_de_producto(p)
    r.forma = rp.formato_sujeto(s) or rp.formato_de(p)
    marca = rp.OCULTOS.set(ocultos)
    try:
        from modulos.compras import clasificador as cl

        idx = cl.indice(catalogo)
        r.sospechoso = idx.sospechoso(p.producto_id)
        vistos: dict[str, tuple[bool, str]] = {}
        c = rp.clasificar_sujeto(bd, s)
        r.rama, r.sub, r.origen, r.seguridad, r.parte = c.rama, c.subcategoria, c.origen, c.seguridad, c.parte
        r.ingrediente, r.por = c.ingrediente, c.texto()
        r.finalistas = "; ".join(f"{n} {x * 100:.0f} %" for n, x in c.finalistas)
        conservar = c.conservar
        r.parecidos, quitados = rp.parecidos_sujeto(bd, s, r.sub, r.rama, conservar, vistos)
        r.quitados = len(quitados)
        if not r.sub and (fuente := rp.clasificacion_de_parecidos(r.parecidos, rp.mismo_de(s, r.parecidos))):
            r.rama, r.sub, r.origen = fuente.rama, fuente.subcategoria, "parecidos"
            r.parecidos = rp._depurar(r.parecidos, r.sub, r.rama, conservar)
    except Exception as ex:  # noqa: BLE001 - un producto que truena no detiene el examen
        if isinstance(ex, SQLAlchemyError):
            bd.rollback()
        r.error = str(ex)[:300]
    finally:
        rp.OCULTOS.reset(marca)
    return r


def _a_dict(r: Resultado) -> dict:
    d = {k: v for k, v in r.__dict__.items() if k != "parecidos"}
    d["parecidos"] = [[q.producto_id, str(sim)] for q, sim in r.parecidos]
    return d


def _de_dict(bd: Session, d: dict) -> Resultado:
    pares = d.pop("parecidos", [])
    r = Resultado(**d)
    r.parecidos = [(q, Decimal(sim)) for pid, sim in pares if (q := bd.get(Producto, pid))]
    return r


def examinar(bd: Session, n: int | None = 300, avance=None, guardar: _Path | None = None
             ) -> tuple[list[Resultado], dict]:
    """`guardar`: archivo donde se va guardando el avance cada 25 productos; si ya existe, sigue desde ahí (Diego, 25
    nov 2026: publicar reiniciaba el examen desde cero)."""
    catalogo, examinables, lanzados = universo(bd)
    rp.cargar_fichas(bd, catalogo)
    por_huella: dict = defaultdict(list)
    for q in catalogo:
        por_huella[(_n(q.marca), huella_nombre(q))].append(q)
    por_sub = Counter(_n(q.subcategoria) for q in catalogo if q.subcategoria)
    elegidos = muestra(examinables, lanzados, n)
    marca = rp.CATALOGO_FIJO.set(catalogo)
    resultados = []
    hechos: dict[str, dict] = {}
    if guardar and guardar.exists():
        try:
            hechos = {d["sku"]: d for d in _json.loads(guardar.read_text())}
        except (OSError, ValueError, KeyError, TypeError):
            hechos = {}
    try:
        for i, p in enumerate(elegidos, 1):
            if p.sku in hechos:
                resultados.append(_de_dict(bd, dict(hechos[p.sku])))
            else:
                resultados.append(examinar_uno(bd, p, catalogo, por_huella, por_sub, lanzados))
            if i % 25 == 0 or i == len(elegidos):
                if guardar:
                    guardar.write_text(_json.dumps([_a_dict(r) for r in resultados], ensure_ascii=False, default=str))
                if avance:
                    avance(i, len(elegidos), resultados)
    finally:
        rp.CATALOGO_FIJO.reset(marca)
    return resultados, {"catalogo": len(catalogo), "examinables": len(examinables), "lanzados": len(lanzados)}


def casos(bd: Session) -> list[dict]:
    """Evaluaciones vigentes de los casos con respuesta conocida: qué subcategoría tienen guardada y qué da hoy."""
    from modulos.compras.modelos_productos import ProductoEvaluacion

    salida = []
    vigentes = list(bd.scalars(select(ProductoEvaluacion).where(ProductoEvaluacion.vigente == true())))
    for caso in CASOS:
        for e in vigentes:
            try:
                s = rp.sujeto_de_propuesta(bd.get(rp.Propuesta, e.propuesta_id)) if e.propuesta_id else \
                    rp.sujeto_de_idea(bd.get(rp.ProductoIdea, e.idea_id))
            except Exception:  # noqa: BLE001
                continue
            texto = _n(f"{s.nombre} {s.descripcion or ''}")
            if not all(w in texto for w in caso["palabras"]):
                continue
            try:
                c = rp.clasificar_sujeto(bd, s)
                sub, origen = c.subcategoria, f"{c.origen} ({c.seguridad})"
            except Exception as ex:  # noqa: BLE001
                sub, origen = None, f"error: {ex}"[:100]
            salida.append({"caso": caso["caso"], "evaluacion": e.evaluacion_id, "producto": s.nombre,
                           "correcta": caso["subcategoria"], "guardada": e.subcategoria,
                           "origen_guardado": e.clasificacion_origen, "hoy": sub, "origen_hoy": origen,
                           "bien": _n(sub) == _n(caso["subcategoria"])})
    return salida


def _pct(a: int, b: int) -> float | None:
    return round(a / b * 100, 1) if b else None


def resumen(resultados: list[Resultado], lista_casos: list[dict]) -> dict:
    ok = [r for r in resultados if not r.error]
    contables = [r for r in ok if not r.posible_error_catalogo]
    por_depto: dict[str, list[Resultado]] = defaultdict(list)
    for r in contables:
        por_depto[r.departamento or "(sin departamento)"].append(r)
    deptos = {d: (_pct(sum(x.bien_sub for x in rs), len(rs)), len(rs)) for d, rs in sorted(por_depto.items())}
    con_vecinos = [r for r in contables if r.vecinos_reales > 0]
    misma = [r.misma_sub_pct for r in contables if r.misma_sub_pct is not None]
    lanz = [r for r in contables if r.lanzamiento]
    medidos = {
        "subcategoria": _pct(sum(r.bien_sub for r in contables), len(contables)),
        "rama": _pct(sum(r.bien_rama for r in contables), len(contables)),
        "departamento_minimo": min((v for v, n in deptos.values() if n >= MIN_DEPTO and v is not None), default=None),
        "lanzamientos": _pct(sum(r.bien_sub for r in lanz), len(lanz)),
        "casos": _pct(sum(c["bien"] for c in lista_casos), len(lista_casos)),
        "sin_parecidos": sum(1 for r in con_vecinos if not r.parecidos),
        "otra_forma_top5": sum(1 for r in contables if r.otra_forma_top5()),
        "parecidos_misma_sub": round(sum(misma) / len(misma), 1) if misma else None,
    }
    pasa = {}
    for k, meta in UMBRAL.items():
        v = medidos[k]
        pasa[k] = None if v is None else (v <= meta if k in ("sin_parecidos", "otra_forma_top5") else v >= meta)
    return {"examinados": len(resultados), "con_error": len(resultados) - len(ok),
            "posibles_errores_catalogo": len(ok) - len(contables), "contables": len(contables),
            "lanzamientos": len(lanz), "medidos": medidos, "pasa": pasa, "deptos": deptos,
            "origenes": Counter(r.origen for r in contables),
            "seguridades": {g: (sum(1 for r in contables if r.seguridad == g),
                                _pct(sum(r.bien_sub for r in contables if r.seguridad == g),
                                     sum(1 for r in contables if r.seguridad == g)))
                            for g in ("segura", "dudosa", "sin_evidencia")},
            "aciertos_por_origen": {o: _pct(sum(r.bien_sub for r in contables if r.origen == o),
                                            sum(1 for r in contables if r.origen == o))
                                    for o in sorted({r.origen for r in contables})}}


NOMBRES = {
    "subcategoria": "Subcategoría correcta (catálogo)", "rama": "Rama correcta (catálogo)",
    "departamento_minimo": "Departamento con menos aciertos (10 o más productos)",
    "lanzamientos": "Subcategoría correcta, lanzamientos 2026", "casos": "Casos que ya fallaron, bien",
    "sin_parecidos": "Productos sin parecidos teniendo vecinos en su subcategoría real",
    "otra_forma_top5": "Productos con un parecido de otra forma entre sus 5 primeros",
    "parecidos_misma_sub": "Parecidos de su subcategoría real (promedio, %)",
}


def a_excel(ruta: str, version: str, resultados: list[Resultado], res: dict, lista_casos: list[dict],
            universo_txt: dict, antes: tuple[list[Resultado], dict] | None = None) -> None:
    """`antes`: el mismo examen corrido como la v0.5.3 (mismos productos), para poner las dos versiones lado a lado."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    verde, rojo = PatternFill("solid", fgColor="D9F2D9"), PatternFill("solid", fgColor="F8D7D7")
    wb = Workbook()
    h = wb.active
    h.title = "Resumen"
    h.append([f"Examen de clasificación del radar de productos · {version}"])
    h["A1"].font = Font(bold=True, size=14)
    h.append([f"Catálogo activo: {universo_txt['catalogo']:,} · con subcategoría, precio y venta: "
              f"{universo_txt['examinables']:,} · examinados: {res['examinados']:,} · lanzamientos 2026 entre ellos: "
              f"{res['lanzamientos']}"])
    h.append([f"No cuentan: {res['posibles_errores_catalogo']} posibles errores del catálogo (hoja aparte) y "
              f"{res['con_error']} que tronaron (hoja Fallas)."])
    h.append([])
    h.append(["Qué se mide", "Resultado", "Mínimo para entregar", "¿Pasa?"] + (["Igual, como la v0.5.3"] if antes else []))
    for c in h[5]:
        c.font = Font(bold=True)
    for k, meta in UMBRAL.items():
        v, ok = res["medidos"][k], res["pasa"][k]
        fila = [NOMBRES[k], "—" if v is None else v,
                f"{'máximo' if k in ('sin_parecidos', 'otra_forma_top5') else 'mínimo'} {meta}",
                "sin datos" if ok is None else ("Sí" if ok else "No")]
        if antes:
            va = antes[1]["medidos"][k]
            fila.append("—" if va is None else va)
        h.append(fila)
        if ok is not None:
            h.cell(h.max_row, 4).fill = verde if ok else rojo
    h.append([])
    h.append(["De dónde salió la subcategoría", "Productos", "Acierto %"])
    h.cell(h.max_row, 1).font = Font(bold=True)
    for o, n in res["origenes"].most_common():
        h.append([o, n, res["aciertos_por_origen"].get(o)])
    h.append([])
    h.append(["Qué tan segura quedó", "Productos", "Acierto %"])
    h.cell(h.max_row, 1).font = Font(bold=True)
    for g, (n, v) in res["seguridades"].items():
        h.append([g, n, v])
    h.append([])
    h.append(["Departamento", "Productos", "Acierto %"])
    h.cell(h.max_row, 1).font = Font(bold=True)
    for d, (v, n) in sorted(res["deptos"].items(), key=lambda x: (x[1][0] is None, x[1][0] or 0)):
        h.append([d, n, v])
    h.column_dimensions["A"].width = 64
    for col in "BCD":
        h.column_dimensions[col].width = 22

    f = wb.create_sheet("Fallas")
    f.append(["SKU", "Producto", "Departamento", "Subcategoría real", "Rama real", "Eligió", "Rama elegida", "De dónde",
              "Qué tan segura", "Finalistas", "Lanzamiento 2026", "Ingrediente usado", "Por qué", "Parecidos (los 5 primeros)",
              "Error"])
    for r in resultados:
        if r.error or (not r.bien_sub and not r.posible_error_catalogo):
            f.append([r.sku, r.descripcion, r.departamento, r.sub_real, r.rama_real, r.sub, r.rama, r.origen, r.seguridad,
                      r.finalistas, "Sí" if r.lanzamiento else "", r.ingrediente or "", r.por,
                      "; ".join(f"{q.descripcion} ({q.subcategoria})" for q, _ in r.parecidos[:5]), r.error])

    e = wb.create_sheet("Posibles errores del catálogo")
    e.append(["SKU", "Producto", "Está en el catálogo", "El radar lo pondría en", "Por qué"])
    for r in resultados:
        if r.posible_error_catalogo:
            e.append([r.sku, r.descripcion, r.sub_real, r.sub, r.por])

    q = wb.create_sheet("Parecidos dudosos")
    q.append(["SKU", "Producto", "Subcategoría real", "Problema", "Parecidos (los 5 primeros)"])
    for r in resultados:
        if r.error or r.posible_error_catalogo:
            continue
        problemas = []
        if not r.parecidos and r.vecinos_reales:
            problemas.append(f"sin parecidos y hay {r.vecinos_reales} en su subcategoría real")
        if (otra := r.otra_forma_top5()):
            problemas.append("otra forma: " + "; ".join(x.descripcion or x.sku for x in otra))
        if r.misma_sub_pct is not None and r.misma_sub_pct < 50:
            problemas.append(f"solo {r.misma_sub_pct:.0f} % de su subcategoría real")
        if problemas:
            q.append([r.sku, r.descripcion, r.sub_real, " · ".join(problemas),
                      "; ".join(f"{x.descripcion} ({x.subcategoria})" for x, _ in r.parecidos[:5])])

    c = wb.create_sheet("Casos")
    c.append(["Caso", "Evaluación", "Producto", "Subcategoría correcta", "Guardada en la evaluación", "Origen guardado",
              "Hoy daría", "Origen hoy", "¿Bien hoy?"])
    for x in lista_casos:
        c.append([x["caso"], x["evaluacion"], x["producto"], x["correcta"], x["guardada"], x["origen_guardado"],
                  x["hoy"], x["origen_hoy"], "Sí" if x["bien"] else "No"])

    d = wb.create_sheet("Detalle")
    d.append(["SKU", "Producto", "Departamento", "Subcategoría real", "Eligió", "¿Bien?", "Rama real", "Rama elegida",
              "¿Rama bien?", "De dónde", "Qué tan segura", "% de votos", "Lanzamiento 2026", "Parecidos",
              "% de su subcategoría real", "Quitados por la IA", "Posible error del catálogo", "Error"])
    for r in resultados:
        d.append([r.sku, r.descripcion, r.departamento, r.sub_real, r.sub, "Sí" if r.bien_sub else "No", r.rama_real,
                  r.rama, "Sí" if r.bien_rama else "No", r.origen, r.seguridad,
                  None if r.parte is None else round(r.parte * 100), "Sí" if r.lanzamiento else "", len(r.parecidos),
                  None if r.misma_sub_pct is None else round(r.misma_sub_pct), r.quitados,
                  "Sí" if r.posible_error_catalogo else "", r.error])
    if antes:
        previos = {r.sku: r for r in antes[0]}
        x = wb.create_sheet("Contra v0.5.3")
        x.append(["SKU", "Producto", "Subcategoría real", "v0.5.3 eligió", "¿Bien en v0.5.3?", "v0.5.4 eligió",
                  "¿Bien en v0.5.4?", "Resultado", "Por qué en v0.5.4", "De dónde en v0.5.3"])
        for r in resultados:
            a = previos.get(r.sku)
            if not a or r.error or a.error or rp._norm(a.sub) == rp._norm(r.sub):
                continue
            veredicto = ("mejoró" if r.bien_sub and not a.bien_sub else "empeoró" if a.bien_sub and not r.bien_sub
                         else "cambió, las dos mal")
            x.append([r.sku, r.descripcion, r.sub_real, a.sub, "Sí" if a.bien_sub else "No", r.sub,
                      "Sí" if r.bien_sub else "No", veredicto, r.por, a.origen])
    for hoja in wb.worksheets[1:]:
        for celda in hoja[1]:
            celda.font = Font(bold=True)
        hoja.freeze_panes = "A2"
    wb.save(ruta)


def version_actual() -> str:
    try:
        from core.config import configuracion

        return configuracion().plataforma_version or "local"
    except Exception:  # noqa: BLE001
        return "versión local"


def limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


# ---------------------------------------------------------------- corrida sola en el servidor (Diego, 24 nov 2026:
# «no tengo noches»): al arrancar una versión publicada, el examen se corre solo en segundo plano, primero con 100
# productos y luego con todo el catálogo, y el Excel se descarga desde la plataforma. Una vez por versión.

import logging as _logging  # noqa: E402
import threading as _threading  # noqa: E402

_log = _logging.getLogger(__name__)
# El examen va con la versión del clasificador, no con la de la plataforma (Diego, 25 nov 2026): publicar un cambio de
# precio, demanda o pantalla no lo vuelve a empezar. Súbela solo cuando cambie la forma de clasificar.
CLASIFICADOR = "v0.5.4"


def clave() -> str | None:
    """De qué clasificador es el examen; None en la laptop o sin versión publicada."""
    from core.config import configuracion

    v = configuracion().plataforma_version
    return CLASIFICADOR if v and v != "local" else None
# 100 productos (las dos versiones) → comparación de las evaluaciones vigentes v0.5.3 contra v0.5.4 → catálogo completo
CORRIDAS = (("100", 100), ("comparacion", None), ("completo", None))
MAX_INTENTOS = 2
_corriendo = _threading.Event()
AVANCE: dict = {"corrida": None, "como": None, "hechos": 0, "total": 0, "bien": 0}


def carpeta() -> _Path:
    from core.config import configuracion

    c = _Path(configuracion().archivos_ruta) / "examenes"
    c.mkdir(parents=True, exist_ok=True)
    return c


def ruta(version: str, corrida: str, ext: str = "xlsx") -> _Path:
    limpio = re.sub(r"[^\w.\-]", "_", version)
    return carpeta() / f"examen_clasificacion_{limpio}_{corrida}.{ext}"


def _intentos(version: str, corrida: str) -> int:
    p = ruta(version, corrida, "intentos")
    try:
        return int(p.read_text())
    except (OSError, ValueError):
        return 0


def pendientes(version: str) -> list[tuple[str, int | None]]:
    return [(c, n) for c, n in CORRIDAS
            if not ruta(version, c).exists() and _intentos(version, c) < MAX_INTENTOS]


def correr(version: str, corrida: str, n: int | None) -> dict:
    from core.bd import motor

    AVANCE.update(corrida=corrida, como=None, hechos=0, total=0, bien=0)
    if corrida == "comparacion":
        from modulos.compras import comparar_versiones as cv

        datos = cv.correr(version, str(ruta(version, corrida)),
                          lambda i, total: AVANCE.update(hechos=i, total=total))
        ruta(version, corrida, "json").write_text(cv.json_de(datos))
        return datos

    def avance(i: int, total: int, rs: list) -> None:
        AVANCE.update(hechos=i, total=total, bien=sum(r.bien_sub for r in rs if not r.error))

    with Session(motor(), expire_on_commit=False) as bd:
        # Primero los mismos productos «como la v0.5.3», para saber de dónde partimos (plan, sección 5)
        AVANCE["como"] = "v0.5.3"
        marca = fi.COMO_V053.set(True)
        try:
            antes, _ = examinar(bd, n, avance, ruta(version, f"{corrida}_v053", "avance"))
            casos_antes = casos(bd)
        finally:
            fi.COMO_V053.reset(marca)
        AVANCE["como"] = version
        resultados, univ = examinar(bd, n, avance, ruta(version, f"{corrida}_actual", "avance"))
        sospecha = {r.sku: r.sospechoso for r in resultados}
        for r in antes:  # los posibles errores del catálogo no cuentan en ninguna de las dos
            r.sospechoso = sospecha.get(r.sku, r.sospechoso)
        res_antes = resumen(antes, casos_antes)
        lista_casos = casos(bd)
        res = resumen(resultados, lista_casos)
        a_excel(str(ruta(version, corrida)), f"{version} · {corrida}", resultados, res, lista_casos, univ,
                (antes, res_antes))
        bd.rollback()
    datos = {"version": version, "corrida": corrida, "medidos": res["medidos"], "pasa": res["pasa"],
             "medidos_v053": res_antes["medidos"],
             "examinados": res["examinados"], "posibles_errores_catalogo": res["posibles_errores_catalogo"]}
    ruta(version, corrida, "json").write_text(_json.dumps(datos, ensure_ascii=False, default=str))
    return datos


def revisar_programa(bd: Session) -> None:  # noqa: ARG001 - el trabajo abre su propia sesión
    """Lo llama el programador cada minuto: en una versión publicada, si falta algún examen, lo corre en su hilo."""
    from core.config import configuracion

    version = clave()
    if _corriendo.is_set() or not version or not pendientes(version):
        return

    def trabajo() -> None:
        try:
            for corrida, n in pendientes(version):
                try:
                    correr(version, corrida, n)
                    _log.info("Examen de clasificación %s %s listo", version, corrida)
                except Exception:  # noqa: BLE001 - solo una falla cuenta como intento; reiniciar la API no
                    ruta(version, corrida, "intentos").write_text(str(_intentos(version, corrida) + 1))
                    _log.exception("Examen de clasificación %s %s falló", version, corrida)
        finally:
            AVANCE["corrida"] = None
            _corriendo.clear()

    _corriendo.set()
    _threading.Thread(target=trabajo, daemon=True, name="examen-clasificacion").start()


def estado() -> dict:
    from core.config import configuracion

    version = clave() or "local"
    salida = {"version": configuracion().plataforma_version, "clasificador": version, "corriendo": _corriendo.is_set(),
              "avance": dict(AVANCE), "corridas": {}}
    for c, _ in CORRIDAS:
        j = ruta(version, c, "json")
        if j.exists():
            try:
                salida["corridas"][c] = _json.loads(j.read_text())
            except (OSError, ValueError):
                pass
        elif _intentos(version, c) >= MAX_INTENTOS:
            salida["corridas"][c] = {"error": "falló dos veces; revisa los mensajes de la API"}
    return salida
