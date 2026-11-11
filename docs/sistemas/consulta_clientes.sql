-- Datos → Clientes (Transformación Digital, 2026-11-09). Solo lee SMNBI.
-- Junta enero–septiembre 2026 por cliente y departamento. NO saca nombres ni números de cliente: cada cliente sale con
-- un código que cambia en cada corrida (no se puede regresar a la persona). Las cuentas genéricas (más de 30 notas al mes
-- o 20 tiendas o más, como «público en general») salen juntas en renglones «GENERICO».
-- Se corre con sqlcmd desde el servidor (ver la pantalla Datos → Clientes). Sale sin encabezado, 9 columnas:
-- cliente, tienda_principal, tiendas, meses, notas, departamento, notas_depto, piezas, importe (sin IVA, con descuento)

SET NOCOUNT ON;
DECLARE @desde date = '20260101';  -- AAAAMMDD
DECLARE @hasta date = '20261001';
DECLARE @sal varchar(36) = CONVERT(varchar(36), NEWID());

IF OBJECT_ID('tempdb..#n') IS NOT NULL DROP TABLE #n;
SELECT v.ID, LTRIM(RTRIM(v.Cliente)) AS Cliente, ISNULL(v.Almacen, '') AS Tienda,
       DATEFROMPARTS(YEAR(v.FechaMov), MONTH(v.FechaMov), 1) AS Mes
INTO #n
FROM dbo.tblVenta v
WHERE v.FechaMov >= @desde AND v.FechaMov < @hasta AND v.Estatus = 'CONCLUIDO' AND v.TipoMov = 'Nota'
  AND NULLIF(LTRIM(RTRIM(v.Cliente)), '') IS NOT NULL;

IF OBJECT_ID('tempdb..#c') IS NOT NULL DROP TABLE #c;
SELECT Cliente, COUNT(*) AS notas, COUNT(DISTINCT Tienda) AS tiendas, COUNT(DISTINCT Mes) AS meses,
       CASE WHEN COUNT(DISTINCT Tienda) >= 20 OR COUNT(*) > 30 * COUNT(DISTINCT Mes) THEN 1 ELSE 0 END AS generico
INTO #c FROM #n GROUP BY Cliente;

IF OBJECT_ID('tempdb..#t') IS NOT NULL DROP TABLE #t;
SELECT Cliente, Tienda INTO #t
FROM (SELECT Cliente, Tienda, ROW_NUMBER() OVER (PARTITION BY Cliente ORDER BY COUNT(*) DESC, Tienda) AS r
      FROM #n GROUP BY Cliente, Tienda) x
WHERE r = 1;

IF OBJECT_ID('tempdb..#d') IS NOT NULL DROP TABLE #d;
SELECT n.Cliente, REPLACE(ISNULL(a.Departamento, 'Sin departamento'), ',', ' ') AS Departamento,
       COUNT(DISTINCT n.ID) AS notas_depto,
       SUM(d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1)) AS piezas,
       SUM(d.Cantidad * d.Precio * (1 - ISNULL(d.DescuentoLinea, 0) / 100.0)) AS importe
INTO #d
FROM #n n
JOIN dbo.tblVentaD d ON d.ID = n.ID
JOIN dbo.tblArticulos a ON a.Articulo = d.Articulo
WHERE ISNULL(d.Unidad, '') NOT IN ('FLETETV', 'Actividad', 'SERVICIO')
GROUP BY n.Cliente, REPLACE(ISNULL(a.Departamento, 'Sin departamento'), ',', ' ');

DECLARE @cuentas int = (SELECT COUNT(*) FROM #c WHERE generico = 1);
DECLARE @notas_gen int = (SELECT ISNULL(SUM(notas), 0) FROM #c WHERE generico = 1);

SELECT LEFT(CONVERT(varchar(64), HASHBYTES('SHA2_256', CONCAT(@sal, c.Cliente)), 2), 16) AS cliente,
       t.Tienda, c.tiendas, c.meses, c.notas, d.Departamento, d.notas_depto,
       CAST(d.piezas AS decimal(14, 2)) AS piezas, CAST(d.importe AS decimal(16, 2)) AS importe
FROM #c c JOIN #t t ON t.Cliente = c.Cliente JOIN #d d ON d.Cliente = c.Cliente
WHERE c.generico = 0
UNION ALL
SELECT 'GENERICO', '', @cuentas, 9, @notas_gen, d.Departamento, SUM(d.notas_depto),
       CAST(SUM(d.piezas) AS decimal(16, 2)), CAST(SUM(d.importe) AS decimal(18, 2))
FROM #d d JOIN #c c ON c.Cliente = d.Cliente
WHERE c.generico = 1
GROUP BY d.Departamento;
