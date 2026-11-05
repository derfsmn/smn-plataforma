"""Centro de datos: esquema datos y catálogo de productos (producto, fuentes, historial de precios, cargas).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

E = "datos"
T = sa.Unicode
ahora = sa.text("SYSUTCDATETIME()")
FUENTES = "fuente IN ('API','TIENDA','ETL')"


def upgrade() -> None:
    op.execute("IF SCHEMA_ID('datos') IS NULL EXEC('CREATE SCHEMA datos')")

    op.create_table(
        "producto",
        sa.Column("producto_id", sa.Integer, primary_key=True),
        sa.Column("sku", T(80), nullable=False, unique=True),
        sa.Column("descripcion", T(1000)),
        sa.Column("marca", T(300)),
        sa.Column("departamento", T(300)),
        sa.Column("rama", T(300)),
        sa.Column("subcategoria", T(300)),
        sa.Column("segmento", T(300)),
        sa.Column("clasificacion", T(100)),
        sa.Column("codigo_proveedor", T(150)),
        sa.Column("nombre_proveedor", T(500)),
        sa.Column("codigo_barras", T(60)),
        sa.Column("precio_lista", sa.Numeric(14, 4)),
        sa.Column("precio_membresia", sa.Numeric(14, 4)),
        sa.Column("iva_pct", sa.Numeric(9, 4)),
        sa.Column("ieps_pct", sa.Numeric(9, 4)),
        sa.Column("precio_lista_con_impuestos", sa.Numeric(14, 2)),
        sa.Column("precio_membresia_con_impuestos", sa.Numeric(14, 2)),
        sa.Column("precio_tienda_en_linea", sa.Numeric(14, 2)),
        sa.Column("disponible_en_linea", sa.Boolean),
        sa.Column("liga_producto", T(600)),
        sa.Column("liga_imagen", T(600)),
        sa.Column("origen", T(20), nullable=False),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("con_diferencias", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("datos_incompletos", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("diferencias", sa.UnicodeText),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("actualizado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.CheckConstraint("origen IN ('API','TIENDA','AMBOS','ETL','ARCHIVADO')", name="ck_producto_origen"),
        schema=E,
    )
    op.create_index("ix_producto_departamento", "producto", ["departamento"], schema=E)
    op.create_index("ix_producto_marca", "producto", ["marca"], schema=E)

    op.create_table(
        "carga",
        sa.Column("carga_id", sa.Integer, primary_key=True),
        sa.Column("fuente", T(20), nullable=False),
        sa.Column("disparada_por", T(20), nullable=False),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("nucleo.usuario.usuario_id")),
        sa.Column("estado", T(20), nullable=False, server_default="en_curso"),
        sa.Column("completa", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("paginas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("leidos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("creados", sa.Integer, nullable=False, server_default="0"),
        sa.Column("actualizados", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sin_cambios", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ausentes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("invalidos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("precios_cambiados", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_fuente", sa.Integer),
        sa.Column("error", T(1000)),
        sa.Column("inicio_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("fin_en", sa.DateTime),
        sa.CheckConstraint(FUENTES, name="ck_carga_fuente"),
        sa.CheckConstraint("estado IN ('en_curso','completa','fallida')", name="ck_carga_estado"),
        sa.CheckConstraint("disparada_por IN ('programador','manual')", name="ck_carga_disparada_por"),
        schema=E,
    )

    op.create_table(
        "producto_fuente",
        sa.Column("producto_fuente_id", sa.Integer, primary_key=True),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("datos.producto.producto_id"), nullable=False),
        sa.Column("fuente", T(20), nullable=False),
        sa.Column("clave_externa", T(120), nullable=False, server_default=""),
        sa.Column("presente", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("datos", sa.UnicodeText, nullable=False),
        sa.Column("huella", sa.String(64), nullable=False),
        sa.Column("visto_por_ultima_vez_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.UniqueConstraint("producto_id", "fuente", "clave_externa", name="uq_producto_fuente"),
        sa.CheckConstraint(FUENTES, name="ck_producto_fuente_fuente"),
        schema=E,
    )

    op.create_table(
        "producto_precio_historial",
        sa.Column("historial_id", sa.Integer, primary_key=True),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("datos.producto.producto_id"), nullable=False),
        sa.Column("precio_lista", sa.Numeric(14, 4)),
        sa.Column("precio_membresia", sa.Numeric(14, 4)),
        sa.Column("iva_pct", sa.Numeric(9, 4)),
        sa.Column("ieps_pct", sa.Numeric(9, 4)),
        sa.Column("precio_tienda_en_linea", sa.Numeric(14, 2)),
        sa.Column("vigente_desde", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("carga_id", sa.Integer, sa.ForeignKey("datos.carga.carga_id")),
        schema=E,
    )
    op.create_index("ix_producto_precio_historial_producto", "producto_precio_historial", ["producto_id", "vigente_desde"], schema=E)


def downgrade() -> None:
    for tabla in ("producto_precio_historial", "producto_fuente", "carga", "producto"):
        op.drop_table(tabla, schema=E)
    op.execute("IF SCHEMA_ID('datos') IS NOT NULL EXEC('DROP SCHEMA datos')")
