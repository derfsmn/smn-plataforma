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

from sqlalchemy.orm import Session

from core.config import configuracion
from ia import puerta
from modulos.compras import coincidencia as co
from modulos.compras import dataforseo as dfs
from modulos.compras import precios as pc
from modulos.compras import tiendas as td
from modulos.compras.modelos_precios import PrecioCorrida
from nucleo.modelos import ahora

log = logging.getLogger("smn.compras.mercado_producto")

ORIGEN = pc.PRODUCTO
DIAS_VIGENCIA = 7  # al recalcular dentro de una semana se reusa la búsqueda y no se vuelve a pagar
MAX_PRECIOS = 30


@dataclass
class Mercado:
    precios: list[dict] = field(default_factory=list)  # {precio, vendedor, fuente: google/sitio, titulo, liga}
    notas: list[str] = field(default_factory=list)
    publicacion: str | None = None  # la publicación de Google que se tomó como el mismo producto
    costo_usd: Decimal = Decimal("0")
    buscado_en: str | None = None
    clave: str = ""  # qué se buscó; si cambia, no se reusa

    def mediana(self) -> Decimal | None:
        return Decimal(str(median([Decimal(str(p["precio"])) for p in self.precios]))) if self.precios else None

    def a_json(self) -> str:
        return json.dumps({"precios": self.precios, "notas": self.notas, "publicacion": self.publicacion,
                           "costo_usd": str(self.costo_usd), "buscado_en": self.buscado_en, "clave": self.clave},
                          ensure_ascii=False)

    @classmethod
    def de_json(cls, texto: str | None) -> "Mercado | None":
        if not texto:
            return None
        d = json.loads(texto)
        return cls(precios=d.get("precios") or [], notas=d.get("notas") or [], publicacion=d.get("publicacion"),
                   costo_usd=Decimal(d.get("costo_usd") or "0"), buscado_en=d.get("buscado_en"), clave=d.get("clave") or "")

    def vigente(self, clave: str) -> bool:
        if self.clave != clave or not self.buscado_en:
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
        m.precios.append({"precio": float(precio), "vendedor": vendedor, "fuente": fuente, "titulo": c.titulo[:200],
                          "liga": (c.datos.get("shopping_url") or c.datos.get("url") or "")[:500] or None})


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
        ids = dfs.enviar(bd, corrida, "productos", tareas)
        for tag, items in dfs.recoger("productos", ids).items():
            if isinstance(items, str):
                m.notas.append(f"Google Shopping: {items}.")
                continue
            estrategia = consultas[int(tag)][0]
            for item in items:
                if c := co.candidato_de(item):
                    candidatos.setdefault(c.clave, c).estrategias.add(estrategia)
        elegido, iguales = _elegir(bd, nombre, marca, list(candidatos.values()), marcas)
        if elegido:
            m.publicacion = elegido.titulo[:300]
            _agregar(m, [elegido, *iguales], "google")
        else:
            m.notas.append("Google Shopping: ningún resultado es claramente el mismo producto." if candidatos
                           else "Google Shopping no regresó resultados.")
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
    ultima = [0.0]
    for tienda in td.conectores(pc.tiendas_directas()):
        cands: dict[str, co.Candidato] = {}
        try:
            for estrategia, texto in consultas:
                for i, r in enumerate(td.buscar_con_pausa(tienda, texto, ultima)):
                    c = cands.setdefault(r.clave, pc.candidato_tienda(tienda, r, i + 1))
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
    consultas = co.consultas(nombre, marca, codigo_barras)
    if not consultas:
        m.notas.append("No hay nombre ni código de barras para buscarlo.")
        return m
    marcas = pc._marcas(bd)
    _google(bd, m, nombre, marca, consultas, marcas, referencia)
    _tiendas(bd, m, nombre, marca, consultas, marcas)
    return m
