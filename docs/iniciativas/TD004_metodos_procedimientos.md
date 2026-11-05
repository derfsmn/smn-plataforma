# TD004 · Métodos y procedimientos

Iniciativa de Transformación Digital abierta el 2026-10-30. Módulo `metodos` en la plataforma, estado piloto. Plan: «Plan: base de conocimiento de métodos y procedimientos» (https://claude.ai/artifact/6DDdDjx5JrrACSs9cmoNw2). Se construyó todo en una entrega, sin fases.

## Qué hace

Pantalla: Métodos y procedimientos (`/metodos`), con 6 pestañas.

1. **Preguntar.** Contesta solo con los manuales vigentes y cita cada dato (documento, versión, sección y página). La cita lleva a la sección del documento. Si no hay respaldo, contesta «No está en los manuales vigentes» y dice a qué área preguntar; la pregunta queda anotada. Cada respuesta se califica con 👍 o 👎.
   - Con la IA local (Ollama) apagada, muestra las 3 secciones que más se parecen, sin redactar («modo palabras»).
   - Desde la pantalla de la DIOT hay un enlace para preguntar a los manuales.
2. **Documentos.** Se cargan PDF, Word, Excel, CSV y Markdown con área dueña, versión, vigencia, fecha de revisión, sistema y quién lo ve (roles). Al cargar una versión nueva, la anterior queda como histórica. Si el archivo ya se había cargado (misma huella), se avisa.
   - También usa los documentos de la Base de conocimiento de Compras (los ve quien tiene `compras.radar.ver`) y de la Base de conocimiento fiscal (los ve quien tiene `contraloria.diot.ver`). Esos se cambian en su módulo, no aquí.
   - Correos, CURP, RFC y teléfonos se ocultan en el texto que usa la búsqueda; el documento original no se toca.
   - Un manual se marca como viejo cuando pasa su fecha de revisión o lleva más de 2 años sin una.
3. **Borradores (IA que redacta).** La IA local redacta un manual nuevo, una versión actualizada o el paso de un manual al formato estándar (Objetivo, Alcance, Responsables, Definiciones, Políticas, Procedimiento, Excepciones, Formatos, Control de cambios). Lo que no sabe lo marca como `[PREGUNTA: …]`; no se puede publicar mientras quede alguna. En una actualización se ve cada cambio y se acepta o rechaza uno por uno. Lo publica el área dueña (permiso `metodos.aprobar`); se descarga en Word.
   - **Diagrama de flujo (2026-11-01, migración `0037`):** al pedir un manual nuevo se pueden subir hasta 5 archivos en lugar de escribir. Después del texto, la IA saca el flujo (carriles por puesto, pasos, decisiones con salidas Sí/No); si no responde, se arma con los pasos numerados. Se corrige en el borrador paso por paso con vista previa. Máximo 40 pasos y 6 puestos.
   - **PDF oficial:** encabezado con logo, clave, versión y vigencia; diagrama después de «Procedimiento»; pie con quién aprobó y número de página. El borrador lleva marca de agua. El Word lleva el mismo diagrama.
4. **Avisos.** Contradicciones entre manuales (la IA compara secciones parecidas) y sugerencias: preguntas sin respuesta o con 👎, manuales viejos y criterios fiscales aprobados que no están en un manual.
5. **Reporte.** Por mes: preguntas, cuántas se contestaron, calificaciones y temas sin respuesta.
6. **Prueba.** Lista de preguntas con su respuesta esperada (incluye preguntas que deben dar «no está»). La corrida mide: al menos 80 % correctas, 0 inventadas, todas las «no está» bien contestadas, menos de 15 segundos por respuesta y con la IA local. Se anuncia a los usuarios hasta pasar la prueba de 40 preguntas.

## Cómo busca

- Por palabras (BM25 con raíces del español) y por significado (huellas con el modelo `bge-m3` en Ollama), combinadas. Solo cuenta como respaldo si cubre la mayor parte de la pregunta o el parecido es alto. Los cortes son provisionales hasta la prueba de 40 preguntas.
- La IA solo redacta con los fragmentos encontrados; si cita un fragmento que no existe, se quita, y sin ninguna cita válida la respuesta es «no está».

## Permisos y roles

- `metodos.consultar`: preguntar y ver documentos. `metodos.cargar`: cargar documentos y pedir borradores. `metodos.aprobar`: publicar y retirar (solo de su área, si el usuario tiene área).
- Roles nuevos: `metodos_consulta` y `metodos_responsable`. Consultar se dio también a los roles de Compras y a `contraloria_fiscal`.
- Tareas de IA (todas `ollama`): `metodos.huella`, `metodos.responder`, `metodos.redactar`, `metodos.contradicciones`.

## Para probar

1. `docker compose up --build -d api web` (migración `0036`) y `docker compose exec api python -m scripts.semilla`.
2. `ollama pull bge-m3` (huellas de significado). Sin él, la búsqueda funciona solo por palabras.
3. Opcional: `docker compose exec api python -m scripts.ejemplos_metodos` carga 3 manuales **FICTICIOS** («EJEMPLO …») y 4 preguntas de prueba. Se quitan con `--quitar`. No describen procesos reales de SMN.

## Pendientes

- **Transformación Digital / áreas:** inventario de documentos reales (cuáles, de qué área, dónde están, quién aprueba).
- **Áreas:** las 40 preguntas de prueba con su respuesta esperada.
- Probar huellas, respuestas y redacción con Ollama real (las pruebas automáticas usan una IA simulada).
