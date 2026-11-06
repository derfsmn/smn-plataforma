#!/usr/bin/env bash
# Publica una versión cerrada en el servidor.
# Uso:  publicar v1.3      (el comando trae la versión de GitHub y corre este script)
# Hace: respaldo previo de la base, instala la versión, aplica migraciones, revisa salud
#       y, si algo falla, regresa sola a la versión anterior. Guarda las últimas 3 versiones.
set -euo pipefail
V=${1:-}
[[ "$V" =~ ^v[0-9]+(\.[0-9]+)+$ ]] || { echo "Uso: publicar v1.3"; exit 1; }
BASE=/datos/plataforma
[ -f $BASE/.env ] || { echo "ERROR: no existe $BASE/.env. La primera vez se usa primera_vez.sh (ver LEEME)."; exit 1; }
docker info >/dev/null 2>&1 || { echo "ERROR: tu usuario no puede usar docker (sal y vuelve a entrar)."; exit 1; }
if [ -d "$BASE/versiones/$V" ]; then echo "ERROR: $V ya está en el servidor. Cierra una versión nueva en tu laptop (siguiente número)."; exit 1; fi

exec > >(tee -a "$BASE/publicar_$V.log") 2>&1
echo "=== Publicar $V - $(date '+%Y-%m-%d %H:%M') ==="

# 1. Sacar la versión de la copia del repositorio
mkdir -p "$BASE/versiones/$V"
git --git-dir="$BASE/repo.git" archive "$V" | tar -x -C "$BASE/versiones/$V"
find "$BASE/versiones/$V" \( -name "*.sh" -o -name "Caddyfile" -o -name "*.yml" \) -exec sed -i 's/\r$//' {} +
. "$BASE/versiones/$V/publicacion/servidor/comun.sh"
ANT=$(version_actual)
echo "[1/6] Versión actual: ${ANT:-ninguna} -> nueva: $V"

# 2. Construir (la versión anterior sigue funcionando mientras tanto)
echo "[2/6] Construyendo API y web (5-10 minutos)..."
dc "$V" build api web

# 3. Respaldo previo
dc "$V" up -d sqlserver ollama correo
esperar_sql
echo "[3/6] Respaldo previo de la base..."
PREVIO="antes_${V}_$(date +%Y%m%d_%H%M).bak"
respaldar "$PREVIO"
echo "$PREVIO" > "$VERS/$V/.respaldo_previo"
[ -n "$ANT" ] && echo "$ANT" > "$VERS/$V/.version_anterior"

# 4. Cambiar a la nueva versión (aquí la plataforma deja de responder 1-2 minutos)
echo "[4/6] Arrancando $V (las migraciones se aplican solas)..."
ln -sfn "$VERS/$V" "$BASE/actual"
dc "$V" up -d --remove-orphans

# 5. Revisión de salud
echo "[5/6] Revisando que todo responda (hasta 5 minutos)..."
if salud_ok "$V"; then
  anotar "PUBLICADA $V (antes: ${ANT:-ninguna}; respaldo previo: $PREVIO)"
  echo "[5/6] OK: API, base y web responden con la versión $V."
else
  echo
  echo "!!! $V NO pasó la revisión de salud. Últimos mensajes de la API:"
  dc "$V" logs --tail 40 api || true
  if [ -n "$ANT" ]; then
    echo "!!! Regresando a $ANT..."
    ln -sfn "$VERS/$ANT" "$BASE/actual"
    dc "$ANT" up -d --remove-orphans
    salud_ok "$ANT" && echo "Se regresó a $ANT y responde." || echo "ATENCIÓN: $ANT tampoco responde. Manda captura a Claude."
    echo "Si $V alcanzó a cambiar tablas y $ANT falla, corre: regresar --con-base"
    anotar "FALLÓ $V; se regresó a $ANT"
    rm -rf "${VERS:?}/$V"   # para poder publicarla otra vez corregida
  else
    anotar "FALLÓ $V (primera versión, no hay a cuál regresar)"
  fi
  exit 1
fi

# 6. Limpieza: se guardan las 3 versiones más recientes
echo "[6/6] Limpiando versiones viejas..."
for viejo in $(ls -1t "$VERS" | tail -n +4); do
  [ "$viejo" = "$V" ] && continue
  rm -rf "${VERS:?}/$viejo"
  docker image rm "smn-api:$viejo" "smn-web:$viejo" >/dev/null 2>&1 || true
  echo "  se quitó $viejo"
done
docker image prune -f >/dev/null
bash "$VERS/$V/publicacion/servidor/bajar_modelos.sh" || true
echo
echo "=== Listo: $V publicada en https://$IP ==="
