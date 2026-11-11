"""Las tareas del radar de productos que no buscan en internet pasan a solo IA local (Ollama). Diego, 2026-11-09:
eligió «Pasar a Ollama» (IA local, sin API externa ni de respaldo). El agente con búsqueda web
(compras.oportunidades_novedades) sigue en la API externa, porque Ollama no busca en internet.

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-09
"""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

TAREAS = ("compras.productos_clasificar", "compras.productos_explicar", "compras.productos_tendencia",
          "compras.productos_politicas", "compras.oportunidades")
ANTES = {"compras.productos_clasificar": "ollama_y_api_respaldo", "compras.productos_explicar": "ollama_y_api_respaldo",
         "compras.productos_tendencia": "ollama_y_api_respaldo", "compras.productos_politicas": "api",
         "compras.oportunidades": "api"}


def upgrade() -> None:
    lista = ", ".join(f"'{t}'" for t in TAREAS)
    op.execute(f"UPDATE nucleo.ia_tarea SET proveedor_ia = 'ollama' WHERE codigo IN ({lista})")


def downgrade() -> None:
    for codigo, proveedor in ANTES.items():
        op.execute(f"UPDATE nucleo.ia_tarea SET proveedor_ia = '{proveedor}' WHERE codigo = '{codigo}'")
