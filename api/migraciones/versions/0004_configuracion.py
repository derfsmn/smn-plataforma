"""Ajustes de la plataforma editables desde la pantalla de Configuración.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

E = "nucleo"


def upgrade() -> None:
    op.create_table(
        "configuracion",
        sa.Column("clave", sa.Unicode(80), primary_key=True),
        sa.Column("valor", sa.Unicode(1000), nullable=False),
        sa.Column("actualizado_por", sa.Integer, sa.ForeignKey(f"{E}.usuario.usuario_id")),
        sa.Column("actualizado_en", sa.DateTime, nullable=False, server_default=sa.text("SYSUTCDATETIME()")),
        schema=E,
    )


def downgrade() -> None:
    op.drop_table("configuracion", schema=E)
