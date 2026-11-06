#!/usr/bin/env bash
# Baja a Ollama los modelos que la plataforma tiene configurados (general y por tarea) y que falten.
# Lo corre publicar.sh al final; también se puede correr a mano:
#   bash /datos/plataforma/actual/publicacion/servidor/bajar_modelos.sh
set -uo pipefail
. "$(dirname "$(readlink -f "$0")")/comun.sh"
MODELOS=$( (leer_env OLLAMA_MODELO
  sqlsa -d "$(bd)" -h -1 -W -Q "SET NOCOUNT ON; SELECT valor FROM nucleo.configuracion WHERE clave='ollama_modelo' UNION SELECT modelo FROM nucleo.ia_tarea WHERE modelo IS NOT NULL AND proveedor_ia LIKE 'ollama%'") | tr -d '\r' | grep -v '^$' | sort -u)
TIENE=$(docker exec smn-ollama-1 ollama list 2>/dev/null | awk 'NR>1{print $1}')
for m in $MODELOS; do
  if echo "$TIENE" | grep -qx -e "$m" -e "$m:latest"; then echo "[modelos] $m ya está"; continue; fi
  echo "[modelos] Bajando $m..."; docker exec smn-ollama-1 ollama pull "$m" || echo "[modelos] No se pudo bajar $m (revisa el nombre en Configuración)"
done
