"""Datos → Clientes: tipos de cliente según cómo compran, y para qué tipo de cliente es cada oportunidad.

Pedido de Diego, 2026-11-09 («con los datos que tenemos podemos crear una sección de clientes para tener los perfiles de
clientes?»; aprobó el plan). Solo se guardan los perfiles de cada tipo: ningún dato de personas.

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-09
"""
import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cliente_corrida",
        sa.Column("corrida_id", sa.Integer, primary_key=True),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("paso", sa.Unicode(300)),
        sa.Column("archivo", sa.Unicode(260)),
        sa.Column("renglones", sa.Integer),
        sa.Column("clientes", sa.Integer),
        sa.Column("tipos", sa.Integer),
        sa.Column("calidad", sa.Float),
        sa.Column("resumen", sa.UnicodeText),
        sa.Column("perfiles", sa.UnicodeText),
        sa.Column("nota_ia", sa.Unicode(500)),
        sa.Column("error", sa.Unicode(1000)),
        sa.Column("iniciada_por", sa.Integer, sa.ForeignKey("nucleo.usuario.usuario_id")),
        sa.Column("iniciada_en", sa.DateTime, nullable=False),
        sa.Column("terminada_en", sa.DateTime),
        sa.CheckConstraint("estado IN ('en_curso','completa','fallida')", name="ck_cliente_corrida_estado"),
        schema="datos",
    )
    op.add_column("oportunidad", sa.Column("tipo_cliente", sa.Unicode(120)), schema="compras")


def downgrade() -> None:
    op.drop_column("oportunidad", "tipo_cliente", schema="compras")
    op.drop_table("cliente_corrida", schema="datos")
