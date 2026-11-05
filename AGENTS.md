# SMN - Transformación digital · Contexto para agentes de código

Este archivo es la fuente única de contexto del proyecto. Lo leen Claude Code (vía `CLAUDE.md`) y Codex (directamente).
Antes de trabajar, lee también `docs/ESTADO.md` (en qué vamos) y `docs/DECISIONES.md` (qué ya se decidió y por qué).
Al terminar una sesión, actualiza `docs/ESTADO.md`. No cambies una decisión de `docs/DECISIONES.md` sin que Diego lo pida.

## 1. Qué es

Plataforma web única de la Gerencia de Innovación y Transformación Digital de **Súper Mayoreo Naturista (SMN, Súper Naturista)**.
Cada iniciativa de un área se conecta como un **módulo** sobre un **cascarón** común.

- Responsable: Diego Ernesto Rodríguez Ferreira, PM de IA y líder de Innovación y Transformación Digital.
- Iniciativas: TD001 Inteligencia de Compras, TD002 Kiosco Digital, TD003 Contraloría / Fiscal (proceso de la DIOT).
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
| Despliegue | Docker / docker-compose en un servidor en **Azure** (decisión 2026-10-15) |
| Código | Git |

## 3. Reglas que no se rompen

0. **Datos de Sistemas** (decisión de Diego, 2026-10-15; ya no aplica la pausa del 2026-10-14): Sistemas pone un histórico en Azure alimentado desde Intelisis. La plataforma no lo consulta en vivo: un ETL propio trae solo lo necesario a nuestra base, en momentos que se eligen desde la plataforma. Nunca se escribe en Azure ni en Intelisis.

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
- Núcleo: `docs/modelos/nucleo_plataforma_v0.dbml` (20 tablas: configuracion, usuario, organizacion_externa, invitacion, restablecimiento_contrasena, sesion, modulo, permiso, rol, rol_permiso, usuario_rol, archivo, notificacion, bitacora, ia_tarea, ia_presupuesto, ia_llamada, ia_costo_real, indicador, indicador_valor). Ya existen en la base 16 (migraciones `0002` identidad, acceso, módulos y bitácora; `0003` archivo, notificacion, ia_tarea, ia_presupuesto, ia_llamada), más `configuracion` (migración `0004`, ajustes editables) e `ia_costo_real` (migración `0006`, costo real de OpenAI por día). Faltan indicador e indicador_valor. Modelos SQLAlchemy en `api/nucleo/modelos.py`.
- Catálogos (módulos, permisos, roles) en `api/scripts/semilla.py`; se aplican al arrancar y no pisan lo que se cambió desde la plataforma. Primer administrador: `docker compose exec api python -m scripts.crear_admin`.
- Compras, Radar de tendencias: `docs/modelos/compras_radar_v0.dbml` (10 tablas `compras.radar_*`, migraciones `0005` y `0007`; `radar_destinatario.tipo_correo` decide si el correo lleva botones de decisión o es informativo).
- Compras, Base de conocimiento: `docs/modelos/compras_conocimiento_v0.dbml` (4 tablas `compras.conocimiento_*`, migración `0016`). Lo que Compras escribe sobre cómo decide; lo leerá el semáforo.
- Compras: `docs/modelos/modelo_semaforo_v3.dbml` (30 tablas) → esquema `compras`. `compras.proveedor` se liga a `nucleo.organizacion_externa` por RFC.
- Centro de datos, catálogo de productos: `docs/modelos/datos_catalogo_v0.dbml` (esquema `datos`, migraciones `0008` y `0009`; código en `api/datos/`: `catalogo.py` API de artículos y consolidación, `tienda.py` tienda en línea e imágenes). Un producto por SKU; cada campo sale de la fuente con más prioridad (ETL > API > tienda); lo crudo de cada fuente en `producto_fuente`. Sin Excel.
- Compras, Radar de precios: `docs/modelos/compras_precios_v0.dbml` (8 tablas `compras.precio_*`, migraciones `0010` a `0015`; código en `api/modulos/compras/`: `coincidencia.py`, `dataforseo.py`, `tiendas.py` (búsqueda directa en Walmart, Chedraui, San Pablo y Soriana), `precios.py`, `rutas_precios.py`). Lee productos de `datos.producto`. Todo automático: la IA elige el producto y marca todas las publicaciones de Google que son el mismo (sus vendedores se juntan); lo que no queda seguro no se compara. Cada envío pagado a DataForSEO se guarda antes de enviarse y nunca se repite.
- Contraloría, Proceso de la DIOT (TD003): `docs/modelos/contraloria_diot_v0.dbml` (esquema `contraloria`, migración `0025`; código en `api/modulos/contraloria/`). Módulo independiente: aquí sí hay RFC de proveedores. Sin IA. Reglas y preguntas para Fiscal en `docs/iniciativas/TD003_contraloria_fiscal.md`.
- `bitacora` es solo inserción.

## 6. Seguridad de acceso

- Contraseñas: mínimo 10 caracteres, hash Argon2 (`api/core/seguridad.py`), nunca en texto.
- Sesión: cookie `smn_td_sesion` httpOnly, SameSite=Lax (Secure fuera de desarrollo), 12 h; en la base solo el SHA-256 del token (`nucleo.sesion`). La web nunca guarda la sesión en localStorage; pide `/api/auth/yo`.
- Tokens de ligas (invitación, restablecimiento) también se guardan solo como SHA-256.
- Recuperación: liga de un solo uso (30 min) que llega por correo; el correo sale después de responder, para que la respuesta tarde lo mismo exista o no la cuenta. El administrador también puede mandar una liga de 24 h desde Usuarios. Sin SMTP configurado, la liga de recuperación sale en la consola de la API (solo en desarrollo).
- Cambiar o restablecer la contraseña avisa a la persona por correo y en la campana.
- Bloqueo de 15 min tras 5 intentos fallidos. Mismo mensaje de error exista o no el correo.
- Internos y externos entran **solo por invitación** de un administrador (liga de 7 días). El rol se elige explícitamente; no hay rol por omisión.
- Permisos: cada ruta usa `requiere("<permiso>")`. El rol `admin` no puede perder `nucleo.usuarios.administrar` ni `nucleo.roles.administrar`; nadie puede desactivarse ni quitarse el rol de admin a sí mismo.
- Desactivar a alguien, cambiar o restablecer su contraseña cierra sus sesiones.
- Todo cambio de usuarios, roles y módulos, y cada inicio de sesión (bueno o fallido), queda en `nucleo.bitacora`.
- Cuentas sin uso en 90 días se desactivan (propuesta).
- Archivos (`/api/archivos`): solo PDF, PNG, JPG, WEBP, XLSX, DOCX y CSV; se revisa la firma del contenido y el tamaño (`ARCHIVOS_MB_MAXIMO`). Se guardan con nombre aleatorio fuera de la base, con su SHA-256. Por ahora los descarga quien los subió o un administrador de usuarios; cada módulo agregará sus reglas.
- Bitácora: se consulta en Administración → Bitácora con `nucleo.bitacora.ver`.
- Aviso de privacidad aceptado y registrado para externos.
- Todo por HTTPS.

### Servicios comunes (etapa 4)

- **Configuración** (Administración → Configuración, permiso `nucleo.configuracion.administrar`): correo SMTP, dirección de la web, duración de sesión, tamaño de archivos y ajustes de IA (Ollama, llave, modelo, precios, tipo de cambio). El catálogo de lo editable está en `api/core/ajustes.py`; lo guardado en `nucleo.configuracion` se sobrepone al `.env` sin reiniciar y se carga al arrancar. Secretos cifrados con Fernet (llave derivada de `CLAVE_CIFRADO`, o de `MSSQL_SA_PASSWORD` si no existe); la pantalla nunca los muestra y la bitácora los oculta. Base de datos, entorno y orígenes solo en `.env`.

- **Correo**: `api/core/correo.py` (SMTP, plantilla con el logo). Se manda con `nucleo.notificaciones.correo(...)`, que deja constancia sin la liga. En local, Mailpit (`docker-compose`, bandeja en http://localhost:8025). Sin `SMTP_SERVIDOR` no se envía y la web muestra la liga para copiarla.
- **Notificaciones**: `nucleo.notificaciones.notificar(bd, usuario_id, titulo, mensaje, liga=..., clave=...)`; `clave` evita repetir el mismo aviso. La campana de la web revisa cada minuto.
- **Puerta de IA** (`api/ia/puerta.py`): `ejecutar(bd, "<modulo>.<tarea>", usuario_id=..., instrucciones=..., mensaje=...)`. Cada tarea se registra en `scripts/semilla.py` (`TAREAS_IA`) con proveedor `ollama`, `api` u `ollama_y_api_respaldo`. La API externa es Anthropic u OpenAI según `ia_proveedor_externo` (OpenAI por la Responses API, con búsqueda web opcional `busqueda_web=True, dominios=[...]`; las citas regresan en `Respuesta.citas`). Con Anthropic (SDK oficial `anthropic`, modelo `IA_MODELO_EXTERNO`, con `fallbacks: "default"` para que Anthropic reintente con su modelo de respaldo si el principal declina) solo se usa con llave, tipo de cambio y tope mensual de plataforma. Topes: plataforma y módulo por mes, persona por día; al llegar se rechaza o se pasa a Ollama; aviso en la campana al % configurado (80 por omisión). El costo en pesos por llamada es estimado con precios y tipo de cambio de Configuración y sirve para frenar antes de gastar. **Costo real** (`api/ia/costos.py`, tabla `nucleo.ia_costo_real`, migración `0006`): con OpenAI y llave de administrador (`openai_admin_key`, opcional `openai_proyecto_id`) el programador baja cada 6 h los últimos 10 días de `/v1/organization/costs` (solo días UTC cerrados); el tope mensual de plataforma usa el real en días cerrados y el estimado en el resto (`costos.gasto_plataforma`); topes de módulo y persona siguen estimados. Pantalla en Administración → IA. Las pruebas simulan la IA y la API de costos; nunca llaman a la API real.

- **Programador**: tarea dentro de la API (`api/main.py`, `PROGRAMADOR_ACTIVO`) que revisa cada minuto. Hoy corre el Radar de tendencias (`modulos/compras/radar.py: revisar_programa`), el Radar de precios (`modulos/compras/precios.py: revisar_programa`), la carga diaria del catálogo de productos (`datos/catalogo.py: revisar_programa`) a la hora configurada, con corrida tardía, 3 reintentos y una corrida por día, y cada 6 h el costo real de OpenAI (`ia/costos.py: revisar`). Cada tarea va en su propio try para que una falla no detenga a la otra.

## 7. Diseño (Súper Naturista)

- Logos oficiales en `marca/`. **No deformar, no recolorear, no recrear el logo.** Barra superior: logo de una línea naranja con blanco sobre negro. Ícono: isotipo naranja.
- Colores medidos en el logo oficial: **naranja #DE951B**, **negro #222221**, blanco y grises. (#F5A01A era solo referencia; prevalece #DE951B.)
- **El verde no es color de marca**; solo para el estado "verde" de un semáforo.
- Tipografía: Nunito como sustituta hasta tener la oficial (el manual no la incluye).
- **Visualmente atractiva y moderna, con animaciones** (requisito de Diego): portada con tarjetas por iniciativa, transiciones suaves, microinteracciones, números y gráficas animados, esqueletos de carga, avisos tipo toast.
- **Tema claro, oscuro o automático** (elige el usuario; se guarda en su navegador). En código usar los tokens `bg-superficie` (tarjetas), `text-tinta` (texto principal), `smn-gris-*` y `aviso-*`, que cambian solos con el tema; no escribir `bg-white` ni colores fijos. Naranja y negro de marca no cambian. Variante `dark:` disponible (ver `web/app/globals.css` y `web/lib/tema.ts`).
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
- Arquitectura con Azure y ETL de Sistemas (2026-10-15): https://claude.ai/artifact/BjdUq7pdUCYzjjze4L4qAj
- Plan de Compras (módulo 1): https://claude.ai/code/artifact/272088f4-3509-49ea-b7aa-ec923c6d4dbc
- Sitio del modelo del semáforo: https://claude.ai/artifact/E9kFBhRt74iN1dCRdzf7uU
- Formulario de proveedores (prototipo HTML): `docs/referencia/formulario_proveedores_producto_nuevo.html`
