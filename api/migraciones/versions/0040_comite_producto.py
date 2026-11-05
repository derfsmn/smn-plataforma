"""Comité de producto nuevo: reuniones, productos del ciclo, pre-filtro, decisiones, revisiones posteriores, asistentes y
peticiones. También guarda en cada evaluación con qué semáforo se calificó (con o sin proveedor). Plan aprobado por Diego,
2026-11-04. Modelo en docs/modelos/compras_comite_v0.dbml.

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

USUARIO = "nucleo.usuario.usuario_id"
REUNION = "compras.comite_reunion.reunion_id"
ITEM = "compras.comite_producto.item_id"


def upgrade() -> None:
    op.add_column("producto_evaluacion", sa.Column("modelo", sa.Unicode(20)), schema="compras")
    op.create_table(
        "comite_reunion",
        sa.Column("reunion_id", sa.Integer, primary_key=True),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("notas", sa.Unicode(2000)),
        sa.Column("estado", sa.Unicode(20), nullable=False),
        sa.Column("aprendizajes", sa.UnicodeText),
        sa.Column("creada_por", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("creada_en", sa.DateTime, nullable=False),
        sa.Column("prefiltro_en", sa.DateTime),
        sa.Column("comite_en", sa.DateTime),
        sa.Column("cerrada_en", sa.DateTime),
        sa.Column("cerrada_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.CheckConstraint("estado IN ('abierta','prefiltro','comite','cerrada')", name="ck_comite_reunion_estado"),
        schema="compras",
    )
    op.create_table(
        "comite_producto",
        sa.Column("item_id", sa.Integer, primary_key=True),
        sa.Column("reunion_id", sa.Integer, sa.ForeignKey(REUNION), nullable=False),
        sa.Column("propuesta_id", sa.Integer, sa.ForeignKey("compras.propuesta.propuesta_id")),
        sa.Column("idea_id", sa.Integer, sa.ForeignKey("compras.producto_idea.idea_id")),
        sa.Column("origen", sa.Unicode(20), nullable=False),
        sa.Column("viene_de", sa.Integer, sa.ForeignKey(ITEM)),
        sa.Column("orden", sa.Integer, nullable=False),
        sa.Column("agregado_por", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("agregado_en", sa.DateTime, nullable=False),
        sa.Column("prefiltro", sa.Unicode(10)),
        sa.Column("prefiltro_motivo", sa.Unicode(1000)),
        sa.Column("criterios", sa.UnicodeText),
        sa.Column("prefiltro_color", sa.Unicode(10)),
        sa.Column("prefiltro_puntaje", sa.Integer),
        sa.Column("prefiltro_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("prefiltro_en", sa.DateTime),
        sa.Column("decision", sa.Unicode(12)),
        sa.Column("decision_motivo", sa.Unicode(1000)),
        sa.Column("decision_color", sa.Unicode(10)),
        sa.Column("decision_puntaje", sa.Integer),
        sa.Column("decision_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("decision_en", sa.DateTime),
        sa.CheckConstraint("(propuesta_id IS NOT NULL AND idea_id IS NULL) OR (propuesta_id IS NULL AND idea_id IS NOT NULL)",
                           name="ck_comite_producto_sujeto"),
        sa.CheckConstraint("origen IN ('captura','propuesta','idea','espera')", name="ck_comite_producto_origen"),
        sa.CheckConstraint("prefiltro IS NULL OR prefiltro IN ('pasa','no_pasa')", name="ck_comite_producto_prefiltro"),
        sa.CheckConstraint("decision IS NULL OR decision IN ('aceptado','denegado','en_espera')",
                           name="ck_comite_producto_decision"),
        schema="compras",
    )
    op.create_index("ux_comite_producto_propuesta", "comite_producto", ["reunion_id", "propuesta_id"], unique=True,
                    schema="compras", mssql_where=sa.text("propuesta_id IS NOT NULL"))
    op.create_index("ux_comite_producto_idea", "comite_producto", ["reunion_id", "idea_id"], unique=True,
                    schema="compras", mssql_where=sa.text("idea_id IS NOT NULL"))
    op.create_table(
        "comite_revision",
        sa.Column("item_id", sa.Integer, sa.ForeignKey(ITEM), primary_key=True),
        sa.Column("tipo", sa.Unicode(20), primary_key=True),
        sa.Column("resultado", sa.Unicode(20), nullable=False),
        sa.Column("nota", sa.Unicode(1000)),
        sa.Column("actualizada_por", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("actualizada_en", sa.DateTime, nullable=False),
        sa.CheckConstraint("tipo IN ('inventario','regulacion')", name="ck_comite_revision_tipo"),
        sa.CheckConstraint("resultado IN ('pendiente','aprobada','rechazada')", name="ck_comite_revision_resultado"),
        schema="compras",
    )
    op.create_table(
        "comite_asistente",
        sa.Column("asistente_id", sa.Integer, primary_key=True),
        sa.Column("reunion_id", sa.Integer, sa.ForeignKey(REUNION), nullable=False),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("nombre", sa.Unicode(200), nullable=False),
        sa.Column("puesto", sa.Unicode(120)),
        sa.Column("agregado_en", sa.DateTime, nullable=False),
        schema="compras",
    )
    op.create_table(
        "comite_peticion",
        sa.Column("peticion_id", sa.Integer, primary_key=True),
        sa.Column("reunion_id", sa.Integer, sa.ForeignKey(REUNION), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey(ITEM)),
        sa.Column("asistente_id", sa.Integer, sa.ForeignKey("compras.comite_asistente.asistente_id")),
        sa.Column("texto", sa.Unicode(1000), nullable=False),
        sa.Column("estado", sa.Unicode(10), nullable=False),
        sa.Column("respuesta", sa.Unicode(1000)),
        sa.Column("atendida_por", sa.Integer, sa.ForeignKey(USUARIO)),
        sa.Column("atendida_en", sa.DateTime),
        sa.Column("creada_por", sa.Integer, sa.ForeignKey(USUARIO), nullable=False),
        sa.Column("creada_en", sa.DateTime, nullable=False),
        sa.CheckConstraint("estado IN ('abierta','atendida')", name="ck_comite_peticion_estado"),
        schema="compras",
    )
    # «compras.comite.decidir» ya existía en el catálogo (sin usarse): la semilla solo agrega a los roles los permisos
    # nuevos, así que aquí se le da a los roles que ya existen y deben poder registrar decisiones.
    op.execute("""
        INSERT INTO nucleo.rol_permiso (rol_id, permiso_id)
        SELECT r.rol_id, p.permiso_id FROM nucleo.rol r JOIN nucleo.permiso p ON p.codigo = 'compras.comite.decidir'
        WHERE r.codigo IN ('admin', 'compras_responsable')
          AND NOT EXISTS (SELECT 1 FROM nucleo.rol_permiso x WHERE x.rol_id = r.rol_id AND x.permiso_id = p.permiso_id)
    """)


def downgrade() -> None:
    op.drop_table("comite_peticion", schema="compras")
    op.drop_table("comite_asistente", schema="compras")
    op.drop_table("comite_revision", schema="compras")
    op.drop_index("ux_comite_producto_idea", "comite_producto", schema="compras")
    op.drop_index("ux_comite_producto_propuesta", "comite_producto", schema="compras")
    op.drop_table("comite_producto", schema="compras")
    op.drop_table("comite_reunion", schema="compras")
    op.drop_column("producto_evaluacion", "modelo", schema="compras")
