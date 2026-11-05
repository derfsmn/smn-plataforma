"""Radar de precios: búsqueda directa en el sitio de Walmart, Chedraui, San Pablo y Soriana (Diego, 2026-10-20).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "precio_tienda_coincidencia",
        sa.Column("tienda_coincidencia_id", sa.Integer, primary_key=True),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("datos.producto.producto_id"), nullable=False),
        sa.Column("tienda", sa.Unicode(40), nullable=False),
        sa.Column("clave", sa.Unicode(120), nullable=False),
        sa.Column("titulo", sa.Unicode(400)),
        sa.Column("liga", sa.Unicode(800)),
        sa.Column("imagen", sa.Unicode(800)),
        sa.Column("ean", sa.Unicode(20)),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("motivo", sa.Unicode(600)),
        sa.Column("decidido_por", sa.Integer, sa.ForeignKey("nucleo.usuario.usuario_id")),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        sa.Column("verificado_en", sa.DateTime),
        schema="compras",
    )
    op.create_index("ix_precio_tienda_coincidencia", "precio_tienda_coincidencia", ["producto_id", "tienda", "estado"], schema="compras")
    op.alter_column("precio_observacion", "coincidencia_id", existing_type=sa.Integer, nullable=True, schema="compras")
    op.add_column("precio_observacion", sa.Column(
        "tienda_coincidencia_id", sa.Integer,
        sa.ForeignKey("compras.precio_tienda_coincidencia.tienda_coincidencia_id", name="fk_precio_observacion_tienda")),
                  schema="compras")
    op.add_column("precio_corrida_producto", sa.Column("tiendas", sa.UnicodeText), schema="compras")


def downgrade() -> None:
    op.drop_column("precio_corrida_producto", "tiendas", schema="compras")
    op.execute("DELETE FROM compras.precio_observacion WHERE coincidencia_id IS NULL")
    op.drop_constraint("fk_precio_observacion_tienda", "precio_observacion", schema="compras", type_="foreignkey")
    op.drop_column("precio_observacion", "tienda_coincidencia_id", schema="compras")
    op.alter_column("precio_observacion", "coincidencia_id", existing_type=sa.Integer, nullable=False, schema="compras")
    op.drop_index("ix_precio_tienda_coincidencia", "precio_tienda_coincidencia", schema="compras")
    op.drop_table("precio_tienda_coincidencia", schema="compras")
