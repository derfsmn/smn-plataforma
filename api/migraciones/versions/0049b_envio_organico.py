"""compras.precio_envio acepta la búsqueda normal de Google («organico») para investigar afuera (17 nov 2026).

Revision ID: 0049b
Revises: 0049
"""
from alembic import op

revision = "0049b"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_precio_envio_tipo", "precio_envio", schema="compras", type_="check")
    op.create_check_constraint("ck_precio_envio_tipo", "precio_envio", "tipo IN ('productos','vendedores','organico')",
                               schema="compras")


def downgrade() -> None:
    op.execute("DELETE FROM compras.precio_envio WHERE tipo = 'organico'")
    op.drop_constraint("ck_precio_envio_tipo", "precio_envio", schema="compras", type_="check")
    op.create_check_constraint("ck_precio_envio_tipo", "precio_envio", "tipo IN ('productos','vendedores')",
                               schema="compras")
