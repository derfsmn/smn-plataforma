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

export async function api<T = unknown>(ruta: string, opciones: { metodo?: string; cuerpo?: unknown } = {}): Promise<T> {
  let respuesta: Response;
  try {
    respuesta = await fetch(`${urlApi()}${ruta}`, {
      method: opciones.metodo ?? (opciones.cuerpo === undefined ? "GET" : "POST"),
      credentials: "include",
      headers: opciones.cuerpo === undefined ? undefined : { "Content-Type": "application/json" },
      body: opciones.cuerpo === undefined ? undefined : JSON.stringify(opciones.cuerpo),
    });
  } catch {
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
export type Icono = "carrito" | "personas" | "radar" | "mas";

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
export type Liga = { liga: string; expira_en: string };
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
