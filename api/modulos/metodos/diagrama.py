"""Dibujo del diagrama de flujo por carriles (un carril por puesto, de arriba hacia abajo).

`dibujo(flujo)` acomoda cajas, rombos y flechas una vez; luego se pinta igual en SVG (pantalla), en PDF (reportlab)
y en PNG (Pillow, para Word). Cada paso va en su propio renglón, así las flechas horizontales nunca cruzan otra caja.
Letra Bitstream Vera (viene con reportlab): la misma medida de texto en los tres.
"""
import os
from dataclasses import dataclass, field
from io import BytesIO
from xml.sax.saxutils import escape

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

NARANJA, NEGRO, BLANCO = "#DE951B", "#222221", "#FFFFFF"
GRIS, GRIS_CLARO, CREMA = "#6B6B68", "#F4F3F0", "#FBEBD0"
_FUENTES = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
LETRA, LETRA_NEGRITA = "Vera", "VeraBd"
RUTA_LETRA = {LETRA: os.path.join(_FUENTES, "Vera.ttf"), LETRA_NEGRITA: os.path.join(_FUENTES, "VeraBd.ttf")}
for _n, _r in RUTA_LETRA.items():
    if _n not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(_n, _r))

TAM, TAM_ETIQUETA, TAM_CARRIL = 7.5, 6.5, 8
INTERLINEA = 1.25
ENCABEZADO = 30
HUECO = 24  # espacio entre renglones, ahí van las flechas horizontales
ORILLA = 9  # de la caja a la orilla del carril; ahí corren las flechas que bajan o regresan


@dataclass
class Dibujo:
    ancho: float
    alto: float
    elementos: list[tuple] = field(default_factory=list)


def _partir(texto: str, ancho: float, tam: float, letra: str = LETRA) -> list[str]:
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if pdfmetrics.stringWidth(prueba, letra, tam) <= ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    # una palabra más larga que la caja se corta
    salida = []
    for l in lineas:
        while pdfmetrics.stringWidth(l, letra, tam) > ancho and len(l) > 4:
            corte = len(l)
            while corte > 1 and pdfmetrics.stringWidth(l[:corte] + "-", letra, tam) > ancho:
                corte -= 1
            salida.append(l[:corte] + "-")
            l = l[corte:]
        salida.append(l)
    return salida or [""]


def dibujo(flujo: dict, ancho: float = 540) -> Dibujo:
    carriles = flujo["carriles"] or ["Sin puesto"]
    pasos = flujo["pasos"]
    ac = ancho / len(carriles)  # ancho de cada carril
    caja = ac - 2 * ORILLA
    linea = TAM * INTERLINEA
    col = {c: i for i, c in enumerate(carriles)}
    orden = {p["id"]: i for i, p in enumerate(pasos)}

    # medidas y lugar de cada paso
    nodos, y = {}, ENCABEZADO + HUECO * 0.6
    for p in pasos:
        if p["tipo"] == "decision":
            lineas = _partir(p["texto"], caja * 0.58, TAM)
            alto = max(46.0, len(lineas) * linea / 0.55 + 8)
        elif p["tipo"] in ("inicio", "fin"):
            lineas = _partir(p["texto"], caja - 16, TAM, LETRA_NEGRITA)
            alto = max(20.0, len(lineas) * linea + 8)
        else:
            lineas = _partir(p["texto"], caja - 10, TAM)
            alto = len(lineas) * linea + 12
        cx = col.get(p["carril"], 0) * ac + ac / 2
        ancho_n = caja if p["tipo"] != "inicio" and p["tipo"] != "fin" else min(caja, max(
            70.0, max(pdfmetrics.stringWidth(l, LETRA_NEGRITA, TAM) for l in lineas) + 26))
        nodos[p["id"]] = {"p": p, "cx": cx, "y": y, "alto": alto, "ancho": ancho_n, "lineas": lineas,
                          "carril": col.get(p["carril"], 0)}
        y += alto + HUECO
    alto_total = y - HUECO * 0.4

    d = Dibujo(ancho, alto_total)
    el = d.elementos
    # carriles
    for i, c in enumerate(carriles):
        x = i * ac
        el.append(("rect", x, 0, ac, alto_total, 0, BLANCO if i % 2 == 0 else GRIS_CLARO, None))
        el.append(("rect", x, 0, ac, ENCABEZADO, 0, NEGRO, None))
        nombre = _partir(c, ac - 8, TAM_CARRIL, LETRA_NEGRITA)[:2]
        el.append(("texto", x + ac / 2, ENCABEZADO / 2, nombre, TAM_CARRIL, BLANCO, True))
        if i:
            el.append(("linea", [(x, 0), (x, alto_total)], "#D9D7D2", False, 0.6))
    el.append(("rect", 0, 0, ancho, alto_total, 0, None, NEGRO))
    el.append(("rect", 0, ENCABEZADO - 2.5, ancho, 2.5, 0, NARANJA, None))

    # flechas (antes que las cajas, para que queden debajo)
    canal: dict[tuple[int, str], int] = {}

    def x_canal(carril: int, lado: str) -> float:
        n = canal.get((carril, lado), 0)
        canal[(carril, lado)] = n + 1
        desfase = 3.5 + (n % 3) * 2.2
        return carril * ac + (ac - desfase if lado == "der" else desfase)

    def lados(n):
        mitad = n["ancho"] / 2
        return n["cx"] - mitad, n["cx"] + mitad, n["y"] + n["alto"] / 2

    for p in pasos:
        o = nodos[p["id"]]
        for k, s in enumerate(p["sig"]):
            t = nodos[s["a"]]
            o_izq, o_der, o_cy = lados(o)
            t_izq, t_der, t_cy = lados(t)
            arriba = t["y"] - HUECO / 2
            if orden[s["a"]] > orden[p["id"]]:
                bloqueado = any(nodos[q["id"]]["carril"] == o["carril"]
                                for q in pasos[orden[p["id"]] + 1:orden[s["a"]]])
                if k == 0 and not bloqueado:
                    inicio = (o["cx"], o["y"] + o["alto"])
                    puntos = [inicio, (o["cx"], arriba), (t["cx"], arriba), (t["cx"], t["y"])]
                    if abs(o["cx"] - t["cx"]) < 0.1:
                        puntos = [inicio, (t["cx"], t["y"])]
                else:
                    lado = "izq" if (k >= 2 or (k == 1 and t["carril"] < o["carril"])) else "der"
                    inicio = (o_izq if lado == "izq" else o_der, o_cy)
                    cx = x_canal(o["carril"], lado)
                    puntos = [inicio, (cx, o_cy), (cx, arriba), (t["cx"], arriba), (t["cx"], t["y"])]
            else:  # regresa a un paso de arriba
                inicio = (o_der, o_cy)
                cx = x_canal(o["carril"], "der")
                fin = (t_der, t_cy) if t["carril"] <= o["carril"] else (t_izq, t_cy)
                puntos = [inicio, (cx, o_cy), (cx, t_cy), fin]
            el.append(("linea", puntos, NEGRO, True, 0.9))
            if s.get("etiqueta"):
                (x1, y1), (x2, y2) = puntos[0], puntos[1]
                if abs(x1 - x2) < 0.1:  # baja
                    el.append(("etiqueta", x1 + 3, y1 + 8, s["etiqueta"]))
                else:  # sale de lado; que no se salga del dibujo
                    w_e = pdfmetrics.stringWidth(s["etiqueta"], LETRA_NEGRITA, TAM_ETIQUETA)
                    if x2 > x1:
                        el.append(("etiqueta", min(x1 + 4, ancho - w_e - 2), y1 - 3, s["etiqueta"], "izq"))
                    else:
                        el.append(("etiqueta", max(x1 - 4, w_e + 2), y1 - 3, s["etiqueta"], "der"))

    # cajas
    for n in nodos.values():
        tipo, x, y0, w, h = n["p"]["tipo"], n["cx"] - n["ancho"] / 2, n["y"], n["ancho"], n["alto"]
        if tipo == "decision":
            el.append(("poligono", [(n["cx"], y0), (x + w, y0 + h / 2), (n["cx"], y0 + h), (x, y0 + h / 2)], CREMA, NARANJA))
            el.append(("texto", n["cx"], y0 + h / 2, n["lineas"], TAM, NEGRO, False))
        elif tipo in ("inicio", "fin"):
            el.append(("rect", x, y0, w, h, h / 2, NEGRO, None))
            el.append(("texto", n["cx"], y0 + h / 2, n["lineas"], TAM, BLANCO, True))
        else:
            el.append(("rect", x, y0, w, h, 3, BLANCO, NEGRO))
            el.append(("texto", n["cx"], y0 + h / 2, n["lineas"], TAM, NEGRO, False))
    return d


# ---------------------------------------------------------------- SVG (pantalla)

def _flecha(puntos):
    (x1, y1), (x2, y2) = puntos[-2], puntos[-1]
    largo = max(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, 0.01)
    ux, uy = (x2 - x1) / largo, (y2 - y1) / largo
    t = 4.2
    return [(x2, y2), (x2 - ux * t * 1.6 - uy * t, y2 - uy * t * 1.6 + ux * t),
            (x2 - ux * t * 1.6 + uy * t, y2 - uy * t * 1.6 - ux * t)]


def svg(d: Dibujo) -> str:
    partes = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -1 {d.ancho + 2:.1f} {d.alto + 2:.1f}" '
              f'width="{d.ancho:.0f}" height="{d.alto:.0f}" font-family="Vera, \'Bitstream Vera Sans\', \'DejaVu Sans\', '
              'Verdana, sans-serif">']
    for e in d.elementos:
        if e[0] == "rect":
            _, x, y, w, h, r, relleno, borde = e
            partes.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r:.1f}" '
                          f'fill="{relleno or "none"}" stroke="{borde or "none"}" stroke-width="0.9"/>')
        elif e[0] == "poligono":
            _, pts, relleno, borde = e
            partes.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="{relleno}" '
                          f'stroke="{borde}" stroke-width="1.1"/>')
        elif e[0] == "linea":
            _, pts, color, flecha, grueso = e
            partes.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" '
                          f'stroke="{color}" stroke-width="{grueso}"/>')
            if flecha:
                partes.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in _flecha(pts))}" fill="{color}"/>')
        elif e[0] == "texto":
            _, x, y, lineas, tam, color, negrita = e
            alto = tam * INTERLINEA
            y0 = y - alto * (len(lineas) - 1) / 2 + tam * 0.36
            for i, l in enumerate(lineas):
                partes.append(f'<text x="{x:.1f}" y="{y0 + i * alto:.1f}" font-size="{tam}" fill="{color}" '
                              f'text-anchor="middle"{" font-weight=\"bold\"" if negrita else ""}>{escape(l)}</text>')
        elif e[0] == "etiqueta":
            x, y, texto = e[1], e[2], e[3]
            ancla = "end" if len(e) > 4 and e[4] == "der" else "start"
            partes.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{TAM_ETIQUETA}" fill="{GRIS}" font-weight="bold" '
                          f'text-anchor="{ancla}">{escape(texto)}</text>')
    partes.append("</svg>")
    return "".join(partes)


# ---------------------------------------------------------------- PDF (reportlab)

def en_pdf(lienzo, d: Dibujo, x0: float, y0: float, escala: float = 1.0) -> None:
    """Pinta el dibujo con su esquina superior izquierda en (x0, y0) del lienzo (coordenadas de PDF, y hacia arriba)."""
    from reportlab.lib.colors import HexColor

    def P(x, y):
        return x0 + x * escala, y0 - y * escala

    lienzo.saveState()
    for e in d.elementos:
        if e[0] == "rect":
            _, x, y, w, h, r, relleno, borde = e
            px, py = P(x, y + h)
            if relleno:
                lienzo.setFillColor(HexColor(relleno))
            if borde:
                lienzo.setStrokeColor(HexColor(borde))
                lienzo.setLineWidth(0.9 * escala)
            if r:
                lienzo.roundRect(px, py, w * escala, h * escala, r * escala, stroke=int(bool(borde)), fill=int(bool(relleno)))
            else:
                lienzo.rect(px, py, w * escala, h * escala, stroke=int(bool(borde)), fill=int(bool(relleno)))
        elif e[0] in ("poligono", "linea"):
            pts = e[1]
            camino = lienzo.beginPath()
            camino.moveTo(*P(*pts[0]))
            for p in pts[1:]:
                camino.lineTo(*P(*p))
            if e[0] == "poligono":
                camino.close()
                lienzo.setFillColor(HexColor(e[2]))
                lienzo.setStrokeColor(HexColor(e[3]))
                lienzo.setLineWidth(1.1 * escala)
                lienzo.drawPath(camino, stroke=1, fill=1)
            else:
                lienzo.setStrokeColor(HexColor(e[2]))
                lienzo.setLineWidth(e[4] * escala)
                lienzo.drawPath(camino, stroke=1, fill=0)
                if e[3]:
                    punta = lienzo.beginPath()
                    f = _flecha(pts)
                    punta.moveTo(*P(*f[0]))
                    for p in f[1:]:
                        punta.lineTo(*P(*p))
                    punta.close()
                    lienzo.setFillColor(HexColor(e[2]))
                    lienzo.drawPath(punta, stroke=0, fill=1)
        elif e[0] == "texto":
            _, x, y, lineas, tam, color, negrita = e
            alto = tam * INTERLINEA
            y_1 = y - alto * (len(lineas) - 1) / 2 + tam * 0.36
            lienzo.setFillColor(HexColor(color))
            lienzo.setFont(LETRA_NEGRITA if negrita else LETRA, tam * escala)
            for i, l in enumerate(lineas):
                lienzo.drawCentredString(*P(x, y_1 + i * alto), l)
        elif e[0] == "etiqueta":
            x, y, texto = e[1], e[2], e[3]
            lienzo.setFillColor(HexColor(GRIS))
            lienzo.setFont(LETRA_NEGRITA, TAM_ETIQUETA * escala)
            (lienzo.drawRightString if len(e) > 4 and e[4] == "der" else lienzo.drawString)(*P(x, y), texto)
    lienzo.restoreState()


# ---------------------------------------------------------------- PNG (Pillow, para Word)

def png(d: Dibujo, escala: float = 3.0) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (int(d.ancho * escala) + 2, int(d.alto * escala) + 2), BLANCO)
    g = ImageDraw.Draw(img)
    letras: dict = {}

    def letra(tam, negrita):
        clave = (round(tam * escala), negrita)
        if clave not in letras:
            letras[clave] = ImageFont.truetype(RUTA_LETRA[LETRA_NEGRITA if negrita else LETRA], clave[0])
        return letras[clave]

    def P(x, y):
        return x * escala, y * escala

    for e in d.elementos:
        if e[0] == "rect":
            _, x, y, w, h, r, relleno, borde = e
            caja = [P(x, y), P(x + w, y + h)]
            ancho = max(1, round(0.9 * escala)) if borde else 0
            if r:
                g.rounded_rectangle(caja, radius=r * escala, fill=relleno, outline=borde, width=ancho)
            else:
                g.rectangle(caja, fill=relleno, outline=borde, width=ancho)
        elif e[0] == "poligono":
            g.polygon([P(*p) for p in e[1]], fill=e[2], outline=e[3], width=max(1, round(1.1 * escala)))
        elif e[0] == "linea":
            g.line([P(*p) for p in e[1]], fill=e[2], width=max(1, round(e[4] * escala)), joint="curve")
            if e[3]:
                g.polygon([P(*p) for p in _flecha(e[1])], fill=e[2])
        elif e[0] == "texto":
            _, x, y, lineas, tam, color, negrita = e
            alto = tam * INTERLINEA
            y_1 = y - alto * (len(lineas) - 1) / 2
            for i, l in enumerate(lineas):
                g.text(P(x, y_1 + i * alto), l, fill=color, font=letra(tam, negrita), anchor="mm")
        elif e[0] == "etiqueta":
            x, y, texto = e[1], e[2], e[3]
            g.text(P(x, y), texto, fill=GRIS, font=letra(TAM_ETIQUETA, True),
                   anchor="rs" if len(e) > 4 and e[4] == "der" else "ls")
    salida = BytesIO()
    img.save(salida, "PNG", optimize=True)
    return salida.getvalue()
