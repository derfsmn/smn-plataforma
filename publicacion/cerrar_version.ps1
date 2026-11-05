# Paso 5 del flujo: cierra una versión y la sube a GitHub, de donde la toma el servidor.
# Uso:  powershell -ExecutionPolicy Bypass -File publicacion\cerrar_version.ps1 -Version v1.1 -Nota "Qué cambió, en palabras de usuario"
param(
  [Parameter(Mandatory = $true)][string]$Version,
  [Parameter(Mandatory = $true)][string]$Nota
)
$ErrorActionPreference = "Continue"  # los programas (git, docker, ssh) escriben avisos en stderr; los errores se revisan a mano
Set-Location (Join-Path $PSScriptRoot "..")
if ($Version -notmatch '^v\d+(\.\d+)+$') { Write-Host "La versión debe ser como v1.0, v1.1 o v1.2.1" -ForegroundColor Red; exit 1 }
if (git status --porcelain) {
  Write-Host "Hay cambios sin guardar en Git. Guárdalos primero:" -ForegroundColor Red
  Write-Host '  git add -A ; git commit -m "Qué cambió"'
  git status --short; exit 1
}
if (git tag --list $Version) { Write-Host "$Version ya existe. Usa el siguiente número." -ForegroundColor Red; exit 1 }

$anterior = git describe --tags --abbrev=0 2>$null
if ($LASTEXITCODE -ne 0) { $anterior = $null }
if ($anterior) {
  $commits = git log --pretty="- %s" "$anterior..HEAD"
  $migr = git diff --name-only --diff-filter=A $anterior HEAD -- api/migraciones/versions
} else {
  $commits = @("- Primera versión publicada")
  $migr = @()
}
$migrTxt = if ($migr) { ($migr | ForEach-Object { "- " + (Split-Path $_ -Leaf) }) -join "`n" } else { "- Ninguna" }
$fecha = Get-Date -Format "yyyy-MM-dd"
$entrada = "## $Version · $fecha`n`n$Nota`n`n**Cambios guardados:**`n$($commits -join "`n")`n`n**Migraciones nuevas:**`n$migrTxt`n`n"
$ruta = Join-Path (Get-Location) "CAMBIOS.md"
$previo = if (Test-Path $ruta) { [IO.File]::ReadAllText($ruta) -replace '^# Registro de cambios\s*', '' } else { "" }
[IO.File]::WriteAllText($ruta, "# Registro de cambios`n`n" + $entrada + $previo, (New-Object Text.UTF8Encoding($false)))

git add CAMBIOS.md
git commit -q -m "Versión $Version"
git tag -a $Version -m $Nota
if ($LASTEXITCODE -ne 0) { Write-Host "No se pudo etiquetar la versión." -ForegroundColor Red; exit 1 }

Write-Host "Subiendo a GitHub..."
git push -q origin HEAD
git push -q origin $Version
if ($LASTEXITCODE -ne 0) { Write-Host "No se pudo subir a GitHub. Revisa tu internet y vuelve a correr:  git push origin HEAD ; git push origin $Version" -ForegroundColor Red; exit 1 }
Write-Host ""
Write-Host "Listo: $Version cerrada y en GitHub." -ForegroundColor Green
Write-Host "Para publicarla, desde la PC de la empresa entra al servidor (ssh smnnatural@172.31.104.4) y escribe:"
Write-Host "  publicar $Version" -ForegroundColor Cyan
