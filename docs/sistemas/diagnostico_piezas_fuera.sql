-- Qué piezas de venta deja fuera el ETL y por qué (27 oct 2026: en enero se cargaron 2,559,753 piezas
-- y el cuadre de SMNBI suma 2,877,669). SOLO LEE. Corre todo el archivo; salen dos tablas.
USE SMNBI;
SET NOCOUNT ON;
DECLARE @desde date = '20260101';
DECLARE @hasta date = DATEADD(MONTH, 1, @desde);

-- 1. Piezas e importe por motivo
SELECT
    v.Empresa,
    CASE WHEN a.Articulo IS NULL THEN 'No está en tblArticulos'
         WHEN ISNULL(d.Unidad, '') IN ('FLETETV', 'Actividad', 'SERVICIO') THEN 'Unidad ' + d.Unidad
         ELSE 'Se carga' END                                   AS motivo,
    COUNT(*)                                                    AS renglones,
    SUM(CASE WHEN v.TipoMov IN ('Nota Devolucion', 'Devolucion Venta') THEN -ABS(d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1))
             ELSE d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1) END) AS piezas,
    SUM(CASE WHEN v.TipoMov IN ('Nota Devolucion', 'Devolucion Venta') THEN -ABS(d.Cantidad * d.Precio)
             ELSE d.Cantidad * d.Precio END)                    AS bruto
FROM dbo.tblVenta v
JOIN dbo.tblVentaD d ON d.ID = v.ID
LEFT JOIN dbo.tblArticulos a ON a.Articulo = d.Articulo
WHERE v.FechaMov >= @desde AND v.FechaMov < @hasta
  AND v.Estatus = 'CONCLUIDO'
  AND v.TipoMov IN ('Nota', 'Factura Electronica', 'Nota Devolucion', 'Devolucion Venta')
GROUP BY v.Empresa,
    CASE WHEN a.Articulo IS NULL THEN 'No está en tblArticulos'
         WHEN ISNULL(d.Unidad, '') IN ('FLETETV', 'Actividad', 'SERVICIO') THEN 'Unidad ' + d.Unidad
         ELSE 'Se carga' END
ORDER BY v.Empresa, motivo;

-- 2. Los 20 artículos con más piezas fuera (sin nombres de personas: solo código, unidad y precio)
SELECT TOP 20
    d.Articulo,
    ISNULL(d.Unidad, '')                                        AS unidad,
    CASE WHEN a.Articulo IS NULL THEN 'No está en tblArticulos' ELSE 'Unidad excluida' END AS motivo,
    SUM(d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1))            AS piezas,
    SUM(d.Cantidad * d.Precio)                                  AS bruto,
    MIN(d.Precio)                                               AS precio_min,
    MAX(d.Precio)                                               AS precio_max
FROM dbo.tblVenta v
JOIN dbo.tblVentaD d ON d.ID = v.ID
LEFT JOIN dbo.tblArticulos a ON a.Articulo = d.Articulo
WHERE v.FechaMov >= @desde AND v.FechaMov < @hasta
  AND v.Estatus = 'CONCLUIDO'
  AND v.TipoMov IN ('Nota', 'Factura Electronica')
  AND (a.Articulo IS NULL OR ISNULL(d.Unidad, '') IN ('FLETETV', 'Actividad', 'SERVICIO'))
GROUP BY d.Articulo, ISNULL(d.Unidad, ''), CASE WHEN a.Articulo IS NULL THEN 'No está en tblArticulos' ELSE 'Unidad excluida' END
ORDER BY piezas DESC;
