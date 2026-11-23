"""compras.producto_evaluacion guarda la pantalla por niveles ya armada (22 nov 2026).

La pantalla del comité y del radar se arma una vez al terminar la evaluación y se lee de aquí.
`pantalla_venta` dice con qué semanas de venta se armó; si cambia, se vuelve a armar.

Revision ID: 0053
Revises: 0052
"""
import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("producto_evaluacion", sa.Column("pantalla", sa.UnicodeText), schema="compras")
    op.add_column("producto_evaluacion", sa.Column("pantalla_venta", sa.Unicode(100)), schema="compras")


def downgrade() -> None:
    op.drop_column("producto_evaluacion", "pantalla_venta", schema="compras")
    op.drop_column("producto_evaluacion", "pantalla", schema="compras")
