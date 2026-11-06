"""Acta de una reunión del comité de producto nuevo, en PDF (pedido de Diego, 2026-11-05): quién asistió, qué se
presentó, qué se decidió con su motivo, lo que no pasó el pre-filtro y lo que pidió el comité. Sale de los mismos datos
de la reunión, sin IA, para mandarla por correo sin redactarla aparte. Si la reunión no está cerrada, sale como borrador.
"""
from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modulos.metodos import diagrama
from modulos.metodos.pdf import LOGO

L, LB = diagrama.LETRA, diagrama.LETRA_NEGRITA
NEGRO, GRIS, NARANJA, CLARO = (HexColor(x) for x in (diagrama.NEGRO, diagrama.GRIS, diagrama.NARANJA, diagrama.GRIS_CLARO))
ANCHO, ALTO = letter
MARGEN = 46
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
DECISION = {"aceptado": "Aceptado", "denegado": "Denegado", "en_espera": "En espera"}
COLOR_DECISION = {"aceptado": "#15803D", "denegado": "#B91C1C", "en_espera": diagrama.GRIS}
SEMAFORO = {"verde": ("Verde", "#16A34A"), "amarillo": ("Amarillo", "#CA8A04"), "rojo": ("Rojo", "#DC2626")}

E = {
    "titulo": ParagraphStyle("titulo", fontName=LB, fontSize=18, leading=22, textColor=NEGRO),
    "sub": ParagraphStyle("sub", fontName=L, fontSize=10, leading=14, textColor=GRIS),
    "h2": ParagraphStyle("h2", fontName=LB, fontSize=11.5, leading=15, textColor=NARANJA, spaceBefore=14, spaceAfter=5),
    "p": ParagraphStyle("p", fontName=L, fontSize=9.5, leading=13, textColor=NEGRO),
    "chico": ParagraphStyle("chico", fontName=L, fontSize=8.5, leading=11.5, textColor=NEGRO),
    "gris": ParagraphStyle("gris", fontName=L, fontSize=8.5, leading=11.5, textColor=GRIS),
    "cab": ParagraphStyle("cab", fontName=LB, fontSize=8, leading=10, textColor=GRIS),
    "cifra": ParagraphStyle("cifra", fontName=LB, fontSize=16, leading=19, textColor=NEGRO),
}


def fecha_larga(f: date) -> str:
    return f"{DIAS[f.weekday()].capitalize()}, {f.day} de {MESES[f.month - 1]} de {f.year}"


def _t(x) -> str:
    return escape(str(x)) if x not in (None, "") else ""


def _tabla(filas: list[list], anchos: list[float]) -> Table:
    t = Table(filas, colWidths=anchos, repeatRows=1)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, NEGRO),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, CLARO),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def generar(r, generado: datetime) -> bytes:
    """`r` es la salida de la reunión (`ReunionSalida`)."""
    cerrada = r.estado == "cerrada"
    util = ANCHO - 2 * MARGEN
    hay: list = []

    titulo = "Acta del comité de producto nuevo" + ("" if cerrada else " (borrador)")
    hay += [Paragraph(titulo, E["titulo"]), Spacer(1, 3), Paragraph(fecha_larga(r.fecha), E["sub"])]
    if not cerrada:
        hay.append(Paragraph(f"La reunión sigue en «{_t(r.estado_texto)}»: las decisiones pueden cambiar.", E["gris"]))
    if r.notas:
        hay += [Spacer(1, 6), Paragraph(_t(r.notas), E["p"])]

    # Cifras
    b = r.embudo
    cifras = [(b.subidos, "se subieron"), (b.pasan, "pasaron el pre-filtro"), (b.aceptados, "aceptados"),
              (b.denegados, "denegados"), (b.en_espera, "en espera")]
    t = Table([[Paragraph(str(n), E["cifra"]) for n, _ in cifras], [Paragraph(x, E["gris"]) for _, x in cifras]],
              colWidths=[util / len(cifras)] * len(cifras))
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CLARO), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 1), (-1, 1), 8)]))
    hay += [Spacer(1, 12), t]

    # Asistentes
    hay.append(Paragraph("Asistieron", E["h2"]))
    if r.asistentes:
        hay.append(Paragraph(" · ".join(_t(a.nombre) + (f" ({_t(a.puesto)})" if a.puesto else "") for a in r.asistentes), E["p"]))
    else:
        hay.append(Paragraph("No se registraron asistentes.", E["gris"]))

    # Decisiones
    presentados = [i for i in r.productos if i.prefiltro == "pasa"]
    hay.append(Paragraph("Decisiones del comité", E["h2"]))
    if presentados:
        filas = [[Paragraph(x, E["cab"]) for x in ("#", "Producto", "Semáforo", "Decisión", "Motivo")]]
        for n, i in enumerate(presentados, start=1):
            color = i.decision_color or (i.evaluacion.color if i.evaluacion else None)
            puntaje = i.evaluacion.puntaje if i.evaluacion else None
            sem = (f'<font name="{LB}" color="{SEMAFORO[color][1]}">{SEMAFORO[color][0]}</font>' if color in SEMAFORO
                   else "Sin semáforo")
            if puntaje is not None:
                sem += f" · {puntaje}"
            prov = i.proveedor or "Sin proveedor"
            producto = f"<font name='{LB}'>{_t(i.nombre)}</font><br/><font color='{diagrama.GRIS}'>{_t(prov)}"
            if i.precio:
                producto += f" · precio ${float(i.precio):,.2f}"
            producto += "</font>"
            dec = (f'<font name="{LB}" color="{COLOR_DECISION[i.decision]}">{DECISION[i.decision]}</font>' if i.decision
                   else '<font color="#B91C1C">Sin decisión</font>')
            filas.append([Paragraph(str(n), E["chico"]), Paragraph(producto, E["chico"]), Paragraph(sem, E["chico"]),
                          Paragraph(dec, E["chico"]), Paragraph(_t(i.decision_motivo), E["chico"])])
        hay.append(_tabla(filas, [18, util * 0.34, util * 0.15, util * 0.13, util - 18 - util * 0.62]))
    else:
        hay.append(Paragraph("Ningún producto pasó el pre-filtro.", E["gris"]))

    no_pasan = [i for i in r.productos if i.prefiltro == "no_pasa"]
    if no_pasan:
        hay.append(Paragraph("No pasaron el pre-filtro de Compras", E["h2"]))
        filas = [[Paragraph(x, E["cab"]) for x in ("Producto", "Motivo")]]
        filas += [[Paragraph(f"<font name='{LB}'>{_t(i.nombre)}</font>", E["chico"]), Paragraph(_t(i.prefiltro_motivo), E["chico"])]
                  for i in no_pasan]
        hay.append(_tabla(filas, [util * 0.38, util * 0.62]))

    # Peticiones
    if r.peticiones:
        hay.append(Paragraph("Lo que pidió el comité", E["h2"]))
        filas = [[Paragraph(x, E["cab"]) for x in ("Petición", "Producto", "Quién la pidió", "Estado")]]
        for p in r.peticiones:
            texto = _t(p.texto) + (f"<br/><font color='{diagrama.GRIS}'>Respuesta: {_t(p.respuesta)}</font>" if p.respuesta else "")
            quien = _t(p.asistente) + (f" ({_t(p.puesto)})" if p.puesto else "")
            filas.append([Paragraph(texto, E["chico"]), Paragraph(_t(p.producto) or "General", E["chico"]),
                          Paragraph(quien or "—", E["chico"]),
                          Paragraph("Atendida" if p.estado == "atendida" else "Abierta", E["chico"])])
        hay.append(_tabla(filas, [util * 0.46, util * 0.24, util * 0.18, util * 0.12]))

    if r.aprendizajes:
        hay += [Paragraph("Qué aprendimos", E["h2"]), Paragraph(_t(r.aprendizajes).replace("\n", "<br/>"), E["p"])]

    pie = (f"Plataforma SMN · Transformación Digital · Generada el {generado.day} de {MESES[generado.month - 1]} de "
           f"{generado.year} a las {generado:%H:%M}")

    def pagina(c, doc):
        c.saveState()
        c.setFillColor(NEGRO)
        c.rect(0, ALTO - 48, ANCHO, 48, stroke=0, fill=1)
        c.setFillColor(NARANJA)
        c.rect(0, ALTO - 51, ANCHO, 3, stroke=0, fill=1)
        if LOGO.is_file():
            c.drawImage(str(LOGO), MARGEN, ALTO - 34, width=130, height=130 * 57 / 400, mask="auto")
        c.setFillColor(HexColor(diagrama.BLANCO))
        c.setFont(LB, 9)
        c.drawRightString(ANCHO - MARGEN, ALTO - 24, "Comité de producto nuevo")
        c.setFont(L, 7.5)
        c.drawRightString(ANCHO - MARGEN, ALTO - 36, fecha_larga(r.fecha))
        c.setFont(L, 7.5)
        c.setFillColor(GRIS)
        c.drawString(MARGEN, 26, pie)
        c.drawRightString(ANCHO - MARGEN, 26, f"Página {doc.page}")
        c.restoreState()

    salida = BytesIO()
    doc = SimpleDocTemplate(salida, pagesize=letter, leftMargin=MARGEN, rightMargin=MARGEN, topMargin=76,
                            bottomMargin=46, title=titulo, author="Súper Mayoreo Naturista")
    doc.build(hay, onFirstPage=pagina, onLaterPages=pagina)
    return salida.getvalue()
