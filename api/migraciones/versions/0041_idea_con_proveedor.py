"""Captura corta con proveedor: una idea de Compras puede llevar su proveedor de Intelisis o el nombre de uno nuevo,
para cargar muchos productos rápido mientras el proveedor no tiene acceso al portal. Pedido de Diego, 2026-11-04.

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("producto_idea", sa.Column("proveedor_intelisis", sa.Unicode(10), nullable=True), schema="compras")
    op.add_column("producto_idea", sa.Column("proveedor_nuevo", sa.Unicode(200), nullable=True), schema="compras")


def downgrade() -> None:
    op.drop_column("producto_idea", "proveedor_nuevo", schema="compras")
    op.drop_column("producto_idea", "proveedor_intelisis", schema="compras")
