"""Crea el esquema nucleo (vacío). Las tablas del núcleo llegan en la etapa 3.

Revision ID: 0001
Revises:
Create Date: 2026-10-13
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("IF SCHEMA_ID('nucleo') IS NULL EXEC('CREATE SCHEMA nucleo')")


def downgrade() -> None:
    op.execute("IF SCHEMA_ID('nucleo') IS NOT NULL EXEC('DROP SCHEMA nucleo')")
