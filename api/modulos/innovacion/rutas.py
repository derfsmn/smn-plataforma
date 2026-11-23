"""Innovación Vidanat (/api/innovacion), TD005 Entrega 1: base de conocimiento, búsqueda, consulta con citas,
investigación en internet e inicio del módulo. Expedientes y reglas viven en rutas_expedientes.py y rutas_reglas.py.
Plan v2 aprobado por Diego el 2026-11-22. Todas las rutas validan el permiso y aplican el filtro de acceso."""
import json
from dataclasses import asdict
from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, ip_de, requiere
from ia import puerta
from modulos.innovacion import acceso as A
from modulos.innovacion import almacen, consulta, indice, investigador, lectura, trabajos
from modulos.innovacion import fuentes_externas as fx
from modulos.innovacion.modelos import (CLASIFICACIONES, TIPOS_RECURSO, Evidencia, Expediente, Hallazgo, Ingrediente,
                                        Investigacion, Recurso, RecursoArchivo, RecursoVersion, Regla, ReglaVersion,
                                        Revision, Trabajo, Vinculo)
from nucleo.bitacora import registrar
from nucleo.modelos import Archivo, Modulo, Usuario, ahora

router = APIRouter(prefix="/api/innovacion", tags=["innovación vidanat"])
MAX_ARCHIVOS = 10
Clasificacion = Literal["general", "restringido", "formula"]


# ---------------------------------------------------------------- comunes

def bitacora(bd: Session, accion: str, ctx: Contexto, request: Request | None, entidad: str, entidad_id,
             detalle: dict | None = None) -> None:
    modulo_id = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "innovacion"))
    registrar(bd, f"innovacion.{accion}", usuario_id=ctx.usuario.usuario_id, modulo_id=modulo_id, entidad=entidad,
              entidad_id=entidad_id, detalle=detalle, ip=ip_de(request) if request else None)


def nombre(bd: Session, usuario_id: int | None) -> str | None:
    return bd.scalar(select(Usuario.nombre).where(Usuario.usuario_id == usuario_id)) if usuario_id else None


def acc_de(bd: Session, ctx: Contexto) -> A.Acceso:
    return A.de(bd, ctx)


def _recurso_visible(bd: Session, acc: A.Acceso, recurso_id: int) -> Recurso:
    r = bd.get(Recurso, recurso_id)
    if not r or not acc.ve(r.clasificacion, r.expediente_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa fuente.")
    return r


def _version(bd: Session, r: Recurso, numero: int) -> RecursoVersion:
    v = bd.scalar(select(RecursoVersion).where(RecursoVersion.recurso_id == r.recurso_id, RecursoVersion.numero == numero))
    if not v:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa versión.")
    return v


def _fecha(v) -> str | None:
    return v.isoformat() if v else None


def _carga(x: str | None) -> dict:
    try:
        return json.loads(x) if x else {}
    except ValueError:
        return {}


def _texto(x) -> str | None:
    x = (str(x).strip() if x is not None else "")
    return x or None


# ---------------------------------------------------------------- inicio del módulo

@router.get("/resumen")
def resumen(ctx: Contexto = Depends(requiere(A.VER)), bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    etapas = dict(bd.execute(select(Expediente.etapa, func.count()).where(Expediente.estado != "cerrado")
                             .group_by(Expediente.etapa)).all())
    fuentes = dict(bd.execute(select(RecursoVersion.estado, func.count()).join(Recurso).where(Recurso.estado == "activo")
                              .group_by(RecursoVersion.estado)).all())
    reglas = dict(bd.execute(select(ReglaVersion.estado, func.count()).group_by(ReglaVersion.estado)).all())
    por_revisar = []
    tipos_que_reviso = [t for t in ("cientifica", "regulatoria", "calidad") if acc.revisa(t)]
    if tipos_que_reviso:
        for v in bd.scalars(select(RecursoVersion).join(Recurso).where(RecursoVersion.estado == "pendiente",
                                                                          Recurso.estado == "activo")
                            .order_by(RecursoVersion.creado_en).limit(50)):
            if A.tipo_revision(v.recurso.tipo) in tipos_que_reviso and acc.ve(v.recurso.clasificacion, v.recurso.expediente_id):
                por_revisar.append({"recurso_id": v.recurso_id, "version": v.numero, "titulo": v.recurso.titulo,
                                    "tipo": v.recurso.tipo, "desde": _fecha(v.creado_en)})
    dictamenes = []
    if acc.puede(A.DICTAMINAR):
        for rv in bd.scalars(select(Revision).where(Revision.estado == "asignada").order_by(Revision.vence_en).limit(30)):
            if acc.admin or not rv.rol or rv.rol in acc.roles or "innovacion_lider" in acc.roles:
                e = bd.get(Expediente, rv.expediente_id)
                regla = bd.get(ReglaVersion, rv.regla_version_id)
                dictamenes.append({"revision_id": rv.revision_id, "folio": e.folio, "expediente": e.nombre,
                                   "regla": regla.regla.codigo, "proposito": regla.proposito, "vence_en": _fecha(rv.vence_en)})
    por_publicar = []
    if acc.puede(A.REGLA_PUBLICAR):
        for rv in bd.scalars(select(ReglaVersion).where(ReglaVersion.estado == "en_revision")):
            if rv.autor_id != acc.usuario_id:
                por_publicar.append({"regla_id": rv.regla_id, "codigo": rv.regla.codigo, "version": rv.numero,
                                     "proposito": rv.proposito})
    por_decidir = []
    if acc.puede(A.FILTRO):
        por_decidir = [{"folio": e.folio, "nombre": e.nombre} for e in bd.scalars(
            select(Expediente).where(Expediente.etapa == "filtro", Expediente.estado == "activo"))]
    expedientes = [{"folio": e.folio, "nombre": e.nombre, "etapa": e.etapa, "estado": e.estado,
                    "actualizado_en": _fecha(e.actualizado_en)}
                   for e in bd.scalars(select(Expediente).where(Expediente.estado != "cerrado")
                                       .order_by(Expediente.actualizado_en.desc()).limit(12))] if acc.puede(A.EXP_VER) else []
    ia = puerta.estado_ollama()
    return {"etapas": etapas, "fuentes": fuentes, "reglas": reglas, "por_revisar": por_revisar[:12],
            "dictamenes": dictamenes, "por_publicar": por_publicar, "por_decidir": por_decidir,
            "expedientes": expedientes, "ia_local": ia.get("disponible", False), "ocr": lectura.hay_ocr(),
            "trabajos_con_error": bd.scalar(select(func.count(Trabajo.trabajo_id)).where(Trabajo.estado == "error")) or 0}


# ---------------------------------------------------------------- ingredientes

class IngredienteEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    tipo: Literal["mineral", "vitamina", "botanico", "aminoacido", "probiotico", "otro"] = "otro"
    forma_quimica: str | None = Field(None, max_length=200)
    sinonimos: list[str] = Field(default_factory=list, max_length=30)
    factor_ui_ug: float | None = Field(None, gt=0)
    factor_version_id: int | None = None


def _ingrediente_dict(i: Ingrediente) -> dict:
    return {"id": i.ingrediente_id, "nombre": i.nombre, "tipo": i.tipo, "forma_quimica": i.forma_quimica,
            "sinonimos": json.loads(i.sinonimos) if i.sinonimos else [], "estado": i.estado,
            "factor_ui_ug": float(i.factor_ui_ug) if i.factor_ui_ug is not None else None,
            "factor_version_id": i.factor_version_id}


@router.get("/ingredientes")
def ingredientes(q: str | None = None, ctx: Contexto = Depends(requiere(A.VER)), bd: Session = Depends(obtener_bd)) -> list[dict]:
    from nucleo.busqueda import sin_acentos

    filas = list(bd.scalars(select(Ingrediente).where(Ingrediente.estado == "activo").order_by(Ingrediente.nombre)))
    if q:
        b = sin_acentos(q.strip())
        filas = [i for i in filas if b in sin_acentos(i.nombre) or b in sin_acentos(i.sinonimos or "")
                 or b in sin_acentos(i.forma_quimica or "")]
    return [_ingrediente_dict(i) for i in filas[:200]]


def _validar_factor(bd: Session, datos: IngredienteEntrada) -> None:
    if datos.factor_ui_ug is not None:
        v = bd.get(RecursoVersion, datos.factor_version_id) if datos.factor_version_id else None
        if not v or v.estado != "revisado":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "El factor UI→µg necesita una fuente revisada que lo respalde.")


@router.post("/ingredientes", status_code=status.HTTP_201_CREATED)
def alta_ingrediente(datos: IngredienteEntrada, request: Request, ctx: Contexto = Depends(requiere(A.CARGAR)),
                     bd: Session = Depends(obtener_bd)) -> dict:
    if bd.scalar(select(Ingrediente).where(Ingrediente.nombre == datos.nombre.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese ingrediente ya está en el catálogo.")
    _validar_factor(bd, datos)
    i = Ingrediente(nombre=datos.nombre.strip(), tipo=datos.tipo, forma_quimica=_texto(datos.forma_quimica),
                    sinonimos=json.dumps([s.strip() for s in datos.sinonimos if s.strip()], ensure_ascii=False) or None,
                    factor_ui_ug=datos.factor_ui_ug, factor_version_id=datos.factor_version_id if datos.factor_ui_ug else None,
                    creado_por=ctx.usuario.usuario_id)
    bd.add(i)
    bd.flush()
    bitacora(bd, "ingrediente_alta", ctx, request, "ingrediente", i.ingrediente_id, {"nombre": i.nombre})
    bd.commit()
    return _ingrediente_dict(i)


@router.put("/ingredientes/{ingrediente_id}")
def editar_ingrediente(ingrediente_id: int, datos: IngredienteEntrada, request: Request,
                       ctx: Contexto = Depends(requiere(A.CARGAR)), bd: Session = Depends(obtener_bd)) -> dict:
    i = bd.get(Ingrediente, ingrediente_id)
    if not i:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese ingrediente.")
    _validar_factor(bd, datos)
    i.nombre, i.tipo, i.forma_quimica = datos.nombre.strip(), datos.tipo, _texto(datos.forma_quimica)
    i.sinonimos = json.dumps([s.strip() for s in datos.sinonimos if s.strip()], ensure_ascii=False)
    i.factor_ui_ug = datos.factor_ui_ug
    i.factor_version_id = datos.factor_version_id if datos.factor_ui_ug else None
    bitacora(bd, "ingrediente_editar", ctx, request, "ingrediente", i.ingrediente_id, {"nombre": i.nombre})
    bd.commit()
    return _ingrediente_dict(i)


def expandir(bd: Session, texto: str) -> str:
    """Si la búsqueda nombra un sinónimo («piridoxina»), agrega el nombre canónico («Vitamina B6») y los demás."""
    from nucleo.busqueda import sin_acentos

    b = sin_acentos(texto)
    extra = []
    for i in bd.scalars(select(Ingrediente).where(Ingrediente.estado == "activo")):
        nombres = [i.nombre] + (json.loads(i.sinonimos) if i.sinonimos else [])
        if any(len(n) > 3 and sin_acentos(n) in b for n in nombres):
            extra += nombres
    return texto + (" " + " ".join(dict.fromkeys(extra)) if extra else "")


# ---------------------------------------------------------------- fuentes (recursos) y versiones

class DatosVersion(BaseModel):
    url: str | None = Field(None, max_length=1000)
    doi: str | None = Field(None, max_length=200)
    pmid: str | None = Field(None, max_length=20)
    autores: str | None = Field(None, max_length=1000)
    anio: int | None = Field(None, ge=1800, le=2100)
    publicado_en: str | None = Field(None, max_length=300)
    idioma: str | None = Field(None, max_length=10)
    resumen: str | None = Field(None, max_length=20_000)
    texto: str | None = Field(None, max_length=400_000)
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    poblacion: str | None = Field(None, max_length=1000)
    cantidad: str | None = Field(None, max_length=1000)
    duracion: str | None = Field(None, max_length=300)
    diseno: str | None = Field(None, max_length=300)


class RecursoEntrada(DatosVersion):
    titulo: str = Field(min_length=3, max_length=500)
    tipo: str
    clasificacion: Clasificacion = "general"
    folio: str | None = None  # dueño, obligatorio para «fórmula»
    ingredientes: list[int] = Field(default_factory=list, max_length=50)
    categorias: list[str] = Field(default_factory=list, max_length=20)
    folios: list[str] = Field(default_factory=list, max_length=20)


def _leer_json(modelo, crudo: str):
    try:
        return modelo.model_validate_json(crudo)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Datos de la fuente incompletos: {e}") from e


def _exp_por_folio(bd: Session, folio: str | None) -> Expediente | None:
    if not folio:
        return None
    return A.expediente(bd, folio)


async def _guardar_archivos(bd: Session, v: RecursoVersion, archivos: list[UploadFile], *, usuario_id: int, cifrado: bool,
                            excluir_sha: set[str] | None = None) -> list[Archivo]:
    if len(archivos) > MAX_ARCHIVOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Máximo {MAX_ARCHIVOS} archivos por versión.")
    guardados = []
    for up in archivos:
        contenido = await up.read()
        try:
            a = almacen.guardar(bd, up.filename or "archivo", contenido, usuario_id=usuario_id, cifrado=cifrado)
        except almacen.ArchivoInvalido as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
        a.entidad_id = str(v.version_id)
        rol = "imagen" if a.tipo_contenido in almacen.IMAGENES else ("principal" if not guardados else "anexo")
        bd.add(RecursoArchivo(version_id=v.version_id, archivo_id=a.archivo_id, rol=rol, cifrado=cifrado))
        guardados.append(a)
    bd.flush()
    return guardados


def _duplicado(bd: Session, acc: A.Acceso, *, doi: str | None, shas: list[str], recurso_id: int | None = None) -> None:
    if doi:
        otro = bd.scalar(select(RecursoVersion).join(Recurso).where(
            func.lower(RecursoVersion.doi) == doi.strip().lower(), Recurso.estado == "activo",
            Recurso.recurso_id != (recurso_id or 0)))
        if otro:
            visible = acc.ve(otro.recurso.clasificacion, otro.recurso.expediente_id)
            raise HTTPException(status.HTTP_409_CONFLICT, "Esa fuente (mismo DOI) ya está en la base"
                                + (f": «{otro.recurso.titulo}». Carga una versión nueva ahí." if visible else "."))
    for sha in shas:
        otro = bd.scalar(select(RecursoVersion).join(RecursoArchivo, RecursoArchivo.version_id == RecursoVersion.version_id)
                         .join(Archivo, Archivo.archivo_id == RecursoArchivo.archivo_id).join(Recurso)
                         .where(Archivo.sha256 == sha, Recurso.estado == "activo", Recurso.recurso_id != (recurso_id or 0)))
        if otro:
            visible = acc.ve(otro.recurso.clasificacion, otro.recurso.expediente_id)
            raise HTTPException(status.HTTP_409_CONFLICT, "Ese mismo archivo ya está en la base"
                                + (f": «{otro.recurso.titulo}»." if visible else "."))


def _metadatos(v: RecursoVersion, d: DatosVersion) -> None:
    v.url, v.doi, v.pmid = _texto(d.url), _texto(d.doi), _texto(d.pmid)
    v.autores, v.anio, v.publicado_en, v.idioma = _texto(d.autores), d.anio, _texto(d.publicado_en), _texto(d.idioma)
    v.resumen, v.texto = _texto(d.resumen), _texto(d.texto)
    v.vigente_desde, v.vigente_hasta = d.vigente_desde, d.vigente_hasta
    previos = _carga(v.datos)
    previos.update({k: getattr(d, k) for k in ("poblacion", "cantidad", "duracion", "diseno") if getattr(d, k)})
    v.datos = json.dumps(previos, ensure_ascii=False) if previos else None


def _validar_clasificacion(acc: A.Acceso, clasificacion: str, exp: Expediente | None) -> None:
    if clasificacion == "formula":
        if not exp:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Una fuente de fórmula debe ser de un folio.")
        if not acc.edita_formula(exp.expediente_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Para cargar material de fórmula necesitas el permiso y ser del equipo del folio.")
    if clasificacion == "restringido":
        if not acc.puede(A.RESTRINGIDO) or (exp and exp.expediente_id not in acc.equipo):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Para cargar material restringido de un folio debes ser de su equipo.")


@router.post("/recursos", status_code=status.HTTP_201_CREATED)
async def cargar(request: Request, fondo: BackgroundTasks, datos: str = Form(...),
                 archivos: list[UploadFile] = File(default=[]), ctx: Contexto = Depends(requiere(A.CARGAR)),
                 bd: Session = Depends(obtener_bd)) -> dict:
    d = _leer_json(RecursoEntrada, datos)
    if d.tipo not in TIPOS_RECURSO:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tipo de fuente desconocido.")
    if not archivos and not d.url and not d.texto and not d.resumen:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pon un enlace, un archivo o el texto de la fuente.")
    acc = acc_de(bd, ctx)
    exp = _exp_por_folio(bd, d.folio)
    _validar_clasificacion(acc, d.clasificacion, exp)
    contenidos = [await up.read() for up in archivos]
    for up in archivos:
        await up.seek(0)
    import hashlib
    _duplicado(bd, acc, doi=d.doi, shas=[hashlib.sha256(c).hexdigest() for c in contenidos if c])
    r = Recurso(titulo=d.titulo.strip(), tipo=d.tipo, clasificacion=d.clasificacion,
                expediente_id=exp.expediente_id if exp else None, responsable_id=ctx.usuario.usuario_id,
                creado_por=ctx.usuario.usuario_id)
    bd.add(r)
    bd.flush()
    v = RecursoVersion(recurso_id=r.recurso_id, numero=1, creado_por=ctx.usuario.usuario_id,
                       tipo_revision=A.tipo_revision(d.tipo))
    _metadatos(v, d)
    bd.add(v)
    bd.flush()
    guardados = await _guardar_archivos(bd, v, archivos, usuario_id=ctx.usuario.usuario_id, cifrado=d.clasificacion == "formula")
    _vincular(bd, v, d.ingredientes, d.categorias, d.folios + ([d.folio] if d.folio else []), ctx.usuario.usuario_id)
    trabajos.encolar(bd, "leer", v.version_id, usuario_id=ctx.usuario.usuario_id)
    bitacora(bd, "fuente_cargar", ctx, request, "recurso", r.recurso_id,
             {"titulo": r.titulo, "clasificacion": r.clasificacion, "archivos": len(guardados)})
    bd.commit()
    fondo.add_task(trabajos.procesar_en_fondo)
    return {"id": r.recurso_id, "version": 1, "archivos": [{"id": a.archivo_id, "nombre": a.nombre_original,
                                                            "sha256": a.sha256} for a in guardados]}


def _vincular(bd: Session, v: RecursoVersion, ingredientes: list[int], categorias: list[str], folios: list[str],
              usuario_id: int) -> None:
    for i in dict.fromkeys(ingredientes):
        if not bd.get(Ingrediente, i):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Uno de los ingredientes no existe.")
        bd.add(Vinculo(version_id=v.version_id, tipo="ingrediente", ingrediente_id=i, creado_por=usuario_id))
    for c in dict.fromkeys(c.strip() for c in categorias if c.strip()):
        bd.add(Vinculo(version_id=v.version_id, tipo="categoria", categoria=c[:120], creado_por=usuario_id))
    for f in dict.fromkeys(f.strip().upper() for f in folios if f and f.strip()):
        e = A.expediente(bd, f)
        bd.add(Vinculo(version_id=v.version_id, tipo="expediente", expediente_id=e.expediente_id, creado_por=usuario_id))
    bd.flush()


@router.get("/recursos")
def lista_recursos(tipo: str | None = None, estado: str | None = None, ingrediente: int | None = None,
                   q: str | None = None, pagina: int = Query(1, ge=1), ctx: Contexto = Depends(requiere(A.VER)),
                   bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    consulta_ = select(Recurso).where(Recurso.estado == "activo").order_by(Recurso.creado_en.desc())
    if tipo:
        consulta_ = consulta_.where(Recurso.tipo == tipo)
    filas = []
    from nucleo.busqueda import sin_acentos
    for r in bd.scalars(consulta_):
        if not acc.ve(r.clasificacion, r.expediente_id):
            continue
        ultima = r.versiones[-1] if r.versiones else None
        if estado and (not ultima or ultima.estado != estado):
            continue
        if q and sin_acentos(q) not in sin_acentos(r.titulo + " " + (ultima.doi or "" if ultima else "")):
            continue
        if ingrediente and not bd.scalar(select(Vinculo.vinculo_id).join(RecursoVersion).where(
                RecursoVersion.recurso_id == r.recurso_id, Vinculo.ingrediente_id == ingrediente)):
            continue
        filas.append(r)
    total = len(filas)
    salida = []
    for r in filas[(pagina - 1) * 50:pagina * 50]:
        u = r.versiones[-1]
        salida.append({"id": r.recurso_id, "titulo": r.titulo, "tipo": r.tipo, "clasificacion": r.clasificacion,
                       "folio": bd.get(Expediente, r.expediente_id).folio if r.expediente_id else None,
                       "version": u.numero, "estado": u.estado, "procesado": u.procesado, "anio": u.anio,
                       "creado_en": _fecha(r.creado_en)})
    return {"total": total, "pagina": pagina, "recursos": salida}


def _version_dict(bd: Session, acc: A.Acceso, r: Recurso, v: RecursoVersion) -> dict:
    archivos = []
    for ra in v.archivos:
        a = bd.get(Archivo, ra.archivo_id)
        archivos.append({"id": a.archivo_id, "nombre": a.nombre_original, "tipo": a.tipo_contenido, "bytes": a.tamano_bytes,
                         "sha256": a.sha256, "rol": ra.rol, "cifrado": ra.cifrado, "descripcion": ra.descripcion,
                         "descripcion_confirmada": ra.descripcion_confirmada})
    vinculos = []
    for vi in bd.scalars(select(Vinculo).where(Vinculo.version_id == v.version_id)):
        item = {"id": vi.vinculo_id, "tipo": vi.tipo}
        if vi.ingrediente_id:
            item["ingrediente"] = bd.get(Ingrediente, vi.ingrediente_id).nombre
            item["ingrediente_id"] = vi.ingrediente_id
        if vi.categoria:
            item["categoria"] = vi.categoria
        if vi.expediente_id:
            item["folio"] = bd.get(Expediente, vi.expediente_id).folio
        vinculos.append(item)
    secciones = bd.scalar(select(func.count()).select_from(indice.Seccion).where(indice.Seccion.version_id == v.version_id))
    return {"numero": v.numero, "version_id": v.version_id, "estado": v.estado, "procesado": v.procesado, "url": v.url,
            "doi": v.doi, "pmid": v.pmid, "autores": v.autores, "anio": v.anio, "publicado_en": v.publicado_en,
            "idioma": v.idioma, "resumen": v.resumen, "tiene_texto": bool(v.texto), "vigente_desde": _fecha(v.vigente_desde),
            "vigente_hasta": _fecha(v.vigente_hasta), "datos": _carga(v.datos), "sugerencias": _carga(v.sugerencias),
            "respalda": v.respalda, "limites": v.limites, "corresponde": v.corresponde, "tipo_revision": v.tipo_revision,
            "revisado_por": nombre(bd, v.revisado_por), "revisado_en": _fecha(v.revisado_en),
            "interpretacion": v.interpretacion, "creado_por": nombre(bd, v.creado_por), "creado_en": _fecha(v.creado_en),
            "archivos": archivos, "vinculos": vinculos, "secciones": secciones}


def _uso(bd: Session, acc: A.Acceso, v: RecursoVersion) -> dict:
    """Dónde se usa la versión: citas en expedientes (solo los que la persona ve) y reglas que la tienen de fuente."""
    citas = []
    for ev in bd.scalars(select(Evidencia).where(Evidencia.version_id == v.version_id, Evidencia.retirada == 0)):
        e = bd.get(Expediente, ev.expediente_id)
        if acc.puede(A.EXP_VER):
            citas.append({"folio": e.folio, "pagina": ev.pagina, "respalda": ev.respalda, "aplica": ev.aplica})
    reglas = [{"codigo": rv.regla.codigo, "version": rv.numero, "estado": rv.estado}
              for rv in bd.scalars(select(ReglaVersion).where(ReglaVersion.fuente_version_id == v.version_id))]
    return {"citas": citas, "reglas": reglas}


@router.get("/recursos/{recurso_id}")
def detalle_recurso(recurso_id: int, ctx: Contexto = Depends(requiere(A.VER)), bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    r = _recurso_visible(bd, acc, recurso_id)
    versiones = [_version_dict(bd, acc, r, v) | {"uso": _uso(bd, acc, v)} for v in reversed(r.versiones)]
    ultima = r.versiones[-1]
    return {"id": r.recurso_id, "titulo": r.titulo, "tipo": r.tipo, "clasificacion": r.clasificacion,
            "folio": bd.get(Expediente, r.expediente_id).folio if r.expediente_id else None,
            "responsable": nombre(bd, r.responsable_id), "estado": r.estado, "versiones": versiones,
            "puede_revisar": acc.revisa(ultima.tipo_revision or "cientifica"),
            "puede_cargar": acc.puede(A.CARGAR), "trabajos": _trabajos(bd, r)}


def _trabajos(bd: Session, r: Recurso) -> list[dict]:
    ids = [v.version_id for v in r.versiones]
    salida = []
    for t in bd.scalars(select(Trabajo).where(Trabajo.objeto_id.in_(ids or [0]),
                                              Trabajo.tipo.in_(("leer", "huellas", "sugerir", "describir")))
                        .order_by(Trabajo.trabajo_id)):
        salida.append({"id": t.trabajo_id, "tipo": t.tipo, "nombre": trabajos.NOMBRES.get(t.tipo, t.tipo),
                       "estado": t.estado, "intentos": t.intentos, "error": t.error,
                       "siguiente_en": _fecha(t.siguiente_en) if t.estado == "pendiente" else None,
                       "version": next(v.numero for v in r.versiones if v.version_id == t.objeto_id)})
    return salida


@router.get("/recursos/{recurso_id}/trabajos")
def trabajos_recurso(recurso_id: int, fondo: BackgroundTasks, ctx: Contexto = Depends(requiere(A.VER)),
                     bd: Session = Depends(obtener_bd)) -> list[dict]:
    r = _recurso_visible(bd, acc_de(bd, ctx), recurso_id)
    fondo.add_task(trabajos.procesar_en_fondo)  # sin programador (laptop), la pantalla mueve la cola
    return _trabajos(bd, r)


@router.post("/trabajos/{trabajo_id}/reintentar")
def reintentar(trabajo_id: int, fondo: BackgroundTasks, ctx: Contexto = Depends(requiere(A.CARGAR)),
               bd: Session = Depends(obtener_bd)) -> dict:
    t = bd.get(Trabajo, trabajo_id)
    if not t or t.estado != "error":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay un trabajo con error ahí.")
    if t.tipo != "investigar":
        v = bd.get(RecursoVersion, t.objeto_id)
        _recurso_visible(bd, acc_de(bd, ctx), v.recurso_id if v else 0)
    trabajos.reintentar(bd, t)
    bd.commit()
    fondo.add_task(trabajos.procesar_en_fondo)
    return {"id": t.trabajo_id, "estado": t.estado}


@router.post("/recursos/{recurso_id}/versiones", status_code=status.HTTP_201_CREATED)
async def nueva_version(recurso_id: int, request: Request, fondo: BackgroundTasks, datos: str = Form(...),
                        archivos: list[UploadFile] = File(default=[]), ctx: Contexto = Depends(requiere(A.CARGAR)),
                        bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    r = _recurso_visible(bd, acc, recurso_id)
    d = _leer_json(DatosVersion, datos)
    if r.clasificacion == "formula" and not acc.edita_formula(r.expediente_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Para cargar material de fórmula debes ser del equipo del folio.")
    import hashlib
    contenidos = [await up.read() for up in archivos]
    for up in archivos:
        await up.seek(0)
    _duplicado(bd, acc, doi=None, shas=[hashlib.sha256(c).hexdigest() for c in contenidos if c], recurso_id=r.recurso_id)
    anterior = r.versiones[-1]
    n = anterior.numero + 1
    v = RecursoVersion(recurso_id=r.recurso_id, numero=n, creado_por=ctx.usuario.usuario_id,
                       tipo_revision=A.tipo_revision(r.tipo))
    _metadatos(v, d)
    bd.add(v)
    bd.flush()
    await _guardar_archivos(bd, v, archivos, usuario_id=ctx.usuario.usuario_id, cifrado=r.clasificacion == "formula")
    for vi in list(bd.scalars(select(Vinculo).where(Vinculo.version_id == anterior.version_id))):
        bd.add(Vinculo(version_id=v.version_id, tipo=vi.tipo, ingrediente_id=vi.ingrediente_id, categoria=vi.categoria,
                       expediente_id=vi.expediente_id, creado_por=ctx.usuario.usuario_id))
    trabajos.encolar(bd, "leer", v.version_id, usuario_id=ctx.usuario.usuario_id)
    bitacora(bd, "fuente_version", ctx, request, "recurso", r.recurso_id, {"version": n})
    bd.commit()
    fondo.add_task(trabajos.procesar_en_fondo)
    return {"id": r.recurso_id, "version": n}


class ConfirmarDatos(DatosVersion):
    titulo: str | None = Field(None, min_length=3, max_length=500)


@router.patch("/recursos/{recurso_id}/versiones/{numero}")
def confirmar_datos(recurso_id: int, numero: int, datos: ConfirmarDatos, request: Request,
                    ctx: Contexto = Depends(requiere(A.CARGAR)), bd: Session = Depends(obtener_bd)) -> dict:
    """Confirmar o corregir los datos (incluidos los que sugirió la IA) mientras la versión está pendiente."""
    acc = acc_de(bd, ctx)
    r = _recurso_visible(bd, acc, recurso_id)
    v = _version(bd, r, numero)
    if v.estado != "pendiente":
        raise HTTPException(status.HTTP_409_CONFLICT, "Una versión revisada ya no se cambia: carga una versión nueva.")
    texto_antes = v.texto
    _metadatos(v, datos)
    if datos.titulo and numero == r.versiones[-1].numero:
        r.titulo = datos.titulo.strip()
    if v.texto != texto_antes:
        trabajos.encolar(bd, "leer", v.version_id, usuario_id=ctx.usuario.usuario_id)
    bitacora(bd, "fuente_datos", ctx, request, "recurso", r.recurso_id, {"version": numero})
    bd.commit()
    return _version_dict(bd, acc, r, v)


class RevisionFuente(BaseModel):
    respalda: str = Field(min_length=3, max_length=5000)
    limites: str | None = Field(None, max_length=5000)
    corresponde: Literal["ingrediente", "producto", "ambos"] | None = None
    interpretacion: str | None = Field(None, max_length=10_000)


@router.post("/recursos/{recurso_id}/versiones/{numero}/revision")
def revisar_fuente(recurso_id: int, numero: int, datos: RevisionFuente, request: Request,
                   ctx: Contexto = Depends(requiere(A.REVISAR)), bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    r = _recurso_visible(bd, acc, recurso_id)
    v = _version(bd, r, numero)
    if not acc.revisa(v.tipo_revision or "cientifica"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"La revisión {v.tipo_revision} la hace otro rol.")
    if v.estado != "pendiente":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa versión ya no está pendiente de revisión.")
    if numero != r.versiones[-1].numero:
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se revisa la versión más nueva.")
    v.estado, v.revisado_por, v.revisado_en = "revisado", ctx.usuario.usuario_id, ahora()
    v.respalda, v.limites, v.corresponde = datos.respalda.strip(), _texto(datos.limites), datos.corresponde
    v.interpretacion = _texto(datos.interpretacion)
    for anterior in r.versiones:  # la anterior queda sustituida y se conserva
        if anterior.numero < numero and anterior.estado == "revisado":
            anterior.estado = "sustituido"
    bitacora(bd, "fuente_revisar", ctx, request, "recurso", r.recurso_id, {"version": numero})
    bd.commit()
    indice.olvidar()
    return _version_dict(bd, acc, r, v)


class VinculoEntrada(BaseModel):
    ingredientes: list[int] = Field(default_factory=list)
    categorias: list[str] = Field(default_factory=list)
    folios: list[str] = Field(default_factory=list)


@router.post("/recursos/{recurso_id}/versiones/{numero}/vinculos")
def vincular(recurso_id: int, numero: int, datos: VinculoEntrada, request: Request,
             ctx: Contexto = Depends(requiere(A.CARGAR)), bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    r = _recurso_visible(bd, acc, recurso_id)
    v = _version(bd, r, numero)
    _vincular(bd, v, datos.ingredientes, datos.categorias, datos.folios, ctx.usuario.usuario_id)
    bitacora(bd, "fuente_vincular", ctx, request, "recurso", r.recurso_id, datos.model_dump())
    bd.commit()
    return _version_dict(bd, acc, r, v)


@router.delete("/vinculos/{vinculo_id}", status_code=status.HTTP_204_NO_CONTENT)
def desvincular(vinculo_id: int, request: Request, ctx: Contexto = Depends(requiere(A.CARGAR)),
                bd: Session = Depends(obtener_bd)) -> Response:
    vi = bd.get(Vinculo, vinculo_id)
    if not vi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese vínculo.")
    v = bd.get(RecursoVersion, vi.version_id)
    _recurso_visible(bd, acc_de(bd, ctx), v.recurso_id)
    bitacora(bd, "fuente_desvincular", ctx, request, "recurso", v.recurso_id, {"vinculo": vinculo_id})
    bd.delete(vi)
    bd.commit()
    return Response(status_code=204)


class Descripcion(BaseModel):
    descripcion: str = Field(min_length=3, max_length=3000)


@router.post("/recursos/{recurso_id}/versiones/{numero}/archivos/{archivo_id}/descripcion")
def confirmar_descripcion(recurso_id: int, numero: int, archivo_id: int, datos: Descripcion, fondo: BackgroundTasks,
                          ctx: Contexto = Depends(requiere(A.CARGAR)), bd: Session = Depends(obtener_bd)) -> dict:
    """La persona confirma (o corrige) la descripción de una imagen; desde ese momento se puede encontrar."""
    r = _recurso_visible(bd, acc_de(bd, ctx), recurso_id)
    v = _version(bd, r, numero)
    ra = bd.get(RecursoArchivo, (v.version_id, archivo_id))
    if not ra:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese archivo en la versión.")
    ra.descripcion, ra.descripcion_confirmada = datos.descripcion.strip(), True
    trabajos.encolar(bd, "leer", v.version_id, usuario_id=ctx.usuario.usuario_id)
    bd.commit()
    fondo.add_task(trabajos.procesar_en_fondo)
    return {"ok": True}


@router.get("/recursos/{recurso_id}/archivos/{archivo_id}")
def descargar(recurso_id: int, archivo_id: int, request: Request, ctx: Contexto = Depends(requiere(A.VER)),
              bd: Session = Depends(obtener_bd)) -> Response:
    acc = acc_de(bd, ctx)
    r = _recurso_visible(bd, acc, recurso_id)
    ra = bd.scalar(select(RecursoArchivo).join(RecursoVersion).where(
        RecursoArchivo.archivo_id == archivo_id, RecursoVersion.recurso_id == r.recurso_id))
    if not ra:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa fuente.")
    a = bd.get(Archivo, archivo_id)
    try:
        contenido = almacen.leer(a, ra.cifrado)
    except almacen.ArchivoInvalido as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    marca = r.clasificacion != "general" and a.tipo_contenido == "application/pdf"
    if marca:
        contenido = almacen.marca_de_agua(contenido, f"{ctx.usuario.nombre} · {ahora():%Y-%m-%d %H:%M} UTC")
    bitacora(bd, "fuente_descargar", ctx, request, "recurso", r.recurso_id,
             {"archivo": archivo_id, "clasificacion": r.clasificacion, "marca_de_agua": marca})
    bd.commit()
    return Response(contenido, media_type=a.tipo_contenido, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(a.nombre_original)}",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.get("/secciones/{fragmento_id}")
def seccion(fragmento_id: int, ctx: Contexto = Depends(requiere(A.VER)), bd: Session = Depends(obtener_bd)) -> dict:
    """Una sección con su fuente, versión y página (para abrir una cita)."""
    f = bd.get(indice.Seccion, fragmento_id)
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa sección.")
    v = bd.get(RecursoVersion, f.version_id)
    r = _recurso_visible(bd, acc_de(bd, ctx), v.recurso_id)
    return {"id": f.fragmento_id, "recurso_id": r.recurso_id, "titulo": r.titulo, "version": v.numero,
            "estado": v.estado, "pagina": f.pagina, "seccion": f.seccion, "texto": f.texto}


# ---------------------------------------------------------------- búsqueda y consulta

@router.get("/buscar")
def buscar(q: str = Query(min_length=2, max_length=300), tipo: str | None = None, ingrediente: int | None = None,
           categoria: str | None = None, estado: str | None = None, vigente: bool | None = None, folio: str | None = None,
           ctx: Contexto = Depends(requiere(A.VER)), bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    exp = _exp_por_folio(bd, folio) if folio else None
    filtros = indice.Filtros(tipo=tipo, ingrediente_id=ingrediente, categoria=categoria, estado=estado, vigente=vigente,
                             expediente_id=exp.expediente_id if exp else None)
    hallazgos, significado = indice.buscar(bd, acc, expandir(bd, q), filtros, limite=25)
    folios = {e.expediente_id: e.folio for e in bd.scalars(select(Expediente))}
    return {"total": len(hallazgos), "con_significado": significado, "resultados": [{
        "fragmento_id": h.entrada.fragmento_id, "recurso_id": h.entrada.recurso_id, "version": h.entrada.numero,
        "version_id": h.entrada.version_id, "titulo": h.entrada.titulo, "tipo": h.entrada.tipo,
        "estado": h.entrada.estado, "clasificacion": h.entrada.clasificacion,
        "folio": folios.get(h.entrada.expediente_id), "seccion": h.entrada.seccion, "pagina": h.entrada.pagina,
        "extracto": h.entrada.texto[:500], "puntos": round(h.puntos * 1000, 1)} for h in hallazgos]}


class Pregunta(BaseModel):
    pregunta: str = Field(min_length=4, max_length=1000)
    folio: str | None = None


@router.post("/consultar")
def consultar(datos: Pregunta, ctx: Contexto = Depends(requiere(A.CONSULTAR)), bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    exp = _exp_por_folio(bd, datos.folio) if datos.folio else None
    r = consulta.responder(bd, acc, expandir(bd, datos.pregunta.strip()), expediente_id=exp.expediente_id if exp else None)
    return asdict(r)


# ---------------------------------------------------------------- investigación en internet

class InvestigacionEntrada(BaseModel):
    tema: str = Field(min_length=3, max_length=500)
    folio: str | None = None


class InvestigacionCambio(BaseModel):
    preguntas: list[dict] | None = Field(None, max_length=20)
    terminos: list[str] | None = Field(None, max_length=12)
    fuentes: list[str] | None = None
    usar_web: bool | None = None


def _investigacion(bd: Session, acc: A.Acceso, investigacion_id: int) -> Investigacion:
    inv = bd.get(Investigacion, investigacion_id)
    propia = inv is not None and inv.creado_por == acc.usuario_id
    if not inv or (not propia and not acc.puede(A.EXP_VER)) or (inv.expediente_id and not acc.puede(A.EXP_VER)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa investigación.")
    return inv


def _inv_dict(bd: Session, inv: Investigacion, *, detalle: bool = True) -> dict:
    d = {"id": inv.investigacion_id, "tema": inv.tema, "estado": inv.estado,
         "folio": bd.get(Expediente, inv.expediente_id).folio if inv.expediente_id else None,
         "creado_por": nombre(bd, inv.creado_por), "creado_en": _fecha(inv.creado_en),
         "terminada_en": _fecha(inv.terminada_en), "costo_usd": float(inv.costo_usd or 0), "error": inv.error}
    if detalle:
        from modulos.compras import buscar_web
        d.update({"preguntas": json.loads(inv.preguntas), "terminos": json.loads(inv.terminos or "[]"),
                  "fuentes": json.loads(inv.fuentes), "usar_web": inv.usar_web, "pasos": json.loads(inv.pasos or "[]"),
                  "informe": json.loads(inv.informe) if inv.informe else None,
                  "catalogo_fuentes": fx.FUENTES, "con_gasto": list(fx.CON_GASTO),
                  "gasto_mes_usd": float(buscar_web.gasto_mes(bd)), "tope_usd": float(buscar_web.tope()),
                  "hallazgos": [{"id": h.hallazgo_id, "origen": h.origen, "identificador": h.identificador,
                                 "titulo": h.titulo, "autores": h.autores, "anio": h.anio, "publicado_en": h.publicado_en,
                                 "url": h.url, "tipo_estudio": h.tipo_estudio, "puntaje": float(h.puntaje or 0),
                                 "seleccionado": h.seleccionado, "extraccion": _carga(h.extraccion),
                                 "texto_abierto": bool(h.texto_abierto), "recurso_id": h.recurso_id}
                                for h in bd.scalars(select(Hallazgo).where(Hallazgo.investigacion_id == inv.investigacion_id)
                                                    .order_by(Hallazgo.puntaje.desc()))]})
    return d


@router.get("/investigaciones")
def investigaciones(ctx: Contexto = Depends(requiere(A.INVESTIGAR)), bd: Session = Depends(obtener_bd)) -> list[dict]:
    acc = acc_de(bd, ctx)
    q = select(Investigacion).order_by(Investigacion.creado_en.desc()).limit(50)
    if not acc.puede(A.EXP_VER):
        q = q.where(Investigacion.creado_por == acc.usuario_id)
    return [_inv_dict(bd, i, detalle=False) for i in bd.scalars(q)]


@router.post("/investigaciones", status_code=status.HTTP_201_CREATED)
def proponer_investigacion(datos: InvestigacionEntrada, request: Request, ctx: Contexto = Depends(requiere(A.INVESTIGAR)),
                           bd: Session = Depends(obtener_bd)) -> dict:
    """Paso 1: preguntas y términos sugeridos. Nada sale a internet hasta «Investigar»."""
    from modulos.innovacion import expedientes as ex

    exp = _exp_por_folio(bd, datos.folio) if datos.folio else None
    ficha = None
    if exp:
        f = ex.ficha_vigente(bd, exp)
        if f:  # solo datos generales: ingrediente, forma, categoría y beneficio (nunca la fórmula)
            base = ex.datos_para_motor(bd, exp, f, None)
            ficha = {"ingredientes": [{"nombre": i.get("nombre"), "forma": i.get("forma")} for i in base["ingredientes"]],
                     "categoria_comercial": base.get("categoria_comercial"), "beneficio": base.get("beneficio")}
    propuesta = investigador.proponer(bd, ficha, datos.tema.strip())
    inv = Investigacion(expediente_id=exp.expediente_id if exp else None, tema=datos.tema.strip(),
                        preguntas=json.dumps(propuesta["preguntas"], ensure_ascii=False),
                        terminos=json.dumps(propuesta["terminos"], ensure_ascii=False),
                        fuentes=json.dumps(list(fx.GRATIS)), creado_por=ctx.usuario.usuario_id)
    bd.add(inv)
    bd.flush()
    bitacora(bd, "investigacion_proponer", ctx, request, "investigacion", inv.investigacion_id, {"tema": inv.tema})
    bd.commit()
    return _inv_dict(bd, inv)


@router.get("/investigaciones/{investigacion_id}")
def detalle_investigacion(investigacion_id: int, fondo: BackgroundTasks, ctx: Contexto = Depends(requiere(A.INVESTIGAR)),
                          bd: Session = Depends(obtener_bd)) -> dict:
    inv = _investigacion(bd, acc_de(bd, ctx), investigacion_id)
    if inv.estado == "corriendo":
        fondo.add_task(trabajos.procesar_en_fondo)
    return _inv_dict(bd, inv)


@router.patch("/investigaciones/{investigacion_id}")
def editar_investigacion(investigacion_id: int, datos: InvestigacionCambio, ctx: Contexto = Depends(requiere(A.INVESTIGAR)),
                         bd: Session = Depends(obtener_bd)) -> dict:
    inv = _investigacion(bd, acc_de(bd, ctx), investigacion_id)
    if inv.estado not in ("propuesta", "lista", "error"):
        raise HTTPException(status.HTTP_409_CONFLICT, "La investigación está corriendo.")
    if datos.preguntas is not None:
        preguntas = [{"tema": p.get("tema") if p.get("tema") in investigador.TEMAS else "eficacia",
                      "texto": str(p.get("texto") or "").strip()[:500]} for p in datos.preguntas if str(p.get("texto") or "").strip()]
        if not preguntas:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Deja al menos una pregunta.")
        inv.preguntas = json.dumps(preguntas, ensure_ascii=False)
    if datos.terminos is not None:
        terminos = [t for t in dict.fromkeys(investigador.limpiar_termino(t) for t in datos.terminos) if t]
        if not terminos:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Deja al menos un término de búsqueda.")
        inv.terminos = json.dumps(terminos, ensure_ascii=False)
    if datos.fuentes is not None:
        fuentes = [f for f in datos.fuentes if f in fx.FUENTES]
        if not fuentes:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige al menos una fuente.")
        inv.fuentes = json.dumps(fuentes)
    if datos.usar_web is not None:
        inv.usar_web = datos.usar_web
    bd.commit()
    return _inv_dict(bd, inv)


@router.post("/investigaciones/{investigacion_id}/correr")
def correr_investigacion(investigacion_id: int, request: Request, fondo: BackgroundTasks,
                         ctx: Contexto = Depends(requiere(A.INVESTIGAR)), bd: Session = Depends(obtener_bd)) -> dict:
    inv = _investigacion(bd, acc_de(bd, ctx), investigacion_id)
    if inv.estado == "corriendo":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya está corriendo.")
    inv.estado, inv.error, inv.informe = "corriendo", None, None
    inv.pasos = json.dumps([{"paso": "preguntas", "texto": f"{len(json.loads(inv.preguntas))} preguntas y "
                             f"{len(json.loads(inv.terminos or '[]'))} términos confirmados por {ctx.usuario.nombre}.",
                             "en": ahora().isoformat(timespec="seconds")}], ensure_ascii=False)
    trabajos.encolar(bd, "investigar", inv.investigacion_id, usuario_id=ctx.usuario.usuario_id)
    bitacora(bd, "investigacion_correr", ctx, request, "investigacion", inv.investigacion_id,
             {"terminos": json.loads(inv.terminos or "[]"), "fuentes": json.loads(inv.fuentes), "web": inv.usar_web})
    bd.commit()
    fondo.add_task(trabajos.procesar_en_fondo)
    return _inv_dict(bd, inv)


TIPO_POR_ESTUDIO = {"metaanalisis": "revision", "revision": "revision", "ensayo": "ensayo_clinico", "oficial": "guia_regulatoria",
                    "observacional": "articulo", "preclinico": "articulo", "web": "otro", "otro": "articulo"}


@router.post("/investigaciones/{investigacion_id}/hallazgos/{hallazgo_id}/agregar", status_code=status.HTTP_201_CREATED)
def agregar_hallazgo(investigacion_id: int, hallazgo_id: int, request: Request, fondo: BackgroundTasks,
                     ctx: Contexto = Depends(requiere(A.CARGAR)), bd: Session = Depends(obtener_bd)) -> dict:
    """Paso 6: el hallazgo entra a la base como «pendiente de revisión», con su enlace y lo que se leyó."""
    acc = acc_de(bd, ctx)
    inv = _investigacion(bd, acc, investigacion_id)
    h = bd.get(Hallazgo, hallazgo_id)
    if not h or h.investigacion_id != inv.investigacion_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese hallazgo.")
    if h.recurso_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya está en la base.")
    doi = h.identificador[4:] if (h.identificador or "").startswith("doi:") else None
    _duplicado(bd, acc, doi=doi, shas=[])
    meta = _carga(h.extraccion)
    r = Recurso(titulo=h.titulo[:500], tipo=TIPO_POR_ESTUDIO.get(h.tipo_estudio or "otro", "articulo"), clasificacion="general",
                responsable_id=ctx.usuario.usuario_id, creado_por=ctx.usuario.usuario_id)
    bd.add(r)
    bd.flush()
    v = RecursoVersion(recurso_id=r.recurso_id, numero=1, url=h.url, doi=doi,
                       pmid=h.identificador[5:] if (h.identificador or "").startswith("pmid:") else None,
                       autores=h.autores, anio=h.anio, publicado_en=h.publicado_en, resumen=h.resumen,
                       texto=h.texto_abierto, creado_por=ctx.usuario.usuario_id, tipo_revision=A.tipo_revision(r.tipo),
                       datos=json.dumps({k: meta.get(k) for k in ("poblacion", "cantidad", "duracion") if meta.get(k)}
                                        | {"investigacion": inv.investigacion_id, "origen": h.origen}, ensure_ascii=False))
    bd.add(v)
    bd.flush()
    if inv.expediente_id:
        bd.add(Vinculo(version_id=v.version_id, tipo="expediente", expediente_id=inv.expediente_id, creado_por=ctx.usuario.usuario_id))
    h.recurso_id = r.recurso_id
    trabajos.encolar(bd, "leer", v.version_id, usuario_id=ctx.usuario.usuario_id)
    bitacora(bd, "investigacion_agregar", ctx, request, "recurso", r.recurso_id, {"hallazgo": hallazgo_id})
    bd.commit()
    fondo.add_task(trabajos.procesar_en_fondo)
    return {"id": r.recurso_id, "version": 1}


# ---------------------------------------------------------------- catálogos para las pantallas

@router.get("/catalogos")
def catalogos(ctx: Contexto = Depends(requiere(A.VER)), bd: Session = Depends(obtener_bd)) -> dict:
    from modulos.innovacion.modelos import ETAPAS, SEVERIDADES
    from modulos.innovacion.motor import OPERADORES, UNIDADES

    return {"tipos": list(TIPOS_RECURSO), "clasificaciones": list(CLASIFICACIONES), "etapas": list(ETAPAS),
            "severidades": list(SEVERIDADES), "operadores": sorted(OPERADORES), "unidades": sorted(UNIDADES),
            "fuentes_externas": fx.FUENTES, "reglas": [{"codigo": r.codigo, "nombre": r.nombre} for r in bd.scalars(select(Regla))]}
