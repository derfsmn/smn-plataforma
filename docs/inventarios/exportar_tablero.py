"""Exporta los CSV del tablero de inventarios. Correr DENTRO del contenedor api:
   docker compose exec -T api python - < exportar_tablero.py
Deja los CSV en /tmp/tablero/ del contenedor (copiar con docker compose cp api:/tmp/tablero <destino>)."""
import csv, os
from sqlalchemy import text
from core.bd import motor
DECL = """DECLARE @corte date = (SELECT MAX(fecha_corte) FROM datos.inventario);
DECLARE @fin date = (SELECT MAX(semana) FROM datos.venta_semanal);
DECLARE @desde date = DATEADD(week, -12, @fin);
"""
Q = {}
Q['inv_por_almacen.csv'] = """SELECT i.fecha_corte, i.empresa, i.almacen, t.nombre, t.categoria, t.region, t.grupo,
       COUNT(*) AS renglones,
       SUM(CASE WHEN i.existencia > 0 THEN 1 ELSE 0 END) AS skus_con_existencia,
       SUM(CASE WHEN i.existencia > 0 THEN i.existencia ELSE 0 END) AS piezas,
       SUM(CASE WHEN i.existencia > 0 THEN i.existencia * COALESCE(i.costo_promedio, c.costo_ultimo, 0) ELSE 0 END) AS valor_costo,
       SUM(CASE WHEN i.existencia > 0 THEN i.existencia * COALESCE(p.precio_lista, 0) ELSE 0 END) AS valor_precio,
       SUM(CASE WHEN i.existencia > 0 AND p.sku IS NULL THEN i.existencia * COALESCE(i.costo_promedio, 0) ELSE 0 END) AS valor_costo_sin_catalogo
FROM datos.inventario i
LEFT JOIN datos.tienda t ON t.almacen = i.almacen
LEFT JOIN datos.producto p ON p.sku = i.sku
LEFT JOIN datos.costo_articulo c ON c.sku = i.sku
GROUP BY i.fecha_corte, i.empresa, i.almacen, t.nombre, t.categoria, t.region, t.grupo"""
Q['inv_por_sku.csv'] = """WITH inv AS (
  SELECT i.sku,
         SUM(CASE WHEN i.existencia > 0 THEN i.existencia ELSE 0 END) AS piezas,
         SUM(CASE WHEN i.existencia > 0 THEN i.existencia * COALESCE(i.costo_promedio, c.costo_ultimo, 0) ELSE 0 END) AS valor_costo,
         SUM(CASE WHEN i.existencia > 0 AND t.categoria = 'MAY' THEN 0
                  WHEN i.existencia > 0 AND v.almacen IS NOT NULL THEN i.existencia * COALESCE(i.costo_promedio, c.costo_ultimo, 0) ELSE 0 END) AS valor_costo_tiendas
  FROM datos.inventario i
  LEFT JOIN datos.costo_articulo c ON c.sku = i.sku
  LEFT JOIN datos.tienda t ON t.almacen = i.almacen
  LEFT JOIN (SELECT DISTINCT tienda AS almacen FROM datos.venta_semanal WHERE semana BETWEEN @desde AND @fin) v ON v.almacen = i.almacen
  WHERE i.fecha_corte = @corte
  GROUP BY i.sku),
ven AS (
  SELECT vs.sku, SUM(vs.piezas - vs.piezas_devueltas) AS piezas_13s, SUM(vs.importe) AS importe_13s, SUM(vs.costo) AS costo_13s
  FROM datos.venta_semanal vs
  LEFT JOIN datos.tienda t ON t.almacen = vs.tienda
  WHERE vs.semana BETWEEN @desde AND @fin AND COALESCE(t.categoria, '') <> 'MAY'
  GROUP BY vs.sku)
SELECT COALESCE(inv.sku, ven.sku) AS sku, p.descripcion, p.marca, p.departamento, p.clasificacion,
       p.precio_lista, @corte AS corte, @desde AS venta_desde, @fin AS venta_hasta,
       COALESCE(inv.piezas, 0) AS piezas, COALESCE(inv.valor_costo, 0) AS valor_costo,
       COALESCE(inv.valor_costo_tiendas, 0) AS valor_costo_tiendas,
       COALESCE(ven.piezas_13s, 0) AS piezas_13s, COALESCE(ven.importe_13s, 0) AS importe_13s,
       COALESCE(ven.costo_13s, 0) AS costo_13s
FROM inv FULL JOIN ven ON ven.sku = inv.sku
LEFT JOIN datos.producto p ON p.sku = COALESCE(inv.sku, ven.sku)"""
Q['salud_por_tienda.csv'] = """WITH inv AS (
  SELECT i.almacen AS tienda, i.sku, SUM(i.existencia) AS ex, MAX(i.costo_promedio) AS cp
  FROM datos.inventario i WHERE i.fecha_corte = @corte GROUP BY i.almacen, i.sku),
ven AS (
  SELECT tienda, sku, SUM(piezas - piezas_devueltas) AS pz, SUM(importe) AS imp
  FROM datos.venta_semanal WHERE semana BETWEEN @desde AND @fin GROUP BY tienda, sku),
act AS (SELECT DISTINCT tienda FROM datos.venta_semanal WHERE semana BETWEEN @desde AND @fin),
u AS (
  SELECT COALESCE(inv.tienda, ven.tienda) AS tienda, COALESCE(inv.ex, 0) AS ex,
         COALESCE(inv.cp, c.costo_ultimo, 0) AS costo, COALESCE(ven.pz, 0) AS pz, COALESCE(ven.imp, 0) AS imp
  FROM inv FULL JOIN ven ON ven.tienda = inv.tienda AND ven.sku = inv.sku
  LEFT JOIN datos.costo_articulo c ON c.sku = COALESCE(inv.sku, ven.sku)
  WHERE COALESCE(inv.tienda, ven.tienda) IN (SELECT tienda FROM act))
SELECT u.tienda, t.nombre, t.categoria, t.region, t.estado,
       SUM(CASE WHEN ex > 0 THEN ex * costo ELSE 0 END) AS valor_costo,
       SUM(imp) AS importe_13s, SUM(pz) AS piezas_13s,
       SUM(CASE WHEN ex > 0 AND pz <= 0 THEN ex * costo ELSE 0 END) AS valor_sin_venta,
       SUM(CASE WHEN ex > 0 AND pz > 0 AND ex * 91 > pz * 180 THEN ex * costo ELSE 0 END) AS valor_exceso,
       SUM(CASE WHEN ex > 0 AND pz <= 0 THEN 1 ELSE 0 END) AS n_sin_venta,
       SUM(CASE WHEN ex > 0 AND pz > 0 AND ex * 91 > pz * 180 THEN 1 ELSE 0 END) AS n_exceso,
       SUM(CASE WHEN ex <= 0 AND pz >= 13 THEN 1 ELSE 0 END) AS n_en_cero,
       SUM(CASE WHEN ex <= 0 AND pz >= 13 THEN imp ELSE 0 END) AS importe_13s_en_cero,
       SUM(CASE WHEN ex > 0 THEN 1 ELSE 0 END) AS n_con_existencia
FROM u LEFT JOIN datos.tienda t ON t.almacen = u.tienda
GROUP BY u.tienda, t.nombre, t.categoria, t.region, t.estado"""
Q['grupos_tiendas.csv'] = """SELECT g.almacen, g.grupo, g.tipicidad
FROM datos.tienda_grupo g
WHERE g.corrida_id = (SELECT MAX(corrida_id) FROM datos.tienda_grupo_corrida WHERE estado = 'completa')"""
os.makedirs("/tmp/tablero", exist_ok=True)
with motor().connect() as c:
    for nombre, sql in Q.items():
        try:
            r = c.exec_driver_sql("SET NOCOUNT ON;\n" + DECL + sql)
            filas = r.fetchall()
            with open("/tmp/tablero/" + nombre, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f); w.writerow(r.keys()); w.writerows(filas)
            print(nombre, len(filas), "renglones")
        except Exception as e:
            print(nombre, "ERROR", e)
