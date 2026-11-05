# Paso 3 del flujo: pone en tu base LOCAL un respaldo del servidor que ya trajiste (USB u OneDrive).
# Tu base local se REEMPLAZA completa. Cómo bajar el respaldo desde la PC de la empresa: publicacion\LEEME.md
# Uso:  powershell -ExecutionPolicy Bypass -File publicacion\copiar_produccion.ps1 -Archivo "D:\smn_td_20261105.bak"
param([Parameter(Mandatory = $true)][string]$Archivo)
$ErrorActionPreference = "Continue"  # los programas (git, docker, ssh) escriben avisos en stderr; los errores se revisan a mano
Set-Location (Join-Path $PSScriptRoot "..")
function LeerEnv($clave) { (Get-Content .env | Where-Object { $_ -match "^$clave=" } | Select-Object -First 1) -replace "^$clave=", "" }
$sa = LeerEnv "MSSQL_SA_PASSWORD"; $bd = LeerEnv "BD_NOMBRE"; if (-not $bd) { $bd = "smn_td" }

Write-Host "Esto REEMPLAZA tu base local ($bd) con la copia del servidor. Lo que capturaste solo en local se pierde." -ForegroundColor Yellow
if ((Read-Host "Escribe SI para continuar") -ne "SI") { Write-Host "Cancelado."; exit 0 }

if (-not (Test-Path $Archivo)) { Write-Host "No encuentro $Archivo" -ForegroundColor Red; exit 1 }
$local = (Resolve-Path $Archivo).Path
Write-Host "1/3 Restaurando en tu SQL Server local..."
docker compose up -d sqlserver | Out-Null
docker compose stop api | Out-Null
docker compose cp "$local" sqlserver:/var/opt/mssql/data/copia_produccion.bak
docker compose exec -T -u 0 sqlserver chown mssql /var/opt/mssql/data/copia_produccion.bak
docker compose exec -T sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $sa -C -b -Q "IF DB_ID('$bd') IS NOT NULL ALTER DATABASE [$bd] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; RESTORE DATABASE [$bd] FROM DISK='/var/opt/mssql/data/copia_produccion.bak' WITH REPLACE; ALTER DATABASE [$bd] SET MULTI_USER;"
if ($LASTEXITCODE -ne 0) { Write-Host "Falló la restauración." -ForegroundColor Red; exit 1 }

Write-Host "2/3 Ajustando para desarrollo (correo, Ollama y dirección de tu equipo; tareas programadas apagadas)..."
docker compose exec -T sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $sa -C -b -d $bd -Q "DELETE FROM nucleo.configuracion WHERE clave IN ('web_url','smtp_servidor','smtp_puerto','smtp_usuario','smtp_contrasena','smtp_tls','ollama_url');"
$envTxt = Get-Content .env
if ($envTxt -match '^PROGRAMADOR_ACTIVO=') { $envTxt = $envTxt -replace '^PROGRAMADOR_ACTIVO=.*', 'PROGRAMADOR_ACTIVO=false' } else { $envTxt += 'PROGRAMADOR_ACTIVO=false' }
[IO.File]::WriteAllLines((Join-Path (Get-Location) ".env"), $envTxt, (New-Object Text.UTF8Encoding($false)))

Write-Host "3/3 Arrancando la API..."
docker compose up -d | Out-Null
Write-Host ""
Write-Host "Listo: tu base local es copia de producción ($((Split-Path $local -Leaf)))." -ForegroundColor Green
Write-Host "En local NO corren tareas programadas (radar de precios, noticias, ETL)."
