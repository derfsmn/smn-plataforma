"""Búsqueda de proveedor: las oportunidades e ideas que salen bien en el semáforo y no tienen quién las surta les llegan a
las personas que buscan proveedores; ahí se registra a quién se contactó y cómo terminó. Pedido de Diego, 2026-11-09.

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-09
"""
import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

USUARIO = "nucleo.usuario.usuario_id"


def upgrade() -> None:
    op.create_table(
        "busqueda_proveedor",
        sa.Column("busqueda_id", sa.Integer, primary_key=True),
        sa.Column("idea_id", sa.Integer, sa.ForeignKey("compras.producto_idea.idea_id"), nullable=False),
        sa.Column("evaluacion_id", sa.Integer, sa.ForeignKey("compras.producto_evaluacion.evaluacion_id")),
        sa.Column("origen", sa.Unicode(12), nullable=False),
        sa.Column("estado", sa.Unicode(15), nullable=False),
        sa.Column("color", sa.Unicode(10)),
        sa.Column("puntaje", sa.Integer),
        sa.Column("nota", sa.Unicode(1000)),
        sa.Column("responsable_id", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("tomada_en", sa.DateTime),
        sa.Column("proveedor_intelisis", sa.Unicode(10)),
        sa.Column("proveedor_nuevo", sa.Unicode(200)),
        sa.Column("costo", sa.Numeric(12, 2)),
        sa.Column("motivo_cierre", sa.Unicode(1000)),
        sa.Column("cerrada_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("cerrada_en", sa.DateTime),
        sa.Column("creada_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("creada_en", sa.DateTime, nullable=False),
        sa.CheckConstraint("origen IN ('automatica','compras')", name="ck_busqueda_proveedor_origen"),
        sa.CheckConstraint("estado IN ('sin_tomar','buscando','encontrado','sin_proveedor','cancelada')",
                           name="ck_busqueda_proveedor_estado"),
        schema="compras",
    )
    op.create_index("ix_busqueda_proveedor_idea", "busqueda_proveedor", ["idea_id"], schema="compras")
    op.create_index("ix_busqueda_proveedor_estado", "busqueda_proveedor", ["estado"], schema="compras")
    op.create_table(
        "busqueda_avance",
        sa.Column("avance_id", sa.Integer, primary_key=True),
        sa.Column("busqueda_id", sa.Integer, sa.ForeignKey("compras.busqueda_proveedor.busqueda_id"), nullable=False),
        sa.Column("tipo", sa.Unicode(12), nullable=False),
        sa.Column("texto", sa.Unicode(1000), nullable=False),
        sa.Column("proveedor", sa.Unicode(200)),
        sa.Column("resultado", sa.Unicode(15)),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        sa.CheckConstraint("tipo IN ('nota','contacto','estado')", name="ck_busqueda_avance_tipo"),
        sa.CheckConstraint("resultado IS NULL OR resultado IN ('sin_respuesta','interesado','cotizo','no_surte')",
                           name="ck_busqueda_avance_resultado"),
        schema="compras",
    )
    op.create_index("ix_busqueda_avance_busqueda", "busqueda_avance", ["busqueda_id"], schema="compras")


def downgrade() -> None:
    op.drop_index("ix_busqueda_avance_busqueda", "busqueda_avance", schema="compras")
    op.drop_table("busqueda_avance", schema="compras")
    op.drop_index("ix_busqueda_proveedor_estado", "busqueda_proveedor", schema="compras")
    op.drop_index("ix_busqueda_proveedor_idea", "busqueda_proveedor", schema="compras")
    op.drop_table("busqueda_proveedor", schema="compras")
