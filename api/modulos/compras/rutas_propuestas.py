"""Propuestas de productos nuevos (/api/compras/propuestas y /api/compras/proveedores).

El proveedor llena el cuestionario de Compras desde su portal: guarda borradores con sus archivos, envía y recibe un
folio. Compras recibe cada propuesta en su bandeja, la revisa y la marca lista para evaluar (entrada del radar de
productos), la regresa al proveedor con un comentario o la rechaza. Reglas del cuestionario en propuestas.py.
"""
import json
import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, ip_de, requiere, usuario_actual
from datos.modelos import Producto, Proveedor as ProveedorIntelisis
from modulos.compras import propuestas as pr
from modulos.compras import radar_productos
from modulos.compras.modelos_propuestas import Propuesta, PropuestaAdjunto, PropuestaEvento
from nucleo.administracion import DIAS_INVITACION, _correo_invitacion, _crear_invitacion
from nucleo.archivos import _raiz
from nucleo.bitacora import registrar
from nucleo.modelos import (
    Archivo, Modulo, OrganizacionExterna, Permiso, Rol, RolPermiso, Usuario, UsuarioRol, ahora,
)
from nucleo.notificaciones import correo, notificar

router = APIRouter(prefix="/api/compras", tags=["compras · propuestas de productos nuevos"])
ENVIAR = "compras.solicitud.enviar"
VER = "compras.propuestas.ver"
REVISAR = "compras.propuestas.revisar"
INVITAR = "compras.proveedores.invitar"


def _modulo_id(bd: Session) -> int | None:
    return bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "compras"))


def _bitacora(bd: Session, accion: str, ctx: Contexto, request: Request, entidad_id, detalle: dict | None = None) -> None:
    registrar(bd, accion, usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd), entidad="propuesta",
              entidad_id=entidad_id, detalle=detalle, ip=ip_de(request))


def _es_proveedor(ctx: Contexto) -> bool:
    return ctx.usuario.tipo == "externo" and ctx.puede(ENVIAR) and ctx.usuario.organizacion_id is not None


def _proveedor(ctx: Contexto = Depends(usuario_actual)) -> Contexto:
    if not _es_proveedor(ctx):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo los proveedores invitados pueden proponer productos.")
    return ctx


def _captura_compras(ctx: Contexto) -> bool:
    return ctx.usuario.tipo == "interno" and ctx.puede(REVISAR)


def _autor(ctx: Contexto = Depends(usuario_actual)) -> Contexto:
    """Quien llena el formulario: el proveedor invitado o Compras cuando captura por el proveedor."""
    if not (_es_proveedor(ctx) or _captura_compras(ctx)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo los proveedores invitados o Compras pueden capturar productos.")
    return ctx


def de_compras(bd: Session, p: Propuesta) -> bool:
    """La capturó Compras por el proveedor (quien la creó es de SMN)."""
    u = bd.get(Usuario, p.creada_por)
    return bool(u and u.tipo == "interno")


def _propuesta(bd: Session, propuesta_id: int, ctx: Contexto) -> Propuesta:
    """La propuesta si quien pregunta la puede ver: el proveedor solo las de su empresa; Compras las enviadas y los
    borradores que capturó Compras."""
    p = bd.get(Propuesta, propuesta_id)
    if p and _es_proveedor(ctx) and p.organizacion_id == ctx.usuario.organizacion_id:
        return p
    if p and ctx.usuario.tipo == "interno" and ctx.puede(VER) and (p.folio or de_compras(bd, p)):
        return p
    raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa propuesta.")


def _para_editar(bd: Session, propuesta_id: int, ctx: Contexto) -> Propuesta:
    """Compras solo edita las que capturó; las del portal las corrige el proveedor."""
    p = _propuesta(bd, propuesta_id, ctx)
    if ctx.usuario.tipo == "interno" and not de_compras(bd, p):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta propuesta la capturó el proveedor: regrésala para que la corrija.")
    _editable(p)
    return p


def _respuestas(p: Propuesta) -> pr.Respuestas:
    return pr.Respuestas.model_validate(json.loads(p.respuestas or "{}"))


def _editable(p: Propuesta) -> None:
    if p.estado not in pr.EDITABLES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta propuesta ya se envió; Compras te avisará si necesita cambios.")


def _evento(bd: Session, p: Propuesta, antes: str | None, despues: str, usuario_id: int, comentario: str | None = None) -> None:
    bd.add(PropuestaEvento(propuesta_id=p.propuesta_id, estado_antes=antes, estado_despues=despues,
                           comentario=comentario, usuario_id=usuario_id))


def _revisores(bd: Session) -> list[int]:
    """Internos activos que pueden revisar propuestas: a ellos les llega el aviso de una nueva."""
    return list(bd.scalars(
        select(Usuario.usuario_id).distinct()
        .join(UsuarioRol, UsuarioRol.usuario_id == Usuario.usuario_id)
        .join(RolPermiso, RolPermiso.rol_id == UsuarioRol.rol_id)
        .join(Permiso, Permiso.permiso_id == RolPermiso.permiso_id)
        .where(Permiso.codigo == REVISAR, Usuario.tipo == "interno", Usuario.estatus == "activo")))


# ---------------------------------------------------------------- salidas

class AdjuntoSalida(BaseModel):
    id: int
    tipo: str
    etiqueta: str | None
    nombre: str
    tipo_contenido: str
    tamano_bytes: int


class FaltaSalida(BaseModel):
    seccion: str
    campo: str
    mensaje: str


class RevisionSalida(BaseModel):
    nivel: str
    texto: str


class EventoSalida(BaseModel):
    estado_antes: str | None
    estado_despues: str
    comentario: str | None
    usuario: str
    ocurrido_en: datetime


class PresentacionSalida(BaseModel):
    orden: int
    codigo_barras: str | None
    descripcion: str | None
    margen_calculado: float | None
    ya_en_catalogo: bool


class PropuestaBreve(BaseModel):
    id: int
    folio: str | None
    estado: str
    estado_texto: str
    producto: str | None
    marca: str | None
    departamento: str | None
    empresa: str
    presentaciones: int
    alertas: int
    enviada_en: datetime | None
    actualizada_en: datetime
    capturada_por_compras: bool = False


class PropuestaSalida(PropuestaBreve):
    editable: bool
    comentario: str | None
    respuestas: dict
    adjuntos: list[AdjuntoSalida]
    faltantes: list[FaltaSalida]
    revisiones: list[RevisionSalida]
    eventos: list[EventoSalida]
    filas: list[PresentacionSalida]
    creada_por: str


def _breve(bd: Session, p: Propuesta, empresas: dict[int, str] | None = None) -> PropuestaBreve:
    empresa = (empresas or {}).get(p.organizacion_id) or bd.get(OrganizacionExterna, p.organizacion_id).nombre
    return PropuestaBreve(id=p.propuesta_id, folio=p.folio, estado=p.estado, estado_texto=pr.ESTADOS[p.estado],
                          producto=p.producto, marca=p.marca, departamento=p.departamento, empresa=empresa,
                          presentaciones=p.presentaciones, alertas=p.alertas, enviada_en=p.enviada_en,
                          actualizada_en=p.actualizada_en, capturada_por_compras=de_compras(bd, p))


def _salida(bd: Session, p: Propuesta, ctx: Contexto) -> PropuestaSalida:
    r = _respuestas(p)
    archivos = {a.archivo_id: a for a in bd.scalars(select(Archivo).where(
        Archivo.archivo_id.in_([x.archivo_id for x in p.adjuntos] or [0])))}
    nombres = dict(bd.execute(select(Usuario.usuario_id, Usuario.nombre).where(Usuario.usuario_id.in_(
        {e.usuario_id for e in bd.scalars(select(PropuestaEvento).where(PropuestaEvento.propuesta_id == p.propuesta_id))}
        | {p.creada_por}))).all())
    interno = ctx.usuario.tipo == "interno"
    captura = de_compras(bd, p)
    eventos = bd.scalars(select(PropuestaEvento).where(PropuestaEvento.propuesta_id == p.propuesta_id)
                         .order_by(PropuestaEvento.evento_id)).all()
    revisiones = [RevisionSalida(**x) for x in json.loads(p.revisiones)] if interno and p.revisiones else []
    return PropuestaSalida(
        **_breve(bd, p).model_dump(),
        editable=p.estado in pr.EDITABLES and (not interno or captura),
        comentario=p.comentario,
        respuestas=r.model_dump(),
        adjuntos=[AdjuntoSalida(id=a.adjunto_id, tipo=a.tipo, etiqueta=a.etiqueta, nombre=archivos[a.archivo_id].nombre_original,
                                tipo_contenido=archivos[a.archivo_id].tipo_contenido,
                                tamano_bytes=archivos[a.archivo_id].tamano_bytes) for a in p.adjuntos],
        faltantes=[FaltaSalida(**vars(f)) for f in pr.faltantes(r, pr.adjuntos_de(p), compras=captura)],
        revisiones=revisiones,
        # El proveedor ve quién de su lado hizo cada cosa; de Compras solo «Compras SMN»
        eventos=[EventoSalida(estado_antes=e.estado_antes, estado_despues=e.estado_despues, comentario=e.comentario,
                              usuario=nombres.get(e.usuario_id, "") if interno or e.estado_despues == "recibida" else "Compras SMN",
                              ocurrido_en=e.ocurrido_en) for e in eventos],
        filas=[PresentacionSalida(orden=f.orden, codigo_barras=f.codigo_barras, descripcion=f.descripcion,
                                  margen_calculado=float(f.margen_calculado) if f.margen_calculado is not None else None,
                                  ya_en_catalogo=f.ya_en_catalogo) for f in p.filas_presentacion] if interno else [],
        creada_por=nombres.get(p.creada_por, ""),
    )


# ---------------------------------------------------------------- catálogos del formulario

class Opcion(BaseModel):
    valor: str
    texto: str


class ReglaAdjunto(BaseModel):
    seccion: str
    tipos: list[str]
    mb: int
    minimo: int
    maximo: int


class Catalogos(BaseModel):
    opciones: dict[str, list[Opcion]]
    secciones: list[Opcion]
    estados: list[Opcion]
    adjuntos: dict[str, ReglaAdjunto]
    departamentos: list[str]


@router.get("/propuestas/catalogos", response_model=Catalogos)
def catalogos(ctx: Contexto = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> Catalogos:
    if not (_es_proveedor(ctx) or ctx.puede(VER)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para esta acción.")
    departamentos = bd.scalars(select(Producto.departamento).distinct()
                               .where(Producto.departamento.is_not(None), Producto.activo).order_by(Producto.departamento))
    return Catalogos(
        opciones={k: [Opcion(valor=v, texto=t) for v, t in lista] for k, lista in pr.OPCIONES.items()},
        secciones=[Opcion(valor=v, texto=t) for v, t in pr.SECCIONES],
        estados=[Opcion(valor=v, texto=t) for v, t in pr.ESTADOS.items()],
        adjuntos={k: ReglaAdjunto(seccion=s, tipos=sorted(t), mb=mb, minimo=mi, maximo=ma)
                  for k, (s, t, mb, mi, ma) in pr.ADJUNTOS.items()},
        departamentos=[d for d in departamentos if d.strip()],
    )


# ---------------------------------------------------------------- portal del proveedor

@router.get("/propuestas/mias", response_model=list[PropuestaBreve])
def mias(ctx: Contexto = Depends(_proveedor), bd: Session = Depends(obtener_bd)) -> list[PropuestaBreve]:
    filas = bd.scalars(select(Propuesta).where(Propuesta.organizacion_id == ctx.usuario.organizacion_id)
                       .order_by(Propuesta.actualizada_en.desc())).all()
    empresa = {ctx.usuario.organizacion_id: ctx.usuario.organizacion.nombre}
    return [_breve(bd, p, empresa) for p in filas]


def _nueva(bd: Session, ctx: Contexto, r: pr.Respuestas, adjuntos: list[PropuestaAdjunto],
           organizacion_id: int | None = None) -> Propuesta:
    marca, producto = pr.resumen_producto(r)
    p = Propuesta(organizacion_id=organizacion_id or ctx.usuario.organizacion_id, creada_por=ctx.usuario.usuario_id, estado="borrador",
                  marca=marca, producto=producto, departamento=pr.limpio(r.general.departamento) or None,
                  presentaciones=len(r.presentaciones), respuestas=r.model_dump_json(), alertas=0)
    bd.add(p)
    bd.flush()
    for a in adjuntos:
        bd.add(PropuestaAdjunto(propuesta_id=p.propuesta_id, archivo_id=a.archivo_id, tipo=a.tipo, etiqueta=a.etiqueta))
    return p


@router.post("/propuestas", response_model=PropuestaSalida, status_code=status.HTTP_201_CREATED)
def crear(request: Request, ctx: Contexto = Depends(_proveedor), bd: Session = Depends(obtener_bd)) -> PropuestaSalida:
    """Borrador nuevo. Los datos del proveedor y los documentos de la empresa salen de su última propuesta;
    si es la primera, de la invitación."""
    ultima = bd.scalar(select(Propuesta).where(Propuesta.organizacion_id == ctx.usuario.organizacion_id)
                       .order_by(Propuesta.propuesta_id.desc()))
    r = pr.Respuestas()
    adjuntos: list[PropuestaAdjunto] = []
    if ultima:
        r.proveedor = _respuestas(ultima).proveedor
        adjuntos = [a for a in ultima.adjuntos if pr.adjunto_de_empresa(a)]
    else:
        org = ctx.usuario.organizacion
        r.proveedor = pr.DatosProveedor(razon_social=org.nombre, rfc=org.rfc, contacto_nombre=ctx.usuario.nombre,
                                        contacto_cargo=ctx.usuario.puesto, contacto_correo=ctx.usuario.correo)
    p = _nueva(bd, ctx, r, adjuntos)
    _bitacora(bd, "crear", ctx, request, p.propuesta_id)
    bd.commit()
    bd.refresh(p)
    return _salida(bd, p, ctx)


@router.post("/propuestas/{propuesta_id}/duplicar", response_model=PropuestaSalida, status_code=status.HTTP_201_CREATED)
def duplicar(propuesta_id: int, request: Request, ctx: Contexto = Depends(_autor),
             bd: Session = Depends(obtener_bd)) -> PropuestaSalida:
    """Copia todo lo capturado para cargar rápido otro sabor o línea. Las fotos y la ficha técnica no se copian
    porque son de otro producto; los documentos de la empresa sí."""
    origen = _propuesta(bd, propuesta_id, ctx)
    if ctx.usuario.tipo == "interno" and not de_compras(bd, origen):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo se duplican las propuestas que capturó Compras.")
    r = _respuestas(origen)
    r.aviso = pr.Aviso()
    p = _nueva(bd, ctx, r, [a for a in origen.adjuntos if pr.adjunto_de_empresa(a)], origen.organizacion_id)
    _bitacora(bd, "duplicar", ctx, request, p.propuesta_id, {"de": origen.folio or origen.propuesta_id})
    bd.commit()
    bd.refresh(p)
    return _salida(bd, p, ctx)


@router.get("/propuestas/{propuesta_id}", response_model=PropuestaSalida)
def ver(propuesta_id: int, ctx: Contexto = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> PropuestaSalida:
    return _salida(bd, _propuesta(bd, propuesta_id, ctx), ctx)


class Guardar(BaseModel):
    respuestas: pr.Respuestas


@router.put("/propuestas/{propuesta_id}", response_model=PropuestaSalida)
def guardar(propuesta_id: int, datos: Guardar, ctx: Contexto = Depends(_autor),
            bd: Session = Depends(obtener_bd)) -> PropuestaSalida:
    """Guardado automático mientras el proveedor escribe. No revisa nada: lo que falta se ve en `faltantes`."""
    p = _para_editar(bd, propuesta_id, ctx)
    r = datos.respuestas
    if not r.presentaciones:
        r.presentaciones = [pr.Presentacion()]
    p.respuestas = r.model_dump_json()
    p.marca, p.producto = pr.resumen_producto(r)
    p.departamento = pr.limpio(r.general.departamento)[:300] or None
    p.presentaciones = len(r.presentaciones)
    p.actualizada_en = ahora()
    bd.commit()
    return _salida(bd, p, ctx)


@router.delete("/propuestas/{propuesta_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar(propuesta_id: int, request: Request, ctx: Contexto = Depends(_autor), bd: Session = Depends(obtener_bd)) -> None:
    p = _propuesta(bd, propuesta_id, ctx)
    if ctx.usuario.tipo == "interno" and not de_compras(bd, p):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta propuesta la capturó el proveedor.")
    if p.folio:
        raise HTTPException(status.HTTP_409_CONFLICT, "Una propuesta enviada no se borra.")
    _bitacora(bd, "borrar", ctx, request, p.propuesta_id)
    bd.delete(p)
    bd.commit()


class NuevoAdjunto(BaseModel):
    archivo_id: int
    tipo: str = Field(max_length=40)
    etiqueta: str | None = Field(default=None, max_length=40)


def _etiqueta_valida(tipo: str, etiqueta: str | None) -> str | None:
    catalogo = {"imagen_producto": "etiqueta_producto", "imagen_etiquetado": "etiqueta_etiquetado"}.get(tipo)
    if not catalogo:
        return None
    validas = [v for v, _ in pr.OPCIONES[catalogo]]
    if etiqueta and etiqueta not in validas:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esa etiqueta no existe.")
    return etiqueta or validas[-1]


@router.post("/propuestas/{propuesta_id}/adjuntos", response_model=PropuestaSalida, status_code=status.HTTP_201_CREATED)
def agregar_adjunto(propuesta_id: int, datos: NuevoAdjunto, ctx: Contexto = Depends(_autor),
                    bd: Session = Depends(obtener_bd)) -> PropuestaSalida:
    """Liga a la propuesta un archivo ya subido con /api/archivos por la misma persona."""
    p = _para_editar(bd, propuesta_id, ctx)
    archivo = bd.get(Archivo, datos.archivo_id)
    if not archivo or archivo.subido_por != ctx.usuario.usuario_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese archivo.")
    if motivo := pr.adjunto_aceptado(datos.tipo, archivo):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, motivo)
    mismos = [a for a in p.adjuntos if a.tipo == datos.tipo]
    if pr.maximo_adjuntos(datos.tipo) == 1:  # documento único: el nuevo reemplaza al anterior
        for a in mismos:
            p.adjuntos.remove(a)
    elif len(mismos) >= pr.maximo_adjuntos(datos.tipo):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Máximo {pr.maximo_adjuntos(datos.tipo)} archivos de este tipo.")
    p.adjuntos.append(PropuestaAdjunto(archivo_id=archivo.archivo_id, tipo=datos.tipo,
                                       etiqueta=_etiqueta_valida(datos.tipo, datos.etiqueta)))
    p.actualizada_en = ahora()
    bd.commit()
    bd.refresh(p)
    return _salida(bd, p, ctx)


class CambioAdjunto(BaseModel):
    etiqueta: str = Field(max_length=40)


@router.patch("/propuestas/{propuesta_id}/adjuntos/{adjunto_id}", response_model=PropuestaSalida)
def etiquetar_adjunto(propuesta_id: int, adjunto_id: int, datos: CambioAdjunto, ctx: Contexto = Depends(_autor),
                      bd: Session = Depends(obtener_bd)) -> PropuestaSalida:
    p = _para_editar(bd, propuesta_id, ctx)
    a = next((x for x in p.adjuntos if x.adjunto_id == adjunto_id), None)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese archivo en la propuesta.")
    a.etiqueta = _etiqueta_valida(a.tipo, datos.etiqueta)
    bd.commit()
    return _salida(bd, p, ctx)


@router.delete("/propuestas/{propuesta_id}/adjuntos/{adjunto_id}", response_model=PropuestaSalida)
def quitar_adjunto(propuesta_id: int, adjunto_id: int, ctx: Contexto = Depends(_autor),
                   bd: Session = Depends(obtener_bd)) -> PropuestaSalida:
    p = _para_editar(bd, propuesta_id, ctx)
    a = next((x for x in p.adjuntos if x.adjunto_id == adjunto_id), None)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese archivo en la propuesta.")
    p.adjuntos.remove(a)
    bd.commit()
    bd.refresh(p)
    return _salida(bd, p, ctx)


@router.get("/propuestas/{propuesta_id}/adjuntos/{adjunto_id}")
def descargar_adjunto(propuesta_id: int, adjunto_id: int, ctx: Contexto = Depends(usuario_actual),
                      bd: Session = Depends(obtener_bd)) -> FileResponse:
    p = _propuesta(bd, propuesta_id, ctx)
    a = next((x for x in p.adjuntos if x.adjunto_id == adjunto_id), None)
    archivo = bd.get(Archivo, a.archivo_id) if a else None
    raiz = _raiz()
    ruta = (raiz / archivo.ruta_almacenamiento).resolve() if archivo else None
    if not ruta or raiz not in ruta.parents or not ruta.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese archivo.")
    return FileResponse(ruta, media_type=archivo.tipo_contenido, filename=archivo.nombre_original,
                        content_disposition_type="inline", headers={"X-Content-Type-Options": "nosniff"})


@router.post("/propuestas/{propuesta_id}/enviar", response_model=PropuestaSalida)
def enviar(propuesta_id: int, request: Request, ctx: Contexto = Depends(_autor),
           bd: Session = Depends(obtener_bd)) -> PropuestaSalida:
    p = _para_editar(bd, propuesta_id, ctx)
    compras = de_compras(bd, p)
    r = pr.normalizar(_respuestas(p))
    if faltan := pr.faltantes(r, pr.adjuntos_de(p), compras=compras):
        secciones = dict(pr.SECCIONES)
        nombres = list(dict.fromkeys(secciones[f.seccion] for f in faltan))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Faltan datos en: {', '.join(nombres)}.")
    antes, reenvio = p.estado, p.folio is not None
    if not p.folio:
        p.folio = pr.nuevo_folio(bd, ahora().year)
    p.respuestas = r.model_dump_json()  # se guarda ya normalizado
    p.marca, p.producto = pr.resumen_producto(r)
    p.estado, p.enviada_en, p.actualizada_en = "recibida", ahora(), ahora()
    p.filas_presentacion.clear()  # al reenviar se reemplazan: primero se borran las anteriores
    bd.flush()
    p.filas_presentacion.extend(pr.filas_presentacion(bd, r))
    bd.flush()
    revisiones = pr.revisar(bd, p, r)
    p.revisiones = json.dumps([vars(x) for x in revisiones], ensure_ascii=False)
    p.alertas = sum(x.nivel == "alerta" for x in revisiones)
    _evento(bd, p, antes, "recibida", ctx.usuario.usuario_id, "Se volvió a enviar con cambios." if reenvio else None)
    _bitacora(bd, "reenviar" if reenvio else "enviar", ctx, request, p.propuesta_id, {"folio": p.folio})
    empresa = bd.get(OrganizacionExterna, p.organizacion_id).nombre
    for uid in _revisores(bd):
        if uid == ctx.usuario.usuario_id:
            continue
        notificar(bd, uid, "Propuesta corregida" if reenvio else "Propuesta de producto nuevo",
                  f"{empresa} {'corrigió' if reenvio else 'envió'} {p.folio}: {p.producto or 'producto nuevo'}"
                  + (f" (capturada por {ctx.usuario.nombre} de Compras)." if compras else "."),
                  liga=f"/compras/propuestas/{p.propuesta_id}", modulo_id=_modulo_id(bd))
    bd.commit()
    from modulos.compras.rutas_comite import al_enviar_propuesta

    try:  # entra al ciclo del comité que esté recibiendo productos; si falla, el envío ya quedó guardado
        al_enviar_propuesta(bd, p, ctx, request, compras)
    except Exception:  # noqa: BLE001
        bd.rollback()
        logging.getLogger(__name__).exception("No se pudo sumar la propuesta %s al comité", p.propuesta_id)
    if compras:  # la capturó Compras: no hay a quién mandarle el acuse
        return _salida(bd, p, ctx)
    correo(bd, ctx.usuario.usuario_id, ctx.usuario.correo, f"Recibimos tu propuesta {p.folio}", f"Hola, {ctx.usuario.nombre}",
           [f"Súper Naturista recibió tu propuesta {p.folio}: {p.producto or 'producto nuevo'}.",
            "Compras la revisará y te avisaremos por este medio y en el portal cuando cambie de estado."],
           nota="Guarda el folio para cualquier aclaración.")
    bd.commit()
    return _salida(bd, p, ctx)


# ---------------------------------------------------------------- bandeja de Compras

class Bandeja(BaseModel):
    propuestas: list[PropuestaBreve]
    por_estado: dict[str, int]


@router.get("/propuestas", response_model=Bandeja)
def bandeja(estado: str | None = None, q: str | None = Query(None, max_length=100), departamento: str | None = None,
            ctx: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> Bandeja:
    """Lo que ya envió algún proveedor (los borradores no se ven), más los borradores que está capturando Compras
    (estado «borrador»)."""
    internos = select(Usuario.usuario_id).where(Usuario.tipo == "interno")
    visibles = or_(Propuesta.folio.is_not(None), Propuesta.creada_por.in_(internos))
    base = select(Propuesta).where(visibles)
    por_estado = dict(bd.execute(select(Propuesta.estado, func.count()).where(visibles)
                                 .group_by(Propuesta.estado)).all())
    if estado:
        base = base.where(Propuesta.estado == estado)
    else:
        base = base.where(Propuesta.estado != "borrador")  # los borradores solo con su filtro
    if departamento:
        base = base.where(Propuesta.departamento == departamento)
    if q and q.strip():
        t = f"%{q.strip()}%"
        base = base.join(OrganizacionExterna, OrganizacionExterna.organizacion_id == Propuesta.organizacion_id).where(
            or_(Propuesta.folio.like(t), Propuesta.producto.like(t), OrganizacionExterna.nombre.like(t)))
    filas = bd.scalars(base.order_by(Propuesta.enviada_en.desc(), Propuesta.actualizada_en.desc()).limit(500)).all()
    empresas = dict(bd.execute(select(OrganizacionExterna.organizacion_id, OrganizacionExterna.nombre).where(
        OrganizacionExterna.organizacion_id.in_({p.organizacion_id for p in filas} or {0}))).all())
    return Bandeja(propuestas=[_breve(bd, p, empresas) for p in filas], por_estado=por_estado)


class CambioEstado(BaseModel):
    estado: Literal["en_revision", "devuelta", "lista", "rechazada"]
    comentario: str | None = Field(default=None, max_length=1000)


@router.post("/propuestas/{propuesta_id}/estado", response_model=PropuestaSalida)
def cambiar_estado(propuesta_id: int, datos: CambioEstado, request: Request, ctx: Contexto = Depends(requiere(REVISAR)),
                   bd: Session = Depends(obtener_bd)) -> PropuestaSalida:
    p = _propuesta(bd, propuesta_id, ctx)
    if datos.estado not in pr.TRANSICIONES.get(p.estado, set()):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Una propuesta {pr.ESTADOS[p.estado].lower()} no puede pasar a «{pr.ESTADOS[datos.estado]}».")
    comentario = pr.limpio(datos.comentario) or None
    if datos.estado in {"devuelta", "rechazada"} and not comentario:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe el motivo para el proveedor.")
    antes = p.estado
    p.estado = datos.estado
    if comentario:
        p.comentario = comentario
    p.actualizada_en = ahora()
    _evento(bd, p, antes, datos.estado, ctx.usuario.usuario_id, comentario)
    _bitacora(bd, "cambiar_estado", ctx, request, p.propuesta_id, {"folio": p.folio, "antes": antes, "despues": datos.estado})
    avisos = {
        "en_revision": ("Tu propuesta está en revisión", f"Compras está revisando {p.folio}."),
        "devuelta": ("Tu propuesta necesita cambios", f"Compras regresó {p.folio} con este comentario: {comentario}"),
        "lista": ("Tu propuesta pasó a evaluación", f"{p.folio} quedó completa y pasa a evaluación de Compras."),
        "rechazada": ("Tu propuesta no fue aceptada", f"Compras no aceptó {p.folio}. Motivo: {comentario}"),
    }
    titulo, mensaje = avisos[datos.estado]
    bd.commit()
    if not de_compras(bd, p):  # si la capturó Compras no hay proveedor en el portal a quién avisar
        notificar(bd, p.creada_por, titulo, mensaje, liga=f"/proveedores/propuesta/{p.propuesta_id}", modulo_id=_modulo_id(bd))
        bd.commit()
        if datos.estado != "en_revision":
            autor = bd.get(Usuario, p.creada_por)
            correo(bd, autor.usuario_id, autor.correo, f"{titulo} ({p.folio})", f"Hola, {autor.nombre}", [mensaje],
                   nota="Entra al portal de proveedores de Súper Naturista para ver el detalle." if datos.estado == "devuelta" else None)
            bd.commit()
    if datos.estado == "lista":  # el radar de productos la evalúa solo (Diego, 2026-10-26)
        e = radar_productos.iniciar(bd, propuesta_id=p.propuesta_id, usuario_id=ctx.usuario.usuario_id)
        radar_productos.en_hilo(e.evaluacion_id)
    return _salida(bd, p, ctx)


class CambioDepartamento(BaseModel):
    departamento: str = Field(min_length=1, max_length=300)


@router.patch("/propuestas/{propuesta_id}/departamento", response_model=PropuestaSalida)
def corregir_departamento(propuesta_id: int, datos: CambioDepartamento, request: Request,
                          ctx: Contexto = Depends(requiere(REVISAR)), bd: Session = Depends(obtener_bd)) -> PropuestaSalida:
    """Compras confirma o corrige el departamento que eligió el proveedor."""
    p = _propuesta(bd, propuesta_id, ctx)
    antes, p.departamento = p.departamento, datos.departamento.strip()
    _bitacora(bd, "corregir_departamento", ctx, request, p.propuesta_id, {"antes": antes, "despues": p.departamento})
    bd.commit()
    return _salida(bd, p, ctx)


# ---------------------------------------------------------------- proveedores invitados

class ProveedorSalida(BaseModel):
    id: int
    nombre: str
    correo: str
    empresa: str | None
    rfc: str | None
    estatus: str
    propuestas: int
    ultimo_acceso_en: datetime | None
    creado_en: datetime


class ProveedorIntelisisSalida(BaseModel):
    codigo: str
    nombre: str
    estatus: str | None
    agente: str | None = None
    rfc: str | None = None


def _busca_proveedores(ctx: Contexto = Depends(usuario_actual)) -> Contexto:
    """Buscan proveedores quienes capturan productos: en Propuestas, en el radar (captura corta) o en el comité."""
    if not any(ctx.puede(p) for p in (REVISAR, "compras.productos.evaluar", "compras.comite.subir")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para esta acción.")
    return ctx


@router.get("/proveedores/intelisis", response_model=list[ProveedorIntelisisSalida])
def buscar_proveedor_intelisis(q: str = Query("", max_length=100), _: Contexto = Depends(_busca_proveedores),
                               bd: Session = Depends(obtener_bd)) -> list[ProveedorIntelisisSalida]:
    """Proveedores que ya tenemos en Intelisis (tblProveedores cargada en Centro de datos), por clave, nombre o RFC.
    Solo los que tienen agente (Diego, 2026-11-03)."""
    consulta = select(ProveedorIntelisis).where(func.ltrim(func.coalesce(ProveedorIntelisis.agente, "")) != "")
    if t := q.strip():
        consulta = consulta.where(or_(ProveedorIntelisis.proveedor.like(f"{t}%"), ProveedorIntelisis.nombre.like(f"%{t}%"),
                                      ProveedorIntelisis.rfc.like(f"{t.upper()}%")))
    sin_nombre = case((func.ltrim(func.coalesce(ProveedorIntelisis.nombre, "")) == "", 1), else_=0)
    filas = bd.scalars(consulta.order_by(sin_nombre, ProveedorIntelisis.estatus, ProveedorIntelisis.nombre)
                       .limit(25)).all()  # los que vienen sin nombre en Intelisis, al final
    # En tblProveedores hay claves sin nombre: se muestran con su clave para no romper la lista
    return [ProveedorIntelisisSalida(codigo=p.proveedor, nombre=(p.nombre or "").strip() or f"Proveedor {p.proveedor}",
                                     estatus=p.estatus, agente=p.agente, rfc=p.rfc) for p in filas]


class NuevaCaptura(BaseModel):
    """Proveedor actual (su clave de Intelisis) o nuevo (razón social y, si se tiene, RFC). Sin contactos."""
    proveedor_codigo: str | None = Field(default=None, max_length=10)
    nombre: str | None = Field(default=None, max_length=200)
    rfc: str | None = Field(default=None, max_length=13)


@router.post("/propuestas/captura", response_model=PropuestaSalida, status_code=status.HTTP_201_CREATED)
def capturar(datos: NuevaCaptura, request: Request, ctx: Contexto = Depends(requiere(REVISAR)),
             bd: Session = Depends(obtener_bd)) -> PropuestaSalida:
    """Compras captura un producto nuevo por el proveedor, sea uno que ya nos surte o uno nuevo (Diego, 2026-11-03).
    Queda en borrador en Productos nuevos; al enviarlo sigue el mismo camino que las del portal."""
    if datos.proveedor_codigo:
        actual = bd.get(ProveedorIntelisis, datos.proveedor_codigo.strip())
        if not actual:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese proveedor no está en Intelisis (Centro de datos → Proveedores).")
        if not (actual.agente or "").strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ese proveedor no tiene agente en Intelisis; para productos nuevos solo se usan proveedores con agente.")
        org = bd.scalar(select(OrganizacionExterna).where(OrganizacionExterna.proveedor_intelisis == actual.proveedor))
        if not org:
            org = OrganizacionExterna(nombre=((actual.nombre or "").strip() or f"Proveedor {actual.proveedor}")[:200],
                                      proveedor_intelisis=actual.proveedor)
            bd.add(org)
            bd.flush()
        es_smn = "si"
        rfc_intelisis = actual.rfc if actual.rfc and pr.rfc_valido(actual.rfc) else None
    else:
        rfc_intelisis = None
        nombre = " ".join((datos.nombre or "").split())
        if len(nombre) < 2:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe la razón social del proveedor nuevo.")
        rfc = pr.limpio(datos.rfc).upper() or None
        if rfc and not pr.rfc_valido(rfc):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "RFC no válido (12 o 13 caracteres).")
        org = bd.scalar(select(OrganizacionExterna).where(OrganizacionExterna.rfc == rfc)) if rfc else None
        if org and org.proveedor_intelisis:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Ese RFC ya es de {org.nombre}, que ya es proveedor: elígelo como proveedor actual.")
        if not org:
            org = bd.scalar(select(OrganizacionExterna).where(OrganizacionExterna.nombre == nombre,
                                                              OrganizacionExterna.proveedor_intelisis.is_(None)))
        if not org:
            org = OrganizacionExterna(nombre=nombre, rfc=rfc)
            bd.add(org)
            bd.flush()
        es_smn = "no"
    ultima = bd.scalar(select(Propuesta).where(Propuesta.organizacion_id == org.organizacion_id)
                       .order_by(Propuesta.propuesta_id.desc()))
    r = pr.Respuestas()
    adjuntos: list[PropuestaAdjunto] = []
    if ultima:
        r.proveedor = _respuestas(ultima).proveedor
        adjuntos = [a for a in ultima.adjuntos if pr.adjunto_de_empresa(a)]
    else:
        r.proveedor = pr.DatosProveedor(razon_social=org.nombre, rfc=org.rfc or rfc_intelisis)
    r.proveedor.es_proveedor_smn = es_smn
    p = _nueva(bd, ctx, r, adjuntos, org.organizacion_id)
    _bitacora(bd, "capturar", ctx, request, p.propuesta_id,
              {"proveedor": org.proveedor_intelisis or "nuevo", "empresa": org.nombre})
    bd.commit()
    bd.refresh(p)
    return _salida(bd, p, ctx)


@router.get("/proveedores", response_model=list[ProveedorSalida])
def proveedores(_: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> list[ProveedorSalida]:
    rol = bd.scalar(select(Rol.rol_id).where(Rol.codigo == "proveedor"))
    usuarios = bd.scalars(select(Usuario).join(UsuarioRol, UsuarioRol.usuario_id == Usuario.usuario_id)
                          .where(UsuarioRol.rol_id == rol, Usuario.tipo == "externo").order_by(Usuario.creado_en.desc())).all()
    cuantas = dict(bd.execute(select(Propuesta.organizacion_id, func.count()).where(Propuesta.folio.is_not(None))
                              .group_by(Propuesta.organizacion_id)).all())
    return [ProveedorSalida(id=u.usuario_id, nombre=u.nombre, correo=u.correo,
                            empresa=u.organizacion.nombre if u.organizacion else None,
                            rfc=u.organizacion.rfc if u.organizacion else None, estatus=u.estatus,
                            propuestas=cuantas.get(u.organizacion_id, 0), ultimo_acceso_en=u.ultimo_acceso_en,
                            creado_en=u.creado_en) for u in usuarios]


class NuevoProveedor(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    correo: EmailStr
    empresa: str = Field(min_length=2, max_length=200)
    rfc: str | None = Field(default=None, max_length=13)
    puesto: str | None = Field(default=None, max_length=120)


class Invitado(BaseModel):
    proveedor: ProveedorSalida
    liga: str
    expira_en: datetime
    correo_enviado: bool


def _rol_proveedor(bd: Session) -> Rol:
    return bd.scalar(select(Rol).where(Rol.codigo == "proveedor"))


@router.post("/proveedores/invitar", response_model=Invitado, status_code=status.HTTP_201_CREATED)
def invitar(datos: NuevoProveedor, request: Request, ctx: Contexto = Depends(requiere(INVITAR)),
            bd: Session = Depends(obtener_bd)) -> Invitado:
    """Invita a una persona de un proveedor (actual o nuevo). Le llega un correo con la liga para crear su
    contraseña; con ella entra al portal y propone productos. Usa la misma invitación que Administración."""
    correo_nuevo = datos.correo.strip().lower()
    if bd.scalar(select(Usuario).where(func.lower(Usuario.correo) == correo_nuevo)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese correo.")
    rfc = pr.limpio(datos.rfc).upper() or None
    if rfc and not pr.rfc_valido(rfc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "RFC no válido (12 o 13 caracteres).")
    organizacion = bd.scalar(select(OrganizacionExterna).where(OrganizacionExterna.rfc == rfc)) if rfc else None
    if not organizacion:
        organizacion = OrganizacionExterna(nombre=datos.empresa.strip(), rfc=rfc)
        bd.add(organizacion)
        bd.flush()
    rol = _rol_proveedor(bd)
    usuario = Usuario(tipo="externo", correo=correo_nuevo, nombre=datos.nombre.strip(), estatus="invitado",
                      area="Proveedor", puesto=pr.limpio(datos.puesto) or None, organizacion_id=organizacion.organizacion_id)
    bd.add(usuario)
    bd.flush()
    bd.add(UsuarioRol(usuario_id=usuario.usuario_id, rol_id=rol.rol_id, asignado_por=ctx.usuario.usuario_id))
    liga = _crear_invitacion(bd, usuario, rol, ctx.usuario.usuario_id)
    registrar(bd, "invitar_proveedor", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd), entidad="usuario",
              entidad_id=usuario.usuario_id, detalle={"correo": correo_nuevo, "empresa": organizacion.nombre}, ip=ip_de(request))
    bd.commit()
    bd.refresh(usuario)
    enviado = _correo_invitacion(bd, usuario, ctx.usuario.nombre, liga.liga)
    return Invitado(proveedor=ProveedorSalida(id=usuario.usuario_id, nombre=usuario.nombre, correo=usuario.correo,
                                              empresa=organizacion.nombre, rfc=organizacion.rfc, estatus=usuario.estatus,
                                              propuestas=0, ultimo_acceso_en=None, creado_en=usuario.creado_en),
                    liga=liga.liga, expira_en=liga.expira_en, correo_enviado=enviado)


class LigaInvitacion(BaseModel):
    liga: str
    expira_en: datetime
    correo_enviado: bool
    dias: int = DIAS_INVITACION


@router.post("/proveedores/{usuario_id}/reenviar", response_model=LigaInvitacion)
def reenviar(usuario_id: int, request: Request, ctx: Contexto = Depends(requiere(INVITAR)),
             bd: Session = Depends(obtener_bd)) -> LigaInvitacion:
    usuario = bd.get(Usuario, usuario_id)
    rol = _rol_proveedor(bd)
    if not usuario or usuario.tipo != "externo" or rol not in usuario.roles:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese proveedor.")
    if usuario.estatus != "invitado":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se reenvía la invitación a quien aún no entra.")
    liga = _crear_invitacion(bd, usuario, rol, ctx.usuario.usuario_id)
    registrar(bd, "reenviar_invitacion", usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd), entidad="usuario",
              entidad_id=usuario_id, ip=ip_de(request))
    bd.commit()
    enviado = _correo_invitacion(bd, usuario, ctx.usuario.nombre, liga.liga)
    return LigaInvitacion(liga=liga.liga, expira_en=liga.expira_en, correo_enviado=enviado)
