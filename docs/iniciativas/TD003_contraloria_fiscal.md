# TD003 · Contraloría / Fiscal

Iniciativa de Transformación Digital abierta el 2026-10-28. Módulo `contraloria` en la plataforma, estado piloto.

## Procesos

| Proceso | Estado | Nota |
|---|---|---|
| Proceso de la DIOT | Piloto con ODP | Declaración Informativa de Operaciones con Terceros. Construido con los papeles de trabajo de agosto y septiembre de 2026 de ODP. Faltan las otras 2 empresas. |

## Proceso de la DIOT

### Cómo se hace hoy (papel de trabajo «MMAA DIOT ODP.xlsx»)

1. Fiscal descarga del portal SM 3 reportes: impuestos de tesorería, aplicaciones de cuentas por pagar y auxiliar de IVA acreditable.
2. Del Explorador de Intelisis saca los gastos comprobados y la caja chica («Gtos detalles → DIOT»), el catálogo de proveedores y el auxiliar de IVA retenido (2500-002-007).
3. En el libro arma la hoja IVAC (por grupo), un pivote por RFC, la hoja «AMARRE VS CFDI-COMPLEMENTO-BCOS» (con importes tecleados a mano), redondea al peso («DIOT AL PESO») y copia al LAYOUT, que se guarda como TXT de 54 campos.

### Qué hace la plataforma

Pantalla: Contraloría y Fiscal → Proceso de la DIOT (`/contraloria/diot`).

1. **Empresa y periodo.** Un periodo por empresa y mes; estados abierto, procesado y cerrado (ya se presentó).
2. **Documentos.**
   - Se suben como se descargan: el .xls del portal (que en realidad es HTML), .xlsx y .csv.
   - Cada uno se reconoce por sus columnas, no por su nombre. Si no se reconoce, se puede elegir el tipo a mano y se valida que traiga las columnas.
   - Si falta un obligatorio, no se procesa.
   - Cada documento queda guardado con su huella SHA-256; si se reemplaza, el anterior queda en la historia.
3. **Proceso, con los mismos pasos que sigue Fiscal** (diagrama «TD007 | DIOT – Contraloría Proceso Actual»). Cada «Procesar» es una corrida que se ve en vivo y deja bitácora; si un paso no se completa, el proceso se detiene ahí y los siguientes quedan «no se ejecutó».
   1. Extraer reportes: revisa que estén los documentos obligatorios con sus columnas y cuenta errores de Excel.
   2. Consolidar y organizar: empresa, catálogo de proveedores, tipos de cambio por póliza, tipos de operación por RFC.
   3. Limpiar y clasificar: aplica las reglas de cada reporte, marca renglones idénticos (posibles duplicados), los que no tienen RFC y valida el formato del RFC.
   4. Conciliar IVA acreditable contra el auxiliar, por movimiento: tesorería por «Origen OrigenID» = «Mov MovID»; gastos y caja chica por póliza; aplicaciones de CxP por movimiento. Tolerancia de $1.00 por movimiento. El «Pago Prov Imptos» (pago del IVA del mes anterior) no se concilia. Decisión «¿Conciliación correcta?».
   5. Revisar diferencias: cada diferencia queda como incidencia. Si se compensa dentro del mismo grupo (por ejemplo, una devolución en otra póliza) es «controlado»; si no, «posible impacto» y bloquea el TXT.
   6. Generar archivo DIOT (TXT): aplica los ajustes de Fiscal, consolida por RFC, redondea y arma el layout.
   7. Validar archivo: 12 verificaciones (CRLF, ASCII, 54 campos, renglones contra consolidado, tipos de tercero y operación, RFC, registros únicos, importes enteros, renglones con importe, IVA contra base ±1, totales). Si una falla, no hay TXT.
   8. Entregar archivo: TXT validado y evidencia; no se entrega mientras haya incidencias de posible impacto sin revisar.
   - Fuera de la plataforma: Fiscal valida el TXT con la herramienta del SAT y presenta.
   - Renglones idénticos en los reportes (agosto: 6 en tesorería, 1 en el Explorador): se cuentan, igual que en el papel de trabajo, y quedan como incidencia «controlado» para que Fiscal confirme.
   - Cruces, clasificación y consolidado por RFC con las reglas de abajo.
   - Se calcula con todos los decimales y se redondea al peso por tercero y campo (mitad hacia arriba).
   - La IA no participa. Lo que no tiene regla no se vuelve cero: queda como incidencia.
4. **Incidencias** en 3 niveles: sin impacto, controlado y posible impacto.
   - Las de posible impacto bloquean el TXT hasta que alguien las marca revisadas con una nota.
   - La revisión se conserva al volver a procesar si la incidencia sale igual.
5. **Consolidado por tercero** con trazabilidad: cada tercero abre los renglones de los reportes que lo formaron y la regla aplicada.
6. **Ajustes de Fiscal.** Lo que Fiscal decide a mano, siempre con motivo:
   - sumar o restar a un campo;
   - quitar o agregar un tercero;
   - cambiar el tipo de tercero o de operación.

   Cada ajuste queda en la bitácora y en la evidencia.
7. **Salidas.**
   - TXT de carga: 54 campos separados por `|`, CRLF, ASCII.
   - Evidencia en Excel con las hojas Consolidado, Operaciones, Incidencias, Ajustes de Fiscal, Documentos, Reglas y Bitácora (la última corrida).
8. **Comparación** contra el TXT que Fiscal ya presentó, campo por campo. Ese TXT solo se usa para comparar; nunca se copia al resultado.

### Documentos que lee

| Documento | Obligatorio | De dónde sale |
|---|---|---|
| Reporte impuestos tesorería | Sí | Portal SM |
| Rep apps cuentas por pagar | Sí | Portal SM |
| Reporte auxiliar IVA acreditable | Sí | Portal SM |
| Explorador de gastos (DIOT) | Sí | Intelisis, «Gtos detalles → DIOT» |
| Catálogo de proveedores | Sí | Intelisis |
| Auxiliar IVA retenido 2500-002-007 | No. Si falta, el IVA retenido sale en cero con aviso. | Intelisis / contabilidad |
| Tipos de operación por RFC | No. Si falta, todos van como 02 con aviso. | Lista de Fiscal (hoja RETENCIONES) |

**Se suben los archivos tal como los entrega Fiscal** (uno por uno o un .zip con todo):
- Los 3 reportes del portal se reconocen por sus columnas.
- Del papel de trabajo «MMAA DIOT <EMPRESA>.xlsx» la plataforma toma solo 4 hojas que son reportes pegados tal cual: «ComprobantesExp» (Explorador de gastos, columnas A a Y), «Proveedores», «IVARetenido» y «RETENCIONES» (tipos de operación). Nunca lee las hojas calculadas (IVAC, AMARRE, DIOT AL PESO) ni históricos con la misma forma (IVARetenidoD). Se ignoran los renglones que solo traen fórmulas arrastradas y los errores de Excel en columnas que el proceso no usa.
- El LAYOUT ya llenado se marca «no se usa»: trae el resultado.
- El TXT presentado («CARGA DIOT») se guarda solo para comparar.

Mientras Intelisis no entregue esas 4 hojas como archivos aparte, el proceso depende de que Fiscal las pegue en su libro como hoy; el resultado no usa ningún valor calculado del libro.

### Reglas implementadas

Desde el 2026-10-30 las reglas viven en la **Base de conocimiento fiscal** (ver abajo) y el proceso las lee de ahí. La carga inicial está en `api/modulos/contraloria/diot_criterios.py` (`SISTEMA`) y `conocimiento_fiscal.py`; el motor (`diot_motor.py`) solo aplica lo que diga la base para la fecha del periodo. Lo que sigue describe la carga inicial.

- **Tesorería**
  - Abonos y cargos bancarios no van (TES-BANCO).
  - «ANTICIPO SF …» (sin factura) no va al pagarse; se declara al aplicarse, con aviso controlado (TES-ANTICIPO-SF).
  - Concepto exactamente «ANTICIPO» (gastos a comprobar) no va; se declara con su comprobante (TES-ANTICIPO). «ANTICIPO PROVEEDOR» y «ANTICIPO ACREEDOR» sí van con su tasa.
  - Reembolsos de caja chica (referencia «Caja Chica», «REEM CC», «CC …») no van; van sus comprobantes (TES-CAJA-CHICA).
  - Nómina, finiquitos, ISR, IMSS de nómina, FONACOT y caja de ahorro no van (TES-NOMINA).
  - Pago al IMSS (por RFC o por nombre) va como no objeto (TES-IMSS). Si el concepto dice «retiro», sale una incidencia de posible impacto porque puede incluir INFONAVIT.
  - Pagos a la propia empresa no van (TES-PROPIA).
  - Con tasa (TES-TASA):
    - IVA = Importe1 × tipo de cambio.
    - Base 16 % = IVA / 0.16.
    - Con tasa 0, base 0 = SubTotal × tipo de cambio.
  - Sin tasa ni regla: no va y sale incidencia de posible impacto (TES-SIN-TASA).
  - El RFC sale del reporte o, si no viene, del catálogo por la clave de contacto.
- **Aplicaciones de CxP**
  - Solo «Aplicacion» con IVA.
  - Base = (SubTotal + IEPS) × tipo de cambio del auxiliar de IVA; IVA = Importe1 × tipo de cambio (APL-APLICACION).
  - Si la póliza no está en el auxiliar, usa el tipo de cambio del reporte, con aviso controlado.
- **Explorador de gastos**
  - Solo comprobantes CONCLUIDOS cuya póliza (Poliza + PolizaID) está en el auxiliar de IVA acreditable del mes (COM-AUXILIAR).
  - Base = Cantidad × Precio × tipo de cambio; IVA = base × % IVA (COM-TASA).
  - Sin IVA: «agua de garrafón» va a tasa 0 (COM-TASA0); lo demás va como no objeto, con aviso controlado (COM-NO-OBJETO).
  - Gastos a nombre de la propia empresa no van (COM-PROPIA).
  - RFC del catálogo por la clave de acreedor; sin RFC → incidencia de posible impacto.
- **IVA retenido.** Haber menos debe del auxiliar 2500-002-007, asignado al acreedor del comprobante de la misma póliza (RET-AUXILIAR).
- **Consolidado**
  - Por RFC.
  - Tipo de tercero (TER-TIPO-TERCERO): 15 para el RFC genérico XAXX010101000, 05 para XEXX010101000 (extranjero), 04 para un RFC mexicano válido. Un RFC inválido ya no se marca 05: sale incidencia y no tiene tipo.
  - Tope del global: si el renglón 15 pasa del 10 % del total de los pagos, sale incidencia.
  - Tipo de operación (TER-TIPO-OPERACION): 85 para el 15, 07 para el 05, la lista de Fiscal y, si no está, 02. **Pendiente de Fiscal**: su lista dice 85 para compras, pero los TXT presentados usan 02.
  - Redondeo (TER-REDONDEO): al final, sobre cada importe ya sumado por tercero y campo. **Pendiente de Fiscal**: los importes que terminan exactamente en 50 centavos se presentaron hacia arriba y el art. 20 CFF dice hacia abajo. Hoy suben; el mes en que aparece uno, sale incidencia.
  - IMSS va como no objeto; INFONAVIT no se declara (si el pago al IMSS incluye «retiro», aviso para restarlo con un ajuste). El impuesto sobre nómina no se declara; predial y derechos van como no objeto.
  - Un gasto de agua sin IVA sale como incidencia «debería llevar IVA» (Fiscal: 16 % tiendas y oficinas, 8 % zona fronteriza). En agosto salió «ODP AGUA POTABLE».
  - Si un tercero trae negativos, importes al 8 % o exentos, queda en «revisar» y no se genera el TXT. El campo del layout para 8 % y exento no está confirmado.
- **Layout TXT.** Se llenan estos campos y los demás quedan vacíos:

  | Campo | Contenido |
  |---|---|
  | 1 | Tipo de tercero |
  | 2 | Tipo de operación |
  | 3 | RFC |
  | 12 | Base 16 % |
  | 22 | IVA 16 % |
  | 48 | IVA retenido |
  | 51 | Base 0 % |
  | 52 | No objeto |
  | 54 | «01» |

### Resultado contra lo que Fiscal presentó (ODP)

| Mes | Renglones del sistema | Presentados | Idénticos |
|---|---|---|---|
| Agosto 2026 | 81 | 81 | 77 |
| Septiembre 2026 | 67 | 69 | 63 |

Diferencias de agosto:
- 3 redondeos de ±1 en IVA.
- Un proveedor persona física que Fiscal quitó.
- El renglón global XAXX010101000 (tipo 15/85, base 35), que Fiscal agregó a mano.
- Base 0 y no objeto cuadran exacto.

Diferencias de septiembre:
- IMSS: Fiscal separó el pago bimestral en IMSS e INFONAVIT.
- GAL070220T56: Fiscal declaró un «ANTICIPO SF PROVEEDOR» como base 0.
- PIC100304TK3 y USS000718PA0: +1 en base e IVA.
- Un proveedor persona física con renglones extra de «libros de julio».
- El IVA retenido cuadra (640).

Todas las diferencias son ajustes manuales del papel de trabajo; se pueden capturar en la plataforma como ajustes de Fiscal con su motivo.

La prueba `test_validacion_con_los_archivos_de_fiscal` (en `api/tests/test_diot.py`) corre estas comparaciones si los archivos reales están en el equipo, fuera del repositorio (`DIOT_ARCHIVOS_REALES`). Si no están, se omite.

Lo que sigue dependiendo de Fiscal:
- los ajustes manuales de arriba;
- la lista de tipos de operación;
- la clasificación de lo que salga como incidencia.

El cálculo y el TXT ya no dependen de valores precalculados del Excel final. Sin embargo, en el piloto el Explorador, el catálogo y el auxiliar de retenido sí salieron del papel de trabajo.

### Preguntas para Fiscal

1. **Redondeos de ±1.** En agosto hubo 3 proveedores con ±1 en IVA; en septiembre, PIC100304TK3 y USS000718PA0 con +1 en base e IVA. ¿Se ajustan para cuadrar contra algo (CFDI, auxiliar)? ¿Cuál es la regla?
2. **Proveedor persona física quitado en agosto.** ¿Por qué no se declaró? ¿Es una regla (por ejemplo, ya declarado en otro mes, o gasto no deducible)?
3. **Renglón global XAXX010101000 (tipo 15/85, base 35) en agosto.** ¿De dónde sale y cuándo se agrega?
4. **«ANTICIPO SF PROVEEDOR» de GAL070220T56 en septiembre, declarado como base 0.** La regla general que vimos es no declarar el anticipo sin factura hasta aplicarlo. ¿Cuál aplica?
5. **IMSS e INFONAVIT.** En septiembre el pago bimestral se separó en IMSS e INFONAVIT. ¿De qué documento sale la parte del INFONAVIT (cédula, SUA)? ¿Podemos recibirlo cada bimestre?
6. **FONACOT.** En agosto no se declaró. ¿Nunca va?
7. **Renglones «extra libros de julio» en septiembre.** ¿Son comprobantes de un mes anterior que entran tarde? ¿Cómo se identifican en Intelisis?
8. **Tasa 0 contra no objeto.** Hoy solo «agua de garrafón» va a tasa 0. DAP, agua potable del municipio, protección civil y donativos van como no objeto. ¿Está bien? ¿Hay más conceptos a tasa 0?
9. **Campo 54 y campos para 8 % y exento.** ¿Qué significa el «01» del campo 54? Si algún mes aparecen importes al 8 % o exentos, ¿en qué campos del layout van?
10. **Amarre contra CFDI y complementos de pago.** La hoja «AMARRE VS CFDI-COMPLEMENTO-BCOS» cruza contra CFDI recibidos y complementos. ¿Nos pueden dar esas descargas para hacer ese cruce en una fase 2? ¿También la lista 69-B?
11. **Exportes de Intelisis.** ¿Pueden entregar cada mes estos archivos aparte, sin pasar por el papel de trabajo?
    - El Explorador de gastos.
    - El catálogo de proveedores.
    - El auxiliar 2500-002-007.

### Respuestas de Fiscal (2026-10-30)

A las 9 preguntas del plan «Plan DIOT: reglas de Fiscal y base de conocimiento fiscal» (https://claude.ai/artifact/T4F7px8T2gqLpfCQorzQpe):

1. Redondeo: se suma todo y se redondea al final. Abierto: los 50 centavos exactos.
2. Extranjero: tercero 05 con operación 07.
3. INFONAVIT se descarta; IMSS como no objeto.
4. Impuesto sobre nómina no se declara; predial y derechos, no objeto.
5. Recibo de agua: 16 % tiendas y oficinas; 8 % zona fronteriza.
6. Tercero 15: tope de 10 % del total de los pagos, con el RFC genérico.
7. Marca de extranjero en Intelisis: no aplica.
8. Campos para 8 %, exento e importación: no aplica por ahora (siguen bloqueando el TXT si aparecen).
9. Layout: el vigente (54 campos, registrado en la base).

Quedan pendientes de aprobar en la base: TER-REDONDEO (50 centavos) y TER-TIPO-OPERACION (02 o 85).

### Base de conocimiento fiscal

Pantalla `/contraloria/conocimiento` (tarjeta en Contraloría / Fiscal). Migración `0033`.

- **Criterios** (`contraloria.fiscal_criterio`): 21 del sistema más los propios que capture Fiscal (condición fija sobre reporte, campo y valor; acción: excluir, tasa 0, no objeto, exento o tipo de operación). Cada cambio es una versión nueva con «vale desde»; la anterior se cierra un día antes. Estados: borrador, pendiente, aprobado, retirado. Historial de cada cambio con motivo (`fiscal_criterio_cambio`).
- **Catálogos y layout** (`fiscal_catalogo`): tipos de tercero, tipos de operación y mapa del TXT, con vigencia.
- **Documentos de soporte** (`fiscal_documento`): archivo con huella SHA-256, versión y vigencia; una versión nueva reemplaza a la anterior y los criterios pasan a citarla.
- Un criterio del sistema pendiente se sigue aplicando, pero el mes en que cambia el resultado sale incidencia; un criterio propio pendiente no se aplica.
- «Probar con un periodo» corre el proceso con lo vigente, sin guardar, y lo compara contra lo último procesado.
- Cada corrida guarda el resumen de criterios que usó (`diot_corrida.criterios`). El Excel de evidencia trae las hojas «Criterios» y «Layout y catálogos».
- Aprobar o regresar pide el permiso `contraloria.criterios.aprobar` (admin y `contraloria_fiscal`). Cambiar pide `contraloria.diot.operar`.
- Sin IA.

Resultado con los archivos reales después del cambio: agosto 77/81 y septiembre 63/69 idénticos (sin cambio).

### Validar el TXT sin ser fiscalista (2026-10-30)

Plan «Plan DIOT: validar el TXT sin ser fiscalista» (https://claude.ai/artifact/UVXVypFXCf9PPred77VV8F), fases 1 y 2 construidas (migración `0034`). La pantalla va en 4 pasos: **Subir y procesar → Resolver pendientes → Validar → Firmar y descargar**, con una frase arriba que dice cómo va el mes, «Proveedores en palabras», un glosario y la «Vista para Fiscal» con las pestañas técnicas de antes.

Las 7 comprobaciones (cada una con semáforo y una frase con el número que la respalda):

1. **Cuadra con contabilidad:** IVA del TXT contra el auxiliar de IVA; tolerancia de medio peso por proveedor por el redondeo, más los ajustes de Fiscal y los RFC excluidos.
2. **Ningún pago sin explicar (embudo):** cada renglón de cada reporte entra a la DIOT o tiene su razón escrita (nómina, banco, anticipos, caja chica…). Los montos del embudo son solo para ubicarse; no se usan en el cálculo.
3. **Cuadra con la declaración de IVA:** se captura el IVA acreditable de la declaración mensual (lo da Fiscal).
4. **Cada proveedor se puede rastrear:** muestra de los 10 con más IVA más 5 al azar (fijos por periodo); alguien marca que sus pagos y facturas cuadran. Si el proveedor cambia al reprocesar, la marca se pierde.
5. **Cambios contra el mes anterior:** proveedores nuevos, los que se fueron y cambios de más de 30 % (y más de $10,000). Solo para mirar.
6. **Formato que acepta el SAT:** las 12 verificaciones del TXT, en palabras.
7. **Contra lo presentado** (solo en el piloto): cada proveedor con diferencia necesita un motivo (ajuste de Fiscal, criterio, error de la plataforma, error en lo presentado u otro con nota).

Firmas: «Revisé las comprobaciones» (quien opera, solo con todo en verde o explicado) y «Visto bueno de Fiscal» (otra persona, con `contraloria.criterios.aprobar`). Valen para ese TXT: si al reprocesar cambia, hay que firmar otra vez. **Mientras dure el piloto las firmas no son obligatorias para descargar** (`FIRMAS_OBLIGATORIAS = False` en `diot_validacion.py`), hasta que Fiscal esté de acuerdo. La evidencia en Excel abre con una hoja «Resumen» con las comprobaciones y las firmas.

Un periodo abierto por error se borra con «Borrar este periodo» (paso 1): quita documentos, resultado, decisiones, ajustes, firmas y corridas, y queda en la bitácora. Un periodo cerrado primero se reabre.

Con los archivos reales: agosto IVA $1,383,691 contra $1,383,693 en contabilidad; septiembre $1,404,639 contra $1,404,640. Agosto y septiembre tienen 3 decisiones pendientes cada uno.

### Datos fiscales y seguridad

- Los RFC de proveedores se guardan solo en el esquema `contraloria` (módulo independiente; decisión del 2026-10-28). No se cargan en Compras ni en SMNBI.
- Nada de la DIOT sale a servicios externos y la DIOT no usa IA. Si después se agrega, será solo Ollama local y el proceso debe funcionar sin ella.
- Las pruebas del repositorio usan datos ficticios; los archivos reales viven fuera del repositorio.

## En la plataforma

- Módulo `contraloria` (TD003), área «Contraloría / Fiscal».
- Permisos: `contraloria.diot.ver`, `contraloria.diot.operar`, `contraloria.criterios.aprobar`.
- Rol: `contraloria_fiscal` (Contraloría / Fiscal).
- Código:
  - `api/modulos/contraloria/`:
    - `diot_lectura.py`: lectura y reconocimiento.
    - `diot_motor.py`: aplica los criterios.
    - `diot_criterios.py`: carga inicial de criterios y configuración.
    - `conocimiento_fiscal.py` y `rutas_conocimiento_fiscal.py`: base de conocimiento fiscal (`/api/contraloria/conocimiento`).
    - `diot_layout.py`: TXT y comparación.
    - `diot.py`: guardar y procesar.
    - `diot_validacion.py`: las 7 comprobaciones, la muestra y las firmas.
    - `rutas_diot.py`: `/api/contraloria/diot`.
    - `modelos_diot.py`.
  - Migración `0025`: esquema `contraloria`, 7 tablas y la empresa ODP.
  - Migración `0034`: comprobaciones (monto por renglón, IVA declarado, `diot_revision`, `diot_firma`).
  - Web: `web/app/(interno)/contraloria/diot/page.tsx`, `guia.tsx` (los 4 pasos), `web/lib/diot.ts` y `web/lib/diot-validacion.ts`.
  - DBML: `docs/modelos/contraloria_diot_v0.dbml`.
  - Pruebas: `api/tests/test_diot.py`, `api/tests/test_diot_validacion.py` y `api/tests/test_conocimiento_fiscal.py`.
- Empresas (migración `0035`): SMN · Super Mayoreo Naturista, ODP · Operadora y Distribuidora de Productos Naturistas y PS · Promotora Saludanat. El RFC de SMN y PS lo captura en la pantalla quien tenga `contraloria.criterios.aprobar` cuando Fiscal lo confirme; sin RFC el mes no se procesa (con él se separan los pagos de la empresa a sí misma).
