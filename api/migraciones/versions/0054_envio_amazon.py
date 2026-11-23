"""compras.precio_envio acepta «amazon»: la señal de venta en Amazon México por DataForSEO (22 nov 2026).

Se construyó sin este cambio y la evaluación tronaba con «ck_precio_envio_tipo» al buscar en Amazon (Diego, 22 nov).

Revision ID: 0054
Revises: 0053
"""
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

E = "compras"
ENVIO = ("productos", "vendedores", "organico", "noticias")


def _en(columna: str, valores) -> str:
    return f"{columna} IN (" + ",".join(f"'{v}'" for v in valores) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_precio_envio_tipo", "precio_envio", schema=E, type_="check")
    op.create_check_constraint("ck_precio_envio_tipo", "precio_envio", _en("tipo", ENVIO + ("amazon",)), schema=E)


def downgrade() -> None:
    op.execute("UPDATE compras.precio_envio SET tipo = 'organico' WHERE tipo = 'amazon'")
    op.drop_constraint("ck_precio_envio_tipo", "precio_envio", schema=E, type_="check")
    op.create_check_constraint("ck_precio_envio_tipo", "precio_envio", _en("tipo", ENVIO), schema=E)
