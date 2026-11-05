"""Catálogo de productos: imagen por SKU en el CDN de la tienda en línea.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("producto", sa.Column("imagen_cdn", sa.Unicode(600)), schema="datos")
    op.add_column("producto", sa.Column("imagen_revisada_en", sa.DateTime), schema="datos")


def downgrade() -> None:
    op.drop_column("producto", "imagen_revisada_en", schema="datos")
    op.drop_column("producto", "imagen_cdn", schema="datos")
