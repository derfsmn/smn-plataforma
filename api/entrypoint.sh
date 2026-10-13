#!/bin/sh
set -e
python -m scripts.preparar_bd
alembic upgrade head
exec uvicorn main:app --host 0.0.0.0 --port 8000 "$@"
