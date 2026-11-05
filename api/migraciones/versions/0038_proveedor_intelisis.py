"""Productos nuevos con proveedor actual o nuevo: Compras puede capturar la propuesta por el proveedor (todavía sin
contactos) y ligar la empresa con su clave de proveedor en Intelisis. Pedido de Diego, 2026-11-03.

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizacion_externa", sa.Column("proveedor_intelisis", sa.Unicode(10), nullable=True), schema="nucleo")


def downgrade() -> None:
    op.drop_column("organizacion_externa", "proveedor_intelisis", schema="nucleo")
