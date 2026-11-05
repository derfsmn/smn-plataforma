# Solo una vez: inicia Git en la carpeta del proyecto y guarda el estado actual.
# Uso (PowerShell, en la carpeta del proyecto):  powershell -ExecutionPolicy Bypass -File publicacion\preparar_git.ps1
$ErrorActionPreference = "Continue"  # los programas (git, docker, ssh) escriben avisos en stderr; los errores se revisan a mano
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "Falta Git. Instálalo con:  winget install --id Git.Git -e   , cierra y abre PowerShell, y repite." -ForegroundColor Yellow; exit 1
}

# Lo que NUNCA se guarda en Git (secretos, datos, cosas que se regeneran)
$ignorar = @"
# --- SMN: no se guarda en Git ---
.env
env_local
**/node_modules/
**/.next/
**/__pycache__/
*.pyc
*.tsbuildinfo
api/.pruebas-archivos/
salida/
*.bak
*.log
docs/sistemas/**/*.csv
sistemas/*.csv
docs/datos/*.zip
# copia vieja que quedó en una ruta equivocada (29 oct); el código bueno está en api/ y web/
plataforma/
"@
if (-not (Test-Path .gitignore) -or -not (Select-String -Path .gitignore -Pattern "SMN: no se guarda" -Quiet)) {
  Add-Content -Path .gitignore -Value $ignorar -Encoding ASCII
}
# Los scripts del servidor siempre con saltos de línea de Linux
$attr = "*.sh text eol=lf`nCaddyfile text eol=lf`n*.yml text eol=lf`n"
if (-not (Test-Path .gitattributes)) { [IO.File]::WriteAllText((Join-Path (Get-Location) ".gitattributes"), $attr) }

if (-not (Test-Path .git)) { git init -b main | Out-Null; Write-Host "Git iniciado." }
if (-not (git config user.name)) { git config user.name "Diego Rodriguez" }
if (-not (git config user.email)) { git config user.email "diegoe.rodriguez.ferreira@gmail.com" }

git config core.quotepath false
git add -A
if ($LASTEXITCODE -ne 0) { Write-Host "Falló git add." -ForegroundColor Red; exit 1 }
# Candado: nada mayor a 20 MB (suele ser un archivo de datos que no debe ir en Git)
$grandes = git diff --cached --name-only | Where-Object { (Test-Path $_) -and ((Get-Item $_).Length -gt 20MB) }
if ($grandes) {
  Write-Host "ALTO: estos archivos pesan más de 20 MB. Agrégalos a .gitignore o muévelos, y repite:" -ForegroundColor Red
  $grandes | ForEach-Object { Write-Host "  $_" }
  git reset -q; exit 1
}
$n = (git diff --cached --name-only | Measure-Object).Count
if ($n -eq 0) { Write-Host "No hay nada nuevo que guardar."; exit 0 }
git commit -q -m "Estado inicial antes de la v1.0"
if ($LASTEXITCODE -ne 0) { Write-Host "Falló el commit." -ForegroundColor Red; exit 1 }
Write-Host "Listo: $n archivos guardados en Git." -ForegroundColor Green
git log --oneline -1
