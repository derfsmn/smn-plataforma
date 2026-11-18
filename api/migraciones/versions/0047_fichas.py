"""Ficha técnica estándar: datos.producto_ficha (catálogo, por SKU) y datos.idea_ficha (ideas y propuestas).

La llenan las reglas y la IA local con el origen y la cita de cada campo; Compras solo puede marcarla «Está mal»
con motivo. Plan «radar de productos inteligente con IA local», aprobado por Diego el 2026-11-17 («Pues dale,
comencemos»). La comparten el radar de productos y el radar de precios (precio por unidad).

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def _campos() -> list[sa.Column]:
    return [
        sa.Column("tipo", sa.Unicode(120)),
        sa.Column("forma", sa.Unicode(40)),
        sa.Column("contenido_cantidad", sa.Numeric(12, 3)),
        sa.Column("contenido_unidad", sa.Unicode(4)),
        sa.Column("piezas", sa.Integer),
        sa.Column("porciones", sa.Integer),
        sa.Column("ingrediente_principal", sa.Unicode(200)),
        sa.Column("activo_g_porcion", sa.Numeric(10, 4)),
        sa.Column("otros_ingredientes", sa.Unicode(500)),
        sa.Column("sabor", sa.Unicode(80)),
        sa.Column("variante", sa.Unicode(80)),
        sa.Column("uso", sa.Unicode(300)),
        sa.Column("registro_sanitario", sa.Unicode(60)),
        sa.Column("iva_pct", sa.Numeric(5, 2)),
        sa.Column("origenes", sa.UnicodeText),
        sa.Column("citas", sa.UnicodeText),
        sa.Column("huella", sa.String(64)),
        sa.Column("estado", sa.Unicode(10), nullable=False, server_default="lista"),
        sa.Column("nota", sa.Unicode(500)),
        sa.Column("intentos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("con_ia", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("mal_motivo", sa.Unicode(500)),
        sa.Column("mal_por", sa.Integer),
        sa.Column("mal_en", sa.DateTime),
        sa.Column("extraida_en", sa.DateTime, nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "producto_ficha",
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("datos.producto.producto_id", name="fk_producto_ficha_producto"),
                  primary_key=True),
        *_campos(), schema="datos")
    op.create_index("ix_producto_ficha_estado", "producto_ficha", ["estado"], schema="datos")
    op.create_table(
        "idea_ficha",
        sa.Column("ficha_id", sa.Integer, primary_key=True),
        sa.Column("origen", sa.Unicode(10), nullable=False),
        sa.Column("origen_id", sa.Integer, nullable=False),
        *_campos(),
        sa.UniqueConstraint("origen", "origen_id", name="uq_idea_ficha_origen"), schema="datos")


def downgrade() -> None:
    op.drop_table("idea_ficha", schema="datos")
    op.drop_index("ix_producto_ficha_estado", "producto_ficha", schema="datos")
    op.drop_table("producto_ficha", schema="datos")
