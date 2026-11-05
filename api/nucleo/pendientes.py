"""Inicio: lo que le toca a cada quien hoy y el pulso de cada área, contado de las tablas reales.

Cada renglón se cuenta solo si la persona tiene el permiso de esa pantalla, y lleva a la pantalla que lo resuelve.
Solo regresa conteos y fechas: nunca nombres, correos ni RFC. Si una tabla todavía no existe en un equipo (migración
pendiente), ese renglón se omite y el resto sigue.
"""
import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, usuario_actual
from nucleo.modelos import Usuario

router = APIRouter(prefix="/api/nucleo", tags=["inicio"])
log = logging.getLogger(__name__)


class Pendiente(BaseModel):
    clave: str
    modulo: str  # código del módulo (compras, contraloria, metodos) o «admin»
    area: str
    texto: str
    cantidad: int
    accion: str
    href: str
    urgente: bool = False


class Pulso(BaseModel):
    clave: str
    texto: str
    valor: str
    detalle: str | None = None
    href: str


class Inicio(BaseModel):
    pendientes: list[Pendiente]
    pulso: list[Pulso]


def _contar(bd: Session, consulta) -> int:
    return int(bd.scalar(consulta) or 0)


def _seguro(bd: Session, clave: str, fn):
    try:
        return fn()
    except SQLAlchemyError:
        bd.rollback()
        log.warning("Inicio: no se pudo contar «%s» (¿falta una migración?)", clave)
        return None


def _fecha(d: date | datetime | None) -> str | None:
    if not d:
        return None
    meses = "ene feb mar abr may jun jul ago sep oct nov dic".split()
    return f"{d.day} {meses[d.month - 1]}"


def pendientes(bd: Session, permisos: set[str]) -> list[Pendiente]:
    salida: list[Pendiente] = []

    def agregar(permiso: str, clave: str, fn, **datos):
        if permiso not in permisos:
            return
        n = _seguro(bd, clave, fn)
        if n:
            salida.append(Pendiente(clave=clave, cantidad=n, **datos))

    # Contraloría
    from modulos.contraloria.modelos_diot import DiotIncidencia, DiotPeriodo, FiscalCriterio
    abiertas = (select(func.count()).select_from(DiotIncidencia).join(DiotPeriodo, DiotPeriodo.periodo_id == DiotIncidencia.periodo_id)
                .where(DiotIncidencia.estado == "pendiente", DiotPeriodo.estado != "cerrado"))
    agregar("contraloria.diot.ver", "diot_impacto", lambda: _contar(bd, abiertas.where(DiotIncidencia.impacto == "posible_impacto")),
            modulo="contraloria", area="Contraloría", texto="Diferencias de la DIOT que pueden cambiar el TXT",
            accion="Revisar", href="/contraloria/diot", urgente=True)
    agregar("contraloria.diot.ver", "diot_revisar", lambda: _contar(bd, abiertas.where(DiotIncidencia.impacto != "posible_impacto")),
            modulo="contraloria", area="Contraloría", texto="Avisos de la DIOT por revisar", accion="Revisar",
            href="/contraloria/diot")
    agregar("contraloria.criterios.aprobar", "criterios",
            lambda: _contar(bd, select(func.count()).select_from(FiscalCriterio).where(FiscalCriterio.estado == "pendiente")),
            modulo="contraloria", area="Contraloría", texto="Criterios fiscales esperando aprobación", accion="Aprobar",
            href="/contraloria/conocimiento")

    # Métodos y procedimientos
    from modulos.metodos.modelos import Alerta, Borrador
    agregar("metodos.aprobar", "borradores",
            lambda: _contar(bd, select(func.count()).select_from(Borrador).where(Borrador.estado == "listo")),
            modulo="metodos", area="Métodos", texto="Borradores de manual por revisar y aprobar", accion="Abrir",
            href="/metodos?vista=borradores")
    agregar("metodos.cargar", "contradicciones",
            lambda: _contar(bd, select(func.count()).select_from(Alerta).where(Alerta.estado == "abierta")),
            modulo="metodos", area="Métodos", texto="Manuales que se contradicen entre sí", accion="Ver",
            href="/metodos?vista=avisos", urgente=True)

    # Compras
    from modulos.compras.modelos import RadarSenal
    from modulos.compras.modelos_productos import Oportunidad, ProductoIdea
    from modulos.compras.modelos_propuestas import Propuesta
    agregar("compras.propuestas.revisar", "propuestas",
            lambda: _contar(bd, select(func.count()).select_from(Propuesta).where(Propuesta.estado.in_(("recibida", "en_revision")))),
            modulo="compras", area="Compras", texto="Propuestas de proveedores por revisar", accion="Revisar",
            href="/compras/propuestas")
    agregar("compras.productos.ver", "ideas",
            lambda: _contar(bd, select(func.count()).select_from(ProductoIdea).where(ProductoIdea.estado == "nueva")),
            modulo="compras", area="Compras", texto="Ideas de producto nuevas", accion="Ver", href="/compras/productos")
    agregar("compras.productos.ver", "oportunidades",
            lambda: _contar(bd, select(func.count()).select_from(Oportunidad).where(Oportunidad.estado == "nueva")),
            modulo="compras", area="Compras", texto="Oportunidades de producto sin revisar", accion="Ver",
            href="/compras/productos/oportunidades")
    from modulos.compras.modelos_comite import ComitePeticion, ComiteProducto, ComiteRevision
    agregar("compras.comite.ver", "comite_peticiones",
            lambda: _contar(bd, select(func.count()).select_from(ComitePeticion).where(ComitePeticion.estado == "abierta")),
            modulo="compras", area="Compras", texto="Peticiones del comité de producto nuevo sin atender", accion="Ver",
            href="/compras/propuestas/comite?vista=peticiones")
    agregar("compras.comite.prefiltrar", "comite_revisiones",
            lambda: _contar(bd, select(func.count()).select_from(ComiteRevision).join(
                ComiteProducto, ComiteProducto.item_id == ComiteRevision.item_id).where(
                ComiteRevision.resultado == "pendiente", ComiteProducto.decision == "aceptado")),
            modulo="compras", area="Compras", texto="Productos aceptados con revisión pendiente (inventario o regulación)",
            accion="Ver", href="/compras/propuestas/comite?vista=revisiones")
    agregar("compras.radar.ver", "senales",
            lambda: _contar(bd, select(func.count()).select_from(RadarSenal).where(RadarSenal.estado == "nueva")),
            modulo="compras", area="Compras", texto="Señales nuevas del radar de mercado", accion="Ver", href="/compras/radar")

    # Administración
    agregar("nucleo.usuarios.administrar", "invitaciones",
            lambda: _contar(bd, select(func.count()).select_from(Usuario).where(Usuario.estatus == "invitado")),
            modulo="admin", area="Administración", texto="Invitaciones que nadie ha aceptado", accion="Ver",
            href="/admin/usuarios")

    salida.sort(key=lambda p: not p.urgente)  # lo urgente primero; dentro, el orden de arriba
    return salida


def pulso(bd: Session, permisos: set[str]) -> list[Pulso]:
    salida: list[Pulso] = []

    if "compras.precios.ver" in permisos:
        from modulos.compras.modelos_precios import PrecioCorrida

        def precios():
            c = bd.scalars(select(PrecioCorrida).where(PrecioCorrida.estado.in_(("completa", "parcial")),
                                                       PrecioCorrida.origen.in_(("programado", "tardio", "manual")))
                           .order_by(PrecioCorrida.iniciado_en.desc()).limit(1)).first()
            if c:
                salida.append(Pulso(clave="precios", texto="Radar de precios", valor=f"{c.con_precios}/{c.productos}",
                                    detalle=f"con precio · corrida del {_fecha(c.fecha)}", href="/compras/precios"))
        _seguro(bd, "pulso_precios", precios)

    if "compras.productos.ver" in permisos:
        from modulos.compras.modelos_productos import ProductoEvaluacion

        def evaluados():
            n = _contar(bd, select(func.count()).select_from(ProductoEvaluacion)
                        .where(ProductoEvaluacion.estado == "lista", ProductoEvaluacion.vigente == True))  # noqa: E712
            salida.append(Pulso(clave="evaluados", texto="Productos evaluados", valor=f"{n:,}", detalle="con semáforo vigente",
                                href="/compras/productos"))
        _seguro(bd, "pulso_evaluados", evaluados)

    if "contraloria.diot.ver" in permisos:
        from modulos.contraloria.modelos_diot import DiotPeriodo

        def diot():
            n = _contar(bd, select(func.count()).select_from(DiotPeriodo).where(DiotPeriodo.estado != "cerrado"))
            salida.append(Pulso(clave="diot", texto="Periodos DIOT abiertos", valor=str(n), detalle="sin cerrar",
                                href="/contraloria/diot"))
        _seguro(bd, "pulso_diot", diot)

    if "metodos.consultar" in permisos:
        from modulos.metodos.modelos import Documento

        def manuales():
            n = _contar(bd, select(func.count()).select_from(Documento).where(Documento.estado == "vigente"))
            salida.append(Pulso(clave="manuales", texto="Manuales vigentes", valor=str(n), detalle="en Métodos",
                                href="/metodos?vista=documentos"))
        _seguro(bd, "pulso_manuales", manuales)

    if len(salida) < 4 and "nucleo.usuarios.administrar" in permisos:
        n = _contar(bd, select(func.count()).select_from(Usuario).where(Usuario.estatus == "activo"))
        salida.append(Pulso(clave="usuarios", texto="Usuarios activos", valor=str(n), detalle="internos y proveedores",
                            href="/admin/usuarios"))
    return salida[:4]


@router.get("/inicio", response_model=Inicio)
def inicio(ctx: Contexto = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> Inicio:
    permisos = set(ctx.permisos)
    return Inicio(pendientes=pendientes(bd, permisos), pulso=pulso(bd, permisos))
