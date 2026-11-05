"""Rutas del Radar de tendencias (/api/compras/radar)."""
import json
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from core.bd import _fabrica, obtener_bd
from core.config import configuracion
from core.seguridad import Contexto, ip_de, requiere
from ia import puerta
from modulos.compras import radar
from modulos.compras.modelos import (RadarAccion, RadarArticulo, RadarDestinatario, RadarDocumento, RadarFuente,
                                     RadarHallazgo, RadarReporte, RadarSenal, RadarSenalArticulo, RadarTema)
from nucleo.archivos import _raiz
from nucleo.lectura import extraer_texto
from nucleo.bitacora import registrar
from nucleo.modelos import Archivo, Modulo, Usuario, ahora

router = APIRouter(prefix="/api/compras/radar", tags=["compras · radar"])
VER = requiere("compras.radar.ver")
DECIDIR = requiere("compras.radar.decidir")
ADMIN = requiere("compras.radar.administrar")

ACCIONES = {"iniciativa": "iniciativa", "vigilar": "vigilar", "descartar": "descartada"}


def _modulo_id(bd: Session) -> int | None:
    return bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "compras"))


# ---------------------------------------------------------------- esquemas

class ArticuloSalida(BaseModel):
    id: int
    titulo: str
    url: str
    sitio: str
    fuente: str | None
    origen: str
    publicado_en: date | None
    leido_en: datetime
    en_ventana: bool
    relevante: bool | None
    categoria: str | None
    nivel: str | None
    area: str | None
    pais: str | None
    por_que: str | None
    extracto: str | None

    @classmethod
    def de(cls, a: RadarArticulo) -> "ArticuloSalida":
        return cls(id=a.articulo_id, titulo=a.titulo, url=a.url, sitio=a.sitio, fuente=a.fuente.nombre if a.fuente else None,
                   origen=a.origen, publicado_en=a.publicado_en, leido_en=a.leido_en, en_ventana=a.en_ventana,
                   relevante=a.relevante, categoria=a.categoria, nivel=a.nivel, area=a.departamento, pais=a.pais,
                   por_que=a.por_que, extracto=a.extracto)


class AccionSalida(BaseModel):
    accion: str
    motivo: str | None
    usuario: str
    ocurrido_en: datetime


class HallazgoSalida(BaseModel):
    orden: int
    senal_id: int
    titulo: str
    por_que: str
    nivel: str
    tipo: str
    area: str | None
    paises: str | None
    estado_senal: str
    ultima_accion: AccionSalida | None
    articulos: list[ArticuloSalida]


class ReporteResumen(BaseModel):
    fecha: date
    estado: str
    origen: str
    intentos: int
    iniciado_en: datetime
    terminado_en: datetime | None
    fuentes_leidas: int
    fuentes_con_error: int
    busquedas: int
    articulos_nuevos: int
    articulos_relevantes: int
    hallazgos: int
    correos_enviados: int
    correos_fallidos: int
    error: str | None
    costo_mxn: float | None = None


class ReporteDetalle(ReporteResumen):
    resumen: str | None
    radar_ejecutivo: list[str]
    avisos: list[str]
    detalle_hallazgos: list[HallazgoSalida]


class EstadoRadar(BaseModel):
    activo: bool
    hora: int
    zona_horaria: str
    proxima_corrida: datetime
    frecuencia: str
    en_curso: bool
    ultimo: ReporteResumen | None
    ia_encendida: bool
    ia_proveedor: str
    ia_motivos: list[str]
    ollama: bool
    correo_configurado: bool
    destinatarios_activos: int
    fuentes_activas: int
    temas_activos: int
    busquedas_por_dia: int


def _ultima_accion(bd: Session, senal_id: int) -> AccionSalida | None:
    fila = bd.execute(select(RadarAccion, Usuario.nombre).join(Usuario, Usuario.usuario_id == RadarAccion.usuario_id)
                      .where(RadarAccion.senal_id == senal_id).order_by(RadarAccion.accion_id.desc())).first()
    if not fila:
        return None
    a, nombre = fila
    return AccionSalida(accion=a.accion, motivo=a.motivo, usuario=nombre, ocurrido_en=a.ocurrido_en)


def _costo(bd: Session, r: RadarReporte) -> float | None:
    from nucleo.modelos import IaLlamada, IaTarea

    fin = r.terminado_en or ahora()
    total = bd.scalar(select(func.coalesce(func.sum(IaLlamada.costo_mxn), 0))
                      .join(IaTarea, IaTarea.tarea_id == IaLlamada.tarea_id)
                      .where(IaTarea.codigo.like("compras.radar_%"), IaLlamada.ocurrido_en >= r.iniciado_en,
                             IaLlamada.ocurrido_en <= fin))
    return float(total or 0)


def _resumen(bd: Session, r: RadarReporte) -> ReporteResumen:
    return ReporteResumen(
        fecha=r.fecha, estado=r.estado, origen=r.origen, intentos=r.intentos, iniciado_en=r.iniciado_en,
        terminado_en=r.terminado_en, fuentes_leidas=r.fuentes_leidas, fuentes_con_error=r.fuentes_con_error,
        busquedas=r.busquedas, articulos_nuevos=r.articulos_nuevos, articulos_relevantes=r.articulos_relevantes,
        hallazgos=len(r.hallazgos), correos_enviados=r.correos_enviados, correos_fallidos=r.correos_fallidos,
        error=r.error, costo_mxn=_costo(bd, r))


def _detalle(bd: Session, r: RadarReporte) -> ReporteDetalle:
    hallazgos = []
    for h in r.hallazgos:
        articulos = bd.scalars(select(RadarArticulo).join(
            RadarSenalArticulo, RadarSenalArticulo.articulo_id == RadarArticulo.articulo_id)
            .where(RadarSenalArticulo.senal_id == h.senal_id, RadarArticulo.reporte_id == r.reporte_id)
            .order_by(RadarArticulo.publicado_en.desc())).all()
        hallazgos.append(HallazgoSalida(
            orden=h.orden, senal_id=h.senal_id, titulo=h.titulo, por_que=h.por_que, nivel=h.nivel, tipo=h.tipo,
            area=h.departamento, paises=h.paises, estado_senal=h.senal.estado,
            ultima_accion=_ultima_accion(bd, h.senal_id), articulos=[ArticuloSalida.de(a) for a in articulos]))
    base = _resumen(bd, r).model_dump()
    return ReporteDetalle(**base, resumen=r.resumen,
                          radar_ejecutivo=json.loads(r.radar_ejecutivo) if r.radar_ejecutivo else [],
                          avisos=json.loads(r.avisos) if r.avisos else [], detalle_hallazgos=hallazgos)


# ---------------------------------------------------------------- estado y corridas

@router.get("/estado", response_model=EstadoRadar)
def estado(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> EstadoRadar:
    cfg = configuracion()
    ultimo = bd.scalar(select(RadarReporte).order_by(RadarReporte.fecha.desc()))
    motivos = puerta.motivos_api_apagada(bd)
    return EstadoRadar(
        activo=cfg.radar_activo, hora=cfg.radar_hora, zona_horaria=cfg.radar_zona_horaria,
        proxima_corrida=radar.proxima_corrida(bd),
        frecuencia=radar.texto_frecuencia(),
        en_curso=bool(bd.scalar(select(func.count()).select_from(RadarReporte).where(RadarReporte.estado == "en_curso"))),
        ultimo=_resumen(bd, ultimo) if ultimo else None, ia_encendida=not motivos,
        ia_proveedor="OpenAI" if cfg.ia_proveedor_externo == "openai" else "Anthropic", ia_motivos=motivos,
        ollama=bool(cfg.ollama_modelo) and puerta.estado_ollama()["disponible"],
        correo_configurado=bool(cfg.smtp_servidor),
        destinatarios_activos=bd.scalar(select(func.count()).select_from(RadarDestinatario).where(RadarDestinatario.activo)),
        fuentes_activas=bd.scalar(select(func.count()).select_from(RadarFuente).where(RadarFuente.activa)),
        temas_activos=bd.scalar(select(func.count()).select_from(RadarTema).where(RadarTema.activo)),
        busquedas_por_dia=cfg.radar_busquedas_por_dia,
    )


def _correr_en_segundo_plano(reporte_id: int, enviar_correo: bool) -> None:
    with _fabrica()() as bd:
        reporte = bd.get(RadarReporte, reporte_id)
        if reporte:
            radar.correr(bd, reporte, enviar_correo=enviar_correo)


class Correr(BaseModel):
    enviar_correo: bool = True


@router.post("/correr", response_model=ReporteResumen, status_code=status.HTTP_202_ACCEPTED)
def correr_ahora(datos: Correr, request: Request, ctx: Contexto = Depends(ADMIN),
                 bd: Session = Depends(obtener_bd)) -> ReporteResumen:
    """Corre el radar de hoy ya (o lo vuelve a correr). Tarda varios minutos: corre aparte y la pantalla consulta el estado."""
    reporte = radar.tomar_reporte(bd, radar.hoy_local(), "manual", ctx.usuario.usuario_id, forzar=True)
    if not reporte:
        raise HTTPException(status.HTTP_409_CONFLICT, "El radar ya está corriendo. Espera a que termine.")
    registrar(bd, "radar_correr", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd), entidad="radar_reporte",
              entidad_id=reporte.reporte_id, detalle={"fecha": reporte.fecha, "enviar_correo": datos.enviar_correo},
              ip=ip_de(request))
    bd.commit()
    threading.Thread(target=_correr_en_segundo_plano, args=(reporte.reporte_id, datos.enviar_correo), daemon=True).start()
    return _resumen(bd, reporte)


@router.get("/reportes", response_model=list[ReporteResumen])
def reportes(limite: int = Query(60, ge=1, le=365), _: Contexto = Depends(VER),
             bd: Session = Depends(obtener_bd)) -> list[ReporteResumen]:
    filas = bd.scalars(select(RadarReporte).order_by(RadarReporte.fecha.desc()).limit(limite)).all()
    return [_resumen(bd, r) for r in filas]


@router.get("/reportes/ultimo", response_model=ReporteDetalle | None)
def ultimo(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> ReporteDetalle | None:
    r = bd.scalar(select(RadarReporte).where(RadarReporte.estado == "listo").order_by(RadarReporte.fecha.desc()))
    return _detalle(bd, r) if r else None


@router.get("/reportes/{fecha}", response_model=ReporteDetalle)
def reporte(fecha: date, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> ReporteDetalle:
    r = bd.scalar(select(RadarReporte).where(RadarReporte.fecha == fecha))
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay reporte de ese día.")
    return _detalle(bd, r)


@router.post("/reportes/{fecha}/enviarme")
def enviarme(fecha: date, ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> dict:
    r = bd.scalar(select(RadarReporte).where(RadarReporte.fecha == fecha, RadarReporte.estado == "listo"))
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay reporte listo de ese día.")
    if not configuracion().smtp_servidor:
        return {"enviado": False, "mensaje": "No hay correo de salida configurado (Administración > Configuración)."}
    enviados, _ = radar.enviar_reporte(bd, r, solo_a=ctx.usuario.correo)
    return {"enviado": bool(enviados),
            "mensaje": f"Enviado a {ctx.usuario.correo}." if enviados else "No se pudo enviar; revisa el correo de salida."}


@router.post("/reportes/{fecha}/enviar-destinatarios")
def enviar_destinatarios(fecha: date, request: Request, ctx: Contexto = Depends(ADMIN),
                         bd: Session = Depends(obtener_bd)) -> dict:
    """Manda el reporte a todos los destinatarios activos (además del envío automático de la corrida)."""
    r = bd.scalar(select(RadarReporte).where(RadarReporte.fecha == fecha, RadarReporte.estado == "listo"))
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay reporte listo de ese día.")
    if not configuracion().smtp_servidor:
        return {"enviado": False, "mensaje": "No hay correo de salida configurado (Administración > Configuración)."}
    activos = bd.scalar(select(func.count()).select_from(RadarDestinatario).where(RadarDestinatario.activo))
    if not activos:
        return {"enviado": False, "mensaje": "No hay destinatarios activos. Agrégalos en la pestaña Destinatarios."}
    enviados, fallidos = radar.enviar_reporte(bd, r)
    r.correos_enviados = (r.correos_enviados or 0) + enviados
    r.correos_fallidos = (r.correos_fallidos or 0) + fallidos
    registrar(bd, "radar_enviar", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd), entidad="radar_reporte",
              entidad_id=r.reporte_id, detalle={"fecha": r.fecha, "enviados": enviados, "fallidos": fallidos},
              ip=ip_de(request))
    bd.commit()
    mensaje = f"Enviado a {_cuantos(enviados, 'destinatario')}."
    if fallidos:
        mensaje += f" No llegó a {fallidos}; revisa el correo de salida y las direcciones."
    return {"enviado": bool(enviados), "mensaje": mensaje if enviados else "No se pudo enviar; revisa el correo de salida."}


def _cuantos(n: int, palabra: str) -> str:
    return f"{n} {palabra}" if n == 1 else f"{n} {palabra}s"


# ---------------------------------------------------------------- señales y decisiones

class SenalSalida(BaseModel):
    id: int
    titulo: str
    descripcion: str | None
    tipo: str
    nivel: str
    categoria: str | None
    area: str | None
    paises: str | None
    sitios_distintos: int
    primera_vez: date
    ultima_vez: date
    veces_reportada: int
    estado: str
    articulos: int
    ultima_accion: AccionSalida | None


class SenalDetalle(SenalSalida):
    lista_articulos: list[ArticuloSalida]
    acciones: list[AccionSalida]
    reportes: list[date]


def _senal(bd: Session, s: RadarSenal) -> SenalSalida:
    n = bd.scalar(select(func.count()).select_from(RadarSenalArticulo).where(RadarSenalArticulo.senal_id == s.senal_id))
    return SenalSalida(id=s.senal_id, titulo=s.titulo, descripcion=s.descripcion, tipo=s.tipo, nivel=s.nivel,
                       categoria=s.categoria, area=s.departamento, paises=s.paises, sitios_distintos=s.sitios_distintos,
                       primera_vez=s.primera_vez, ultima_vez=s.ultima_vez, veces_reportada=s.veces_reportada,
                       estado=s.estado, articulos=n or 0, ultima_accion=_ultima_accion(bd, s.senal_id))


@router.get("/senales", response_model=list[SenalSalida])
def senales(estado: str | None = None, tipo: str | None = None, q: str | None = Query(None, max_length=100),
            _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> list[SenalSalida]:
    consulta = select(RadarSenal)
    if estado:
        consulta = consulta.where(RadarSenal.estado == estado)
    if tipo:
        consulta = consulta.where(RadarSenal.tipo == tipo)
    if q:
        consulta = consulta.where(or_(RadarSenal.titulo.contains(q), RadarSenal.descripcion.contains(q)))
    filas = bd.scalars(consulta.order_by(RadarSenal.ultima_vez.desc(), RadarSenal.senal_id.desc()).limit(300)).all()
    return [_senal(bd, s) for s in filas]


@router.get("/senales/{senal_id}", response_model=SenalDetalle)
def senal(senal_id: int, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> SenalDetalle:
    s = bd.get(RadarSenal, senal_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa señal.")
    acciones = [AccionSalida(accion=a.accion, motivo=a.motivo, usuario=nombre, ocurrido_en=a.ocurrido_en)
                for a, nombre in bd.execute(select(RadarAccion, Usuario.nombre)
                                            .join(Usuario, Usuario.usuario_id == RadarAccion.usuario_id)
                                            .where(RadarAccion.senal_id == senal_id)
                                            .order_by(RadarAccion.accion_id.desc()))]
    fechas = list(bd.scalars(select(RadarReporte.fecha).join(RadarHallazgo, RadarHallazgo.reporte_id == RadarReporte.reporte_id)
                             .where(RadarHallazgo.senal_id == senal_id).order_by(RadarReporte.fecha.desc())))
    return SenalDetalle(**_senal(bd, s).model_dump(), lista_articulos=[ArticuloSalida.de(a) for a in s.articulos],
                        acciones=acciones, reportes=fechas)


class Decision(BaseModel):
    accion: str = Field(pattern="^(iniciativa|vigilar|descartar)$")
    motivo: str | None = Field(None, max_length=600)


@router.post("/senales/{senal_id}/accion", response_model=SenalSalida)
def decidir(senal_id: int, datos: Decision, request: Request, ctx: Contexto = Depends(DECIDIR),
            bd: Session = Depends(obtener_bd)) -> SenalSalida:
    s = bd.get(RadarSenal, senal_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa señal.")
    motivo = (datos.motivo or "").strip() or None
    if datos.accion == "descartar" and not motivo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe por qué se descarta; sirve para que el radar aprenda.")
    antes = s.estado
    s.estado = ACCIONES[datos.accion]
    bd.add(RadarAccion(senal_id=senal_id, accion=datos.accion, motivo=motivo, usuario_id=ctx.usuario.usuario_id))
    registrar(bd, "radar_decidir", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd), entidad="radar_senal",
              entidad_id=senal_id, detalle={"antes": antes, "accion": datos.accion, "motivo": motivo}, ip=ip_de(request))
    bd.commit()
    return _senal(bd, s)


# ---------------------------------------------------------------- histórico de notas

class PaginaArticulos(BaseModel):
    total: int
    articulos: list[ArticuloSalida]


@router.get("/articulos", response_model=PaginaArticulos)
def articulos(q: str | None = Query(None, max_length=100), desde: date | None = None, hasta: date | None = None,
              solo_relevantes: bool = False, origen: str | None = None, fuente_id: int | None = None,
              pagina: int = Query(0, ge=0), _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> PaginaArticulos:
    consulta = select(RadarArticulo)
    if q:
        consulta = consulta.where(or_(RadarArticulo.titulo.contains(q), RadarArticulo.extracto.contains(q),
                                      RadarArticulo.sitio.contains(q)))
    if desde:
        consulta = consulta.where(RadarArticulo.leido_en >= datetime.combine(desde, datetime.min.time()))
    if hasta:
        consulta = consulta.where(RadarArticulo.leido_en < datetime.combine(hasta, datetime.max.time()))
    if solo_relevantes:
        consulta = consulta.where(RadarArticulo.relevante == true())
    if origen:
        consulta = consulta.where(RadarArticulo.origen == origen)
    if fuente_id:
        consulta = consulta.where(RadarArticulo.fuente_id == fuente_id)
    total = bd.scalar(select(func.count()).select_from(consulta.subquery()))
    filas = bd.scalars(consulta.order_by(RadarArticulo.leido_en.desc(), RadarArticulo.articulo_id.desc())
                       .offset(pagina * 25).limit(25)).all()
    return PaginaArticulos(total=total or 0, articulos=[ArticuloSalida.de(a) for a in filas])


# ---------------------------------------------------------------- fuentes

class FuenteEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=160)
    liga: str = Field(min_length=8, max_length=400, pattern="^https?://")
    tipo: str = Field(pattern="^(oficial|especializada|negocios|estudios)$")
    pais: str = Field(min_length=2, max_length=20)
    idioma: str = Field(pattern="^(es|en)$")
    metodo: str = Field(pattern="^(rss|busqueda|manual)$")
    lectura: str | None = Field(None, max_length=600)
    activa: bool = True
    notas: str | None = Field(None, max_length=400)


class FuenteSalida(FuenteEntrada):
    id: int
    ultima_lectura_en: datetime | None
    ultimo_resultado: str | None
    ultimos_articulos: int | None
    articulos_total: int


def _fuente(bd: Session, f: RadarFuente) -> FuenteSalida:
    total = bd.scalar(select(func.count()).select_from(RadarArticulo).where(RadarArticulo.fuente_id == f.fuente_id))
    return FuenteSalida(id=f.fuente_id, nombre=f.nombre, liga=f.liga, tipo=f.tipo, pais=f.pais, idioma=f.idioma,
                        metodo=f.metodo, lectura=f.lectura, activa=f.activa, notas=f.notas,
                        ultima_lectura_en=f.ultima_lectura_en, ultimo_resultado=f.ultimo_resultado,
                        ultimos_articulos=f.ultimos_articulos, articulos_total=total or 0)


def _validar_fuente(datos: FuenteEntrada) -> FuenteEntrada:
    lectura = (datos.lectura or "").strip()
    if datos.metodo == "rss" and not lectura.startswith(("http://", "https://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Para RSS escribe la dirección completa del feed (https://...).")
    if datos.metodo == "busqueda":
        if not lectura:
            lectura = radar.sitio_de(datos.liga)
        lectura = ",".join(d.strip().removeprefix("https://").removeprefix("http://").removeprefix("www.").strip("/")
                           for d in lectura.split(",") if d.strip())
    return datos.model_copy(update={"lectura": lectura or None})


@router.get("/fuentes", response_model=list[FuenteSalida])
def fuentes(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> list[FuenteSalida]:
    return [_fuente(bd, f) for f in bd.scalars(select(RadarFuente).order_by(RadarFuente.tipo, RadarFuente.nombre)).all()]


@router.post("/fuentes", response_model=FuenteSalida, status_code=status.HTTP_201_CREATED)
def crear_fuente(datos: FuenteEntrada, request: Request, ctx: Contexto = Depends(ADMIN),
                 bd: Session = Depends(obtener_bd)) -> FuenteSalida:
    datos = _validar_fuente(datos)
    f = RadarFuente(**datos.model_dump())
    bd.add(f)
    bd.flush()
    registrar(bd, "radar_fuente_crear", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd),
              entidad="radar_fuente", entidad_id=f.fuente_id, detalle=datos.model_dump(), ip=ip_de(request))
    bd.commit()
    return _fuente(bd, f)


@router.put("/fuentes/{fuente_id}", response_model=FuenteSalida)
def editar_fuente(fuente_id: int, datos: FuenteEntrada, request: Request, ctx: Contexto = Depends(ADMIN),
                  bd: Session = Depends(obtener_bd)) -> FuenteSalida:
    f = bd.get(RadarFuente, fuente_id)
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa fuente.")
    datos = _validar_fuente(datos)
    antes = {k: getattr(f, k) for k in datos.model_dump()}
    for k, v in datos.model_dump().items():
        setattr(f, k, v)
    registrar(bd, "radar_fuente_editar", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd),
              entidad="radar_fuente", entidad_id=fuente_id, detalle={"antes": antes, "despues": datos.model_dump()},
              ip=ip_de(request))
    bd.commit()
    return _fuente(bd, f)


class PruebaFuente(BaseModel):
    ok: bool
    mensaje: str
    ejemplos: list[dict]


@router.post("/fuentes/probar", response_model=PruebaFuente)
def probar_fuente(datos: FuenteEntrada, _: Contexto = Depends(ADMIN)) -> PruebaFuente:
    """Lee un RSS sin guardar nada, para revisar la dirección antes de agregarla. Sin costo."""
    datos = _validar_fuente(datos)
    if datos.metodo != "rss":
        return PruebaFuente(ok=True, mensaje="Esta fuente se lee con la búsqueda de la IA en la corrida diaria; "
                            "no se prueba aquí porque cada búsqueda cuesta.", ejemplos=[])
    try:
        notas = radar.leer_rss(datos.lectura or "")
    except radar.ErrorRadar as e:
        return PruebaFuente(ok=False, mensaje=str(e), ejemplos=[])
    return PruebaFuente(ok=bool(notas), mensaje=f"El RSS trae {len(notas)} notas." if notas else "El RSS no trae notas.",
                        ejemplos=[{"titulo": n["titulo"], "url": n["url"],
                                   "fecha": n["publicado_en"].isoformat() if n["publicado_en"] else None} for n in notas[:5]])


# ---------------------------------------------------------------- temas

class TemaEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    descripcion: str = Field(min_length=5, max_length=600)
    activo: bool = True
    orden: int = Field(100, ge=0, le=10000)


class TemaSalida(TemaEntrada):
    id: int


def _tema(t: RadarTema) -> TemaSalida:
    return TemaSalida(id=t.tema_id, nombre=t.nombre, descripcion=t.descripcion, activo=t.activo, orden=t.orden)


@router.get("/temas", response_model=list[TemaSalida])
def temas(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> list[TemaSalida]:
    return [_tema(t) for t in bd.scalars(select(RadarTema).order_by(RadarTema.orden, RadarTema.tema_id)).all()]


@router.post("/temas", response_model=TemaSalida, status_code=status.HTTP_201_CREATED)
def crear_tema(datos: TemaEntrada, request: Request, ctx: Contexto = Depends(ADMIN),
               bd: Session = Depends(obtener_bd)) -> TemaSalida:
    t = RadarTema(**datos.model_dump())
    bd.add(t)
    bd.flush()
    registrar(bd, "radar_tema_crear", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd), entidad="radar_tema",
              entidad_id=t.tema_id, detalle=datos.model_dump(), ip=ip_de(request))
    bd.commit()
    return _tema(t)


@router.put("/temas/{tema_id}", response_model=TemaSalida)
def editar_tema(tema_id: int, datos: TemaEntrada, request: Request, ctx: Contexto = Depends(ADMIN),
                bd: Session = Depends(obtener_bd)) -> TemaSalida:
    t = bd.get(RadarTema, tema_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese tema.")
    for k, v in datos.model_dump().items():
        setattr(t, k, v)
    registrar(bd, "radar_tema_editar", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd), entidad="radar_tema",
              entidad_id=tema_id, detalle=datos.model_dump(), ip=ip_de(request))
    bd.commit()
    return _tema(t)


# ---------------------------------------------------------------- destinatarios

class DestinatarioEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=160)
    correo: EmailStr
    area: str | None = Field(None, max_length=120)
    activo: bool = True
    tipo_correo: Literal["decision", "informativo"] = "decision"


class DestinatarioSalida(DestinatarioEntrada):
    id: int


def _destinatario(d: RadarDestinatario) -> DestinatarioSalida:
    return DestinatarioSalida(id=d.destinatario_id, nombre=d.nombre, correo=d.correo, area=d.area, activo=d.activo,
                              tipo_correo=d.tipo_correo or "decision")


@router.get("/destinatarios", response_model=list[DestinatarioSalida])
def destinatarios(_: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> list[DestinatarioSalida]:
    return [_destinatario(d) for d in bd.scalars(select(RadarDestinatario).order_by(RadarDestinatario.nombre)).all()]


def _correo_libre(bd: Session, correo: str, propio: int | None = None) -> None:
    otro = bd.scalar(select(RadarDestinatario).where(func.lower(RadarDestinatario.correo) == correo.lower()))
    if otro and otro.destinatario_id != propio:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese correo ya está en la lista.")


@router.post("/destinatarios", response_model=DestinatarioSalida, status_code=status.HTTP_201_CREATED)
def crear_destinatario(datos: DestinatarioEntrada, request: Request, ctx: Contexto = Depends(ADMIN),
                       bd: Session = Depends(obtener_bd)) -> DestinatarioSalida:
    _correo_libre(bd, datos.correo)
    d = RadarDestinatario(nombre=datos.nombre.strip(), correo=datos.correo.lower(), area=datos.area, activo=datos.activo,
                          tipo_correo=datos.tipo_correo)
    bd.add(d)
    bd.flush()
    registrar(bd, "radar_destinatario_crear", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd),
              entidad="radar_destinatario", entidad_id=d.destinatario_id, detalle={"correo": d.correo}, ip=ip_de(request))
    bd.commit()
    return _destinatario(d)


@router.put("/destinatarios/{destinatario_id}", response_model=DestinatarioSalida)
def editar_destinatario(destinatario_id: int, datos: DestinatarioEntrada, request: Request,
                        ctx: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> DestinatarioSalida:
    d = bd.get(RadarDestinatario, destinatario_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese destinatario.")
    _correo_libre(bd, datos.correo, destinatario_id)
    d.nombre, d.correo, d.area, d.activo = datos.nombre.strip(), datos.correo.lower(), datos.area, datos.activo
    d.tipo_correo = datos.tipo_correo
    registrar(bd, "radar_destinatario_editar", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd),
              entidad="radar_destinatario", entidad_id=destinatario_id,
              detalle={"correo": d.correo, "activo": d.activo, "tipo_correo": d.tipo_correo}, ip=ip_de(request))
    bd.commit()
    return _destinatario(d)


@router.delete("/destinatarios/{destinatario_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_destinatario(destinatario_id: int, request: Request, ctx: Contexto = Depends(ADMIN),
                        bd: Session = Depends(obtener_bd)) -> None:
    d = bd.get(RadarDestinatario, destinatario_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese destinatario.")
    registrar(bd, "radar_destinatario_borrar", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd),
              entidad="radar_destinatario", entidad_id=destinatario_id, detalle={"correo": d.correo}, ip=ip_de(request))
    bd.delete(d)
    bd.commit()


# ---------------------------------------------------------------- base de conocimiento

class DocumentoEntrada(BaseModel):
    archivo_id: int
    titulo: str = Field(min_length=2, max_length=200)
    descripcion: str | None = Field(None, max_length=600)


class DocumentoSalida(BaseModel):
    id: int
    archivo_id: int
    titulo: str
    descripcion: str | None
    nombre_archivo: str
    caracteres: int
    activo: bool
    subido_por: str
    subido_en: datetime


def _documento(bd: Session, d: RadarDocumento) -> DocumentoSalida:
    a = bd.get(Archivo, d.archivo_id)
    u = bd.get(Usuario, d.subido_por)
    return DocumentoSalida(id=d.documento_id, archivo_id=d.archivo_id, titulo=d.titulo, descripcion=d.descripcion,
                           nombre_archivo=a.nombre_original if a else "", caracteres=d.caracteres, activo=d.activo,
                           subido_por=u.nombre if u else "", subido_en=d.subido_en)


@router.get("/documentos", response_model=list[DocumentoSalida])
def documentos(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> list[DocumentoSalida]:
    return [_documento(bd, d) for d in bd.scalars(select(RadarDocumento).order_by(RadarDocumento.subido_en.desc())).all()]


@router.post("/documentos", response_model=DocumentoSalida, status_code=status.HTTP_201_CREATED)
def agregar_documento(datos: DocumentoEntrada, request: Request, ctx: Contexto = Depends(ADMIN),
                      bd: Session = Depends(obtener_bd)) -> DocumentoSalida:
    a = bd.get(Archivo, datos.archivo_id)
    if not a or a.subido_por != ctx.usuario.usuario_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese archivo.")
    if a.tipo_contenido.startswith("image/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sube un PDF, Word, Excel o CSV; de una imagen no se puede leer el texto.")
    texto = " ".join(extraer_texto(_raiz() / a.ruta_almacenamiento, a.tipo_contenido).split())[:200_000]
    d = RadarDocumento(archivo_id=a.archivo_id, titulo=datos.titulo.strip(), descripcion=datos.descripcion,
                       texto=texto or None, caracteres=len(texto), subido_por=ctx.usuario.usuario_id)
    bd.add(d)
    bd.flush()
    registrar(bd, "radar_documento_agregar", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd),
              entidad="radar_documento", entidad_id=d.documento_id,
              detalle={"titulo": d.titulo, "caracteres": d.caracteres}, ip=ip_de(request))
    bd.commit()
    return _documento(bd, d)


class DocumentoCambio(BaseModel):
    activo: bool


@router.put("/documentos/{documento_id}", response_model=DocumentoSalida)
def cambiar_documento(documento_id: int, datos: DocumentoCambio, request: Request, ctx: Contexto = Depends(ADMIN),
                      bd: Session = Depends(obtener_bd)) -> DocumentoSalida:
    d = bd.get(RadarDocumento, documento_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese documento.")
    d.activo = datos.activo
    registrar(bd, "radar_documento_cambiar", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd),
              entidad="radar_documento", entidad_id=documento_id, detalle={"activo": d.activo}, ip=ip_de(request))
    bd.commit()
    return _documento(bd, d)
