-- Tablas de SMNBI para el semáforo de productos (Centro de datos -> ETL -> Fuentes de Sistemas).
-- SOLO LEEN. Corre cada consulta, guarda su resultado como CSV (clic derecho en la tabla > «Guardar resultados
-- como...») y súbelo en la tarjeta de su fuente. Con o sin encabezados.

USE SMNBI;
SET NOCOUNT ON;

-- 1. Artículos (tblArticulos): 14 columnas. Completa el catálogo: subcategoría, estatus (ALTA o DESCONTINUADO), proveedor y fabricante.
SELECT Articulo, Descripcion, Departamento, Rama, Categoria, SubCategoria, Segmento, Fabricante, Proveedor,
       Marca, TipoCompra, Clasificacion, Estatus, Codigo
FROM dbo.tblArticulos
ORDER BY Articulo;

-- 2. Tiendas y almacenes (tblAlmacenes): 14 columnas. Nombre, región, categoría (AA a E; MAY es mayoreo) y apertura de cada almacén de la venta.
SELECT Almacen, Nombre, Poblacion, Estado, CodigoPostal, Grupo, Ruta, Sucursal, Estatus, Region, Categoria,
       CONVERT(char(10), FechaApertura, 23), MapaLatitud, MapaLongitud
FROM dbo.tblAlmacenes
ORDER BY Almacen;

-- 3. Proveedores (tblProveedores): 8 columnas. Días de entrega que promete cada proveedor, condición de pago y descuentos (sin RFC).
-- Sin RFC: no se necesita y puede ser de una persona física
SELECT Proveedor, Nombre, Estatus, Condicion, Descuento, DescuentoAdicional, DiasEntrega, Penalizacion
FROM dbo.tblProveedores
ORDER BY Proveedor;

-- 4. Compras por orden (tblCompra, tblCompraD): 13 columnas. Cada orden de compra con lo que llegó y cuándo: tiempo de entrega y cumplimiento real de cada proveedor.
-- Una fila por orden de compra con lo que llegó (Entrada Compra), se perdió o se rechazó, ligados por Origen/OrigenID
WITH o AS (
    SELECT ID, Empresa, NumMov, Proveedor, Almacen, FechaMov, Estatus FROM dbo.tblCompra
    WHERE TipoMov = 'Orden Compra' AND Estatus IN ('CONCLUIDO', 'PENDIENTE')
), pedido AS (
    SELECT d.ID, SUM(d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1)) AS piezas, SUM(d.Cantidad * d.Costo) AS importe
    FROM dbo.tblCompraD d JOIN o ON o.ID = d.ID GROUP BY d.ID
), mov AS (
    SELECT c.Empresa, c.OrigenID, c.TipoMov, MIN(c.FechaMov) AS primera, MAX(c.FechaMov) AS ultima,
           SUM(ABS(d.Cantidad) * ISNULL(NULLIF(d.Factor, 0), 1)) AS piezas
    FROM dbo.tblCompra c JOIN dbo.tblCompraD d ON d.ID = c.ID
    WHERE c.Origen = 'Orden Compra' AND c.Estatus = 'CONCLUIDO'
      AND c.TipoMov IN ('Entrada Compra', 'Compra Perdida', 'Compra Rechazada')
    GROUP BY c.Empresa, c.OrigenID, c.TipoMov
)
SELECT o.Empresa, o.NumMov, o.Proveedor, o.Almacen, CONVERT(char(10), o.FechaMov, 23), o.Estatus,
       pedido.piezas, pedido.importe,
       CONVERT(char(10), e.primera, 23), CONVERT(char(10), e.ultima, 23),
       ISNULL(e.piezas, 0), ISNULL(p.piezas, 0), ISNULL(r.piezas, 0)
FROM o
LEFT JOIN pedido ON pedido.ID = o.ID
LEFT JOIN mov e ON e.Empresa = o.Empresa AND e.OrigenID = o.NumMov AND e.TipoMov = 'Entrada Compra'
LEFT JOIN mov p ON p.Empresa = o.Empresa AND p.OrigenID = o.NumMov AND p.TipoMov = 'Compra Perdida'
LEFT JOIN mov r ON r.Empresa = o.Empresa AND r.OrigenID = o.NumMov AND r.TipoMov = 'Compra Rechazada'
ORDER BY o.Empresa, o.NumMov;

-- 5. Costo de compra por artículo (tblCompra, tblCompraD): 7 columnas. Lo que nos cuesta cada artículo: la última compra y el promedio de 12 meses, por pieza y sin IVA.
-- Costo por pieza sin IVA de las entradas de compra: la última y el promedio de los últimos 12 meses
WITH e AS (
    SELECT d.Articulo, c.Proveedor, c.FechaMov, d.Costo / ISNULL(NULLIF(d.Factor, 0), 1) AS costo_pieza, d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1) AS piezas,
           ROW_NUMBER() OVER (PARTITION BY d.Articulo ORDER BY c.FechaMov DESC, c.ID DESC) AS n
    FROM dbo.tblCompra c JOIN dbo.tblCompraD d ON d.ID = c.ID
    WHERE c.TipoMov = 'Entrada Compra' AND c.Estatus = 'CONCLUIDO' AND d.Cantidad > 0 AND d.Costo > 0
), ultimos AS (
    SELECT Articulo, SUM(costo_pieza * piezas) / NULLIF(SUM(piezas), 0) AS costo, SUM(piezas) AS piezas, COUNT(*) AS compras
    FROM e WHERE FechaMov >= DATEADD(MONTH, -12, (SELECT MAX(FechaMov) FROM e))
    GROUP BY Articulo
)
SELECT u.Articulo, u.Proveedor, CONVERT(char(10), u.FechaMov, 23), u.costo_pieza, a.costo, a.piezas, a.compras
FROM e u LEFT JOIN ultimos a ON a.Articulo = u.Articulo
WHERE u.n = 1
ORDER BY u.Articulo;

-- 6. Inventario (tblInventario): 6 columnas. Existencia por almacén y artículo en la fecha de corte. Cada fecha se guarda aparte para ver quiebres después.
SELECT CONVERT(char(10), FechaCorte, 23), Empresa, Almacen, Articulo, Existencia, CostoPromedio
FROM dbo.tblInventario
ORDER BY Almacen, Articulo;
