"""Datos → Grupos de tiendas: tiendas que venden parecido, calculadas con la venta por departamento.

Pedido de Diego, 2026-10-29: eligió «Grupos de tiendas» para meterle IA al mapa, y «quiero que sea local la IA»:
el agrupamiento corre en Python y el texto de cada grupo lo redacta Ollama, sin API externa.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-29
"""
import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tienda_grupo_corrida",
        sa.Column("corrida_id", sa.Integer, primary_key=True),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("iniciada_por", sa.Integer, sa.ForeignKey("nucleo.usuario.usuario_id")),
        sa.Column("iniciada_en", sa.DateTime, nullable=False),
        sa.Column("terminada_en", sa.DateTime),
        sa.Column("tiendas", sa.Integer),
        sa.Column("grupos", sa.Integer),
        sa.Column("calidad", sa.Float),
        sa.Column("contexto", sa.UnicodeText),
        sa.Column("perfiles", sa.UnicodeText),
        sa.Column("nota_ia", sa.Unicode(500)),
        sa.Column("error", sa.Unicode(1000)),
        sa.CheckConstraint("estado IN ('en_curso','completa','fallida')", name="ck_tienda_grupo_corrida_estado"),
        schema="datos",
    )
    op.create_table(
        "tienda_grupo",
        sa.Column("corrida_id", sa.Integer, sa.ForeignKey("datos.tienda_grupo_corrida.corrida_id"), primary_key=True),
        sa.Column("almacen", sa.Unicode(10), primary_key=True),
        sa.Column("grupo", sa.Integer, nullable=False),
        sa.Column("tipicidad", sa.Integer),
        sa.Column("rasgos", sa.UnicodeText),
        schema="datos",
    )


def downgrade() -> None:
    op.drop_table("tienda_grupo", schema="datos")
    op.drop_table("tienda_grupo_corrida", schema="datos")
