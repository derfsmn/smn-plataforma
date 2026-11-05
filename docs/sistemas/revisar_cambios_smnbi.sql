-- ¿Hay cambios en SMNBI? Revisión para Centro de datos -> ETL -> «Revisar si hay cambios».
-- SOLO LEE. Corre todo, guarda el resultado como CSV (clic derecho en la tabla > «Guardar resultados como...») y
-- súbelo en la plataforma. Tarda lo que tarda sumar la venta de todos los meses.
-- Archivo generado por api/datos/revision_smnbi.py: si cambian las reglas del ETL, se vuelve a descargar.

USE SMNBI;
SET NOCOUNT ON;

SELECT 'articulos' AS fuente, 'total' AS clave, '' AS empresa, COUNT(*) AS filas, NULL AS piezas, NULL AS importe,
       NULL AS fecha
FROM dbo.tblArticulos
UNION ALL
SELECT 'articulos', 'alta', '', COUNT(*), NULL, NULL, NULL FROM dbo.tblArticulos WHERE Estatus = 'ALTA'
UNION ALL
SELECT 'tiendas', 'total', '', COUNT(*), NULL, NULL, NULL FROM dbo.tblAlmacenes
UNION ALL
SELECT 'proveedores', 'total', '', COUNT(*), NULL, NULL, NULL FROM dbo.tblProveedores
UNION ALL
SELECT 'compras', 'ordenes', '', COUNT(*), NULL, NULL, CONVERT(char(10), MAX(FechaMov), 23)
FROM dbo.tblCompra WHERE TipoMov = 'Orden Compra' AND Estatus IN ('CONCLUIDO', 'PENDIENTE')
UNION ALL
SELECT 'compras', 'pendientes', '', COUNT(*), NULL, NULL, NULL
FROM dbo.tblCompra WHERE TipoMov = 'Orden Compra' AND Estatus = 'PENDIENTE'
UNION ALL
SELECT 'compras', 'entradas', '', COUNT(*), NULL, NULL, CONVERT(char(10), MAX(FechaMov), 23)
FROM dbo.tblCompra WHERE TipoMov = 'Entrada Compra' AND Origen = 'Orden Compra' AND Estatus = 'CONCLUIDO'
UNION ALL
SELECT 'costos', 'total', '', COUNT(DISTINCT d.Articulo), NULL, NULL, CONVERT(char(10), MAX(c.FechaMov), 23)
FROM dbo.tblCompra c JOIN dbo.tblCompraD d ON d.ID = c.ID
WHERE c.TipoMov = 'Entrada Compra' AND c.Estatus = 'CONCLUIDO' AND d.Cantidad > 0 AND d.Costo > 0
UNION ALL
SELECT 'inventario', 'corte', '', COUNT(*), NULL, NULL, CONVERT(char(10), MAX(FechaCorte), 23)
FROM dbo.tblInventario WHERE FechaCorte = (SELECT MAX(FechaCorte) FROM dbo.tblInventario)
UNION ALL
-- Venta de cada mes por empresa, con las mismas reglas que la carga (devoluciones restan, descuentos en %)
SELECT 'venta', CONVERT(char(10), DATEFROMPARTS(YEAR(v.FechaMov), MONTH(v.FechaMov), 1), 23), v.Empresa, COUNT(*),
       SUM(CASE WHEN v.TipoMov IN ('Nota Devolucion', 'Devolucion Venta') THEN -1 ELSE 1 END * (CASE WHEN v.TipoMov IN ('Nota Devolucion', 'Devolucion Venta') THEN ABS(d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1)) ELSE d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1) END)), SUM(CASE WHEN v.TipoMov IN ('Nota Devolucion', 'Devolucion Venta') THEN -1 ELSE 1 END * ((CASE WHEN v.TipoMov IN ('Nota Devolucion', 'Devolucion Venta') THEN ABS(d.Cantidad * d.Precio) ELSE d.Cantidad * d.Precio END) - (CASE WHEN v.TipoMov IN ('Nota Devolucion', 'Devolucion Venta') THEN ABS(d.Cantidad * d.Precio * (1 - (1 - ISNULL(d.DescuentoLinea, 0) / 100.0) * (1 - ISNULL(v.DescuentoGlobal, 0) / 100.0))) ELSE d.Cantidad * d.Precio * (1 - (1 - ISNULL(d.DescuentoLinea, 0) / 100.0) * (1 - ISNULL(v.DescuentoGlobal, 0) / 100.0)) END))), CONVERT(char(10), MAX(v.FechaMov), 23)
FROM dbo.tblVenta v
JOIN dbo.tblVentaD d ON d.ID = v.ID
JOIN dbo.tblArticulos a ON a.Articulo = d.Articulo
WHERE v.TipoMov IN ('Nota', 'Nota Devolucion', 'Devolucion Venta', 'Factura Electronica') AND ISNULL(d.Unidad, '') NOT IN ('FLETETV', 'Actividad', 'SERVICIO') AND v.Estatus = 'CONCLUIDO'
GROUP BY DATEFROMPARTS(YEAR(v.FechaMov), MONTH(v.FechaMov), 1), v.Empresa
ORDER BY 1, 2, 3;
