// Datos → Proveedores: calificación de cada proveedor con compras, venta, costo e inventario de SMNBI.

export const RUTA = "/api/datos/proveedores";

export type ColorProveedor = "verde" | "amarillo" | "rojo";
export type Confianza = "alta" | "media" | "baja" | "sin_datos";
export type Bloque = "cumplimiento" | "comercial" | "costo" | "inventario";

export type Evaluacion = {
  id: number;
  estado: "en_curso" | "completa" | "fallida";
  iniciada_por: string | null;
  iniciada_en: string;
  terminada_en: string | null;
  proveedores: number | null;
  calificados: number | null;
  contexto: { venta?: string; inventario?: string; compras?: string; precios?: string | null; margen_empresa?: number | null };
  error: string | null;
};

export type FilaProveedor = {
  proveedor: string;
  nombre: string | null;
  puntaje: number | null;
  color: ColorProveedor | null;
  confianza: Confianza;
  cumplimiento: number | null;
  comercial: number | null;
  costo: number | null;
  inventario: number | null;
  skus_activos: number;
  venta: string | null;
  compra: string | null;
  agente: string | null; // clave del agente en Intelisis
  rfc: string | null;
};

export type ListaProveedores = {
  evaluacion: Evaluacion | null;
  en_curso: Evaluacion | null;
  bloques: { clave: Bloque; nombre: string; que_mide: string; peso: number }[];
  pesos_de: "compras" | "provisionales";
  conteo: Partial<Record<ColorProveedor | "sin_datos", number>>;
  filas: FilaProveedor[];
  agentes: string[];
  /** Excel para Compras: proveedores en ALTA con agente y qué se cargó después de la evaluación. */
  reporte?: { proveedores?: number; desactualizada?: string | null };
};

export type SkuProveedor = {
  sku: string;
  descripcion: string | null;
  departamento: string | null;
  activo: boolean;
  por_tienda_mes: number;
  venta: number;
  margen_pct: number | null;
  dias_inventario: number | null;
  sin_venta_con_existencia: boolean;
  meta: number;
  permanencia: number;
};

export type MetricasProveedor = {
  notas: string[];
  cumplimiento?: { ordenes: number; surtido_pct: number; perdidas_rechazadas_pct: number; dias_reales: number | null; dias_prometidos: number | null; retraso_dias: number | null };
  comercial?: {
    margen_pct: number | null;
    margen_empresa_pct: number | null;
    skus_activos: number;
    buena_rotacion: number;
    buena_rotacion_pct: number;
    debajo_permanencia: number;
    debajo_permanencia_pct: number;
  };
  costo?: { alza_costo_pct: number | null; skus_con_costo: number; condicion: string | null; dias_credito: number | null; descuento: string | null };
  inventario?: { existencia: number; dias: number | null; skus_con_existencia: number; skus_exceso: number; skus_exceso_pct: number };
  precio_mercado?: { productos: number; mediana_dif_pct: number; mas_caros: number };
  skus?: SkuProveedor[];
};

export type FichaProveedor = FilaProveedor & {
  estatus: string | null;
  condicion: string | null;
  descuento: string | null;
  dias_entrega: number | null;
  metricas: MetricasProveedor;
  ordenes_por_mes: { mes: string; ordenes: number; pedidas: number; recibidas: number }[];
};

export const COLOR: Record<ColorProveedor | "sin_datos", { texto: string; punto: string; insignia: string }> = {
  verde: { texto: "Verde", punto: "bg-emerald-500", insignia: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" },
  amarillo: { texto: "Amarillo", punto: "bg-amber-400", insignia: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300" },
  rojo: { texto: "Rojo", punto: "bg-red-500", insignia: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300" },
  sin_datos: { texto: "Sin datos", punto: "bg-smn-gris-300", insignia: "bg-smn-gris-100 text-smn-gris-700" },
};

export const CONFIANZA: Record<Confianza, string> = {
  alta: "Confianza alta",
  media: "Confianza media",
  baja: "Confianza baja",
  sin_datos: "Sin datos",
};
