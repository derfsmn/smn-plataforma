"""Reglas de Vidanat (/api/innovacion/reglas): borrador → en revisión → publicada → sustituida o retirada.

- Quien propone una versión no puede publicarla (separación de funciones, en el servidor).
- Publicar exige condición válida (si es automática), fuente revisada, fecha de inicio y que no choque con otra regla
  publicada sobre el mismo campo en un alcance común.
- Publicar o retirar crea otra evaluación para los expedientes abiertos en alcance.
- «Probar» evalúa contra los expedientes en alcance sin guardar nada.
Las reglas «apenas se están pensando» (Diego, 2026-11-21): el módulo funciona sin reglas.
"""
import json
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, requiere
from modulos.innovacion import acceso as A
from modulos.innovacion import evaluacion as evs
from modulos.innovacion import expedientes as ex
from modulos.innovacion import motor
from modulos.innovacion.modelos import SEVERIDADES, Expediente, Regla, RecursoVersion, ReglaVersion
from modulos.innovacion.rutas import _fecha, _texto, acc_de, bitacora, nombre
from nucleo.modelos import ahora

router = APIRouter(prefix="/api/innovacion", tags=["innovación vidanat"])
AREAS = {"REG": "Regulatorio", "COMP": "Composición", "EVI": "Evidencia", "DOC": "Documentos", "BOT": "Botánicos",
         "CAL": "Calidad", "ETQ": "Etiqueta", "MKT": "Comercial"}
AREAS_POR_ROL = {"innovacion_regulatorio": {"REG", "ETQ", "DOC"}, "innovacion_calidad": {"CAL", "DOC"}}


class VersionEntrada(BaseModel):
    proposito: str = Field(min_length=5, max_length=1000)
    modo: str = Field("automatica", pattern="^(automatica|manual|asistida)$")
    alcance: dict = Field(default_factory=dict)
    condicion: dict | None = None
    severidad: str = Field("mayor", pattern="^(bloqueante|mayor|menor)$")
    si_falta: str = Field("pendiente", pattern="^(pendiente|incumple)$")
    admite_excepcion: bool = False
    exige_fuente_vigente: bool = False
    sustituye_a: str | None = None  # código de regla
    fuente_version_id: int | None = None
    fuente_ubicacion: str | None = Field(None, max_length=300)
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    rol_revisor: str | None = Field(None, max_length=60)
    plazo_dias: int = Field(5, ge=1, le=60)
    campos_relevantes: list[str] = Field(default_factory=list, max_length=20)


class ReglaEntrada(VersionEntrada):
    area: str = Field(pattern="^[A-Z]{2,5}$")
    nombre: str = Field(min_length=3, max_length=300)
    codigo: str | None = Field(None, pattern=r"^R-[A-Z]{2,5}-\d{3}$")


def _version_dict(bd: Session, rv: ReglaVersion) -> dict:
    fuente = bd.get(RecursoVersion, rv.fuente_version_id) if rv.fuente_version_id else None
    sust = bd.get(Regla, rv.sustituye_a) if rv.sustituye_a else None
    return {"numero": rv.numero, "id": rv.regla_version_id, "estado": rv.estado, "proposito": rv.proposito, "modo": rv.modo,
            "alcance": json.loads(rv.alcance) if rv.alcance else {}, "condicion": json.loads(rv.condicion) if rv.condicion else None,
            "severidad": rv.severidad, "si_falta": rv.si_falta, "admite_excepcion": rv.admite_excepcion,
            "exige_fuente_vigente": rv.exige_fuente_vigente, "sustituye_a": sust.codigo if sust else None,
            "fuente": {"version_id": fuente.version_id, "recurso_id": fuente.recurso_id, "version": fuente.numero,
                       "titulo": fuente.recurso.titulo, "estado": fuente.estado} if fuente else None,
            "fuente_ubicacion": rv.fuente_ubicacion, "vigente_desde": _fecha(rv.vigente_desde),
            "vigente_hasta": _fecha(rv.vigente_hasta), "rol_revisor": rv.rol_revisor, "plazo_dias": rv.plazo_dias,
            "campos_relevantes": json.loads(rv.campos_relevantes) if rv.campos_relevantes else [],
            "autor": nombre(bd, rv.autor_id), "autor_id": rv.autor_id, "creado_en": _fecha(rv.creado_en),
            "enviado_en": _fecha(rv.enviado_en), "aprobador": nombre(bd, rv.aprobador_id), "publicado_en": _fecha(rv.publicado_en),
            "retirado_por": nombre(bd, rv.retirado_por), "retirado_en": _fecha(rv.retirado_en), "motivo_retiro": rv.motivo_retiro}


def _regla_dict(bd: Session, r: Regla, *, versiones: bool = True) -> dict:
    vigente = next((v for v in reversed(r.versiones) if v.estado == "publicada"), None)
    ultima = r.versiones[-1] if r.versiones else None
    d = {"id": r.regla_id, "codigo": r.codigo, "area": r.area, "area_nombre": AREAS.get(r.area, r.area), "nombre": r.nombre,
         "vigente": vigente.numero if vigente else None, "ultima": ultima.numero if ultima else None,
         "estado": ultima.estado if ultima else None, "severidad": (vigente or ultima).severidad if (vigente or ultima) else None,
         "modo": (vigente or ultima).modo if (vigente or ultima) else None}
    if versiones:
        d["versiones"] = [_version_dict(bd, v) for v in reversed(r.versiones)]
    return d


def _llenar(bd: Session, rv: ReglaVersion, d: VersionEntrada) -> None:
    if d.modo == "automatica":
        if not d.condicion:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Una regla automática necesita su condición.")
        try:
            motor.validar(d.condicion)
        except motor.CondicionInvalida as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Condición: {e}") from e
    desconocidas = set(d.alcance) - set(motor.ALCANCE)
    if desconocidas:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Alcance desconocido: {', '.join(sorted(desconocidas))}.")
    if d.vigente_desde and d.vigente_hasta and d.vigente_hasta < d.vigente_desde:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La vigencia termina antes de empezar.")
    sust = None
    if d.sustituye_a:
        sust = bd.scalar(select(Regla).where(Regla.codigo == d.sustituye_a))
        if not sust:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"No existe la regla {d.sustituye_a}.")
    rv.proposito, rv.modo, rv.severidad, rv.si_falta = d.proposito.strip(), d.modo, d.severidad, d.si_falta
    rv.alcance = json.dumps(d.alcance, ensure_ascii=False) if d.alcance else None
    rv.condicion = json.dumps(d.condicion, ensure_ascii=False) if d.condicion and d.modo == "automatica" else None
    rv.admite_excepcion, rv.exige_fuente_vigente = d.admite_excepcion, d.exige_fuente_vigente
    rv.sustituye_a = sust.regla_id if sust else None
    rv.fuente_version_id, rv.fuente_ubicacion = d.fuente_version_id, _texto(d.fuente_ubicacion)
    rv.vigente_desde, rv.vigente_hasta = d.vigente_desde, d.vigente_hasta
    rv.rol_revisor = _texto(d.rol_revisor) if d.modo != "automatica" else None
    rv.plazo_dias = d.plazo_dias
    rv.campos_relevantes = json.dumps(d.campos_relevantes) if d.campos_relevantes else None


def _regla(bd: Session, regla_id: int) -> Regla:
    r = bd.get(Regla, regla_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa regla.")
    return r


def _version(bd: Session, r: Regla, numero: int) -> ReglaVersion:
    rv = bd.scalar(select(ReglaVersion).where(ReglaVersion.regla_id == r.regla_id, ReglaVersion.numero == numero))
    if not rv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa versión.")
    return rv


@router.get("/reglas")
def reglas(ctx: Contexto = Depends(requiere(A.VER)), bd: Session = Depends(obtener_bd)) -> list[dict]:
    return [_regla_dict(bd, r, versiones=False) for r in bd.scalars(select(Regla).order_by(Regla.codigo))]


@router.get("/reglas/{regla_id}")
def regla(regla_id: int, ctx: Contexto = Depends(requiere(A.VER)), bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    r = _regla(bd, regla_id)
    return _regla_dict(bd, r) | {"puede_proponer": acc.puede(A.REGLA_PROPONER),
                                 "puede_publicar": acc.puede(A.REGLA_PUBLICAR) and _de_su_area(acc, r)}


def _siguiente_codigo(bd: Session, area: str) -> str:
    codigos = bd.scalars(select(Regla.codigo).where(Regla.codigo.like(f"R-{area}-%")))
    n = max((int(c.rsplit("-", 1)[1]) for c in codigos if re.match(rf"^R-{area}-\d{{3}}$", c)), default=0) + 1
    return f"R-{area}-{n:03d}"


@router.post("/reglas", status_code=status.HTTP_201_CREATED)
def crear(datos: ReglaEntrada, request: Request, ctx: Contexto = Depends(requiere(A.REGLA_PROPONER)),
          bd: Session = Depends(obtener_bd)) -> dict:
    codigo = datos.codigo or _siguiente_codigo(bd, datos.area)
    if bd.scalar(select(Regla).where(Regla.codigo == codigo)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe la regla {codigo}.")
    r = Regla(codigo=codigo, area=datos.area, nombre=datos.nombre.strip(), creado_por=ctx.usuario.usuario_id)
    bd.add(r)
    bd.flush()
    rv = ReglaVersion(regla_id=r.regla_id, numero=1, autor_id=ctx.usuario.usuario_id, proposito=datos.proposito)
    _llenar(bd, rv, datos)
    bd.add(rv)
    bd.flush()
    bitacora(bd, "regla_crear", ctx, request, "regla", codigo)
    bd.commit()
    bd.refresh(r)
    return _regla_dict(bd, r)


@router.post("/reglas/{regla_id}/versiones", status_code=status.HTTP_201_CREATED)
def nueva_version(regla_id: int, datos: VersionEntrada, request: Request, ctx: Contexto = Depends(requiere(A.REGLA_PROPONER)),
                  bd: Session = Depends(obtener_bd)) -> dict:
    r = _regla(bd, regla_id)
    if any(v.estado in ("borrador", "en_revision") for v in r.versiones):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay una versión en borrador o en revisión de esta regla.")
    rv = ReglaVersion(regla_id=r.regla_id, numero=r.versiones[-1].numero + 1, autor_id=ctx.usuario.usuario_id,
                      proposito=datos.proposito)
    _llenar(bd, rv, datos)
    bd.add(rv)
    bd.flush()
    bitacora(bd, "regla_version", ctx, request, "regla", r.codigo, {"version": rv.numero})
    bd.commit()
    bd.refresh(r)
    return _regla_dict(bd, r)


@router.put("/reglas/{regla_id}/versiones/{numero}")
def editar_version(regla_id: int, numero: int, datos: VersionEntrada, ctx: Contexto = Depends(requiere(A.REGLA_PROPONER)),
                   bd: Session = Depends(obtener_bd)) -> dict:
    r = _regla(bd, regla_id)
    rv = _version(bd, r, numero)
    if rv.estado != "borrador":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se edita una versión en borrador.")
    if rv.autor_id != ctx.usuario.usuario_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo quien la propuso edita su borrador.")
    _llenar(bd, rv, datos)
    bd.commit()
    return _version_dict(bd, rv)


@router.post("/reglas/{regla_id}/versiones/{numero}/enviar")
def enviar(regla_id: int, numero: int, request: Request, ctx: Contexto = Depends(requiere(A.REGLA_PROPONER)),
           bd: Session = Depends(obtener_bd)) -> dict:
    r = _regla(bd, regla_id)
    rv = _version(bd, r, numero)
    if rv.estado != "borrador":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se envía a revisión un borrador.")
    rv.estado, rv.enviado_en = "en_revision", ahora()
    bitacora(bd, "regla_enviar", ctx, request, "regla", r.codigo, {"version": numero})
    bd.commit()
    return _version_dict(bd, rv)


@router.post("/reglas/{regla_id}/versiones/{numero}/regresar")
def regresar(regla_id: int, numero: int, ctx: Contexto = Depends(requiere(A.REGLA_PUBLICAR)), bd: Session = Depends(obtener_bd)) -> dict:
    """El aprobador la regresa a borrador para que su autor la ajuste."""
    r = _regla(bd, regla_id)
    rv = _version(bd, r, numero)
    if rv.estado != "en_revision":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa versión no está en revisión.")
    rv.estado = "borrador"
    bd.commit()
    return _version_dict(bd, rv)


def _de_su_area(acc: A.Acceso, r: Regla) -> bool:
    if acc.admin or "innovacion_lider" in acc.roles:
        return True
    return any(r.area in areas for rol, areas in AREAS_POR_ROL.items() if rol in acc.roles)


def _choques(bd: Session, rv: ReglaVersion) -> list[str]:
    if not rv.condicion:
        return []
    mios = motor.rangos(json.loads(rv.condicion))
    if not mios:
        return []
    alcance = json.loads(rv.alcance) if rv.alcance else {}
    salida = []
    for otra in bd.scalars(select(ReglaVersion).where(ReglaVersion.estado == "publicada", ReglaVersion.regla_id != rv.regla_id)):
        if not otra.condicion or otra.regla_id == rv.sustituye_a or otra.sustituye_a == rv.regla_id:
            continue
        if not motor.alcances_se_cruzan(alcance, json.loads(otra.alcance) if otra.alcance else {}):
            continue
        for a in mios:
            for b in motor.rangos(json.loads(otra.condicion)):
                if m := motor.choque(a, b):
                    salida.append(f"Choca con {otra.regla.codigo} v{otra.numero}: {m}")
    return salida


@router.post("/reglas/{regla_id}/versiones/{numero}/publicar")
def publicar(regla_id: int, numero: int, request: Request, ctx: Contexto = Depends(requiere(A.REGLA_PUBLICAR)),
             bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    r = _regla(bd, regla_id)
    rv = _version(bd, r, numero)
    if rv.estado != "en_revision":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se publica una versión enviada a revisión.")
    if rv.autor_id == acc.usuario_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Quien propone una regla no puede publicarla: la publica otra persona.")
    if not _de_su_area(acc, r):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Las reglas del área {AREAS.get(r.area, r.area)} las publica su área.")
    faltas = []
    if not rv.vigente_desde:
        faltas.append("fecha de inicio de vigencia")
    fuente = bd.get(RecursoVersion, rv.fuente_version_id) if rv.fuente_version_id else None
    if not fuente or fuente.estado != "revisado":
        faltas.append("fuente revisada (con su versión)")
    if rv.modo != "automatica" and not rv.rol_revisor:
        faltas.append("rol que revisa")
    if faltas:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Para publicar falta: " + ", ".join(faltas) + ".")
    if choques := _choques(bd, rv):
        raise HTTPException(status.HTTP_409_CONFLICT, {"mensaje": "No se publica: hay reglas en choque. Ajusta el alcance o "
                                                      "declara qué regla sustituye.", "choques": choques})
    for anterior in r.versiones:
        if anterior.estado == "publicada" and anterior.numero != numero:
            anterior.estado = "sustituida"
            if not anterior.vigente_hasta or anterior.vigente_hasta >= rv.vigente_desde:
                anterior.vigente_hasta = rv.vigente_desde - timedelta(days=1)
    rv.estado, rv.aprobador_id, rv.publicado_en = "publicada", acc.usuario_id, ahora()
    bd.flush()
    n = evs.reevaluar_abiertos(bd, rv, motivo="regla", usuario_id=acc.usuario_id)
    bitacora(bd, "regla_publicar", ctx, request, "regla", r.codigo, {"version": numero, "reevaluados": n})
    bd.commit()
    return _version_dict(bd, rv) | {"reevaluados": n}


class Retiro(BaseModel):
    motivo: str = Field(min_length=5, max_length=1000)
    desde: date | None = None


@router.post("/reglas/{regla_id}/versiones/{numero}/retirar")
def retirar(regla_id: int, numero: int, datos: Retiro, request: Request, ctx: Contexto = Depends(requiere(A.REGLA_PUBLICAR)),
            bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    r = _regla(bd, regla_id)
    rv = _version(bd, r, numero)
    if rv.estado != "publicada":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo se retira una versión publicada.")
    if not _de_su_area(acc, r):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La retira su área.")
    desde = datos.desde or date.today()
    rv.estado, rv.retirado_por, rv.retirado_en, rv.motivo_retiro = "retirada", acc.usuario_id, ahora(), datos.motivo.strip()
    rv.vigente_hasta = desde - timedelta(days=1)
    bd.flush()
    n = evs.reevaluar_abiertos(bd, rv, motivo="regla", usuario_id=acc.usuario_id)
    bitacora(bd, "regla_retirar", ctx, request, "regla", r.codigo, {"version": numero, "motivo": rv.motivo_retiro})
    bd.commit()
    return _version_dict(bd, rv) | {"reevaluados": n}


@router.post("/reglas/{regla_id}/versiones/{numero}/probar")
def probar(regla_id: int, numero: int, ctx: Contexto = Depends(requiere(A.REGLA_PROPONER)), bd: Session = Depends(obtener_bd)) -> list[dict]:
    """Resultado por expediente abierto, sin registrar nada."""
    acc = acc_de(bd, ctx)
    r = _regla(bd, regla_id)
    rv = _version(bd, r, numero)
    salida = []
    for e in bd.scalars(select(Expediente).where(Expediente.estado != "cerrado")):
        ficha = ex.ficha_vigente(bd, e)
        if not ficha:
            continue
        datos = ex.datos_para_motor(bd, e, ficha, ex.formula_vigente(bd, e))
        dentro, fuera = motor.en_alcance(json.loads(rv.alcance) if rv.alcance else {}, datos)
        if not dentro:
            salida.append({"folio": e.folio, "nombre": e.nombre, "resultado": "no_aplica", "motivo": fuera})
            continue
        if rv.modo != "automatica":
            salida.append({"folio": e.folio, "nombre": e.nombre, "resultado": "pendiente", "motivo": "Revisión manual"})
            continue
        try:
            res = motor.evaluar(json.loads(rv.condicion), datos)
        except motor.CondicionInvalida as err:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(err)) from err
        salida.append({"folio": e.folio, "nombre": e.nombre, "resultado": res.valor, "motivo": res.motivo(),
                       "faltantes": res.faltantes,
                       "datos_usados": motor.enmascarar(res.usados, acc.ve_formula(e.expediente_id))})
    return salida


@router.get("/reglas-catalogo")
def catalogo(ctx: Contexto = Depends(requiere(A.VER)), bd: Session = Depends(obtener_bd)) -> dict:
    return {"areas": AREAS, "severidades": list(SEVERIDADES), "alcance": list(motor.ALCANCE),
            "operadores": sorted(motor.OPERADORES), "unidades": sorted(motor.UNIDADES),
            "publicadas": bd.scalar(select(func.count()).select_from(ReglaVersion).where(ReglaVersion.estado == "publicada"))}
