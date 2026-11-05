"""Consulta de la bitácora (solo lectura) para quien tiene nucleo.bitacora.ver."""
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from core.bd import obtener_bd
from core.seguridad import Contexto, requiere
from nucleo.modelos import Bitacora, Modulo, Usuario

router = APIRouter(prefix="/api/nucleo/bitacora", tags=["bitácora"])
VER = "nucleo.bitacora.ver"


class RenglonBitacora(BaseModel):
    id: int
    ocurrido_en: datetime
    usuario: str | None
    correo: str | None
    accion: str
    entidad: str | None
    entidad_id: str | None
    modulo: str | None
    detalle: dict | list | str | None
    ip: str | None


class PaginaBitacora(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    renglones: list[RenglonBitacora]


def _detalle(texto: str | None):
    if not texto:
        return None
    try:
        return json.loads(texto)
    except ValueError:
        return texto


def _utc(momento: datetime) -> datetime:
    return momento.astimezone(UTC).replace(tzinfo=None) if momento.tzinfo else momento


@router.get("", response_model=PaginaBitacora)
def consultar(
    accion: str | None = Query(None, max_length=60),
    buscar: str | None = Query(None, max_length=120, description="Nombre o correo de quien hizo la acción"),
    desde: datetime | None = Query(None, description="Desde este momento (incluido)"),
    hasta: datetime | None = Query(None, description="Hasta este momento (sin incluirlo)"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    _: Contexto = Depends(requiere(VER)),
    bd: Session = Depends(obtener_bd),
) -> PaginaBitacora:
    u = aliased(Usuario)
    condiciones = []
    if accion:
        condiciones.append(Bitacora.accion == accion)
    if buscar:
        patron = f"%{buscar.strip()}%"
        condiciones.append(or_(u.nombre.ilike(patron), u.correo.ilike(patron), Bitacora.detalle.ilike(patron)))
    # La web manda los límites del día en la hora local de quien consulta; en la base todo está en UTC
    if desde:
        condiciones.append(Bitacora.ocurrido_en >= _utc(desde))
    if hasta:
        condiciones.append(Bitacora.ocurrido_en < _utc(hasta))

    base = select(Bitacora, u, Modulo).outerjoin(u, u.usuario_id == Bitacora.usuario_id) \
        .outerjoin(Modulo, Modulo.modulo_id == Bitacora.modulo_id).where(*condiciones)
    total = bd.scalar(select(func.count()).select_from(base.subquery()))
    filas = bd.execute(base.order_by(Bitacora.bitacora_id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina))
    return PaginaBitacora(
        total=total, pagina=pagina, por_pagina=por_pagina,
        renglones=[
            RenglonBitacora(id=b.bitacora_id, ocurrido_en=b.ocurrido_en, usuario=quien.nombre if quien else None,
                            correo=quien.correo if quien else None, accion=b.accion, entidad=b.entidad,
                            entidad_id=b.entidad_id, modulo=m.area if m else None, detalle=_detalle(b.detalle), ip=b.ip)
            for b, quien, m in filas
        ],
    )


@router.get("/acciones", response_model=list[str])
def acciones(_: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> list[str]:
    return list(bd.scalars(select(Bitacora.accion).distinct().order_by(Bitacora.accion)))
