"""Métodos y procedimientos (TD004): base de conocimiento de manuales con búsqueda por palabras y por significado,
respuestas con cita, borradores de manuales hechos por la IA local, avisos de manuales viejos o contradictorios,
calificación de respuestas y prueba de preguntas. Pedido de Diego, 2026-10-30.

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

E = "metodos"
USUARIO = "nucleo.usuario.usuario_id"
DOCUMENTO = f"{E}.documento.documento_id"


def upgrade() -> None:
    op.execute(f"IF SCHEMA_ID('{E}') IS NULL EXEC('CREATE SCHEMA {E}')")
    op.create_table(
        "documento",
        sa.Column("documento_id", sa.Integer, primary_key=True),
        sa.Column("clave", sa.Unicode(40)),
        sa.Column("titulo", sa.Unicode(300), nullable=False),
        sa.Column("tipo", sa.Unicode(20), nullable=False),
        sa.Column("area", sa.Unicode(120), nullable=False),
        sa.Column("version", sa.Unicode(30), nullable=False),
        sa.Column("vigente_desde", sa.Date),
        sa.Column("revisar_antes", sa.Date),
        sa.Column("sistema", sa.Unicode(120)),
        sa.Column("roles", sa.Unicode(1000)),
        sa.Column("permiso", sa.Unicode(120)),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("origen", sa.Unicode(20), nullable=False, server_default="cargado"),
        sa.Column("origen_id", sa.Integer),
        sa.Column("archivo_id", sa.BigInteger, sa.ForeignKey("nucleo.archivo.archivo_id")),
        sa.Column("reemplaza_a", sa.Integer, sa.ForeignKey(DOCUMENTO)),
        sa.Column("texto", sa.UnicodeText),
        sa.Column("avisos", sa.UnicodeText),
        sa.Column("cargado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("cargado_en", sa.DateTime, nullable=False),
        sa.Column("aprobado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("aprobado_en", sa.DateTime),
        sa.CheckConstraint("tipo IN ('manual','politica','instructivo','formato','preguntas','otro')", name="ck_metodos_documento_tipo"),
        sa.CheckConstraint("estado IN ('borrador','vigente','reemplazado','retirado')", name="ck_metodos_documento_estado"),
        sa.CheckConstraint("origen IN ('cargado','ia','compras','fiscal')", name="ck_metodos_documento_origen"),
        schema=E,
    )
    op.create_table(
        "fragmento",
        sa.Column("fragmento_id", sa.Integer, primary_key=True),
        sa.Column("documento_id", sa.Integer, sa.ForeignKey(DOCUMENTO, ondelete="CASCADE"), nullable=False),
        sa.Column("orden", sa.Integer, nullable=False),
        sa.Column("seccion", sa.Unicode(400)),
        sa.Column("pagina", sa.Integer),
        sa.Column("texto", sa.UnicodeText, nullable=False),
        sa.Column("vector", sa.LargeBinary),
        sa.Column("modelo_vector", sa.Unicode(80)),
        schema=E,
    )
    op.create_index("ix_metodos_fragmento_documento", "fragmento", ["documento_id", "orden"], schema=E)
    op.create_table(
        "pregunta",
        sa.Column("pregunta_id", sa.Integer, primary_key=True),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("texto", sa.Unicode(1000), nullable=False),
        sa.Column("respuesta", sa.UnicodeText),
        sa.Column("citas", sa.UnicodeText),
        sa.Column("encontrada", sa.Boolean, nullable=False),
        sa.Column("modo", sa.Unicode(20), nullable=False),
        sa.Column("origen", sa.Unicode(60)),
        sa.Column("duracion_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("util", sa.Boolean),
        sa.Column("comentario", sa.Unicode(500)),
        sa.Column("es_prueba", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        schema=E,
    )
    op.create_index("ix_metodos_pregunta_fecha", "pregunta", ["creado_en"], schema=E)
    op.create_table(
        "borrador",
        sa.Column("borrador_id", sa.Integer, primary_key=True),
        sa.Column("tipo", sa.Unicode(20), nullable=False),
        sa.Column("documento_id", sa.Integer, sa.ForeignKey(DOCUMENTO)),
        sa.Column("titulo", sa.Unicode(300), nullable=False),
        sa.Column("area", sa.Unicode(120), nullable=False),
        sa.Column("instrucciones", sa.UnicodeText),
        sa.Column("fuentes", sa.Unicode(1000)),
        sa.Column("texto", sa.UnicodeText),
        sa.Column("cambios", sa.UnicodeText),
        sa.Column("preguntas_abiertas", sa.UnicodeText),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("error", sa.Unicode(1000)),
        sa.Column("creado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        sa.Column("revisado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("revisado_en", sa.DateTime),
        sa.Column("nota", sa.Unicode(1000)),
        sa.Column("publicado_id", sa.Integer, sa.ForeignKey(DOCUMENTO)),
        sa.CheckConstraint("tipo IN ('nuevo','actualizacion','formato')", name="ck_metodos_borrador_tipo"),
        sa.CheckConstraint("estado IN ('generando','listo','error','aprobado','descartado')", name="ck_metodos_borrador_estado"),
        schema=E,
    )
    op.create_table(
        "alerta",
        sa.Column("alerta_id", sa.Integer, primary_key=True),
        sa.Column("tipo", sa.Unicode(20), nullable=False),
        sa.Column("documento_id", sa.Integer, sa.ForeignKey(DOCUMENTO), nullable=False),
        sa.Column("otro_documento_id", sa.Integer, sa.ForeignKey(DOCUMENTO)),
        sa.Column("fragmento_id", sa.Integer),
        sa.Column("otro_fragmento_id", sa.Integer),
        sa.Column("detalle", sa.Unicode(2000), nullable=False),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        sa.Column("atendida_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("atendida_en", sa.DateTime),
        sa.Column("nota", sa.Unicode(1000)),
        sa.CheckConstraint("tipo IN ('contradiccion')", name="ck_metodos_alerta_tipo"),
        sa.CheckConstraint("estado IN ('abierta','atendida','descartada')", name="ck_metodos_alerta_estado"),
        schema=E,
    )
    op.create_table(
        "prueba_pregunta",
        sa.Column("prueba_pregunta_id", sa.Integer, primary_key=True),
        sa.Column("pregunta", sa.Unicode(1000), nullable=False),
        sa.Column("respuesta_esperada", sa.Unicode(2000)),
        sa.Column("documento_id", sa.Integer, sa.ForeignKey(DOCUMENTO)),
        sa.Column("debe_contestar", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("area", sa.Unicode(120)),
        sa.Column("activa", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("creado_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("creado_en", sa.DateTime, nullable=False),
        schema=E,
    )
    op.create_table(
        "prueba_corrida",
        sa.Column("corrida_id", sa.Integer, primary_key=True),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("modo", sa.Unicode(20)),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hechas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("correctas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("inventadas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("no_esta_bien", sa.Integer, nullable=False, server_default="0"),
        sa.Column("no_esta_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("promedio_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("detalle", sa.UnicodeText),
        sa.Column("error", sa.Unicode(1000)),
        sa.Column("corrido_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("iniciada_en", sa.DateTime, nullable=False),
        sa.Column("terminada_en", sa.DateTime),
        sa.CheckConstraint("estado IN ('en_curso','terminada','error')", name="ck_metodos_corrida_estado"),
        schema=E,
    )


def downgrade() -> None:
    for t in ("prueba_corrida", "prueba_pregunta", "alerta", "borrador", "pregunta", "fragmento", "documento"):
        op.drop_table(t, schema=E)
    op.execute(f"IF SCHEMA_ID('{E}') IS NOT NULL EXEC('DROP SCHEMA {E}')")
