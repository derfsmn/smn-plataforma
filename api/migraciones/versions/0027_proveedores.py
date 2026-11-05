"""Datos → Proveedores: calificación de cada proveedor con lo que ya está cargado de SMNBI (compras, costos, venta,
inventario) y los pesos que Compras pone a cada bloque.

Pedido de Diego, 2026-10-28: «un módulo de proveedores donde esté en datos» y cómo evaluarlos con los datos que
tenemos (eligió ficha y calificación).

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

USUARIO = "nucleo.usuario.usuario_id"


def upgrade() -> None:
    op.create_table(
        "proveedor_evaluacion",
        sa.Column("evaluacion_id", sa.Integer, primary_key=True),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("iniciada_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("iniciada_en", sa.DateTime, nullable=False),
        sa.Column("terminada_en", sa.DateTime),
        sa.Column("proveedores", sa.Integer),
        sa.Column("calificados", sa.Integer),
        sa.Column("contexto", sa.UnicodeText),
        sa.Column("error", sa.Unicode(1000)),
        sa.CheckConstraint("estado IN ('en_curso','completa','fallida')", name="ck_proveedor_evaluacion_estado"),
        schema="datos",
    )
    op.create_table(
        "proveedor_calificacion",
        sa.Column("evaluacion_id", sa.Integer, sa.ForeignKey("datos.proveedor_evaluacion.evaluacion_id"),
                  primary_key=True),
        sa.Column("proveedor", sa.Unicode(10), primary_key=True),
        sa.Column("nombre", sa.Unicode(100)),
        sa.Column("puntaje", sa.Integer),
        sa.Column("color", sa.Unicode(10)),
        sa.Column("confianza", sa.Unicode(10), nullable=False),
        sa.Column("cumplimiento", sa.Integer),
        sa.Column("comercial", sa.Integer),
        sa.Column("costo", sa.Integer),
        sa.Column("inventario", sa.Integer),
        sa.Column("skus_activos", sa.Integer, nullable=False),
        sa.Column("venta", sa.Numeric(18, 2)),
        sa.Column("compra", sa.Numeric(18, 2)),
        sa.Column("metricas", sa.UnicodeText),
        schema="datos",
    )
    op.create_table(
        "conocimiento_peso_proveedor",
        sa.Column("bloque", sa.Unicode(30), primary_key=True),
        sa.Column("puntos", sa.Integer, nullable=False),
        sa.Column("nota", sa.Unicode(600)),
        sa.Column("actualizado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("actualizado_en", sa.DateTime, nullable=False),
        schema="compras",
    )


def downgrade() -> None:
    op.drop_table("conocimiento_peso_proveedor", schema="compras")
    op.drop_table("proveedor_calificacion", schema="datos")
    op.drop_table("proveedor_evaluacion", schema="datos")
