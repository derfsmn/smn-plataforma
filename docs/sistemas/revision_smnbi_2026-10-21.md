# Revisión de la base SMNBI (acceso de Sistemas, 21 oct 2026)

Fuente: `sistemas/estructura.csv`, que Diego sacó con una consulta de estructura (sin datos). Base **SMNBI**, esquema `dbo`, 5 tablas.

| Tabla | Filas | Qué es |
|---|---|---|
| `tblArticulos` | 5,795 | Catálogo de artículos (16 columnas) |
| `tblVenta` | 5,871,196 | Encabezado de cada venta (17 columnas) |
| `tblVentaD` | 15,307,091 | Renglones de cada venta (9 columnas) |
| `tblCompra` | **0** | Encabezado de compras (vacía) |
| `tblCompraD` | **0** | Renglones de compras (vacía) |

## Contra lo que necesita el semáforo (modelo_semaforo_v3)

| Lo que necesita el semáforo | ¿Está? | Detalle |
|---|---|---|
| Producto: departamento, rama, subcategoría, segmento, marca, proveedor | Sí | `tblArticulos`; se liga con nuestro catálogo por `Articulo` = SKU |
| Producto: código de barras | Por confirmar | `Codigo` parece serlo |
| Producto: IVA e IEPS | Sí | `IVA`, `IEPS` |
| Producto: contenido neto y unidad de medida | No | |
| Producto: costo vigente | Parcial | Se puede tomar el último `Costo` vendido de `tblVentaD`, pero no es el costo de compra vigente |
| Producto: fecha de alta y de baja | No | Solo `Estatus` |
| Venta por producto, tienda y semana | Sí | `tblVenta` + `tblVentaD` (fecha, sucursal, cantidad, precio, costo, descuentos) |
| Tickets por producto | Sí | Se cuentan ventas distintas (`ID`) por artículo |
| Venta a socios (membresía) | Por confirmar | Quizá por `Cliente` |
| Margen histórico | Sí | Precio y costo por renglón |
| Compras (lead time y cumplimiento del proveedor) | Vacía | `tblCompra` y `tblCompraD` tienen 0 filas; además no traen fecha prometida ni de recepción |
| Catálogo de proveedores (nombre, RFC, alta, días de crédito, origen) | No | Solo viene el código en artículos y compras |
| Catálogo de tiendas (nombre, formato, clase, código postal, apertura, cierre) | No | Solo los códigos `Sucursal` y `Almacen` |
| Inventario y quiebres | No | |
| Surtido por tienda (qué tienda maneja qué producto) | No | |
| Promociones | No | |
| Merma | No | |
| Devoluciones a proveedor | No | |

## Preguntas para Sistemas

1. ¿Por qué `tblCompra` y `tblCompraD` están vacías? ¿Se van a llenar?
2. ¿Qué valores tiene `TipoMov` y `Estatus` en ventas? ¿Cuáles hay que excluir (canceladas, devoluciones)?
3. ¿`Importe` es sin impuestos? ¿`Precio` en `tblVentaD` es por unidad de venta, y qué significan `Unidad` y `Factor`?
4. ¿Cuál es la diferencia entre `Almacen` y `Sucursal`? ¿Hay venta en línea ahí?
5. ¿`Cliente` permite distinguir venta a socios?
6. ¿`Codigo` en artículos es el código de barras?
7. ¿`Departamento` y `Rama` son claves? ¿Hay catálogo con los nombres?
8. ¿Desde qué fecha hay ventas y cada cuánto se actualiza la base?
9. Faltantes para pedir: catálogo de tiendas, catálogo de proveedores, inventario, surtido por tienda, promociones, merma, devoluciones, contenido neto y unidad de medida, fecha de alta y baja de artículos.
