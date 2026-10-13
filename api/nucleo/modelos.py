"""Tablas del núcleo (esquema nucleo): identidad, acceso, módulos y bitácora.

Fuente: docs/modelos/nucleo_plataforma_v0.dbml. Las fechas se guardan en UTC sin zona.
"""
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Unicode, UnicodeText
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ESQUEMA = "nucleo"


def ahora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class OrganizacionExterna(Base):
    __tablename__ = "organizacion_externa"
    __table_args__ = {"schema": ESQUEMA}

    organizacion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(Unicode(20), default="proveedor")
    nombre: Mapped[str] = mapped_column(Unicode(200))
    rfc: Mapped[str | None] = mapped_column(Unicode(13))
    estatus: Mapped[str] = mapped_column(Unicode(20), default="activa")
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = {"schema": ESQUEMA}

    usuario_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(Unicode(10))  # interno / externo
    correo: Mapped[str] = mapped_column(Unicode(254), unique=True)
    nombre: Mapped[str] = mapped_column(Unicode(200))
    puesto: Mapped[str | None] = mapped_column(Unicode(120))
    area: Mapped[str | None] = mapped_column(Unicode(120))
    hash_contrasena: Mapped[str | None] = mapped_column(Unicode(255))
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    debe_cambiar_contrasena: Mapped[bool] = mapped_column(Boolean, default=False)
    organizacion_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.organizacion_externa.organizacion_id"))
    estatus: Mapped[str] = mapped_column(Unicode(20), default="invitado")  # invitado / activo / inactivo
    acepto_aviso_privacidad_en: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_acceso_en: Mapped[datetime | None] = mapped_column(DateTime)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)

    organizacion: Mapped[OrganizacionExterna | None] = relationship()
    roles: Mapped[list["Rol"]] = relationship(
        secondary=f"{ESQUEMA}.usuario_rol",
        primaryjoin="Usuario.usuario_id == UsuarioRol.usuario_id",
        secondaryjoin="Rol.rol_id == UsuarioRol.rol_id",
        viewonly=True,
    )


class Modulo(Base):
    __tablename__ = "modulo"
    __table_args__ = {"schema": ESQUEMA}

    modulo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(Unicode(40), unique=True)
    codigo_iniciativa: Mapped[str | None] = mapped_column(Unicode(20))
    nombre: Mapped[str] = mapped_column(Unicode(120))
    area: Mapped[str] = mapped_column(Unicode(120))
    descripcion: Mapped[str | None] = mapped_column(Unicode(400))
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.usuario.usuario_id"))
    estado: Mapped[str] = mapped_column(Unicode(20), default="en_diseno")
    tiene_portal_externo: Mapped[bool] = mapped_column(Boolean, default=False)
    orden_menu: Mapped[int] = mapped_column(Integer, default=100)
    icono: Mapped[str] = mapped_column(Unicode(40), default="mas")
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    responsable: Mapped[Usuario | None] = relationship()


class Permiso(Base):
    __tablename__ = "permiso"
    __table_args__ = {"schema": ESQUEMA}

    permiso_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    modulo_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.modulo.modulo_id"))  # nulo = plataforma
    codigo: Mapped[str] = mapped_column(Unicode(120), unique=True)
    descripcion: Mapped[str] = mapped_column(Unicode(300))

    modulo: Mapped[Modulo | None] = relationship()


class Rol(Base):
    __tablename__ = "rol"
    __table_args__ = {"schema": ESQUEMA}

    rol_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(Unicode(60), unique=True)
    modulo_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.modulo.modulo_id"))  # nulo = plataforma
    nombre: Mapped[str] = mapped_column(Unicode(120))
    descripcion: Mapped[str | None] = mapped_column(Unicode(300))
    para_tipo_usuario: Mapped[str] = mapped_column(Unicode(10))  # interno / externo

    permisos: Mapped[list[Permiso]] = relationship(secondary=f"{ESQUEMA}.rol_permiso", order_by=Permiso.permiso_id)


class RolPermiso(Base):
    __tablename__ = "rol_permiso"
    __table_args__ = {"schema": ESQUEMA}

    rol_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.rol.rol_id"), primary_key=True)
    permiso_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.permiso.permiso_id"), primary_key=True)


class UsuarioRol(Base):
    __tablename__ = "usuario_rol"
    __table_args__ = {"schema": ESQUEMA}

    usuario_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.usuario.usuario_id"), primary_key=True)
    rol_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.rol.rol_id"), primary_key=True)
    asignado_por: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.usuario.usuario_id"))
    asignado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Invitacion(Base):
    __tablename__ = "invitacion"
    __table_args__ = {"schema": ESQUEMA}

    invitacion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.usuario.usuario_id"))
    correo: Mapped[str] = mapped_column(Unicode(254))
    organizacion_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.organizacion_externa.organizacion_id"))
    modulo_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.modulo.modulo_id"))
    rol_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.rol.rol_id"))
    invitado_por: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.usuario.usuario_id"))
    token_hash: Mapped[str] = mapped_column(Unicode(64), index=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime)
    usada_en: Mapped[datetime | None] = mapped_column(DateTime)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class RestablecimientoContrasena(Base):
    __tablename__ = "restablecimiento_contrasena"
    __table_args__ = {"schema": ESQUEMA}

    restablecimiento_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.usuario.usuario_id"))
    token_hash: Mapped[str] = mapped_column(Unicode(64), index=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime)
    usado_en: Mapped[datetime | None] = mapped_column(DateTime)
    solicitado_desde_ip: Mapped[str | None] = mapped_column(Unicode(45))


class Sesion(Base):
    __tablename__ = "sesion"
    __table_args__ = {"schema": ESQUEMA}

    sesion_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.usuario.usuario_id"))
    token_hash: Mapped[str] = mapped_column(Unicode(64), unique=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    expira_en: Mapped[datetime] = mapped_column(DateTime)
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime)
    ip: Mapped[str | None] = mapped_column(Unicode(45))
    agente: Mapped[str | None] = mapped_column(Unicode(300))

    usuario: Mapped[Usuario] = relationship()


class Bitacora(Base):
    __tablename__ = "bitacora"
    __table_args__ = {"schema": ESQUEMA}

    bitacora_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.usuario.usuario_id"))
    modulo_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.modulo.modulo_id"))
    accion: Mapped[str] = mapped_column(Unicode(60))
    entidad: Mapped[str | None] = mapped_column(Unicode(60))
    entidad_id: Mapped[str | None] = mapped_column(Unicode(60))
    detalle: Mapped[str | None] = mapped_column(UnicodeText)
    ip: Mapped[str | None] = mapped_column(Unicode(45))
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
