"""Búsquedas de proveedor (Compras → Productos nuevos → «Búsqueda de proveedores»). Lógica en busquedas.py."""
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, requiere
from datos.modelos import Proveedor
from modulos.compras import busquedas as bq
from modulos.compras import oportunidades as op
from modulos.compras import radar_productos as rp
from modulos.compras.modelos_busquedas import BusquedaProveedor
from modulos.compras.modelos_comite import ComiteProducto, ComiteReunion
from modulos.compras.modelos_productos import Oportunidad, ProductoIdea, ProductoIdeaFoto
from modulos.compras.rutas_productos import EVALUAR, _bitacora, _texto, proveedor_de_idea
from nucleo.modelos import Usuario, ahora

router = APIRouter(prefix="/api/compras/busquedas", tags=["compras: búsqueda de proveedor"])


# ---------------------------------------------------------------- salidas

class Persona(BaseModel):
    id: int
    nombre: str


class AvanceSalida(BaseModel):
    id: int
    tipo: str
    texto: str
    proveedor: str | None
    resultado: str | None
    resultado_texto: str | None
    quien: str | None
    creado_en: datetime


class SemaforoBreve(BaseModel):
    evaluacion_id: int
    estado: str
    color: str | None
    puntaje: int | None
    confianza: str | None
    modelo: str | None
    explicacion: str | None


class Evidencia(BaseModel):
    fuente: str
    texto: str


class ReunionBreve(BaseModel):
    id: int
    fecha: date
    estado: str
    decision: str | None = None


class BusquedaBreve(BaseModel):
    id: int
    estado: str
    estado_texto: str
    origen: str
    idea_id: int
    nombre: str
    marca: str | None
    departamento: str | None
    color: str | None  # el de hoy (el semáforo vigente)
    puntaje: int | None
    imagen: str | None
    puertas: list[str]  # por qué llegó: tendencia / mas_vendido / captura
    responsable: Persona | None
    contactos: int
    ultimo_avance: datetime | None
    proveedor: str | None
    creada_en: datetime
    cerrada_en: datetime | None


class BusquedaDetalle(BusquedaBreve):
    color_inicial: str | None
    puntaje_inicial: int | None
    nota: str | None
    descripcion: str | None
    contenido: str | None
    forma: str | None
    precio_visto: Decimal | None
    donde_se_vio: str | None
    fotos: list[int]
    por_que: str | None
    evidencia: list[Evidencia]
    costo: Decimal | None
    motivo_cierre: str | None
    semaforo: SemaforoBreve | None
    avances: list[AvanceSalida]
    reunion_abierta: ReunionBreve | None  # para subirla al comité
    en_comite: ReunionBreve | None  # la última reunión donde está


class Bandeja(BaseModel):
    busquedas: list[BusquedaBreve]
    conteos: dict[str, int]
    colores_automaticos: list[str]


# ---------------------------------------------------------------- armar

def _personas(bd: Session, ids: set[int]) -> dict[int, Persona]:
    if not ids:
        return {}
    return {u.usuario_id: Persona(id=u.usuario_id, nombre=u.nombre)
            for u in bd.scalars(select(Usuario).where(Usuario.usuario_id.in_(ids)))}


def _oportunidades(bd: Session, ideas: list[int]) -> dict[int, Oportunidad]:
    if not ideas:
        return {}
    return {o.idea_id: o for o in bd.scalars(select(Oportunidad).where(Oportunidad.idea_id.in_(ideas)))}


def _breve(bd: Session, b: BusquedaProveedor, idea: ProductoIdea, o: Oportunidad | None, gente: dict[int, Persona],
           clase=BusquedaBreve, **extra):
    e = rp.vigente(bd, idea_id=idea.idea_id)
    contactos = [a for a in b.avances if a.tipo == "contacto"]
    return clase(
        id=b.busqueda_id, estado=b.estado, estado_texto=bq.ESTADOS[b.estado], origen=b.origen, idea_id=idea.idea_id,
        nombre=idea.nombre, marca=idea.marca, departamento=idea.departamento,
        color=bq.color_de(e) if e and e.estado == "lista" else None,
        puntaje=e.puntaje if e and e.estado == "lista" else None, imagen=o.imagen if o else None,
        puertas=op.puertas(json.loads(o.evidencia) if o and o.evidencia else None),
        responsable=gente.get(b.responsable_id) if b.responsable_id else None, contactos=len(contactos),
        ultimo_avance=b.avances[-1].creado_en if b.avances else None,
        proveedor=proveedor_de_idea(bd, idea) if b.estado == "encontrado" else None,
        creada_en=b.creada_en, cerrada_en=b.cerrada_en, **extra)


def _detalle(bd: Session, b: BusquedaProveedor) -> BusquedaDetalle:
    idea = bd.get(ProductoIdea, b.idea_id)
    o = _oportunidades(bd, [idea.idea_id]).get(idea.idea_id)
    gente = _personas(bd, {x for x in [b.responsable_id, *(a.usuario_id for a in b.avances)] if x})
    e = rp.vigente(bd, idea_id=idea.idea_id)
    fotos = list(bd.scalars(select(ProductoIdeaFoto.archivo_id).where(ProductoIdeaFoto.idea_id == idea.idea_id)))
    evidencia = [Evidencia(fuente=str(x.get("fuente") or ""), texto=str(x.get("texto") or ""))
                 for x in (json.loads(o.evidencia) if o and o.evidencia else [])]
    abierta = bd.scalar(select(ComiteReunion).where(ComiteReunion.estado == "abierta").order_by(ComiteReunion.fecha))
    item = bd.scalar(select(ComiteProducto).where(ComiteProducto.idea_id == idea.idea_id)
                     .order_by(ComiteProducto.item_id.desc()))
    reunion = bd.get(ComiteReunion, item.reunion_id) if item else None
    return _breve(
        bd, b, idea, o, gente, BusquedaDetalle,
        color_inicial=b.color, puntaje_inicial=b.puntaje, nota=b.nota,
        descripcion=idea.descripcion, contenido=idea.contenido, forma=idea.forma, precio_visto=idea.precio_visto,
        donde_se_vio=idea.donde_se_vio, fotos=fotos, por_que=o.por_que if o else None, evidencia=evidencia,
        costo=b.costo, motivo_cierre=b.motivo_cierre,
        semaforo=SemaforoBreve(evaluacion_id=e.evaluacion_id, estado=e.estado, color=bq.color_de(e), puntaje=e.puntaje,
                               confianza=e.confianza, modelo=e.modelo, explicacion=e.explicacion) if e else None,
        avances=[AvanceSalida(id=a.avance_id, tipo=a.tipo, texto=a.texto, proveedor=a.proveedor, resultado=a.resultado,
                              resultado_texto=bq.RESULTADOS.get(a.resultado) if a.resultado else None,
                              quien=gente[a.usuario_id].nombre if a.usuario_id in gente else None,
                              creado_en=a.creado_en) for a in reversed(b.avances)],
        reunion_abierta=ReunionBreve(id=abierta.reunion_id, fecha=abierta.fecha, estado=abierta.estado) if abierta else None,
        en_comite=ReunionBreve(id=reunion.reunion_id, fecha=reunion.fecha, estado=reunion.estado,
                               decision=item.decision) if reunion else None,
    )


def _de(bd: Session, busqueda_id: int) -> BusquedaProveedor:
    b = bd.get(BusquedaProveedor, busqueda_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa búsqueda de proveedor.")
    return b


def _abierta(b: BusquedaProveedor) -> None:
    if b.estado not in bq.ABIERTAS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Esta búsqueda ya está cerrada ({bq.ESTADOS[b.estado].lower()}).")


def _tomar(b: BusquedaProveedor, ctx: Contexto) -> None:
    if b.responsable_id == ctx.usuario.usuario_id and b.estado == "buscando":
        return
    texto = f"{ctx.usuario.nombre} la tomó."
    b.estado, b.responsable_id, b.tomada_en = "buscando", ctx.usuario.usuario_id, ahora()
    bq.avance(b, texto, ctx.usuario.usuario_id)


# ---------------------------------------------------------------- rutas

@router.get("", response_model=Bandeja)
def bandeja(vista: Literal["abiertas", "mias", "cerradas", "todas"] = "abiertas",
            ctx: Contexto = Depends(requiere(bq.VER)), bd: Session = Depends(obtener_bd)) -> Bandeja:
    yo = ctx.usuario.usuario_id
    q = select(BusquedaProveedor)
    if vista == "abiertas":
        q = q.where(BusquedaProveedor.estado.in_(bq.ABIERTAS))
    elif vista == "mias":
        q = q.where(BusquedaProveedor.estado.in_(bq.ABIERTAS), BusquedaProveedor.responsable_id == yo)
    elif vista == "cerradas":
        q = q.where(BusquedaProveedor.estado.not_in(bq.ABIERTAS))
    filas = list(bd.scalars(q.order_by(BusquedaProveedor.busqueda_id.desc()).limit(300)))
    ideas = {i.idea_id: i for i in bd.scalars(select(ProductoIdea).where(
        ProductoIdea.idea_id.in_({b.idea_id for b in filas} or {0})))}
    ops = _oportunidades(bd, list(ideas))
    gente = _personas(bd, {b.responsable_id for b in filas if b.responsable_id})
    lista = [_breve(bd, b, ideas[b.idea_id], ops.get(b.idea_id), gente) for b in filas]
    if vista in ("abiertas", "mias"):  # primero las que nadie ha tomado, luego por color y puntaje
        orden = {"verde": 0, "amarillo": 1, "rojo": 2}
        lista.sort(key=lambda x: (x.estado != "sin_tomar", orden.get(x.color or "", 3), -(x.puntaje or 0)))
    contar = lambda *w: int(bd.scalar(select(func.count()).select_from(BusquedaProveedor).where(*w)) or 0)  # noqa: E731
    conteos = {
        "sin_tomar": contar(BusquedaProveedor.estado == "sin_tomar"),
        "buscando": contar(BusquedaProveedor.estado == "buscando"),
        "mias": contar(BusquedaProveedor.estado.in_(bq.ABIERTAS), BusquedaProveedor.responsable_id == yo),
        "cerradas": contar(BusquedaProveedor.estado.not_in(bq.ABIERTAS)),
        "encontrado": contar(BusquedaProveedor.estado == "encontrado"),
    }
    return Bandeja(busquedas=lista, conteos=conteos, colores_automaticos=sorted(bq.colores_automaticos(), reverse=True))


@router.get("/{busqueda_id}", response_model=BusquedaDetalle)
def detalle(busqueda_id: int, _: Contexto = Depends(requiere(bq.VER)), bd: Session = Depends(obtener_bd)) -> BusquedaDetalle:
    return _detalle(bd, _de(bd, busqueda_id))


class NuevaBusqueda(BaseModel):
    idea_id: int
    nota: str | None = Field(None, max_length=1000)


@router.post("", response_model=BusquedaDetalle, status_code=status.HTTP_201_CREATED)
def pedir(datos: NuevaBusqueda, request: Request, ctx: Contexto = Depends(requiere(EVALUAR)),
          bd: Session = Depends(obtener_bd)) -> BusquedaDetalle:
    """Compras pide proveedor a mano para cualquier idea (por ejemplo, una amarilla que le interesa)."""
    idea = bd.get(ProductoIdea, datos.idea_id)
    if not idea:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa idea.")
    if idea.estado == "descartada":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa idea está descartada; cámbiala de estado antes.")
    if idea.proveedor_intelisis or idea.proveedor_nuevo:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Esa idea ya tiene proveedor: {proveedor_de_idea(bd, idea)}.")
    ya = bq.de_idea(bd, idea.idea_id, abiertas=True)
    b = ya or bq.abrir(bd, idea, rp.vigente(bd, idea_id=idea.idea_id), origen="compras",
                       usuario_id=ctx.usuario.usuario_id, nota=_texto(datos.nota))
    if not ya:
        bd.flush()
        _bitacora(bd, "pedir_proveedor", ctx, request, "busqueda_proveedor", b.busqueda_id, {"idea": idea.idea_id})
    bd.commit()
    return _detalle(bd, b)


@router.post("/{busqueda_id}/tomar", response_model=BusquedaDetalle)
def tomar(busqueda_id: int, request: Request, ctx: Contexto = Depends(requiere(bq.ATENDER)),
          bd: Session = Depends(obtener_bd)) -> BusquedaDetalle:
    b = _de(bd, busqueda_id)
    _abierta(b)
    _tomar(b, ctx)
    _bitacora(bd, "tomar_busqueda", ctx, request, "busqueda_proveedor", b.busqueda_id)
    bd.commit()
    return _detalle(bd, b)


class NuevoAvance(BaseModel):
    texto: str = Field(..., max_length=1000)
    proveedor: str | None = Field(None, max_length=200)  # a quién se contactó
    resultado: Literal["sin_respuesta", "interesado", "cotizo", "no_surte"] | None = None


@router.post("/{busqueda_id}/avances", response_model=BusquedaDetalle, status_code=status.HTTP_201_CREATED)
def registrar(busqueda_id: int, datos: NuevoAvance, request: Request, ctx: Contexto = Depends(requiere(bq.ATENDER)),
              bd: Session = Depends(obtener_bd)) -> BusquedaDetalle:
    """Registra a quién se contactó y qué dijo (o una nota). Si nadie la había tomado, la toma quien escribe."""
    b = _de(bd, busqueda_id)
    _abierta(b)
    texto, proveedor = _texto(datos.texto), _texto(datos.proveedor)
    if not texto or len(texto) < 3:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe qué pasó.")
    if datos.resultado and not proveedor:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe a qué proveedor contactaste.")
    if b.estado == "sin_tomar":
        _tomar(b, ctx)
    bq.avance(b, texto, ctx.usuario.usuario_id, "contacto" if proveedor else "nota", proveedor, datos.resultado)
    _bitacora(bd, "avance_busqueda", ctx, request, "busqueda_proveedor", b.busqueda_id,
              {"proveedor": proveedor, "resultado": datos.resultado})
    bd.commit()
    return _detalle(bd, b)


class Encontrado(BaseModel):
    proveedor_codigo: str | None = Field(None, max_length=10)  # de Intelisis
    proveedor_nuevo: str | None = Field(None, max_length=200)
    costo: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)  # sin IVA
    nota: str | None = Field(None, max_length=1000)


@router.post("/{busqueda_id}/encontrado", response_model=BusquedaDetalle)
def encontrado(busqueda_id: int, datos: Encontrado, request: Request, ctx: Contexto = Depends(requiere(bq.ATENDER)),
               bd: Session = Depends(obtener_bd)) -> BusquedaDetalle:
    """Se cierra con proveedor: queda en la idea (con su costo, si lo dio) y la idea se vuelve a evaluar con él."""
    b = _de(bd, busqueda_id)
    _abierta(b)
    codigo, nuevo = _texto(datos.proveedor_codigo), _texto(datos.proveedor_nuevo)
    if bool(codigo) == bool(nuevo):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige un proveedor de Intelisis o escribe uno nuevo (uno de los dos).")
    if codigo:
        prov = bd.get(Proveedor, codigo)
        if not prov or not (prov.agente or "").strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ese proveedor no está en Intelisis con agente.")
    if nuevo is not None and len(nuevo) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe el nombre del proveedor nuevo.")
    idea = bd.get(ProductoIdea, b.idea_id)
    if b.estado == "sin_tomar":
        _tomar(b, ctx)
    idea.proveedor_intelisis, idea.proveedor_nuevo = codigo, nuevo
    if datos.costo is not None:
        idea.costo_estimado = datos.costo
    idea.estado, idea.actualizada_en = "nueva", ahora()
    nombre = proveedor_de_idea(bd, idea)
    b.estado, b.proveedor_intelisis, b.proveedor_nuevo, b.costo = "encontrado", codigo, nuevo, datos.costo
    b.cerrada_por, b.cerrada_en, b.motivo_cierre = ctx.usuario.usuario_id, ahora(), _texto(datos.nota)
    bq.avance(b, f"Proveedor encontrado: {nombre} ({bq.costo_texto(datos.costo)})."
              + (f" {b.motivo_cierre.rstrip('.')}." if b.motivo_cierre else "") + " Se vuelve a evaluar con él.",
              ctx.usuario.usuario_id, proveedor=nombre)
    bq.avisar_encontrado(bd, b, idea, nombre, ctx.usuario.usuario_id)
    _bitacora(bd, "proveedor_encontrado", ctx, request, "busqueda_proveedor", b.busqueda_id,
              {"idea": idea.idea_id, "intelisis": codigo, "nuevo": nuevo, "costo": str(datos.costo) if datos.costo else None})
    bd.commit()
    e = rp.iniciar(bd, idea_id=idea.idea_id, usuario_id=ctx.usuario.usuario_id)
    rp.en_hilo(e.evaluacion_id)
    bd.expire_all()  # la evaluación corre en otra sesión
    return _detalle(bd, b)


class Cierre(BaseModel):
    estado: Literal["sin_proveedor", "cancelada"]
    motivo: str = Field(..., max_length=1000)


@router.post("/{busqueda_id}/cerrar", response_model=BusquedaDetalle)
def cerrar(busqueda_id: int, datos: Cierre, request: Request, ctx: Contexto = Depends(requiere(bq.ATENDER)),
           bd: Session = Depends(obtener_bd)) -> BusquedaDetalle:
    """Sin proveedor (se buscó y no hubo) o cancelada (ya no interesa); el motivo es obligatorio."""
    b = _de(bd, busqueda_id)
    _abierta(b)
    motivo = _texto(datos.motivo)
    if not motivo or len(motivo) < 10:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe el motivo (al menos 10 letras).")
    b.estado, b.motivo_cierre, b.cerrada_por, b.cerrada_en = datos.estado, motivo, ctx.usuario.usuario_id, ahora()
    bq.avance(b, f"{'Se cerró sin proveedor' if datos.estado == 'sin_proveedor' else 'Se canceló'}: {motivo}",
              ctx.usuario.usuario_id)
    idea = bd.get(ProductoIdea, b.idea_id)
    if idea.estado == "buscar_proveedor":
        idea.estado, idea.actualizada_en = "vigilar" if datos.estado == "sin_proveedor" else "nueva", ahora()
    _bitacora(bd, "cerrar_busqueda", ctx, request, "busqueda_proveedor", b.busqueda_id,
              {"estado": datos.estado, "motivo": motivo})
    bd.commit()
    return _detalle(bd, b)


@router.post("/{busqueda_id}/reabrir", response_model=BusquedaDetalle)
def reabrir(busqueda_id: int, request: Request, ctx: Contexto = Depends(requiere(bq.ATENDER)),
            bd: Session = Depends(obtener_bd)) -> BusquedaDetalle:
    """Una búsqueda sin proveedor o cancelada se puede retomar (por ejemplo, apareció un proveedor nuevo)."""
    b = _de(bd, busqueda_id)
    if b.estado not in ("sin_proveedor", "cancelada"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se reabre una búsqueda sin proveedor o cancelada.")
    idea = bd.get(ProductoIdea, b.idea_id)
    if idea.estado == "descartada":
        raise HTTPException(status.HTTP_409_CONFLICT, "La idea está descartada en el radar de productos.")
    if idea.proveedor_intelisis or idea.proveedor_nuevo:
        raise HTTPException(status.HTTP_409_CONFLICT, f"La idea ya tiene proveedor: {proveedor_de_idea(bd, idea)}.")
    if bq.de_idea(bd, idea.idea_id, abiertas=True):
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa idea ya tiene otra búsqueda abierta.")
    b.estado, b.responsable_id, b.tomada_en = "buscando", ctx.usuario.usuario_id, ahora()
    b.cerrada_por = b.cerrada_en = b.motivo_cierre = None
    bq.avance(b, f"{ctx.usuario.nombre} la reabrió.", ctx.usuario.usuario_id)
    idea.estado, idea.actualizada_en = "buscar_proveedor", ahora()
    _bitacora(bd, "reabrir_busqueda", ctx, request, "busqueda_proveedor", b.busqueda_id)
    bd.commit()
    return _detalle(bd, b)


@router.get("/idea/{idea_id}", response_model=BusquedaBreve | None)
def de_idea(idea_id: int, _: Contexto = Depends(requiere(bq.VER)), bd: Session = Depends(obtener_bd)) -> BusquedaBreve | None:
    """La búsqueda más reciente de una idea, para mostrarla en el detalle del radar de productos."""
    b = bq.de_idea(bd, idea_id)
    if not b:
        return None
    idea = bd.get(ProductoIdea, idea_id)
    return _breve(bd, b, idea, _oportunidades(bd, [idea_id]).get(idea_id),
                  _personas(bd, {b.responsable_id} if b.responsable_id else set()))
