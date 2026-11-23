"""Buscar en internet sin API externa: Google por DataForSEO + IA local (Diego, 18 nov 2026).

- compras.precio_corrida acepta el origen «web» (búsquedas del radar de noticias y de los más vendidos).
- compras.precio_envio acepta «noticias» (Google Noticias).
- Las tareas compras.radar_buscar y compras.oportunidades_novedades dejan la API externa: pasan a Ollama con qwen3:8b.
  Solo se cambian si siguen en «api» (si alguien ya las cambió en Administración > IA, se respeta).
- El resumen y la clasificación del radar de noticias y la coincidencia del radar de precios quedan solo en Ollama
  (sin respaldo en la API externa): Diego quiere solo IA local.

Revision ID: 0051
Revises: 0050
Create Date: 2026-11-18
"""
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

E = "compras"
CORRIDA = ("programado", "tardio", "manual", "prueba", "producto", "oportunidad", "nocturna")
ENVIO = ("productos", "vendedores", "organico")
TAREAS = "('compras.radar_buscar','compras.oportunidades_novedades')"
SOLO_LOCAL = "('compras.radar_resumen','compras.radar_clasificar','compras.precios_coincidencia')"


def _en(columna: str, valores) -> str:
    return f"{columna} IN (" + ",".join(f"'{v}'" for v in valores) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_precio_corrida_origen", "precio_corrida", schema=E, type_="check")
    op.create_check_constraint("ck_precio_corrida_origen", "precio_corrida", _en("origen", CORRIDA + ("web",)), schema=E)
    op.drop_constraint("ck_precio_envio_tipo", "precio_envio", schema=E, type_="check")
    op.create_check_constraint("ck_precio_envio_tipo", "precio_envio", _en("tipo", ENVIO + ("noticias",)), schema=E)
    op.execute(f"UPDATE nucleo.ia_tarea SET proveedor_ia = 'ollama', modelo = COALESCE(modelo, 'qwen3:8b') "
               f"WHERE codigo IN {TAREAS} AND proveedor_ia = 'api'")
    # Las que aún podían caer en la API externa (lo mismo que se hizo a mano en el servidor el 18 nov)
    op.execute(f"UPDATE nucleo.ia_tarea SET proveedor_ia = 'ollama' WHERE codigo IN {SOLO_LOCAL} AND proveedor_ia <> 'ollama'")


def downgrade() -> None:
    op.execute(f"UPDATE nucleo.ia_tarea SET proveedor_ia = 'api' WHERE codigo IN {TAREAS}")
    op.execute("UPDATE compras.precio_envio SET tipo = 'organico' WHERE tipo = 'noticias'")
    op.drop_constraint("ck_precio_envio_tipo", "precio_envio", schema=E, type_="check")
    op.create_check_constraint("ck_precio_envio_tipo", "precio_envio", _en("tipo", ENVIO), schema=E)
    op.execute("UPDATE compras.precio_corrida SET origen = 'oportunidad' WHERE origen = 'web'")
    op.drop_constraint("ck_precio_corrida_origen", "precio_corrida", schema=E, type_="check")
    op.create_check_constraint("ck_precio_corrida_origen", "precio_corrida", _en("origen", CORRIDA), schema=E)
