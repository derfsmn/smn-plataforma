# SMN - Transformación digital

Plataforma de las iniciativas de Innovación y Transformación Digital de Súper Naturista.
Contexto completo para personas y agentes: **[AGENTS.md](AGENTS.md)**. Estado actual: **[docs/ESTADO.md](docs/ESTADO.md)**.

## Requisitos en tu equipo (Windows)

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) con WSL 2 (para SQL Server y para levantar todo junto).
- Opcional, para desarrollar sin Docker: Python 3.12, Node.js 22 y el [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server).

## Arrancar todo con Docker

```powershell
copy .env.ejemplo .env      # y cambia MSSQL_SA_PASSWORD
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000/api/salud (documentación en http://localhost:8000/docs)
- SQL Server: localhost,1433 (usuario `sa`, base `smn_td`)

La API crea la base `smn_td` si no existe y aplica las migraciones al arrancar.

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
uvicorn main:app --reload
pytest
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
db/       semillas de datos ficticios
docs/     estado, decisiones, modelos .dbml, referencias
marca/    logos oficiales originales, sin modificar
```
