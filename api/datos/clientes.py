"""Datos → Clientes: tipos de cliente según cómo compran (Diego, 2026-11-09: «con los datos que tenemos podemos crear una
sección de clientes para tener los perfiles de clientes?»; aprobó el plan).

De SMNBI sale un CSV por cliente y departamento (docs/sistemas/consulta_clientes.sql) SIN nombres ni números de cliente:
cada cliente trae un código que cambia en cada corrida. Las cuentas genéricas («público en general» de cada tienda) vienen
juntas en renglones GENERICO. Aquí:
1. Se agrupan los clientes con k-medias (Python puro, el mismo de Grupos de tiendas) por qué tan seguido compran, cuánto
   gastan, su ticket, el precio por pieza que pagan, cuántos meses compran y su mezcla por departamento. Para que alcance
   con cientos de miles de clientes, los grupos se buscan con una muestra y luego cada cliente va al grupo más cercano.
2. Cada tipo queda con su perfil (cuántos son, qué compran, en qué rango de precio, en qué regiones) y Ollama le pone
   nombre y lo explica (tarea datos.clientes_tipos, solo IA local).
3. «Buscar oportunidades» usa los tipos y el precio que paga nuestro cliente en cada departamento (para_oportunidades).
"""
import csv
import gzip
import io
import json
import logging
import math
import random
import threading
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.config import configuracion
from datos import grupos_tiendas as gt
from datos.modelos import ClienteCorrida, ClienteObjetivo, Tienda
from ia import puerta
from nucleo.modelos import ahora

log = logging.getLogger("smn.datos.clientes")

TAREA_IA = "datos.clientes_tipos"
GENERICO = "GENERICO"
COLUMNAS = ("cliente", "tienda_principal", "tiendas", "meses", "notas", "departamento", "notas_depto", "piezas", "importe")
MUESTRA = 1500  # clientes con los que se buscan los grupos (la silueta compara todos contra todos)
MIN_CLIENTES = 50
MIN_TIPOS, MAX_TIPOS = 3, 7
MAX_PEDIDOS = 8
DEPTOS_EN_MEZCLA = 5  # los departamentos que más venden entran a la mezcla; los demás van juntos en «Otros»
MIN_PARTE_TOPE = 1.0  # % mínimo de la venta identificada para que un departamento ponga tope de precio en «Buscar oportunidades»
MIN_PARTE_DEPTO = 0.05  # un departamento entra al perfil de precios del tipo si pesa al menos 5 % de lo que compra
DE_MAS_PTS = 5.0
CORRIDAS_GUARDADAS = 5
IVA = 1.16  # la venta de SMNBI viene sin IVA; los precios de internet lo traen
PERCENTILES = (25, 50, 75, 90, 95)
SEMILLA = 7

INSTRUCCIONES = """Eres analista comercial de Súper Mayoreo Naturista, cadena de tiendas naturistas en México.
Te doy tipos de cliente que salieron de agrupar a nuestros clientes identificados por cómo compran (enero a septiembre):
cuántos son, qué tan seguido compran, cuánto gastan, su ticket, el precio por pieza que pagan (sin IVA), qué departamentos
compran de más que el promedio y en qué regiones están sus tiendas.
Para cada tipo escribe:
- nombre: de 2 a 5 palabras que describan cómo compra (ej. «Cliente frecuente de suplementos»), sin nombres de personas;
- descripcion: una o dos oraciones con los números que lo distinguen;
- acciones: hasta 3 ideas cortas para Compras (qué productos buscarle y en qué rango de precio).
Usa solo los datos que te doy; no inventes edades, sexo, ingresos ni nada que no venga en los datos.
Contesta solo JSON: {"tipos": [{"tipo": 1, "nombre": "...", "descripcion": "...", "acciones": ["..."]}]}"""


# ---------------------------------------------------------------- archivo

def _carpeta() -> Path:
    d = Path(configuracion().archivos_ruta).resolve() / "clientes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def guardar_archivo(contenido: bytes) -> Path:
    """Se guarda solo el último archivo (comprimido) para poder recalcular con otro número de tipos."""
    ruta = _carpeta() / "clientes.csv.gz"
    with gzip.open(ruta, "wb") as f:
        f.write(contenido)
    return ruta


def hay_archivo() -> bool:
    return (_carpeta() / "clientes.csv.gz").exists()


def _texto(contenido: bytes) -> str:
    for cod in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            t = contenido.decode(cod)
            if cod != "utf-16" or "," in t[:200]:
                return t
        except UnicodeDecodeError:
            continue
    return contenido.decode("latin-1")


def _num(v: str) -> float:
    return float(v.strip().replace("$", "") or 0)


def leer(contenido: bytes) -> tuple[dict[str, dict], dict, int]:
    """(clientes, genéricos, renglones leídos). Acepta el archivo con o sin encabezado; se salta renglones vacíos o los
    avisos que a veces agrega sqlcmd. Error con el número de renglón si el archivo no es el de la consulta."""
    clientes: dict[str, dict] = {}
    gen = {"cuentas": 0, "notas": 0, "deptos": {}}
    leidos = 0
    for n, fila in enumerate(csv.reader(io.StringIO(_texto(contenido))), start=1):
        fila = [c.strip() for c in fila]
        if not fila or not any(fila) or fila[0].lower() == "cliente" or fila[0].startswith("("):
            continue
        if len(fila) != len(COLUMNAS):
            raise ValueError(f"El renglón {n} trae {len(fila)} columnas y deben ser {len(COLUMNAS)} "
                             f"({', '.join(COLUMNAS)}). Usa el archivo que sale de la consulta de Datos → Clientes.")
        try:
            codigo, tienda, depto = fila[0], fila[1], fila[5] or "Sin departamento"
            tiendas, meses, notas = int(_num(fila[2])), int(_num(fila[3])), int(_num(fila[4]))
            nd, piezas, importe = int(_num(fila[6])), _num(fila[7]), _num(fila[8])
        except ValueError:
            raise ValueError(f"El renglón {n} tiene un número que no se pudo leer: {', '.join(fila)[:200]}") from None
        leidos += 1
        if codigo == GENERICO:
            gen["cuentas"], gen["notas"] = tiendas, notas
            d = gen["deptos"].setdefault(depto, [0, 0.0, 0.0])
        else:
            c = clientes.setdefault(codigo, {"tienda": tienda, "meses": max(meses, 1), "notas": notas, "deptos": {}})
            d = c["deptos"].setdefault(depto, [0, 0.0, 0.0])
        d[0] += nd
        d[1] += piezas
        d[2] += importe
    if not leidos:
        raise ValueError("El archivo viene vacío.")
    return clientes, gen, leidos


# ---------------------------------------------------------------- cálculo

def _total(c: dict) -> tuple[float, float]:
    return sum(d[1] for d in c["deptos"].values()), sum(d[2] for d in c["deptos"].values())


def _mediana(vals: list[float]) -> float | None:
    vals = sorted(vals)
    if not vals:
        return None
    m = len(vals) // 2
    return vals[m] if len(vals) % 2 else (vals[m - 1] + vals[m]) / 2


def percentiles(pares: list[tuple[float, float]]) -> dict[str, float] | None:
    """Percentiles del precio por pieza pesados por piezas: (precio, piezas)."""
    pares = sorted((p, w) for p, w in pares if p > 0 and w > 0)
    total = sum(w for _, w in pares)
    if not pares or total <= 0:
        return None
    salida, acum, i = {}, 0.0, 0
    for q in PERCENTILES:
        meta = total * q / 100
        while i < len(pares) - 1 and acum + pares[i][1] < meta:
            acum += pares[i][1]
            i += 1
        salida[f"p{q}"] = round(pares[i][0], 2)
    return salida


def _rasgos(c: dict, deptos: list[str]) -> list[float]:
    piezas, importe = _total(c)
    mezcla = [c["deptos"].get(d, [0, 0, 0])[2] / importe for d in deptos]
    return [math.log(c["notas"] / c["meses"]), math.log1p(importe / c["meses"]), math.log1p(importe / max(c["notas"], 1)),
            math.log1p(importe / piezas) if piezas > 0 else 0.0, c["meses"] / 9, *mezcla, max(0.0, 1 - sum(mezcla))]


def _escalar(x: list[list[float]], base: list[list[float]]) -> list[list[float]]:
    columnas = list(zip(*base))
    medias = [sum(v) / len(v) for v in columnas]
    desv = [math.sqrt(sum((a - m) ** 2 for a in v) / len(v)) or 1.0 for v, m in zip(columnas, medias)]
    return [[(a - m) / s for a, m, s in zip(f, medias, desv)] for f in x]


def _elegir(x: list[list[float]], pedido: int | None) -> tuple[int, list[list[float]], float, list[dict]]:
    """Prueba de 3 a 7 tipos (o el que se pidió) y se queda con la mejor silueta. Regresa los centros."""
    opciones, mejor = [], None
    for k in ([pedido] if pedido else range(MIN_TIPOS, MAX_TIPOS + 1)):
        etiquetas, _ = gt.kmedias(x, k, semilla=SEMILLA)
        s = gt.silueta(x, etiquetas)
        opciones.append({"tipos": k, "calidad": round(s, 3)})
        if mejor is None or s > mejor[2] + 1e-9:
            mejor = (k, etiquetas, s)
    k, etiquetas, s = mejor
    centros = []
    for j in range(k):
        miembros = [p for p, e in zip(x, etiquetas) if e == j]
        centros.append(gt._centro(miembros) if miembros else x[0])
    return k, centros, s, opciones


def _cercano(p: list[float], centros: list[list[float]]) -> int:
    return min(range(len(centros)), key=lambda j: gt._dist2(p, centros[j]))


def calcular_tipos(clientes: dict[str, dict], gen: dict, regiones: dict[str, str], pedido: int | None = None) -> dict:
    """Todo el cálculo sin base de datos (para probarlo solo). Regresa resumen, perfiles y opciones."""
    validos = {k: c for k, c in clientes.items() if _total(c)[1] > 0 and c["notas"] > 0}
    if len(validos) < MIN_CLIENTES:
        raise ValueError(f"Hay {len(validos)} clientes con compras en el archivo; se necesitan al menos {MIN_CLIENTES}.")
    por_depto: Counter = Counter()
    for c in validos.values():
        for d, v in c["deptos"].items():
            por_depto[d] += v[2]
    deptos = [d for d, _ in por_depto.most_common(DEPTOS_EN_MEZCLA)]
    codigos = list(validos)
    azar = random.Random(SEMILLA)
    muestra = azar.sample(codigos, min(MUESTRA, len(codigos)))
    base = [_rasgos(validos[k], deptos) for k in muestra]
    x = _escalar(base, base)
    if pedido:
        pedido = max(2, min(pedido, MAX_PEDIDOS, len(x) // 3))
    k, centros, calidad, opciones = _elegir(x, pedido)

    # Cada cliente al tipo más cercano (con la misma escala de la muestra)
    columnas = list(zip(*base))
    medias = [sum(v) / len(v) for v in columnas]
    desv = [math.sqrt(sum((a - m) ** 2 for a in v) / len(v)) or 1.0 for v, m in zip(columnas, medias)]
    tipo_de: dict[str, int] = {}
    for cod, c in validos.items():
        r = _rasgos(c, deptos)
        tipo_de[cod] = _cercano([(a - m) / s for a, m, s in zip(r, medias, desv)], centros)

    total_imp = sum(por_depto.values())
    total_notas = sum(c["notas"] for c in validos.values())
    mezcla_total = {d: v / total_imp for d, v in por_depto.items()}
    perfiles = []
    for j in range(k):
        miembros = [validos[cod] for cod, t in tipo_de.items() if t == j]
        if not miembros:
            continue
        imp_d: Counter = Counter()
        precios: dict[str, list[tuple[float, float]]] = defaultdict(list)
        regs: Counter = Counter()
        for c in miembros:
            for d, (_, pz, imp) in c["deptos"].items():
                imp_d[d] += imp
                if pz > 0 and imp > 0:
                    precios[d].append((imp / pz, pz))
            regs[regiones.get(c["tienda"]) or "Sin región"] += 1
        imp = sum(imp_d.values())
        mezcla = {d: v / imp for d, v in imp_d.most_common()}
        perfiles.append({
            "tipo": j + 1,
            "nombre": None, "descripcion": None, "acciones": [],
            "clientes": len(miembros), "parte_clientes": round(len(miembros) / len(validos) * 100, 1),
            "notas": sum(c["notas"] for c in miembros),
            "parte_notas": round(sum(c["notas"] for c in miembros) / total_notas * 100, 1),
            "parte_venta": round(imp / total_imp * 100, 1),
            "compras_al_mes": round(_mediana([c["notas"] / c["meses"] for c in miembros]), 2),
            "gasto_al_mes": round(_mediana([_total(c)[1] / c["meses"] for c in miembros]), 2),
            "ticket": round(_mediana([_total(c)[1] / c["notas"] for c in miembros]), 2),
            "precio_por_pieza": round(_mediana([_total(c)[1] / _total(c)[0] for c in miembros if _total(c)[0] > 0]) or 0, 2),
            "meses_que_compra": _mediana([c["meses"] for c in miembros]),
            "mezcla": [{"departamento": d, "parte": round(p * 100, 1),
                        "empresa": round(mezcla_total.get(d, 0) * 100, 1)} for d, p in list(mezcla.items())[:6]],
            "de_mas": [d for d, p in mezcla.items() if (p - mezcla_total.get(d, 0)) * 100 >= DE_MAS_PTS],
            "precios": {d: percentiles(precios[d]) for d, p in mezcla.items() if p >= MIN_PARTE_DEPTO and percentiles(precios[d])},
            "regiones": [{"region": r, "parte": round(n / len(miembros) * 100, 1)} for r, n in regs.most_common(3)],
        })
    perfiles.sort(key=lambda p: -p["parte_venta"])

    todos: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for c in validos.values():
        for d, (_, pz, imp) in c["deptos"].items():
            if pz > 0 and imp > 0:
                todos[d].append((imp / pz, pz))
    gen_imp = sum(v[2] for v in gen["deptos"].values())
    resumen = {
        "clientes": len(validos), "renglones_fuera": len(clientes) - len(validos),
        "notas_identificadas": total_notas, "venta_identificada": round(total_imp, 2),
        "cuentas_genericas": gen["cuentas"], "notas_genericas": gen["notas"], "venta_generica": round(gen_imp, 2),
        "parte_notas_identificadas": round(total_notas / (total_notas + gen["notas"]) * 100, 1) if total_notas + gen["notas"] else None,
        "precios_por_departamento": {d: percentiles(todos[d]) for d, _ in por_depto.most_common() if percentiles(todos[d])},
        "precio_generico_por_departamento": {d: round(v[2] / v[1], 2) for d, v in gen["deptos"].items() if v[1] > 0},
        "parte_venta_por_departamento": {d: round(v / total_imp * 100, 2) for d, v in por_depto.most_common()} if total_imp else {},
        "departamentos_en_mezcla": deptos,
    }
    return {"resumen": resumen, "perfiles": perfiles, "opciones": opciones, "tipos": len(perfiles),
            "calidad": round(calidad, 3)}


def _explicar(bd: Session, perfiles: list[dict], usuario_id: int | None) -> str | None:
    datos = [{"tipo": p["tipo"], "clientes": p["clientes"], "parte_de_la_venta_identificada": p["parte_venta"],
              "compras_al_mes": p["compras_al_mes"], "gasto_al_mes": p["gasto_al_mes"], "ticket": p["ticket"],
              "precio_por_pieza_sin_iva": p["precio_por_pieza"], "meses_que_compra_de_9": p["meses_que_compra"],
              "compra_de_mas": p["de_mas"], "mezcla": p["mezcla"][:4], "regiones": p["regiones"]} for p in perfiles]
    mensaje = json.dumps({"tipos": datos}, ensure_ascii=False)
    try:
        r = puerta.ejecutar(bd, TAREA_IA, usuario_id=usuario_id, instrucciones=INSTRUCCIONES, proveedor="ollama",
                            mensaje=mensaje, max_tokens=2500,
                            contexto=puerta.ventana(INSTRUCCIONES, mensaje, salida=2500))
        respuesta = json.loads(r.texto[r.texto.find("{"):r.texto.rfind("}") + 1])
    except puerta.ErrorIA as e:
        return f"La IA local no redactó los tipos: {e}"[:500]
    except (ValueError, TypeError, AttributeError):
        return "La IA local contestó algo que no se pudo leer; los tipos quedan con número."
    por_tipo = {p["tipo"]: p for p in perfiles}
    escritos = 0
    for t in (respuesta.get("tipos") or []) if isinstance(respuesta, dict) else []:
        if not isinstance(t, dict):
            continue
        try:
            p = por_tipo.get(int(t.get("tipo")))
        except (TypeError, ValueError):
            continue
        if not p or not str(t.get("nombre") or "").strip():
            continue
        p["nombre"] = str(t["nombre"]).strip()[:60]
        p["descripcion"] = str(t.get("descripcion") or "").strip()[:400] or None
        p["acciones"] = [str(a).strip()[:200] for a in (t.get("acciones") or [])[:3] if str(a).strip()]
        escritos += 1
    if escritos < len(perfiles):
        return f"La IA local describió {escritos} de {len(perfiles)} tipos; los demás quedan con número."
    return None


def calcular(bd: Session, corrida_id: int, pedido: int | None = None) -> ClienteCorrida:
    c = bd.get(ClienteCorrida, corrida_id)
    try:
        c.paso = "Leyendo el archivo"
        bd.commit()
        with gzip.open(_carpeta() / "clientes.csv.gz", "rb") as f:
            clientes, gen, leidos = leer(f.read())
        c.renglones, c.paso = leidos, f"Buscando los tipos de cliente ({len(clientes):,} clientes)"
        bd.commit()
        regiones = {t.almacen: t.region for t in bd.scalars(select(Tienda))}
        r = calcular_tipos(clientes, gen, regiones, pedido)
        c.paso = "La IA local está poniendo nombre a cada tipo"
        bd.commit()
        c.nota_ia = _explicar(bd, r["perfiles"], c.iniciada_por)
        for p in r["perfiles"]:
            p["nombre"] = p["nombre"] or f"Tipo {p['tipo']}"
        c.clientes, c.tipos, c.calidad = r["resumen"]["clientes"], r["tipos"], r["calidad"]
        c.resumen = json.dumps({**r["resumen"], "opciones": r["opciones"]}, ensure_ascii=False)
        c.perfiles = json.dumps(r["perfiles"], ensure_ascii=False)
        c.estado, c.paso = "completa", None
    except Exception as e:  # noqa: BLE001
        log.exception("Clientes: falló el cálculo %s", corrida_id)
        bd.rollback()
        c = bd.get(ClienteCorrida, corrida_id)
        c.estado, c.paso = "fallida", None
        c.error = (str(e) if isinstance(e, ValueError) else f"No se pudo terminar: {e}")[:1000]
    c.terminada_en = ahora()
    bd.commit()
    _limpiar(bd)
    return c


# ---------------------------------------------------------------- corridas

def _limpiar(bd: Session) -> None:
    viejas = list(bd.scalars(select(ClienteCorrida.corrida_id).where(ClienteCorrida.estado != "en_curso")
                             .order_by(ClienteCorrida.corrida_id.desc()).offset(CORRIDAS_GUARDADAS)))
    if viejas:
        bd.execute(delete(ClienteCorrida).where(ClienteCorrida.corrida_id.in_(viejas)))
        bd.commit()


def en_curso(bd: Session) -> ClienteCorrida | None:
    return bd.scalar(select(ClienteCorrida).where(ClienteCorrida.estado == "en_curso"))


def ultima(bd: Session) -> ClienteCorrida | None:
    return bd.scalar(select(ClienteCorrida).where(ClienteCorrida.estado == "completa")
                     .order_by(ClienteCorrida.corrida_id.desc()))


def iniciar(bd: Session, usuario_id: int | None, archivo: str | None) -> ClienteCorrida:
    c = ClienteCorrida(estado="en_curso", iniciada_por=usuario_id, iniciada_en=ahora(), archivo=archivo,
                       paso="Empezando")
    bd.add(c)
    bd.flush()
    return c


def en_hilo(corrida_id: int, pedido: int | None = None) -> None:
    from core.bd import _fabrica

    def correr():
        with _fabrica()() as bd:
            calcular(bd, corrida_id, pedido)

    threading.Thread(target=correr, daemon=True, name=f"clientes-{corrida_id}").start()


def cerrar_huerfanas(bd: Session) -> int:
    abiertas = list(bd.scalars(select(ClienteCorrida).where(ClienteCorrida.estado == "en_curso")))
    for c in abiertas:
        c.estado, c.terminada_en, c.paso = "fallida", ahora(), None
        c.error = "La plataforma se reinició a medio cálculo; vuelve a calcular."
    bd.commit()
    return len(abiertas)


# ---------------------------------------------------------------- para «Buscar oportunidades»

def para_oportunidades(bd: Session) -> dict | None:
    """Lo que la IA de «Buscar oportunidades» necesita saber de nuestro cliente. None si no se han calculado los tipos."""
    c = ultima(bd)
    if not c or not c.perfiles:
        return None
    resumen = json.loads(c.resumen or "{}")
    tipos = [{"nombre": p["nombre"], "descripcion": p.get("descripcion"), "parte_de_la_venta": p["parte_venta"],
              "compras_al_mes": p["compras_al_mes"], "ticket": p["ticket"], "compra_de_mas": p["de_mas"],
              "precio_por_pieza_sin_iva_por_departamento": {d: {"de": v["p25"], "a": v["p75"]} for d, v in p["precios"].items()}}
             for p in json.loads(c.perfiles)]
    return {"tipos": tipos, "precios": precios_con_tope(resumen),
            "parte_notas_identificadas": resumen.get("parte_notas_identificadas")}


# ---------------------------------------------------------------- «Nuestro cliente» (nivel socioeconómico)

NIVELES = ("A/B", "C+", "C", "C-", "D+", "D", "E")  # niveles socioeconómicos como se usan en México, de mayor a menor


def borrador_objetivo(bd: Session) -> str | None:
    """Lo que los datos dicen de cómo compra nuestro cliente, para arrancar la descripción. Solo cifras calculadas."""
    c = ultima(bd)
    if not c or not c.perfiles:
        return None
    perfiles, resumen = json.loads(c.perfiles), json.loads(c.resumen or "{}")
    tickets = sorted(p["ticket"] for p in perfiles)
    veces = sorted(p["compras_al_mes"] for p in perfiles)
    partes = resumen.get("parte_venta_por_departamento") or {}
    precios = precios_con_tope(resumen)
    lineas = [f"Según sus compras en nuestras tiendas (clientes identificados, {resumen.get('parte_notas_identificadas')} % de las compras):",
              f"- Compra de {veces[0]:g} a {veces[-1]:g} veces al mes y gasta de ${tickets[0]:,.0f} a ${tickets[-1]:,.0f} por compra (sin IVA), según el tipo de cliente."]
    for d in list(precios)[:4]:
        lineas.append(f"- En {d.capitalize()} ({partes.get(d, 0):g} % de la venta) paga de ${precios[d]['p25']:,.0f} a "
                      f"${precios[d]['p75']:,.0f} por pieza; casi nada arriba de ${precios[d]['p90']:,.0f} (sin IVA).")
    return "\n".join(lineas)


def objetivo(bd: Session) -> dict | None:
    """Nivel y descripción de «Nuestro cliente». None si no se ha definido."""
    o = bd.get(ClienteObjetivo, 1)
    if not o:
        return None
    return {"nivel": o.nivel, "descripcion": o.descripcion, "actualizado_en": o.actualizado_en}


def objetivo_para_ia(bd: Session) -> dict | None:
    """Lo que recibe la IA de «Buscar oportunidades»: el nivel, lo que escribieron y lo que dicen las compras."""
    o = objetivo(bd)
    if not o:
        return None
    salida = {"nivel_socioeconomico": o["nivel"]}
    if (o["descripcion"] or "").strip():
        salida["descripcion_de_compras"] = o["descripcion"].strip()
    if (b := borrador_objetivo(bd)):
        salida["como_compra_segun_nuestras_ventas"] = b
    return salida


def guardar_objetivo(bd: Session, nivel: str, descripcion: str | None, usuario_id: int | None) -> dict:
    o = bd.get(ClienteObjetivo, 1)
    if not o:
        o = ClienteObjetivo(objetivo_id=1, nivel=nivel)
        bd.add(o)
    o.nivel, o.descripcion = nivel, (descripcion or "").strip() or None
    o.actualizado_por, o.actualizado_en = usuario_id, ahora()
    bd.flush()
    return objetivo(bd)


def precios_con_tope(resumen: dict) -> dict:
    """Rangos de precio que sí ponen tope: un departamento chico (p. ej. SUPLEMENTOS a $1 la pieza) quitaría todo lo suyo.
    Una corrida anterior sin la parte de cada departamento no pone tope hasta recalcular."""
    partes = resumen.get("parte_venta_por_departamento") or {}
    return {d: v for d, v in (resumen.get("precios_por_departamento") or {}).items() if partes.get(d, 0) >= MIN_PARTE_TOPE}


def tope_de_precio(perfil: dict | None, departamento: str | None, percentil: int) -> float | None:
    """Precio con IVA arriba del cual el producto ya no le queda a nuestro cliente en ese departamento (None = sin dato)."""
    if not perfil or not departamento or not percentil:
        return None
    from modulos.compras import coincidencia as co

    clave = co.normalizar(departamento)
    for d, p in perfil["precios"].items():
        if co.normalizar(d) == clave and p and p.get(f"p{percentil}"):
            return round(p[f"p{percentil}"] * IVA, 2)
    return None
