#!/bin/sh
set -e
# Arranca como root solo para dejar al usuario «app» la carpeta de archivos (volumen o carpeta del servidor) y luego
# corre todo como «app», sin privilegios (revisión de seguridad 2026-11-22, M6).
if [ "$(id -u)" = "0" ]; then
  RUTA="${ARCHIVOS_RUTA:-/datos/archivos}"
  mkdir -p "$RUTA"
  find "$RUTA" \( ! -user app -o ! -group app \) -exec chown app:app {} + 2>/dev/null || true
  exec setpriv --reuid=app --regid=app --init-groups "$0" "$@"
fi
python -m scripts.preparar_bd
alembic upgrade head
python -m scripts.semilla
exec uvicorn main:app --host 0.0.0.0 --port 8000 "$@"
