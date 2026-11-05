"""Base de conocimiento fiscal (TD003): documentos de soporte, catálogos del SAT con vigencia, criterios fiscales con
versión y aprobación, y su historial. Pedido de Diego, 2026-10-30. La carga inicial la hace scripts.semilla.

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

E = "contraloria"
USUARIO = "nucleo.usuario.usuario_id"
DOCUMENTO = f"{E}.fiscal_documento.documento_id"


def upgrade() -> None:
    op.create_table(
        "fiscal_documento",
        sa.Column("documento_id", sa.Integer, primary_key=True),
        sa.Column("titulo", sa.Unicode(300), nullable=False),
        sa.Column("tipo", sa.Unicode(30), nullable=False),
        sa.Column("version", sa.Unicode(50)),
        sa.Column("vigente_desde", sa.Date),
        sa.Column("notas", sa.Unicode(1000)),
        sa.Column("nombre_archivo", sa.Unicode(260)),
        sa.Column("contenido", sa.LargeBinary),
        sa.Column("tamano", sa.Integer),
        sa.Column("sha256", sa.Unicode(64)),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("reemplaza_a", sa.Integer),
        sa.Column("cargado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("cargado_en", sa.DateTime, nullable=False),
        schema=E,
    )
    op.create_table(
        "fiscal_catalogo",
        sa.Column("catalogo_id", sa.Integer, primary_key=True),
        sa.Column("catalogo", sa.Unicode(20), nullable=False),
        sa.Column("clave", sa.Unicode(20), nullable=False),
        sa.Column("descripcion", sa.Unicode(500), nullable=False),
        sa.Column("valor", sa.Unicode(50)),
        sa.Column("vigente_desde", sa.Date, nullable=False),
        sa.Column("vigente_hasta", sa.Date),
        sa.Column("documento_id", sa.Integer, sa.ForeignKey(DOCUMENTO)),
        sa.Column("creado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        sa.CheckConstraint("catalogo IN ('tipo_tercero','tipo_operacion','layout')", name="ck_fiscal_catalogo"),
        schema=E,
    )
    op.create_table(
        "fiscal_criterio",
        sa.Column("criterio_id", sa.Integer, primary_key=True),
        sa.Column("clave", sa.Unicode(40), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("tipo", sa.Unicode(10), nullable=False),
        sa.Column("categoria", sa.Unicode(20), nullable=False),
        sa.Column("titulo", sa.Unicode(200), nullable=False),
        sa.Column("descripcion", sa.Unicode(2000), nullable=False),
        sa.Column("parametros", sa.UnicodeText),
        sa.Column("condicion", sa.UnicodeText),
        sa.Column("accion", sa.UnicodeText),
        sa.Column("contradiccion", sa.Unicode(2000)),
        sa.Column("documento_id", sa.Integer, sa.ForeignKey(DOCUMENTO)),
        sa.Column("referencia", sa.Unicode(500)),
        sa.Column("evidencia", sa.Unicode(1000)),
        sa.Column("prioridad", sa.Integer, nullable=False, server_default="100"),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey(f"{E}.diot_empresa.empresa_id")),
        sa.Column("vigente_desde", sa.Date, nullable=False),
        sa.Column("vigente_hasta", sa.Date),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("aprobado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("aprobado_en", sa.DateTime),
        sa.Column("nota_aprobacion", sa.Unicode(1000)),
        sa.Column("creado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        sa.UniqueConstraint("clave", "version", name="uq_fiscal_criterio_version"),
        sa.CheckConstraint("tipo IN ('sistema','propio')", name="ck_fiscal_criterio_tipo"),
        sa.CheckConstraint("estado IN ('borrador','pendiente','aprobado','retirado')", name="ck_fiscal_criterio_estado"),
        schema=E,
    )
    op.create_table(
        "fiscal_criterio_cambio",
        sa.Column("cambio_id", sa.Integer, primary_key=True),
        sa.Column("clave", sa.Unicode(40), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("accion", sa.Unicode(20), nullable=False),
        sa.Column("motivo", sa.Unicode(1000)),
        sa.Column("detalle", sa.UnicodeText),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("momento", sa.DateTime, nullable=False),
        schema=E,
    )
    op.add_column("diot_corrida", sa.Column("criterios", sa.UnicodeText), schema=E)


def downgrade() -> None:
    op.drop_column("diot_corrida", "criterios", schema=E)
    for t in ("fiscal_criterio_cambio", "fiscal_criterio", "fiscal_catalogo", "fiscal_documento"):
        op.drop_table(t, schema=E)
