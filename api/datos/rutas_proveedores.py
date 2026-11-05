"""Datos → Proveedores (/api/datos/proveedores): lista con su calificación, ficha de cada uno y el cálculo."""
import json
from urllib.parse import quote
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, ip_de, requiere
from datos import excel_proveedores as xp
from datos import proveedores as pv
from datos.modelos import CompraOrden, Proveedor, ProveedorCalificacion, ProveedorEvaluacion
from nucleo.bitacora import registrar
from nucleo.modelos import Usuario

router = APIRouter(prefix="/api/datos/proveedores", tags=["datos · proveedores"])
VER = requiere("datos.proveedores.ver")
CALCULAR = requiere("datos.proveedores.calcular")


class Bloque(BaseModel):
    clave: str
    nombre: str
    que_mide: str
    peso: int


class Evaluacion(BaseModel):
    id: int
    estado: str
    iniciada_por: str | None
    iniciada_en: datetime
    terminada_en: datetime | None
    proveedores: int | None
    calificados: int | None
    contexto: dict
    error: str | None


class Fila(BaseModel):
    proveedor: str
    nombre: str | None
    puntaje: int | None
    color: str | None
    confianza: str
    cumplimiento: int | None
    comercial: int | None
    costo: int | None
    inventario: int | None
    skus_activos: int
    venta: Decimal | None
    compra: Decimal | None
    agente: str | None = None
    rfc: str | None = None


class Lista(BaseModel):
    evaluacion: Evaluacion | None
    en_curso: Evaluacion | None
    bloques: list[Bloque]
    pesos_de: str  # compras / provisionales
    conteo: dict[str, int]
    filas: list[Fila]
    agentes: list[str] = []  # claves de agente en tblProveedores, para filtrar
    reporte: dict = {}  # Excel para Compras: cuántos en ALTA con agente y qué se cargó después de la evaluación


class Ficha(Fila):
    estatus: str | None
    condicion: str | None
    descuento: str | None
    dias_entrega: int | None
    metricas: dict
    ordenes_por_mes: list[dict]


def _evaluacion(bd: Session, ev: ProveedorEvaluacion | None) -> Evaluacion | None:
    if not ev:
        return None
    u = bd.get(Usuario, ev.iniciada_por) if ev.iniciada_por else None
    return Evaluacion(id=ev.evaluacion_id, estado=ev.estado, iniciada_por=u.nombre if u else None,
                      iniciada_en=ev.iniciada_en, terminada_en=ev.terminada_en, proveedores=ev.proveedores,
                      calificados=ev.calificados, contexto=json.loads(ev.contexto) if ev.contexto else {},
                      error=ev.error)


def _fila(c: ProveedorCalificacion, p: Proveedor | None = None) -> dict:
    return dict(proveedor=c.proveedor, nombre=c.nombre, puntaje=c.puntaje, color=c.color, confianza=c.confianza,
                cumplimiento=c.cumplimiento, comercial=c.comercial, costo=c.costo, inventario=c.inventario,
                skus_activos=c.skus_activos, venta=c.venta, compra=c.compra,
                agente=p.agente if p else None, rfc=p.rfc if p else None)


Orden = Literal["puntaje", "venta", "compra", "nombre"]
Color = Literal["", "verde", "amarillo", "rojo", "sin_datos"]


@router.get("", response_model=Lista)
def lista(q: str = "", color: Color = "", orden: Orden = "venta", agente: str = "", rfc: Literal["", "con", "sin"] = "",
          _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Lista:
    """agente: clave del agente, o «-» para los que no tienen. rfc: con / sin RFC en Intelisis."""
    ev = pv.ultima(bd)
    peso, de_quien = pv.pesos(bd)
    bloques = [Bloque(clave=k, nombre=n, que_mide=m, peso=peso[k]) for k, (n, m) in pv.BLOQUES.items()]
    if not ev:
        return Lista(evaluacion=None, en_curso=_evaluacion(bd, pv.en_curso(bd)), bloques=bloques, pesos_de=de_quien,
                     conteo={}, filas=[])
    base = select(ProveedorCalificacion).where(ProveedorCalificacion.evaluacion_id == ev.evaluacion_id)
    conteo = {(c or "sin_datos"): n for c, n in bd.execute(
        select(ProveedorCalificacion.color, func.count()).where(ProveedorCalificacion.evaluacion_id == ev.evaluacion_id)
        .group_by(ProveedorCalificacion.color))}
    catalogo = {p.proveedor: p for p in bd.scalars(select(Proveedor))}
    agentes = sorted({p.agente for p in catalogo.values() if p.agente})
    if q.strip():
        t = f"%{q.strip()}%"
        por_rfc = [k for k, p in catalogo.items() if p.rfc and p.rfc.startswith(q.strip().upper())]
        base = base.where(or_(ProveedorCalificacion.nombre.ilike(t), ProveedorCalificacion.proveedor.ilike(t),
                              ProveedorCalificacion.proveedor.in_(por_rfc or [""])))
    if color == "sin_datos":
        base = base.where(ProveedorCalificacion.color.is_(None))
    elif color:
        base = base.where(ProveedorCalificacion.color == color)
    filas = list(bd.scalars(base))
    if agente:
        filas = [c for c in filas if ((catalogo.get(c.proveedor) and catalogo[c.proveedor].agente) or "-") == agente]
    if rfc:
        filas = [c for c in filas if bool(catalogo.get(c.proveedor) and catalogo[c.proveedor].rfc) == (rfc == "con")]
    clave = {"puntaje": lambda c: (c.puntaje is None, c.puntaje if c.puntaje is not None else 0),
             "venta": lambda c: -float(c.venta or 0), "compra": lambda c: -float(c.compra or 0),
             "nombre": lambda c: (c.nombre or c.proveedor).lower()}[orden]
    filas.sort(key=clave)
    reporte = {"proveedores": len(xp.en_alta_con_agente(bd, "" if agente == "-" else agente)) if agente != "-" else 0,
               "desactualizada": xp.desactualizada(bd, ev)}
    return Lista(evaluacion=_evaluacion(bd, ev), en_curso=_evaluacion(bd, pv.en_curso(bd)), bloques=bloques,
                 pesos_de=de_quien, conteo=conteo, agentes=agentes, reporte=reporte,
                 filas=[Fila(**_fila(c, catalogo.get(c.proveedor))) for c in filas])


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/excel")
def excel(request: Request, agente: str = "", ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Response:
    """Reporte para Compras: proveedores en ALTA con agente y su última calificación (sin RFC)."""
    try:
        contenido, n = xp.reporte(bd, agente)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    registrar(bd, "proveedores_excel", usuario_id=ctx.usuario.usuario_id, entidad="proveedor_evaluacion",
              detalle={"agente": agente or "todos", "proveedores": n}, ip=ip_de(request))
    bd.commit()
    nombre = f"Proveedores en alta con agente{f' - {agente}' if agente else ''} - {datetime.now():%Y-%m-%d}.xlsx"
    return Response(contenido, media_type=XLSX, headers={
        "Content-Disposition": f"attachment; filename=\"proveedores.xlsx\"; filename*=UTF-8''{quote(nombre)}"})


@router.get("/{codigo}", response_model=Ficha)
def ficha(codigo: str, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Ficha:
    ev = pv.ultima(bd)
    c = bd.get(ProveedorCalificacion, (ev.evaluacion_id, codigo)) if ev else None
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese proveedor no está en la última evaluación.")
    p = bd.get(Proveedor, codigo)
    por_mes: dict[str, list[float]] = {}
    for fecha, pedidas, recibidas in bd.execute(select(CompraOrden.fecha_orden, CompraOrden.piezas_pedidas,
                                                       CompraOrden.piezas_recibidas)
                                                .where(CompraOrden.proveedor == codigo, CompraOrden.piezas_pedidas > 0)):
        m = por_mes.setdefault(f"{fecha:%Y-%m}", [0, 0.0, 0.0])
        m[0] += 1
        m[1] += float(pedidas or 0)
        m[2] += float(recibidas or 0)
    ordenes = [{"mes": k, "ordenes": int(n), "pedidas": pe, "recibidas": re}
               for k, (n, pe, re) in sorted(por_mes.items())]
    return Ficha(**_fila(c, p), estatus=p.estatus if p else None, condicion=p.condicion if p else None,
                 descuento=p.descuento if p else None, dias_entrega=p.dias_entrega if p else None,
                 metricas=json.loads(c.metricas) if c.metricas else {}, ordenes_por_mes=ordenes[-12:])


@router.post("/calcular", response_model=Evaluacion, status_code=status.HTTP_202_ACCEPTED)
def calcular(request: Request, ctx: Contexto = Depends(CALCULAR), bd: Session = Depends(obtener_bd)) -> Evaluacion:
    """Recalcula la calificación de todos los proveedores con lo cargado hoy. Corre aparte."""
    if pv.en_curso(bd):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya se está calculando. Espera a que termine.")
    ev = pv.iniciar(bd, ctx.usuario.usuario_id)
    registrar(bd, "proveedores_calcular", usuario_id=ctx.usuario.usuario_id, entidad="proveedor_evaluacion",
              entidad_id=ev.evaluacion_id, ip=ip_de(request))
    bd.commit()
    pv.en_hilo(ev.evaluacion_id)
    return _evaluacion(bd, ev)
