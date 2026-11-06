// Comité de producto nuevo (Compras, TD001). API: api/modulos/compras/rutas_comite.py
// Cada reunión abre un ciclo: subir productos → semáforo → pre-filtro de Compras → comité (Aceptado, Denegado o En espera).

import { urlApi } from "./api";
import { descargar, type Color } from "./precios";

export const RUTA = "/api/compras/comite";

export type EstadoReunion = "abierta" | "prefiltro" | "comite" | "cerrada";
export type Decision = "aceptado" | "denegado" | "en_espera";
export type ValorCriterio = "bien" | "regular" | "mal";

export type Embudo = { subidos: number; evaluados: number; pasan: number; no_pasan: number; aceptados: number; denegados: number; en_espera: number };

export type ReunionBreve = {
  id: number;
  fecha: string;
  notas: string | null;
  estado: EstadoReunion;
  estado_texto: string;
  embudo: Embudo;
  peticiones_abiertas: number;
  creada_en: string;
  cerrada_en: string | null;
};

export type FactorBreve = { factor: string; nombre: string; puntaje: number | null; valor: string | null; peso: string };

export type Semaforo = {
  id: number;
  estado: "en_curso" | "lista" | "fallida";
  color: Color | null;
  color_radar: Color | null;
  puntaje: number | null;
  confianza: "alta" | "media" | "baja" | null;
  modelo: "con_proveedor" | "sin_proveedor" | null;
  avance: string | null;
  error: string | null;
  explicacion: string | null;
  motivo_cambio: string | null;
  factores: FactorBreve[];
  ejecutivo?: Ejecutivo | null;
};

export type PuntoClave = { factor: string; nombre: string; puntaje: number; texto: string };
/** El semáforo en una lámina ejecutiva (lo arma la API con los mismos factores, sin IA). */
export type Ejecutivo = {
  titular: string;
  a_favor: PuntoClave[];
  en_contra: PuntoClave[];
  para_verde: string | null;
  faltan_puntos: number | null;
  margen_minimo: string | null;
};

export type Criterio = { criterio: string; valor: ValorCriterio; nota: string | null };

export type Revision = { tipo: "inventario" | "regulacion"; nombre: string; resultado: "pendiente" | "aprobada" | "rechazada"; nota: string | null; por: string | null; en: string };

export type Item = {
  id: number;
  tipo: "propuesta" | "idea";
  sujeto_id: number;
  nombre: string;
  marca: string | null;
  departamento: string | null;
  folio: string | null;
  proveedor: string | null;
  proveedor_actual: boolean;
  origen: "captura" | "propuesta" | "idea" | "espera";
  viene_de_fecha: string | null;
  presentacion: string | null;
  descripcion: string | null;
  precio: string | null;
  costo: string | null;
  margen: string | null;
  fotos: number;
  foto_externa: string | null;
  estado_sujeto: string;
  falta: string | null;
  faltantes: string[]; // lo que le falta para presentarse completo
  llego_solo: boolean;
  evaluacion: Semaforo | null;
  prefiltro: "pasa" | "no_pasa" | null;
  prefiltro_motivo: string | null;
  criterios: Criterio[];
  prefiltro_color: Color | null;
  prefiltro_por: string | null;
  prefiltro_en: string | null;
  decision: Decision | null;
  decision_motivo: string | null;
  decision_color: Color | null;
  decision_por: string | null;
  decision_en: string | null;
  revisiones: Revision[];
  agregado_por: string | null;
  agregado_en: string;
};

export type Asistente = { id: number; usuario_id: number | null; nombre: string; puesto: string | null };

export type Peticion = {
  id: number;
  reunion_id: number;
  fecha_reunion: string;
  item_id: number | null;
  producto: string | null;
  asistente: string | null;
  puesto: string | null;
  texto: string;
  estado: "abierta" | "atendida";
  respuesta: string | null;
  atendida_por: string | null;
  atendida_en: string | null;
  creada_en: string;
};

export type Reunion = ReunionBreve & {
  aprendizajes: string | null;
  creada_por: string | null;
  prefiltro_en: string | null;
  comite_en: string | null;
  cerrada_por: string | null;
  productos: Item[];
  asistentes: Asistente[];
  peticiones: Peticion[];
};

export type Candidato = { tipo: "propuesta" | "idea"; id: number; nombre: string; detalle: string; color: Color | null; en_otra: boolean };
export type UsuarioBreve = { id: number; nombre: string; puesto: string | null; area: string | null };
export type Criterios = { politicas: { id: number; titulo: string; tema: string }[]; usados: string[] };
export type Aceptado = { reunion_id: number; fecha_reunion: string; producto: Item };

export const PASOS: { estado: EstadoReunion; texto: string }[] = [
  { estado: "abierta", texto: "Subir productos" },
  { estado: "prefiltro", texto: "Pre-filtro" },
  { estado: "comite", texto: "Comité" },
  { estado: "cerrada", texto: "Cerrada" },
];

export const DECISION: Record<Decision, { texto: string; boton: string; clase: string }> = {
  aceptado: { texto: "Aceptado", boton: "Aceptar", clase: "bg-green-600/10 text-green-700 dark:text-green-400" },
  denegado: { texto: "Denegado", boton: "Denegar", clase: "bg-red-600/10 text-red-700 dark:text-red-400" },
  en_espera: { texto: "En espera", boton: "En espera", clase: "bg-smn-gris-100 text-smn-gris-700" },
};

export const VALOR: Record<ValorCriterio, { texto: string; clase: string }> = {
  bien: { texto: "Bien", clase: "bg-green-600/10 text-green-700 dark:text-green-400" },
  regular: { texto: "Regular", clase: "bg-yellow-500/15 text-yellow-800 dark:text-yellow-300" },
  mal: { texto: "Mal", clase: "bg-red-600/10 text-red-700 dark:text-red-400" },
};

export const RESULTADO_REVISION: Record<Revision["resultado"], { texto: string; clase: string }> = {
  pendiente: { texto: "Pendiente", clase: "bg-smn-gris-100 text-smn-gris-700" },
  aprobada: { texto: "Aprobada", clase: "bg-green-600/10 text-green-700 dark:text-green-400" },
  rechazada: { texto: "Rechazada", clase: "bg-red-600/10 text-red-700 dark:text-red-400" },
};

export const MODELO = {
  con_proveedor: "Con proveedor actual (6 factores)",
  sin_proveedor: "Sin proveedor actual: rentabilidad y proveedor solo cuentan si hay datos",
};

export const urlFoto = (item: number, n: number) => `${urlApi()}${RUTA}/productos/${item}/fotos/${n}`;

/** La fecha de la reunión (AAAA-MM-DD) sin que la zona horaria la mueva un día. */
export const fechaReunion = (f: string, opciones: Intl.DateTimeFormatOptions = { weekday: "long", day: "numeric", month: "long", year: "numeric" }) =>
  new Date(`${f}T12:00:00`).toLocaleDateString("es-MX", opciones);

/** En qué columna del ciclo va el producto. */
export function columna(i: Item, estado: EstadoReunion): 0 | 1 | 2 | 3 {
  if (i.prefiltro === "pasa" && (estado === "comite" || estado === "cerrada")) return 3;
  if (i.prefiltro) return 2;
  if (i.evaluacion?.estado === "lista") return 1;
  return 0;
}

export const pesos = (n: string | null) => (n == null ? null : Number(n).toLocaleString("es-MX", { style: "currency", currency: "MXN" }));

/** Parecidos que ya vendemos, con su venta real en SMNBI (para la diapositiva del comité). */
export type Parecido = {
  producto_id: number;
  sku: string;
  descripcion: string | null;
  marca: string | null;
  imagen: string | null;
  precio: string | null;
  al_mes: number | null;
  tiendas: number | null;
  por_tienda_mes: number | null;
  cambio: number | null;
};
export type Parecidos = { ventana: string | null; productos: Parecido[] };

/** Acta en PDF de la reunión (borrador si no está cerrada). */
export const descargarActa = (r: Pick<Reunion, "id" | "fecha" | "estado">) =>
  descargar(`${RUTA}/reuniones/${r.id}/acta`, `Acta comite producto nuevo ${r.fecha}${r.estado === "cerrada" ? "" : " borrador"}.pdf`);
