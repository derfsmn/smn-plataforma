"""Radar de precios: validación automática de cada precio, «Está mal» de Compras, corrida nocturna por lotes y
selecciones guardadas del reporte a Excel.

Pedido de Diego, 2026-11-17 (plan aprobado: «entonces comienza a trabajar por favor»). Compras no valida nada: la
máquina revisa cada precio con 6 comprobaciones; lo dudoso no cuenta y se reintenta otra noche; Compras solo marca
«Está mal» con motivo.

Revision ID: 0050
Revises: 0049b
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049b"
branch_labels = None
depends_on = None

E = "compras"
CORRIDA = ("programado", "tardio", "manual", "prueba", "producto", "oportunidad")
VIGILADO = ("pantalla", "migracion")


def _en(valores) -> str:
    return "origen IN (" + ",".join(f"'{v}'" for v in valores) + ")"


def upgrade() -> None:
    # Lotes de noche: corridas «nocturna» y productos que entran solos al radar (todo el catálogo activo)
    op.drop_constraint("ck_precio_corrida_origen", "precio_corrida", schema=E)
    op.create_check_constraint("ck_precio_corrida_origen", "precio_corrida", _en(CORRIDA + ("nocturna",)), schema=E)
    op.drop_constraint("ck_precio_vigilado_origen", "precio_vigilado", schema=E)
    op.create_check_constraint("ck_precio_vigilado_origen", "precio_vigilado", _en(VIGILADO + ("nocturna",)), schema=E)
    op.add_column("precio_vigilado", sa.Column("validacion", sa.Unicode(20)), schema=E)  # validado / dudoso / sin_referencia
    op.add_column("precio_vigilado", sa.Column("validado_en", sa.DateTime), schema=E)
    op.add_column("precio_vigilado", sa.Column("revisado_en", sa.DateTime), schema=E)
    op.add_column("precio_vigilado", sa.Column("proxima_revision", sa.DateTime), schema=E)
    op.add_column("precio_vigilado", sa.Column("noches_sin_validar", sa.Integer), schema=E)
    op.create_index("ix_precio_vigilado_proxima", "precio_vigilado", ["proxima_revision"], schema=E)

    op.create_table(
        "precio_validacion",
        sa.Column("observacion_id", sa.BigInteger, sa.ForeignKey(f"{E}.precio_observacion.observacion_id"), primary_key=True),
        sa.Column("corrida_id", sa.Integer, sa.ForeignKey(f"{E}.precio_corrida.corrida_id"), nullable=False),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("datos.producto.producto_id"), nullable=False),
        sa.Column("resultado", sa.Unicode(20), nullable=False),  # validado / dudoso / no_cuenta
        sa.Column("motivo", sa.Unicode(400)),
        sa.Column("comprobaciones", sa.UnicodeText),  # JSON: codigo, marca, variante, contenido, piezas, foto
        sa.Column("sello", sa.UnicodeText),  # JSON: liga, disponible, moneda, promocion, tipo de vendedor, salto
        sa.Column("huella", sa.Unicode(64)),  # liga + título + código + foto: si no cambia, la foto no se vuelve a revisar
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=sa.func.getutcdate()),
        schema=E)
    op.create_index("ix_precio_validacion_producto", "precio_validacion", ["producto_id", "huella"], schema=E)
    op.create_index("ix_precio_validacion_corrida", "precio_validacion", ["corrida_id"], schema=E)

    op.create_table(
        "precio_marca_mal",
        sa.Column("marca_id", sa.Integer, primary_key=True),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey("datos.producto.producto_id"), nullable=False),
        sa.Column("observacion_id", sa.BigInteger, sa.ForeignKey(f"{E}.precio_observacion.observacion_id")),
        sa.Column("vendedor", sa.Unicode(200), nullable=False),
        sa.Column("dominio", sa.Unicode(200)),
        sa.Column("liga", sa.Unicode(800)),
        sa.Column("titulo", sa.Unicode(400)),
        sa.Column("precio", sa.Numeric(12, 2)),
        sa.Column("motivo", sa.Unicode(30), nullable=False),  # otro_sabor / otro_tamano / otro_producto / precio_equivocado / otro
        sa.Column("nota", sa.Unicode(400)),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("nucleo.usuario.usuario_id")),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=sa.func.getutcdate()),
        schema=E)
    op.create_index("ix_precio_marca_mal_producto", "precio_marca_mal", ["producto_id"], schema=E)

    op.create_table(
        "precio_seleccion",
        sa.Column("seleccion_id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.Unicode(120), nullable=False),
        sa.Column("contenido", sa.UnicodeText, nullable=False),  # JSON: producto_ids, marcas, categorias, hojas
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("nucleo.usuario.usuario_id")),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=sa.func.getutcdate()),
        sa.Column("usado_en", sa.DateTime),
        schema=E)


def downgrade() -> None:
    op.drop_table("precio_seleccion", schema=E)
    op.drop_index("ix_precio_marca_mal_producto", "precio_marca_mal", schema=E)
    op.drop_table("precio_marca_mal", schema=E)
    op.drop_index("ix_precio_validacion_corrida", "precio_validacion", schema=E)
    op.drop_index("ix_precio_validacion_producto", "precio_validacion", schema=E)
    op.drop_table("precio_validacion", schema=E)
    op.drop_index("ix_precio_vigilado_proxima", "precio_vigilado", schema=E)
    op.drop_constraint("ck_precio_vigilado_origen", "precio_vigilado", schema=E)
    op.create_check_constraint("ck_precio_vigilado_origen", "precio_vigilado", _en(VIGILADO), schema=E)
    op.drop_constraint("ck_precio_corrida_origen", "precio_corrida", schema=E)
    op.create_check_constraint("ck_precio_corrida_origen", "precio_corrida", _en(CORRIDA), schema=E)
    for c in ("noches_sin_validar", "proxima_revision", "revisado_en", "validado_en", "validacion"):
        op.drop_column("precio_vigilado", c, schema=E)
