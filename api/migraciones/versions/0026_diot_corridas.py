"""DIOT: cada «Procesar» es una corrida con sus 8 pasos (los del proceso de Fiscal) y la bitácora de lo que hizo.

Pedido de Diego, 2026-10-28: que siga el mismo proceso que el equipo de Fiscal, que se vea cada paso mientras corre y
que deje registro de todo (no una caja negra).

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

E = "contraloria"
USUARIO = "nucleo.usuario.usuario_id"


def upgrade() -> None:
    op.create_table(
        "diot_corrida",
        sa.Column("corrida_id", sa.Integer, primary_key=True),
        sa.Column("periodo_id", sa.Integer, sa.ForeignKey(f"{E}.diot_periodo.periodo_id"), nullable=False),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("resultado", sa.Unicode(500)),
        sa.Column("iniciada_por", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("iniciada_en", sa.DateTime, nullable=False),
        sa.Column("terminada_en", sa.DateTime),
        sa.CheckConstraint("estado IN ('en_curso','terminada','detenida','fallida')", name="ck_diot_corrida_estado"),
        schema=E,
    )
    op.create_index("ix_diot_corrida_periodo", "diot_corrida", ["periodo_id", "corrida_id"], schema=E)
    op.create_table(
        "diot_corrida_paso",
        sa.Column("paso_id", sa.Integer, primary_key=True),
        sa.Column("corrida_id", sa.Integer, sa.ForeignKey(f"{E}.diot_corrida.corrida_id"), nullable=False),
        sa.Column("orden", sa.Integer, nullable=False),
        sa.Column("nombre", sa.Unicode(100), nullable=False),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("resumen", sa.Unicode(1000)),
        sa.Column("inicio_en", sa.DateTime),
        sa.Column("fin_en", sa.DateTime),
        sa.UniqueConstraint("corrida_id", "orden", name="uq_diot_corrida_paso"),
        sa.CheckConstraint("estado IN ('pendiente','en_curso','ok','aviso','detenido','no_ejecutado')",
                           name="ck_diot_corrida_paso_estado"),
        schema=E,
    )
    op.create_table(
        "diot_corrida_log",
        sa.Column("log_id", sa.Integer, primary_key=True),
        sa.Column("corrida_id", sa.Integer, sa.ForeignKey(f"{E}.diot_corrida.corrida_id"), nullable=False),
        sa.Column("orden_paso", sa.Integer, nullable=False),
        sa.Column("momento", sa.DateTime, nullable=False),
        sa.Column("nivel", sa.Unicode(10), nullable=False),
        sa.Column("mensaje", sa.Unicode(1000), nullable=False),
        sa.Column("detalle", sa.UnicodeText),
        sa.CheckConstraint("nivel IN ('info','ok','aviso','error')", name="ck_diot_corrida_log_nivel"),
        schema=E,
    )
    op.create_index("ix_diot_corrida_log", "diot_corrida_log", ["corrida_id", "log_id"], schema=E)


def downgrade() -> None:
    for t in ("diot_corrida_log", "diot_corrida_paso", "diot_corrida"):
        op.drop_table(t, schema=E)
