"""Ficha técnica estándar de un producto (migración 0047).

Una ficha con campos fijos para comparar ficha contra ficha: tipo, forma, contenido neto y unidad, piezas, porciones,
ingrediente principal y gramos por porción, otros ingredientes, sabor, variante, uso declarado y registro sanitario.

Cómo se llena (plan del radar inteligente con IA local, aprobado por Diego el 2026-11-17):
1. Reglas del código: contenido, piezas, forma, porciones y registro sanitario salen del texto con expresiones fijas.
2. La IA local (Ollama, tarea `datos.fichas`, nunca la API externa) lee el texto (o la foto de la etiqueta) y propone
   los demás campos, cada uno con el pedazo de texto que lo prueba. Un campo solo se acepta si ese pedazo está de
   verdad en el texto; si no, queda vacío. Nada se inventa.
3. Lo que dicen las reglas gana sobre la IA en números (contenido, piezas, porciones).
4. Sin tipo ni contenido la ficha queda «dudosa» y se vuelve a intentar otra noche; no cuenta para comparar.
5. Nadie aprueba fichas: Compras solo puede marcarla «Está mal» con motivo; desde ese momento deja de usarse y la
   siguiente lectura recibe el motivo.

Aquí viven también las reglas de tamaño y formato (antes en el radar de productos) para que las usen el radar de
productos, el reporte y el radar de precios.
"""
import base64
import hashlib
import json
import logging
import math
import re
import struct
import threading
import unicodedata
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session

from datos.modelos import IdeaFicha, Producto, ProductoFicha, ProductoFuente, ProductoHuella
from ia import puerta
from nucleo.modelos import ahora

log = logging.getLogger(__name__)

TAREA = "datos.fichas"


def _norm(texto: str | None) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


# ---------------------------------------------------------------- reglas de tamaño y formato

UNIDADES = {"kg": ("g", 1000), "kilo": ("g", 1000), "kilos": ("g", 1000), "g": ("g", 1), "gr": ("g", 1),
            "grs": ("g", 1), "gramos": ("g", 1), "l": ("ml", 1000), "lt": ("ml", 1000), "lts": ("ml", 1000),
            "litro": ("ml", 1000), "litros": ("ml", 1000), "ml": ("ml", 1), "mililitros": ("ml", 1),
            "m": ("m", 1), "metros": ("m", 1)}
UNIDADES.update({u: ("pz", 1) for u in (
    "cap", "caps", "capsula", "capsulas", "softgel", "softgels", "tab", "tabs", "tableta", "tabletas", "comprimidos",
    "sob", "sobre", "sobres", "pz", "pza", "pzas", "pzs", "pieza", "piezas", "tiras", "varitas", "toallitas",
    "gomita", "gomitas", "gomas", "perlas", "grageas", "pastillas")})
_CAPSULAS = {"cap", "caps", "capsula", "capsulas", "softgel", "softgels", "perlas"}  # ninguna pesa 3 g o más
NOMBRE_UNIDAD = {"g": "gramo", "ml": "mililitro", "pz": "pieza", "m": "metro"}
_TAMANO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(" + "|".join(sorted(UNIDADES, key=len, reverse=True)) + r")\b")


def tamano(*textos: str | None) -> dict[str, Decimal]:
    """Tamaño de la presentación por unidad: {"g": 120} para «120 g», {"pz": 15, "g": 79.5} para «15 tabletas de
    5.3 g c/u». Toma el primer texto que diga algo (el contenido antes que el nombre). Los mg no cuentan: son dosis."""
    for texto in textos:
        t = _norm(texto)
        salida: dict[str, Decimal] = {}
        unidad_pz = None
        for numero, unidad in _TAMANO.findall(t):
            dim, factor = UNIDADES[unidad]
            if dim == "pz" and "pz" not in salida:
                unidad_pz = unidad
            cantidad = Decimal(numero.replace(",", ".")) * factor
            if cantidad > 0 and dim not in salida:
                salida[dim] = cantidad
        cada = "c/u" in t or " cada" in t or re.search(r"\d\s*[a-z]+\s+(?:de|con|x)\s+\d", t)
        if "pz" in salida and cada:  # 15 tabletas de 5.3 g c/u = 79.5 g; 8 piezas de 100 g = 800 g
            if unidad_pz in _CAPSULAS and salida.get("g", 0) >= 3:
                salida.pop("g")  # «30 cápsulas de 346 g» es un error de captura (eran mg): solo cuentan las piezas
            for dim in ("g", "ml"):
                if dim in salida:
                    salida[dim] *= salida["pz"]
        if salida:
            return salida
    return {}



_FORMATOS = (
    ("sobre", {"sobre", "sobres", "sob", "stick", "sticks", "sachet", "sachets"}),
    ("capsula", {"cap", "caps", "capsula", "capsulas", "softgel", "softgels", "perlas"}),
    ("tableta", {"tab", "tabs", "tableta", "tabletas", "comprimidos", "grageas", "pastillas", "efervescentes"}),
    ("gomita", {"gomita", "gomitas", "gomas"}),
    ("polvo", {"polvo"}),
    ("liquido", {"liquido", "jarabe", "gotas", "bebida", "shot", "shots"}),
    # 24 nov 2026 (plan de clasificación automática): una crema de colágeno no es un colágeno en polvo
    ("crema", {"crema", "cremas", "gel", "unguento", "pomada", "locion", "balsamo", "serum", "roll", "mascarilla"}),
)
GRUPO_FORMATO = {"sobre": "polvo", "polvo": "polvo", "capsula": "solido", "tableta": "solido", "gomita": "gomita",
                 "liquido": "liquido", "crema": "topico"}
NOMBRE_FORMATO = {"sobre": "sobre", "polvo": "polvo", "capsula": "cápsulas", "tableta": "tabletas", "gomita": "gomitas",
                  "liquido": "líquido", "crema": "crema"}


# v0.5.4: para comparar contra la v0.5.3 sin adivinar (pedido de Diego, 24 nov 2026), el examen y la comparación corren
# también «como la v0.5.3». En la operación normal siempre es False.
COMO_V053: ContextVar[bool] = ContextVar("como_v053", default=False)


def formato(*textos: str | None) -> str | None:
    """sobre, polvo, cápsula, tableta, gomita o líquido; el primer texto que lo diga (por palabra o, si no, por la
    unidad: solo mililitros es líquido y solo gramos es polvo)."""
    for texto in textos:
        if not texto:
            continue
        ps = set(re.findall(r"[a-zñ]+", _norm(texto)))
        for nombre, claves in _FORMATOS:
            if nombre == "crema" and COMO_V053.get():
                continue  # la v0.5.3 no conocía la forma «crema»
            if ps & claves:
                return nombre
        tam = tamano(texto)
        if set(tam) == {"ml"}:
            return "liquido"
        if set(tam) == {"g"}:
            return "polvo"
    return None




# ---------------------------------------------------------------- la ficha

TEXTO = ("tipo", "forma", "ingrediente_principal", "otros_ingredientes", "sabor", "variante", "uso",
         "registro_sanitario")
NUMEROS = ("contenido_cantidad", "piezas", "porciones", "activo_g_porcion")
NOMBRES_CAMPO = {
    "tipo": "Tipo de producto", "forma": "Forma", "contenido": "Contenido", "piezas": "Piezas", "porciones": "Porciones",
    "ingrediente_principal": "Ingrediente principal", "activo_g_porcion": "Ingrediente principal por porción",
    "otros_ingredientes": "Otros ingredientes", "sabor": "Sabor", "variante": "Variante", "uso": "Uso que declara",
    "registro_sanitario": "Registro sanitario", "iva_pct": "IVA"}
LARGOS = {"tipo": 120, "forma": 40, "ingrediente_principal": 200, "otros_ingredientes": 500, "sabor": 80,
          "variante": 80, "uso": 300, "registro_sanitario": 60}


@dataclass
class Ficha:
    tipo: str | None = None
    forma: str | None = None
    contenido_cantidad: Decimal | None = None
    contenido_unidad: str | None = None
    piezas: int | None = None
    porciones: int | None = None
    ingrediente_principal: str | None = None
    activo_g_porcion: Decimal | None = None
    otros_ingredientes: str | None = None
    sabor: str | None = None
    variante: str | None = None
    uso: str | None = None
    registro_sanitario: str | None = None
    iva_pct: Decimal | None = None
    origenes: dict[str, str] = field(default_factory=dict)
    citas: dict[str, str] = field(default_factory=dict)

    @property
    def util(self) -> bool:
        """Sirve para comparar: dice qué es o cuánto trae."""
        return bool(self.tipo or self.contenido_cantidad)

    def contenido_texto(self) -> str | None:
        if not self.contenido_cantidad or not self.contenido_unidad:
            return None
        n = self.contenido_cantidad.normalize()
        return f"{n:f} {ETIQUETA_UNIDAD.get(self.contenido_unidad, self.contenido_unidad)}"

    def tamano(self) -> dict[str, Decimal]:
        """Igual que `tamano()`: {"g": 300} o {"pz": 60}, con piezas aparte si hay contenido en peso o volumen."""
        salida: dict[str, Decimal] = {}
        if self.contenido_cantidad and self.contenido_unidad:
            salida[self.contenido_unidad] = Decimal(self.contenido_cantidad)
        if self.piezas and "pz" not in salida:
            salida["pz"] = Decimal(self.piezas)
        return salida

    def activo_total_g(self) -> Decimal | None:
        if self.activo_g_porcion and self.porciones:
            return Decimal(self.activo_g_porcion) * self.porciones
        return None

    def para_ia(self) -> dict:
        """Campos con valor, en palabras, para dárselos a otra tarea de IA."""
        d = {NOMBRES_CAMPO[c]: getattr(self, c) for c in TEXTO if getattr(self, c)}
        if t := self.contenido_texto():
            d["Contenido"] = t
        for c in ("piezas", "porciones"):
            if getattr(self, c):
                d[NOMBRES_CAMPO[c]] = getattr(self, c)
        if self.activo_g_porcion:
            d[NOMBRES_CAMPO["activo_g_porcion"]] = f"{Decimal(self.activo_g_porcion).normalize():f} g"
        return d


ETIQUETA_UNIDAD = {"g": "g", "ml": "ml", "pz": "piezas", "m": "m"}
_REGISTRO = re.compile(r"\b(\d{2,4}\s?[a-z]\s?\d{4}\s?ssa(?:\s?[ivx0-9]{1,4})?)\b")
_PORCIONES = re.compile(r"(\d{1,4})\s*(?:porciones|servicios|tomas|raciones)\b")


def reglas(*textos: str | None) -> Ficha:
    """Lo que el código sabe leer solo, sin IA."""
    f = Ficha()
    tam = tamano(*textos)
    for dim in ("g", "ml", "m"):
        if dim in tam:
            f.contenido_cantidad, f.contenido_unidad = tam[dim], dim
            break
    if "pz" in tam:
        f.piezas = int(tam["pz"])
        if not f.contenido_cantidad:
            f.contenido_cantidad, f.contenido_unidad = tam["pz"], "pz"
    if f.contenido_cantidad:
        f.origenes["contenido"] = "reglas"
    if forma := formato(*textos):
        f.forma, f.origenes["forma"] = NOMBRE_FORMATO[forma], "reglas"
    todo = " ".join(_norm(t) for t in textos if t)
    if m := _PORCIONES.search(todo):
        f.porciones, f.origenes["porciones"], f.citas["porciones"] = int(m.group(1)), "reglas", m.group(0)
    if m := _REGISTRO.search(todo):
        f.registro_sanitario, f.origenes["registro_sanitario"] = m.group(1).upper(), "reglas"
    return f


# ---------------------------------------------------------------- IA local

INSTRUCCIONES = """Eres capturista de fichas técnicas de una cadena de tiendas naturistas en México.
Te doy el texto de un producto. Llena su ficha SOLO con lo que el texto dice. Para cada campo que llenes copia en
"cita" el pedazo EXACTO del texto que lo prueba (de 2 a 12 palabras, tal cual, sin cambiar letras). Si el texto no lo
dice, no pongas el campo. No adivines, no completes con lo que sabes del producto.
Campos:
- tipo: qué es, en pocas palabras genéricas y sin marca (ej. "proteína en polvo", "shampoo", "cinta kinesiológica",
  "té de hierbas", "orégano seco para cocinar", "suplemento de magnesio").
- forma: cápsulas, tabletas, softgels, gomitas, polvo, sobres, gotas, jarabe, líquido, crema, gel, barra, sólido, aceite.
- contenido_cantidad y contenido_unidad: contenido neto del envase; unidad g, ml, pz o m (kg y l conviértelos).
- piezas: cápsulas, tabletas, sobres o piezas por envase. porciones: porciones por envase.
- ingrediente_principal y activo_g_porcion: el activo principal y sus gramos por porción (mg entre 1000).
- otros_ingredientes, sabor, variante (Plus, Premier, Clásico, Kids, Sport…), uso (lo que dice que hace, como lo dice),
  registro_sanitario.
Contesta SOLO un JSON así: {"tipo": {"valor": "...", "cita": "..."}, "contenido_cantidad": {"valor": 300,
"cita": "..."}, ...}"""

INSTRUCCIONES_FOTO = """Eres capturista de fichas técnicas de una cadena de tiendas naturistas en México.
Te doy la foto de un producto. Primero copia en "etiqueta" todo el texto que se lee en la foto, tal cual. Después
llena la ficha SOLO con lo que copiaste, cada campo con "cita" = pedazo exacto de lo que copiaste.
""" + INSTRUCCIONES.split("\n", 2)[2].replace(
    'Contesta SOLO un JSON así: {', 'Contesta SOLO un JSON así: {"etiqueta": "texto leído", ')


def _limpio(texto: str) -> str:
    return re.sub(r"[^a-z0-9ñ.,%/]+", " ", _norm(texto)).strip()


def _numero(v) -> Decimal | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        n = Decimal(str(v).replace(",", "."))
    except InvalidOperation:
        return None
    return n if n > 0 else None


def _en_cita(n: Decimal, cita: str) -> bool:
    """El número (o su equivalente en mil: 1 kg = 1000 g, 500 mg = 0.5 g) aparece en la cita."""
    nums = {Decimal(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", cita)}
    return any(n == x or n == x * 1000 or n * 1000 == x for x in nums)


def leer_ia(bd: Session, texto: str, foto: bytes | None = None, aviso: str | None = None) -> tuple[Ficha, str | None]:
    """La IA local propone la ficha. Solo quedan los campos cuya cita está de verdad en el texto (o en lo que la IA
    copió de la foto). Devuelve (ficha, error)."""
    instrucciones = INSTRUCCIONES_FOTO if foto else INSTRUCCIONES
    mensaje = (f"Texto del producto:\n{texto[:3000]}" if not foto else
               f"Texto que ya tenemos (puede faltar algo):\n{texto[:1500]}")
    if aviso:
        mensaje += f"\n\nOjo: una persona marcó la ficha anterior como mal hecha por esto: {aviso[:300]}"
    try:
        r = puerta.ejecutar(bd, TAREA, usuario_id=None, instrucciones=instrucciones, mensaje=mensaje,
                            max_tokens=900 if foto else 600, esfuerzo="low",
                            contexto=puerta.ventana(instrucciones, mensaje, salida=900),
                            **({"imagenes": [base64.b64encode(foto).decode()]} if foto else {}))
        datos = json.loads(r.texto[r.texto.find("{"):r.texto.rfind("}") + 1])
    except (puerta.ErrorIA, ValueError, AttributeError) as e:
        return Ficha(), f"La IA local no pudo leer el producto: {str(e)[:200]}"
    if not isinstance(datos, dict):
        return Ficha(), "La IA local no contestó una ficha."
    base = _limpio(texto + " " + (str(datos.get("etiqueta") or "") if foto else ""))
    origen = "foto" if foto else "texto"
    f = Ficha()
    for campo in (*TEXTO, *NUMEROS, "contenido_unidad"):
        x = datos.get(campo)
        if not isinstance(x, dict):
            continue
        valor, cita = x.get("valor"), str(x.get("cita") or "").strip()
        if valor in (None, "") or len(cita) < 2 or _limpio(cita) not in base:
            continue
        if campo in TEXTO:
            setattr(f, campo, str(valor).strip()[:LARGOS[campo]])
        elif campo == "contenido_unidad":
            u = str(valor).strip().lower()
            if u in ("kg", "l"):
                u = {"kg": "g", "l": "ml"}[u]
            if u in ("g", "ml", "pz", "m"):
                f.contenido_unidad = u
            continue
        else:
            n = _numero(valor)
            if n is None or not _en_cita(n, cita):
                continue
            if campo in ("piezas", "porciones"):
                if n != n.to_integral_value() or n > 10000:
                    continue
                n = int(n)
            setattr(f, campo, n)
        f.origenes["contenido" if campo == "contenido_cantidad" else campo] = origen
        f.citas["contenido" if campo == "contenido_cantidad" else campo] = cita[:200]
    if f.contenido_cantidad and not f.contenido_unidad:
        f.contenido_cantidad = None
        f.origenes.pop("contenido", None)
        f.citas.pop("contenido", None)
    return f, None


def juntar(de_reglas: Ficha, de_ia: Ficha) -> Ficha:
    """Las reglas ganan en números; la IA llena lo que las reglas no saben."""
    f = Ficha(origenes=dict(de_ia.origenes), citas=dict(de_ia.citas))
    for campo in (*TEXTO, *NUMEROS, "contenido_unidad", "iva_pct"):
        setattr(f, campo, getattr(de_ia, campo))
    for campo in ("contenido_cantidad", "contenido_unidad", "piezas", "porciones", "forma", "registro_sanitario"):
        if getattr(de_reglas, campo) is not None:
            setattr(f, campo, getattr(de_reglas, campo))
    f.origenes.update(de_reglas.origenes)
    for c in de_reglas.origenes:
        if c in de_reglas.citas:
            f.citas[c] = de_reglas.citas[c]
        else:
            f.citas.pop(c, None)
    return f


def extraer(bd: Session | None, texto: str, foto: bytes | None = None, *, con_ia: bool = True,
            aviso: str | None = None) -> tuple[Ficha, str | None]:
    """Ficha de un texto (y, si hay, la foto de la etiqueta): reglas + IA local. Devuelve (ficha, nota)."""
    f = reglas(texto)
    nota = None
    if con_ia and bd is not None:
        ia, nota = leer_ia(bd, texto, aviso=aviso)
        f = juntar(f, ia)
        if foto and not (f.tipo and f.contenido_cantidad):
            ia_foto, nota_foto = leer_ia(bd, texto, foto, aviso=aviso)
            for campo in (*TEXTO, *NUMEROS, "contenido_unidad"):
                if getattr(f, campo) is None and getattr(ia_foto, campo) is not None:
                    setattr(f, campo, getattr(ia_foto, campo))
                    clave = "contenido" if campo in ("contenido_cantidad", "contenido_unidad") else campo
                    f.origenes[clave] = "foto"
                    if clave in ia_foto.citas:
                        f.citas[clave] = ia_foto.citas[clave]
            nota = nota or nota_foto
    return f, nota


def precio_por_unidad(precio: Decimal | None, ficha: "Ficha | None") -> tuple[Decimal, str] | None:
    """Precio por gramo, mililitro, pieza o metro con la ficha (para el radar de precios y el de productos)."""
    if not precio or ficha is None or not ficha.contenido_cantidad or not ficha.contenido_unidad:
        return None
    return Decimal(precio) / Decimal(ficha.contenido_cantidad), ficha.contenido_unidad


# ---------------------------------------------------------------- guardar y leer

def _huella(texto: str, foto: bytes | None = None) -> str:
    h = hashlib.sha256(_norm(texto).encode())
    if foto:
        h.update(hashlib.sha256(foto).digest())
    return h.hexdigest()


def a_ficha(fila: ProductoFicha | IdeaFicha | None) -> Ficha | None:
    """La ficha guardada, si se puede usar (no está dudosa, fallida ni marcada «Está mal»)."""
    if fila is None or fila.estado != "lista":
        return None
    f = Ficha(**{c: getattr(fila, c) for c in (*TEXTO, *NUMEROS, "contenido_unidad", "iva_pct")})
    f.origenes = json.loads(fila.origenes or "{}")
    f.citas = json.loads(fila.citas or "{}")
    return f


def _guardar(fila: ProductoFicha | IdeaFicha, f: Ficha, huella: str, nota: str | None, con_ia: bool) -> None:
    for c in (*TEXTO, *NUMEROS, "contenido_unidad", "iva_pct"):
        setattr(fila, c, getattr(f, c))
    fila.origenes = json.dumps(f.origenes, ensure_ascii=False)
    fila.citas = json.dumps(f.citas, ensure_ascii=False)
    fila.huella, fila.nota, fila.con_ia = huella, (nota or None) and nota[:500], con_ia
    fila.intentos = (fila.intentos or 0) + 1
    fila.estado = "lista" if f.util else "dudosa"
    fila.mal_motivo = fila.mal_por = fila.mal_en = None
    fila.extraida_en = ahora()


def texto_producto(bd: Session, p: Producto) -> str:
    """Lo que sabemos de un producto del catálogo: descripción, marca, clasificación y lo que dice la tienda."""
    partes = [p.descripcion, p.marca and f"Marca: {p.marca}", p.subcategoria and f"Subcategoría: {p.subcategoria}",
              p.segmento and f"Segmento: {p.segmento}"]
    for fuente in bd.scalars(select(ProductoFuente).where(ProductoFuente.producto_id == p.producto_id,
                                                          ProductoFuente.fuente == "TIENDA")):
        try:
            d = json.loads(fuente.datos)
        except ValueError:
            continue
        if isinstance(d, dict):
            partes += [d.get("titulo"), d.get("variante") not in (None, "Default Title") and d.get("variante"),
                       d.get("tipo") and f"Tipo en la tienda: {d['tipo']}"]
    return "\n".join(str(x) for x in partes if x)


def de_producto(bd: Session, p: Producto, *, con_ia: bool = True, forzar: bool = False) -> Ficha | None:
    """Ficha del producto del catálogo; la lee si no existe o si cambió su texto. Una ficha marcada «Está mal» no se
    usa hasta volver a leerse (lo hace el lote nocturno o `forzar`)."""
    texto = texto_producto(bd, p)
    huella = _huella(texto)
    fila = bd.get(ProductoFicha, p.producto_id)
    if fila and fila.huella == huella and not forzar and (fila.estado != "dudosa" or not con_ia):
        return a_ficha(fila)
    if fila is None:
        fila = ProductoFicha(producto_id=p.producto_id)
        bd.add(fila)
    aviso = fila.mal_motivo
    f, nota = extraer(bd, texto, con_ia=con_ia, aviso=aviso)
    if p.iva_pct is not None:
        f.iva_pct, f.origenes["iva_pct"] = p.iva_pct, "catalogo"
    _guardar(fila, f, huella, nota, con_ia)
    bd.flush()
    return a_ficha(fila)


def de_idea(bd: Session, origen: str, origen_id: int, texto: str, foto: bytes | None = None, *,
            con_ia: bool = True) -> Ficha | None:
    """Ficha de una idea o propuesta; se rehace si cambió lo capturado o si la marcaron «Está mal»."""
    huella = _huella(texto, foto)
    fila = bd.scalar(select(IdeaFicha).where(IdeaFicha.origen == origen, IdeaFicha.origen_id == origen_id))
    if fila and fila.huella == huella and fila.estado in ("lista", "dudosa") and (fila.estado == "lista" or not con_ia):
        return a_ficha(fila)
    if fila is None:
        fila = IdeaFicha(origen=origen, origen_id=origen_id)
        bd.add(fila)
    f, nota = extraer(bd, texto, foto, con_ia=con_ia, aviso=fila.mal_motivo)
    _guardar(fila, f, huella, nota, con_ia)
    bd.flush()
    return a_ficha(fila)


def _listas(bd: Session, producto_ids: list[int]) -> list[ProductoFicha]:
    """Fichas usables de esos productos. En tandas de 1,000: SQL Server no acepta más de 2,100 valores por consulta
    (con todo el catálogo, 5,795, tronaba con «COUNT field incorrect»)."""
    ids = list(dict.fromkeys(producto_ids))
    filas: list[ProductoFicha] = []
    for i in range(0, len(ids), 1000):
        filas += bd.scalars(select(ProductoFicha).where(ProductoFicha.producto_id.in_(ids[i:i + 1000]),
                                                        ProductoFicha.estado == "lista"))
    return filas


def tamanos(bd: Session, producto_ids: list[int]) -> dict[int, dict[str, Decimal]]:
    """Tamaño de cada producto según su ficha (solo las que se pueden usar), para comparar ficha contra ficha."""
    return {f.producto_id: t for f in _listas(bd, producto_ids) if (t := a_ficha(f).tamano())}


def de_productos(bd: Session, producto_ids: list[int]) -> dict[int, Ficha]:
    return {f.producto_id: a_ficha(f) for f in _listas(bd, producto_ids)}


def marcar_mal(bd: Session, fila: ProductoFicha | IdeaFicha, motivo: str, usuario_id: int) -> None:
    """«Está mal»: deja de usarse al momento y la siguiente lectura recibe el motivo."""
    fila.estado, fila.mal_motivo, fila.mal_por, fila.mal_en = "mal", motivo.strip()[:500], usuario_id, ahora()
    fila.huella = None  # para que se vuelva a leer


def salida(fila: ProductoFicha | IdeaFicha | None) -> dict | None:
    """Para la pantalla: cada campo con su valor, de dónde salió y su cita."""
    if fila is None:
        return None
    origenes, citas = json.loads(fila.origenes or "{}"), json.loads(fila.citas or "{}")
    f = Ficha(**{c: getattr(fila, c) for c in (*TEXTO, *NUMEROS, "contenido_unidad", "iva_pct")})
    campos = []
    for clave, valor in (("tipo", f.tipo), ("forma", f.forma), ("contenido", f.contenido_texto()),
                         ("piezas", f.piezas), ("porciones", f.porciones),
                         ("ingrediente_principal", f.ingrediente_principal),
                         ("activo_g_porcion", f.activo_g_porcion and f"{Decimal(f.activo_g_porcion).normalize():f} g"),
                         ("sabor", f.sabor), ("variante", f.variante), ("uso", f.uso),
                         ("otros_ingredientes", f.otros_ingredientes), ("registro_sanitario", f.registro_sanitario),
                         ("iva_pct", f.iva_pct is not None and f"{Decimal(f.iva_pct).normalize():f} %" or None)):
        campos.append({"campo": clave, "nombre": NOMBRES_CAMPO[clave], "valor": None if valor is None else str(valor),
                       "origen": origenes.get(clave), "cita": citas.get(clave)})
    return {"estado": fila.estado, "nota": fila.nota, "extraida_en": fila.extraida_en, "con_ia": fila.con_ia,
            "mal_motivo": fila.mal_motivo, "mal_en": fila.mal_en, "campos": campos}


# ---------------------------------------------------------------- sustitutos por función (bge-m3)

TAREA_HUELLA = "datos.fichas_huella"
MIN_FUNCION = 0.6  # parecido de significado mínimo para proponer un sustituto
_INDICE: dict = {}
_INDICE_LOCK = threading.Lock()


def texto_funcion(f: Ficha | None) -> str | None:
    """Qué es y para qué sirve, sin marca ni tamaño: es lo que se compara para encontrar sustitutos."""
    if f is None or not (f.tipo or f.uso):
        return None
    return ". ".join(x for x in (f.tipo, f.uso, f.ingrediente_principal, f.forma) if x)[:600]


def _empacar(v: list[float]) -> bytes:
    norma = math.sqrt(sum(x * x for x in v)) or 1.0
    return struct.pack(f"{len(v)}f", *(x / norma for x in v))


def _desempacar(b: bytes) -> tuple[float, ...]:
    return struct.unpack(f"{len(b) // 4}f", b)


def huellas_pendientes(bd: Session, limite: int = 200) -> list[tuple[int, str]]:
    """(producto_id, texto) de las fichas que todavía no tienen huella o cuyo texto cambió."""
    filas = bd.execute(select(ProductoFicha, ProductoHuella.huella_texto)
                       .outerjoin(ProductoHuella, ProductoHuella.producto_id == ProductoFicha.producto_id)
                       .where(ProductoFicha.estado == "lista",
                              or_(ProductoFicha.tipo.is_not(None), ProductoFicha.uso.is_not(None)))).all()
    salida = []
    for fila, previa in filas:
        texto = texto_funcion(a_ficha(fila))
        if texto and hashlib.sha256(texto.encode()).hexdigest() != previa:
            salida.append((fila.producto_id, texto))
            if len(salida) >= limite:
                break
    return salida


def calcular_huellas(bd: Session, limite: int = 500) -> int:
    """Calcula la huella de significado de las fichas que la necesitan, en tandas de 32. Si Ollama no tiene el modelo
    de huella, no hace nada (se reintenta la noche siguiente)."""
    hechas = 0
    for _ in range(0, limite, 32):
        tanda = huellas_pendientes(bd, 32)
        if not tanda:
            break
        try:
            modelo, vectores = puerta.vectores(bd, TAREA_HUELLA, [t for _, t in tanda])
        except puerta.ErrorIA as e:
            log.info("Huellas de fichas: %s", e)
            break
        for (pid, texto), v in zip(tanda, vectores):
            h = bd.get(ProductoHuella, pid) or ProductoHuella(producto_id=pid)
            h.modelo, h.vector, h.calculada_en = modelo, _empacar(v), ahora()
            h.huella_texto = hashlib.sha256(texto.encode()).hexdigest()
            bd.merge(h)
        bd.commit()
        hechas += len(tanda)
    _INDICE.clear()
    return hechas


def _indice(bd: Session) -> dict:
    with _INDICE_LOCK:
        if not _INDICE or (ahora() - _INDICE["cargado_en"]).total_seconds() > 600:
            filas = bd.execute(select(ProductoHuella.producto_id, ProductoHuella.modelo, ProductoHuella.vector)).all()
            _INDICE.clear()
            _INDICE.update(cargado_en=ahora(), filas=[(pid, m, _desempacar(v)) for pid, m, v in filas])
        return _INDICE


def cercanos_por_funcion(bd: Session, ficha: Ficha | None, k: int = 20, minimo: float = MIN_FUNCION
                         ) -> list[tuple[int, float]]:
    """Productos del catálogo que hacen lo mismo según el significado de su ficha (aunque no compartan palabras):
    [(producto_id, parecido 0–1)], del más parecido al menos. Vacío si no hay ficha, huellas u Ollama."""
    texto = texto_funcion(ficha)
    if not texto:
        return []
    indice = _indice(bd)
    if not indice["filas"]:
        return []
    try:
        modelo, vectores = puerta.vectores(bd, TAREA_HUELLA, [texto])
    except puerta.ErrorIA as e:
        log.info("Sustitutos por función: %s", e)
        return []
    q = _desempacar(_empacar(vectores[0]))
    salida = [(pid, sum(a * b for a, b in zip(q, v))) for pid, m, v in indice["filas"] if m == modelo and len(v) == len(q)]
    salida = [(pid, c) for pid, c in salida if c >= minimo]
    salida.sort(key=lambda x: -x[1])
    return salida[:k]


# ---------------------------------------------------------------- lote nocturno del catálogo

ZONA = ZoneInfo("America/Mexico_City")
HORA_INICIO, HORA_FIN = 22, 6  # de noche, para no quitarle Ollama a nadie de día
_corriendo = threading.Event()
AVANCE: dict = {}


def pendientes(bd: Session, limite: int = 200) -> list[int]:
    """Productos activos sin ficha, con ficha vieja (el producto cambió), marcada «Está mal» o dudosa (máximo 3
    intentos, uno por noche)."""
    hace_un_dia = ahora() - timedelta(hours=20)
    sin = select(Producto.producto_id).outerjoin(ProductoFicha, ProductoFicha.producto_id == Producto.producto_id).where(
        Producto.activo == true(),
        or_(ProductoFicha.producto_id.is_(None),
            ProductoFicha.estado == "mal",
            ProductoFicha.extraida_en < Producto.actualizado_en,
            (ProductoFicha.estado.in_(("dudosa", "fallida"))) & (ProductoFicha.intentos < 3)
            & (ProductoFicha.extraida_en < hace_un_dia))
    ).order_by(Producto.producto_id).limit(limite)
    return list(bd.scalars(sin))


def en_horario(momento: datetime | None = None) -> bool:
    h = (momento or datetime.now(ZONA)).astimezone(ZONA).hour
    return h >= HORA_INICIO or h < HORA_FIN


def lote(bd: Session, hasta: datetime | None = None, limite: int | None = None) -> int:
    """Lee fichas del catálogo una por una hasta acabar, llegar a `hasta` o a `limite`. Devuelve cuántas leyó."""
    hechas = 0
    while True:
        ids = pendientes(bd, 50)
        if not ids:
            break
        for pid in ids:
            if (hasta and datetime.now(ZONA) >= hasta) or (limite is not None and hechas >= limite):
                return hechas
            p = bd.get(Producto, pid)
            try:
                de_producto(bd, p, forzar=True)
                bd.commit()
            except Exception as e:  # noqa: BLE001 - un producto no detiene el lote
                bd.rollback()
                log.warning("Ficha del producto %s: %s", pid, e)
                fila = bd.get(ProductoFicha, pid) or ProductoFicha(producto_id=pid)
                fila.estado, fila.nota = "fallida", str(e)[:500]
                fila.intentos = (fila.intentos or 0) + 1
                fila.extraida_en = ahora()
                bd.merge(fila)
                bd.commit()
            hechas += 1
            AVANCE.update(hechas=hechas, ultimo=pid)
    return hechas


def revisar_programa(bd: Session) -> None:
    """Lo llama el programador cada minuto: de noche, si hay fichas por leer y no corre otra, arranca el lote en su
    propio hilo hasta las 6 de la mañana."""
    if _corriendo.is_set() or not en_horario() or not (pendientes(bd, 1) or huellas_pendientes(bd, 1)):
        return
    ahora_mx = datetime.now(ZONA)
    fin = ahora_mx.replace(hour=HORA_FIN, minute=0, second=0, microsecond=0)
    if fin <= ahora_mx:
        fin += timedelta(days=1)

    def trabajo() -> None:
        from core.bd import _fabrica

        try:
            with _fabrica()() as s:
                AVANCE.clear()
                AVANCE.update(inicio=ahora(), hechas=0)
                n = lote(s, hasta=fin)
                h = calcular_huellas(s, limite=5000) if datetime.now(ZONA) < fin else 0
                log.info("Fichas técnicas: %s leídas y %s huellas esta noche", n, h)
        finally:
            _corriendo.clear()

    _corriendo.set()
    threading.Thread(target=trabajo, daemon=True, name="fichas").start()


def resumen(bd: Session) -> dict:
    from sqlalchemy import func

    filas = dict(bd.execute(select(ProductoFicha.estado, func.count()).group_by(ProductoFicha.estado)).all())
    activos = bd.scalar(select(func.count()).select_from(Producto).where(Producto.activo == true())) or 0
    return {"activos": activos, "por_estado": filas, "corriendo": _corriendo.is_set(), "avance": dict(AVANCE)}

