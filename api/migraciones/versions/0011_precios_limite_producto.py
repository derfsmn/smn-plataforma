"""Radar de precios: límite del semáforo por producto vigilado (vacío = el general de Configuración).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("precio_vigilado", sa.Column("limite_pct", sa.Numeric(5, 2)), schema="compras")
    op.create_check_constraint("ck_precio_vigilado_limite", "precio_vigilado", "limite_pct >= 0 AND limite_pct <= 100", schema="compras")


def downgrade() -> None:
    op.drop_constraint("ck_precio_vigilado_limite", "precio_vigilado", schema="compras", type_="check")
    op.drop_column("precio_vigilado", "limite_pct", schema="compras")
