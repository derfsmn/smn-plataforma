# Funciones compartidas por publicar.sh, regresar.sh, primera_vez.sh y respaldo_diario.sh
BASE=/datos/plataforma
ENVF=$BASE/.env
VERS=$BASE/versiones
IP=172.31.104.4
HIST=$BASE/historial.log
REPO=$BASE/repo.git                 # copia del repositorio de GitHub (solo lectura)
export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/smn_github -o IdentitiesOnly=yes"
gitr(){ git --git-dir="$REPO" "$@"; }
traer_github(){ gitr fetch -q --prune --tags origin '+refs/heads/*:refs/heads/*'; }

leer_env(){ grep -m1 "^$1=" "$ENVF" 2>/dev/null | cut -d= -f2- | tr -d '\r' || true; }
bd(){ local b; b=$(leer_env BD_NOMBRE); echo "${b:-smn_td}"; }
poner_env(){ if grep -q "^$1=" "$ENVF"; then sed -i "s|^$1=.*|$1=$2|" "$ENVF"; else echo "$1=$2" >> "$ENVF"; fi; }

# docker compose de una versión:  dc v1.2 up -d
dc(){ local v=$1; shift; VERSION=$v docker compose --env-file "$ENVF" -f "$VERS/$v/publicacion/servidor/docker-compose.servidor.yml" "$@"; }

# sqlcmd como sa dentro del contenedor de SQL Server
sqlsa(){ docker exec -i smn-sqlserver-1 /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$(leer_env MSSQL_SA_PASSWORD)" -C -b "$@"; }

version_actual(){ [ -L "$BASE/actual" ] && basename "$(readlink -f "$BASE/actual")" || echo ""; }

esperar_sql(){
  for _ in $(seq 1 60); do sqlsa -Q "SELECT 1" >/dev/null 2>&1 && return 0; sleep 3; done
  echo "ERROR: SQL Server no respondió en 3 minutos."; return 1
}

# Revisión de salud: API y base OK, con la versión esperada, y la web contesta
salud_ok(){
  local v=$1 r
  for _ in $(seq 1 60); do
    r=$(curl -sk -m 5 "https://$IP/api/salud" || true)
    if echo "$r" | grep -q '"api":"ok"' && echo "$r" | grep -q '"base_de_datos":"ok"' && echo "$r" | grep -q "\"version\":\"$v\""; then
      [ "$(curl -sk -m 10 -o /dev/null -w '%{http_code}' "https://$IP/login")" = "200" ] && return 0
    fi
    sleep 5
  done
  echo "Última respuesta de /api/salud: ${r:-sin respuesta}"; return 1
}

respaldar(){ # nombre_de_archivo (sin ruta)
  sqlsa -Q "BACKUP DATABASE [$(bd)] TO DISK='/respaldos/$1' WITH INIT, CHECKSUM" >/dev/null
  sudo chmod 644 "/datos/respaldos/$1"
  echo "[respaldo] /datos/respaldos/$1 ($(du -h "/datos/respaldos/$1" | cut -f1))"
}

anotar(){ echo "$(date '+%Y-%m-%d %H:%M') $*" >> "$HIST"; }
