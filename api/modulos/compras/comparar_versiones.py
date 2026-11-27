"""Comparación v0.5.3 contra v0.5.4 con las evaluaciones que ya existen (Diego, 24 nov 2026: «revisa bien todo»).

Antes de que la reclasificación nocturna toque una sola evaluación, se toma la lista fija de evaluaciones vigentes y cada
una se vuelve a calcular dos veces, en borrador y con los mismos datos de internet que ya tenía guardados (no sale a
internet): una «como la v0.5.3» y otra con la v0.5.4. Así cualquier diferencia es solo por el cambio de versión, y para
cada producto que cambia se dice por qué: cambió la subcategoría (y qué votó), o cambiaron sus parecidos (cuáles salieron
y por qué: misma marca que ya no suma, otra forma, otra subcategoría). Si un puntaje cambia sin que cambien ni la
subcategoría ni los parecidos, se marca «sin explicar» para revisarlo.

Los borradores no son vigentes, no abren búsquedas de proveedor y se borran en cuanto se leen; no salen en el historial.
El resultado es un Excel que se descarga desde la plataforma.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from datos import fichas as fi
from datos.modelos import Producto
from modulos.compras import radar_productos as rp
from modulos.compras.modelos_productos import EvaluacionComparable, ProductoEvaluacion

log = logging.getLogger(__name__)
EN_BORRADOR: set[int] = set()  # evaluaciones de borrador en curso: el historial no las enseña
FACTORES_FIJOS = ("rentabilidad",)  # no dependen de la clasificación ni de los parecidos: si cambian, algo está mal


@dataclass
class Foto:
    """Lo que dio una versión para una evaluación."""
    puntaje: int | None = None
    color: str | None = None
    subcategoria: str | None = None
    origen: str | None = None
    factores: dict[str, int | None] = field(default_factory=dict)
    parecidos: dict[int, str] = field(default_factory=dict)  # producto_id -> descripción
    clasificacion: str = ""  # el texto de la clasificación automática (v0.5.4)
    error: str | None = None


def foto_de(e: ProductoEvaluacion) -> Foto:
    texto = next((b for b in (e.explicacion or "").split("\n\n") if b.startswith(("Clasificación", "Se reclasificó"))), "")
    return Foto(e.puntaje, e.color, e.subcategoria, e.clasificacion_origen,
                {f.factor: f.puntaje for f in e.factores},
                {c.producto_id: "" for c in e.comparables}, texto, e.error if e.estado == "fallida" else None)


def lista_fija(bd: Session) -> list[int]:
    """Las evaluaciones vigentes ya hechas: las que ve hoy el comité."""
    return list(bd.scalars(select(ProductoEvaluacion.evaluacion_id).where(
        ProductoEvaluacion.vigente == true(), ProductoEvaluacion.estado == "lista").order_by(ProductoEvaluacion.evaluacion_id)))


def simular(bd: Session, evaluacion_id: int, como_v053: bool, hoy: date | None = None) -> Foto:
    """Calcula la evaluación otra vez en un borrador (no vigente) y lo borra. Mismo mercado e investigación guardados."""
    original = bd.get(ProductoEvaluacion, evaluacion_id)
    b = ProductoEvaluacion(propuesta_id=original.propuesta_id, idea_id=original.idea_id, estado="en_curso",
                           vigente=False, creada_en=rp.ahora())
    if como_v053 and original.clasificacion_origen == "compras":
        b.rama, b.subcategoria, b.segmento, b.clasificacion_origen = (original.rama, original.subcategoria,
                                                                      original.segmento, "compras")
    bd.add(b)
    bd.flush()
    EN_BORRADOR.add(b.evaluacion_id)
    if any(c.origen == "compras" for c in original.comparables):  # los que fijó Compras se quedan, como en iniciar
        for c in original.comparables:
            b.comparables.append(EvaluacionComparable(producto_id=c.producto_id, rango=c.rango,
                                                      similitud=Decimal(0), origen="compras"))
    bd.commit()
    bid = b.evaluacion_id
    m1 = fi.COMO_V053.set(como_v053)
    m2 = rp.MERCADO_FIJO.set((original.mercado, original.investigacion))
    try:
        b = rp.evaluar(bd, bid, hoy, rapido=False)
        foto = foto_de(b)
        for c in b.comparables:
            p = bd.get(Producto, c.producto_id)
            foto.parecidos[c.producto_id] = (p.descripcion or p.sku) if p else str(c.producto_id)
        return foto
    finally:
        rp.MERCADO_FIJO.reset(m2)
        fi.COMO_V053.reset(m1)
        try:
            bd.rollback()
            if (x := bd.get(ProductoEvaluacion, bid)) is not None:
                bd.delete(x)
                bd.commit()
        except Exception:  # noqa: BLE001
            bd.rollback()
            log.exception("No se pudo borrar el borrador %s", bid)
        EN_BORRADOR.discard(bid)


def _grupo(p: Producto | None) -> str | None:
    f = rp.formato_de(p) if p else None
    return fi.GRUPO_FORMATO.get(f) if f else None


def por_que(bd: Session, e: ProductoEvaluacion, a: Foto, d: Foto) -> tuple[str, bool]:
    """En palabras, por qué la v0.5.4 (d) dio distinto que la v0.5.3 (a). Devuelve (texto, explicado)."""
    s = rp.sujeto_de_propuesta(bd.get(rp.Propuesta, e.propuesta_id)) if e.propuesta_id else \
        rp.sujeto_de_idea(bd.get(rp.ProductoIdea, e.idea_id))
    suyo = fi.GRUPO_FORMATO.get(rp.formato_sujeto(s) or "")
    marca = rp._norm(s.marca).strip()
    partes = []
    if rp._norm(a.subcategoria) != rp._norm(d.subcategoria):
        partes.append(f"Cambió la subcategoría: «{a.subcategoria or 'ninguna'}» ({a.origen}) → «{d.subcategoria or 'ninguna'}»"
                      f" ({d.origen}). {d.clasificacion}")
    salieron = [pid for pid in a.parecidos if pid not in d.parecidos]
    entraron = [pid for pid in d.parecidos if pid not in a.parecidos]
    motivos = []
    for pid in salieron:
        p = bd.get(Producto, pid)
        if p and marca and rp._norm(p.marca).strip() == marca:
            m = "misma marca (la marca ya no suma)"
        elif p and suyo and _grupo(p) and _grupo(p) != suyo:
            m = "otra forma de producto"
        elif p and rp._norm(p.subcategoria) != rp._norm(d.subcategoria):
            m = "es de otra subcategoría"
        else:
            m = "lo desplazó uno más parecido"
        motivos.append(f"{a.parecidos[pid]} ({m})")
    if motivos:
        partes.append("Salieron de sus parecidos: " + "; ".join(motivos[:6]) + ".")
    if entraron:
        partes.append("Entraron: " + "; ".join(d.parecidos[pid] for pid in entraron[:6]) + ".")
    cambian = [f"{f.capitalize()} {a.factores.get(f)} → {d.factores.get(f)}" for f in sorted(set(a.factores) | set(d.factores))
               if a.factores.get(f) != d.factores.get(f)]
    if cambian:
        partes.append("Factores que cambian: " + ", ".join(cambian) + ".")
    fijos_mal = [f for f in FACTORES_FIJOS if a.factores.get(f) != d.factores.get(f)]
    explicado = bool(partes[:-1] if cambian else partes) and not fijos_mal
    if a.puntaje == d.puntaje and a.color == d.color:
        explicado = True
    if fijos_mal:
        partes.append(f"REVISAR: cambió {', '.join(fijos_mal)}, que no depende de la clasificación.")
    elif not explicado:
        partes.append("REVISAR: cambió el puntaje sin cambiar la subcategoría ni los parecidos.")
    return " ".join(partes), explicado


def comparar(bd: Session, ids: list[int], avance=None, hoy: date | None = None) -> list[dict]:
    filas = []
    for i, eid in enumerate(ids, 1):
        if avance:
            avance(i, len(ids))
        e = bd.get(ProductoEvaluacion, eid)
        if e is None:
            continue
        guardada = foto_de(e)
        nombre = rp.sujeto_de_propuesta(bd.get(rp.Propuesta, e.propuesta_id)).nombre if e.propuesta_id else \
            rp.sujeto_de_idea(bd.get(rp.ProductoIdea, e.idea_id)).nombre
        fila = {"evaluacion": eid, "producto": nombre, "guardada": guardada}
        try:
            fila["v053"] = simular(bd, eid, True, hoy)
            fila["v054"] = simular(bd, eid, False, hoy)
            fila["por_que"], fila["explicado"] = por_que(bd, e, fila["v053"], fila["v054"])
        except Exception as ex:  # noqa: BLE001 - una que truena no detiene a las demás
            bd.rollback()
            log.exception("Comparación de la evaluación %s", eid)
            fila["error"] = str(ex)[:300]
        filas.append(fila)
    return filas


def resumen(filas: list[dict]) -> dict:
    ok = [f for f in filas if "v054" in f]
    return {"evaluaciones": len(filas), "comparadas": len(ok), "con_error": len(filas) - len(ok),
            "cambian_color": sum(1 for f in ok if f["v053"].color != f["v054"].color),
            "cambian_puntaje": sum(1 for f in ok if f["v053"].puntaje != f["v054"].puntaje),
            "cambian_subcategoria": sum(1 for f in ok if rp._norm(f["v053"].subcategoria) != rp._norm(f["v054"].subcategoria)),
            "sin_explicar": sum(1 for f in ok if not f["explicado"])}


def a_excel(ruta: str, version: str, filas: list[dict]) -> dict:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    res = resumen(filas)
    wb = Workbook()
    h = wb.active
    h.title = "Resumen"
    h.append([f"Comparación v0.5.3 contra {version} · evaluaciones vigentes"])
    h["A1"].font = Font(bold=True, size=14)
    h.append(["Cada evaluación se calculó dos veces hoy, con los mismos precios de internet que ya tenía guardados: "
              "una como la v0.5.3 y otra con la nueva versión. Ninguna evaluación real cambió por esta comparación."])
    h.append([])
    for k, txt in (("evaluaciones", "Evaluaciones vigentes comparadas"), ("cambian_color", "Cambian de color"),
                   ("cambian_puntaje", "Cambian de puntaje"), ("cambian_subcategoria", "Cambian de subcategoría"),
                   ("sin_explicar", "Cambios sin explicar (revisar)"), ("con_error", "No se pudieron calcular")):
        h.append([txt, res[k]])
    h.column_dimensions["A"].width = 48
    rojo, verde, amarillo = (PatternFill("solid", fgColor=c) for c in ("F8D7D7", "D9F2D9", "FFF3CD"))
    for titulo, cuales in (("Cambios", lambda f: "v054" in f and (f["v053"].puntaje != f["v054"].puntaje
                                                                   or f["v053"].color != f["v054"].color
                                                                   or rp._norm(f["v053"].subcategoria) != rp._norm(f["v054"].subcategoria))),
                           ("Todas", lambda f: True)):
        x = wb.create_sheet(titulo)
        x.append(["Evaluación", "Producto", "Guardada hoy", "Color guardado", "v0.5.3 (recalculada)", "Color v0.5.3",
                  "v0.5.4", "Color v0.5.4", "Diferencia", "Subcategoría v0.5.3", "Subcategoría v0.5.4", "Por qué",
                  "¿Explicado?", "Error"])
        for f in filas:
            if not cuales(f):
                continue
            g, a, d = f["guardada"], f.get("v053") or Foto(), f.get("v054") or Foto()
            dif = (d.puntaje - a.puntaje) if d.puntaje is not None and a.puntaje is not None else None
            x.append([f["evaluacion"], f["producto"], g.puntaje, g.color, a.puntaje, a.color, d.puntaje, d.color, dif,
                      a.subcategoria, d.subcategoria, f.get("por_que", ""),
                      "" if "v054" not in f else ("Sí" if f["explicado"] else "No"), f.get("error") or a.error or d.error])
            if "v054" in f and not f["explicado"]:
                x.cell(x.max_row, 13).fill = amarillo
            if dif:
                x.cell(x.max_row, 9).fill = verde if dif > 0 else rojo
            x.cell(x.max_row, 12).alignment = Alignment(wrap_text=True, vertical="top")
        for celda in x[1]:
            celda.font = Font(bold=True)
        x.freeze_panes = "A2"
        x.column_dimensions["B"].width = 40
        x.column_dimensions["L"].width = 90
    wb.save(ruta)
    return res


def correr(version: str, ruta_xlsx: str, avance=None) -> dict:
    from core.bd import motor

    with Session(motor(), expire_on_commit=False) as bd:
        filas = comparar(bd, lista_fija(bd), avance)
        res = a_excel(ruta_xlsx, version, filas)
    return {"version": version, "corrida": "comparacion", **res}


def json_de(res: dict) -> str:
    return json.dumps(res, ensure_ascii=False, default=str)
