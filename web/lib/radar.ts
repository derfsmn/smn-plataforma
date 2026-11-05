// Tipos y textos del Radar de tendencias (api/modulos/compras/rutas_radar.py)

export type ArticuloRadar = {
  id: number;
  titulo: string;
  url: string;
  sitio: string;
  fuente: string | null;
  origen: "lista" | "busqueda";
  publicado_en: string | null;
  leido_en: string;
  en_ventana: boolean;
  relevante: boolean | null;
  categoria: string | null;
  nivel: Nivel | null;
  area: string | null;
  pais: string | null;
  por_que: string | null;
  extracto: string | null;
};

export type Nivel = "ALTA" | "MEDIA" | "TEMPRANA";
export type EstadoSenal = "nueva" | "vigilar" | "descartada" | "iniciativa";
export type Accion = "iniciativa" | "vigilar" | "descartar";

export type AccionRadar = { accion: Accion; motivo: string | null; usuario: string; ocurrido_en: string };

export type Hallazgo = {
  orden: number;
  senal_id: number;
  titulo: string;
  por_que: string;
  nivel: Nivel;
  tipo: "emergente" | "tendencia";
  area: string | null;
  paises: string | null;
  estado_senal: EstadoSenal;
  ultima_accion: AccionRadar | null;
  articulos: ArticuloRadar[];
};

export type ReporteResumen = {
  fecha: string;
  estado: "en_curso" | "listo" | "error";
  origen: "programado" | "tardio" | "manual";
  intentos: number;
  iniciado_en: string;
  terminado_en: string | null;
  fuentes_leidas: number;
  fuentes_con_error: number;
  busquedas: number;
  articulos_nuevos: number;
  articulos_relevantes: number;
  hallazgos: number;
  correos_enviados: number;
  correos_fallidos: number;
  error: string | null;
  costo_mxn: number | null;
};

export type ReporteDetalle = ReporteResumen & {
  resumen: string | null;
  radar_ejecutivo: string[];
  avisos: string[];
  detalle_hallazgos: Hallazgo[];
};

export type EstadoRadar = {
  activo: boolean;
  hora: number;
  zona_horaria: string;
  proxima_corrida: string;
  frecuencia: string;
  en_curso: boolean;
  ultimo: ReporteResumen | null;
  ia_encendida: boolean;
  ia_proveedor: string;
  ia_motivos: string[];
  ollama: boolean;
  correo_configurado: boolean;
  destinatarios_activos: number;
  fuentes_activas: number;
  temas_activos: number;
  busquedas_por_dia: number;
};

export type Senal = {
  id: number;
  titulo: string;
  descripcion: string | null;
  tipo: "emergente" | "tendencia";
  nivel: Nivel;
  categoria: string | null;
  area: string | null;
  paises: string | null;
  sitios_distintos: number;
  primera_vez: string;
  ultima_vez: string;
  veces_reportada: number;
  estado: EstadoSenal;
  articulos: number;
  ultima_accion: AccionRadar | null;
};

export type SenalDetalle = Senal & { lista_articulos: ArticuloRadar[]; acciones: AccionRadar[]; reportes: string[] };

export type Fuente = {
  id: number;
  nombre: string;
  liga: string;
  tipo: "oficial" | "especializada" | "negocios" | "estudios";
  pais: string;
  idioma: "es" | "en";
  metodo: "rss" | "busqueda" | "manual";
  lectura: string | null;
  activa: boolean;
  notas: string | null;
  ultima_lectura_en: string | null;
  ultimo_resultado: string | null;
  ultimos_articulos: number | null;
  articulos_total: number;
};

export type Tema = { id: number; nombre: string; descripcion: string; activo: boolean; orden: number };
export type TipoCorreo = "decision" | "informativo";
export type Destinatario = { id: number; nombre: string; correo: string; area: string | null; activo: boolean; tipo_correo: TipoCorreo };
export type Documento = {
  id: number;
  archivo_id: number;
  titulo: string;
  descripcion: string | null;
  nombre_archivo: string;
  caracteres: number;
  activo: boolean;
  subido_por: string;
  subido_en: string;
};

export const TEXTO_ACCION: Record<Accion, string> = { iniciativa: "Abrir iniciativa", vigilar: "Vigilar", descartar: "Descartar" };
export const TEXTO_ESTADO: Record<EstadoSenal, string> = {
  nueva: "Sin decidir",
  vigilar: "En vigilancia",
  descartada: "Descartada",
  iniciativa: "Iniciativa abierta",
};
export const CLASE_ESTADO: Record<EstadoSenal, string> = {
  nueva: "bg-smn-gris-100 text-smn-gris-700",
  vigilar: "bg-aviso-fondo text-aviso-texto",
  descartada: "bg-smn-gris-100 text-smn-gris-500 line-through",
  iniciativa: "bg-smn-naranja text-smn-negro",
};
export const CLASE_NIVEL: Record<Nivel, string> = {
  ALTA: "bg-smn-naranja text-smn-negro",
  MEDIA: "bg-tinta text-superficie",
  TEMPRANA: "bg-smn-gris-100 text-smn-gris-700",
};
export const TEXTO_TIPO = { emergente: "Señal emergente", tendencia: "Tendencia" } as const;
export const TEXTO_FUENTE_TIPO = {
  oficial: "Oficial",
  especializada: "Especializada",
  negocios: "Negocios",
  estudios: "Estudios de mercado",
} as const;
export const TEXTO_METODO = { rss: "RSS", busqueda: "Búsqueda en su sitio", manual: "Solo consulta manual" } as const;
export const TEXTO_ORIGEN = { programado: "A su hora", tardio: "Tardía", manual: "Manual" } as const;

export const fechaCorta = (iso: string | null) =>
  iso ? new Date(iso.length === 10 ? `${iso}T12:00:00` : iso).toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "numeric" }) : "Sin fecha";
export const fechaLarga = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("es-MX", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
// La API guarda en UTC sin zona
// zona: la del radar, para que la hora programada se lea igual desde cualquier equipo
export const fechaHora = (iso: string, zona?: string) =>
  new Date(/([zZ]|[+-]\d\d:\d\d)$/.test(iso) ? iso : `${iso}Z`).toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short", timeZone: zona });
export const pesos = (n: number | null) => (n === null ? "—" : `${n.toLocaleString("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 2 })} MXN`);
