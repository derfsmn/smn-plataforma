"""Configuración de Alembic. La URL de la base sale de .env (core.config)."""
from alembic import context
from sqlalchemy import create_engine

from core.config import configuracion

# Cuando existan modelos SQLAlchemy, se asigna aquí su metadata para autogenerar migraciones.
target_metadata = None


def run_migrations_online() -> None:
    motor = create_engine(configuracion().url_bd())
    with motor.connect() as conexion:
        context.configure(connection=conexion, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(url=configuracion().url_bd(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
