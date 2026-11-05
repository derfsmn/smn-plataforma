"""Notificaciones dentro de la plataforma (campana) y registro de correos enviados."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.correo import enviar
from core.seguridad import Contexto, usuario_actual
from nucleo.modelos import Notificacion, ahora

router = APIRouter(prefix="/api/notificaciones", tags=["notificaciones"])


def notificar(bd: Session, usuario_id: int, titulo: str, mensaje: str, *, liga: str | None = None,
              modulo_id: int | None = None, clave: str | None = None) -> bool:
    """Crea un aviso en la campana. Con `clave`, no lo repite si ese usuario ya lo tiene. Devuelve si se creó."""
    if clave and bd.scalar(select(Notificacion.notificacion_id).where(
            Notificacion.usuario_id == usuario_id, Notificacion.clave == clave)):
        return False
    bd.add(Notificacion(usuario_id=usuario_id, modulo_id=modulo_id, canal="app", titulo=titulo[:200],
                        mensaje=mensaje[:1000], liga=liga, clave=clave))
    return True


def correo(bd: Session, usuario_id: int, para: str, asunto: str, titulo: str, parrafos: list[str], *,
           boton: tuple[str, str] | None = None, nota: str | None = None) -> bool:
    """Envía un correo y deja constancia (sin la liga, que es secreta) en notificacion con canal 'correo'."""
    enviado = enviar(para, asunto, titulo, parrafos, boton, nota)
    if enviado:
        bd.add(Notificacion(usuario_id=usuario_id, canal="correo", titulo=asunto[:200], mensaje=" ".join(parrafos)[:1000]))
    return enviado


class NotificacionSalida(BaseModel):
    id: int
    titulo: str
    mensaje: str
    liga: str | None
    enviada_en: datetime
    leida: bool


class Bandeja(BaseModel):
    no_leidas: int
    notificaciones: list[NotificacionSalida]


@router.get("", response_model=Bandeja)
def bandeja(ctx: Contexto = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> Bandeja:
    mias = (Notificacion.usuario_id == ctx.usuario.usuario_id, Notificacion.canal == "app")
    filas = bd.scalars(select(Notificacion).where(*mias).order_by(Notificacion.enviada_en.desc(),
                                                                  Notificacion.notificacion_id.desc()).limit(30)).all()
    return Bandeja(
        no_leidas=bd.scalar(select(func.count()).select_from(Notificacion).where(*mias, Notificacion.leida_en.is_(None))),
        notificaciones=[NotificacionSalida(id=n.notificacion_id, titulo=n.titulo, mensaje=n.mensaje, liga=n.liga,
                                           enviada_en=n.enviada_en, leida=n.leida_en is not None) for n in filas],
    )


@router.post("/{notificacion_id}/leer", status_code=status.HTTP_204_NO_CONTENT)
def leer(notificacion_id: int, ctx: Contexto = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> None:
    n = bd.get(Notificacion, notificacion_id)
    if not n or n.usuario_id != ctx.usuario.usuario_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa notificación.")
    n.leida_en = n.leida_en or ahora()
    bd.commit()


@router.post("/leer-todas", status_code=status.HTTP_204_NO_CONTENT)
def leer_todas(ctx: Contexto = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> None:
    bd.execute(update(Notificacion).where(Notificacion.usuario_id == ctx.usuario.usuario_id,
                                          Notificacion.leida_en.is_(None)).values(leida_en=ahora()))
    bd.commit()
