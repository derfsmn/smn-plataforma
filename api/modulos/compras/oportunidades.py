"""Radar de productos, fase 2: «Buscar oportunidades» (pedido de Diego, 2026-10-27: «un botón donde le piquemos y junte
toda la información de lo que tenemos y nos recomiende productos que no tenemos y que deberíamos buscar meter»).

Diego (2026-10-28): «queremos productos que sí o sí vayan a vender», pero no solo lo que ya teníamos («los quitamos
por algo»): también lo nuevo de las tendencias. Por eso cada recomendación es un producto concreto (marca o
presentación) que no tenemos, con una prueba de que YA se vende, y de preferencia ligado a una tendencia:
- V: más vendidos en internet: un agente busca, guiado por las tendencias del radar, productos que están en las listas
  de más vendidos de México (Amazon, Mercado Libre, farmacias y tiendas naturistas) y trae la prueba de venta (lugar en
  la lista, «+5 mil vendidos», reseñas) con su liga.
- C: lo que venden dos o más tiendas de la competencia y no tenemos (Google Shopping por subcategoría; solo si se pide,
  cuesta DataForSEO).
- T: señales del radar de tendencias. Solo respaldan: una tendencia sola no es un producto que se venda.
- H: huecos del surtido en SMNBI (subcategorías que venden mucho por producto con pocas opciones). Solo respaldan.
- R/K: reglas de rechazo y casos rechazados de Compras: lo que NO se debe recomendar.
Los productos que descontinuamos ya no entran: se quitaron por algo.

La IA propone hasta 20 productos; una propuesta sin una prueba de venta (V o C) que exista, o que ya vendemos, se
descarta. Sin IA se arma una lista directa de V y C. Cada recomendación lleva la foto que su propia página dice que es
suya (o la de Google Shopping) y se manda al semáforo como idea de Compras.
"""
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from itertools import zip_longest
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
from statistics import median

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from core.config import configuracion
from datos import clientes as cl
from datos.modelos import Producto
from ia import puerta
from modulos.compras import coincidencia as co
from modulos.compras import dataforseo as dfs
from modulos.compras import imagenes as img
from modulos.compras import precios as pc
from modulos.compras import radar
from modulos.compras import radar_productos as rp
from modulos.compras import realidad_producto as rr
from modulos.compras.modelos import RadarSenal
from modulos.compras.modelos_conocimiento import ConocimientoCaso, ConocimientoRegla
from modulos.compras.modelos_precios import PrecioCorrida
from modulos.compras.modelos_productos import Oportunidad, OportunidadCorrida, ProductoIdea
from nucleo.modelos import ahora

log = logging.getLogger("smn.compras.oportunidades")

TAREA_IA = "compras.oportunidades"
TAREA_VENDIDOS = "compras.oportunidades_novedades"  # mismo código de tarea; ahora busca los más vendidos
MAX_VENDIDOS = 8  # por búsqueda (una por tendencia o por departamento)
AGENTES_A_LA_VEZ = 4
EVALUACIONES_A_LA_VEZ = 3
# Con búsqueda web el razonamiento y las búsquedas cuentan dentro del tope de OpenAI; con 12,000 a veces no alcanzaba
MAX_TOKENS_AGENTE = 32000
MAX_OPORTUNIDADES = 20
MAX_TENDENCIAS = 30
PRUEBAS = "VC"  # fuentes que prueban que el producto ya se vende
APOYOS = "TH"  # respaldan, pero solas no bastan
MAX_HUECOS = 15
MAX_DESCONTINUADOS = 15
MAX_COMPETENCIA = 40
POR_CONSULTA = 3  # productos de la competencia que se guardan por subcategoría buscada
MAX_DATOS_COMPETENCIA = 90
MIN_TIENDAS = 2  # tiendas distintas (un marketplace cuenta una vez) para tomarlo como competencia
COBERTURA_TENEMOS = 0.75  # parte de las palabras de nuestro producto que deben estar en el título para decir «lo tenemos»
PRIORIDADES = ("alta", "media", "baja")

INSTRUCCIONES = """Eres comprador senior de Súper Naturista, cadena de tiendas naturistas en México. Compras te pide
productos NUEVOS para nosotros que SÍ O SÍ se van a vender: que ya se venden bien en México, vayan o no con una
tendencia. Nada de ideas sueltas ni de productos que ya teníamos.
Te doy datos con una clave cada uno:
- V = productos que están en las listas de más vendidos de tiendas en internet en México, con su prueba de venta. Cada
  uno dice por qué puerta llegó: «tendencia» (se buscó con una tendencia del radar) o «mas_vendido» (es de lo más
  vendido de uno de nuestros departamentos, aunque no esté de moda). Las dos puertas valen igual;
- C = productos que venden dos o más tiendas de la competencia y nosotros no;
- T = tendencias del radar. Solo respaldan: una tendencia no es un producto;
- H = huecos de nuestro surtido: subcategorías que venden mucho por producto con pocas opciones. Solo respaldan.
R y K son reglas y casos que Compras ya rechazó: NO recomiendes nada que caiga en ellos.
Si te doy «nuestros_clientes» (tipos de cliente que salieron de cómo compran en nuestras tiendas y el precio por pieza
sin IVA que paga cada uno por departamento), propón solo lo que le compraría alguno de esos tipos y a un precio cercano al
que paga; en tipo_cliente pon el nombre del tipo que lo compraría.
Si te doy «cliente_objetivo» (el nivel socioeconómico al que le vendemos, cómo lo describe Compras y cómo compra según
nuestras ventas), revisa cada producto contra él y dilo en «encaje»: "si" si ese cliente lo compraría (lo necesita o lo
quiere, y lo puede pagar), "dudoso" si no queda claro, "no" si es para otro público (muy caro para su bolsillo, de lujo
o de nicho que ese cliente no busca). En «encaje_motivo» di por qué en una oración, con el dato en que te basas. No
dejes fuera un producto por esto: inclúyelo con encaje "no" y su motivo, para que Compras vea qué se quitó.
Somos una tienda naturista física: suplementos, herbolaria, vitaminas, alimentos saludables y cuidado personal natural, y
algunos abarrotes saludables, a precio accesible. NO propongas lo que no venderíamos: comida chatarra o carnes, dulces
comerciales, aceites para auto, libros, ropa, aparatos, productos de importación cara, etc., aunque venga en los datos.
Propón hasta 20 productos concretos que NO tenemos. Cada uno DEBE tener al menos una prueba de venta (V o C). Incluye
productos de las dos puertas: no descartes un más vendido por no ir con una tendencia. Ordénalos del más seguro al
menos seguro. Para cada uno:
- nombre: el producto como se pide a un proveedor: marca (si viene en el dato), ingrediente, forma y presentación
  (ej. «Magnesio citrato 500 mg 120 cápsulas»), nunca una categoría ni una idea;
- por_que: una o dos oraciones que citen la prueba de venta con sus números (lugar en la lista, vendidos, reseñas,
  tiendas que lo venden), la tendencia o el hueco si aplica, y por qué lo compraría nuestro cliente;
- evidencia: las claves que lo respaldan (V o C y, si aplica, T y H);
- prioridad: alta si tiene prueba de venta fuerte (top 10 de una lista de más vendidos en México) y además llegó por las
  dos puertas, o también lo vende la competencia (C), o cae en un hueco (H); media si tiene una prueba de venta sólida;
  baja si la prueba es débil.
No inventes ventas, precios ni pruebas. No repitas productos.
Contesta solo JSON: {"oportunidades": [{"nombre": "...", "marca": null, "departamento": "...", "subcategoria": "...",
"forma": "...", "por_que": "...", "evidencia": ["H2", "T5"], "prioridad": "alta", "tipo_cliente": null, "encaje": "si", "encaje_motivo": "..."}]}"""


@dataclass
class Fuentes:
    datos: dict[str, dict] = field(default_factory=dict)  # clave -> dato
    notas: list[str] = field(default_factory=list)
    costo_usd: Decimal = Decimal("0")

    def agregar(self, letra: str, dato: dict) -> str:
        clave = f"{letra}{sum(1 for k in self.datos if k[0] == letra) + 1}"
        self.datos[clave] = {"clave": clave, **dato}
        return clave

    def de(self, letra: str) -> list[dict]:
        return [d for k, d in self.datos.items() if k[0] == letra]


# ---------------------------------------------------------------- catálogo

class Catalogo:
    """Índice de palabras de los productos activos, para saber rápido si algo ya lo tenemos."""

    def __init__(self, bd: Session):
        self.productos = list(bd.scalars(select(Producto).where(Producto.activo == true())))
        self.suyas = {p.producto_id: rp.palabras(p.descripcion) for p in self.productos}
        self.marcas = {p.producto_id: rp.palabras(p.marca) for p in self.productos}
        self.indice: dict[str, set[int]] = defaultdict(set)
        for pid, ps in self.suyas.items():
            for x in ps:
                self.indice[x].add(pid)
        self.por_id = {p.producto_id: p for p in self.productos}

    def con_palabras(self, ps: set[str], minimo: int = 2) -> list[Producto]:
        cuenta = Counter(pid for x in ps for pid in self.indice.get(x, ()))
        return [self.por_id[pid] for pid, n in cuenta.items() if n >= min(minimo, len(ps))]

    def lo_tenemos(self, titulo: str) -> Producto | None:
        t = rp.palabras(titulo)
        for p in self.con_palabras(t, 1):
            suyas = self.suyas[p.producto_id]
            marca = self.marcas[p.producto_id]
            if len(suyas) < 2 or (marca and not marca & t):
                continue
            if len(suyas & t) / len(suyas) >= COBERTURA_TENEMOS:
                return p
        return None


# ---------------------------------------------------------------- fuentes

def tendencias(bd: Session, f: Fuentes, cat: Catalogo) -> None:
    desde = ahora().date() - timedelta(days=rp.DIAS_SENALES)
    senales = bd.scalars(select(RadarSenal).where(RadarSenal.estado != "descartada", RadarSenal.ultima_vez >= desde,
                                                  RadarSenal.nivel.in_(("ALTA", "MEDIA")))).all()
    senales = sorted(senales, key=lambda s: (-rp.NIVEL_SENAL.get(s.nivel, 50), -s.veces_reportada))[:MAX_TENDENCIAS]
    for s in senales:
        tenemos = cat.con_palabras(rp.palabras(s.titulo))
        f.agregar("T", {"titulo": s.titulo, "descripcion": (s.descripcion or "")[:300], "nivel": s.nivel,
                        "tipo": s.tipo, "veces_reportada": s.veces_reportada, "vista_por_ultima_vez": str(s.ultima_vez),
                        "productos_que_tenemos_con_esas_palabras": len(tenemos),
                        "ejemplos": [p.descripcion for p in tenemos[:3]]})
    if not senales:
        f.notas.append("Tendencias: el radar no tiene señales altas o medias de los últimos 6 meses.")


def _por_subcategoria(cat: Catalogo) -> dict[str, list[Producto]]:
    grupos: dict[str, list[Producto]] = defaultdict(list)
    for p in cat.productos:
        if p.subcategoria:
            grupos[p.subcategoria].append(p)
    return grupos


def huecos(bd: Session, f: Fuentes, cat: Catalogo, v: rr.Ventana) -> list[str]:
    """Agrega los huecos y regresa las subcategorías que más venden (para buscar a la competencia)."""
    venta = rr.venta_por_sku(bd, v)
    grupos = _por_subcategoria(cat)
    tipica = rp._tamano_tipico(bd) or 1
    filas = []
    for sub, prods in grupos.items():
        con = [venta[p.sku] for p in prods if p.sku in venta]
        if not con:
            continue
        al_mes = sum(x.al_mes for x in con)
        filas.append((sub, prods, len(con), al_mes, al_mes / len(con)))
    if not filas:
        f.notas.append("Huecos: no hay venta de SMNBI ligada a productos con subcategoría.")
        return []
    filas.sort(key=lambda x: -x[4])
    medianas = median(x[4] for x in filas)
    elegidas = []
    for sub, prods, n_venta, al_mes, por_sku in filas:
        if len(elegidas) >= MAX_HUECOS:
            break
        dias = rr.dias_inventario(bd, v, sub)
        pocos = len(prods) <= tipica
        se_acaba = dias is not None and dias[0] < 45
        if por_sku < medianas or not (pocos or se_acaba):
            continue
        depto = Counter(p.departamento for p in prods if p.departamento).most_common(1)
        top = sorted(prods, key=lambda p: -(venta[p.sku].al_mes if p.sku in venta else 0))[:3]
        f.agregar("H", {"subcategoria": sub, "departamento": depto[0][0] if depto else None,
                        "productos_activos": len(prods), "subcategoria_tipica_tiene": round(tipica),
                        "piezas_al_mes": round(al_mes), "piezas_al_mes_por_producto": round(por_sku, 1),
                        "dias_de_inventario": round(dias[0]) if dias else None,
                        "los_que_mas_venden": [p.descripcion for p in top]})
        elegidas.append(sub)
    if not elegidas:
        f.notas.append("Huecos: ninguna subcategoría vende más que la mediana con pocas opciones o poco inventario.")
    return [sub for sub, *_ in filas]


def rechazos(bd: Session, f: Fuentes) -> None:
    for r in bd.scalars(select(ConocimientoRegla).where(ConocimientoRegla.activa == true(),
                                                       ConocimientoRegla.tipo == "rechazo")):
        f.datos[f"R{r.regla_id}"] = {"clave": f"R{r.regla_id}", "regla_de_rechazo": r.criterio,
                                     "departamento": r.departamento, "descripcion": r.descripcion}
    for c in bd.scalars(select(ConocimientoCaso).where(ConocimientoCaso.decision == "rechazado")):
        f.datos[f"K{c.caso_id}"] = {"clave": f"K{c.caso_id}", "producto_rechazado": c.producto, "motivo": c.motivo}


def _propio(vendedor: str) -> bool:
    v = co.normalizar(vendedor).replace(" ", "")
    propios = [co.normalizar(d).replace(" ", "").split(".")[0] for d in configuracion().precios_dominios_propios.split(",")]
    return any(d and d in v for d in propios) or "supernaturista" in v


MARKETPLACES = (("ebay", "eBay"), ("amazon", "Amazon"), ("mercado libre", "Mercado Libre"), ("mercadolibre", "Mercado Libre"),
                ("walmart", "Walmart"), ("aliexpress", "AliExpress"), ("liverpool", "Liverpool"), ("coppel", "Coppel"))


def tienda_de(vendedor: str) -> str:
    """Los vendedores de un marketplace cuentan como una sola tienda («eBay - x» y «eBay - y» son eBay)."""
    v = co.normalizar(vendedor)
    return next((nombre for clave, nombre in MARKETPLACES if clave in v), vendedor.split(" - ")[0].strip()[:80])


def _raiz(p: str) -> str:
    return p[:5]


def vocabulario(prods: list[Producto], consulta: str) -> set[str]:
    """Palabras de nuestros productos de la subcategoría, sin las de la búsqueda: con eso se sabe si un resultado de
    Google es del mismo tipo de producto («aceite de coco» sí; «aceite Mobil» para auto no)."""
    quitar = {_raiz(x) for x in rp.palabras(consulta)}
    return {_raiz(x) for p in prods for x in rp.palabras(p.descripcion) if _raiz(x) not in quitar}


def competencia(bd: Session, f: Fuentes, cat: Catalogo, subcategorias: list[str], corrida: OportunidadCorrida) -> None:
    if falta := dfs.configurado():
        f.notas.append("Competencia: no se buscó, falta " + ", ".join(falta) + " en Configuración.")
        return
    consultas = [s for s in subcategorias if len(s.strip()) >= 4][:configuracion().oportunidades_busquedas]
    if not consultas:
        f.notas.append("Competencia: no hay subcategorías con venta para buscar.")
        return
    cfg = configuracion()
    pcorrida = PrecioCorrida(fecha=pc.hoy_local(), origen=pc.OPORTUNIDAD, estado="en_curso", productos=len(consultas),
                             lista=json.dumps({"oportunidades": corrida.corrida_id}, ensure_ascii=False))
    bd.add(pcorrida)
    bd.commit()
    try:
        tareas = [{"keyword": s.lower(), "depth": cfg.precios_profundidad, "tag": str(n)} for n, s in enumerate(consultas)]
        ids = dfs.enviar(bd, pcorrida, "productos", tareas)
        total = len(ids)
        resultados = dfs.recoger("productos", ids, avance=lambda faltan: _paso(
            bd, corrida, f"Buscando lo que vende la competencia en Google Shopping ({total - len(faltan)} de {total} "
                         "subcategorías listas; espera máxima 15 min)"))
        pcorrida.estado = "completa"
    except dfs.ErrorDataForSEO as e:
        f.notas.append(f"Competencia: no se buscó, {e}")
        pcorrida.estado, pcorrida.error = "fallida", str(e)[:1000]
        resultados = {}
    pcorrida.terminado_en = ahora()
    f.costo_usd += pcorrida.costo_usd or Decimal("0")
    bd.commit()

    por_sub = _por_subcategoria(cat)
    fuera = 0
    for tag, items in sorted(resultados.items(), key=lambda x: int(x[0])):
        if isinstance(items, str):
            f.notas.append(f"Competencia ({consultas[int(tag)]}): {items}.")
            continue
        grupos: dict[str, dict] = {}
        vocab = vocabulario(por_sub.get(consultas[int(tag)], []), consultas[int(tag)])
        for item in items:
            c = co.candidato_de(item)
            precio = pc._decimal(item.get("price"))
            vendedor = str(item.get("seller") or item.get("source") or "").strip()
            if not c or not vendedor or _propio(vendedor) or (item.get("currency") or "MXN").upper() != "MXN":
                continue
            if cat.lo_tenemos(c.titulo):
                continue
            if vocab and not {_raiz(x) for x in rp.palabras(c.titulo)} & vocab:
                fuera += 1
                continue  # no se parece a nada de lo que vendemos en esa subcategoría
            g = grupos.setdefault(co.normalizar(c.titulo), {"titulo": c.titulo[:200], "vendedores": set(), "precios": [],
                                                             "foto": None})
            g["vendedores"].add(tienda_de(vendedor))
            g["foto"] = g["foto"] or img.de_candidato(item) or item.get("thumbnail")
            if precio and precio > 0:
                g["precios"].append(precio)
        mejores = [g for g in sorted(grupos.values(), key=lambda g: -len(g["vendedores"]))
                   if len(g["vendedores"]) >= MIN_TIENDAS][:POR_CONSULTA]
        for g in mejores:
            if len(f.de("C")) >= MAX_DATOS_COMPETENCIA:
                break
            f.agregar("C", {"titulo": g["titulo"], "buscado_como": consultas[int(tag)],
                            "tiendas_que_lo_venden": len(g["vendedores"]), "tiendas": sorted(g["vendedores"])[:4],
                            "precio_mediana": float(median(g["precios"])) if g["precios"] else None,
                            "foto": g["foto"]})
    if fuera:
        f.notas.append(f"Competencia: se quitaron {fuera} resultado(s) de Google que no se parecen a lo que vendemos en esa "
                       "subcategoría (por ejemplo, aceite para auto en «aceites»).")
    if not f.de("C") and resultados:
        f.notas.append(f"Competencia: nada de lo que salió en Google Shopping está en {MIN_TIENDAS} tiendas o más y no lo "
                       "tenemos.")


_REGLAS_AGENTE = f"""Para cada producto trae la prueba de venta que viste: lugar en la lista de más vendidos, la etiqueta «Más
vendido», cuántos vendidos dice la página (ej. «+5 mil vendidos») o cuántas reseñas tiene.
Reglas:
- Producto concreto: marca, ingrediente, forma y presentación. Nada de categorías ni ingredientes sueltos.
- Solo lo que viste en los resultados de tu búsqueda, con la liga exacta de la página donde está la prueba. No inventes
  ligas, lugares ni cifras.
- Nada de lo que ya vendemos (te doy nuestras subcategorías y los productos que más vendemos).
- Nada que no venda una tienda naturista (comida chatarra, aparatos, ropa, medicamentos de patente).
- No afirmes propiedades médicas.
- Si te doy «precio_que_paga_nuestro_cliente», busca productos en ese rango de precio: nuestro cliente difícilmente
  compra algo mucho más caro.
- Si te doy «cliente_objetivo» (nivel socioeconómico al que le vendemos y cómo compra), busca productos para ese
  cliente: nada de lujo ni de nicho que no sea para él.
- Máximo {{maximo}}.
Responde solo JSON: {{{{"productos": [{{{{"nombre": "marca + producto + presentación", "marca": "...",
"prueba_de_venta": "lo que viste: lugar 3 en más vendidos de suplementos de Amazon México, +10 mil vendidos, 4,500 reseñas",
"tienda": "dónde lo viste", "precio": 0, "url": "https://..."}}}}]}}}}"""

_DONDE = """Dónde buscar: listas de «más vendidos» de Amazon México y Mercado Libre, los más vendidos de farmacias (San
Pablo, Farmacias Guadalajara, Benavides, del Ahorro) y de tiendas naturistas o de suplementos en México."""

# Puerta «por tendencia» (Diego, 2026-11-09): una búsqueda por cada tendencia fuerte del radar
INSTRUCCIONES_TENDENCIA = f"""{radar.CONTEXTO_SMN}

Eres comprador senior de una cadena de tiendas naturistas en México. Te doy UNA tendencia del radar. Busca en internet
productos concretos que van con esa tendencia y que HOY ya se venden mucho en México. No quiero noticias, lanzamientos
sin venta ni apuestas: si no encuentras productos con prueba de venta para esta tendencia, contesta la lista vacía.
{_DONDE}
""" + _REGLAS_AGENTE.format(maximo=5)

# Puerta «por lo más vendido» (Diego, 2026-11-09: «pueden ser los productos naturistas más vendidos» aunque no estén
# en ninguna tendencia): una búsqueda por cada departamento que más vendemos
INSTRUCCIONES_DEPARTAMENTO = f"""{radar.CONTEXTO_SMN}

Eres comprador senior de una cadena de tiendas naturistas en México. Te doy UNO de nuestros departamentos. Busca en
internet los productos naturistas de ese departamento que HOY más se venden en México y nosotros no tenemos, estén o no
de moda. No quiero noticias, lanzamientos sin venta ni apuestas: solo productos con prueba de venta.
{_DONDE}
""" + _REGLAS_AGENTE.format(maximo=6)

# Corridas anteriores al 9 nov 2026 usaban una sola búsqueda mezclada; se deja el nombre para la pantalla de instrucciones
INSTRUCCIONES_VENDIDOS = INSTRUCCIONES_DEPARTAMENTO


def _top_nuestros(bd: Session, cat: Catalogo, n: int = 60) -> list[str]:
    """Lo que más vendemos, para que el agente no lo proponga y sepa qué tipo de producto se vende en SMN."""
    v = rr.ventana(bd)
    if not v:
        return []
    venta = rr.venta_por_sku(bd, v)
    activos = {p.sku: p for p in cat.productos}
    top = sorted((s for s in venta if s in activos), key=lambda s: -venta[s].al_mes)[:n]
    return [activos[s].descripcion for s in top if activos[s].descripcion]


INSTRUCCIONES_A_JSON = """Te paso lo que escribió un agente que buscó productos en internet. Pásalo a JSON tal cual: no
agregues productos, ligas, cifras ni pruebas que no estén en el texto, y deja fuera los que no traigan liga.
Responde solo JSON: {"productos": [{"nombre": "...", "marca": null, "prueba_de_venta": "...", "tendencia": null,
"tienda": "...", "precio": null, "url": "https://..."}]}"""


def _lista_del_agente(bd: Session, r, f: Fuentes) -> dict | None:
    """La lista del agente. Si contestó en texto y no en JSON (29 oct: «La IA no respondió JSON»), otra llamada sin
    internet lo pasa a JSON sin agregar nada; las ligas se siguen comprobando contra lo que el agente sí buscó."""
    try:
        return radar._json_de(r.texto) or {}
    except (ValueError, TypeError):
        pass
    texto = (r.texto or "").strip()
    log.info("Oportunidades: el agente no contestó JSON (completa=%s, %s caracteres): %s",
             getattr(r, "completa", None), len(texto), texto[:500])
    if not texto:
        f.notas.append("Más vendidos: el agente se quedó sin espacio antes de contestar."
                       if not getattr(r, "completa", True) else "Más vendidos: el agente no contestó nada.")
        return None
    try:
        r2 = puerta.ejecutar(bd, TAREA_VENDIDOS, usuario_id=None, instrucciones=INSTRUCCIONES_A_JSON,
                             mensaje=texto[:40000], max_tokens=8000, esfuerzo="low")
        datos = radar._json_de(r2.texto) or {}
    except (puerta.ErrorIA, ValueError, TypeError, AttributeError) as e:
        f.notas.append(f"Más vendidos: el agente contestó en texto y no se pudo pasar a la lista ({str(e)[:200]}).")
        return None
    f.notas.append("Más vendidos: el agente contestó en texto; se pasó a la lista sin agregar nada.")
    return datos


def departamentos_que_mas_venden(bd: Session, cat: Catalogo, n: int) -> list[str]:
    """Nuestros departamentos ordenados por venta (SMNBI); sin venta cargada, por cuántos productos activos tienen."""
    v = rr.ventana(bd)
    venta = rr.venta_por_sku(bd, v) if v else {}
    suma: Counter = Counter()
    for p in cat.productos:
        if p.departamento:
            suma[p.departamento] += venta[p.sku].al_mes if p.sku in venta else (0 if venta else 1)
    return [d for d, x in suma.most_common() if x > 0][:n]


def _encargos(bd: Session, f: Fuentes, cat: Catalogo) -> list[dict]:
    """Una búsqueda del agente por cada tendencia fuerte y por cada departamento que más vendemos."""
    cfg = configuracion()
    base = {"subcategorias_que_ya_vendemos": sorted({p.subcategoria for p in cat.productos if p.subcategoria})[:200],
            "lo_que_mas_vendemos": _top_nuestros(bd, cat)}
    if (objetivo := cl.objetivo_para_ia(bd)):
        base["cliente_objetivo"] = objetivo
    salida = [{"puerta": "tendencia", "tema": d["titulo"], "instrucciones": INSTRUCCIONES_TENDENCIA,
               "mensaje": {"tendencia": d["titulo"], "de_que_trata": d["descripcion"], **base}}
              for d in f.de("T")[:cfg.oportunidades_tendencias]]
    perfil = cl.para_oportunidades(bd)
    salida += [{"puerta": "mas_vendido", "tema": d, "instrucciones": INSTRUCCIONES_DEPARTAMENTO,
                "mensaje": {"departamento": d, **base, **_rango(perfil, d)}}
               for d in departamentos_que_mas_venden(bd, cat, cfg.oportunidades_departamentos)]
    return salida


def _rango(perfil: dict | None, departamento: str) -> dict:
    """Lo que paga por pieza la mitad de en medio de nuestros clientes en el departamento, con IVA (Datos → Clientes)."""
    p25 = cl.tope_de_precio(perfil, departamento, 25)
    p75 = cl.tope_de_precio(perfil, departamento, 75)
    return {"precio_que_paga_nuestro_cliente": {"de": p25, "a": p75, "moneda": "MXN con IVA"}} if p25 and p75 else {}


INSTRUCCIONES_LEER_VENDIDOS = f"""{radar.CONTEXTO_SMN}

Eres comprador senior de una cadena de tiendas naturistas en México. Te doy el texto de UNA página de internet que salió
en Google al buscar lo que más se vende de un tema. Saca de la página hasta 3 productos concretos que la página muestre
con prueba de venta: lugar en una lista de más vendidos, «más vendido», número de vendidos, número de reseñas.
- nombre: marca + ingrediente + forma + presentación, como se le pide a un proveedor; nunca una categoría.
- prueba_de_venta: copia EXACTA de la página (de 2 a 15 palabras, sin cambiar letras) que prueba que se vende.
- precio: el precio en pesos que dice la página, o null.
Solo productos que vendería una tienda naturista física (suplementos, herbolaria, vitaminas, alimentos saludables,
cuidado personal natural). Nada de lo que «ya vendemos» si te lo doy. Si la página no prueba ventas, la lista va vacía.
No inventes nada. Responde solo JSON: {{"productos": [{{"nombre": "...", "marca": null, "prueba_de_venta": "...",
"precio": null}}]}}"""


def _preguntar_web(bd: Session, encargo: dict):
    """Lo mismo que el agente con internet, sin API externa (18 nov 2026): la IA local escribe las búsquedas, Google
    (DataForSEO) da las páginas y la IA local lee cada una. Un producto solo cuenta si su prueba de venta está escrita
    en la página (o en lo que Google mostró de ella, si no se deja leer); su liga es la de esa página."""
    from types import SimpleNamespace

    from modulos.compras import buscar_web as bw

    m, notas = encargo["mensaje"], encargo["notas"]
    tema = m.get("tendencia") or m.get("departamento") or encargo["tema"]
    fijas = [f"más vendidos {tema} México", f"{tema} más vendidos Amazon México", f"{tema} más vendido Mercado Libre"]
    que = (f"Productos de «{tema}» que hoy más se venden en México (listas de más vendidos de Amazon, Mercado Libre, "
           f"farmacias y tiendas naturistas)." + (f" De qué trata: {m['de_que_trata']}" if m.get("de_que_trata") else ""))
    b = bw.google(bd, bw.frases(bd, TAREA_VENDIDOS, que, fijas), "organico", f"más vendidos: {tema}")
    notas.notas.extend(f"Más vendidos: {n}" for n in b.notas)
    productos, citas, sin_cita, sin_nombre, ejemplo = [], [], 0, 0, ""
    ya = {"lo_que_mas_vendemos": m.get("lo_que_mas_vendemos", [])[:30]}
    for r in bw.elegir(b.resultados):
        citas.append({"url": r.url, "titulo": r.titulo})
        texto = bw.leer(r.url) or f"{r.titulo}\n{r.descripcion}"
        try:
            resp = puerta.ejecutar(bd, TAREA_VENDIDOS, usuario_id=None, instrucciones=INSTRUCCIONES_LEER_VENDIDOS,
                                   mensaje=json.dumps({"tema": tema, "sitio": r.dominio, "titulo": r.titulo,
                                                       "lo_que_google_muestra": r.descripcion,
                                                       "texto": bw.recorte(texto, f"{tema} vendido vendidos reseñas"), **ya},
                                                      ensure_ascii=False),
                                   max_tokens=1200, contexto=8192)
            lista = (radar._json_de(resp.texto) or {}).get("productos") or []
        except (puerta.ErrorIA, ValueError, TypeError, AttributeError) as e:
            notas.notas.append(f"Más vendidos: la IA local no pudo leer {r.dominio} ({str(e)[:80]}).")
            continue
        for x in (lista if isinstance(lista, list) else [])[:3]:
            if not isinstance(x, dict):
                continue
            prueba = str(x.get("prueba_de_venta") or "").strip()
            pagina = f"{r.titulo}\n{r.descripcion}\n{texto}"
            if not prueba or not bw.cita_ok(prueba, pagina):
                sin_cita += 1  # la frase no está en la página: no se puede comprobar
                ejemplo = ejemplo or f"«{prueba[:80]}» en {r.dominio}"
                continue
            if not (_que_pesan(x.get("nombre")) & _que_pesan(pagina)):
                sin_nombre += 1  # la página ni siquiera nombra el producto: lo inventó la IA
                continue
            productos.append({**x, "prueba_de_venta": prueba, "tienda": r.dominio, "url": r.url})
    if sin_cita:
        notas.notas.append(f"Más vendidos: se quitaron {sin_cita} producto(s) cuya prueba de venta no está escrita en la página"
                           f" (por ejemplo {ejemplo}).")
    if sin_nombre:
        notas.notas.append(f"Más vendidos: se quitaron {sin_nombre} producto(s) que la página ni siquiera nombra.")
    return SimpleNamespace(texto="", citas=citas, completa=True), {"productos": productos}


def _preguntar(encargo: dict):
    """Cada búsqueda con su propia conexión, para correr varias a la vez."""
    with _sesion() as bd:
        if encargo.get("web"):
            return _preguntar_web(bd, encargo)
        r = puerta.ejecutar(bd, TAREA_VENDIDOS, usuario_id=None, instrucciones=encargo["instrucciones"],
                            mensaje=json.dumps(encargo["mensaje"], ensure_ascii=False), max_tokens=MAX_TOKENS_AGENTE,
                            esfuerzo="low", busqueda_web=True)
        datos = _lista_del_agente(bd, r, encargo["notas"])
        return r, datos


def mas_vendidos(bd: Session, f: Fuentes, cat: Catalogo, avance=None) -> None:
    """El agente busca en internet por dos puertas: productos que ya se venden con cada tendencia fuerte, y los más
    vendidos de cada departamento nuestro aunque no estén en ninguna tendencia. Solo cuenta lo que trae una liga que
    salió de su búsqueda y una prueba de venta; lo que ya tenemos se quita. Si un producto sale por las dos puertas, se
    junta en uno solo con las dos."""
    encargos = _encargos(bd, f, cat)
    if not encargos:
        f.notas.append("Internet: no hay tendencias fuertes ni departamentos con venta para buscar.")
        return
    from modulos.compras import buscar_web as bw

    web = bw.usar_web(bd, TAREA_VENDIDOS)  # Google por DataForSEO + IA local (18 nov 2026)
    for e in encargos:
        e["notas"] = Fuentes()  # cada hilo junta sus avisos aparte
        e["web"] = web
    hechos = 0
    resultados: list[tuple[dict, object, dict | None, Exception | None]] = []
    with ThreadPoolExecutor(max_workers=bw.A_LA_VEZ if web else AGENTES_A_LA_VEZ) as ex:
        futuros = {ex.submit(_preguntar, e): e for e in encargos}
        for fut in as_completed(futuros):
            e = futuros[fut]
            try:
                r, datos = fut.result()
                resultados.append((e, r, datos, None))
            except (puerta.ErrorIA, ValueError, TypeError, AttributeError) as x:
                resultados.append((e, None, None, x))
            hechos += 1
            if avance:
                avance(hechos, len(encargos))
    sin_liga = sin_prueba = repetidos = 0
    por_nombre: dict[str, str] = {}
    for e, r, datos, error in sorted(resultados, key=lambda x: encargos.index(x[0])):
        cual = f"«{e['tema']}»"
        f.notas.extend(n.replace("Más vendidos:", f"Internet {cual}:") for n in e["notas"].notas)
        if error:
            f.notas.append(f"Internet {cual}: el agente no buscó ({str(error)[:200] or error.__class__.__name__}).")
            continue
        if datos is None:
            continue
        vistas = {radar._clave_url(c["url"]) for c in r.citas if c.get("url")}
        for x in (datos.get("productos") or [])[:MAX_VENDIDOS]:
            if not isinstance(x, dict):
                continue
            nombre, url = _texto(x.get("nombre"), 300), str(x.get("url") or "").strip()
            prueba = _texto(x.get("prueba_de_venta"), 400)
            if not nombre or not url.startswith(("http://", "https://")) or radar._clave_url(url) not in vistas:
                sin_liga += 1  # la liga no salió de la búsqueda: no se puede comprobar
                continue
            if not prueba:
                sin_prueba += 1
                continue
            if cat.lo_tenemos(f"{x.get('marca') or ''} {nombre}"):
                repetidos += 1
                continue
            clave_nombre = co.normalizar(nombre)
            if (ya := por_nombre.get(clave_nombre)):  # el mismo producto por otra puerta: se le suma
                d = f.datos[ya]
                if e["puerta"] not in d["puertas"]:
                    d["puertas"].append(e["puerta"])
                if e["puerta"] == "tendencia" and not d.get("tendencia"):
                    d["tendencia"] = e["tema"]
                if e["puerta"] == "mas_vendido" and not d.get("departamento_buscado"):
                    d["departamento_buscado"] = e["tema"]
                continue
            precio = pc._decimal(x.get("precio"))
            por_nombre[clave_nombre] = f.agregar("V", {
                "producto": nombre, "marca": _texto(x.get("marca"), 120), "prueba_de_venta": prueba,
                "puertas": [e["puerta"]],
                "tendencia": e["tema"] if e["puerta"] == "tendencia" else None,
                "departamento_buscado": e["tema"] if e["puerta"] == "mas_vendido" else None,
                "tienda": _texto(x.get("tienda"), 120), "precio": float(precio) if precio and precio > 0 else None,
                "url": url[:500], "sitio": radar.sitio_de(url)[:120]})
    if sin_liga:
        f.notas.append(f"Internet: se quitaron {sin_liga} producto(s) del agente cuya liga no salió de su búsqueda.")
    if sin_prueba:
        f.notas.append(f"Internet: se quitaron {sin_prueba} producto(s) sin prueba de venta.")
    if repetidos:
        f.notas.append(f"Internet: se quitaron {repetidos} producto(s) que ya vendemos.")
    if not f.de("V"):
        f.notas.append("Internet: el agente no encontró productos con prueba de venta que se puedan comprobar.")


def juntar(bd: Session, corrida: OportunidadCorrida) -> Fuentes:
    f = Fuentes()
    cat = Catalogo(bd)
    _paso(bd, corrida, "Revisando el radar de tendencias")
    tendencias(bd, f, cat)
    v = rr.ventana(bd)
    subcategorias: list[str] = []
    if v:
        _paso(bd, corrida, "Buscando huecos del surtido en la venta de SMNBI")
        subcategorias = huecos(bd, f, cat, v)
    else:
        f.notas.append("Huecos: todavía no hay ventas cargadas de SMNBI.")
    rechazos(bd, f)
    _paso(bd, corrida, "El agente busca en internet por tendencia y lo más vendido por departamento")
    mas_vendidos(bd, f, cat, avance=lambda n, total: _paso(
        bd, corrida, f"El agente busca en internet por tendencia y lo más vendido por departamento ({n} de {total} "
                     "búsquedas listas)"))
    if corrida.competencia:
        n = min(len(subcategorias), configuracion().oportunidades_busquedas)
        _paso(bd, corrida, f"Buscando lo que vende la competencia en Google Shopping ({n} subcategorías)")
        competencia(bd, f, cat, subcategorias, corrida)
    return f


# ---------------------------------------------------------------- propuestas

@dataclass
class Propuesta:
    nombre: str
    por_que: str
    evidencia: list[str]
    prioridad: str = "media"
    marca: str | None = None
    departamento: str | None = None
    subcategoria: str | None = None
    forma: str | None = None
    tipo_cliente: str | None = None
    encaje: str | None = None  # si / dudoso / no contra «Nuestro cliente»
    encaje_motivo: str | None = None


ENCAJES = {"si": "si", "sí": "si", "dudoso": "dudoso", "no": "no"}


def _texto(v, largo: int) -> str | None:
    v = " ".join(str(v or "").split())
    return v[:largo] or None


def con_ia(bd: Session, f: Fuentes) -> list[Propuesta] | str:
    """Las propuestas, o el motivo por el que la IA no contestó."""
    perfil = cl.para_oportunidades(bd)
    cuerpo = {"datos": list(f.datos.values())}
    if perfil:
        cuerpo["nuestros_clientes"] = perfil["tipos"]
    objetivo = cl.objetivo_para_ia(bd)
    if objetivo:
        cuerpo["cliente_objetivo"] = objetivo
    mensaje = json.dumps(cuerpo, ensure_ascii=False, default=str)
    tipos = {co.normalizar(t["nombre"]): t["nombre"] for t in perfil["tipos"]} if perfil else {}
    try:
        r = puerta.ejecutar(bd, TAREA_IA, usuario_id=None, instrucciones=INSTRUCCIONES, mensaje=mensaje,
                            max_tokens=8000, esfuerzo="medium",
                            contexto=puerta.ventana(INSTRUCCIONES, mensaje, salida=8000))
        respuesta = json.loads(r.texto[r.texto.find("{"):r.texto.rfind("}") + 1])
    except (puerta.ErrorIA, ValueError, TypeError, AttributeError) as e:
        log.info("Oportunidades: la IA no propuso: %s", e)
        return str(e)[:300] or e.__class__.__name__
    salida = []
    for o in respuesta.get("oportunidades") or []:
        if not isinstance(o, dict):
            continue
        evidencia = [k for k in dict.fromkeys(str(x).strip().upper() for x in o.get("evidencia") or [])
                     if k in f.datos and k[0] in PRUEBAS + APOYOS]
        nombre, por_que = _texto(o.get("nombre"), 300), _texto(o.get("por_que"), 1000)
        if not any(k[0] in PRUEBAS for k in evidencia) or not nombre or not por_que:
            continue  # sin una prueba de venta que exista, no se propone
        salida.append(Propuesta(nombre=nombre, por_que=por_que, evidencia=evidencia,
                                prioridad=o.get("prioridad") if o.get("prioridad") in PRIORIDADES else "media",
                                marca=_texto(o.get("marca"), 120), departamento=_texto(o.get("departamento"), 300),
                                subcategoria=_texto(o.get("subcategoria"), 300), forma=_texto(o.get("forma"), 60),
                                tipo_cliente=tipos.get(co.normalizar(str(o.get("tipo_cliente") or ""))),
                                encaje=ENCAJES.get(str(o.get("encaje") or "").strip().lower()) if objetivo else None,
                                encaje_motivo=_texto(o.get("encaje_motivo"), 400) if objetivo else None))
    return salida


def sin_ia(f: Fuentes) -> list[Propuesta]:
    """Lista directa de las pruebas de venta, sin redactar: primero los más vendidos que van con una tendencia, luego
    intercala los demás más vendidos y la competencia."""
    vendidos = sorted(f.de("V"), key=lambda v: -len(v.get("puertas") or []))
    vendidos_ = [Propuesta(nombre=v["producto"], marca=v["marca"], evidencia=[v["clave"]],
                           por_que=f"{v['prueba_de_venta']} ({v.get('tienda') or v['sitio']})."
                                   + (f" Va con la tendencia «{v['tendencia']}»." if v.get("tendencia") else ""))
                 for v in vendidos]
    comp = [Propuesta(nombre=c["titulo"], subcategoria=c["buscado_como"], evidencia=[c["clave"]],
                      por_que=f"Lo venden {c['tiendas_que_lo_venden']} tiendas ({', '.join(c['tiendas'])}) y no lo "
                              "tenemos.") for c in sorted(f.de("C"), key=lambda c: -c["tiendas_que_lo_venden"])]
    salida = []
    for grupo in zip_longest(vendidos_, comp):
        salida.extend(p for p in grupo if p)
    return salida[:MAX_OPORTUNIDADES]


def foto(f: Fuentes, evidencia: list[str]) -> tuple[str | None, str | None]:
    """La foto del producto y de dónde salió: primero la que su propia página dice que es suya (más vendidos), luego
    la de Google Shopping (competencia)."""
    for k in evidencia:
        if k[0] == "V" and (u := img.de_pagina(f.datos[k]["url"])):
            return u, f"Página del producto en {f.datos[k]['sitio']}"
    for k in evidencia:
        if k[0] == "C" and (u := f.datos[k].get("foto")) and str(u).startswith("https://"):
            return str(u)[:800], "Google Shopping"
    return None, None


_SIN_PESO = {"con", "de", "del", "la", "el", "en", "para", "y", "sin", "por", "mas", "plus", "caps", "capsulas", "tabletas",
             "tab", "polvo", "sabor", "pzas", "piezas", "mg", "gr", "g", "ml"}


def _que_pesan(t: str | None) -> set[str]:
    return {w for w in co.normalizar(t or "").split() if len(w) > 2 and not w.replace(".", "").isdigit() and w not in _SIN_PESO}


def _mismo_nombre(propuesto: str, visto: str | None) -> bool:
    """El producto que propone la IA es el que traía la prueba de venta: comparten al menos la mitad de las palabras que
    pesan del más corto (Diego, 18 nov 2026: la IA propuso «Vitamina D liposomal» con la prueba de un citrato de magnesio)."""
    a, b = _que_pesan(propuesto), _que_pesan(visto)
    if not a or not b:
        return True  # sin palabras para comparar no se quita
    return len(a & b) * 2 >= min(len(a), len(b))


def _ya_lo_tenemos(bd: Session, p: Propuesta) -> Producto | None:
    s = rp.Sujeto(tipo="idea", nombre=p.nombre, marca=p.marca, departamento=p.departamento)
    return rp.mismo_de(s, rp.buscar_parecidos(bd, s, p.subcategoria))


def _firma(nombre: str) -> set[str]:
    """Palabras y números del nombre («Magnesio citrato 500 mg 120 cápsulas»), para comparar presentaciones."""
    return set(co.normalizar(nombre).split())


def _vistos_antes(bd: Session) -> list[tuple[set[str], str]]:
    """Lo que ya está en el radar como idea y lo que Compras descartó antes, para que no regrese en cada corrida."""
    salida = [(_firma(i.nombre), "Compras ya la descartó antes" if i.estado == "descartada" else
               "ya está en el radar de productos")
              for i in bd.scalars(select(ProductoIdea))]
    salida += [(_firma(o.nombre), "Compras ya la descartó antes")
               for o in bd.scalars(select(Oportunidad).where(Oportunidad.estado == "descartada"))]
    # Primero lo descartado: si está en las dos, el motivo que importa es ese
    return sorted(((ps, m) for ps, m in salida if len(ps) >= 2), key=lambda x: "descart" not in x[1])


def _ya_visto(vistos: list[tuple[set[str], str]], nombre: str) -> str | None:
    ps = _firma(nombre)
    if len(ps) < 2:
        return None
    for suyas, motivo in vistos:
        if len(ps & suyas) / max(len(ps), len(suyas)) >= 0.8:
            return motivo
    return None


def a_idea(bd: Session, o: Oportunidad, usuario_id: int) -> ProductoIdea:
    """La oportunidad pasa al radar de productos como idea, con la evidencia en la descripción."""
    evidencia = "\n".join(f"- {x['fuente']}: {x['texto']}" for x in json.loads(o.evidencia))
    i = ProductoIdea(nombre=o.nombre[:300], marca=o.marca, departamento=o.departamento, forma=o.forma,
                     descripcion=f"Recomendado por «Buscar oportunidades»: {o.por_que}\n{evidencia}"[:2000],
                     precio_visto=o.precio_visto, donde_se_vio=o.donde_se_vio, estado="nueva",
                     creada_por=usuario_id, creada_en=ahora(), actualizada_en=ahora())
    bd.add(i)
    bd.flush()
    o.idea_id, o.estado, o.actualizada_por, o.actualizada_en = i.idea_id, "evaluada", usuario_id, ahora()
    return i


def _evaluar_una(evaluacion_id: int) -> None:
    with _sesion() as bd:
        rp.evaluar(bd, evaluacion_id, rapido=False)


def evaluar_todas(bd: Session, c: OportunidadCorrida) -> int:
    """Cada oportunidad nueva se evalúa sola en el semáforo (Diego, 2026-11-09: «cuando llegue algo así debe estar
    evaluado»). Las que salen verdes o amarillas abren solas su búsqueda de proveedor (busquedas.al_evaluar)."""
    usuario = c.disparada_por
    nuevas = [o for o in c.oportunidades if o.estado == "nueva" and not o.idea_id]
    if not nuevas or not usuario:
        return 0
    evaluaciones = []
    for o in nuevas:
        i = a_idea(bd, o, usuario)
        bd.commit()
        evaluaciones.append(rp.iniciar(bd, idea_id=i.idea_id, usuario_id=usuario).evaluacion_id)
    hechas = 0
    _paso(bd, c, f"Evaluando cada oportunidad en el semáforo (0 de {len(evaluaciones)})")
    with ThreadPoolExecutor(max_workers=EVALUACIONES_A_LA_VEZ) as ex:
        for fut in as_completed([ex.submit(_evaluar_una, e) for e in evaluaciones]):
            try:
                fut.result()
            except Exception:  # noqa: BLE001  la evaluación ya queda «fallida» con su error
                log.exception("Oportunidades: falló una evaluación de la corrida %s", c.corrida_id)
            hechas += 1
            _paso(bd, c, f"Evaluando cada oportunidad en el semáforo ({hechas} de {len(evaluaciones)})")
    return hechas


# ---------------------------------------------------------------- corrida

def _paso(bd: Session, corrida: OportunidadCorrida, texto: str) -> None:
    corrida.paso = texto[:300]
    bd.commit()


def iniciar(bd: Session, usuario_id: int | None, competencia_: bool, programada: bool = False) -> OportunidadCorrida | None:
    """None si ya hay una corriendo."""
    if bd.scalar(select(OportunidadCorrida).where(OportunidadCorrida.estado == "en_curso")):
        return None
    c = OportunidadCorrida(estado="en_curso", competencia=competencia_, disparada_por=usuario_id, creada_en=ahora(),
                           paso="Empezando", costo_usd=Decimal("0"),
                           notas=json.dumps([NOTA_PROGRAMADA], ensure_ascii=False) if programada else None)
    bd.add(c)
    bd.commit()
    return c


def correr(bd: Session, corrida_id: int) -> OportunidadCorrida:
    c = bd.get(OportunidadCorrida, corrida_id)
    try:
        f = juntar(bd, c)
        c.fuentes = json.dumps(f.datos, ensure_ascii=False, default=str)
        c.costo_usd = f.costo_usd
        utiles = [k for k in f.datos if k[0] in PRUEBAS]
        propuestas: list[Propuesta] = []
        if utiles:
            _paso(bd, c, "La IA está eligiendo los productos")
            propuestas = con_ia(bd, f)
            c.con_ia = not isinstance(propuestas, str)
            if isinstance(propuestas, str):
                f.notas.append(f"La IA no contestó ({propuestas}); la lista sale directo de las fuentes, sin redactar "
                               "y sin el filtro de qué vendería una tienda naturista.")
                propuestas = sin_ia(f)
        else:
            f.notas.append("No hubo productos con prueba de venta: el agente no encontró más vendidos comprobables y no "
                           "se buscó a la competencia (marca la casilla para incluirla).")
        _paso(bd, c, "Revisando que no los vendamos ya y buscando la foto de cada uno")
        vistos = set()
        antes = _vistos_antes(bd)
        perfil = cl.para_oportunidades(bd)
        percentil = int(configuracion().oportunidades_tope_precio or 0)
        if not perfil and propuestas:
            f.notas.append("Todavía no hay tipos de cliente (Datos → Clientes): no se revisó si el precio le queda a "
                           "nuestro cliente.")
        objetivo = cl.objetivo(bd)
        if objetivo and c.con_ia and propuestas:
            f.notas.append(f"Cada producto se revisó contra nuestro cliente (nivel {objetivo['nivel']}, Datos → Clientes); "
                           "los que no encajan se quitaron.")
        elif objetivo and propuestas:
            f.notas.append("No se revisó si encajan con nuestro cliente: esa revisión la hace la IA y no contestó.")
        orden = 0
        for p in propuestas:
            clave = co.normalizar(p.nombre)
            if clave in vistos:
                continue
            vistos.add(clave)
            if p.encaje == "no":
                f.notas.append(f"Se quitó «{p.nombre}»: no encaja con nuestro cliente ({objetivo['nivel']}). "
                               f"{p.encaje_motivo or 'La IA no dio el motivo.'}")
                continue
            vendidos_ev = [f.datos[k] for k in p.evidencia if k[0] == "V" and k in f.datos]
            if vendidos_ev and not any(_mismo_nombre(p.nombre, x.get("producto")) for x in vendidos_ev):
                f.notas.append(f"Se quitó «{p.nombre}»: la IA le puso un nombre que no es el del producto con prueba de "
                               f"venta («{vendidos_ev[0].get('producto')}»).")
                continue
            if (mismo := _ya_lo_tenemos(bd, p)):
                f.notas.append(f"Se quitó «{p.nombre}»: ya lo vendemos ({mismo.sku} {mismo.descripcion}).")
                continue
            if (motivo := _ya_visto(antes, p.nombre)):
                f.notas.append(f"Se quitó «{p.nombre}»: {motivo}.")
                continue
            orden += 1
            competencia_ = [f.datos[k] for k in p.evidencia if k[0] == "C"]
            vendidos = [f.datos[k] for k in p.evidencia if k[0] == "V"]
            precios = [Decimal(str(x["precio_mediana"])) for x in competencia_ if x.get("precio_mediana")]
            precios += [Decimal(str(x["precio"])) for x in vendidos if x.get("precio")]
            tiendas = sorted({t for x in competencia_ for t in x["tiendas"]} | {x.get("tienda") or x["sitio"] for x in vendidos})
            precio = Decimal(str(median(precios))).quantize(Decimal("0.01")) if precios else None
            depto = p.departamento or next((x.get("departamento_buscado") for x in vendidos if x.get("departamento_buscado")), None)
            tope = cl.tope_de_precio(perfil, depto, percentil)
            if precio and tope and float(precio) > tope:
                f.notas.append(f"Se quitó «{p.nombre}»: cuesta ${precio:,.2f} y el {percentil} % de lo que compran "
                               f"nuestros clientes en {depto} cuesta hasta ${tope:,.2f} la pieza (con IVA).")
                orden -= 1
                continue
            imagen, imagen_de = foto(f, p.evidencia)
            c.oportunidades.append(Oportunidad(
                orden=orden, nombre=p.nombre, marca=p.marca, departamento=p.departamento, subcategoria=p.subcategoria,
                forma=p.forma, por_que=p.por_que, prioridad=p.prioridad, estado="nueva", tipo_cliente=p.tipo_cliente,
                encaje=p.encaje, encaje_motivo=p.encaje_motivo,
                evidencia=json.dumps([_evidencia(f.datos[k]) for k in p.evidencia], ensure_ascii=False, default=str),
                precio_visto=precio,
                donde_se_vio=", ".join(tiendas)[:300] or None, imagen=imagen, imagen_de=imagen_de))
            if orden >= MAX_OPORTUNIDADES:
                break
        c.notas = json.dumps((json.loads(c.notas) if c.notas else []) + f.notas, ensure_ascii=False)
        bd.commit()
        if c.oportunidades:
            evaluar_todas(bd, c)
        c.estado, c.paso = "lista", None
    except Exception as ex:  # noqa: BLE001
        log.exception("Oportunidades: falló la corrida %s", corrida_id)
        bd.rollback()
        c = bd.get(OportunidadCorrida, corrida_id)
        c.estado, c.error, c.paso = "fallida", f"No se pudo terminar: {str(ex)[:900]}", None
    c.terminada_en = ahora()
    bd.commit()
    return c


FUENTE = {"V": "Más vendido en internet", "C": "Competencia", "T": "Tendencia", "H": "Hueco del surtido",
          # Corridas anteriores al 28 oct 2026
          "D": "Descontinuado que vendía", "N": "Novedad en internet"}
VIEJAS = "DN"  # fuentes que ya no se usan: solo se muestran en corridas que las tienen


def _evidencia(d: dict) -> dict:
    """La evidencia en una línea para la pantalla."""
    k = d["clave"]
    if k[0] == "T":
        texto = (f"«{d['titulo']}» (nivel {d['nivel'].lower()}, vista el {d['vista_por_ultima_vez']}); tenemos "
                 f"{d['productos_que_tenemos_con_esas_palabras']} producto(s) con esas palabras.")
    elif k[0] == "N":
        extra = " ".join(f"{t}: {d[c]}." for t, c in (("Etapa", "etapa"), ("Para", "consumidor"), ("Encaje", "encaje"),
                                                      ("Riesgo", "riesgo")) if d.get(c))
        texto = f"{d['producto']}: {d.get('por_que') or ''} {extra} ({d['sitio']}, {d['url']})".replace("  ", " ")
    elif k[0] == "V":
        precio = f", ${d['precio']:,.2f}" if d.get("precio") else ""
        tendencia = f" Va con la tendencia «{d['tendencia']}»." if d.get("tendencia") else ""
        if d.get("departamento_buscado"):
            tendencia += f" Es de lo más vendido en {d['departamento_buscado']}."
        texto = f"{d['producto']}: {d['prueba_de_venta']} ({d.get('tienda') or d['sitio']}{precio}, {d['url']}).{tendencia}"
    elif k[0] == "H":
        inv = f"; inventario para {d['dias_de_inventario']} días" if d.get("dias_de_inventario") is not None else ""
        texto = (f"{d['subcategoria']}: {d['piezas_al_mes_por_producto']:,.1f} piezas al mes por producto con "
                 f"{d['productos_activos']} productos (una subcategoría típica tiene {d['subcategoria_tipica_tiene']}){inv}.")
    elif k[0] == "D":
        texto = (f"{d['producto']}: vendía {d['piezas_al_mes_cuando_se_vendia']:,.1f} piezas al mes en {d['tiendas']} "
                 "tiendas antes de descontinuarse.")
    else:
        precio = f", mediana ${d['precio_mediana']:,.2f}" if d.get("precio_mediana") else ""
        texto = f"«{d['titulo']}»: lo venden {d['tiendas_que_lo_venden']} tienda(s) ({', '.join(d['tiendas'])}){precio}."
    if k[0] == "V":
        puertas_ = d.get("puertas") or (["tendencia"] if d.get("tendencia") else ["mas_vendido"])
    else:
        puertas_ = {"T": ["tendencia"], "C": ["mas_vendido"]}.get(k[0], [])
    return {"clave": k, "fuente": FUENTE[k[0]], "texto": texto, "puertas": puertas_}


# Las tres puertas por las que llega una oportunidad (Diego, 2026-11-09: «quiero que sea por tendencia, porque alguien
# lo capturó o porque es lo que más se vende»)
PUERTAS = {"tendencia": "Por tendencia", "mas_vendido": "De lo más vendido", "captura": "Capturado por Compras"}


def puertas(evidencia: list[dict] | None) -> list[str]:
    """Las puertas de una oportunidad según su evidencia; sin oportunidad (idea capturada a mano), «captura»."""
    if evidencia is None:
        return ["captura"]
    vistas = {p for x in evidencia for p in (x.get("puertas") or [])}
    if not vistas:  # corridas anteriores al 9 nov 2026: se deduce de la fuente
        vistas = {"tendencia" if x.get("clave", " ")[0] == "T" else "mas_vendido"
                  for x in evidencia if x.get("clave", " ")[0] in "TVC"}
    return [p for p in PUERTAS if p in vistas]


def _sesion() -> Session:
    from core.bd import _fabrica

    return _fabrica()()


def en_hilo(corrida_id: int) -> None:
    def trabajo():
        with _sesion() as bd:
            correr(bd, corrida_id)

    threading.Thread(target=trabajo, daemon=True, name=f"oportunidades-{corrida_id}").start()


# ---------------------------------------------------------------- corrida programada

NOTA_PROGRAMADA = "Corrida programada desde Administración > Configuración."


def es_programada(c: OportunidadCorrida) -> bool:
    return bool(c.notas) and NOTA_PROGRAMADA in c.notas


def zona() -> ZoneInfo:
    try:
        return ZoneInfo(configuracion().oportunidades_zona_horaria or "America/Mexico_City")
    except Exception:  # noqa: BLE001  zona mal escrita: la de México
        return ZoneInfo("America/Mexico_City")


def _local(d: datetime) -> date:
    """Las fechas de la base están en UTC sin zona."""
    from datetime import timezone

    return d.replace(tzinfo=timezone.utc).astimezone(zona()).date()


def _dias_semana() -> set[int]:
    return {int(d) for d in (configuracion().oportunidades_dias_semana or "").split(",") if d.strip().isdigit()} \
        or set(range(1, 8))


def toca(fecha: date, ultima: date | None) -> bool:
    cfg = configuracion()
    if cfg.oportunidades_frecuencia == "dias":
        return fecha.isoweekday() in _dias_semana()
    if cfg.oportunidades_frecuencia == "cada_n":
        return ultima is None or (fecha - ultima).days >= max(cfg.oportunidades_cada_dias, 1)
    return True


DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos")


def texto_programa() -> str | None:
    cfg = configuracion()
    if not cfg.oportunidades_activo:
        return None
    if cfg.oportunidades_frecuencia == "cada_n":
        cuando = f"cada {cfg.oportunidades_cada_dias} días"
    elif cfg.oportunidades_frecuencia == "dias" and len(_dias_semana()) < 7:
        dias = [DIAS[d - 1] for d in sorted(_dias_semana())]
        cuando = "los " + (", ".join(dias[:-1]) + " y " + dias[-1] if len(dias) > 1 else dias[0])
    else:
        cuando = "todos los días"
    return f"Corre sola {cuando} a las {cfg.oportunidades_hora}:00"


def responsable_programa(bd: Session) -> int | None:
    """Las ideas necesitan a nombre de quién quedan: el último que guardó «Buscar oportunidades automáticamente»."""
    from nucleo.modelos import ConfiguracionAjuste, Usuario

    fila = bd.get(ConfiguracionAjuste, "oportunidades_activo")
    u = bd.get(Usuario, fila.actualizado_por) if fila and fila.actualizado_por else None
    return u.usuario_id if u and u.estatus == "activo" else None


def revisar_programa(bd: Session) -> OportunidadCorrida | None:
    """Lo llama el programador cada minuto. Corre una vez el día que toca, a la hora o en cuanto vuelva la plataforma.
    No corre si ya hubo una búsqueda ese día (con el botón o programada) o si hay una en curso."""
    cfg = configuracion()
    if not cfg.oportunidades_activo:
        return None
    ahora_local = datetime.now(zona())
    if ahora_local.hour < cfg.oportunidades_hora:
        return None
    hoy = ahora_local.date()
    recientes = bd.scalars(select(OportunidadCorrida).order_by(OportunidadCorrida.corrida_id.desc()).limit(20)).all()
    if any(_local(c.creada_en) == hoy for c in recientes):
        return None
    terminadas = [_local(c.creada_en) for c in recientes if c.estado == "lista"]
    if not toca(hoy, max(terminadas) if terminadas else None):
        return None
    usuario = responsable_programa(bd)
    if not usuario:
        log.warning("Buscar oportunidades programada: no se sabe a nombre de quién crear las ideas; enciéndalo de nuevo "
                    "en Configuración")
        return None
    c = iniciar(bd, usuario, cfg.oportunidades_competencia_programada, programada=True)
    if not c:
        return None
    log.info("Buscar oportunidades: corrida programada %s", c.corrida_id)
    en_hilo(c.corrida_id)
    return c


def cerrar_huerfanas(bd: Session) -> int:
    """Al arrancar: las corridas que quedaron en curso (la API se reinició) se marcan fallidas."""
    filas = bd.scalars(select(OportunidadCorrida).where(OportunidadCorrida.estado == "en_curso")).all()
    for c in filas:
        c.estado, c.error, c.paso, c.terminada_en = "fallida", "La API se reinició a medio camino.", None, ahora()
    bd.commit()
    return len(filas)
