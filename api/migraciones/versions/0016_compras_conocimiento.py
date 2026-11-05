"""Base de conocimiento de Compras: políticas, reglas, pesos y casos pasados (Diego, 2026-10-21).

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-21
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

USUARIO = "nucleo.usuario.usuario_id"


def upgrade() -> None:
    op.create_table(
        "conocimiento_politica",
        sa.Column("politica_id", sa.Integer, primary_key=True),
        sa.Column("tema", sa.Unicode(30), nullable=False),
        sa.Column("titulo", sa.Unicode(200), nullable=False),
        sa.Column("contenido", sa.UnicodeText, nullable=False),
        sa.Column("departamento", sa.Unicode(300)),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("creado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        sa.Column("actualizado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("actualizado_en", sa.DateTime, nullable=False),
        schema="compras",
    )
    op.create_table(
        "conocimiento_regla",
        sa.Column("regla_id", sa.Integer, primary_key=True),
        sa.Column("tipo", sa.Unicode(20), nullable=False),
        sa.Column("criterio", sa.Unicode(200), nullable=False),
        sa.Column("departamento", sa.Unicode(300)),
        sa.Column("minimo", sa.Numeric(14, 4)),
        sa.Column("maximo", sa.Numeric(14, 4)),
        sa.Column("unidad", sa.Unicode(40)),
        sa.Column("periodo_meses", sa.Integer),
        sa.Column("descripcion", sa.Unicode(1000)),
        sa.Column("activa", sa.Boolean, nullable=False),
        sa.Column("actualizado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("actualizado_en", sa.DateTime, nullable=False),
        schema="compras",
    )
    op.create_index("ix_conocimiento_regla_tipo", "conocimiento_regla", ["tipo"], schema="compras")
    op.create_table(
        "conocimiento_peso",
        sa.Column("factor", sa.Unicode(30), primary_key=True),
        sa.Column("puntos", sa.Integer, nullable=False),
        sa.Column("nota", sa.Unicode(600)),
        sa.Column("actualizado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("actualizado_en", sa.DateTime, nullable=False),
        schema="compras",
    )
    op.create_table(
        "conocimiento_caso",
        sa.Column("caso_id", sa.Integer, primary_key=True),
        sa.Column("producto", sa.Unicode(300), nullable=False),
        sa.Column("sku", sa.Unicode(60)),
        sa.Column("proveedor", sa.Unicode(200)),
        sa.Column("departamento", sa.Unicode(300)),
        sa.Column("fecha_decision", sa.Date),
        sa.Column("decision", sa.Unicode(20), nullable=False),
        sa.Column("motivo", sa.Unicode(1000)),
        sa.Column("resultado", sa.Unicode(20), nullable=False),
        sa.Column("notas", sa.Unicode(1000)),
        sa.Column("creado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        sa.Column("actualizado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("actualizado_en", sa.DateTime, nullable=False),
        schema="compras",
    )


def downgrade() -> None:
    op.drop_table("conocimiento_caso", schema="compras")
    op.drop_table("conocimiento_peso", schema="compras")
    op.drop_index("ix_conocimiento_regla_tipo", table_name="conocimiento_regla", schema="compras")
    op.drop_table("conocimiento_regla", schema="compras")
    op.drop_table("conocimiento_politica", schema="compras")
