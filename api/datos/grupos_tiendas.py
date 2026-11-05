"""Datos → Grupos de tiendas (Diego eligió «Grupos de tiendas», 2026-10-29, y pidió «quiero que sea local la IA»).

Después pidió «no podríamos hacer por ventas, por disminución importante, por demográficos y mezcladas, quiero algo
inteligente»: quien calcula elige uno o varios **criterios** y el peso de cada uno.
- **Ventas:** venta por semana, precio promedio por pieza, margen y productos distintos vendidos.
- **Tendencia:** cambio de las últimas 13 semanas contra las 13 anteriores, ritmo semanal (pendiente de 26 semanas) y
  qué tanto varía de una semana a otra.
- **Mezcla:** qué parte de su venta es de cada departamento (departamentos de menos del 1 % van a «Otros»).
- **Demografía:** de la localidad urbana de la tienda, con el Censo 2020 del INEGI (ver `datos/demografia.py`).

Cómo se calcula (todo en Python, dentro de la plataforma):
1. Venta sin IVA de las últimas 26 semanas cargadas, sin mayoreo. Fuera: tiendas con menos de 8 semanas con venta.
2. Cada rasgo se estandariza (media 0, desviación 1, recortado a ±3; venta y habitantes en logaritmo). Cada criterio
   pesa lo que se eligió, sin importar cuántos rasgos tenga. Lo que falta (p. ej. tienda sin coordenadas) cuenta como
   el promedio.
3. k-medias probando de 2 a 8 grupos y quedándose con el que mejor separa (silueta), o el número que se pidió (2 a 10).
4. Por grupo: los rasgos que más lo distinguen contra la empresa (mediana de todas las tiendas). Por tienda: qué tan
   típica es, en qué se sale de su grupo y si va **abajo de sus pares** (vende 30 % menos por semana, cae 10 puntos más
   o tiene 5 puntos menos de margen que la mediana de las otras tiendas de su grupo).
5. El nombre y la explicación de cada grupo los redacta la IA local (Ollama, tarea `datos.tiendas_grupos`), solo con
   esos números. Nunca va a la API externa; si Ollama no responde, los grupos quedan con número y la nota dice por qué.
"""
import json
import logging
import math
import random
import statistics
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from datos import demografia
from datos.modelos import Producto, Tienda, TiendaGrupo, TiendaGrupoCorrida, VentaSemanal
from ia import puerta
from modulos.compras import realidad_producto as rr
from nucleo.modelos import ahora

log = logging.getLogger(__name__)

SEMANAS = 26
MITAD = 13
MIN_SEMANAS = 8
MIN_SEMANAS_MITAD = 4  # semanas con venta en cada mitad para medir el cambio
MIN_TIENDAS = 6
MIN_PARTICIPACION = 0.01
MAX_GRUPOS = 8
MAX_PEDIDOS = 10  # tope cuando el usuario elige cuántos grupos
REINICIOS = 10
CORRIDAS_GUARDADAS = 5
TAREA_IA = "datos.tiendas_grupos"
OTROS = "Otros"
SIN_DEPTO = "Sin departamento"

CRITERIOS = {"ventas": "Ventas", "tendencia": "Tendencia", "mezcla": "Mezcla por departamento",
             "demografia": "Demografía de la zona"}
PESOS_POR_OMISION = {"ventas": 1, "tendencia": 1, "mezcla": 1, "demografia": 1}

# Abajo de sus pares: contra la mediana de las otras tiendas de su grupo
PARES_VENTA = 0.70
PARES_CAMBIO_PTS = 10.0
PARES_MARGEN_PTS = 5.0


@dataclass(frozen=True)
class Rasgo:
    clave: str
    criterio: str
    nombre: str
    unidad: str  # "$", "%", "% por semana", "" (número)
    log: bool = False  # se agrupa con su logaritmo (venta, habitantes)


RASGOS = [
    Rasgo("venta_semanal", "ventas", "Venta por semana", "$", True),
    Rasgo("precio_pieza", "ventas", "Precio promedio por pieza", "$"),
    Rasgo("margen", "ventas", "Margen", "%"),
    Rasgo("surtido", "ventas", "Productos distintos vendidos", ""),
    Rasgo("cambio", "tendencia", "Cambio de venta (13 semanas contra las 13 anteriores)", "%"),
    Rasgo("pendiente", "tendencia", "Ritmo de la venta en 26 semanas", "% por semana"),
    Rasgo("variabilidad", "tendencia", "Variación de una semana a otra", "%"),
    Rasgo("poblacion", "demografia", "Habitantes de la localidad", "", True),
    Rasgo("pct_60_mas", "demografia", "Población de 60 años o más", "%"),
    Rasgo("pct_0_14", "demografia", "Población de 0 a 14 años", "%"),
    Rasgo("nse", "demografia", "Nivel socioeconómico aproximado (0 a 100)", ""),
    Rasgo("pct_sin_salud", "demografia", "Población sin servicio de salud", "%"),
]
POR_CLAVE = {r.clave: r for r in RASGOS}

INSTRUCCIONES = """Eres analista comercial de Súper Mayoreo Naturista, cadena de tiendas naturistas en México.
Te paso grupos de tiendas que se armaron con estos criterios: {criterios}. Para cada grupo van los rasgos que más
lo distinguen (valor del grupo contra la mediana de la empresa) y, según el criterio, qué departamentos vende de más
o de menos, en qué departamentos le va peor que a la empresa (cambio de las últimas 13 semanas) y en qué
localidades están. «Nivel socioeconómico aproximado» sale del Censo (escolaridad y viviendas con auto, internet y
computadora), no del ingreso.
Para cada grupo escribe, en español de México y con palabras simples:
- "nombre": de 2 a 4 palabras que describan qué lo distingue (por ejemplo «Grandes que vienen cayendo»).
- "descripcion": máximo 45 palabras con los números que te paso.
- "acciones": 2 o 3 ideas concretas para Compras u Operaciones (máximo 20 palabras cada una) basadas solo en esos números.
Reglas: usa solo los datos que te paso; no inventes causas (clima, competencia) ni cifras.
Contesta SOLO con JSON: {{"grupos": [{{"grupo": 1, "nombre": "...", "descripcion": "...", "acciones": ["..."]}}]}}"""


# ---------------------------------------------------------------- matemáticas (sin numpy)

def _dist2(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _centro(puntos: list[list[float]]) -> list[float]:
    n = len(puntos)
    return [sum(p[i] for p in puntos) / n for i in range(len(puntos[0]))]


def kmedias(x: list[list[float]], k: int, semilla: int = 42) -> tuple[list[int], float]:
    """k-medias con arranque k-means++ y varios reinicios; regresa (grupo de cada punto, inercia)."""
    mejor: tuple[list[int], float] | None = None
    for r in range(REINICIOS):
        azar = random.Random(semilla + r)
        centros = [x[azar.randrange(len(x))]]
        while len(centros) < k:
            d = [min(_dist2(p, c) for c in centros) for p in x]
            total = sum(d)
            if total == 0:
                centros.append(x[azar.randrange(len(x))])
                continue
            u, acum = azar.random() * total, 0.0
            for p, di in zip(x, d):
                acum += di
                if acum >= u:
                    centros.append(p)
                    break
        etiquetas = [0] * len(x)
        for _ in range(100):
            nuevas = [min(range(k), key=lambda j: _dist2(p, centros[j])) for p in x]
            for j in range(k):
                miembros = [p for p, e in zip(x, nuevas) if e == j]
                if miembros:
                    centros[j] = _centro(miembros)
            if nuevas == etiquetas:
                break
            etiquetas = nuevas
        inercia = sum(_dist2(p, centros[e]) for p, e in zip(x, etiquetas))
        if mejor is None or inercia < mejor[1]:
            mejor = (etiquetas, inercia)
    return mejor


def silueta(x: list[list[float]], etiquetas: list[int]) -> float:
    """Promedio de la silueta: cerca de 1, grupos bien separados; cerca de 0, se enciman."""
    grupos = set(etiquetas)
    if len(grupos) < 2:
        return 0.0
    valores = []
    for i, p in enumerate(x):
        por_grupo: dict[int, list[float]] = {}
        for j, q in enumerate(x):
            if i != j:
                por_grupo.setdefault(etiquetas[j], []).append(math.sqrt(_dist2(p, q)))
        propio = por_grupo.get(etiquetas[i])
        if not propio:
            valores.append(0.0)
            continue
        a = sum(propio) / len(propio)
        b = min(sum(d) / len(d) for g, d in por_grupo.items() if g != etiquetas[i])
        valores.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    return sum(valores) / len(valores)


def k_maximo(n: int, pedido: bool = False) -> int:
    """Más grupos posibles con n tiendas: al menos 3 tiendas por grupo en promedio."""
    return max(2, min(MAX_PEDIDOS if pedido else MAX_GRUPOS, n // 3))


def elegir_k(x: list[list[float]], pedido: int | None = None) -> tuple[int, list[int], float, list[dict]]:
    """Prueba de 2 a 8 grupos (sin pasar de una tercera parte de las tiendas) y se queda con la mejor silueta, o con
    `pedido` si el usuario eligió cuántos. Devuelve también la calidad de cada número probado."""
    tope = k_maximo(len(x), pedido is not None)
    if pedido is not None:
        pedido = max(2, min(pedido, tope))
    mejor, elegido, opciones = None, None, []
    for k in range(2, max(tope, pedido or 2) + 1):
        etiquetas, _ = kmedias(x, k)
        s = silueta(x, etiquetas)
        opciones.append({"grupos": k, "calidad": round(s, 3)})
        if k <= MAX_GRUPOS and (mejor is None or s > mejor[2] + 1e-9):
            mejor = (k, etiquetas, s)
        if k == pedido:
            elegido = (k, etiquetas, s)
    k, etiquetas, s = elegido or mejor
    return k, etiquetas, s, opciones


# ---------------------------------------------------------------- datos

def _datos(bd: Session) -> dict:
    """Todo lo que se necesita por tienda en una pasada a la base (26 semanas, sin mayoreo)."""
    v = rr.ventana(bd, SEMANAS)
    if not v:
        raise ValueError("Todavía no hay venta cargada de SMNBI.")
    mitad = v.fin - timedelta(weeks=MITAD)
    reciente = case((VentaSemanal.semana > mitad, VentaSemanal.importe), else_=0)
    deptos: dict[str, dict[str, list[float]]] = {}  # tienda → depto → [26 semanas, recientes, anteriores]
    for tienda, depto, imp, rec in bd.execute(
            select(VentaSemanal.tienda, Producto.departamento, func.sum(VentaSemanal.importe), func.sum(reciente))
            .outerjoin(Producto, Producto.sku == VentaSemanal.sku).where(*v.filtro())
            .group_by(VentaSemanal.tienda, Producto.departamento)):
        imp, rec = float(imp or 0), float(rec or 0)
        d = deptos.setdefault(tienda, {}).setdefault(depto or SIN_DEPTO, [0.0, 0.0, 0.0])
        d[0] += imp
        d[1] += rec
        d[2] += imp - rec
    serie: dict[str, dict] = {}  # tienda → semana → (importe, piezas)
    margen: dict[str, list[float]] = {}  # tienda → [importe con costo, costo]
    con_costo = case((VentaSemanal.costo.is_not(None), VentaSemanal.importe), else_=0)
    for tienda, semana, imp, pz, imp_c, costo in bd.execute(
            select(VentaSemanal.tienda, VentaSemanal.semana, func.sum(VentaSemanal.importe), func.sum(rr.NETAS),
                   func.sum(con_costo), func.sum(VentaSemanal.costo))
            .where(*v.filtro()).group_by(VentaSemanal.tienda, VentaSemanal.semana)):
        serie.setdefault(tienda, {})[semana] = (float(imp or 0), float(pz or 0))
        m = margen.setdefault(tienda, [0.0, 0.0])
        m[0] += float(imp_c or 0)
        m[1] += float(costo or 0)
    surtido = dict(bd.execute(select(VentaSemanal.tienda, func.count(VentaSemanal.sku.distinct()))
                              .where(*v.filtro(), VentaSemanal.importe > 0).group_by(VentaSemanal.tienda)).all())
    info = {t.almacen: {"nombre": t.nombre, "region": t.region, "categoria": t.categoria, "lat": t.latitud,
                        "lon": t.longitud} for t in bd.scalars(select(Tienda))}
    return {"ventana": v, "mitad": mitad, "deptos": deptos, "serie": serie, "margen": margen, "surtido": surtido,
            "info": info}


def _metricas(d: dict, tienda: str) -> dict:
    """Los rasgos de ventas, tendencia y demografía de una tienda, en sus unidades (None si no se puede medir)."""
    semanas = d["serie"].get(tienda, {})
    ventas = [imp for imp, _ in semanas.values() if imp > 0]
    total = sum(imp for imp, _ in semanas.values())
    piezas = sum(pz for _, pz in semanas.values())
    m: dict = {"semanas": len(ventas)}
    m["venta_semanal"] = total / len(ventas) if ventas else None
    m["precio_pieza"] = total / piezas if piezas > 0 else None
    imp_c, costo = d["margen"].get(tienda, (0, 0))
    m["margen"] = (imp_c - costo) / imp_c * 100 if imp_c > 0 and costo > 0 else None
    m["surtido"] = float(d["surtido"].get(tienda, 0)) or None
    rec = [imp for s, (imp, _) in semanas.items() if s > d["mitad"] and imp > 0]
    ant = [imp for s, (imp, _) in semanas.items() if s <= d["mitad"] and imp > 0]
    m["cambio"] = ((sum(rec) / len(rec)) / (sum(ant) / len(ant)) - 1) * 100 \
        if len(rec) >= MIN_SEMANAS_MITAD and len(ant) >= MIN_SEMANAS_MITAD else None
    puntos = sorted((s, imp) for s, (imp, _) in semanas.items() if imp > 0)
    if len(puntos) >= MIN_SEMANAS:
        xs = [(s - puntos[0][0]).days / 7 for s, _ in puntos]
        ys = [imp for _, imp in puntos]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        m["pendiente"] = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx) / my * 100 if sxx and my else None
        m["variabilidad"] = statistics.pstdev(ys) / my * 100 if my else None
    else:
        m["pendiente"] = m["variabilidad"] = None
    i = d["info"].get(tienda, {})
    loc = demografia.cercana(i.get("lat"), i.get("lon")) if demografia.disponible() else None
    if loc:
        l, km = loc
        m |= {"poblacion": l["poblacion"], "pct_60_mas": l["pct_60_mas"], "pct_0_14": l["pct_0_14"],
              "nse": demografia.nse_por_clave().get(l["clave"]), "pct_sin_salud": l["pct_sin_salud"],
              "localidad": {"nombre": l["localidad"], "municipio": l["municipio"], "estado": l["estado"],
                            "km": round(km, 1)}}
    return m


def _columna(valores: list[float | None], log_: bool = False) -> list[float] | None:
    """Estandariza una columna (media 0, desviación 1, ±3). Lo que falta queda en 0 (el promedio)."""
    vals = [None if v is None else (math.log10(max(v, 1.0)) if log_ else v) for v in valores]
    presentes = [v for v in vals if v is not None]
    if len(presentes) < 2:
        return None
    media = sum(presentes) / len(presentes)
    desv = math.sqrt(sum((v - media) ** 2 for v in presentes) / len(presentes))
    if desv == 0:
        return None
    return [0.0 if v is None else max(-3.0, min(3.0, (v - media) / desv)) for v in vals]


def _mediana(vals) -> float | None:
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def _red(v: float | None, n: int = 1) -> float | None:
    return None if v is None else round(v, n)


def _explicar(bd: Session, perfiles: list[dict], criterios: dict[str, int], usuario_id: int | None) -> str | None:
    """Pone nombre, descripción y acciones a cada grupo con Ollama. Regresa la nota si no se pudo."""
    datos = []
    for p in perfiles:
        g = {"grupo": p["grupo"], "tiendas": p["tiendas"],
             "rasgos_que_lo_distinguen": [{"rasgo": x["nombre"], "unidad": x["unidad"], "grupo": x["grupo"],
                                           "empresa": x["empresa"]} for x in p["distintivos"]],
             "regiones": p["regiones"], "tiendas_abajo_de_sus_pares": p["abajo_de_pares"]}
        if "mezcla" in criterios:
            g["vende_de_mas_que_la_empresa"] = p["de_mas"]
            g["vende_de_menos_que_la_empresa"] = p["de_menos"]
        if "tendencia" in criterios:
            g["departamentos_donde_va_peor_que_la_empresa"] = p["caen_en"]
        if "demografia" in criterios:
            g["localidades"] = p["localidades"]
        datos.append(g)
    instrucciones = INSTRUCCIONES.format(criterios=", ".join(CRITERIOS[c] for c in criterios))
    try:
        r = puerta.ejecutar(bd, TAREA_IA, usuario_id=usuario_id, instrucciones=instrucciones, proveedor="ollama",
                            mensaje=json.dumps({"grupos": datos}, ensure_ascii=False), max_tokens=2500)
        respuesta = json.loads(r.texto[r.texto.find("{"):r.texto.rfind("}") + 1])
    except puerta.ErrorIA as e:
        return f"La IA local no redactó los grupos: {e}"[:500]
    except (ValueError, TypeError, AttributeError):
        return "La IA local contestó algo que no se pudo leer; los grupos quedan con número."
    por_grupo = {p["grupo"]: p for p in perfiles}
    escritos = 0
    for g in respuesta.get("grupos") or [] if isinstance(respuesta, dict) else []:
        if not isinstance(g, dict):
            continue
        try:
            p = por_grupo.get(int(g.get("grupo")))
        except (TypeError, ValueError):
            continue
        if not p or not str(g.get("nombre") or "").strip():
            continue  # no puede describir un grupo que no existe
        p["nombre"] = str(g["nombre"]).strip()[:60]
        p["descripcion"] = str(g.get("descripcion") or "").strip()[:400] or None
        p["acciones"] = [str(a).strip()[:200] for a in (g.get("acciones") or [])[:3] if str(a).strip()]
        escritos += 1
    if escritos < len(perfiles):
        return f"La IA local describió {escritos} de {len(perfiles)} grupos; los demás quedan con número."
    return None


def _pesos(criterios: dict[str, int] | None) -> dict[str, int]:
    pesos = {c: int(w) for c, w in (criterios or PESOS_POR_OMISION).items() if c in CRITERIOS and w and int(w) > 0}
    if not pesos:
        raise ValueError("Elige al menos un criterio para agrupar.")
    return pesos


def _alertas(t: str, otros: list[str], met: dict[str, dict]) -> list[dict]:
    """Abajo de sus pares: contra la mediana de las otras tiendas de su grupo."""
    if len(otros) < 2:
        return []
    a, m = [], met[t]
    v = _mediana(met[o]["venta_semanal"] for o in otros)
    if m["venta_semanal"] is not None and v and m["venta_semanal"] < PARES_VENTA * v:
        a.append({"tipo": "venta", "texto": f"Vende {round((1 - m['venta_semanal'] / v) * 100)} % menos por semana "
                  f"que la mediana de su grupo (${m['venta_semanal']:,.0f} contra ${v:,.0f})."})
    c = _mediana(met[o]["cambio"] for o in otros)
    if m["cambio"] is not None and c is not None and m["cambio"] <= c - PARES_CAMBIO_PTS:
        a.append({"tipo": "cambio", "texto": f"Su venta cambió {m['cambio']:+.0f} % en 13 semanas; su grupo, "
                  f"{c:+.0f} %."})
    g = _mediana(met[o]["margen"] for o in otros)
    if m["margen"] is not None and g is not None and m["margen"] <= g - PARES_MARGEN_PTS:
        a.append({"tipo": "margen", "texto": f"Margen de {m['margen']:.0f} % contra {g:.0f} % de su grupo."})
    return a


def calcular(bd: Session, corrida_id: int, grupos: int | None = None,
             criterios: dict[str, int] | None = None) -> None:
    c = bd.get(TiendaGrupoCorrida, corrida_id)
    try:
        pesos = _pesos(criterios)
        avisos = []
        if "demografia" in pesos and not demografia.disponible():
            del pesos["demografia"]
            avisos.append("Demografía no se usó: falta preparar el archivo del Censo 2020 del INEGI.")
            if not pesos:
                raise ValueError("Falta el archivo del Censo 2020 del INEGI para agrupar por demografía.")
        d = _datos(bd)
        info = d["info"]
        venta = {t: {dep: x[0] for dep, x in ds.items() if x[0] > 0} for t, ds in d["deptos"].items()}
        venta = {t: ds for t, ds in venta.items() if sum(ds.values()) > 0}
        met = {t: _metricas(d, t) for t in venta}
        fuera = {t: f"solo {met[t]['semanas']} semanas con venta" for t in venta if met[t]["semanas"] < MIN_SEMANAS}
        tiendas = sorted(t for t in venta if t not in fuera)
        if len(tiendas) < MIN_TIENDAS:
            raise ValueError(f"Se necesitan al menos {MIN_TIENDAS} tiendas con {MIN_SEMANAS} semanas de venta; "
                             f"hay {len(tiendas)}.")
        # Mezcla por departamento
        total_d = Counter()
        for t in tiendas:
            total_d.update(venta[t])
        gran_total = sum(total_d.values())
        deptos = sorted(x for x, v in total_d.items() if v / gran_total >= MIN_PARTICIPACION)
        if any(v / gran_total < MIN_PARTICIPACION for v in total_d.values()):
            deptos.append(OTROS)
        clave_d = {x: (x if x in deptos and x != OTROS else OTROS) for x in total_d}
        mezcla: dict[str, dict[str, float]] = {}
        for t in tiendas:
            tot = sum(venta[t].values())
            mz = {x: 0.0 for x in deptos}
            for x, v in venta[t].items():
                mz[clave_d[x]] += v / tot
            mezcla[t] = mz
        empresa_mz = {x: sum(v for y, v in total_d.items() if clave_d[y] == x) / gran_total for x in deptos}
        # Columnas estandarizadas por criterio; cada criterio pesa lo elegido sin importar cuántas columnas tenga
        columnas: dict[str, list[tuple[str, list[float]]]] = {k: [] for k in pesos}
        for r in RASGOS:
            if r.criterio in pesos:
                col = _columna([met[t].get(r.clave) for t in tiendas], r.log)
                if col:
                    columnas[r.criterio].append((r.clave, col))
        if "mezcla" in pesos:
            for x in deptos:
                col = _columna([mezcla[t][x] for t in tiendas])
                if col:
                    columnas["mezcla"].append((f"depto:{x}", col))
        for k in [k for k, cols in columnas.items() if not cols]:
            avisos.append(f"{CRITERIOS[k]} no se usó: no hay datos que distingan a las tiendas.")
            del columnas[k]
            del pesos[k]
        if not columnas:
            raise ValueError("Con los criterios elegidos no hay datos que distingan a las tiendas.")
        suma = sum(pesos.values())
        factor = {k: math.sqrt(pesos[k] / suma / len(cols)) for k, cols in columnas.items()}
        usadas = [(k, clave, col) for k, cols in columnas.items() for clave, col in cols]
        x = [[col[i] * factor[k] for k, _, col in usadas] for i in range(len(tiendas))]
        z = {clave: col for _, clave, col in usadas}  # sin peso, para describir
        k_, etiquetas, s, opciones = elegir_k(x, grupos)
        # Grupo 1 = el de más tiendas
        nuevo = {g: i + 1 for i, (g, _) in enumerate(Counter(etiquetas).most_common())}
        etiquetas = [nuevo[e] for e in etiquetas]
        miembros = {g: [i for i, e in enumerate(etiquetas) if e == g] for g in range(1, k_ + 1)}
        empresa = {r.clave: _mediana(met[t].get(r.clave) for t in tiendas) for r in RASGOS}
        # Cambio por departamento (promedio semanal de las 13 recientes contra las anteriores) para «va peor en»
        todas = {s_ for t in tiendas for s_ in d["serie"].get(t, {})}
        n_rec = max(1, sum(1 for s_ in todas if s_ > d["mitad"]))
        n_ant = sum(1 for s_ in todas if s_ <= d["mitad"])

        def cambio_deptos(ts):
            if n_ant < MIN_SEMANAS_MITAD:
                return {}
            rec, ant = Counter(), Counter()
            for t in ts:
                for x, (_, r_, a_) in d["deptos"][t].items():
                    rec[clave_d.get(x, OTROS)] += r_
                    ant[clave_d.get(x, OTROS)] += a_
            return {x: ((rec[x] / n_rec) / (ant[x] / n_ant) - 1) * 100 for x in deptos if ant[x] > 0}
        cambio_emp = cambio_deptos(tiendas)

        def describir(clave: str, ts: list[str]) -> dict:
            if clave.startswith("depto:"):
                dep = clave[6:]
                return {"criterio": "mezcla", "nombre": f"Venta en {dep}", "unidad": "% de la venta",
                        "grupo": _red(sum(mezcla[t][dep] for t in ts) / len(ts) * 100),
                        "empresa": _red(empresa_mz[dep] * 100)}
            r = POR_CLAVE[clave]
            return {"criterio": r.criterio, "nombre": r.nombre, "unidad": r.unidad,
                    "grupo": _red(_mediana(met[t].get(clave) for t in ts), 2 if r.unidad == "$" else 1),
                    "empresa": _red(empresa[clave], 2 if r.unidad == "$" else 1)}

        perfiles = []
        for g, idx in miembros.items():
            ts = [tiendas[i] for i in idx]
            prom = {x: sum(mezcla[t][x] for t in ts) / len(ts) for x in deptos}
            dif = sorted(((x, (prom[x] - empresa_mz[x]) * 100) for x in deptos), key=lambda y: y[1])
            medias = sorted(((clave, sum(col[i] for i in idx) / len(idx)) for clave, col in z.items()),
                            key=lambda y: -abs(y[1]))
            cg = cambio_deptos(ts)
            caen = sorted(((x, cg[x] - cambio_emp[x]) for x in cg if x in cambio_emp and x != OTROS
                           and empresa_mz[x] >= MIN_PARTICIPACION), key=lambda y: y[1])
            perfiles.append({
                "grupo": g, "nombre": f"Grupo {g}", "descripcion": None, "acciones": [], "tiendas": len(ts),
                "venta_semanal": round(sum(met[t]["venta_semanal"] or 0 for t in ts) / len(ts), 2),
                "distintivos": [describir(clave, ts) | {"z": round(mz_, 2)} for clave, mz_ in medias[:4]
                                if abs(mz_) >= 0.3],
                "valores": {r.clave: describir(r.clave, ts)["grupo"] for r in RASGOS},
                "mezcla": {x: round(prom[x] * 100, 1) for x in deptos},
                "de_mas": [{"departamento": x, "puntos": round(p, 1), "grupo_pct": round(prom[x] * 100, 1),
                            "empresa_pct": round(empresa_mz[x] * 100, 1)} for x, p in reversed(dif[-3:]) if p > 0.5],
                "de_menos": [{"departamento": x, "puntos": round(p, 1), "grupo_pct": round(prom[x] * 100, 1),
                              "empresa_pct": round(empresa_mz[x] * 100, 1)} for x, p in dif[:3] if p < -0.5],
                "caen_en": [{"departamento": x, "grupo_pct": round(cg[x], 1), "empresa_pct": round(cambio_emp[x], 1)}
                            for x, p in caen[:3] if p <= -5],
                "localidades": [f"{n}" for n, _ in Counter(
                    f"{met[t]['localidad']['nombre']}, {met[t]['localidad']['estado']}" for t in ts
                    if met[t].get("localidad")).most_common(4)],
                "regiones": [r for r, _ in Counter(info.get(t, {}).get("region") or "Sin región"
                                                   for t in ts).most_common(3)],
                "categorias": dict(Counter(info.get(t, {}).get("categoria") or "Sin categoría"
                                           for t in ts).most_common()),
                "abajo_de_pares": 0,
            })
        # Por tienda: qué tan típica es, en qué se sale de su grupo y si va abajo de sus pares
        for g, idx in miembros.items():
            centro = _centro([x[i] for i in idx])
            dist = {i: math.sqrt(_dist2(x[i], centro)) for i in idx}
            lo, hi = min(dist.values()), max(dist.values())
            ts = [tiendas[i] for i in idx]
            for i in idx:
                t = tiendas[i]
                difs = sorted(((clave, col[i] - sum(col[j] for j in idx) / len(idx)) for clave, col in z.items()),
                              key=lambda y: -abs(y[1]))
                rasgos = []
                for clave, dz in difs[:3]:
                    if abs(dz) < 0.75:
                        break
                    base = describir(clave, ts)
                    propio = (mezcla[t][clave[6:]] * 100 if clave.startswith("depto:") else met[t].get(clave))
                    rasgos.append({"nombre": base["nombre"], "unidad": base["unidad"], "tienda": _red(propio, 2),
                                   "grupo": base["grupo"]})
                alertas = _alertas(t, [o for o in ts if o != t], met)
                if alertas:
                    perfiles[g - 1]["abajo_de_pares"] += 1
                propias = {r.clave: _red(met[t].get(r.clave), 2) for r in RASGOS}
                bd.add(TiendaGrupo(corrida_id=corrida_id, almacen=t, grupo=g,
                                   tipicidad=round(100 * (1 - (dist[i] - lo) / (hi - lo))) if hi > lo else 100,
                                   rasgos=json.dumps(rasgos, ensure_ascii=False),
                                   alertas=json.dumps(alertas, ensure_ascii=False) if alertas else None,
                                   metricas=json.dumps(propias | {"localidad": met[t].get("localidad")},
                                                       ensure_ascii=False)))
        c.nota_ia = _explicar(bd, perfiles, pesos, c.iniciada_por)
        sin_localidad = [t for t in tiendas if not met[t].get("localidad")] if "demografia" in pesos else []
        c.tiendas, c.grupos, c.calidad = len(tiendas), k_, round(s, 3)
        c.perfiles = json.dumps(perfiles, ensure_ascii=False)
        c.contexto = json.dumps({
            "venta": d["ventana"].texto(), "criterios": pesos, "avisos": avisos, "departamentos": deptos,
            "empresa": {r.clave: _red(empresa[r.clave], 2) for r in RASGOS},
            "rasgos": [{"clave": r.clave, "criterio": r.criterio, "nombre": r.nombre, "unidad": r.unidad}
                       for r in RASGOS],
            "demografia": {"fuente": demografia.FUENTE, "sin_localidad": sin_localidad} if "demografia" in pesos
            else None,
            "fuera": fuera, "pedidos": grupos, "opciones": opciones}, ensure_ascii=False)
        c.estado, c.terminada_en = "completa", ahora()
        bd.commit()
        _limpiar(bd)
    except Exception as e:  # noqa: BLE001 - la corrida se cierra y dice qué pasó
        if not isinstance(e, ValueError):
            log.exception("Grupos de tiendas: la corrida %s falló", corrida_id)
        bd.rollback()
        c = bd.get(TiendaGrupoCorrida, corrida_id)
        c.estado, c.terminada_en, c.error = "fallida", ahora(), str(e)[:1000]
        bd.commit()


def _limpiar(bd: Session) -> None:
    viejas = list(bd.scalars(select(TiendaGrupoCorrida.corrida_id).where(TiendaGrupoCorrida.estado != "en_curso")
                             .order_by(TiendaGrupoCorrida.corrida_id.desc()).offset(CORRIDAS_GUARDADAS)))
    for i in viejas:
        bd.execute(delete(TiendaGrupo).where(TiendaGrupo.corrida_id == i))
        bd.execute(delete(TiendaGrupoCorrida).where(TiendaGrupoCorrida.corrida_id == i))
    bd.commit()


def en_curso(bd: Session) -> TiendaGrupoCorrida | None:
    return bd.scalar(select(TiendaGrupoCorrida).where(TiendaGrupoCorrida.estado == "en_curso"))


def ultima(bd: Session) -> TiendaGrupoCorrida | None:
    return bd.scalar(select(TiendaGrupoCorrida).where(TiendaGrupoCorrida.estado == "completa")
                     .order_by(TiendaGrupoCorrida.corrida_id.desc()))


def iniciar(bd: Session, usuario_id: int | None) -> TiendaGrupoCorrida:
    c = TiendaGrupoCorrida(estado="en_curso", iniciada_por=usuario_id, iniciada_en=ahora())
    bd.add(c)
    bd.flush()
    return c


def en_hilo(corrida_id: int, grupos: int | None = None, criterios: dict[str, int] | None = None) -> None:
    from core.bd import _fabrica

    def correr():
        with _fabrica()() as bd:
            calcular(bd, corrida_id, grupos, criterios)

    threading.Thread(target=correr, daemon=True, name=f"grupos-tiendas-{corrida_id}").start()


def cerrar_huerfanas(bd: Session) -> int:
    abiertas = list(bd.scalars(select(TiendaGrupoCorrida).where(TiendaGrupoCorrida.estado == "en_curso")))
    for c in abiertas:
        c.estado, c.terminada_en = "fallida", ahora()
        c.error = "La plataforma se reinició a medio cálculo; vuelve a calcular."
    bd.commit()
    return len(abiertas)
