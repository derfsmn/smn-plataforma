"""Radar de productos: el producto nuevo se busca en Google Shopping y en las tiendas clave como en el radar de precios
(pedido de Diego, 2026-10-26: «que se evalúe con todo lo que tenemos»). La búsqueda queda como corrida «producto» del
radar de precios (para el gasto) y su resultado en la evaluación. También se guarda la revisión contra las políticas y
reglas de Compras.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def _origenes(extra: tuple[str, ...]) -> str:
    return "origen IN (" + ",".join(f"'{o}'" for o in ("programado", "tardio", "manual", "prueba", *extra)) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_precio_corrida_origen", "precio_corrida", schema="compras")
    op.create_check_constraint("ck_precio_corrida_origen", "precio_corrida", _origenes(("producto",)), schema="compras")
    op.add_column("producto_evaluacion", sa.Column("mercado", sa.UnicodeText), schema="compras")
    op.add_column("producto_evaluacion", sa.Column("politicas", sa.UnicodeText), schema="compras")


def downgrade() -> None:
    op.drop_column("producto_evaluacion", "politicas", schema="compras")
    op.drop_column("producto_evaluacion", "mercado", schema="compras")
    # Su gasto de DataForSEO se conserva: quedan como «prueba», que tampoco cuenta como corrida del radar
    op.execute("UPDATE compras.precio_corrida SET origen = 'prueba' WHERE origen = 'producto'")
    op.drop_constraint("ck_precio_corrida_origen", "precio_corrida", schema="compras")
    op.create_check_constraint("ck_precio_corrida_origen", "precio_corrida", _origenes(()), schema="compras")
