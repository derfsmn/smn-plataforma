# Paso 3 del flujo: trae el respaldo más reciente del servidor y lo pone en tu base LOCAL.
# Tu base local se REEMPLAZA completa. También sirve como copia del respaldo fuera del servidor.
# Uso:  powershell -ExecutionPolicy Bypass -File publicacion\copiar_produccion.ps1
$ErrorActionPreference = "Continue"  # los programas (git, docker, ssh) escriben avisos en stderr; los errores se revisan a mano
Set-Location (Join-Path $PSScriptRoot "..")
$servidor = "smnnatural@172.31.104.4"
function LeerEnv($clave) { (Get-Content .env | Where-Object { $_ -match "^$clave=" } | Select-Object -First 1) -replace "^$clave=", "" }
$sa = LeerEnv "MSSQL_SA_PASSWORD"; $bd = LeerEnv "BD_NOMBRE"; if (-not $bd) { $bd = "smn_td" }

Write-Host "Esto REEMPLAZA tu base local ($bd) con la copia del servidor. Lo que capturaste solo en local se pierde." -ForegroundColor Yellow
if ((Read-Host "Escribe SI para continuar") -ne "SI") { Write-Host "Cancelado."; exit 0 }

Write-Host "1/5 Buscando el respaldo más reciente (pide la contraseña del servidor)..."
$archivo = "$(ssh $servidor "ls -1t /datos/respaldos/smn_td_2*.bak /datos/respaldos/antes_*.bak 2>/dev/null | head -1")".Trim()
if (-not $archivo) { Write-Host "No hay respaldos en el servidor todavía." -ForegroundColor Red; exit 1 }
$dir = Join-Path (Get-Location) "salida\produccion"; New-Item -ItemType Directory -Force -Path $dir | Out-Null
$local = Join-Path $dir (Split-Path $archivo -Leaf)
Write-Host "2/5 Bajando $archivo (pide la contraseña otra vez)..."
scp "${servidor}:$archivo" "$local"
if ($LASTEXITCODE -ne 0) { Write-Host "No se pudo bajar el respaldo." -ForegroundColor Red; exit 1 }

Write-Host "3/5 Restaurando en tu SQL Server local..."
docker compose up -d sqlserver | Out-Null
docker compose stop api | Out-Null
docker compose cp "$local" sqlserver:/var/opt/mssql/data/copia_produccion.bak
docker compose exec -T -u 0 sqlserver chown mssql /var/opt/mssql/data/copia_produccion.bak
docker compose exec -T sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $sa -C -b -Q "IF DB_ID('$bd') IS NOT NULL ALTER DATABASE [$bd] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; RESTORE DATABASE [$bd] FROM DISK='/var/opt/mssql/data/copia_produccion.bak' WITH REPLACE; ALTER DATABASE [$bd] SET MULTI_USER;"
if ($LASTEXITCODE -ne 0) { Write-Host "Falló la restauración." -ForegroundColor Red; exit 1 }

Write-Host "4/5 Ajustando para desarrollo (correo, Ollama y dirección de tu equipo; tareas programadas apagadas)..."
docker compose exec -T sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $sa -C -b -d $bd -Q "DELETE FROM nucleo.configuracion WHERE clave IN ('web_url','smtp_servidor','smtp_puerto','smtp_usuario','smtp_contrasena','smtp_tls','ollama_url');"
$envTxt = Get-Content .env
if ($envTxt -match '^PROGRAMADOR_ACTIVO=') { $envTxt = $envTxt -replace '^PROGRAMADOR_ACTIVO=.*', 'PROGRAMADOR_ACTIVO=false' } else { $envTxt += 'PROGRAMADOR_ACTIVO=false' }
[IO.File]::WriteAllLines((Join-Path (Get-Location) ".env"), $envTxt, (New-Object Text.UTF8Encoding($false)))

Write-Host "5/5 Arrancando la API..."
docker compose up -d | Out-Null
Write-Host ""
Write-Host "Listo: tu base local es copia de producción ($((Split-Path $archivo -Leaf)))." -ForegroundColor Green
Write-Host "En local NO corren tareas programadas (radar de precios, noticias, ETL). La copia queda en $local"
