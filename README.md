# SMN - Transformación digital

Plataforma de las iniciativas de Innovación y Transformación Digital de Súper Naturista.
Contexto completo para personas y agentes: **[AGENTS.md](AGENTS.md)**. Estado actual: **[docs/ESTADO.md](docs/ESTADO.md)**.

## Requisitos en tu equipo (Windows)

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) con WSL 2 (para SQL Server y para levantar todo junto).
- Opcional, para desarrollar sin Docker: Python 3.12, Node.js 22 y el [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server).

## Arrancar todo con Docker

```powershell
copy entorno.ejemplo .env      # y cambia MSSQL_SA_PASSWORD
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000/api/salud (documentación en http://localhost:8000/docs)
- SQL Server: localhost,1433 (usuario `sa`, base `smn_td`)
- Buzón de correo de prueba (Mailpit): http://localhost:8025 — aquí llegan todos los correos de la plataforma; nada sale a internet.

La API crea la base `smn_td` si no existe, aplica las migraciones y carga los catálogos al arrancar.

**La primera vez**, con todo corriendo, crea tu usuario administrador en otra terminal:

```powershell
docker compose exec api python -m scripts.crear_admin
```

Te pide nombre, correo y contraseña (10 caracteres o más). Después entra a http://localhost:3000 con ese correo.
A las demás personas se les invita desde **Administración → Usuarios**: les llega un correo (en local, al buzón de prueba) y además ves la liga por si quieres mandarla tú.

### Puerta de IA en local (opcional)

- **Ollama**: instálalo en tu equipo, descarga un modelo (`ollama pull <modelo>`) y pon su nombre en **Administración → Configuración** (o en `OLLAMA_MODELO` del `.env`). La API lo busca en `host.docker.internal:11434`.
- **API externa (Anthropic)**: queda apagada hasta que captures la llave y el tipo de cambio en **Administración → Configuración** y el tope mensual en **Administración → Inteligencia artificial**. Ahí mismo hay un botón para probar.

Correo, dirección de la web, archivos e IA se cambian en **Administración → Configuración** sin reiniciar; lo que guardes ahí manda sobre el `.env`.

Si cambias el `.env`, reinicia la API: `docker compose up -d --build api`.
En desarrollo funciona con `localhost`, `127.0.0.1` o la IP de tu equipo (útil para probar desde el celular en la misma red).

## Desarrollar sin Docker (más rápido para editar)

Deja solo SQL Server en Docker: `docker compose up sqlserver`

API (PowerShell, desde `api/`):

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy ..\.env .env
python -m scripts.preparar_bd
alembic upgrade head
python -m scripts.semilla
python -m scripts.crear_admin
uvicorn main:app --reload
pytest            # crea y usa la base smn_td_pruebas
```

Web (desde `web/`):

```powershell
npm install
npm run dev
```

## Estructura

```
api/      FastAPI: core (configuración y BD), nucleo, ia, modulos, migraciones (Alembic), tests
web/      Next.js: app (pantallas), public/marca (logos optimizados)
docs/     estado, decisiones, modelos .dbml, referencias
marca/    logos oficiales originales, sin modificar
```
