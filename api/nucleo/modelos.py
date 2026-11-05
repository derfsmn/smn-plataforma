"""Tablas del núcleo (esquema nucleo): identidad, acceso, módulos, bitácora, servicios comunes e IA.

Fuente: docs/modelos/nucleo_plataforma_v0.dbml. Las fechas se guardan en UTC sin zona.
"""
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Unicode, UnicodeText
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
    proveedor_intelisis: Mapped[str | None] = mapped_column(Unicode(10))  # clave en tblProveedores (datos.proveedor)
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


# ---------------------------------------------------------------- servicios comunes (etapa 4)

class Archivo(Base):
    __tablename__ = "archivo"
    __table_args__ = {"schema": ESQUEMA}

    archivo_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    modulo_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.modulo.modulo_id"))
    entidad: Mapped[str | None] = mapped_column(Unicode(60))
    entidad_id: Mapped[str | None] = mapped_column(Unicode(60))
    nombre_original: Mapped[str] = mapped_column(Unicode(255))
    tipo_contenido: Mapped[str] = mapped_column(Unicode(120))
    tamano_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(Unicode(64))
    ruta_almacenamiento: Mapped[str] = mapped_column(Unicode(400))
    subido_por: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.usuario.usuario_id"))
    subido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Notificacion(Base):
    __tablename__ = "notificacion"
    __table_args__ = {"schema": ESQUEMA}

    notificacion_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.usuario.usuario_id"))
    modulo_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.modulo.modulo_id"))
    canal: Mapped[str] = mapped_column(Unicode(10), default="app")  # app / correo
    titulo: Mapped[str] = mapped_column(Unicode(200))
    mensaje: Mapped[str] = mapped_column(Unicode(1000))
    liga: Mapped[str | None] = mapped_column(Unicode(400))
    # Evita repetir el mismo aviso (p. ej. "80 % del tope de IA" una vez por mes)
    clave: Mapped[str | None] = mapped_column(Unicode(120))
    enviada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    leida_en: Mapped[datetime | None] = mapped_column(DateTime)


# ---------------------------------------------------------------- IA (etapa 4)

class IaTarea(Base):
    __tablename__ = "ia_tarea"
    __table_args__ = {"schema": ESQUEMA}

    tarea_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    modulo_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.modulo.modulo_id"))
    codigo: Mapped[str] = mapped_column(Unicode(120), unique=True)
    descripcion: Mapped[str] = mapped_column(Unicode(300))
    proveedor_ia: Mapped[str] = mapped_column(Unicode(30), default="ollama")  # ollama / api / ollama_y_api_respaldo
    modelo: Mapped[str | None] = mapped_column(Unicode(120))  # nulo = el de la configuración
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    modulo: Mapped[Modulo | None] = relationship()


class IaPresupuesto(Base):
    __tablename__ = "ia_presupuesto"
    __table_args__ = {"schema": ESQUEMA}

    presupuesto_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alcance: Mapped[str] = mapped_column(Unicode(20))  # plataforma (mes) / modulo (mes) / usuario_dia
    modulo_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.modulo.modulo_id"))
    tope_mxn: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    aviso_pct: Mapped[int] = mapped_column(Integer, default=80)
    al_superar: Mapped[str] = mapped_column(Unicode(20), default="rechazar")  # rechazar / usar_ollama
    vigente_desde: Mapped[date] = mapped_column(Date)

    modulo: Mapped[Modulo | None] = relationship()


class IaLlamada(Base):
    __tablename__ = "ia_llamada"
    __table_args__ = {"schema": ESQUEMA}

    llamada_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tarea_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.ia_tarea.tarea_id"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.usuario.usuario_id"))
    proveedor_ia: Mapped[str] = mapped_column(Unicode(20))  # ollama / api
    modelo: Mapped[str | None] = mapped_column(Unicode(120))
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0)
    tokens_salida: Mapped[int] = mapped_column(Integer, default=0)
    costo_mxn: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    duracion_ms: Mapped[int] = mapped_column(Integer, default=0)
    resultado: Mapped[str] = mapped_column(Unicode(30))  # ok / error / rechazada_por_tope / rechazada_por_modelo
    detalle: Mapped[str | None] = mapped_column(Unicode(500))
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    tarea: Mapped[IaTarea] = relationship()
    usuario: Mapped[Usuario | None] = relationship()


class IaCostoReal(Base):
    """Lo que el proveedor de IA realmente cobró por día (UTC), bajado de su API de costos."""
    __tablename__ = "ia_costo_real"
    __table_args__ = {"schema": ESQUEMA}

    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    proveedor: Mapped[str] = mapped_column(Unicode(20), primary_key=True)
    costo_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    tipo_cambio: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    costo_mxn: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    obtenido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class ConfiguracionAjuste(Base):
    """Ajuste cambiado desde Administración > Configuración. Sobrepone el valor del .env (ver core/ajustes.py)."""
    __tablename__ = "configuracion"
    __table_args__ = {"schema": ESQUEMA}

    clave: Mapped[str] = mapped_column(Unicode(80), primary_key=True)
    valor: Mapped[str] = mapped_column(Unicode(1000))  # los secretos van cifrados
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.usuario.usuario_id"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)
