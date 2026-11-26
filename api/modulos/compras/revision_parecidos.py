"""Revisión por lote de los parecidos del radar de productos (Diego, 26 nov 2026: «tenemos muchos colágenos… por qué no
sale» y «no podemos ir producto por producto»).

Junta todas las evaluaciones vigentes y cuenta cuántos parecidos tiene cada una. Las que tienen menos de 3 y llevan un
ingrediente principal del que sí tenemos productos en el catálogo son las que se quedaron sin parecidos por los filtros
(caso Colágeno + Inositol). Después de «Recalcular todas» con la v0.6.5, esa cuenta debe bajar a casi cero.
Solo lee: no usa la IA ni DataForSEO, no cambia las evaluaciones."""
from collections import Counter
from dataclasses import dataclass
from io import BytesIO

from sqlalchemy import select, true
from sqlalchemy.orm import Session, selectinload

from modulos.compras import radar_productos as rp
from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
from modulos.compras.modelos_propuestas import Propuesta

POCOS = 3


@dataclass
class Fila:
    evaluacion_id: int
    referencia: str
    nombre: str
    subcategoria: str | None
    clasificacion: str | None
    parecidos: int
    ingrediente: str | None
    del_ingrediente: int
    parecidos_del_ingrediente: int
    puntaje: int | None
    demanda: str | None

    @property
    def afectada(self) -> bool:
        """Menos de 3 parecidos aunque en el catálogo hay 3 o más con su ingrediente principal."""
        return self.parecidos < POCOS and self.del_ingrediente >= rp.MIN_POR_INGREDIENTE


def revisar(bd: Session) -> list[Fila]:
    activos = rp.catalogo_activo(bd)
    evals = bd.scalars(select(ProductoEvaluacion).options(selectinload(ProductoEvaluacion.comparables),
                                                         selectinload(ProductoEvaluacion.factores))
                       .where(ProductoEvaluacion.vigente == true(), ProductoEvaluacion.estado == "lista")
                       .order_by(ProductoEvaluacion.evaluacion_id)).all()
    ideas = {i.idea_id: i for i in bd.scalars(select(ProductoIdea).where(
        ProductoIdea.idea_id.in_([e.idea_id for e in evals if e.idea_id] or [0])))}
    props = {p.propuesta_id: p for p in bd.scalars(select(Propuesta).where(
        Propuesta.propuesta_id.in_([e.propuesta_id for e in evals if e.propuesta_id] or [0])))}
    filas: list[Fila] = []
    for e in evals:
        try:
            if e.idea_id and e.idea_id in ideas:
                s, ref = rp.sujeto_de_idea(ideas[e.idea_id]), f"idea {e.idea_id}"
            elif e.propuesta_id and e.propuesta_id in props:
                s, ref = rp.sujeto_de_propuesta(props[e.propuesta_id]), f"propuesta {e.propuesta_id}"
            else:
                continue
        except Exception:  # noqa: BLE001 - una captura rara no detiene la revisión
            continue
        suyo = rp.del_ingrediente(s, activos)
        ids = suyo[1] if suyo else set()
        comparables = {c.producto_id for c in e.comparables}
        demanda = next((f"{f.puntaje if f.puntaje is not None else 'sin datos'} · {f.valor or ''}" for f in e.factores
                        if f.factor == "demanda"), None)
        filas.append(Fila(e.evaluacion_id, ref, s.nombre, e.subcategoria, e.clasificacion_origen, len(comparables),
                          suyo[0] if suyo else None, len(ids), len(comparables & ids),
                          e.puntaje, demanda))
    return filas


def resumen(filas: list[Fila]) -> dict:
    por = Counter(min(f.parecidos, POCOS) for f in filas)
    return {"evaluaciones": len(filas),
            "sin_parecidos": por[0], "uno": por[1], "dos": por[2], "tres_o_mas": por[POCOS],
            "afectadas": sum(f.afectada for f in filas)}


def a_excel(filas: list[Fila], res: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    h = wb.active
    h.title = "Resumen"
    h.append(["Revisión de parecidos del radar de productos"])
    h["A1"].font = Font(bold=True, size=14)
    h.append([])
    for texto, n in (("Evaluaciones vigentes", res["evaluaciones"]), ("Sin ningún parecido", res["sin_parecidos"]),
                     ("Con 1 parecido", res["uno"]), ("Con 2 parecidos", res["dos"]), ("Con 3 o más", res["tres_o_mas"]),
                     ("Afectadas: menos de 3 parecidos aunque hay productos con su ingrediente", res["afectadas"])):
        h.append([texto, n])
    h.append([])
    h.append(["Qué hacer: publicar la v0.6.5 y dar «Recalcular todas». Las afectadas deben quedar en casi cero."])
    h.column_dimensions["A"].width = 72
    d = wb.create_sheet("Detalle")
    d.append(["Evaluación", "Referencia", "Producto", "Subcategoría", "Cómo se clasificó", "Parecidos",
              "Ingrediente principal", "Productos con ese ingrediente", "De ellos entre sus parecidos", "Afectada",
              "Calificación", "Demanda"])
    for f in sorted(filas, key=lambda f: (not f.afectada, f.parecidos, f.evaluacion_id)):
        d.append([f.evaluacion_id, f.referencia, f.nombre, f.subcategoria, f.clasificacion, f.parecidos, f.ingrediente,
                  f.del_ingrediente, f.parecidos_del_ingrediente, "Sí" if f.afectada else "", f.puntaje, f.demanda])
    for col, ancho in zip("ABCDEFGHIJKL", (11, 16, 48, 30, 16, 10, 18, 14, 14, 10, 12, 60)):
        d.column_dimensions[col].width = ancho
    for celda in d[1]:
        celda.font = Font(bold=True)
    salida = BytesIO()
    wb.save(salida)
    return salida.getvalue()
