"""PDF oficial de un manual: encabezado con logo, clave, versión y vigencia; el texto en el formato estándar; el
diagrama de flujo después de la sección «Procedimiento»; y en el pie quién lo aprobó y la página.

Si el diagrama no cabe en una hoja carta, va en una hoja más larga (mismo ancho) para que se lea completo.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer)
from reportlab.pdfgen import canvas as canvas_

from modulos.metodos import diagrama
from modulos.metodos.redaccion import PREGUNTA
from nucleo.lectura import bloques_de_texto

LOGO = Path(__file__).resolve().parents[2] / "recursos" / "logo-correo.png"
ANCHO, ALTO = letter
MARGEN = 50
ARRIBA, ABAJO = 92, 58
UTIL = ANCHO - 2 * MARGEN
L, LB = diagrama.LETRA, diagrama.LETRA_NEGRITA

ESTILOS = {
    "titulo": ParagraphStyle("titulo", fontName=LB, fontSize=17, leading=21, textColor=HexColor(diagrama.NEGRO),
                             spaceAfter=4),
    "datos": ParagraphStyle("datos", fontName=L, fontSize=8.5, leading=12, textColor=HexColor(diagrama.GRIS), spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName=LB, fontSize=12, leading=16, textColor=HexColor(diagrama.NARANJA),
                         spaceBefore=12, spaceAfter=5),
    "h3": ParagraphStyle("h3", fontName=LB, fontSize=10, leading=14, textColor=HexColor(diagrama.NEGRO),
                         spaceBefore=8, spaceAfter=4),
    "p": ParagraphStyle("p", fontName=L, fontSize=9.5, leading=13.5, textColor=HexColor(diagrama.NEGRO), spaceAfter=5,
                        alignment=TA_LEFT),
}
ESTILOS["lista"] = ParagraphStyle("lista", parent=ESTILOS["p"], leftIndent=16, bulletIndent=2, spaceAfter=3)


@dataclass
class Datos:
    titulo: str
    texto: str
    flujo: dict | None
    area: str
    version: str
    clave: str | None = None
    vigente_desde: date | None = None
    sistema: str | None = None
    aprobado_por: str | None = None
    aprobado_en: datetime | None = None
    pie: str = ""
    borrador: bool = False


def _en_linea(texto: str, borrador: bool) -> str:
    t = escape(texto)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    if borrador:
        t = PREGUNTA.sub(lambda m: f'<font backColor="#FBEBD0" color="#8A5A00"><b>[PREGUNTA: {m.group(1)}]</b></font>', t)
    return t


class DiagramaFlowable(Flowable):
    def __init__(self, d: diagrama.Dibujo, ancho: float):
        super().__init__()
        self.d, self.escala = d, min(1.0, ancho / d.ancho)

    def wrap(self, *_):
        return self.d.ancho * self.escala, self.d.alto * self.escala

    def draw(self):
        diagrama.en_pdf(self.canv, self.d, 0, self.d.alto * self.escala, self.escala)


def _pie_numerado(datos: Datos):
    class Lienzo(canvas_.Canvas):
        """Pone «Página n de m» cuando ya se conocen todas las hojas."""

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._hojas = []

        def showPage(self):
            self._hojas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._hojas)
            for estado in self._hojas:
                self.__dict__.update(estado)
                ancho = self._pagesize[0]
                self.setFont(L, 7.5)
                self.setFillColor(HexColor(diagrama.GRIS))
                self.drawRightString(ancho - MARGEN, 30, f"Página {self._pageNumber} de {total}")
                super().showPage()
            super().save()
    return Lienzo


def _encabezado(datos: Datos):
    def pintar(c, doc):
        ancho, alto = c._pagesize
        c.saveState()
        c.setFillColor(HexColor(diagrama.NEGRO))
        c.rect(0, alto - 58, ancho, 58, stroke=0, fill=1)
        c.setFillColor(HexColor(diagrama.NARANJA))
        c.rect(0, alto - 61, ancho, 3, stroke=0, fill=1)
        if LOGO.is_file():
            c.drawImage(str(LOGO), MARGEN, alto - 40, width=150, height=150 * 57 / 400, mask="auto")
        c.setFillColor(HexColor(diagrama.BLANCO))
        c.setFont(LB, 9.5)
        titulo = datos.titulo if len(datos.titulo) <= 60 else datos.titulo[:57] + "…"
        c.drawRightString(ancho - MARGEN, alto - 27, titulo)
        c.setFont(L, 7.5)
        c.drawRightString(ancho - MARGEN, alto - 40, " · ".join(x for x in (
            datos.clave, f"Versión {datos.version}",
            f"Vigente desde {datos.vigente_desde:%d/%m/%Y}" if datos.vigente_desde else None, datos.area) if x))
        # pie
        c.setStrokeColor(HexColor("#D9D7D2"))
        c.setLineWidth(0.5)
        c.line(MARGEN, 44, ancho - MARGEN, 44)
        c.setFont(L, 7.5)
        c.setFillColor(HexColor(diagrama.GRIS))
        pie = datos.pie if len(datos.pie) <= 120 else datos.pie[:117] + "…"
        c.drawString(MARGEN, 30, pie)
        if datos.borrador:
            c.setFillColor(HexColor("#DE951B"), alpha=0.10)
            c.setFont(LB, 90)
            c.translate(ancho / 2, alto / 2)
            c.rotate(45)
            c.drawCentredString(0, 0, "BORRADOR")
        c.restoreState()
    return pintar


def manual(datos: Datos) -> bytes:
    salida = BytesIO()
    d = diagrama.dibujo(datos.flujo, ancho=UTIL) if datos.flujo and datos.flujo.get("pasos") else None
    alto_util = ALTO - ARRIBA - ABAJO
    largo = d is not None and d.alto > alto_util - 30

    pintar = _encabezado(datos)
    plantillas = [PageTemplate(id="normal", frames=[Frame(MARGEN, ABAJO, UTIL, alto_util, id="f", leftPadding=0,
                                                           rightPadding=0, topPadding=0, bottomPadding=0)],
                               onPage=pintar, pagesize=letter)]
    if largo:
        alto_hoja = d.alto + ARRIBA + ABAJO + 40
        plantillas.append(PageTemplate(id="diagrama", frames=[Frame(MARGEN, ABAJO, UTIL, alto_hoja - ARRIBA - ABAJO,
                                                                     id="fd", leftPadding=0, rightPadding=0,
                                                                     topPadding=0, bottomPadding=0)],
                                       onPage=pintar, pagesize=(ANCHO, alto_hoja)))
    doc = BaseDocTemplate(salida, pagesize=letter, pageTemplates=plantillas, title=datos.titulo,
                          author="Transformación Digital SMN", subject=f"{datos.area} · versión {datos.version}",
                          leftMargin=MARGEN, rightMargin=MARGEN, topMargin=ARRIBA, bottomMargin=ABAJO)

    def bloque_diagrama():
        titulo = Paragraph("Diagrama de flujo", ESTILOS["h3"])
        if not largo:
            return [KeepTogether([titulo, Spacer(1, 4), DiagramaFlowable(d, UTIL)])]
        return [Paragraph("El diagrama de flujo está en la hoja siguiente.", ESTILOS["p"]),
                NextPageTemplate("diagrama"), PageBreak(), titulo, Spacer(1, 4), DiagramaFlowable(d, UTIL),
                NextPageTemplate("normal"), PageBreak()]

    historia, en_procedimiento, puesto = [], False, d is None
    titulo_puesto = False
    for b in bloques_de_texto(datos.texto or ""):
        if b.nivel == 1 and not titulo_puesto:
            historia.append(Paragraph(_en_linea(b.texto, datos.borrador), ESTILOS["titulo"]))
            titulo_puesto = True
            continue
        if b.nivel:
            if en_procedimiento and not puesto:
                historia += bloque_diagrama()
                puesto = True
            en_procedimiento = b.nivel == 2 and "procedimiento" in b.texto.lower()
            historia.append(Paragraph(_en_linea(b.texto, datos.borrador), ESTILOS["h2" if b.nivel <= 2 else "h3"]))
            continue
        m = re.match(r"^([-*•]|\d+[.)])\s+(.*)$", b.texto)
        if m:
            vineta = "•" if m.group(1) in "-*•" else m.group(1)
            historia.append(Paragraph(_en_linea(m.group(2), datos.borrador), ESTILOS["lista"], bulletText=vineta))
        else:
            historia.append(Paragraph(_en_linea(b.texto, datos.borrador), ESTILOS["p"]))
    if not titulo_puesto:
        historia.insert(0, Paragraph(escape(datos.titulo), ESTILOS["titulo"]))
    if not puesto:
        if not en_procedimiento:
            historia.append(Paragraph("Anexo", ESTILOS["h2"]))
        historia += bloque_diagrama()
    if historia and isinstance(historia[-1], PageBreak):  # el diagrama largo quedó al final: sin hoja en blanco
        historia = historia[:-2]
    aprobado = (f"Aprobado por {datos.aprobado_por} el {datos.aprobado_en:%d/%m/%Y}." if datos.aprobado_por and
                datos.aprobado_en else "Sin aprobar.")
    historia.insert(1, Paragraph(" · ".join(x for x in (
        datos.area, f"versión {datos.version}", datos.sistema and f"sistema: {datos.sistema}", aprobado) if x),
        ESTILOS["datos"]))
    doc.build(historia, canvasmaker=_pie_numerado(datos))
    return salida.getvalue()
