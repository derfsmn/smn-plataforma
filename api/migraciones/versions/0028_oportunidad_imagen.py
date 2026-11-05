"""Buscar oportunidades: foto de cada producto recomendado.

Pedido de Diego, 2026-10-28: «no sé si en algún momento vemos la imagen del producto que crees debamos meter».

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("oportunidad", sa.Column("imagen", sa.Unicode(800), nullable=True), schema="compras")
    op.add_column("oportunidad", sa.Column("imagen_de", sa.Unicode(300), nullable=True), schema="compras")


def downgrade() -> None:
    op.drop_column("oportunidad", "imagen_de", schema="compras")
    op.drop_column("oportunidad", "imagen", schema="compras")
