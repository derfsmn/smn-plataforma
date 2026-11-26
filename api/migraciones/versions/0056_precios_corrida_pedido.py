"""Corridas a pedido del radar de precios (Diego, 26 nov 2026: «una pantalla donde tengamos listado de corridas»).

- compras.precio_corrida acepta el origen «pedido»: la lanza quien usa el radar, subiendo un Excel de SKU o eligiendo
  marca, clasificación y categoría.
- y el estado «en_espera»: si otra corrida está corriendo (p. ej. un lote de la noche), la corrida a pedido se forma y
  arranca sola en cuanto quede libre.

Revision ID: 0056
Revises: 0055
Create Date: 2026-11-26
"""
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

E = "compras"
ORIGENES = ("programado", "tardio", "manual", "prueba", "producto", "oportunidad", "nocturna", "web")
ESTADOS = ("en_curso", "completa", "parcial", "fallida")


def _en(columna: str, valores) -> str:
    return f"{columna} IN (" + ",".join(f"'{v}'" for v in valores) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_precio_corrida_origen", "precio_corrida", schema=E, type_="check")
    op.create_check_constraint("ck_precio_corrida_origen", "precio_corrida", _en("origen", ORIGENES + ("pedido",)), schema=E)
    op.drop_constraint("ck_precio_corrida_estado", "precio_corrida", schema=E, type_="check")
    op.create_check_constraint("ck_precio_corrida_estado", "precio_corrida", _en("estado", ESTADOS + ("en_espera",)), schema=E)


def downgrade() -> None:
    op.execute("UPDATE compras.precio_corrida SET estado = 'fallida', error = 'No arrancó' WHERE estado = 'en_espera'")
    op.execute("UPDATE compras.precio_corrida SET origen = 'manual' WHERE origen = 'pedido'")
    op.drop_constraint("ck_precio_corrida_estado", "precio_corrida", schema=E, type_="check")
    op.create_check_constraint("ck_precio_corrida_estado", "precio_corrida", _en("estado", ESTADOS), schema=E)
    op.drop_constraint("ck_precio_corrida_origen", "precio_corrida", schema=E, type_="check")
    op.create_check_constraint("ck_precio_corrida_origen", "precio_corrida", _en("origen", ORIGENES), schema=E)
