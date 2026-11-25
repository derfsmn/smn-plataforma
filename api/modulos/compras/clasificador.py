"""Clasificación automática por votación de evidencias (plan aprobado por Diego el 24 nov 2026).

Nadie confirma la subcategoría a mano. Votan, cada una con su peso:

1. El mismo producto (código de barras o mismo nombre y presentación) o el mismo producto en otro sabor o tamaño que ya
   vendemos: deciden solos.
2. Los productos del catálogo con el mismo ingrediente principal en el nombre: cada uno vota 1 si es de la misma forma
   (cápsula con cápsula, gotas con gotas, crema con crema) y la cuarta parte si es de otra.
3. Los 15 productos más parecidos por nombre (sin la marca) y por el significado de su ficha: cada uno vota según qué
   tan cerca está; los de otra forma, la mitad.
4. La IA local solo desempata entre las 2 o 3 finalistas cuando la votación queda dudosa.

Un producto del catálogo cuyos vecinos de su mismo ingrediente y forma están casi todos (80 %) en otra subcategoría se
toma como posible error del catálogo y no vota. Gana la subcategoría con más votos: «segura» con 70 % o más, «dudosa» si
no (entonces los parecidos se buscan en las dos finalistas). Sin ninguna evidencia, «sin evidencia».
"""
from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from datos import fichas as fi
from datos.modelos import Producto
from ia import puerta
from modulos.compras import radar_productos as rp

log = logging.getLogger(__name__)

PESO_INGREDIENTE = 1.0
PESO_INGREDIENTE_OTRA_FORMA = 0.25
PESO_VECINO = 1.0
VECINO_OTRA_FORMA = 0.5
VECINOS = 15
MIN_VECINO = 0.2  # parecido mínimo (0 a 1) para que un vecino vote
MIN_POR_INGREDIENTE = 2  # productos con el ingrediente para que la palabra cuente como ingrediente
SEGURA = 0.7
SOSPECHA_ACUERDO = 0.8
SOSPECHA_MIN = 4  # vecinos de su ingrediente y forma para poder sospechar del catálogo
FINALISTAS = 3
# 25 nov 2026 (examen v0.5.4: 19 fallas en que la más votada era la buena y la IA la cambió): la IA solo desempata entre
# las finalistas que van parejas, con al menos este tanto de los votos de la primera
VENTAJA_IA = 0.75
# «Misma forma, mismo mundo» (25 nov 2026: un extracto de 30 ml caía en «Saborizada», el agua): una subcategoría solo
# entra si tiene productos de la forma del producto (cápsulas, gotas, líquido, polvo, gomitas, crema)
MUNDO_MIN = 0.15  # parte de la subcategoría con esa forma
MUNDO_MIN_N = 3  # o al menos tantos productos con esa forma
GOTAS_ML = 60  # un líquido de hasta 60 ml es un gotero o extracto, no una bebida


def _n(t: str | None) -> str:
    return rp._norm(t).strip()


def grupo(forma: str | None) -> str | None:
    return fi.GRUPO_FORMATO.get(forma) if forma else None


def mundo(gr: str | None, tam: dict | None) -> str | None:
    """La forma para «mismo mundo»: como el grupo, pero un líquido chico (gotero, extracto) aparte de las bebidas."""
    if gr == "liquido":
        ml = (tam or {}).get("ml")
        return "gotas" if ml is not None and ml <= GOTAS_ML else "liquido"
    return gr


@dataclass
class Voto:
    producto: Producto
    peso: float
    por: str  # «ingrediente» / «vecino»


@dataclass
class Clasificacion:
    rama: str | None = None
    subcategoria: str | None = None
    segmento: str | None = None
    origen: str = "sin_clasificar"  # mismo / variante_catalogo / votos / votos_ia / ia / sin_clasificar
    seguridad: str = "sin_evidencia"  # segura / dudosa / sin_evidencia
    parte: float = 0.0  # parte de los votos de la ganadora
    finalistas: list[tuple[str, float]] = field(default_factory=list)  # (subcategoría, parte)
    razones: list[str] = field(default_factory=list)
    conservar: set[int] = field(default_factory=set)  # parecidos que no se quitan (ingrediente en su forma; 2.ª finalista)
    segunda: tuple[str | None, str | None] | None = None  # (rama, subcategoría) de la 2.ª finalista si quedó dudosa
    ingrediente: str | None = None  # la raíz que se usó como ingrediente
    sospechosos: list[Producto] = field(default_factory=list)  # posibles errores del catálogo que no votaron

    def texto(self) -> str:
        """Para la explicación de la evaluación (la pantalla la muestra tal cual)."""
        if not self.subcategoria:
            return ("Clasificación: no se encontró ningún producto parecido en el catálogo; es un producto nuevo para el "
                    "surtido y no hay contra qué compararlo.")
        if self.origen in ("mismo", "variante_catalogo"):
            return f"Clasificación: {self.subcategoria}. {self.razones[0] if self.razones else ''}".strip()
        partes = f"{self.parte * 100:.0f} % de los votos"
        txt = f"Clasificación automática: {self.subcategoria} ({'segura' if self.seguridad == 'segura' else 'dudosa'}, {partes})."
        if self.seguridad == "dudosa" and len(self.finalistas) > 1:
            txt += (f" Quedó entre {self.finalistas[0][0]} y {self.finalistas[1][0]} "
                    f"({self.finalistas[1][1] * 100:.0f} %); se compara contra las dos.")
        if self.origen == "votos_ia":
            txt += " Desempató la IA local."
        if self.razones:
            txt += " Por qué: " + "; ".join(self.razones[:3]) + "."
        if self.sospechosos:
            txt += (" No votaron por posible error del catálogo: "
                    + ", ".join(p.descripcion or p.sku for p in self.sospechosos[:3]) + ".")
        return txt


# ---------------------------------------------------------------- índice del catálogo

@dataclass
class _Fila:
    p: Producto
    raices: frozenset[str]
    grupo: str | None
    marca: str
    mundo: str | None = None  # el grupo, con los goteros aparte de las bebidas (25 nov 2026)


class Indice:
    """El catálogo activo listo para votar: palabras del nombre sin la marca, forma y quién lleva cada palabra."""

    def __init__(self, catalogo: list[Producto]):
        self.filas: dict[int, _Fila] = {}
        self.por_raiz: dict[str, list[int]] = defaultdict(list)
        self.mundos: dict[str, Counter] = defaultdict(Counter)  # subcategoría → cuántos de cada forma
        for p in catalogo:
            marca = rp.raices(rp.palabras(p.marca))
            rs = frozenset(rp.raices(rp.palabras(rp.sin_sabor(p.descripcion))) - marca)
            g = grupo(rp.formato_de(p))
            self.filas[p.producto_id] = _Fila(p, rs, g, _n(p.marca), mundo(g, rp.tamano(p.descripcion)))
            if p.subcategoria:
                self.mundos[_n(p.subcategoria)][self.filas[p.producto_id].mundo] += 1
            for r in rs:
                self.por_raiz[r].append(p.producto_id)
        self._sospecha: dict[int, bool] = {}

    def en_mundo(self, sub: str, m: str | None) -> bool:
        """¿La subcategoría tiene productos de esta forma? Sin forma conocida, todas entran."""
        if not m:
            return True
        cuenta = self.mundos.get(sub)
        if not cuenta:
            return True
        n = cuenta.get(m, 0)
        return n >= MUNDO_MIN_N or n / sum(cuenta.values()) >= MUNDO_MIN

    def visibles(self, ids) -> list[_Fila]:
        fuera = rp.OCULTOS.get()
        return [self.filas[i] for i in ids if i not in fuera and i in self.filas]

    def con_raiz(self, r: str) -> list[_Fila]:
        return [f for f in self.visibles(self.por_raiz.get(r, ())) if f.p.subcategoria and rp._con_precio(f.p)]

    def sospechoso(self, pid: int) -> bool:
        """¿La subcategoría de este producto del catálogo contradice a casi todos los de su ingrediente y forma?"""
        if pid in self._sospecha:
            return self._sospecha[pid]
        f = self.filas.get(pid)
        resultado = False
        if f and f.p.subcategoria:
            s = rp.Sujeto(tipo="idea", nombre=f.p.descripcion or "", marca=f.p.marca)
            for r in rp._candidatas_ingrediente(s):
                mates = [x for x in self.por_raiz.get(r, ()) if x != pid]
                # misma forma con goteros aparte de bebidas: un extracto de 30 ml no es error por no estar con las aguas
                mates = [self.filas[x] for x in mates if self.filas[x].p.subcategoria
                         and (not f.mundo or not self.filas[x].mundo or self.filas[x].mundo == f.mundo)]
                if len(mates) < SOSPECHA_MIN:
                    continue
                sub, n = Counter(_n(x.p.subcategoria) for x in mates).most_common(1)[0]
                resultado = sub != _n(f.p.subcategoria) and n / len(mates) >= SOSPECHA_ACUERDO
                break
        self._sospecha[pid] = resultado
        return resultado


_CACHE: dict = {}


def indice(catalogo: list[Producto]) -> Indice:
    """Se arma una vez por catálogo (en el examen se reusa para miles de productos)."""
    llave = (id(catalogo), len(catalogo))
    if _CACHE.get("llave") != llave:
        _CACHE.clear()
        _CACHE.update(llave=llave, indice=Indice(catalogo))
    return _CACHE["indice"]


def catalogo_completo(bd: Session) -> list[Producto]:
    """El catálogo activo sin esconder a nadie (el índice esconde aparte, para poder reusarse en el examen)."""
    marca = rp.OCULTOS.set(frozenset())
    try:
        lista = rp.catalogo_activo(bd)
    finally:
        rp.OCULTOS.reset(marca)
    rp.cargar_fichas(bd, lista)
    return lista


# ---------------------------------------------------------------- votación

def _parecido_nombre(suyas: frozenset[str], otras: frozenset[str]) -> float:
    if not suyas or not otras:
        return 0.0
    comun = len(suyas & otras)
    if not comun:
        return 0.0
    return comun / len(suyas) * 0.6 + comun / len(suyas | otras) * 0.4


def _mismo_o_variante(s: rp.Sujeto, idx: Indice, suyas: frozenset[str]) -> Clasificacion | None:
    marca = _n(s.marca)
    for f in idx.visibles(idx.filas):
        p = f.p
        if not p.subcategoria:
            continue
        if (s.codigo_barras and p.codigo_barras and s.codigo_barras.strip() == p.codigo_barras.strip()) or rp.es_mismo(s, p):
            return Clasificacion(p.rama, p.subcategoria, p.segmento, "mismo", "segura", 1.0, [(p.subcategoria, 1.0)],
                                 [f"ya vendemos este mismo producto ({p.sku} {p.descripcion})"])
    if marca and suyas:
        for f in idx.visibles(idx.filas):
            if f.marca == marca and f.raices == suyas and f.p.subcategoria:
                p = f.p
                return Clasificacion(p.rama, p.subcategoria, p.segmento, "variante_catalogo", "segura", 1.0,
                                     [(p.subcategoria, 1.0)],
                                     [f"ya vendemos el mismo producto en otro sabor o tamaño ({p.sku} {p.descripcion})"])
    return None


def votos(bd: Session, s: rp.Sujeto, idx: Indice) -> tuple[list[Voto], str | None, list[Producto]]:
    """(votos, raíz usada como ingrediente, productos que no votaron por posible error del catálogo)."""
    suyo = grupo(rp.formato_sujeto(s))
    salida: list[Voto] = []
    sospechosos: list[Producto] = []
    raiz = None
    for r in rp._candidatas_ingrediente(s):
        con = idx.con_raiz(r)
        if len(con) >= MIN_POR_INGREDIENTE:
            raiz = r
            for f in con:
                if idx.sospechoso(f.p.producto_id):
                    sospechosos.append(f.p)
                    continue
                otra = bool(suyo and f.grupo and f.grupo != suyo)
                salida.append(Voto(f.p, PESO_INGREDIENTE_OTRA_FORMA if otra else PESO_INGREDIENTE, "ingrediente"))
            break
    marca = rp.raices(rp.palabras(s.marca))
    suyas = frozenset(rp.raices(rp.palabras(rp.sin_sabor(s.nombre), s.ingrediente)) - marca)
    cerca: dict[int, float] = {}
    for r in suyas:
        for f in idx.visibles(idx.por_raiz.get(r, ())):
            if f.p.producto_id not in cerca and f.p.subcategoria and rp._con_precio(f.p):
                cerca[f.p.producto_id] = _parecido_nombre(suyas, f.raices)
    try:
        for pid, cos in fi.cercanos_por_funcion(bd, s.ficha, k=VECINOS * 2):
            f = idx.filas.get(pid)
            if f and pid not in rp.OCULTOS.get() and f.p.subcategoria:
                cerca[pid] = max(cerca.get(pid, 0.0), float(cos))
    except Exception as e:  # noqa: BLE001 - sin huellas u Ollama votan solo las palabras
        log.info("Clasificador: sin vecinos por significado: %s", e)
    mejores = sorted(((pid, v) for pid, v in cerca.items() if v >= MIN_VECINO), key=lambda x: -x[1])[:VECINOS]
    for pid, v in mejores:
        f = idx.filas[pid]
        if idx.sospechoso(pid):
            if f.p not in sospechosos:
                sospechosos.append(f.p)
            continue
        otra = bool(suyo and f.grupo and f.grupo != suyo)
        salida.append(Voto(f.p, PESO_VECINO * v * (VECINO_OTRA_FORMA if otra else 1.0), "vecino"))
    return salida, raiz, sospechosos


INSTRUCCIONES_DESEMPATE = """Eres comprador de una cadena de tiendas naturistas en México. Te doy un producto nuevo y 2 o 3
subcategorías de nuestro catálogo, cada una con ejemplos de productos que ya vendemos ahí. Elige la subcategoría donde un
cliente buscaría este producto en el anaquel. Contesta SOLO un JSON así: {"subcategoria": "<copiada tal cual>",
"motivo": "pocas palabras"}"""


def desempatar(bd: Session, s: rp.Sujeto, finalistas: list[str], ejemplos: dict[str, list[str]]) -> str | None:
    mensaje = json.dumps({"producto": s.nombre, "marca": s.marca, "ingrediente": s.ingrediente, "forma": s.forma,
                          "descripcion": (s.descripcion or "")[:300] or None,
                          "opciones": [{"subcategoria": c, "ejemplos": ejemplos.get(c, [])[:4]} for c in finalistas]},
                         ensure_ascii=False)
    try:
        r = puerta.ejecutar(bd, rp.TAREA_CLASIFICAR, usuario_id=None, instrucciones=INSTRUCCIONES_DESEMPATE,
                            mensaje=mensaje, max_tokens=200, esfuerzo="low", formato="json",
                            contexto=puerta.ventana(INSTRUCCIONES_DESEMPATE, mensaje, salida=200))
        datos = json.loads(r.texto[r.texto.find("{"):r.texto.rfind("}") + 1])
    except (puerta.ErrorIA, ValueError, AttributeError) as e:
        log.info("Clasificador: la IA no desempató «%s»: %s", s.nombre, e)
        return None
    elegida = _n(datos.get("subcategoria"))
    return next((c for c in finalistas if _n(c) == elegida), None)


def clasificar(bd: Session, s: rp.Sujeto, usar_ia: bool = True) -> Clasificacion:
    idx = indice(catalogo_completo(bd))
    marca = rp.raices(rp.palabras(s.marca))
    suyas = frozenset(rp.raices(rp.palabras(rp.sin_sabor(s.nombre))) - marca)
    if (directa := _mismo_o_variante(s, idx, suyas)):
        return directa
    lista, raiz, sospechosos = votos(bd, s, idx)
    if not lista:
        c = Clasificacion(ingrediente=raiz, sospechosos=sospechosos)
        if usar_ia:  # ningún producto se parece: como último recurso, la IA entre las subcategorías del catálogo
            rama, sub, seg = rp.clasificar(bd, s, [])
            if sub:
                c.rama, c.subcategoria, c.segmento, c.origen, c.seguridad = rama, sub, seg, "ia", "dudosa"
        return c
    peso: dict[str, float] = defaultdict(float)
    quien: dict[str, list[Voto]] = defaultdict(list)
    for v in lista:
        k = _n(v.producto.subcategoria)
        peso[k] += v.peso
        quien[k].append(v)
    # Misma forma, mismo mundo: fuera las subcategorías sin productos de su forma (si queda alguna)
    suyo_mundo = mundo(grupo(rp.formato_sujeto(s)), rp.tamano(s.contenido, s.nombre))
    fuera_mundo = [k for k in peso if not idx.en_mundo(k, suyo_mundo)]
    if fuera_mundo and len(fuera_mundo) < len(peso):
        for k in fuera_mundo:
            del peso[k]
            del quien[k]
    else:
        fuera_mundo = []
    total = sum(peso.values())
    orden = sorted(peso, key=lambda k: -peso[k])
    nombre = {k: Counter(v.producto.subcategoria for v in quien[k]).most_common(1)[0][0] for k in orden}
    finalistas = [(nombre[k], peso[k] / total) for k in orden[:FINALISTAS]]
    ganadora, origen = orden[0], "votos"
    parte = peso[ganadora] / total
    seguridad = "segura" if parte >= SEGURA else "dudosa"
    parejas = [k for k in orden[:FINALISTAS] if peso[k] >= VENTAJA_IA * peso[orden[0]]]
    if seguridad == "dudosa" and usar_ia and len(parejas) > 1:
        ejemplos = {nombre[k]: [v.producto.descripcion or v.producto.sku for v in
                                sorted(quien[k], key=lambda v: -v.peso)] for k in parejas}
        if (elegida := desempatar(bd, s, [nombre[k] for k in parejas], ejemplos)):
            ganadora = _n(elegida)
            origen = "votos_ia"
            parte = peso[ganadora] / total
    guia = Counter((v.producto.rama, v.producto.segmento) for v in quien[ganadora]).most_common(1)[0][0]
    c = Clasificacion(guia[0], nombre[ganadora], guia[1], origen, seguridad, parte, finalistas, [], set(), None, raiz,
                      sospechosos)
    suyo = grupo(rp.formato_sujeto(s))
    c.conservar = {v.producto.producto_id for v in lista if v.por == "ingrediente"
                   and _n(v.producto.subcategoria) == ganadora
                   and not (suyo and idx.filas[v.producto.producto_id].grupo
                            and idx.filas[v.producto.producto_id].grupo != suyo)}
    if seguridad == "dudosa" and len(orden) > 1:
        segunda = next(k for k in orden if k != ganadora)
        c.segunda = (quien[segunda][0].producto.rama, nombre[segunda])
        c.conservar |= {v.producto.producto_id for v in quien[segunda]
                        if not (suyo and idx.filas[v.producto.producto_id].grupo
                                and idx.filas[v.producto.producto_id].grupo != suyo)}
    # Por qué, en palabras: cuántos de cada evidencia votaron por la ganadora
    ing = [v for v in quien[ganadora] if v.por == "ingrediente"]
    vec = [v for v in quien[ganadora] if v.por == "vecino"]
    if ing:
        misma = sum(1 for v in ing if v.peso == PESO_INGREDIENTE)
        c.razones.append(f"{len(ing)} producto(s) con su mismo ingrediente están ahí"
                         + (f", {misma} en su misma forma" if suyo and misma != len(ing) else "")
                         + f" (p. ej. {ing[0].producto.descripcion})")
    if vec:
        top = sorted(vec, key=lambda v: -v.peso)[:2]
        c.razones.append(f"{len(vec)} de sus productos más parecidos también ("
                         + "; ".join(v.producto.descripcion or v.producto.sku for v in top) + ")")
    if fuera_mundo:
        c.razones.append(f"no entran {len(fuera_mundo)} subcategoría(s) sin productos de su forma")
    return c
