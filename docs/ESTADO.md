# Estado del proyecto

Actualizar al final de cada sesión (Claude Code o Codex). Lo más reciente arriba.

## Estado actual (2026-10-13)

- **Etapa:** 2 de 6 — Prototipo visual del cascarón: **construida y probada en el entorno de Claude** (2026-10-13); falta que Diego la vea en su equipo.
- **Etapa 1** terminada y verificada en el equipo de Diego (2026-10-13).
- **Hecho en etapa 2 (`web/`):**
  - Dependencias nuevas: `motion` (animaciones) y `lucide-react` (íconos). Correr `npm install` en `web/` o reconstruir con `docker compose up --build`.
  - `/login`: pestañas Colaborador SMN / Proveedor, validación (correo, contraseña ≥10), mostrar/ocultar contraseña, recuperación con liga (simulada).
  - Cascarón interno `app/(interno)/`: menú lateral oscuro con indicador animado (escritorio), barra inferior (celular), menú de perfil, transición entre páginas.
  - `/inicio`: saludo, indicadores con contador animado, tarjetas de iniciativas con hover, tarjeta "Registrar iniciativa" para admin.
  - `/modulos/[codigo]`: portada del módulo "en construcción".
  - `/perfil`: datos y cambio de contraseña con medidor de fortaleza.
  - `/admin/usuarios` (buscar, filtrar internos/proveedores, invitar en ventana, activar/desactivar, esqueleto de carga), `/admin/roles` (permisos por rol con interruptores), `/admin/modulos` (cambiar estado), `/admin/sistema` (estado real de API y base).
  - Portal externo `app/(externo)/proveedores`.
  - Componentes reutilizables en `web/componentes/` (Boton, Campo, Insignia, Esqueleto, Entrada, Encabezado, Contador, avisos tipo toast, franja de datos de ejemplo).
  - **Todo es simulado:** datos en `web/lib/datos-ficticios.ts`, sesión en `localStorage` (`web/lib/sesion.ts`). Cualquier correo y contraseña de 10+ caracteres entra. Franja visible "Prototipo con datos de ejemplo" en todas las pantallas.
  - Probado con Playwright a 1440 px y 390 px: sin errores de consola y sin desplazamiento horizontal.
- **Siguiente paso:** Diego revisa el prototipo y pide ajustes; después etapa 3 (acceso real contra SQL Server: tablas del núcleo, hash de contraseñas, invitaciones, permisos).

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
| 2026-10-13 | Claude (proyecto) | Etapa 2: prototipo visual del cascarón con animaciones y datos de ejemplo; probado escritorio y celular | Revisión de Diego; etapa 3 acceso real |
| 2026-10-13 | Claude (proyecto) | Etapa 1: estructura, API base, web base, docker-compose, migración del esquema nucleo; probado | Etapa 2: prototipo visual |
| 2026-10-13 | Claude (proyecto) | Arquitectura, modelo del núcleo, archivos de contexto | Crear repositorio y docker-compose |
