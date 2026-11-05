"""ETL de ventas desde SMNBI: venta por producto, tienda y semana, cuadre y avance de cada carga (plan del 2026-10-23).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

CARGA = "datos.carga.carga_id"


def upgrade() -> None:
    # Avance de cada carga del ETL (las del catálogo los dejan vacíos)
    for columna in (
        sa.Column("desde", sa.Date),
        sa.Column("hasta", sa.Date),
        sa.Column("paso", sa.Unicode(20)),
        sa.Column("mes_actual", sa.Date),
        sa.Column("meses_total", sa.Integer),
        sa.Column("meses_hechos", sa.Integer),
        sa.Column("detener", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("archivo", sa.Unicode(260)),
    ):
        op.add_column("carga", columna, schema="datos")
    op.drop_constraint("ck_carga_fuente", "carga", schema="datos", type_="check")
    op.create_check_constraint("ck_carga_fuente", "carga", "fuente IN ('API','TIENDA','ETL','ETL_VENTAS')", schema="datos")
    op.drop_constraint("ck_carga_estado", "carga", schema="datos", type_="check")
    op.create_check_constraint("ck_carga_estado", "carga", "estado IN ('en_curso','completa','fallida','detenida')", schema="datos")

    op.create_table(
        "venta_semanal",
        sa.Column("sku", sa.Unicode(80), nullable=False),
        sa.Column("tienda", sa.Unicode(10), nullable=False),
        sa.Column("semana", sa.Date, nullable=False),
        sa.Column("mes", sa.Date, nullable=False),
        sa.Column("empresa", sa.Unicode(5), nullable=False),
        sa.Column("piezas", sa.Numeric(14, 3), nullable=False),
        sa.Column("piezas_devueltas", sa.Numeric(14, 3), nullable=False),
        sa.Column("importe_bruto", sa.Numeric(16, 2), nullable=False),
        sa.Column("descuento", sa.Numeric(16, 2), nullable=False),
        sa.Column("importe", sa.Numeric(16, 2), nullable=False),
        sa.Column("costo", sa.Numeric(16, 2)),
        sa.Column("tickets", sa.Integer, nullable=False),
        sa.Column("carga_id", sa.Integer, sa.ForeignKey(CARGA), nullable=False),
        sa.PrimaryKeyConstraint("mes", "sku", "tienda", "semana", "empresa", name="pk_venta_semanal"),
        schema="datos",
    )
    op.create_index("ix_venta_semanal_semana", "venta_semanal", ["semana"], schema="datos")
    op.create_index("ix_venta_semanal_sku", "venta_semanal", ["sku", "semana"], schema="datos")

    op.create_table(
        "venta_cuadre",
        sa.Column("cuadre_id", sa.Integer, primary_key=True),
        sa.Column("carga_id", sa.Integer, sa.ForeignKey(CARGA), nullable=False),
        sa.Column("mes", sa.Date, nullable=False),
        sa.Column("empresa", sa.Unicode(5), nullable=False),
        sa.Column("importe_origen", sa.Numeric(18, 2)),
        sa.Column("importe_cargado", sa.Numeric(18, 2), nullable=False),
        sa.Column("piezas_origen", sa.Numeric(18, 3)),
        sa.Column("piezas_cargadas", sa.Numeric(18, 3), nullable=False),
        sa.Column("renglones_fuera", sa.Integer),
        sa.Column("cuadra", sa.Boolean),
        schema="datos",
    )
    op.create_index("ix_venta_cuadre_carga", "venta_cuadre", ["carga_id"], schema="datos")

    op.create_table(
        "carga_paso",
        sa.Column("paso_id", sa.Integer, primary_key=True),
        sa.Column("carga_id", sa.Integer, sa.ForeignKey(CARGA), nullable=False),
        sa.Column("mes", sa.Date),
        sa.Column("paso", sa.Unicode(20), nullable=False),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("filas", sa.Integer),
        sa.Column("nota", sa.Unicode(500)),
        sa.Column("inicio_en", sa.DateTime, nullable=False),
        sa.Column("fin_en", sa.DateTime),
        schema="datos",
    )
    op.create_index("ix_carga_paso_carga", "carga_paso", ["carga_id"], schema="datos")


def downgrade() -> None:
    op.drop_table("carga_paso", schema="datos")
    op.drop_table("venta_cuadre", schema="datos")
    op.drop_table("venta_semanal", schema="datos")
    for nombre in ("archivo", "detener", "meses_hechos", "meses_total", "mes_actual", "paso", "hasta", "desde"):
        op.drop_column("carga", nombre, schema="datos", mssql_drop_default=nombre == "detener")
    op.execute("DELETE FROM datos.carga WHERE fuente = 'ETL_VENTAS'")
    op.drop_constraint("ck_carga_estado", "carga", schema="datos", type_="check")
    op.create_check_constraint("ck_carga_estado", "carga", "estado IN ('en_curso','completa','fallida')", schema="datos")
    op.drop_constraint("ck_carga_fuente", "carga", schema="datos", type_="check")
    op.create_check_constraint("ck_carga_fuente", "carga", "fuente IN ('API','TIENDA','ETL')", schema="datos")
