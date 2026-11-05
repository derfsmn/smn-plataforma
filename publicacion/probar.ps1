# Paso 2 del flujo: pruebas automáticas de la API y compilación de la web, con el código actual.
# Uso:  powershell -ExecutionPolicy Bypass -File publicacion\probar.ps1
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
Write-Host "1/3 Reconstruyendo la API con tu código actual..."
docker compose up -d --build api | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "FALLÓ: la API no se pudo construir." -ForegroundColor Red; exit 1 }
Write-Host "2/3 Pruebas de la API (usan una base aparte, smn_td_pruebas; tus datos no se tocan)..."
docker compose exec -T api python -m pytest -q -p no:cacheprovider
$pruebas = $LASTEXITCODE
Write-Host "3/3 Compilando la web..."
docker compose build web
$web = $LASTEXITCODE
docker compose up -d | Out-Null
Write-Host ""
if ($pruebas -eq 0 -and $web -eq 0) { Write-Host "OK: pruebas y web sin fallas. Puedes cerrar versión." -ForegroundColor Green; exit 0 }
if ($pruebas -ne 0) { Write-Host "FALLARON pruebas de la API (arriba dice cuáles)." -ForegroundColor Red }
if ($web -ne 0) { Write-Host "FALLÓ la compilación de la web (arriba dice dónde)." -ForegroundColor Red }
exit 1
