"""Contraseñas, tokens de un solo uso y sesiones con cookie.

- Contraseñas con Argon2 (argon2-cffi).
- Tokens (sesión, invitación, restablecimiento): aleatorios; en la base solo se guarda su SHA-256.
- La sesión viaja en una cookie httpOnly; nunca en localStorage.
"""
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.config import configuracion
from nucleo.modelos import Permiso, RolPermiso, Sesion, Usuario, UsuarioRol, ahora

COOKIE_SESION = "smn_td_sesion"
LONGITUD_MINIMA = 10
_hasher = PasswordHasher()


def cifrar_contrasena(contrasena: str) -> str:
    return _hasher.hash(contrasena)


def verificar_contrasena(hash_guardado: str | None, contrasena: str) -> bool:
    if not hash_guardado:
        return False
    try:
        return _hasher.verify(hash_guardado, contrasena)
    except (VerifyMismatchError, InvalidHashError):
        return False


def error_contrasena(contrasena: str) -> str | None:
    """Regla de la plataforma: 10 caracteres o más. Devuelve el motivo si no cumple."""
    if len(contrasena) < LONGITUD_MINIMA:
        return f"La contraseña debe tener al menos {LONGITUD_MINIMA} caracteres."
    if len(contrasena) > 128:
        return "La contraseña es demasiado larga."
    return None


def nuevo_token() -> tuple[str, str]:
    """Devuelve (token para la liga o cookie, hash para la base)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ip_de(request: Request) -> str | None:
    return request.client.host if request.client else None


def iniciar_sesion(bd: Session, usuario: Usuario, request: Request, response: Response) -> None:
    cfg = configuracion()
    token, token_hash = nuevo_token()
    bd.add(Sesion(
        usuario_id=usuario.usuario_id,
        token_hash=token_hash,
        expira_en=ahora() + timedelta(hours=cfg.sesion_horas),
        ip=ip_de(request),
        agente=(request.headers.get("user-agent") or "")[:300],
    ))
    response.set_cookie(
        COOKIE_SESION, token,
        max_age=cfg.sesion_horas * 3600,
        httponly=True,
        samesite="lax",
        secure=not cfg.es_desarrollo,
        path="/",
    )


def cerrar_sesion(bd: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE_SESION)
    if token:
        sesion = bd.scalar(select(Sesion).where(Sesion.token_hash == hash_token(token)))
        if sesion and not sesion.revocada_en:
            sesion.revocada_en = ahora()
    response.delete_cookie(COOKIE_SESION, path="/")


def revocar_sesiones(bd: Session, usuario_id: int) -> None:
    for s in bd.scalars(select(Sesion).where(Sesion.usuario_id == usuario_id, Sesion.revocada_en.is_(None))):
        s.revocada_en = ahora()


def permisos_de(bd: Session, usuario_id: int) -> set[str]:
    filas = bd.scalars(
        select(Permiso.codigo)
        .join(RolPermiso, RolPermiso.permiso_id == Permiso.permiso_id)
        .join(UsuarioRol, UsuarioRol.rol_id == RolPermiso.rol_id)
        .where(UsuarioRol.usuario_id == usuario_id)
    )
    return set(filas)


@dataclass
class Contexto:
    usuario: Usuario
    permisos: set[str] = field(default_factory=set)

    def puede(self, permiso: str) -> bool:
        return permiso in self.permisos


NO_AUTENTICADO = HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicia sesión para continuar.")


def usuario_actual(request: Request, bd: Session = Depends(obtener_bd)) -> Contexto:
    token = request.cookies.get(COOKIE_SESION)
    if not token:
        raise NO_AUTENTICADO
    sesion = bd.scalar(select(Sesion).where(Sesion.token_hash == hash_token(token)))
    if not sesion or sesion.revocada_en or sesion.expira_en < ahora():
        raise NO_AUTENTICADO
    usuario = sesion.usuario
    if usuario.estatus != "activo":
        raise NO_AUTENTICADO
    return Contexto(usuario=usuario, permisos=permisos_de(bd, usuario.usuario_id))


def requiere(permiso: str):
    """Dependencia: exige que el usuario tenga el permiso indicado."""

    def verificar(ctx: Contexto = Depends(usuario_actual)) -> Contexto:
        if not ctx.puede(permiso):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para esta acción.")
        return ctx

    return verificar
