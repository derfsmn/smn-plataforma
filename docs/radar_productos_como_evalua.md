# Radar de productos: cómo se evalúa un producto nuevo

Versión del 27 de octubre de 2026. Todas las escalas son **provisionales** hasta que Compras capture sus reglas en la Base de conocimiento.

## 1. El resultado

- Se califican **6 factores** de 0 a 100. Hoy cada uno pesa lo mismo (17 %), hasta que Compras defina sus pesos.
- **Puntaje** = el promedio de los factores **que tienen datos**. Un factor sin datos no cuenta como 0: se quita del promedio.
- **Confianza**: alta si hay datos de factores que suman 80 % del peso o más; media si suman 50 a 79 %; baja si es menos.
- **Color**: verde si el puntaje es mayor a 80; amarillo de 60 a 80; rojo si es 59 o menos. Con confianza baja, un verde baja a amarillo. Si el producto cae en una regla de rechazo de Compras, queda en rojo sin importar el puntaje.
- **Oportunidades** (productos que vienen de «Buscar oportunidades»): la pregunta es si vale la pena buscarles proveedor. Si no tienen costo ni proveedor, Rentabilidad y Proveedor dicen «Se califica al conseguir proveedor», no cuentan y la confianza se mide sobre los otros 4 factores (Diego, 2 nov 2026). Si Compras ya capturó costo o proveedor, ese factor cuenta como siempre.
- Compras puede cambiar el color final con un motivo.

**Ejemplo NUOM Colágeno + Electrolitos:** hubo datos en 4 de 6 factores (Rentabilidad 0, Precio 100, Tendencia 100 y Categoría 75). (0 + 100 + 100 + 75) / 4 = 68.75, que se redondea a **69**, amarillo. 4 de 6 factores con datos es 67 %, así que la confianza es **media**.

## 2. Antes de calificar

1. **Clasificación.** La IA propone rama, subcategoría y segmento del catálogo. Si no puede, se toma la subcategoría que comparten al menos el 60 % de los parecidos cercanos. Compras la confirma o la cambia.
2. **Parecidos.** Se buscan los 10 productos activos del catálogo que más se parecen, por palabras del nombre en común. Suben la misma marca, la misma subcategoría, el mismo departamento y la misma forma. Compras puede corregir la lista.
3. **¿Ya lo vendemos?** Si un producto del catálogo tiene el mismo nombre y la misma presentación (por ejemplo, «30 Cápsulas» = «C/30 CAPS»), se avisa arriba y la evaluación usa la venta, el margen y el precio reales de ese SKU. Lo que Compras escriba de más solo puede ser genérico («Bebida hidratante … sabor …»), y los números deben coincidir: 355 ml no es 630 ml.
4. **Internet.** Se busca el producto en Google Shopping y en los sitios de Walmart, Chedraui, San Pablo y Soriana. Se descartan los precios que valen menos de 0.4 o más de 2.5 veces la referencia, porque no son la misma presentación.

## 3. Los 6 factores

| Factor | Con qué se calcula | Escala |
|---|---|---|
| **Demanda** | Venta de SMNBI de las últimas 26 semanas cargadas, sin almacenes de mayoreo. Piezas por tienda al mes de los parecidos (o del mismo SKU si ya lo vendemos), contra los demás productos del departamento (o de toda la cadena, si el departamento tiene menos de 5 con venta). | El puntaje es el percentil: si vende más que el 70 % de los productos, vale 70. Sube o baja hasta 10 puntos según cómo van sus últimas 13 semanas contra las 13 anteriores. |
| **Rentabilidad** | Margen = (precio sin IVA − costo) / precio sin IVA. En ideas: precio visto y costo estimado. En propuestas: lo que puso el proveedor. Si ya lo vendemos, su margen real en SMNBI, aunque Compras haya capturado costo. | En el mínimo (hoy 30 %) vale 60. Cada punto arriba suma 2.7 y llega a 100 con 15 puntos más. Cada punto abajo resta 6. Sube o baja 5 puntos más contra el margen real de su subcategoría. |
| **Precio** | Primero contra internet. Si no hay, contra la competencia que reportó el proveedor. Al final, contra el precio de lista de los parecidos que vendemos. | Igual al mercado vale 70. Cada 1 % más barato suma 2 y cada 1 % más caro resta 2. |
| **Tendencia** | Señales del radar de tendencias de los últimos 6 meses que la IA dice que hablan del producto, su ingrediente o su uso. | Señal alta 100, media 80, temprana 65. Sin señales, 60: no suma ni resta. |
| **Categoría** | Cuántos productos activos hay en su subcategoría: menos productos, más hueco en el surtido. Si no hay subcategoría, cuenta los parecidos con 30 % o más. | Contra el tamaño de la subcategoría donde está el producto típico del catálogo (mediana por producto): hasta la cuarta parte 90; hasta la mitad 80; hasta el típico 70; hasta el doble 60; hasta 4 veces 45; más, 35. Sin subcategoría: 0 parecidos 90, 1 a 3 parecidos 75, 4 a 7 parecidos 65, 8 o más parecidos 55. Más de 180 días de inventario resta 5 y menos de 45 suma 5. Si ya vendemos uno igual o de la misma línea que tiene venta, resta 5. Si es el mismo producto, vale 10. |
| **Proveedor** | Historial real en compras de SMNBI: piezas surtidas, rechazos y días de entrega contra los prometidos. En ideas sin proveedor, el que ya surte esa marca. | Surtir todo vale 90 y cada punto que falta resta 1. Entregar más de 3 días tarde resta 10. Las propuestas suman puntos por GS1, registro sanitario y apoyos de lanzamiento. |

Después, la IA revisa el producto contra las políticas y reglas de Compras. También redacta el «¿Por qué este color?» usando solo los números de arriba.

## 4. Lo que el ejemplo NUOM muestra mal

1. **Demanda «sin datos» estaba mal dicho.** El departamento SUPLEMENTOS casi no tiene productos con venta para comparar, y el mensaje lo hacía pasar por «los parecidos no tienen venta». En la misma pantalla, el 18453 vende 798 piezas al mes. **Corregido:** si el departamento tiene menos de 5 productos con venta, se compara contra toda la cadena.
2. **Rentabilidad 0.** El precio visto de $180 con IVA da $155.17 sin IVA. Contra un costo de $150, el margen es 3.3 %, muy abajo del 30 %. Solo es correcto si los $150 son **sin IVA y por la misma pieza** que se vende en $180.
3. **Precio 100 no significa mucho.** Al no encontrarlo en internet, se comparó contra parecidos de otra presentación: colágeno en tabletas y jabones. Eso no es un precio de la competencia.
4. **Tendencia 100 por una señal que no tiene que ver** («La UE acelera novel foods…»). Ya está más estricta desde la corrección de Demograss; se verá al recalcular.
5. **¿El 18453 COLAGENO ELECTROLITOS LIMON JENGIBRE 12 G (WONU) es este mismo producto?** El sistema no lo reconoció: la marca capturada es WONUMX contra WONU en el catálogo, y los nombres son distintos. Si es el mismo, la evaluación debería decir «Ya lo vendemos».
