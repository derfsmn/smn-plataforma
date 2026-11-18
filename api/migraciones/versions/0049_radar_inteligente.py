"""Radar de productos inteligente con IA local: investigación afuera, pronóstico por grupo de tiendas, memoria del
comité con motivo por indicador, «Aceptado a prueba» en pocas tiendas y seguimiento a 4, 8 y 12 semanas.

Plan aprobado por Diego el 2026-11-17 («Pues dale, comencemos»). La 0048 es del radar de precios (otro hilo).

Revision ID: 0049
Revises: 0048
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0047"  # TODO al integrar: "0048" (radar de precios)
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Huella de significado (bge-m3) de lo que hace cada producto, para encontrar sustitutos por función
    op.create_table(
        "producto_huella",
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("datos.producto.producto_id", name="fk_producto_huella_producto"),
                  primary_key=True),
        sa.Column("modelo", sa.Unicode(80), nullable=False),
        sa.Column("vector", sa.LargeBinary, nullable=False),  # float32 normalizado
        sa.Column("huella_texto", sa.String(64), nullable=False),  # SHA-256 del texto con que se calculó
        sa.Column("calculada_en", sa.DateTime, nullable=False),
        schema="datos")
    op.add_column("producto_evaluacion", sa.Column("investigacion", sa.UnicodeText), schema="compras")
    op.add_column("producto_evaluacion", sa.Column("pronostico", sa.UnicodeText), schema="compras")
    for col in (sa.Column("indicadores", sa.UnicodeText),  # JSON [{factor, sentido, motivo}]
                sa.Column("radar_error_factor", sa.Unicode(20)),
                sa.Column("radar_error_motivo", sa.Unicode(500)),
                sa.Column("prueba_tiendas", sa.UnicodeText),  # JSON [clave de tienda]
                sa.Column("prueba_precio", sa.Numeric(12, 2)),
                sa.Column("prueba_revision", sa.Date),
                sa.Column("prueba_condicion", sa.Unicode(500)),
                sa.Column("sku", sa.Unicode(80))):
        op.add_column("comite_producto", col, schema="compras")
    # «Aceptado a prueba» en pocas tiendas
    op.drop_constraint("ck_comite_producto_decision", "comite_producto", schema="compras", type_="check")
    op.create_check_constraint("ck_comite_producto_decision", "comite_producto",
                               "decision IS NULL OR decision IN ('aceptado','a_prueba','denegado','en_espera')",
                               schema="compras")
    op.create_table(
        "producto_seguimiento",
        sa.Column("seguimiento_id", sa.Integer, primary_key=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("compras.comite_producto.item_id",
                                                       name="fk_producto_seguimiento_item"), nullable=False),
        sa.Column("semana", sa.Integer, nullable=False),  # 4 / 8 / 12
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("pronostico_bajo", sa.Numeric(12, 2)),
        sa.Column("pronostico_medio", sa.Numeric(12, 2)),
        sa.Column("pronostico_alto", sa.Numeric(12, 2)),
        sa.Column("real", sa.Numeric(12, 2)),
        sa.Column("tiendas", sa.Integer),
        sa.Column("resultado", sa.Unicode(12), nullable=False),  # arriba / en_linea / abajo / sin_venta / sin_sku
        sa.Column("propuesta", sa.Unicode(12)),  # ampliar / mantener / retirar
        sa.Column("texto", sa.Unicode(1000)),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        sa.UniqueConstraint("item_id", "semana", name="uq_producto_seguimiento"),
        schema="compras")


def downgrade() -> None:
    op.drop_table("producto_seguimiento", schema="compras")
    op.execute("UPDATE compras.comite_producto SET decision = 'aceptado' WHERE decision = 'a_prueba'")
    op.drop_constraint("ck_comite_producto_decision", "comite_producto", schema="compras", type_="check")
    op.create_check_constraint("ck_comite_producto_decision", "comite_producto",
                               "decision IS NULL OR decision IN ('aceptado','denegado','en_espera')", schema="compras")
    for c in ("sku", "prueba_condicion", "prueba_revision", "prueba_precio", "prueba_tiendas", "radar_error_motivo",
              "radar_error_factor", "indicadores"):
        op.drop_column("comite_producto", c, schema="compras")
    op.drop_column("producto_evaluacion", "pronostico", schema="compras")
    op.drop_column("producto_evaluacion", "investigacion", schema="compras")
    op.drop_table("producto_huella", schema="datos")
