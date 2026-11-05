"""Contraloría / Fiscal (TD003): proceso de la DIOT. Pedido de Diego, 2026-10-28.

Fiscal sube los reportes de Intelisis de una empresa y un mes; la plataforma reconoce cada documento, aplica las reglas
reconstruidas del papel de trabajo de Fiscal, consolida por RFC, deja las incidencias para revisión y genera el TXT.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

E = "contraloria"
USUARIO = "nucleo.usuario.usuario_id"
PERIODO = f"{E}.diot_periodo.periodo_id"


def _importe(nombre: str, nulo: bool = False) -> sa.Column:
    return sa.Column(nombre, sa.Numeric(20, 6), nullable=nulo)


def upgrade() -> None:
    op.execute(f"IF SCHEMA_ID('{E}') IS NULL EXEC('CREATE SCHEMA {E}')")
    op.create_table(
        "diot_empresa",
        sa.Column("empresa_id", sa.Integer, primary_key=True),
        sa.Column("codigo", sa.Unicode(20), nullable=False, unique=True),
        sa.Column("nombre", sa.Unicode(200), nullable=False),
        sa.Column("rfc", sa.Unicode(13), nullable=False),
        sa.Column("activa", sa.Boolean, nullable=False, server_default=sa.text("1")),
        schema=E,
    )
    op.create_table(
        "diot_periodo",
        sa.Column("periodo_id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey(f"{E}.diot_empresa.empresa_id"), nullable=False),
        sa.Column("anio", sa.Integer, nullable=False),
        sa.Column("mes", sa.Integer, nullable=False),
        sa.Column("estado", sa.Unicode(20), nullable=False, server_default="abierto"),
        sa.Column("resumen", sa.UnicodeText),
        sa.Column("txt", sa.UnicodeText),
        sa.Column("referencia_nombre", sa.Unicode(200)),
        sa.Column("referencia_txt", sa.UnicodeText),
        sa.Column("comparacion", sa.UnicodeText),
        sa.Column("procesado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("procesado_en", sa.DateTime),
        sa.Column("creado_por", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        sa.UniqueConstraint("empresa_id", "anio", "mes", name="uq_diot_periodo"),
        sa.CheckConstraint("mes BETWEEN 1 AND 12", name="ck_diot_periodo_mes"),
        sa.CheckConstraint("estado IN ('abierto','procesado','cerrado')", name="ck_diot_periodo_estado"),
        schema=E,
    )
    op.create_table(
        "diot_documento",
        sa.Column("documento_id", sa.Integer, primary_key=True),
        sa.Column("periodo_id", sa.Integer, sa.ForeignKey(PERIODO), nullable=False),
        sa.Column("tipo", sa.Unicode(30), nullable=False),
        sa.Column("nombre_archivo", sa.Unicode(260), nullable=False),
        sa.Column("contenido", sa.LargeBinary, nullable=False),
        sa.Column("tamano", sa.Integer, nullable=False),
        sa.Column("sha256", sa.Unicode(64), nullable=False),
        sa.Column("filas", sa.Integer, nullable=False),
        sa.Column("hoja", sa.Unicode(100)),
        sa.Column("vigente", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("cargado_por", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("cargado_en", sa.DateTime, nullable=False),
        schema=E,
    )
    op.create_index("ix_diot_documento_periodo", "diot_documento", ["periodo_id", "tipo"], schema=E)
    op.create_table(
        "diot_operacion",
        sa.Column("operacion_id", sa.Integer, primary_key=True),
        sa.Column("periodo_id", sa.Integer, sa.ForeignKey(PERIODO), nullable=False),
        sa.Column("fuente", sa.Unicode(30), nullable=False),
        sa.Column("renglon", sa.Integer, nullable=False),
        sa.Column("referencia", sa.Unicode(300), nullable=False),
        sa.Column("rfc", sa.Unicode(20)),
        sa.Column("nombre", sa.Unicode(300)),
        sa.Column("regla", sa.Unicode(30), nullable=False),
        sa.Column("incluida", sa.Boolean, nullable=False),
        sa.Column("tasa", sa.Unicode(20)),
        _importe("tipo_cambio"), _importe("base16"), _importe("iva16"), _importe("base8"), _importe("iva8"),
        _importe("base0"), _importe("exento"), _importe("no_objeto"), _importe("iva_retenido"),
        sa.Column("nota", sa.Unicode(500)),
        schema=E,
    )
    op.create_index("ix_diot_operacion_periodo", "diot_operacion", ["periodo_id", "rfc"], schema=E)
    op.create_table(
        "diot_tercero",
        sa.Column("tercero_id", sa.Integer, primary_key=True),
        sa.Column("periodo_id", sa.Integer, sa.ForeignKey(PERIODO), nullable=False),
        sa.Column("rfc", sa.Unicode(20), nullable=False),
        sa.Column("nombre", sa.Unicode(300)),
        sa.Column("tipo_tercero", sa.Unicode(2), nullable=False),
        sa.Column("tipo_operacion", sa.Unicode(2), nullable=False),
        sa.Column("exactos", sa.UnicodeText, nullable=False),
        sa.Column("redondeados", sa.UnicodeText, nullable=False),
        sa.Column("operaciones", sa.Integer, nullable=False),
        sa.Column("fuentes", sa.Unicode(200), nullable=False),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("ajustado", sa.Boolean, nullable=False, server_default=sa.text("0")),
        schema=E,
    )
    op.create_index("ix_diot_tercero_periodo", "diot_tercero", ["periodo_id"], schema=E)
    op.create_table(
        "diot_incidencia",
        sa.Column("incidencia_id", sa.Integer, primary_key=True),
        sa.Column("periodo_id", sa.Integer, sa.ForeignKey(PERIODO), nullable=False),
        sa.Column("huella", sa.Unicode(64), nullable=False),
        sa.Column("impacto", sa.Unicode(20), nullable=False),
        sa.Column("codigo", sa.Unicode(30), nullable=False),
        sa.Column("mensaje", sa.Unicode(1000), nullable=False),
        sa.Column("fuente", sa.Unicode(30)),
        sa.Column("renglon", sa.Integer),
        sa.Column("rfc", sa.Unicode(20)),
        _importe("importe", True),
        sa.Column("estado", sa.Unicode(20), nullable=False, server_default="pendiente"),
        sa.Column("nota_revision", sa.Unicode(1000)),
        sa.Column("revisada_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("revisada_en", sa.DateTime),
        sa.CheckConstraint("impacto IN ('sin_impacto','controlado','posible_impacto')", name="ck_diot_incidencia_impacto"),
        sa.CheckConstraint("estado IN ('pendiente','revisada')", name="ck_diot_incidencia_estado"),
        schema=E,
    )
    op.create_index("ix_diot_incidencia_periodo", "diot_incidencia", ["periodo_id"], schema=E)
    op.create_table(
        "diot_ajuste",
        sa.Column("ajuste_id", sa.Integer, primary_key=True),
        sa.Column("periodo_id", sa.Integer, sa.ForeignKey(PERIODO), nullable=False),
        sa.Column("rfc", sa.Unicode(20), nullable=False),
        sa.Column("nombre", sa.Unicode(300)),
        sa.Column("campo", sa.Unicode(20)),
        _importe("importe", True),
        sa.Column("excluir", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("tipo_tercero", sa.Unicode(2)),
        sa.Column("tipo_operacion", sa.Unicode(2)),
        sa.Column("motivo", sa.Unicode(1000), nullable=False),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("creado_por", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        schema=E,
    )
    # Empresa piloto (las otras dos se dan de alta cuando Fiscal mande sus archivos)
    op.execute(f"INSERT INTO {E}.diot_empresa (codigo, nombre, rfc, activa) VALUES "
               "(N'ODP', N'Operadora y Distribuidora de Productos Naturistas SA de CV', N'ODP160830242', 1)")


def downgrade() -> None:
    for t in ("diot_ajuste", "diot_incidencia", "diot_tercero", "diot_operacion", "diot_documento", "diot_periodo",
              "diot_empresa"):
        op.drop_table(t, schema=E)
    op.execute(f"DROP SCHEMA {E}")
