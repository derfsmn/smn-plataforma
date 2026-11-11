-- ¿Sirve el campo Cliente de tblVenta para armar perfiles de clientes? (Transformación Digital, 2026-11-09)
-- Solo lee y solo regresa CONTEOS: ningún nombre, número de cliente, RFC ni correo sale de SMNBI.
-- Un mes (septiembre 2026), solo notas de tienda concluidas. Puede tardar unos minutos.

USE SMNBI;
SET NOCOUNT ON;

DECLARE @desde date = '20260901';  -- AAAAMMDD (con el idioma español del servidor)
DECLARE @hasta date = DATEADD(MONTH, 1, @desde);

WITH notas AS (
    SELECT v.ID, NULLIF(LTRIM(RTRIM(v.Cliente)), '') AS Cliente, v.Almacen
    FROM dbo.tblVenta v
    WHERE v.FechaMov >= @desde AND v.FechaMov < @hasta AND v.Estatus = 'CONCLUIDO' AND v.TipoMov = 'Nota'
),
por_cliente AS (
    SELECT Cliente, COUNT(*) AS notas, COUNT(DISTINCT Almacen) AS tiendas
    FROM notas WHERE Cliente IS NOT NULL GROUP BY Cliente
)
-- 1. Cuántas notas traen cliente y cuánto pesa el cliente más grande (si es «público en general», casi todas caen ahí)
SELECT
    (SELECT COUNT(*) FROM notas)                                   AS notas_del_mes,
    (SELECT COUNT(*) FROM notas WHERE Cliente IS NULL)             AS notas_sin_cliente,
    (SELECT COUNT(*) FROM por_cliente)                             AS clientes_distintos,
    (SELECT MAX(notas) FROM por_cliente)                           AS notas_del_cliente_mas_grande,
    (SELECT MAX(tiendas) FROM por_cliente)                         AS tiendas_del_cliente_mas_grande,
    (SELECT COUNT(*) FROM por_cliente WHERE tiendas >= 20)         AS clientes_en_20_o_mas_tiendas;  -- probables genéricos

-- 2. Cuántas veces compra cada cliente en el mes (sin los que compran en 20 o más tiendas, que serían genéricos)
WITH notas AS (
    SELECT v.ID, NULLIF(LTRIM(RTRIM(v.Cliente)), '') AS Cliente, v.Almacen
    FROM dbo.tblVenta v
    WHERE v.FechaMov >= @desde AND v.FechaMov < @hasta AND v.Estatus = 'CONCLUIDO' AND v.TipoMov = 'Nota'
),
por_cliente AS (
    SELECT Cliente, COUNT(*) AS notas, COUNT(DISTINCT Almacen) AS tiendas
    FROM notas WHERE Cliente IS NOT NULL GROUP BY Cliente
)
SELECT
    CASE WHEN notas = 1 THEN '1 vez' WHEN notas <= 3 THEN '2 a 3 veces' WHEN notas <= 10 THEN '4 a 10 veces'
         ELSE 'más de 10 veces' END AS compras_en_el_mes,
    COUNT(*)   AS clientes,
    SUM(notas) AS notas
FROM por_cliente
WHERE tiendas < 20
GROUP BY CASE WHEN notas = 1 THEN '1 vez' WHEN notas <= 3 THEN '2 a 3 veces' WHEN notas <= 10 THEN '4 a 10 veces'
              ELSE 'más de 10 veces' END
ORDER BY MIN(notas);

-- 3. ¿Hay alguna tabla de clientes o socios en SMNBI? (solo nombres de tablas y columnas, sin datos)
SELECT t.name AS tabla, c.name AS columna
FROM sys.tables t JOIN sys.columns c ON c.object_id = t.object_id
WHERE t.name LIKE '%Client%' OR t.name LIKE '%Socio%' OR t.name LIKE '%Membres%'
ORDER BY t.name, c.column_id;
