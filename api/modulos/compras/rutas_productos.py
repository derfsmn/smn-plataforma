"""Radar de productos (/api/compras/productos): semáforo de cada producto nuevo e ideas que captura Compras.

Una propuesta que Compras marca «Lista para evaluar» se evalúa sola (rutas_propuestas). Compras también puede capturar
un producto que vio, con fotos y descripción, para analizarlo sin proveedor. Compras confirma la clasificación y los
productos parecidos (eso recalcula) y es quien pone el color final, siempre con motivo. El proveedor no ve nada de esto.
Reglas del motor en radar_productos.py.
"""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, ip_de, requiere
from datos.modelos import Producto, Proveedor
from modulos.compras import mercado_producto as mp
from modulos.compras import politicas_producto as pp
from modulos.compras import radar_productos as rp
from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea, ProductoIdeaFoto
from modulos.compras.modelos_propuestas import Propuesta
from nucleo.archivos import _raiz
from nucleo.bitacora import registrar
from nucleo.modelos import Archivo, Modulo, OrganizacionExterna, Usuario, ahora

router = APIRouter(prefix="/api/compras/productos", tags=["compras · radar de productos"])
VER = "compras.productos.ver"
EVALUAR = "compras.productos.evaluar"
AJUSTAR = "compras.productos.ajustar"
MAX_FOTOS = 6
ESTADOS_IDEA = {"nueva": "Nueva", "buscar_proveedor": "Buscar proveedor", "vigilar": "Vigilar", "descartada": "Descartada"}
Color = Literal["verde", "amarillo", "rojo"]


def _bitacora(bd: Session, accion: str, ctx: Contexto, request: Request, entidad: str, entidad_id,
              detalle: dict | None = None) -> None:
    modulo_id = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "compras"))
    registrar(bd, accion, usuario_id=ctx.usuario.usuario_id, modulo_id=modulo_id, entidad=entidad,
              entidad_id=entidad_id, detalle=detalle, ip=ip_de(request))


def _texto(v: str | None) -> str | None:
    v = " ".join((v or "").split())
    return v or None


# ---------------------------------------------------------------- salidas

class SujetoSalida(BaseModel):
    tipo: str  # propuesta / idea
    id: int
    nombre: str
    marca: str | None
    departamento: str | None
    folio: str | None = None
    proveedor: str | None = None
    estado: str | None = None  # de la idea


class EvaluacionResumen(BaseModel):
    id: int
    sujeto: SujetoSalida
    estado: str
    puntaje: int | None
    color: str | None
    color_final: str | None
    confianza: str | None
    subcategoria: str | None
    creada_en: datetime
    terminada_en: datetime | None
    modelo: str | None = None  # con_proveedor / sin_proveedor


class FactorSalida(BaseModel):
    factor: str
    nombre: str
    peso: Decimal
    puntaje: int | None
    valor: str | None
    detalle: str | None
    provisional: bool
    calculo: str | None = None
    mejora: str | None = None


class ComparableSalida(BaseModel):
    producto_id: int
    sku: str
    descripcion: str | None
    marca: str | None
    subcategoria: str | None
    precio: Decimal | None  # de lista con impuestos
    similitud: Decimal
    origen: str


class FotoSalida(BaseModel):
    archivo_id: int
    nombre: str


class HistorialSalida(BaseModel):
    id: int
    creada_en: datetime
    estado: str
    puntaje: int | None
    color: str | None
    color_final: str | None


class PrecioInternet(BaseModel):
    precio: Decimal
    vendedor: str
    fuente: Literal["google", "sitio"]
    titulo: str
    liga: str | None


class MercadoSalida(BaseModel):
    """Lo que encontró el radar de precios del producto nuevo en internet."""
    precios: list[PrecioInternet]
    mediana: Decimal | None
    notas: list[str]
    publicacion: str | None
    buscado_en: datetime | None
    costo_usd: Decimal


def _mercado(texto: str | None) -> MercadoSalida | None:
    m = mp.Mercado.de_json(texto)
    if not m:
        return None
    return MercadoSalida(precios=[PrecioInternet(**p) for p in m.precios], mediana=m.mediana(), notas=m.notas,
                         publicacion=m.publicacion, buscado_en=datetime.fromisoformat(m.buscado_en) if m.buscado_en else None,
                         costo_usd=m.costo_usd)


class HallazgoPolitica(BaseModel):
    id: str  # R12 = regla, P3 = política
    tipo: Literal["rechazo", "umbral", "politica"]
    titulo: str
    resultado: Literal["cumple", "no_cumple", "sin_datos", "sin_revisar"]
    motivo: str


class CasoParecido(BaseModel):
    caso_id: int
    producto: str
    decision: str
    motivo: str | None
    resultado: str
    fecha: str | None
    similitud: float


class PoliticasSalida(BaseModel):
    """Revisión contra la Base de conocimiento de Compras."""
    hallazgos: list[HallazgoPolitica]
    rechazo: HallazgoPolitica | None
    casos: list[CasoParecido]
    notas: list[str]
    revisada_ia: bool


class EvaluacionDetalle(EvaluacionResumen):
    vigente: bool
    rama: str | None
    segmento: str | None
    clasificacion_origen: str | None
    pesos_origen: str | None
    explicacion: str | None
    explicacion_ia: bool
    motivo_cambio: str | None
    cambiado_por: str | None
    cambiado_en: datetime | None
    error: str | None
    avance: str | None = None
    factores: list[FactorSalida]
    comparables: list[ComparableSalida]
    fotos: list[FotoSalida]
    descripcion: str | None  # de la idea
    precio_visto: Decimal | None
    donde_se_vio: str | None
    costo_estimado: Decimal | None
    historial: list[HistorialSalida]
    mercado: MercadoSalida | None
    politicas: PoliticasSalida | None


def proveedor_de_idea(bd: Session, i: ProductoIdea) -> str | None:
    """El nombre del proveedor que se capturó con la idea (de Intelisis o nuevo), si lo tiene."""
    if i.proveedor_intelisis:
        p = bd.get(Proveedor, i.proveedor_intelisis)
        return ((p.nombre if p else None) or "").strip() or f"Proveedor {i.proveedor_intelisis}"
    return i.proveedor_nuevo


def _sujetos(bd: Session, evaluaciones: list[ProductoEvaluacion]) -> dict[int, SujetoSalida]:
    pids = {e.propuesta_id for e in evaluaciones if e.propuesta_id}
    iids = {e.idea_id for e in evaluaciones if e.idea_id}
    salida: dict[int, SujetoSalida] = {}
    propuestas = {p.propuesta_id: (p, org) for p, org in bd.execute(
        select(Propuesta, OrganizacionExterna.nombre)
        .join(OrganizacionExterna, OrganizacionExterna.organizacion_id == Propuesta.organizacion_id)
        .where(Propuesta.propuesta_id.in_(pids or [0])))}
    ideas = {i.idea_id: i for i in bd.scalars(select(ProductoIdea).where(ProductoIdea.idea_id.in_(iids or [0])))}
    for e in evaluaciones:
        if e.propuesta_id:
            p, org = propuestas[e.propuesta_id]
            salida[e.evaluacion_id] = SujetoSalida(tipo="propuesta", id=p.propuesta_id, nombre=p.producto or "Sin nombre",
                                                   marca=p.marca, departamento=p.departamento, folio=p.folio, proveedor=org)
        else:
            i = ideas[e.idea_id]
            salida[e.evaluacion_id] = SujetoSalida(tipo="idea", id=i.idea_id, nombre=i.nombre, marca=i.marca,
                                                   departamento=i.departamento, estado=i.estado,
                                                   proveedor=proveedor_de_idea(bd, i))
    return salida


def _resumen(e: ProductoEvaluacion, sujeto: SujetoSalida) -> EvaluacionResumen:
    return EvaluacionResumen(id=e.evaluacion_id, sujeto=sujeto, estado=e.estado, puntaje=e.puntaje, color=e.color,
                             color_final=e.color_final, confianza=e.confianza, subcategoria=e.subcategoria,
                             creada_en=e.creada_en, terminada_en=e.terminada_en, modelo=e.modelo)


def _detalle(bd: Session, e: ProductoEvaluacion) -> EvaluacionDetalle:
    sujeto = _sujetos(bd, [e])[e.evaluacion_id]
    productos = {p.producto_id: p for p in bd.scalars(select(Producto).where(
        Producto.producto_id.in_([c.producto_id for c in e.comparables] or [0])))}
    idea = bd.get(ProductoIdea, e.idea_id) if e.idea_id else None
    fotos = []
    if idea and idea.fotos:
        nombres = dict(bd.execute(select(Archivo.archivo_id, Archivo.nombre_original)
                                  .where(Archivo.archivo_id.in_([f.archivo_id for f in idea.fotos]))).all())
        fotos = [FotoSalida(archivo_id=f.archivo_id, nombre=nombres.get(f.archivo_id, "foto")) for f in idea.fotos]
    q = select(ProductoEvaluacion).order_by(ProductoEvaluacion.evaluacion_id.desc())
    q = q.where(ProductoEvaluacion.propuesta_id == e.propuesta_id) if e.propuesta_id else q.where(
        ProductoEvaluacion.idea_id == e.idea_id)
    historial = [HistorialSalida(id=h.evaluacion_id, creada_en=h.creada_en, estado=h.estado, puntaje=h.puntaje,
                                 color=h.color, color_final=h.color_final) for h in bd.scalars(q.limit(20))]
    quien = bd.get(Usuario, e.cambiado_por) if e.cambiado_por else None
    orden = {f: i for i, f in enumerate(rp.FACTORES)}
    return EvaluacionDetalle(
        **_resumen(e, sujeto).model_dump(), vigente=e.vigente, rama=e.rama, segmento=e.segmento,
        clasificacion_origen=e.clasificacion_origen, pesos_origen=e.pesos_origen, explicacion=e.explicacion,
        explicacion_ia=e.explicacion_ia, motivo_cambio=e.motivo_cambio, cambiado_por=quien.nombre if quien else None,
        cambiado_en=e.cambiado_en, error=e.error, avance=e.avance, mercado=_mercado(e.mercado),
        politicas=PoliticasSalida(**r.__dict__) if (r := pp.Revision.de_json(e.politicas)) else None,
        factores=[FactorSalida(factor=f.factor, nombre=rp.NOMBRES.get(f.factor, f.factor), peso=f.peso, puntaje=f.puntaje,
                               valor=f.valor, detalle=f.detalle, provisional=f.provisional,
                               calculo=f.calculo, mejora=f.mejora)
                  for f in sorted(e.factores, key=lambda f: orden.get(f.factor, 99))],
        comparables=[ComparableSalida(producto_id=c.producto_id, sku=productos[c.producto_id].sku,
                                      descripcion=productos[c.producto_id].descripcion,
                                      marca=productos[c.producto_id].marca,
                                      subcategoria=productos[c.producto_id].subcategoria,
                                      precio=productos[c.producto_id].precio_lista_con_impuestos,
                                      similitud=c.similitud, origen=c.origen)
                     for c in e.comparables if c.producto_id in productos],
        fotos=fotos, descripcion=idea.descripcion if idea else None, precio_visto=idea.precio_visto if idea else None,
        donde_se_vio=idea.donde_se_vio if idea else None, costo_estimado=idea.costo_estimado if idea else None,
        historial=historial,
    )


def _evaluacion(bd: Session, evaluacion_id: int) -> ProductoEvaluacion:
    e = bd.get(ProductoEvaluacion, evaluacion_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa evaluación.")
    return e


def _vigente_lista(bd: Session, evaluacion_id: int) -> ProductoEvaluacion:
    """Solo se corrige la evaluación vigente y que ya terminó; recalcular mientras corre duplicaría trabajo."""
    e = _evaluacion(bd, evaluacion_id)
    if not e.vigente:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa evaluación ya no es la vigente; abre la más reciente.")
    if e.estado == "en_curso":
        raise HTTPException(status.HTTP_409_CONFLICT, "La evaluación sigue en curso; espera a que termine.")
    return e


def _relanzar(bd: Session, e: ProductoEvaluacion, ctx: Contexto, **kwargs) -> ProductoEvaluacion:
    nueva = rp.iniciar(bd, propuesta_id=e.propuesta_id, idea_id=e.idea_id, usuario_id=ctx.usuario.usuario_id, **kwargs)
    rp.en_hilo(nueva.evaluacion_id)
    return nueva


# ---------------------------------------------------------------- evaluaciones

@router.get("/evaluaciones", response_model=list[EvaluacionResumen])
def evaluaciones(tipo: Literal["propuesta", "idea"] | None = None, color: Color | None = None,
                 _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> list[EvaluacionResumen]:
    """Las evaluaciones vigentes, la más reciente primero. El filtro de color usa el color final si Compras lo cambió."""
    q = select(ProductoEvaluacion).where(ProductoEvaluacion.vigente == true())
    if tipo == "propuesta":
        q = q.where(ProductoEvaluacion.propuesta_id.is_not(None))
    elif tipo == "idea":
        q = q.where(ProductoEvaluacion.idea_id.is_not(None))
    filas = list(bd.scalars(q.order_by(ProductoEvaluacion.evaluacion_id.desc()).limit(500)))
    if color:
        filas = [e for e in filas if (e.color_final or e.color) == color]
    sujetos = _sujetos(bd, filas)
    return [_resumen(e, sujetos[e.evaluacion_id]) for e in filas]


@router.get("/evaluaciones/{evaluacion_id}", response_model=EvaluacionDetalle)
def evaluacion(evaluacion_id: int, _: Contexto = Depends(requiere(VER)),
               bd: Session = Depends(obtener_bd)) -> EvaluacionDetalle:
    return _detalle(bd, _evaluacion(bd, evaluacion_id))


@router.get("/propuestas/{propuesta_id}", response_model=EvaluacionDetalle | None)
def de_propuesta(propuesta_id: int, _: Contexto = Depends(requiere(VER)),
                 bd: Session = Depends(obtener_bd)) -> EvaluacionDetalle | None:
    """La evaluación vigente de una propuesta, para mostrarla en su detalle; nada si no se ha evaluado."""
    e = rp.vigente(bd, propuesta_id=propuesta_id)
    return _detalle(bd, e) if e else None


@router.post("/evaluaciones/{evaluacion_id}/recalcular", response_model=EvaluacionDetalle)
def recalcular(evaluacion_id: int, request: Request, ctx: Contexto = Depends(requiere(EVALUAR)),
               bd: Session = Depends(obtener_bd)) -> EvaluacionDetalle:
    e = _vigente_lista(bd, evaluacion_id)
    nueva = _relanzar(bd, e, ctx)
    _bitacora(bd, "recalcular_evaluacion", ctx, request, "producto_evaluacion", nueva.evaluacion_id,
              {"anterior": e.evaluacion_id})
    bd.commit()
    return _detalle(bd, nueva)


class Clasificacion(BaseModel):
    rama: str | None = Field(None, max_length=300)
    subcategoria: str | None = Field(None, max_length=300)
    segmento: str | None = Field(None, max_length=300)


class OpcionClasificacion(BaseModel):
    rama: str
    subcategoria: str
    segmento: str


@router.get("/clasificaciones", response_model=list[OpcionClasificacion])
def clasificaciones(departamento: str | None = None, _: Contexto = Depends(requiere(VER)),
                    bd: Session = Depends(obtener_bd)) -> list[OpcionClasificacion]:
    """Las combinaciones de rama, subcategoría y segmento que ya existen en el catálogo, para confirmar la clasificación."""
    filas = sorted(rp.opciones_clasificacion(bd, departamento))
    return [OpcionClasificacion(rama=r, subcategoria=s, segmento=g) for r, s, g in filas]


@router.put("/evaluaciones/{evaluacion_id}/clasificacion", response_model=EvaluacionDetalle)
def confirmar_clasificacion(evaluacion_id: int, datos: Clasificacion, request: Request,
                            ctx: Contexto = Depends(requiere(EVALUAR)), bd: Session = Depends(obtener_bd)) -> EvaluacionDetalle:
    """Compras confirma o corrige la clasificación; se recalcula con ella y se conserva en los siguientes cálculos."""
    e = _vigente_lista(bd, evaluacion_id)
    elegida = (datos.rama or "", datos.subcategoria or "", datos.segmento or "")
    if elegida != ("", "", "") and elegida not in rp.opciones_clasificacion(bd, e.departamento):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige una clasificación que exista en el catálogo.")
    nueva = _relanzar(bd, e, ctx, clasificacion=tuple(v or None for v in elegida))
    _bitacora(bd, "confirmar_clasificacion", ctx, request, "producto_evaluacion", nueva.evaluacion_id,
              {"anterior": e.evaluacion_id, "antes": [e.rama, e.subcategoria, e.segmento], "despues": list(elegida)})
    bd.commit()
    return _detalle(bd, nueva)


class Comparables(BaseModel):
    skus: list[str] = Field(max_length=rp.MAX_COMPARABLES)


@router.put("/evaluaciones/{evaluacion_id}/comparables", response_model=EvaluacionDetalle)
def fijar_comparables(evaluacion_id: int, datos: Comparables, request: Request,
                      ctx: Contexto = Depends(requiere(EVALUAR)), bd: Session = Depends(obtener_bd)) -> EvaluacionDetalle:
    """Compras quita o agrega productos parecidos (por SKU); se recalcula y la lista queda fija. Vacía = el sistema busca."""
    e = _vigente_lista(bd, evaluacion_id)
    skus = list(dict.fromkeys(s.strip() for s in datos.skus if s.strip()))
    ids = dict(bd.execute(select(Producto.sku, Producto.producto_id).where(Producto.sku.in_(skus or [""]))).all())
    if faltan := [s for s in skus if s not in ids]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Estos SKU no están en el catálogo: {', '.join(faltan)}.")
    nueva = _relanzar(bd, e, ctx, comparables=[ids[s] for s in skus])  # vacía: el sistema vuelve a buscar
    _bitacora(bd, "fijar_comparables", ctx, request, "producto_evaluacion", nueva.evaluacion_id,
              {"anterior": e.evaluacion_id, "skus": skus})
    bd.commit()
    return _detalle(bd, nueva)


class CambioColor(BaseModel):
    color: Color | None  # nada = regresar al color del radar
    motivo: str = Field(min_length=1, max_length=1000)


@router.post("/evaluaciones/{evaluacion_id}/color", response_model=EvaluacionDetalle)
def cambiar_color(evaluacion_id: int, datos: CambioColor, request: Request, ctx: Contexto = Depends(requiere(AJUSTAR)),
                  bd: Session = Depends(obtener_bd)) -> EvaluacionDetalle:
    """Compras pone el color final; el motivo es obligatorio y queda en la bitácora (Diego, 2026-10-26)."""
    e = _vigente_lista(bd, evaluacion_id)
    if e.estado != "lista":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta evaluación falló; recalcúlala antes de cambiar el color.")
    motivo = _texto(datos.motivo)
    if not motivo or len(motivo) < 10:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe el motivo del cambio (al menos 10 letras).")
    antes = e.color_final or e.color
    e.color_final = datos.color if datos.color != e.color else None
    e.motivo_cambio, e.cambiado_por, e.cambiado_en = motivo, ctx.usuario.usuario_id, ahora()
    _bitacora(bd, "cambiar_color", ctx, request, "producto_evaluacion", e.evaluacion_id,
              {"radar": e.color, "antes": antes, "despues": e.color_final or e.color, "motivo": motivo})
    bd.commit()
    return _detalle(bd, e)


class ProductoBusqueda(BaseModel):
    producto_id: int
    sku: str
    descripcion: str | None
    marca: str | None
    subcategoria: str | None
    precio: Decimal | None


@router.get("/catalogo", response_model=list[ProductoBusqueda])
def buscar_catalogo(q: str = Query(min_length=2, max_length=100), _: Contexto = Depends(requiere(EVALUAR)),
                    bd: Session = Depends(obtener_bd)) -> list[ProductoBusqueda]:
    """Productos activos por SKU o descripción, para agregarlos como parecidos."""
    texto = f"%{q.strip()}%"
    filas = bd.scalars(select(Producto).where(Producto.activo == true(), or_(
        Producto.sku == q.strip(), Producto.descripcion.ilike(texto), Producto.marca.ilike(texto)))
        .order_by(Producto.descripcion).limit(20))
    return [ProductoBusqueda(producto_id=p.producto_id, sku=p.sku, descripcion=p.descripcion, marca=p.marca,
                             subcategoria=p.subcategoria, precio=p.precio_lista_con_impuestos) for p in filas]


# ---------------------------------------------------------------- ideas de Compras

class IdeaEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=300)
    marca: str | None = Field(None, max_length=120)
    descripcion: str | None = Field(None, max_length=2000)
    departamento: str | None = Field(None, max_length=300)
    ingrediente: str | None = Field(None, max_length=200)
    forma: str | None = Field(None, max_length=60)
    contenido: str | None = Field(None, max_length=60)
    precio_visto: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)
    donde_se_vio: str | None = Field(None, max_length=300)
    costo_estimado: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)
    fotos: list[int] = Field(default_factory=list, max_length=MAX_FOTOS)  # archivo_id subidos con /api/archivos
    # Captura corta con proveedor (Diego, 2026-11-04): clave de Intelisis, o el nombre de un proveedor nuevo
    proveedor_codigo: str | None = Field(None, max_length=10)
    proveedor_nuevo: str | None = Field(None, max_length=200)


@router.post("/ideas", response_model=EvaluacionDetalle, status_code=status.HTTP_201_CREATED)
def capturar_idea(datos: IdeaEntrada, request: Request, ctx: Contexto = Depends(requiere(EVALUAR)),
                  bd: Session = Depends(obtener_bd)) -> EvaluacionDetalle:
    """Compras captura un producto con el cuestionario corto, con o sin proveedor. Se evalúa solo al guardarlo.
    Con proveedor de Intelisis se califica con el semáforo «con proveedor actual»."""
    codigo, nuevo = _texto(datos.proveedor_codigo), _texto(datos.proveedor_nuevo)
    if codigo and nuevo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige un proveedor de Intelisis o escribe uno nuevo, no los dos.")
    if codigo:
        prov = bd.get(Proveedor, codigo)
        if not prov or not (prov.agente or "").strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ese proveedor no está en Intelisis con agente.")
    if nuevo is not None and len(nuevo) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe el nombre del proveedor nuevo.")
    fotos = list(dict.fromkeys(datos.fotos))
    archivos = {a.archivo_id: a for a in bd.scalars(select(Archivo).where(Archivo.archivo_id.in_(fotos or [0])))}
    for fid in fotos:
        a = archivos.get(fid)
        if not a or a.subido_por != ctx.usuario.usuario_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Una de las fotos no existe o no la subiste tú.")
        if not a.tipo_contenido.startswith("image/"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"«{a.nombre_original}» no es una imagen.")
    i = ProductoIdea(nombre=_texto(datos.nombre), marca=_texto(datos.marca), descripcion=(datos.descripcion or "").strip() or None,
                     departamento=_texto(datos.departamento), ingrediente=_texto(datos.ingrediente),
                     forma=_texto(datos.forma), contenido=_texto(datos.contenido), precio_visto=datos.precio_visto,
                     donde_se_vio=_texto(datos.donde_se_vio), costo_estimado=datos.costo_estimado, estado="nueva",
                     proveedor_intelisis=codigo, proveedor_nuevo=nuevo,
                     creada_por=ctx.usuario.usuario_id, creada_en=ahora(), actualizada_en=ahora())
    i.fotos = [ProductoIdeaFoto(archivo_id=f) for f in fotos]
    bd.add(i)
    bd.flush()
    for f in fotos:  # el archivo queda ligado a la idea
        archivos[f].entidad, archivos[f].entidad_id = "producto_idea", str(i.idea_id)
    _bitacora(bd, "capturar_idea", ctx, request, "producto_idea", i.idea_id, {"nombre": i.nombre, "fotos": len(fotos),
                                                                                  "proveedor": codigo or nuevo})
    bd.commit()
    e = rp.iniciar(bd, idea_id=i.idea_id, usuario_id=ctx.usuario.usuario_id)
    rp.en_hilo(e.evaluacion_id)
    return _detalle(bd, e)


class CambioEstadoIdea(BaseModel):
    estado: Literal["nueva", "buscar_proveedor", "vigilar", "descartada"]


@router.patch("/ideas/{idea_id}/estado", response_model=SujetoSalida)
def cambiar_estado_idea(idea_id: int, datos: CambioEstadoIdea, request: Request,
                        ctx: Contexto = Depends(requiere(EVALUAR)), bd: Session = Depends(obtener_bd)) -> SujetoSalida:
    i = bd.get(ProductoIdea, idea_id)
    if not i:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa idea.")
    antes, i.estado, i.actualizada_en = i.estado, datos.estado, ahora()
    _bitacora(bd, "cambiar_estado_idea", ctx, request, "producto_idea", i.idea_id, {"antes": antes, "despues": i.estado})
    bd.commit()
    return SujetoSalida(tipo="idea", id=i.idea_id, nombre=i.nombre, marca=i.marca, departamento=i.departamento,
                        estado=i.estado)


@router.get("/ideas/{idea_id}/fotos/{archivo_id}")
def foto_idea(idea_id: int, archivo_id: int, _: Contexto = Depends(requiere(VER)),
              bd: Session = Depends(obtener_bd)) -> FileResponse:
    """Cualquiera con permiso de ver el radar ve las fotos de una idea (el almacén solo deja al que la subió)."""
    ligada = bd.get(ProductoIdeaFoto, (idea_id, archivo_id))
    archivo = bd.get(Archivo, archivo_id) if ligada else None
    raiz = _raiz()
    ruta = (raiz / archivo.ruta_almacenamiento).resolve() if archivo else None
    if not ruta or raiz not in ruta.parents or not ruta.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa foto.")
    return FileResponse(ruta, media_type=archivo.tipo_contenido, filename=archivo.nombre_original,
                        headers={"X-Content-Type-Options": "nosniff"})
