"""Calificación de proveedores con lo que ya está cargado de SMNBI (pedido de Diego, 2026-10-28: «un módulo de
proveedores donde esté en datos» y cómo evaluarlos; eligió ficha y calificación).

Cuatro bloques de 0 a 100, que se suman con los pesos que Compras pone en la Base de conocimiento (si no los ha puesto,
los provisionales de PESOS). Las escalas de cada métrica son provisionales hasta que Compras defina las suyas.

- Cumplimiento (órdenes de los últimos 12 meses cargados): % de piezas surtidas, días de retraso contra lo que promete
  en tblProveedores (los dos en días hábiles de lunes a viernes, sin festivos oficiales) y % de piezas perdidas o
  rechazadas. Se califica con 3 órdenes o más.
- Comercial (venta de las últimas 26 semanas cargadas, sin mayoreo): margen real de sus SKU contra el de toda la
  empresa, % de sus SKU activos con buena rotación y % debajo de la permanencia (metas de la Base de conocimiento).
- Costo y condiciones: costo de la última compra contra el promedio de 12 meses (ponderado por piezas) y días de
  crédito que se leen de la condición de pago.
- Inventario (foto más reciente): días que alcanza su existencia al ritmo de las últimas 13 semanas y % de sus SKU con
  más de 180 días.

Informativo, sin calificar: su precio de venta contra el mercado (última corrida regular del Radar de precios).

Un SKU es del proveedor por datos.producto.codigo_proveedor (de tblArticulos). Todo se calcula en Python con unas
pocas consultas agrupadas por SKU: sin listas largas en IN (SQL Server acepta a lo más 2,100 parámetros).
"""
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from statistics import median

from sqlalchemy import case, delete, func, select, true
from sqlalchemy.orm import Session

from nucleo.calendario import dias_habiles

from datos.modelos import (CompraOrden, CostoArticulo, Inventario, Producto, Proveedor, ProveedorCalificacion,
                           ProveedorEvaluacion, VentaSemanal)
from nucleo.modelos import ahora

log = logging.getLogger("smn.datos.proveedores")

BLOQUES = {
    "cumplimiento": ("Cumplimiento", "Surte lo que se le pide, a tiempo y sin rechazos"),
    "comercial": ("Desempeño comercial", "Margen, rotación y permanencia de sus productos"),
    "costo": ("Costo y condiciones", "Si sube su costo y cuántos días de crédito da"),
    "inventario": ("Inventario", "Días de inventario y productos con exceso"),
}
PESOS = {"cumplimiento": 35, "comercial": 30, "costo": 20, "inventario": 15}  # provisionales (Diego, 2026-10-28)
SEMANAS_VENTA = 26
SEMANAS_RITMO = 13
SEMANAS_MES = 4.345
MESES_COMPRAS = 12
MIN_ORDENES = 3
DIAS_EXCESO = 180
META_ROTACION = 3.0  # piezas por sucursal al mes si Compras no tiene la meta (su «buena rotación del resto»)
META_PERMANENCIA = 0.75  # su «permanencia del resto y deportivos»
TOP_SKUS = 40
EVALUACIONES_GUARDADAS = 10


def _lineal(x: float, cero: float, cien: float) -> float:
    """0 en `cero`, 100 en `cien`, recta entre los dos (sirve en ambos sentidos)."""
    if cien == cero:
        return 100.0
    return max(0.0, min(100.0, (x - cero) / (cien - cero) * 100))


def _tramos(x: float, puntos: list[tuple[float, float]]) -> float:
    """Interpola entre (x, puntaje) ordenados por x."""
    if x <= puntos[0][0]:
        return puntos[0][1]
    for (x0, y0), (x1, y1) in zip(puntos, puntos[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return puntos[-1][1]


def _promedio(valores: list[float | None]) -> int | None:
    v = [x for x in valores if x is not None]
    return round(sum(v) / len(v)) if v else None


def dias_credito(condicion: str | None) -> int | None:
    """«30 DIAS» → 30, «CONTADO» → 0; None si no se entiende."""
    t = (condicion or "").upper()
    if "CONTADO" in t:
        return 0
    m = re.search(r"(\d{1,3})", t)
    return int(m.group(1)) if m else None


def color_de(puntaje: int | None, confianza: str) -> str | None:
    """Mismos cortes que el semáforo de productos: más de 80 verde, 60 a 80 amarillo, menos rojo."""
    if puntaje is None:
        return None
    color = "verde" if puntaje > 80 else "amarillo" if puntaje >= 60 else "rojo"
    return "amarillo" if color == "verde" and confianza == "baja" else color


# ---------------------------------------------------------------- metas y pesos de Compras

@dataclass
class Metas:
    rotacion: dict[str | None, float]  # por departamento; None = general
    permanencia: dict[str | None, float]
    provisional: list[str] = field(default_factory=list)

    def de(self, tabla: dict[str | None, float], departamento: str | None, defecto: float) -> float:
        return tabla.get(departamento, tabla.get(None, defecto))


def metas(bd: Session) -> Metas:
    """Metas de la Base de conocimiento: «Lanzamiento exitoso» (buena rotación) y el umbral de «permanencia»."""
    from modulos.compras.modelos_conocimiento import ConocimientoRegla

    rot: dict[str | None, float] = {}
    per: dict[str | None, float] = {}
    general: dict[str, float] = {}
    for r in bd.scalars(select(ConocimientoRegla).where(ConocimientoRegla.activa == true(),
                                                       ConocimientoRegla.minimo.is_not(None))):
        texto = r.criterio.lower()
        if "pieza" not in (r.unidad or "").lower() and "pieza" not in texto:
            continue
        if r.tipo == "exito" and "rotaci" in texto:
            if r.departamento:
                rot[r.departamento] = float(r.minimo)
            elif "resto" in texto:
                general["resto"] = float(r.minimo)
            elif "impulso" not in texto and "deport" not in texto:  # esas dos necesitan su departamento
                general.setdefault("otra", float(r.minimo))
        elif r.tipo == "umbral" and "permanencia" in texto:
            per[r.departamento or None] = float(r.minimo)
    if g := general.get("resto", general.get("otra")):
        rot[None] = g
    m = Metas(rot, per)
    if None not in rot:
        m.provisional.append(f"buena rotación {META_ROTACION:g} piezas por sucursal al mes")
    if None not in per:
        m.provisional.append(f"permanencia {META_PERMANENCIA:g} piezas por sucursal al mes")
    return m


def pesos(bd: Session) -> tuple[dict[str, int], str]:
    """Los de Compras si están los 4 y suman 100; si no, los provisionales."""
    from modulos.compras.modelos_conocimiento import ConocimientoPesoProveedor

    filas = {p.bloque: p.puntos for p in bd.scalars(select(ConocimientoPesoProveedor))}
    if set(filas) == set(BLOQUES) and sum(filas.values()) == 100:
        return filas, "compras"
    return dict(PESOS), "provisionales"


# ---------------------------------------------------------------- cálculo

@dataclass
class Sku:
    sku: str
    descripcion: str | None
    departamento: str | None
    activo: bool
    netas: float = 0.0
    tiendas: int = 0
    semanas: int = 0
    recientes: float = 0.0  # últimas 13 semanas
    importe: float = 0.0
    importe_con_costo: float = 0.0
    costo: float = 0.0
    existencia: float | None = None

    @property
    def por_tienda_mes(self) -> float:
        return self.netas / max(1, self.tiendas) / max(1, self.semanas) * SEMANAS_MES

    @property
    def dias_inventario(self) -> float | None:
        if not self.existencia or self.existencia <= 0:
            return None
        if self.recientes <= 0:
            return float("inf")
        return self.existencia / (self.recientes / (SEMANAS_RITMO * 7))


def _skus(bd: Session) -> tuple[dict[str, list[Sku]], dict]:
    """SKU de cada proveedor con su venta (26 semanas, sin mayoreo) e inventario (foto más reciente)."""
    from modulos.compras import realidad_producto as rr

    por_sku: dict[str, Sku] = {}
    de_quien: dict[str, str] = {}
    for sku, prov, desc, depto, activo in bd.execute(select(
            Producto.sku, Producto.codigo_proveedor, Producto.descripcion, Producto.departamento, Producto.activo)
            .where(Producto.codigo_proveedor.is_not(None))):
        prov = (prov or "").strip()
        if prov:
            por_sku[sku] = Sku(sku, desc, depto, bool(activo))
            de_quien[sku] = prov
    contexto: dict = {}
    v = rr.ventana(bd, SEMANAS_VENTA)
    if v:
        contexto["venta"] = v.texto()
        mitad = v.fin - timedelta(weeks=SEMANAS_RITMO)
        netas = VentaSemanal.piezas - VentaSemanal.piezas_devueltas
        con_costo = VentaSemanal.costo.is_not(None)
        q = (select(VentaSemanal.sku, func.sum(netas), func.count(VentaSemanal.tienda.distinct()),
                    func.count(VentaSemanal.semana.distinct()),
                    func.sum(case((VentaSemanal.semana > mitad, netas), else_=0)), func.sum(VentaSemanal.importe),
                    func.sum(case((con_costo, VentaSemanal.importe), else_=0)),
                    func.sum(case((con_costo, VentaSemanal.costo), else_=0)))
             .where(*v.filtro()).group_by(VentaSemanal.sku))
        for sku, n, t, s, r, imp, imp_c, costo in bd.execute(q):
            if x := por_sku.get(sku):
                x.netas, x.tiendas, x.semanas, x.recientes = float(n or 0), t, s, float(r or 0)
                x.importe, x.importe_con_costo, x.costo = float(imp or 0), float(imp_c or 0), float(costo or 0)
        total_imp, total_costo = bd.execute(select(
            func.sum(case((VentaSemanal.costo.is_not(None), VentaSemanal.importe), else_=0)),
            func.sum(VentaSemanal.costo)).where(*v.filtro())).one()
        if total_imp and total_costo and total_imp > 0:
            contexto["margen_empresa"] = round((float(total_imp) - float(total_costo)) / float(total_imp) * 100, 1)
    corte = bd.scalar(select(func.max(Inventario.fecha_corte)))
    if corte:
        contexto["inventario"] = f"foto del inventario del {corte:%d/%m/%Y}"
        for sku, ex in bd.execute(select(Inventario.sku, func.sum(Inventario.existencia))
                                  .where(Inventario.fecha_corte == corte).group_by(Inventario.sku)):
            if x := por_sku.get(sku):
                x.existencia = float(ex or 0)
    agrupado: dict[str, list[Sku]] = {}
    for sku, prov in de_quien.items():
        agrupado.setdefault(prov, []).append(por_sku[sku])
    return agrupado, contexto


def _ordenes(bd: Session) -> tuple[dict[str, list[CompraOrden]], str | None]:
    ultima = bd.scalar(select(func.max(CompraOrden.fecha_orden)))
    if not ultima:
        return {}, None
    desde = ultima - timedelta(days=365 * MESES_COMPRAS // 12)
    salida: dict[str, list[CompraOrden]] = {}
    for o in bd.scalars(select(CompraOrden).where(CompraOrden.fecha_orden >= desde, CompraOrden.piezas_pedidas > 0)):
        if o.proveedor:
            salida.setdefault(o.proveedor.strip(), []).append(o)
    return salida, f"órdenes de compra del {desde:%d/%m/%Y} al {ultima:%d/%m/%Y}"


def _costos(bd: Session) -> dict[str, tuple[float, int]]:
    """Por proveedor: alza del costo (%) de la última compra contra el promedio de 12 meses, y cuántos SKU."""
    suma: dict[str, list[float]] = {}
    for c in bd.scalars(select(CostoArticulo).where(CostoArticulo.costo_ultimo > 0, CostoArticulo.costo_12m > 0,
                                                    CostoArticulo.piezas_12m > 0)):
        if not c.proveedor:
            continue
        s = suma.setdefault(c.proveedor.strip(), [0.0, 0.0, 0])
        piezas = float(c.piezas_12m)
        s[0] += float(c.costo_ultimo) * piezas
        s[1] += float(c.costo_12m) * piezas
        s[2] += 1
    return {p: ((a / b - 1) * 100, int(n)) for p, (a, b, n) in suma.items() if b > 0}


def _precios(bd: Session) -> tuple[dict[str, list[float]], str | None]:
    """Diferencia de nuestro precio contra la mediana del mercado de sus productos (última corrida regular)."""
    from modulos.compras import precios as pr
    from modulos.compras.modelos_precios import PrecioCorrida, PrecioCorridaProducto

    c = bd.scalar(select(PrecioCorrida).where(PrecioCorrida.estado != "en_curso", pr.REGULAR)
                  .order_by(PrecioCorrida.fecha.desc(), PrecioCorrida.corrida_id.desc()))
    if not c:
        return {}, None
    salida: dict[str, list[float]] = {}
    for f, prov in bd.execute(select(PrecioCorridaProducto, Producto.codigo_proveedor)
                              .join(Producto, Producto.producto_id == PrecioCorridaProducto.producto_id)
                              .where(PrecioCorridaProducto.corrida_id == c.corrida_id)):
        if prov and (d := pr.dif_nuestro(f)) is not None:
            salida.setdefault(prov.strip(), []).append(float(d))
    return salida, f"Radar de precios del {c.fecha:%d/%m/%Y}"


def calificar(p: Proveedor | None, codigo: str, skus: list[Sku], ordenes: list[CompraOrden],
              alza: tuple[float, int] | None, precios: list[float], m: Metas, peso: dict[str, int],
              margen_empresa: float | None) -> ProveedorCalificacion:
    met: dict = {"notas": []}
    bloques: dict[str, int | None] = {}

    # Cumplimiento
    if len(ordenes) >= MIN_ORDENES:
        pedidas = sum(float(o.piezas_pedidas) for o in ordenes)
        surtido = min(100.0, sum(float(o.piezas_recibidas) for o in ordenes) / pedidas * 100)
        malas = sum(float(o.piezas_perdidas) + float(o.piezas_rechazadas) for o in ordenes) / pedidas * 100
        dias = [dias_habiles(o.fecha_orden, o.primera_entrada) for o in ordenes if o.primera_entrada]  # lo prometido es en hábiles
        reales = sum(dias) / len(dias) if dias else None
        prometidos = p.dias_entrega if p and p.dias_entrega else None
        retraso = max(0.0, reales - prometidos) if reales is not None and prometidos else None
        met["cumplimiento"] = {"ordenes": len(ordenes), "surtido_pct": round(surtido, 1),
                               "perdidas_rechazadas_pct": round(malas, 1),
                               "dias_reales": round(reales, 1) if reales is not None else None,
                               "dias_prometidos": prometidos, "retraso_dias": round(retraso, 1) if retraso is not None else None}
        bloques["cumplimiento"] = _promedio([_lineal(surtido, 70, 98), _lineal(malas, 10, 0),
                                             _lineal(retraso, 10, 0) if retraso is not None else None])
    else:
        bloques["cumplimiento"] = None
        met["notas"].append(f"{len(ordenes)} orden(es) en 12 meses: el cumplimiento se califica con {MIN_ORDENES} o más.")

    # Comercial
    activos = [s for s in skus if s.activo]
    imp_c = sum(s.importe_con_costo for s in skus)
    margen = (imp_c - sum(s.costo for s in skus)) / imp_c * 100 if imp_c > 0 else None
    if activos and any(s.netas for s in activos):
        buenos = [s for s in activos if s.por_tienda_mes >= m.de(m.rotacion, s.departamento, META_ROTACION)]
        bajos = [s for s in activos if s.por_tienda_mes < m.de(m.permanencia, s.departamento, META_PERMANENCIA)]
        buena_pct, bajo_pct = len(buenos) / len(activos) * 100, len(bajos) / len(activos) * 100
        partes = [_lineal(buena_pct, 0, 60), _lineal(bajo_pct, 50, 0)]
        if margen is not None and margen_empresa is not None:
            partes.append(_tramos(margen - margen_empresa, [(-10, 0), (0, 70), (10, 100)]))
        bloques["comercial"] = _promedio(partes)
        met["comercial"] = {"margen_pct": round(margen, 1) if margen is not None else None,
                            "margen_empresa_pct": margen_empresa, "skus_activos": len(activos),
                            "buena_rotacion": len(buenos), "buena_rotacion_pct": round(buena_pct, 1),
                            "debajo_permanencia": len(bajos), "debajo_permanencia_pct": round(bajo_pct, 1)}
    else:
        bloques["comercial"] = None
        met["notas"].append("Sin venta de sus productos activos en la ventana.")

    # Costo y condiciones
    credito = dias_credito(p.condicion if p else None)
    partes = []
    if alza:
        partes.append(_lineal(alza[0], 10, 0))
    if credito is not None:
        partes.append(_tramos(credito, [(0, 20), (30, 70), (60, 100)]))
    bloques["costo"] = _promedio(partes)
    met["costo"] = {"alza_costo_pct": round(alza[0], 1) if alza else None, "skus_con_costo": alza[1] if alza else 0,
                    "condicion": p.condicion if p else None, "dias_credito": credito,
                    "descuento": p.descuento if p else None}

    # Inventario
    con_ex = [s for s in skus if s.existencia and s.existencia > 0]
    if con_ex:
        existencia = sum(s.existencia for s in con_ex)
        ritmo = sum(s.recientes for s in con_ex) / (SEMANAS_RITMO * 7)
        dias = existencia / ritmo if ritmo > 0 else None
        exceso = [s for s in con_ex if (s.dias_inventario or 0) > DIAS_EXCESO]
        exceso_pct = len(exceso) / len(con_ex) * 100
        bloques["inventario"] = _promedio([_tramos(dias, [(60, 100), (240, 0)]) if dias is not None else 0.0,
                                           _lineal(exceso_pct, 50, 0)])
        met["inventario"] = {"existencia": round(existencia), "dias": round(dias) if dias is not None else None,
                             "skus_con_existencia": len(con_ex), "skus_exceso": len(exceso),
                             "skus_exceso_pct": round(exceso_pct, 1)}
    else:
        bloques["inventario"] = None

    if precios:
        met["precio_mercado"] = {"productos": len(precios), "mediana_dif_pct": round(median(precios), 1),
                                 "mas_caros": sum(1 for d in precios if d > 0)}

    con_datos = {b: v for b, v in bloques.items() if v is not None}
    cubierto = sum(peso[b] for b in con_datos)
    puntaje = round(sum(peso[b] * v for b, v in con_datos.items()) / cubierto) if cubierto else None
    confianza = "sin_datos" if not cubierto else "alta" if cubierto >= 80 else "media" if cubierto >= 50 else "baja"
    met["skus"] = [{"sku": s.sku, "descripcion": s.descripcion, "departamento": s.departamento, "activo": s.activo,
                    "por_tienda_mes": round(s.por_tienda_mes, 2) if s.netas else 0, "venta": round(s.importe, 2),
                    "margen_pct": round((s.importe_con_costo - s.costo) / s.importe_con_costo * 100, 1)
                    if s.importe_con_costo > 0 else None,
                    "dias_inventario": None if s.dias_inventario in (None, float("inf")) else round(s.dias_inventario),
                    "sin_venta_con_existencia": s.dias_inventario == float("inf"),
                    "meta": m.de(m.rotacion, s.departamento, META_ROTACION),
                    "permanencia": m.de(m.permanencia, s.departamento, META_PERMANENCIA)}
                   for s in sorted(skus, key=lambda s: -s.importe)[:TOP_SKUS]]
    return ProveedorCalificacion(
        proveedor=codigo, nombre=(p.nombre if p else None), puntaje=puntaje, color=color_de(puntaje, confianza),
        confianza=confianza, skus_activos=len(activos), venta=round(sum(s.importe for s in skus), 2) if skus else None,
        compra=round(sum(float(o.importe_pedido or 0) for o in ordenes), 2) if ordenes else None,
        metricas=json.dumps(met, ensure_ascii=False), **bloques)


def evaluar(bd: Session, evaluacion_id: int) -> None:
    ev = bd.get(ProveedorEvaluacion, evaluacion_id)
    try:
        catalogo = {p.proveedor.strip(): p for p in bd.scalars(select(Proveedor))}
        skus, contexto = _skus(bd)
        ordenes, texto_compras = _ordenes(bd)
        costos = _costos(bd)
        precios, texto_precios = _precios(bd)
        m = metas(bd)
        peso, de_quien = pesos(bd)
        codigos = set(catalogo) | set(ordenes) | {c for c, lista in skus.items() if any(s.activo for s in lista)}
        calificados = 0
        for codigo in sorted(codigos):
            c = calificar(catalogo.get(codigo), codigo, skus.get(codigo, []), ordenes.get(codigo, []),
                          costos.get(codigo), precios.get(codigo, []), m, peso, contexto.get("margen_empresa"))
            if c.puntaje is None and not c.skus_activos and not c.compra:
                continue  # proveedor sin productos ni compras: no se lista
            c.evaluacion_id = evaluacion_id
            calificados += c.puntaje is not None
            bd.add(c)
        ev.proveedores, ev.calificados = len(codigos), calificados
        ev.contexto = json.dumps({**contexto, "compras": texto_compras, "precios": texto_precios, "pesos": peso,
                                  "pesos_de": de_quien, "metas_provisionales": m.provisional,
                                  "metas_rotacion": {k or "general": v for k, v in m.rotacion.items()},
                                  "metas_permanencia": {k or "general": v for k, v in m.permanencia.items()}},
                                 ensure_ascii=False)
        ev.estado, ev.terminada_en = "completa", ahora()
        bd.commit()
        _limpiar(bd)
    except Exception as e:  # noqa: BLE001 - la evaluación se cierra y dice qué pasó
        log.exception("Proveedores: la evaluación %s falló", evaluacion_id)
        bd.rollback()
        ev = bd.get(ProveedorEvaluacion, evaluacion_id)
        ev.estado, ev.terminada_en, ev.error = "fallida", ahora(), str(e)[:1000]
        bd.commit()


def _limpiar(bd: Session) -> None:
    """Se guardan las últimas evaluaciones completas; las demás se borran."""
    viejas = list(bd.scalars(select(ProveedorEvaluacion.evaluacion_id).where(ProveedorEvaluacion.estado != "en_curso")
                             .order_by(ProveedorEvaluacion.evaluacion_id.desc()).offset(EVALUACIONES_GUARDADAS)))
    for i in viejas:
        bd.execute(delete(ProveedorCalificacion).where(ProveedorCalificacion.evaluacion_id == i))
        bd.execute(delete(ProveedorEvaluacion).where(ProveedorEvaluacion.evaluacion_id == i))
    bd.commit()


def en_curso(bd: Session) -> ProveedorEvaluacion | None:
    return bd.scalar(select(ProveedorEvaluacion).where(ProveedorEvaluacion.estado == "en_curso"))


def ultima(bd: Session) -> ProveedorEvaluacion | None:
    return bd.scalar(select(ProveedorEvaluacion).where(ProveedorEvaluacion.estado == "completa")
                     .order_by(ProveedorEvaluacion.evaluacion_id.desc()))


def calificacion_de(bd: Session, codigo: str) -> ProveedorCalificacion | None:
    """La calificación más reciente de un proveedor (la usa el semáforo de productos)."""
    ev = ultima(bd)
    return bd.get(ProveedorCalificacion, (ev.evaluacion_id, codigo)) if ev else None


def iniciar(bd: Session, usuario_id: int | None) -> ProveedorEvaluacion:
    ev = ProveedorEvaluacion(estado="en_curso", iniciada_por=usuario_id, iniciada_en=ahora())
    bd.add(ev)
    bd.flush()
    return ev


def en_hilo(evaluacion_id: int) -> None:
    from core.bd import _fabrica

    def correr():
        with _fabrica()() as bd:
            evaluar(bd, evaluacion_id)

    threading.Thread(target=correr, daemon=True, name=f"proveedores-{evaluacion_id}").start()


def cerrar_huerfanas(bd: Session) -> int:
    abiertas = list(bd.scalars(select(ProveedorEvaluacion).where(ProveedorEvaluacion.estado == "en_curso")))
    for ev in abiertas:
        ev.estado, ev.terminada_en = "fallida", ahora()
        ev.error = "La plataforma se reinició a media evaluación; vuelve a calcular."
    bd.commit()
    return len(abiertas)
