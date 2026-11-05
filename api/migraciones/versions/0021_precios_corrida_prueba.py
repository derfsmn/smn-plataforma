"""Radar de precios: corrida de prueba con una lista de SKU subida en Excel (pedido de Diego, 2026-10-26).

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("precio_corrida", sa.Column("lista", sa.UnicodeText), schema="compras")  # JSON: archivo, productos, no encontrados
    op.drop_constraint("ck_precio_corrida_origen", "precio_corrida", schema="compras")
    op.create_check_constraint("ck_precio_corrida_origen", "precio_corrida",
                               "origen IN ('programado','tardio','manual','prueba')", schema="compras")


def downgrade() -> None:
    op.execute("DELETE o FROM compras.precio_observacion o JOIN compras.precio_corrida c ON c.corrida_id = o.corrida_id WHERE c.origen = 'prueba'")
    op.execute("DELETE f FROM compras.precio_corrida_producto f JOIN compras.precio_corrida c ON c.corrida_id = f.corrida_id WHERE c.origen = 'prueba'")
    op.execute("UPDATE e SET corrida_id = NULL FROM compras.precio_envio e JOIN compras.precio_corrida c ON c.corrida_id = e.corrida_id WHERE c.origen = 'prueba'")
    op.execute("DELETE FROM compras.precio_corrida WHERE origen = 'prueba'")
    op.drop_constraint("ck_precio_corrida_origen", "precio_corrida", schema="compras")
    op.create_check_constraint("ck_precio_corrida_origen", "precio_corrida",
                               "origen IN ('programado','tardio','manual')", schema="compras")
    op.drop_column("precio_corrida", "lista", schema="compras")
