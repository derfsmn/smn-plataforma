// Cliente de la API. La sesión viaja en una cookie httpOnly (credentials: "include").

const API_CONFIGURADA = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Si la API está en "localhost", se usa el mismo nombre con el que se abrió la web
// (localhost, 127.0.0.1 o la IP del equipo). Así el navegador manda la cookie de sesión.
export function urlApi(): string {
  if (typeof window === "undefined") return API_CONFIGURADA;
  try {
    const u = new URL(API_CONFIGURADA);
    if (u.hostname === "localhost" || u.hostname === "127.0.0.1") {
      u.hostname = window.location.hostname;
      return u.origin;
    }
  } catch {}
  return API_CONFIGURADA;
}

export class ErrorApi extends Error {
  constructor(public estado: number, mensaje: string) {
    super(mensaje);
  }
}

// `senal` permite cancelar la petición (AbortController); si se cancela, se relanza el error original.
export async function api<T = unknown>(ruta: string, opciones: { metodo?: string; cuerpo?: unknown; senal?: AbortSignal } = {}): Promise<T> {
  let respuesta: Response;
  try {
    respuesta = await fetch(`${urlApi()}${ruta}`, {
      method: opciones.metodo ?? (opciones.cuerpo === undefined ? "GET" : "POST"),
      credentials: "include",
      headers: opciones.cuerpo === undefined ? undefined : { "Content-Type": "application/json" },
      body: opciones.cuerpo === undefined ? undefined : JSON.stringify(opciones.cuerpo),
      signal: opciones.senal,
    });
  } catch (e) {
    if (opciones.senal?.aborted) throw e;
    throw new ErrorApi(0, "No hay conexión con la API. Revisa que esté corriendo.");
  }
  if (respuesta.status === 204) return undefined as T;
  const datos = await respuesta.json().catch(() => null);
  if (!respuesta.ok) {
    const detalle = datos?.detail;
    const mensaje =
      typeof detalle === "string" ? detalle : Array.isArray(detalle) ? "Revisa los datos del formulario." : "Algo salió mal. Intenta de nuevo.";
    throw new ErrorApi(respuesta.status, mensaje);
  }
  return datos as T;
}

export const mensajeDe = (e: unknown) => (e instanceof Error ? e.message : "Algo salió mal. Intenta de nuevo.");

// ---- Tipos que devuelve la API (api/nucleo/esquemas.py)

export type EstadoModulo = "en_diseno" | "piloto" | "activo" | "retirado";
export type Icono = "carrito" | "personas" | "radar" | "tienda" | "fiscal" | "libro" | "mas";

export type Usuario = {
  id: number;
  nombre: string;
  correo: string;
  tipo: "interno" | "externo";
  area: string | null;
  puesto: string | null;
  empresa: string | null;
  estatus: "invitado" | "activo" | "inactivo";
  roles: { codigo: string; nombre: string }[];
  ultimo_acceso_en: string | null;
  creado_en: string;
};

export type Modulo = {
  codigo: string;
  iniciativa: string | null;
  nombre: string;
  area: string;
  descripcion: string | null;
  estado: EstadoModulo;
  responsable: string | null;
  tiene_portal_externo: boolean;
  icono: Icono;
};

export type Yo = {
  usuario: Usuario;
  permisos: string[];
  modulos: Modulo[];
  debe_cambiar_contrasena: boolean;
  entorno: string;
};

export type Rol = { codigo: string; nombre: string; descripcion: string | null; para: "interno" | "externo"; modulo: string | null; permisos: string[] };
export type Permiso = { codigo: string; descripcion: string; modulo: string };
export type Liga = { liga: string; expira_en: string; correo_enviado: boolean };
export type DatosLiga = { nombre: string; correo: string; tipo: "interno" | "externo"; empresa: string | null };
export type Resumen = { iniciativas: number; usuarios_activos: number; proveedores: number; invitaciones_pendientes: number };

export const estadoModulo: Record<EstadoModulo, { texto: string; clase: string }> = {
  en_diseno: { texto: "En diseño", clase: "bg-smn-gris-100 text-smn-gris-700" },
  piloto: { texto: "Piloto", clase: "bg-smn-naranja/15 text-aviso-texto" },
  activo: { texto: "Activo", clase: "bg-tinta text-superficie" },
  retirado: { texto: "Retirado", clase: "bg-smn-gris-100 text-smn-gris-500 line-through" },
};

// Fechas de la API vienen en UTC sin zona
export function haceCuanto(fecha: string | null): string {
  if (!fecha) return "Nunca";
  const ms = Date.now() - new Date(fecha.endsWith("Z") ? fecha : `${fecha}Z`).getTime();
  const min = Math.floor(ms / 60000);
  if (min < 2) return "Hace un momento";
  if (min < 60) return `Hace ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `Hace ${h} h`;
  const d = Math.floor(h / 24);
  return d === 1 ? "Ayer" : `Hace ${d} días`;
}

export const fechaLocal = (fecha: string, opciones: Intl.DateTimeFormatOptions = { dateStyle: "medium", timeStyle: "short" }) =>
  new Date(fecha.endsWith("Z") ? fecha : `${fecha}Z`).toLocaleString("es-MX", opciones);

// Todo monto va con su moneda: los costos de la plataforma están en pesos (MXN); los precios de la IA, en dólares (USD).
export const pesos = (n: number | string) =>
  `${Number(n).toLocaleString("es-MX", { style: "currency", currency: "MXN", minimumFractionDigits: 2, maximumFractionDigits: 2 })} MXN`;
export const dolares = (n: number | string, decimales = 2) =>
  `${Number(n).toLocaleString("es-MX", { style: "currency", currency: "USD", currencyDisplay: "narrowSymbol", minimumFractionDigits: decimales, maximumFractionDigits: decimales })} USD`;

// ---- Servicios comunes (etapa 4)

export type Notificacion = { id: number; titulo: string; mensaje: string; liga: string | null; enviada_en: string; leida: boolean };
export type Bandeja = { no_leidas: number; notificaciones: Notificacion[] };

export type RenglonBitacora = {
  id: number;
  ocurrido_en: string;
  usuario: string | null;
  correo: string | null;
  accion: string;
  entidad: string | null;
  entidad_id: string | null;
  modulo: string | null;
  detalle: unknown;
  ip: string | null;
};
export type PaginaBitacora = { total: number; pagina: number; por_pagina: number; renglones: RenglonBitacora[] };

export type Archivo = {
  id: number;
  nombre: string;
  tipo: string;
  tamano_bytes: number;
  subido_en: string;
  modulo: string | null;
  entidad: string | null;
  entidad_id: string | null;
};

// Subida con avance (fetch no informa el progreso de subida)
export function subirArchivo(
  archivo: File,
  extra: { modulo?: string; entidad?: string; entidad_id?: string } = {},
  alAvanzar?: (porcentaje: number) => void,
): Promise<Archivo> {
  return new Promise((resolver, rechazar) => {
    const datos = new FormData();
    datos.append("archivo", archivo);
    Object.entries(extra).forEach(([k, v]) => v && datos.append(k, v));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${urlApi()}/api/archivos`);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => e.lengthComputable && alAvanzar?.(Math.round((e.loaded / e.total) * 100));
    xhr.onerror = () => rechazar(new ErrorApi(0, "No hay conexión con la API. Revisa que esté corriendo."));
    xhr.onload = () => {
      let cuerpo: { detail?: unknown } | null = null;
      try {
        cuerpo = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) return resolver(cuerpo as Archivo);
      rechazar(new ErrorApi(xhr.status, typeof cuerpo?.detail === "string" ? cuerpo.detail : "No se pudo subir el archivo."));
    };
    xhr.send(datos);
  });
}

export const urlArchivo = (id: number) => `${urlApi()}/api/archivos/${id}`;

export function tamanoLegible(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// ---- Puerta de IA

export type Gasto = { alcance: string; modulo: string | null; nombre: string; gastado_mxn: string; tope_mxn: string | null };
export type EstadoIA = {
  ollama_url: string;
  ollama_modelo: string | null;
  ollama_disponible: boolean;
  ollama_modelos: string[];
  api_encendida: boolean;
  api_motivos: string[];
  api_proveedor: string;
  api_modelo: string;
  precio_entrada_usd_mtok: number;
  precio_salida_usd_mtok: number;
  tipo_cambio_mxn: number | null;
  gastos: Gasto[];
  costo_real_activo: boolean;
};
export type DiaCosto = { fecha: string; estimado_mxn: string; real_mxn: string | null; real_usd: string | null };
export type CostosReales = {
  activo: boolean;
  motivo: string | null;
  proyecto: string | null;
  ultimo_intento: string | null;
  error: string | null;
  dias: DiaCosto[];
};
export type Tope = {
  alcance: "plataforma" | "modulo" | "usuario_dia";
  modulo: string | null;
  tope_mxn: string;
  aviso_pct: number;
  al_superar: "rechazar" | "usar_ollama";
};
export type TareaIA = { codigo: string; descripcion: string; modulo: string | null; proveedor_ia: "ollama" | "api" | "ollama_y_api_respaldo"; modelo: string | null; activa: boolean };
export type LlamadaIA = {
  id: number;
  ocurrido_en: string;
  tarea: string;
  usuario: string | null;
  proveedor_ia: string;
  modelo: string | null;
  tokens_entrada: number;
  tokens_salida: number;
  costo_mxn: string;
  duracion_ms: number;
  resultado: string;
  detalle: string | null;
};
export type ResultadoPrueba = {
  texto: string;
  proveedor: string;
  modelo: string;
  tokens_entrada: number;
  tokens_salida: number;
  costo_mxn: string;
  duracion_ms: number;
  completa: boolean;
};

// ---- Configuración (Administración > Configuración)

export type AjusteConfig = {
  clave: string;
  etiqueta: string;
  tipo: "texto" | "url" | "entero" | "decimal" | "booleano" | "secreto" | "opcion" | "dias";
  ayuda: string;
  minimo: number | null;
  maximo: number | null;
  opciones: { valor: string; texto: string }[];
  valor: string | number | boolean | null;
  configurado: boolean;
  pista: string | null;
  origen: "pantalla" | "archivo" | "omision";
};
export type GrupoConfig = { grupo: string; nombre: string; ajustes: AjusteConfig[] };
