"""Radar de precios: cada «Correr ahora» es su propia corrida, con su hora; ya no se reescribe la del mismo día.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-20
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # La restricción única de 0010 no tiene nombre fijo en SQL Server: se busca por la columna
    op.execute("""
DECLARE @n sysname, @s nvarchar(400);
SELECT @n = kc.name FROM sys.key_constraints kc
  JOIN sys.index_columns ic ON ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id
  JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
 WHERE kc.type = 'UQ' AND kc.parent_object_id = OBJECT_ID('compras.precio_corrida') AND c.name = 'fecha';
IF @n IS NOT NULL
BEGIN
  SET @s = N'ALTER TABLE compras.precio_corrida DROP CONSTRAINT ' + QUOTENAME(@n);
  EXEC sp_executesql @s;
END
""")
    op.create_index("ix_precio_corrida_fecha", "precio_corrida", ["fecha"], schema="compras")


def downgrade() -> None:
    op.drop_index("ix_precio_corrida_fecha", "precio_corrida", schema="compras")
    op.create_unique_constraint("uq_precio_corrida_fecha", "precio_corrida", ["fecha"], schema="compras")
