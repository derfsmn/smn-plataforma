# SMN - Transformación digital · Contexto para agentes de código

Este archivo es la fuente única de contexto del proyecto. Lo leen Claude Code (vía `CLAUDE.md`) y Codex (directamente).
Antes de trabajar, lee también `docs/ESTADO.md` (en qué vamos) y `docs/DECISIONES.md` (qué ya se decidió y por qué).
Al terminar una sesión, actualiza `docs/ESTADO.md`. No cambies una decisión de `docs/DECISIONES.md` sin que Diego lo pida.

## 1. Qué es

Plataforma web única de la Gerencia de Innovación y Transformación Digital de **Súper Mayoreo Naturista (SMN, Súper Naturista)**.
Cada iniciativa de un área se conecta como un **módulo** sobre un **cascarón** común.

- Responsable: Diego Ernesto Rodríguez Ferreira, PM de IA y líder de Innovación y Transformación Digital.
- Orden de módulos: 1) Compras (TD001, semáforo de producto nuevo), 2) RRHH, 3) otras áreas.
- Primero se construye el cascarón; Compras se construye encima después.
- Usuarios internos (colaboradores SMN) y externos (proveedores; después candidatos).
- Al área de TI de SMN se le llama **Sistemas**. El ERP es **Intelisis**.

## 2. Stack (decidido)

| Capa | Tecnología |
|---|---|
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, Motion (animaciones), librería de gráficas |
| Backend | Python, FastAPI |
| Base de datos | **SQL Server** (la plataforma completa; el radar de precios en MySQL se migrará) |
| Migraciones | Alembic (SQLAlchemy) |
| IA | Ollama local + API de IA externa con tope de gasto, siempre detrás de la "puerta de IA" |
| Despliegue | Docker / docker-compose en el servidor que se pidió a Sistemas el 2026-10-12 |
| Código | Git |

## 3. Reglas que no se rompen

1. **Intelisis nunca se toca.** Sistemas deposita los datos en una base aparte; la plataforma solo lee esa base y guarda lo suyo en su propia base.
2. **Acceso con usuario y contraseña propios** de la plataforma, para internos y externos. **Sin Microsoft 365 ni SSO.** El correo se usa para invitaciones, recuperación de contraseña y avisos.
3. **La IA sugiere y explica; una persona decide.** En Compras el color del semáforo lo calcula el motor de reglas, no la IA.
4. Ningún módulo llama a una IA directamente: todo pasa por `api/ia/` (puerta de IA), que elige Ollama o API, revisa el tope de gasto y registra la llamada.
5. **Nunca usar datos inventados como reales.** Los datos de prueba se marcan como ficticios y viven en `tests/` o `db/semillas/`.
6. Permisos validados en el servidor, no solo ocultando botones.
7. Un externo solo ve sus propios registros y nunca el portal interno.

## 4. Arquitectura

```
Usuarios internos ─┐                     ┌─ Usuarios externos
                   ▼                     ▼
          web/app/(interno)      web/app/(externo)     ← Next.js responsiva
                   └──────── API REST ───┘
                              ▼
api/nucleo   acceso, usuarios, roles, módulos, archivos, notificaciones, bitácora
api/ia       puerta de IA (Ollama / API, topes, registro)
api/modulos/<nombre>   cada módulo (compras, rrhh...)
                              ▼
SQL Server: esquema nucleo + un esquema por módulo │ base de Sistemas (solo lectura) │ almacén de archivos │ Ollama │ API IA
```

### Estructura del repositorio

```
smn-transformacion-digital/
├─ AGENTS.md  CLAUDE.md
├─ docs/      ESTADO.md, DECISIONES.md, modelos .dbml, documentos de diseño
├─ marca/     logos oficiales sin modificar
├─ api/
│  ├─ core/  (configuración y conexión a BD)
│  ├─ nucleo/  ia/  modulos/<nombre>/
│  ├─ migraciones/  (Alembic)  scripts/  tests/
├─ web/
│  ├─ componentes/        librería de diseño SMN
│  └─ app/(interno)/<modulo>  app/(externo)/<modulo>
├─ db/semillas/
├─ tests/
└─ docker-compose.yml
```

### Contrato de módulo (todo módulo nuevo lo cumple)

1. Registro en `nucleo.modulo` con código de iniciativa (TD001…), área, responsable y estado (`en_diseno`, `piloto`, `activo`, `retirado`). Solo `piloto` y `activo` aparecen en el menú.
2. Declara sus permisos con formato `<modulo>.<entidad>.<accion>` (p. ej. `compras.solicitud.ver`).
3. Su propio esquema SQL (`compras`, `rrhh`). Solo lee de `nucleo`; nunca del esquema de otro módulo.
4. Backend en `api/modulos/<nombre>`, rutas bajo `/api/<nombre>`.
5. Pantallas en `web/app/(interno)/<nombre>` y, si aplica, `web/app/(externo)/<nombre>`, usando `web/componentes`.
6. Declara sus tareas de IA (`<modulo>.<tarea>`) y su tope de gasto en la puerta de IA.
7. Declara sus indicadores de valor.

## 5. Datos

- Convención: `snake_case`, nombres de negocio en español.
- **El DBML es la fuente de verdad del modelo**: primero se cambia el `.dbml`, después la migración.
- Núcleo: `docs/modelos/nucleo_plataforma_v0.dbml` (17 tablas: usuario, organizacion_externa, invitacion, restablecimiento_contrasena, modulo, permiso, rol, rol_permiso, usuario_rol, archivo, notificacion, bitacora, ia_tarea, ia_presupuesto, ia_llamada, indicador, indicador_valor).
- Compras: `docs/modelos/modelo_semaforo_v3.dbml` (30 tablas) → esquema `compras`. `compras.proveedor` se liga a `nucleo.organizacion_externa` por RFC.
- `bitacora` es solo inserción.

## 6. Seguridad de acceso

- Contraseñas: mínimo 10 caracteres, hash (argon2 o bcrypt), nunca en texto.
- Recuperación: liga de un solo uso por correo, con expiración.
- Bloqueo temporal tras 5 intentos fallidos; cierre de sesión por inactividad.
- Internos: los da de alta un administrador. Externos: por invitación de un interno.
- Cuentas sin uso en 90 días se desactivan (propuesta).
- Aviso de privacidad aceptado y registrado para externos.
- Todo por HTTPS.

## 7. Diseño (Súper Naturista)

- Logos oficiales en `marca/`. **No deformar, no recolorear, no recrear el logo.** Barra superior: logo de una línea naranja con blanco sobre negro. Ícono: isotipo naranja.
- Colores medidos en el logo oficial: **naranja #DE951B**, **negro #222221**, blanco y grises. (#F5A01A era solo referencia; prevalece #DE951B.)
- **El verde no es color de marca**; solo para el estado "verde" de un semáforo.
- Tipografía: Nunito como sustituta hasta tener la oficial (el manual no la incluye).
- **Visualmente atractiva y moderna, con animaciones** (requisito de Diego): portada con tarjetas por iniciativa, transiciones suaves, microinteracciones, números y gráficas animados, esqueletos de carga, avisos tipo toast, modo oscuro opcional.
- Animaciones de 150–400 ms; nada se mueve solo salvo la carga; respetar `prefers-reduced-motion`; menos animación en celular.
- Responsiva, diseñada primero para celular; en celular las tablas se vuelven tarjetas.

## 8. Cómo trabajar

- Idioma: español de México en interfaz, comentarios de negocio y documentación. Código (identificadores técnicos) puede ir en español `snake_case` para negocio.
- Tareas pequeñas; cada cambio en una rama y pull request que Diego revisa.
- Pruebas para reglas de negocio, permisos y la puerta de IA.
- Distinguir propuesta de implementación: no marcar algo como "hecho" si no corre y no tiene prueba.
- No inventar procesos actuales de SMN (AS-IS); si falta información, dejarlo como pendiente en `docs/ESTADO.md`.
- Preferir infraestructura existente antes que servicios de pago nuevos.

## 9. Relevo entre agentes (Claude Code ↔ Codex)

Al **terminar** cada sesión, actualiza `docs/ESTADO.md`:
- Qué se hizo (con archivos tocados).
- Qué quedó a medias y en qué archivo.
- Siguiente paso concreto.
- Pendientes que dependen de Diego o de Sistemas.

Al **empezar**, lee `AGENTS.md`, `docs/ESTADO.md` y `docs/DECISIONES.md`, y revisa `git log` reciente. Si algo de este archivo choca con lo que pide Diego en la conversación, gana Diego y se actualiza este archivo.

## 10. Documentos de referencia

- Arquitectura del cascarón: https://claude.ai/code/artifact/d5568e4b-f6b2-4feb-af61-469285b80b87
- Plan de Compras (módulo 1): https://claude.ai/code/artifact/272088f4-3509-49ea-b7aa-ec923c6d4dbc
- Sitio del modelo del semáforo: https://claude.ai/artifact/E9kFBhRt74iN1dCRdzf7uU
- Formulario de proveedores (prototipo HTML): `docs/referencia/formulario_proveedores_producto_nuevo.html`
