"""Grupos de tiendas por varios criterios: ventas, tendencia, mezcla y demografía (Censo 2020 del INEGI).

Pedido de Diego, 2026-10-29: «no podríamos hacer por ventas, por disminución importante, por demográficos y
mezcladas, quiero algo inteligente». Cada tienda guarda sus rasgos medidos y en qué va abajo de sus pares.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-29
"""
import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tienda_grupo", sa.Column("alertas", sa.UnicodeText), schema="datos")
    op.add_column("tienda_grupo", sa.Column("metricas", sa.UnicodeText), schema="datos")


def downgrade() -> None:
    op.drop_column("tienda_grupo", "metricas", schema="datos")
    op.drop_column("tienda_grupo", "alertas", schema="datos")
