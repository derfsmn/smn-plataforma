"""Radar de precios: encontrar nuestro producto en Google Shopping sin que nadie intervenga.

Tomado del proyecto Radar Precios (product_matcher.evaluate_v2 y query_builder, flujo V2):
- Búsquedas: el código de barras (si hay) y una consulta con marca, nombre y presentación.
- Cada resultado se califica de 0 a 100: marca 35, nombre 30, presentación 30, señales 5.
- Reglas duras: si la marca no aparece no se acepta; una presentación distinta (60 contra 120 cápsulas) descarta.
- Encontrado por código de barras con la marca correcta y sin presentación contradictoria: se acepta.
- Lo dudoso (pasa las reglas pero no llega a la calificación, o dos casi empatan) lo revisa la IA.
  Si la IA no queda segura, el producto se queda sin coincidencia y no entra a la comparación.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field, replace

from rapidfuzz.fuzz import token_set_ratio, token_sort_ratio

ABREVIATURAS = {
    "caps": "capsulas", "cap": "capsulas", "capsula": "capsulas", "capsule": "capsulas", "capsules": "capsulas",
    "tab": "tabletas", "tableta": "tabletas", "tabs": "tabletas",
    "gr": "g", "grs": "g", "gramo": "g", "gramos": "g", "kgs": "kg", "kilos": "kg", "kilo": "kg",
    "mililitros": "ml", "mililitro": "ml", "litro": "l", "litros": "l", "lt": "l", "lts": "l",
    "pza": "piezas", "pzas": "piezas", "pieza": "piezas",
    "paquete": "paquetes", "pack": "paquetes", "packs": "paquetes",
    "caramelo": "piezas", "caramelos": "piezas",
}
PRESENTACION = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(mcg|mg|kg|g|ml|l|capsulas|tabletas|piezas|paquetes)\b")
VACIAS = {"con", "sin", "para", "por", "del", "las", "los", "una", "un", "y", "de", "el", "en", "producto"}
MEDIDA = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mcg|mg|kg|gr(?:amos?)?|g|ml|mililitros?|l|litros?|c[aá]ps?(?:ulas?)?|tabletas?|tabs?|"
    r"piezas?|pzas?|pack|paquetes?|porciones?)\b", re.IGNORECASE)
UNIDADES = {"mcg", "mg", "kg", "g", "ml", "l", "capsulas", "tabletas", "piezas", "paquetes", "porciones", "softgels", "gomitas", "sobres"}
# Palabras que, si no están en nuestra descripción, delatan un paquete o kit (caso Birdman: «Kit…», «+ Creatina», «Shaker»)
PAQUETE = {"kit", "combo", "paquetes", "set", "bundle", "shaker", "regalo", "sobres", "lote", "duo", "trio", "mayoreo", "caja"}
PESOS = {"marca": 35, "nombre": 30, "presentacion": 20, "cantidad": 10, "senales": 5}
MARGEN = 1.0  # si el segundo queda a menos de esto del primero, decide la IA
CONFIANZA_IA = 80  # la IA tiene que estar al menos así de segura


def normalizar(texto: str | None) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9.,]+", " ", t)
    t = re.sub(r"(\d)([a-z])", r"\1 \2", t)  # 510gr -> 510 gr, 1000mg -> 1000 mg
    t = re.sub(r"(?<!\d)[.,]|[.,](?!\d)", " ", t)  # punto y coma solo dentro de números (2.5 g); «Clásico,» = «clasico»
    return " ".join(ABREVIATURAS.get(p, p) for p in t.split())


def marca_comercial(marca: str | None) -> str:
    """VIDANAT/VITAMINAS -> VIDANAT: la familia del catálogo no es parte de la marca."""
    return re.split(r"[/|;]", marca or "", maxsplit=1)[0].strip()


def formas_marca(marca: str) -> set[str]:
    """La marca y sus siglas: «nb foods» también se escribe «nbf» (caso NBF en Google, 2026-10-20)."""
    formas = {marca}
    partes = marca.split()
    if len(partes) > 1:
        siglas = partes[0] + "".join(p[0] for p in partes[1:])
        if len(siglas) >= 3:
            formas.add(siglas)
    return formas


def sin_presentacion(texto: str | None) -> str:
    """El texto sin cantidades ni unidades: «Aceite de ajo 500 ml» -> «Aceite de ajo» (para buscadores de tiendas)."""
    return re.sub(r"\s+", " ", MEDIDA.sub(" ", texto or "")).strip()


def presentaciones(texto: str | None) -> set[tuple[str, str]]:
    salida = set()
    for cantidad, unidad in PRESENTACION.findall(normalizar(texto)):
        # «1,000 mg» es mil; «2,5 g» es dos y medio
        n = float(cantidad.replace(",", "") if re.fullmatch(r"\d{1,3},\d{3}", cantidad) else cantidad.replace(",", "."))
        if unidad == "kg":
            n, unidad = n * 1_000_000, "mg"
        elif unidad == "g":
            n, unidad = n * 1000, "mg"
        elif unidad == "mcg":
            n, unidad = n / 1000, "mg"
        elif unidad == "l":
            n, unidad = n * 1000, "ml"
        salida.add((f"{n:g}", unidad))
    return salida


# ---------------------------------------------------------------- búsquedas

PUBLICIDAD = ("apoya tu alimentación", "apoya tu alimentacion", "fórmula limpia", "formula limpia", "sin aditivos",
              "esencia refrescante", "suplemento alimenticio", "alimentación diaria", "alimentacion diaria",
              "cápsula vegana", "capsula vegana", "calidad premium", "100% natural")


def _limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[|;/]+", " ", texto)).strip(" ,-|")


def _sin_publicidad(descripcion: str) -> str:
    """Deja el nombre (primer tramo) y los tramos con medidas; quita frases de publicidad."""
    tramos = [t.strip() for t in re.split(r"[|;]", descripcion) if t.strip()]
    plano = lambda t: unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()  # noqa: E731
    quedan = [t for i, t in enumerate(tramos)
              if i == 0 or (MEDIDA.search(t) and not any(plano(f) in plano(t) for f in PUBLICIDAD))]
    texto = " ".join(quedan) or descripcion
    for frase in PUBLICIDAD:
        texto = re.sub(re.escape(frase), " ", texto, flags=re.IGNORECASE)
    return _limpiar(texto)


def consultas(descripcion: str | None, marca: str | None, codigo_barras: str | None,
              consulta_manual: str | None = None, nombre_tienda: str | None = None) -> list[tuple[str, str]]:
    """[(estrategia, texto)]: a lo más el código de barras y una búsqueda por descripción."""
    if consulta_manual and consulta_manual.strip():
        return [("consulta", consulta_manual.strip())]
    # Primero marca y descripción, como el flujo de n8n de Diego; el código de barras solo si con eso no
    # quedó resuelto (buscar el código en Google Shopping suele traer otros productos)
    salida = []
    comercial = marca_comercial(marca)
    texto = _sin_publicidad(descripcion or "")
    if comercial:
        texto = re.sub(rf"\b{re.escape(comercial)}\b", " ", texto, flags=re.IGNORECASE)
    texto = _limpiar(f"{comercial} {texto}")
    if texto:
        salida.append(("descripcion", texto[:200]))
    # El nombre comercial de la tienda en línea suele ser como lo conoce Google (caso Birdman: «Fitmingo»)
    if nombre_tienda:
        tienda = _sin_publicidad(nombre_tienda)
        if comercial:
            tienda = re.sub(rf"\b{re.escape(comercial)}\b", " ", tienda, flags=re.IGNORECASE)
        tienda = _limpiar(f"{comercial} {tienda}")
        if tienda and set(normalizar(tienda).split()) != set(normalizar(texto).split()):
            salida.append(("tienda", tienda[:200]))
    if codigo_barras and re.fullmatch(r"\d{8,14}", codigo_barras.strip()):
        salida.append(("codigo_barras", codigo_barras.strip()))
    return salida


# ---------------------------------------------------------------- calificación

@dataclass(frozen=True)
class Evaluacion:
    calificacion: float
    marca: bool | None  # None = no se pudo comprobar
    presentacion: bool | None
    contradice: bool
    nombre: float
    aceptada: bool
    dudosa: bool
    motivo: str
    mismo_nombre: bool = False  # el nombre coincide y trae los números y letras sueltas del nuestro
    es_paquete: bool = False  # el título parece un kit o paquete que el nuestro no es


def evaluar(descripcion: str | None, marca: str | None, titulo: str, umbral: float,
            marcas_conocidas: set[str], posicion: int | None = None) -> Evaluacion:
    candidato = normalizar(titulo)
    propia = normalizar(marca_comercial(marca))
    if not propia:
        coincide_marca = None
    elif any(re.search(rf"\b{re.escape(f)}\b", candidato) for f in formas_marca(propia)):
        coincide_marca = True
    else:
        otra = any(m != propia and re.search(rf"\b{re.escape(m)}\b", candidato) for m in marcas_conocidas)
        coincide_marca = False if otra else None

    # Se comparan nombres limpios de los dos lados: sin palabras vacías, cantidades, unidades ni la marca
    # (la presentación se revisa aparte). Si todas las palabras de nuestro nombre están en el título, coincide.
    de_marca = set(propia.split())

    def limpio(t: str) -> list[str]:
        partes = re.sub(r"(\d)([a-z])", r"\1 \2", t).split()
        salida = []
        for i, p in enumerate(partes):
            numero = re.fullmatch(r"[\d.,]+", p)
            if numero and i + 1 < len(partes) and partes[i + 1] in UNIDADES:
                continue  # cantidad de la presentación (500 mg, 100 cápsulas): se revisa aparte
            if p in VACIAS or p in UNIDADES or p in de_marca or p in (".", ","):
                continue
            salida.append(p)  # se quedan letras y números sueltos: vitamina C, omega 3
        return salida

    origen, destino = limpio(normalizar(descripcion)), limpio(candidato)
    if not origen and de_marca:
        # El nombre es la marca misma (DEMOGRASS 30 CAP de la marca DEMOGRASS): se compara con ella
        # (corrida 2005: salía «nombre 0» y no se aceptaba ni en San Pablo ni en Soriana)
        de_marca = set()
        origen, destino = limpio(normalizar(descripcion)), limpio(candidato)
    nombre = 0.0
    if origen:
        a, b = " ".join(origen), " ".join(destino)
        cobertura = 100.0 * sum(1 for p in set(origen) if p in set(destino)) / len(set(origen))
        nombre = max(cobertura, min(float(token_set_ratio(a, b)), float(token_sort_ratio(a, b)) + 15))
    # Números y letras sueltas del nombre distinguen productos (omega 3 / omega 6, vitamina C / D): deben estar
    faltan = sorted({p for p in origen if re.fullmatch(r"[\d.,]+|[a-z]", p)} - set(destino))
    # Las palabras del tipo de producto también (caso Aceite de Ajonjolí contra Aceite de Aguacate, 2026-10-20);
    # se vale abreviada de cualquier lado (multivit / multivitaminas). Las cortas deben estar tal cual: «ajo» no
    # está en «ajonjolí» (caso Aceite de Ajo contra Aceite de Oliva en Walmart, corrida 2004)
    def esta(p: str) -> bool:
        if len(p) < 4:
            return p in destino
        return any(d.startswith(p[:5]) or (len(d) >= 4 and p.startswith(d)) for d in destino)

    sin_palabra = sorted(p for p in set(origen) if len(p) >= 3 and not re.search(r"\d", p) and not esta(p))
    mismo_producto = nombre >= 65 and not faltan and not sin_palabra

    esperadas, encontradas = presentaciones(descripcion), presentaciones(titulo)
    coincide_pres = None if not esperadas or not encontradas else bool(esperadas & encontradas)
    por_unidad = lambda conj: {u: {n for n, uu in conj if uu == u} for _, u in conj}  # noqa: E731
    e, a = por_unidad(esperadas), por_unidad(encontradas)
    contradice = any(not e[u] & a[u] for u in set(e) & set(a))

    puntos = PESOS["marca"] if coincide_marca is True else 0
    puntos += PESOS["nombre"] * nombre / 100
    pres = PESOS["presentacion"] + PESOS["cantidad"]
    puntos += pres if coincide_pres else (0 if esperadas else pres * 0.8)
    rango = 3 if posicion == 1 else 2.5 if posicion and posicion <= 3 else 2 if posicion and posicion <= 10 else 1 if posicion else 0
    puntos = min(100.0, puntos + rango * PESOS["senales"] / 5)

    es_paquete = paquete(descripcion, titulo)
    if es_paquete:
        puntos = max(0.0, puntos - 30)
    reglas = ((not propia or coincide_marca is True) and mismo_producto and not contradice
              and (not esperadas or coincide_pres is True) and not es_paquete)
    aceptada = puntos >= umbral and reglas
    # Dudoso (lo decide la IA): mismo nombre sin marca segura, o marca y presentación iguales con nombre
    # distinto (Google a veces omite «Clásico» u otra palabra del nombre: «Demograss 90 cápsulas»)
    misma_marca_y_pres = coincide_marca is True and coincide_pres is True and not faltan
    dudosa = not aceptada and not contradice and not es_paquete and (
        (coincide_marca is not False and mismo_producto) or misma_marca_y_pres)
    motivos = [f"calificación {puntos:.0f}", f"nombre {nombre:.0f}",
               "marca coincide" if coincide_marca else "marca distinta" if coincide_marca is False else "marca no comprobada"]
    if faltan or sin_palabra:
        motivos.append("el título no trae " + ", ".join(f"«{p.upper()}»" for p in [*faltan, *sin_palabra]))
    if contradice:
        motivos.append(f"presentación distinta ({_pres(esperadas)} contra {_pres(encontradas)})")
    elif coincide_pres:
        motivos.append("presentación coincide")
    elif esperadas:
        motivos.append("presentación no comprobada")
    if es_paquete:
        motivos.append(es_paquete)
    return Evaluacion(puntos, coincide_marca, coincide_pres, contradice, nombre, aceptada, dudosa, "; ".join(motivos), mismo_producto,
                      bool(es_paquete))


def paquete(descripcion: str | None, titulo: str | None) -> str | None:
    """Motivo si el título parece un paquete o kit que nuestra descripción no es; None si no."""
    if not titulo:
        return None
    nuestras = set(normalizar(descripcion).split())
    suyas = normalizar(titulo).split()
    palabras = sorted({p for p in suyas if p in PAQUETE} - nuestras)
    if palabras:
        return f"parece paquete o kit («{palabras[0]}»)"
    # «+» solo delata un kit si antes ya viene un producto completo con su tamaño («Proteína 510g + Creatina»);
    # «Citrato + Cloruro + Glicinato de Magnesio» es un solo producto (3 Magnesios, 2026-10-20)
    if "+" in titulo and "+" not in (descripcion or "") and presentaciones(titulo.split("+")[0]):
        return "parece paquete o kit («+»)"
    piezas = [float(n.replace(",", ".")) for n, u in re.findall(r"\b(\d+(?:[.,]\d+)?)\s*(piezas|paquetes)\b", normalizar(titulo))]
    cuenta = {float(n.replace(",", ".")) for n, _ in re.findall(
        r"\b(\d+(?:[.,]\d+)?)\s*(capsulas|tabletas|gomitas|softgels|piezas|sobres)\b", normalizar(descripcion))}
    piezas = [n for n in piezas if n not in cuenta]  # «90 piezas» de nuestras 90 gomitas no es paquete (Belabear, 2026-10-20)
    if any(n > 1 for n in piezas) and "piezas" not in nuestras and "paquetes" not in nuestras:
        return "parece paquete de varias piezas"
    # Dos tamaños distintos de la unidad que vendemos: «Creatina 450 g + Proteína 510 g»
    esperadas, encontradas = presentaciones(descripcion), presentaciones(titulo)
    unidades = {u for _, u in esperadas}
    if any(len({n for n, uu in encontradas if uu == u}) > 1 for u in unidades) and len(esperadas) == len(unidades):
        return "parece paquete o kit (trae varios tamaños)"
    return None


def presentacion_distinta(descripcion: str | None, titulo: str | None) -> str | None:
    """Texto del motivo si el título trae otra presentación (510 g contra 34 g); None si no se contradice."""
    esperadas, encontradas = presentaciones(descripcion), presentaciones(titulo)
    por_unidad = lambda conj: {u: {n for n, uu in conj if uu == u} for _, u in conj}  # noqa: E731
    e, a = por_unidad(esperadas), por_unidad(encontradas)
    if any(not e[u] & a[u] for u in set(e) & set(a)):
        return f"otra presentación ({_pres(encontradas)})"
    return None


def _pres(conj: set[tuple[str, str]]) -> str:
    def legible(n: str, u: str) -> str:
        x = float(n)
        if u == "mg" and x >= 1_000_000:
            x, u = x / 1_000_000, "kg"
        elif u == "mg" and x >= 1000:
            x, u = x / 1000, "g"
        return f"{x:g} {u}"
    return ", ".join(legible(n, u) for n, u in sorted(conj)) or "sin dato"


# ---------------------------------------------------------------- decisión

@dataclass
class Candidato:
    clave: str  # product_id de Google Shopping (o data_docid)
    titulo: str
    datos: dict
    estrategias: set[str] = field(default_factory=set)
    evaluacion: Evaluacion | None = None


def candidato_de(item: dict) -> Candidato | None:
    clave = item.get("product_id") or item.get("data_docid") or item.get("gid")
    titulo = item.get("title") or item.get("product_title")
    if not clave or not titulo:
        return None
    return Candidato(str(clave), str(titulo), item)


@dataclass
class Decision:
    elegido: Candidato | None
    estado: str | None  # automatica / None (dudosos o nada)
    motivo: str
    dudosos: list[Candidato]


def decidir(descripcion: str | None, marca: str | None, candidatos: list[Candidato], umbral: float,
            marcas_conocidas: set[str], rechazados: set[str]) -> Decision:
    """Elige sin intervención. Si queda duda, regresa los dudosos para que los revise la IA."""
    vivos = [c for c in candidatos if c.clave not in rechazados]
    for c in vivos:
        ev = evaluar(descripcion, marca, c.titulo, umbral, marcas_conocidas, c.datos.get("rank_absolute"))
        # El mismo producto en las dos búsquedas es evidencia de que es el bueno
        if len(c.estrategias) > 1:
            cal = min(100.0, ev.calificacion + min(15.0, (len(c.estrategias) - 1) * 8.0))
            # Pero no suple palabras que faltan: con la búsqueda sin presentación, el aceite de oliva salía en las
            # dos y se aceptaba por Aceite de Aguacate y de Ajonjolí (corrida 2005)
            aceptada = cal >= umbral and ev.marca is not False and ev.mismo_nombre and not ev.contradice
            ev = replace(ev, calificacion=cal, aceptada=aceptada, dudosa=not aceptada and ev.dudosa,
                         motivo=ev.motivo + "; salió en las dos búsquedas")
        c.evaluacion = ev
    vivos.sort(key=lambda c: c.evaluacion.calificacion, reverse=True)

    # Encontrado por código de barras, con la marca correcta, el mismo nombre y sin presentación contradictoria.
    # El nombre también se exige: Google a veces regresa por el código otro producto de la misma marca
    # (caso de Diego: Birdman Proteína Vegetal Vainilla 510 g)
    por_barras = [c for c in vivos if "codigo_barras" in c.estrategias and c.evaluacion.marca is True
                  and c.evaluacion.mismo_nombre and not c.evaluacion.contradice]
    if por_barras:
        c = por_barras[0]
        return Decision(c, "automatica", "Encontrado por código de barras; " + c.evaluacion.motivo, [])

    aceptados = [c for c in vivos if c.evaluacion.aceptada]
    if aceptados:
        primero = aceptados[0]
        segundo = next((c for c in vivos if c is not primero and (c.evaluacion.aceptada or c.evaluacion.dudosa)), None)
        if not segundo or primero.evaluacion.calificacion - segundo.evaluacion.calificacion >= MARGEN:
            return Decision(primero, "automatica", primero.evaluacion.motivo, [])
    dudosos = [c for c in vivos if c.evaluacion.aceptada or c.evaluacion.dudosa][:3]
    if dudosos:
        return Decision(None, None, "Hay candidatos parecidos; los revisa la IA", dudosos)
    if not vivos:
        return Decision(None, None, "Google Shopping no regresó resultados", [])
    return Decision(None, None, "Ningún resultado es el mismo producto: " + vivos[0].evaluacion.motivo, [])


# ---------------------------------------------------------------- IA

INSTRUCCIONES_IA = """Eres un verificador automático de identidad de productos para retail mexicano (suplementos y naturistas).
Decide si uno de los candidatos (de Google Shopping o del buscador de una tienda) es exactamente el producto solicitado, no solo uno parecido.
Usa solo la evidencia dada. Una marca visible diferente o una presentación distinta (cantidad, tamaño, número de cápsulas) obliga a rechazar.
No elijas por precio, vendedor ni posición. No inventes marca, tamaño ni atributos.
Si hay duda razonable, responde no_match.
Responde solo con este JSON, sin texto adicional:
{"decision": "match" o "no_match", "clave": "<clave del candidato elegido o null>", "confianza": <0 a 100>, "motivo": "<una frase en español>"}"""


def mensaje_ia(descripcion: str | None, marca: str | None, dudosos: list[Candidato], nombre_tienda: str | None = None,
               precio: object = None, busqueda_compras: str | None = None, confirmada: str | None = None) -> str:
    producto = {"descripcion": descripcion, "marca": marca_comercial(marca)}
    if busqueda_compras:
        producto["busqueda_escrita_por_compras"] = busqueda_compras
    if confirmada:
        producto["publicacion_confirmada_por_una_persona"] = confirmada
    if nombre_tienda:
        producto["nombre_en_nuestra_tienda"] = nombre_tienda
    if precio is not None:
        producto["nuestro_precio_mxn"] = str(precio)
    return json.dumps({
        "producto": producto,
        "candidatos": [{"clave": c.clave, "titulo": c.titulo, "vendedor": c.datos.get("seller"),
                        **({"precio": str(c.datos.get("price")), "moneda": c.datos.get("currency")} if precio is not None
                           and c.datos.get("price") is not None else {})} for c in dudosos],
    }, ensure_ascii=False)


INSTRUCCIONES_IA_ELEGIR = """Eres un verificador automático de identidad de productos para retail mexicano (suplementos y naturistas).
Recibes nuestro producto y resultados de Google Shopping que ya pasaron un filtro: son de nuestra marca (o de una marca
desconocida), sin otra presentación y sin kits. Tu trabajo es elegir el que sea nuestro producto.
Nuestra descripción viene del sistema interno y es genérica: casi nunca trae el nombre comercial o la línea con que el
fabricante lo vende (por ejemplo «Fitmingo», «By Ale Rubio»). Que el título de Google traiga un nombre comercial que
nuestra descripción no tiene NO es motivo para rechazarlo. El nombre en nuestra tienda en línea, si viene, sí suele traerlo.
Es el mismo producto si coinciden: la marca, el tipo de producto (proteína vegetal, colágeno, cápsulas de moringa...),
el sabor o variante si lo hay, y la presentación (gramos, mililitros, cápsulas, piezas).
Las variantes o líneas de una marca (Premier, Clásico, Plus, Fem, Lx...) son productos distintos aunque tengan la misma
presentación: nunca pongas en "claves" dos variantes diferentes. Para saber cuál es la nuestra usa, en este orden,
"busqueda_escrita_por_compras", "publicacion_confirmada_por_una_persona" y "nombre_en_nuestra_tienda"; si alguno dice la
variante, un resultado con otra variante es otro producto y uno que no dice variante puede ser el mismo. Si ninguno dice
la variante y los resultados traen variantes distintas, responde no_match.
Si el título de un resultado no dice la presentación, no la des por buena: Google junta varios tamaños en una misma
publicación. Si otro resultado del mismo producto sí trae nuestra presentación en el título, elige ese.
Recházalo solo si el título contradice alguno de esos datos (otro sabor, otro tipo de producto, otra marca, otra cantidad),
si es un kit o paquete, o si el precio es tan distinto del nuestro que parece otra presentación.
Nunca elijas al más barato por serlo. Google suele tener el mismo producto en varias publicaciones (cada una con sus
tiendas): queremos todas, para comparar todos los precios del mercado. En "claves" pon TODAS las que sean el mismo producto;
en "clave" la de título más completo.
Responde solo con este JSON, sin texto adicional:
{"decision": "match" o "no_match", "clave": "<la mejor o null>", "claves": ["<todas las que son el mismo producto>"], "confianza": <0 a 100>, "motivo": "<una frase en español>"}"""


# Líneas o variantes con que las marcas venden el mismo tipo de producto (caso Demograss Premier / clásico, 2026-10-20)
VARIANTES = ("premier", "clasico", "plus", "fem", "lx", "forte", "ultra", "kids")


def variantes(texto: str | None) -> set[str]:
    palabras = set(normalizar(texto).split())
    return {v for v in VARIANTES if v in palabras}


INSTRUCCIONES_IA_IMAGENES = """Eres un verificador de productos para retail mexicano (suplementos y naturistas).
La primera imagen es la foto de NUESTRO producto. Las siguientes son fotos de resultados de Google Shopping, en el mismo
orden que la lista "candidatos" (el campo "imagen" dice qué número de imagen es cada uno).
Las marcas venden varias variantes o líneas con empaques parecidos (Premier, Clásico, Plus, Lx...): fíjate en el texto,
los colores y el diseño del empaque. Di cuáles candidatos muestran exactamente el mismo producto que nuestra foto
(misma variante y mismo empaque). Si una foto no se ve clara o no estás seguro, no la incluyas.
Responde solo con este JSON, sin texto adicional:
{"variante": "<la variante que se lee en nuestro empaque, o null>", "claves": ["<claves de los candidatos que son el mismo producto>"], "motivo": "<una frase en español>"}"""


def cuidar_variante(elegido: Candidato, iguales: list[Candidato], referencias: list[str | None],
                    revisables: list[Candidato]) -> tuple[Candidato | None, list[Candidato], str | None]:
    """Revisa con reglas lo que eligió la IA, porque con modelos chicos la instrucción no basta: nunca junta variantes
    distintas y, si no sabemos cuál es la nuestra y Google trae varias, no adivina. (elegido, iguales, problema)."""
    nuestra = set().union(*(variantes(r) for r in referencias if r))
    if nuestra:
        def sirve(c: Candidato) -> bool:
            return not variantes(c.titulo) or bool(variantes(c.titulo) & nuestra)
        if not sirve(elegido):
            return None, [], (f"La IA eligió «{elegido.titulo}», que es otra variante; la nuestra es "
                              f"{', '.join(sorted(nuestra))}")
        return elegido, [c for c in iguales if sirve(c)], None
    vistas = sorted(set().union(*(variantes(c.titulo) for c in revisables)))
    if len(vistas) >= 2:
        return None, [], (f"Google trae varias variantes ({', '.join(vistas)}) y nuestra descripción no dice cuál es la "
                          "nuestra: elige la correcta en «Lo que regresó Google» o escribe la búsqueda con la variante")
    return elegido, iguales, None


def con_presentacion(revisables: list[Candidato], descripcion: str | None) -> list[Candidato]:
    """Si algún resultado de nuestra marca trae nuestra presentación en el título, la IA elige solo entre los que la traen.
    Google junta todos los tamaños en una publicación sin tamaño («San Lucas · Aceite de Ajonjolí Extra Virgen») y sus
    tiendas venden el de 500 ml; la IA la daba por 250 ml (corrida 2006)."""
    if not presentaciones(descripcion):
        return revisables
    confirman = [c for c in revisables if c.evaluacion and c.evaluacion.presentacion is True]
    return confirman if any(c.evaluacion.marca is True for c in confirman) else revisables


def para_ia(candidatos: list[Candidato], rechazados: set[str], maximo: int = 8, descripcion: str | None = None) -> list[Candidato]:
    """Lo que revisa la IA cuando elige siempre: sin otra marca, otra presentación ni paquetes, de mejor a peor.
    Con la descripción, solo los que traen nuestra presentación cuando los hay (con_presentacion)."""
    vivos = [c for c in candidatos if c.clave not in rechazados and pasa_reglas(c)]
    if descripcion:
        vivos = con_presentacion(vivos, descripcion)
    return sorted(vivos, key=lambda c: c.evaluacion.calificacion, reverse=True)[:maximo]


def _json_ia(texto: str) -> dict:
    t = texto.strip()
    if "```" in t:
        t = re.sub(r"^```(?:json)?|```$", "", t.strip(), flags=re.MULTILINE).strip()
    inicio, fin = t.find("{"), t.rfind("}")
    return json.loads(t[inicio:fin + 1]) if inicio >= 0 and fin > inicio else {}


def pasa_reglas(c: Candidato) -> bool:
    """Lo que la IA no puede saltarse: otra marca, otra presentación o un paquete."""
    ev = c.evaluacion
    return bool(ev) and ev.marca is not False and not ev.contradice and not ev.es_paquete


def iguales_ia(texto: str, revisables: list[Candidato], elegido: Candidato) -> list[Candidato]:
    """Las otras publicaciones que la IA marcó como el mismo producto (en "claves"), si pasan las reglas."""
    try:
        claves = _json_ia(texto).get("claves") or []
    except ValueError:
        return []
    claves = {str(k) for k in claves} if isinstance(claves, list) else set()
    return [c for c in revisables if c.clave in claves and c is not elegido and pasa_reglas(c)]


def leer_respuesta_ia(texto: str, dudosos: list[Candidato]) -> tuple[Candidato | None, float, str]:
    """(candidato elegido o None, confianza, motivo). Las reglas duras siguen mandando sobre la IA."""
    datos = _json_ia(texto)
    confianza = float(datos.get("confianza") or 0)
    motivo = str(datos.get("motivo") or "")[:300]
    if datos.get("decision") != "match":
        return None, confianza, motivo or "La IA dijo que ninguno es el mismo producto"
    elegido = next((c for c in dudosos if c.clave == str(datos.get("clave"))), None)
    if not elegido or elegido.evaluacion.marca is False or elegido.evaluacion.contradice:
        return None, confianza, "La IA eligió un candidato que no pasa las reglas de marca y presentación"
    if confianza < CONFIANZA_IA:
        return None, confianza, f"La IA no quedó segura ({confianza:.0f} de 100): {motivo}"
    return elegido, confianza, motivo
