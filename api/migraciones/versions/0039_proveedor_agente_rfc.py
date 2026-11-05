"""Datos → Proveedores guarda el Agente y el RFC de tblProveedores, aunque vengan vacíos, para filtrar.
Pedido de Diego, 2026-11-03.

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proveedor", sa.Column("agente", sa.Unicode(10), nullable=True), schema="datos")
    op.add_column("proveedor", sa.Column("rfc", sa.Unicode(15), nullable=True), schema="datos")


def downgrade() -> None:
    op.drop_column("proveedor", "rfc", schema="datos")
    op.drop_column("proveedor", "agente", schema="datos")
