@echo off
rem Plataforma SMN: alias plataformaia.smn.internal + certificado del servidor.
rem Se corre UNA vez por equipo, con clic derecho - Ejecutar como administrador.
rem El archivo "Certificado plataforma SMN.crt" debe estar en la misma carpeta.
setlocal
set IP=172.31.104.4
set NOMBRE=plataformaia.smn.internal
set HOSTS=%WINDIR%\System32\drivers\etc\hosts
set CRT=%~dp0Certificado plataforma SMN.crt

net session >nul 2>&1
if errorlevel 1 (
  echo ERROR: abre este archivo con clic derecho y "Ejecutar como administrador".
  pause
  exit /b 1
)
if not exist "%CRT%" (
  echo ERROR: no encuentro el certificado junto a este archivo:
  echo %CRT%
  pause
  exit /b 1
)

findstr /i /c:"%NOMBRE%" "%HOSTS%" >nul
if errorlevel 1 (
  >>"%HOSTS%" echo.
  >>"%HOSTS%" echo %IP% %NOMBRE%
  echo [1/3] Alias agregado al archivo hosts.
) else (
  echo [1/3] El alias ya estaba en el archivo hosts.
)

ipconfig /flushdns >nul
echo [2/3] Cache de DNS limpia.

certutil -addstore -f Root "%CRT%" >nul
if errorlevel 1 (
  echo ERROR: no se pudo instalar el certificado. Usa la forma manual de la hoja.
) else (
  echo [3/3] Certificado instalado en Entidades de certificacion raiz de confianza.
)

echo.
ping -4 -n 1 %NOMBRE% | findstr /c:"%IP%" >nul
if errorlevel 1 (
  echo REVISA: %NOMBRE% no apunta a %IP%. Abre el hosts con Bloc de notas y revisa la ultima linea.
) else (
  echo OK: %NOMBRE% apunta a %IP%.
)
echo.
echo Cierra TODAS las ventanas de Chrome y Edge y entra a https://%NOMBRE%
pause
