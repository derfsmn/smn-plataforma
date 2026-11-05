// TD004 · Métodos y procedimientos (api/modulos/metodos/rutas.py)

export const RUTA = "/api/metodos";
export const PERMISO_CONSULTAR = "metodos.consultar";
export const PERMISO_CARGAR = "metodos.cargar";
export const PERMISO_APROBAR = "metodos.aprobar";

export type TipoDoc = "manual" | "politica" | "instructivo" | "formato" | "preguntas" | "otro";
export const TIPOS: Record<TipoDoc, string> = {
  manual: "Manual de procedimientos",
  politica: "Política",
  instructivo: "Instructivo o paso a paso",
  formato: "Formato o plantilla",
  preguntas: "Preguntas frecuentes",
  otro: "Otro",
};
export const ORIGENES: Record<string, string> = {
  cargado: "Cargado",
  ia: "Redactado con IA y aprobado",
  compras: "De la Base de conocimiento de Compras",
  fiscal: "De la Base de conocimiento fiscal",
};
export const ESTADOS_DOC: Record<string, { texto: string; clase: string }> = {
  vigente: { texto: "Vigente", clase: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300" },
  borrador: { texto: "Borrador", clase: "bg-smn-gris-100 text-smn-gris-700" },
  reemplazado: { texto: "Reemplazado", clase: "bg-smn-gris-100 text-smn-gris-500" },
  retirado: { texto: "Retirado", clase: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300" },
};

export type Estado = {
  documentos: number;
  fragmentos: number;
  con_huella: number;
  ollama: boolean;
  modelo_huella: string | null;
  modelo_respuesta: string | null;
  huellas_en_curso: boolean;
  contradicciones_en_curso: boolean;
  puede_cargar: boolean;
  puede_aprobar: boolean;
  areas: string[];
  roles: { codigo: string; nombre: string }[];
};

export type Cita = {
  numero: number;
  fragmento_id: number;
  documento_id: number;
  titulo: string;
  clave: string | null;
  version: string;
  vigente_desde: string | null;
  area: string;
  seccion: string | null;
  pagina: number | null;
  extracto: string;
};

export type Respuesta = {
  pregunta_id: number;
  texto: string;
  encontrada: boolean;
  modo: "ia" | "palabras";
  citas: Cita[];
  preguntar_a: string | null;
  aviso: string | null;
  duracion_ms: number;
};

export type Documento = {
  id: number;
  clave: string | null;
  titulo: string;
  tipo: TipoDoc;
  area: string;
  version: string;
  vigente_desde: string | null;
  revisar_antes: string | null;
  sistema: string | null;
  roles: string[];
  estado: string;
  origen: string;
  reemplaza_a: number | null;
  fragmentos: number;
  con_huella: number;
  avisos: string[];
  viejo: string | null;
  archivo: string | null;
  cargado_por: string | null;
  cargado_en: string;
  aprobado_por: string | null;
  aprobado_en: string | null;
};

export type Seccion = { id: number; orden: number; seccion: string | null; pagina: number | null; texto: string; con_huella: boolean };
export type DocumentoDetalle = Documento & { secciones: Seccion[]; versiones: Documento[]; diagrama_svg: string | null; pdf: boolean };
export type Cargado = { documento: Documento; fragmentos: number; con_huella: number; datos_personales: Record<string, number> };

export type Borrador = {
  id: number;
  tipo: "nuevo" | "actualizacion" | "formato";
  documento_id: number | null;
  documento: string | null;
  version_anterior: string | null;
  titulo: string;
  area: string;
  estado: "generando" | "listo" | "error" | "aprobado" | "descartado";
  error: string | null;
  creado_por: string | null;
  creado_en: string;
  revisado_por: string | null;
  revisado_en: string | null;
  publicado_id: number | null;
};
export type Cambio = { n: number; tipo: "cambia" | "quita" | "agrega"; seccion: string | null; antes: string[]; despues: string[] };
export type BorradorDetalle = Borrador & {
  instrucciones: string | null;
  fuentes: { id: number; titulo: string; version: string }[];
  texto: string | null;
  texto_anterior: string | null;
  cambios: Cambio[];
  preguntas_abiertas: string[];
  nota: string | null;
  version_sugerida: string;
  archivos: { id: number; nombre: string }[];
  flujo: Flujo | null;
  diagrama_svg: string | null;
};

// Diagrama de flujo: un carril por puesto; cada paso dice a cuál sigue (las decisiones, con etiqueta).
export type TipoPaso = "inicio" | "paso" | "decision" | "fin";
export type Salida = { a: string; etiqueta: string | null };
export type PasoFlujo = { id: string; tipo: TipoPaso; texto: string; carril: string; sig: Salida[] };
export type Flujo = { carriles: string[]; pasos: PasoFlujo[]; origen?: "ia" | "texto" | "persona"; aviso?: string | null };
export const TIPOS_PASO: Record<TipoPaso, string> = { inicio: "Inicio", paso: "Paso", decision: "Decisión", fin: "Fin" };
export const ORIGEN_FLUJO: Record<string, string> = {
  ia: "La IA local lo sacó del texto.",
  texto: "Se armó con los pasos numerados del texto, sin decisiones.",
  persona: "Corregido a mano.",
};
export const TIPOS_BORRADOR: Record<Borrador["tipo"], string> = {
  nuevo: "Manual nuevo",
  actualizacion: "Versión actualizada",
  formato: "Pasar al formato estándar",
};
export const ESTADOS_BORRADOR: Record<Borrador["estado"], { texto: string; clase: string }> = {
  generando: { texto: "La IA está redactando", clase: "bg-smn-naranja/15 text-smn-negro dark:text-smn-naranja" },
  listo: { texto: "Listo para revisar", clase: "bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300" },
  error: { texto: "No se pudo", clase: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300" },
  aprobado: { texto: "Aprobado y publicado", clase: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300" },
  descartado: { texto: "Descartado", clase: "bg-smn-gris-100 text-smn-gris-500" },
};

export type Alerta = {
  id: number;
  documento_id: number;
  documento: string;
  area: string;
  otro_documento_id: number | null;
  otro_documento: string | null;
  otra_area: string | null;
  texto: string | null;
  otro_texto: string | null;
  detalle: string;
  estado: string;
  creado_en: string;
};

export type Sugerencias = {
  temas: { preguntas: string[]; veces: number; sin_respuesta: number; no_sirvio: number; documento_id: number | null; documento: string | null; area: string | null; accion: "actualizacion" | "nuevo" }[];
  viejos: { documento_id: number; titulo: string; area: string; version: string; motivo: string }[];
  criterios: { titulo: string; aprobado_en: string; documento_id: number | null; documento: string | null }[];
};

export type Reporte = {
  mes: string;
  total: number;
  encontradas: number;
  sin_respuesta: { preguntas: string[]; veces: number }[];
  calificadas: number;
  utiles: number;
  no_sirvieron: { pregunta: string; respuesta: string; comentario: string | null }[];
  promedio_ms: number;
  mas_citados: { documento_id: number; titulo: string; veces: number }[];
  por_origen: { origen: string; veces: number }[];
};

export type PruebaPregunta = {
  id: number;
  pregunta: string;
  respuesta_esperada: string | null;
  documento_id: number | null;
  documento: string | null;
  debe_contestar: boolean;
  area: string | null;
  activa: boolean;
};

type Meta = { valor: number; meta: number; pasa: boolean; de?: number };
export type Corrida = {
  id: number;
  estado: "en_curso" | "terminada" | "error";
  modo: string | null;
  total: number;
  hechas: number;
  correctas: number;
  inventadas: number;
  no_esta_bien: number;
  no_esta_total: number;
  promedio_ms: number;
  error: string | null;
  corrido_por: string | null;
  iniciada_en: string;
  terminada_en: string | null;
  metas: { correctas: Meta; inventadas: Meta; no_esta: Meta; segundos: Meta; con_ia: boolean; pasa: boolean };
};
export type CorridaDetalle = Corrida & {
  detalle: {
    id: number;
    pregunta: string;
    esperada: string | null;
    documento_esperado: string | null;
    debe_contestar: boolean;
    respuesta: string;
    modo: string;
    citas: { titulo: string; seccion: string | null; version: string }[];
    calificacion: "correcta" | "otra_cita" | "no_encontro" | "inventada" | "no_esta_bien";
    ms: number;
  }[];
};
export const CALIFICACION: Record<CorridaDetalle["detalle"][number]["calificacion"], { texto: string; bien: boolean }> = {
  correcta: { texto: "Correcta, con la cita esperada", bien: true },
  otra_cita: { texto: "Contestó, pero citó otro documento", bien: false },
  no_encontro: { texto: "No encontró la respuesta", bien: false },
  inventada: { texto: "Contestó algo que no está en los manuales", bien: false },
  no_esta_bien: { texto: "Dijo bien que no está", bien: true },
};

export const fecha = (iso: string | null) =>
  iso ? new Date(iso.length === 10 ? iso + "T12:00:00" : iso).toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "numeric" }) : "—";

// «[2]» en la respuesta de la IA → número de cita para resaltarlo
export function partesConCitas(texto: string): (string | number)[] {
  return texto.split(/(\[\d{1,2}\])/).map((p) => (/^\[\d{1,2}\]$/.test(p) ? Number(p.slice(1, -1)) : p));
}
