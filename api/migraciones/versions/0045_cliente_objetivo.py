"""«Nuestro cliente»: el nivel socioeconómico al que le vendemos y si cada oportunidad encaja con él.

Pedido de Diego, 2026-11-10 («nuestro sector de clientes lo denominan C-, entonces podríamos definir cuál es el tipo de
cliente que tenemos para que con base en ello el radar de oportunidades también valide eso»; aprobó el plan).

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tabla = op.create_table(
        "cliente_objetivo",
        sa.Column("objetivo_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("nivel", sa.Unicode(10), nullable=False),
        sa.Column("descripcion", sa.UnicodeText),
        sa.Column("actualizado_por", sa.Integer, sa.ForeignKey("nucleo.usuario.usuario_id")),
        sa.Column("actualizado_en", sa.DateTime),
        sa.CheckConstraint("objetivo_id = 1", name="ck_cliente_objetivo_unico"),
        schema="datos",
    )
    op.bulk_insert(tabla, [{"objetivo_id": 1, "nivel": "C-"}])  # el nivel que dijo Diego; la descripción la escriben ellos
    op.add_column("oportunidad", sa.Column("encaje", sa.Unicode(10)), schema="compras")
    op.add_column("oportunidad", sa.Column("encaje_motivo", sa.Unicode(400)), schema="compras")


def downgrade() -> None:
    op.drop_column("oportunidad", "encaje_motivo", schema="compras")
    op.drop_column("oportunidad", "encaje", schema="compras")
    op.drop_table("cliente_objetivo", schema="datos")
