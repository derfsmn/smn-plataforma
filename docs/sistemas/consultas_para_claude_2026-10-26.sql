-- Consultas para Claude sobre SMNBI (26 oct 2026). Para correr en SSMS con el acceso de solo lectura.
-- SOLO LEEN: no cambian nada. Regresan estructura, conteos y totales; no traen clientes ni datos personales.
-- Cómo mandar los resultados: cada consulta numerada regresa una tabla. Clic derecho en la tabla > «Guardar resultados
-- como...» CSV con el nombre del número (01.csv, 02.csv...), o cópialas a un Excel con una hoja por número.
-- Antes de mandarlo, revísalo: si algo trae nombres de personas, RFC, teléfonos o correos, bórralo.
-- Si una consulta marca error (por ejemplo, una tabla que todavía no existe), sáltala y sigue con las demás.

USE SMNBI;
SET NOCOUNT ON;

-- 01. Estructura de todas las tablas: columnas y tipos (para ligar las tablas nuevas con la plataforma)
SELECT t.TABLE_NAME AS tabla, c.ORDINAL_POSITION AS n, c.COLUMN_NAME AS columna, c.DATA_TYPE AS tipo,
       c.CHARACTER_MAXIMUM_LENGTH AS largo, c.NUMERIC_PRECISION AS precision_, c.NUMERIC_SCALE AS escala,
       c.IS_NULLABLE AS acepta_nulos
FROM INFORMATION_SCHEMA.TABLES t
JOIN INFORMATION_SCHEMA.COLUMNS c ON c.TABLE_SCHEMA = t.TABLE_SCHEMA AND c.TABLE_NAME = t.TABLE_NAME
WHERE t.TABLE_TYPE IN ('BASE TABLE', 'VIEW')
ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION;

-- 02. Filas por tabla
SELECT s.name AS esquema, o.name AS tabla, SUM(p.rows) AS filas
FROM sys.objects o
JOIN sys.schemas s ON s.schema_id = o.schema_id
JOIN sys.partitions p ON p.object_id = o.object_id AND p.index_id IN (0, 1)
WHERE o.type = 'U'
GROUP BY s.name, o.name
ORDER BY o.name;

-- 03. Ejemplo de tiendas y almacenes (5 renglones): para ver qué trae el catálogo
SELECT TOP 5 * FROM dbo.tblAlmacenes;

-- 04. Ejemplo de inventario (5 renglones)
SELECT TOP 5 * FROM dbo.tblInventario;

-- 05. Ejemplo de compras: encabezado y renglones (5 de cada uno)
SELECT TOP 5 * FROM dbo.tblCompra;
SELECT TOP 5 * FROM dbo.tblCompraD;

-- 06. Proveedores: solo cuántos hay (sin ejemplos, puede traer RFC o personas físicas)
SELECT COUNT(*) AS proveedores FROM dbo.tblProveedores;

-- 07. Venta: periodo que cubre hoy (para saber si ya trae octubre o años anteriores)
SELECT MIN(FechaMov) AS primera, MAX(FechaMov) AS ultima, COUNT(*) AS ventas FROM dbo.tblVenta;

-- 08. Pregunta 3, ¿la Factura Electronica repite ventas de Nota? Una factura global junta muchos tickets,
--     así que trae muchos más renglones por venta que una nota normal. Septiembre 2026.
WITH por_venta AS (
    SELECT v.ID, v.TipoMov, COUNT(*) AS renglones, SUM(d.Cantidad * d.Precio) AS bruto
    FROM dbo.tblVenta v JOIN dbo.tblVentaD d ON d.ID = v.ID
    WHERE v.FechaMov >= '2026-09-01' AND v.FechaMov < '2026-10-01' AND v.Estatus = 'CONCLUIDO'
    GROUP BY v.ID, v.TipoMov
)
SELECT TipoMov, COUNT(*) AS ventas, AVG(CAST(renglones AS float)) AS renglones_promedio, MAX(renglones) AS renglones_max,
       AVG(bruto) AS bruto_promedio, MAX(bruto) AS bruto_max, SUM(bruto) AS bruto_total
FROM por_venta
GROUP BY TipoMov
ORDER BY TipoMov;

-- 09. Pregunta 5, ¿Precio es por pieza o por la unidad del renglón? Mismo artículo vendido por PIEZA y por PAQUETE/CAJA:
--     si precio_paquete / factor se parece a precio_pieza, Precio es por la unidad del renglón. Septiembre 2026.
WITH p AS (
    SELECT d.Articulo,
           AVG(CASE WHEN d.Unidad = 'PIEZA' THEN d.Precio END) AS precio_pieza,
           AVG(CASE WHEN d.Unidad <> 'PIEZA' AND d.Factor > 1 THEN d.Precio END) AS precio_paquete,
           AVG(CASE WHEN d.Unidad <> 'PIEZA' AND d.Factor > 1 THEN CAST(d.Factor AS float) END) AS factor
    FROM dbo.tblVenta v JOIN dbo.tblVentaD d ON d.ID = v.ID
    WHERE v.FechaMov >= '2026-09-01' AND v.FechaMov < '2026-10-01' AND v.Estatus = 'CONCLUIDO' AND v.TipoMov = 'Nota'
    GROUP BY d.Articulo
)
SELECT TOP 20 Articulo, precio_pieza, precio_paquete, factor, precio_paquete / NULLIF(factor, 0) AS paquete_entre_factor
FROM p
WHERE precio_pieza IS NOT NULL AND precio_paquete IS NOT NULL
ORDER BY Articulo;

-- 10. Pregunta 5, ¿los importes traen impuestos? Encabezado contra suma de renglones, por tipo. Septiembre 2026.
--     Si importe_encabezado / bruto_renglones sale cerca de 1, son la misma base; cerca de 1.16, uno trae IVA.
WITH sep AS (
    SELECT ID, TipoMov, Importe FROM dbo.tblVenta
    WHERE FechaMov >= '2026-09-01' AND FechaMov < '2026-10-01' AND Estatus = 'CONCLUIDO'
), r AS (
    SELECT d.ID, SUM(d.Cantidad * d.Precio) AS bruto, SUM(ISNULL(d.DescuentoLinea, 0)) AS descuento
    FROM dbo.tblVentaD d JOIN sep ON sep.ID = d.ID
    GROUP BY d.ID
)
SELECT v.TipoMov, SUM(v.Importe) AS importe_encabezado, SUM(r.bruto) AS bruto_renglones,
       SUM(r.descuento) AS descuento_renglones, SUM(v.Importe) / NULLIF(SUM(r.bruto), 0) AS razon
FROM sep v JOIN r ON r.ID = v.ID
GROUP BY v.TipoMov
ORDER BY v.TipoMov;

-- 11. Pregunta 6, ¿qué relación hay entre Sucursal y Almacen? Cuántos almacenes usa cada sucursal (2026).
SELECT Sucursal, COUNT(DISTINCT Almacen) AS almacenes, COUNT(*) AS ventas,
       MIN(Almacen) AS un_almacen, MAX(Almacen) AS otro_almacen
FROM dbo.tblVenta
WHERE FechaMov >= '2026-01-01' AND Estatus = 'CONCLUIDO'
GROUP BY Sucursal
ORDER BY almacenes DESC, Sucursal;
