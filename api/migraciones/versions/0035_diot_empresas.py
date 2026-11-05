"""DIOT: las tres empresas del proceso (SMN, ODP y PS). El RFC de SMN y PS se captura en la pantalla cuando Fiscal lo
confirme; mientras falte, el mes no se procesa. Pedido de Diego, 2026-10-30.

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

E = "contraloria"
EMPRESAS = [("SMN", "Super Mayoreo Naturista"), ("PS", "Promotora Saludanat")]


def upgrade() -> None:
    op.alter_column("diot_empresa", "rfc", existing_type=sa.Unicode(13), nullable=True, schema=E)
    for codigo, nombre in EMPRESAS:
        op.execute(f"IF NOT EXISTS (SELECT 1 FROM {E}.diot_empresa WHERE codigo = N'{codigo}') "
                   f"INSERT INTO {E}.diot_empresa (codigo, nombre, rfc, activa) VALUES (N'{codigo}', N'{nombre}', NULL, 1)")


def downgrade() -> None:
    for codigo, _ in EMPRESAS:
        op.execute(f"DELETE FROM {E}.diot_empresa WHERE codigo = N'{codigo}' AND NOT EXISTS "
                   f"(SELECT 1 FROM {E}.diot_periodo p WHERE p.empresa_id = {E}.diot_empresa.empresa_id)")
    op.alter_column("diot_empresa", "rfc", existing_type=sa.Unicode(13), nullable=False, schema=E)
