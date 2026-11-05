"""Radar de precios: otras publicaciones de Google Shopping que son el mismo producto (para juntar todos sus precios).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("precio_coincidencia", sa.Column("iguales", sa.UnicodeText()), schema="compras")


def downgrade() -> None:
    op.drop_column("precio_coincidencia", "iguales", schema="compras")
