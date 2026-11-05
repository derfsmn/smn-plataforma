"""IA: costo real por día bajado de la API de costos del proveedor.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ia_costo_real",
        sa.Column("fecha", sa.Date, primary_key=True),
        sa.Column("proveedor", sa.Unicode(20), primary_key=True),
        sa.Column("costo_usd", sa.Numeric(12, 4), nullable=False),
        sa.Column("tipo_cambio", sa.Numeric(10, 4), nullable=False),
        sa.Column("costo_mxn", sa.Numeric(12, 4), nullable=False),
        sa.Column("obtenido_en", sa.DateTime, nullable=False, server_default=sa.text("SYSUTCDATETIME()")),
        schema="nucleo",
    )


def downgrade() -> None:
    op.drop_table("ia_costo_real", schema="nucleo")
