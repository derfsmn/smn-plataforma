"""DIOT: comprobaciones para validar el TXT sin ser fiscalista (TD003). Monto de cada renglón (para el embudo de lo
pagado a lo declarado), IVA acreditable de la declaración mensual capturado por Fiscal, revisiones (muestra de
proveedores, motivos de diferencias contra lo presentado) y firmas. Plan aprobado por Diego, 2026-10-30.

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

E = "contraloria"
USUARIO = "nucleo.usuario.usuario_id"
PERIODO = f"{E}.diot_periodo.periodo_id"


def upgrade() -> None:
    op.add_column("diot_operacion", sa.Column("monto", sa.Numeric(20, 6)), schema=E)
    op.add_column("diot_periodo", sa.Column("iva_declarado", sa.Numeric(20, 2)), schema=E)
    op.add_column("diot_periodo", sa.Column("iva_declarado_nota", sa.Unicode(500)), schema=E)
    op.add_column("diot_periodo", sa.Column("iva_declarado_por", sa.Integer, sa.ForeignKey(USUARIO)), schema=E)
    op.add_column("diot_periodo", sa.Column("iva_declarado_en", sa.DateTime), schema=E)
    op.create_table(
        "diot_revision",
        sa.Column("revision_id", sa.Integer, primary_key=True),
        sa.Column("periodo_id", sa.Integer, sa.ForeignKey(PERIODO), nullable=False),
        sa.Column("tipo", sa.Unicode(20), nullable=False),
        sa.Column("clave", sa.Unicode(40), nullable=False),
        sa.Column("motivo", sa.Unicode(30)),
        sa.Column("nota", sa.Unicode(1000)),
        sa.Column("huella", sa.Unicode(64)),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("momento", sa.DateTime, nullable=False),
        sa.CheckConstraint("tipo IN ('muestra','diferencia')", name="ck_diot_revision_tipo"),
        sa.UniqueConstraint("periodo_id", "tipo", "clave", name="uq_diot_revision"),
        schema=E,
    )
    op.create_table(
        "diot_firma",
        sa.Column("firma_id", sa.Integer, primary_key=True),
        sa.Column("periodo_id", sa.Integer, sa.ForeignKey(PERIODO), nullable=False),
        sa.Column("tipo", sa.Unicode(20), nullable=False),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("momento", sa.DateTime, nullable=False),
        sa.Column("nota", sa.Unicode(1000)),
        sa.Column("huella_txt", sa.Unicode(64), nullable=False),
        sa.Column("activa", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint("tipo IN ('revision','fiscal')", name="ck_diot_firma_tipo"),
        schema=E,
    )


def downgrade() -> None:
    op.drop_table("diot_firma", schema=E)
    op.drop_table("diot_revision", schema=E)
    for c in ("iva_declarado_en", "iva_declarado_por", "iva_declarado_nota", "iva_declarado"):
        op.drop_column("diot_periodo", c, schema=E)
    op.drop_column("diot_operacion", "monto", schema=E)
