# Estado del proyecto

Actualizar al final de cada sesión (Claude Code o Codex). Lo más reciente arriba.

## Estado actual (2026-10-13)

- **Etapa:** 3 de 6 — Acceso real: **construida y probada en el entorno de Claude** (2026-10-13); falta probarla en el equipo de Diego.
- **Etapas 1 y 2** terminadas (la 2 revisada por Diego, con tema claro/oscuro).
- **Hecho en etapa 3:**
  - Base: migración `0002` con 11 tablas en `nucleo` (usuario, organizacion_externa, invitacion, restablecimiento_contrasena, sesion, modulo, permiso, rol, rol_permiso, usuario_rol, bitacora). DBML actualizado (18 tablas).
  - Catálogos: `scripts/semilla.py` (módulos compras y rrhh en diseño, 8 permisos, 5 roles) corre al arrancar la API. Primer administrador con `scripts/crear_admin.py`.
  - API `/api/auth`: iniciar, salir, yo, cambiar-contrasena, recuperar, restablecer/{token}, invitacion/{token}. API `/api/nucleo`: resumen, usuarios (listar, invitar, reenviar invitación, liga de contraseña, activar/desactivar, cambiar rol), roles y permisos, módulos. Detalle de seguridad en AGENTS.md §6.
  - Pruebas: `api/tests/test_acceso.py` (11 pruebas, base aparte `smn_td_pruebas` que se crea sola). Todas pasan.
  - Web: sin datos ficticios. Sesión real (`componentes/sesion.tsx`), menú armado con permisos, `/invitacion/[token]` y `/restablecer/[token]`, administración que guarda en SQL Server, ventana con la liga para copiar, menú de acciones por usuario. Franja "Entorno de desarrollo" en vez de "datos de ejemplo".
  - Prueba de punta a punta en navegador (Playwright): login con error, invitar proveedor e interno, aceptar invitaciones, liga reutilizada rechazada, proveedor no entra a admin, módulo visible al pasar a piloto, permisos que se guardan, desactivar corta la sesión, restablecer contraseña, celular sin desbordes, sin errores de consola.
- **Pendiente en esta etapa:** desactivar cuentas sin uso en 90 días (propuesta, no hecho); texto del aviso de privacidad (Jurídico).
- **Siguiente paso:** Diego prueba en su equipo; después etapa 4 (correo de salida, archivos, notificaciones, puerta de IA con topes).

### Plan del cascarón
1. Cimientos: repositorio, AGENTS.md/CLAUDE.md, Docker, SQL Server vacío con esquema `nucleo`.
2. Prototipo visual: login, inicio con tarjetas de iniciativas, menú, perfil, administración de usuarios y roles; celular y escritorio.
3. Acceso real: usuario y contraseña, recuperación por correo, invitación de externos, permisos por módulo.
4. Servicios comunes: archivos, notificaciones por correo, bitácora, puerta de IA con topes.
5. Puesta en servidor (Sistemas).
6. Módulo Compras (TD001).

### Pendientes de Diego / Sistemas
- Respuesta de Sistemas a la solicitud de servidor del 2026-10-12.
- Avisar a Sistemas: los servidores alojan toda la plataforma; ya no se necesita login corporativo; falta equipo con GPU para Ollama. **En pausa por decisión de Diego (2026-10-13).**
- Montos de los topes de gasto de IA.
- Fuente tipográfica oficial (si existe).
- Compras: lista de restricciones, umbrales por departamento, pesos del score, definición de lanzamiento exitoso.

## Bitácora de sesiones

| Fecha | Agente | Qué se hizo | Siguiente paso |
|---|---|---|---|
| 2026-10-13 | Claude (proyecto) | Etapa 3: acceso real con SQL Server (tablas del núcleo, Argon2, sesiones con cookie, invitaciones, permisos, bitácora); pruebas API y navegador | Diego prueba en su equipo; etapa 4 |
| 2026-10-13 | Claude (proyecto) | Etapa 2: prototipo visual del cascarón con animaciones y datos de ejemplo; tema claro/oscuro; probado escritorio y celular | Revisión de Diego; etapa 3 acceso real |
| 2026-10-13 | Claude (proyecto) | Etapa 1: estructura, API base, web base, docker-compose, migración del esquema nucleo; probado | Etapa 2: prototipo visual |
| 2026-10-13 | Claude (proyecto) | Arquitectura, modelo del núcleo, archivos de contexto | Crear repositorio y docker-compose |
