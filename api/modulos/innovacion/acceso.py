"""Filtro de acceso único de Innovación Vidanat: se aplica antes de buscar, contestar, descargar o exportar.

- general: cualquiera con innovacion.recurso.ver.
- restringido: innovacion.restringido.ver y, si la fuente es de un folio, ser del equipo de ese folio.
- formula: innovacion.formula.ver y ser del equipo del folio. Sin excepción para administradores: para ver una
  fórmula hay que estar en el equipo (decisión de Diego, 2026-11-21).
"""
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.seguridad import Contexto
from modulos.innovacion.modelos import Expediente, ExpedienteEquipo

P = "innovacion."
VER = P + "recurso.ver"
CARGAR = P + "recurso.cargar"
REVISAR = P + "recurso.revisar"
RESTRINGIDO = P + "restringido.ver"
CONSULTAR = P + "consulta.usar"
INVESTIGAR = P + "investigacion.correr"
EXP_VER = P + "expediente.ver"
EXP_EDITAR = P + "expediente.editar"
FORMULA_VER = P + "formula.ver"
FORMULA_EDITAR = P + "formula.editar"
EVALUAR = P + "evaluacion.correr"
REGLA_PROPONER = P + "regla.proponer"
REGLA_PUBLICAR = P + "regla.publicar"
DICTAMINAR = P + "dictamen.emitir"
EXCEPCION = P + "excepcion.aprobar"
FILTRO = P + "decision.filtro"
EXPORTAR = P + "exportar"

# Rol que revisa cada tipo de fuente. El Líder I+D revisa todas mientras no haya Regulatorio ni Calidad.
REVISION_POR_TIPO = {"guia_regulatoria": "regulatoria", "norma": "regulatoria", "certificado": "calidad",
                     "ficha_tecnica": "calidad", "prueba_interna": "calidad"}
ROLES_POR_REVISION = {"cientifica": {"innovacion_lider"},
                      "regulatoria": {"innovacion_lider", "innovacion_regulatorio"},
                      "calidad": {"innovacion_lider", "innovacion_calidad"}}
NO_EXISTE = HTTPException(status.HTTP_404_NOT_FOUND, "No existe.")


@dataclass
class Acceso:
    usuario_id: int
    permisos: set[str]
    roles: set[str]
    equipo: set[int] = field(default_factory=set)  # expedientes donde está en el equipo

    def puede(self, permiso: str) -> bool:
        return permiso in self.permisos

    @property
    def admin(self) -> bool:
        return "admin" in self.roles

    def ve(self, clasificacion: str, expediente_id: int | None) -> bool:
        if not self.puede(VER):
            return False
        if clasificacion == "general":
            return True
        if clasificacion == "restringido":
            return self.puede(RESTRINGIDO) and (expediente_id is None or expediente_id in self.equipo)
        if clasificacion == "formula":
            return self.puede(FORMULA_VER) and expediente_id is not None and expediente_id in self.equipo
        return False

    def ve_formula(self, expediente_id: int) -> bool:
        return self.puede(FORMULA_VER) and expediente_id in self.equipo

    def edita_formula(self, expediente_id: int) -> bool:
        return self.puede(FORMULA_EDITAR) and expediente_id in self.equipo

    def revisa(self, tipo_revision: str) -> bool:
        return self.puede(REVISAR) and (self.admin or bool(self.roles & ROLES_POR_REVISION.get(tipo_revision, set())))


def de(bd: Session, ctx: Contexto) -> Acceso:
    equipo = set(bd.scalars(select(ExpedienteEquipo.expediente_id)
                            .where(ExpedienteEquipo.usuario_id == ctx.usuario.usuario_id)))
    return Acceso(ctx.usuario.usuario_id, set(ctx.permisos), {r.codigo for r in ctx.usuario.roles}, equipo)


def expediente(bd: Session, folio: str) -> Expediente:
    e = bd.scalar(select(Expediente).where(Expediente.folio == folio.upper()))
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese expediente.")
    return e


def tipo_revision(tipo_recurso: str) -> str:
    return REVISION_POR_TIPO.get(tipo_recurso, "cientifica")
