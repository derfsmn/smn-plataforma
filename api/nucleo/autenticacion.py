"""Inicio de sesión con correo y contraseña propios (sin Microsoft 365)."""
import logging
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.bd import motor, obtener_bd
from core.config import configuracion
from core.seguridad import (
    Contexto, cerrar_sesion, cifrar_contrasena, error_contrasena, hash_token, iniciar_sesion, ip_de, nuevo_token,
    permisos_de, revocar_sesiones, usuario_actual, verificar_contrasena, _hasher,
)
from nucleo.bitacora import registrar
from nucleo.notificaciones import correo, notificar
from nucleo.esquemas import (
    CambioContrasena, Credenciales, DatosLiga, ModuloSalida, NuevaContrasena, SolicitudRecuperacion, UsuarioSalida, Yo,
)
from nucleo.modelos import Invitacion, Modulo, Permiso, RestablecimientoContrasena, Usuario, ahora

router = APIRouter(prefix="/api/auth", tags=["acceso"])
log = logging.getLogger("uvicorn.error")

INTENTOS_MAXIMOS = 5
MINUTOS_BLOQUEO = 15
MINUTOS_LIGA_RECUPERACION = 30
INCORRECTO = "Correo o contraseña incorrectos."
# Hash de relleno para que tardar lo mismo exista o no el correo
_HASH_RELLENO = cifrar_contrasena("relleno-que-no-es-de-nadie")


def modulos_visibles(bd: Session, permisos: set[str]) -> list[Modulo]:
    """Admin de módulos ve todos; los demás, los módulos en piloto o activos donde tienen algún permiso."""
    modulos = bd.scalars(select(Modulo).order_by(Modulo.orden_menu)).all()
    if "nucleo.modulos.administrar" in permisos:
        return list(modulos)
    con_permiso = set(bd.scalars(select(Permiso.modulo_id).where(Permiso.codigo.in_(permisos or {""}))))
    return [m for m in modulos if m.estado in ("piloto", "activo") and m.modulo_id in con_permiso]


def armar_yo(bd: Session, usuario: Usuario) -> Yo:
    permisos = permisos_de(bd, usuario.usuario_id)
    modulos = modulos_visibles(bd, permisos) if usuario.tipo == "interno" else []
    return Yo(
        usuario=UsuarioSalida.de(usuario),
        permisos=sorted(permisos),
        modulos=[ModuloSalida.de(m) for m in modulos],
        debe_cambiar_contrasena=usuario.debe_cambiar_contrasena,
        entorno=configuracion().api_entorno,
    )


def _correo_en_segundo_plano(usuario_id: int, para: str, asunto: str, titulo: str, parrafos: list[str],
                             boton: tuple[str, str] | None = None, nota: str | None = None) -> bool:
    """Se corre después de responder, con su propia conexión, para no hacer esperar a la persona."""
    with Session(motor()) as bd:
        enviado = correo(bd, usuario_id, para, asunto, titulo, parrafos, boton=boton, nota=nota)
        bd.commit()
    return enviado


def _avisar_cambio_contrasena(bd: Session, usuario: Usuario, tareas: BackgroundTasks) -> None:
    notificar(bd, usuario.usuario_id, "Tu contraseña cambió",
              "Si no fuiste tú, avisa de inmediato al administrador de la plataforma.", liga="/perfil")
    tareas.add_task(
        _correo_en_segundo_plano, usuario.usuario_id, usuario.correo, "Tu contraseña cambió", f"Hola, {usuario.nombre}",
        ["La contraseña de tu cuenta en SMN - Transformación digital acaba de cambiar y se cerraron tus otras sesiones.",
         "Si fuiste tú, no tienes que hacer nada. Si no fuiste tú, avisa de inmediato al administrador de la plataforma."],
    )


def buscar_por_correo(bd: Session, correo: str) -> Usuario | None:
    return bd.scalar(select(Usuario).where(func.lower(Usuario.correo) == correo.strip().lower()))


@router.post("/iniciar", response_model=Yo)
def iniciar(datos: Credenciales, request: Request, response: Response, bd: Session = Depends(obtener_bd)) -> Yo:
    usuario = buscar_por_correo(bd, datos.correo)
    if not usuario or usuario.estatus != "activo" or not usuario.hash_contrasena:
        verificar_contrasena(_HASH_RELLENO, datos.contrasena)
        registrar(bd, "login_fallido", entidad="usuario", detalle={"correo": datos.correo[:254]}, ip=ip_de(request))
        bd.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INCORRECTO)

    if usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora():
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Tu cuenta está bloqueada por {INTENTOS_MAXIMOS} intentos fallidos. Intenta en {MINUTOS_BLOQUEO} minutos o recupera tu contraseña.",
        )

    if not verificar_contrasena(usuario.hash_contrasena, datos.contrasena):
        usuario.intentos_fallidos += 1
        detalle = {"intentos": usuario.intentos_fallidos}
        if usuario.intentos_fallidos >= INTENTOS_MAXIMOS:
            usuario.bloqueado_hasta = ahora() + timedelta(minutes=MINUTOS_BLOQUEO)
            usuario.intentos_fallidos = 0
            detalle["bloqueado_hasta"] = usuario.bloqueado_hasta
        registrar(bd, "login_fallido", usuario_id=usuario.usuario_id, entidad="usuario",
                  entidad_id=usuario.usuario_id, detalle=detalle, ip=ip_de(request))
        bd.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INCORRECTO)

    if _hasher.check_needs_rehash(usuario.hash_contrasena):
        usuario.hash_contrasena = cifrar_contrasena(datos.contrasena)
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_acceso_en = ahora()
    iniciar_sesion(bd, usuario, request, response)
    registrar(bd, "login", usuario_id=usuario.usuario_id, entidad="usuario", entidad_id=usuario.usuario_id, ip=ip_de(request))
    bd.commit()
    return armar_yo(bd, usuario)


@router.post("/salir", status_code=status.HTTP_204_NO_CONTENT)
def salir(request: Request, response: Response, bd: Session = Depends(obtener_bd)) -> None:
    cerrar_sesion(bd, request, response)
    bd.commit()


@router.get("/yo", response_model=Yo)
def yo(ctx: Contexto = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> Yo:
    return armar_yo(bd, ctx.usuario)


@router.post("/cambiar-contrasena", response_model=Yo)
def cambiar_contrasena(
    datos: CambioContrasena, request: Request, response: Response, tareas: BackgroundTasks,
    ctx: Contexto = Depends(usuario_actual), bd: Session = Depends(obtener_bd),
) -> Yo:
    usuario = ctx.usuario
    if not verificar_contrasena(usuario.hash_contrasena, datos.actual):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña actual no es correcta.")
    if motivo := error_contrasena(datos.nueva):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, motivo)
    if datos.nueva == datos.actual:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La nueva contraseña debe ser distinta de la actual.")
    usuario.hash_contrasena = cifrar_contrasena(datos.nueva)
    usuario.debe_cambiar_contrasena = False
    # Cierra las demás sesiones abiertas y deja una nueva en este navegador
    revocar_sesiones(bd, usuario.usuario_id)
    iniciar_sesion(bd, usuario, request, response)
    registrar(bd, "cambio_contrasena", usuario_id=usuario.usuario_id, entidad="usuario", entidad_id=usuario.usuario_id, ip=ip_de(request))
    _avisar_cambio_contrasena(bd, usuario, tareas)
    bd.commit()
    return armar_yo(bd, usuario)


@router.post("/recuperar")
def recuperar(datos: SolicitudRecuperacion, request: Request, tareas: BackgroundTasks,
              bd: Session = Depends(obtener_bd)) -> dict:
    """Siempre responde lo mismo, para no revelar qué correos tienen cuenta."""
    usuario = buscar_por_correo(bd, datos.correo)
    if usuario and usuario.estatus == "activo":
        token, token_hash = nuevo_token()
        bd.add(RestablecimientoContrasena(
            usuario_id=usuario.usuario_id, token_hash=token_hash,
            expira_en=ahora() + timedelta(minutes=MINUTOS_LIGA_RECUPERACION), solicitado_desde_ip=ip_de(request),
        ))
        registrar(bd, "recuperacion_solicitada", usuario_id=usuario.usuario_id, entidad="usuario",
                  entidad_id=usuario.usuario_id, ip=ip_de(request))
        bd.commit()
        liga = f"{configuracion().web_url}/restablecer/{token}"
        # Sin correo configurado, en desarrollo la liga se ve en la consola de la API
        if configuracion().es_desarrollo and not configuracion().smtp_servidor:
            log.info("Liga de recuperación para %s: %s", usuario.correo, liga)
        # El correo sale después de responder: así tarda lo mismo exista o no la cuenta
        tareas.add_task(
            _correo_en_segundo_plano, usuario.usuario_id, usuario.correo, "Recupera tu contraseña", f"Hola, {usuario.nombre}",
            ["Recibimos una solicitud para crear una contraseña nueva en SMN - Transformación digital.",
             f"La liga vence en {MINUTOS_LIGA_RECUPERACION} minutos y solo se puede usar una vez."],
            ("Crear contraseña nueva", liga),
            "Si no lo pediste, ignora este correo; tu contraseña no cambia.",
        )
    return {"mensaje": "Si el correo tiene cuenta, recibirá una liga para crear una nueva contraseña."}


def _restablecimiento_valido(bd: Session, token: str) -> RestablecimientoContrasena:
    r = bd.scalar(select(RestablecimientoContrasena).where(RestablecimientoContrasena.token_hash == hash_token(token)))
    if not r or r.usado_en or r.expira_en < ahora():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La liga ya se usó o venció. Pide una nueva.")
    return r


def _invitacion_valida(bd: Session, token: str) -> Invitacion:
    i = bd.scalar(select(Invitacion).where(Invitacion.token_hash == hash_token(token)))
    if not i or i.usada_en or i.expira_en < ahora():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La invitación ya se usó o venció. Pide una nueva al equipo de SMN.")
    return i


def _datos_liga(u: Usuario) -> DatosLiga:
    return DatosLiga(nombre=u.nombre, correo=u.correo, tipo=u.tipo, empresa=u.organizacion.nombre if u.organizacion else None)


@router.get("/restablecer/{token}", response_model=DatosLiga)
def ver_restablecimiento(token: str, bd: Session = Depends(obtener_bd)) -> DatosLiga:
    r = _restablecimiento_valido(bd, token)
    return _datos_liga(bd.get(Usuario, r.usuario_id))


@router.post("/restablecer/{token}")
def restablecer(token: str, datos: NuevaContrasena, request: Request, tareas: BackgroundTasks,
                bd: Session = Depends(obtener_bd)) -> dict:
    r = _restablecimiento_valido(bd, token)
    if motivo := error_contrasena(datos.contrasena):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, motivo)
    usuario = bd.get(Usuario, r.usuario_id)
    usuario.hash_contrasena = cifrar_contrasena(datos.contrasena)
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.debe_cambiar_contrasena = False
    r.usado_en = ahora()
    revocar_sesiones(bd, usuario.usuario_id)
    registrar(bd, "contrasena_restablecida", usuario_id=usuario.usuario_id, entidad="usuario",
              entidad_id=usuario.usuario_id, ip=ip_de(request))
    _avisar_cambio_contrasena(bd, usuario, tareas)
    bd.commit()
    return {"mensaje": "Listo. Ya puedes iniciar sesión con tu nueva contraseña."}


@router.get("/invitacion/{token}", response_model=DatosLiga)
def ver_invitacion(token: str, bd: Session = Depends(obtener_bd)) -> DatosLiga:
    i = _invitacion_valida(bd, token)
    return _datos_liga(bd.get(Usuario, i.usuario_id))


@router.post("/invitacion/{token}", response_model=Yo)
def aceptar_invitacion(
    token: str, datos: NuevaContrasena, request: Request, response: Response, bd: Session = Depends(obtener_bd),
) -> Yo:
    i = _invitacion_valida(bd, token)
    usuario = bd.get(Usuario, i.usuario_id)
    if usuario.estatus == "inactivo":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esta cuenta está desactivada.")
    if motivo := error_contrasena(datos.contrasena):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, motivo)
    if usuario.tipo == "externo" and not datos.acepta_aviso_privacidad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Para continuar acepta el aviso de privacidad.")
    usuario.hash_contrasena = cifrar_contrasena(datos.contrasena)
    usuario.estatus = "activo"
    usuario.ultimo_acceso_en = ahora()
    if datos.acepta_aviso_privacidad:
        usuario.acepto_aviso_privacidad_en = ahora()
    i.usada_en = ahora()
    iniciar_sesion(bd, usuario, request, response)
    registrar(bd, "invitacion_aceptada", usuario_id=usuario.usuario_id, entidad="usuario",
              entidad_id=usuario.usuario_id, ip=ip_de(request))
    if i.invitado_por and i.invitado_por != usuario.usuario_id:
        quien = f"{usuario.nombre} ({usuario.organizacion.nombre})" if usuario.organizacion else usuario.nombre
        notificar(bd, i.invitado_por, "Invitación aceptada", f"{quien} creó su contraseña y ya puede entrar.",
                  liga="/admin/usuarios")
    bd.commit()
    return armar_yo(bd, usuario)
