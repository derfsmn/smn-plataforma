# Estado del proyecto

Actualizar al final de cada sesión (Claude Code o Codex). Lo más reciente arriba.

## Estado actual (2026-10-13)

- **Etapa:** 1 de 6 — Cimientos: **terminada** en código; falta que Diego la levante en su equipo y haga `git init`.
- **Hecho:**
  - `api/`: FastAPI con `/api/salud` (reporta API y conexión a SQL Server), configuración por `.env`, conexión SQL Server vía pyodbc (ODBC Driver 18), Alembic con migración `0001` que crea el esquema `nucleo` vacío, script `scripts/preparar_bd.py` que crea la base `smn_td`, prueba con pytest.
  - `web/`: Next.js 15 + React 19 + Tailwind 4, colores SMN como tokens (`smn-naranja`, `smn-negro`, grises), Nunito, logo oficial optimizado en `public/marca/`, página provisional que muestra el estado de API y base.
  - `docker-compose.yml`: SQL Server 2022 Developer + api + web.
  - Verificado en el entorno de Claude (2026-10-13): SQL Server levantó, se creó `smn_td`, migración aplicada (esquema `nucleo`), `/api/salud` respondió api ok y base ok, la web mostró el estado en escritorio y celular, la imagen Docker de la web construyó y respondió 200.
  - No verificado: construir la imagen Docker de la API (el entorno de Claude no pudo descargar paquetes de Debian por su red). Validar en el equipo de Diego con `docker compose up --build`.
- **Siguiente paso:** etapa 2, prototipo visual del cascarón (login, inicio con tarjetas de iniciativas, menú, perfil, administración de usuarios y roles) con animaciones y datos ficticios marcados.

### Plan del cascarón
1. Cimientos: repositorio, AGENTS.md/CLAUDE.md, Docker, SQL Server vacío con esquema `nucleo`.
2. Prototipo visual: login, inicio con tarjetas de iniciativas, menú, perfil, administración de usuarios y roles; celular y escritorio.
3. Acceso real: usuario y contraseña, recuperación por correo, invitación de externos, permisos por módulo.
4. Servicios comunes: archivos, notificaciones por correo, bitácora, puerta de IA con topes.
5. Puesta en servidor (Sistemas).
6. Módulo Compras (TD001).

### Pendientes de Diego / Sistemas
- Respuesta de Sistemas a la solicitud de servidor del 2026-10-12.
- Avisar a Sistemas: los servidores alojan toda la plataforma; ya no se necesita login corporativo; falta equipo con GPU para Ollama.
- Montos de los topes de gasto de IA.
- Fuente tipográfica oficial (si existe).
- Compras: lista de restricciones, umbrales por departamento, pesos del score, definición de lanzamiento exitoso.

## Bitácora de sesiones

| Fecha | Agente | Qué se hizo | Siguiente paso |
|---|---|---|---|
| 2026-10-13 | Claude (proyecto) | Etapa 1: estructura, API base, web base, docker-compose, migración del esquema nucleo; probado | Etapa 2: prototipo visual |
| 2026-10-13 | Claude (proyecto) | Arquitectura, modelo del núcleo, archivos de contexto | Crear repositorio y docker-compose |
