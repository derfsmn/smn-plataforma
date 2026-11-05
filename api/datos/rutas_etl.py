"""Rutas del ETL de ventas (/api/datos/etl): estado y avance en vivo, cargas, cuadre, probar conexión y carga con CSV."""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.config import configuracion
from core.seguridad import Contexto, ip_de, requiere
from datos import etl, revision_smnbi, smnbi
from datos.modelos import Carga, CargaPaso, VentaCuadre, VentaSemanal
from nucleo.bitacora import registrar
from nucleo.modelos import Usuario

router = APIRouter(prefix="/api/datos/etl", tags=["datos · ETL"])
VER = requiere("datos.etl.ver")
CORRER = requiere(etl.CORRER)
MB_ARCHIVO = 300

VENTAS = {"codigo": "ventas", "nombre": "Ventas", "tablas": ["tblVenta", "tblVentaD"], "estado": "lista",
          "nota": "Venta por producto, tienda (almacén) y semana. Ene a sep 2026; las facturas de mayoreo cuentan."}


class UltimaCarga(BaseModel):
    id: int
    estado: str
    archivo: str | None
    nota: str | None  # en una carga buena, lo que dejó; en una fallida, por qué falló
    cargados: int
    fuera: int
    fin_en: datetime | None
    inicio_en: datetime


class FuenteEtl(BaseModel):
    codigo: str
    nombre: str
    tablas: list[str]
    estado: str  # lista / en_curso
    nota: str
    columnas: int | None = None
    filas: int | None = None
    ultima_carga: datetime | None = None  # ventas: la última buena
    ultima: UltimaCarga | None = None  # tablas de SMNBI: la última carga, buena o no


class CargaEtl(BaseModel):
    id: int
    disparada_por: str
    usuario: str | None
    estado: str
    archivo: str | None
    desde: date | None
    hasta: date | None
    paso: str | None
    mes_actual: date | None
    meses_total: int
    meses_hechos: int
    leidos: int
    cargados: int
    fuera: int
    detener: bool
    error: str | None
    cuadra: bool | None
    inicio_en: datetime
    fin_en: datetime | None


class PasoSalida(BaseModel):
    mes: date | None
    paso: str
    estado: str
    filas: int | None
    nota: str | None
    inicio_en: datetime
    fin_en: datetime | None


class CuadreSalida(BaseModel):
    mes: date
    empresa: str
    importe_origen: Decimal | None
    importe_cargado: Decimal
    piezas_origen: Decimal | None
    piezas_cargadas: Decimal
    renglones_fuera: int | None
    cuadra: bool | None


class CargaDetalle(CargaEtl):
    pasos: list[PasoSalida]
    cuadre: list[CuadreSalida]


class Conexion(BaseModel):
    configurada: bool
    falta: list[str]
    servidor: str
    base: str


class Resumen(BaseModel):
    filas: int
    semana_desde: date | None
    semana_hasta: date | None
    meses: int
    ultima_buena: datetime | None


class EstadoEtl(BaseModel):
    conexion: Conexion
    factura_electronica: bool
    programado: bool
    hora: int
    dias_semana: list[int]
    proximos_meses: list[date]
    en_curso: CargaEtl | None
    resumen: Resumen
    fuentes: list[FuenteEtl]
    cargas: list[CargaEtl]


def _cuadra(bd: Session, carga_id: int) -> bool | None:
    valores = bd.scalars(select(VentaCuadre.cuadra).where(VentaCuadre.carga_id == carga_id)).all()
    return None if not valores else all(v is not False for v in valores)


def _salida(bd: Session, c: Carga) -> CargaEtl:
    usuario = bd.get(Usuario, c.usuario_id) if c.usuario_id else None
    return CargaEtl(id=c.carga_id, disparada_por=c.disparada_por, usuario=usuario.nombre if usuario else None, estado=c.estado,
                    archivo=c.archivo, desde=c.desde, hasta=c.hasta, paso=c.paso, mes_actual=c.mes_actual,
                    meses_total=c.meses_total or 0, meses_hechos=c.meses_hechos or 0, leidos=c.leidos or 0,
                    cargados=c.creados or 0, fuera=c.invalidos or 0, detener=bool(c.detener), error=c.error,
                    cuadra=_cuadra(bd, c.carga_id), inicio_en=c.inicio_en, fin_en=c.fin_en)


@router.get("", response_model=EstadoEtl)
def estado(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> EstadoEtl:
    cfg = configuracion()
    actual = etl.en_curso(bd)
    cargas = bd.scalars(select(Carga).where(Carga.fuente == etl.FUENTE).order_by(Carga.carga_id.desc()).limit(20)).all()
    filas, desde, hasta, meses = bd.execute(select(func.count(), func.min(VentaSemanal.semana), func.max(VentaSemanal.semana),
                                                   func.count(VentaSemanal.mes.distinct()))).one()
    ultima = bd.scalar(select(func.max(Carga.fin_en)).where(Carga.fuente == etl.FUENTE, Carga.estado == "completa"))
    fuentes = [FuenteEtl(**VENTAS, ultima_carga=ultima)]
    for codigo, r in smnbi.resumen(bd).items():
        f, c = smnbi.FUENTES[codigo], r["ultima"]
        fuentes.append(FuenteEtl(
            codigo=codigo, nombre=f.nombre, tablas=list(f.tablas), nota=f.nota, columnas=len(f.columnas), filas=r["filas"],
            estado="en_curso" if c and c.estado == "en_curso" else "lista",
            ultima=UltimaCarga(id=c.carga_id, estado=c.estado, archivo=c.archivo, nota=c.error,
                               cargados=(c.creados or 0) + (c.actualizados or 0) + (c.sin_cambios or 0)
                               if codigo == "articulos" else c.creados or 0,
                               fuera=c.invalidos or 0, fin_en=c.fin_en, inicio_en=c.inicio_en) if c else None))
    return EstadoEtl(
        conexion=Conexion(configurada=not etl.falta_conexion(), falta=etl.falta_conexion(), servidor=cfg.smnbi_servidor,
                          base=cfg.smnbi_base),
        factura_electronica=cfg.etl_factura_electronica, programado=cfg.etl_activo, hora=cfg.etl_hora,
        dias_semana=sorted(int(d) for d in cfg.etl_dias_semana.split(",") if d.strip().isdigit()),
        proximos_meses=etl.meses_a_cargar(bd), en_curso=_salida(bd, actual) if actual else None,
        resumen=Resumen(filas=filas or 0, semana_desde=desde, semana_hasta=hasta, meses=meses or 0, ultima_buena=ultima),
        fuentes=fuentes, cargas=[_salida(bd, c) for c in cargas])


@router.get("/cargas/{carga_id}", response_model=CargaDetalle)
def detalle(carga_id: int, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> CargaDetalle:
    c = bd.get(Carga, carga_id)
    if not c or c.fuente != etl.FUENTE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa carga.")
    pasos = bd.scalars(select(CargaPaso).where(CargaPaso.carga_id == carga_id).order_by(CargaPaso.paso_id)).all()
    cuadre = bd.scalars(select(VentaCuadre).where(VentaCuadre.carga_id == carga_id)
                        .order_by(VentaCuadre.mes, VentaCuadre.empresa)).all()
    return CargaDetalle(
        **_salida(bd, c).model_dump(),
        pasos=[PasoSalida(mes=p.mes, paso=p.paso, estado=p.estado, filas=p.filas, nota=p.nota, inicio_en=p.inicio_en,
                          fin_en=p.fin_en) for p in pasos],
        cuadre=[CuadreSalida(mes=q.mes, empresa=q.empresa, importe_origen=q.importe_origen, importe_cargado=q.importe_cargado,
                             piezas_origen=q.piezas_origen, piezas_cargadas=q.piezas_cargadas,
                             renglones_fuera=q.renglones_fuera, cuadra=q.cuadra) for q in cuadre])


@router.post("/probar")
def probar(request: Request, ctx: Contexto = Depends(CORRER), bd: Session = Depends(obtener_bd)) -> dict:
    """Prueba la conexión a SMNBI y regresa el periodo y cuántas ventas y artículos ve. Solo lee."""
    registrar(bd, "etl_probar_conexion", usuario_id=ctx.usuario.usuario_id, entidad="etl", ip=ip_de(request))
    bd.commit()
    try:
        return etl.probar_conexion()
    except etl.ErrorEtl as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"SMNBI respondió con un error: {etl._sin_secretos(e)}") from None


@router.post("/correr", response_model=CargaEtl, status_code=status.HTTP_202_ACCEPTED)
def correr(request: Request, ctx: Contexto = Depends(CORRER), bd: Session = Depends(obtener_bd)) -> CargaEtl:
    """Carga desde SMNBI los meses que tocan (la primera vez, todos desde el primer mes). Corre aparte."""
    if falta := etl.falta_conexion():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Falta capturar en Configuración: " + ", ".join(falta) + ".")
    meses = etl.meses_a_cargar(bd)
    carga = etl.iniciar(bd, "manual", ctx.usuario.usuario_id, meses)
    if not carga:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay una carga del ETL en curso. Espera a que termine o detenla.")
    registrar(bd, "etl_correr", usuario_id=ctx.usuario.usuario_id, entidad="carga", entidad_id=carga.carga_id,
              detalle={"meses": [m.isoformat() for m in meses]}, ip=ip_de(request))
    bd.commit()
    cid = carga.carga_id
    etl.en_hilo(lambda s: etl.ejecutar(s, cid, meses))
    return _salida(bd, carga)


@router.post("/detener", response_model=CargaEtl)
def detener(request: Request, ctx: Contexto = Depends(CORRER), bd: Session = Depends(obtener_bd)) -> CargaEtl:
    """Pide detener la carga: termina lo que esté guardando y para. Los meses terminados quedan."""
    carga = etl.pedir_detener(bd)
    if not carga:
        raise HTTPException(status.HTTP_409_CONFLICT, "No hay ninguna carga del ETL en curso.")
    registrar(bd, "etl_detener", usuario_id=ctx.usuario.usuario_id, entidad="carga", entidad_id=carga.carga_id, ip=ip_de(request))
    bd.commit()
    return _salida(bd, carga)


@router.post("/archivo", response_model=CargaEtl, status_code=status.HTTP_202_ACCEPTED)
async def archivo(request: Request, archivo: UploadFile = File(...), ctx: Contexto = Depends(CORRER),
                  bd: Session = Depends(obtener_bd)) -> CargaEtl:
    """Carga un mes desde el CSV que sale de consulta_venta_semanal.sql en SSMS (con o sin encabezados)."""
    nombre = (archivo.filename or "archivo.csv")[:200]
    if not nombre.lower().endswith((".csv", ".txt")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sube el resultado de la consulta guardado como CSV.")
    contenido = await archivo.read(MB_ARCHIVO * 1024 * 1024 + 1)
    if len(contenido) > MB_ARCHIVO * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El archivo pasa de {MB_ARCHIVO} MB. Sube un mes por archivo.")
    try:
        filas = etl.leer_csv(contenido)
        mes = etl.mes_del_archivo(filas)
    except etl.ErrorEtl as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    carga = etl.iniciar(bd, "manual", ctx.usuario.usuario_id, [mes], archivo=nombre)
    if not carga:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay una carga del ETL en curso. Espera a que termine o detenla.")
    registrar(bd, "etl_archivo", usuario_id=ctx.usuario.usuario_id, entidad="carga", entidad_id=carga.carga_id,
              detalle={"archivo": nombre, "mes": mes.isoformat(), "filas": len(filas)}, ip=ip_de(request))
    bd.commit()
    cid = carga.carga_id
    etl.en_hilo(lambda s: etl.ejecutar_archivo(s, cid, filas, mes))
    return _salida(bd, carga)


# ---------------------------------------------------------------- tablas de SMNBI para el semáforo de productos

@router.get("/smnbi/consultas", response_class=PlainTextResponse)
def consultas_smnbi(_: Contexto = Depends(VER)) -> str:
    """Las consultas para SSMS de cada tabla, en un solo archivo."""
    return smnbi.consultas_sql()


class RenglonRevision(BaseModel):
    fuente: str
    que: str
    smnbi: str
    plataforma: str
    estado: str
    accion: str | None


class Revision(BaseModel):
    resumen: str
    renglones: list[RenglonRevision]


@router.get("/smnbi/revision/consulta", response_class=PlainTextResponse)
def consulta_revision(_: Contexto = Depends(VER)) -> str:
    """La consulta para SSMS que dice cómo está SMNBI hoy, para compararlo con lo cargado."""
    return revision_smnbi.consulta()


@router.post("/smnbi/revision", response_model=Revision)
async def revisar_smnbi(request: Request, archivo: UploadFile = File(...), ctx: Contexto = Depends(VER),
                        bd: Session = Depends(obtener_bd)) -> Revision:
    """Compara el resultado de esa consulta con lo que hay en la plataforma. Solo lee: no carga ni borra nada."""
    contenido = await archivo.read(5 * 1024 * 1024 + 1)
    if len(contenido) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ese archivo es demasiado grande para ser la revisión.")
    try:
        renglones = revision_smnbi.comparar(bd, revision_smnbi.leer(contenido))
    except revision_smnbi.ErrorRevision as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    cambios = [r for r in renglones if r.estado != "igual"]
    registrar(bd, "etl_smnbi_revision", usuario_id=ctx.usuario.usuario_id, entidad="carga", entidad_id=None,
              detalle={"renglones": len(renglones), "cambios": len(cambios)}, ip=ip_de(request))
    bd.commit()
    return Revision(resumen=revision_smnbi.resumen(renglones),
                    renglones=[RenglonRevision(**r) for r in revision_smnbi.a_dict(renglones)])


@router.post("/smnbi/{codigo}/archivo", response_model=UltimaCarga, status_code=status.HTTP_202_ACCEPTED)
async def archivo_smnbi(codigo: str, request: Request, archivo: UploadFile = File(...), ctx: Contexto = Depends(CORRER),
                        bd: Session = Depends(obtener_bd)) -> UltimaCarga:
    """Carga una tabla de SMNBI desde el CSV de su consulta. Reemplaza lo que había (el inventario, solo su fecha)."""
    fuente = smnbi.FUENTES.get(codigo)
    if not fuente:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa fuente no existe.")
    nombre = (archivo.filename or "archivo.csv")[:200]
    if not nombre.lower().endswith((".csv", ".txt")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sube el resultado de la consulta guardado como CSV.")
    contenido = await archivo.read(MB_ARCHIVO * 1024 * 1024 + 1)
    if len(contenido) > MB_ARCHIVO * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El archivo pasa de {MB_ARCHIVO} MB.")
    try:
        filas = smnbi.leer(contenido, fuente)
    except smnbi.ErrorArchivo as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    carga = smnbi.iniciar(bd, fuente, ctx.usuario.usuario_id, nombre)
    if not carga:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya se está cargando {fuente.nombre}. Espera a que termine.")
    registrar(bd, "etl_smnbi_archivo", usuario_id=ctx.usuario.usuario_id, entidad="carga", entidad_id=carga.carga_id,
              detalle={"fuente": codigo, "archivo": nombre, "filas": len(filas)}, ip=ip_de(request))
    bd.commit()
    cid = carga.carga_id
    smnbi.en_hilo(lambda s: smnbi.ejecutar(s, cid, codigo, filas))
    return UltimaCarga(id=cid, estado=carga.estado, archivo=nombre, nota=None, cargados=0, fuera=0, fin_en=None,
                       inicio_en=carga.inicio_en)
