"""Base de conocimiento fiscal (/api/contraloria/conocimiento): criterios con versión y aprobación, catálogos del SAT
con vigencia, documentos de soporte y «Probar con un periodo». Pedido de Diego, 2026-10-30."""
import json
from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, ip_de, requiere
from modulos.contraloria import conocimiento_fiscal as conocimiento
from modulos.contraloria import diot_criterios as crit
from modulos.contraloria.modelos_diot import (
    DiotEmpresa, DiotPeriodo, FiscalCatalogo, FiscalCriterio, FiscalCriterioCambio, FiscalDocumento,
)
from nucleo.bitacora import registrar
from nucleo.modelos import Modulo, Usuario

router = APIRouter(prefix="/api/contraloria/conocimiento", tags=["contraloría · conocimiento fiscal"])
VER, EDITAR, APROBAR = "contraloria.diot.ver", "contraloria.diot.operar", "contraloria.criterios.aprobar"
MB_DOCUMENTO = 20


def _bitacora(bd: Session, accion: str, ctx: Contexto, request: Request, entidad: str, entidad_id,
              detalle: dict | None = None) -> None:
    modulo_id = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "contraloria"))
    registrar(bd, accion, usuario_id=ctx.usuario.usuario_id, modulo_id=modulo_id, entidad=entidad,
              entidad_id=entidad_id, detalle=detalle, ip=ip_de(request))


def _error(e: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


# ---------------------------------------------------------------- esquemas

class CampoParametro(BaseModel):
    nombre: str
    etiqueta: str
    tipo: str  # lista / opcion / texto
    opciones: dict[str, str] | None


class Version(BaseModel):
    id: int
    version: int
    estado: str
    vigente_desde: date
    vigente_hasta: date | None
    parametros: dict | None
    condicion: dict | None
    accion: dict | None
    titulo: str
    descripcion: str
    creado_por: str | None
    creado_en: datetime
    aprobado_por: str | None
    aprobado_en: datetime | None
    nota_aprobacion: str | None


class Criterio(BaseModel):
    clave: str
    tipo: str
    categoria: str
    titulo: str
    descripcion: str
    contradiccion: str | None
    documento_id: int | None
    documento: str | None
    referencia: str | None
    evidencia: str | None
    prioridad: int
    empresa_id: int | None
    campos: list[CampoParametro]
    si_pendiente: str
    vigente: Version  # la que aplica hoy
    ultima: Version  # la más reciente (puede empezar después o estar por aprobar)
    versiones: int


class Cambio(BaseModel):
    version: int
    accion: str
    motivo: str | None
    detalle: dict | None
    usuario: str | None
    momento: datetime


class Catalogo(BaseModel):
    id: int
    catalogo: str
    clave: str
    descripcion: str
    valor: str | None
    vigente_desde: date
    vigente_hasta: date | None
    documento_id: int | None


class Documento(BaseModel):
    id: int
    titulo: str
    tipo: str
    version: str | None
    vigente_desde: date | None
    notas: str | None
    archivo: str | None
    tamano: int | None
    sha256: str | None
    activo: bool
    reemplaza_a: int | None
    cargado_por: str | None
    cargado_en: datetime


class Opciones(BaseModel):
    categorias: dict[str, str]
    fuentes: dict[str, str]
    campos_condicion: dict[str, str]
    operadores: dict[str, str]
    acciones: dict[str, str]
    que_lleva: dict[str, str]
    tipos_documento: dict[str, str]
    empresas: dict[int, str]


class Base_(BaseModel):
    criterios: list[Criterio]
    catalogos: list[Catalogo]
    documentos: list[Documento]
    opciones: Opciones
    resumen: dict[str, int]


class EdicionCriterio(BaseModel):
    parametros: dict | None = None
    titulo: str | None = Field(None, max_length=200)
    descripcion: str | None = Field(None, max_length=2000)
    condicion: dict | None = None
    accion: dict | None = None
    contradiccion: str | None = Field(None, max_length=2000)
    documento_id: int | None = None
    referencia: str | None = Field(None, max_length=500)
    evidencia: str | None = Field(None, max_length=1000)
    prioridad: int | None = Field(None, ge=1, le=999)
    vigente_desde: date
    motivo: str = Field(min_length=3, max_length=1000)
    borrador: bool = False


class NuevoPropio(BaseModel):
    titulo: str = Field(min_length=3, max_length=200)
    descripcion: str = Field("", max_length=2000)
    condicion: dict
    accion: dict
    documento_id: int | None = None
    referencia: str | None = Field(None, max_length=500)
    evidencia: str | None = Field(None, max_length=1000)
    prioridad: int = Field(100, ge=1, le=999)
    empresa_id: int | None = None
    vigente_desde: date
    motivo: str | None = Field(None, max_length=1000)
    borrador: bool = False


class Accion(BaseModel):
    accion: str  # aprobar / regresar / enviar / retirar
    nota: str | None = Field(None, max_length=1000)


class NuevoCatalogo(BaseModel):
    catalogo: str
    clave: str = Field(min_length=1, max_length=20)
    descripcion: str = Field("", max_length=500)
    valor: str | None = Field(None, max_length=50)
    vigente_desde: date
    documento_id: int | None = None


class Baja(BaseModel):
    vigente_hasta: date


class Prueba(BaseModel):
    periodo_id: int
    criterio_id: int | None = None


class CambioPrueba(BaseModel):
    rfc: str
    que: str
    antes: str | None
    despues: str | None


class ResultadoPrueba(BaseModel):
    periodo: str
    procesado: bool
    terceros_antes: int
    terceros_despues: int
    cambios: list[CambioPrueba]
    txt: bool
    bloqueado: bool
    incidencias_posibles: int
    criterios_pendientes: list[str]


# ---------------------------------------------------------------- ayudas

def _usuario(bd: Session, uid: int | None) -> str | None:
    u = bd.get(Usuario, uid) if uid else None
    return u.nombre if u else None


def _version(bd: Session, c: FiscalCriterio) -> Version:
    return Version(id=c.criterio_id, version=c.version, estado=c.estado, vigente_desde=c.vigente_desde,
                   vigente_hasta=c.vigente_hasta, parametros=json.loads(c.parametros) if c.parametros else None,
                   condicion=json.loads(c.condicion) if c.condicion else None,
                   accion=json.loads(c.accion) if c.accion else None, titulo=c.titulo, descripcion=c.descripcion,
                   creado_por=_usuario(bd, c.creado_por), creado_en=c.creado_en,
                   aprobado_por=_usuario(bd, c.aprobado_por), aprobado_en=c.aprobado_en,
                   nota_aprobacion=c.nota_aprobacion)


def _si_pendiente(c: FiscalCriterio) -> str:
    if c.tipo == "propio":
        return "Mientras no esté aprobado, no se aplica."
    return ("Mientras no esté aprobado, el proceso lo aplica igual, pero si cambia el resultado del mes sale una "
            "incidencia con posible impacto y el TXT no se entrega hasta revisarla.")


def _criterios(bd: Session) -> list[Criterio]:
    hoy = date.today()
    todas: dict[str, list[FiscalCriterio]] = {}
    for c in bd.scalars(select(FiscalCriterio).order_by(FiscalCriterio.clave, FiscalCriterio.version)):
        todas.setdefault(c.clave, []).append(c)
    docs = {d.documento_id: d.titulo for d in bd.scalars(select(FiscalDocumento))}
    orden = {d.clave: n for n, d in enumerate(crit.SISTEMA)}
    salida = []
    for clave, vs in sorted(todas.items(), key=lambda x: (orden.get(x[0], 999), x[0])):
        ultima = vs[-1]
        vigentes = [v for v in vs if conocimiento._vigente(v.vigente_desde, v.vigente_hasta, hoy)]
        vigente = vigentes[-1] if vigentes else ultima
        d = crit.POR_CLAVE.get(clave)
        salida.append(Criterio(
            clave=clave, tipo=ultima.tipo, categoria=ultima.categoria, titulo=ultima.titulo,
            descripcion=ultima.descripcion, contradiccion=ultima.contradiccion, documento_id=ultima.documento_id,
            documento=docs.get(ultima.documento_id), referencia=ultima.referencia, evidencia=ultima.evidencia,
            prioridad=ultima.prioridad, empresa_id=ultima.empresa_id,
            campos=[CampoParametro(nombre=n, etiqueta=e, tipo=t, opciones=o) for n, e, t, o in d.campos] if d else [],
            si_pendiente=_si_pendiente(ultima), vigente=_version(bd, vigente), ultima=_version(bd, ultima),
            versiones=len(vs)))
    return salida


def _catalogo(c: FiscalCatalogo) -> Catalogo:
    return Catalogo(id=c.catalogo_id, catalogo=c.catalogo, clave=c.clave, descripcion=c.descripcion, valor=c.valor,
                    vigente_desde=c.vigente_desde, vigente_hasta=c.vigente_hasta, documento_id=c.documento_id)


def _documento(bd: Session, d: FiscalDocumento) -> Documento:
    return Documento(id=d.documento_id, titulo=d.titulo, tipo=d.tipo, version=d.version, vigente_desde=d.vigente_desde,
                     notas=d.notas, archivo=d.nombre_archivo, tamano=d.tamano, sha256=d.sha256, activo=d.activo,
                     reemplaza_a=d.reemplaza_a, cargado_por=_usuario(bd, d.cargado_por), cargado_en=d.cargado_en)


def _base(bd: Session) -> Base_:
    criterios = _criterios(bd)
    empresas = {e.empresa_id: f"{e.codigo} · {e.nombre}" for e in bd.scalars(select(DiotEmpresa))}
    resumen = {"aprobados": sum(1 for c in criterios if c.ultima.estado == crit.APROBADO),
               "pendientes": sum(1 for c in criterios if c.ultima.estado == crit.PENDIENTE),
               "borradores": sum(1 for c in criterios if c.ultima.estado == crit.BORRADOR),
               "contradicciones": sum(1 for c in criterios if c.contradiccion and c.ultima.estado != crit.APROBADO)}
    return Base_(
        criterios=criterios,
        catalogos=[_catalogo(c) for c in bd.scalars(select(FiscalCatalogo).order_by(FiscalCatalogo.catalogo,
                                                                                      FiscalCatalogo.catalogo_id))],
        documentos=[_documento(bd, d) for d in bd.scalars(select(FiscalDocumento).order_by(
            FiscalDocumento.documento_id))],
        opciones=Opciones(categorias=crit.CATEGORIAS, fuentes=crit.FUENTES_PROPIAS,
                          campos_condicion=crit.CAMPOS_CONDICION, operadores=crit.OPERADORES, acciones=crit.ACCIONES,
                          que_lleva=crit.QUE_LLEVA, tipos_documento=conocimiento.TIPOS_DOCUMENTO, empresas=empresas),
        resumen=resumen)


def _criterio_id(bd: Session, criterio_id: int) -> FiscalCriterio:
    c = bd.get(FiscalCriterio, criterio_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese criterio no existe.")
    return c


# ---------------------------------------------------------------- rutas

@router.get("", response_model=Base_)
def base(_: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> Base_:
    return _base(bd)


@router.get("/criterios/{clave}/historial", response_model=list[Cambio])
def cambios(clave: str, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> list[Cambio]:
    q = select(FiscalCriterioCambio).where(FiscalCriterioCambio.clave == clave)
    return [Cambio(version=c.version, accion=c.accion, motivo=c.motivo, detalle=json.loads(c.detalle) if c.detalle
                   else None, usuario=_usuario(bd, c.usuario_id) or "Carga inicial", momento=c.momento)
            for c in bd.scalars(q.order_by(FiscalCriterioCambio.cambio_id.desc()))]


@router.post("/criterios/{clave}/versiones", response_model=Base_)
def editar(clave: str, datos: EdicionCriterio, request: Request, ctx: Contexto = Depends(requiere(EDITAR)),
           bd: Session = Depends(obtener_bd)) -> Base_:
    cambios_ = datos.model_dump(exclude_unset=True, exclude={"vigente_desde", "motivo", "borrador"})
    try:
        v = conocimiento.nueva_version(bd, clave, cambios_, ctx.usuario.usuario_id, datos.motivo, datos.vigente_desde,
                                       datos.borrador)
    except conocimiento.ErrorCriterio as e:
        raise _error(e) from e
    bd.flush()
    _bitacora(bd, "contraloria.criterio.editado", ctx, request, "fiscal_criterio", v.criterio_id,
              {"clave": clave, "version": v.version, "motivo": datos.motivo})
    bd.commit()
    return _base(bd)


@router.post("/criterios", response_model=Base_)
def nuevo(datos: NuevoPropio, request: Request, ctx: Contexto = Depends(requiere(EDITAR)),
          bd: Session = Depends(obtener_bd)) -> Base_:
    try:
        c = conocimiento.nuevo_propio(bd, datos.model_dump(), ctx.usuario.usuario_id, datos.vigente_desde,
                                      datos.borrador)
    except conocimiento.ErrorCriterio as e:
        raise _error(e) from e
    bd.flush()
    _bitacora(bd, "contraloria.criterio.creado", ctx, request, "fiscal_criterio", c.criterio_id, {"clave": c.clave})
    bd.commit()
    return _base(bd)


@router.post("/criterios/version/{criterio_id}/estado", response_model=Base_)
def estado(criterio_id: int, datos: Accion, request: Request, ctx: Contexto = Depends(requiere(EDITAR)),
           bd: Session = Depends(obtener_bd)) -> Base_:
    if datos.accion in ("aprobar", "regresar") and APROBAR not in ctx.permisos:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo quien aprueba criterios fiscales puede hacerlo.")
    c = _criterio_id(bd, criterio_id)
    try:
        conocimiento.cambiar_estado(bd, c, datos.accion, ctx.usuario.usuario_id, datos.nota)
    except conocimiento.ErrorCriterio as e:
        raise _error(e) from e
    _bitacora(bd, f"contraloria.criterio.{datos.accion}", ctx, request, "fiscal_criterio", c.criterio_id,
              {"clave": c.clave, "version": c.version, "nota": datos.nota})
    bd.commit()
    return _base(bd)


@router.post("/probar", response_model=ResultadoPrueba)
def probar(datos: Prueba, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> ResultadoPrueba:
    p = bd.get(DiotPeriodo, datos.periodo_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese periodo no existe.")
    c = _criterio_id(bd, datos.criterio_id) if datos.criterio_id else None
    try:
        return ResultadoPrueba(**conocimiento.probar(bd, p, c))
    except conocimiento.ErrorCriterio as e:
        raise _error(e) from e


@router.post("/catalogos", response_model=Base_)
def catalogo(datos: NuevoCatalogo, request: Request, ctx: Contexto = Depends(requiere(APROBAR)),
             bd: Session = Depends(obtener_bd)) -> Base_:
    try:
        c = conocimiento.catalogo_nuevo(bd, datos.catalogo, datos.clave, datos.descripcion, datos.valor,
                                        datos.vigente_desde, datos.documento_id, ctx.usuario.usuario_id)
    except conocimiento.ErrorCriterio as e:
        raise _error(e) from e
    bd.flush()
    _bitacora(bd, "contraloria.catalogo.cambiado", ctx, request, "fiscal_catalogo", c.catalogo_id,
              datos.model_dump(mode="json"))
    bd.commit()
    return _base(bd)


@router.post("/catalogos/{catalogo_id}/baja", response_model=Base_)
def baja(catalogo_id: int, datos: Baja, request: Request, ctx: Contexto = Depends(requiere(APROBAR)),
         bd: Session = Depends(obtener_bd)) -> Base_:
    c = bd.get(FiscalCatalogo, catalogo_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese renglón no existe.")
    if datos.vigente_hasta < c.vigente_desde:
        raise _error(conocimiento.ErrorCriterio("La fecha de baja es antes de que empezara a valer."))
    c.vigente_hasta = datos.vigente_hasta
    _bitacora(bd, "contraloria.catalogo.baja", ctx, request, "fiscal_catalogo", c.catalogo_id,
              {"hasta": datos.vigente_hasta.isoformat()})
    bd.commit()
    return _base(bd)


@router.post("/documentos", response_model=Base_)
async def documento(request: Request, titulo: str = Form(...), tipo: str = Form(...), version: str | None = Form(None),
                    vigente_desde: date | None = Form(None), notas: str | None = Form(None),
                    reemplaza: int | None = Form(None), archivo: UploadFile | None = File(None),
                    ctx: Contexto = Depends(requiere(EDITAR)), bd: Session = Depends(obtener_bd)) -> Base_:
    contenido = await archivo.read() if archivo else None
    if contenido and len(contenido) > MB_DOCUMENTO * 1024 * 1024:
        raise _error(conocimiento.ErrorCriterio(f"El archivo pasa de {MB_DOCUMENTO} MB."))
    anterior = bd.get(FiscalDocumento, reemplaza) if reemplaza else None
    try:
        d = conocimiento.documento_nuevo(bd, titulo, tipo, archivo.filename if archivo else None, contenido or None,
                                         version, vigente_desde, notas, ctx.usuario.usuario_id, anterior)
    except conocimiento.ErrorCriterio as e:
        raise _error(e) from e
    bd.flush()
    if anterior:  # los criterios que citaban la versión anterior pasan a citar la nueva
        for c in bd.scalars(select(FiscalCriterio).where(FiscalCriterio.documento_id == anterior.documento_id)):
            c.documento_id = d.documento_id
    _bitacora(bd, "contraloria.documento.cargado", ctx, request, "fiscal_documento", d.documento_id,
              {"titulo": d.titulo, "sha256": d.sha256, "reemplaza": reemplaza})
    bd.commit()
    return _base(bd)


@router.get("/documentos/{documento_id}/archivo")
def archivo(documento_id: int, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> Response:
    d = bd.get(FiscalDocumento, documento_id)
    if not d or not d.contenido:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese documento no tiene archivo.")
    return Response(d.contenido, media_type="application/octet-stream",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(d.nombre_archivo or
                                                                                            "documento")})
