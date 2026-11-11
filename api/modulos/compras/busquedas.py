"""Búsqueda de proveedor: de una oportunidad o idea bien evaluada a las personas que le buscan quién la surta.

Flujo (pedido de Diego, 2026-11-09: «esas iniciativas ya evaluadas y con buena evaluación deberían llegar a los
stakeholders para que les busquen proveedores»):
1. Una idea sin proveedor (sea de «Buscar oportunidades» o capturada por Compras) sale verde en el semáforo → se abre
   sola una búsqueda (con amarillo también, si el ajuste lo pide). Compras también la puede abrir a mano.
2. Les llega un aviso (campana y correo) a quienes tienen el permiso `compras.busquedas.atender`.
3. Una persona la toma, registra a quién contactó y qué dijo.
4. Se cierra con el proveedor encontrado (la idea se vuelve a evaluar con él, ahora con rentabilidad y proveedor, y queda
   lista para el comité) o sin proveedor, con motivo.
No se inventan proveedores: el que se registra lo escribe una persona o se elige de Intelisis.
"""
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import configuracion
from modulos.compras.modelos_busquedas import BusquedaAvance, BusquedaProveedor
from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
from nucleo.modelos import Modulo, Permiso, RolPermiso, Usuario, UsuarioRol, ahora
from nucleo.notificaciones import correo, notificar

log = logging.getLogger(__name__)

VER = "compras.busquedas.ver"
ATENDER = "compras.busquedas.atender"
ABIERTAS = ("sin_tomar", "buscando")
ESTADOS = {"sin_tomar": "Sin responsable", "buscando": "Buscando", "encontrado": "Proveedor encontrado",
           "sin_proveedor": "Sin proveedor", "cancelada": "Cancelada"}
RESULTADOS = {"sin_respuesta": "Sin respuesta", "interesado": "Interesado", "cotizo": "Mandó cotización",
              "no_surte": "No lo surte"}


def colores_automaticos() -> set[str]:
    cfg = configuracion()
    return {c for c, si in (("verde", cfg.busquedas_auto_verde), ("amarillo", cfg.busquedas_auto_amarillo)) if si}


def con_permiso(bd: Session, codigo: str) -> list[Usuario]:
    """Internos activos con ese permiso por alguno de sus roles."""
    return list(bd.scalars(
        select(Usuario).distinct()
        .join(UsuarioRol, UsuarioRol.usuario_id == Usuario.usuario_id)
        .join(RolPermiso, RolPermiso.rol_id == UsuarioRol.rol_id)
        .join(Permiso, Permiso.permiso_id == RolPermiso.permiso_id)
        .where(Permiso.codigo == codigo, Usuario.tipo == "interno", Usuario.estatus == "activo")))


def de_idea(bd: Session, idea_id: int, *, abiertas: bool = False) -> BusquedaProveedor | None:
    q = select(BusquedaProveedor).where(BusquedaProveedor.idea_id == idea_id)
    if abiertas:
        q = q.where(BusquedaProveedor.estado.in_(ABIERTAS))
    return bd.scalar(q.order_by(BusquedaProveedor.busqueda_id.desc()))


def color_de(e: ProductoEvaluacion | None) -> str | None:
    return (e.color_final or e.color) if e else None


def avance(b: BusquedaProveedor, texto: str, usuario_id: int | None, tipo: str = "estado",
           proveedor: str | None = None, resultado: str | None = None) -> None:
    b.avances.append(BusquedaAvance(tipo=tipo, texto=texto[:1000], proveedor=proveedor, resultado=resultado,
                                    usuario_id=usuario_id, creado_en=ahora()))


def _liga(b: BusquedaProveedor) -> str:
    return f"/compras/propuestas/busquedas/{b.busqueda_id}"


def _avisar(bd: Session, usuarios: list[Usuario], titulo: str, mensaje: str, b: BusquedaProveedor, clave: str,
            boton: str, sin: int | None = None) -> int:
    modulo = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "compras"))
    web = configuracion().web_url.rstrip("/")
    n = 0
    for u in usuarios:
        if u.usuario_id == sin:
            continue
        if notificar(bd, u.usuario_id, titulo, mensaje, liga=_liga(b), modulo_id=modulo, clave=f"{clave}:{u.usuario_id}"):
            n += 1
            try:
                correo(bd, u.usuario_id, u.correo, titulo, f"Hola, {u.nombre}", [mensaje],
                       boton=(boton, f"{web}{_liga(b)}"))
            except Exception:  # noqa: BLE001  el aviso en la campana ya quedó
                log.exception("Búsqueda de proveedor %s: no se pudo mandar el correo", b.busqueda_id)
    return n


def abrir(bd: Session, idea: ProductoIdea, e: ProductoEvaluacion | None, *, origen: str, usuario_id: int | None,
          nota: str | None = None) -> BusquedaProveedor:
    """Abre la búsqueda (o regresa la que ya está abierta), pasa la idea a «Buscar proveedor» y avisa."""
    if b := de_idea(bd, idea.idea_id, abiertas=True):
        return b
    b = BusquedaProveedor(idea_id=idea.idea_id, evaluacion_id=e.evaluacion_id if e else None, origen=origen,
                          estado="sin_tomar", color=color_de(e), puntaje=e.puntaje if e else None, nota=nota,
                          creada_por=usuario_id, creada_en=ahora())
    bd.add(b)
    if e and e.color_final and e.puntaje is not None:
        como = f"Compras lo puso {e.color_final} (el semáforo dio {e.puntaje} de 100)"
    elif e and e.puntaje is not None:
        como = f"salió {e.color} con {e.puntaje} de 100 en el semáforo"
    else:
        como = "Compras la pidió"
    avance(b, f"Se abrió la búsqueda: {como}." + (f" Nota: {nota}" if nota else ""), usuario_id)
    idea.estado, idea.actualizada_en = "buscar_proveedor", ahora()
    bd.flush()
    _avisar(bd, con_permiso(bd, ATENDER), f"Buscar proveedor: {idea.nombre}"[:200],
            f"«{idea.nombre}»: {como} y no tiene quién nos lo surta. Tómala y registra a quién contactas.",
            b, f"busqueda:{b.busqueda_id}", "Ver la búsqueda", sin=usuario_id)
    return b


def al_evaluar(bd: Session, e: ProductoEvaluacion) -> BusquedaProveedor | None:
    """Después de cada evaluación: si una idea sin proveedor salió con el color que pide proveedor, abre su búsqueda.
    Una sola vez por idea: si ya tuvo una (abierta o cerrada), no se vuelve a abrir sola."""
    if e.estado != "lista" or not e.vigente or not e.idea_id or color_de(e) not in colores_automaticos():
        return None
    idea = bd.get(ProductoIdea, e.idea_id)
    if not idea or idea.estado == "descartada" or idea.proveedor_intelisis or idea.proveedor_nuevo:
        return None
    if de_idea(bd, idea.idea_id):
        return None
    b = abrir(bd, idea, e, origen="automatica", usuario_id=None)
    bd.commit()
    return b


def despues_de_evaluar(bd: Session, e: ProductoEvaluacion) -> None:
    """Lo llama el radar de productos al terminar; nunca tumba la evaluación."""
    try:
        al_evaluar(bd, e)
    except Exception:  # noqa: BLE001
        bd.rollback()
        log.exception("No se pudo abrir la búsqueda de proveedor de la evaluación %s", e.evaluacion_id)


def al_descartar(bd: Session, idea: ProductoIdea, usuario_id: int) -> None:
    """Si Compras descarta la idea en el radar, su búsqueda abierta se cancela."""
    if b := de_idea(bd, idea.idea_id, abiertas=True):
        b.estado, b.cerrada_por, b.cerrada_en = "cancelada", usuario_id, ahora()
        b.motivo_cierre = "La idea se descartó en el radar de productos."
        avance(b, "Se canceló: la idea se descartó en el radar de productos.", usuario_id)


def avisar_encontrado(bd: Session, b: BusquedaProveedor, idea: ProductoIdea, proveedor: str, usuario_id: int) -> None:
    """Quien sube productos al comité se entera de que ya hay proveedor."""
    _avisar(bd, con_permiso(bd, "compras.comite.subir"), f"Ya hay proveedor: {idea.nombre}"[:200],
            f"Se encontró proveedor para «{idea.nombre}»: {proveedor}. Se volvió a evaluar con él y se puede subir al "
            "comité de producto nuevo.", b, f"busqueda_encontrado:{b.busqueda_id}", "Ver la búsqueda", sin=usuario_id)


def costo_texto(c: Decimal | None) -> str:
    return f"${c:,.2f} sin IVA" if c is not None else "sin costo todavía"
