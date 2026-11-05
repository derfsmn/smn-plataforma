// Modelo de datos del Semáforo de producto nuevo (TD001), versión 3 (2026-10-12). PROPUESTA: no validada con Compras.
// Generado desde td001/modelo_semaforo_visual.html (misma fuente que docs/modelos/modelo_semaforo_v3.dbml). No editar a mano:
// si cambia el modelo, se cambia el .dbml y se vuelve a generar este archivo.

export type OrigenModelo = "ti" | "cat" | "radar" | "form" | "sis" | "com";
export type CampoModelo = { n: string; t: string; pk?: boolean; u?: boolean; fk?: string; nota?: string };
export type TablaModelo = { nombre: string; nota: string; origen: OrigenModelo; campos: CampoModelo[] };
export type PasoProceso = { titulo: string; pregunta: string; que: string; quien: string; entra: string[]; sale: string[]; tablas: string[]; ia?: boolean };

export const ORIGENES: Record<OrigenModelo, string> = {
 "ti": "Intelisis / Sistemas",
 "cat": "Catálogo consolidado",
 "radar": "Radares",
 "form": "Formulario de proveedor",
 "sis": "Generado por el sistema",
 "com": "Compras / Comité"
};

export const TABLAS_V3: TablaModelo[] = [
 {
  "nombre": "proveedor",
  "nota": "Datos maestros. Desempeño real (cumplimiento, lead time real) se calcula desde orden_compra.",
  "origen": "cat",
  "campos": [
   {
    "n": "proveedor_id",
    "t": "int",
    "pk": true
   },
   {
    "n": "codigo_proveedor",
    "t": "varchar",
    "u": true,
    "nota": "Catálogo consolidado. Nulo si es prospecto (aún no proveedor de SMN)"
   },
   {
    "n": "nombre_proveedor",
    "t": "varchar",
    "nota": "Catálogo consolidado / razón social del formulario"
   },
   {
    "n": "nombre_comercial",
    "t": "varchar",
    "nota": "Formulario"
   },
   {
    "n": "nombre_corto",
    "t": "varchar",
    "nota": "PEDIR A SISTEMAS: nombre corto en Intelisis"
   },
   {
    "n": "categoria",
    "t": "varchar",
    "nota": "PEDIR A SISTEMAS: categoría del proveedor en Intelisis"
   },
   {
    "n": "rfc",
    "t": "varchar",
    "u": true,
    "nota": "Formulario. Llave para ligar prospecto con proveedor existente"
   },
   {
    "n": "es_prospecto",
    "t": "boolean",
    "nota": "true si llegó por el formulario y no está en Intelisis"
   },
   {
    "n": "estatus",
    "t": "varchar",
    "nota": "activo / inactivo / restringido / prospecto"
   },
   {
    "n": "fecha_alta",
    "t": "date",
    "nota": "Antigüedad como proveedor de SMN"
   },
   {
    "n": "origen",
    "t": "varchar",
    "nota": "nacional / importado"
   },
   {
    "n": "calle_numero",
    "t": "varchar"
   },
   {
    "n": "colonia",
    "t": "varchar"
   },
   {
    "n": "ciudad",
    "t": "varchar"
   },
   {
    "n": "codigo_postal",
    "t": "varchar"
   },
   {
    "n": "estado_republica",
    "t": "varchar"
   },
   {
    "n": "dias_credito",
    "t": "int",
    "nota": "Condición vigente con SMN"
   },
   {
    "n": "descuento_pct",
    "t": "decimal(5,2)"
   },
   {
    "n": "monto_minimo_compra",
    "t": "decimal(12,2)"
   },
   {
    "n": "lead_time_pactado_dias",
    "t": "int"
   },
   {
    "n": "acepta_devolucion",
    "t": "boolean"
   },
   {
    "n": "exclusividad",
    "t": "boolean"
   }
  ]
 },
 {
  "nombre": "proveedor_contacto",
  "nota": "Formulario: contacto principal y alterno.",
  "origen": "form",
  "campos": [
   {
    "n": "contacto_id",
    "t": "int",
    "pk": true
   },
   {
    "n": "proveedor_id",
    "t": "int",
    "fk": "proveedor"
   },
   {
    "n": "nombre",
    "t": "varchar"
   },
   {
    "n": "cargo",
    "t": "varchar"
   },
   {
    "n": "correo",
    "t": "varchar"
   },
   {
    "n": "telefono",
    "t": "varchar"
   },
   {
    "n": "es_principal",
    "t": "boolean"
   }
  ]
 },
 {
  "nombre": "producto",
  "nota": "Origen: catálogo consolidado de producto (22 campos) + 6 campos a pedir a Sistemas.",
  "origen": "cat",
  "campos": [
   {
    "n": "producto_id",
    "t": "int",
    "pk": true
   },
   {
    "n": "sku",
    "t": "varchar",
    "u": true,
    "nota": "SKU"
   },
   {
    "n": "nombre",
    "t": "varchar",
    "nota": "Nombre corto del producto"
   },
   {
    "n": "descripcion",
    "t": "varchar",
    "nota": "Descripción: texto descriptivo del producto"
   },
   {
    "n": "marca",
    "t": "varchar",
    "nota": "Marca"
   },
   {
    "n": "departamento",
    "t": "varchar",
    "nota": "Departamento"
   },
   {
    "n": "rama",
    "t": "varchar",
    "nota": "Rama"
   },
   {
    "n": "subcategoria",
    "t": "varchar",
    "nota": "Subcategoría"
   },
   {
    "n": "segmento",
    "t": "varchar",
    "nota": "Segmento"
   },
   {
    "n": "clasificacion",
    "t": "varchar",
    "nota": "Clasificación (significado por confirmar)"
   },
   {
    "n": "proveedor_id",
    "t": "int",
    "fk": "proveedor",
    "nota": "Se liga por Código del proveedor"
   },
   {
    "n": "codigo_barras",
    "t": "varchar",
    "nota": "Código de barras; liga con radar de precios"
   },
   {
    "n": "precio_lista_sin_impuestos",
    "t": "decimal(12,2)"
   },
   {
    "n": "precio_membresia_sin_impuestos",
    "t": "decimal(12,2)"
   },
   {
    "n": "iva_pct",
    "t": "decimal(5,2)"
   },
   {
    "n": "ieps_pct",
    "t": "decimal(5,2)"
   },
   {
    "n": "precio_lista_con_impuestos",
    "t": "decimal(12,2)",
    "nota": "Precio lista con impuestos registrados"
   },
   {
    "n": "precio_membresia_con_impuestos",
    "t": "decimal(12,2)",
    "nota": "Precio membresía con impuestos registrados"
   },
   {
    "n": "tasas_impuestos_incompletas",
    "t": "boolean",
    "nota": "Indicador de tasas de impuestos incompletas"
   },
   {
    "n": "precio_shopify",
    "t": "decimal(12,2)",
    "nota": "Precio publicado en Shopify"
   },
   {
    "n": "moneda_shopify",
    "t": "varchar",
    "nota": "Moneda del precio publicado"
   },
   {
    "n": "disponible_en_linea",
    "t": "boolean",
    "nota": "Disponibilidad en tienda en línea"
   },
   {
    "n": "url_producto",
    "t": "varchar"
   },
   {
    "n": "url_imagen",
    "t": "varchar"
   },
   {
    "n": "contenido_neto",
    "t": "decimal(12,2)",
    "nota": "PEDIR A SISTEMAS: cantidad por envase, p. ej. 60 o 500"
   },
   {
    "n": "unidad_medida",
    "t": "varchar",
    "nota": "PEDIR A SISTEMAS: cápsulas, tabletas, g, ml, etc."
   },
   {
    "n": "costo",
    "t": "decimal(12,2)",
    "nota": "PEDIR A SISTEMAS: costo de compra vigente, sin impuestos"
   },
   {
    "n": "estatus",
    "t": "varchar",
    "nota": "PEDIR A SISTEMAS: activo / baja"
   },
   {
    "n": "fecha_alta",
    "t": "date",
    "nota": "PEDIR A SISTEMAS"
   },
   {
    "n": "fecha_baja",
    "t": "date",
    "nota": "PEDIR A SISTEMAS"
   }
  ]
 },
 {
  "nombre": "tienda",
  "nota": "Ajustar a la entidad TIENDA acordada antes en modelo_smn.dbml cuando se recupere.",
  "origen": "ti",
  "campos": [
   {
    "n": "tienda_id",
    "t": "int",
    "pk": true
   },
   {
    "n": "codigo_tienda",
    "t": "varchar",
    "u": true,
    "nota": "Clave en Intelisis"
   },
   {
    "n": "nombre",
    "t": "varchar"
   },
   {
    "n": "formato",
    "t": "varchar",
    "nota": "Tipo de local"
   },
   {
    "n": "clase",
    "t": "varchar",
    "nota": "Clasificación de la tienda por nivel de venta"
   },
   {
    "n": "calle_numero",
    "t": "varchar"
   },
   {
    "n": "colonia",
    "t": "varchar"
   },
   {
    "n": "estado_republica",
    "t": "varchar"
   },
   {
    "n": "ciudad",
    "t": "varchar"
   },
   {
    "n": "codigo_postal",
    "t": "varchar",
    "nota": "Permite cruzar con datos de nivel socioeconómico (INEGI)"
   },
   {
    "n": "fecha_apertura",
    "t": "date"
   },
   {
    "n": "fecha_cierre",
    "t": "date",
    "nota": "Vacío si sigue abierta"
   },
   {
    "n": "estatus",
    "t": "varchar",
    "nota": "abierta / cerrada"
   },
   {
    "n": "num_empleados",
    "t": "int"
   },
   {
    "n": "metros_cuadrados",
    "t": "decimal(10,2)"
   },
   {
    "n": "num_anaqueles",
    "t": "int",
    "nota": "O metros lineales de exhibición, el dato que exista"
   }
  ]
 },
 {
  "nombre": "venta",
  "nota": "Origen: Intelisis. Granularidad propuesta: producto-tienda-semana. Solo tiendas físicas.",
  "origen": "ti",
  "campos": [
   {
    "n": "venta_id",
    "t": "bigint",
    "pk": true
   },
   {
    "n": "producto_id",
    "t": "int",
    "fk": "producto"
   },
   {
    "n": "tienda_id",
    "t": "int",
    "fk": "tienda"
   },
   {
    "n": "semana",
    "t": "date",
    "nota": "Lunes de la semana"
   },
   {
    "n": "unidades",
    "t": "decimal(12,2)",
    "nota": "Unidades vendidas"
   },
   {
    "n": "unidades_devueltas",
    "t": "decimal(12,2)"
   },
   {
    "n": "importe_bruto",
    "t": "decimal(14,2)",
    "nota": "Antes de descuentos, sin impuestos"
   },
   {
    "n": "descuento",
    "t": "decimal(14,2)"
   },
   {
    "n": "importe",
    "t": "decimal(14,2)",
    "nota": "Neto: bruto menos descuento, sin impuestos"
   },
   {
    "n": "costo",
    "t": "decimal(14,2)"
   },
   {
    "n": "tickets",
    "t": "int",
    "nota": "Número de tickets que incluyen el producto"
   },
   {
    "n": "unidades_membresia",
    "t": "decimal(12,2)",
    "nota": "Parte de las unidades vendidas a socios"
   },
   {
    "n": "importe_membresia",
    "t": "decimal(14,2)"
   }
  ]
 },
 {
  "nombre": "orden_compra",
  "nota": "PEDIR A SISTEMAS. Con esto se calcula lead time real y % de cumplimiento del proveedor.",
  "origen": "ti",
  "campos": [
   {
    "n": "orden_compra_id",
    "t": "bigint",
    "pk": true
   },
   {
    "n": "folio",
    "t": "varchar"
   },
   {
    "n": "proveedor_id",
    "t": "int",
    "fk": "proveedor"
   },
   {
    "n": "producto_id",
    "t": "int",
    "fk": "producto"
   },
   {
    "n": "tienda_id",
    "t": "int",
    "fk": "tienda",
    "nota": "O CEDIS de destino"
   },
   {
    "n": "fecha_pedido",
    "t": "date"
   },
   {
    "n": "fecha_recepcion",
    "t": "date"
   },
   {
    "n": "cantidad_pedida",
    "t": "decimal(12,2)"
   },
   {
    "n": "cantidad_recibida",
    "t": "decimal(12,2)"
   },
   {
    "n": "costo_unitario",
    "t": "decimal(12,2)"
   }
  ]
 },
 {
  "nombre": "costo_precio_historico",
  "nota": "PEDIR A SISTEMAS. Margen histórico de comparables.",
  "origen": "ti",
  "campos": [
   {
    "n": "costo_precio_id",
    "t": "bigint",
    "pk": true
   },
   {
    "n": "producto_id",
    "t": "int",
    "fk": "producto"
   },
   {
    "n": "fecha_inicio",
    "t": "date"
   },
   {
    "n": "fecha_fin",
    "t": "date"
   },
   {
    "n": "costo",
    "t": "decimal(12,2)"
   },
   {
    "n": "precio_lista_sin_impuestos",
    "t": "decimal(12,2)"
   }
  ]
 },
 {
  "nombre": "inventario",
  "nota": "PEDIR A SISTEMAS. Evita confundir falta de venta con falta de producto.",
  "origen": "ti",
  "campos": [
   {
    "n": "inventario_id",
    "t": "bigint",
    "pk": true
   },
   {
    "n": "producto_id",
    "t": "int",
    "fk": "producto"
   },
   {
    "n": "tienda_id",
    "t": "int",
    "fk": "tienda"
   },
   {
    "n": "semana",
    "t": "date"
   },
   {
    "n": "existencia",
    "t": "decimal(12,2)"
   },
   {
    "n": "dias_sin_existencia",
    "t": "int",
    "nota": "Quiebre en la semana"
   }
  ]
 },
 {
  "nombre": "promocion",
  "nota": "PEDIR A SISTEMAS / Mercadotecnia.",
  "origen": "ti",
  "campos": [
   {
    "n": "promocion_id",
    "t": "bigint",
    "pk": true
   },
   {
    "n": "producto_id",
    "t": "int",
    "fk": "producto"
   },
   {
    "n": "fecha_inicio",
    "t": "date"
   },
   {
    "n": "fecha_fin",
    "t": "date"
   },
   {
    "n": "tipo",
    "t": "varchar"
   },
   {
    "n": "descuento_pct",
    "t": "decimal(5,2)"
   }
  ]
 },
 {
  "nombre": "surtido_tienda",
  "nota": "PEDIR A SISTEMAS. En qué tiendas está dado de alta cada producto; permite medir venta por tienda que lo maneja.",
  "origen": "ti",
  "campos": [
   {
    "n": "producto_id",
    "t": "int",
    "pk": true,
    "fk": "producto"
   },
   {
    "n": "tienda_id",
    "t": "int",
    "pk": true,
    "fk": "tienda"
   },
   {
    "n": "fecha_alta",
    "t": "date",
    "pk": true,
    "nota": "Desde cuándo se maneja en la tienda"
   },
   {
    "n": "fecha_baja",
    "t": "date",
    "nota": "Vacío si sigue activo"
   }
  ]
 },
 {
  "nombre": "merma",
  "nota": "PEDIR A SISTEMAS. Afecta la rentabilidad real de comparables.",
  "origen": "ti",
  "campos": [
   {
    "n": "merma_id",
    "t": "bigint",
    "pk": true
   },
   {
    "n": "producto_id",
    "t": "int",
    "fk": "producto"
   },
   {
    "n": "tienda_id",
    "t": "int",
    "fk": "tienda"
   },
   {
    "n": "semana",
    "t": "date"
   },
   {
    "n": "unidades_merma",
    "t": "decimal(12,2)",
    "nota": "Daño, robo u otra causa"
   },
   {
    "n": "unidades_caducadas",
    "t": "decimal(12,2)"
   },
   {
    "n": "costo",
    "t": "decimal(14,2)",
    "nota": "Costo de lo mermado y caducado"
   }
  ]
 },
 {
  "nombre": "devolucion_proveedor",
  "nota": "PEDIR A SISTEMAS (por confirmar que exista). Calidad de lo que surte el proveedor.",
  "origen": "ti",
  "campos": [
   {
    "n": "devolucion_id",
    "t": "bigint",
    "pk": true
   },
   {
    "n": "folio",
    "t": "varchar"
   },
   {
    "n": "proveedor_id",
    "t": "int",
    "fk": "proveedor"
   },
   {
    "n": "producto_id",
    "t": "int",
    "fk": "producto"
   },
   {
    "n": "tienda_id",
    "t": "int",
    "fk": "tienda",
    "nota": "Tienda o CEDIS que devuelve"
   },
   {
    "n": "fecha",
    "t": "date"
   },
   {
    "n": "cantidad",
    "t": "decimal(12,2)"
   },
   {
    "n": "importe",
    "t": "decimal(14,2)"
   },
   {
    "n": "motivo",
    "t": "varchar",
    "nota": "Caducidad, daño, calidad u otro"
   }
  ]
 },
 {
  "nombre": "bonificacion_proveedor",
  "nota": "PEDIR A SISTEMAS (por confirmar que exista). Apoyos reales contra lo prometido en el formulario.",
  "origen": "ti",
  "campos": [
   {
    "n": "bonificacion_id",
    "t": "bigint",
    "pk": true
   },
   {
    "n": "folio",
    "t": "varchar"
   },
   {
    "n": "proveedor_id",
    "t": "int",
    "fk": "proveedor"
   },
   {
    "n": "producto_id",
    "t": "int",
    "fk": "producto",
    "nota": "Vacío si aplica a todo el proveedor"
   },
   {
    "n": "fecha",
    "t": "date"
   },
   {
    "n": "tipo",
    "t": "varchar",
    "nota": "Bonificación, nota de crédito u otro"
   },
   {
    "n": "importe",
    "t": "decimal(14,2)"
   },
   {
    "n": "concepto",
    "t": "varchar"
   }
  ]
 },
 {
  "nombre": "senal",
  "nota": "Una sola tabla para todas las señales externas e internas.",
  "origen": "radar",
  "campos": [
   {
    "n": "senal_id",
    "t": "bigint",
    "pk": true
   },
   {
    "n": "fecha",
    "t": "date",
    "nota": "AAAA-MM-DD"
   },
   {
    "n": "tipo_fuente",
    "t": "varchar",
    "nota": "radar_noticias / google_trends / rrss / expo / proveedor / tienda"
   },
   {
    "n": "titulo",
    "t": "varchar"
   },
   {
    "n": "fuente_url",
    "t": "varchar"
   },
   {
    "n": "nivel",
    "t": "varchar",
    "nota": "ALTA / MEDIA / TEMPRANA"
   },
   {
    "n": "palabra_clave",
    "t": "varchar",
    "nota": "Ingrediente, producto o tendencia"
   },
   {
    "n": "subcategoria",
    "t": "varchar"
   },
   {
    "n": "valor",
    "t": "decimal(12,2)",
    "nota": "Métrica cuando aplica: índice de búsquedas, menciones"
   }
  ]
 },
 {
  "nombre": "precio_competencia",
  "nota": "Origen: radar de precios multitienda.",
  "origen": "radar",
  "campos": [
   {
    "n": "precio_competencia_id",
    "t": "bigint",
    "pk": true
   },
   {
    "n": "competidor",
    "t": "varchar",
    "nota": "Walmart / San Pablo / Chedraui / Soriana / otro"
   },
   {
    "n": "producto_competidor",
    "t": "varchar"
   },
   {
    "n": "codigo_barras",
    "t": "varchar"
   },
   {
    "n": "precio",
    "t": "decimal(12,2)"
   },
   {
    "n": "fecha",
    "t": "date"
   },
   {
    "n": "producto_id",
    "t": "int",
    "fk": "producto",
    "nota": "Si ya lo vendemos"
   },
   {
    "n": "candidato_id",
    "t": "int",
    "fk": "producto_candidato",
    "nota": "Si es un producto nuevo"
   }
  ]
 },
 {
  "nombre": "producto_candidato",
  "nota": "Una solicitud por producto. Las presentaciones van en candidato_presentacion.",
  "origen": "form",
  "campos": [
   {
    "n": "candidato_id",
    "t": "int",
    "pk": true
   },
   {
    "n": "folio",
    "t": "varchar",
    "u": true,
    "nota": "Folio que recibe el proveedor"
   },
   {
    "n": "fecha_registro",
    "t": "datetime"
   },
   {
    "n": "canal_registro",
    "t": "varchar",
    "nota": "formulario_proveedor / captura_compras / radar / tienda"
   },
   {
    "n": "proveedor_id",
    "t": "int",
    "fk": "proveedor"
   },
   {
    "n": "contacto_id",
    "t": "int",
    "fk": "proveedor_contacto"
   },
   {
    "n": "marca",
    "t": "varchar"
   },
   {
    "n": "descripcion",
    "t": "varchar(180)"
   },
   {
    "n": "departamento",
    "t": "varchar",
    "nota": "Elegido por el proveedor de la lista del catálogo"
   },
   {
    "n": "rama",
    "t": "varchar",
    "nota": "Sugerida por IA, confirmada por Compras"
   },
   {
    "n": "subcategoria",
    "t": "varchar",
    "nota": "Sugerida por IA, confirmada por Compras"
   },
   {
    "n": "segmento",
    "t": "varchar",
    "nota": "Sugerido por IA, confirmado por Compras"
   },
   {
    "n": "clasificacion_confirmada",
    "t": "boolean",
    "nota": "Compras validó rama, subcategoría y segmento"
   },
   {
    "n": "ingrediente_principal",
    "t": "varchar"
   },
   {
    "n": "forma",
    "t": "varchar",
    "nota": "cápsula / tableta / polvo / líquido / gomita / otro"
   },
   {
    "n": "tipo_regulatorio",
    "t": "varchar",
    "nota": "suplemento / alimento / bebida / cosmético / herbolario / medicamento / otro"
   },
   {
    "n": "registro_sanitario",
    "t": "varchar"
   },
   {
    "n": "fabricante",
    "t": "varchar"
   },
   {
    "n": "pais_origen",
    "t": "varchar"
   },
   {
    "n": "diferenciador",
    "t": "varchar"
   },
   {
    "n": "necesidad_atendida",
    "t": "varchar"
   },
   {
    "n": "canal_actual",
    "t": "varchar",
    "nota": "no_se_comercializa / fisico / digital / ambos"
   },
   {
    "n": "sin_comparables",
    "t": "boolean"
   },
   {
    "n": "similares_en_smn",
    "t": "boolean"
   },
   {
    "n": "similares_cuales",
    "t": "varchar",
    "nota": "Texto del proveedor; el sistema busca los reales por kNN"
   },
   {
    "n": "minimo_compra_piezas",
    "t": "int"
   },
   {
    "n": "dias_credito",
    "t": "int"
   },
   {
    "n": "acepta_devolucion",
    "t": "boolean"
   },
   {
    "n": "condicion_devolucion",
    "t": "varchar"
   },
   {
    "n": "cobertura",
    "t": "varchar",
    "nota": "local / foraneo"
   },
   {
    "n": "destinos",
    "t": "varchar"
   },
   {
    "n": "tiempo_entrega",
    "t": "varchar",
    "nota": "Rango de días naturales"
   },
   {
    "n": "vida_util_total",
    "t": "int"
   },
   {
    "n": "vida_util_minima_entrega",
    "t": "int"
   },
   {
    "n": "unidad_vida_util",
    "t": "varchar",
    "nota": "meses / días"
   },
   {
    "n": "argumento_principal",
    "t": "varchar"
   },
   {
    "n": "sustento",
    "t": "varchar(220)"
   },
   {
    "n": "acepta_aviso_privacidad",
    "t": "boolean"
   },
   {
    "n": "declara_veracidad",
    "t": "boolean"
   },
   {
    "n": "estado",
    "t": "varchar",
    "nota": "borrador / registrado / evaluado / a_comite / aprobado / rechazado"
   },
   {
    "n": "responsable_compras",
    "t": "varchar"
   },
   {
    "n": "producto_id",
    "t": "int",
    "fk": "producto",
    "nota": "SKU asignado si se aprueba"
   }
  ]
 },
 {
  "nombre": "candidato_opcion",
  "nota": "Respuestas de selección múltiple del formulario, una fila por opción marcada.",
  "origen": "form",
  "campos": [
   {
    "n": "candidato_id",
    "t": "int",
    "pk": true,
    "fk": "producto_candidato"
   },
   {
    "n": "campo",
    "t": "varchar",
    "pk": true,
    "nota": "publico_objetivo / comercios_actuales / manejo_especial / certificacion"
   },
   {
    "n": "valor",
    "t": "varchar",
    "pk": true
   },
   {
    "n": "detalle",
    "t": "varchar",
    "nota": "Texto cuando la opción es otro"
   }
  ]
 },
 {
  "nombre": "candidato_desempeno",
  "nota": "Pregunta 8. Autodeclarado: entra con menos peso que ventas internas.",
  "origen": "form",
  "campos": [
   {
    "n": "candidato_id",
    "t": "int",
    "pk": true,
    "fk": "producto_candidato"
   },
   {
    "n": "tipo",
    "t": "varchar",
    "pk": true,
    "nota": "unidades_mes / unidades_sucursal_mes / posicion_categoria"
   },
   {
    "n": "cifra",
    "t": "decimal(14,2)"
   },
   {
    "n": "canal",
    "t": "varchar"
   },
   {
    "n": "periodo",
    "t": "varchar"
   },
   {
    "n": "fuente",
    "t": "varchar"
   }
  ]
 },
 {
  "nombre": "candidato_senal",
  "nota": "Señales que respaldan al candidato.",
  "origen": "sis",
  "campos": [
   {
    "n": "candidato_id",
    "t": "int",
    "pk": true,
    "fk": "producto_candidato"
   },
   {
    "n": "senal_id",
    "t": "bigint",
    "pk": true,
    "fk": "senal"
   },
   {
    "n": "relevancia",
    "t": "decimal(4,3)",
    "nota": "Similitud calculada entre señal y candidato"
   }
  ]
 },
 {
  "nombre": "modelo_score",
  "nota": "Versiona reglas y pesos para que cada evaluación sea reproducible.",
  "origen": "com",
  "campos": [
   {
    "n": "version",
    "t": "varchar",
    "pk": true,
    "nota": "v0, v1..."
   },
   {
    "n": "fecha_vigencia",
    "t": "date"
   },
   {
    "n": "pesos",
    "t": "json",
    "nota": "Peso por componente"
   },
   {
    "n": "corte_verde",
    "t": "int",
    "nota": "Verde si score > 80"
   },
   {
    "n": "corte_amarillo",
    "t": "int",
    "nota": "Amarillo de 60 a 80; rojo 59 o menos"
   },
   {
    "n": "aprobado_por",
    "t": "varchar"
   }
  ]
 },
 {
  "nombre": "evaluacion_semaforo",
  "nota": "Una fila por evaluación; conserva lo sugerido y lo decidido.",
  "origen": "sis",
  "campos": [
   {
    "n": "evaluacion_id",
    "t": "int",
    "pk": true
   },
   {
    "n": "candidato_id",
    "t": "int",
    "fk": "producto_candidato"
   },
   {
    "n": "modelo_version",
    "t": "varchar",
    "fk": "modelo_score"
   },
   {
    "n": "fecha",
    "t": "datetime"
   },
   {
    "n": "bloqueo",
    "t": "varchar",
    "nota": "Motivo si hubo rojo directo"
   },
   {
    "n": "score",
    "t": "int",
    "nota": "0-100"
   },
   {
    "n": "confianza",
    "t": "varchar",
    "nota": "alta / media / baja"
   },
   {
    "n": "color",
    "t": "varchar",
    "nota": "verde / amarillo / rojo"
   },
   {
    "n": "explicacion",
    "t": "text",
    "nota": "Redactada por IA a partir de los componentes"
   },
   {
    "n": "color_final",
    "t": "varchar",
    "nota": "Decisión de Compras"
   },
   {
    "n": "justificacion_ajuste",
    "t": "text"
   },
   {
    "n": "evaluado_por",
    "t": "varchar"
   }
  ]
 },
 {
  "nombre": "evaluacion_componente",
  "nota": "El benchmark por componente; es lo que hace explicable el score.",
  "origen": "sis",
  "campos": [
   {
    "n": "evaluacion_id",
    "t": "int",
    "pk": true,
    "fk": "evaluacion_semaforo"
   },
   {
    "n": "componente",
    "t": "varchar",
    "pk": true,
    "nota": "demanda / rentabilidad / precio / tendencia / categoria / proveedor"
   },
   {
    "n": "valor_crudo",
    "t": "decimal(14,4)",
    "nota": "Ej. margen 38%, índice de precio 0.95"
   },
   {
    "n": "percentil",
    "t": "decimal(5,2)",
    "nota": "Dentro de la subcategoría"
   },
   {
    "n": "puntaje",
    "t": "decimal(5,2)",
    "nota": "0-100"
   },
   {
    "n": "peso",
    "t": "decimal(5,2)"
   },
   {
    "n": "detalle",
    "t": "text"
   }
  ]
 },
 {
  "nombre": "candidato_comparable",
  "nota": "Los productos internos contra los que se comparó (kNN).",
  "origen": "sis",
  "campos": [
   {
    "n": "evaluacion_id",
    "t": "int",
    "pk": true,
    "fk": "evaluacion_semaforo"
   },
   {
    "n": "producto_id",
    "t": "int",
    "pk": true,
    "fk": "producto"
   },
   {
    "n": "similitud",
    "t": "decimal(4,3)"
   },
   {
    "n": "rango",
    "t": "int",
    "nota": "1 = el más parecido"
   },
   {
    "n": "venta_semanal_tienda",
    "t": "decimal(12,2)"
   },
   {
    "n": "margen_pct",
    "t": "decimal(5,2)"
   }
  ]
 },
 {
  "nombre": "decision_comite",
  "nota": "Las decisiones pasadas no están guardadas (proceso manual). Se registran desde el arranque y sirven para entrenar el modelo de aprendizaje.",
  "origen": "com",
  "campos": [
   {
    "n": "decision_id",
    "t": "int",
    "pk": true
   },
   {
    "n": "candidato_id",
    "t": "int",
    "fk": "producto_candidato"
   },
   {
    "n": "fecha",
    "t": "date"
   },
   {
    "n": "decision",
    "t": "varchar",
    "nota": "aprobado / rechazado / condicionado"
   },
   {
    "n": "motivo",
    "t": "text"
   },
   {
    "n": "meta_exito",
    "t": "text",
    "nota": "Venta, tiendas, margen y periodo esperados"
   }
  ]
 },
 {
  "nombre": "candidato_presentacion",
  "nota": "Una fila por presentación. Costo, precio y precio por porción se comparan aquí.",
  "origen": "form",
  "campos": [
   {
    "n": "presentacion_id",
    "t": "int",
    "pk": true
   },
   {
    "n": "candidato_id",
    "t": "int",
    "fk": "producto_candidato"
   },
   {
    "n": "codigo_barras",
    "t": "varchar",
    "nota": "EAN/GTIN con dígito verificador validado"
   },
   {
    "n": "contenido_neto",
    "t": "decimal(10,2)"
   },
   {
    "n": "unidad_medida",
    "t": "varchar",
    "nota": "g / kg / ml / L / cápsulas / tabletas / piezas"
   },
   {
    "n": "porciones_por_envase",
    "t": "decimal(10,2)",
    "nota": "PROPUESTO, no está en el formulario aún"
   },
   {
    "n": "cantidad_ingrediente_porcion",
    "t": "decimal(10,3)",
    "nota": "PROPUESTO. Ej. 400 (mg de magnesio por porción)"
   },
   {
    "n": "unidad_ingrediente",
    "t": "varchar",
    "nota": "PROPUESTO. mg / g / UI / UFC"
   },
   {
    "n": "piezas_caja_master",
    "t": "int"
   },
   {
    "n": "costo_neto_sin_iva",
    "t": "decimal(12,2)"
   },
   {
    "n": "pvp_sugerido",
    "t": "decimal(12,2)"
   },
   {
    "n": "tasa_iva",
    "t": "varchar"
   },
   {
    "n": "tasa_ieps",
    "t": "varchar"
   },
   {
    "n": "margen_propuesto_pct",
    "t": "decimal(5,2)",
    "nota": "Referencia; SMN recalcula"
   },
   {
    "n": "duplicado_producto_id",
    "t": "int",
    "fk": "producto",
    "nota": "Se llena si el código de barras ya existe en catálogo"
   }
  ]
 },
 {
  "nombre": "candidato_competidor",
  "nota": "Hasta 3 competidores declarados por el proveedor (autodeclarado).",
  "origen": "form",
  "campos": [
   {
    "n": "candidato_id",
    "t": "int",
    "pk": true,
    "fk": "producto_candidato"
   },
   {
    "n": "orden",
    "t": "int",
    "pk": true
   },
   {
    "n": "marca",
    "t": "varchar"
   },
   {
    "n": "producto",
    "t": "varchar"
   },
   {
    "n": "presentacion",
    "t": "varchar"
   },
   {
    "n": "precio_publico",
    "t": "decimal(12,2)"
   },
   {
    "n": "comercio",
    "t": "varchar"
   }
  ]
 },
 {
  "nombre": "candidato_adjunto",
  "nota": "Imágenes y documentos del formulario.",
  "origen": "form",
  "campos": [
   {
    "n": "adjunto_id",
    "t": "int",
    "pk": true
   },
   {
    "n": "candidato_id",
    "t": "int",
    "fk": "producto_candidato"
   },
   {
    "n": "tipo",
    "t": "varchar",
    "nota": "imagen_producto / imagen_etiquetado / ficha_tecnica / benchmark / documento_adicional"
   },
   {
    "n": "etiqueta",
    "t": "varchar",
    "nota": "frente / reverso / lateral / tabla_nutrimental / sellos / certificacion / ingredientes / otra"
   },
   {
    "n": "nombre_archivo",
    "t": "varchar"
   },
   {
    "n": "url",
    "t": "varchar"
   },
   {
    "n": "tamano_mb",
    "t": "decimal(6,2)"
   },
   {
    "n": "fecha_carga",
    "t": "datetime"
   },
   {
    "n": "extraido_ia",
    "t": "json",
    "nota": "Datos que la IA leyó de la imagen o PDF (contenido, registro, ingredientes)"
   },
   {
    "n": "discrepancias",
    "t": "text",
    "nota": "Diferencias entre lo extraído y lo declarado"
   }
  ]
 },
 {
  "nombre": "candidato_condicion",
  "nota": "Condiciones comerciales (pregunta 12) y apoyos de lanzamiento (pregunta 15).",
  "origen": "form",
  "campos": [
   {
    "n": "candidato_id",
    "t": "int",
    "fk": "producto_candidato"
   },
   {
    "n": "tipo",
    "t": "varchar",
    "nota": "descuento_introduccion / capacitacion / bonificacion / promociones / muestras / pop / contenido_digital / campana / inversion / otro"
   },
   {
    "n": "clase",
    "t": "varchar",
    "nota": "condicion_comercial / apoyo_lanzamiento"
   },
   {
    "n": "detalle",
    "t": "varchar",
    "nota": "Porcentaje, monto o condición"
   },
   {
    "n": "fecha_inicio",
    "t": "date"
   },
   {
    "n": "fecha_fin",
    "t": "date"
   }
  ]
 },
 {
  "nombre": "lista_restriccion",
  "nota": "Lo que manda a rojo directo. La define Compras; hoy no existe formalizada.",
  "origen": "com",
  "campos": [
   {
    "n": "restriccion_id",
    "t": "int",
    "pk": true
   },
   {
    "n": "tipo",
    "t": "varchar",
    "nota": "proveedor / marca / ingrediente / tipo_regulatorio / departamento"
   },
   {
    "n": "valor",
    "t": "varchar"
   },
   {
    "n": "motivo",
    "t": "varchar"
   },
   {
    "n": "vigente",
    "t": "boolean"
   },
   {
    "n": "definido_por",
    "t": "varchar"
   }
  ]
 },
 {
  "nombre": "parametro_departamento",
  "nota": "Umbrales por departamento que usa la evaluación automática. Los define Compras.",
  "origen": "com",
  "campos": [
   {
    "n": "departamento",
    "t": "varchar",
    "pk": true
   },
   {
    "n": "margen_minimo_pct",
    "t": "decimal(5,2)",
    "nota": "Debajo de esto, alerta o rojo"
   },
   {
    "n": "vida_util_minima_meses",
    "t": "int",
    "nota": "Vida útil mínima aceptable al recibir"
   },
   {
    "n": "requiere_registro_sanitario",
    "t": "boolean"
   },
   {
    "n": "max_dias_entrega",
    "t": "int"
   }
  ]
 }
];

// [tabla, campo, tabla referida, campo referido]
export const RELACIONES_V3: [string, string, string, string][] = [["proveedor_contacto", "proveedor_id", "proveedor", "proveedor_id"], ["producto", "proveedor_id", "proveedor", "proveedor_id"], ["venta", "producto_id", "producto", "producto_id"], ["venta", "tienda_id", "tienda", "tienda_id"], ["orden_compra", "proveedor_id", "proveedor", "proveedor_id"], ["orden_compra", "producto_id", "producto", "producto_id"], ["orden_compra", "tienda_id", "tienda", "tienda_id"], ["costo_precio_historico", "producto_id", "producto", "producto_id"], ["inventario", "producto_id", "producto", "producto_id"], ["inventario", "tienda_id", "tienda", "tienda_id"], ["promocion", "producto_id", "producto", "producto_id"], ["surtido_tienda", "producto_id", "producto", "producto_id"], ["surtido_tienda", "tienda_id", "tienda", "tienda_id"], ["merma", "producto_id", "producto", "producto_id"], ["merma", "tienda_id", "tienda", "tienda_id"], ["devolucion_proveedor", "proveedor_id", "proveedor", "proveedor_id"], ["devolucion_proveedor", "producto_id", "producto", "producto_id"], ["devolucion_proveedor", "tienda_id", "tienda", "tienda_id"], ["bonificacion_proveedor", "proveedor_id", "proveedor", "proveedor_id"], ["bonificacion_proveedor", "producto_id", "producto", "producto_id"], ["precio_competencia", "producto_id", "producto", "producto_id"], ["precio_competencia", "candidato_id", "producto_candidato", "candidato_id"], ["producto_candidato", "proveedor_id", "proveedor", "proveedor_id"], ["producto_candidato", "contacto_id", "proveedor_contacto", "contacto_id"], ["producto_candidato", "producto_id", "producto", "producto_id"], ["candidato_opcion", "candidato_id", "producto_candidato", "candidato_id"], ["candidato_desempeno", "candidato_id", "producto_candidato", "candidato_id"], ["candidato_senal", "candidato_id", "producto_candidato", "candidato_id"], ["candidato_senal", "senal_id", "senal", "senal_id"], ["evaluacion_semaforo", "candidato_id", "producto_candidato", "candidato_id"], ["evaluacion_semaforo", "modelo_version", "modelo_score", "version"], ["evaluacion_componente", "evaluacion_id", "evaluacion_semaforo", "evaluacion_id"], ["candidato_comparable", "evaluacion_id", "evaluacion_semaforo", "evaluacion_id"], ["candidato_comparable", "producto_id", "producto", "producto_id"], ["decision_comite", "candidato_id", "producto_candidato", "candidato_id"], ["candidato_presentacion", "candidato_id", "producto_candidato", "candidato_id"], ["candidato_presentacion", "duplicado_producto_id", "producto", "producto_id"], ["candidato_competidor", "candidato_id", "producto_candidato", "candidato_id"], ["candidato_adjunto", "candidato_id", "producto_candidato", "candidato_id"], ["candidato_condicion", "candidato_id", "producto_candidato", "candidato_id"]];

// Columnas del mapa, de izquierda a derecha, con sus bloques
export const COLUMNAS_V3: { bloque: string; tablas: string[] }[][] = [
 [
  {
   "bloque": "Solicitud del proveedor",
   "tablas": [
    "producto_candidato",
    "candidato_presentacion",
    "candidato_opcion",
    "candidato_desempeno",
    "candidato_competidor",
    "candidato_adjunto",
    "candidato_condicion",
    "proveedor_contacto"
   ]
  }
 ],
 [
  {
   "bloque": "Evaluación",
   "tablas": [
    "evaluacion_semaforo",
    "evaluacion_componente",
    "candidato_comparable",
    "candidato_senal",
    "modelo_score",
    "decision_comite"
   ]
  }
 ],
 [
  {
   "bloque": "Políticas de Compras",
   "tablas": [
    "lista_restriccion",
    "parametro_departamento"
   ]
  },
  {
   "bloque": "Señales externas",
   "tablas": [
    "senal",
    "precio_competencia"
   ]
  }
 ],
 [
  {
   "bloque": "Catálogo y maestros",
   "tablas": [
    "producto",
    "proveedor",
    "tienda"
   ]
  }
 ],
 [
  {
   "bloque": "Histórico de Intelisis",
   "tablas": [
    "venta",
    "costo_precio_historico",
    "orden_compra",
    "inventario",
    "promocion",
    "surtido_tienda",
    "merma",
    "devolucion_proveedor",
    "bonificacion_proveedor"
   ]
  }
 ]
];

export const PASOS_SEMAFORO: PasoProceso[] = [
 {
  "titulo": "Registro",
  "pregunta": "¿Llegó completo?",
  "que": "El proveedor llena el formulario en línea, con presentaciones, precios e imágenes. Compras también puede capturar oportunidades de otras fuentes.",
  "quien": "Proveedor o comprador",
  "entra": [
   "Formulario de 9 secciones",
   "Fotos del producto y del etiquetado",
   "Ficha técnica"
  ],
  "sale": [
   "Solicitud con folio en estado “registrado”"
  ],
  "tablas": [
   "producto_candidato",
   "candidato_presentacion",
   "candidato_opcion",
   "candidato_desempeno",
   "candidato_competidor",
   "candidato_adjunto",
   "candidato_condicion",
   "proveedor",
   "proveedor_contacto"
  ]
 },
 {
  "titulo": "Validación y clasificación",
  "pregunta": "¿Qué es y dónde va?",
  "que": "El sistema valida formatos. La IA lee ficha e imágenes, marca diferencias con lo declarado y sugiere rama, subcategoría y segmento.",
  "quien": "Sistema e IA; Compras confirma la clasificación",
  "entra": [
   "Solicitud registrada",
   "Árbol de categorías del catálogo"
  ],
  "sale": [
   "Clasificación confirmada",
   "Discrepancias detectadas"
  ],
  "tablas": [
   "producto_candidato",
   "candidato_adjunto",
   "candidato_presentacion",
   "producto",
   "proveedor"
  ],
  "ia": true
 },
 {
  "titulo": "Bloqueos",
  "pregunta": "¿Hay algo que lo descarte?",
  "que": "Reglas fijas: proveedor o ingrediente restringido, código de barras ya en catálogo, sin registro sanitario, vida útil o margen debajo del mínimo del departamento.",
  "quien": "Sistema, con reglas que define Compras",
  "entra": [
   "Lista de restricciones",
   "Umbrales por departamento",
   "Catálogo"
  ],
  "sale": [
   "Rojo directo con motivo, o pasa a benchmark"
  ],
  "tablas": [
   "lista_restriccion",
   "parametro_departamento",
   "producto_candidato",
   "candidato_presentacion",
   "producto",
   "proveedor",
   "evaluacion_semaforo"
  ]
 },
 {
  "titulo": "Benchmark",
  "pregunta": "¿Cómo se compara?",
  "que": "Busca los productos internos más parecidos (kNN) y compara venta, margen, precio contra competencia, señales de tendencia, salud de la categoría y desempeño del proveedor.",
  "quien": "Sistema",
  "entra": [
   "Ventas, costos y órdenes de compra",
   "Radar de precios y de noticias"
  ],
  "sale": [
   "Comparables y valor de cada componente"
  ],
  "tablas": [
   "candidato_presentacion",
   "producto",
   "venta",
   "costo_precio_historico",
   "orden_compra",
   "tienda",
   "inventario",
   "promocion",
   "surtido_tienda",
   "merma",
   "devolucion_proveedor",
   "bonificacion_proveedor",
   "precio_competencia",
   "senal",
   "candidato_senal",
   "candidato_comparable",
   "evaluacion_componente"
  ]
 },
 {
  "titulo": "Score y confianza",
  "pregunta": "¿Cuánto suma?",
  "que": "Cada componente se convierte a percentil dentro de su subcategoría y se suma con los pesos vigentes. La confianza baja si faltan comparables o precios de competencia.",
  "quien": "Sistema, con pesos aprobados por Compras",
  "entra": [
   "Componentes del benchmark",
   "Versión vigente de pesos y cortes"
  ],
  "sale": [
   "Score 0 a 100",
   "Confianza alta, media o baja"
  ],
  "tablas": [
   "evaluacion_componente",
   "modelo_score",
   "evaluacion_semaforo",
   "parametro_departamento"
  ]
 },
 {
  "titulo": "Semáforo con explicación",
  "pregunta": "¿Por qué ese color?",
  "que": "Se asigna verde, amarillo o rojo. La IA redacta motivos, riesgos y preguntas para Compras a partir de los componentes; no calcula el color.",
  "quien": "Sistema e IA",
  "entra": [
   "Score, confianza y bloqueos",
   "Comparables"
  ],
  "sale": [
   "Color sugerido con explicación"
  ],
  "tablas": [
   "evaluacion_semaforo",
   "evaluacion_componente",
   "candidato_comparable",
   "candidato_adjunto",
   "producto_candidato"
  ],
  "ia": true
 },
 {
  "titulo": "Revisión de Compras",
  "pregunta": "¿Lo confirmamos?",
  "que": "El comprador confirma o cambia el color y deja su justificación. Los verdes pasan a Comité con su ficha.",
  "quien": "Comprador de la categoría",
  "entra": [
   "Semáforo sugerido y ficha"
  ],
  "sale": [
   "Color final",
   "Estado “a comité” o “rechazado”"
  ],
  "tablas": [
   "evaluacion_semaforo",
   "producto_candidato"
  ]
 },
 {
  "titulo": "Comité y aprendizaje",
  "pregunta": "¿Entra? ¿Funcionó?",
  "que": "El Comité decide y define la meta de éxito. Después se compara la venta real contra la meta y contra el score, para ajustar pesos y cortes. Las decisiones pasadas no están guardadas; se registran desde el arranque.",
  "quien": "Comité de Producto Nuevo",
  "entra": [
   "Expedientes evaluados",
   "Ventas reales del producto"
  ],
  "sale": [
   "Decisión y meta de éxito",
   "Nueva versión de pesos"
  ],
  "tablas": [
   "decision_comite",
   "producto_candidato",
   "producto",
   "venta",
   "modelo_score"
  ]
 }
];
