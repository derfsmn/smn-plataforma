// TD003 · Base de conocimiento fiscal de la DIOT (api/modulos/contraloria/rutas_conocimiento_fiscal.py)

export const RUTA_BASE = "/api/contraloria/conocimiento";
export const PERMISO_APROBAR = "contraloria.criterios.aprobar";

export type EstadoCriterio = "borrador" | "pendiente" | "aprobado" | "retirado";
export type CampoParametro = { nombre: string; etiqueta: string; tipo: "lista" | "opcion" | "texto"; opciones: Record<string, string> | null };
export type Condicion = { fuente: string; campo: string; operador: string; valor: string };
export type AccionPropia = { accion: string; tipo_operacion?: string };

export type Version = {
  id: number;
  version: number;
  estado: EstadoCriterio;
  vigente_desde: string;
  vigente_hasta: string | null;
  parametros: Record<string, string | string[]> | null;
  condicion: Condicion | null;
  accion: AccionPropia | null;
  titulo: string;
  descripcion: string;
  creado_por: string | null;
  creado_en: string;
  aprobado_por: string | null;
  aprobado_en: string | null;
  nota_aprobacion: string | null;
};

export type Criterio = {
  clave: string;
  tipo: "sistema" | "propio";
  categoria: string;
  titulo: string;
  descripcion: string;
  contradiccion: string | null;
  documento_id: number | null;
  documento: string | null;
  referencia: string | null;
  evidencia: string | null;
  prioridad: number;
  empresa_id: number | null;
  campos: CampoParametro[];
  si_pendiente: string;
  vigente: Version;
  ultima: Version;
  versiones: number;
};

export type Catalogo = {
  id: number;
  catalogo: "tipo_tercero" | "tipo_operacion" | "layout";
  clave: string;
  descripcion: string;
  valor: string | null;
  vigente_desde: string;
  vigente_hasta: string | null;
  documento_id: number | null;
};

export type DocumentoFiscal = {
  id: number;
  titulo: string;
  tipo: string;
  version: string | null;
  vigente_desde: string | null;
  notas: string | null;
  archivo: string | null;
  tamano: number | null;
  sha256: string | null;
  activo: boolean;
  reemplaza_a: number | null;
  cargado_por: string | null;
  cargado_en: string;
};

export type Opciones = {
  categorias: Record<string, string>;
  fuentes: Record<string, string>;
  campos_condicion: Record<string, string>;
  operadores: Record<string, string>;
  acciones: Record<string, string>;
  que_lleva: Record<string, string>;
  tipos_documento: Record<string, string>;
  empresas: Record<string, string>;
};

export type BaseFiscal = {
  criterios: Criterio[];
  catalogos: Catalogo[];
  documentos: DocumentoFiscal[];
  opciones: Opciones;
  resumen: { aprobados: number; pendientes: number; borradores: number; contradicciones: number };
};

export type CambioHistorial = { version: number; accion: string; motivo: string | null; detalle: Record<string, unknown> | null; usuario: string | null; momento: string };

export type ResultadoPrueba = {
  periodo: string;
  procesado: boolean;
  terceros_antes: number;
  terceros_despues: number;
  cambios: { rfc: string; que: string; antes: string | null; despues: string | null }[];
  txt: boolean;
  bloqueado: boolean;
  incidencias_posibles: number;
  criterios_pendientes: string[];
};

export const ESTADOS: Record<EstadoCriterio, { texto: string; clase: string }> = {
  aprobado: { texto: "Aprobado", clase: "bg-emerald-100 text-emerald-800" },
  pendiente: { texto: "Pendiente de aprobar", clase: "bg-amber-100 text-amber-800" },
  borrador: { texto: "Borrador", clase: "bg-smn-gris-100 text-smn-gris-700" },
  retirado: { texto: "Retirado", clase: "bg-smn-gris-100 text-smn-gris-500 line-through" },
};

export const ACCIONES_HISTORIAL: Record<string, string> = {
  creado: "Creado",
  editado: "Cambiado",
  enviado: "Mandado a aprobar",
  aprobado: "Aprobado",
  regresado: "Regresado",
  retirado: "Retirado",
};

export const CATALOGOS: Record<Catalogo["catalogo"], { titulo: string; ayuda: string }> = {
  tipo_tercero: { titulo: "Tipos de tercero", ayuda: "Las claves que acepta el TXT en el campo de tipo de tercero." },
  tipo_operacion: { titulo: "Tipos de operación", ayuda: "Las claves que acepta el TXT en el campo de tipo de operación." },
  layout: { titulo: "Layout del TXT", ayuda: "Qué lleva cada campo del renglón. Los campos que no están aquí van vacíos." },
};

/** Primer día del mes actual, en AAAA-MM-DD: la fecha por omisión desde la que vale un cambio. */
export function inicioDeMes(): string {
  const h = new Date();
  return `${h.getFullYear()}-${String(h.getMonth() + 1).padStart(2, "0")}-01`;
}

export const fecha = (f: string | null) => (f ? new Date(`${f.slice(0, 10)}T12:00:00`).toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "numeric" }) : "—");

/** Cómo se ve un parámetro en una línea: listas separadas por coma, opciones con su texto. */
export function valorParametro(c: CampoParametro, v: string | string[] | undefined): string {
  if (v === undefined || v === null) return "—";
  if (Array.isArray(v)) return v.length ? v.map((x) => `«${x}»`).join(", ") : "(ninguno)";
  if (c.tipo === "opcion" && c.opciones) return c.opciones[v] ?? v;
  return String(v);
}
