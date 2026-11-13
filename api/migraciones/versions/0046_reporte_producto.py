"""Reporte PDF por producto validado: nuestro precio aparte del visto, código de barras y activo por porción en la
idea, y el reporte que se guarda cuando el comité acepta el producto.

Pedido de Diego, 2026-11-13 («este reporte ayudaría mucho a entregarlo para cada producto validado»; aprobó el plan:
«a ver dale, empecemos»).

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("producto_idea", sa.Column("precio_nuestro", sa.Numeric(12, 2)), schema="compras")
    op.add_column("producto_idea", sa.Column("codigo_barras", sa.Unicode(20)), schema="compras")
    op.add_column("producto_idea", sa.Column("activo_g_porcion", sa.Numeric(10, 3)), schema="compras")
    op.add_column("producto_idea", sa.Column("porciones", sa.Integer), schema="compras")
    op.add_column("comite_producto", sa.Column("reporte_archivo_id", sa.BigInteger,
                                               sa.ForeignKey("nucleo.archivo.archivo_id",
                                                             name="fk_comite_producto_reporte")), schema="compras")


def downgrade() -> None:
    op.drop_constraint("fk_comite_producto_reporte", "comite_producto", schema="compras", type_="foreignkey")
    op.drop_column("comite_producto", "reporte_archivo_id", schema="compras")
    for c in ("porciones", "activo_g_porcion", "codigo_barras", "precio_nuestro"):
        op.drop_column("producto_idea", c, schema="compras")
