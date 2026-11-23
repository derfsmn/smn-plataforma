"""Expedientes de Vidanat: folio, equipo, ficha y fórmula versionadas, y los datos que lee el motor de reglas."""
import json
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from modulos.innovacion import almacen
from modulos.innovacion.modelos import (Expediente, FichaIngrediente, FichaVersion, FormulaVersion, Ingrediente, Recurso,
                                        RecursoVersion, Vinculo)
from nucleo.modelos import ahora

CAMPOS_FICHA = ("nombre_comercial", "presentacion", "porcion", "porciones_dia", "unidad_porcion", "beneficio",
                "poblacion", "modo_de_uso", "advertencias", "declaraciones", "categoria_sanitaria",
                "categoria_comercial", "jurisdiccion", "precio_objetivo", "notas")
CAMPOS_INGREDIENTE = ("ingrediente_id", "nombre", "tipo", "forma", "en_compuesto", "cantidad_compuesto",
                      "unidad_compuesto", "cantidad_activa", "unidad_activa", "fraccion_activa", "fuente_version_id", "nota")


def nuevo_folio(bd: Session) -> str:
    anio = ahora().year
    prefijo = f"VID-{anio}-"
    ultimo = bd.scalar(select(func.max(Expediente.folio)).where(Expediente.folio.like(f"{prefijo}%")))
    n = int(ultimo.rsplit("-", 1)[1]) + 1 if ultimo else 1
    return f"{prefijo}{n:04d}"


def ficha_vigente(bd: Session, e: Expediente) -> FichaVersion | None:
    return bd.scalar(select(FichaVersion).where(FichaVersion.expediente_id == e.expediente_id)
                     .order_by(FichaVersion.numero.desc()))


def formula_vigente(bd: Session, e: Expediente) -> FormulaVersion | None:
    return bd.scalar(select(FormulaVersion).where(FormulaVersion.expediente_id == e.expediente_id)
                     .order_by(FormulaVersion.numero.desc()))


def guardar_ficha(bd: Session, e: Expediente, datos: dict, ingredientes: list[dict], *, usuario_id: int,
                  nota: str | None = None) -> FichaVersion:
    """Versión n+1, congelada. La anterior no cambia."""
    n = (bd.scalar(select(func.max(FichaVersion.numero)).where(FichaVersion.expediente_id == e.expediente_id)) or 0) + 1
    f = formula_vigente(bd, e)
    limpio = {k: datos.get(k) for k in CAMPOS_FICHA if datos.get(k) not in (None, "", [])}
    v = FichaVersion(expediente_id=e.expediente_id, numero=n, datos=json.dumps(limpio, ensure_ascii=False, default=str),
                     formula_id=f.formula_id if f else None, nota=nota, creado_por=usuario_id)
    bd.add(v)
    bd.flush()
    for i, ing in enumerate(ingredientes, start=1):
        bd.add(FichaIngrediente(ficha_id=v.ficha_id, orden=i, **{k: ing.get(k) for k in CAMPOS_INGREDIENTE}))
    bd.flush()
    return v


def guardar_formula(bd: Session, e: Expediente, contenido: dict, *, usuario_id: int, nota: str | None = None) -> FormulaVersion:
    n = (bd.scalar(select(func.max(FormulaVersion.numero)).where(FormulaVersion.expediente_id == e.expediente_id)) or 0) + 1
    f = FormulaVersion(expediente_id=e.expediente_id, numero=n, nota=nota, creado_por=usuario_id,
                       contenido=almacen.cifrar(json.dumps(contenido, ensure_ascii=False, default=str).encode()))
    bd.add(f)
    bd.flush()
    return f


def leer_formula(f: FormulaVersion) -> dict:
    return json.loads(almacen.descifrar(f.contenido).decode())


def _documentos(bd: Session, vinculos_de: list[Vinculo]) -> list[dict]:
    salida = []
    for vi in vinculos_de:
        v = bd.get(RecursoVersion, vi.version_id)
        if not v:
            continue
        r = v.recurso
        if r.estado != "activo":
            continue
        salida.append({"tipo": r.tipo, "estado": v.estado, "vigente_hasta": v.vigente_hasta.isoformat() if v.vigente_hasta else None,
                       "version_id": v.version_id, "titulo": r.titulo})
    return salida


def datos_para_motor(bd: Session, e: Expediente, ficha: FichaVersion | None, formula: FormulaVersion | None) -> dict:
    """Lo que lee el motor: datos generales del expediente, la ficha, sus ingredientes (con el factor UI del catálogo y
    sus documentos vinculados) y, si hay, la fórmula técnica bajo «formula»."""
    datos = {"jurisdiccion": e.jurisdiccion, "categoria_sanitaria": e.categoria_sanitaria,
             "categoria_comercial": e.categoria_comercial, "presentacion": e.presentacion, "etapa": e.etapa}
    if ficha:
        datos.update(json.loads(ficha.datos or "{}"))
    datos["ingredientes"] = []
    for i in (ficha.ingredientes if ficha else []):
        d = {k: (float(getattr(i, k)) if k.startswith(("cantidad", "fraccion")) and getattr(i, k) is not None else getattr(i, k))
             for k in CAMPOS_INGREDIENTE}
        if i.ingrediente_id and (cat := bd.get(Ingrediente, i.ingrediente_id)):
            d["tipo"] = d.get("tipo") or cat.tipo
            if cat.factor_ui_ug is not None and cat.factor_version_id:
                d["factor_ui_ug"] = str(cat.factor_ui_ug)
            d["documentos"] = _documentos(bd, list(bd.scalars(select(Vinculo).where(
                Vinculo.ingrediente_id == i.ingrediente_id, Vinculo.tipo == "ingrediente"))))
        else:
            d["documentos"] = []
        datos["ingredientes"].append({k: v for k, v in d.items() if v is not None})
    datos["documentos"] = _documentos(bd, list(bd.scalars(select(Vinculo).where(
        Vinculo.expediente_id == e.expediente_id, Vinculo.tipo == "expediente"))))
    if formula:
        datos["formula"] = leer_formula(formula)
    return datos


def fuentes_restringidas(bd: Session, e: Expediente) -> int:
    return bd.scalar(select(func.count(Recurso.recurso_id)).where(Recurso.expediente_id == e.expediente_id)) or 0


def hoy() -> date:
    return date.today()
