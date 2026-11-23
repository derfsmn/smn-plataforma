"""Pronóstico de piezas de un producto nuevo por grupo de tiendas, y lo que aprende de los lanzamientos de 2026
(plan del radar inteligente con IA local, aprobado por Diego el 2026-11-17). Todo en Python, sin IA.

Cómo se calcula:
1. Lanzamientos de 2026: SKU cuya primera venta en SMNBI cae al menos 8 semanas después de que empieza la historia
   cargada y que ya tienen 12 semanas de venta. Para cada uno se mide cuánto vendió por tienda al mes en sus semanas
   1–4, 5–8 y 9–12, contra lo que vendía en esas mismas semanas lo típico de su subcategoría (la mediana de los SKU
   que ya estaban). Esa razón dice «un producto nuevo arranca vendiendo X veces lo típico de su subcategoría».
2. Pronóstico: lo que venden por tienda al mes los parecidos de precio cercano (o, sin ellos, lo típico de la
   subcategoría) × las razones de arranque (percentil 10, mediana y percentil 90 = rango bajo / medio / alto). Es un
   rango, no un número seguro. Si ya hay prueba con lanzamientos reales (paso 5), el bajo y el alto salen de cuánto se
   equivocó de verdad (percentil 10 y 90 de lo vendido ÷ lo pronosticado). Hasta el 20 nov 2026 eran cuartil bajo y alto, y en la prueba con 12 lanzamientos reales
   solo 3 cayeron dentro: el rango era demasiado estrecho.
3. Por grupo de tiendas (última corrida de Datos → Mapa de tiendas): lo mismo con la venta de los parecidos en las
   tiendas de cada grupo.
4. Venta nueva contra canibalizada: en los lanzamientos, cuánto bajaron los demás SKU de su subcategoría en las 12
   semanas después del lanzamiento contra las 12 de antes, como parte de lo que vendió el nuevo.
5. Examen: a cada lanzamiento se le pronostica con las razones de los demás (sin verlo) y se mide cuántas veces cayó
   dentro del rango y el error de la mediana. Además, la prueba completa (`validacion_demanda`): a lanzamientos reales
   se les pronostica con sus parecidos y la venta de antes de salir, y se cuenta en cuántos atinó el color de la Demanda
   y la clase AA–E. Se muestra tal cual, sea bueno o malo.
6. Cada producto aceptado que se revisa a las 4, 8 y 12 semanas entra como un lanzamiento más (aprende solo).
"""
import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datos.modelos import Producto, Tienda, TiendaGrupo, TiendaGrupoCorrida, VentaSemanal
from modulos.compras import realidad_producto as rr
from nucleo.modelos import ahora

log = logging.getLogger("smn.compras.pronostico")

TRAMOS = (4, 8, 12)
SEMANAS_PREVIAS = 8  # la primera venta debe caer al menos 8 semanas después del inicio de la historia
MIN_LANZAMIENTOS = 5
_CACHE: dict = {}


def _cuartiles(xs: list[float], ps: tuple[float, float, float] = (0.25, 0.5, 0.75)
               ) -> tuple[float, float, float] | None:
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)

    def q(p: float) -> float:
        i = (n - 1) * p
        a, b = int(i), min(int(i) + 1, n - 1)
        return xs[a] + (xs[b] - xs[a]) * (i - a)

    return q(ps[0]), q(ps[1]), q(ps[2])


BANDA = (0.10, 0.50, 0.90)  # pesimista / esperado / optimista (20 nov 2026, antes 25/50/75)


def _banda(xs: list[float]) -> tuple[float, float, float] | None:
    return _cuartiles(xs, BANDA)


@dataclass
class Lanzamiento:
    sku: str
    subcategoria: str | None
    inicio: date
    razon: dict[int, float]  # tramo -> piezas por tienda al mes / lo típico de su subcategoría
    por_tienda: dict[int, float]  # tramo -> piezas por tienda al mes
    canibal: float | None  # parte de su venta que se le quitó a los demás de su subcategoría (0 a 1)


@dataclass
class Modelo:
    lanzamientos: list[Lanzamiento] = field(default_factory=list)
    razones: dict[int, tuple[float, float, float]] = field(default_factory=dict)  # tramo -> cuartiles
    canibal: float | None = None
    examen: dict = field(default_factory=dict)
    fin: date | None = None
    prueba: dict | None = None  # validacion_demanda.prueba: en cuántos lanzamientos reales atinó


def _semanales(bd: Session) -> tuple[dict[str, dict[date, tuple[float, int]]], date, date] | None:
    """Por SKU y semana: (piezas netas, tiendas con venta), sin mayoreo."""
    v = rr.ventana(bd, semanas=200)
    if not v:
        return None
    inicio = bd.scalar(select(func.min(VentaSemanal.semana)))
    q = (select(VentaSemanal.sku, VentaSemanal.semana, func.sum(rr.NETAS), func.count(VentaSemanal.tienda.distinct()))
         .where(*v.filtro()).group_by(VentaSemanal.sku, VentaSemanal.semana))
    datos: dict[str, dict[date, tuple[float, int]]] = defaultdict(dict)
    for sku, semana, piezas, tiendas in bd.execute(q):
        if piezas and piezas > 0:
            datos[sku][semana] = (float(piezas), int(tiendas))
    return datos, inicio, v.fin


def _por_tienda_mes(semanas: dict[date, tuple[float, int]], desde: date, hasta: date) -> float | None:
    filas = [x for s, x in semanas.items() if desde <= s <= hasta]
    if not filas:
        return None
    piezas = sum(p for p, _ in filas)
    tiendas = max(t for _, t in filas)
    n = (hasta - desde).days // 7 + 1
    return piezas / max(1, tiendas) / n * rr.SEMANAS_MES


def _por_tienda_como_demanda(bd: Session, lanzamientos: list[Lanzamiento], datos: dict, fin: date) -> None:
    """Piezas por tienda al mes de cada lanzamiento medidas igual que la Demanda (19 nov 2026): entre todas las tiendas
    que ya lo habían vendido desde su lanzamiento, no entre las de la semana con más tiendas. Así el pronóstico de un
    producto nuevo y lo que vendieron los lanzamientos se comparan en la misma unidad (Wonu salía «más que 0 de cada
    100 lanzamientos» con 0.9 piezas por tienda)."""
    v = rr.ventana(bd, semanas=200) if lanzamientos else None
    if not v:
        return
    primera: dict[str, list[date]] = defaultdict(list)
    skus = [x.sku for x in lanzamientos]
    for i in range(0, len(skus), 1000):
        q = (select(VentaSemanal.sku, VentaSemanal.tienda, func.min(VentaSemanal.semana))
             .where(*v.filtro(), VentaSemanal.sku.in_(skus[i:i + 1000]), rr.NETAS > 0)
             .group_by(VentaSemanal.sku, VentaSemanal.tienda))
        for sku, _, semana in bd.execute(q):
            primera[sku].append(semana)
    for x in lanzamientos:
        for tramo in list(x.por_tienda):
            desde, hasta = x.inicio + timedelta(weeks=tramo - 4), x.inicio + timedelta(weeks=tramo - 1)
            tiendas = sum(1 for d in primera[x.sku] if d <= hasta)
            piezas = sum(p for s, (p, _) in datos[x.sku].items() if desde <= s <= hasta)
            x.por_tienda[tramo] = piezas / max(1, tiendas) / 4 * rr.SEMANAS_MES


def entrenar(bd: Session) -> Modelo:
    """Mide los lanzamientos de la historia cargada. Se guarda en memoria un día."""
    hoy = ahora().date()
    if _CACHE.get("dia") == hoy and "modelo" in _CACHE:
        return _CACHE["modelo"]
    m = Modelo()
    base = _semanales(bd)
    if not base:
        return m
    datos, inicio_hist, fin = base
    m.fin = fin
    sub = dict(bd.execute(select(Producto.sku, Producto.subcategoria)).all())
    primera = {sku: min(s) for sku, s in datos.items()}
    corte = inicio_hist + timedelta(weeks=SEMANAS_PREVIAS)
    por_sub: dict[str | None, list[str]] = defaultdict(list)
    for sku in datos:
        por_sub[sub.get(sku)].append(sku)
    for sku, ini in primera.items():
        if ini < corte or ini + timedelta(weeks=11) > fin:
            continue
        razon, por_tienda = {}, {}
        viejos = [x for x in por_sub[sub.get(sku)] if primera[x] < ini - timedelta(weeks=4) and x != sku]
        for tramo in TRAMOS:
            desde, hasta = ini + timedelta(weeks=tramo - 4), ini + timedelta(weeks=tramo - 1)
            suyo = _por_tienda_mes(datos[sku], desde, hasta)
            if suyo is None:
                continue
            por_tienda[tramo] = suyo
            tipicos = [t for x in viejos if (t := _por_tienda_mes(datos[x], desde, hasta))]
            if len(tipicos) >= 3:
                razon[tramo] = suyo / median(tipicos)
        if not razon:
            continue
        canibal = None
        if len(viejos) >= 3 and ini - timedelta(weeks=12) >= inicio_hist:
            antes = sum(p for x in viejos for s, (p, _) in datos[x].items() if ini - timedelta(weeks=12) <= s < ini)
            despues = sum(p for x in viejos for s, (p, _) in datos[x].items() if ini <= s < ini + timedelta(weeks=12))
            nuevo = sum(p for s, (p, _) in datos[sku].items() if ini <= s < ini + timedelta(weeks=12))
            if nuevo > 0:
                canibal = max(0.0, min(1.0, (antes - despues) / nuevo))
        m.lanzamientos.append(Lanzamiento(sku, sub.get(sku), ini, razon, por_tienda, canibal))
    _por_tienda_como_demanda(bd, m.lanzamientos, datos, fin)
    for tramo in TRAMOS:
        if c := _banda([x.razon[tramo] for x in m.lanzamientos if tramo in x.razon]):
            m.razones[tramo] = c
    canibales = [x.canibal for x in m.lanzamientos if x.canibal is not None]
    m.canibal = median(canibales) if len(canibales) >= MIN_LANZAMIENTOS else None
    if m.canibal is not None and m.canibal >= 0.9:
        # Casi todo «quitado» no es creíble: la subcategoría completa bajó por temporada, no por el nuevo (Wonu, 17 nov)
        m.canibal = None
    m.examen = examen(m)
    if isinstance(bd, Session) and len(m.lanzamientos) >= MIN_LANZAMIENTOS:
        try:
            from modulos.compras import validacion_demanda

            m.prueba = validacion_demanda.prueba(bd, m)
        except Exception as ex:  # noqa: BLE001  sin prueba el pronóstico sigue
            log.warning("Pronóstico: no se pudo hacer la prueba con lanzamientos reales: %s", ex)
    _CACHE.update(dia=hoy, modelo=m)
    return m


def examen(m: Modelo, tramo: int = 12) -> dict:
    """Pronostica cada lanzamiento con las razones de los demás (sin verlo) y mide qué tan bien le atina."""
    con = [x for x in m.lanzamientos if tramo in x.razon]
    if len(con) < MIN_LANZAMIENTOS:
        return {"lanzamientos": len(con), "suficientes": False}
    dentro, errores = 0, []
    for x in con:
        otros = _banda([y.razon[tramo] for y in con if y is not x])
        bajo, medio, alto = otros
        real = x.razon[tramo]
        dentro += bajo <= real <= alto
        errores.append(abs(medio - real) / real)
    return {"lanzamientos": len(con), "suficientes": True, "dentro_pct": round(dentro / len(con) * 100),
            "error_mediano_pct": round(median(errores) * 100)}


# ---------------------------------------------------------------- pronóstico de un producto

@dataclass
class PorGrupo:
    grupo: int
    nombre: str
    tiendas: int
    bajo: float
    medio: float
    alto: float


@dataclass
class Pronostico:
    base: float | None = None  # piezas por tienda al mes de los parecidos (o lo típico de la subcategoría)
    base_de: str = ""
    tramos: dict[str, list[float]] = field(default_factory=dict)  # "4" -> [bajo, medio, alto]
    grupos: list[PorGrupo] = field(default_factory=list)
    canibal_pct: float | None = None
    lanzamientos: int = 0
    examen: dict = field(default_factory=dict)  # incluye "prueba" con lanzamientos reales si se pudo hacer
    nota: str | None = None
    misma_sub: list[dict] = field(default_factory=list)  # lanzamientos de 2026 de su subcategoría: sku, descripcion, por_tienda
    contra: list[float] = field(default_factory=list)  # lanzamientos contra los que se calificó la Demanda (piezas por tienda al mes)
    contra_depto: bool = False  # si `contra` son solo los de su departamento

    def a_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def de_json(cls, texto: str | None) -> "Pronostico | None":
        if not texto:
            return None
        d = json.loads(texto)
        d["grupos"] = [PorGrupo(**g) for g in d.get("grupos") or []]
        return cls(**d)

    def rango(self, tramo: int = 12) -> list[float] | None:
        return self.tramos.get(str(tramo))


def _grupos(bd: Session) -> tuple[dict[str, int], dict[int, str]]:
    """Tienda -> grupo y grupo -> nombre de la última corrida completa de grupos de tiendas."""
    c = bd.scalar(select(TiendaGrupoCorrida).where(TiendaGrupoCorrida.estado == "completa")
                  .order_by(TiendaGrupoCorrida.corrida_id.desc()))
    if not c:
        return {}, {}
    de = dict(bd.execute(select(TiendaGrupo.almacen, TiendaGrupo.grupo).where(TiendaGrupo.corrida_id == c.corrida_id)).all())
    nombres = {}
    try:
        for p in json.loads(c.perfiles or "[]"):
            nombres[int(p["grupo"])] = str(p.get("nombre") or f"Grupo {p['grupo']}")
    except (ValueError, KeyError, TypeError):
        pass
    return de, nombres


def pronosticar(bd: Session, skus_parecidos: list[str], subcategoria: str | None) -> Pronostico:
    """Rango de piezas por tienda al mes a 4, 8 y 12 semanas, en total y por grupo de tiendas."""
    m = entrenar(bd)
    p = Pronostico(lanzamientos=len(m.lanzamientos), examen={**m.examen, **({"prueba": m.prueba} if m.prueba else {})},
                   canibal_pct=round(m.canibal * 100) if m.canibal is not None else None)
    if subcategoria:  # para decir contra qué productos reales se compara (Diego, 20 nov 2026)
        suyos = sorted((x for x in m.lanzamientos if x.subcategoria == subcategoria and 12 in x.por_tienda),
                       key=lambda x: -x.por_tienda[12])
        nombres = dict(bd.execute(select(Producto.sku, Producto.descripcion).where(
            Producto.sku.in_([x.sku for x in suyos]))).all()) if suyos else {}
        p.misma_sub = [{"sku": x.sku, "descripcion": nombres.get(x.sku) or x.sku, "por_tienda": round(x.por_tienda[12], 2)}
                       for x in suyos]
    if len(m.lanzamientos) < MIN_LANZAMIENTOS or not m.razones:
        p.nota = (f"Todavía no hay suficientes lanzamientos en la venta cargada para pronosticar ({len(m.lanzamientos)}; "
                  f"hacen falta {MIN_LANZAMIENTOS}).")
        return p
    v = rr.ventana(bd)
    if not v:
        return p
    venta = rr.venta_por_sku(bd, v, skus_parecidos) if skus_parecidos else {}
    if venta:
        p.base = sum(x.por_tienda_mes for x in venta.values()) / len(venta)
        p.base_de = f"{len(venta)} parecido(s) que ya vendemos"
    elif subcategoria:
        de_sub = rr.venta_por_sku(bd, v, list(bd.scalars(select(Producto.sku).where(Producto.subcategoria == subcategoria))))
        if de_sub:
            p.base = median([x.por_tienda_mes for x in de_sub.values()])
            p.base_de = f"lo típico de la subcategoría {subcategoria}"
    if not p.base:
        p.nota = "No hay venta de parecidos ni de su subcategoría para pronosticar."
        return p
    ajuste = (m.prueba or {}).get("ajuste")  # rango con los errores reales de la prueba (20 nov 2026)
    for tramo, (bajo, medio, alto) in m.razones.items():
        if ajuste:
            bajo, alto = medio * ajuste[0], medio * ajuste[1]
        p.tramos[str(tramo)] = [round(p.base * bajo, 2), round(p.base * medio, 2), round(p.base * alto, 2)]
    # Por grupo de tiendas: la venta de los parecidos en las tiendas de cada grupo
    de, nombres = _grupos(bd)
    if de and venta:
        q = (select(VentaSemanal.tienda, func.sum(rr.NETAS)).where(*v.filtro(), VentaSemanal.sku.in_(list(venta)))
             .group_by(VentaSemanal.tienda))
        semanas = max(1, (v.fin - v.desde).days // 7 + 1)
        por_grupo: dict[int, list[float]] = defaultdict(list)
        for tienda, piezas in bd.execute(q):
            if (g := de.get(tienda)) is not None:
                por_grupo[g].append(float(piezas or 0) / len(venta) / semanas * rr.SEMANAS_MES)
        bajo, medio, alto = m.razones[12]
        if ajuste:
            bajo, alto = medio * ajuste[0], medio * ajuste[1]
        for g, xs in sorted(por_grupo.items()):
            b = sum(xs) / len(xs)
            p.grupos.append(PorGrupo(g, nombres.get(g, f"Grupo {g}"), len(xs), round(b * bajo, 2), round(b * medio, 2),
                                     round(b * alto, 2)))
    return p


def lugar_entre_lanzamientos(bd: Session, por_tienda_mes: float, departamento: str | None = None
                             ) -> tuple[float, int, bool] | None:
    """Qué tan arriba quedaría un producto que vende `por_tienda_mes` entre los lanzamientos de 2026 a 12 semanas:
    (de cada 100 lanzamientos, cuántos vendieron igual o menos; cuántos lanzamientos; si son solo del departamento).
    Con 20 o más lanzamientos en el departamento se compara contra ellos; si no, contra todos. Plan de Demanda aprobado
    por Diego el 19 nov 2026: la calificación sale del pronóstico, no del promedio de los parecidos."""
    lista, del_depto = lanzamientos_contra(bd, departamento)
    if len(lista) < MIN_LANZAMIENTOS:
        return None
    lugar = sum(1 for x in lista if x <= por_tienda_mes) / len(lista) * 100
    return lugar, len(lista), del_depto


def modelo_de_hoy() -> "Modelo | None":
    """El modelo ya medido hoy en este proceso, sin volver a medirlo (la pantalla del comité no debe esperar)."""
    return _CACHE.get("modelo") if _CACHE.get("dia") == ahora().date() else None


def lanzamientos_contra(bd: Session, departamento: str | None = None) -> tuple[list[float], bool]:
    """Piezas por tienda al mes en las semanas 9 a 12 de los lanzamientos contra los que se califica la Demanda: los
    del departamento si son 20 o más; si no, todos. (venta, si son solo del departamento)."""
    m = entrenar(bd)
    todos = [x for x in m.lanzamientos if 12 in x.por_tienda]
    if departamento:
        del_suyo = set(bd.scalars(select(Producto.sku).where(Producto.departamento == departamento)))
        suyos = [x for x in todos if x.sku in del_suyo]
        if len(suyos) >= 20:
            return [x.por_tienda[12] for x in suyos], True
    return [x.por_tienda[12] for x in todos], False


# ---------------------------------------------------------------- tiendas para una prueba

def tiendas_para_prueba(bd: Session, skus_parecidos: list[str], n: int = 10) -> list[dict]:
    """Tiendas sugeridas para «Aceptado a prueba»: de cada grupo de tiendas, las más típicas del grupo, de regiones
    distintas y, si se puede, donde ya se venden los parecidos. El comité elige."""
    c = bd.scalar(select(TiendaGrupoCorrida).where(TiendaGrupoCorrida.estado == "completa")
                  .order_by(TiendaGrupoCorrida.corrida_id.desc()))
    if not c:
        return []
    _, nombres = _grupos(bd)
    v = rr.ventana(bd)
    con_venta: set[str] = set()
    if v and skus_parecidos:
        con_venta = set(bd.scalars(select(VentaSemanal.tienda.distinct()).where(
            *v.filtro(), VentaSemanal.sku.in_(skus_parecidos))))
    filas = bd.execute(select(TiendaGrupo, Tienda).join(Tienda, Tienda.almacen == TiendaGrupo.almacen)
                       .where(TiendaGrupo.corrida_id == c.corrida_id)).all()
    por_grupo: dict[int, list] = defaultdict(list)
    for tg, t in filas:
        por_grupo[tg.grupo].append((t.almacen in con_venta, tg.tipicidad or 0, tg, t))
    salida: list[dict] = []
    ronda = 0
    while len(salida) < n and any(por_grupo.values()):
        for g in sorted(por_grupo):
            lista = sorted(por_grupo[g], key=lambda x: (-x[0], -x[1]))
            usadas = {s["region"] for s in salida if s["grupo"] == g}
            elegida = next((x for x in lista if x[3].region not in usadas), lista[0] if lista else None)
            if elegida is None:
                continue
            por_grupo[g].remove(elegida)
            _, tip, tg, t = elegida
            salida.append({"almacen": t.almacen, "nombre": t.nombre, "region": t.region, "grupo": g,
                           "grupo_nombre": nombres.get(g, f"Grupo {g}"), "tipicidad": tip,
                           "vende_parecidos": t.almacen in con_venta})
            if len(salida) >= n:
                break
        ronda += 1
        if ronda > 50:
            break
    return salida
