"""PDF del expediente, armado con los permisos de quien lo pide: la fórmula técnica solo va si esa persona puede
verla, y cada página lleva su nombre y la fecha como marca de agua."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from modulos.metodos import diagrama

LOGO = Path(__file__).resolve().parents[2] / "recursos" / "logo-reporte.png"
ANCHO, ALTO = letter
M = 46
L, LB = diagrama.LETRA, diagrama.LETRA_NEGRITA
NEGRO, GRIS, NARANJA = HexColor(diagrama.NEGRO), HexColor(diagrama.GRIS), HexColor(diagrama.NARANJA)
E = {
    "t": ParagraphStyle("t", fontName=LB, fontSize=16, leading=20, textColor=NEGRO, spaceAfter=2),
    "d": ParagraphStyle("d", fontName=L, fontSize=8.5, leading=12, textColor=GRIS, spaceAfter=8),
    "h": ParagraphStyle("h", fontName=LB, fontSize=11.5, leading=15, textColor=NARANJA, spaceBefore=10, spaceAfter=4),
    "p": ParagraphStyle("p", fontName=L, fontSize=9, leading=12.5, textColor=NEGRO, spaceAfter=4),
    "c": ParagraphStyle("c", fontName=L, fontSize=7.8, leading=10, textColor=NEGRO),
    "cb": ParagraphStyle("cb", fontName=LB, fontSize=7.8, leading=10, textColor=NEGRO),
}
COLOR = {"cumple": "#1f9d55", "incumple": "#d93025", "pendiente": "#b07d05", "no_aplica": "#7c7c76"}


def _p(texto, estilo="p") -> Paragraph:
    return Paragraph(escape(str(texto if texto is not None else "—")), E[estilo])


def _tabla(encabezados: list[str], filas: list[list], anchos: list[float]) -> Table:
    datos = [[Paragraph(escape(h), E["cb"]) for h in encabezados]] + [
        [c if isinstance(c, Paragraph) else _p(c, "c") for c in f] for f in filas]
    t = Table(datos, colWidths=[a * (ANCHO - 2 * M) for a in anchos], repeatRows=1)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.6, HexColor("#d2d2cd")),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.3, HexColor("#e4e4e0")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def armar(d: dict, *, quien: str, cuando: str) -> bytes:
    """`d` ya viene filtrado por permisos (ver rutas_expedientes.pdf)."""
    salida = BytesIO()

    def pagina(c, doc):
        c.saveState()
        if LOGO.is_file():
            c.drawImage(str(LOGO), M, ALTO - 40, width=110, height=22, preserveAspectRatio=True, mask="auto")
        c.setFont(L, 7.5)
        c.setFillColor(GRIS)
        c.drawRightString(ANCHO - M, ALTO - 30, f"{d['folio']} · Innovación Vidanat")
        c.drawString(M, 24, f"Pedido por {quien} el {cuando}. Documento interno; no se reenvía.")
        c.drawRightString(ANCHO - M, 24, f"Página {doc.page}")
        c.setFillColor(Color(0.85, 0.2, 0.15, alpha=0.10))
        c.setFont(LB, 26)
        c.translate(ANCHO / 2, ALTO / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, f"{quien} · {cuando}")
        c.restoreState()

    doc = BaseDocTemplate(salida, pagesize=letter, leftMargin=M, rightMargin=M, topMargin=60, bottomMargin=44,
                          title=f"{d['folio']} {d['nombre']}", author="Plataforma SMN")
    doc.addPageTemplates([PageTemplate("p", [Frame(M, 44, ANCHO - 2 * M, ALTO - 104, id="f")], onPage=pagina)])
    h = [_p(f"{d['folio']} · {d['nombre']}", "t"),
         _p(f"Etapa: {d['etapa']} · Estado: {d['estado']} · Categoría: {d.get('categoria_sanitaria') or '—'} · "
            f"Jurisdicción: {d.get('jurisdiccion')}", "d")]
    ficha = d.get("ficha")
    h.append(_p("Ficha del producto", "h"))
    if ficha:
        h.append(_p(f"Versión {ficha['numero']} del {ficha['creado_en'][:10]}", "d"))
        for k, v in ficha["datos"].items():
            h.append(_p(f"{k.replace('_', ' ').capitalize()}: {', '.join(v) if isinstance(v, list) else v}"))
        h.append(_tabla(["Ingrediente", "Forma", "Compuesto", "Activo"],
                        [[i.get("nombre"), i.get("forma"),
                          f"{i.get('cantidad_compuesto') or '—'} {i.get('unidad_compuesto') or ''}",
                          f"{i.get('cantidad_activa') or '—'} {i.get('unidad_activa') or ''}"] for i in ficha["ingredientes"]],
                        [0.34, 0.26, 0.2, 0.2]))
    else:
        h.append(_p("Sin ficha capturada."))
    h.append(_p("Fórmula técnica", "h"))
    if d.get("formula") is None:
        h.append(_p("Restringida: no se incluye para quien pidió este PDF."))
    elif d["formula"]:
        f = d["formula"]
        h.append(_p(f"Versión {f['numero']}", "d"))
        h.append(_tabla(["Componente", "Función", "Cantidad", "Proveedor"],
                        [[x.get("nombre"), x.get("funcion"), f"{x.get('cantidad') or ''} {x.get('unidad') or ''}",
                          x.get("proveedor")] for x in f["contenido"].get("componentes", [])], [0.36, 0.2, 0.2, 0.24]))
    else:
        h.append(_p("Sin fórmula capturada."))
    h.append(_p("Evidencia citada", "h"))
    h.append(_tabla(["Fuente", "Pág.", "Qué respalda", "Aplica"],
                    [[f"{e['titulo']} (v{e['version']})", e.get("pagina"), e["respalda"], e["aplica"]] for e in d["evidencia"]]
                    or [["Sin evidencia citada", "", "", ""]], [0.36, 0.07, 0.43, 0.14]))
    ev = d.get("evaluacion")
    h.append(_p("Reglas: última evaluación", "h"))
    if ev:
        h.append(_p(f"Evaluación #{ev['numero']} del {ev['creada_en'][:16].replace('T', ' ')} · motor {ev['motor']} · "
                    f"ficha v{ev.get('ficha_version') or '—'}", "d"))
        h.append(_tabla(["Resultado", "Regla", "Severidad", "Motivo"],
                        [[Paragraph(f'<font color="{COLOR.get(r["resultado"], "#222221")}"><b>{escape(r["resultado"])}</b></font>', E["c"]),
                          f"{r['regla']} v{r['version']}", r["severidad"], r["motivo"]] for r in ev["resultados"]],
                        [0.13, 0.17, 0.12, 0.58]))
    else:
        h.append(_p("Sin evaluación."))
    h.append(_p("Decisiones", "h"))
    h.append(_tabla(["Fecha", "Etapa", "Resultado", "Motivo y condiciones", "Decidió"],
                    [[x["decidida_en"][:10], x["etapa"], x["resultado"], f"{x['motivo']} {x.get('condiciones') or ''}",
                      x.get("decidida_por")] for x in d["decisiones"]] or [["", "", "Sin decisiones", "", ""]],
                    [0.12, 0.12, 0.12, 0.44, 0.2]))
    h.append(Spacer(1, 6))
    doc.build(h)
    return salida.getvalue()
