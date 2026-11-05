-- Vista previa del ETL de ventas (docs/sistemas/diseno_etl_ventas.md), para correr en SSMS sobre SMNBI.
-- Solo lee. Aplica las reglas a UN mes y regresa la venta sumada por producto, tienda y semana, y el cuadre del mes.
-- Cambia @desde para probar otro mes. Puede tardar unos minutos: lee ~1.7 millones de renglones de venta por mes y
-- regresa menos (cerca de 800 mil en enero 2026), porque los suma por producto, tienda y semana.
-- Es la misma lógica que usa el ETL (api/datos/etl.py). Para cargar el mes sin conexión: en SSMS, «Resultados a archivo»
-- (o clic derecho en la primera tabla > Guardar resultados como... CSV) y súbelo en Centro de datos > ETL > Subir CSV.
-- El archivo debe traer las 10 columnas en este orden; el encabezado es opcional.

USE SMNBI;
SET NOCOUNT ON;

DECLARE @desde date = '20260901';  -- AAAAMMDD: con el idioma español del servidor '2026-09-01' en datetime se lee como 9 de enero
DECLARE @hasta date = DATEADD(MONTH, 1, @desde);

WITH renglones AS (
    SELECT
        v.ID,
        v.Empresa,
        ISNULL(v.Almacen, '') AS Tienda,  -- la tienda es el Almacen: Sucursal viene vacía (revisión 2026-10-26)
        -- Semana = su lunes (el 1900-01-01 fue lunes), sin depender de DATEFIRST
        CAST(DATEADD(DAY, -(DATEDIFF(DAY, '19000101', v.FechaMov) % 7), CAST(v.FechaMov AS date)) AS date) AS semana,
        d.Articulo,
        -- «Nota Devolucion» trae la cantidad en negativo y «Devolucion Venta» en positivo: valor absoluto y se resta
        CASE WHEN v.TipoMov IN ('Nota Devolucion', 'Devolucion Venta') THEN -1 ELSE 1 END AS signo,
        CASE WHEN v.TipoMov IN ('Nota Devolucion', 'Devolucion Venta') THEN ABS(d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1)) ELSE d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1) END  AS piezas,
        CASE WHEN v.TipoMov IN ('Nota Devolucion', 'Devolucion Venta') THEN ABS(d.Cantidad * d.Precio) ELSE d.Cantidad * d.Precio END                         AS bruto,
        -- Descuento en pesos: DescuentoLinea y DescuentoGlobal son porcentajes (revisión 2026-10-26)
        CASE WHEN v.TipoMov IN ('Nota Devolucion', 'Devolucion Venta') THEN ABS(d.Cantidad * d.Precio * (1 - (1 - ISNULL(d.DescuentoLinea, 0) / 100.0) * (1 - ISNULL(v.DescuentoGlobal, 0) / 100.0))) ELSE d.Cantidad * d.Precio * (1 - (1 - ISNULL(d.DescuentoLinea, 0) / 100.0) * (1 - ISNULL(v.DescuentoGlobal, 0) / 100.0)) END AS descuento_linea,
        CASE WHEN v.TipoMov IN ('Nota Devolucion', 'Devolucion Venta') THEN ABS(d.Cantidad * d.Costo) ELSE d.Cantidad * d.Costo END                          AS costo
    FROM dbo.tblVenta v
    JOIN dbo.tblVentaD d ON d.ID = v.ID
    JOIN dbo.tblArticulos a ON a.Articulo = d.Articulo
    WHERE v.FechaMov >= @desde AND v.FechaMov < @hasta
      AND v.Estatus = 'CONCLUIDO'
      AND v.TipoMov IN ('Nota', 'Factura Electronica', 'Nota Devolucion', 'Devolucion Venta')  -- facturas = mayoreo, no repiten Notas
      AND ISNULL(d.Unidad, '') NOT IN ('FLETETV', 'Actividad', 'SERVICIO')
)
SELECT
    Articulo                                           AS sku,
    Tienda                                             AS tienda,
    semana,
    Empresa                                            AS empresa,
    SUM(CASE WHEN signo = 1 THEN piezas ELSE 0 END)    AS piezas,
    SUM(CASE WHEN signo = -1 THEN piezas ELSE 0 END)   AS piezas_devueltas,
    SUM(signo * bruto)                                 AS importe_bruto,
    SUM(signo * descuento_linea)                       AS descuento_linea,
    SUM(signo * costo)                                 AS costo,
    COUNT(DISTINCT CASE WHEN signo = 1 THEN ID END)    AS tickets
FROM renglones
GROUP BY Articulo, Tienda, semana, Empresa
ORDER BY semana, tienda, sku;  -- una semana que cruza de mes trae solo los días de este mes

-- Cuadre del mes: con estos totales se valida contra lo que conoce Finanzas
SELECT
    v.Empresa,
    v.TipoMov,
    COUNT(DISTINCT v.ID)                  AS ventas,
    SUM(v.Importe)                        AS importe_encabezado,
    SUM(d.Cantidad * d.Precio)            AS bruto_renglones,
    SUM(d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1)) AS piezas
FROM dbo.tblVenta v
JOIN dbo.tblVentaD d ON d.ID = v.ID
WHERE v.FechaMov >= @desde AND v.FechaMov < @hasta
  AND v.Estatus = 'CONCLUIDO'
GROUP BY v.Empresa, v.TipoMov
ORDER BY v.Empresa, v.TipoMov;
