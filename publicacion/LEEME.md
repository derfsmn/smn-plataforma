# Publicación: de tu laptop al servidor

Son 3 equipos y cada uno tiene su papel:

| Equipo | Qué hace | Qué corre ahí |
|---|---|---|
| **Laptop (taller)** | Programar y probar. Tiene el código, Docker y Git | Los `.ps1` de esta carpeta, `git` |
| **PC de la empresa** | Puente: es la única con VPN al servidor | Solo `ssh` y `scp`. Nada de scripts |
| **Servidor SMNIASRV** | La plataforma «de verdad»: https://172.31.104.4 | `publicar`, `regresar` |

El **código** viaja laptop → GitHub (privado, `derfsmn/smn-plataforma`) → servidor. La PC de la empresa no toca el código.
Los **datos** solo viajan por la PC de la empresa (USB u OneDrive): una vez al inicio, y de vez en cuando una copia del servidor para probar en la laptop.

Plan completo: https://claude.ai/artifact/Dgcc8xDXyc3zvHLTAqhgVM

---

## Cada cambio (el flujo de siempre)

| # | Dónde | Qué |
|---|---|---|
| 1 | Laptop | Programamos. Cuando algo queda listo: `git add -A ; git commit -m "Qué cambió"` |
| 2 | Laptop | `powershell -ExecutionPolicy Bypass -File publicacion\probar.ps1` y debe decir **OK** |
| 3 | Laptop | Si es importante, pruébalo con datos reales (ver «Copia del servidor a la laptop») |
| 4 | — | Visto bueno del área, si cambia cómo trabajan |
| 5 | Laptop | `powershell -ExecutionPolicy Bypass -File publicacion\cerrar_version.ps1 -Version v1.1 -Nota "Compras ya puede ..."`: etiqueta, escribe `CAMBIOS.md` y sube a GitHub |
| 6 | PC empresa | Fuera del horario de uso: `ssh smnnatural@172.31.104.4` y luego `publicar v1.1` |
| 7 | PC empresa | Entra a https://172.31.104.4, revisa lo que cambió y que **Administración → Sistema** diga la versión nueva. Avisa a las áreas con `CAMBIOS.md` |

`publicar` hace respaldo previo, construye, aplica migraciones, revisa que todo responda y, si algo falla, **regresa solo** a la versión anterior. Tarda de 10 a 15 minutos.

**Números de versión:** v1.1, v1.2… por publicación; v1.2.1 para una corrección urgente sobre la v1.2.

### Si algo sale mal (en el servidor)

| Qué pasó | Comando |
|---|---|
| Error en pantallas, sin cambios de tablas | `regresar` |
| Error después de una migración | `regresar --con-base` (se pierde lo capturado desde la publicación) |

Los dos piden escribir `SI` antes de hacer algo.

---

## Una sola vez: la primera publicación (v1.0)

### 1. Laptop: subir a GitHub

```
git remote add origin https://github.com/derfsmn/smn-plataforma.git
git push -u origin master
```

### 2. Servidor: llave de GitHub de solo lectura

Desde la PC de la empresa, entra con `ssh smnnatural@172.31.104.4` y pega:

```
mkdir -p ~/.ssh && ssh-keygen -t ed25519 -f ~/.ssh/smn_github -N "" -C SMNIASRV && ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null && cat ~/.ssh/smn_github.pub
```

Copia el renglón que empieza con `ssh-ed25519`. En GitHub entra a **derfsmn/smn-plataforma → Settings → Deploy keys → Add deploy key**. En Title pon `SMNIASRV`, pega la llave y **no** marques «Allow write access». Luego, en el servidor:

```
sudo mkdir -p /datos/plataforma && sudo chown $USER:$USER /datos/plataforma && GIT_SSH_COMMAND="ssh -i ~/.ssh/smn_github -o IdentitiesOnly=yes" git clone --bare git@github.com:derfsmn/smn-plataforma.git /datos/plataforma/repo.git
```

Debe decir `done.` al final. Si dice *Permission denied (publickey)*, la llave no quedó en Deploy keys.

### 3. Laptop: cerrar la v1.0 y preparar los datos

```
git add -A ; git commit -m "Publicación con GitHub"
powershell -ExecutionPolicy Bypass -File publicacion\probar.ps1
powershell -ExecutionPolicy Bypass -File publicacion\cerrar_version.ps1 -Version v1.0 -Nota "Primera versión en el servidor"
```

Respaldo de tu base. En **SSMS**, conectado a `localhost,1433`:

```sql
BACKUP DATABASE smn_td TO DISK = '/var/opt/mssql/data/smn_td.bak' WITH COPY_ONLY, INIT;
```

Luego en PowerShell:

```
mkdir salida -Force ; docker compose cp sqlserver:/var/opt/mssql/data/smn_td.bak salida\smn_td.bak ; Copy-Item .env salida\env_local
```

Pasa `salida\smn_td.bak` y `salida\env_local` a la PC de la empresa por **USB** (o OneDrive). `env_local` trae tus contraseñas: bórralo de la USB al terminar.

### 4. PC de la empresa: subir los datos al servidor

En PowerShell, en la carpeta donde dejaste los 2 archivos:

```
scp smn_td.bak env_local smnnatural@172.31.104.4:
```

### 5. Servidor: preparar y publicar

```
GIT_SSH_COMMAND="ssh -i ~/.ssh/smn_github -o IdentitiesOnly=yes" git --git-dir=/datos/plataforma/repo.git fetch -q --tags origin '+refs/heads/*:refs/heads/*' && git --git-dir=/datos/plataforma/repo.git show v1.0:publicacion/servidor/primera_vez.sh | tr -d '\r' > ~/primera_vez.sh && bash ~/primera_vez.sh v1.0
```

Tarda de 15 a 20 minutos. Debe terminar con `Listo: v1.0 publicada en https://172.31.104.4`. Después borra las copias sensibles: `rm ~/env_local ~/smn_td.bak`

### 6. Servidor: modelos de IA

Usa el mismo modelo de texto que tienes en Configuración → Modelo de Ollama. Si no tienes uno, `qwen2.5:14b` cabe en la T4 y escribe bien en español:

```
docker exec smn-ollama-1 ollama pull bge-m3 && docker exec smn-ollama-1 ollama pull qwen2.5:14b
```

### 7. PC de la empresa: entrar

Abre **https://172.31.104.4**. La primera vez el navegador avisa que la conexión no es privada: **Configuración avanzada → Continuar** (para quitar el aviso, ve a «Certificado» abajo). En **Administración → Sistema** debe decir Entorno `produccion` y Versión `v1.0`.

### 8. Tu usuario y el firewall (cuando quieras)

En la PC de la empresa:

```
ssh-keygen -t ed25519
scp "$env:USERPROFILE\.ssh\id_ed25519.pub" smnnatural@172.31.104.4:
```

En el servidor:

```
git --git-dir=/datos/plataforma/repo.git show v1.0:publicacion/servidor/asegurar_servidor.sh | tr -d '\r' > ~/asegurar_servidor.sh && bash ~/asegurar_servidor.sh diego ~/id_ed25519.pub
```

**Sin cerrar esa ventana**, abre otra y prueba `ssh diego@172.31.104.4`. Debe entrar sin contraseña. Desde ahí, entra con `diego`.

---

## Copia del servidor a la laptop (para probar con datos reales)

1. **PC de la empresa**, ver qué respaldos hay: `ssh smnnatural@172.31.104.4 "ls -1t /datos/respaldos | head -5"`
2. **PC de la empresa**, bajar el más reciente a la USB: `scp "smnnatural@172.31.104.4:/datos/respaldos/smn_td_20261105.bak" D:\` (cambia la fecha y la letra de la USB)
3. **Laptop**: `powershell -ExecutionPolicy Bypass -File publicacion\copiar_produccion.ps1 -Archivo "D:\smn_td_20261105.bak"`

Tu base local se **reemplaza** completa y las tareas programadas quedan apagadas en la laptop. Ese mismo `.bak` es la copia fuera del servidor: guarda uno por semana, como mínimo, en un lugar seguro.

## Comandos útiles (en el servidor)

- **Historial de publicaciones:** `cat /datos/plataforma/historial.log`
- **Qué está corriendo:** `docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"`
- **Errores de la API:** `docker logs --tail 100 smn-api-1`
- **Respaldos y reinicios:** `tail -20 /datos/respaldos/respaldo.log`
- **Correos de prueba (Mailpit):** desde la PC de la empresa, `ssh -L 8025:localhost:8025 smnnatural@172.31.104.4`, déjalo abierto y abre http://localhost:8025
- **Contraseña de solo lectura** (SSMS a `172.31.104.4,1433`): `cat ~/clave_smn_lectura.txt`. No la pegues en el chat.
- **Certificado** (para quitar el aviso del navegador): en el servidor corre `sudo cp /datos/caddy/data/caddy/pki/authorities/local/root.crt ~/smn-servidor.crt && sudo chown $USER ~/smn-servidor.crt`. En la PC de la empresa corre `scp smnnatural@172.31.104.4:smn-servidor.crt .`, abre el archivo → Instalar certificado → Usuario actual → **Entidades de certificación raíz de confianza** → Finalizar, y vuelve a abrir el navegador.
