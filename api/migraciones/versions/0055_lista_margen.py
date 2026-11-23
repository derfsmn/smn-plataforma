"""Tipo de producto (lista de márgenes A–F) y precio de membresía en ideas y propuestas (22 nov 2026).

Diego: «al momento de dar de alta un producto que se meta el tipo de producto para que lo evalúe con ese rendimiento»
y «hay que considerar el precio de lista y el precio de membresía». Las listas salen de «MARGENES PARA CALCULO DE
PRECIOS.xlsx» de Compras (29 oct 2026). En la propuesta los pone Compras al revisarla: el proveedor no los ve.

Revision ID: 0055
Revises: 0054
"""
import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

E = "compras"
TABLAS = ("producto_idea", "propuesta")


def upgrade() -> None:
    for t in TABLAS:
        op.add_column(t, sa.Column("lista_margen", sa.Unicode(1), nullable=True), schema=E)
        op.add_column(t, sa.Column("precio_membresia", sa.Numeric(12, 2), nullable=True), schema=E)
        op.create_check_constraint(f"ck_{t}_lista_margen", t, "lista_margen IN ('A','B','C','D','E','F')", schema=E)


def downgrade() -> None:
    for t in TABLAS:
        op.drop_constraint(f"ck_{t}_lista_margen", t, schema=E, type_="check")
        op.drop_column(t, "precio_membresia", schema=E)
        op.drop_column(t, "lista_margen", schema=E)
