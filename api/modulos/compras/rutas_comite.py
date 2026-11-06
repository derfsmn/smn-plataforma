"""Comité de producto nuevo (/api/compras/comite). Plan aprobado por Diego el 2026-11-04.

Cada reunión abre un ciclo con cuatro pasos: el equipo de producto de Compras sube productos (propuestas capturadas o del
portal, ideas y oportunidades), cada uno se evalúa con el semáforo (con proveedor si ya nos surte; si no, sin proveedor),
Compras hace el pre-filtro con motivo y el comité decide Aceptado, Denegado o En espera. Lo que queda en espera pasa a la
siguiente reunión. Se registran los asistentes con su puesto y lo que pidió cada uno, para darle seguimiento.
Una sola reunión sin cerrar a la vez. Nada se borra al cerrar: el ciclo queda de solo lectura.
"""
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, ip_de, requiere
from modulos.compras import propuestas as pr
from modulos.compras import radar_productos as rp
from modulos.compras.modelos_comite import ComiteAsistente, ComitePeticion, ComiteProducto, ComiteReunion, ComiteRevision
from modulos.compras.modelos_conocimiento import ConocimientoPolitica
from modulos.compras.modelos_productos import Oportunidad, ProductoEvaluacion, ProductoIdea
from modulos.compras.modelos_propuestas import Propuesta
from modulos.compras.rutas_productos import proveedor_de_idea
from nucleo.archivos import _raiz
from nucleo.bitacora import registrar
from nucleo.modelos import Archivo, Modulo, OrganizacionExterna, Usuario, ahora

router = APIRouter(prefix="/api/compras/comite", tags=["compras · comité de producto nuevo"])
VER = "compras.comite.ver"
SUBIR = "compras.comite.subir"
PREFILTRAR = "compras.comite.prefiltrar"  # también abre, avanza y cierra la reunión
DECIDIR = "compras.comite.decidir"

ESTADOS = {"abierta": "Subiendo productos", "prefiltro": "Pre-filtro de Compras", "comite": "En comité",
           "cerrada": "Cerrada"}
# Se puede regresar un paso mientras no esté cerrada (por si se avanzó antes de tiempo)
PASOS = {"abierta": {"prefiltro"}, "prefiltro": {"abierta", "comite"}, "comite": {"prefiltro", "cerrada"}, "cerrada": {"comite"}}
DECISIONES = {"aceptado": "Aceptado", "denegado": "Denegado", "en_espera": "En espera"}
REVISIONES = {"inventario": "Espacio en inventario", "regulacion": "Regulación"}
ESTADOS_IDEA = {"nueva": "Nueva", "buscar_proveedor": "Buscar proveedor", "vigilar": "Vigilar", "descartada": "Descartada"}
EN_PORTAL = {"borrador", "devuelta"}  # la propuesta todavía no está completa para evaluarse
RECIBEN = ("abierta", "prefiltro")  # mientras la reunión esté en estos pasos, lo que llega de proveedores entra a su ciclo


def _bitacora(bd: Session, accion: str, ctx: Contexto, request: Request, entidad: str, entidad_id,
              detalle: dict | None = None) -> None:
    modulo_id = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "compras"))
    registrar(bd, f"comite_{accion}", usuario_id=ctx.usuario.usuario_id, modulo_id=modulo_id, entidad=entidad,
              entidad_id=entidad_id, detalle=detalle, ip=ip_de(request))


def _decimal(v) -> Decimal | None:
    try:
        return Decimal(str(v)) if v not in (None, "") else None
    except (ArithmeticError, ValueError):
        return None


def _texto(v: str | None) -> str | None:
    v = " ".join((v or "").split())
    return v or None


def _alguno(*permisos: str):
    def verificar(ctx: Contexto = Depends(requiere(VER))) -> Contexto:
        if not any(ctx.puede(p) for p in permisos):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para esta acción.")
        return ctx
    return verificar


# ---------------------------------------------------------------- salidas

class FactorBreve(BaseModel):
    factor: str
    nombre: str
    puntaje: int | None
    valor: str | None
    peso: Decimal


class PuntoClave(BaseModel):
    factor: str
    nombre: str
    puntaje: int
    texto: str


class Ejecutivo(BaseModel):
    """El semáforo en una lámina ejecutiva: un titular, lo que está a favor y en contra, y qué haría falta para verde."""
    titular: str
    a_favor: list[PuntoClave]
    en_contra: list[PuntoClave]
    para_verde: str | None
    faltan_puntos: int | None
    margen_minimo: Decimal | None


class SemaforoSalida(BaseModel):
    id: int
    estado: str  # en_curso / lista / fallida
    color: str | None  # el vigente: el de Compras si lo cambió, si no el del radar
    color_radar: str | None
    puntaje: int | None
    confianza: str | None
    modelo: str | None  # con_proveedor / sin_proveedor
    avance: str | None
    error: str | None
    explicacion: str | None
    motivo_cambio: str | None
    factores: list[FactorBreve]
    ejecutivo: Ejecutivo | None = None


class Criterio(BaseModel):
    criterio: str = Field(min_length=1, max_length=200)
    valor: Literal["bien", "regular", "mal"]
    nota: str | None = Field(None, max_length=300)


class RevisionSalida(BaseModel):
    tipo: str
    nombre: str
    resultado: str
    nota: str | None
    por: str | None
    en: datetime


class ItemSalida(BaseModel):
    id: int
    tipo: str  # propuesta / idea
    sujeto_id: int
    nombre: str
    marca: str | None
    departamento: str | None
    folio: str | None
    proveedor: str | None
    proveedor_actual: bool
    origen: str
    viene_de_fecha: date | None
    presentacion: str | None
    descripcion: str | None
    precio: Decimal | None  # al público, con impuestos (sugerido o el que se vio)
    costo: Decimal | None  # sin IVA
    margen: Decimal | None
    fotos: int
    foto_externa: str | None  # foto de internet de una oportunidad
    estado_sujeto: str
    falta: str | None  # por qué todavía no se puede evaluar
    # «Listo para presentar» (Diego, 2026-11-06): lo que le falta para que la diapositiva salga completa
    faltantes: list[str] = []
    llego_solo: bool = False  # la mandó el proveedor por el portal durante el ciclo y entró sola
    evaluacion: SemaforoSalida | None
    prefiltro: str | None
    prefiltro_motivo: str | None
    criterios: list[Criterio]
    prefiltro_color: str | None
    prefiltro_por: str | None
    prefiltro_en: datetime | None
    decision: str | None
    decision_motivo: str | None
    decision_color: str | None
    decision_por: str | None
    decision_en: datetime | None
    revisiones: list[RevisionSalida]
    agregado_por: str | None
    agregado_en: datetime


class AsistenteSalida(BaseModel):
    id: int
    usuario_id: int | None
    nombre: str
    puesto: str | None


class PeticionSalida(BaseModel):
    id: int
    reunion_id: int
    fecha_reunion: date
    item_id: int | None
    producto: str | None
    asistente: str | None
    puesto: str | None
    texto: str
    estado: str
    respuesta: str | None
    atendida_por: str | None
    atendida_en: datetime | None
    creada_en: datetime


class Embudo(BaseModel):
    subidos: int
    evaluados: int
    pasan: int
    no_pasan: int
    aceptados: int
    denegados: int
    en_espera: int


class ReunionBreve(BaseModel):
    id: int
    fecha: date
    notas: str | None
    estado: str
    estado_texto: str
    embudo: Embudo
    peticiones_abiertas: int
    creada_en: datetime
    cerrada_en: datetime | None


class ReunionSalida(ReunionBreve):
    aprendizajes: str | None
    creada_por: str | None
    prefiltro_en: datetime | None
    comite_en: datetime | None
    cerrada_por: str | None
    productos: list[ItemSalida]
    asistentes: list[AsistenteSalida]
    peticiones: list[PeticionSalida]


# ---------------------------------------------------------------- armar las salidas

def _nombres(bd: Session, ids: set[int | None]) -> dict[int, str]:
    ids = {i for i in ids if i}
    return dict(bd.execute(select(Usuario.usuario_id, Usuario.nombre).where(Usuario.usuario_id.in_(ids or {0}))).all())


def _semaforo(e: ProductoEvaluacion | None, precio: Decimal | None = None, costo: Decimal | None = None) -> SemaforoSalida | None:
    if not e:
        return None
    orden = {f: i for i, f in enumerate(rp.FACTORES)}
    return SemaforoSalida(
        id=e.evaluacion_id, estado=e.estado, color=e.color_final or e.color, color_radar=e.color, puntaje=e.puntaje,
        confianza=e.confianza, modelo=e.modelo, avance=e.avance, error=e.error, explicacion=e.explicacion,
        motivo_cambio=e.motivo_cambio,
        factores=[FactorBreve(factor=f.factor, nombre=rp.NOMBRES.get(f.factor, f.factor), puntaje=f.puntaje, valor=f.valor,
                              peso=f.peso) for f in sorted(e.factores, key=lambda f: orden.get(f.factor, 99))],
        ejecutivo=_ejecutivo(e, precio, costo) if e.estado == "lista" else None)


A_FAVOR, EN_CONTRA = 70, 60  # 70 o más se cuenta a favor; menos de 60, en contra (entre 60 y 69 no destaca)


def _y(nombres: list[str]) -> str:
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _dinero(x: Decimal) -> str:
    return f"${x:,.2f}"


def _ejecutivo(e: ProductoEvaluacion, precio: Decimal | None, costo: Decimal | None) -> Ejecutivo:
    """Sin IA: sale de los mismos factores del semáforo, ordenados por lo que pesan."""
    con = [f for f in e.factores if f.puntaje is not None]
    peso = lambda f: float(f.peso or 0)  # noqa: E731
    favor = sorted((f for f in con if f.puntaje >= A_FAVOR), key=lambda f: (-f.puntaje * peso(f), f.factor))[:3]
    contra = sorted((f for f in con if f.puntaje < EN_CONTRA), key=lambda f: (f.puntaje * peso(f) - 100 * peso(f), f.factor))[:3]

    def punto(f) -> PuntoClave:
        return PuntoClave(factor=f.factor, nombre=rp.NOMBRES.get(f.factor, f.factor), puntaje=f.puntaje,
                          texto=f.valor or (f.detalle or "").split(". ")[0])

    nombre = lambda f: rp.NOMBRES.get(f.factor, f.factor).lower()  # noqa: E731
    politicas = json.loads(e.politicas) if e.politicas else {}
    if (r := politicas.get("rechazo")):
        titular = f"Cae en una regla de rechazo de Compras: {r.get('titulo')}."
    elif favor and contra:
        titular = f"Fuerte en {_y([nombre(f) for f in favor])}; débil en {_y([nombre(f) for f in contra])}."
    elif favor:
        titular = f"Fuerte en {_y([nombre(f) for f in favor])}, sin puntos débiles."
    elif contra:
        titular = f"Débil en {_y([nombre(f) for f in contra])}, sin factores a favor."
    else:
        titular = "Ningún factor destaca: todos quedan en medio."

    color = e.color_final or e.color
    faltan = (81 - e.puntaje) if e.puntaje is not None and color != "verde" and e.puntaje <= 80 else None
    renta = next((f for f in con if f.factor == "rentabilidad"), None)
    minimo = None
    if renta and renta.valor and (m := re.search(r"mínimo ([\d.]+) %", renta.valor)):
        minimo = Decimal(m.group(1))
    para_verde = None
    if color != "verde":
        sin = [nombre(f) for f in e.factores if f.puntaje is None and not (e.modelo == "sin_proveedor" and f.factor == "proveedor")]
        meta = re.search(r"al menos ([\d.]+) % de margen", renta.mejora or "") if renta else None
        actual = re.search(r"Deja ([\d.]+) % de margen", renta.valor or "") if renta else None
        if e.puntaje is not None and e.puntaje > 80:
            para_verde = f"Tiene puntos para verde, pero faltan datos de {_y(sin)}." if sin else None
        elif renta in contra and meta and actual and precio and costo:
            m_meta, m_hoy = Decimal(meta.group(1)) / 100, Decimal(actual.group(1)) / 100
            base = costo / (1 - m_hoy)  # el precio sin impuestos, sacado del margen que ya se calculó
            precio_meta = (precio * (costo / (1 - m_meta)) / base).quantize(Decimal("0.01"))
            costo_meta = (base * (1 - m_meta)).quantize(Decimal("0.01"))
            para_verde = (f"Rentabilidad arriba de 80: que deje {meta.group(1)} % de margen, vendiéndolo en "
                          f"{_dinero(precio_meta)} o consiguiéndolo en {_dinero(costo_meta)} sin IVA.")
        else:
            palanca = sorted((f for f in con if f.mejora and f.puntaje <= 80),
                             key=lambda f: (-peso(f) * (100 - f.puntaje), f.factor))
            if palanca:
                texto = re.sub(r"^Para que este factor salga arriba de 80,? (tendría que )?", "", palanca[0].mejora)
                texto = re.sub(r"\s*\([^)]*\)(?=\.?$)", "", texto)  # sin el paréntesis final con la escala
                para_verde = f"{rp.NOMBRES.get(palanca[0].factor)} arriba de 80: {texto[0].lower()}{texto[1:]}"
            elif sin:
                para_verde = f"Faltan datos de {_y(sin)}."
    return Ejecutivo(titular=titular, a_favor=[punto(f) for f in favor], en_contra=[punto(f) for f in contra],
                     para_verde=para_verde, faltan_puntos=faltan, margen_minimo=minimo)


def _datos_propuesta(p: Propuesta) -> dict:
    """Lo que se presenta de una propuesta. Una captura a medias puede no tener presentaciones todavía."""
    try:
        r = pr.Respuestas.model_validate_json(p.respuestas)
        principal = next((x for x in r.presentaciones if x.pvp_sugerido or x.costo_neto_sin_iva), None) or (
            r.presentaciones[0] if r.presentaciones else None)
    except Exception:  # noqa: BLE001
        return {}
    if not principal:
        return {}
    forma = principal.forma_otro if principal.forma == "Otro" else principal.forma
    presentacion = " · ".join(x for x in (principal.contenido_neto and f"{principal.contenido_neto} {principal.unidad_medida or ''}".strip(),
                                          forma) if x) or None
    return {"presentacion": presentacion, "descripcion": principal.descripcion or None,
            "precio": pr.numero(principal.pvp_sugerido), "costo": pr.numero(principal.costo_neto_sin_iva),
            "margen": pr.margen(principal)}


def _fotos_propuesta(p: Propuesta) -> list[int]:
    """archivo_id de las fotos del producto, la de frente primero."""
    fotos = [a for a in p.adjuntos if a.tipo == "imagen_producto"]
    fotos.sort(key=lambda a: (a.etiqueta != "Frente", a.etiqueta != "Reverso", a.adjunto_id))
    return [a.archivo_id for a in fotos]


def _fotos(bd: Session, item: ComiteProducto) -> list[int]:
    if item.propuesta_id:
        return _fotos_propuesta(bd.get(Propuesta, item.propuesta_id))
    idea = bd.get(ProductoIdea, item.idea_id)
    return [f.archivo_id for f in idea.fotos]


def _items(bd: Session, items: list[ComiteProducto]) -> list[ItemSalida]:
    usuarios = _nombres(bd, {u for i in items for u in (i.agregado_por, i.prefiltro_por, i.decision_por)}
                        | {r.actualizada_por for i in items for r in i.revisiones})
    externos = set(bd.scalars(select(Usuario.usuario_id).where(
        Usuario.usuario_id.in_({i.agregado_por for i in items} or {0}), Usuario.tipo != "interno")))
    origenes = dict(bd.execute(
        select(ComiteProducto.item_id, ComiteReunion.fecha).join(ComiteReunion)
        .where(ComiteProducto.item_id.in_({i.viene_de for i in items if i.viene_de} or {0}))).all())
    salida = []
    for i in items:
        if i.propuesta_id:
            p = bd.get(Propuesta, i.propuesta_id)
            org = bd.get(OrganizacionExterna, p.organizacion_id)
            e = rp.vigente(bd, propuesta_id=p.propuesta_id)
            datos = _datos_propuesta(p)
            falta = None
            if p.estado == "borrador":
                falta = "Falta terminar y enviar la captura."
            elif p.estado == "devuelta":
                falta = "Se regresó para corregir."
            elif p.estado == "rechazada":
                falta = "La propuesta está rechazada en Propuestas."
            base = dict(tipo="propuesta", sujeto_id=p.propuesta_id, nombre=p.producto or "Producto sin nombre", marca=p.marca,
                        departamento=p.departamento, folio=p.folio, proveedor=org.nombre,
                        proveedor_actual=bool(org.proveedor_intelisis), fotos=len(_fotos_propuesta(p)), foto_externa=None,
                        estado_sujeto=pr.ESTADOS.get(p.estado, p.estado), falta=falta,
                        presentacion=datos.get("presentacion"), descripcion=datos.get("descripcion"),
                        precio=datos.get("precio"), costo=datos.get("costo"), margen=datos.get("margen"))
        else:
            idea = bd.get(ProductoIdea, i.idea_id)
            e = rp.vigente(bd, idea_id=idea.idea_id)
            op = bd.scalar(select(Oportunidad).where(Oportunidad.idea_id == idea.idea_id))
            margen = rp.sujeto_de_idea(idea).margen
            presentacion = " · ".join(x for x in (idea.contenido, idea.forma) if x) or None
            base = dict(tipo="idea", sujeto_id=idea.idea_id, nombre=idea.nombre, marca=idea.marca,
                        departamento=idea.departamento, folio=None, proveedor=proveedor_de_idea(bd, idea),
                        proveedor_actual=bool(idea.proveedor_intelisis),
                        fotos=len(idea.fotos), foto_externa=op.imagen if op and not idea.fotos else None,
                        estado_sujeto=ESTADOS_IDEA.get(idea.estado, idea.estado), falta=None, presentacion=presentacion,
                        descripcion=idea.descripcion, precio=idea.precio_visto, costo=idea.costo_estimado, margen=margen)
        salida.append(ItemSalida(
            id=i.item_id, origen=i.origen, viene_de_fecha=origenes.get(i.viene_de), evaluacion=_semaforo(e, _decimal(base.get("precio")), _decimal(base.get("costo"))),
            llego_solo=i.agregado_por in externos,
            prefiltro=i.prefiltro, prefiltro_motivo=i.prefiltro_motivo,
            criterios=[Criterio(**c) for c in json.loads(i.criterios or "[]")], prefiltro_color=i.prefiltro_color,
            prefiltro_por=usuarios.get(i.prefiltro_por), prefiltro_en=i.prefiltro_en, decision=i.decision,
            decision_motivo=i.decision_motivo, decision_color=i.decision_color, decision_por=usuarios.get(i.decision_por),
            decision_en=i.decision_en, agregado_por=usuarios.get(i.agregado_por), agregado_en=i.agregado_en,
            revisiones=[RevisionSalida(tipo=r.tipo, nombre=REVISIONES[r.tipo], resultado=r.resultado, nota=r.nota,
                                       por=usuarios.get(r.actualizada_por), en=r.actualizada_en)
                        for r in sorted(i.revisiones, key=lambda r: list(REVISIONES).index(r.tipo))],
            faltantes=_faltantes(e, base), **base))
    return salida


def _faltantes(e: ProductoEvaluacion | None, base: dict) -> list[str]:
    """Lo que le falta a un producto para presentarse completo en el comité, en palabras."""
    falta = []
    if not base.get("fotos") and not base.get("foto_externa"):
        falta.append("foto")
    if base.get("precio") in (None, ""):
        falta.append("precio")
    if base.get("costo") in (None, ""):
        falta.append("costo")
    if not e or e.estado != "lista":
        falta.append("semáforo terminado")
    elif not e.comparables:
        falta.append("productos parecidos")
    return falta


def _embudo(bd: Session, items: list[ComiteProducto]) -> Embudo:
    evaluados = 0
    for i in items:
        e = rp.vigente(bd, propuesta_id=i.propuesta_id) if i.propuesta_id else rp.vigente(bd, idea_id=i.idea_id)
        evaluados += bool(e and e.estado == "lista")
    return Embudo(subidos=len(items), evaluados=evaluados, pasan=sum(i.prefiltro == "pasa" for i in items),
                  no_pasan=sum(i.prefiltro == "no_pasa" for i in items),
                  aceptados=sum(i.decision == "aceptado" for i in items),
                  denegados=sum(i.decision == "denegado" for i in items),
                  en_espera=sum(i.decision == "en_espera" for i in items))


def _peticiones(bd: Session, filas: list[ComitePeticion]) -> list[PeticionSalida]:
    usuarios = _nombres(bd, {p.atendida_por for p in filas})
    asistentes = {a.asistente_id: a for a in bd.scalars(select(ComiteAsistente).where(
        ComiteAsistente.asistente_id.in_({p.asistente_id for p in filas if p.asistente_id} or {0})))}
    fechas = dict(bd.execute(select(ComiteReunion.reunion_id, ComiteReunion.fecha).where(
        ComiteReunion.reunion_id.in_({p.reunion_id for p in filas} or {0}))).all())
    nombres = {}
    for p in filas:
        if p.item_id and p.item_id not in nombres:
            it = bd.get(ComiteProducto, p.item_id)
            nombres[p.item_id] = (bd.get(Propuesta, it.propuesta_id).producto if it.propuesta_id
                                  else bd.get(ProductoIdea, it.idea_id).nombre) or "Producto sin nombre"
    return [PeticionSalida(id=p.peticion_id, reunion_id=p.reunion_id, fecha_reunion=fechas[p.reunion_id], item_id=p.item_id,
                           producto=nombres.get(p.item_id), asistente=(a := asistentes.get(p.asistente_id)) and a.nombre,
                           puesto=a.puesto if a else None, texto=p.texto, estado=p.estado, respuesta=p.respuesta,
                           atendida_por=usuarios.get(p.atendida_por), atendida_en=p.atendida_en, creada_en=p.creada_en)
            for p in filas]


def _abiertas(bd: Session, reunion_id: int) -> int:
    return len(bd.scalars(select(ComitePeticion.peticion_id).where(ComitePeticion.reunion_id == reunion_id,
                                                                   ComitePeticion.estado == "abierta")).all())


def _breve(bd: Session, r: ComiteReunion) -> ReunionBreve:
    return ReunionBreve(id=r.reunion_id, fecha=r.fecha, notas=r.notas, estado=r.estado, estado_texto=ESTADOS[r.estado],
                        embudo=_embudo(bd, r.productos), peticiones_abiertas=_abiertas(bd, r.reunion_id),
                        creada_en=r.creada_en, cerrada_en=r.cerrada_en)


def _salida(bd: Session, r: ComiteReunion) -> ReunionSalida:
    usuarios = _nombres(bd, {r.creada_por, r.cerrada_por})
    peticiones = list(bd.scalars(select(ComitePeticion).where(ComitePeticion.reunion_id == r.reunion_id)
                                 .order_by(ComitePeticion.peticion_id)))
    return ReunionSalida(**_breve(bd, r).model_dump(), aprendizajes=r.aprendizajes, creada_por=usuarios.get(r.creada_por),
                         prefiltro_en=r.prefiltro_en, comite_en=r.comite_en, cerrada_por=usuarios.get(r.cerrada_por),
                         productos=_items(bd, r.productos),
                         asistentes=[AsistenteSalida(id=a.asistente_id, usuario_id=a.usuario_id, nombre=a.nombre,
                                                     puesto=a.puesto) for a in r.asistentes],
                         peticiones=_peticiones(bd, peticiones))


def _reunion(bd: Session, reunion_id: int) -> ComiteReunion:
    r = bd.get(ComiteReunion, reunion_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa reunión.")
    return r


def _item(bd: Session, item_id: int) -> ComiteProducto:
    i = bd.get(ComiteProducto, item_id)
    if not i:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese producto no está en ninguna reunión.")
    return i


def _en(r: ComiteReunion, *estados: str, que: str) -> None:
    if r.estado not in estados:
        cuando = " o ".join(f"«{ESTADOS[e]}»" for e in estados)
        raise HTTPException(status.HTTP_409_CONFLICT, f"{que} solo se puede cuando la reunión está en {cuando}.")


# ---------------------------------------------------------------- evaluar

def evaluar_sujeto(bd: Session, item: ComiteProducto, ctx: Contexto, request: Request | None) -> None:
    """Pone a evaluar el producto si todavía no tiene semáforo. Una propuesta enviada pasa a «Lista para evaluar» (la
    entrada del radar), con el mismo aviso al proveedor que si Compras la marcara desde Propuestas."""
    if item.idea_id:
        if not rp.vigente(bd, idea_id=item.idea_id):
            e = rp.iniciar(bd, idea_id=item.idea_id, usuario_id=ctx.usuario.usuario_id)
            rp.en_hilo(e.evaluacion_id)
        return
    p = bd.get(Propuesta, item.propuesta_id)
    if p.estado in ("recibida", "en_revision"):
        from modulos.compras import rutas_propuestas as rpr

        rpr.cambiar_estado(p.propuesta_id, rpr.CambioEstado(estado="lista"), request, ctx, bd)  # evalúa ahí mismo
    elif p.estado == "lista" and not rp.vigente(bd, propuesta_id=p.propuesta_id):
        e = rp.iniciar(bd, propuesta_id=p.propuesta_id, usuario_id=ctx.usuario.usuario_id)
        rp.en_hilo(e.evaluacion_id)


def al_enviar_propuesta(bd: Session, p: Propuesta, ctx: Contexto, request: Request, compras: bool) -> None:
    """Lo que llega de proveedores durante un ciclo se considera en ese ciclo.

    - Si ya está en una reunión sin cerrar (por ejemplo, una captura que se empezó desde el comité o una corrección),
      se queda ahí.
    - Si no, y hay una reunión subiendo productos o en pre-filtro, entra sola a esa reunión.
    - Si la reunión ya está en comité (o no hay ninguna abierta), entra a la siguiente al abrirla (ver `abrir`).
    Lo que capturó Compras se evalúa en cuanto se envía; lo que mandó el proveedor por el portal espera a que Compras
    lo revise y pulse «Evaluar», igual que en Propuestas."""
    item = bd.scalar(select(ComiteProducto).join(ComiteReunion).where(
        ComiteProducto.propuesta_id == p.propuesta_id, ComiteReunion.estado != "cerrada"))
    if not item:
        if bd.scalar(select(ComiteProducto.item_id).where(ComiteProducto.propuesta_id == p.propuesta_id)):
            return  # ya pasó por un comité; si quedó en espera, se lleva solo a la siguiente
        r = bd.scalar(select(ComiteReunion).where(ComiteReunion.estado.in_(RECIBEN)))
        if not r:
            return
        item = _sumar_llegada(bd, r, p, ctx.usuario.usuario_id)
        _bitacora(bd, "llegada", ctx, request, "comite_producto", item.item_id,
                  {"reunion": r.reunion_id, "propuesta": p.propuesta_id})
        bd.commit()
    if compras and bd.get(ComiteReunion, item.reunion_id).estado in RECIBEN:
        evaluar_sujeto(bd, item, ctx, request)


def _sumar_llegada(bd: Session, r: ComiteReunion, p: Propuesta, usuario_id: int) -> ComiteProducto:
    autor = bd.get(Usuario, p.creada_por)
    orden = bd.scalar(select(ComiteProducto.orden).where(ComiteProducto.reunion_id == r.reunion_id)
                      .order_by(ComiteProducto.orden.desc())) or 0
    item = ComiteProducto(reunion_id=r.reunion_id, propuesta_id=p.propuesta_id, idea_id=None,
                          origen="captura" if autor and autor.tipo == "interno" else "propuesta",
                          orden=orden + 1, agregado_por=usuario_id, agregado_en=ahora())
    bd.add(item)
    bd.flush()
    return item


# ---------------------------------------------------------------- reuniones

@router.get("/reuniones", response_model=list[ReunionBreve])
def reuniones(_: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> list[ReunionBreve]:
    filas = bd.scalars(select(ComiteReunion).order_by(ComiteReunion.fecha.desc(), ComiteReunion.reunion_id.desc()).limit(200))
    return [_breve(bd, r) for r in filas]


class NuevaReunion(BaseModel):
    fecha: date
    notas: str | None = Field(None, max_length=2000)


@router.post("/reuniones", response_model=ReunionSalida, status_code=status.HTTP_201_CREATED)
def abrir(datos: NuevaReunion, request: Request, ctx: Contexto = Depends(requiere(PREFILTRAR)),
          bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    """Registra la fecha y abre el ciclo. Lo que quedó «En espera» en reuniones anteriores entra solo, ya pre-filtrado."""
    if otra := bd.scalar(select(ComiteReunion).where(ComiteReunion.estado != "cerrada")):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Ya hay una reunión sin cerrar (la del {otra.fecha:%d/%m/%Y}). Ciérrala antes de abrir otra.")
    r = ComiteReunion(fecha=datos.fecha, notas=(datos.notas or "").strip() or None, estado="abierta",
                      creada_por=ctx.usuario.usuario_id, creada_en=ahora())
    bd.add(r)
    bd.flush()
    llevados = {x for x in bd.scalars(select(ComiteProducto.viene_de).where(ComiteProducto.viene_de.is_not(None)))}
    en_espera = bd.scalars(select(ComiteProducto).where(ComiteProducto.decision == "en_espera")
                           .order_by(ComiteProducto.item_id)).all()
    orden = 0
    for x in en_espera:
        if x.item_id in llevados:
            continue
        orden += 1
        bd.add(ComiteProducto(reunion_id=r.reunion_id, propuesta_id=x.propuesta_id, idea_id=x.idea_id, origen="espera",
                              viene_de=x.item_id, orden=orden, agregado_por=ctx.usuario.usuario_id, agregado_en=ahora(),
                              prefiltro=x.prefiltro, prefiltro_motivo=x.prefiltro_motivo, criterios=x.criterios,
                              prefiltro_color=x.prefiltro_color, prefiltro_puntaje=x.prefiltro_puntaje,
                              prefiltro_por=x.prefiltro_por, prefiltro_en=x.prefiltro_en))
    # Lo que llegó de proveedores después de que la reunión anterior pasó a comité entra a este ciclo.
    anterior = bd.scalar(select(ComiteReunion).where(ComiteReunion.reunion_id != r.reunion_id, ComiteReunion.comite_en.is_not(None))
                         .order_by(ComiteReunion.comite_en.desc()))
    llegadas = []
    if anterior:
        ya = select(ComiteProducto.propuesta_id).where(ComiteProducto.propuesta_id.is_not(None))
        llegadas = bd.scalars(select(Propuesta).where(
            Propuesta.enviada_en >= anterior.comite_en, Propuesta.estado.in_(("recibida", "en_revision", "lista")),
            Propuesta.propuesta_id.not_in(ya)).order_by(Propuesta.enviada_en)).all()
    if llegadas:
        from modulos.compras.rutas_propuestas import de_compras
    for p in llegadas:
        orden += 1
        bd.add(ComiteProducto(reunion_id=r.reunion_id, propuesta_id=p.propuesta_id, idea_id=None,
                              origen="captura" if de_compras(bd, p) else "propuesta", orden=orden,
                              agregado_por=p.creada_por, agregado_en=ahora()))
    _bitacora(bd, "abrir", ctx, request, "comite_reunion", r.reunion_id,
              {"fecha": str(r.fecha), "en_espera": orden - len(llegadas), "llegadas": len(llegadas)})
    bd.commit()
    bd.refresh(r)
    return _salida(bd, r)


@router.get("/reuniones/{reunion_id}/acta")
def acta(reunion_id: int, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> Response:
    """Acta en PDF para mandar por correo; si la reunión no está cerrada sale como borrador."""
    from modulos.compras import acta_comite

    r = _salida(bd, _reunion(bd, reunion_id))
    pdf = acta_comite.generar(r, datetime.now(ZoneInfo("America/Mexico_City")))
    nombre = f"Acta comite producto nuevo {r.fecha:%Y-%m-%d}{'' if r.estado == 'cerrada' else ' borrador'}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/reuniones/{reunion_id}", response_model=ReunionSalida)
def reunion(reunion_id: int, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    return _salida(bd, _reunion(bd, reunion_id))


class CambioReunion(BaseModel):
    fecha: date | None = None
    notas: str | None = Field(None, max_length=2000)
    aprendizajes: str | None = Field(None, max_length=20000)


@router.patch("/reuniones/{reunion_id}", response_model=ReunionSalida)
def cambiar(reunion_id: int, datos: CambioReunion, request: Request, ctx: Contexto = Depends(requiere(PREFILTRAR)),
            bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    """Fecha y notas mientras no esté cerrada; «Qué aprendimos» se puede escribir también después de cerrar."""
    r = _reunion(bd, reunion_id)
    campos = datos.model_dump(exclude_unset=True)
    if r.estado == "cerrada" and set(campos) - {"aprendizajes"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "La reunión está cerrada: solo se puede escribir «Qué aprendimos».")
    if "fecha" in campos and datos.fecha:
        r.fecha = datos.fecha
    if "notas" in campos:
        r.notas = (datos.notas or "").strip() or None
    if "aprendizajes" in campos:
        r.aprendizajes = (datos.aprendizajes or "").strip() or None
    _bitacora(bd, "cambiar", ctx, request, "comite_reunion", r.reunion_id, {"campos": sorted(campos)})
    bd.commit()
    return _salida(bd, r)


class CambioEstado(BaseModel):
    estado: Literal["abierta", "prefiltro", "comite", "cerrada"]
    # Para regresar del comité al pre-filtro cuando ya hay decisiones (Diego, 2026-11-05: «que pudiera regresar a los
    # status previos… estoy haciendo pruebas»). Las decisiones se borran y queda en la bitácora qué había.
    borrar_decisiones: bool = False


@router.post("/reuniones/{reunion_id}/estado", response_model=ReunionSalida)
def avanzar(reunion_id: int, datos: CambioEstado, request: Request, ctx: Contexto = Depends(requiere(PREFILTRAR)),
            bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    r = _reunion(bd, reunion_id)
    if datos.estado not in PASOS.get(r.estado, set()):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Una reunión en «{ESTADOS[r.estado]}» no puede pasar a «{ESTADOS[datos.estado]}».")
    if datos.estado == "comite":
        if faltan := [i for i in r.productos if not i.prefiltro]:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Faltan {len(faltan)} producto(s) por pre-filtrar.")
        if not any(i.prefiltro == "pasa" for i in r.productos):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ningún producto pasó el pre-filtro: no hay qué presentar.")
    decididos = [i for i in r.productos if i.decision]
    if datos.estado == "prefiltro" and r.estado == "comite" and decididos and not datos.borrar_decisiones:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"El comité ya decidió sobre {len(decididos)} producto(s). Para regresar al pre-filtro hay que borrar esas decisiones.")
    if r.estado == "cerrada":  # reabrir: volver al comité
        if otra := bd.scalar(select(ComiteReunion).where(ComiteReunion.estado != "cerrada", ComiteReunion.reunion_id != r.reunion_id)):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Ya hay otra reunión sin cerrar (la del {otra.fecha:%d/%m/%Y}). Solo puede haber una abierta a la vez.")
        llevados = bd.scalar(select(func.count()).select_from(ComiteProducto).where(
            ComiteProducto.viene_de.in_([i.item_id for i in r.productos] or [0])))
        if llevados:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"{llevados} producto(s) que quedaron «En espera» ya entraron a otra reunión: no se puede reabrir esta.")
    if datos.estado == "prefiltro" and r.estado == "abierta" and not r.productos:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sube al menos un producto antes de empezar el pre-filtro.")
    if datos.estado == "cerrada" and (faltan := [i for i in r.productos if i.prefiltro == "pasa" and not i.decision]):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Falta la decisión del comité en {len(faltan)} producto(s).")
    borradas = []
    if datos.estado == "prefiltro" and r.estado == "comite":
        for i in decididos:
            borradas.append({"item": i.item_id, "decision": i.decision, "motivo": i.decision_motivo})
            i.decision = i.decision_motivo = i.decision_color = i.decision_puntaje = None
            i.decision_por = i.decision_en = None
            i.revisiones.clear()
    antes, r.estado = r.estado, datos.estado
    if antes == "cerrada":
        r.cerrada_en = r.cerrada_por = None
    if datos.estado == "prefiltro" and antes == "abierta":
        r.prefiltro_en = ahora()
    elif datos.estado == "comite":
        r.comite_en = r.comite_en or ahora()
    elif datos.estado == "cerrada":
        r.cerrada_en, r.cerrada_por = ahora(), ctx.usuario.usuario_id
    _bitacora(bd, "estado", ctx, request, "comite_reunion", r.reunion_id, {"antes": antes, "despues": r.estado, **({"decisiones_borradas": borradas} if borradas else {})})
    bd.commit()
    return _salida(bd, r)


# ---------------------------------------------------------------- subir productos

class Candidato(BaseModel):
    tipo: str  # propuesta / idea
    id: int
    nombre: str
    detalle: str  # folio, proveedor, estado
    color: str | None
    en_otra: bool = False  # ya está en esta reunión


@router.get("/candidatos", response_model=list[Candidato])
def candidatos(q: str = Query("", max_length=100), _: Contexto = Depends(requiere(VER)),
               bd: Session = Depends(obtener_bd)) -> list[Candidato]:
    """Propuestas (enviadas o capturas de Compras) e ideas u oportunidades evaluadas que se pueden subir al ciclo."""
    abierta = bd.scalar(select(ComiteReunion).where(ComiteReunion.estado != "cerrada"))
    ya_p = {i.propuesta_id for i in abierta.productos} if abierta else set()
    ya_i = {i.idea_id for i in abierta.productos} if abierta else set()
    t = f"%{q.strip()}%"
    qp = (select(Propuesta, OrganizacionExterna).join(OrganizacionExterna,
                                                      OrganizacionExterna.organizacion_id == Propuesta.organizacion_id)
          .join(Usuario, Usuario.usuario_id == Propuesta.creada_por)
          .where(Propuesta.estado != "rechazada", or_(Propuesta.folio.is_not(None), Usuario.tipo == "interno")))
    qi = select(ProductoIdea).where(ProductoIdea.estado != "descartada")
    if q.strip():
        qp = qp.where(or_(Propuesta.folio.like(t), Propuesta.producto.like(t), OrganizacionExterna.nombre.like(t)))
        qi = qi.where(or_(ProductoIdea.nombre.like(t), ProductoIdea.marca.like(t)))
    salida = []
    for p, org in bd.execute(qp.order_by(Propuesta.actualizada_en.desc()).limit(30)):
        e = rp.vigente(bd, propuesta_id=p.propuesta_id)
        salida.append(Candidato(tipo="propuesta", id=p.propuesta_id, nombre=p.producto or "Producto sin nombre",
                                detalle=" · ".join(x for x in (p.folio or "Captura sin enviar", org.nombre,
                                                               pr.ESTADOS.get(p.estado, p.estado)) if x),
                                color=e and (e.color_final or e.color), en_otra=p.propuesta_id in ya_p))
    for i in bd.scalars(qi.order_by(ProductoIdea.idea_id.desc()).limit(30)):
        e = rp.vigente(bd, idea_id=i.idea_id)
        op = bd.scalar(select(Oportunidad.oportunidad_id).where(Oportunidad.idea_id == i.idea_id))
        salida.append(Candidato(tipo="idea", id=i.idea_id, nombre=i.nombre,
                                detalle=" · ".join(x for x in ("Oportunidad" if op else "Idea de Compras", i.marca,
                                                               "sin proveedor") if x),
                                color=e and (e.color_final or e.color), en_otra=i.idea_id in ya_i))
    return salida


class NuevoProducto(BaseModel):
    propuesta_id: int | None = None
    idea_id: int | None = None


@router.post("/reuniones/{reunion_id}/productos", response_model=ReunionSalida, status_code=status.HTTP_201_CREATED)
def subir(reunion_id: int, datos: NuevoProducto, request: Request, ctx: Contexto = Depends(requiere(SUBIR)),
          bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    r = _reunion(bd, reunion_id)
    _en(r, "abierta", que="Subir productos")
    if bool(datos.propuesta_id) == bool(datos.idea_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige una propuesta o una idea.")
    if datos.propuesta_id:
        p = bd.get(Propuesta, datos.propuesta_id)
        autor = bd.get(Usuario, p.creada_por) if p else None
        if not p or not (p.folio or (autor and autor.tipo == "interno")):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa propuesta.")
        if p.estado == "rechazada":
            raise HTTPException(status.HTTP_409_CONFLICT, "Esa propuesta está rechazada en Propuestas.")
        if any(i.propuesta_id == p.propuesta_id for i in r.productos):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ese producto ya está en esta reunión.")
        origen = "captura" if autor and autor.tipo == "interno" else "propuesta"
    else:
        idea = bd.get(ProductoIdea, datos.idea_id)
        if not idea:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa idea.")
        if any(i.idea_id == idea.idea_id for i in r.productos):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ese producto ya está en esta reunión.")
        origen = "idea"
    item = ComiteProducto(reunion_id=r.reunion_id, propuesta_id=datos.propuesta_id, idea_id=datos.idea_id, origen=origen,
                          orden=max((i.orden for i in r.productos), default=0) + 1, agregado_por=ctx.usuario.usuario_id,
                          agregado_en=ahora())
    bd.add(item)
    bd.flush()
    _bitacora(bd, "subir", ctx, request, "comite_producto", item.item_id,
              {"reunion": r.reunion_id, "propuesta": datos.propuesta_id, "idea": datos.idea_id})
    bd.commit()
    evaluar_sujeto(bd, item, ctx, request)
    bd.expire_all()  # la evaluación corre en otra sesión
    return _salida(bd, _reunion(bd, reunion_id))


@router.delete("/productos/{item_id}", response_model=ReunionSalida)
def quitar(item_id: int, request: Request, ctx: Contexto = Depends(requiere(SUBIR)),
           bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    """Solo mientras se suben productos. El producto no se borra: sigue en Propuestas o en el radar."""
    i = _item(bd, item_id)
    r = _reunion(bd, i.reunion_id)
    _en(r, "abierta", que="Quitar productos")
    if bd.scalar(select(ComitePeticion.peticion_id).where(ComitePeticion.item_id == i.item_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese producto tiene peticiones registradas; no se puede quitar.")
    _bitacora(bd, "quitar", ctx, request, "comite_producto", i.item_id,
              {"reunion": r.reunion_id, "propuesta": i.propuesta_id, "idea": i.idea_id})
    r.productos.remove(i)
    bd.commit()
    bd.refresh(r)
    return _salida(bd, r)


@router.post("/productos/{item_id}/evaluar", response_model=ReunionSalida)
def evaluar(item_id: int, request: Request, ctx: Contexto = Depends(requiere(SUBIR)),
            bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    """Vuelve a evaluar (por ejemplo, si falló o si se corrigió la captura)."""
    i = _item(bd, item_id)
    r = _reunion(bd, i.reunion_id)
    _en(r, "abierta", "prefiltro", que="Evaluar")
    if i.propuesta_id:
        p = bd.get(Propuesta, i.propuesta_id)
        if p.estado in EN_PORTAL or p.estado == "rechazada":
            raise HTTPException(status.HTTP_409_CONFLICT, "La propuesta todavía no está enviada: termínala primero.")
    e = rp.vigente(bd, propuesta_id=i.propuesta_id) if i.propuesta_id else rp.vigente(bd, idea_id=i.idea_id)
    if e and e.estado == "en_curso":
        raise HTTPException(status.HTTP_409_CONFLICT, "La evaluación sigue en curso; espera a que termine.")
    if e:
        nueva = rp.iniciar(bd, propuesta_id=i.propuesta_id, idea_id=i.idea_id, usuario_id=ctx.usuario.usuario_id)
        rp.en_hilo(nueva.evaluacion_id)
    else:
        evaluar_sujeto(bd, i, ctx, request)
    _bitacora(bd, "evaluar", ctx, request, "comite_producto", i.item_id, {"reunion": r.reunion_id})
    bd.commit()
    bd.expire_all()  # la evaluación corre en otra sesión
    return _salida(bd, _reunion(bd, r.reunion_id))


@router.get("/productos/{item_id}/fotos/{n}")
def foto(item_id: int, n: int, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> FileResponse:
    """La foto n (desde 0) del producto: las del cuestionario del proveedor o las de la idea."""
    fotos = _fotos(bd, _item(bd, item_id))
    archivo = bd.get(Archivo, fotos[n]) if 0 <= n < len(fotos) else None
    raiz = _raiz()
    ruta = (raiz / archivo.ruta_almacenamiento).resolve() if archivo else None
    if not ruta or raiz not in ruta.parents or not ruta.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa foto.")
    return FileResponse(ruta, media_type=archivo.tipo_contenido, filename=archivo.nombre_original,
                        content_disposition_type="inline", headers={"X-Content-Type-Options": "nosniff"})


# ---------------------------------------------------------------- pre-filtro

class Prefiltro(BaseModel):
    resultado: Literal["pasa", "no_pasa"]
    motivo: str = Field(min_length=1, max_length=1000)
    criterios: list[Criterio] = Field(default_factory=list, max_length=30)


@router.put("/productos/{item_id}/prefiltro", response_model=ReunionSalida)
def prefiltrar(item_id: int, datos: Prefiltro, request: Request, ctx: Contexto = Depends(requiere(PREFILTRAR)),
               bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    i = _item(bd, item_id)
    r = _reunion(bd, i.reunion_id)
    _en(r, "prefiltro", que="El pre-filtro")
    motivo = _texto(datos.motivo)
    if not motivo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe el motivo.")
    e = rp.vigente(bd, propuesta_id=i.propuesta_id) if i.propuesta_id else rp.vigente(bd, idea_id=i.idea_id)
    i.prefiltro, i.prefiltro_motivo = datos.resultado, motivo
    i.criterios = json.dumps([{"criterio": _texto(c.criterio), "valor": c.valor, "nota": _texto(c.nota)}
                              for c in datos.criterios if _texto(c.criterio)], ensure_ascii=False)
    i.prefiltro_color = (e.color_final or e.color) if e and e.estado == "lista" else None
    i.prefiltro_puntaje = e.puntaje if e and e.estado == "lista" else None
    i.prefiltro_por, i.prefiltro_en = ctx.usuario.usuario_id, ahora()
    _bitacora(bd, "prefiltro", ctx, request, "comite_producto", i.item_id,
              {"reunion": r.reunion_id, "resultado": datos.resultado, "semaforo": i.prefiltro_color})
    bd.commit()
    return _salida(bd, r)


class Referencia(BaseModel):
    id: int
    titulo: str
    tema: str


class Criterios(BaseModel):
    politicas: list[Referencia]  # las vigentes de la Base de conocimiento
    usados: list[str]  # criterios que ya se usaron en otros pre-filtros (p. ej. «Gusto del empaque»)


@router.get("/criterios", response_model=Criterios)
def criterios(_: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> Criterios:
    politicas = bd.scalars(select(ConocimientoPolitica).where(ConocimientoPolitica.estado == "vigente",
                                                              ConocimientoPolitica.tema != "proceso")
                           .order_by(ConocimientoPolitica.tema, ConocimientoPolitica.titulo)).all()
    usados: dict[str, str] = {}
    for texto in bd.scalars(select(ComiteProducto.criterios).where(ComiteProducto.criterios.is_not(None))):
        for c in json.loads(texto or "[]"):
            usados.setdefault(c["criterio"].lower(), c["criterio"])
    return Criterios(politicas=[Referencia(id=p.politica_id, titulo=p.titulo, tema=p.tema) for p in politicas],
                     usados=sorted(usados.values(), key=str.lower))


# ---------------------------------------------------------------- comité

class Decision(BaseModel):
    decision: Literal["aceptado", "denegado", "en_espera"]
    motivo: str = Field(min_length=1, max_length=1000)


@router.put("/productos/{item_id}/decision", response_model=ReunionSalida)
def decidir(item_id: int, datos: Decision, request: Request, ctx: Contexto = Depends(requiere(DECIDIR)),
            bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    i = _item(bd, item_id)
    r = _reunion(bd, i.reunion_id)
    _en(r, "comite", que="Registrar la decisión")
    if i.prefiltro != "pasa":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se decide sobre los productos que pasaron el pre-filtro.")
    motivo = _texto(datos.motivo)
    if not motivo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe el motivo.")
    e = rp.vigente(bd, propuesta_id=i.propuesta_id) if i.propuesta_id else rp.vigente(bd, idea_id=i.idea_id)
    i.decision, i.decision_motivo = datos.decision, motivo
    i.decision_color = (e.color_final or e.color) if e and e.estado == "lista" else None
    i.decision_puntaje = e.puntaje if e and e.estado == "lista" else None
    i.decision_por, i.decision_en = ctx.usuario.usuario_id, ahora()
    if datos.decision != "aceptado":
        i.revisiones.clear()
    _bitacora(bd, "decision", ctx, request, "comite_producto", i.item_id,
              {"reunion": r.reunion_id, "decision": datos.decision, "semaforo": i.decision_color})
    bd.commit()
    return _salida(bd, r)


class Revision(BaseModel):
    resultado: Literal["pendiente", "aprobada", "rechazada"]
    nota: str | None = Field(None, max_length=1000)


@router.put("/productos/{item_id}/revisiones/{tipo}", response_model=ReunionSalida)
def revisar(item_id: int, tipo: Literal["inventario", "regulacion"], datos: Revision, request: Request,
            ctx: Contexto = Depends(requiere(PREFILTRAR)), bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    """Revisión después de aceptar, si aplica: espacio en inventario y después regulación. Sigue abierta al cerrar."""
    i = _item(bd, item_id)
    if i.decision != "aceptado":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo los productos aceptados pasan a revisión.")
    rev = next((x for x in i.revisiones if x.tipo == tipo), None)
    if not rev:
        rev = ComiteRevision(tipo=tipo)
        i.revisiones.append(rev)
    rev.resultado, rev.nota = datos.resultado, _texto(datos.nota)
    rev.actualizada_por, rev.actualizada_en = ctx.usuario.usuario_id, ahora()
    _bitacora(bd, "revision", ctx, request, "comite_producto", i.item_id, {"tipo": tipo, "resultado": datos.resultado})
    bd.commit()
    return _salida(bd, _reunion(bd, i.reunion_id))


# ---------------------------------------------------------------- asistentes

class UsuarioBreve(BaseModel):
    id: int
    nombre: str
    puesto: str | None
    area: str | None


@router.get("/usuarios", response_model=list[UsuarioBreve])
def usuarios(q: str = Query("", max_length=100), _: Contexto = Depends(requiere(VER)),
             bd: Session = Depends(obtener_bd)) -> list[UsuarioBreve]:
    """Colaboradores de SMN con cuenta, para elegir a los asistentes."""
    consulta = select(Usuario).where(Usuario.tipo == "interno", Usuario.estatus == "activo")
    if q.strip():
        t = f"%{q.strip()}%"
        consulta = consulta.where(or_(Usuario.nombre.like(t), Usuario.puesto.like(t), Usuario.area.like(t)))
    return [UsuarioBreve(id=u.usuario_id, nombre=u.nombre, puesto=u.puesto, area=u.area)
            for u in bd.scalars(consulta.order_by(Usuario.nombre).limit(20))]


class NuevoAsistente(BaseModel):
    usuario_id: int | None = None
    nombre: str | None = Field(None, max_length=200)
    puesto: str | None = Field(None, max_length=120)


@router.post("/reuniones/{reunion_id}/asistentes", response_model=ReunionSalida, status_code=status.HTTP_201_CREATED)
def agregar_asistente(reunion_id: int, datos: NuevoAsistente, request: Request,
                      ctx: Contexto = Depends(_alguno(PREFILTRAR, DECIDIR)), bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    r = _reunion(bd, reunion_id)
    _en(r, "abierta", "prefiltro", "comite", que="Registrar asistentes")
    if datos.usuario_id:
        u = bd.get(Usuario, datos.usuario_id)
        if not u or u.tipo != "interno":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese colaborador.")
        if any(a.usuario_id == u.usuario_id for a in r.asistentes):
            raise HTTPException(status.HTTP_409_CONFLICT, f"{u.nombre} ya está en la lista.")
        nombre, puesto = u.nombre, _texto(datos.puesto) or u.puesto
    else:
        nombre, puesto = _texto(datos.nombre), _texto(datos.puesto)
        if not nombre or len(nombre) < 2:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige a un colaborador o escribe el nombre.")
    a = ComiteAsistente(reunion_id=r.reunion_id, usuario_id=datos.usuario_id, nombre=nombre, puesto=puesto,
                        agregado_en=ahora())
    r.asistentes.append(a)
    bd.flush()
    _bitacora(bd, "asistente", ctx, request, "comite_reunion", r.reunion_id, {"asistente": a.asistente_id})
    bd.commit()
    return _salida(bd, r)


@router.delete("/asistentes/{asistente_id}", response_model=ReunionSalida)
def quitar_asistente(asistente_id: int, request: Request, ctx: Contexto = Depends(_alguno(PREFILTRAR, DECIDIR)),
                     bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    a = bd.get(ComiteAsistente, asistente_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese asistente.")
    r = _reunion(bd, a.reunion_id)
    _en(r, "abierta", "prefiltro", "comite", que="Quitar asistentes")
    if bd.scalar(select(ComitePeticion.peticion_id).where(ComitePeticion.asistente_id == asistente_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa persona tiene peticiones registradas; no se puede quitar.")
    _bitacora(bd, "quitar_asistente", ctx, request, "comite_reunion", r.reunion_id, {"asistente": asistente_id})
    r.asistentes.remove(a)
    bd.commit()
    return _salida(bd, r)


# ---------------------------------------------------------------- peticiones

class NuevaPeticion(BaseModel):
    texto: str = Field(min_length=2, max_length=1000)
    item_id: int | None = None
    asistente_id: int | None = None


@router.post("/reuniones/{reunion_id}/peticiones", response_model=ReunionSalida, status_code=status.HTTP_201_CREATED)
def pedir(reunion_id: int, datos: NuevaPeticion, request: Request, ctx: Contexto = Depends(_alguno(PREFILTRAR, DECIDIR)),
          bd: Session = Depends(obtener_bd)) -> ReunionSalida:
    r = _reunion(bd, reunion_id)
    _en(r, "prefiltro", "comite", que="Anotar peticiones")
    if datos.item_id and not any(i.item_id == datos.item_id for i in r.productos):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ese producto no está en esta reunión.")
    if datos.asistente_id and not any(a.asistente_id == datos.asistente_id for a in r.asistentes):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esa persona no está en la lista de asistentes.")
    texto = _texto(datos.texto)
    if not texto:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe qué se pidió.")
    p = ComitePeticion(reunion_id=r.reunion_id, item_id=datos.item_id, asistente_id=datos.asistente_id, texto=texto,
                       estado="abierta", creada_por=ctx.usuario.usuario_id, creada_en=ahora())
    bd.add(p)
    bd.flush()
    _bitacora(bd, "peticion", ctx, request, "comite_peticion", p.peticion_id, {"reunion": r.reunion_id})
    bd.commit()
    return _salida(bd, r)


class CambioPeticion(BaseModel):
    estado: Literal["abierta", "atendida"]
    respuesta: str | None = Field(None, max_length=1000)


@router.patch("/peticiones/{peticion_id}", response_model=PeticionSalida)
def atender(peticion_id: int, datos: CambioPeticion, request: Request,
            ctx: Contexto = Depends(_alguno(PREFILTRAR, DECIDIR)), bd: Session = Depends(obtener_bd)) -> PeticionSalida:
    """Se atiende también después de cerrar la reunión: para eso es el seguimiento."""
    p = bd.get(ComitePeticion, peticion_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa petición.")
    p.estado, p.respuesta = datos.estado, _texto(datos.respuesta)
    p.atendida_por, p.atendida_en = (ctx.usuario.usuario_id, ahora()) if datos.estado == "atendida" else (None, None)
    _bitacora(bd, "atender", ctx, request, "comite_peticion", p.peticion_id, {"estado": datos.estado})
    bd.commit()
    return _peticiones(bd, [p])[0]


@router.get("/peticiones", response_model=list[PeticionSalida])
def peticiones(estado: Literal["abierta", "atendida"] | None = None, _: Contexto = Depends(requiere(VER)),
               bd: Session = Depends(obtener_bd)) -> list[PeticionSalida]:
    """Las peticiones de todas las reuniones, para verificar que se atiendan."""
    q = select(ComitePeticion)
    if estado:
        q = q.where(ComitePeticion.estado == estado)
    return _peticiones(bd, list(bd.scalars(q.order_by(ComitePeticion.peticion_id.desc()).limit(500))))


# ---------------------------------------------------------------- aceptados y sus revisiones

class Aceptado(BaseModel):
    reunion_id: int
    fecha_reunion: date
    producto: ItemSalida


@router.get("/aceptados", response_model=list[Aceptado])
def aceptados(_: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> list[Aceptado]:
    """Los aceptados de todas las reuniones, con su revisión de inventario y regulación si aplica."""
    filas = list(bd.scalars(select(ComiteProducto).where(ComiteProducto.decision == "aceptado")
                            .order_by(ComiteProducto.decision_en.desc()).limit(300)))
    fechas = dict(bd.execute(select(ComiteReunion.reunion_id, ComiteReunion.fecha).where(
        ComiteReunion.reunion_id.in_({i.reunion_id for i in filas} or {0}))).all())
    return [Aceptado(reunion_id=i.reunion_id, fecha_reunion=fechas[i.reunion_id], producto=x)
            for i, x in zip(filas, _items(bd, filas))]


# ---------------------------------------------------------------- asistente de IA por producto

class Turno(BaseModel):
    pregunta: str = Field(max_length=500)
    respuesta: str = Field(max_length=2000)


class PreguntaEntrada(BaseModel):
    pregunta: str = Field(min_length=3, max_length=500)
    historial: list[Turno] = Field(default_factory=list, max_length=10)


class Fuente(BaseModel):
    numero: int
    titulo: str


class RespuestaAsistente(BaseModel):
    texto: str
    encontrada: bool
    fuentes: list[Fuente]
    aviso: str | None = None


class ParecidoSalida(BaseModel):
    producto_id: int
    sku: str
    descripcion: str | None
    marca: str | None
    imagen: str | None
    precio: Decimal | None
    al_mes: float | None
    tiendas: int | None
    por_tienda_mes: float | None
    cambio: float | None


class Parecidos(BaseModel):
    ventana: str | None  # de qué periodo es la venta; None si no hay ventas cargadas
    productos: list[ParecidoSalida]


@router.get("/productos/{item_id}/parecidos", response_model=Parecidos)
def parecidos(item_id: int, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> Parecidos:
    """Para la diapositiva: los parecidos que ya vendemos con su precio y su venta real, junto al producto nuevo."""
    from modulos.compras import asistente_comite as ac

    i = _item(bd, item_id)
    e = rp.vigente(bd, propuesta_id=i.propuesta_id) if i.propuesta_id else rp.vigente(bd, idea_id=i.idea_id)
    if not e or e.estado != "lista":
        return Parecidos(ventana=None, productos=[])
    ventana, filas = ac.parecidos_con_venta(bd, e, n=3)
    return Parecidos(ventana=ventana, productos=[ParecidoSalida(
        producto_id=x.producto.producto_id, sku=x.producto.sku, descripcion=x.producto.descripcion, marca=x.producto.marca,
        imagen=x.producto.liga_imagen or x.producto.imagen_cdn, precio=x.precio, al_mes=x.al_mes, tiendas=x.tiendas,
        por_tienda_mes=x.por_tienda_mes, cambio=x.cambio) for x in filas])


@router.post("/productos/{item_id}/preguntar", response_model=RespuestaAsistente)
def preguntar(item_id: int, datos: PreguntaEntrada, ctx: Contexto = Depends(requiere(VER)),
              bd: Session = Depends(obtener_bd)) -> RespuestaAsistente:
    """Pregunta sobre un producto del comité. Solo IA local; contesta con la ficha del producto y dice de dónde sale."""
    from ia import puerta
    from modulos.compras import asistente_comite as ac

    item = _item(bd, item_id)
    pregunta = _texto(datos.pregunta)
    if not pregunta:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe la pregunta.")
    try:
        r = ac.preguntar(bd, ctx.usuario.usuario_id, item, _items(bd, [item])[0].model_dump(), pregunta,
                         [t.model_dump() for t in datos.historial])
    except puerta.ErrorIA as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    return RespuestaAsistente(texto=r.texto, encontrada=r.encontrada, fuentes=[Fuente(**f) for f in r.fuentes], aviso=r.aviso)
