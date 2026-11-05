"""Rutas del catálogo de productos del Centro de datos (/api/datos)."""
import json
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import false, func, or_, select, true
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.config import configuracion
from core.seguridad import Contexto, ip_de, requiere
from datos import catalogo
from datos.modelos import Carga, Producto, ProductoFuente, ProductoPrecioHistorial
from nucleo.bitacora import registrar
from nucleo.modelos import Usuario

router = APIRouter(prefix="/api/datos", tags=["datos · catálogo"])
VER = requiere("datos.productos.ver")
ADMIN = requiere("datos.catalogo.administrar")


# ---------------------------------------------------------------- esquemas

class ProductoResumen(BaseModel):
    id: int
    sku: str
    descripcion: str | None
    marca: str | None
    departamento: str | None
    nombre_proveedor: str | None
    precio_lista_con_impuestos: Decimal | None
    precio_membresia_con_impuestos: Decimal | None
    origen: str
    activo: bool
    con_diferencias: bool
    datos_incompletos: bool
    liga_imagen: str | None
    actualizado_en: datetime

    @classmethod
    def de(cls, p: Producto) -> "ProductoResumen":
        return cls(id=p.producto_id, sku=p.sku, descripcion=p.descripcion, marca=p.marca, departamento=p.departamento,
                   nombre_proveedor=p.nombre_proveedor, precio_lista_con_impuestos=p.precio_lista_con_impuestos,
                   precio_membresia_con_impuestos=p.precio_membresia_con_impuestos, origen=p.origen, activo=p.activo,
                   con_diferencias=p.con_diferencias, datos_incompletos=p.datos_incompletos, liga_imagen=p.liga_imagen,
                   actualizado_en=p.actualizado_en)


class PaginaProductos(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    productos: list[ProductoResumen]


class FuenteSalida(BaseModel):
    fuente: str
    presente: bool
    visto_por_ultima_vez_en: datetime
    datos: dict


class PrecioSalida(BaseModel):
    vigente_desde: datetime
    precio_lista: Decimal | None
    precio_membresia: Decimal | None
    iva_pct: Decimal | None
    ieps_pct: Decimal | None
    precio_tienda_en_linea: Decimal | None


class ProductoDetalle(ProductoResumen):
    rama: str | None
    subcategoria: str | None
    segmento: str | None
    clasificacion: str | None
    codigo_proveedor: str | None
    codigo_barras: str | None
    precio_lista: Decimal | None
    precio_membresia: Decimal | None
    iva_pct: Decimal | None
    ieps_pct: Decimal | None
    precio_tienda_en_linea: Decimal | None
    disponible_en_linea: bool | None
    liga_producto: str | None
    creado_en: datetime
    de_donde: dict[str, str]
    diferencias: list[dict]
    fuentes: list[FuenteSalida]
    historial: list[PrecioSalida]


class CargaSalida(BaseModel):
    id: int
    fuente: str
    disparada_por: str
    usuario: str | None
    estado: str
    completa: bool
    paginas: int
    leidos: int
    creados: int
    actualizados: int
    sin_cambios: int
    ausentes: int
    invalidos: int
    precios_cambiados: int
    total_fuente: int | None
    error: str | None
    inicio_en: datetime
    fin_en: datetime | None


class EstadoCatalogo(BaseModel):
    falta_configurar: list[str]  # del API de artículos
    tienda_url: str  # vacío = la tienda no se carga
    automatico: bool
    hora: int
    dias_semana: list[int]
    zona_horaria: str
    en_curso: CargaSalida | None
    totales: dict[str, int]
    cargas: list[CargaSalida]


def _carga(bd: Session, c: Carga) -> CargaSalida:
    usuario = bd.get(Usuario, c.usuario_id) if c.usuario_id else None
    return CargaSalida(id=c.carga_id, fuente=c.fuente, disparada_por=c.disparada_por, usuario=usuario.nombre if usuario else None,
                       estado=c.estado, completa=c.completa, paginas=c.paginas, leidos=c.leidos, creados=c.creados,
                       actualizados=c.actualizados, sin_cambios=c.sin_cambios, ausentes=c.ausentes, invalidos=c.invalidos,
                       precios_cambiados=c.precios_cambiados, total_fuente=c.total_fuente, error=c.error,
                       inicio_en=c.inicio_en, fin_en=c.fin_en)


# ---------------------------------------------------------------- productos

Estado = Literal["activos", "archivados", "diferencias", "incompletos", "todos"]


@router.get("/productos", response_model=PaginaProductos)
def productos(q: str = "", departamento: str = "", marca: str = "", estado: Estado = "activos",
              pagina: int = Query(1, ge=1), por_pagina: int = Query(50, ge=10, le=200),
              _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> PaginaProductos:
    filtro = select(Producto)
    if q.strip():
        texto = f"%{q.strip()}%"
        filtro = filtro.where(or_(Producto.sku.like(texto), Producto.descripcion.like(texto), Producto.marca.like(texto),
                                  Producto.codigo_barras.like(texto), Producto.nombre_proveedor.like(texto)))
    if departamento:
        filtro = filtro.where(Producto.departamento == departamento)
    if marca:
        filtro = filtro.where(Producto.marca == marca)
    if estado == "activos":
        filtro = filtro.where(Producto.activo == true())
    elif estado == "archivados":
        filtro = filtro.where(Producto.activo == false())
    elif estado == "diferencias":
        filtro = filtro.where(Producto.activo == true(), Producto.con_diferencias == true())
    elif estado == "incompletos":
        filtro = filtro.where(Producto.activo == true(), Producto.datos_incompletos == true())
    total = bd.scalar(select(func.count()).select_from(filtro.subquery())) or 0
    filas = bd.scalars(filtro.order_by(Producto.descripcion, Producto.sku)
                       .offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
    return PaginaProductos(total=total, pagina=pagina, por_pagina=por_pagina, productos=[ProductoResumen.de(p) for p in filas])


@router.get("/productos/filtros")
def filtros(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> dict[str, list[str]]:
    def distintos(columna):
        return [v for v in bd.scalars(select(columna).where(Producto.activo == true(), columna.is_not(None))
                                      .distinct().order_by(columna))]

    return {"departamentos": distintos(Producto.departamento), "marcas": distintos(Producto.marca)}


def _datos_fuente(texto: str) -> dict:
    """Lo que trajo la fuente. Los artículos de SMNBI se guardan como lista en el orden de la consulta."""
    datos = json.loads(texto)
    if isinstance(datos, list):
        return dict(zip((c for c, _ in catalogo.COLUMNAS_ETL), datos))
    return datos if isinstance(datos, dict) else {"valor": datos}


@router.get("/productos/{producto_id}", response_model=ProductoDetalle)
def producto(producto_id: int, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> ProductoDetalle:
    p = bd.get(Producto, producto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese producto no existe.")
    extra = json.loads(p.diferencias) if p.diferencias else {}
    fuentes = bd.scalars(select(ProductoFuente).where(ProductoFuente.producto_id == p.producto_id)
                         .order_by(ProductoFuente.fuente)).all()
    historial = bd.scalars(select(ProductoPrecioHistorial).where(ProductoPrecioHistorial.producto_id == p.producto_id)
                           .order_by(ProductoPrecioHistorial.vigente_desde.desc()).limit(60)).all()
    return ProductoDetalle(
        **ProductoResumen.de(p).model_dump(), rama=p.rama, subcategoria=p.subcategoria, segmento=p.segmento,
        clasificacion=p.clasificacion, codigo_proveedor=p.codigo_proveedor, codigo_barras=p.codigo_barras,
        precio_lista=p.precio_lista, precio_membresia=p.precio_membresia, iva_pct=p.iva_pct, ieps_pct=p.ieps_pct,
        precio_tienda_en_linea=p.precio_tienda_en_linea, disponible_en_linea=p.disponible_en_linea,
        liga_producto=p.liga_producto, creado_en=p.creado_en,
        de_donde=extra.get("de_donde", {}), diferencias=extra.get("diferencias", []),
        fuentes=[FuenteSalida(fuente=f.fuente, presente=f.presente, visto_por_ultima_vez_en=f.visto_por_ultima_vez_en,
                              datos=_datos_fuente(f.datos)) for f in fuentes],
        historial=[PrecioSalida(vigente_desde=h.vigente_desde, precio_lista=h.precio_lista, precio_membresia=h.precio_membresia,
                                iva_pct=h.iva_pct, ieps_pct=h.ieps_pct, precio_tienda_en_linea=h.precio_tienda_en_linea)
                   for h in historial])


# ---------------------------------------------------------------- cargas

@router.get("/catalogo", response_model=EstadoCatalogo)
def estado(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> EstadoCatalogo:
    cfg = configuracion()
    actual = catalogo.en_curso(bd)
    cargas = bd.scalars(select(Carga).where(Carga.fuente.in_(catalogo.FUENTES)).order_by(Carga.inicio_en.desc()).limit(20)).all()
    return EstadoCatalogo(
        falta_configurar=catalogo.api_configurada(), tienda_url=cfg.tienda_url, automatico=cfg.catalogo_activo, hora=cfg.catalogo_hora,
        dias_semana=sorted(int(d) for d in cfg.catalogo_dias_semana.split(",") if d.strip().isdigit()),
        zona_horaria=cfg.catalogo_zona_horaria, en_curso=_carga(bd, actual) if actual else None,
        totales=catalogo.totales(bd), cargas=[_carga(bd, c) for c in cargas])


Fuente = Literal["API", "TIENDA"]
NOMBRE = {"API": "el API de artículos", "TIENDA": "la tienda en línea"}


@router.post("/catalogo/cargar", response_model=CargaSalida, status_code=status.HTTP_202_ACCEPTED)
def cargar(request: Request, fuente: Fuente = "API", ctx: Contexto = Depends(ADMIN),
           bd: Session = Depends(obtener_bd)) -> CargaSalida:
    """Carga ya el catálogo desde una fuente. Corre aparte; la pantalla consulta el estado."""
    if falta := catalogo.FALTA[fuente]():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Falta capturar en Configuración: " + ", ".join(falta) + ".")
    carga = catalogo.iniciar(bd, fuente, "manual", ctx.usuario.usuario_id)
    if not carga:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay una carga en curso. Espera a que termine.")
    registrar(bd, "catalogo_cargar", usuario_id=ctx.usuario.usuario_id, entidad="carga", entidad_id=carga.carga_id,
              detalle={"fuente": fuente}, ip=ip_de(request))
    bd.commit()
    catalogo.ejecutar_aparte(carga.carga_id)
    return _carga(bd, carga)
