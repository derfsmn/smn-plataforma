"""Radar de precios: lo que regresó Google Shopping en la búsqueda de cada producto (para revisarlo y elegir a mano).

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("precio_corrida_producto", sa.Column("candidatos", sa.UnicodeText()), schema="compras")


def downgrade() -> None:
    op.drop_column("precio_corrida_producto", "candidatos", schema="compras")
