// Tipos y ayudas del Radar de precios (/api/compras/precios)

import { ErrorApi, urlApi } from "./api";

export type EstadoCorrida = "en_curso" | "completa" | "parcial" | "fallida";
export type EstadoFila = "pendiente" | "con_precios" | "sin_coincidencia" | "sin_precios" | "fallido" | "sin_presupuesto";
export type EstadoCoincidencia = "automatica" | "ia" | "persona" | "rechazada" | "invalidada";

export type Corrida = {
  id: number;
  fecha: string;
  origen: "programado" | "tardio" | "manual" | "prueba" | "producto";
  estado: EstadoCorrida;
  intentos: number;
  usuario: string | null;
  productos: number;
  con_coincidencia: number;
  sin_coincidencia: number;
  con_precios: number;
  fallidos: number;
  alertas: number;
  tope_usd: string | null;
  costo_usd: string;
  avisos: string[];
  error: string | null;
  iniciado_en: string;
  terminado_en: string | null;
  fase: string | null; // qué hace en este momento, mientras corre
  avance: Avance | null; // en qué paso va, cuántos lleva y en qué productos
  archivo: string | null; // prueba con Excel
  no_encontrados: string[];
};

export type Envio = { tipo: "productos" | "vendedores"; tareas: number; estado: string; estimado_usd: string; costo_usd: string | null; creado_en: string };
export type CorridaDetalle = Corrida & { envios: Envio[] };

export type Fila = {
  producto_id: number;
  sku: string;
  descripcion: string | null;
  marca: string | null;
  departamento: string | null;
  imagen: string | null;
  estado: EstadoFila;
  mensaje: string | null;
  precio_lista: string | null;
  precio_membresia: string | null;
  precio_tienda: string | null;
  vendedores: number;
  minimo: string | null;
  mediana: string | null;
  maximo: string | null;
  dif_lista_mediana_pct: string | null;
  dif_membresia_mediana_pct: string | null;
  dif_lista_minimo_pct: string | null;
  base: "lista" | "tienda" | null; // qué precio nuestro se comparó: lista o, si falta, tienda en línea
  coincidencia: "automatica" | "ia" | "persona" | null;
  limite_pct: string; // semáforo: el del producto o el general
  color: Color | null;
  tiendas: Record<string, string>; // precio de cada tienda clave que apareció (el más bajo que cuenta)
};

export type Resumen = {
  falta_configurar: string[];
  automatico: boolean;
  frecuencia: string;
  hora: number;
  proxima: string | null;
  gasto_mes_usd: string;
  tope_mes_usd: string;
  tope_corrida_usd: string;
  estimado_usd: string;
  alerta_pct: number;
  vigilados: number;
  con_coincidencia: number;
  en_curso: Corrida | null;
  ultima: Corrida | null;
  ultima_prueba: Corrida | null;
};

/** Grupos de la pantalla de productos: semáforo, los que necesitan revisión (sin coincidencia) y los que se quedaron sin precios. */
export type Grupo = "todos" | "verde" | "amarillo" | "rojo" | "revisar" | "sin_precios";
export type Orden = "diferencia" | "nombre" | "vendedores";

/** Una página de productos de la última corrida; el filtro y la paginación los hace la API. */
export type Lista = {
  corrida: Corrida | null;
  conteos: Record<Grupo, number>;
  marcas: string[];
  total: number;
  tiendas: string[]; // tiendas clave
  cobertura: Record<string, number>; // en cuántos productos apareció cada una
  pagina: number;
  por_pagina: number;
  filas: Fila[];
};

export type Coincidencia = {
  id: number;
  google_id: string | null;
  titulo: string | null;
  liga: string | null;
  imagen: string | null;
  estado: EstadoCoincidencia;
  confianza: string | null;
  motivo: string | null;
  estrategia: string | null;
  decidido_por: string | null;
  creado_en: string;
  verificado_en: string | null;
  iguales: Publicacion[];
};

/** Otra publicación de Google Shopping del mismo producto; sus vendedores también cuentan. */
export type Publicacion = {
  titulo: string | null;
  vendedor: string | null;
  precio: string | null;
  liga: string | null;
};

export type Observacion = {
  vendedor: string;
  vendedor_original: string | null;
  liga: string | null;
  precio_comparable: string;
  envio: string | null;
  moneda: string;
  disponibilidad: string | null;
  es_propia: boolean;
  fuera: string | null;
  publicacion: string | null; // título de la publicación de Google de donde salió el precio
  tienda_clave: string | null; // Walmart, Chedraui... si es una de las tiendas clave
  directa: boolean; // se leyó en el sitio de la tienda, no en Google
};

/** Qué pasó al buscar el producto en el sitio de una tienda en la última corrida. */
export type TiendaDirecta = {
  tienda: string;
  estado: "encontrado" | "sin_precio" | "no_lo_tiene" | "dudoso" | "error";
  mensaje: string | null;
  titulo: string | null;
  liga: string | null;
  precio: string | null;
  id: number | null;
};

/** Un precio de un vendedor para uno de nuestros productos (tabla de precios). */
export type RenglonTabla = {
  producto_id: number;
  sku: string;
  descripcion: string | null;
  marca: string | null;
  nuestro_precio: string | null;
  vendedor: string;
  publicacion: string | null;
  precio: string;
  envio: string | null;
  moneda: string;
  disponibilidad: string | null;
  liga: string | null;
  dif_pct: string | null; // nuestro precio contra el de este vendedor
  cuenta: boolean;
  motivo: string | null;
};

export type TablaPrecios = { corrida: Corrida | null; alerta_pct: number; renglones: RenglonTabla[] };

/** Todos los precios de la corrida (un renglón por vendedor) en CSV para Excel. */
export function csvTabla(renglones: RenglonTabla[]): string {
  const celda = (v: string | number | null) => {
    const t = v === null ? "" : String(v);
    return /[",\n;]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
  };
  const encabezado = ["SKU", "Producto", "Marca", "Nuestro precio", "Vendedor", "Publicación en Google", "Precio", "Envío", "Moneda",
    "Diferencia nuestra %", "Disponibilidad", "Cuenta para la mediana", "Por qué no cuenta", "Liga"];
  const filas = renglones.map((r) => [r.sku, r.descripcion, r.marca, r.nuestro_precio, r.vendedor, r.publicacion, r.precio, r.envio, r.moneda,
    r.dif_pct, r.disponibilidad, r.cuenta ? "Sí" : "No", r.motivo, r.liga].map(celda).join(","));
  return "\ufeff" + [encabezado.join(","), ...filas].join("\r\n"); // BOM para que Excel lea los acentos
}

export type Punto = { fecha: string; precio_lista: string | null; precio_membresia: string | null; minimo: string | null; mediana: string | null };

export type DetalleProducto = {
  producto_id: number;
  sku: string;
  descripcion: string | null;
  marca: string | null;
  codigo_barras: string | null;
  imagen: string | null;
  liga_tienda: string | null;
  vigilado: boolean;
  consulta: string | null;
  limite_propio_pct: string | null; // vacío = el general
  limite_pct: string;
  consultas: string[];
  coincidencia: Coincidencia | null;
  anteriores: Coincidencia[];
  ultima: Fila | null;
  ultima_fecha: string | null;
  ultima_iniciada: string | null; // hora en que empezó esa corrida
  observaciones: Observacion[];
  serie: Punto[];
  candidatos: CandidatoGoogle[]; // lo que regresó Google en la última búsqueda
  candidatos_fecha: string | null;
  tiendas: string[]; // tiendas clave
  directas: TiendaDirecta[]; // búsqueda en el sitio de cada tienda
};

export type CandidatoGoogle = {
  clave: string;
  titulo: string;
  precio: string | null;
  moneda: string | null;
  vendedor: string | null;
  liga: string | null;
  imagen: string | null;
  posicion: number | null;
  estrategias: string[];
  calificacion: number | null;
  aceptada: boolean;
  dudosa: boolean;
  motivo: string | null;
  elegida: boolean;
};

export type ProductoCatalogo = {
  producto_id: number;
  sku: string;
  descripcion: string | null;
  marca: string | null;
  imagen: string | null;
  precio_lista_con_impuestos: string | null;
  vigilado: boolean;
  limite_propio_pct: string | null;
  limite_pct: string | null;
  dif_pct: string | null; // última corrida: nuestro lista contra la mediana
  color: Color | null;
  ultima_fecha: string | null;
};

export const TEXTO_FILA: Record<EstadoFila, string> = {
  pendiente: "Pendiente",
  con_precios: "Con precios",
  sin_coincidencia: "Sin coincidencia confiable",
  sin_precios: "Sin precios",
  fallido: "Falló",
  sin_presupuesto: "Sin presupuesto",
};

export const TEXTO_COINCIDENCIA: Record<EstadoCoincidencia, string> = {
  automatica: "Automática",
  ia: "Decidida por la IA",
  persona: "Confirmada por una persona",
  rechazada: "Rechazada por una persona",
  invalidada: "Invalidada",
};

export const TEXTO_CORRIDA: Record<EstadoCorrida, string> = { en_curso: "En curso", completa: "Completa", parcial: "Parcial", fallida: "Falló" };

/** Estado para mostrar: una corrida que alguien detuvo dice «Detenida», no «Falló». */
export const textoCorrida = (c: Pick<Corrida, "estado" | "error">) => (c.estado === "fallida" && c.error?.startsWith("Detenida por") ? "Detenida" : TEXTO_CORRIDA[c.estado]);
export const CLASE_CORRIDA: Record<EstadoCorrida, string> = {
  en_curso: "bg-aviso-fondo text-aviso-texto",
  completa: "bg-smn-negro text-white dark:bg-smn-gris-700 dark:text-smn-negro",
  parcial: "bg-aviso-fondo text-aviso-texto",
  fallida: "bg-red-500/10 text-red-700 dark:text-red-400",
};

export const ORIGEN: Record<Corrida["origen"], string> = { programado: "programada", tardio: "programada (tardía)", manual: "a mano", prueba: "prueba con Excel", producto: "radar de productos" };

export const pct = (v: string | null, signo = true) =>
  v === null ? "—" : `${signo && Number(v) > 0 ? "+" : ""}${Number(v).toLocaleString("es-MX", { maximumFractionDigits: 1 })} %`;

// Fechas de día (sin hora) que manda la API: "2026-10-16"
export const dia = (f: string, estilo: "long" | "medium" = "long") => new Date(`${f}T12:00:00`).toLocaleDateString("es-MX", { dateStyle: estilo });
// La API manda la hora en UTC sin zona; se muestra en la hora del navegador
export const hora = (iso: string) => new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleTimeString("es-MX", { hour: "numeric", minute: "2-digit" });

/** Semáforo de precio: verde = igual o más barato que la mediana; amarillo = más caro hasta el límite; rojo = arriba del límite. */
export type Color = "verde" | "amarillo" | "rojo";

export function colorDe(valor: string | number | null, limite: number): Color | null {
  if (valor === null) return null;
  const n = Number(valor);
  return n <= 0 ? "verde" : n <= limite ? "amarillo" : "rojo";
}

export const SEMAFORO: Record<Color, { punto: string; insignia: string; texto: string }> = {
  verde: { punto: "bg-green-600", insignia: "bg-green-600/10 text-green-700 dark:text-green-400", texto: "Verde" },
  amarillo: { punto: "bg-yellow-500", insignia: "bg-yellow-500/15 text-yellow-800 dark:text-yellow-300", texto: "Amarillo" },
  rojo: { punto: "bg-red-600", insignia: "bg-red-600/10 text-red-700 dark:text-red-400", texto: "Rojo" },
};

/** Nuestro precio que se compara: el precio lista o, si el catálogo no lo tiene, el de la tienda en línea. */
export const nuestroPrecio = (f: Pick<Fila, "precio_lista" | "precio_tienda" | "base">) => (f.base === "tienda" ? f.precio_tienda : f.precio_lista);

const DISPONIBILIDAD: Record<string, string> = {
  in_stock: "En existencia",
  instock: "En existencia",
  out_of_stock: "Agotado",
  outofstock: "Agotado",
  preorder: "Preventa",
  pre_order: "Preventa",
  backorder: "Sobre pedido",
  limited_availability: "Pocas piezas",
  discontinued: "Descontinuado",
};

/** Disponibilidad de Google Shopping en español (viene como in_stock, out_of_stock…). */
export const disponibilidad = (texto: string | null) =>
  texto ? (DISPONIBILIDAD[texto.trim().toLowerCase().replace(/[\s-]+/g, "_")] ?? texto) : "Disponibilidad sin dato";

// ---------------------------------------------------------------- prueba con Excel (lista de SKU)

export type ProductoPrueba = { producto_id: number; sku: string; descripcion: string | null; marca: string | null; vigilado: boolean };
export type Prueba = { skus: number; encontrados: ProductoPrueba[]; no_encontrados: string[]; estimado_usd: string; corrida: Corrida | null };

/** Sube el Excel de la prueba. Con `revisar` solo dice qué SKU encontró y cuánto costaría; sin él, lanza la corrida. */
export async function subirPrueba(archivo: File, revisar: boolean): Promise<Prueba> {
  const datos = new FormData();
  datos.append("archivo", archivo);
  let r: Response;
  try {
    r = await fetch(`${urlApi()}/api/compras/precios/prueba?revisar=${revisar}`, { method: "POST", body: datos, credentials: "include" });
  } catch {
    throw new ErrorApi(0, "No hay conexión con la API. Revisa que esté corriendo.");
  }
  const cuerpo = await r.json().catch(() => null);
  if (!r.ok) throw new ErrorApi(r.status, typeof cuerpo?.detail === "string" ? cuerpo.detail : "No se pudo leer el archivo.");
  return cuerpo as Prueba;
}

/** Descarga un archivo de la API (Excel de una corrida o la plantilla) con la sesión del usuario. */
export async function descargar(ruta: string, nombre: string): Promise<void> {
  const r = await fetch(`${urlApi()}${ruta}`, { credentials: "include" });
  if (!r.ok) {
    const cuerpo = await r.json().catch(() => null);
    throw new ErrorApi(r.status, typeof cuerpo?.detail === "string" ? cuerpo.detail : "No se pudo descargar.");
  }
  const liga = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = liga;
  a.download = nombre;
  a.click();
  URL.revokeObjectURL(liga);
}

export const excelCorrida = (c: Pick<Corrida, "id" | "fecha" | "origen">) =>
  descargar(`/api/compras/precios/corridas/${c.id}/excel`, `radar-precios-${c.origen === "prueba" ? "prueba-" : ""}${c.fecha}-${c.id}.xlsx`);

export type Avance = {
  paso: number | null; // 1 a 4
  pasos: number;
  titulo: string | null;
  texto: string;
  hechos: number | null;
  total: number | null;
};
