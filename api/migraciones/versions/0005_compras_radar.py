"""Compras: esquema compras y tablas del Radar de tendencias.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

E = "compras"
N = "nucleo"
T = sa.Unicode
ahora = sa.text("SYSUTCDATETIME()")


def fk(tabla: str, columna: str, esquema: str = E) -> sa.ForeignKey:
    return sa.ForeignKey(f"{esquema}.{tabla}.{columna}")


def upgrade() -> None:
    op.execute("IF SCHEMA_ID('compras') IS NULL EXEC('CREATE SCHEMA compras')")

    op.create_table(
        "radar_fuente",
        sa.Column("fuente_id", sa.Integer, primary_key=True),
        sa.Column("nombre", T(160), nullable=False),
        sa.Column("liga", T(400), nullable=False),
        sa.Column("tipo", T(30), nullable=False),
        sa.Column("pais", T(20), nullable=False),
        sa.Column("idioma", T(5), nullable=False),
        sa.Column("metodo", T(20), nullable=False),
        sa.Column("lectura", T(600)),
        sa.Column("activa", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notas", T(400)),
        sa.Column("ultima_lectura_en", sa.DateTime),
        sa.Column("ultimo_resultado", T(300)),
        sa.Column("ultimos_articulos", sa.Integer),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("actualizado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.CheckConstraint("metodo IN ('rss','busqueda','manual')", name="ck_radar_fuente_metodo"),
        sa.CheckConstraint("tipo IN ('oficial','especializada','negocios','estudios')", name="ck_radar_fuente_tipo"),
        schema=E,
    )

    op.create_table(
        "radar_tema",
        sa.Column("tema_id", sa.Integer, primary_key=True),
        sa.Column("nombre", T(120), nullable=False),
        sa.Column("descripcion", T(600), nullable=False),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("orden", sa.Integer, nullable=False, server_default="100"),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        schema=E,
    )

    op.create_table(
        "radar_reporte",
        sa.Column("reporte_id", sa.Integer, primary_key=True),
        sa.Column("fecha", sa.Date, nullable=False, unique=True),
        sa.Column("estado", T(20), nullable=False, server_default="en_curso"),
        sa.Column("origen", T(20), nullable=False),
        sa.Column("intentos", sa.Integer, nullable=False, server_default="1"),
        sa.Column("iniciado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("terminado_en", sa.DateTime),
        sa.Column("iniciado_por", sa.Integer, fk("usuario", "usuario_id", N)),
        sa.Column("fuentes_leidas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("fuentes_con_error", sa.Integer, nullable=False, server_default="0"),
        sa.Column("busquedas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("articulos_nuevos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("articulos_relevantes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("resumen", sa.UnicodeText),
        sa.Column("radar_ejecutivo", sa.UnicodeText),
        sa.Column("avisos", sa.UnicodeText),
        sa.Column("correos_enviados", sa.Integer, nullable=False, server_default="0"),
        sa.Column("correos_fallidos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", T(1000)),
        sa.CheckConstraint("estado IN ('en_curso','listo','error')", name="ck_radar_reporte_estado"),
        sa.CheckConstraint("origen IN ('programado','tardio','manual')", name="ck_radar_reporte_origen"),
        schema=E,
    )

    op.create_table(
        "radar_articulo",
        sa.Column("articulo_id", sa.BigInteger, primary_key=True),
        sa.Column("reporte_id", sa.Integer, fk("radar_reporte", "reporte_id")),
        sa.Column("fuente_id", sa.Integer, fk("radar_fuente", "fuente_id")),
        sa.Column("tema_id", sa.Integer, fk("radar_tema", "tema_id")),
        sa.Column("origen", T(20), nullable=False),
        sa.Column("url", T(1000), nullable=False),
        sa.Column("url_hash", T(64), nullable=False, unique=True),
        sa.Column("titulo_hash", T(64), nullable=False),
        sa.Column("sitio", T(200), nullable=False),
        sa.Column("titulo", T(500), nullable=False),
        sa.Column("extracto", sa.UnicodeText),
        sa.Column("publicado_en", sa.Date),
        sa.Column("leido_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.Column("en_ventana", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("relevante", sa.Boolean),
        sa.Column("categoria", T(40)),
        sa.Column("nivel", T(10)),
        sa.Column("departamento", T(80)),
        sa.Column("pais", T(20)),
        sa.Column("por_que", T(600)),
        sa.Column("clasificado_en", sa.DateTime),
        sa.CheckConstraint("origen IN ('lista','busqueda')", name="ck_radar_articulo_origen"),
        schema=E,
    )
    op.create_index("ix_radar_articulo_reporte", "radar_articulo", ["reporte_id", "relevante"], schema=E)
    op.create_index("ix_radar_articulo_titulo", "radar_articulo", ["titulo_hash"], schema=E)
    op.create_index("ix_radar_articulo_leido", "radar_articulo", ["leido_en"], schema=E)

    op.create_table(
        "radar_senal",
        sa.Column("senal_id", sa.Integer, primary_key=True),
        sa.Column("titulo", T(300), nullable=False),
        sa.Column("descripcion", T(1000)),
        sa.Column("tipo", T(20), nullable=False, server_default="emergente"),
        sa.Column("nivel", T(10), nullable=False),
        sa.Column("categoria", T(40)),
        sa.Column("departamento", T(80)),
        sa.Column("paises", T(60)),
        sa.Column("sitios_distintos", sa.Integer, nullable=False, server_default="1"),
        sa.Column("primera_vez", sa.Date, nullable=False),
        sa.Column("ultima_vez", sa.Date, nullable=False),
        sa.Column("veces_reportada", sa.Integer, nullable=False, server_default="0"),
        sa.Column("estado", T(20), nullable=False, server_default="nueva"),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.CheckConstraint("tipo IN ('emergente','tendencia')", name="ck_radar_senal_tipo"),
        sa.CheckConstraint("estado IN ('nueva','vigilar','descartada','iniciativa')", name="ck_radar_senal_estado"),
        schema=E,
    )

    op.create_table(
        "radar_senal_articulo",
        sa.Column("senal_id", sa.Integer, fk("radar_senal", "senal_id"), primary_key=True),
        sa.Column("articulo_id", sa.BigInteger, fk("radar_articulo", "articulo_id"), primary_key=True),
        schema=E,
    )

    op.create_table(
        "radar_hallazgo",
        sa.Column("hallazgo_id", sa.Integer, primary_key=True),
        sa.Column("reporte_id", sa.Integer, fk("radar_reporte", "reporte_id"), nullable=False),
        sa.Column("senal_id", sa.Integer, fk("radar_senal", "senal_id"), nullable=False),
        sa.Column("orden", sa.Integer, nullable=False),
        sa.Column("titulo", T(300), nullable=False),
        sa.Column("por_que", T(1000), nullable=False),
        sa.Column("nivel", T(10), nullable=False),
        sa.Column("tipo", T(20), nullable=False),
        sa.Column("departamento", T(80)),
        sa.Column("paises", T(60)),
        schema=E,
    )

    op.create_table(
        "radar_accion",
        sa.Column("accion_id", sa.Integer, primary_key=True),
        sa.Column("senal_id", sa.Integer, fk("radar_senal", "senal_id"), nullable=False),
        sa.Column("accion", T(20), nullable=False),
        sa.Column("motivo", T(600)),
        sa.Column("usuario_id", sa.Integer, fk("usuario", "usuario_id", N), nullable=False),
        sa.Column("ocurrido_en", sa.DateTime, nullable=False, server_default=ahora),
        sa.CheckConstraint("accion IN ('iniciativa','vigilar','descartar')", name="ck_radar_accion_accion"),
        schema=E,
    )

    op.create_table(
        "radar_destinatario",
        sa.Column("destinatario_id", sa.Integer, primary_key=True),
        sa.Column("nombre", T(160), nullable=False),
        sa.Column("correo", T(254), nullable=False, unique=True),
        sa.Column("area", T(120)),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime, nullable=False, server_default=ahora),
        schema=E,
    )

    op.create_table(
        "radar_documento",
        sa.Column("documento_id", sa.Integer, primary_key=True),
        sa.Column("archivo_id", sa.BigInteger, fk("archivo", "archivo_id", N), nullable=False),
        sa.Column("titulo", T(200), nullable=False),
        sa.Column("descripcion", T(600)),
        sa.Column("texto", sa.UnicodeText),
        sa.Column("caracteres", sa.Integer, nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("subido_por", sa.Integer, fk("usuario", "usuario_id", N), nullable=False),
        sa.Column("subido_en", sa.DateTime, nullable=False, server_default=ahora),
        schema=E,
    )


def downgrade() -> None:
    for tabla in ("radar_documento", "radar_destinatario", "radar_accion", "radar_hallazgo", "radar_senal_articulo",
                  "radar_senal", "radar_articulo", "radar_reporte", "radar_tema", "radar_fuente"):
        op.drop_table(tabla, schema=E)
    op.execute("IF SCHEMA_ID('compras') IS NOT NULL EXEC('DROP SCHEMA compras')")
