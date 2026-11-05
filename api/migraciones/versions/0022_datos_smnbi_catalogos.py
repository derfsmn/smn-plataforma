"""Tablas de SMNBI para el semáforo de productos: artículos (al catálogo), tiendas, proveedores, compras por orden,
costo de compra por artículo e inventario (pedido de Diego, 2026-10-26: «que se evalúe con todo lo que tenemos»).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

CARGA = "datos.carga.carga_id"
FUENTES_NUEVAS = ("SMNBI_ARTICULOS", "SMNBI_TIENDAS", "SMNBI_PROVEEDORES", "SMNBI_COMPRAS", "SMNBI_COSTOS", "SMNBI_INVENTARIO")


def _fuentes(extra: tuple[str, ...]) -> str:
    return "fuente IN (" + ",".join(f"'{f}'" for f in ("API", "TIENDA", "ETL", "ETL_VENTAS", *extra)) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_carga_fuente", "carga", schema="datos", type_="check")
    op.create_check_constraint("ck_carga_fuente", "carga", _fuentes(FUENTES_NUEVAS), schema="datos")

    # De tblArticulos: solo los trae SMNBI
    for columna in (sa.Column("categoria", sa.Unicode(300)), sa.Column("fabricante", sa.Unicode(300)),
                    sa.Column("tipo_compra", sa.Unicode(100)), sa.Column("estatus_erp", sa.Unicode(30))):
        op.add_column("producto", columna, schema="datos")

    op.create_table(
        "tienda",
        sa.Column("almacen", sa.Unicode(10), primary_key=True),  # = venta_semanal.tienda
        sa.Column("nombre", sa.Unicode(100), nullable=False),
        sa.Column("poblacion", sa.Unicode(100)),
        sa.Column("estado", sa.Unicode(30)),
        sa.Column("codigo_postal", sa.Unicode(15)),
        sa.Column("grupo", sa.Unicode(50)),
        sa.Column("ruta", sa.Unicode(50)),  # TIENDAS = tienda de venta al público
        sa.Column("sucursal", sa.Integer),
        sa.Column("estatus", sa.Unicode(15)),
        sa.Column("region", sa.Unicode(50)),
        sa.Column("categoria", sa.Unicode(50)),  # AA, A, B, C, D, E; MAY = mayoreo
        sa.Column("fecha_apertura", sa.Date),
        sa.Column("latitud", sa.Float),
        sa.Column("longitud", sa.Float),
        sa.Column("carga_id", sa.Integer, sa.ForeignKey(CARGA), nullable=False),
        schema="datos",
    )

    op.create_table(
        "proveedor",
        sa.Column("proveedor", sa.Unicode(10), primary_key=True),  # = producto.codigo_proveedor
        sa.Column("nombre", sa.Unicode(100)),
        sa.Column("estatus", sa.Unicode(15)),
        sa.Column("condicion", sa.Unicode(30)),
        sa.Column("descuento", sa.Unicode(30)),
        sa.Column("descuento_adicional", sa.Numeric(9, 4)),
        sa.Column("dias_entrega", sa.Integer),  # lo que promete
        sa.Column("penalizacion", sa.Numeric(9, 4)),
        sa.Column("carga_id", sa.Integer, sa.ForeignKey(CARGA), nullable=False),
        schema="datos",
    )

    # Una fila por orden de compra con lo que pasó después (entradas, compra perdida, compra rechazada)
    op.create_table(
        "compra_orden",
        sa.Column("empresa", sa.Unicode(5), nullable=False),
        sa.Column("orden", sa.Unicode(20), nullable=False),  # tblCompra.NumMov
        sa.Column("proveedor", sa.Unicode(10)),
        sa.Column("almacen", sa.Unicode(10)),
        sa.Column("fecha_orden", sa.Date, nullable=False),
        sa.Column("estatus", sa.Unicode(15)),
        sa.Column("piezas_pedidas", sa.Numeric(16, 3)),
        sa.Column("importe_pedido", sa.Numeric(18, 2)),
        sa.Column("primera_entrada", sa.Date),
        sa.Column("ultima_entrada", sa.Date),
        sa.Column("piezas_recibidas", sa.Numeric(16, 3), nullable=False),
        sa.Column("piezas_perdidas", sa.Numeric(16, 3), nullable=False),
        sa.Column("piezas_rechazadas", sa.Numeric(16, 3), nullable=False),
        sa.Column("carga_id", sa.Integer, sa.ForeignKey(CARGA), nullable=False),
        sa.PrimaryKeyConstraint("empresa", "orden", name="pk_compra_orden"),
        schema="datos",
    )
    op.create_index("ix_compra_orden_proveedor", "compra_orden", ["proveedor", "fecha_orden"], schema="datos")

    # Costo de compra por artículo: la última entrada y el promedio de los últimos 12 meses, por pieza y sin IVA
    op.create_table(
        "costo_articulo",
        sa.Column("sku", sa.Unicode(80), primary_key=True),
        sa.Column("proveedor", sa.Unicode(10)),
        sa.Column("fecha_ultima", sa.Date),
        sa.Column("costo_ultimo", sa.Numeric(14, 4)),
        sa.Column("costo_12m", sa.Numeric(14, 4)),
        sa.Column("piezas_12m", sa.Numeric(16, 3)),
        sa.Column("compras_12m", sa.Integer),
        sa.Column("carga_id", sa.Integer, sa.ForeignKey(CARGA), nullable=False),
        schema="datos",
    )

    # Foto del inventario por fecha de corte (cada carga reemplaza su fecha; las demás se quedan)
    op.create_table(
        "inventario",
        sa.Column("fecha_corte", sa.Date, nullable=False),
        sa.Column("empresa", sa.Unicode(5), nullable=False),
        sa.Column("almacen", sa.Unicode(10), nullable=False),
        sa.Column("sku", sa.Unicode(80), nullable=False),
        sa.Column("existencia", sa.Numeric(16, 3), nullable=False),
        sa.Column("costo_promedio", sa.Numeric(14, 4)),
        sa.Column("carga_id", sa.Integer, sa.ForeignKey(CARGA), nullable=False),
        sa.PrimaryKeyConstraint("fecha_corte", "empresa", "almacen", "sku", name="pk_inventario"),
        schema="datos",
    )
    op.create_index("ix_inventario_sku", "inventario", ["sku", "fecha_corte"], schema="datos")


def downgrade() -> None:
    for tabla in ("inventario", "costo_articulo", "compra_orden", "proveedor", "tienda"):
        op.drop_table(tabla, schema="datos")
    for nombre in ("estatus_erp", "tipo_compra", "fabricante", "categoria"):
        op.drop_column("producto", nombre, schema="datos")
    op.execute("DELETE FROM datos.producto_fuente WHERE fuente = 'ETL'")
    op.execute("DELETE FROM datos.carga WHERE fuente LIKE 'SMNBI[_]%'")
    op.drop_constraint("ck_carga_fuente", "carga", schema="datos", type_="check")
    op.create_check_constraint("ck_carga_fuente", "carga", _fuentes(()), schema="datos")
