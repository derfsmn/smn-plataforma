// Radar de productos (Compras): semáforo de productos nuevos e ideas que captura Compras. API: api/modulos/compras/rutas_productos.py

import { urlApi } from "./api";
import type { Color } from "./precios";

export type { Color };
export type EstadoEvaluacion = "en_curso" | "lista" | "fallida";
export type EstadoIdea = "nueva" | "buscar_proveedor" | "vigilar" | "descartada";

export type Sujeto = {
  tipo: "propuesta" | "idea";
  id: number;
  nombre: string;
  marca: string | null;
  departamento: string | null;
  folio: string | null;
  proveedor: string | null;
  estado: EstadoIdea | null;
};

export type EvaluacionResumen = {
  id: number;
  sujeto: Sujeto;
  estado: EstadoEvaluacion;
  puntaje: number | null;
  color: Color | null;
  color_final: Color | null;
  confianza: "alta" | "media" | "baja" | null;
  subcategoria: string | null;
  creada_en: string;
  terminada_en: string | null;
  modelo?: "con_proveedor" | "sin_proveedor" | null;
};

export type Factor = {
  factor: string;
  nombre: string;
  peso: string;
  puntaje: number | null;
  valor: string | null;
  detalle: string | null;
  provisional: boolean;
  calculo?: string | null;
  mejora?: string | null;
};

/** Qué mide cada factor, en palabras de Compras. */
export const QUE_MIDE: Record<string, string> = {
  demanda: "Cuánto se venden en nuestras tiendas los productos parecidos (o este mismo, si ya lo vendemos).",
  rentabilidad: "Cuánto nos deja de cada peso que se vende, contra el margen mínimo.",
  precio: "Si nuestro precio queda más caro o más barato que lo que se ve en el mercado.",
  tendencia: "Si en internet se está hablando de este producto o de su ingrediente.",
  categoria: "Si llena un hueco en el surtido o si ya tenemos muchos parecidos.",
  proveedor: "Qué tan confiable es quien lo surte: entregas, documentos y apoyos.",
};

/** Puntos del total que aporta cada factor con datos: su calificación por su peso entre los que tienen datos. */
export function aportes(factores: Factor[]): Record<string, number> {
  const con = factores.filter((f) => f.puntaje !== null);
  const cubierto = con.reduce((a, f) => a + Number(f.peso), 0);
  return Object.fromEntries(con.map((f) => [f.factor, cubierto ? (Number(f.peso) * (f.puntaje ?? 0)) / cubierto : 0]));
}

/** Cuántos puntos le faltan para el siguiente color (verde más de 80, amarillo 60 a 80). */
export function faltaPara(puntaje: number | null, color: Color | null): string | null {
  if (puntaje === null || color === "verde") return null;
  if (puntaje > 80) return "Por puntos sería verde, pero con confianza baja no puede salir verde.";
  if (puntaje >= 60) return 81 - puntaje === 1 ? "Le falta 1 punto para verde." : `Le faltan ${81 - puntaje} puntos para verde.`;
  return `Le faltan ${60 - puntaje} puntos para amarillo y ${81 - puntaje} para verde.`;
}

export type Comparable = {
  producto_id: number;
  sku: string;
  descripcion: string | null;
  marca: string | null;
  subcategoria: string | null;
  precio: string | null;
  similitud: string;
  origen: "sistema" | "compras";
};

export type Evaluacion = EvaluacionResumen & {
  vigente: boolean;
  rama: string | null;
  segmento: string | null;
  clasificacion_origen: "ia" | "compras" | "parecidos" | "variante" | "ingrediente" | "sin_clasificar" | null;
  pesos_origen: "compras" | "iguales" | null;
  explicacion: string | null;
  avance?: string | null;
  explicacion_ia: boolean;
  motivo_cambio: string | null;
  cambiado_por: string | null;
  cambiado_en: string | null;
  error: string | null;
  factores: Factor[];
  comparables: Comparable[];
  fotos: { archivo_id: number; nombre: string }[];
  descripcion: string | null;
  precio_visto: string | null;
  donde_se_vio: string | null;
  costo_estimado: string | null;
  precio_nuestro?: string | null;
  codigo_barras?: string | null;
  activo_g_porcion?: string | null;
  porciones?: number | null;
  /** 22 nov 2026: tipo de producto (lista de márgenes A–F) y precio de membresía con IVA */
  lista_margen?: string | null;
  precio_membresia?: string | null;
  historial: { id: number; creada_en: string; estado: EstadoEvaluacion; puntaje: number | null; color: Color | null; color_final: Color | null }[];
  mercado: MercadoInternet | null;
  investigacion?: Investigacion | null;
  pronostico?: Pronostico | null;
  politicas: RevisionPoliticas | null;
};

export type HallazgoWeb = {
  url: string;
  dominio: string;
  titulo: string;
  tipo: "mismo" | "misma_marca" | "sustituto";
  producto: string | null;
  precio: string | null;
  presentacion: string | null;
  dosis: string | null;
  afirmaciones: string[];
  citas: Record<string, string>;
};

export type Pronostico = {
  base: number | null;
  base_de: string;
  tramos: Record<string, number[]>; // "4" | "8" | "12" -> [bajo, medio, alto] piezas por tienda al mes
  grupos: { grupo: number; nombre: string; tiendas: number; bajo: number; medio: number; alto: number }[];
  canibal_pct: number | null;
  lanzamientos: number;
  examen: {
    lanzamientos?: number; suficientes?: boolean; dentro_pct?: number; error_mediano_pct?: number;
    prueba?: { probados: number; color: number; clase: number; en_rango: number; error_tipico_pct: number | null };
  };
  nota: string | null;
};

export type Investigacion = { hallazgos: HallazgoWeb[]; consultas: string[]; notas: string[]; buscado_en: string | null; costo_usd: string };

export type HallazgoPolitica = {
  id: string;
  tipo: "rechazo" | "umbral" | "politica";
  titulo: string;
  resultado: "cumple" | "no_cumple" | "sin_datos" | "sin_revisar";
  motivo: string;
  sin_prueba?: boolean;
};

export type RevisionPoliticas = {
  hallazgos: HallazgoPolitica[];
  rechazo: HallazgoPolitica | null;
  casos: { caso_id: number; producto: string; decision: string; motivo: string | null; resultado: string; fecha: string | null; similitud: number }[];
  notas: string[];
  revisada_ia: boolean;
};

export type MercadoInternet = {
  precios: { precio: string; vendedor: string; fuente: "google" | "sitio" | "web"; titulo: string; liga: string | null }[];
  mediana: string | null;
  notas: string[];
  publicacion: string | null;
  buscado_en: string | null;
  costo_usd: string;
};

export type OpcionClasificacion = { rama: string; subcategoria: string; segmento: string };
export type ProductoCatalogo = { producto_id: number; sku: string; descripcion: string | null; marca: string | null; subcategoria: string | null; precio: string | null };

export const RUTA = "/api/compras/productos";
/** Con `ancho`, la API manda la foto reducida (la original pesa varios MB y por la VPN tarda). */
export const urlFoto = (idea: number, archivo: number, ancho?: number) =>
  `${urlApi()}${RUTA}/ideas/${idea}/fotos/${archivo}${ancho ? `?ancho=${ancho}` : ""}`;

export const ESTADOS_IDEA: Record<EstadoIdea, string> = {
  nueva: "Nueva",
  buscar_proveedor: "Buscar proveedor",
  vigilar: "Vigilar",
  descartada: "Descartada",
};

export const CONFIANZA = { alta: "Confianza alta", media: "Confianza media", baja: "Confianza baja" } as const;

/** El color que cuenta: el que puso Compras si lo cambió, si no el del radar. */
export const colorVigente = (e: Pick<EvaluacionResumen, "color" | "color_final">) => e.color_final ?? e.color;

/** Tipo de producto = lista de márgenes de Compras («MARGENES PARA CALCULO DE PRECIOS.xlsx», 29 oct 2026). Los
 *  porcentajes se editan en Configuración; aquí solo los nombres. */
export const LISTAS_MARGEN = [
  { valor: "A", texto: "A · Autoservicio (renombre)" },
  { valor: "B", texto: "B · Margen general" },
  { valor: "C", texto: "C · 80/20 (revisar con gerencia)" },
  { valor: "D", texto: "D · Nutrición deportiva nacional" },
  { valor: "E", texto: "E · Nutrición deportiva importación" },
  { valor: "F", texto: "F · Margen específico" },
];

export const FORMAS = ["Cápsula", "Tableta", "Capleta", "Líquido", "Polvo", "Gomita", "Pieza", "Sobres", "Otro"];

// «Buscar oportunidades» (fase 2): productos que no tenemos y convendría buscar, con su evidencia
export const RUTA_OPORTUNIDADES = "/api/compras/oportunidades";
export type Prioridad = "alta" | "media" | "baja";
export type EstadoOportunidad = "nueva" | "evaluada" | "descartada";

export interface Oportunidad {
  id: number;
  orden: number;
  nombre: string;
  marca: string | null;
  departamento: string | null;
  subcategoria: string | null;
  forma: string | null;
  por_que: string;
  prioridad: Prioridad;
  evidencia: { clave: string; fuente: string; texto: string; puertas?: string[] }[];
  precio_visto: string | null;
  donde_se_vio: string | null;
  imagen: string | null;
  imagen_de: string | null;
  estado: EstadoOportunidad;
  evaluacion_id: number | null;
  evaluacion_estado: "en_curso" | "lista" | "fallida" | null;
  color: Color | null;
  puntaje: number | null;
  puertas: string[]; // tendencia / mas_vendido (2026-11-09)
  busqueda_id: number | null;
  busqueda_estado: string | null;
  tipo_cliente: string | null; // para qué tipo de cliente (Datos → Clientes)
  encaje: "si" | "dudoso" | null; // contra «Nuestro cliente»; las que no encajan se quitan
  encaje_motivo: string | null;
}

export interface CorridaOportunidades {
  id: number;
  estado: "en_curso" | "lista" | "fallida";
  paso: string | null;
  competencia: boolean;
  con_ia: boolean;
  costo_usd: string;
  error: string | null;
  disparada_por: string | null;
  programada: boolean;
  creada_en: string;
  terminada_en: string | null;
  total: number;
}

export interface CorridaOportunidadesDetalle extends CorridaOportunidades {
  notas: string[];
  fuentes: Record<string, number>;
  oportunidades: Oportunidad[];
}

export interface EstadoOportunidades {
  costo_maximo_competencia_usd: string;
  busquedas_competencia: number;
  falta_configurar: string[];
  programa: string | null; // «Corre sola los lunes a las 8:00»; null = solo con el botón
  corridas: CorridaOportunidades[];
}

// El botón «Capturar producto» vive en el encabezado (layout); la ventana de captura la abre la lista al oír este evento.
export const EVENTO_CAPTURAR = "smn:capturar-producto";
