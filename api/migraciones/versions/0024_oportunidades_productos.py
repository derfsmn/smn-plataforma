"""Radar de productos, fase 2: «Buscar oportunidades» (pedido de Diego, 2026-10-27: «un botón donde le piquemos y junte
toda la información de lo que tenemos y nos recomiende productos que no tenemos»).

Una corrida junta tendencias, huecos del surtido, descontinuados que vendían, lo que Compras ya decidió y, si se pide,
lo que vende la competencia en Google Shopping; la IA propone productos con su evidencia. Cada recomendación se puede
mandar al semáforo como idea. La búsqueda en Google Shopping queda como corrida «oportunidad» del radar de precios.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

USUARIO = "nucleo.usuario.usuario_id"


def _origenes(extra: tuple[str, ...]) -> str:
    return "origen IN (" + ",".join(f"'{o}'" for o in ("programado", "tardio", "manual", "prueba", *extra)) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_precio_corrida_origen", "precio_corrida", schema="compras")
    op.create_check_constraint("ck_precio_corrida_origen", "precio_corrida", _origenes(("producto", "oportunidad")),
                               schema="compras")
    op.create_table(
        "oportunidad_corrida",
        sa.Column("corrida_id", sa.Integer, primary_key=True),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("paso", sa.Unicode(300)),
        sa.Column("competencia", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("fuentes", sa.UnicodeText),
        sa.Column("notas", sa.UnicodeText),
        sa.Column("con_ia", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("costo_usd", sa.Numeric(10, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Unicode(1000)),
        sa.Column("disparada_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("creada_en", sa.DateTime, nullable=False),
        sa.Column("terminada_en", sa.DateTime),
        sa.CheckConstraint("estado IN ('en_curso','lista','fallida')", name="ck_oportunidad_corrida_estado"),
        schema="compras",
    )
    op.create_table(
        "oportunidad",
        sa.Column("oportunidad_id", sa.Integer, primary_key=True),
        sa.Column("corrida_id", sa.Integer, sa.ForeignKey("compras.oportunidad_corrida.corrida_id"), nullable=False),
        sa.Column("orden", sa.Integer, nullable=False),
        sa.Column("nombre", sa.Unicode(300), nullable=False),
        sa.Column("marca", sa.Unicode(120)),
        sa.Column("departamento", sa.Unicode(300)),
        sa.Column("subcategoria", sa.Unicode(300)),
        sa.Column("forma", sa.Unicode(60)),
        sa.Column("por_que", sa.Unicode(1000), nullable=False),
        sa.Column("prioridad", sa.Unicode(10), nullable=False),
        sa.Column("evidencia", sa.UnicodeText, nullable=False),
        sa.Column("precio_visto", sa.Numeric(12, 2)),
        sa.Column("donde_se_vio", sa.Unicode(300)),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("idea_id", sa.Integer, sa.ForeignKey("compras.producto_idea.idea_id")),
        sa.Column("actualizada_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("actualizada_en", sa.DateTime),
        sa.CheckConstraint("estado IN ('nueva','evaluada','descartada')", name="ck_oportunidad_estado"),
        sa.CheckConstraint("prioridad IN ('alta','media','baja')", name="ck_oportunidad_prioridad"),
        schema="compras",
    )
    op.create_index("ix_oportunidad_corrida", "oportunidad", ["corrida_id"], schema="compras")


def downgrade() -> None:
    op.drop_index("ix_oportunidad_corrida", "oportunidad", schema="compras")
    op.drop_table("oportunidad", schema="compras")
    op.drop_table("oportunidad_corrida", schema="compras")
    op.execute("UPDATE compras.precio_corrida SET origen = 'prueba' WHERE origen = 'oportunidad'")
    op.drop_constraint("ck_precio_corrida_origen", "precio_corrida", schema="compras")
    op.create_check_constraint("ck_precio_corrida_origen", "precio_corrida", _origenes(("producto",)), schema="compras")
