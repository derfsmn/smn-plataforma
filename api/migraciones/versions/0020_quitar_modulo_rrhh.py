"""Quita la iniciativa Recursos Humanos (módulo «rrhh», Reclutamiento digital) a pedido de Diego (2026-10-26).

Lo que la mencionaba (bitácora, archivos, avisos, etc.) se conserva y queda como de plataforma.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-26
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

TABLAS = ("permiso", "rol", "invitacion", "bitacora", "archivo", "notificacion", "ia_tarea", "ia_presupuesto")
RRHH = "(SELECT modulo_id FROM nucleo.modulo WHERE codigo = 'rrhh')"


def upgrade() -> None:
    for tabla in TABLAS:
        op.execute(f"UPDATE nucleo.{tabla} SET modulo_id = NULL WHERE modulo_id = {RRHH}")
    op.execute("DELETE FROM nucleo.modulo WHERE codigo = 'rrhh'")


def downgrade() -> None:
    op.execute(
        "IF NOT EXISTS (SELECT 1 FROM nucleo.modulo WHERE codigo = 'rrhh') "
        "INSERT INTO nucleo.modulo (codigo, nombre, area, descripcion, estado, tiene_portal_externo, orden_menu, icono, creado_en) "
        "VALUES ('rrhh', N'Reclutamiento digital', N'Recursos Humanos', "
        "N'Postulación a vacantes por tienda con QR y seguimiento.', 'en_diseno', 1, 20, 'personas', GETDATE())"
    )
