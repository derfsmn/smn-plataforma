"""Radar de productos: en qué paso va cada evaluación mientras corre.

Diego, 2026-10-29: «la pantalla se queda así cargando, se tarda mucho en algún proceso». La evaluación ahora guarda su
avance en cada paso y la pantalla lo muestra.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-29
"""
import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("producto_evaluacion", sa.Column("avance", sa.Unicode(200)), schema="compras")


def downgrade() -> None:
    op.drop_column("producto_evaluacion", "avance", schema="compras")
