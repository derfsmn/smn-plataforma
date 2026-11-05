#!/usr/bin/env bash
# Solo una vez: prepara /datos/plataforma, restaura tu base y publica la primera versión.
# Antes: la llave de GitHub, la copia del repositorio en /datos/plataforma/repo.git y en tu carpeta (~)
#        smn_td.bak y env_local (copia del .env de tu laptop). Ver publicacion/LEEME.md
# Uso:  bash ~/primera_vez.sh v1.0
set -euo pipefail
V=${1:-}
BASE=/datos/plataforma
[[ "$V" =~ ^v[0-9]+(\.[0-9]+)+$ ]] || { echo "Uso: bash primera_vez.sh v1.0"; exit 1; }
[ -d $BASE/repo.git ] || { echo "ERROR: falta la copia del repositorio ($BASE/repo.git). Ver LEEME."; exit 1; }
for f in ~/smn_td.bak ~/env_local; do [ -f "$f" ] || { echo "ERROR: falta $f. No se hizo nada."; exit 1; }; done
[ -f $BASE/.env ] && { echo "ERROR: el servidor ya está preparado ($BASE/.env existe). Para publicar usa publicar.sh."; exit 1; }
docker info >/dev/null 2>&1 || { echo "ERROR: tu usuario no puede usar docker (sal y vuelve a entrar)."; exit 1; }
mountpoint -q /datos || { echo "ERROR: /datos no está montado."; exit 1; }
exec > >(tee -a ~/primera_vez.log) 2>&1
echo "=== Primera vez - $(date '+%Y-%m-%d %H:%M') ==="

# 1. Carpetas
sudo mkdir -p /datos/sqlserver /datos/respaldos /datos/ollama /datos/archivos /datos/caddy/data /datos/caddy/config $BASE/versiones
sudo chown -R 10001:0 /datos/sqlserver /datos/respaldos      # usuario interno de SQL Server
sudo chmod 755 /datos/respaldos
sudo chown "$USER":"$USER" $BASE $BASE/versiones
sudo chgrp -R docker $BASE && sudo chmod -R g+rwX $BASE

# 2. .env del servidor a partir del de tu equipo
#    MSSQL_SA_PASSWORD y CLAVE_CIFRADO se quedan IGUAL: con ellas se descifran los secretos de Configuración.
tr -d '\r' < ~/env_local > $BASE/.env
chmod 600 $BASE/.env
TMP=$(mktemp -d); git --git-dir=$BASE/repo.git archive "$V" publicacion/servidor | tar -x -C "$TMP"; find "$TMP" -type f -exec sed -i 's/\r$//' {} +
. "$TMP/publicacion/servidor/comun.sh"
[ -n "$(leer_env MSSQL_SA_PASSWORD)" ] || { echo "ERROR: env_local no trae MSSQL_SA_PASSWORD."; rm -f $BASE/.env; exit 1; }
poner_env API_ENTORNO produccion
poner_env API_ORIGENES_PERMITIDOS "https://$IP"
poner_env WEB_URL "https://$IP"
poner_env NEXT_PUBLIC_API_URL "https://$IP"
poner_env OLLAMA_URL "http://ollama:11434"
poner_env SMTP_SERVIDOR correo
poner_env SMTP_PUERTO 1025
poner_env PROGRAMADOR_ACTIVO true
echo "[env] Listo $BASE/.env"

# 3. SQL Server Express y tu base
VERSION=inicial docker compose --env-file "$ENVF" -f "$TMP/publicacion/servidor/docker-compose.servidor.yml" up -d sqlserver
esperar_sql
sqlsa -Q "SELECT @@VERSION" | grep -i -E "express|developer|standard" | head -1 || true
if [ "$(sqlsa -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name='$(bd)'" | tr -d '[:space:]')" != "0" ]; then
  echo "ERROR: la base $(bd) ya existe en el servidor. No se restaura encima."; exit 1
fi
sudo cp ~/smn_td.bak /datos/respaldos/inicial_$(date +%Y%m%d).bak
sudo chown 10001:0 /datos/respaldos/inicial_$(date +%Y%m%d).bak
echo "[base] Restaurando (unos minutos)..."
sqlsa -Q "RESTORE DATABASE [$(bd)] FROM DISK='/respaldos/inicial_$(date +%Y%m%d).bak' WITH REPLACE, STATS=25"

# Ajustes de pantalla que dependen del equipo: se borran para que mande el .env del servidor
sqlsa -d "$(bd)" -Q "DELETE FROM nucleo.configuracion WHERE clave IN ('web_url','smtp_servidor','smtp_puerto','smtp_usuario','smtp_contrasena','smtp_tls','ollama_url'); SELECT @@ROWCOUNT AS ajustes_de_tu_equipo_quitados;"

# 4. Usuarios de la base: smn_app (la plataforma, dueña solo de su base) y smn_lectura (solo lectura)
CLAVE_APP="Smn-$(openssl rand -hex 16)-A1"
CLAVE_LEC="Lec-$(openssl rand -hex 12)-B2"
sqlsa -Q "CREATE LOGIN smn_app WITH PASSWORD='$CLAVE_APP', DEFAULT_DATABASE=[$(bd)]; CREATE LOGIN smn_lectura WITH PASSWORD='$CLAVE_LEC', DEFAULT_DATABASE=[$(bd)];"
sqlsa -d "$(bd)" -Q "CREATE USER smn_app FOR LOGIN smn_app; ALTER ROLE db_owner ADD MEMBER smn_app; CREATE USER smn_lectura FOR LOGIN smn_lectura; ALTER ROLE db_datareader ADD MEMBER smn_lectura;"
poner_env BD_USUARIO smn_app
poner_env BD_CONTRASENA "$CLAVE_APP"
echo "smn_lectura / $CLAVE_LEC" > ~/clave_smn_lectura.txt; chmod 600 ~/clave_smn_lectura.txt
echo "[base] La plataforma usa smn_app (no sa). Contraseña de smn_lectura en ~/clave_smn_lectura.txt"

# 5. Respaldo diario 2:30 am
echo "30 2 * * * root bash $BASE/actual/publicacion/servidor/respaldo_diario.sh" | sudo tee /etc/cron.d/smn-respaldo >/dev/null
sudo chmod 644 /etc/cron.d/smn-respaldo
echo "[respaldo] Programado diario a las 2:30 am en /datos/respaldos"

# 6. Comandos «publicar» y «regresar»
sudo install -m 755 "$TMP/publicacion/servidor/publicar_comando.sh" /usr/local/bin/publicar
printf '#!/usr/bin/env bash\nexec bash /datos/plataforma/actual/publicacion/servidor/regresar.sh "$@"\n' | sudo tee /usr/local/bin/regresar >/dev/null
sudo chmod 755 /usr/local/bin/regresar
rm -rf "$TMP"
echo "[comandos] Ya puedes usar: publicar vX.Y  y  regresar"

# 7. Publicar la primera versión
publicar "$V"
