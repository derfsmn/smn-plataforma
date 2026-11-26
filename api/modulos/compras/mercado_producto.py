"""Precios de internet de un producto que todavía no vendemos, con las mismas piezas del radar de precios
(pedido de Diego, 2026-10-26: «que se evalúe con todo lo que tenemos»).

Busca el producto en Google Shopping (DataForSEO) y en el sitio de las tiendas clave (Walmart, Chedraui, San Pablo,
Soriana). Para decidir qué resultado es el mismo producto usa las reglas del radar de precios (marca, nombre,
presentación, código de barras) y, si quedan dudosos, la IA. El gasto de DataForSEO queda en «Corridas y gasto» del
radar de precios como una corrida «Radar de productos» y cuenta para el tope del mes.
"""
import json
import logging
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
DIAS_VIGENCIA = 7  # al recalcular dentro de una semana se reusa la búsqueda y no se vuelve a pagar
MAX_PRECIOS = 30
# Versión de la regla que decide si una publicación es el mismo producto. Una búsqueda sin precios hecha con una regla
# anterior se vuelve a hacer al recalcular (25 nov 2026: la línea de la marca, «BDM Life» de JUVETERNAL)
REGLA = 5  # 5: consultas en texto plano, sin «+» ni «–», como las del radar de precios (BDM Life, v0.6.2)


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

    def mediana(self) -> Decimal | None:
        return Decimal(str(median([Decimal(str(p["precio"])) for p in self.precios]))) if self.precios else None

    def a_json(self) -> str:
        return json.dumps({"precios": self.precios, "notas": self.notas, "publicacion": self.publicacion,
                           "costo_usd": str(self.costo_usd), "buscado_en": self.buscado_en, "clave": self.clave,
                           "senales": self.senales, "regla": self.regla},
                          ensure_ascii=False)

    @classmethod
    def de_json(cls, texto: str | None) -> "Mercado | None":
        if not texto:
            return None
        d = json.loads(texto)
        return cls(precios=d.get("precios") or [], notas=d.get("notas") or [], publicacion=d.get("publicacion"),
                   costo_usd=Decimal(d.get("costo_usd") or "0"), buscado_en=d.get("buscado_en"), clave=d.get("clave") or "",
                   senales=d.get("senales") or [], regla=int(d.get("regla") or 1))

    def vigente(self, clave: str) -> bool:
        if self.clave != clave or not self.buscado_en:
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


def _agregar(m: Mercado, candidatos: list[co.Candidato], fuente: str) -> None:
    vistos = {(p["vendedor"], p["precio"]) for p in m.precios}
    for c in candidatos:
        precio = _precio(c)
        vendedor = str(c.datos.get("seller") or c.datos.get("source") or "Vendedor sin nombre")[:120]
        if precio is None or (vendedor, float(precio)) in vistos or len(m.precios) >= MAX_PRECIOS:
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
        r = puerta.ejecutar(bd, pc.TAREA_IA, usuario_id=None, instrucciones=co.INSTRUCCIONES_IA,
                            mensaje=co.mensaje_ia(nombre, marca, dudosos), max_tokens=400, esfuerzo="low")
        elegido, _, _ = co.leer_respuesta_ia(r.texto, dudosos)
        return elegido
    except (puerta.ErrorIA, ValueError, TypeError) as e:
        log.info("Radar de productos: la IA no decidió entre los dudosos de «%s»: %s", nombre, e)
        return None


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
        for tag, items in dfs.recoger("productos", ids).items():
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


def _tiendas(bd: Session, m: Mercado, nombre: str, marca: str | None, consultas: list[tuple[str, str]], marcas: set[str]) -> None:
    log.info("Precios de afuera: buscando «%s» en las tiendas clave", nombre[:80])
    ultima = [0.0]
    for tienda in td.conectores(pc.tiendas_directas()):
        cands: dict[str, co.Candidato] = {}
        try:
            for estrategia, texto in consultas:
                for i, r in enumerate(td.buscar_con_pausa(tienda, texto, ultima)):
                    c = cands.setdefault(r.clave, pc.candidato_tienda(tienda, r, i + 1))
                    if r.datos.get("venta"):  # reseñas y «Comprado +X veces» de Walmart (22 nov 2026)
                        c.datos["venta"] = r.datos["venta"]
                    c.estrategias.add(estrategia)
        except td.ErrorTienda as e:
            m.notas.append(f"{tienda.nombre}: {e}")
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


def buscar(bd: Session, nombre: str, marca: str | None, codigo_barras: str | None, referencia: str) -> Mercado:
    """Busca el producto en Google Shopping y en las tiendas clave. Nunca lanza: lo que falle queda en las notas."""
    m = Mercado(buscado_en=ahora().isoformat(), clave=clave_de(nombre, marca, codigo_barras))
    # Por código de barras primero, como el radar de precios (ajuste precios_barras_primero; 13 nov 2026)
    marcas = pc._marcas(bd)
    consultas = co.consultas(nombre, marca, codigo_barras, barras_primero=configuracion().precios_barras_primero,
                             marcas_conocidas=marcas)
    if not consultas:
        m.notas.append("No hay nombre ni código de barras para buscarlo.")
        return m
    # También como lo buscaría una persona: el nombre sin la presentación (BDM Life: con «120 CAP DE 1.2G» Google
    # regresaba otros productos de 120 cápsulas). La presentación se sigue revisando al comparar los resultados.
    if (desc := next((t for e, t in consultas if e == "descripcion"), None)) and \
            (corto := co.nombre_sin_medidas(desc)) and co.normalizar(corto) != co.normalizar(desc) and len(corto.split()) >= 2:
        consultas.append(("nombre", corto[:200]))
    # Como vienen los nombres del catálogo de SMNBI (los del radar de precios): solo letras y números. Las ideas de
    # Compras traen «+» y «–» y Google regresaba cualquier cosa (BDM Life: una muñeca de Disney; 25 nov 2026)
    consultas = list(dict.fromkeys((e, co.texto_plano(t)) for e, t in consultas))
    # Se compara contra la marca con que se vende si nuestro nombre empieza con ella (BDM-LIFE, no JUVETERNAL)
    if vende := co.marca_del_nombre(nombre, marca, marcas):
        m.notas.append(f"Se buscó con la marca «{vende.upper()}» de su nombre (capturada: {marca}).")
        marca = vende
    _google(bd, m, nombre, marca, consultas, marcas, referencia)
    _tiendas(bd, m, nombre, marca, consultas, marcas)
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
