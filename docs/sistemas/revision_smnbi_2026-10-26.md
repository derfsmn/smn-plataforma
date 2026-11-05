# Revisión de SMNBI con las tablas nuevas (26 oct 2026)

Fuente: resultados de `consultas_para_claude_2026-10-26.sql` (11 consultas) que Transformación Digital corrió en SSMS con el acceso de solo lectura. Solo estructura, conteos y totales; no se guardan los ejemplos de compras ni de proveedores.

## Tablas

| Tabla | Filas | Qué trae |
|---|---|---|
| `tblAlmacenes` | 213 | **Catálogo de tiendas**: `Almacen` (código), `Nombre`, dirección, `Poblacion`, `Estado`, `CodigoPostal`, `Grupo`, `Ruta` (TIENDAS), `Sucursal` (número), `Estatus`, `Region`, `Categoria` (C, MAY…), `FechaApertura`, latitud y longitud |
| `tblArticulos` | 5,795 | Igual que el 21 oct (16 columnas) |
| `tblCompra` | 184,039 | Encabezado de compras: `TipoMov` (Orden Compra, Entrada Compra, Devolucion Compra…), fecha, `Almacen`, `Proveedor`, `Estatus`, `Importe`, `Impuestos`, `Origen` y `OrigenID` (la entrada dice de qué orden viene) |
| `tblCompraD` | 936,766 | Renglones: `Articulo`, `Cantidad`, `Unidad`, `Factor`, `Costo` |
| `tblInventario` | 915,577 | Existencia y `CostoPromedio` por empresa, almacén y artículo, con `FechaCorte` (el ejemplo es del 22 oct 2026) |
| `tblProveedores` | 1,529 | Código, nombre, estatus, condición de pago, descuentos, `DiasEntrega`, penalización, Agente y RFC (desde 2026-11-03 se traen Agente y RFC, aunque vengan vacíos) |
| `tblVenta` / `tblVentaD` | 5,871,196 / 15,307,091 | Sin cambio: ventas del 1 ene al 30 sep 2026 |

## Lo que cambia en el ETL de ventas (ya corregido)

1. **La tienda es el `Almacen`, no la `Sucursal`.** En 2026, 5,828,330 ventas (99.3 %) traen `Sucursal` vacía, repartidas en 198 almacenes. El ETL agrupaba por `Sucursal` y habría juntado casi todo en una sola «tienda» vacía. Ahora agrupa por `Almacen`, que liga con `tblAlmacenes`.
2. **Devoluciones.** En septiembre, «Nota Devolucion» trae los renglones en negativo (-10,654) y «Devolucion Venta» en positivo (42,617). Con el signo que aplicaba el ETL, las Notas Devolución se habrían **sumado** a la venta. Ahora se toma el valor absoluto y se resta en las dos.
3. **Precio es por la unidad del renglón** (pregunta 5, contestada): en 20 artículos vendidos por pieza y por paquete, el precio del paquete entre su factor da casi el precio de la pieza (por ejemplo 101.39 / 5 = 20.28 contra 20.59). Así que `Cantidad × Precio` es el importe correcto y las piezas son `Cantidad × Factor`, como ya estaba.
4. **Importes sin IVA** (inferido): el `Importe` del encabezado es 97.5 % de la suma de renglones en Nota y 95.6 % en Factura; si uno trajera IVA y el otro no, la razón sería cercana a 1.16. La diferencia parece ser el descuento. El IVA va aparte en `Impuestos`.

Las pruebas del ETL usan ahora datos con la forma real (Sucursal vacía y Nota Devolucion en negativo). `consulta_venta_semanal.sql` tiene los mismos cambios.

## Segunda ronda (consultas 12 a 19)

**Ojo con las fechas:** las consultas 8, 9, 10, 13, 14 y 15 usaban fechas como '2026-09-01'. Con el idioma español del servidor, SQL Server las lee como año-día-mes, así que **midieron el 9 de enero de 2026, no septiembre**. Por eso «septiembre» salía con 23 mil notas. Las conclusiones de forma (precio por unidad, descuentos, facturas) siguen valiendo porque no dependen del mes. De aquí en adelante las fechas van como '20260901'. El ETL no tiene el problema: manda las fechas como parámetros.

- **Venta completa (consulta 12):** de enero a septiembre hay entre 600 y 690 mil notas por mes ($150 a $173 millones) y entre 3 y 5 mil facturas ($36 a $50 millones). Septiembre está completo.
- **Factura Electronica es venta de mayoreo y no repite Notas (consulta 13):** sale de ALM-MEXICO (Almacén México), CORP (Corporativos), SANBORNS (consignación) y GDL 1 (Mayoreo Guadalajara), no de tiendas. Es ~22 % de la venta. **El ETL ahora la cuenta** (se puede apagar en Configuración); como la tienda es el almacén, queda separada de la venta de tiendas.
- **Descuentos son porcentajes (consultas 14 y 15):** el importe de 3,501 notas cuadra al centavo con `Cantidad × Precio × (1 − DescuentoLinea/100)` ($2,013,620.03 contra $2,013,619.99); como monto daría $2,077,510.82. `DescuentoGlobal` no viene en notas; en facturas va de 2 a 7 %. **El ETL ahora calcula el descuento en pesos con los dos porcentajes**; antes los restaba como si fueran pesos.
- **Inventario (consulta 16):** una sola foto, del 22 oct 2026: PS 130 almacenes, VCE 74, LAB 1; ~7,500 artículos; 15 existencias negativas. Para medir quiebres hay que guardar una foto cada día.
- **Compras (consultas 17 y 18):** ene 2025 a sep 2026. Órdenes (~80 mil), entradas (~75 mil), devoluciones, y además «Compra Perdida» (~13 mil) y «Compra Rechazada» (~5 mil) que dicen de qué orden vienen. 74,574 entradas se ligan con su orden: **7 días en promedio** de la orden a la entrada (hay casos raros de -37 días). Con eso se mide tiempo de entrega y cumplimiento por proveedor.
- **Tiendas (consulta 19):** Grupo VENTAS / Ruta TIENDAS, con `Categoria` AA, A, B, C, D y E (E son las abiertas de 2025 en adelante) y 7 regiones. Los almacenes MAY son mayoreo y LABORATORIO es el laboratorio.

## Lo que sigue abierto

- Qué significan «Compra Perdida» y «Compra Rechazada» (¿lo que no llegó de una orden?). Se le puede preguntar a Compras o Sistemas.
- Qué es cada `Categoria` de tienda (AA a E): ¿tamaño, venta, formato?
- Las ~190 ventas con `Sucursal` numérica salen casi todas de ALM-MEXICO; parecen pedidos de otro canal. No se usa.

## Lo que abre para el radar de productos (sin construir todavía)

- **Costo vigente:** `tblInventario.CostoPromedio` y el último `Costo` de `tblCompraD` dan el costo real de cada artículo, para rentabilidad.
- **Proveedor:** con `tblCompra` se puede medir el tiempo de entrega (orden contra entrada por `OrigenID`) y el cumplimiento (cantidad pedida contra recibida). `DiasEntrega` de `tblProveedores` es lo prometido.
- **Tiendas:** `tblAlmacenes` da nombre, región, categoría, apertura y ubicación para comparar tiendas parecidas.
- **Quiebres:** `tblInventario` es una foto del día; para ver quiebres hace falta guardar la foto cada día o que Sistemas tenga historia.
