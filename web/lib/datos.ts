// Tipos del catálogo de productos del Centro de datos (/api/datos)

export type EstadoProductos = "activos" | "archivados" | "diferencias" | "incompletos" | "todos";

export type ProductoResumen = {
  id: number;
  sku: string;
  descripcion: string | null;
  marca: string | null;
  departamento: string | null;
  nombre_proveedor: string | null;
  precio_lista_con_impuestos: string | null;
  precio_membresia_con_impuestos: string | null;
  origen: "API" | "TIENDA" | "AMBOS" | "ETL" | "ARCHIVADO";
  activo: boolean;
  con_diferencias: boolean;
  datos_incompletos: boolean;
  liga_imagen: string | null;
  actualizado_en: string;
};

export type PaginaProductos = { total: number; pagina: number; por_pagina: number; productos: ProductoResumen[] };

export type ProductoDetalle = ProductoResumen & {
  rama: string | null;
  subcategoria: string | null;
  segmento: string | null;
  clasificacion: string | null;
  codigo_proveedor: string | null;
  codigo_barras: string | null;
  precio_lista: string | null;
  precio_membresia: string | null;
  iva_pct: string | null;
  ieps_pct: string | null;
  precio_tienda_en_linea: string | null;
  disponible_en_linea: boolean | null;
  liga_producto: string | null;
  creado_en: string;
  de_donde: Record<string, string>;
  diferencias: { campo: string; valores: Record<string, string> }[];
  fuentes: { fuente: string; presente: boolean; visto_por_ultima_vez_en: string; datos: Record<string, unknown> }[];
  historial: {
    vigente_desde: string;
    precio_lista: string | null;
    precio_membresia: string | null;
    iva_pct: string | null;
    ieps_pct: string | null;
    precio_tienda_en_linea: string | null;
  }[];
};

export type Carga = {
  id: number;
  fuente: string;
  disparada_por: "programador" | "manual";
  usuario: string | null;
  estado: "en_curso" | "completa" | "fallida";
  completa: boolean;
  paginas: number;
  leidos: number;
  creados: number;
  actualizados: number;
  sin_cambios: number;
  ausentes: number;
  invalidos: number;
  precios_cambiados: number;
  total_fuente: number | null;
  error: string | null;
  inicio_en: string;
  fin_en: string | null;
};

export type EstadoCatalogo = {
  falta_configurar: string[];
  tienda_url: string;
  automatico: boolean;
  hora: number;
  dias_semana: number[];
  zona_horaria: string;
  en_curso: Carga | null;
  totales: {
    productos: number;
    activos: number;
    archivados: number;
    con_diferencias: number;
    incompletos: number;
    en_api: number;
    en_tienda: number;
    con_imagen: number;
  };
  cargas: Carga[];
};

export const FUENTES: Record<string, string> = {
  API: "API de artículos SMN",
  TIENDA: "Tienda en línea",
  ETL: "Base de Sistemas (Azure)",
  AMBOS: "API y tienda en línea",
  ARCHIVADO: "Archivado",
  CDN: "Foto por SKU en la tienda",
};

