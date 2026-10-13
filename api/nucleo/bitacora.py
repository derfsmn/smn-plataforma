"""Bitácora de acciones. Solo se inserta; nunca se edita ni se borra."""
import json

from sqlalchemy.orm import Session

from nucleo.modelos import Bitacora


def registrar(
    bd: Session,
    accion: str,
    *,
    usuario_id: int | None = None,
    entidad: str | None = None,
    entidad_id: object = None,
    detalle: dict | None = None,
    ip: str | None = None,
    modulo_id: int | None = None,
) -> None:
    bd.add(Bitacora(
        accion=accion,
        usuario_id=usuario_id,
        modulo_id=modulo_id,
        entidad=entidad,
        entidad_id=None if entidad_id is None else str(entidad_id),
        detalle=json.dumps(detalle, ensure_ascii=False, default=str) if detalle else None,
        ip=ip,
    ))
