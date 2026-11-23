# TD005 · Investigación, base de conocimiento y reglas de Vidanat

Iniciativa de Transformación Digital. Módulo `innovacion` de la plataforma, estado piloto. Plan v2 en PDF, aprobado por Diego el 2026-11-22 («puedes comenzar el desarrollo»). Esta ficha cubre la **Entrega 1**, que ya está construida.

Vidanat es la marca propia de SMN. El módulo es solo para usuarios internos y, por ahora, solo para el equipo de Desarrollo e Innovación. El comité de Compras no participa. Lo comercial es de Marketing y llega en la Entrega 2.

## Qué hace

Pantallas bajo `/innovacion`, con menú propio en el grupo «Innovación».

1. **Inicio.** Bandejas de trabajo: fuentes por revisar, expedientes que esperan dictamen o Filtro, reglas en revisión y excepciones por aprobar.
2. **Fuentes** (`/innovacion/fuentes`). Se suben hasta 10 archivos por fuente, de 40 MB cada uno.
   - Todo lo que se sube es comprado, así que se guarda completo.
   - Cada fuente tiene versiones, clasificación (pública, interna o restringida) y estado: pendiente, revisada o rechazada.
   - Al cargarla se lee el texto. Los PDF escaneados y las imágenes pasan por OCR con Tesseract en español e inglés. Las imágenes y las infografías las describe la IA local para que también se puedan encontrar.
   - La IA sugiere título, autores, tipo y otros datos, y una persona los confirma.
   - En cada fuente se ven sus vínculos (a ingredientes, reglas y expedientes) y dónde se usa.
   - Lo pesado corre en una cola con reintentos a 1, 5 y 30 minutos. La pantalla muestra el avance.
3. **Búsqueda.** Combina palabras (BM25) y significado (`bge-m3`). El código está en `api/nucleo/busqueda.py` y se comparte con Métodos y procedimientos.
   - Los sinónimos del catálogo de ingredientes también cuentan: buscar «piridoxina» encuentra «Vitamina B6».
4. **Consultar** (`/innovacion/consultar`). La IA contesta solo con fuentes revisadas que la persona tiene permiso de ver.
   - Cada dato lleva su cita, y una cita que no existe se quita.
   - Si las fuentes no alcanzan, la respuesta es «evidencia insuficiente».
5. **Investigar** (`/innovacion/investigar`). La IA actúa como investigador científico y químico. Plantea las preguntas, elige qué leer, lo lee y escribe un informe con citas.
   - Fuentes gratis: PubMed, Europe PMC (con texto completo de acceso abierto), ClinicalTrials.gov, OpenAlex y Crossref.
   - Con gasto: sitios oficiales (COFEPRIS, DOF, FDA, EFSA, NIH ODS) y la web en general, por DataForSEO y dentro del tope del mes de «buscar en internet».
   - Lo que encuentra entra a Fuentes como **pendiente**, y una persona lo revisa antes de que cuente.
6. **Expedientes** (`/innovacion/expedientes`). Hay un folio por producto en desarrollo, y cada folio tiene su equipo. Pestañas:
   - **Ficha.** Datos del producto.
   - **Fórmula.** Se guarda cifrada. Para verla hace falta el permiso **y** ser del equipo del folio.
   - **Evidencia.** Fuentes citadas, que se eligen desde la búsqueda.
   - **Mercado.** Comparables, escenarios y pendientes.
   - **Historial.** Evaluaciones, que no se pueden cambiar y se pueden comparar entre sí, además de los dictámenes y las excepciones. Nadie aprueba su propia excepción.
   - **Filtro.** Lo decide un usuario directivo. Al decidir queda una foto congelada del expediente.
7. **Reglas** (`/innovacion/reglas`). Cada regla pasa por borrador, revisión, publicada y retirada.
   - Severidad: bloqueante, mayor o menor.
   - La condición se escribe en JSON y se puede probar contra un expediente antes de enviarla.
   - Al publicar se revisan los choques con otras reglas.
   - El módulo funciona **sin ninguna regla publicada**, porque las reglas «apenas se están pensando».
8. **Revisiones** (`/innovacion/revisiones/{id}`). Pantalla para dictaminar. La IA sugiere un dictamen con su razón y lo que falta, y la persona decide.
9. **Ingredientes** (`/innovacion/ingredientes`). El catálogo con nombre, tipo, forma química y sinónimos.
   - El factor UI → µg solo se acepta si una fuente revisada lo respalda.

## Lo que nunca sale del servidor

- Ninguna tarea de IA del módulo puede usar una API externa. El candado está en `api/ia/puerta.py` (`SOLO_LOCAL = ("innovacion.",)`) y deja solo Ollama.
- A internet solo salen términos de búsqueda. La fórmula, la ficha y los datos de un folio nunca se mandan afuera.
- El texto que viene de una fuente se trata como dato, no como instrucción.

## Permisos y roles

- Permisos:
  - `innovacion.recurso.ver`, `.recurso.cargar`, `.recurso.revisar` y `.restringido.ver`
  - `innovacion.consulta.usar` e `innovacion.investigacion.correr`
  - `innovacion.expediente.ver` y `.expediente.editar`
  - `innovacion.formula.ver` y `.formula.editar`
  - `innovacion.evaluacion.correr`
  - `innovacion.regla.proponer` y `.regla.publicar`
  - `innovacion.dictamen.emitir`, `.excepcion.aprobar` y `.decision.filtro`
  - `innovacion.exportar`
- Roles: `innovacion_investigador`, `innovacion_lider`, `innovacion_formulacion`, `innovacion_regulatorio`, `innovacion_calidad`, `innovacion_directivo` e `innovacion_marketing`. Regulatorio y Calidad se crean sin asignar.
- Tareas de IA, todas en `ollama`:
  - `innovacion.huella` (`bge-m3`)
  - `innovacion.sugerir_datos`
  - `innovacion.describir_imagen` (`qwen3-vl:4b-instruct`)
  - `innovacion.responder`
  - `innovacion.sugerir_dictamen`
  - `innovacion.investigar`

## Dónde está el código

- API:
  - `api/modulos/innovacion/`, con modelos, motor de reglas, acceso, almacén, lectura/OCR, índice, IA local, trabajos, fuentes externas, investigador, expedientes, evaluación, consulta, PDF y rutas.
  - La migración es `api/migraciones/versions/0052_innovacion.py`, que cuelga de 0051.
- Web: `web/app/(interno)/innovacion/` y `web/lib/innovacion.ts`.
- Pruebas: `api/tests/test_innovacion.py`, con 13 pruebas.
- El `api/Dockerfile` instala `tesseract-ocr`, `tesseract-ocr-spa`, `tesseract-ocr-eng` y `poppler-utils`.

## Para probar

1. Construye y levanta: `docker compose up --build -d api web`. Instala Tesseract, corre la migración 0052 y la semilla.
2. Baja los modelos en el equipo donde corre Ollama:
   - `ollama pull bge-m3`
   - `ollama pull qwen3-vl:4b-instruct`

   Sin ellos, la búsqueda queda solo por palabras y las imágenes no se describen.
3. En Usuarios, asigna los roles `innovacion_*` a las personas del equipo de Desarrollo e Innovación.
4. Esto es opcional: `docker compose exec api python -m scripts.ejemplos_innovacion` carga datos **FICTICIOS** marcados «[EJEMPLO]»:
   - 4 ingredientes.
   - 12 fuentes: 9 revisadas y 3 pendientes.
   - 8 reglas en varios estados.
   - 2 expedientes:
     - «Magnesio para relajación» cumple todo menos el dictamen pendiente.
     - «Ashwagandha con melatonina» falla R-ETQ-901 por decir «cura».

   Se quitan con `--quitar`, y los ingredientes se quedan.

## Pendientes

- Entrega 2: lo comercial con Marketing y el análisis previo con la base histórica de ventas.
- Las reglas reales, cuando Desarrollo e Innovación las defina.
- Quién del equipo tiene cada rol, sobre todo quién es el directivo que decide el Filtro.
- Probar con Ollama en el equipo de Diego y después publicarlo en el servidor.
