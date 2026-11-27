"""Precios de internet de un producto que todavía no vendemos, con las mismas piezas del radar de precios
(pedido de Diego, 2026-10-26: «que se evalúe con todo lo que tenemos»).

Busca el producto en Google Shopping (DataForSEO) y en el sitio de las tiendas clave (Walmart, Chedraui, San Pablo,
Soriana). Para decidir qué resultado es el mismo producto usa las reglas del radar de precios (marca, nombre,
presentación, código de barras) y, si quedan dudosos, la IA. El gasto de DataForSEO queda en «Corridas y gasto» del
radar de precios como una corrida «Radar de productos» y cuenta para el tope del mes.
"""
import contextvars
import json
import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import configuracion
from ia import puerta
from modulos.compras import coincidencia as co
from modulos.compras import dataforseo as dfs
from modulos.compras import precios as pc
from modulos.compras import senal_venta as sv
from modulos.compras import tiendas as td
from modulos.compras.modelos_precios import PrecioCorrida, PrecioEnvio
from nucleo.modelos import ahora

log = logging.getLogger("smn.compras.mercado_producto")

ORIGEN = pc.PRODUCTO
# Para que la pantalla diga en qué va mientras busca afuera (26 nov 2026: frente a Dirección se evalúa en vivo y el
# paso 3 duraba minutos con el mismo texto). La evaluación pone aquí una función que recibe el texto.
AVANCE: "contextvars.ContextVar[Callable[[str], None] | None]" = contextvars.ContextVar("avance_afuera", default=None)


def _avance(m: "Mercado", texto: str) -> None:
    if (f := AVANCE.get()) is not None:
        try:
            n = len(m.precios)
            f(texto + (f" · llevamos {n} precio{'s' if n != 1 else ''} de afuera" if n else ""))
        except Exception:  # noqa: BLE001 - el avance nunca detiene la búsqueda
            log.debug("No se pudo anotar el avance", exc_info=True)
DIAS_VIGENCIA = 7  # al recalcular dentro de una semana se reusa la búsqueda y no se vuelve a pagar
MAX_PRECIOS = 30
# Reglas con un defecto que dejó fuera algo de la búsqueda: lo buscado con ellas no se reusa aunque traiga precio.
# 6 (v0.6.11) no buscaba en las tiendas directas (decisión de Diego, 26 nov 2026: «sí, que se vuelvan a buscar»)
REGLAS_INVALIDADAS = frozenset({6, 7, 8, 9, 10, 11, 12})  # 7 a 12: solo existieron en la laptop la noche del 26 nov
# Versión de la regla que decide si una publicación es el mismo producto. Una búsqueda sin precios hecha con una regla
# anterior se vuelve a hacer al recalcular (25 nov 2026: la línea de la marca, «BDM Life» de JUVETERNAL)
# 12: «sabor natural» o «sin sabor» no se exige en el título (26 nov 2026)
# 11: una respuesta rara de Google Shopping (falla pasajera de DataForSEO) se repite una vez (26 nov 2026)
# 10: las tiendas de Compras sin conector se buscan en Google limitado a su sitio (26 nov 2026)
# 9: si una tienda bloquea su sitio, se busca en Google limitado a su dominio (26 nov 2026)
# 8: si Google trae el producto sin decir el tamaño, la IA local lo revisa; sin tamaño se muestra y no cuenta
# 7: vuelven las tiendas directas, que v0.6.11 dejó de llamar (revisión del 26 nov 2026)
REGLA = 13  # 13: el apóstrofo de la marca se queda («Nature's Bounty») y «polvo» o «micronizada» no se exigen en el título; Amazon México ya se consulta con su idioma (26 nov 2026). 6: si no encontró nada, otra búsqueda con la marca y el ingrediente (26 nov 2026). 5: consultas en texto plano, sin «+» ni «–», como las del radar de precios (BDM Life, v0.6.2)


@dataclass
class Mercado:
    precios: list[dict] = field(default_factory=list)  # {precio, vendedor, fuente: google/sitio, titulo, liga}
    notas: list[str] = field(default_factory=list)
    publicacion: str | None = None  # la publicación de Google que se tomó como el mismo producto
    costo_usd: Decimal = Decimal("0")
    buscado_en: str | None = None
    clave: str = ""  # qué se buscó; si cambia, no se reusa
    senales: list[dict] = field(default_factory=list)  # señal de venta en internet (senal_venta.Senal), 22 nov 2026
    regla: int = REGLA
    # Es el mismo producto pero su publicación no dice el tamaño: se muestra con su precio y no califica (26 nov 2026)
    vistos: list[dict] = field(default_factory=list)

    def mediana(self) -> Decimal | None:
        return Decimal(str(median([Decimal(str(p["precio"])) for p in self.precios]))) if self.precios else None

    def a_json(self) -> str:
        return json.dumps({"precios": self.precios, "notas": self.notas, "publicacion": self.publicacion,
                           "costo_usd": str(self.costo_usd), "buscado_en": self.buscado_en, "clave": self.clave,
                           "senales": self.senales, "regla": self.regla, "vistos": self.vistos},
                          ensure_ascii=False)

    @classmethod
    def de_json(cls, texto: str | None) -> "Mercado | None":
        if not texto:
            return None
        d = json.loads(texto)
        return cls(precios=d.get("precios") or [], notas=d.get("notas") or [], publicacion=d.get("publicacion"),
                   costo_usd=Decimal(d.get("costo_usd") or "0"), buscado_en=d.get("buscado_en"), clave=d.get("clave") or "",
                   senales=d.get("senales") or [], regla=int(d.get("regla") or 1), vistos=d.get("vistos") or [])

    def vigente(self, clave: str) -> bool:
        if self.clave != clave or not self.buscado_en:
            return False
        if self.regla in REGLAS_INVALIDADAS:
            return False
        if not self.precios and self.regla < REGLA:
            return False
        return (ahora() - datetime.fromisoformat(self.buscado_en)).days < DIAS_VIGENCIA


def clave_de(nombre: str, marca: str | None, codigo_barras: str | None) -> str:
    return "|".join(co.normalizar(x or "") for x in (nombre, marca, codigo_barras))


def _precio(c: co.Candidato) -> Decimal | None:
    d = c.datos
    if (d.get("currency") or "MXN").upper() != "MXN":
        return None
    p = pc._decimal(d.get("price"))
    return p if p and p > 0 else None


def _tienda(vendedor: str | None, liga: str | None) -> str:
    """La tienda de un precio: la de Compras si se reconoce (Mercado Libre = «mercadolibre.com.mx»), o el vendedor."""
    return pc.tienda_clave(vendedor, liga) or " ".join(str(vendedor or "").lower().split())


def _vendedor_limpio(vendedor: str) -> str:
    """Sin las etiquetas internas que a veces trae Google en el nombre del vendedor (Gold Standard Whey, 26 nov 2026: salía
    «eBay - item_title_google_cloud_translation_test_for_us_es» en la pantalla)."""
    return re.sub(r"\s+-\s+\w*_\w*$", "", vendedor).strip() or vendedor


def _agregar(m: Mercado, candidatos: list[co.Candidato], fuente: str) -> None:
    vistos = {(p["vendedor"], p["precio"]) for p in m.precios}
    for c in candidatos:
        precio = _precio(c)
        vendedor = _vendedor_limpio(str(c.datos.get("seller") or c.datos.get("source") or "Vendedor sin nombre"))[:120]
        if precio is None or (vendedor, float(precio)) in vistos or len(m.precios) >= MAX_PRECIOS:
            continue
        # eBay en Google Shopping es importación (precio de EUA con envío): no es el precio de afuera en México.
        # Revisión de coherencia, 26 nov 2026: Whey Gold Standard tomó solo eBay a $2,948 y salió «barato» con 100;
        # el magnesio tenía eBay a $1,912 contra $650–685
        if re.match(r"ebay\b", vendedor.strip().lower()):
            nota = "eBay: publicaciones de importación; no se toman como precio de afuera."
            if nota not in m.notas:
                m.notas.append(nota)
            continue
        # Una tienda cuenta una vez, con su precio más bajo (BDM Life en la laptop, 26 nov 2026: Mercado Libre salía dos
        # veces, como «mercadolibre.com.mx» y como «Mercado Libre»)
        liga = c.datos.get("shopping_url") or c.datos.get("url")
        suya = next((p for p in m.precios if _tienda(p["vendedor"], p.get("liga")) == _tienda(vendedor, liga)), None)
        if suya is not None:
            if float(precio) < suya["precio"]:
                m.precios.remove(suya)
            else:
                continue
        vistos.add((vendedor, float(precio)))
        fila = {"precio": float(precio), "vendedor": vendedor, "fuente": fuente, "titulo": c.titulo[:200],
                "liga": (c.datos.get("shopping_url") or c.datos.get("url") or "")[:500] or None}
        venta = c.datos.get("venta") or (sv.venta_google(c.datos) if fuente == "google" else None)
        if venta:
            fila["venta"] = venta
        m.precios.append(fila)


def _con_ia(bd: Session, nombre: str, marca: str | None, dudosos: list[co.Candidato]) -> co.Candidato | None:
    try:
        with puerta.temperatura(0):  # la misma pregunta, la misma respuesta (26 nov 2026)
            r = puerta.ejecutar(bd, pc.TAREA_IA, usuario_id=None, instrucciones=co.INSTRUCCIONES_IA,
                                mensaje=co.mensaje_ia(nombre, marca, dudosos), max_tokens=400, esfuerzo="low")
        elegido, _, _ = co.leer_respuesta_ia(r.texto, dudosos)
        return elegido
    except (puerta.ErrorIA, ValueError, TypeError) as e:
        log.info("Radar de productos: la IA no decidió entre los dudosos de «%s»: %s", nombre, e)
        return None


INSTRUCCIONES_TAMANO = """Eres un verificador de productos para retail mexicano (suplementos y naturistas).
Recibes nuestro producto y publicaciones de Google Shopping de la misma marca y con el mismo nombre, pero cuyo título no
dice el tamaño. Decide con la evidencia dada (título, descripción, vendedor, precio):
- "mismo_producto": true solo si es el mismo producto (marca, tipo, sabor o variante); una variante distinta es otro producto.
- "tamano": "confirmado" si algún dato de la oferta dice nuestra misma presentación; "distinto" si dice otra; "sin_dato" si
  no se puede saber. No supongas el tamaño por el precio.
Responde solo con este JSON, sin texto adicional:
{"mismo_producto": true o false, "tamano": "confirmado" o "distinto" o "sin_dato", "claves": ["<claves que son el mismo producto>"], "confianza": <0 a 100>, "motivo": "<una frase en español>"}"""


def _sin_tamano(c: co.Candidato) -> bool:
    """Misma marca y mismo nombre, el título no dice el tamaño y no lo contradice (ni es paquete)."""
    ev = c.evaluacion
    return bool(ev) and ev.marca is True and ev.mismo_nombre and ev.presentacion is None and not ev.contradice         and not ev.es_paquete and _precio(c) is not None


def _revisar_sin_tamano(bd: Session, nombre: str, marca: str | None, candidatos: list[co.Candidato]
                        ) -> tuple[list[co.Candidato], list[co.Candidato], str]:
    """«No dice el tamaño» no es «dice otro tamaño» (Diego, 26 nov 2026): lo que tiene la misma marca y el mismo nombre
    va a la IA local. (confirmados que cuentan, vistos sin tamaño que solo se muestran, motivo)."""
    fuertes = [c for c in candidatos if _sin_tamano(c)][:4]
    if not fuertes:
        return [], [], ""
    mensaje = json.dumps({"producto": {"descripcion": nombre, "marca": co.marca_comercial(marca)},
                          "candidatos": [{"clave": c.clave, "titulo": c.titulo, "vendedor": c.datos.get("seller"),
                                          "descripcion": str(c.datos.get("description") or "")[:400],
                                          "precio": str(c.datos.get("price")), "moneda": c.datos.get("currency") or "MXN"}
                                         for c in fuertes]}, ensure_ascii=False)
    try:
        with puerta.temperatura(0):
            r = puerta.ejecutar(bd, pc.TAREA_IA, usuario_id=None, instrucciones=INSTRUCCIONES_TAMANO, mensaje=mensaje,
                                max_tokens=400, esfuerzo="low")
        d = co._json_ia(r.texto)
    except (puerta.ErrorIA, ValueError, TypeError) as e:
        # Sin la IA no se confirma nada: se muestran como vistos sin tamaño y no califican
        log.info("Precios de afuera: la IA no revisó los de tamaño sin confirmar de «%s»: %s", nombre, e)
        return [], fuertes, "la IA local no contestó"
    claves = {str(k) for k in d.get("claves") or []} if isinstance(d.get("claves"), list) else set()
    suyos = [c for c in fuertes if c.clave in claves]
    motivo = str(d.get("motivo") or "")[:200]
    if not d.get("mismo_producto") or not suyos:
        return [], [], motivo
    if d.get("tamano") == "confirmado" and float(d.get("confianza") or 0) >= co.CONFIANZA_IA:
        return suyos, [], motivo
    if d.get("tamano") == "distinto":
        return [], [], motivo
    return [], suyos, motivo


def _elegir(bd: Session, nombre: str, marca: str | None, candidatos: list[co.Candidato], marcas: set[str]
            ) -> tuple[co.Candidato | None, list[co.Candidato]]:
    """El mismo producto y las demás publicaciones que las reglas también aceptan."""
    dec = co.decidir(nombre, marca, candidatos, configuracion().precios_umbral, marcas, set())
    elegido = dec.elegido or (_con_ia(bd, nombre, marca, dec.dudosos) if dec.dudosos else None)
    if not elegido:
        return None, []
    iguales = [c for c in candidatos if c is not elegido and c.evaluacion and c.evaluacion.aceptada and co.pasa_reglas(c)]
    return elegido, iguales


def _mensajes_envio(bd: Session, corrida_id: int) -> dict[str, str]:
    """{tag: «código mensaje»} de lo que contestó DataForSEO al recibir cada búsqueda."""
    salida = {}
    for r in bd.scalars(select(PrecioEnvio.respuesta).where(PrecioEnvio.corrida_id == corrida_id)):
        try:
            for t in json.loads(r or "[]"):
                salida[str(t.get("tag") or "")] = f"{t.get('estado')} {t.get('mensaje') or ''}".strip()
        except (ValueError, TypeError, AttributeError):
            continue
    return salida


def _respuesta_rara(items, nombre: str, marca: str | None) -> bool:
    """Error del servidor de DataForSEO, o resultados que no tienen que ver: ninguno trae la marca ni la palabra principal."""
    if isinstance(items, str):
        return "server error" in items.lower() or "internal" in items.lower()
    if len(items) < 5:
        return False
    claves = {w for w in co.normalizar(f"{marca or ''} {nombre}").split() if len(w) >= 5}
    if not claves:
        return False
    return not any(any(w in co.normalizar(str(i.get("title") or "")) for w in claves) for i in items)


def _google(bd: Session, m: Mercado, nombre: str, marca: str | None, consultas: list[tuple[str, str]], marcas: set[str],
            referencia: str) -> None:
    if falta := dfs.configurado():
        m.notas.append("Google Shopping: no se buscó, falta " + ", ".join(falta) + " en Configuración.")
        return
    cfg = configuracion()
    corrida = PrecioCorrida(fecha=pc.hoy_local(), origen=ORIGEN, estado="en_curso", productos=1,
                            lista=json.dumps({"radar_productos": referencia}, ensure_ascii=False))
    bd.add(corrida)
    bd.commit()
    candidatos: dict[str, co.Candidato] = {}
    try:
        tareas = [{"keyword": texto, "depth": cfg.precios_profundidad, "tag": f"{n}"} for n, (_, texto) in enumerate(consultas)]
        log.info("Precios de afuera (%s): se mandan %s búsquedas a Google Shopping: %s", referencia, len(tareas),
                 " · ".join(f"«{t}»" for _, t in consultas))
        ids = dfs.enviar(bd, corrida, "productos", tareas)
        log.info("Precios de afuera (%s): DataForSEO aceptó %s de %s; esperando a que Google conteste", referencia,
                 len(ids), len(tareas))
        # Una búsqueda que DataForSEO no acepta no regresa nada y antes no se decía (BDM Life, 25 nov 2026: solo
        # quedaba la del código de barras y Google regresaba cualquier cosa)
        if faltan := [n for n in range(len(consultas)) if str(n) not in ids]:
            mensajes = _mensajes_envio(bd, corrida.corrida_id)
            for n in faltan:
                por_que = f" ({mensajes[str(n)]})" if mensajes.get(str(n)) else ""
                m.notas.append(f"Google Shopping no aceptó la búsqueda «{consultas[n][1]}»{por_que}.")
        respuesta = dfs.recoger("productos", ids)
        # Una falla pasajera de DataForSEO («Internal SE Server Error») o una respuesta donde ningún resultado trae la
        # marca ni la palabra principal (libros y cursos para «Optimum Nutrition Creatina», 26 nov 2026) se repite una vez
        repetir = [n for n in range(len(consultas)) if str(n) in respuesta and consultas[n][0] != "codigo_barras"
                   and _respuesta_rara(respuesta[str(n)], nombre, marca)]  # por código casi siempre regresa otras cosas
        if repetir:
            log.info("Precios de afuera (%s): Google Shopping regresó algo raro; se repiten %s búsquedas", referencia, len(repetir))
            otra = dfs.recoger("productos", dfs.enviar(bd, corrida, "productos", [tareas[n] for n in repetir]))
            for tag, items in otra.items():
                if not _respuesta_rara(items, nombre, marca) or isinstance(respuesta.get(tag), str):
                    respuesta[tag] = items
        for tag, items in respuesta.items():
            if isinstance(items, str):
                m.notas.append(f"Google Shopping: {items}.")
                continue
            estrategia = consultas[int(tag)][0]
            for item in items:
                if c := co.candidato_de(item):
                    candidatos.setdefault(c.clave, c).estrategias.add(estrategia)
        log.info("Precios de afuera (%s): Google regresó %s resultados; comparando si alguno es el mismo producto",
                 referencia, len(candidatos))
        elegido, iguales = _elegir(bd, nombre, marca, list(candidatos.values()), marcas)
        log.info("Precios de afuera (%s): %s", referencia,
                 f"tomado «{elegido.titulo[:80]}»" if elegido else "ninguno es el mismo producto")
        if not elegido:
            confirmados, sin_tamano, por_que = _revisar_sin_tamano(bd, nombre, marca, list(candidatos.values()))
            if confirmados:
                elegido, iguales = confirmados[0], confirmados[1:]
            for c in sin_tamano:
                if len(m.vistos) < 6 and (precio := _precio(c)):
                    m.vistos.append({"precio": float(precio), "titulo": c.titulo[:200],
                                     "vendedor": str(c.datos.get("seller") or "Vendedor sin nombre")[:120],
                                     "liga": (c.datos.get("shopping_url") or c.datos.get("url") or "")[:500] or None,
                                     "motivo": por_que})
            if sin_tamano:
                v = min(m.vistos, key=lambda x: x["precio"]) if m.vistos else None
                if v:
                    m.notas.append(f"Google Shopping: lo vimos a ${v['precio']:,.2f} en {v['vendedor']}, pero la "
                                   "publicación no dice el tamaño; se muestra y no cuenta para la calificación.")
        if elegido:
            m.publicacion = elegido.titulo[:300]
            _agregar(m, [elegido, *iguales], "google")
        else:
            m.notas.append("Google Shopping: ningún resultado es claramente el mismo producto." if candidatos
                           else "Google Shopping no regresó resultados.")
            # Qué se vio y por qué no se tomó, para poder revisarlo sin repetir la búsqueda (25 nov 2026)
            vistos = sorted((c for c in candidatos.values() if c.evaluacion), key=lambda c: -c.evaluacion.calificacion)[:3]
            if vistos:
                m.notas.append("Google Shopping, lo más parecido: " + " | ".join(
                    f"«{c.titulo[:90]}» ({c.evaluacion.motivo})" for c in vistos))
            m.notas.append("Google Shopping, se buscó: " + " · ".join(f"«{t}»" for _, t in consultas))
            # Todo lo que regresó, para saber si falló la búsqueda o la comparación (Diego, 26 nov 2026: «buscándolo
            # por nombre sí sale»)
            if candidatos:
                m.notas.append(f"Google Shopping regresó {len(candidatos)}: " + " · ".join(
                    f"«{c.titulo[:60]}»" for c in list(candidatos.values())[:12]))
        corrida.estado = "completa"
    except dfs.SinPresupuesto as e:
        m.notas.append(f"Google Shopping: no se buscó, {e}")
        corrida.estado, corrida.error = "fallida", str(e)[:1000]
    except dfs.ErrorDataForSEO as e:
        m.notas.append(f"Google Shopping falló: {e}")
        corrida.estado, corrida.error = "fallida", str(e)[:1000]
    corrida.terminado_en = ahora()
    corrida.con_precios = 1 if m.precios else 0
    m.costo_usd += corrida.costo_usd or Decimal("0")
    bd.commit()


def _respaldo_google(bd: Session, m: Mercado, tienda: td.Tienda, consultas: list[tuple[str, str]],
                     referencia: str) -> dict[str, co.Candidato] | None:
    """La tienda bloqueó la consulta a su sitio: se busca en Google limitado a su dominio (una búsqueda normal de
    DataForSEO, dentro del tope). Regresa sus resultados como candidatos, o None si no se pudo buscar."""
    texto = next((t for e, t in consultas if e != "codigo_barras"), None)
    if not texto:
        return None
    if falta := dfs.configurado():
        m.notas.append(f"{tienda.nombre}: no se buscó en Google, falta " + ", ".join(falta) + " en Configuración.")
        return None
    corrida = PrecioCorrida(fecha=pc.hoy_local(), origen=ORIGEN, estado="en_curso", productos=1,
                            lista=json.dumps({"radar_productos": referencia, "respaldo_tienda": tienda.nombre},
                                             ensure_ascii=False))
    bd.add(corrida)
    bd.commit()
    items: list[dict] = []
    try:
        ids = dfs.enviar(bd, corrida, "organico", [{"keyword": td.consulta_sitio(tienda, texto), "depth": 10, "tag": "0"}])
        for resultado in dfs.recoger("organico", ids).values():
            if isinstance(resultado, list):
                items += resultado
        corrida.estado = "completa"
    except dfs.SinPresupuesto as e:
        m.notas.append(f"{tienda.nombre}: no se buscó en Google, {e}")
        corrida.estado, corrida.error = "fallida", str(e)[:1000]
        return None
    except dfs.ErrorDataForSEO as e:
        m.notas.append(f"{tienda.nombre}: la búsqueda en Google falló ({e}).")
        corrida.estado, corrida.error = "fallida", str(e)[:1000]
        return None
    finally:
        corrida.terminado_en = ahora()
        m.costo_usd += corrida.costo_usd or Decimal("0")
        bd.commit()
    return {r.clave: pc.candidato_tienda(tienda, r, i + 1) for i, r in enumerate(td.de_google(tienda, items))}


def _tiendas_google(bd: Session, m: Mercado, nombre: str, marca: str | None, consultas: list[tuple[str, str]],
                    marcas: set[str], referencia: str) -> None:
    """Las tiendas de Compras sin conector (Farmacias del Ahorro, HEB, GNC…), en Google limitado a su sitio, varias
    por búsqueda. Lo que trae pasa por las mismas reglas; una tienda que ya tiene precio no se repite (26 nov 2026)."""
    _tiendas_google_recoger(bd, m, nombre, marca, marcas, _tiendas_google_enviar(bd, m, consultas, referencia))


def _tiendas_google_enviar(bd: Session, m: Mercado, consultas: list[tuple[str, str]], referencia: str) -> dict | None:
    """Manda la búsqueda de las tiendas de Compras y no la espera. `buscar` la manda al empezar y la recoge después de
    las tiendas directas: la espera de DataForSEO corre junto con lo demás y no al final (26 nov 2026: era 1 a 2 min
    más por producto). Mismas consultas que antes: el resultado no cambia."""
    cfg = configuracion()
    tiendas = td.sitios_google() if cfg.tiendas_google_activo else []
    texto = next((t for e, t in consultas if e != "codigo_barras"), None)
    if not tiendas or not texto or dfs.configurado():
        return None
    grupos = td.grupos_google(tiendas, cfg.tiendas_google_por_busqueda)
    corrida = PrecioCorrida(fecha=pc.hoy_local(), origen=ORIGEN, estado="en_curso", productos=1,
                            lista=json.dumps({"radar_productos": referencia, "tiendas_google": True}, ensure_ascii=False))
    bd.add(corrida)
    bd.commit()
    try:
        ids = dfs.enviar(bd, corrida, "organico", [{"keyword": td.consulta_grupo(g, texto), "depth": 10, "tag": str(i)}
                                                   for i, g in enumerate(grupos)])
    except (dfs.SinPresupuesto, dfs.ErrorDataForSEO) as e:
        m.notas.append(f"Tiendas de Compras en Google: no se buscó, {e}")
        corrida.estado, corrida.error, corrida.terminado_en = "fallida", str(e)[:1000], ahora()
        m.costo_usd += corrida.costo_usd or Decimal("0")
        bd.commit()
        return None
    return {"corrida": corrida, "grupos": grupos, "tiendas": tiendas, "ids": ids}


def _tiendas_google_recoger(bd: Session, m: Mercado, nombre: str, marca: str | None, marcas: set[str],
                            enviado: dict | None) -> None:
    if not enviado:
        return
    corrida, grupos, tiendas = enviado["corrida"], enviado["grupos"], enviado["tiendas"]
    respuesta: dict = {}
    try:
        respuesta = dfs.recoger("organico", enviado["ids"])
        corrida.estado = "completa"
    except (dfs.SinPresupuesto, dfs.ErrorDataForSEO) as e:
        m.notas.append(f"Tiendas de Compras en Google: no se buscó, {e}")
        corrida.estado, corrida.error = "fallida", str(e)[:1000]
    finally:
        corrida.terminado_en = ahora()
        m.costo_usd += corrida.costo_usd or Decimal("0")
        bd.commit()
    ya = {pc.tienda_clave(p.get("vendedor"), p.get("liga")) for p in m.precios} - {None}
    con_precio = []
    for i, g in enumerate(grupos):
        items = respuesta.get(str(i))
        if not isinstance(items, list):
            continue
        for t in g:
            if t.nombre in ya:
                continue
            suyos = td.de_google(t, items)
            cands = {r.clave: pc.candidato_tienda(t, r, j + 1) for j, r in enumerate(suyos)}
            elegido, _ = _elegir(bd, nombre, marca, list(cands.values()), marcas) if cands else (None, [])
            if elegido and _precio(elegido):
                _agregar(m, [elegido], td.FUENTE_GOOGLE_SITIO)
                con_precio.append(f"{t.nombre} ${float(_precio(elegido)):,.2f}")
    if respuesta:
        m.notas.append("Tiendas de Compras en Google (" + ", ".join(t.nombre for t in tiendas) + "): "
                       + ("con precio en " + ", ".join(con_precio) + "." if con_precio else "ninguna lo tiene publicado."))


def _consultar_tienda(tienda: td.Tienda, consultas: list[tuple[str, str]]
                      ) -> tuple[dict[str, co.Candidato], Exception | None]:
    """Corre en su propio hilo: solo consulta el sitio de la tienda (nada de base ni IA)."""
    ultima, cands = [0.0], {}
    try:
        for estrategia, texto in consultas:
            for i, r in enumerate(td.buscar_con_pausa(tienda, texto, ultima)):
                c = cands.setdefault(r.clave, pc.candidato_tienda(tienda, r, i + 1))
                if r.datos.get("venta"):  # reseñas y «Comprado +X veces» de Walmart (22 nov 2026)
                    c.datos["venta"] = r.datos["venta"]
                c.estrategias.add(estrategia)
    except Exception as e:  # noqa: BLE001 - se decide en el hilo principal
        return cands, e
    return cands, None


def _tiendas(bd: Session, m: Mercado, nombre: str, marca: str | None, consultas: list[tuple[str, str]], marcas: set[str],
             referencia: str = "") -> None:
    log.info("Precios de afuera: buscando «%s» en las tiendas clave", nombre[:80])
    # Las 4 tiendas se consultan al mismo tiempo, cada una con su pausa (26 nov 2026: en serie sumaban hasta un minuto);
    # lo que usa la base o la IA (decidir, respaldo) sigue aquí, en orden
    conectores = td.conectores(pc.tiendas_directas())
    with ThreadPoolExecutor(max_workers=max(1, len(conectores)), thread_name_prefix="tienda") as ex:
        futuros = [(t, ex.submit(_consultar_tienda, t, consultas)) for t in conectores]
    for tienda, futuro in futuros:
        cands, error = futuro.result()
        try:
            if error:
                raise error
        except td.ErrorTienda as e:
            m.notas.append(f"{tienda.nombre}: {e}")
            if not td.es_bloqueo(str(e)):
                continue
            # Bloqueó su sitio: lo que Google muestra de esa tienda (26 nov 2026)
            de_google = _respaldo_google(bd, m, tienda, consultas, referencia)
            if de_google is None:
                continue
            elegido, _ = _elegir(bd, nombre, marca, list(de_google.values()), marcas)
            if elegido and _precio(elegido):
                _agregar(m, [elegido], td.FUENTE_GOOGLE_SITIO)
            elif elegido:
                m.notas.append(f"{tienda.nombre}: según Google sí lo vende ({elegido.datos.get('url')}), pero Google no "
                               "muestra su precio.")
            else:
                m.notas.append(f"{tienda.nombre}: en Google no aparece este producto en su sitio.")
            continue
        except Exception:  # noqa: BLE001 - una tienda no detiene la evaluación
            log.exception("Radar de productos: falló la búsqueda en %s", tienda.nombre)
            m.notas.append(f"{tienda.nombre}: no se pudo leer su buscador.")
            continue
        elegido, _ = _elegir(bd, nombre, marca, list(cands.values()), marcas)
        if elegido and _precio(elegido):
            _agregar(m, [elegido], "sitio")
        else:
            m.notas.append(f"{tienda.nombre}: no lo tiene." if not cands else f"{tienda.nombre}: no está claro que lo tenga.")


def _consultas(bd: Session, m: "Mercado | None", nombre: str, marca: str | None, codigo_barras: str | None
               ) -> tuple[list[tuple[str, str]], set[str], str | None]:
    """Las búsquedas del producto, las marcas conocidas y la marca con que se compara."""
    # Por código de barras primero, como el radar de precios (ajuste precios_barras_primero; 13 nov 2026)
    marcas = pc._marcas(bd)
    consultas = co.consultas(nombre, marca, codigo_barras, barras_primero=configuracion().precios_barras_primero,
                             marcas_conocidas=marcas)
    if not consultas:
        return [], marcas, marca
    # También como lo buscaría una persona: el nombre sin la presentación (BDM Life: con «120 CAP DE 1.2G» Google
    # regresaba otros productos de 120 cápsulas). La presentación se sigue revisando al comparar los resultados.
    if (desc := next((t for e, t in consultas if e == "descripcion"), None)) and             (corto := co.nombre_sin_medidas(desc)) and co.normalizar(corto) != co.normalizar(desc) and len(corto.split()) >= 2:
        consultas.append(("nombre", corto[:200]))
    # Como vienen los nombres del catálogo de SMNBI (los del radar de precios): solo letras y números. Las ideas de
    # Compras traen «+» y «–» y Google regresaba cualquier cosa (BDM Life: una muñeca de Disney; 25 nov 2026)
    consultas = list(dict.fromkeys((e, co.texto_plano(t)) for e, t in consultas))
    # Se compara contra la marca con que se vende si nuestro nombre empieza con ella (BDM-LIFE, no JUVETERNAL)
    if vende := co.marca_del_nombre(nombre, marca, marcas):
        if m is not None:
            m.notas.append(f"Se buscó con la marca «{vende.upper()}» de su nombre (capturada: {marca}).")
        marca = vende
    return consultas, marcas, marca


SIN_CONECTAR_ML = "Mercado Libre: sin conectar"


def ml_pendiente(m: "Mercado") -> bool:
    """La búsqueda guardada se hizo sin la aplicación de Mercado Libre y hoy ya está capturada."""
    cfg = configuracion()
    return bool(cfg.mercado_libre_app_id and cfg.mercado_libre_clave) and any(
        n.startswith(SIN_CONECTAR_ML) for n in m.notas)


def refrescar_mercado_libre(bd: Session, m: "Mercado", nombre: str, marca: str | None, codigo_barras: str | None) -> "Mercado":
    """Al reusar una búsqueda de afuera (7 días) que se hizo sin la aplicación de Mercado Libre, se pregunta otra vez
    solo a Mercado Libre, que no cuesta DataForSEO (revisión del 26 nov 2026: Diego capturó la aplicación y el radar
    seguía diciendo «sin conectar»). Lo demás de la búsqueda se queda igual."""
    consultas, marcas, marca = _consultas(bd, None, nombre, marca, codigo_barras)
    if not consultas:
        return m
    ml, notas, elegidos = sv.mercado_libre(bd, nombre, marca, consultas, lambda c: _elegir(bd, nombre, marca, c, marcas))
    m.notas = [n for n in m.notas if not n.startswith("Mercado Libre")] + notas
    m.precios = [p for p in m.precios if p.get("fuente") != "mercadolibre"]
    _agregar(m, elegidos, "mercadolibre")
    otras = [x for x in sv.de_lista(m.senales) if x.fuente == "Amazon"]
    m.senales = sv.a_dicts(sv.de_precios(m.precios) + ml + otras)
    return m


def buscar(bd: Session, nombre: str, marca: str | None, codigo_barras: str | None, referencia: str,
           extras: list[str] | None = None) -> Mercado:
    """Busca el producto en Google Shopping y en las tiendas clave. Nunca lanza: lo que falle queda en las notas.
    `extras`: búsquedas de rescate, como las haría una persona (la marca y su ingrediente), si con las primeras Google
    no regresó el producto."""
    m = Mercado(buscado_en=ahora().isoformat(), clave=clave_de(nombre, marca, codigo_barras))
    consultas, marcas, marca = _consultas(bd, m, nombre, marca, codigo_barras)
    if not consultas:
        m.notas.append("No hay nombre ni código de barras para buscarlo.")
        return m
    # Las tiendas de Compras vía Google se mandan primero y se recogen después: su espera corre junto con lo demás
    tiendas_google = _tiendas_google_enviar(bd, m, consultas, referencia)
    _avance(m, "buscando en Google Shopping")
    _google(bd, m, nombre, marca, consultas, marcas, referencia)
    # Diego, 26 nov 2026 (B-Fit Femme Colágeno + Inositol): cada tienda le pone su nombre y con «B FIT COLAGENO INOSITOL
    # 360 G» Google regresó otros inositoles. Si no se tomó nada, una vuelta más con la marca y el ingrediente; lo que
    # regrese igual tiene que pasar marca, nombre y presentación al compararlo.
    ya = {co.normalizar(t) for _, t in consultas}
    rescate = [("rescate", t) for t in dict.fromkeys(co.texto_plano(x)[:200] for x in extras or [] if x and x.strip())
               if co.normalizar(t) not in ya and len(t.split()) >= 2]
    if rescate and not m.precios:
        _avance(m, "buscando también con la marca y su ingrediente")
        _google(bd, m, nombre, marca, rescate, marcas, referencia)
    # Las tiendas clave (Walmart, San Pablo, Chedraui, Soriana), con las consultas originales y después del rescate,
    # para que un precio de tienda no apague el rescate de Google. v0.6.11 borró esta llamada al unir cambios y el
    # producto nuevo dejó de buscarse en las tiendas (revisión del 26 nov 2026)
    _avance(m, "consultando Walmart, Chedraui, San Pablo y Soriana")
    _tiendas(bd, m, nombre, marca, consultas, marcas, referencia)
    _avance(m, "revisando farmacias y tiendas de Compras")
    _tiendas_google_recoger(bd, m, nombre, marca, marcas, tiendas_google)
    _avance(m, "revisando Mercado Libre y Amazon")
    senal_de_venta(bd, m, nombre, marca, consultas, marcas, referencia)
    return m


def senal_de_venta(bd: Session, m: Mercado, nombre: str, marca: str | None, consultas: list[tuple[str, str]],
                   marcas: set[str], referencia: str) -> None:
    """¿Se vende afuera? Mercado Libre y Amazon México, más lo que ya trajeron Walmart y Google Shopping. Sus precios
    cuentan como unos más de afuera. Nunca lanza (22 nov 2026)."""
    def elegir(cands):
        return _elegir(bd, nombre, marca, cands, marcas)

    ml, notas_ml, elegidos_ml = sv.mercado_libre(bd, nombre, marca, consultas, elegir)
    _agregar(m, elegidos_ml, "mercadolibre")
    try:
        az, notas_az, elegidos_az, costo = sv.amazon(bd, nombre, marca, consultas, elegir, referencia)
    except Exception:  # noqa: BLE001
        # Sin rollback la sesión quedaba inservible y la evaluación entera fallaba (22 nov 2026, ck_precio_envio_tipo)
        bd.rollback()
        log.exception("Radar de productos: falló Amazon para «%s»", nombre)
        az, notas_az, elegidos_az, costo = [], ["Amazon: no se pudo leer su respuesta."], [], Decimal(0)
    _agregar(m, elegidos_az, "amazon")
    m.costo_usd += costo
    m.notas += notas_ml + notas_az
    m.senales = sv.a_dicts(sv.de_precios(m.precios) + ml + az)
