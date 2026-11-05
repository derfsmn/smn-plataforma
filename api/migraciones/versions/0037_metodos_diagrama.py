"""Métodos y procedimientos: diagrama de flujo de cada manual (pasos, puestos y decisiones) y archivos de apoyo que se
suben al pedir un borrador. El manual hecho con IA se descarga en PDF con su diagrama. Pedido de Diego, 2026-11-01.

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-01
"""
import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

E = "metodos"


def upgrade() -> None:
    op.add_column("borrador", sa.Column("flujo", sa.UnicodeText(), nullable=True), schema=E)
    op.add_column("borrador", sa.Column("archivos", sa.Unicode(1000), nullable=True), schema=E)
    op.add_column("documento", sa.Column("flujo", sa.UnicodeText(), nullable=True), schema=E)


def downgrade() -> None:
    op.drop_column("documento", "flujo", schema=E)
    op.drop_column("borrador", "archivos", schema=E)
    op.drop_column("borrador", "flujo", schema=E)
