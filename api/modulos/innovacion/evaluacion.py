"""Evaluaciones de reglas (inmutables), revisiones manuales, excepciones, compuerta y decisión del Filtro.

Una evaluación guarda por resultado la versión de la regla y de su fuente, los datos que leyó y la versión del motor.
Cambiar la ficha o la fórmula, o publicar o retirar una regla, crea otra evaluación; la anterior no se toca.
"""
import json
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from modulos.innovacion import expedientes as ex
from modulos.innovacion import motor
from modulos.innovacion.modelos import (ETAPAS, Evaluacion, EvaluacionResultado, Excepcion, Expediente, Pendiente,
                                        Regla, RecursoVersion, ReglaVersion, Revision)
from nucleo.modelos import ahora


def reglas_aplicables(bd: Session, dia: date) -> list[ReglaVersion]:
    return [rv for rv in bd.scalars(select(ReglaVersion).where(ReglaVersion.estado == "publicada"))
            if motor.vigente(rv.vigente_desde, rv.vigente_hasta, dia)]


def _alcance(rv: ReglaVersion) -> dict:
    return json.loads(rv.alcance) if rv.alcance else {}


def _aviso_fuente(bd: Session, rv: ReglaVersion, dia: date) -> str | None:
    if not rv.fuente_version_id:
        return None
    v = bd.get(RecursoVersion, rv.fuente_version_id)
    if not v:
        return None
    if v.estado == "sustituido":
        return "Fuente por revisar: la versión citada ya fue sustituida"
    if v.vigente_hasta and v.vigente_hasta < dia:
        return f"Fuente por revisar: venció el {v.vigente_hasta.isoformat()}"
    return None


def _valor(datos: dict, ruta: str):
    actual = datos
    for parte in ruta.replace("]", "").replace("[", ".").split("."):
        if isinstance(actual, list):
            try:
                actual = actual[int(parte) - 1]
            except (ValueError, IndexError):
                return None
        elif isinstance(actual, dict):
            actual = actual.get(parte)
        else:
            return None
    return actual


def _dictamen_vigente(bd: Session, e: Expediente, rv: ReglaVersion, datos: dict) -> Revision | None:
    """Un dictamen vale para la versión de la regla y la ficha que revisó; si cambió un dato relevante, no se arrastra."""
    r = bd.scalar(select(Revision).where(Revision.expediente_id == e.expediente_id,
                                         Revision.regla_version_id == rv.regla_version_id,
                                         Revision.estado == "dictaminada").order_by(Revision.dictaminada_en.desc()))
    if not r:
        return None
    campos = json.loads(rv.campos_relevantes) if rv.campos_relevantes else []
    if campos and r.ficha_id:
        anterior = ex.datos_para_motor(bd, e, bd.get(ex.FichaVersion, r.ficha_id), None)
        if any(_valor(anterior, c) != _valor(datos, c) for c in campos):
            return None
    return r


def evaluar(bd: Session, e: Expediente, *, motivo: str, usuario_id: int | None, regla_version_id: int | None = None,
            dia: date | None = None) -> Evaluacion:
    dia = dia or date.today()
    ficha = ex.ficha_vigente(bd, e)
    formula = ex.formula_vigente(bd, e)
    datos = ex.datos_para_motor(bd, e, ficha, formula)
    numero = (bd.scalar(select(func.max(Evaluacion.numero)).where(Evaluacion.expediente_id == e.expediente_id)) or 0) + 1
    ev = Evaluacion(expediente_id=e.expediente_id, numero=numero, motivo=motivo, regla_version_id=regla_version_id,
                    ficha_id=ficha.ficha_id if ficha else None, formula_id=formula.formula_id if formula else None,
                    etapa=e.etapa, motor=motor.VERSION, resumen="{}", creada_por=usuario_id)
    bd.add(ev)
    bd.flush()
    aplicables = reglas_aplicables(bd, dia)
    sustituidas: dict[int, str] = {}
    for rv in aplicables:
        if rv.sustituye_a and motor.en_alcance(_alcance(rv), datos)[0]:
            sustituidas[rv.sustituye_a] = rv.regla.codigo
    conteo = {"cumple": 0, "incumple": 0, "pendiente": 0, "no_aplica": 0}
    for rv in aplicables:
        aviso = _aviso_fuente(bd, rv, dia)
        dentro, fuera = motor.en_alcance(_alcance(rv), datos)
        usados, faltantes = {}, []
        if rv.regla_id in sustituidas:
            valor, texto = "no_aplica", f"Sustituida por {sustituidas[rv.regla_id]} en este alcance"
        elif not dentro:
            valor, texto = "no_aplica", fuera
        elif rv.modo in ("manual", "asistida"):
            previo = _dictamen_vigente(bd, e, rv, datos)
            if previo:
                valor, texto = previo.dictamen, f"Dictamen del {previo.dictaminada_en:%Y-%m-%d}: {(previo.motivo or '')[:300]}"
            else:
                valor, texto = "pendiente", f"Esperando dictamen · {rv.rol_revisor or 'revisor'}"
        else:
            try:
                r = motor.evaluar(json.loads(rv.condicion or "{}"), datos, hoy=dia)
                valor, texto, usados, faltantes = r.valor, r.motivo(), r.usados, r.faltantes
            except motor.CondicionInvalida as err:
                valor, texto = "pendiente", f"La condición de la regla no se pudo evaluar: {err}"
            if valor == "pendiente" and rv.si_falta == "incumple":
                valor = "incumple"
        if aviso and rv.exige_fuente_vigente and valor == "cumple":
            valor, texto = "pendiente", aviso
        res = EvaluacionResultado(evaluacion_id=ev.evaluacion_id, regla_version_id=rv.regla_version_id, resultado=valor,
                                  severidad=rv.severidad, motivo=texto[:1000],
                                  datos_usados=json.dumps(usados, ensure_ascii=False) if usados else None,
                                  faltantes=json.dumps(faltantes, ensure_ascii=False) if faltantes else None,
                                  aviso_fuente=aviso)
        bd.add(res)
        bd.flush()
        conteo[valor] += 1
        if valor == "pendiente" and rv.modo in ("manual", "asistida") and dentro and rv.regla_id not in sustituidas:
            abierta = bd.scalar(select(Revision).where(Revision.expediente_id == e.expediente_id,
                                                       Revision.regla_version_id == rv.regla_version_id,
                                                       Revision.estado == "asignada"))
            if abierta:  # la revisión abierta pasa a esta evaluación, con la ficha nueva
                abierta.resultado_id, abierta.ficha_id = res.resultado_id, ficha.ficha_id if ficha else None
            else:
                bd.add(Revision(expediente_id=e.expediente_id, resultado_id=res.resultado_id,
                                regla_version_id=rv.regla_version_id, ficha_id=ficha.ficha_id if ficha else None,
                                rol=rv.rol_revisor, vence_en=ahora() + timedelta(days=rv.plazo_dias or 5)))
    ev.resumen = json.dumps(conteo)
    bd.flush()
    return ev


def ultima(bd: Session, e: Expediente) -> Evaluacion | None:
    return bd.scalar(select(Evaluacion).where(Evaluacion.expediente_id == e.expediente_id)
                     .order_by(Evaluacion.numero.desc()))


def excepciones_vigentes(bd: Session, e: Expediente, dia: date | None = None) -> dict[int, Excepcion]:
    dia = dia or date.today()
    return {x.regla_id: x for x in bd.scalars(select(Excepcion).where(
        Excepcion.expediente_id == e.expediente_id, Excepcion.estado == "aprobada", Excepcion.vence_en >= dia))}


def _aplica_a_etapa(rv: ReglaVersion, etapa: str) -> bool:
    destino = _alcance(rv).get("etapa_destino")
    if not destino:
        return True
    destinos = destino if isinstance(destino, list) else [destino]
    return any(d in ETAPAS and ETAPAS.index(d) <= ETAPAS.index(etapa) for d in destinos)


def compuerta(bd: Session, e: Expediente, etapa: str) -> dict:
    """Bloqueantes abiertos para pasar a `etapa`: severidad bloqueante, resultado distinto de cumple o no aplica, sin
    excepción vigente. Las de severidad «mayor» se muestran pero no detienen."""
    ev = ultima(bd, e)
    if not ev:
        return {"etapa": etapa, "puede_avanzar": False, "evaluacion": None, "bloqueantes_abiertos": [],
                "mayores_abiertos": [], "motivo": "Falta evaluar el expediente."}
    excepciones = excepciones_vigentes(bd, e)
    bloqueantes, mayores = [], []
    for res in ev.resultados:
        if res.resultado in ("cumple", "no_aplica"):
            continue
        rv = bd.get(ReglaVersion, res.regla_version_id)
        if not _aplica_a_etapa(rv, etapa) or rv.regla_id in excepciones:
            continue
        item = {"regla": rv.regla.codigo, "version": rv.numero, "resultado": res.resultado, "motivo": res.motivo,
                "resultado_id": res.resultado_id}
        if res.severidad == "bloqueante":
            bloqueantes.append(item)
        elif res.severidad == "mayor":
            mayores.append(item)
    pendientes = [{"id": p.pendiente_id, "descripcion": p.descripcion, "fecha_limite": p.fecha_limite}
                  for p in bd.scalars(select(Pendiente).where(Pendiente.expediente_id == e.expediente_id,
                                                              Pendiente.estado == "abierto", Pendiente.determinante))]
    return {"etapa": etapa, "puede_avanzar": not bloqueantes, "evaluacion": ev.numero,
            "bloqueantes_abiertos": bloqueantes, "mayores_abiertos": mayores, "pendientes_determinantes": pendientes,
            "excepciones_vigentes": [{"regla": bd.get(Regla, x.regla_id).codigo, "vence_en": x.vence_en.isoformat()}
                                     for x in excepciones.values()],
            "motivo": None if not bloqueantes else f"{len(bloqueantes)} bloqueantes abiertos."}


def reevaluar_abiertos(bd: Session, rv: ReglaVersion, *, motivo: str, usuario_id: int | None) -> int:
    """Al publicar o retirar una regla: otra evaluación para cada expediente abierto en su alcance."""
    n = 0
    for e in bd.scalars(select(Expediente).where(Expediente.estado != "cerrado")):
        ficha = ex.ficha_vigente(bd, e)
        if not ficha:
            continue
        datos = ex.datos_para_motor(bd, e, ficha, None)
        if motor.en_alcance(_alcance(rv), datos)[0]:
            evaluar(bd, e, motivo="regla", usuario_id=usuario_id, regla_version_id=rv.regla_version_id)
            n += 1
    return n
