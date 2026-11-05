"""Propuestas de productos nuevos desde el portal de proveedores (plan aprobado por Diego, 2026-10-22).

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

USUARIO = "nucleo.usuario.usuario_id"
PROPUESTA = "compras.propuesta.propuesta_id"


def upgrade() -> None:
    op.create_table(
        "propuesta",
        sa.Column("propuesta_id", sa.Integer, primary_key=True),
        sa.Column("folio", sa.Unicode(20)),
        sa.Column("organizacion_id", sa.Integer, sa.ForeignKey("nucleo.organizacion_externa.organizacion_id"), nullable=False),
        sa.Column("creada_por", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("producto", sa.Unicode(300)),
        sa.Column("marca", sa.Unicode(120)),
        sa.Column("departamento", sa.Unicode(300)),
        sa.Column("presentaciones", sa.Integer, nullable=False),
        sa.Column("respuestas", sa.UnicodeText, nullable=False),
        sa.Column("revisiones", sa.UnicodeText),
        sa.Column("alertas", sa.Integer, nullable=False),
        sa.Column("comentario", sa.Unicode(1000)),
        sa.Column("enviada_en", sa.DateTime),
        sa.Column("creada_en", sa.DateTime, nullable=False),
        sa.Column("actualizada_en", sa.DateTime, nullable=False),
        schema="compras",
    )
    # Único solo entre los que ya tienen folio (los borradores no tienen)
    op.create_index("ux_propuesta_folio", "propuesta", ["folio"], unique=True, schema="compras",
                    mssql_where=sa.text("folio IS NOT NULL"))
    op.create_index("ix_propuesta_organizacion", "propuesta", ["organizacion_id", "estado"], schema="compras")
    op.create_index("ix_propuesta_estado", "propuesta", ["estado", "enviada_en"], schema="compras")
    op.create_table(
        "propuesta_presentacion",
        sa.Column("presentacion_id", sa.Integer, primary_key=True),
        sa.Column("propuesta_id", sa.Integer, sa.ForeignKey(PROPUESTA), nullable=False),
        sa.Column("orden", sa.Integer, nullable=False),
        sa.Column("codigo_barras", sa.Unicode(14)),
        sa.Column("descripcion", sa.Unicode(180)),
        sa.Column("forma", sa.Unicode(60)),
        sa.Column("contenido_neto", sa.Numeric(12, 3)),
        sa.Column("unidad_medida", sa.Unicode(20)),
        sa.Column("costo_sin_iva", sa.Numeric(12, 2)),
        sa.Column("pvp_sugerido", sa.Numeric(12, 2)),
        sa.Column("tasa_iva", sa.Numeric(5, 2)),
        sa.Column("tasa_ieps", sa.Numeric(5, 2)),
        sa.Column("margen_calculado", sa.Numeric(7, 2)),
        sa.Column("ya_en_catalogo", sa.Boolean, nullable=False),
        sa.UniqueConstraint("propuesta_id", "orden", name="uq_propuesta_presentacion_orden"),
        schema="compras",
    )
    op.create_index("ix_propuesta_presentacion_codigo", "propuesta_presentacion", ["codigo_barras"], schema="compras")
    op.create_table(
        "propuesta_adjunto",
        sa.Column("adjunto_id", sa.Integer, primary_key=True),
        sa.Column("propuesta_id", sa.Integer, sa.ForeignKey(PROPUESTA), nullable=False),
        sa.Column("archivo_id", sa.BigInteger, sa.ForeignKey("nucleo.archivo.archivo_id"), nullable=False),
        sa.Column("tipo", sa.Unicode(40), nullable=False),
        sa.Column("etiqueta", sa.Unicode(40)),
        sa.Column("agregado_en", sa.DateTime, nullable=False),
        schema="compras",
    )
    op.create_index("ix_propuesta_adjunto", "propuesta_adjunto", ["propuesta_id"], schema="compras")
    op.create_table(
        "propuesta_evento",
        sa.Column("evento_id", sa.Integer, primary_key=True),
        sa.Column("propuesta_id", sa.Integer, sa.ForeignKey(PROPUESTA), nullable=False),
        sa.Column("estado_antes", sa.Unicode(20)),
        sa.Column("estado_despues", sa.Unicode(20), nullable=False),
        sa.Column("comentario", sa.Unicode(1000)),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("ocurrido_en", sa.DateTime, nullable=False),
        schema="compras",
    )
    op.create_index("ix_propuesta_evento", "propuesta_evento", ["propuesta_id"], schema="compras")


def downgrade() -> None:
    op.drop_index("ix_propuesta_evento", table_name="propuesta_evento", schema="compras")
    op.drop_table("propuesta_evento", schema="compras")
    op.drop_index("ix_propuesta_adjunto", table_name="propuesta_adjunto", schema="compras")
    op.drop_table("propuesta_adjunto", schema="compras")
    op.drop_index("ix_propuesta_presentacion_codigo", table_name="propuesta_presentacion", schema="compras")
    op.drop_table("propuesta_presentacion", schema="compras")
    op.drop_index("ix_propuesta_estado", table_name="propuesta", schema="compras")
    op.drop_index("ix_propuesta_organizacion", table_name="propuesta", schema="compras")
    op.drop_index("ux_propuesta_folio", table_name="propuesta", schema="compras")
    op.drop_table("propuesta", schema="compras")
