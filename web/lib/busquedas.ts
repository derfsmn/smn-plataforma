// Búsqueda de proveedor (Compras, TD001). API: api/modulos/compras/rutas_busquedas.py
// Una oportunidad o idea sin proveedor que sale bien en el semáforo les llega a quienes buscan proveedores: la toman,
// registran a quién contactaron y la cierran con el proveedor encontrado (se vuelve a evaluar y puede subir al comité) o sin él.

import type { Color } from "./precios";

export const RUTA = "/api/compras/busquedas";

export type EstadoBusqueda = "sin_tomar" | "buscando" | "encontrado" | "sin_proveedor" | "cancelada";
export type Resultado = "sin_respuesta" | "interesado" | "cotizo" | "no_surte";
export type Vista = "abiertas" | "mias" | "cerradas";

export type Persona = { id: number; nombre: string };

export type BusquedaBreve = {
  id: number;
  estado: EstadoBusqueda;
  estado_texto: string;
  origen: "automatica" | "compras";
  idea_id: number;
  nombre: string;
  marca: string | null;
  departamento: string | null;
  color: Color | null;
  puntaje: number | null;
  imagen: string | null;
  puertas: string[]; // por qué llegó: tendencia / mas_vendido / captura
  responsable: Persona | null;
  contactos: number;
  ultimo_avance: string | null;
  proveedor: string | null;
  creada_en: string;
  cerrada_en: string | null;
};

export type Avance = {
  id: number;
  tipo: "nota" | "contacto" | "estado";
  texto: string;
  proveedor: string | null;
  resultado: Resultado | null;
  resultado_texto: string | null;
  quien: string | null;
  creado_en: string;
};

export type ReunionBreve = { id: number; fecha: string; estado: string; decision: string | null };

export type BusquedaDetalle = BusquedaBreve & {
  color_inicial: Color | null;
  puntaje_inicial: number | null;
  nota: string | null;
  descripcion: string | null;
  contenido: string | null;
  forma: string | null;
  precio_visto: string | null;
  donde_se_vio: string | null;
  fotos: number[];
  por_que: string | null;
  evidencia: { fuente: string; texto: string }[];
  costo: string | null;
  motivo_cierre: string | null;
  semaforo: {
    evaluacion_id: number;
    estado: "en_curso" | "lista" | "fallida";
    color: Color | null;
    puntaje: number | null;
    confianza: string | null;
    modelo: string | null;
    explicacion: string | null;
  } | null;
  avances: Avance[];
  reunion_abierta: ReunionBreve | null;
  en_comite: ReunionBreve | null;
};

export type Bandeja = {
  busquedas: BusquedaBreve[];
  conteos: { sin_tomar: number; buscando: number; mias: number; cerradas: number; encontrado: number };
  colores_automaticos: Color[];
};

export const RESULTADOS: { valor: Resultado; texto: string }[] = [
  { valor: "interesado", texto: "Interesado" },
  { valor: "cotizo", texto: "Mandó cotización" },
  { valor: "sin_respuesta", texto: "Sin respuesta" },
  { valor: "no_surte", texto: "No lo surte" },
];

export const ESTILO_ESTADO: Record<EstadoBusqueda, string> = {
  sin_tomar: "bg-smn-naranja/15 text-tinta",
  buscando: "bg-tinta text-superficie",
  encontrado: "bg-green-600/10 text-green-700 dark:text-green-400",
  sin_proveedor: "bg-smn-gris-100 text-smn-gris-700",
  cancelada: "bg-smn-gris-100 text-smn-gris-500",
};

export const PUERTA: Record<string, string> = { tendencia: "Por tendencia", mas_vendido: "De lo más vendido", captura: "Capturado por Compras" };

export const abierta = (e: EstadoBusqueda) => e === "sin_tomar" || e === "buscando";
