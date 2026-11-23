"""Expedientes de Vidanat (/api/innovacion/expedientes): folio, equipo, ficha y fórmula versionadas, evidencia,
comparables, escenarios, pendientes, evaluaciones, dictámenes, excepciones, compuerta, decisión del Filtro y PDF."""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, requiere
from ia import puerta
from modulos.innovacion import acceso as A
from modulos.innovacion import evaluacion as evs
from modulos.innovacion import expedientes as ex
from modulos.innovacion import ia_local, motor, pdf
from modulos.innovacion.modelos import (ETAPAS, Comparable, Decision, Escenario, Evaluacion, EvaluacionResultado,
                                        Evidencia, Excepcion, Expediente, ExpedienteEquipo, FichaVersion, Seccion,
                                        FormulaVersion, Pendiente, RecursoVersion, Regla, ReglaVersion, Revision)
from modulos.innovacion.rutas import _carga, _fecha, _texto, acc_de, bitacora, nombre
from nucleo.modelos import Rol, Usuario, UsuarioRol, ahora

router = APIRouter(prefix="/api/innovacion", tags=["innovación vidanat"])


def _dinero(x) -> float | None:
    return float(x) if x is not None else None


# ---------------------------------------------------------------- alta, lista y equipo

class ExpedienteEntrada(BaseModel):
    nombre: str = Field(min_length=3, max_length=200)
    descripcion: str | None = Field(None, max_length=5000)
    jurisdiccion: str = Field("MX", max_length=10)
    categoria_sanitaria: str | None = Field(None, max_length=60)
    categoria_comercial: str | None = Field(None, max_length=120)
    presentacion: str | None = Field(None, max_length=60)
    equipo: list[int] = Field(default_factory=list, max_length=20)


def _equipo(bd: Session, e: Expediente) -> list[dict]:
    return [{"usuario_id": m.usuario_id, "nombre": nombre(bd, m.usuario_id), "papel": m.papel} for m in e.equipo]


def _poner_equipo(bd: Session, e: Expediente, ids: list[int], responsable: int) -> None:
    validos = set(bd.scalars(select(Usuario.usuario_id).where(Usuario.usuario_id.in_(ids or [0]), Usuario.tipo == "interno")))
    if faltan := set(ids) - validos:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"No existen esos usuarios internos: {sorted(faltan)}.")
    e.equipo.clear()
    bd.flush()
    for u in dict.fromkeys([responsable, *ids]):
        e.equipo.append(ExpedienteEquipo(usuario_id=u, papel="responsable" if u == responsable else None))


@router.get("/equipo-disponible")
def equipo_disponible(ctx: Contexto = Depends(requiere(A.EXP_VER)), bd: Session = Depends(obtener_bd)) -> list[dict]:
    """Usuarios con algún rol de Innovación Vidanat, para armar el equipo de un folio."""
    filas = bd.execute(select(Usuario.usuario_id, Usuario.nombre, Rol.nombre).join(UsuarioRol, UsuarioRol.usuario_id == Usuario.usuario_id)
                       .join(Rol, Rol.rol_id == UsuarioRol.rol_id).where(Rol.codigo.like("innovacion_%"), Usuario.estatus == "activo"))
    salida: dict[int, dict] = {}
    for uid, n, rol in filas:
        salida.setdefault(uid, {"usuario_id": uid, "nombre": n, "roles": []})["roles"].append(rol)
    return sorted(salida.values(), key=lambda x: x["nombre"])


@router.get("/expedientes")
def expedientes(ctx: Contexto = Depends(requiere(A.EXP_VER)), bd: Session = Depends(obtener_bd)) -> list[dict]:
    acc = acc_de(bd, ctx)
    salida = []
    for e in bd.scalars(select(Expediente).order_by(Expediente.actualizado_en.desc())):
        ev = evs.ultima(bd, e)
        salida.append({"folio": e.folio, "nombre": e.nombre, "etapa": e.etapa, "estado": e.estado,
                       "categoria_comercial": e.categoria_comercial, "responsable": nombre(bd, e.responsable_id),
                       "soy_del_equipo": e.expediente_id in acc.equipo, "actualizado_en": _fecha(e.actualizado_en),
                       "resumen": json.loads(ev.resumen) if ev else None})
    return salida


@router.post("/expedientes", status_code=status.HTTP_201_CREATED)
def alta_expediente(datos: ExpedienteEntrada, request: Request, ctx: Contexto = Depends(requiere(A.EXP_EDITAR)),
                    bd: Session = Depends(obtener_bd)) -> dict:
    e = Expediente(folio=ex.nuevo_folio(bd), nombre=datos.nombre.strip(), descripcion=_texto(datos.descripcion),
                   jurisdiccion=datos.jurisdiccion.strip().upper() or "MX", categoria_sanitaria=_texto(datos.categoria_sanitaria),
                   categoria_comercial=_texto(datos.categoria_comercial), presentacion=_texto(datos.presentacion),
                   etapa="investigacion", responsable_id=ctx.usuario.usuario_id, creado_por=ctx.usuario.usuario_id)
    bd.add(e)
    bd.flush()
    _poner_equipo(bd, e, datos.equipo, ctx.usuario.usuario_id)
    bitacora(bd, "expediente_alta", ctx, request, "expediente", e.folio, {"nombre": e.nombre})
    bd.commit()
    return {"folio": e.folio}


class EquipoEntrada(BaseModel):
    equipo: list[int] = Field(max_length=20)


@router.put("/expedientes/{folio}/equipo")
def cambiar_equipo(folio: str, datos: EquipoEntrada, request: Request, ctx: Contexto = Depends(requiere(A.EXP_EDITAR)),
                   bd: Session = Depends(obtener_bd)) -> list[dict]:
    e = A.expediente(bd, folio)
    acc = acc_de(bd, ctx)
    if e.responsable_id != acc.usuario_id and not acc.admin and "innovacion_lider" not in acc.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El equipo lo cambia el responsable del folio o el Líder de I+D.")
    _poner_equipo(bd, e, datos.equipo, e.responsable_id)
    bitacora(bd, "expediente_equipo", ctx, request, "expediente", e.folio, {"equipo": datos.equipo})
    bd.commit()
    return _equipo(bd, e)


# ---------------------------------------------------------------- detalle

def _ficha_dict(bd: Session, f: FichaVersion | None) -> dict | None:
    if not f:
        return None
    return {"numero": f.numero, "ficha_id": f.ficha_id, "datos": json.loads(f.datos or "{}"), "nota": f.nota,
            "formula_version": bd.get(FormulaVersion, f.formula_id).numero if f.formula_id else None,
            "creado_por": nombre(bd, f.creado_por), "creado_en": _fecha(f.creado_en),
            "ingredientes": [{k: (float(getattr(i, k)) if k.startswith(("cantidad", "fraccion")) and getattr(i, k) is not None
                                  else getattr(i, k)) for k in ex.CAMPOS_INGREDIENTE} | {"orden": i.orden}
                             for i in f.ingredientes]}


def _evidencia(bd: Session, acc: A.Acceso, e: Expediente) -> list[dict]:
    salida = []
    for ev in bd.scalars(select(Evidencia).where(Evidencia.expediente_id == e.expediente_id, Evidencia.retirada == 0)
                         .order_by(Evidencia.creado_en)):
        v = bd.get(RecursoVersion, ev.version_id)
        r = v.recurso
        visible = acc.ve(r.clasificacion, r.expediente_id)
        salida.append({"id": ev.evidencia_id, "recurso_id": r.recurso_id if visible else None,
                       "titulo": r.titulo if visible else "Fuente restringida", "version": v.numero,
                       "estado_fuente": v.estado, "fragmento_id": ev.fragmento_id if visible else None,
                       "pagina": ev.pagina, "seccion": ev.seccion if visible else None, "respalda": ev.respalda,
                       "limites": ev.limites, "aplica": ev.aplica, "sentido": ev.sentido,
                       "creado_por": nombre(bd, ev.creado_por), "creado_en": _fecha(ev.creado_en)})
    return salida


def _resultado_dict(bd: Session, acc: A.Acceso, e: Expediente, r: EvaluacionResultado, excepciones: dict) -> dict:
    rv = bd.get(ReglaVersion, r.regla_version_id)
    fuente = bd.get(RecursoVersion, rv.fuente_version_id) if rv.fuente_version_id else None
    revision = bd.scalar(select(Revision).where(Revision.resultado_id == r.resultado_id))
    x = excepciones.get(rv.regla_id)
    return {"id": r.resultado_id, "regla": rv.regla.codigo, "regla_id": rv.regla_id, "version": rv.numero,
            "proposito": rv.proposito, "modo": rv.modo, "resultado": r.resultado, "severidad": r.severidad,
            "motivo": r.motivo, "faltantes": json.loads(r.faltantes) if r.faltantes else [],
            "datos_usados": motor.enmascarar(json.loads(r.datos_usados) if r.datos_usados else {}, acc.ve_formula(e.expediente_id)),
            "aviso_fuente": r.aviso_fuente, "admite_excepcion": rv.admite_excepcion,
            "fuente": {"recurso_id": fuente.recurso_id, "version": fuente.numero, "titulo": fuente.recurso.titulo,
                       "ubicacion": rv.fuente_ubicacion} if fuente and acc.ve(fuente.recurso.clasificacion, fuente.recurso.expediente_id) else None,
            "revision": {"id": revision.revision_id, "estado": revision.estado, "rol": revision.rol} if revision else None,
            "excepcion": {"id": x.excepcion_id, "vence_en": x.vence_en.isoformat()} if x else None}


def _evaluacion_dict(bd: Session, acc: A.Acceso, e: Expediente, ev: Evaluacion | None) -> dict | None:
    if not ev:
        return None
    excepciones = evs.excepciones_vigentes(bd, e)
    orden = {"incumple": 0, "pendiente": 1, "cumple": 2, "no_aplica": 3}
    resultados = sorted((_resultado_dict(bd, acc, e, r, excepciones) for r in ev.resultados),
                        key=lambda r: (orden[r["resultado"]], {"bloqueante": 0, "mayor": 1, "menor": 2}.get(r["severidad"], 3)))
    return {"numero": ev.numero, "motivo": ev.motivo, "etapa": ev.etapa, "motor": ev.motor,
            "ficha_version": bd.get(FichaVersion, ev.ficha_id).numero if ev.ficha_id else None,
            "formula_version": bd.get(FormulaVersion, ev.formula_id).numero if ev.formula_id else None,
            "regla": bd.get(ReglaVersion, ev.regla_version_id).regla.codigo if ev.regla_version_id else None,
            "creada_por": nombre(bd, ev.creada_por), "creada_en": _fecha(ev.creada_en), "resumen": json.loads(ev.resumen),
            "resultados": resultados}


def _decision_dict(bd: Session, d: Decision) -> dict:
    return {"id": d.decision_id, "etapa": d.etapa, "resultado": d.resultado, "motivo": d.motivo,
            "condiciones": d.condiciones, "evaluacion": bd.get(Evaluacion, d.evaluacion_id).numero if d.evaluacion_id else None,
            "decidida_por": nombre(bd, d.decidida_por), "decidida_en": _fecha(d.decidida_en)}


@router.get("/expedientes/{folio}")
def detalle(folio: str, ctx: Contexto = Depends(requiere(A.EXP_VER)), bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    e = A.expediente(bd, folio)
    formula = ex.formula_vigente(bd, e)
    siguiente = ETAPAS[min(ETAPAS.index(e.etapa) + 1, len(ETAPAS) - 1)]
    return {
        "folio": e.folio, "nombre": e.nombre, "descripcion": e.descripcion, "jurisdiccion": e.jurisdiccion,
        "categoria_sanitaria": e.categoria_sanitaria, "categoria_comercial": e.categoria_comercial,
        "presentacion": e.presentacion, "etapa": e.etapa, "estado": e.estado, "responsable": nombre(bd, e.responsable_id),
        "equipo": _equipo(bd, e), "soy_del_equipo": e.expediente_id in acc.equipo,
        "ficha": _ficha_dict(bd, ex.ficha_vigente(bd, e)),
        "fichas": [{"numero": f.numero, "creado_en": _fecha(f.creado_en), "creado_por": nombre(bd, f.creado_por)}
                   for f in bd.scalars(select(FichaVersion).where(FichaVersion.expediente_id == e.expediente_id)
                                       .order_by(FichaVersion.numero.desc()))],
        "formula": {"numero": formula.numero, "creado_en": _fecha(formula.creado_en), "creado_por": nombre(bd, formula.creado_por),
                    "puede_ver": acc.ve_formula(e.expediente_id), "puede_editar": acc.edita_formula(e.expediente_id)} if formula
        else {"numero": None, "puede_ver": acc.ve_formula(e.expediente_id), "puede_editar": acc.edita_formula(e.expediente_id)},
        "evidencia": _evidencia(bd, acc, e),
        "comparables": [{"id": c.comparable_id, "origen": c.origen, "producto": c.producto, "marca": c.marca,
                         "presentacion": c.presentacion, "precio": _dinero(c.precio), "url": c.url, "fuente": c.fuente,
                         "nota": c.nota} for c in bd.scalars(select(Comparable).where(Comparable.expediente_id == e.expediente_id))],
        "escenarios": [_escenario(s) for s in bd.scalars(select(Escenario).where(Escenario.expediente_id == e.expediente_id))],
        "pendientes": [{"id": p.pendiente_id, "descripcion": p.descripcion, "responsable": nombre(bd, p.responsable_id),
                        "responsable_id": p.responsable_id, "fecha_limite": _fecha(p.fecha_limite),
                        "determinante": p.determinante, "estado": p.estado}
                       for p in bd.scalars(select(Pendiente).where(Pendiente.expediente_id == e.expediente_id)
                                           .order_by(Pendiente.estado, Pendiente.fecha_limite))],
        "evaluacion": _evaluacion_dict(bd, acc, e, evs.ultima(bd, e)),
        "compuerta": evs.compuerta(bd, e, siguiente), "siguiente_etapa": siguiente,
        "decisiones": [_decision_dict(bd, d) for d in bd.scalars(select(Decision).where(Decision.expediente_id == e.expediente_id)
                                                                 .order_by(Decision.decidida_en.desc()))],
        "puede": {"editar": acc.puede(A.EXP_EDITAR), "evaluar": acc.puede(A.EVALUAR), "filtro": acc.puede(A.FILTRO),
                  "exportar": acc.puede(A.EXPORTAR), "dictaminar": acc.puede(A.DICTAMINAR),
                  "excepcion": acc.puede(A.EXCEPCION), "investigar": acc.puede(A.INVESTIGAR)},
    }


# ---------------------------------------------------------------- ficha y fórmula

class IngredienteFicha(BaseModel):
    ingrediente_id: int | None = None
    nombre: str = Field(min_length=1, max_length=200)
    tipo: str | None = Field(None, max_length=20)
    forma: str | None = Field(None, max_length=200)
    en_compuesto: bool = False
    cantidad_compuesto: float | None = Field(None, ge=0)
    unidad_compuesto: str | None = Field(None, max_length=20)
    cantidad_activa: float | None = Field(None, ge=0)
    unidad_activa: str | None = Field(None, max_length=20)
    fraccion_activa: float | None = Field(None, ge=0, le=1)
    fuente_version_id: int | None = None
    nota: str | None = Field(None, max_length=500)


class FichaEntrada(BaseModel):
    datos: dict = Field(default_factory=dict)
    ingredientes: list[IngredienteFicha] = Field(default_factory=list, max_length=60)
    nota: str | None = Field(None, max_length=1000)


def _evaluar_y_avisar(bd: Session, e: Expediente, motivo: str, ctx: Contexto) -> Evaluacion:
    ev = evs.evaluar(bd, e, motivo=motivo, usuario_id=ctx.usuario.usuario_id)
    e.actualizado_en = ahora()
    return ev


@router.post("/expedientes/{folio}/fichas", status_code=status.HTTP_201_CREATED)
def guardar_ficha(folio: str, datos: FichaEntrada, request: Request, ctx: Contexto = Depends(requiere(A.EXP_EDITAR)),
                  bd: Session = Depends(obtener_bd)) -> dict:
    e = A.expediente(bd, folio)
    if e.estado == "cerrado":
        raise HTTPException(status.HTTP_409_CONFLICT, "El expediente está cerrado.")
    for i in datos.ingredientes:
        for u in (i.unidad_compuesto, i.unidad_activa):
            if u and motor.dimension(u) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{i.nombre}: unidad desconocida «{u}».")
    f = ex.guardar_ficha(bd, e, datos.datos, [i.model_dump() for i in datos.ingredientes], usuario_id=ctx.usuario.usuario_id,
                         nota=_texto(datos.nota))
    ev = _evaluar_y_avisar(bd, e, "ficha", ctx)
    bitacora(bd, "ficha_guardar", ctx, request, "expediente", e.folio, {"version": f.numero, "evaluacion": ev.numero})
    bd.commit()
    return {"numero": f.numero, "evaluacion": ev.numero}


@router.get("/expedientes/{folio}/fichas/{numero}")
def ver_ficha(folio: str, numero: int, ctx: Contexto = Depends(requiere(A.EXP_VER)), bd: Session = Depends(obtener_bd)) -> dict:
    e = A.expediente(bd, folio)
    f = bd.scalar(select(FichaVersion).where(FichaVersion.expediente_id == e.expediente_id, FichaVersion.numero == numero))
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa versión de la ficha.")
    return _ficha_dict(bd, f)


class Componente(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    funcion: str | None = Field(None, max_length=60)  # activo / excipiente / recubrimiento…
    cantidad: float | None = Field(None, ge=0)
    unidad: str | None = Field(None, max_length=20)
    proveedor: str | None = Field(None, max_length=200)
    especificacion: str | None = Field(None, max_length=500)


class FormulaEntrada(BaseModel):
    componentes: list[Componente] = Field(min_length=1, max_length=80)
    proceso: str | None = Field(None, max_length=20_000)
    lote_teorico: str | None = Field(None, max_length=100)
    notas: str | None = Field(None, max_length=5000)
    nota: str | None = Field(None, max_length=1000)


def _formula_permitida(acc: A.Acceso, e: Expediente, editar: bool) -> None:
    ok = acc.edita_formula(e.expediente_id) if editar else acc.ve_formula(e.expediente_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe.")


@router.post("/expedientes/{folio}/formulas", status_code=status.HTTP_201_CREATED)
def guardar_formula(folio: str, datos: FormulaEntrada, request: Request, ctx: Contexto = Depends(requiere(A.FORMULA_EDITAR)),
                    bd: Session = Depends(obtener_bd)) -> dict:
    e = A.expediente(bd, folio)
    _formula_permitida(acc_de(bd, ctx), e, True)
    contenido = datos.model_dump(exclude={"nota"})
    f = ex.guardar_formula(bd, e, contenido, usuario_id=ctx.usuario.usuario_id, nota=_texto(datos.nota))
    ev = _evaluar_y_avisar(bd, e, "formula", ctx)
    bitacora(bd, "formula_guardar", ctx, request, "expediente", e.folio, {"version": f.numero, "evaluacion": ev.numero})
    bd.commit()
    return {"numero": f.numero, "evaluacion": ev.numero}


@router.get("/expedientes/{folio}/formulas/{numero}")
def ver_formula(folio: str, numero: int, request: Request, ctx: Contexto = Depends(requiere(A.FORMULA_VER)),
                bd: Session = Depends(obtener_bd)) -> dict:
    e = A.expediente(bd, folio)
    _formula_permitida(acc_de(bd, ctx), e, False)
    f = bd.scalar(select(FormulaVersion).where(FormulaVersion.expediente_id == e.expediente_id, FormulaVersion.numero == numero))
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe.")
    bitacora(bd, "formula_ver", ctx, request, "expediente", e.folio, {"version": numero})
    bd.commit()
    return {"numero": f.numero, "contenido": ex.leer_formula(f), "nota": f.nota, "creado_por": nombre(bd, f.creado_por),
            "creado_en": _fecha(f.creado_en)}


# ---------------------------------------------------------------- evidencia, comparables, escenarios y pendientes

class EvidenciaEntrada(BaseModel):
    version_id: int
    fragmento_id: int | None = None
    pagina: int | None = Field(None, ge=1)
    seccion: str | None = Field(None, max_length=400)
    respalda: str = Field(min_length=3, max_length=1000)
    limites: str | None = Field(None, max_length=1000)
    aplica: str = Field("por_dictaminar", pattern="^(si|parcial|no|por_dictaminar)$")
    sentido: str = Field("a_favor", pattern="^(a_favor|contradictoria)$")


@router.post("/expedientes/{folio}/evidencia", status_code=status.HTTP_201_CREATED)
def citar(folio: str, datos: EvidenciaEntrada, request: Request, ctx: Contexto = Depends(requiere(A.EXP_EDITAR)),
          bd: Session = Depends(obtener_bd)) -> dict:
    """La cita queda ligada a una versión concreta de la fuente, nunca a «la última»."""
    acc = acc_de(bd, ctx)
    e = A.expediente(bd, folio)
    v = bd.get(RecursoVersion, datos.version_id)
    if not v or not acc.ve(v.recurso.clasificacion, v.recurso.expediente_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa fuente.")
    pagina, seccion = datos.pagina, datos.seccion
    if datos.fragmento_id:
        f = bd.get(Seccion, datos.fragmento_id)
        if not f or f.version_id != v.version_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Esa sección no es de esa versión.")
        pagina, seccion = pagina or f.pagina, seccion or f.seccion
    ev = Evidencia(expediente_id=e.expediente_id, version_id=v.version_id, fragmento_id=datos.fragmento_id, pagina=pagina,
                   seccion=seccion, respalda=datos.respalda.strip(), limites=_texto(datos.limites), aplica=datos.aplica,
                   sentido=datos.sentido, creado_por=ctx.usuario.usuario_id)
    bd.add(ev)
    e.actualizado_en = ahora()
    bd.flush()
    bitacora(bd, "evidencia_citar", ctx, request, "expediente", e.folio, {"version_id": v.version_id, "pagina": pagina})
    bd.commit()
    return {"id": ev.evidencia_id, "pagina": pagina, "seccion": seccion, "version": v.numero}


@router.delete("/evidencia/{evidencia_id}", status_code=status.HTTP_204_NO_CONTENT)
def retirar_evidencia(evidencia_id: int, request: Request, ctx: Contexto = Depends(requiere(A.EXP_EDITAR)),
                      bd: Session = Depends(obtener_bd)) -> Response:
    ev = bd.get(Evidencia, evidencia_id)
    if not ev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa cita.")
    ev.retirada = True  # no se borra: un dictamen o una decisión pudieron usarla
    bitacora(bd, "evidencia_retirar", ctx, request, "evidencia", evidencia_id)
    bd.commit()
    return Response(status_code=204)


class ComparableEntrada(BaseModel):
    origen: str = Field("manual", pattern="^(manual|catalogo)$")
    producto: str = Field(min_length=2, max_length=300)
    marca: str | None = Field(None, max_length=120)
    presentacion: str | None = Field(None, max_length=120)
    precio: float | None = Field(None, ge=0)
    sku: str | None = Field(None, max_length=40)
    url: str | None = Field(None, max_length=1000)
    fuente: str | None = Field(None, max_length=300)
    nota: str | None = Field(None, max_length=1000)


@router.post("/expedientes/{folio}/comparables", status_code=status.HTTP_201_CREATED)
def comparable(folio: str, datos: ComparableEntrada, ctx: Contexto = Depends(requiere(A.EXP_EDITAR)),
               bd: Session = Depends(obtener_bd)) -> dict:
    e = A.expediente(bd, folio)
    if datos.origen == "manual" and not (datos.fuente or datos.url):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Un comparable manual necesita su fuente o enlace.")
    c = Comparable(expediente_id=e.expediente_id, creado_por=ctx.usuario.usuario_id, **datos.model_dump())
    bd.add(c)
    bd.commit()
    return {"id": c.comparable_id}


@router.delete("/comparables/{comparable_id}", status_code=status.HTTP_204_NO_CONTENT)
def quitar_comparable(comparable_id: int, ctx: Contexto = Depends(requiere(A.EXP_EDITAR)), bd: Session = Depends(obtener_bd)) -> Response:
    c = bd.get(Comparable, comparable_id)
    if c:
        bd.delete(c)
        bd.commit()
    return Response(status_code=204)


class EscenarioEntrada(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    costo_unitario: float | None = Field(None, ge=0)
    precio: float | None = Field(None, ge=0)
    supuestos: str | None = Field(None, max_length=5000)
    confianza: str | None = Field(None, pattern="^(alta|media|baja)$")


def _escenario(s: Escenario) -> dict:
    margen = None
    if s.precio and s.costo_unitario is not None and s.precio > 0:
        margen = round(float((s.precio - s.costo_unitario) / s.precio) * 100, 1)
    return {"id": s.escenario_id, "nombre": s.nombre, "costo_unitario": _dinero(s.costo_unitario), "precio": _dinero(s.precio),
            "margen_pct": margen, "supuestos": s.supuestos, "confianza": s.confianza}


@router.post("/expedientes/{folio}/escenarios", status_code=status.HTTP_201_CREATED)
def escenario(folio: str, datos: EscenarioEntrada, ctx: Contexto = Depends(requiere(A.EXP_EDITAR)),
              bd: Session = Depends(obtener_bd)) -> dict:
    e = A.expediente(bd, folio)
    s = Escenario(expediente_id=e.expediente_id, creado_por=ctx.usuario.usuario_id, **datos.model_dump())
    bd.add(s)
    bd.commit()
    return _escenario(s)


class PendienteEntrada(BaseModel):
    descripcion: str = Field(min_length=3, max_length=1000)
    responsable_id: int | None = None
    fecha_limite: date | None = None
    determinante: bool = False


@router.post("/expedientes/{folio}/pendientes", status_code=status.HTTP_201_CREATED)
def pendiente(folio: str, datos: PendienteEntrada, ctx: Contexto = Depends(requiere(A.EXP_EDITAR)),
              bd: Session = Depends(obtener_bd)) -> dict:
    e = A.expediente(bd, folio)
    p = Pendiente(expediente_id=e.expediente_id, creado_por=ctx.usuario.usuario_id, **datos.model_dump())
    bd.add(p)
    bd.commit()
    return {"id": p.pendiente_id}


@router.post("/pendientes/{pendiente_id}/cerrar")
def cerrar_pendiente(pendiente_id: int, ctx: Contexto = Depends(requiere(A.EXP_EDITAR)), bd: Session = Depends(obtener_bd)) -> dict:
    p = bd.get(Pendiente, pendiente_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese pendiente.")
    p.estado, p.cerrado_por, p.cerrado_en = "cerrado", ctx.usuario.usuario_id, ahora()
    bd.commit()
    return {"id": p.pendiente_id, "estado": p.estado}


# ---------------------------------------------------------------- evaluaciones

@router.post("/expedientes/{folio}/evaluaciones", status_code=status.HTTP_201_CREATED)
def evaluar_ahora(folio: str, request: Request, ctx: Contexto = Depends(requiere(A.EVALUAR)), bd: Session = Depends(obtener_bd)) -> dict:
    e = A.expediente(bd, folio)
    ev = _evaluar_y_avisar(bd, e, "manual", ctx)
    bitacora(bd, "evaluar", ctx, request, "expediente", e.folio, {"evaluacion": ev.numero})
    bd.commit()
    return _evaluacion_dict(bd, acc_de(bd, ctx), e, ev)


@router.get("/expedientes/{folio}/evaluaciones")
def evaluaciones(folio: str, ctx: Contexto = Depends(requiere(A.EXP_VER)), bd: Session = Depends(obtener_bd)) -> list[dict]:
    e = A.expediente(bd, folio)
    decididas = {d.evaluacion_id: d for d in bd.scalars(select(Decision).where(Decision.expediente_id == e.expediente_id))}
    salida = []
    for ev in bd.scalars(select(Evaluacion).where(Evaluacion.expediente_id == e.expediente_id).order_by(Evaluacion.numero.desc())):
        d = decididas.get(ev.evaluacion_id)
        salida.append({"numero": ev.numero, "motivo": ev.motivo, "creada_en": _fecha(ev.creada_en),
                       "creada_por": nombre(bd, ev.creada_por), "resumen": json.loads(ev.resumen),
                       "ficha_version": bd.get(FichaVersion, ev.ficha_id).numero if ev.ficha_id else None,
                       "regla": bd.get(ReglaVersion, ev.regla_version_id).regla.codigo if ev.regla_version_id else None,
                       "decision": {"etapa": d.etapa, "resultado": d.resultado} if d else None})
    return salida


def _evaluacion(bd: Session, e: Expediente, numero: int) -> Evaluacion:
    ev = bd.scalar(select(Evaluacion).where(Evaluacion.expediente_id == e.expediente_id, Evaluacion.numero == numero))
    if not ev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa evaluación.")
    return ev


@router.get("/expedientes/{folio}/evaluaciones/{numero}")
def ver_evaluacion(folio: str, numero: int, ctx: Contexto = Depends(requiere(A.EXP_VER)), bd: Session = Depends(obtener_bd)) -> dict:
    e = A.expediente(bd, folio)
    return _evaluacion_dict(bd, acc_de(bd, ctx), e, _evaluacion(bd, e, numero))


@router.get("/expedientes/{folio}/comparar")
def comparar(folio: str, a: int, b: int, ctx: Contexto = Depends(requiere(A.EXP_VER)), bd: Session = Depends(obtener_bd)) -> dict:
    """Solo lo que cambió entre dos evaluaciones, regla por regla."""
    acc = acc_de(bd, ctx)
    e = A.expediente(bd, folio)
    ea, eb = _evaluacion_dict(bd, acc, e, _evaluacion(bd, e, a)), _evaluacion_dict(bd, acc, e, _evaluacion(bd, e, b))
    pa, pb = {r["regla"]: r for r in ea["resultados"]}, {r["regla"]: r for r in eb["resultados"]}
    cambios = []
    for regla in sorted(set(pa) | set(pb)):
        x, y = pa.get(regla), pb.get(regla)
        if not x or not y or x["resultado"] != y["resultado"] or x["version"] != y["version"] or x["motivo"] != y["motivo"]:
            cambios.append({"regla": regla, "antes": x and {k: x[k] for k in ("version", "resultado", "motivo")},
                            "despues": y and {k: y[k] for k in ("version", "resultado", "motivo")}})
    return {"a": {k: ea[k] for k in ("numero", "motivo", "ficha_version", "formula_version", "creada_en", "resumen")},
            "b": {k: eb[k] for k in ("numero", "motivo", "ficha_version", "formula_version", "creada_en", "resumen")},
            "cambios": cambios}


# ---------------------------------------------------------------- revisiones manuales (dictamen)

def _revision(bd: Session, revision_id: int) -> Revision:
    r = bd.get(Revision, revision_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa revisión.")
    return r


def _secciones_respaldo(bd: Session, acc: A.Acceso, e: Expediente) -> list[tuple[int, str]]:
    salida = []
    for ev in bd.scalars(select(Evidencia).where(Evidencia.expediente_id == e.expediente_id, Evidencia.retirada == 0)):
        v = bd.get(RecursoVersion, ev.version_id)
        if not acc.ve(v.recurso.clasificacion, v.recurso.expediente_id):
            continue
        texto = bd.get(Seccion, ev.fragmento_id).texto if ev.fragmento_id else ev.respalda
        salida.append((ev.evidencia_id, f"{v.recurso.titulo} v{v.numero}" + (f" pág. {ev.pagina}" if ev.pagina else "")
                       + f" — {ev.respalda}\n{texto[:1500]}"))
    return salida


@router.get("/revisiones/{revision_id}")
def ver_revision(revision_id: int, ctx: Contexto = Depends(requiere(A.EXP_VER)), bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    r = _revision(bd, revision_id)
    e = bd.get(Expediente, r.expediente_id)
    rv = bd.get(ReglaVersion, r.regla_version_id)
    fuente = bd.get(RecursoVersion, rv.fuente_version_id) if rv.fuente_version_id else None
    return {"id": r.revision_id, "folio": e.folio, "expediente": e.nombre, "estado": r.estado, "rol": r.rol,
            "regla": {"codigo": rv.regla.codigo, "version": rv.numero, "proposito": rv.proposito, "severidad": rv.severidad,
                      "fuente": {"recurso_id": fuente.recurso_id, "version": fuente.numero, "titulo": fuente.recurso.titulo,
                                 "ubicacion": rv.fuente_ubicacion} if fuente else None},
            "ficha": _ficha_dict(bd, bd.get(FichaVersion, r.ficha_id)) if r.ficha_id else None,
            "evidencia": _evidencia(bd, acc, e), "sugerencia_ia": _carga(r.sugerencia_ia) or None,
            "dictamen": r.dictamen, "motivo": r.motivo, "respaldo": json.loads(r.respaldo) if r.respaldo else [],
            "dictaminada_por": nombre(bd, r.dictaminada_por), "dictaminada_en": _fecha(r.dictaminada_en),
            "vence_en": _fecha(r.vence_en), "puede_dictaminar": _puede_dictaminar(acc, r)}


def _puede_dictaminar(acc: A.Acceso, r: Revision) -> bool:
    return acc.puede(A.DICTAMINAR) and (acc.admin or not r.rol or r.rol in acc.roles or "innovacion_lider" in acc.roles)


@router.post("/revisiones/{revision_id}/sugerencia")
def sugerencia(revision_id: int, ctx: Contexto = Depends(requiere(A.DICTAMINAR)), bd: Session = Depends(obtener_bd)) -> dict:
    """Sugerencia de la IA local, marcada como tal. No cambia ningún resultado."""
    acc = acc_de(bd, ctx)
    r = _revision(bd, revision_id)
    e = bd.get(Expediente, r.expediente_id)
    rv = bd.get(ReglaVersion, r.regla_version_id)
    ficha = _ficha_dict(bd, bd.get(FichaVersion, r.ficha_id)) if r.ficha_id else {}
    secciones = [t for _, t in _secciones_respaldo(bd, acc, e)]
    try:
        s = ia_local.sugerir_dictamen(bd, rv.proposito, {"datos": (ficha or {}).get("datos"),
                                                         "ingredientes": (ficha or {}).get("ingredientes")}, secciones,
                                      acc.usuario_id)
    except (puerta.ErrorIA, ia_local.RespuestaInvalida) as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"La IA local no pudo sugerir: {err}") from err
    r.sugerencia_ia = json.dumps(s, ensure_ascii=False)
    bd.commit()
    return s


class DictamenEntrada(BaseModel):
    dictamen: str = Field(pattern="^(cumple|incumple|no_aplica)$")
    motivo: str = Field(min_length=10, max_length=5000)
    respaldo: list[int] = Field(default_factory=list, max_length=20)  # ids de evidencia


@router.post("/revisiones/{revision_id}/dictamen")
def dictaminar(revision_id: int, datos: DictamenEntrada, request: Request, ctx: Contexto = Depends(requiere(A.DICTAMINAR)),
               bd: Session = Depends(obtener_bd)) -> dict:
    acc = acc_de(bd, ctx)
    r = _revision(bd, revision_id)
    if not _puede_dictaminar(acc, r):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Esta revisión le toca al rol {r.rol}.")
    if r.estado != "asignada":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa revisión ya se dictaminó.")
    if not datos.respaldo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El dictamen necesita al menos una evidencia de respaldo.")
    validas = {ev.evidencia_id for ev in bd.scalars(select(Evidencia).where(
        Evidencia.expediente_id == r.expediente_id, Evidencia.evidencia_id.in_(datos.respaldo), Evidencia.retirada == 0))}
    if validas != set(datos.respaldo):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El respaldo debe ser evidencia citada en este expediente.")
    r.estado, r.dictamen, r.motivo = "dictaminada", datos.dictamen, datos.motivo.strip()
    r.respaldo = json.dumps(sorted(validas))
    r.dictaminada_por, r.dictaminada_en = ctx.usuario.usuario_id, ahora()
    e = bd.get(Expediente, r.expediente_id)
    ev = evs.evaluar(bd, e, motivo="manual", usuario_id=ctx.usuario.usuario_id)  # la compuerta se vuelve a revisar
    bitacora(bd, "dictamen", ctx, request, "expediente", e.folio,
             {"revision": revision_id, "dictamen": datos.dictamen, "respaldo": sorted(validas), "evaluacion": ev.numero})
    bd.commit()
    return {"id": r.revision_id, "estado": r.estado, "evaluacion": ev.numero}


# ---------------------------------------------------------------- excepciones

class ExcepcionEntrada(BaseModel):
    justificacion: str = Field(min_length=10, max_length=5000)
    vence_en: date


@router.post("/resultados/{resultado_id}/excepcion", status_code=status.HTTP_201_CREATED)
def pedir_excepcion(resultado_id: int, datos: ExcepcionEntrada, request: Request, ctx: Contexto = Depends(requiere(A.EXP_EDITAR)),
                    bd: Session = Depends(obtener_bd)) -> dict:
    res = bd.get(EvaluacionResultado, resultado_id)
    if not res:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese resultado.")
    rv = bd.get(ReglaVersion, res.regla_version_id)
    if not rv.admite_excepcion:
        raise HTTPException(status.HTTP_409_CONFLICT, f"La regla {rv.regla.codigo} no admite excepción.")
    if datos.vence_en <= date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La excepción debe vencer después de hoy.")
    ev = bd.get(Evaluacion, res.evaluacion_id)
    x = Excepcion(expediente_id=ev.expediente_id, resultado_id=resultado_id, regla_id=rv.regla_id,
                  justificacion=datos.justificacion.strip(), vence_en=datos.vence_en, solicitada_por=ctx.usuario.usuario_id)
    bd.add(x)
    bd.flush()
    bitacora(bd, "excepcion_pedir", ctx, request, "expediente", bd.get(Expediente, ev.expediente_id).folio,
             {"regla": rv.regla.codigo, "vence_en": datos.vence_en.isoformat()})
    bd.commit()
    return {"id": x.excepcion_id, "estado": x.estado}


class ResolverExcepcion(BaseModel):
    aprobar: bool
    nota: str | None = Field(None, max_length=1000)


@router.post("/excepciones/{excepcion_id}/resolver")
def resolver_excepcion(excepcion_id: int, datos: ResolverExcepcion, request: Request,
                       ctx: Contexto = Depends(requiere(A.EXCEPCION)), bd: Session = Depends(obtener_bd)) -> dict:
    x = bd.get(Excepcion, excepcion_id)
    if not x or x.estado != "solicitada":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay una excepción por resolver ahí.")
    if x.solicitada_por == ctx.usuario.usuario_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Quien pide una excepción no puede aprobarla.")
    x.estado = "aprobada" if datos.aprobar else "rechazada"
    x.resuelta_por, x.resuelta_en, x.nota = ctx.usuario.usuario_id, ahora(), _texto(datos.nota)
    e = bd.get(Expediente, x.expediente_id)
    bitacora(bd, "excepcion_resolver", ctx, request, "expediente", e.folio,
             {"excepcion": excepcion_id, "estado": x.estado, "regla": bd.get(Regla, x.regla_id).codigo})
    bd.commit()
    return {"id": x.excepcion_id, "estado": x.estado}


@router.get("/expedientes/{folio}/excepciones")
def excepciones(folio: str, ctx: Contexto = Depends(requiere(A.EXP_VER)), bd: Session = Depends(obtener_bd)) -> list[dict]:
    e = A.expediente(bd, folio)
    return [{"id": x.excepcion_id, "regla": bd.get(Regla, x.regla_id).codigo, "estado": x.estado,
             "justificacion": x.justificacion, "vence_en": x.vence_en.isoformat(), "solicitada_por": nombre(bd, x.solicitada_por),
             "resuelta_por": nombre(bd, x.resuelta_por), "nota": x.nota}
            for x in bd.scalars(select(Excepcion).where(Excepcion.expediente_id == e.expediente_id).order_by(Excepcion.solicitada_en.desc()))]


# ---------------------------------------------------------------- compuerta, envío y decisión del Filtro

@router.get("/expedientes/{folio}/compuerta")
def ver_compuerta(folio: str, etapa: str = "filtro", ctx: Contexto = Depends(requiere(A.EXP_VER)),
                  bd: Session = Depends(obtener_bd)) -> dict:
    if etapa not in ETAPAS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Etapa desconocida.")
    return evs.compuerta(bd, A.expediente(bd, folio), etapa)


def _congelar(bd: Session, e: Expediente, ev: Evaluacion | None) -> str:
    excepciones = evs.excepciones_vigentes(bd, e)
    return json.dumps({
        "evaluacion": ev.numero if ev else None,
        "ficha_id": ev.ficha_id if ev else None, "formula_id": ev.formula_id if ev else None,
        "evidencia": [{"id": x.evidencia_id, "version_id": x.version_id, "pagina": x.pagina}
                      for x in bd.scalars(select(Evidencia).where(Evidencia.expediente_id == e.expediente_id, Evidencia.retirada == 0))],
        "excepciones": [{"id": x.excepcion_id, "regla_id": x.regla_id, "vence_en": x.vence_en.isoformat()} for x in excepciones.values()],
        "etapa": e.etapa, "en": ahora().isoformat(timespec="seconds")}, ensure_ascii=False)


class Envio(BaseModel):
    etapa: str = "filtro"
    nota: str | None = Field(None, max_length=1000)


@router.post("/expedientes/{folio}/enviar")
def enviar(folio: str, datos: Envio, request: Request, ctx: Contexto = Depends(requiere(A.EXP_EDITAR)),
           bd: Session = Depends(obtener_bd)) -> dict:
    """Pasar a la etapa siguiente. Con un bloqueante abierto responde 409."""
    e = A.expediente(bd, folio)
    if datos.etapa not in ETAPAS or ETAPAS.index(datos.etapa) != ETAPAS.index(e.etapa) + 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"De «{e.etapa}» solo se pasa a la etapa siguiente.")
    if e.estado != "activo":
        raise HTTPException(status.HTTP_409_CONFLICT, "El expediente no está activo.")
    c = evs.compuerta(bd, e, datos.etapa)
    if not c["puede_avanzar"]:
        raise HTTPException(status.HTTP_409_CONFLICT, {"mensaje": c["motivo"], "compuerta": c})
    e.etapa, e.actualizado_en = datos.etapa, ahora()
    bitacora(bd, "expediente_enviar", ctx, request, "expediente", e.folio, {"etapa": datos.etapa, "evaluacion": c["evaluacion"]})
    from nucleo.notificaciones import notificar
    if datos.etapa == "filtro":  # avisar a quienes deciden el Filtro
        for (uid,) in bd.execute(select(UsuarioRol.usuario_id).join(Rol, Rol.rol_id == UsuarioRol.rol_id)
                                 .where(Rol.codigo == "innovacion_directivo")):
            notificar(bd, uid, f"{e.folio} espera decisión del Filtro", e.nombre, liga=f"/innovacion/expedientes/{e.folio}?vista=filtro")
    bd.commit()
    return {"folio": e.folio, "etapa": e.etapa}


class DecisionEntrada(BaseModel):
    resultado: str = Field(pattern="^(avanzar|ajustar|espera|cerrar)$")
    motivo: str = Field(min_length=10, max_length=5000)
    condiciones: str | None = Field(None, max_length=5000)


@router.post("/expedientes/{folio}/decisiones", status_code=status.HTTP_201_CREATED)
def decidir(folio: str, datos: DecisionEntrada, request: Request, ctx: Contexto = Depends(requiere(A.FILTRO)),
            bd: Session = Depends(obtener_bd)) -> dict:
    e = A.expediente(bd, folio)
    if e.etapa != "filtro" or e.estado != "activo":
        raise HTTPException(status.HTTP_409_CONFLICT, "El expediente no está esperando la decisión del Filtro.")
    ev = evs.ultima(bd, e)
    if datos.resultado == "avanzar":
        c = evs.compuerta(bd, e, "desarrollo")
        if not c["puede_avanzar"]:
            raise HTTPException(status.HTTP_409_CONFLICT, {"mensaje": "No se puede aprobar con bloqueantes abiertos.", "compuerta": c})
    d = Decision(expediente_id=e.expediente_id, etapa="filtro", evaluacion_id=ev.evaluacion_id if ev else None,
                 resultado=datos.resultado, motivo=datos.motivo.strip(), condiciones=_texto(datos.condiciones),
                 congelado=_congelar(bd, e, ev), decidida_por=ctx.usuario.usuario_id)
    bd.add(d)
    if datos.resultado == "avanzar":
        e.etapa = "desarrollo"
    elif datos.resultado == "ajustar":
        e.etapa = "investigacion"
    elif datos.resultado == "espera":
        e.estado = "en_espera"
    else:
        e.estado = "cerrado"
    e.actualizado_en = ahora()
    bd.flush()
    bitacora(bd, "decision_filtro", ctx, request, "expediente", e.folio,
             {"resultado": datos.resultado, "evaluacion": ev.numero if ev else None})
    bd.commit()
    return _decision_dict(bd, d)


@router.get("/expedientes/{folio}/decisiones/{decision_id}")
def ver_decision(folio: str, decision_id: int, ctx: Contexto = Depends(requiere(A.EXP_VER)), bd: Session = Depends(obtener_bd)) -> dict:
    """La decisión con lo que se vio ese día: evaluación, versiones y evidencia congeladas."""
    acc = acc_de(bd, ctx)
    e = A.expediente(bd, folio)
    d = bd.get(Decision, decision_id)
    if not d or d.expediente_id != e.expediente_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa decisión.")
    congelado = json.loads(d.congelado)
    return _decision_dict(bd, d) | {"congelado": congelado,
                                    "evaluacion_detalle": _evaluacion_dict(bd, acc, e, bd.get(Evaluacion, d.evaluacion_id)) if d.evaluacion_id else None,
                                    "ficha": _ficha_dict(bd, bd.get(FichaVersion, congelado["ficha_id"])) if congelado.get("ficha_id") else None}


# ---------------------------------------------------------------- PDF

@router.get("/expedientes/{folio}/pdf")
def exportar(folio: str, request: Request, ctx: Contexto = Depends(requiere(A.EXPORTAR)), bd: Session = Depends(obtener_bd)) -> Response:
    acc = acc_de(bd, ctx)
    e = A.expediente(bd, folio)
    formula = ex.formula_vigente(bd, e)
    contenido_formula = None  # None = restringida para esta persona
    if acc.ve_formula(e.expediente_id):
        contenido_formula = {"numero": formula.numero, "contenido": ex.leer_formula(formula)} if formula else {}
    datos = {"folio": e.folio, "nombre": e.nombre, "etapa": e.etapa, "estado": e.estado, "jurisdiccion": e.jurisdiccion,
             "categoria_sanitaria": e.categoria_sanitaria, "ficha": _ficha_dict(bd, ex.ficha_vigente(bd, e)),
             "formula": contenido_formula, "evidencia": _evidencia(bd, acc, e),
             "evaluacion": _evaluacion_dict(bd, acc, e, evs.ultima(bd, e)),
             "decisiones": [_decision_dict(bd, d) for d in bd.scalars(select(Decision).where(Decision.expediente_id == e.expediente_id))]}
    cuando = ahora().strftime("%Y-%m-%d %H:%M UTC")
    contenido = pdf.armar(datos, quien=ctx.usuario.nombre, cuando=cuando)
    bitacora(bd, "exportar_pdf", ctx, request, "expediente", e.folio, {"con_formula": contenido_formula is not None})
    bd.commit()
    return Response(contenido, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{e.folio}.pdf"', "Cache-Control": "no-store"})


