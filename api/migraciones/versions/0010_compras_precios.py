"""Compras: Radar de precios (productos vigilados, coincidencias, corridas, observaciones, envíos y vendedores).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

E = "compras"
T = sa.Unicode
ahora = sa.text("SYSUTCDATETIME()")
PRODUCTO = "datos.producto.producto_id"
USUARIO = "nucleo.usuario.usuario_id"


def upgrade() -> None:
    op.create_table(
        "precio_vigilado",
        sa.Column("vigilado_id", sa.Integer, primary_key=True),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey(PRODUCTO), nullable=False, unique=True),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("consulta", T(300)),
        sa.Column("origen", T(20), nullable=False),
        sa.Column("agregado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.CheckConstraint("origen IN ('pantalla','migracion')", name="ck_precio_vigilado_origen"),
        schema=E,
    )
    op.create_table(
        "precio_coincidencia",
        sa.Column("coincidencia_id", sa.Integer, primary_key=True),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey(PRODUCTO), nullable=False),
        sa.Column("google_id", T(80)),
        sa.Column("titulo", T(400)),
        sa.Column("liga", T(800)),
        sa.Column("imagen", T(800)),
        sa.Column("estado", T(20), nullable=False),
        sa.Column("confianza", sa.Numeric(5, 2)),
        sa.Column("motivo", T(600)),
        sa.Column("estrategia", T(40)),
        sa.Column("fallos_seguidos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("candidato", sa.UnicodeText),
        sa.Column("decidido_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("verificado_en", sa.DateTime),
        sa.CheckConstraint("estado IN ('automatica','ia','persona','rechazada','invalidada')", name="ck_precio_coincidencia_estado"),
        schema=E,
    )
    op.create_index("ix_precio_coincidencia_producto", "precio_coincidencia", ["producto_id", "estado"], schema=E)
    op.create_table(
        "precio_corrida",
        sa.Column("corrida_id", sa.Integer, primary_key=True),
        sa.Column("fecha", sa.Date, nullable=False, unique=True),
        sa.Column("origen", T(20), nullable=False),
        sa.Column("estado", T(20), nullable=False),
        sa.Column("intentos", sa.Integer, nullable=False, server_default="1"),
        sa.Column("iniciado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        *[sa.Column(c, sa.Integer, nullable=False, server_default="0")
          for c in ("productos", "con_coincidencia", "sin_coincidencia", "con_precios", "fallidos", "alertas")],
        sa.Column("tope_usd", sa.Numeric(10, 4)),
        sa.Column("costo_usd", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("avisos", sa.UnicodeText),
        sa.Column("error", T(1000)),
        sa.Column("iniciado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("terminado_en", sa.DateTime),
        sa.CheckConstraint("origen IN ('programado','tardio','manual')", name="ck_precio_corrida_origen"),
        sa.CheckConstraint("estado IN ('en_curso','completa','parcial','fallida')", name="ck_precio_corrida_estado"),
        schema=E,
    )
    op.create_table(
        "precio_corrida_producto",
        sa.Column("corrida_producto_id", sa.Integer, primary_key=True),
        sa.Column("corrida_id", sa.Integer, sa.ForeignKey(f"{E}.precio_corrida.corrida_id"), nullable=False),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey(PRODUCTO), nullable=False),
        sa.Column("coincidencia_id", sa.Integer, sa.ForeignKey(f"{E}.precio_coincidencia.coincidencia_id")),
        sa.Column("estado", T(30), nullable=False),
        sa.Column("mensaje", T(400)),
        *[sa.Column(c, sa.Numeric(12, 2)) for c in ("precio_lista", "precio_membresia", "precio_tienda")],
        sa.Column("vendedores", sa.Integer, nullable=False, server_default="0"),
        *[sa.Column(c, sa.Numeric(12, 2)) for c in ("minimo", "maximo", "promedio", "mediana")],
        *[sa.Column(c, sa.Numeric(8, 2)) for c in ("dif_lista_mediana_pct", "dif_membresia_mediana_pct", "dif_lista_minimo_pct")],
        sa.UniqueConstraint("corrida_id", "producto_id", name="uq_precio_corrida_producto"),
        schema=E,
    )
    op.create_index("ix_precio_corrida_producto_producto", "precio_corrida_producto", ["producto_id"], schema=E)
    op.create_table(
        "precio_observacion",
        sa.Column("observacion_id", sa.BigInteger, primary_key=True),
        sa.Column("corrida_id", sa.Integer, sa.ForeignKey(f"{E}.precio_corrida.corrida_id"), nullable=False),
        sa.Column("producto_id", sa.Integer, sa.ForeignKey(PRODUCTO), nullable=False),
        sa.Column("coincidencia_id", sa.Integer, sa.ForeignKey(f"{E}.precio_coincidencia.coincidencia_id"), nullable=False),
        sa.Column("vendedor", T(200), nullable=False),
        sa.Column("vendedor_original", T(200)),
        sa.Column("dominio", T(200)),
        sa.Column("liga", T(800)),
        *[sa.Column(c, sa.Numeric(12, 2)) for c in ("precio", "envio", "total")],
        sa.Column("precio_comparable", sa.Numeric(12, 2), nullable=False),
        sa.Column("moneda", T(5), nullable=False),
        sa.Column("disponibilidad", T(120)),
        sa.Column("es_propia", sa.Boolean, nullable=False),
        sa.Column("datos", sa.UnicodeText, nullable=False),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        schema=E,
    )
    op.create_index("ix_precio_observacion_producto", "precio_observacion", ["producto_id", "corrida_id"], schema=E)
    op.create_table(
        "precio_envio",
        sa.Column("envio_id", sa.Integer, primary_key=True),
        sa.Column("corrida_id", sa.Integer, sa.ForeignKey(f"{E}.precio_corrida.corrida_id")),
        sa.Column("tipo", T(20), nullable=False),
        sa.Column("tareas", sa.Integer, nullable=False),
        sa.Column("estado", T(20), nullable=False),
        sa.Column("estimado_usd", sa.Numeric(10, 4), nullable=False),
        sa.Column("costo_usd", sa.Numeric(10, 4)),
        sa.Column("respuesta", sa.UnicodeText),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("confirmado_en", sa.DateTime),
        sa.CheckConstraint("tipo IN ('productos','vendedores')", name="ck_precio_envio_tipo"),
        sa.CheckConstraint("estado IN ('reservado','confirmado','incierto','rechazado')", name="ck_precio_envio_estado"),
        schema=E,
    )
    op.create_table(
        "precio_vendedor",
        sa.Column("vendedor_id", sa.Integer, primary_key=True),
        sa.Column("nombre", T(120), nullable=False, unique=True),
        sa.Column("alias", T(1000)),
        sa.Column("es_propio", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        schema=E,
    )


def downgrade() -> None:
    for tabla in ("precio_vendedor", "precio_envio", "precio_observacion", "precio_corrida_producto",
                  "precio_corrida", "precio_coincidencia", "precio_vigilado"):
        op.drop_table(tabla, schema=E)
