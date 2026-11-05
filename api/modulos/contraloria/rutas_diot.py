"""DIOT (/api/contraloria/diot): periodos por empresa, carga de documentos, proceso, revisión y TXT para el SAT."""
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import false, select, true
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, ip_de, requiere
from modulos.contraloria import conocimiento_fiscal as conocimiento
from modulos.contraloria import diot
from modulos.contraloria import diot_layout as layout
from modulos.contraloria import diot_lectura as lectura
from modulos.contraloria import diot_motor as motor
from modulos.contraloria import diot_validacion as validacion
from modulos.contraloria.modelos_diot import (
    DiotAjuste, DiotCorrida, DiotCorridaLog, DiotCorridaPaso, DiotDocumento, DiotEmpresa, DiotIncidencia, DiotOperacion,
    DiotFirma, DiotPeriodo, DiotRevision, DiotTercero,
)
from nucleo.bitacora import registrar
from nucleo.modelos import Modulo, Usuario, ahora

router = APIRouter(prefix="/api/contraloria/diot", tags=["contraloría · DIOT"])
VER, OPERAR, APROBAR = "contraloria.diot.ver", "contraloria.diot.operar", "contraloria.criterios.aprobar"


def _bitacora(bd: Session, accion: str, ctx: Contexto, request: Request, entidad: str, entidad_id,
              detalle: dict | None = None) -> None:
    modulo_id = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "contraloria"))
    registrar(bd, accion, usuario_id=ctx.usuario.usuario_id, modulo_id=modulo_id, entidad=entidad,
              entidad_id=entidad_id, detalle=detalle, ip=ip_de(request))


# ---------------------------------------------------------------- esquemas

class Empresa(BaseModel):
    id: int
    codigo: str
    nombre: str
    rfc: str | None


class TipoDoc(BaseModel):
    codigo: str
    nombre: str
    obligatorio: bool
    para_que: str
    columnas: list[str]
    comprobar: bool = False  # no entra al cálculo (estado de cuenta)
    varios: bool = False  # se puede subir más de uno


class Documento(BaseModel):
    id: int
    tipo: str
    tipo_nombre: str
    archivo: str
    filas: int
    tamano: int
    cargado_por: str | None
    cargado_en: datetime


class PeriodoResumen(BaseModel):
    id: int
    empresa: Empresa
    anio: int
    mes: int
    nombre: str
    estado: str
    procesado_en: datetime | None
    terceros: int
    pendientes: int  # incidencias con posible impacto sin revisar


class CorridaResumen(BaseModel):
    id: int
    estado: str
    resultado: str | None
    iniciada_por: str | None
    iniciada_en: datetime
    terminada_en: datetime | None


class PasoCorrida(BaseModel):
    orden: int
    nombre: str
    que_hace: str
    estado: str
    resumen: str | None
    inicio_en: datetime | None
    fin_en: datetime | None


class LineaBitacora(BaseModel):
    id: int
    paso: int
    momento: datetime
    nivel: str
    mensaje: str


class Corrida(CorridaResumen):
    pasos: list[PasoCorrida]
    lineas: list[LineaBitacora]


class Periodo(PeriodoResumen):
    documentos: list[Documento]
    faltan: list[str]  # documentos obligatorios que no se han subido
    resumen: dict | None
    conteo_incidencias: dict[str, dict[str, int]]
    puede_txt: bool
    motivo_sin_txt: str | None
    referencia: str | None
    comparacion: dict | None
    corrida: CorridaResumen | None  # la última


class Tercero(BaseModel):
    id: int
    rfc: str
    nombre: str | None
    tipo_tercero: str
    tipo_operacion: str
    exactos: dict[str, Decimal]
    redondeados: dict[str, int]
    operaciones: int
    fuentes: list[str]
    estado: str
    ajustado: bool


class Operacion(BaseModel):
    id: int
    fuente: str
    fuente_nombre: str
    renglon: int
    referencia: str
    rfc: str | None
    nombre: str | None
    regla: str
    regla_texto: str
    incluida: bool
    tasa: str | None
    tipo_cambio: Decimal
    base16: Decimal
    iva16: Decimal
    base8: Decimal
    iva8: Decimal
    base0: Decimal
    exento: Decimal
    no_objeto: Decimal
    iva_retenido: Decimal
    nota: str | None
    monto: Decimal | None = None


class Incidencia(BaseModel):
    id: int
    impacto: str
    codigo: str
    mensaje: str
    fuente: str | None
    renglon: int | None
    rfc: str | None
    importe: Decimal | None
    estado: str
    nota_revision: str | None
    revisada_por: str | None
    revisada_en: datetime | None


class Ajuste(BaseModel):
    id: int
    rfc: str
    nombre: str | None
    campo: str | None
    importe: Decimal | None
    excluir: bool
    tipo_tercero: str | None
    tipo_operacion: str | None
    motivo: str
    creado_por: str | None
    creado_en: datetime


class Catalogos(BaseModel):
    empresas: list[Empresa]
    tipos: list[TipoDoc]
    reglas: dict[str, str]
    campos: list[str]
    tipos_tercero: dict[str, str]  # vigentes hoy en la Base de conocimiento fiscal
    tipos_operacion: dict[str, str]


# ---------------------------------------------------------------- ayudas

def _empresa(e: DiotEmpresa) -> Empresa:
    return Empresa(id=e.empresa_id, codigo=e.codigo, nombre=e.nombre, rfc=e.rfc)


def _periodo(bd: Session, periodo_id: int) -> DiotPeriodo:
    p = bd.get(DiotPeriodo, periodo_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese periodo no existe.")
    return p


def _abierto(p: DiotPeriodo) -> None:
    if p.estado == "cerrado":
        raise HTTPException(status.HTTP_409_CONFLICT, "El periodo está cerrado; reábrelo para cambiarlo.")


def _sin_corrida(bd: Session, p: DiotPeriodo) -> None:
    if diot.corrida_en_curso(bd, p.periodo_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Se está procesando el periodo; espera a que termine.")


def _corrida_resumen(bd: Session, co: DiotCorrida | None) -> CorridaResumen | None:
    if not co:
        return None
    return CorridaResumen(id=co.corrida_id, estado=co.estado, resultado=co.resultado,
                          iniciada_por=_nombre_usuario(bd, co.iniciada_por), iniciada_en=co.iniciada_en,
                          terminada_en=co.terminada_en)


def _nombre_usuario(bd: Session, uid: int | None) -> str | None:
    u = bd.get(Usuario, uid) if uid else None
    return u.nombre if u else None


def _resumen(bd: Session, p: DiotPeriodo) -> PeriodoResumen:
    terceros = len(list(bd.scalars(select(DiotTercero.tercero_id).where(DiotTercero.periodo_id == p.periodo_id))))
    return PeriodoResumen(id=p.periodo_id, empresa=_empresa(p.empresa), anio=p.anio, mes=p.mes,
                          nombre=f"{diot.MESES[p.mes - 1].capitalize()} {p.anio}", estado=p.estado,
                          procesado_en=p.procesado_en, terceros=terceros,
                          pendientes=diot.pendientes_que_bloquean(bd, p.periodo_id))


def _sin_txt(bd: Session, p: DiotPeriodo) -> str | None:
    if diot.corrida_en_curso(bd, p.periodo_id):
        return "Se está procesando el periodo."
    if p.estado == "abierto" or p.procesado_en is None:
        return "Procesa el periodo con sus documentos."
    if not p.txt:
        return "Hay terceros por revisar o falta un documento; revisa las incidencias."
    n = diot.pendientes_que_bloquean(bd, p.periodo_id)
    if n:
        return f"Hay {n} incidencia(s) con posible impacto sin revisar."
    if validacion.FIRMAS_OBLIGATORIAS:
        f = validacion.firmas(bd, p)
        if not (f["revision"]["firmada"] and f["fiscal"]["firmada"]):
            return "Falta la firma de quien revisó o el visto bueno de Fiscal."
    return None


def _detalle(bd: Session, p: DiotPeriodo) -> Periodo:
    docs = diot.vigentes(bd, p.periodo_id)
    tipos = {d.tipo for d in docs}
    conteo: dict[str, dict[str, int]] = {}
    for i in bd.scalars(select(DiotIncidencia).where(DiotIncidencia.periodo_id == p.periodo_id)):
        conteo.setdefault(i.impacto, {"pendiente": 0, "revisada": 0})[i.estado] += 1
    motivo = _sin_txt(bd, p)
    return Periodo(**_resumen(bd, p).model_dump(),
                   documentos=[Documento(id=d.documento_id, tipo=d.tipo, tipo_nombre=lectura.TIPOS[d.tipo].nombre,
                                         archivo=d.nombre_archivo, filas=d.filas, tamano=d.tamano,
                                         cargado_por=_nombre_usuario(bd, d.cargado_por), cargado_en=d.cargado_en)
                               for d in docs],
                   faltan=[t.nombre for t in lectura.TIPOS.values() if t.obligatorio and t.codigo not in tipos],
                   resumen=json.loads(p.resumen) if p.resumen else None, conteo_incidencias=conteo,
                   puede_txt=motivo is None, motivo_sin_txt=motivo, referencia=p.referencia_nombre,
                   comparacion=json.loads(p.comparacion) if p.comparacion else None,
                   corrida=_corrida_resumen(bd, bd.scalars(select(DiotCorrida).where(
                       DiotCorrida.periodo_id == p.periodo_id).order_by(DiotCorrida.corrida_id.desc())).first()))


def _guardar_referencia(bd: Session, p: DiotPeriodo, nombre: str, contenido: bytes) -> None:
    """El TXT que Fiscal ya presentó: solo para comparar campo por campo; nunca se copia al resultado."""
    texto = contenido.decode("latin-1")
    p.referencia_nombre, p.referencia_txt = nombre[:200], texto
    p.comparacion = json.dumps(layout.comparar(p.txt, texto, conocimiento.config_periodo(bd, p)),
                               ensure_ascii=False) if p.txt else None


# ---------------------------------------------------------------- catálogos y periodos

@router.get("/catalogos", response_model=Catalogos)
def catalogos(_: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> Catalogos:
    cfg = conocimiento.config(bd, date.today())
    empresas = bd.scalars(select(DiotEmpresa).where(DiotEmpresa.activa == true()).order_by(DiotEmpresa.codigo))
    return Catalogos(empresas=[_empresa(e) for e in empresas],
                     tipos=[TipoDoc(codigo=t.codigo, nombre=t.nombre, obligatorio=t.obligatorio, para_que=t.para_que,
                                    columnas=list(t.columnas), comprobar=t.comprobar, varios=t.varios)
                           for t in lectura.TIPOS.values()],
                     reglas=motor.REGLAS, campos=list(motor.CAMPOS), tipos_tercero=cfg.tipos_tercero,
                     tipos_operacion=cfg.tipos_operacion)


@router.get("/periodos", response_model=list[PeriodoResumen])
def periodos(empresa_id: int | None = None, _: Contexto = Depends(requiere(VER)),
             bd: Session = Depends(obtener_bd)) -> list[PeriodoResumen]:
    q = select(DiotPeriodo).order_by(DiotPeriodo.anio.desc(), DiotPeriodo.mes.desc())
    if empresa_id:
        q = q.where(DiotPeriodo.empresa_id == empresa_id)
    return [_resumen(bd, p) for p in bd.scalars(q.limit(60))]


class NuevoPeriodo(BaseModel):
    empresa_id: int
    anio: int = Field(ge=2020, le=2100)
    mes: int = Field(ge=1, le=12)


@router.post("/periodos", response_model=Periodo)
def nuevo_periodo(datos: NuevoPeriodo, request: Request, ctx: Contexto = Depends(requiere(OPERAR)),
                  bd: Session = Depends(obtener_bd)) -> Periodo:
    if not bd.get(DiotEmpresa, datos.empresa_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa empresa no existe.")
    p = bd.scalar(select(DiotPeriodo).where(DiotPeriodo.empresa_id == datos.empresa_id, DiotPeriodo.anio == datos.anio,
                                            DiotPeriodo.mes == datos.mes))
    if not p:
        p = DiotPeriodo(empresa_id=datos.empresa_id, anio=datos.anio, mes=datos.mes, estado="abierto",
                        creado_por=ctx.usuario.usuario_id, creado_en=ahora())
        bd.add(p)
        bd.flush()
        _bitacora(bd, "diot_periodo", ctx, request, "diot_periodo", p.periodo_id,
                  {"empresa": datos.empresa_id, "anio": datos.anio, "mes": datos.mes})
        bd.commit()
    return _detalle(bd, p)


@router.get("/periodos/{periodo_id}", response_model=Periodo)
def periodo(periodo_id: int, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> Periodo:
    return _detalle(bd, _periodo(bd, periodo_id))


class CambioEstado(BaseModel):
    estado: Literal["procesado", "cerrado"]


@router.patch("/periodos/{periodo_id}", response_model=Periodo)
def cerrar(periodo_id: int, datos: CambioEstado, request: Request, ctx: Contexto = Depends(requiere(OPERAR)),
           bd: Session = Depends(obtener_bd)) -> Periodo:
    """Cerrar el periodo (ya se presentó) o reabrirlo a «procesado»."""
    p = _periodo(bd, periodo_id)
    if datos.estado == "cerrado" and _sin_txt(bd, p):
        raise HTTPException(status.HTTP_409_CONFLICT, f"No se puede cerrar: {_sin_txt(bd, p)}")
    if datos.estado == "procesado" and p.estado != "cerrado":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se reabre un periodo cerrado.")
    p.estado = datos.estado
    _bitacora(bd, "diot_estado", ctx, request, "diot_periodo", p.periodo_id, {"estado": datos.estado})
    bd.commit()
    return _detalle(bd, p)


class DatosEmpresa(BaseModel):
    rfc: str = Field(pattern=r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")


class NuevaEmpresa(BaseModel):
    codigo: str = Field(min_length=2, max_length=20, pattern=r"^[A-Z0-9_-]+$")
    nombre: str = Field(min_length=3, max_length=200)
    rfc: str | None = Field(default=None, pattern=r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")


@router.post("/empresas", response_model=Empresa, status_code=status.HTTP_201_CREATED)
def alta_empresa(datos: NuevaEmpresa, request: Request, ctx: Contexto = Depends(requiere(APROBAR)),
                 bd: Session = Depends(obtener_bd)) -> Empresa:
    """Da de alta otra empresa para la DIOT. El RFC puede quedar pendiente: sin él la empresa no procesa."""
    codigo, nombre = datos.codigo.strip().upper(), " ".join(datos.nombre.split())
    if bd.scalar(select(DiotEmpresa).where(DiotEmpresa.codigo == codigo)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe una empresa con la clave {codigo}.")
    if datos.rfc and bd.scalar(select(DiotEmpresa).where(DiotEmpresa.rfc == datos.rfc)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una empresa con ese RFC.")
    e = DiotEmpresa(codigo=codigo, nombre=nombre, rfc=datos.rfc, activa=True)
    bd.add(e)
    bd.flush()
    _bitacora(bd, "diot_empresa_alta", ctx, request, "diot_empresa", e.empresa_id,
              {"codigo": codigo, "nombre": nombre, "con_rfc": bool(datos.rfc)})
    bd.commit()
    return _empresa(e)


@router.patch("/empresas/{empresa_id}", response_model=Empresa)
def cambiar_empresa(empresa_id: int, datos: DatosEmpresa, request: Request, ctx: Contexto = Depends(requiere(APROBAR)),
                    bd: Session = Depends(obtener_bd)) -> Empresa:
    """El RFC de la empresa (lo confirma Fiscal). Se usa para no declarar los pagos de la empresa a sí misma."""
    e = bd.get(DiotEmpresa, empresa_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa empresa no existe.")
    antes, e.rfc = e.rfc, datos.rfc
    _bitacora(bd, "diot_empresa_rfc", ctx, request, "diot_empresa", e.empresa_id, {"antes": antes, "ahora": e.rfc})
    bd.commit()
    return _empresa(e)


@router.delete("/periodos/{periodo_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_periodo(periodo_id: int, request: Request, ctx: Contexto = Depends(requiere(OPERAR)),
                   bd: Session = Depends(obtener_bd)) -> Response:
    """Borra un periodo abierto por error o que se quiere empezar de cero: documentos, resultado, decisiones,
    ajustes, firmas y corridas. Un periodo cerrado (ya presentado) no se borra; primero se reabre."""
    p = _periodo(bd, periodo_id)
    _abierto(p)
    _sin_corrida(bd, p)
    pid = p.periodo_id
    corridas = select(DiotCorrida.corrida_id).where(DiotCorrida.periodo_id == pid)
    for modelo in (DiotCorridaLog, DiotCorridaPaso):
        bd.query(modelo).filter(modelo.corrida_id.in_(corridas)).delete(synchronize_session=False)
    for modelo in (DiotCorrida, DiotFirma, DiotRevision, DiotAjuste, DiotIncidencia, DiotTercero, DiotOperacion,
                   DiotDocumento):
        bd.query(modelo).filter(modelo.periodo_id == pid).delete(synchronize_session=False)
    _bitacora(bd, "diot_periodo_borrar", ctx, request, "diot_periodo", pid,
              {"empresa_id": p.empresa_id, "anio": p.anio, "mes": p.mes})
    bd.delete(p)
    bd.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- documentos

class ResultadoArchivo(BaseModel):
    archivo: str
    resultado: Literal["documento", "referencia", "no_se_usa", "error"]
    tipo: str | None = None
    tipo_nombre: str | None = None
    mensaje: str


class Carga(BaseModel):
    periodo: Periodo
    archivos: list[ResultadoArchivo]


@router.post("/periodos/{periodo_id}/documentos", response_model=Carga)
async def subir(periodo_id: int, request: Request, archivo: UploadFile = File(...), tipo: str | None = Form(None),
                ctx: Contexto = Depends(requiere(OPERAR)), bd: Session = Depends(obtener_bd)) -> Carga:
    """Acepta los archivos como los entrega Fiscal: cada reporte, el papel de trabajo completo (se toman solo sus hojas
    crudas), el TXT presentado (solo para comparar) o un .zip con todo. Con `tipo`, el archivo se toma como ese tipo."""
    p = _periodo(bd, periodo_id)
    _abierto(p)
    _sin_corrida(bd, p)
    nombre = (archivo.filename or "documento")[:260]
    contenido = await archivo.read(diot.MB_DOCUMENTO * 1024 * 1024 + 1)
    if len(contenido) > diot.MB_DOCUMENTO * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El archivo pasa de {diot.MB_DOCUMENTO} MB.")
    if not contenido:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo está vacío.")
    partes = lectura.separar(nombre, contenido)
    if tipo:  # elegido a mano: la hoja de ese tipo si viene en el papel de trabajo; si no, el archivo tal cual
        del_tipo = [a for a in partes if a.clase == "documento" and a.tipo == tipo]
        if not del_tipo and any("papel de trabajo" in a.mensaje for a in partes) and tipo in lectura.TIPOS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"{nombre} es el papel de trabajo de Fiscal y no trae «{lectura.TIPOS[tipo].nombre}» "
                                "como sale de Intelisis. Sube ese reporte aparte, tal como lo descargas.")
        conocido = next((a.mensaje for a in partes if a.clase == "no_se_usa" and a.mensaje), None)
        if not del_tipo and conocido and tipo in lectura.TIPOS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"{nombre} no es «{lectura.TIPOS[tipo].nombre}». Es {conocido[0].lower()}{conocido[1:]}")
        partes = del_tipo or [lectura.Archivo(nombre, "documento", contenido, tipo)]
    resultados = []
    for a in partes:
        r = ResultadoArchivo(archivo=a.nombre, resultado=a.clase, tipo=a.tipo, mensaje=a.mensaje)
        if a.clase == "documento":
            try:
                doc, _ = diot.guardar_documento(bd, p, a.nombre, a.contenido, ctx.usuario.usuario_id, a.tipo)
            except lectura.ErrorLectura as e:
                r.resultado, r.tipo, r.mensaje = "error", None, str(e)
            else:
                bd.flush()
                r.tipo, r.tipo_nombre = doc.tipo, lectura.TIPOS[doc.tipo].nombre
                r.mensaje = f"{r.tipo_nombre} · {doc.filas:,} renglones" + (f" ({a.mensaje})" if a.mensaje else "")
                _bitacora(bd, "diot_documento", ctx, request, "diot_documento", doc.documento_id,
                          {"periodo": p.periodo_id, "tipo": doc.tipo, "archivo": a.nombre, "subido_como": nombre,
                           "filas": doc.filas, "sha256": doc.sha256})
        elif a.clase == "referencia":
            _guardar_referencia(bd, p, a.nombre, a.contenido)
            _bitacora(bd, "diot_referencia", ctx, request, "diot_periodo", p.periodo_id, {"archivo": a.nombre})
        resultados.append(r)
    if not any(r.resultado in ("documento", "referencia") for r in resultados):
        bd.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            " ".join(f"{r.archivo}: {r.mensaje}" for r in resultados) or "No se pudo leer el archivo.")
    bd.commit()
    return Carga(periodo=_detalle(bd, p), archivos=resultados)


@router.delete("/periodos/{periodo_id}/documentos/{documento_id}", response_model=Periodo)
def quitar_documento(periodo_id: int, documento_id: int, request: Request, ctx: Contexto = Depends(requiere(OPERAR)),
                     bd: Session = Depends(obtener_bd)) -> Periodo:
    p = _periodo(bd, periodo_id)
    _abierto(p)
    _sin_corrida(bd, p)
    d = bd.get(DiotDocumento, documento_id)
    if not d or d.periodo_id != periodo_id or not d.vigente:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese documento no existe.")
    d.vigente = False  # se queda en la historia
    p.estado = "abierto"
    _bitacora(bd, "diot_documento_quitar", ctx, request, "diot_documento", d.documento_id, {"tipo": d.tipo})
    bd.commit()
    return _detalle(bd, p)


# ---------------------------------------------------------------- proceso y resultado

@router.post("/periodos/{periodo_id}/procesar", response_model=Periodo)
def procesar(periodo_id: int, request: Request, ctx: Contexto = Depends(requiere(OPERAR)),
             bd: Session = Depends(obtener_bd)) -> Periodo:
    """Arranca una corrida con los 8 pasos del proceso de Fiscal; avanza en segundo plano y se sigue en
    /corridas/{id}."""
    p = _periodo(bd, periodo_id)
    _abierto(p)
    _sin_corrida(bd, p)
    if not p.empresa.rfc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Falta el RFC de {p.empresa.nombre}: sin él no se pueden separar "
                                                      "sus propios pagos. Captúralo en la pantalla de la empresa (Empresas, luego la empresa).")
    co = diot.iniciar_corrida(bd, p, ctx.usuario.usuario_id)
    _bitacora(bd, "diot_procesar", ctx, request, "diot_corrida", co.corrida_id, {"periodo": p.periodo_id})
    bd.commit()
    diot.en_hilo(co.corrida_id)
    return _detalle(bd, p)


@router.get("/periodos/{periodo_id}/corridas", response_model=list[CorridaResumen])
def corridas(periodo_id: int, _: Contexto = Depends(requiere(VER)),
             bd: Session = Depends(obtener_bd)) -> list[CorridaResumen]:
    _periodo(bd, periodo_id)
    q = select(DiotCorrida).where(DiotCorrida.periodo_id == periodo_id).order_by(DiotCorrida.corrida_id.desc())
    return [_corrida_resumen(bd, co) for co in bd.scalars(q.limit(50))]


@router.get("/corridas/{corrida_id}", response_model=Corrida)
def corrida(corrida_id: int, desde: int = 0, _: Contexto = Depends(requiere(VER)),
            bd: Session = Depends(obtener_bd)) -> Corrida:
    """Los pasos y la bitácora de una corrida; con `desde` solo los renglones nuevos (para seguirla en vivo)."""
    co = bd.get(DiotCorrida, corrida_id)
    if not co:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa corrida no existe.")
    que_hace = {n: q for n, _, q in motor.PASOS}
    pasos = [PasoCorrida(orden=x.orden, nombre=x.nombre, que_hace=que_hace.get(x.orden, ""), estado=x.estado,
                         resumen=x.resumen, inicio_en=x.inicio_en, fin_en=x.fin_en)
             for x in bd.scalars(select(DiotCorridaPaso).where(DiotCorridaPaso.corrida_id == corrida_id)
                                 .order_by(DiotCorridaPaso.orden))]
    lineas = [LineaBitacora(id=x.log_id, paso=x.orden_paso, momento=x.momento, nivel=x.nivel, mensaje=x.mensaje)
              for x in bd.scalars(select(DiotCorridaLog).where(DiotCorridaLog.corrida_id == corrida_id,
                                                               DiotCorridaLog.log_id > desde)
                                  .order_by(DiotCorridaLog.log_id).limit(2000))]
    return Corrida(**_corrida_resumen(bd, co).model_dump(), pasos=pasos, lineas=lineas)


@router.get("/periodos/{periodo_id}/terceros", response_model=list[Tercero])
def terceros(periodo_id: int, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> list[Tercero]:
    _periodo(bd, periodo_id)
    q = select(DiotTercero).where(DiotTercero.periodo_id == periodo_id).order_by(DiotTercero.tipo_tercero,
                                                                                  DiotTercero.rfc)
    return [Tercero(id=t.tercero_id, rfc=t.rfc, nombre=t.nombre, tipo_tercero=t.tipo_tercero,
                    tipo_operacion=t.tipo_operacion, exactos={k: Decimal(v) for k, v in json.loads(t.exactos).items()},
                    redondeados=json.loads(t.redondeados), operaciones=t.operaciones,
                    fuentes=t.fuentes.split(",") if t.fuentes else [], estado=t.estado, ajustado=t.ajustado)
            for t in bd.scalars(q)]


@router.get("/periodos/{periodo_id}/operaciones", response_model=list[Operacion])
def operaciones(periodo_id: int, rfc: str | None = None, fuente: str | None = None, incluida: bool | None = None,
                _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> list[Operacion]:
    cfg = conocimiento.config_periodo(bd, _periodo(bd, periodo_id))
    q = select(DiotOperacion).where(DiotOperacion.periodo_id == periodo_id)
    if rfc:
        q = q.where(DiotOperacion.rfc == rfc)
    if fuente:
        q = q.where(DiotOperacion.fuente == fuente)
    if incluida is not None:
        q = q.where(DiotOperacion.incluida == (true() if incluida else false()))
    return [Operacion(id=o.operacion_id, fuente=o.fuente,
                      fuente_nombre=lectura.TIPOS[o.fuente].nombre if o.fuente in lectura.TIPOS else o.fuente,
                      renglon=o.renglon, referencia=o.referencia, rfc=o.rfc, nombre=o.nombre, regla=o.regla,
                      regla_texto=motor.texto_regla(cfg, o.regla), incluida=o.incluida, tasa=o.tasa,
                      tipo_cambio=o.tipo_cambio, base16=o.base16, iva16=o.iva16, base8=o.base8, iva8=o.iva8,
                      base0=o.base0, exento=o.exento, no_objeto=o.no_objeto, iva_retenido=o.iva_retenido,
                      nota=o.nota, monto=o.monto)
            for o in bd.scalars(q.order_by(DiotOperacion.fuente, DiotOperacion.renglon).limit(5000))]


def _incidencia(bd: Session, i: DiotIncidencia) -> Incidencia:
    return Incidencia(id=i.incidencia_id, impacto=i.impacto, codigo=i.codigo, mensaje=i.mensaje, fuente=i.fuente,
                      renglon=i.renglon, rfc=i.rfc, importe=i.importe, estado=i.estado, nota_revision=i.nota_revision,
                      revisada_por=_nombre_usuario(bd, i.revisada_por), revisada_en=i.revisada_en)


@router.get("/periodos/{periodo_id}/incidencias", response_model=list[Incidencia])
def incidencias(periodo_id: int, _: Contexto = Depends(requiere(VER)),
                bd: Session = Depends(obtener_bd)) -> list[Incidencia]:
    _periodo(bd, periodo_id)
    orden = {motor.POSIBLE: 0, motor.CONTROLADO: 1, motor.SIN_IMPACTO: 2}
    filas = list(bd.scalars(select(DiotIncidencia).where(DiotIncidencia.periodo_id == periodo_id)))
    filas.sort(key=lambda i: (i.estado != "pendiente", orden.get(i.impacto, 3), i.incidencia_id))
    return [_incidencia(bd, i) for i in filas]


class Revision(BaseModel):
    estado: Literal["pendiente", "revisada"]
    nota: str | None = Field(None, max_length=1000)


@router.patch("/incidencias/{incidencia_id}", response_model=Incidencia)
def revisar(incidencia_id: int, datos: Revision, request: Request, ctx: Contexto = Depends(requiere(OPERAR)),
            bd: Session = Depends(obtener_bd)) -> Incidencia:
    i = bd.get(DiotIncidencia, incidencia_id)
    if not i:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa incidencia no existe.")
    _abierto(_periodo(bd, i.periodo_id))
    nota = " ".join((datos.nota or "").split()) or None
    if datos.estado == "revisada" and i.impacto == motor.POSIBLE and not nota:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe qué revisaste: esta incidencia puede cambiar importes.")
    i.estado, i.nota_revision = datos.estado, nota
    # Pendiente con nota = «se preguntó a Fiscal»: se guarda quién y cuándo para mostrar desde cuándo espera.
    i.revisada_por, i.revisada_en = ((ctx.usuario.usuario_id, ahora()) if datos.estado == "revisada" or nota
                                     else (None, None))
    _bitacora(bd, "diot_incidencia", ctx, request, "diot_incidencia", i.incidencia_id,
              {"estado": datos.estado, "nota": nota})
    bd.commit()
    return _incidencia(bd, i)


class RevisionLote(Revision):
    ids: list[int] = Field(min_length=1, max_length=5000)


@router.post("/periodos/{periodo_id}/incidencias/lote")
def revisar_lote(periodo_id: int, datos: RevisionLote, request: Request, ctx: Contexto = Depends(requiere(OPERAR)),
                 bd: Session = Depends(obtener_bd)) -> dict:
    """La misma decisión para varias incidencias del periodo (por ejemplo, todas las de un mismo tipo). Cada una queda
    en la bitácora con la misma nota."""
    p = _periodo(bd, periodo_id)
    _abierto(p)
    nota = " ".join((datos.nota or "").split()) or None
    filas = list(bd.scalars(select(DiotIncidencia).where(DiotIncidencia.periodo_id == p.periodo_id,
                                                         DiotIncidencia.incidencia_id.in_(datos.ids))))
    if len(filas) != len(set(datos.ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alguna incidencia no es de este periodo.")
    if datos.estado == "revisada" and not nota and any(i.impacto == motor.POSIBLE for i in filas):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe qué revisaste: estas incidencias pueden cambiar "
                                                         "importes.")
    quien = (ctx.usuario.usuario_id, ahora()) if datos.estado == "revisada" or nota else (None, None)
    for i in filas:
        i.estado, i.nota_revision = datos.estado, nota
        i.revisada_por, i.revisada_en = quien
    _bitacora(bd, "diot_incidencia_lote", ctx, request, "diot_periodo", p.periodo_id,
              {"estado": datos.estado, "nota": nota, "incidencias": len(filas)})
    bd.commit()
    return {"actualizadas": len(filas)}


# ---------------------------------------------------------------- ajustes de Fiscal

def _ajuste(bd: Session, a: DiotAjuste) -> Ajuste:
    return Ajuste(id=a.ajuste_id, rfc=a.rfc, nombre=a.nombre, campo=a.campo, importe=a.importe, excluir=a.excluir,
                  tipo_tercero=a.tipo_tercero, tipo_operacion=a.tipo_operacion, motivo=a.motivo,
                  creado_por=_nombre_usuario(bd, a.creado_por), creado_en=a.creado_en)


@router.get("/periodos/{periodo_id}/ajustes", response_model=list[Ajuste])
def ajustes(periodo_id: int, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> list[Ajuste]:
    _periodo(bd, periodo_id)
    q = select(DiotAjuste).where(DiotAjuste.periodo_id == periodo_id, DiotAjuste.activo == true())
    return [_ajuste(bd, a) for a in bd.scalars(q.order_by(DiotAjuste.ajuste_id))]


class NuevoAjuste(BaseModel):
    rfc: str = Field(min_length=3, max_length=20)
    nombre: str | None = Field(None, max_length=300)
    campo: Literal["base16", "iva16", "base8", "iva8", "base0", "exento", "no_objeto", "iva_retenido"] | None = None
    importe: Decimal | None = None
    excluir: bool = False
    tipo_tercero: Literal["04", "05", "15"] | None = None
    tipo_operacion: Literal["02", "03", "06", "07", "08", "85"] | None = None
    motivo: str = Field(min_length=5, max_length=1000)


@router.post("/periodos/{periodo_id}/ajustes", response_model=list[Ajuste])
def nuevo_ajuste(periodo_id: int, datos: NuevoAjuste, request: Request, ctx: Contexto = Depends(requiere(OPERAR)),
                 bd: Session = Depends(obtener_bd)) -> list[Ajuste]:
    p = _periodo(bd, periodo_id)
    _abierto(p)
    _sin_corrida(bd, p)
    if not datos.excluir and not (datos.campo and datos.importe) and not datos.tipo_operacion and not datos.tipo_tercero:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Di qué cambia: un importe en un campo, el tipo de tercero u "
                                                         "operación, o quitar al tercero.")
    a = DiotAjuste(periodo_id=periodo_id, rfc=datos.rfc.strip().upper(), nombre=datos.nombre, campo=datos.campo,
                   importe=datos.importe if datos.campo else None, excluir=datos.excluir,
                   tipo_tercero=datos.tipo_tercero, tipo_operacion=datos.tipo_operacion,
                   motivo=" ".join(datos.motivo.split()), activo=True, creado_por=ctx.usuario.usuario_id,
                   creado_en=ahora())
    bd.add(a)
    bd.flush()
    p.estado = "abierto"  # hay que volver a procesar
    _bitacora(bd, "diot_ajuste", ctx, request, "diot_ajuste", a.ajuste_id, datos.model_dump(mode="json"))
    bd.commit()
    return ajustes(periodo_id, ctx, bd)


@router.delete("/periodos/{periodo_id}/ajustes/{ajuste_id}", response_model=list[Ajuste])
def quitar_ajuste(periodo_id: int, ajuste_id: int, request: Request, ctx: Contexto = Depends(requiere(OPERAR)),
                  bd: Session = Depends(obtener_bd)) -> list[Ajuste]:
    p = _periodo(bd, periodo_id)
    _abierto(p)
    _sin_corrida(bd, p)
    a = bd.get(DiotAjuste, ajuste_id)
    if not a or a.periodo_id != periodo_id or not a.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese ajuste no existe.")
    a.activo = False
    p.estado = "abierto"
    _bitacora(bd, "diot_ajuste_quitar", ctx, request, "diot_ajuste", a.ajuste_id)
    bd.commit()
    return ajustes(periodo_id, ctx, bd)


# ---------------------------------------------------------------- salidas

@router.get("/periodos/{periodo_id}/txt")
def txt(periodo_id: int, request: Request, ctx: Contexto = Depends(requiere(OPERAR)),
        bd: Session = Depends(obtener_bd)) -> Response:
    p = _periodo(bd, periodo_id)
    motivo = _sin_txt(bd, p)
    if motivo:
        raise HTTPException(status.HTTP_409_CONFLICT, motivo)
    _bitacora(bd, "diot_txt", ctx, request, "diot_periodo", p.periodo_id)
    bd.commit()
    nombre = diot.nombre_archivo(p, "carga SAT.txt")
    return Response(p.txt.encode("ascii", errors="strict"), media_type="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/periodos/{periodo_id}/evidencia")
def evidencia(periodo_id: int, request: Request, ctx: Contexto = Depends(requiere(VER)),
              bd: Session = Depends(obtener_bd)) -> Response:
    p = _periodo(bd, periodo_id)
    if p.procesado_en is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Procesa el periodo primero.")
    _bitacora(bd, "diot_evidencia", ctx, request, "diot_periodo", p.periodo_id)
    bd.commit()
    nombre = diot.nombre_archivo(p, "evidencia.xlsx")
    return Response(diot.evidencia(bd, p),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/periodos/{periodo_id}/referencia", response_model=Periodo)
async def referencia(periodo_id: int, request: Request, archivo: UploadFile = File(...),
                     ctx: Contexto = Depends(requiere(OPERAR)), bd: Session = Depends(obtener_bd)) -> Periodo:
    """El TXT que Fiscal ya presentó, solo para comparar campo por campo. Nunca se copia al resultado."""
    p = _periodo(bd, periodo_id)
    contenido = await archivo.read(2 * 1024 * 1024 + 1)
    if len(contenido) > 2 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El TXT pasa de 2 MB.")
    if b"|" not in contenido:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No parece un TXT de la DIOT (campos separados por «|»).")
    _guardar_referencia(bd, p, archivo.filename or "referencia.txt", contenido)
    _bitacora(bd, "diot_referencia", ctx, request, "diot_periodo", p.periodo_id, {"archivo": p.referencia_nombre})
    bd.commit()
    return _detalle(bd, p)


# ---------------------------------------------------------------- comprobaciones y firmas (validar sin ser fiscalista)

@router.get("/periodos/{periodo_id}/comprobaciones")
def comprobaciones(periodo_id: int, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> dict:
    """Las 9 comprobaciones del mes, en palabras, con su semáforo y el estado de las firmas."""
    return validacion.comprobaciones(bd, _periodo(bd, periodo_id))


def _marca(bd: Session, p: DiotPeriodo, tipo: str, clave: str, ctx: Contexto, motivo: str | None, nota: str | None,
           huella: str) -> None:
    m = bd.scalars(select(DiotRevision).where(DiotRevision.periodo_id == p.periodo_id, DiotRevision.tipo == tipo,
                                              DiotRevision.clave == clave)).first()
    if not m:
        m = DiotRevision(periodo_id=p.periodo_id, tipo=tipo, clave=clave)
        bd.add(m)
    m.motivo, m.nota, m.huella = motivo, (nota or "").strip()[:1000] or None, huella
    m.usuario_id, m.momento = ctx.usuario.usuario_id, ahora()


class MarcaMuestra(BaseModel):
    revisado: bool
    nota: str | None = Field(default=None, max_length=1000)


@router.post("/periodos/{periodo_id}/muestra/{rfc}")
def marcar_muestra(periodo_id: int, rfc: str, datos: MarcaMuestra, request: Request,
                   ctx: Contexto = Depends(requiere(OPERAR)), bd: Session = Depends(obtener_bd)) -> dict:
    """Marca un proveedor de la muestra como revisado (sus pagos y facturas cuadran) o le quita la marca."""
    p = _periodo(bd, periodo_id)
    t = bd.scalars(select(DiotTercero).where(DiotTercero.periodo_id == p.periodo_id, DiotTercero.rfc == rfc)).first()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese proveedor no está en el mes.")
    if datos.revisado:
        _marca(bd, p, "muestra", rfc, ctx, None, datos.nota, validacion._huella_tercero(t))
    else:
        for m in bd.scalars(select(DiotRevision).where(DiotRevision.periodo_id == p.periodo_id,
                                                       DiotRevision.tipo == "muestra", DiotRevision.clave == rfc)):
            bd.delete(m)
    _bitacora(bd, "diot_muestra", ctx, request, "diot_periodo", p.periodo_id, {"rfc": rfc, "revisado": datos.revisado})
    bd.commit()
    return validacion.comprobaciones(bd, p)


class MotivoDiferencia(BaseModel):
    motivo: Literal["ajuste_fiscal", "criterio", "error_plataforma", "error_presentado", "otro"]
    nota: str | None = Field(default=None, max_length=1000)


@router.post("/periodos/{periodo_id}/diferencias/{rfc}")
def motivo_diferencia(periodo_id: int, rfc: str, datos: MotivoDiferencia, request: Request,
                      ctx: Contexto = Depends(requiere(OPERAR)), bd: Session = Depends(obtener_bd)) -> dict:
    """El motivo de una diferencia contra el TXT presentado. «Otro» pide nota."""
    p = _periodo(bd, periodo_id)
    d = next((x for x in validacion.diferencias(bd, p) if x["rfc"] == rfc), None)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese proveedor no tiene diferencias contra lo presentado.")
    if datos.motivo == "otro" and not (datos.nota or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Explica el motivo en la nota.")
    _marca(bd, p, "diferencia", rfc, ctx, datos.motivo, datos.nota, d["huella"])
    _bitacora(bd, "diot_diferencia_motivo", ctx, request, "diot_periodo", p.periodo_id,
              {"rfc": rfc, "motivo": datos.motivo})
    bd.commit()
    return validacion.comprobaciones(bd, p)


class IvaDeclarado(BaseModel):
    importe: Decimal | None = Field(default=None, ge=0)
    nota: str | None = Field(default=None, max_length=500)


@router.put("/periodos/{periodo_id}/iva-declarado")
def iva_declarado(periodo_id: int, datos: IvaDeclarado, request: Request, ctx: Contexto = Depends(requiere(OPERAR)),
                  bd: Session = Depends(obtener_bd)) -> dict:
    """El IVA acreditable que Fiscal puso en la declaración mensual (pago provisional), para compararlo con el TXT."""
    p = _periodo(bd, periodo_id)
    p.iva_declarado = datos.importe
    p.iva_declarado_nota = (datos.nota or "").strip()[:500] or None
    p.iva_declarado_por, p.iva_declarado_en = ctx.usuario.usuario_id, ahora()
    _bitacora(bd, "diot_iva_declarado", ctx, request, "diot_periodo", p.periodo_id,
              {"importe": str(datos.importe) if datos.importe is not None else None})
    bd.commit()
    return validacion.comprobaciones(bd, p)


class NuevaFirma(BaseModel):
    tipo: Literal["revision", "fiscal"]
    nota: str | None = Field(default=None, max_length=1000)


@router.post("/periodos/{periodo_id}/firmas")
def firmar(periodo_id: int, datos: NuevaFirma, request: Request, ctx: Contexto = Depends(requiere(OPERAR)),
           bd: Session = Depends(obtener_bd)) -> dict:
    """Firma de quien revisó las comprobaciones, o visto bueno de Fiscal (otra persona, con permiso de aprobar).
    La firma vale para este TXT: si se vuelve a procesar y el TXT cambia, hay que firmar de nuevo."""
    p = _periodo(bd, periodo_id)
    c = validacion.comprobaciones(bd, p)
    h = validacion.huella_txt(p)
    if not h:
        raise HTTPException(status.HTTP_409_CONFLICT, "No hay TXT que firmar.")
    if datos.tipo == "revision":
        if not c["puede_firmar_revision"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Primero resuelve las decisiones pendientes y las "
                                                          "comprobaciones en rojo o amarillo.")
    else:
        if not ctx.puede(APROBAR):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "El visto bueno lo da alguien de Fiscal con permiso de "
                                                           "aprobar criterios.")
        rev = c["firmas"]["revision"]
        if not rev["firmada"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Primero debe firmar quien revisó las comprobaciones.")
        if rev["usuario_id"] == ctx.usuario.usuario_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "El visto bueno lo da una persona distinta de quien "
                                                          "revisó.")
    for f in bd.scalars(select(DiotFirma).where(DiotFirma.periodo_id == p.periodo_id, DiotFirma.tipo == datos.tipo,
                                                DiotFirma.activa == true())):
        f.activa = False
    bd.add(DiotFirma(periodo_id=p.periodo_id, tipo=datos.tipo, usuario_id=ctx.usuario.usuario_id, momento=ahora(),
                     nota=(datos.nota or "").strip()[:1000] or None, huella_txt=h, activa=True))
    _bitacora(bd, "diot_firma", ctx, request, "diot_periodo", p.periodo_id, {"tipo": datos.tipo, "huella": h[:12]})
    bd.commit()
    return validacion.comprobaciones(bd, p)


@router.delete("/periodos/{periodo_id}/firmas/{tipo}")
def retirar_firma(periodo_id: int, tipo: Literal["revision", "fiscal"], request: Request,
                  ctx: Contexto = Depends(requiere(OPERAR)), bd: Session = Depends(obtener_bd)) -> dict:
    """Quita una firma (por ejemplo, si apareció algo después). Quitar la de revisión quita también la de Fiscal."""
    p = _periodo(bd, periodo_id)
    tipos = ("revision", "fiscal") if tipo == "revision" else ("fiscal",)
    for f in bd.scalars(select(DiotFirma).where(DiotFirma.periodo_id == p.periodo_id, DiotFirma.tipo.in_(tipos),
                                                DiotFirma.activa == true())):
        f.activa = False
    _bitacora(bd, "diot_firma_retirar", ctx, request, "diot_periodo", p.periodo_id, {"tipo": tipo})
    bd.commit()
    return validacion.comprobaciones(bd, p)
