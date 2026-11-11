-- Gasto de la IA externa por tarea y por día (base smn_td). Correr en SSMS conectado a localhost,1433
-- (y, si se puede, también en el servidor). Guardar cada resultado como CSV.
USE smn_td;

-- 1) Por día y tarea, últimos 14 días
SELECT CAST(l.ocurrido_en AS date)            AS dia,
       t.codigo                               AS tarea,
       l.proveedor_ia, l.modelo, l.resultado,
       COUNT(*)                               AS llamadas,
       SUM(CAST(l.tokens_entrada AS bigint))  AS tokens_entrada,
       SUM(CAST(l.tokens_salida  AS bigint))  AS tokens_salida,
       SUM(l.costo_mxn)                       AS costo_mxn_estimado
FROM nucleo.ia_llamada l
JOIN nucleo.ia_tarea t ON t.tarea_id = l.tarea_id
WHERE l.ocurrido_en >= DATEADD(day, -14, GETDATE())
GROUP BY CAST(l.ocurrido_en AS date), t.codigo, l.proveedor_ia, l.modelo, l.resultado
ORDER BY dia DESC, costo_mxn_estimado DESC;

-- 2) Cómo está configurada cada tarea hoy
SELECT codigo, proveedor_ia, modelo, activa FROM nucleo.ia_tarea ORDER BY codigo;

-- 3) Ajustes de IA y programador guardados en la plataforma (sin llaves)
SELECT clave, valor FROM nucleo.configuracion
WHERE clave LIKE 'ia[_]%' OR clave LIKE 'ollama%' OR clave LIKE 'oportunidades%'
   OR clave LIKE 'radar[_]%' OR clave LIKE 'precios%' OR clave = 'programador_activo'
ORDER BY clave;
