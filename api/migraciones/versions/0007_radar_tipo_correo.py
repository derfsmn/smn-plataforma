"""Radar: cada destinatario recibe el correo con botones de decisión o solo informativo.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("radar_destinatario",
                  sa.Column("tipo_correo", sa.Unicode(20), nullable=False, server_default="decision"),
                  schema="compras")
    op.create_check_constraint("ck_radar_destinatario_tipo_correo", "radar_destinatario",
                               "tipo_correo IN ('decision', 'informativo')", schema="compras")


def downgrade() -> None:
    op.drop_constraint("ck_radar_destinatario_tipo_correo", "radar_destinatario", schema="compras", type_="check")
    op.drop_column("radar_destinatario", "tipo_correo", schema="compras", mssql_drop_default=True)
