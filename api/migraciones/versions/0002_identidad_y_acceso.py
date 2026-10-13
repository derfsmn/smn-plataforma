"""Tablas de identidad y acceso del núcleo (etapa 3).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

E = "nucleo"
T = sa.Unicode
ahora = sa.text("SYSUTCDATETIME()")


def fk(tabla: str, columna: str) -> sa.ForeignKey:
    return sa.ForeignKey(f"{E}.{tabla}.{columna}")


def upgrade() -> None:
    op.create_table(
        "organizacion_externa",
        sa.Column("organizacion_id", sa.Integer, primary_key=True),
        sa.Column("tipo", T(20), nullable=False, server_default="proveedor"),
        sa.Column("nombre", T(200), nullable=False),
        sa.Column("rfc", T(13)),
        sa.Column("estatus", T(20), nullable=False, server_default="activa"),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("actualizado_en", sa.DateTime, nullable=False, server_default=ahora),
        schema=E,
    )
    # RFC único solo cuando existe
    op.execute(f"CREATE UNIQUE INDEX ux_organizacion_rfc ON {E}.organizacion_externa (rfc) WHERE rfc IS NOT NULL")

    op.create_table(
        "usuario",
        sa.Column("usuario_id", sa.Integer, primary_key=True),
        sa.Column("tipo", T(10), nullable=False),
        sa.Column("correo", T(254), nullable=False, unique=True),
        sa.Column("nombre", T(200), nullable=False),
        sa.Column("puesto", T(120)),
        sa.Column("area", T(120)),
        sa.Column("hash_contrasena", T(255)),
        sa.Column("intentos_fallidos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("bloqueado_hasta", sa.DateTime),
        sa.Column("debe_cambiar_contrasena", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("organizacion_id", sa.Integer, fk("organizacion_externa", "organizacion_id")),
        sa.Column("estatus", T(20), nullable=False, server_default="invitado"),
        sa.Column("acepto_aviso_privacidad_en", sa.DateTime),
        sa.Column("ultimo_acceso_en", sa.DateTime),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("actualizado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.CheckConstraint("tipo IN ('interno','externo')", name="ck_usuario_tipo"),
        sa.CheckConstraint("estatus IN ('invitado','activo','inactivo')", name="ck_usuario_estatus"),
        schema=E,
    )

    op.create_table(
        "modulo",
        sa.Column("modulo_id", sa.Integer, primary_key=True),
        sa.Column("codigo", T(40), nullable=False, unique=True),
        sa.Column("codigo_iniciativa", T(20)),
        sa.Column("nombre", T(120), nullable=False),
        sa.Column("area", T(120), nullable=False),
        sa.Column("descripcion", T(400)),
        sa.Column("responsable_id", sa.Integer, fk("usuario", "usuario_id")),
        sa.Column("estado", T(20), nullable=False, server_default="en_diseno"),
        sa.Column("tiene_portal_externo", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("orden_menu", sa.Integer, nullable=False, server_default="100"),
        sa.Column("icono", T(40), nullable=False, server_default="mas"),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.CheckConstraint("estado IN ('en_diseno','piloto','activo','retirado')", name="ck_modulo_estado"),
        schema=E,
    )

    op.create_table(
        "permiso",
        sa.Column("permiso_id", sa.Integer, primary_key=True),
        sa.Column("modulo_id", sa.Integer, fk("modulo", "modulo_id")),
        sa.Column("codigo", T(120), nullable=False, unique=True),
        sa.Column("descripcion", T(300), nullable=False),
        schema=E,
    )

    op.create_table(
        "rol",
        sa.Column("rol_id", sa.Integer, primary_key=True),
        sa.Column("codigo", T(60), nullable=False, unique=True),
        sa.Column("modulo_id", sa.Integer, fk("modulo", "modulo_id")),
        sa.Column("nombre", T(120), nullable=False),
        sa.Column("descripcion", T(300)),
        sa.Column("para_tipo_usuario", T(10), nullable=False),
        schema=E,
    )

    op.create_table(
        "rol_permiso",
        sa.Column("rol_id", sa.Integer, fk("rol", "rol_id"), primary_key=True),
        sa.Column("permiso_id", sa.Integer, fk("permiso", "permiso_id"), primary_key=True),
        schema=E,
    )

    op.create_table(
        "usuario_rol",
        sa.Column("usuario_id", sa.Integer, fk("usuario", "usuario_id"), primary_key=True),
        sa.Column("rol_id", sa.Integer, fk("rol", "rol_id"), primary_key=True),
        sa.Column("asignado_por", sa.Integer, fk("usuario", "usuario_id")),
        sa.Column("asignado_en", sa.DateTime, nullable=False, server_default=ahora),
        schema=E,
    )

    op.create_table(
        "invitacion",
        sa.Column("invitacion_id", sa.Integer, primary_key=True),
        sa.Column("usuario_id", sa.Integer, fk("usuario", "usuario_id"), nullable=False),
        sa.Column("correo", T(254), nullable=False),
        sa.Column("organizacion_id", sa.Integer, fk("organizacion_externa", "organizacion_id")),
        sa.Column("modulo_id", sa.Integer, fk("modulo", "modulo_id")),
        sa.Column("rol_id", sa.Integer, fk("rol", "rol_id"), nullable=False),
        sa.Column("invitado_por", sa.Integer, fk("usuario", "usuario_id")),
        sa.Column("token_hash", T(64), nullable=False, index=True),
        sa.Column("expira_en", sa.DateTime, nullable=False),
        sa.Column("usada_en", sa.DateTime),
        sa.Column("creada_en", sa.DateTime, nullable=False, server_default=ahora),
        schema=E,
    )

    op.create_table(
        "restablecimiento_contrasena",
        sa.Column("restablecimiento_id", sa.Integer, primary_key=True),
        sa.Column("usuario_id", sa.Integer, fk("usuario", "usuario_id"), nullable=False),
        sa.Column("token_hash", T(64), nullable=False, index=True),
        sa.Column("expira_en", sa.DateTime, nullable=False),
        sa.Column("usado_en", sa.DateTime),
        sa.Column("solicitado_desde_ip", T(45)),
        schema=E,
    )

    op.create_table(
        "sesion",
        sa.Column("sesion_id", sa.BigInteger, primary_key=True),
        sa.Column("usuario_id", sa.Integer, fk("usuario", "usuario_id"), nullable=False),
        sa.Column("token_hash", T(64), nullable=False, unique=True),
        sa.Column("creada_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("expira_en", sa.DateTime, nullable=False),
        sa.Column("revocada_en", sa.DateTime),
        sa.Column("ip", T(45)),
        sa.Column("agente", T(300)),
        schema=E,
    )

    op.create_table(
        "bitacora",
        sa.Column("bitacora_id", sa.BigInteger, primary_key=True),
        sa.Column("usuario_id", sa.Integer, fk("usuario", "usuario_id")),
        sa.Column("modulo_id", sa.Integer, fk("modulo", "modulo_id")),
        sa.Column("accion", T(60), nullable=False),
        sa.Column("entidad", T(60)),
        sa.Column("entidad_id", T(60)),
        sa.Column("detalle", sa.UnicodeText),
        sa.Column("ip", T(45)),
        sa.Column("ocurrido_en", sa.DateTime, nullable=False, server_default=ahora),
        schema=E,
    )


def downgrade() -> None:
    for tabla in [
        "bitacora", "sesion", "restablecimiento_contrasena", "invitacion", "usuario_rol",
        "rol_permiso", "rol", "permiso", "modulo", "usuario", "organizacion_externa",
    ]:
        op.drop_table(tabla, schema=E)
