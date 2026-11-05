// Datos → Mapa de tiendas: cada almacén de tblAlmacenes con su ubicación y la venta de sus últimas 13 semanas.

export const RUTA = "/api/datos/tiendas";

export type Ubicacion = "ok" | "falta" | "fuera";

export type TiendaMapa = {
  almacen: string;
  nombre: string;
  poblacion: string | null;
  estado: string | null;
  codigo_postal: string | null;
  region: string | null;
  categoria: string | null;
  grupo: string | null;
  ruta: string | null;
  estatus: string | null;
  fecha_apertura: string | null;
  latitud: number | null;
  longitud: number | null;
  ubicacion: Ubicacion;
  venta: number | null;
  piezas: number | null;
  tickets: number | null;
  cambio_pct: number | null;
};

export type ListaTiendas = { tiendas: TiendaMapa[]; periodo: { desde: string; hasta: string; semanas: number } | null };

export type FichaTienda = Omit<TiendaMapa, "venta" | "piezas" | "tickets" | "cambio_pct"> & {
  por_mes: { mes: string; venta: number; piezas: number }[];
  productos: { sku: string; descripcion: string | null; departamento: string | null; venta: number; piezas: number }[];
};

export const UBICACION: Record<Exclude<Ubicacion, "ok">, string> = {
  falta: "Sin coordenadas en tblAlmacenes",
  fuera: "Coordenadas fuera de México (¿volteadas o mal capturadas?)",
};

// Colores para grupos (región o categoría); se repiten si hay más grupos que colores
export const PALETA = ["#DE951B", "#2563EB", "#059669", "#DC2626", "#7C3AED", "#0891B2", "#DB2777", "#65A30D", "#EA580C", "#4B5563", "#CA8A04", "#0F766E"];

// Grupos de tiendas que venden parecido (k-medias con la mezcla de venta por departamento; texto con la IA local)
export const RUTA_GRUPOS = "/api/datos/grupos-tiendas";

export type CorridaGrupos = {
  id: number;
  estado: "en_curso" | "completa" | "fallida";
  iniciada_en: string;
  terminada_en: string | null;
  tiendas: number | null;
  grupos: number | null;
  calidad: number | null;
  nota_ia: string | null;
  error: string | null;
  contexto: {
    venta?: string;
    fuera?: Record<string, string>;
    pedidos?: number | null;
    opciones?: { grupos: number; calidad: number }[];
    criterios?: Partial<Record<Criterio, number>>;
    avisos?: string[];
    demografia?: { fuente: string; sin_localidad: string[] } | null;
  };
};

export type Criterio = "ventas" | "tendencia" | "mezcla" | "demografia";

export const PESOS_CRITERIO = [
  { valor: 0, nombre: "No usar" },
  { valor: 1, nombre: "Poco" },
  { valor: 2, nombre: "Normal" },
  { valor: 3, nombre: "Mucho" },
];

export const AYUDA_CRITERIO: Record<Criterio, string> = {
  ventas: "Venta por semana, precio por pieza, margen y productos distintos",
  tendencia: "Si sube o cae (13 semanas contra 13), su ritmo y qué tan estable es",
  mezcla: "Qué parte de su venta es de cada departamento",
  demografia: "Habitantes, edades, nivel socioeconómico aproximado y servicio de salud de su localidad (Censo 2020)",
};

export type Distintivo = { criterio: Criterio; nombre: string; unidad: string; grupo: number | null; empresa: number | null; z: number };

export type DiferenciaDepto = { departamento: string; puntos: number; grupo_pct: number; empresa_pct: number };

export type PerfilGrupo = {
  grupo: number;
  nombre: string;
  descripcion: string | null;
  acciones: string[];
  tiendas: number;
  venta_semanal: number;
  de_mas: DiferenciaDepto[];
  de_menos: DiferenciaDepto[];
  regiones: string[];
  categorias: Record<string, number>;
  distintivos?: Distintivo[];
  caen_en?: { departamento: string; grupo_pct: number; empresa_pct: number }[];
  localidades?: string[];
  abajo_de_pares?: number;
};

export type TiendaEnGrupo = {
  almacen: string;
  grupo: number;
  tipicidad: number | null;
  rasgos: { nombre: string; unidad: string; tienda: number | null; grupo: number | null }[];
  alertas: { tipo: "venta" | "cambio" | "margen"; texto: string }[];
  metricas: Record<string, number | null> & { localidad?: { nombre: string; municipio: string; estado: string; km: number } | null };
};

export type Grupos = {
  corrida: CorridaGrupos | null;
  en_curso: CorridaGrupos | null;
  fallida: CorridaGrupos | null;
  grupos: PerfilGrupo[];
  tiendas: TiendaEnGrupo[];
  criterios: { clave: Criterio; nombre: string; disponible: boolean }[];
};

export function valorRasgo(v: number | null | undefined, unidad: string): string {
  if (v === null || v === undefined) return "sin dato";
  const n = (x: number, d = 1) => x.toLocaleString("es-MX", { maximumFractionDigits: d });
  if (unidad === "$") return v >= 1000 ? `$${n(v / 1000)} k` : `$${n(v, 2)}`;
  if (unidad === "% por semana") return `${v > 0 ? "+" : ""}${n(v)} % por semana`;
  if (unidad.startsWith("%")) return `${n(v)} %`;
  return n(v);
}

export function calidadGrupos(s: number | null): string {
  if (s === null) return "Sin dato";
  if (s >= 0.5) return "Grupos bien separados";
  if (s >= 0.25) return "Grupos con separación media";
  return "Grupos poco separados: las tiendas venden muy parecido entre sí";
}
