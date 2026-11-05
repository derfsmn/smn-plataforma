#!/usr/bin/env bash
# Lo corre cron todos los días a las 2:30 am (como root). Guarda 14 días de respaldos diarios
# y 30 días de respaldos previos a cada publicación. Anota si el servidor se reinició.
set -uo pipefail
. "$(dirname "$(readlink -f "$0")")/comun.sh"
LOG=/datos/respaldos/respaldo.log
{
  echo "--- $(date '+%Y-%m-%d %H:%M') · encendido desde $(uptime -s)"
  respaldar "smn_td_$(date +%Y%m%d).bak" || echo "ERROR: falló el respaldo"
  find /datos/respaldos -name 'smn_td_2*.bak' -mtime +14 -delete
  find /datos/respaldos -name 'antes_*.bak' -mtime +30 -delete
  df -h /datos | tail -1
} >> "$LOG" 2>&1
