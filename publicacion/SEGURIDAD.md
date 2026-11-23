# Arreglos de seguridad (revisión 2026-11-22): qué cambió y pasos en el servidor

Informe completo: https://claude.ai/artifact/VeWK5J8iQ8C2iC3GHvKD5r

## Qué cambió en el código

| Hallazgo | Cambio | Archivos |
|---|---|---|
| A2 llave derivada de sa | Una sola fuente de llaves (`core/cifrado.py`). Poner `CLAVE_CIFRADO` ya no deja nada sin abrir: lo viejo se sigue leyendo con la llave anterior. `scripts/rotar_llave.py` vuelve a cifrar todo con la llave vigente. | `core/cifrado.py`, `core/ajustes.py`, `modulos/innovacion/almacen.py`, `scripts/rotar_llave.py`, `publicacion/servidor/rotar_llave.sh` |
| A3 texto de fórmulas en claro | Texto de las secciones, texto pegado, descripciones de imágenes y respuestas/citas de la consulta de Innovación se guardan cifrados (`TextoProtegido`). Lo que ya estaba se cifra con `rotar_llave`. | `modulos/innovacion/modelos.py` |
| A3 smn_lectura | `primera_vez.sh` le niega el esquema `innovacion`. En el servidor actual va el paso 4. | `publicacion/servidor/primera_vez.sh` |
| M1 laptop | SQL Server (1433) y Mailpit (8025) solo en `127.0.0.1`. SSMS en tu laptop sigue entrando a `localhost`. | `docker-compose.yml` |
| M2 respaldos | Los `.bak` nuevos quedan `640` del grupo docker y la carpeta `750`. | `publicacion/servidor/comun.sh`, `primera_vez.sh` |
| M3 / B7 límites | 20 fallas por IP en 15 min → espera. 5 fallas por correo → bloqueo de 15 min, exista o no la cuenta (ya no se distingue). Recuperar: 10 por IP y 3 por correo por hora (responde igual y no manda más). | `core/limites.py`, `nucleo/autenticacion.py` |
| M5 encabezados | Caddy manda `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` (micrófono permitido para Naturi), CSP de marcos y HSTS; quita `Server`/`X-Powered-By`. Next ya no dice «Next.js». | `publicacion/servidor/Caddyfile`, `web/next.config.ts` |
| M6 contenedores | La API corre como `app` (uid 10001): `entrypoint.sh` arranca como root solo para dejarle `/datos/archivos` y cambia de usuario. La web corre como `node`. En el servidor la API se instala sin herramientas de prueba. | `api/Dockerfile`, `api/entrypoint.sh`, `web/Dockerfile`, `docker-compose.servidor.yml` |
| B1 costos | Permiso nuevo `compras.costos.ver` (se agrega solo a admin y a los 3 roles de Compras); sin él, la ficha del buscador no trae costo ni margen. | `modulos/compras/rutas_buscador.py`, `scripts/semilla.py` |
| B2 red interna | RSS y robots.txt solo a sitios públicos, también al redirigir. | `modulos/compras/radar.py`, `modulos/innovacion/fuentes_externas.py` |
| B3 Excel | `defusedxml` (openpyxl lo usa solo). | `api/requirements.txt` |
| B6 resumen | Un proveedor ya no ve cuántos usuarios/proveedores hay. | `nucleo/administracion.py` |

Pendiente, sin código: B5 (fijar versiones de ollama, caddy y SQL Server: espero la salida de `revisar_seguridad.sh` para fijar las que ya tienes) y M2 copia de respaldos fuera del servidor.

## En tu laptop (antes de publicar)

1. `docker compose up -d --build` y `publicacion\probar.ps1`. Debe quedar todo verde.
2. Comprueba: entra a la plataforma, sube un archivo en cualquier módulo y ábrelo (prueba que la API sin root escribe en archivos).

## En el servidor, después de publicar la versión

Cada paso dice qué debes ver. Si algo no sale así, para y mándame la salida.

**1. Comprobar la versión nueva**

```bash
docker top smn-api-1 -o user,cmd | grep uvicorn      # debe decir 10001 (o app), no root
curl -skI https://172.31.104.4/ | grep -Ei 'x-frame|x-powered|server:'   # debe salir X-Frame-Options: DENY y nada más
```

**2. Llave de cifrado propia** (respalda la base y el .env antes)

```bash
bash /datos/plataforma/actual/publicacion/servidor/rotar_llave.sh llave
```

Debe terminar con «Todo quedó con la llave vigente». Después copia la llave a un lugar seguro fuera del servidor:
`grep ^CLAVE_CIFRADO= /datos/plataforma/.env`

**3. Contraseña de sa nueva**

```bash
bash /datos/plataforma/actual/publicacion/servidor/rotar_llave.sh sa
grep ^MSSQL_SA_PASSWORD= /datos/plataforma/.env | cut -d= -f2- | sha256sum | cut -c1-8   # ya NO debe ser 0e65b43f
```

**4. smn_lectura sin acceso a Innovación**

```bash
. /datos/plataforma/actual/publicacion/servidor/comun.sh
sqlsa -d smn_td -Q "DENY SELECT ON SCHEMA::innovacion TO smn_lectura;"
```

Comprobación en SSMS (por el túnel) entrando como `smn_lectura`: `SELECT TOP 1 * FROM innovacion.fragmento` debe dar el error 229 (permiso denegado).

**5. Permisos de los respaldos que ya existen**

```bash
sudo chgrp docker /datos/respaldos /datos/respaldos/*.bak
sudo chmod 750 /datos/respaldos && sudo chmod 640 /datos/respaldos/*.bak
ls -ld /datos/respaldos && ls -l /datos/respaldos | tail -3    # drwxr-x--- y -rw-r-----
```

**6. SSH sin contraseña.** Solo cuando `revisar_seguridad.sh` confirme que tu usuario con llave existe. Si Sistemas entra con contraseña como `smnnatural`, se le deja con una excepción. Te doy ese paso con la salida del script.

## Si traes un respaldo del servidor a tu laptop

Pon en el `.env` de la laptop la misma `CLAVE_CIFRADO` del servidor. Sin ella, la laptop no abre las fórmulas ni los secretos de ese respaldo.
