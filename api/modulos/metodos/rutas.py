"""Métodos y procedimientos (/api/metodos): preguntar con cita, documentos y versiones, borradores de la IA local,
avisos, sugerencias, reporte del mes y prueba de preguntas. Pedido de Diego, 2026-10-30."""
import json
from datetime import date, datetime
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import false, func, select, true
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, ip_de, requiere, usuario_actual
from ia import puerta
from modulos.metodos import documentos as docs_
from modulos.metodos import diagrama, flujo as flujo_, indice, pdf, redaccion, respuestas, revision
from modulos.metodos.modelos import Alerta, Borrador, Documento, Fragmento, Pregunta, PruebaCorrida, PruebaPregunta
from nucleo.archivos import _raiz
from nucleo.bitacora import registrar
from nucleo.modelos import Archivo, IaTarea, Modulo, Rol, Usuario, ahora

router = APIRouter(prefix="/api/metodos", tags=["métodos y procedimientos"])
CONSULTAR, CARGAR, APROBAR = "metodos.consultar", "metodos.cargar", "metodos.aprobar"
TipoDoc = Literal["manual", "politica", "instructivo", "formato", "preguntas", "otro"]


def _bitacora(bd: Session, accion: str, ctx: Contexto, request: Request, entidad: str, entidad_id,
              detalle: dict | None = None) -> None:
    modulo_id = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "metodos"))
    registrar(bd, accion, usuario_id=ctx.usuario.usuario_id, modulo_id=modulo_id, entidad=entidad,
              entidad_id=entidad_id, detalle=detalle, ip=ip_de(request))


def _nombre(bd: Session, usuario_id: int | None) -> str | None:
    return bd.scalar(select(Usuario.nombre).where(Usuario.usuario_id == usuario_id)) if usuario_id else None


def _visible(bd: Session, ctx: Contexto, d: Documento) -> bool:
    return indice.puede_ver(set(json.loads(d.roles)) if d.roles else set(), d.permiso, ctx, indice.roles_de(bd, ctx))


def _documento(bd: Session, ctx: Contexto, documento_id: int) -> Documento:
    d = bd.get(Documento, documento_id)
    if not d or not _visible(bd, ctx, d) or (d.estado != "vigente" and not ctx.puede(CARGAR)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese documento.")
    return d


def _del_area(ctx: Contexto, area: str) -> None:
    """Aprueba el área dueña: si la persona tiene área en su perfil, debe ser la del documento."""
    mia = (ctx.usuario.area or "").strip().lower()
    if mia and mia != area.strip().lower() and not ctx.puede("nucleo.modulos.administrar"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Lo aprueba el área dueña ({area}). Tu perfil dice que eres de {ctx.usuario.area}.")


# ---------------------------------------------------------------- estado

class Estado(BaseModel):
    documentos: int
    fragmentos: int
    con_huella: int
    ollama: bool
    modelo_huella: str | None
    modelo_respuesta: str | None
    huellas_en_curso: bool
    contradicciones_en_curso: bool
    puede_cargar: bool
    puede_aprobar: bool
    areas: list[str]
    roles: list[dict]


@router.get("/estado", response_model=Estado)
def estado(ctx: Contexto = Depends(requiere(CONSULTAR)), bd: Session = Depends(obtener_bd)) -> Estado:
    vigentes = select(Documento.documento_id).where(Documento.estado == "vigente")
    fila = bd.execute(select(func.count(Fragmento.fragmento_id), func.count(Fragmento.vector))
                      .where(Fragmento.documento_id.in_(vigentes))).one()
    tareas = {t.codigo: t for t in bd.scalars(select(IaTarea).where(IaTarea.codigo.like("metodos.%")))}
    from core.config import configuracion

    def modelo(codigo):
        t = tareas.get(codigo)
        return (t.modelo or configuracion().ollama_modelo or None) if t else None
    return Estado(
        documentos=bd.scalar(select(func.count()).select_from(vigentes.subquery())), fragmentos=fila[0], con_huella=fila[1],
        ollama=puerta.estado_ollama()["disponible"], modelo_huella=tareas[indice.TAREA_HUELLA].modelo
        if indice.TAREA_HUELLA in tareas else None, modelo_respuesta=modelo(respuestas.TAREA_RESPONDER),
        huellas_en_curso=revision.corriendo("huellas"), contradicciones_en_curso=revision.corriendo("contradicciones"),
        puede_cargar=ctx.puede(CARGAR), puede_aprobar=ctx.puede(APROBAR),
        areas=sorted({a for a in bd.scalars(select(Documento.area).distinct()) if a}),
        roles=[{"codigo": r.codigo, "nombre": r.nombre} for r in bd.scalars(
            select(Rol).where(Rol.para_tipo_usuario == "interno").order_by(Rol.nombre))],
    )


# ---------------------------------------------------------------- preguntar

class PideRespuesta(BaseModel):
    pregunta: str = Field(min_length=3, max_length=1000)
    origen: str | None = Field(None, max_length=60)


class CitaSalida(BaseModel):
    numero: int
    fragmento_id: int
    documento_id: int
    titulo: str
    clave: str | None
    version: str
    vigente_desde: str | None
    area: str
    seccion: str | None
    pagina: int | None
    extracto: str


class RespuestaSalida(BaseModel):
    pregunta_id: int
    texto: str
    encontrada: bool
    modo: str
    citas: list[CitaSalida]
    preguntar_a: str | None
    aviso: str | None
    duracion_ms: int


@router.post("/preguntar", response_model=RespuestaSalida)
def preguntar(datos: PideRespuesta, ctx: Contexto = Depends(requiere(CONSULTAR)),
              bd: Session = Depends(obtener_bd)) -> RespuestaSalida:
    r = respuestas.responder(bd, ctx, datos.pregunta.strip(), origen=datos.origen)
    return RespuestaSalida(pregunta_id=r.pregunta_id, texto=r.texto, encontrada=r.encontrada, modo=r.modo,
                           citas=[CitaSalida(**c.__dict__) for c in r.citas], preguntar_a=r.preguntar_a, aviso=r.aviso,
                           duracion_ms=r.duracion_ms)


class Calificacion(BaseModel):
    util: bool
    comentario: str | None = Field(None, max_length=500)


@router.patch("/preguntas/{pregunta_id}", status_code=status.HTTP_204_NO_CONTENT)
def calificar(pregunta_id: int, datos: Calificacion, ctx: Contexto = Depends(requiere(CONSULTAR)),
              bd: Session = Depends(obtener_bd)) -> None:
    p = bd.get(Pregunta, pregunta_id)
    if not p or p.usuario_id != ctx.usuario.usuario_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa pregunta.")
    p.util, p.comentario = datos.util, (datos.comentario or "").strip() or None
    bd.commit()


class PreguntaSalida(BaseModel):
    id: int
    texto: str
    encontrada: bool
    util: bool | None
    creado_en: datetime


@router.get("/preguntas/mias", response_model=list[PreguntaSalida])
def mis_preguntas(ctx: Contexto = Depends(requiere(CONSULTAR)), bd: Session = Depends(obtener_bd)) -> list[PreguntaSalida]:
    filas = bd.scalars(select(Pregunta).where(Pregunta.usuario_id == ctx.usuario.usuario_id, Pregunta.es_prueba == false())
                       .order_by(Pregunta.pregunta_id.desc()).limit(15))
    return [PreguntaSalida(id=p.pregunta_id, texto=p.texto, encontrada=p.encontrada, util=p.util, creado_en=p.creado_en)
            for p in filas]


# ---------------------------------------------------------------- documentos

class DocumentoSalida(BaseModel):
    id: int
    clave: str | None
    titulo: str
    tipo: str
    area: str
    version: str
    vigente_desde: date | None
    revisar_antes: date | None
    sistema: str | None
    roles: list[str]
    estado: str
    origen: str
    reemplaza_a: int | None
    fragmentos: int
    con_huella: int
    avisos: list[str]
    viejo: str | None
    archivo: str | None
    cargado_por: str | None
    cargado_en: datetime
    aprobado_por: str | None
    aprobado_en: datetime | None


def _salida(bd: Session, d: Documento, cuentas: dict | None = None) -> DocumentoSalida:
    if cuentas is None:
        fila = bd.execute(select(func.count(Fragmento.fragmento_id), func.count(Fragmento.vector))
                          .where(Fragmento.documento_id == d.documento_id)).one()
        cuentas = {d.documento_id: tuple(fila)}
    n, h = cuentas.get(d.documento_id, (0, 0))
    archivo = bd.scalar(select(Archivo.nombre_original).where(Archivo.archivo_id == d.archivo_id)) if d.archivo_id else None
    return DocumentoSalida(
        id=d.documento_id, clave=d.clave, titulo=d.titulo, tipo=d.tipo, area=d.area, version=d.version,
        vigente_desde=d.vigente_desde, revisar_antes=d.revisar_antes, sistema=d.sistema,
        roles=json.loads(d.roles) if d.roles else [], estado=d.estado, origen=d.origen, reemplaza_a=d.reemplaza_a,
        fragmentos=n, con_huella=h, avisos=docs_.avisos_en_palabras(d),
        viejo=docs_.viejo(d) if d.estado == "vigente" and d.origen in ("cargado", "ia") else None,
        archivo=archivo or (f"{d.titulo}.docx" if d.origen == "ia" else None),
        cargado_por=_nombre(bd, d.cargado_por), cargado_en=d.cargado_en, aprobado_por=_nombre(bd, d.aprobado_por),
        aprobado_en=d.aprobado_en)


@router.get("/documentos", response_model=list[DocumentoSalida])
def documentos(todos: bool = False, ctx: Contexto = Depends(requiere(CONSULTAR)),
               bd: Session = Depends(obtener_bd)) -> list[DocumentoSalida]:
    q = select(Documento).order_by(Documento.area, Documento.titulo, Documento.documento_id.desc())
    if not (todos and ctx.puede(CARGAR)):
        q = q.where(Documento.estado == "vigente")
    filas = [d for d in bd.scalars(q) if _visible(bd, ctx, d)]
    cuentas = {did: (n, h) for did, n, h in bd.execute(
        select(Fragmento.documento_id, func.count(Fragmento.fragmento_id), func.count(Fragmento.vector))
        .group_by(Fragmento.documento_id))}
    return [_salida(bd, d, cuentas) for d in filas]


class FragmentoSalida(BaseModel):
    id: int
    orden: int
    seccion: str | None
    pagina: int | None
    texto: str
    con_huella: bool


class DocumentoDetalle(DocumentoSalida):
    secciones: list[FragmentoSalida]
    versiones: list[DocumentoSalida]
    diagrama_svg: str | None
    pdf: bool


@router.get("/documentos/{documento_id}", response_model=DocumentoDetalle)
def documento(documento_id: int, ctx: Contexto = Depends(requiere(CONSULTAR)),
              bd: Session = Depends(obtener_bd)) -> DocumentoDetalle:
    d = _documento(bd, ctx, documento_id)
    # todas las versiones: hacia atrás por «reemplaza_a» y hacia adelante por quien lo reemplazó
    cadena, actual = [], d
    while actual.reemplaza_a and (anterior := bd.get(Documento, actual.reemplaza_a)) and len(cadena) < 50:
        cadena.append(anterior)
        actual = anterior
    siguiente = d
    while (nuevo := bd.scalar(select(Documento).where(Documento.reemplaza_a == siguiente.documento_id))) and len(cadena) < 100:
        cadena.insert(0, nuevo)
        siguiente = nuevo
    base = _salida(bd, d)
    return DocumentoDetalle(
        **base.model_dump(),
        secciones=[FragmentoSalida(id=f.fragmento_id, orden=f.orden, seccion=f.seccion, pagina=f.pagina, texto=f.texto,
                                   con_huella=f.vector is not None) for f in d.fragmentos],
        versiones=[_salida(bd, v) for v in cadena if ctx.puede(CARGAR) or v.estado == "vigente"],
        diagrama_svg=_svg(flujo_.cargar(d.flujo)), pdf=d.origen == "ia",
    )


def _svg(f: dict | None) -> str | None:
    return diagrama.svg(diagrama.dibujo(f)) if f and f.get("pasos") else None


def _png(f: dict | None) -> bytes | None:
    return diagrama.png(diagrama.dibujo(f)) if f and f.get("pasos") else None


def _descarga(contenido: bytes, nombre: str, tipo: str) -> Response:
    return Response(contenido, media_type=tipo, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}"})


PDF_TIPO = "application/pdf"
WORD_TIPO = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _pie_publicado(bd: Session, d: Documento) -> str:
    return (f"Versión {d.version}, vigente desde {d.vigente_desde:%d/%m/%Y}. Hecho con la IA local de SMN y aprobado por "
            f"{_nombre(bd, d.aprobado_por) or 'el área dueña'} ({d.area}).")


@router.get("/documentos/{documento_id}/pdf")
def documento_pdf(documento_id: int, ctx: Contexto = Depends(requiere(CONSULTAR)), bd: Session = Depends(obtener_bd)) -> Response:
    d = _documento(bd, ctx, documento_id)
    if d.origen != "ia":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este documento se descarga como se cargó.")
    contenido = pdf.manual(pdf.Datos(
        titulo=d.titulo, texto=d.texto or "", flujo=flujo_.cargar(d.flujo), area=d.area, version=d.version, clave=d.clave,
        vigente_desde=d.vigente_desde, sistema=d.sistema, aprobado_por=_nombre(bd, d.aprobado_por),
        aprobado_en=d.aprobado_en, pie=_pie_publicado(bd, d)))
    return _descarga(contenido, f"{d.titulo[:120]} v{d.version}.pdf", PDF_TIPO)


@router.get("/documentos/{documento_id}/archivo")
def archivo(documento_id: int, ctx: Contexto = Depends(requiere(CONSULTAR)), bd: Session = Depends(obtener_bd)):
    d = _documento(bd, ctx, documento_id)
    if d.origen == "ia":
        contenido = redaccion.word(d.titulo, d.texto or "", _pie_publicado(bd, d), _png(flujo_.cargar(d.flujo)))
        return _descarga(contenido, f"{d.titulo[:120]}.docx", WORD_TIPO)
    a = bd.get(Archivo, d.archivo_id) if d.archivo_id else None
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este documento vive en otra base; ábrelo desde su módulo.")
    raiz = _raiz()
    ruta = (raiz / a.ruta_almacenamiento).resolve()
    if raiz not in ruta.parents or not ruta.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El archivo ya no está en el almacén.")
    return FileResponse(ruta, media_type=a.tipo_contenido, filename=a.nombre_original,
                        headers={"X-Content-Type-Options": "nosniff"})


class DocumentoEntrada(BaseModel):
    archivo_id: int
    titulo: str = Field(min_length=3, max_length=300)
    tipo: TipoDoc = "manual"
    area: str = Field(min_length=2, max_length=120)
    version: str = Field(min_length=1, max_length=30)
    vigente_desde: date | None = None
    revisar_antes: date | None = None
    clave: str | None = Field(None, max_length=40)
    sistema: str | None = Field(None, max_length=120)
    roles: list[str] = Field(default_factory=list, max_length=60)
    reemplaza_a: int | None = None


class Cargado(BaseModel):
    documento: DocumentoSalida
    fragmentos: int
    con_huella: int
    datos_personales: dict[str, int]


def _limpio(texto: str | None) -> str | None:
    return (texto or "").strip() or None


@router.post("/documentos", response_model=Cargado, status_code=status.HTTP_201_CREATED)
def cargar(datos: DocumentoEntrada, request: Request, ctx: Contexto = Depends(requiere(CARGAR)),
           bd: Session = Depends(obtener_bd)) -> Cargado:
    a = bd.get(Archivo, datos.archivo_id)
    if not a or a.subido_por != ctx.usuario.usuario_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese archivo.")
    if bd.scalar(select(Documento.documento_id).join(Archivo, Archivo.archivo_id == Documento.archivo_id).where(
            Archivo.sha256 == a.sha256, Documento.estado == "vigente")):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese mismo archivo ya está cargado y vigente.")
    reemplaza = None
    if datos.reemplaza_a:
        reemplaza = bd.get(Documento, datos.reemplaza_a)
        if not reemplaza or reemplaza.estado != "vigente" or reemplaza.origen not in ("cargado", "ia"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe la versión vigente que quieres reemplazar.")
    validos = set(bd.scalars(select(Rol.codigo)))
    if desconocidos := [r for r in datos.roles if r not in validos]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"No existen los roles: {', '.join(desconocidos)}.")
    if not a.modulo_id:
        a.modulo_id = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "metodos"))
    a.entidad = "metodos_documento"
    d, resumen = docs_.cargar(
        bd, archivo=a, titulo=datos.titulo.strip(), tipo=datos.tipo, area=datos.area.strip(), version=datos.version.strip(),
        vigente_desde=datos.vigente_desde or date.today(), revisar_antes=datos.revisar_antes, clave=_limpio(datos.clave),
        sistema=_limpio(datos.sistema), roles=datos.roles, usuario_id=ctx.usuario.usuario_id, reemplaza=reemplaza)
    a.entidad_id = str(d.documento_id)
    _bitacora(bd, "metodos_documento_cargar", ctx, request, "metodos_documento", d.documento_id,
              {"titulo": d.titulo, "version": d.version, "reemplaza_a": d.reemplaza_a, **resumen})
    bd.commit()
    return Cargado(documento=_salida(bd, d), fragmentos=resumen["fragmentos"], con_huella=resumen["con_huella"],
                   datos_personales=resumen["datos_personales"])


class DocumentoCambio(BaseModel):
    titulo: str | None = Field(None, min_length=3, max_length=300)
    tipo: TipoDoc | None = None
    area: str | None = Field(None, min_length=2, max_length=120)
    revisar_antes: date | None = None
    clave: str | None = Field(None, max_length=40)
    sistema: str | None = Field(None, max_length=120)
    roles: list[str] | None = Field(None, max_length=60)


@router.patch("/documentos/{documento_id}", response_model=DocumentoSalida)
def cambiar(documento_id: int, datos: DocumentoCambio, request: Request, ctx: Contexto = Depends(requiere(CARGAR)),
            bd: Session = Depends(obtener_bd)) -> DocumentoSalida:
    d = _documento(bd, ctx, documento_id)
    if d.origen in ("compras", "fiscal"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Este documento se cambia en su módulo de origen.")
    cambios = datos.model_dump(exclude_unset=True)
    if "roles" in cambios:
        validos = set(bd.scalars(select(Rol.codigo)))
        if desconocidos := [r for r in cambios["roles"] or [] if r not in validos]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"No existen los roles: {', '.join(desconocidos)}.")
        cambios["roles"] = json.dumps(sorted(set(cambios["roles"]))) if cambios["roles"] else None
    for campo, valor in cambios.items():
        setattr(d, campo, valor.strip() if isinstance(valor, str) else valor)
    if {"titulo", "roles"} & cambios.keys():
        indice.olvidar_cache()
    _bitacora(bd, "metodos_documento_cambiar", ctx, request, "metodos_documento", d.documento_id,
              {k: (v if not isinstance(v, date) else v.isoformat()) for k, v in cambios.items()})
    bd.commit()
    return _salida(bd, d)


class Nota(BaseModel):
    nota: str | None = Field(None, max_length=1000)


@router.post("/documentos/{documento_id}/retirar", response_model=DocumentoSalida)
def retirar(documento_id: int, datos: Nota, request: Request, ctx: Contexto = Depends(requiere(APROBAR)),
            bd: Session = Depends(obtener_bd)) -> DocumentoSalida:
    d = _documento(bd, ctx, documento_id)
    if d.origen in ("compras", "fiscal"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Este documento se retira en su módulo de origen.")
    if d.estado != "vigente":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese documento ya no está vigente.")
    _del_area(ctx, d.area)
    d.estado = "retirado"
    indice.olvidar_cache()
    _bitacora(bd, "metodos_documento_retirar", ctx, request, "metodos_documento", d.documento_id, {"nota": datos.nota})
    bd.commit()
    return _salida(bd, d)


@router.post("/documentos/{documento_id}/releer", response_model=DocumentoSalida)
def releer(documento_id: int, ctx: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> DocumentoSalida:
    d = _documento(bd, ctx, documento_id)
    try:
        docs_.reindexar(bd, d, ctx.usuario.usuario_id)
    except docs_.ErrorDocumento as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    bd.commit()
    return _salida(bd, d)


@router.post("/huellas", status_code=status.HTTP_202_ACCEPTED)
def huellas(ctx: Contexto = Depends(requiere(CARGAR))) -> dict:
    """Saca la huella de los fragmentos que no la tienen (por ejemplo, los que se cargaron con Ollama apagado)."""
    if not puerta.estado_ollama()["disponible"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ollama no está prendido; la huella de significado se saca con él.")
    revision.en_segundo_plano("huellas", revision.completar_huellas, ctx.usuario.usuario_id)
    return {"en_curso": True}


@router.post("/sincronizar")
def sincronizar(request: Request, ctx: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> dict:
    cuenta = docs_.sincronizar_otras_bases(bd)
    _bitacora(bd, "metodos_sincronizar", ctx, request, "metodos_documento", None, cuenta)
    bd.commit()
    return cuenta


# ---------------------------------------------------------------- borradores

class BorradorEntrada(BaseModel):
    tipo: Literal["nuevo", "actualizacion", "formato"]
    documento_id: int | None = None
    titulo: str | None = Field(None, min_length=3, max_length=300)
    area: str | None = Field(None, min_length=2, max_length=120)
    instrucciones: str | None = Field(None, max_length=20_000)
    fuentes: list[int] = Field(default_factory=list, max_length=5)
    archivos: list[int] = Field(default_factory=list, max_length=5)  # subidos solo como apoyo, no se publican


class BorradorSalida(BaseModel):
    id: int
    tipo: str
    documento_id: int | None
    documento: str | None
    version_anterior: str | None
    titulo: str
    area: str
    estado: str
    error: str | None
    creado_por: str | None
    creado_en: datetime
    revisado_por: str | None
    revisado_en: datetime | None
    publicado_id: int | None


class BorradorDetalle(BorradorSalida):
    instrucciones: str | None
    fuentes: list[dict]
    texto: str | None
    texto_anterior: str | None
    cambios: list[dict]
    preguntas_abiertas: list[str]
    nota: str | None
    version_sugerida: str
    archivos: list[dict]
    flujo: dict | None
    diagrama_svg: str | None


def _borrador_salida(bd: Session, b: Borrador) -> BorradorSalida:
    return BorradorSalida(id=b.borrador_id, tipo=b.tipo, documento_id=b.documento_id,
                          documento=b.documento.titulo if b.documento else None,
                          version_anterior=b.documento.version if b.documento else None, titulo=b.titulo, area=b.area,
                          estado=b.estado, error=b.error, creado_por=_nombre(bd, b.creado_por), creado_en=b.creado_en,
                          revisado_por=_nombre(bd, b.revisado_por), revisado_en=b.revisado_en, publicado_id=b.publicado_id)


def _borrador(bd: Session, borrador_id: int) -> Borrador:
    b = bd.get(Borrador, borrador_id)
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese borrador.")
    return b


@router.get("/borradores", response_model=list[BorradorSalida])
def borradores(_: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> list[BorradorSalida]:
    return [_borrador_salida(bd, b) for b in bd.scalars(select(Borrador).order_by(Borrador.borrador_id.desc()).limit(100))]


@router.post("/borradores", response_model=BorradorSalida, status_code=status.HTTP_201_CREATED)
def nuevo_borrador(datos: BorradorEntrada, request: Request, ctx: Contexto = Depends(requiere(CARGAR)),
                   bd: Session = Depends(obtener_bd)) -> BorradorSalida:
    base = None
    if datos.tipo == "nuevo":
        if not (datos.titulo and datos.area and ((datos.instrucciones or "").strip() or datos.archivos)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Para un manual nuevo pon el título, el área dueña y cómo se hace hoy (escrito o en archivos).")
    else:
        base = _documento(bd, ctx, datos.documento_id or 0)
        if base.estado != "vigente" or base.origen not in ("cargado", "ia") or not base.texto:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ese documento no está vigente o no tiene texto que se pueda leer.")
        if datos.tipo == "actualizacion" and not (datos.instrucciones or "").strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Escribe qué cambió en el proceso.")
    fuentes = [f for f in dict.fromkeys(datos.fuentes) if f != datos.documento_id]
    for f in fuentes:
        _documento(bd, ctx, f)
    archivos = list(dict.fromkeys(datos.archivos))
    for aid in archivos:
        a = bd.get(Archivo, aid)
        if not a or a.subido_por != ctx.usuario.usuario_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontré uno de los archivos de apoyo; vuelve a subirlo.")
    if not puerta.estado_ollama()["disponible"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "La IA local (Ollama) no está prendida; sin ella no se puede redactar.")
    b = Borrador(tipo=datos.tipo, documento_id=base.documento_id if base else None,
                 titulo=(datos.titulo or (base.titulo if base else "")).strip(),
                 area=(datos.area or (base.area if base else "")).strip(), instrucciones=_limpio(datos.instrucciones),
                 fuentes=json.dumps(fuentes) if fuentes else None, archivos=json.dumps(archivos) if archivos else None,
                 estado="generando", creado_por=ctx.usuario.usuario_id)
    bd.add(b)
    bd.flush()
    _bitacora(bd, "metodos_borrador_pedir", ctx, request, "metodos_borrador", b.borrador_id,
              {"tipo": b.tipo, "documento_id": b.documento_id, "fuentes": fuentes, "archivos": archivos})
    bd.commit()
    redaccion.redactar_aparte(b.borrador_id)
    return _borrador_salida(bd, b)


@router.get("/borradores/{borrador_id}", response_model=BorradorDetalle)
def borrador(borrador_id: int, ctx: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> BorradorDetalle:
    b = _borrador(bd, borrador_id)
    fuentes = [{"id": d.documento_id, "titulo": d.titulo, "version": d.version}
               for f in json.loads(b.fuentes or "[]") if (d := bd.get(Documento, f))]
    return BorradorDetalle(
        **_borrador_salida(bd, b).model_dump(), instrucciones=b.instrucciones, fuentes=fuentes, texto=b.texto,
        texto_anterior=b.documento.texto if b.documento else None, cambios=json.loads(b.cambios or "[]"),
        preguntas_abiertas=json.loads(b.preguntas_abiertas or "[]"), nota=b.nota,
        version_sugerida=docs_.siguiente_version(b.documento.version if b.documento else None),
        archivos=[{"id": a.archivo_id, "nombre": a.nombre_original}
                  for aid in json.loads(b.archivos or "[]") if (a := bd.get(Archivo, aid))],
        flujo=flujo_.cargar(b.flujo), diagrama_svg=_svg(flujo_.cargar(b.flujo)))


class Aprobacion(BaseModel):
    version: str = Field(min_length=1, max_length=30)
    rechazados: list[int] = Field(default_factory=list, max_length=2000)
    texto: str | None = Field(None, max_length=200_000)  # el área puede corregir el borrador antes de aprobarlo
    nota: str | None = Field(None, max_length=1000)
    tipo: TipoDoc = "manual"


@router.post("/borradores/{borrador_id}/aprobar", response_model=BorradorSalida)
def aprobar(borrador_id: int, datos: Aprobacion, request: Request, ctx: Contexto = Depends(requiere(APROBAR)),
            bd: Session = Depends(obtener_bd)) -> BorradorSalida:
    b = _borrador(bd, borrador_id)
    if b.estado != "listo":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se aprueba un borrador listo.")
    _del_area(ctx, b.area)
    base = b.documento
    if base and base.estado != "vigente":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "El manual cambió mientras se revisaba el borrador; pide un borrador nuevo sobre la versión vigente.")
    if datos.texto is not None:
        texto = datos.texto.strip()
    elif base:
        texto = redaccion.aplicar(base.texto or "", b.texto or "", set(datos.rechazados))
    else:
        texto = b.texto or ""
    if pendientes := redaccion.PREGUNTA.findall(texto):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Quedan {len(pendientes)} preguntas sin contestar en el texto ([PREGUNTA: …]). "
                            "Contéstalas o quítalas antes de aprobar.")
    if not texto:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El texto quedó vacío.")
    d = docs_.publicar_texto(bd, titulo=b.titulo, tipo=base.tipo if base else datos.tipo, area=b.area,
                             version=datos.version.strip(), texto=texto, usuario_id=b.creado_por or ctx.usuario.usuario_id,
                             aprobado_por=ctx.usuario.usuario_id, reemplaza=base, roles=base.roles if base else None,
                             clave=base.clave if base else None, sistema=base.sistema if base else None,
                             flujo=b.flujo)
    b.estado, b.revisado_por, b.revisado_en, b.nota, b.publicado_id = (
        "aprobado", ctx.usuario.usuario_id, ahora(), _limpio(datos.nota), d.documento_id)
    _bitacora(bd, "metodos_borrador_aprobar", ctx, request, "metodos_borrador", b.borrador_id,
              {"documento_id": d.documento_id, "version": d.version, "reemplaza_a": d.reemplaza_a,
               "rechazados": sorted(set(datos.rechazados)), "editado": datos.texto is not None})
    bd.commit()
    return _borrador_salida(bd, b)


@router.post("/borradores/{borrador_id}/descartar", response_model=BorradorSalida)
def descartar(borrador_id: int, datos: Nota, request: Request, ctx: Contexto = Depends(requiere(CARGAR)),
              bd: Session = Depends(obtener_bd)) -> BorradorSalida:
    b = _borrador(bd, borrador_id)
    if b.estado in ("aprobado", "descartado", "generando"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese borrador no se puede descartar ahora.")
    b.estado, b.revisado_por, b.revisado_en, b.nota = "descartado", ctx.usuario.usuario_id, ahora(), _limpio(datos.nota)
    _bitacora(bd, "metodos_borrador_descartar", ctx, request, "metodos_borrador", b.borrador_id, {"nota": b.nota})
    bd.commit()
    return _borrador_salida(bd, b)


@router.post("/borradores/{borrador_id}/reintentar", response_model=BorradorSalida)
def reintentar(borrador_id: int, ctx: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> BorradorSalida:
    b = _borrador(bd, borrador_id)
    if b.estado not in ("error", "listo"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese borrador no se puede volver a hacer.")
    if not puerta.estado_ollama()["disponible"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "La IA local (Ollama) no está prendida.")
    b.estado, b.error = "generando", None
    bd.commit()
    redaccion.redactar_aparte(b.borrador_id)
    return _borrador_salida(bd, b)


@router.get("/borradores/{borrador_id}/word")
def borrador_word(borrador_id: int, _: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> Response:
    b = _borrador(bd, borrador_id)
    if not b.texto:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El borrador todavía no tiene texto.")
    return _descarga(redaccion.word(b.titulo, b.texto, _pie_borrador(b), _png(flujo_.cargar(b.flujo))),
                     f"Borrador - {b.titulo[:110]}.docx", WORD_TIPO)


def _pie_borrador(b: Borrador) -> str:
    return f"BORRADOR hecho con la IA local de SMN el {b.creado_en:%d/%m/%Y}. No vale hasta que lo apruebe {b.area}."


@router.get("/borradores/{borrador_id}/pdf")
def borrador_pdf(borrador_id: int, _: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> Response:
    b = _borrador(bd, borrador_id)
    if not b.texto:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El borrador todavía no tiene texto.")
    base = b.documento
    contenido = pdf.manual(pdf.Datos(
        titulo=b.titulo, texto=b.texto, flujo=flujo_.cargar(b.flujo), area=b.area,
        version=docs_.siguiente_version(base.version if base else None), clave=base.clave if base else None,
        sistema=base.sistema if base else None, pie=_pie_borrador(b), borrador=True))
    return _descarga(contenido, f"Borrador - {b.titulo[:110]}.pdf", PDF_TIPO)


class FlujoEntrada(BaseModel):
    flujo: dict


class FlujoVista(BaseModel):
    flujo: dict
    svg: str


@router.post("/diagrama", response_model=FlujoVista)
def vista_diagrama(datos: FlujoEntrada, _: Contexto = Depends(requiere(CARGAR))) -> FlujoVista:
    """Revisa y dibuja un diagrama sin guardarlo; la pantalla lo usa mientras la persona corrige."""
    try:
        f = flujo_.validar(datos.flujo)
    except flujo_.FlujoInvalido as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return FlujoVista(flujo=f, svg=_svg(f) or "")


@router.put("/borradores/{borrador_id}/flujo", response_model=FlujoVista)
def guardar_flujo(borrador_id: int, datos: FlujoEntrada, request: Request, ctx: Contexto = Depends(requiere(CARGAR)),
                  bd: Session = Depends(obtener_bd)) -> FlujoVista:
    b = _borrador(bd, borrador_id)
    if b.estado != "listo":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se corrige el diagrama de un borrador listo.")
    try:
        f = flujo_.validar({**datos.flujo, "origen": "persona", "aviso": None})
    except flujo_.FlujoInvalido as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    b.flujo = json.dumps(f, ensure_ascii=False)
    _bitacora(bd, "metodos_borrador_diagrama", ctx, request, "metodos_borrador", b.borrador_id, {"pasos": len(f["pasos"])})
    bd.commit()
    return FlujoVista(flujo=f, svg=_svg(f) or "")


class Sacar(BaseModel):
    usar_ia: bool = True


@router.post("/borradores/{borrador_id}/flujo/sacar", response_model=FlujoVista)
def sacar_flujo(borrador_id: int, datos: Sacar, ctx: Contexto = Depends(requiere(CARGAR)),
                bd: Session = Depends(obtener_bd)) -> FlujoVista:
    """Vuelve a sacar el diagrama del texto del borrador (con la IA local o con los pasos numerados). No guarda."""
    b = _borrador(bd, borrador_id)
    if b.estado != "listo" or not b.texto:
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se saca el diagrama de un borrador listo.")
    usar_ia = datos.usar_ia and puerta.estado_ollama()["disponible"]
    f = flujo_.sacar(bd, b.texto, ctx.usuario.usuario_id, usar_ia=usar_ia)
    if not f:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "No encontré pasos en el texto para armar el diagrama. Agrégalos a mano.")
    if datos.usar_ia and not usar_ia:
        f["aviso"] = "La IA local está apagada: armé el diagrama con los pasos numerados, sin decisiones."
    return FlujoVista(flujo=f, svg=_svg(f) or "")


# ---------------------------------------------------------------- avisos, sugerencias y reporte

class AlertaSalida(BaseModel):
    id: int
    documento_id: int
    documento: str
    area: str
    otro_documento_id: int | None
    otro_documento: str | None
    otra_area: str | None
    texto: str | None
    otro_texto: str | None
    detalle: str
    estado: str
    creado_en: datetime


@router.get("/alertas", response_model=list[AlertaSalida])
def alertas(todas: bool = False, ctx: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> list[AlertaSalida]:
    q = select(Alerta).order_by(Alerta.alerta_id.desc())
    if not todas:
        q = q.where(Alerta.estado == "abierta")
    salida = []
    for a in bd.scalars(q.limit(200)):
        f1 = bd.get(Fragmento, a.fragmento_id) if a.fragmento_id else None
        f2 = bd.get(Fragmento, a.otro_fragmento_id) if a.otro_fragmento_id else None
        salida.append(AlertaSalida(
            id=a.alerta_id, documento_id=a.documento_id, documento=a.documento.titulo, area=a.documento.area,
            otro_documento_id=a.otro_documento_id, otro_documento=a.otro_documento.titulo if a.otro_documento else None,
            otra_area=a.otro_documento.area if a.otro_documento else None, texto=f1.texto[:800] if f1 else None,
            otro_texto=f2.texto[:800] if f2 else None, detalle=a.detalle, estado=a.estado, creado_en=a.creado_en))
    return salida


@router.post("/alertas/buscar", status_code=status.HTTP_202_ACCEPTED)
def buscar_contradicciones(ctx: Contexto = Depends(requiere(CARGAR))) -> dict:
    if not puerta.estado_ollama()["disponible"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "La IA local (Ollama) no está prendida; ella compara los manuales.")
    revision.en_segundo_plano("contradicciones", revision.buscar_contradicciones, ctx.usuario.usuario_id)
    return {"en_curso": True}


class AlertaCambio(BaseModel):
    estado: Literal["atendida", "descartada", "abierta"]
    nota: str | None = Field(None, max_length=1000)


@router.patch("/alertas/{alerta_id}", response_model=AlertaSalida)
def atender(alerta_id: int, datos: AlertaCambio, request: Request, ctx: Contexto = Depends(requiere(CARGAR)),
            bd: Session = Depends(obtener_bd)) -> AlertaSalida:
    a = bd.get(Alerta, alerta_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese aviso.")
    a.estado, a.nota = datos.estado, _limpio(datos.nota)
    a.atendida_por, a.atendida_en = (ctx.usuario.usuario_id, ahora()) if datos.estado != "abierta" else (None, None)
    _bitacora(bd, "metodos_alerta", ctx, request, "metodos_alerta", a.alerta_id, {"estado": a.estado, "nota": a.nota})
    bd.commit()
    return next(x for x in alertas(True, ctx, bd) if x.id == alerta_id)


@router.get("/sugerencias")
def sugerencias(ctx: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> dict:
    return revision.sugerencias(bd, ctx)


@router.get("/reporte")
def reporte(mes: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), _: Contexto = Depends(requiere(CARGAR)),
            bd: Session = Depends(obtener_bd)) -> dict:
    return revision.reporte(bd, mes)


# ---------------------------------------------------------------- prueba de preguntas

class PruebaEntrada(BaseModel):
    pregunta: str = Field(min_length=3, max_length=1000)
    respuesta_esperada: str | None = Field(None, max_length=2000)
    documento_id: int | None = None
    debe_contestar: bool = True
    area: str | None = Field(None, max_length=120)
    activa: bool = True


class PruebaSalida(PruebaEntrada):
    id: int
    documento: str | None


def _prueba_salida(p: PruebaPregunta) -> PruebaSalida:
    return PruebaSalida(id=p.prueba_pregunta_id, pregunta=p.pregunta, respuesta_esperada=p.respuesta_esperada,
                        documento_id=p.documento_id, debe_contestar=p.debe_contestar, area=p.area, activa=p.activa,
                        documento=p.documento.titulo if p.documento else None)


@router.get("/prueba/preguntas", response_model=list[PruebaSalida])
def preguntas_prueba(_: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> list[PruebaSalida]:
    return [_prueba_salida(p) for p in bd.scalars(select(PruebaPregunta).order_by(PruebaPregunta.prueba_pregunta_id))]


def _validar_prueba(bd: Session, datos: PruebaEntrada) -> None:
    if datos.documento_id and not bd.get(Documento, datos.documento_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese documento.")
    if not datos.debe_contestar and datos.documento_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Una pregunta que debe contestar «no está» no lleva documento esperado.")


@router.post("/prueba/preguntas", response_model=PruebaSalida, status_code=status.HTTP_201_CREATED)
def nueva_prueba(datos: PruebaEntrada, ctx: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> PruebaSalida:
    _validar_prueba(bd, datos)
    p = PruebaPregunta(**datos.model_dump(), creado_por=ctx.usuario.usuario_id)
    bd.add(p)
    bd.commit()
    return _prueba_salida(p)


@router.put("/prueba/preguntas/{prueba_id}", response_model=PruebaSalida)
def cambiar_prueba(prueba_id: int, datos: PruebaEntrada, _: Contexto = Depends(requiere(CARGAR)),
                   bd: Session = Depends(obtener_bd)) -> PruebaSalida:
    p = bd.get(PruebaPregunta, prueba_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa pregunta de prueba.")
    _validar_prueba(bd, datos)
    for campo, valor in datos.model_dump().items():
        setattr(p, campo, valor)
    bd.commit()
    return _prueba_salida(p)


@router.delete("/prueba/preguntas/{prueba_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_prueba(prueba_id: int, _: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> None:
    if p := bd.get(PruebaPregunta, prueba_id):
        bd.delete(p)
        bd.commit()


class CorridaSalida(BaseModel):
    id: int
    estado: str
    modo: str | None
    total: int
    hechas: int
    correctas: int
    inventadas: int
    no_esta_bien: int
    no_esta_total: int
    promedio_ms: int
    error: str | None
    corrido_por: str | None
    iniciada_en: datetime
    terminada_en: datetime | None
    metas: dict


class CorridaDetalle(CorridaSalida):
    detalle: list[dict]


def _corrida_salida(bd: Session, c: PruebaCorrida) -> CorridaSalida:
    return CorridaSalida(id=c.corrida_id, estado=c.estado, modo=c.modo, total=c.total, hechas=c.hechas,
                         correctas=c.correctas, inventadas=c.inventadas, no_esta_bien=c.no_esta_bien,
                         no_esta_total=c.no_esta_total, promedio_ms=c.promedio_ms, error=c.error,
                         corrido_por=_nombre(bd, c.corrido_por), iniciada_en=c.iniciada_en, terminada_en=c.terminada_en,
                         metas=revision.metas(c))


@router.post("/prueba/correr", response_model=CorridaSalida, status_code=status.HTTP_202_ACCEPTED)
def correr_prueba(request: Request, ctx: Contexto = Depends(requiere(APROBAR)), bd: Session = Depends(obtener_bd)) -> CorridaSalida:
    if bd.scalar(select(PruebaCorrida.corrida_id).where(PruebaCorrida.estado == "en_curso")):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay una prueba corriendo.")
    if not bd.scalar(select(func.count(PruebaPregunta.prueba_pregunta_id)).where(PruebaPregunta.activa == true())):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Primero captura las preguntas de prueba.")
    c = PruebaCorrida(estado="en_curso", corrido_por=ctx.usuario.usuario_id)
    bd.add(c)
    bd.flush()
    _bitacora(bd, "metodos_prueba_correr", ctx, request, "metodos_prueba", c.corrida_id)
    bd.commit()
    revision.correr_prueba_aparte(c.corrida_id, ctx.usuario.usuario_id)
    return _corrida_salida(bd, c)


@router.get("/prueba/corridas", response_model=list[CorridaSalida])
def corridas(_: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> list[CorridaSalida]:
    return [_corrida_salida(bd, c) for c in bd.scalars(select(PruebaCorrida).order_by(PruebaCorrida.corrida_id.desc()).limit(20))]


@router.get("/prueba/corridas/{corrida_id}", response_model=CorridaDetalle)
def corrida(corrida_id: int, _: Contexto = Depends(requiere(CARGAR)), bd: Session = Depends(obtener_bd)) -> CorridaDetalle:
    c = bd.get(PruebaCorrida, corrida_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa corrida.")
    bd.refresh(c)
    return CorridaDetalle(**_corrida_salida(bd, c).model_dump(), detalle=json.loads(c.detalle or "[]"))


# para quien solo inició sesión: saber si puede preguntar (la liga desde otros módulos)
@router.get("/puedo")
def puedo(ctx: Contexto = Depends(usuario_actual)) -> dict:
    return {"consultar": ctx.puede(CONSULTAR), "cargar": ctx.puede(CARGAR), "aprobar": ctx.puede(APROBAR)}
