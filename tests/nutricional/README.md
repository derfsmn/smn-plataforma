# Prueba local de extracción nutrimental

## Segunda etapa: revisión documental del producto

Para revisar **el archivo que ya generaste**, sin repetir la lectura de fotos:

```powershell
python .\prueba_nutricional.py --ficha .\ficha.json --salida .\revision.json
```

Ejemplo reproducible con un archivo que viene en el repositorio:

```powershell
python .\prueba_nutricional.py --ficha .\tests\nutricional\55527.json --categoria suplemento --salida .\revision.json
```

Para extraer y revisar en una sola ejecución:

```powershell
python .\prueba_nutricional.py --imagen .\tests\nutricional\55527.jpg --sku 55527 --categoria suplemento --evaluar --salida .\ficha_con_revision.json
```

La salida JSON conserva la extracción y agrega `revision_nutrimental`. Incluye contexto, aporte por base y por día cuando sea calculable, hallazgos por bloque (aporte, pertinencia, sustento científico, precauciones, coherencia y etiquetado), referencias, preguntas al proveedor y pendientes. Cada hallazgo incluye criterio, motivo, acción, incertidumbre, datos de origen y referencias cuando corresponden. Las advertencias conservan sus textos y fotos.

**Diego pidió dejar finalidad y población pendientes.** No se asignan por omisión. Los resultados reales de esta prueba son:

| Producto | Hallazgo documental |
|---|---|
| 55527 | El aporte elemental se identifica: 70 mg por porción y 70 mg/día según la instrucción visible de 2 tabletas al día. Es un dato declarado, no una recomendación. No puede concluirse adecuación ni beneficio sin contexto y evidencia. |
| 55541 | El consumo se interpreta como una porción al día y las masas de ocho compuestos suman 400 mg/día. Falta el magnesio elemental declarado: solicitarlo al proveedor; no calcularlo desde los compuestos. |
| 77755 | Se conserva lo declarado por 100 g y por envase. No se inventa tamaño de porción ni consumo diario, y no se aplican reglas de suplementos a un alimento. |

Los tres reportes quedan en `informacion_insuficiente` con motivos y acciones concretas. Ese estado refleja lo que todavía impide concluir. Las referencias institucionales no demuestran eficacia del producto terminado. **Esta versión no ingiere expedientes de estudios ni realiza una búsqueda clínica exhaustiva**: registra ese bloque como pendiente y solicita estudios comparables de ingrediente, forma, cantidad, población y finalidad. No libera productos ni recomienda tratamientos.

Reglas y cálculos en `revision_nutrimental.py`; referencias revisadas el 2026-11-24 en `docs/referencias_nutrimentales_v1.json` (NIH ODS, FDA y COFEPRIS). El catálogo y su huella quedan registrados en cada reporte. Las referencias estadounidenses se identifican como tales y **no se usan como límites legales mexicanos**. Son criterios documentales provisionales para esta prueba, no políticas de aprobación de SMN.

Ollama local (`qwen3:8b`, contexto 8192, temperatura 0, seed 42, máximo 1024 tokens) **solo prioriza IDs de hallazgos ya calculados**. No puede modificar cantidades, referencias, estados ni acciones. Python rechaza IDs inexistentes, duplicados, campos adicionales y respuestas truncadas; todos los hallazgos se conservan. Si Ollama falla, el informe determinista sigue disponible y muestra `ia.estado=no_disponible`. `--sin-ia-revision` omite esta llamada.

Opciones adicionales, sin valores supuestos:

- `--finalidad` y `--poblacion`: contexto libre proporcionado por el usuario.
- `--perfil`: perfil explícito del catálogo para una comparación descriptiva. Solo hay cuatro perfiles de adultos sanos de 19–30 o 31–50 años; mujeres sin embarazo/lactancia. El perfil define la población de referencia y no se combina con una población libre contradictoria. Se distingue ingesta total de referencia, valor diario de etiquetado y límite suplementario; no se interpreta un porcentaje como dosis eficaz, carencia o seguridad individual.
- `--porciones-dia`: escenario del usuario, identificado como tal; no reemplaza lo declarado ni prescribe una dosis. Si difiere de las instrucciones legibles, genera observación para revisión profesional.
- `--afirmacion`: afirmación propuesta por el usuario para revisar, repetible; no se presenta como lectura de la foto ni como beneficio demostrado.
- `--modelo-revision`: modelo Ollama para priorizar; por omisión usa el modelo de texto.

Solo se interpreta automáticamente un consumo diario inequívoco con una instrucción explícita del tipo «Tomar ... tabletas/cápsulas/piezas al día» y un tamaño de porción consistente. No se asume que porción y consumo diario sean lo mismo. Conflictos entre fotos, unidades fuera del catálogo y criterios sin cobertura requieren revisión.

Verificación de esta etapa:

```powershell
python -m unittest discover -s tests -p "test_*.py"
python tests/nutricional/ejecutar_revision_real.py
python tests/nutricional/verificar_revision_real.py
```

Pasaron **35 pruebas** (16 anteriores de extracción y 19 nuevas de reglas/integración con datos ficticios y respuestas simuladas). Además se ejecutaron tres priorizaciones **reales** con Ollama sobre fichas de inferencias visuales reales previamente guardadas; no se repitió OCR en esas ejecuciones. `ejecutar_revision_real.py` comprueba que las fichas originales no cambien. Se verificaron aparte los tres cotejos de extracción anteriores.

| SKU | prompt_eval_count | eval_count | done_reason | Contenido final |
|---|---:|---:|---|---|
| 55527 | 835 | 31 | stop | Sí |
| 55541 | 835 | 31 | stop | Sí |
| 77755 | 907 | 31 | stop | Sí |

Reportes completos: [revision_55527.json](revision_55527.json), [revision_55541.json](revision_55541.json) y [revision_77755.json](revision_77755.json), con resúmenes `.salida.txt` y respuestas originales `.revision.respuesta.json`. El archivo `ficha.json` del usuario no se modifica al exportar a otra ruta.

## Primera etapa: extracción

Prueba independiente de Python, sin integración con módulos, base de datos ni API externa. Las fotos son reales y públicas; las respuestas de `tests/test_prueba_nutricional.py` son ficticias y se usan únicamente para probar validadores.

Entorno observado el 24 de noviembre de 2026: Windows, Python 3.13.5, Pillow 12.3.0, Ollama 0.40.17 y RTX 4060 Laptop de 8 GB. No se descargaron modelos nuevos. Rama: `fix/prueba-nutricional-local`.

## Uso

Desde la raíz del repositorio:

```powershell
python -m pip install -r tests/nutricional/requirements.txt
python .\prueba_nutricional.py --imagen .\etiqueta.jpg --sku DEMO-001 --modelo qwen3-vl:4b-instruct --salida .\ficha.json
python .\prueba_nutricional.py --imagen .\trasera.jpg .\frontal.jpg --sku DEMO-001 --categoria alimento --modelo qwen3-vl:4b-instruct --salida .\ficha.json
python .\prueba_nutricional.py --imagen .\shampoo.jpg --categoria shampoo --salida .\shampoo.json
```

Pillow ya estaba instalado; el comando de instalación se proporciona como preparación, no como una instalación realizada en esta sesión. `--ollama` sigue siendo alias de `--modelo`. La categoría puede omitirse; si no se identifica, queda pendiente. Una categoría no alimentaria como shampoo da evaluación nutrimental `no aplica`, conservando lo visible.

La reducción conserva proporción, corrige orientación EXIF y no recorta. `--max-lado 0` conserva resolución. Cada foto conserva ruta original, dimensiones y SHA-256; el archivo original no se modifica. Las fotos adicionales corresponden al mismo producto: el usuario debe elegirlas así.

El flujo elegido separa lectura y estructura: `qwen3-vl:4b-instruct` recibe **cada fotografía real**, sin JSON forzado, con contexto 16384. `qwen3:8b` estructura exclusivamente las transcripciones recién generadas con contexto 8192. Ambos usan temperatura 0, seed 42, `think=false`, límite de salida 8192 y reducción proporcional a 1600 píxeles. Todo es local. El modelo de texto se cambia con `--modelo-texto` y su contexto con `--contexto-texto`. La prueba experimental de ficha directa sigue disponible con `--lectura-directa`; no es el flujo elegido.

Python reconoce tablas lineales con encabezados explícitos y una celda por columna, así como tablas de una columna con cantidades junto al nombre. Reconstruye sus celdas desde el OCR real, sin valores predefinidos, y registra cada ajuste. No asume coordenadas ni nombres de producto. La clasificación auxiliar de filas usa nombres de nutrimentos y formas de compuestos; las filas desconocidas conservan la sugerencia del modelo o quedan como `otro`. No se deduce una equivalencia química: solo se vincula una fila literal «Equivalente a» cuando hay un único compuesto precedente en esa base. Las cantidades permanecen las declaradas. Diseños o encabezados no reconocidos conservan la extracción del modelo y requieren revisión.

El resumen se imprime en consola. `--salida` guarda la ficha, `.lecturas.json` (transcripciones visuales reales) y `.respuesta.json` (estructura original con métricas). Nunca guarda `message.thinking`. La ficha registra las reconstrucciones y validaciones, conservando las respuestas originales para comparar. Una extracción inválida termina con código distinto de cero. Una respuesta truncada no se convierte en ficha ni se sustituye por datos de ejemplo.

## Diagnóstico observado

`ollama --version`, `ollama list`, `ollama show qwen3-vl:8b` y `ollama show qwen3-vl:4b-instruct` se ejecutaron; sus salidas están en los archivos `.txt` de esta carpeta. Ambos modelos admiten visión, Q4_K_M y contexto teórico 262144. La variante 8B instalada usa renderer/parser `qwen3-vl-thinking`; la 4B Instruct usa `qwen3-vl-instruct`.

Sondas directas a `/api/chat`, `think=false`, temperatura 0 y `num_predict=2048`:

| Modelo / entrada | num_ctx | prompt_eval_count | eval_count | done_reason | Contenido final |
|---|---:|---:|---:|---|---|
| 8B, texto | 4096 | 38 | 349 | stop | Sí |
| 8B, JPEG original 2000 × 2000 | 4096 | 3884 | 212 | length | No |
| 8B, imagen proporcional 1280 × 1280 | 4096 | 1640 | 2048 | length | No |
| 8B, imagen 1280, formato libre | 16384 | 1640 | 1420 | stop | Sí: compuesto 500 mg y equivalente 70 mg |
| 8B, imagen 1280, format=json | 16384 | 1640 | 1419 | stop | Sí: compuesto 500 mg y equivalente 70 mg |
| 4B Instruct, imagen 1280, format=json | 16384 | 1640 | 300 | stop | Sí, extracción parcial |

La imagen original agotó el contexto: 3884 + 212 = 4096. Reducirla liberó contexto, pero la variante Thinking todavía consumió 2048 tokens sin respuesta final. Ampliar a 16384 permitió terminar, con y sin `format=json`: no es exclusivamente un problema del formato. Se observó `thinking` incluso enviando `think=false`; no se inspecciona ni reproduce su contenido. No se atribuye esto a un fallo específico del servidor sin más pruebas.

`ollama ps` confirmó contexto efectivo 4096 y luego 16384. El 8B con contexto 16384 se distribuyó aproximadamente 33 % CPU / 67 % GPU; 4B Instruct cupo íntegramente en GPU. El máximo anunciado por el modelo no equivale al contexto asignado a una solicitud. Véase la definición de [`num_ctx` de Ollama](https://github.com/ollama/ollama/blob/main/docs/modelfile.mdx).

Las fichas complejas de 4B Instruct confundieron columnas y algunas unidades. Se conservaron los intentos con nombres `instruct` para diagnóstico, no como fichas aprobadas. También se probó el visual instalado `qwen3.5:4b`: generó equivalencias incompatibles que Python rechazó. Que un modelo termine con `stop` y JSON válido no garantiza una lectura correcta.

La ficha compleja directa de 8B se interrumpió deliberadamente por su demora y uso mixto de CPU/GPU, para dar paso a las otras pruebas; no se reporta como una inferencia completa ni como `length`. El texto de `qwen3:8b` con 8192 cabe completamente en GPU en esta máquina; con 16384 también descargó parte a CPU. Se eligieron contextos por estas mediciones, sin cambiar la configuración global de Ollama.

Ejecuciones de las fichas y experimentos (comandos realmente usados, además de las sondas anteriores):

```powershell
python tests/nutricional/probar_ocr.py
python tests/nutricional/probar_dos_pasos.py
python tests/nutricional/probar_texto.py
python prueba_nutricional.py --imagen tests/nutricional/55527.jpg --sku 55527 --modelo qwen3.5:4b --salida tests/nutricional/55527-qwen35.json
python prueba_nutricional.py --imagen tests/nutricional/55541.jpg --sku 55541 --modelo qwen3.5:4b --categoria suplemento --salida tests/nutricional/55541-qwen35.json
python tests/nutricional/ejecutar_reales.py --skus 55527 55541
python prueba_nutricional.py --imagen tests/nutricional/77755A.jpg --sku 77755 --categoria alimento --salida tests/nutricional/77755.json
python prueba_nutricional.py --imagen tests/nutricional/55527.jpg --sku 55527 --modelo qwen3-vl:4b-instruct --salida tests/nutricional/55527.json
python tests/nutricional/revisar_guardadas.py
```

Los dos comandos de qwen3.5 se ejecutaron durante el experimento de ficha visual directa, antes de que el flujo de dos pasos fuera el predeterminado; para repetir ese experimento con el script final hay que añadir `--lectura-directa`. `probar_texto.py` y `probar_dos_pasos.py` son experimentos con transcripciones **generadas por la inferencia real anterior**, no respuestas simuladas; conservan sus fallos. `ejecutar_reales.py` muestra los comandos completos de cada producto, invoca el extractor sin importar expectativas y conserva sus resúmenes `.salida.txt`.

La versión final también separa ingredientes y advertencias por encabezados y frases literales del OCR. `revisar_guardadas.py` reaplica exactamente el mismo procesamiento Python del extractor a las respuestas de inferencia real archivadas; no llama a Ollama, no corrige las transcripciones ni carga expectativas. Esto permitió revisar los últimos ajustes de secciones sin repetir las inferencias. Después se ejecutó otra vez el extractor completo del 55527 con la versión final: terminó correctamente.

Comandos de las sondas iniciales: `python tests/nutricional/diagnostico.py` y `python tests/nutricional/comparar.py`. Este último se ordenó después para usar la sonda parametrizable. Para reproducir cada condición aisladamente:

```powershell
python tests/nutricional/descargar_casos.py
python tests/nutricional/sonda_ollama.py --modelo qwen3-vl:8b --salida tests/nutricional/sonda-texto.json
python tests/nutricional/sonda_ollama.py --modelo qwen3-vl:8b --imagen tests/nutricional/55527.jpg --salida tests/nutricional/sonda-original.json
python tests/nutricional/sonda_ollama.py --modelo qwen3-vl:8b --imagen tests/nutricional/55527.jpg --max-lado 1280 --salida tests/nutricional/sonda-reducida.json
python tests/nutricional/sonda_ollama.py --modelo qwen3-vl:8b --imagen tests/nutricional/55527.jpg --max-lado 1280 --contexto 16384 --salida tests/nutricional/sonda-amplia.json
python tests/nutricional/sonda_ollama.py --modelo qwen3-vl:8b --imagen tests/nutricional/55527.jpg --max-lado 1280 --contexto 16384 --formato json --salida tests/nutricional/sonda-json.json
python tests/nutricional/sonda_ollama.py --modelo qwen3-vl:4b-instruct --imagen tests/nutricional/55527.jpg --max-lado 1280 --contexto 16384 --formato json --salida tests/nutricional/sonda-instruct.json
```

La copia `script_original.py` conserva el archivo recibido (que estaba sin seguimiento en Git), incluidos los ejemplos Vidanat. Sus transcripciones no se importan ni se entregan al modelo. `descargar_casos.py` y `casos_reales.json` contienen las fuentes y expectativas de cotejo, exclusivamente como datos de prueba.

## Validación

```powershell
python -m unittest discover -s tests -p test_prueba_nutricional.py -v
python tests/nutricional/verificar_reales.py
```

La primera orden utiliza respuestas simuladas y no hace inferencias. Verifica respuesta vacía con `length` (72 y 2872 tokens), truncamiento aunque el JSON sea parseable, cero frente a ausencia, unidades y fuentes inválidas, no inferencia de elemental, conservación de equivalencias, duplicación de bases y operaciones decimales. La segunda coteja archivos de inferencia real con la lectura manual y verifica las huellas de sus fotos; no genera ni corrige las fichas.

Resultado: **16 pruebas simuladas en verde y los tres cotejos de inferencia real correctos**. Los tres productos se leyeron con su foto trasera sola. Dos fotos y shampoo se cubren con pruebas simuladas de las reglas; no se presentan como inferencias reales de esos casos.

| SKU | Visión: prompt / salida | Estructura: prompt / salida | Fin en ambas etapas | Cantidades de la ficha |
|---|---|---|---|---:|
| 55527 | 2625 / 318 | 729 / 1753 | stop, contenido final | 21 |
| 55541 | 2625 / 505 | 915 / 6039 | stop, contenido final | 33 |
| 77755 | 2625 / 693 | 1114 / 2345 | stop, contenido final | 16 |

Salidas completas: [55527.json](55527.json), [55541.json](55541.json), [77755.json](77755.json), y sus correspondientes `.salida.txt`. Sus `.lecturas.json` y `.respuesta.json` conservan las dos etapas originales para auditar cada reconstrucción.

- **55527:** Glicinato de Magnesio, 2 tabletas (1200 mg), 30 porciones por frasco, biglicinato 500 mg y equivalente declarado de magnesio 70 mg por porción. Se conservan además 41667 mg de compuesto y 5833 mg de magnesio por 100 g y las equivalencias explícitas. Categoría pendiente: no se proporcionó ni se lee expresamente en la foto.
- **55541:** 8 Magnesios, 2 tabletas (1020 mg), 30 porciones por frasco; citrato de trimagnesio anhidro, aminoquelado biglicinato, cloruro hexahidratado, óxido, L-treonato, taurato, gluconato y malato dihidratado: **50 mg de cada uno por porción**. Suma Python **400 mg de compuestos**. Magnesio elemental **no declarado en la foto**, sin calcularlo ni inventar equivalencias. Se conservan también los 4902 mg por 100 g de cada compuesto.

El cotejo visual de galletas 77755 confirmó por 100 g: energía 420.4 kcal / 1774.7 kJ, proteínas 8.4 g, grasas totales 9.6 g, saturadas 1.2 g, trans **0 mg**, poliinsaturadas 1.6 g, monoinsaturadas 6.3 g, colesterol 1.3 mg, carbohidratos 75.1 g, azúcares 2.5 g, añadidos **0 g**, fibra 2.3 g y sodio **460 mg**. La foto también declara energía por envase. No muestra tamaño de porción ni porciones por envase. La primera extracción omitió kJ y se conserva como intento, no como extracción exhaustiva.

Las citas literales son transcripciones del modelo, no una validación óptica independiente. Python valida estructura, números, unidades, fuentes, duplicados y cálculos; el cotejo humano contra la fotografía comprueba lectura y cobertura. No se emite dictamen sanitario.

El cotejo numérico no certifica la ortografía de todos los ingredientes: se observaron errores OCR como `microcrystallina` y `achiete`. Se conserva lo que devolvió la lectura, con su foto, para corregirlo tras revisión; no se sustituye por una composición supuesta. El catálogo de unidades está en `UNIDADES`; las no admitidas se rechazan para no reinterpretarlas silenciosamente.
