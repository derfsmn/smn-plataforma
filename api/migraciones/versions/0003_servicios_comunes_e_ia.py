"""Servicios comunes (archivos, notificaciones) y puerta de IA (etapa 4).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

E = "nucleo"
T = sa.Unicode
ahora = sa.text("SYSUTCDATETIME()")


def fk(tabla: str, columna: str) -> sa.ForeignKey:
    return sa.ForeignKey(f"{E}.{tabla}.{columna}")


def upgrade() -> None:
    op.create_table(
        "archivo",
        sa.Column("archivo_id", sa.BigInteger, primary_key=True),
        sa.Column("modulo_id", sa.Integer, fk("modulo", "modulo_id")),
        sa.Column("entidad", T(60)),
        sa.Column("entidad_id", T(60)),
        sa.Column("nombre_original", T(255), nullable=False),
        sa.Column("tipo_contenido", T(120), nullable=False),
        sa.Column("tamano_bytes", sa.BigInteger, nullable=False),
        sa.Column("sha256", T(64), nullable=False),
        sa.Column("ruta_almacenamiento", T(400), nullable=False),
        sa.Column("subido_por", sa.Integer, fk("usuario", "usuario_id"), nullable=False),
        sa.Column("subido_en", sa.DateTime, nullable=False, server_default=ahora),
        schema=E,
    )
    op.create_index("ix_archivo_entidad", "archivo", ["modulo_id", "entidad", "entidad_id"], schema=E)

    op.create_table(
        "notificacion",
        sa.Column("notificacion_id", sa.BigInteger, primary_key=True),
        sa.Column("usuario_id", sa.Integer, fk("usuario", "usuario_id"), nullable=False),
        sa.Column("modulo_id", sa.Integer, fk("modulo", "modulo_id")),
        sa.Column("canal", T(10), nullable=False, server_default="app"),
        sa.Column("titulo", T(200), nullable=False),
        sa.Column("mensaje", T(1000), nullable=False),
        sa.Column("liga", T(400)),
        sa.Column("clave", T(120)),
        sa.Column("enviada_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("leida_en", sa.DateTime),
        sa.CheckConstraint("canal IN ('app','correo')", name="ck_notificacion_canal"),
        schema=E,
    )
    op.create_index("ix_notificacion_usuario", "notificacion", ["usuario_id", "canal", "leida_en"], schema=E)

    op.create_table(
        "ia_tarea",
        sa.Column("tarea_id", sa.Integer, primary_key=True),
        sa.Column("modulo_id", sa.Integer, fk("modulo", "modulo_id")),
        sa.Column("codigo", T(120), nullable=False, unique=True),
        sa.Column("descripcion", T(300), nullable=False),
        sa.Column("proveedor_ia", T(30), nullable=False, server_default="ollama"),
        sa.Column("modelo", T(120)),
        sa.Column("activa", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.CheckConstraint("proveedor_ia IN ('ollama','api','ollama_y_api_respaldo')", name="ck_ia_tarea_proveedor"),
        schema=E,
    )

    op.create_table(
        "ia_presupuesto",
        sa.Column("presupuesto_id", sa.Integer, primary_key=True),
        sa.Column("alcance", T(20), nullable=False),
        sa.Column("modulo_id", sa.Integer, fk("modulo", "modulo_id")),
        sa.Column("tope_mxn", sa.Numeric(12, 2), nullable=False),
        sa.Column("aviso_pct", sa.Integer, nullable=False, server_default="80"),
        sa.Column("al_superar", T(20), nullable=False, server_default="rechazar"),
        sa.Column("vigente_desde", sa.Date, nullable=False),
        sa.CheckConstraint("alcance IN ('plataforma','modulo','usuario_dia')", name="ck_ia_presupuesto_alcance"),
        sa.CheckConstraint("al_superar IN ('rechazar','usar_ollama')", name="ck_ia_presupuesto_al_superar"),
        sa.CheckConstraint("tope_mxn >= 0 AND aviso_pct BETWEEN 1 AND 100", name="ck_ia_presupuesto_valores"),
        schema=E,
    )
    # Un solo tope por alcance (y por módulo)
    op.execute(f"CREATE UNIQUE INDEX ux_ia_presupuesto ON {E}.ia_presupuesto (alcance, modulo_id)")

    op.create_table(
        "ia_llamada",
        sa.Column("llamada_id", sa.BigInteger, primary_key=True),
        sa.Column("tarea_id", sa.Integer, fk("ia_tarea", "tarea_id"), nullable=False),
        sa.Column("usuario_id", sa.Integer, fk("usuario", "usuario_id")),
        sa.Column("proveedor_ia", T(20), nullable=False),
        sa.Column("modelo", T(120)),
        sa.Column("tokens_entrada", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_salida", sa.Integer, nullable=False, server_default="0"),
        sa.Column("costo_mxn", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("duracion_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("resultado", T(30), nullable=False),
        sa.Column("detalle", T(500)),
        sa.Column("ocurrido_en", sa.DateTime, nullable=False, server_default=ahora),
        schema=E,
    )
    op.create_index("ix_ia_llamada_fecha", "ia_llamada", ["ocurrido_en"], schema=E)


def downgrade() -> None:
    for tabla in ("ia_llamada", "ia_presupuesto", "ia_tarea", "notificacion", "archivo"):
        op.drop_table(tabla, schema=E)
