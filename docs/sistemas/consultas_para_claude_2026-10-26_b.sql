-- Segunda ronda de consultas sobre SMNBI (26 oct 2026). SOLO LEEN. Mismas instrucciones que la primera:
-- guarda cada resultado como CSV con su número (12.csv, 13.csv...) y revisa que no traiga nombres de personas, RFC ni correos.
-- Si una consulta marca error, sáltala y sigue.

USE SMNBI;
SET NOCOUNT ON;

-- 12. Ventas por mes y tipo: ¿septiembre está completo?
SELECT CONVERT(char(7), FechaMov, 120) AS mes, TipoMov, COUNT(*) AS ventas, SUM(Importe) AS importe
FROM dbo.tblVenta
WHERE Estatus = 'CONCLUIDO'
GROUP BY CONVERT(char(7), FechaMov, 120), TipoMov
ORDER BY mes, TipoMov;

-- 13. Factura Electronica por almacén (septiembre): ¿son ventas a empresas o canales, o repiten notas de tienda?
SELECT v.Almacen, a.Nombre, a.Categoria, COUNT(*) AS facturas, COUNT(DISTINCT v.Cliente) AS clientes, SUM(v.Importe) AS importe
FROM dbo.tblVenta v
LEFT JOIN dbo.tblAlmacenes a ON a.Almacen = v.Almacen
WHERE v.FechaMov >= '2026-09-01' AND v.FechaMov < '2026-10-01' AND v.Estatus = 'CONCLUIDO' AND v.TipoMov = 'Factura Electronica'
GROUP BY v.Almacen, a.Nombre, a.Categoria
ORDER BY importe DESC;

-- 14. ¿DescuentoLinea es monto o porcentaje? Notas de septiembre sin descuento global, con algún descuento de renglón.
--     Si importe se parece a «como_monto», es monto; si se parece a «como_porcentaje», es porcentaje.
WITH n AS (
    SELECT ID, Importe FROM dbo.tblVenta
    WHERE FechaMov >= '2026-09-01' AND FechaMov < '2026-10-01' AND Estatus = 'CONCLUIDO' AND TipoMov = 'Nota'
      AND ISNULL(DescuentoGlobal, 0) = 0
), r AS (
    SELECT d.ID, SUM(d.Cantidad * d.Precio - ISNULL(d.DescuentoLinea, 0)) AS como_monto,
           SUM(d.Cantidad * d.Precio * (1 - ISNULL(d.DescuentoLinea, 0) / 100.0)) AS como_porcentaje,
           SUM(ISNULL(d.DescuentoLinea, 0)) AS descuento
    FROM dbo.tblVentaD d JOIN n ON n.ID = d.ID
    GROUP BY d.ID
    HAVING SUM(ISNULL(d.DescuentoLinea, 0)) <> 0
)
SELECT COUNT(*) AS notas, SUM(n.Importe) AS importe, SUM(r.como_monto) AS como_monto, SUM(r.como_porcentaje) AS como_porcentaje,
       MIN(r.descuento) AS descuento_min, MAX(r.descuento) AS descuento_max
FROM n JOIN r ON r.ID = n.ID;

-- 15. DescuentoGlobal: cómo viene (septiembre)
SELECT TipoMov, COUNT(*) AS ventas, SUM(CASE WHEN ISNULL(DescuentoGlobal, 0) <> 0 THEN 1 ELSE 0 END) AS con_descuento_global,
       MIN(NULLIF(DescuentoGlobal, 0)) AS minimo, MAX(DescuentoGlobal) AS maximo, AVG(NULLIF(DescuentoGlobal, 0)) AS promedio
FROM dbo.tblVenta
WHERE FechaMov >= '2026-09-01' AND FechaMov < '2026-10-01' AND Estatus = 'CONCLUIDO'
GROUP BY TipoMov;

-- 16. Inventario: ¿una sola foto o varias fechas?
SELECT FechaCorte, Empresa, COUNT(*) AS renglones, COUNT(DISTINCT Almacen) AS almacenes, COUNT(DISTINCT Articulo) AS articulos,
       SUM(CASE WHEN Existencia > 0 THEN 1 ELSE 0 END) AS con_existencia, SUM(CASE WHEN Existencia < 0 THEN 1 ELSE 0 END) AS negativos
FROM dbo.tblInventario
GROUP BY FechaCorte, Empresa
ORDER BY FechaCorte, Empresa;

-- 17. Compras: tipos, estatus y periodo
SELECT TipoMov, Estatus, Empresa, COUNT(*) AS movimientos, MIN(FechaMov) AS primero, MAX(FechaMov) AS ultimo,
       SUM(CASE WHEN Origen IS NOT NULL AND OrigenID IS NOT NULL THEN 1 ELSE 0 END) AS con_origen
FROM dbo.tblCompra
GROUP BY TipoMov, Estatus, Empresa
ORDER BY TipoMov, Estatus, Empresa;

-- 18. ¿Las entradas se ligan con su orden? Días entre la orden y la entrada (solo las que dicen su orden)
SELECT COUNT(*) AS entradas_ligadas, AVG(CAST(DATEDIFF(DAY, o.FechaMov, e.FechaMov) AS float)) AS dias_promedio,
       MIN(DATEDIFF(DAY, o.FechaMov, e.FechaMov)) AS dias_min, MAX(DATEDIFF(DAY, o.FechaMov, e.FechaMov)) AS dias_max
FROM dbo.tblCompra e
JOIN dbo.tblCompra o ON o.TipoMov = e.Origen AND o.NumMov = e.OrigenID AND o.Empresa = e.Empresa
WHERE e.TipoMov = 'Entrada Compra' AND e.Origen = 'Orden Compra';

-- 19. Catálogo de tiendas: cómo se agrupa
SELECT Grupo, Ruta, Categoria, Estatus, Region, COUNT(*) AS almacenes, MIN(FechaApertura) AS primera_apertura,
       MAX(FechaApertura) AS ultima_apertura
FROM dbo.tblAlmacenes
GROUP BY Grupo, Ruta, Categoria, Estatus, Region
ORDER BY almacenes DESC;
