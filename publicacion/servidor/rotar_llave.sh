#!/usr/bin/env bash
# Llave de cifrado propia y contraseña de sa nueva (revisión de seguridad 2026-11-22, hallazgo A2). Se corre en el servidor,
# después de publicar la versión que trae scripts/rotar_llave.py. Son dos partes, en este orden:
#
#   bash rotar_llave.sh llave   1) respaldo, 2) crea CLAVE_CIFRADO si falta, 3) reinicia la API, 4) vuelve a cifrar todo
#                               con la llave nueva y comprueba que todo abre.
#   bash rotar_llave.sh sa      cambia la contraseña de sa (solo si la parte «llave» terminó bien) y vuelve a comprobar.
#
# La llave nueva SOLO vive en /datos/plataforma/.env: cópiala también a un lugar seguro (gestor de contraseñas de la
# empresa). Sin ella no se abren las fórmulas ni los secretos, ni en el servidor ni en un respaldo.
set -euo pipefail
. "$(dirname "$(readlink -f "$0")")/comun.sh"
PARTE=${1:-}
V=$(version_actual)
[ -n "$V" ] || { echo "ERROR: no hay versión publicada."; exit 1; }
api(){ docker exec -i smn-api-1 python -m scripts.rotar_llave "$@"; }
reiniciar_api(){ dc "$V" up -d --force-recreate api >/dev/null; salud_ok "$V" || { echo "ERROR: la API no quedó sana."; exit 1; }; }

case "$PARTE" in
  llave)
    docker exec smn-api-1 test -f scripts/rotar_llave.py || { echo "ERROR: la versión $V no trae scripts/rotar_llave.py; publica la nueva primero."; exit 1; }
    F=$(date +%Y%m%d_%H%M)
    respaldar "antes_llave_$F.bak"
    sudo cp "$ENVF" "$BASE/.env.antes_llave_$F" && sudo chmod 600 "$BASE/.env.antes_llave_$F"
    echo "[respaldo] .env copiado a $BASE/.env.antes_llave_$F"
    if [ -z "$(leer_env CLAVE_CIFRADO)" ]; then
      poner_env CLAVE_CIFRADO "$(openssl rand -base64 48 | tr -d '\n/+=' | cut -c1-56)"
      echo "[llave] CLAVE_CIFRADO creada en $ENVF (56 caracteres)."
    else
      echo "[llave] CLAVE_CIFRADO ya existía; se usa esa."
    fi
    reiniciar_api
    echo; echo "=== Estado antes ==="; api || true
    echo; echo "=== Volver a cifrar con la llave nueva ==="
    if api --aplicar; then
      anotar "llave de cifrado propia aplicada (v$V)"
      echo; echo "=== Listo. Siguiente: guarda la llave (grep ^CLAVE_CIFRADO= $ENVF) en un lugar seguro y corre: bash $0 sa ==="
    else
      echo; echo "=== OJO: revisa el mensaje de arriba. NO corras la parte «sa» todavía; mándame esta salida. ==="; exit 1
    fi
    ;;
  sa)
    [ -n "$(leer_env CLAVE_CIFRADO)" ] || { echo "ERROR: primero corre: bash $0 llave"; exit 1; }
    api >/dev/null || { echo "ERROR: rotar_llave dice que algo no está con la llave nueva; corre «bash $0 llave» y mándame la salida."; exit 1; }
    NUEVA="Sa-$(openssl rand -hex 20)-Z9"
    sqlsa -Q "ALTER LOGIN sa WITH PASSWORD = '$NUEVA'" >/dev/null
    poner_env MSSQL_SA_PASSWORD "$NUEVA"
    esperar_sql
    reiniciar_api
    echo "=== Comprobación con la contraseña nueva ==="
    api
    anotar "contraseña de sa cambiada (v$V)"
    echo; echo "=== Listo. La contraseña de sa ya no es la de tu laptop. Está solo en $ENVF. ==="
    ;;
  *)
    echo "Uso: bash $0 llave   (primero)   ·   bash $0 sa   (después)"; exit 1 ;;
esac
