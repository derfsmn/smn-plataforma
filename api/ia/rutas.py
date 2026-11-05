"""Administración de la puerta de IA: estado, topes, tareas, llamadas y prueba."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.config import configuracion
from core.seguridad import Contexto, ip_de, requiere
from ia import costos, puerta
from nucleo.bitacora import registrar
from nucleo.modelos import IaCostoReal, IaLlamada, IaPresupuesto, IaTarea, Modulo

router = APIRouter(prefix="/api/ia", tags=["puerta de IA"])
ADMIN = requiere(puerta.ADMINISTRAR_IA)
TAREA_PRUEBA = "nucleo.prueba"


class Gasto(BaseModel):
    alcance: str
    modulo: str | None
    nombre: str
    gastado_mxn: Decimal
    tope_mxn: Decimal | None


class EstadoIA(BaseModel):
    ollama_url: str
    ollama_modelo: str | None
    ollama_disponible: bool
    ollama_modelos: list[str]
    api_encendida: bool
    api_motivos: list[str]
    api_proveedor: str
    api_modelo: str
    precio_entrada_usd_mtok: float
    precio_salida_usd_mtok: float
    tipo_cambio_mxn: float | None
    costo_real_activo: bool
    gastos: list[Gasto]


class DiaCosto(BaseModel):
    fecha: date
    estimado_mxn: Decimal
    real_mxn: Decimal | None
    real_usd: Decimal | None


class CostosReales(BaseModel):
    activo: bool
    motivo: str | None
    proyecto: str | None
    ultimo_intento: datetime | None
    error: str | None
    dias: list[DiaCosto]


class Tope(BaseModel):
    alcance: Literal["plataforma", "modulo", "usuario_dia"]
    modulo: str | None = None
    tope_mxn: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    aviso_pct: int = Field(80, ge=1, le=100)
    al_superar: Literal["rechazar", "usar_ollama"] = "rechazar"


class TopeSalida(Tope):
    vigente_desde: date


class TareaSalida(BaseModel):
    codigo: str
    descripcion: str
    modulo: str | None
    proveedor_ia: str
    modelo: str | None
    activa: bool


class CambioTarea(BaseModel):
    proveedor_ia: Literal["ollama", "api", "ollama_y_api_respaldo"] | None = None
    modelo: str | None = Field(None, max_length=120)
    activa: bool | None = None


class LlamadaSalida(BaseModel):
    id: int
    ocurrido_en: datetime
    tarea: str
    usuario: str | None
    proveedor_ia: str
    modelo: str | None
    tokens_entrada: int
    tokens_salida: int
    costo_mxn: Decimal
    duracion_ms: int
    resultado: str
    detalle: str | None


class Prueba(BaseModel):
    mensaje: str = Field(min_length=1, max_length=2000)
    proveedor: Literal["ollama", "api"]


class ResultadoPrueba(BaseModel):
    texto: str
    proveedor: str
    modelo: str
    tokens_entrada: int
    tokens_salida: int
    costo_mxn: Decimal
    duracion_ms: int
    completa: bool


def _tope_salida(p: IaPresupuesto) -> TopeSalida:
    return TopeSalida(alcance=p.alcance, modulo=p.modulo.codigo if p.modulo else None, tope_mxn=p.tope_mxn,
                      aviso_pct=p.aviso_pct, al_superar=p.al_superar, vigente_desde=p.vigente_desde)


@router.get("/estado", response_model=EstadoIA)
def estado(_: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> EstadoIA:
    cfg = configuracion()
    ollama = puerta.estado_ollama()
    mes = puerta.inicio_de_mes()
    plataforma = puerta.presupuesto(bd, "plataforma")
    gastos = [Gasto(alcance="plataforma", modulo=None, nombre="Plataforma (mes)", gastado_mxn=costos.gasto_plataforma(bd, mes),
                    tope_mxn=plataforma.tope_mxn if plataforma else None)]
    for m in bd.scalars(select(Modulo).order_by(Modulo.orden_menu)).all():
        p = puerta.presupuesto(bd, "modulo", m.modulo_id)
        gastos.append(Gasto(alcance="modulo", modulo=m.codigo, nombre=f"{m.area} (mes)",
                            gastado_mxn=puerta.gasto(bd, mes, modulo_id=m.modulo_id), tope_mxn=p.tope_mxn if p else None))
    motivos = puerta.motivos_api_apagada(bd)
    return EstadoIA(
        ollama_url=cfg.ollama_url, ollama_modelo=cfg.ollama_modelo or None, ollama_disponible=ollama["disponible"],
        ollama_modelos=ollama["modelos"], api_encendida=not motivos, api_motivos=motivos,
        api_proveedor="OpenAI" if cfg.ia_proveedor_externo == "openai" else "Anthropic",
        api_modelo=cfg.ia_modelo_externo, precio_entrada_usd_mtok=cfg.ia_precio_entrada_usd_mtok,
        precio_salida_usd_mtok=cfg.ia_precio_salida_usd_mtok, tipo_cambio_mxn=cfg.ia_tipo_cambio_mxn,
        costo_real_activo=costos.activo(), gastos=gastos,
    )


@router.get("/topes", response_model=list[TopeSalida])
def topes(_: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> list[TopeSalida]:
    return [_tope_salida(p) for p in bd.scalars(select(IaPresupuesto).order_by(IaPresupuesto.presupuesto_id)).all()]


@router.put("/topes", response_model=list[TopeSalida])
def guardar_topes(
    datos: list[Tope], request: Request, ctx: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd),
) -> list[TopeSalida]:
    """Reemplaza todos los topes. Un alcance que no viene en la lista se queda sin tope."""
    antes = [t.model_dump(mode="json") for t in topes(ctx, bd)]
    modulos = {m.codigo: m for m in bd.scalars(select(Modulo))}
    vistos = set()
    nuevos = []
    for t in datos:
        if (t.alcance == "modulo") != bool(t.modulo):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo el tope por módulo lleva módulo.")
        if t.modulo and t.modulo not in modulos:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"No existe el módulo {t.modulo}.")
        llave = (t.alcance, t.modulo)
        if llave in vistos:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hay un tope repetido.")
        vistos.add(llave)
        nuevos.append(IaPresupuesto(alcance=t.alcance, modulo_id=modulos[t.modulo].modulo_id if t.modulo else None,
                                    tope_mxn=t.tope_mxn, aviso_pct=t.aviso_pct, al_superar=t.al_superar,
                                    vigente_desde=date.today()))
    bd.execute(delete(IaPresupuesto))
    bd.add_all(nuevos)
    bd.flush()
    despues = [t.model_dump(mode="json") for t in datos]
    registrar(bd, "actualizar", usuario_id=ctx.usuario.usuario_id, entidad="ia_presupuesto",
              detalle={"antes": antes, "despues": despues}, ip=ip_de(request))
    bd.commit()
    return topes(ctx, bd)


@router.get("/tareas", response_model=list[TareaSalida])
def tareas(_: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> list[TareaSalida]:
    return [TareaSalida(codigo=t.codigo, descripcion=t.descripcion, modulo=t.modulo.area if t.modulo else None,
                        proveedor_ia=t.proveedor_ia, modelo=t.modelo, activa=t.activa)
            for t in bd.scalars(select(IaTarea).order_by(IaTarea.codigo)).all()]


@router.patch("/tareas/{codigo}", response_model=TareaSalida)
def cambiar_tarea(
    codigo: str, datos: CambioTarea, request: Request, ctx: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd),
) -> TareaSalida:
    t = bd.scalar(select(IaTarea).where(IaTarea.codigo == codigo))
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa tarea.")
    antes = {"proveedor_ia": t.proveedor_ia, "modelo": t.modelo, "activa": t.activa}
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(t, campo, (valor or None) if campo == "modelo" else valor)
    registrar(bd, "actualizar", usuario_id=ctx.usuario.usuario_id, entidad="ia_tarea", entidad_id=codigo,
              detalle={"antes": antes, "despues": datos.model_dump(exclude_unset=True)}, ip=ip_de(request))
    bd.commit()
    return next(x for x in tareas(ctx, bd) if x.codigo == codigo)


@router.get("/llamadas", response_model=list[LlamadaSalida])
def llamadas(limite: int = Query(50, ge=1, le=200), _: Contexto = Depends(ADMIN),
             bd: Session = Depends(obtener_bd)) -> list[LlamadaSalida]:
    return [
        LlamadaSalida(id=l.llamada_id, ocurrido_en=l.ocurrido_en, tarea=l.tarea.codigo,
                      usuario=l.usuario.nombre if l.usuario else None, proveedor_ia=l.proveedor_ia, modelo=l.modelo,
                      tokens_entrada=l.tokens_entrada, tokens_salida=l.tokens_salida, costo_mxn=l.costo_mxn,
                      duracion_ms=l.duracion_ms, resultado=l.resultado, detalle=l.detalle)
        for l in bd.scalars(select(IaLlamada).order_by(IaLlamada.llamada_id.desc()).limit(limite)).all()
    ]


@router.post("/probar", response_model=ResultadoPrueba)
def probar(datos: Prueba, ctx: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> ResultadoPrueba:
    try:
        r = puerta.ejecutar(
            bd, TAREA_PRUEBA, usuario_id=ctx.usuario.usuario_id, proveedor=datos.proveedor, max_tokens=400,
            esfuerzo="low", mensaje=datos.mensaje,
            instrucciones="Eres el asistente de prueba de la plataforma SMN - Transformación digital. "
                          "Responde en español de México, breve y claro.",
        )
    except puerta.ErrorIA as e:
        raise HTTPException(status.HTTP_409_CONFLICT if isinstance(e, puerta.TopeAlcanzado) else status.HTTP_502_BAD_GATEWAY,
                            str(e)) from e
    return ResultadoPrueba(texto=r.texto, proveedor=r.proveedor, modelo=r.modelo, tokens_entrada=r.tokens_entrada,
                           tokens_salida=r.tokens_salida, costo_mxn=r.costo_mxn, duracion_ms=r.duracion_ms,
                           completa=r.completa)


def _costos_reales(bd: Session) -> CostosReales:
    cfg = configuracion()
    desde = puerta.ahora().date() - timedelta(days=13)
    estimados = costos.estimado_por_dia(bd, desde)
    reales = {f.fecha: f for f in bd.scalars(select(IaCostoReal).where(
        IaCostoReal.proveedor == "openai", IaCostoReal.fecha >= desde))}
    dias = []
    for i in range(14):
        d = puerta.ahora().date() - timedelta(days=i)
        r = reales.get(d)
        dias.append(DiaCosto(fecha=d, estimado_mxn=estimados.get(d, Decimal(0)),
                             real_mxn=r.costo_mxn if r else None, real_usd=r.costo_usd if r else None))
    motivo = None
    if cfg.ia_proveedor_externo != "openai":
        motivo = "Solo disponible con OpenAI como proveedor de la API externa."
    elif not cfg.openai_admin_key:
        motivo = "Falta la llave de administrador de OpenAI (Administración > Configuración)."
    return CostosReales(activo=costos.activo(), motivo=motivo, proyecto=cfg.openai_proyecto_id or None,
                        ultimo_intento=costos.ESTADO["ultimo_intento"], error=costos.ESTADO["error"], dias=dias)


@router.get("/costos-reales", response_model=CostosReales)
def costos_reales(_: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> CostosReales:
    return _costos_reales(bd)


@router.post("/costos-reales/sincronizar", response_model=CostosReales)
def sincronizar_costos(_: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> CostosReales:
    try:
        costos.sincronizar(bd)
    except costos.ErrorCostos as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return _costos_reales(bd)
