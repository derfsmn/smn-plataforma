"""Administración del núcleo: usuarios, invitaciones, roles, permisos y módulos."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.config import configuracion
from core.seguridad import Contexto, ip_de, nuevo_token, requiere, revocar_sesiones, usuario_actual
from nucleo.autenticacion import modulos_visibles
from nucleo.bitacora import registrar
from nucleo.notificaciones import correo
from nucleo.esquemas import (
    CambioModulo, CambioUsuario, InvitacionCreada, Liga, ModuloSalida, NuevaInvitacion, PermisoSalida, PermisosDeRol,
    Resumen, RolSalida, UsuarioSalida,
)
from nucleo.modelos import (
    Bitacora, Invitacion, Modulo, Notificacion, OrganizacionExterna, Permiso, RestablecimientoContrasena, Rol, RolPermiso,
    Sesion, Usuario, UsuarioRol, ahora,
)

router = APIRouter(prefix="/api/nucleo", tags=["administración"])

DIAS_INVITACION = 7
HORAS_LIGA_ADMIN = 24
USUARIOS = "nucleo.usuarios.administrar"
ROLES = "nucleo.roles.administrar"
MODULOS = "nucleo.modulos.administrar"
# Permisos que el rol admin no puede perder, para que siempre haya quien administre
PERMISOS_ADMIN_FIJOS = {USUARIOS, ROLES}


def _no_encontrado(que: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"No existe {que}.")


def _usuario(bd: Session, usuario_id: int) -> Usuario:
    u = bd.get(Usuario, usuario_id)
    if not u:
        raise _no_encontrado("ese usuario")
    return u


# ---------------------------------------------------------------- resumen

@router.get("/resumen", response_model=Resumen)
def resumen(ctx: Contexto = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> Resumen:
    contar = lambda *condiciones: bd.scalar(select(func.count()).select_from(Usuario).where(*condiciones))  # noqa: E731
    return Resumen(
        iniciativas=len(modulos_visibles(bd, ctx.permisos)),
        usuarios_activos=contar(Usuario.estatus == "activo"),
        proveedores=contar(Usuario.tipo == "externo", Usuario.estatus != "inactivo"),
        invitaciones_pendientes=contar(Usuario.estatus == "invitado"),
    )


# ---------------------------------------------------------------- usuarios

@router.get("/usuarios", response_model=list[UsuarioSalida])
def listar_usuarios(_: Contexto = Depends(requiere(USUARIOS)), bd: Session = Depends(obtener_bd)) -> list[UsuarioSalida]:
    return [UsuarioSalida.de(u) for u in bd.scalars(select(Usuario).order_by(Usuario.creado_en.desc()))]


def _crear_invitacion(bd: Session, usuario: Usuario, rol: Rol, invitado_por: int) -> Liga:
    # Una invitación nueva anula las anteriores que sigan vigentes
    for vieja in bd.scalars(select(Invitacion).where(Invitacion.usuario_id == usuario.usuario_id, Invitacion.usada_en.is_(None))):
        vieja.expira_en = ahora()
    token, token_hash = nuevo_token()
    expira = ahora() + timedelta(days=DIAS_INVITACION)
    bd.add(Invitacion(
        usuario_id=usuario.usuario_id, correo=usuario.correo, organizacion_id=usuario.organizacion_id,
        modulo_id=rol.modulo_id, rol_id=rol.rol_id, invitado_por=invitado_por, token_hash=token_hash, expira_en=expira,
    ))
    return Liga(liga=f"{configuracion().web_url}/invitacion/{token}", expira_en=expira)


def _correo_invitacion(bd: Session, usuario: Usuario, invito: str, liga: str) -> bool:
    if usuario.tipo == "externo":
        empresa = usuario.organizacion.nombre if usuario.organizacion else "tu empresa"
        primero = f"{invito}, de Súper Naturista, te invitó a la plataforma SMN - Transformación digital como proveedor de {empresa}."
    else:
        primero = f"{invito} te invitó a la plataforma SMN - Transformación digital."
    enviado = correo(
        bd, usuario.usuario_id, usuario.correo, "Te invitaron a SMN - Transformación digital", f"Hola, {usuario.nombre}",
        [primero, f"Con esta liga creas tu contraseña. Vence en {DIAS_INVITACION} días y solo se puede usar una vez."],
        boton=("Crear mi contraseña", liga),
        nota="Si no esperabas esta invitación, ignora este correo.",
    )
    bd.commit()
    return enviado


@router.post("/usuarios/invitar", response_model=InvitacionCreada, status_code=status.HTTP_201_CREATED)
def invitar(
    datos: NuevaInvitacion, request: Request,
    ctx: Contexto = Depends(requiere(USUARIOS)), bd: Session = Depends(obtener_bd),
) -> InvitacionCreada:
    correo_nuevo = datos.correo.strip().lower()
    if bd.scalar(select(Usuario).where(func.lower(Usuario.correo) == correo_nuevo)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese correo.")
    rol = bd.scalar(select(Rol).where(Rol.codigo == datos.rol))
    if not rol or rol.para_tipo_usuario != datos.tipo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ese rol no corresponde al tipo de usuario.")

    organizacion = None
    if datos.tipo == "externo":
        if not datos.empresa:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe la razón social del proveedor.")
        rfc = datos.rfc.strip().upper() if datos.rfc else None
        organizacion = bd.scalar(select(OrganizacionExterna).where(OrganizacionExterna.rfc == rfc)) if rfc else None
        if not organizacion:
            organizacion = OrganizacionExterna(nombre=datos.empresa.strip(), rfc=rfc)
            bd.add(organizacion)
            bd.flush()

    usuario = Usuario(
        tipo=datos.tipo, correo=correo_nuevo, nombre=datos.nombre.strip(), estatus="invitado",
        area=datos.area if datos.tipo == "interno" else "Proveedor", puesto=datos.puesto,
        organizacion_id=organizacion.organizacion_id if organizacion else None,
    )
    bd.add(usuario)
    bd.flush()
    bd.add(UsuarioRol(usuario_id=usuario.usuario_id, rol_id=rol.rol_id, asignado_por=ctx.usuario.usuario_id))
    liga = _crear_invitacion(bd, usuario, rol, ctx.usuario.usuario_id)
    registrar(bd, "invitar", usuario_id=ctx.usuario.usuario_id, entidad="usuario", entidad_id=usuario.usuario_id,
              detalle={"correo": correo_nuevo, "tipo": datos.tipo, "rol": rol.codigo}, ip=ip_de(request))
    bd.commit()
    bd.refresh(usuario)
    liga.correo_enviado = _correo_invitacion(bd, usuario, ctx.usuario.nombre, liga.liga)
    return InvitacionCreada(usuario=UsuarioSalida.de(usuario), **liga.model_dump())


@router.post("/usuarios/{usuario_id}/reenviar-invitacion", response_model=Liga)
def reenviar_invitacion(
    usuario_id: int, request: Request, ctx: Contexto = Depends(requiere(USUARIOS)), bd: Session = Depends(obtener_bd),
) -> Liga:
    usuario = _usuario(bd, usuario_id)
    if usuario.estatus != "invitado":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se reenvía la invitación a quien aún no entra.")
    rol = usuario.roles[0] if usuario.roles else None
    if not rol:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El usuario no tiene rol asignado.")
    liga = _crear_invitacion(bd, usuario, rol, ctx.usuario.usuario_id)
    registrar(bd, "reenviar_invitacion", usuario_id=ctx.usuario.usuario_id, entidad="usuario", entidad_id=usuario_id, ip=ip_de(request))
    bd.commit()
    liga.correo_enviado = _correo_invitacion(bd, usuario, ctx.usuario.nombre, liga.liga)
    return liga


@router.post("/usuarios/{usuario_id}/liga-contrasena", response_model=Liga)
def liga_contrasena(
    usuario_id: int, request: Request, ctx: Contexto = Depends(requiere(USUARIOS)), bd: Session = Depends(obtener_bd),
) -> Liga:
    """Liga de un solo uso (24 h) para que la persona cree una contraseña nueva. Se envía por correo y se muestra."""
    usuario = _usuario(bd, usuario_id)
    if usuario.estatus != "activo":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo para cuentas activas.")
    token, token_hash = nuevo_token()
    expira = ahora() + timedelta(hours=HORAS_LIGA_ADMIN)
    bd.add(RestablecimientoContrasena(usuario_id=usuario_id, token_hash=token_hash, expira_en=expira, solicitado_desde_ip=ip_de(request)))
    registrar(bd, "liga_contrasena", usuario_id=ctx.usuario.usuario_id, entidad="usuario", entidad_id=usuario_id, ip=ip_de(request))
    bd.commit()
    liga = f"{configuracion().web_url}/restablecer/{token}"
    enviado = correo(
        bd, usuario.usuario_id, usuario.correo, "Crea una contraseña nueva", f"Hola, {usuario.nombre}",
        [f"{ctx.usuario.nombre} generó una liga para que crees una contraseña nueva en SMN - Transformación digital.",
         f"La liga vence en {HORAS_LIGA_ADMIN} horas y solo se puede usar una vez."],
        boton=("Crear contraseña nueva", liga),
        nota="Si no lo pediste, avisa al administrador de la plataforma. Tu contraseña actual sigue funcionando hasta que uses la liga.",
    )
    bd.commit()
    return Liga(liga=liga, expira_en=expira, correo_enviado=enviado)


@router.patch("/usuarios/{usuario_id}", response_model=UsuarioSalida)
def cambiar_usuario(
    usuario_id: int, datos: CambioUsuario, request: Request,
    ctx: Contexto = Depends(requiere(USUARIOS)), bd: Session = Depends(obtener_bd),
) -> UsuarioSalida:
    usuario = _usuario(bd, usuario_id)
    es_yo = usuario.usuario_id == ctx.usuario.usuario_id
    antes = {"estatus": usuario.estatus, "roles": [r.codigo for r in usuario.roles]}

    if datos.estatus and datos.estatus != usuario.estatus:
        if es_yo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes desactivar tu propia cuenta.")
        if datos.estatus == "inactivo":
            usuario.estatus = "inactivo"
            revocar_sesiones(bd, usuario.usuario_id)
        else:  # reactivar: si nunca creó contraseña vuelve a invitado
            usuario.estatus = "activo" if usuario.hash_contrasena else "invitado"
            usuario.intentos_fallidos = 0
            usuario.bloqueado_hasta = None

    if datos.roles is not None:
        roles = bd.scalars(select(Rol).where(Rol.codigo.in_(datos.roles or [""]))).all()
        if len(roles) != len(set(datos.roles)) or any(r.para_tipo_usuario != usuario.tipo for r in roles):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Algún rol no existe o no corresponde al tipo de usuario.")
        if not roles:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El usuario necesita al menos un rol.")
        if es_yo and "admin" in antes["roles"] and "admin" not in datos.roles:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes quitarte el rol de administrador.")
        bd.execute(delete(UsuarioRol).where(UsuarioRol.usuario_id == usuario.usuario_id))
        bd.add_all(UsuarioRol(usuario_id=usuario.usuario_id, rol_id=r.rol_id, asignado_por=ctx.usuario.usuario_id) for r in roles)

    bd.flush()
    bd.expire(usuario, ["roles"])
    registrar(bd, "actualizar", usuario_id=ctx.usuario.usuario_id, entidad="usuario", entidad_id=usuario_id,
              detalle={"antes": antes, "despues": {"estatus": usuario.estatus, "roles": [r.codigo for r in usuario.roles]}},
              ip=ip_de(request))
    bd.commit()
    return UsuarioSalida.de(usuario)



@router.delete("/usuarios/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_usuario(
    usuario_id: int, request: Request, ctx: Contexto = Depends(requiere(USUARIOS)), bd: Session = Depends(obtener_bd),
) -> None:
    """Borra una cuenta sin trabajo registrado (p. ej. de prueba) para liberar su correo. Si ya capturó algo, se desactiva."""
    usuario = _usuario(bd, usuario_id)
    if usuario.usuario_id == ctx.usuario.usuario_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes eliminar tu propia cuenta.")
    detalle = {"correo": usuario.correo, "nombre": usuario.nombre, "tipo": usuario.tipo, "estatus": usuario.estatus,
               "roles": [r.codigo for r in usuario.roles]}
    try:
        with bd.begin_nested():
            for tabla in (UsuarioRol, Invitacion, RestablecimientoContrasena, Sesion, Notificacion):
                bd.execute(delete(tabla).where(tabla.usuario_id == usuario_id))
            bd.execute(update(UsuarioRol).where(UsuarioRol.asignado_por == usuario_id).values(asignado_por=None))
            bd.execute(update(Invitacion).where(Invitacion.invitado_por == usuario_id).values(invitado_por=None))
            # La bitácora se conserva; sus renglones quedan sin usuario y el evento de abajo guarda quién era
            bd.execute(update(Bitacora).where(Bitacora.usuario_id == usuario_id).values(usuario_id=None))
            bd.delete(usuario)
            bd.flush()
    except IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Esta cuenta ya tiene trabajo registrado en la plataforma (propuestas, archivos u otros), así que no se puede eliminar. Desactívala.",
        ) from None
    registrar(bd, "eliminar", usuario_id=ctx.usuario.usuario_id, entidad="usuario", entidad_id=usuario_id, detalle=detalle,
              ip=ip_de(request))
    bd.commit()

# ---------------------------------------------------------------- roles y permisos

def _rol_salida(r: Rol, bd: Session) -> RolSalida:
    modulo = bd.get(Modulo, r.modulo_id) if r.modulo_id else None
    return RolSalida(codigo=r.codigo, nombre=r.nombre, descripcion=r.descripcion, para=r.para_tipo_usuario,
                     modulo=modulo.codigo if modulo else None, permisos=[p.codigo for p in r.permisos])


@router.get("/roles", response_model=list[RolSalida])
def listar_roles(ctx: Contexto = Depends(usuario_actual), bd: Session = Depends(obtener_bd)) -> list[RolSalida]:
    if not (ctx.puede(ROLES) or ctx.puede(USUARIOS)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para esta acción.")
    return [_rol_salida(r, bd) for r in bd.scalars(select(Rol).order_by(Rol.rol_id))]


@router.get("/permisos", response_model=list[PermisoSalida])
def listar_permisos(_: Contexto = Depends(requiere(ROLES)), bd: Session = Depends(obtener_bd)) -> list[PermisoSalida]:
    return [
        PermisoSalida(codigo=p.codigo, descripcion=p.descripcion, modulo=p.modulo.area if p.modulo else "Plataforma")
        for p in bd.scalars(select(Permiso).order_by(Permiso.permiso_id))
    ]


@router.put("/roles/{codigo}/permisos", response_model=RolSalida)
def cambiar_permisos_rol(
    codigo: str, datos: PermisosDeRol, request: Request,
    ctx: Contexto = Depends(requiere(ROLES)), bd: Session = Depends(obtener_bd),
) -> RolSalida:
    rol = bd.scalar(select(Rol).where(Rol.codigo == codigo))
    if not rol:
        raise _no_encontrado("ese rol")
    if rol.codigo == "admin" and not PERMISOS_ADMIN_FIJOS <= set(datos.permisos):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El administrador siempre conserva los permisos de usuarios y roles.")
    permisos = bd.scalars(select(Permiso).where(Permiso.codigo.in_(datos.permisos or [""]))).all()
    if len(permisos) != len(set(datos.permisos)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Algún permiso no existe.")
    antes = [p.codigo for p in rol.permisos]
    bd.execute(delete(RolPermiso).where(RolPermiso.rol_id == rol.rol_id))
    bd.add_all(RolPermiso(rol_id=rol.rol_id, permiso_id=p.permiso_id) for p in permisos)
    registrar(bd, "actualizar", usuario_id=ctx.usuario.usuario_id, entidad="rol", entidad_id=rol.codigo,
              detalle={"antes": antes, "despues": sorted(datos.permisos)}, ip=ip_de(request))
    bd.commit()
    bd.expire(rol)
    return _rol_salida(rol, bd)


# ---------------------------------------------------------------- módulos

@router.get("/modulos", response_model=list[ModuloSalida])
def listar_modulos(_: Contexto = Depends(requiere(MODULOS)), bd: Session = Depends(obtener_bd)) -> list[ModuloSalida]:
    return [ModuloSalida.de(m) for m in bd.scalars(select(Modulo).order_by(Modulo.orden_menu))]


@router.patch("/modulos/{codigo}", response_model=ModuloSalida)
def cambiar_modulo(
    codigo: str, datos: CambioModulo, request: Request,
    ctx: Contexto = Depends(requiere(MODULOS)), bd: Session = Depends(obtener_bd),
) -> ModuloSalida:
    modulo = bd.scalar(select(Modulo).where(Modulo.codigo == codigo))
    if not modulo:
        raise _no_encontrado("ese módulo")
    antes = modulo.estado
    modulo.estado = datos.estado
    registrar(bd, "cambiar_estado", usuario_id=ctx.usuario.usuario_id, modulo_id=modulo.modulo_id, entidad="modulo",
              entidad_id=codigo, detalle={"antes": antes, "despues": datos.estado}, ip=ip_de(request))
    bd.commit()
    return ModuloSalida.de(modulo)
