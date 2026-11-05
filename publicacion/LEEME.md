# Publicación: de tu equipo al servidor

Se programa y se prueba en tu equipo. Al servidor SMNIASRV (https://172.31.104.4) solo llega una **versión cerrada**. El plan completo está en https://claude.ai/artifact/Dgcc8xDXyc3zvHLTAqhgVM

| Script | Dónde corre | Para qué |
|---|---|---|
| `preparar_git.ps1` | Tu equipo, una vez | Inicia Git y guarda el estado actual |
| `probar.ps1` | Tu equipo | Pruebas de la API y compilación de la web |
| `cerrar_version.ps1` | Tu equipo | Etiqueta la versión, escribe `CAMBIOS.md` y arma el paquete |
| `copiar_produccion.ps1` | Tu equipo | Trae el respaldo del servidor a tu base local |
| `servidor/primera_vez.sh` | Servidor, una vez | Prepara todo, restaura tu base y publica la v1.0 |
| `servidor/publicar.sh` | Servidor | Publica una versión, con respaldo previo y regreso automático |
| `servidor/regresar.sh` | Servidor | Regresa a la versión anterior |
| `servidor/respaldo_diario.sh` | Servidor (solo, 2:30 am) | Respaldo diario de la base |
| `servidor/asegurar_servidor.sh` | Servidor, una vez | Tu usuario con llave SSH y el firewall |

Los comandos de tu equipo se corren en **PowerShell, dentro de la carpeta del proyecto** (donde está `docker-compose.yml`). El equipo tiene que estar conectado a la VPN para llegar al servidor.

---

## Una sola vez

### A. Git

```
powershell -ExecutionPolicy Bypass -File publicacion\preparar_git.ps1
```

Debe terminar con `Listo: N archivos guardados en Git`. Si dice que falta Git: `winget install --id Git.Git -e`, cierra y abre PowerShell y repite el comando. Si dice **ALTO** por archivos de más de 20 MB, mándame la lista.

### B. Primera publicación (v1.0)

1. Pruebas:
   ```
   powershell -ExecutionPolicy Bypass -File publicacion\probar.ps1
   ```
   Debe decir `OK: pruebas y web sin fallas`.
2. Cerrar la versión:
   ```
   powershell -ExecutionPolicy Bypass -File publicacion\cerrar_version.ps1 -Version v1.0 -Nota "Primera versión en el servidor"
   ```
3. Respaldo de tu base local. En **SSMS**, conectado a `localhost,1433`:
   ```sql
   BACKUP DATABASE smn_td TO DISK = '/var/opt/mssql/data/smn_td.bak' WITH COPY_ONLY, INIT;
   ```
   Luego en PowerShell:
   ```
   docker compose cp sqlserver:/var/opt/mssql/data/smn_td.bak salida\v1.0\smn_td.bak
   Copy-Item .env salida\v1.0\env_local
   ```
4. Subir todo al servidor (pide la contraseña):
   ```
   scp salida\v1.0\plataforma-v1.0.tgz salida\v1.0\publicar.sh salida\v1.0\primera_vez.sh salida\v1.0\smn_td.bak salida\v1.0\env_local smnnatural@172.31.104.4:
   ```
5. En el servidor (`ssh smnnatural@172.31.104.4`):
   ```
   sed -i 's/\r$//' ~/publicar.sh ~/primera_vez.sh && bash ~/primera_vez.sh ~/plataforma-v1.0.tgz
   ```
   Tarda de 15 a 20 minutos. Debe terminar con `Listo: v1.0 publicada en https://172.31.104.4`.
6. Borrar las copias sensibles que subiste (ya están dentro del servidor donde deben estar):
   ```
   rm ~/env_local ~/smn_td.bak
   ```
7. Modelos de IA. Pon el mismo modelo de texto que tienes en Configuración → Modelo de Ollama; si no tienes uno, `qwen2.5:14b` cabe en la T4 y escribe bien en español:
   ```
   docker exec smn-ollama-1 ollama pull bge-m3 && docker exec smn-ollama-1 ollama pull qwen2.5:14b
   ```
8. Entra a **https://172.31.104.4**. La primera vez el navegador avisa que la conexión no es privada: **Configuración avanzada → Continuar**. Para quitar el aviso, ve a «Certificado» en Comandos útiles.
9. En **Administración → Sistema** debe decir Entorno `produccion` y Versión `v1.0`.

### C. Tu usuario y el firewall

En tu equipo:

```
ssh-keygen -t ed25519
scp "$env:USERPROFILE\.ssh\id_ed25519.pub" publicacion\servidor\asegurar_servidor.sh smnnatural@172.31.104.4:
```

Con `ssh-keygen` da Enter a todo. Luego, en el servidor:

```
sed -i 's/\r$//' ~/asegurar_servidor.sh && bash ~/asegurar_servidor.sh diego ~/id_ed25519.pub
```

**Sin cerrar esa ventana**, abre otra y prueba `ssh diego@172.31.104.4`. Debe entrar sin pedir contraseña. Desde entonces, entra con `diego`.

---

## Cada cambio (el flujo de siempre)

1. Programamos en tu equipo. Cuando algo queda listo, guárdalo en Git:
   ```
   git add -A ; git commit -m "Qué cambió"
   ```
2. Pruebas: `powershell -ExecutionPolicy Bypass -File publicacion\probar.ps1` y debe decir `OK`.
3. Si el cambio es importante, prueba con datos reales: `powershell -ExecutionPolicy Bypass -File publicacion\copiar_produccion.ps1` (**reemplaza** tu base local).
4. Visto bueno del área, si el cambio cambia cómo trabajan.
5. Cerrar la versión:
   ```
   powershell -ExecutionPolicy Bypass -File publicacion\cerrar_version.ps1 -Version v1.1 -Nota "Compras ya puede ..."
   ```
   Al final te imprime los 2 comandos exactos para el paso 6.
6. Publicar, fuera del horario de uso: el `scp` y el `bash ~/publicar.sh ...` que imprimió el paso 5. Si algo falla, regresa solo a la versión anterior.
7. Revisar: entra, abre lo que cambió y revisa que **Administración → Sistema** muestre la versión nueva. Avisa a las áreas con lo que dice `CAMBIOS.md`.

**Números de versión:** v1.1, v1.2… por publicación; v1.2.1 para una corrección urgente sobre la v1.2.

## Si algo sale mal

| Qué pasó | Comando en el servidor |
|---|---|
| Error en pantallas, sin cambios de tablas | `bash /datos/plataforma/actual/publicacion/servidor/regresar.sh` |
| Error después de una migración | `bash /datos/plataforma/actual/publicacion/servidor/regresar.sh --con-base` (se pierde lo capturado desde la publicación) |

Los dos piden escribir `SI` antes de hacer algo.

## Comandos útiles

- **Historial de publicaciones:** `cat /datos/plataforma/historial.log`
- **Qué está corriendo:** `docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"`
- **Errores de la API:** `docker logs --tail 100 smn-api-1`
- **Respaldos y reinicios:** `tail -20 /datos/respaldos/respaldo.log`
- **Copia del respaldo fuera del servidor** (mínimo una vez por semana): `copiar_produccion.ps1` la deja en `salida\produccion`. Si solo quieres la copia sin restaurar: `scp "smnnatural@172.31.104.4:/datos/respaldos/smn_td_*.bak" salida\`
- **Correos de prueba (Mailpit):** `ssh -L 8025:localhost:8025 smnnatural@172.31.104.4`, déjalo abierto y abre http://localhost:8025
- **Contraseña de solo lectura** (SSMS a `172.31.104.4,1433`): en el servidor, `cat ~/clave_smn_lectura.txt`. No la pegues en el chat.
- **Certificado** (para quitar el aviso del navegador): en el servidor corre `sudo cp /datos/caddy/data/caddy/pki/authorities/local/root.crt ~/smn-servidor.crt && sudo chown $USER ~/smn-servidor.crt`. Luego, en tu equipo, `scp smnnatural@172.31.104.4:smn-servidor.crt salida\`. Abre el archivo → Instalar certificado → Usuario actual → Colocar en **Entidades de certificación raíz de confianza** → Finalizar. Cierra y abre el navegador.
