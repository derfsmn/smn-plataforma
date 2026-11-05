#!/usr/bin/env bash
# Regresa a la versión anterior.
# Uso:  regresar             (solo código, ~2 min, no se pierde nada)
#       regresar --con-base  (código + base como estaba antes de publicar)
set -euo pipefail
. "$(dirname "$(readlink -f "$0")")/comun.sh"
CON_BASE=${1:-}
ACT=$(version_actual)
[ -n "$ACT" ] || { echo "ERROR: no hay versión publicada."; exit 1; }
ANT=$(cat "$VERS/$ACT/.version_anterior" 2>/dev/null || true)
[ -n "$ANT" ] && [ -d "$VERS/$ANT" ] || { echo "ERROR: no encuentro la versión anterior a $ACT en el servidor."; exit 1; }

echo "Versión actual: $ACT  ->  regresar a: $ANT"
if [ "$CON_BASE" = "--con-base" ]; then
  PREVIO=$(cat "$VERS/$ACT/.respaldo_previo")
  echo "La base se va a regresar a como estaba ANTES de publicar $ACT ($PREVIO)."
  echo "Todo lo capturado desde esa publicación se PIERDE (queda un respaldo por si acaso)."
fi
read -r -p "Escribe SI para continuar: " ok
[ "$ok" = "SI" ] || { echo "Cancelado. No se cambió nada."; exit 0; }
exec > >(tee -a "$BASE/regresar_$(date +%Y%m%d_%H%M).log") 2>&1

if [ "$CON_BASE" = "--con-base" ]; then
  respaldar "antes_regresar_${ACT}_$(date +%Y%m%d_%H%M).bak"
  dc "$ACT" stop api
  sqlsa -Q "ALTER DATABASE [$(bd)] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; RESTORE DATABASE [$(bd)] FROM DISK='/respaldos/$PREVIO' WITH REPLACE; ALTER DATABASE [$(bd)] SET MULTI_USER;"
  echo "[base] Restaurada a $PREVIO"
fi
ln -sfn "$VERS/$ANT" "$BASE/actual"
dc "$ANT" up -d --remove-orphans
if salud_ok "$ANT"; then
  anotar "REGRESO de $ACT a $ANT ${CON_BASE}"
  echo "=== Listo: de regreso en $ANT ==="
  # la versión con problemas se quita para poder corregirla y publicarla de nuevo
  rm -rf "${VERS:?}/$ACT"; docker image rm "smn-api:$ACT" "smn-web:$ACT" >/dev/null 2>&1 || true
else
  echo "ATENCIÓN: $ANT no responde. Manda captura a Claude."; exit 1
fi
