# Diseño del ETL de ventas (SMNBI → plataforma)

Propuesta del 21 oct 2026, para revisión de Transformación Digital. **No hay carga corriendo**: este documento solo dice qué se trae, cómo se transforma y qué falta confirmar con Sistemas. Las tablas están en [`docs/modelos/datos_ventas_v0.dbml`](../modelos/datos_ventas_v0.dbml).

## Qué se trae

| De SMNBI | A la plataforma | Para qué |
|---|---|---|
| `tblArticulos` | `datos.producto` (campos nuevos: categoría, fabricante, tipo de compra, estatus) | Catálogo con la clasificación de Intelisis |
| `tblVenta.Sucursal` | `datos.tienda` (solo el código; nombre y formato cuando llegue el catálogo) | Venta por tienda |
| `tblVenta` + `tblVentaD` | `datos.venta_semanal`, ya sumada por producto, tienda y semana | Semáforo de productos: venta, margen, tickets, comparables |

No se traen tickets ni clientes uno por uno: SMNBI hace la suma y la plataforma solo recibe el resultado. Así se mueven miles de filas por semana y no millones, y no se guardan datos de clientes.

## Reglas de transformación

1. **Solo ventas cerradas:** `tblVenta.Estatus = 'CONCLUIDO'`. Quedan fuera las 3 en PROCESAR.
2. **Tipo de movimiento:**
   - `Nota`: venta.
   - `Nota Devolucion` y `Devolucion Venta`: devolución; resta piezas e importe y se guarda aparte en `piezas_devueltas`. La Nota Devolucion ya viene en negativo y la Devolucion Venta en positivo: se toma el valor absoluto y se resta.
   - `Bonificacion Venta`: fuera, porque no es venta de producto.
   - `Factura Electronica`: **cuenta** (26 oct): es venta de mayoreo y canales desde almacenes que no son tiendas, ~22 % de la venta; no repite las Notas. Se puede apagar en Configuración.
3. **Renglones que no son producto:** fuera las unidades `FLETETV`, `Actividad` y `SERVICIO`, y cualquier artículo que no esté en `tblArticulos` (se cuentan en el cuadre como «renglones fuera»).
4. **Piezas:** `Cantidad × Factor`, para que PAQUETE y CAJA se conviertan a piezas.
5. **Importe bruto:** `Cantidad × Precio` por renglón. `Precio` es por la unidad del renglón (confirmado el 26 oct) y, por lo que cuadra con el encabezado, sin IVA.
6. **Descuento:** `DescuentoLinea` y `DescuentoGlobal` son porcentajes (26 oct). En pesos: `Cantidad × Precio × (1 − (1 − línea/100) × (1 − global/100))`.
7. **Costo:** `Cantidad × Costo` por renglón. Sirve para el margen histórico; no es el costo de compra vigente.
8. **Semana:** lunes de la semana de `FechaMov` (semana ISO). Una venta del domingo cuenta en la semana que empezó el lunes anterior.
9. **Tienda:** `Almacen`, que liga con el catálogo `tblAlmacenes`. `Sucursal` viene vacía en el 99 % de las ventas (revisión del 26 oct, [`revision_smnbi_2026-10-26.md`](revision_smnbi_2026-10-26.md)).
10. **Tickets:** número de `tblVenta.ID` distintos que traen el producto en esa tienda y semana.
11. **Empresa:** se guarda (PS / VCE) para poder separarla después; LAB tiene una sola venta.
12. **Membresía:** vacío hasta saber cómo distinguir socios (pregunta 7).

## Cómo corre

- **Credenciales:** usuario de solo lectura de SMNBI, capturado en Configuración y guardado cifrado, como las demás claves. Nunca en el chat ni en archivos.
- **Primera carga:** mes por mes (ene a sep 2026), para no pedirle a SMNBI una consulta enorme de golpe.
- **Cargas siguientes:** cuando se lance desde la plataforma (DECISIONES 2026-10-15), se vuelven a traer las **últimas 8 semanas** completas. Así entran ventas que se cerraron tarde o se corrigieron. Las semanas que trae se borran y se insertan en una sola transacción, así que repetir una carga no duplica nada.
- **Cuadre:** al final de cada carga se suma lo mismo en SMNBI y en la plataforma, por mes y empresa. Si no cuadra (diferencia mayor a 0.01 %), la carga queda marcada y se avisa en la campana.
- **Bitácora:** cada carga queda en `datos.carga` (fuente ETL_VENTAS, semanas desde/hasta) y se ve en Centro de datos → Cargas.

## Cómo probar las reglas antes de construir

[`consulta_venta_semanal.sql`](consulta_venta_semanal.sql) aplica las reglas de arriba a **un solo mes** y regresa la venta sumada por producto, tienda y semana. Se corre en SSMS con el acceso de solo lectura y solo lee. También trae un cuadre del mes para comparar contra lo que Sistemas o Finanzas reporten.

Si el total del mes se parece a lo que Finanzas conoce, las reglas van bien. Si sale muy arriba, lo más probable es la Factura Electronica (doble conteo) o el `Precio` por paquete.

## Lo que falta de Sistemas para cerrarlo

Las preguntas 3, 5, 6 y 7 de [`revision_smnbi_2026-10-21.md`](revision_smnbi_2026-10-21.md) cambian números; las demás no detienen el diseño. Además, para que la plataforma corra el ETL sola necesita:

1. Que el servidor de la plataforma pueda llegar a SMNBI por la red, o un acuerdo de cómo se entregan los datos.
2. Un usuario de solo lectura para la plataforma, distinto del de Diego.
