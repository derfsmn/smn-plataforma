"""Semáforo de productos más explicativo: cada factor guarda cómo se calificó y qué lo haría subir.

Pedido de Diego, 2026-10-29: «hay algunas cosas que no se entienden tan bien en la redacción del semáforo, quiero que
sea muy explicativo y muy entendible».

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-29
"""
import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("producto_evaluacion_factor", sa.Column("calculo", sa.Unicode(1000)), schema="compras")
    op.add_column("producto_evaluacion_factor", sa.Column("mejora", sa.Unicode(600)), schema="compras")


def downgrade() -> None:
    op.drop_column("producto_evaluacion_factor", "mejora", schema="compras")
    op.drop_column("producto_evaluacion_factor", "calculo", schema="compras")
