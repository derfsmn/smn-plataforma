"""Radar de productos, fase 1: ideas que captura Compras y evaluación con semáforo (plan aprobado por Diego, 2026-10-26).

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

USUARIO = "nucleo.usuario.usuario_id"
EVALUACION = "compras.producto_evaluacion.evaluacion_id"


def upgrade() -> None:
    op.create_table(
        "producto_idea",
        sa.Column("idea_id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.Unicode(300), nullable=False),
        sa.Column("marca", sa.Unicode(120)),
        sa.Column("descripcion", sa.Unicode(2000)),
        sa.Column("departamento", sa.Unicode(300)),
        sa.Column("ingrediente", sa.Unicode(200)),
        sa.Column("forma", sa.Unicode(60)),
        sa.Column("contenido", sa.Unicode(60)),
        sa.Column("precio_visto", sa.Numeric(12, 2)),
        sa.Column("donde_se_vio", sa.Unicode(300)),
        sa.Column("costo_estimado", sa.Numeric(12, 2)),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("creada_por", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("creada_en", sa.DateTime, nullable=False),
        sa.Column("actualizada_en", sa.DateTime, nullable=False),
        sa.CheckConstraint("estado IN ('nueva','buscar_proveedor','vigilar','descartada')", name="ck_producto_idea_estado"),
        schema="compras",
    )
    op.create_table(
        "producto_idea_foto",
        sa.Column("idea_id", sa.Integer, sa.ForeignKey("compras.producto_idea.idea_id"), primary_key=True),
        sa.Column("archivo_id", sa.BigInteger, sa.ForeignKey("nucleo.archivo.archivo_id"), primary_key=True),
        schema="compras",
    )
    op.create_table(
        "producto_evaluacion",
        sa.Column("evaluacion_id", sa.Integer, primary_key=True),
        sa.Column("propuesta_id", sa.Integer, sa.ForeignKey("compras.propuesta.propuesta_id")),
        sa.Column("idea_id", sa.Integer, sa.ForeignKey("compras.producto_idea.idea_id")),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("vigente", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("departamento", sa.Unicode(300)),
        sa.Column("rama", sa.Unicode(300)),
        sa.Column("subcategoria", sa.Unicode(300)),
        sa.Column("segmento", sa.Unicode(300)),
        sa.Column("clasificacion_origen", sa.Unicode(20)),
        sa.Column("puntaje", sa.Integer),
        sa.Column("color", sa.Unicode(10)),
        sa.Column("confianza", sa.Unicode(10)),
        sa.Column("pesos_origen", sa.Unicode(20)),
        sa.Column("explicacion", sa.UnicodeText),
        sa.Column("explicacion_ia", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("color_final", sa.Unicode(10)),
        sa.Column("motivo_cambio", sa.Unicode(1000)),
        sa.Column("cambiado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("cambiado_en", sa.DateTime),
        sa.Column("error", sa.Unicode(1000)),
        sa.Column("disparada_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("creada_en", sa.DateTime, nullable=False),
        sa.Column("terminada_en", sa.DateTime),
        # Se evalúa una propuesta de proveedor o una idea de Compras, nunca las dos
        sa.CheckConstraint("(propuesta_id IS NOT NULL AND idea_id IS NULL) OR (propuesta_id IS NULL AND idea_id IS NOT NULL)",
                           name="ck_producto_evaluacion_sujeto"),
        sa.CheckConstraint("estado IN ('en_curso','lista','fallida')", name="ck_producto_evaluacion_estado"),
        sa.CheckConstraint("color IS NULL OR color IN ('verde','amarillo','rojo')", name="ck_producto_evaluacion_color"),
        sa.CheckConstraint("color_final IS NULL OR color_final IN ('verde','amarillo','rojo')",
                           name="ck_producto_evaluacion_color_final"),
        schema="compras",
    )
    op.create_index("ix_producto_evaluacion_propuesta", "producto_evaluacion", ["propuesta_id"], schema="compras")
    op.create_index("ix_producto_evaluacion_idea", "producto_evaluacion", ["idea_id"], schema="compras")
    op.create_table(
        "producto_evaluacion_factor",
        sa.Column("evaluacion_id", sa.Integer, sa.ForeignKey(EVALUACION), primary_key=True),
        sa.Column("factor", sa.Unicode(20), primary_key=True),
        sa.Column("peso", sa.Numeric(6, 2), nullable=False),
        sa.Column("puntaje", sa.Integer),
        sa.Column("valor", sa.Unicode(300)),
        sa.Column("detalle", sa.Unicode(1000)),
        sa.Column("provisional", sa.Boolean, nullable=False, server_default=sa.text("0")),
        schema="compras",
    )
    op.create_table(
        "producto_evaluacion_comparable",
        sa.Column("evaluacion_id", sa.Integer, sa.ForeignKey(EVALUACION), primary_key=True),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("datos.producto.producto_id"), primary_key=True),
        sa.Column("rango", sa.Integer, nullable=False),
        sa.Column("similitud", sa.Numeric(5, 3), nullable=False),
        sa.Column("origen", sa.Unicode(10), nullable=False),
        schema="compras",
    )


def downgrade() -> None:
    op.drop_table("producto_evaluacion_comparable", schema="compras")
    op.drop_table("producto_evaluacion_factor", schema="compras")
    op.drop_table("producto_evaluacion", schema="compras")
    op.drop_table("producto_idea_foto", schema="compras")
    op.drop_table("producto_idea", schema="compras")
