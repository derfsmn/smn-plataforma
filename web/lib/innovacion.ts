// TD005 · Innovación Vidanat (api/modulos/innovacion). Plan v2 aprobado por Diego el 2026-11-22.
// La fórmula técnica nunca se manda a ningún lado fuera del servidor: la IA es solo local (Ollama).

import { ErrorApi, urlApi } from "@/lib/api";

export const RUTA = "/api/innovacion";
export const P = {
  ver: "innovacion.recurso.ver",
  cargar: "innovacion.recurso.cargar",
  revisar: "innovacion.recurso.revisar",
  consultar: "innovacion.consulta.usar",
  investigar: "innovacion.investigacion.correr",
  expVer: "innovacion.expediente.ver",
  expEditar: "innovacion.expediente.editar",
  reglaProponer: "innovacion.regla.proponer",
  reglaPublicar: "innovacion.regla.publicar",
  dictaminar: "innovacion.dictamen.emitir",
  excepcion: "innovacion.excepcion.aprobar",
  filtro: "innovacion.decision.filtro",
} as const;

export const TIPOS: Record<string, string> = {
  articulo: "Artículo",
  ensayo_clinico: "Ensayo clínico",
  revision: "Revisión o metaanálisis",
  guia_regulatoria: "Guía regulatoria",
  norma: "Norma o ley",
  ficha_tecnica: "Ficha técnica",
  certificado: "Certificado de análisis",
  patente: "Patente",
  libro: "Libro",
  presentacion: "Presentación",
  imagen: "Imagen",
  prueba_interna: "Prueba interna",
  nota: "Nota",
  informe_ia: "Informe del investigador",
  otro: "Otro",
};
export const CLASIFICACION: Record<string, { texto: string; ayuda: string; clase: string }> = {
  general: { texto: "General", ayuda: "La ve todo el equipo de Innovación.", clase: "bg-smn-gris-100 text-smn-gris-700" },
  restringido: {
    texto: "Restringida",
    ayuda: "Solo quien tiene el permiso de restringidos (y el equipo del folio, si es de un folio).",
    clase: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  },
  formula: {
    texto: "Fórmula",
    ayuda: "Solo el equipo del folio con permiso de fórmula. Se guarda cifrada y nunca entra a la búsqueda general.",
    clase: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300",
  },
};
export const ESTADO_FUENTE: Record<string, { texto: string; clase: string }> = {
  pendiente: { texto: "Pendiente de revisión", clase: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300" },
  revisado: { texto: "Revisada", clase: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300" },
  sustituido: { texto: "Sustituida", clase: "bg-smn-gris-100 text-smn-gris-500" },
};
export const ETAPAS: Record<string, string> = {
  idea: "Idea",
  prefiltro: "Prefiltro",
  investigacion: "Investigación",
  filtro: "Filtro",
  desarrollo: "Desarrollo",
  salida_comercial: "Salida comercial",
  validacion: "Validación",
};
export const ESTADO_EXP: Record<string, string> = { activo: "Activo", en_espera: "En espera", cerrado: "Cerrado" };
export const RESULTADO: Record<string, { texto: string; clase: string; punto: string }> = {
  cumple: { texto: "Cumple", clase: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300", punto: "bg-emerald-500" },
  incumple: { texto: "No cumple", clase: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300", punto: "bg-red-500" },
  pendiente: { texto: "Pendiente", clase: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300", punto: "bg-amber-500" },
  no_aplica: { texto: "No aplica", clase: "bg-smn-gris-100 text-smn-gris-500", punto: "bg-smn-gris-300" },
};
export const SEVERIDAD: Record<string, string> = { bloqueante: "Bloqueante", mayor: "Mayor", menor: "Menor" };
export const ESTADO_REGLA: Record<string, { texto: string; clase: string }> = {
  borrador: { texto: "Borrador", clase: "bg-smn-gris-100 text-smn-gris-700" },
  en_revision: { texto: "En revisión", clase: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300" },
  publicada: { texto: "Publicada", clase: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300" },
  sustituida: { texto: "Sustituida", clase: "bg-smn-gris-100 text-smn-gris-500" },
  retirada: { texto: "Retirada", clase: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300" },
};
export const MODO_REGLA: Record<string, string> = {
  automatica: "Automática (la revisa el motor)",
  manual: "Manual (la dictamina una persona)",
  asistida: "Asistida (la IA local sugiere, una persona dictamina)",
};
export const DECISION: Record<string, string> = {
  avanzar: "Avanzar a desarrollo",
  ajustar: "Regresar a investigación para ajustar",
  espera: "Dejar en espera",
  cerrar: "Cerrar el expediente",
};
export const ESTADO_INV: Record<string, { texto: string; clase: string }> = {
  propuesta: { texto: "Por confirmar", clase: "bg-smn-gris-100 text-smn-gris-700" },
  lista: { texto: "Lista", clase: "bg-smn-gris-100 text-smn-gris-700" },
  corriendo: { texto: "Investigando", clase: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300" },
  terminada: { texto: "Terminada", clase: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300" },
  error: { texto: "Con error", clase: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300" },
};
export const TEMAS: Record<string, string> = { quimica: "Química", eficacia: "Eficacia", seguridad: "Seguridad", regulacion: "Regulación", mercado: "Mercado" };
export const TIPO_INGREDIENTE: Record<string, string> = {
  mineral: "Mineral",
  vitamina: "Vitamina",
  botanico: "Botánico",
  aminoacido: "Aminoácido",
  probiotico: "Probiótico",
  otro: "Otro",
};
export const UNIDADES = ["mg", "g", "µg", "mcg", "UI", "ml", "%", "UFC", "cápsulas", "tabletas"];
export const CAMPOS_FICHA: { clave: string; texto: string; largo?: boolean }[] = [
  { clave: "nombre_comercial", texto: "Nombre comercial" },
  { clave: "presentacion", texto: "Presentación (p. ej. 60 cápsulas)" },
  { clave: "porcion", texto: "Porción" },
  { clave: "unidad_porcion", texto: "Unidad de la porción" },
  { clave: "porciones_dia", texto: "Porciones al día" },
  { clave: "categoria_sanitaria", texto: "Categoría sanitaria" },
  { clave: "categoria_comercial", texto: "Categoría comercial" },
  { clave: "precio_objetivo", texto: "Precio objetivo (MXN)" },
  { clave: "beneficio", texto: "Beneficio que se quiere comunicar", largo: true },
  { clave: "poblacion", texto: "Para quién", largo: true },
  { clave: "modo_de_uso", texto: "Modo de uso", largo: true },
  { clave: "advertencias", texto: "Advertencias", largo: true },
  { clave: "declaraciones", texto: "Declaraciones de etiqueta", largo: true },
  { clave: "notas", texto: "Notas", largo: true },
];

// ---------------------------------------------------------------- tipos

export type Resumen = {
  etapas: Record<string, number>;
  fuentes: Record<string, number>;
  reglas: Record<string, number>;
  por_revisar: { recurso_id: number; version: number; titulo: string; tipo: string; desde: string }[];
  dictamenes: { revision_id: number; folio: string; expediente: string; regla: string; proposito: string; vence_en: string | null }[];
  por_publicar: { regla_id: number; codigo: string; version: number; proposito: string }[];
  por_decidir: { folio: string; nombre: string }[];
  expedientes: { folio: string; nombre: string; etapa: string; estado: string; actualizado_en: string }[];
  ia_local: boolean;
  ocr: boolean;
  trabajos_con_error: number;
};

export type Ingrediente = {
  id: number;
  nombre: string;
  tipo: string;
  forma_quimica: string | null;
  sinonimos: string[];
  estado: string;
  factor_ui_ug: number | null;
  factor_version_id: number | null;
};

export type FilaRecurso = {
  id: number;
  titulo: string;
  tipo: string;
  clasificacion: string;
  folio: string | null;
  version: number;
  estado: string;
  procesado: string;
  anio: number | null;
  creado_en: string;
};

export type ArchivoFuente = {
  id: number;
  nombre: string;
  tipo: string;
  bytes: number;
  sha256: string;
  rol: string;
  cifrado: boolean;
  descripcion: string | null;
  descripcion_confirmada: boolean;
};

export type Vinculo = { id: number; tipo: string; ingrediente?: string; ingrediente_id?: number; categoria?: string; folio?: string };

export type VersionFuente = {
  numero: number;
  version_id: number;
  estado: string;
  procesado: string;
  url: string | null;
  doi: string | null;
  pmid: string | null;
  autores: string | null;
  anio: number | null;
  publicado_en: string | null;
  idioma: string | null;
  resumen: string | null;
  tiene_texto: boolean;
  vigente_desde: string | null;
  vigente_hasta: string | null;
  datos: Record<string, string>;
  sugerencias: Record<string, unknown>;
  respalda: string | null;
  limites: string | null;
  corresponde: string | null;
  tipo_revision: string | null;
  revisado_por: string | null;
  revisado_en: string | null;
  interpretacion: string | null;
  creado_por: string | null;
  creado_en: string;
  archivos: ArchivoFuente[];
  vinculos: Vinculo[];
  secciones: number;
  uso: { citas: { folio: string; pagina: number | null; respalda: string; aplica: string }[]; reglas: { codigo: string; version: number; estado: string }[] };
};

export type TrabajoFuente = {
  id: number;
  tipo: string;
  nombre: string;
  estado: "pendiente" | "corriendo" | "listo" | "error";
  intentos: number;
  error: string | null;
  siguiente_en: string | null;
  version: number;
};

export type Fuente = {
  id: number;
  titulo: string;
  tipo: string;
  clasificacion: string;
  folio: string | null;
  responsable: string | null;
  estado: string;
  versiones: VersionFuente[];
  puede_revisar: boolean;
  puede_cargar: boolean;
  trabajos: TrabajoFuente[];
};

export type Resultado = {
  fragmento_id: number;
  recurso_id: number;
  version: number;
  version_id: number;
  titulo: string;
  tipo: string;
  estado: string;
  clasificacion: string;
  folio: string | null;
  seccion: string | null;
  pagina: number | null;
  extracto: string;
  puntos: number;
};
export type Busqueda = { total: number; con_significado: boolean; resultados: Resultado[] };

export type Seccion = { id: number; recurso_id: number; titulo: string; version: number; estado: string; pagina: number | null; seccion: string | null; texto: string };

export type Cita = {
  numero: number;
  fragmento_id: number;
  recurso_id: number;
  version_id: number;
  version: number;
  titulo: string;
  tipo: string;
  seccion: string | null;
  pagina: number | null;
  extracto: string;
  clasificacion: string;
};
export type Respuesta = {
  consulta_id: number;
  texto: string;
  insuficiente: boolean;
  modo: "ia" | "palabras";
  citas: Cita[];
  no_usadas: { recurso_id: number; titulo: string; version: number }[];
  aviso: string | null;
  duracion_ms: number;
};

export type FilaExpediente = {
  folio: string;
  nombre: string;
  etapa: string;
  estado: string;
  categoria_comercial: string | null;
  responsable: string | null;
  soy_del_equipo: boolean;
  actualizado_en: string;
  resumen: Record<string, number> | null;
};

export type IngredienteFicha = {
  ingrediente_id: number | null;
  nombre: string;
  tipo: string | null;
  forma: string | null;
  en_compuesto: boolean;
  cantidad_compuesto: number | null;
  unidad_compuesto: string | null;
  cantidad_activa: number | null;
  unidad_activa: string | null;
  fraccion_activa: number | null;
  fuente_version_id: number | null;
  nota: string | null;
  orden?: number;
};

export type Ficha = {
  numero: number;
  ficha_id: number;
  datos: Record<string, string>;
  nota: string | null;
  formula_version: number | null;
  creado_por: string | null;
  creado_en: string;
  ingredientes: IngredienteFicha[];
};

export type Evidencia = {
  id: number;
  recurso_id: number | null;
  titulo: string;
  version: number;
  estado_fuente: string;
  fragmento_id: number | null;
  pagina: number | null;
  seccion: string | null;
  respalda: string;
  limites: string | null;
  aplica: string;
  sentido: string;
  creado_por: string | null;
  creado_en: string;
};

export type ResultadoRegla = {
  id: number;
  regla: string;
  regla_id: number;
  version: number;
  proposito: string;
  modo: string;
  resultado: "cumple" | "incumple" | "pendiente" | "no_aplica";
  severidad: string;
  motivo: string;
  faltantes: string[];
  datos_usados: Record<string, unknown>;
  aviso_fuente: string | null;
  admite_excepcion: boolean;
  fuente: { recurso_id: number; version: number; titulo: string; ubicacion: string | null } | null;
  revision: { id: number; estado: string; rol: string | null } | null;
  excepcion: { id: number; vence_en: string } | null;
};

export type Evaluacion = {
  numero: number;
  motivo: string;
  etapa: string;
  motor: string;
  ficha_version: number | null;
  formula_version: number | null;
  regla: string | null;
  creada_por: string | null;
  creada_en: string;
  resumen: Record<string, number>;
  resultados: ResultadoRegla[];
};

export type Abierto = { regla: string; version: number; resultado: string; motivo: string; resultado_id: number };
export type Compuerta = {
  etapa: string;
  puede_avanzar: boolean;
  evaluacion: number | null;
  bloqueantes_abiertos: Abierto[];
  mayores_abiertos: Abierto[];
  pendientes_determinantes?: { id: number; descripcion: string; fecha_limite: string | null }[];
  excepciones_vigentes?: { regla: string; vence_en: string }[];
  motivo: string | null;
};

export type Decision = {
  id: number;
  etapa: string;
  resultado: string;
  motivo: string;
  condiciones: string | null;
  evaluacion: number | null;
  decidida_por: string | null;
  decidida_en: string;
};

export type Expediente = {
  folio: string;
  nombre: string;
  descripcion: string | null;
  jurisdiccion: string;
  categoria_sanitaria: string | null;
  categoria_comercial: string | null;
  presentacion: string | null;
  etapa: string;
  estado: string;
  responsable: string | null;
  equipo: { usuario_id: number; nombre: string; papel: string | null }[];
  soy_del_equipo: boolean;
  ficha: Ficha | null;
  fichas: { numero: number; creado_en: string; creado_por: string | null }[];
  formula: { numero: number | null; creado_en?: string; creado_por?: string | null; puede_ver: boolean; puede_editar: boolean };
  evidencia: Evidencia[];
  comparables: { id: number; origen: string; producto: string; marca: string | null; presentacion: string | null; precio: number | null; url: string | null; fuente: string | null; nota: string | null }[];
  escenarios: { id: number; nombre: string; costo_unitario: number | null; precio: number | null; margen_pct: number | null; supuestos: string | null; confianza: string | null }[];
  pendientes: { id: number; descripcion: string; responsable: string | null; responsable_id: number | null; fecha_limite: string | null; determinante: boolean; estado: string }[];
  evaluacion: Evaluacion | null;
  compuerta: Compuerta;
  siguiente_etapa: string;
  decisiones: Decision[];
  puede: { editar: boolean; evaluar: boolean; filtro: boolean; exportar: boolean; dictaminar: boolean; excepcion: boolean; investigar: boolean };
};

// Lo que recibe cada pestaña del expediente.
export type PropsPestana = { e: Expediente; alCambiar: () => Promise<void> };

export type Componente = { nombre: string; funcion: string | null; cantidad: number | null; unidad: string | null; proveedor: string | null; especificacion: string | null };
export type Formula = {
  numero: number;
  contenido: { componentes: Componente[]; proceso: string | null; lote_teorico: string | null; notas: string | null };
  nota: string | null;
  creado_por: string | null;
  creado_en: string;
};

export type Revision = {
  id: number;
  folio: string;
  expediente: string;
  estado: string;
  rol: string | null;
  regla: { codigo: string; version: number; proposito: string; severidad: string; fuente: { recurso_id: number; version: number; titulo: string; ubicacion: string | null } | null };
  ficha: Ficha | null;
  evidencia: Evidencia[];
  sugerencia_ia: { sugerencia: "cumple" | "incumple" | "no_aplica" | "no_se_puede"; razon: string; falta: string | null } | null;
  dictamen: string | null;
  motivo: string | null;
  respaldo: number[];
  dictaminada_por: string | null;
  dictaminada_en: string | null;
  vence_en: string | null;
  puede_dictaminar: boolean;
};

export type FilaRegla = {
  id: number;
  codigo: string;
  area: string;
  area_nombre: string;
  nombre: string;
  vigente: number | null;
  ultima: number | null;
  estado: string | null;
  severidad: string | null;
  modo: string | null;
};

export type VersionRegla = {
  numero: number;
  id: number;
  estado: string;
  proposito: string;
  modo: string;
  alcance: Record<string, string[] | string>;
  condicion: Record<string, unknown> | null;
  severidad: string;
  si_falta: string;
  admite_excepcion: boolean;
  exige_fuente_vigente: boolean;
  sustituye_a: string | null;
  fuente: { version_id: number; recurso_id: number; version: number; titulo: string; estado: string } | null;
  fuente_ubicacion: string | null;
  vigente_desde: string | null;
  vigente_hasta: string | null;
  rol_revisor: string | null;
  plazo_dias: number;
  campos_relevantes: string[];
  autor: string | null;
  autor_id: number;
  creado_en: string;
  enviado_en: string | null;
  aprobador: string | null;
  publicado_en: string | null;
  retirado_por: string | null;
  retirado_en: string | null;
  motivo_retiro: string | null;
};
export type Regla = FilaRegla & { versiones: VersionRegla[]; puede_proponer: boolean; puede_publicar: boolean };
export type CatalogoReglas = { areas: Record<string, string>; severidades: string[]; alcance: string[]; operadores: string[]; unidades: string[]; publicadas: number };

export type Hallazgo = {
  id: number;
  origen: string;
  identificador: string | null;
  titulo: string;
  autores: string | null;
  anio: number | null;
  publicado_en: string | null;
  url: string | null;
  tipo_estudio: string | null;
  puntaje: number;
  seleccionado: boolean;
  extraccion: Record<string, string>;
  texto_abierto: boolean;
  recurso_id: number | null;
};
export type FilaInvestigacion = {
  id: number;
  tema: string;
  estado: "propuesta" | "lista" | "corriendo" | "terminada" | "error";
  folio: string | null;
  creado_por: string | null;
  creado_en: string;
  terminada_en: string | null;
  costo_usd: number;
  error: string | null;
};
export type Investigacion = FilaInvestigacion & {
  preguntas: { tema: string; texto: string }[];
  terminos: string[];
  fuentes: string[];
  usar_web: boolean;
  pasos: { paso: string; texto: string; en: string }[];
  informe: { pregunta: string; tema: string | null; texto: string; insuficiente: boolean; citas: { n: number; hallazgo_id: number; titulo: string; url: string | null }[] }[] | null;
  catalogo_fuentes: Record<string, string>;
  con_gasto: string[];
  gasto_mes_usd: number;
  tope_usd: number;
  hallazgos: Hallazgo[];
};

// ---------------------------------------------------------------- ayudas

export const fecha = (f: string | null | undefined) =>
  f ? new Date(f.length === 10 ? `${f}T12:00:00` : f).toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "numeric" }) : "—";

async function error(r: Response): Promise<never> {
  const datos = await r.json().catch(() => null);
  const d = datos?.detail;
  throw new ErrorApi(r.status, typeof d === "string" ? d : d?.mensaje ?? "Algo salió mal. Intenta de nuevo.");
}

// Alta de fuente o versión nueva: datos en JSON más los archivos, en un solo envío.
export async function enviarFuente<T>(ruta: string, datos: unknown, archivos: File[]): Promise<T> {
  const cuerpo = new FormData();
  cuerpo.append("datos", JSON.stringify(datos));
  archivos.forEach((a) => cuerpo.append("archivos", a));
  let r: Response;
  try {
    r = await fetch(`${urlApi()}${ruta}`, { method: "POST", credentials: "include", body: cuerpo });
  } catch {
    throw new ErrorApi(0, "No hay conexión con la API. Revisa que esté corriendo.");
  }
  if (!r.ok) await error(r);
  return r.json();
}

// Descargas con la sesión (archivos de fuentes y PDF del expediente). Las restringidas llevan marca de agua.
export async function descargar(ruta: string, nombre: string): Promise<void> {
  const r = await fetch(`${urlApi()}${ruta}`, { credentials: "include" });
  if (!r.ok) await error(r);
  const liga = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = liga;
  a.download = nombre;
  a.click();
  setTimeout(() => URL.revokeObjectURL(liga), 2000);
}

// El 409 de enviar/decidir/publicar trae {mensaje, compuerta|choques}: se lee completo.
export async function postConDetalle<T>(ruta: string, cuerpo: unknown): Promise<{ ok: true; datos: T } | { ok: false; mensaje: string; detalle: Record<string, unknown> | null }> {
  let r: Response;
  try {
    r = await fetch(`${urlApi()}${ruta}`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
  } catch {
    return { ok: false, mensaje: "No hay conexión con la API. Revisa que esté corriendo.", detalle: null };
  }
  const datos = await r.json().catch(() => null);
  if (r.ok) return { ok: true, datos: datos as T };
  const d = datos?.detail;
  return {
    ok: false,
    mensaje: typeof d === "string" ? d : d?.mensaje ?? (Array.isArray(d) ? "Revisa los datos del formulario." : "Algo salió mal. Intenta de nuevo."),
    detalle: d && typeof d === "object" && !Array.isArray(d) ? d : null,
  };
}

// Texto con citas [1], [2]… partido en piezas para pintar cada número como liga.
export function partesConCitas(texto: string): (string | number)[] {
  const salida: (string | number)[] = [];
  let ultimo = 0;
  for (const m of texto.matchAll(/\[(\d{1,2})\]/g)) {
    if (m.index! > ultimo) salida.push(texto.slice(ultimo, m.index));
    salida.push(Number(m[1]));
    ultimo = m.index! + m[0].length;
  }
  if (ultimo < texto.length) salida.push(texto.slice(ultimo));
  return salida;
}
