// Inicio: lo que le toca a cada quien hoy y el pulso de cada área (GET /api/nucleo/inicio).

export type Pendiente = {
  clave: string;
  modulo: string;
  area: string;
  texto: string;
  cantidad: number;
  accion: string;
  href: string;
  urgente: boolean;
};

export type Pulso = { clave: string; texto: string; valor: string; detalle: string | null; href: string };

export type DatosInicio = { pendientes: Pendiente[]; pulso: Pulso[] };

// Nombres de cada tramo de la ruta para la barra de arriba (Compras / Radar de precios)
export const NOMBRES_RUTA: Record<string, string> = {
  inicio: "Inicio",
  modulos: "Iniciativas",
  compras: "Compras",
  precios: "Radar de precios",
  productos: "Productos",
  propuestas: "Propuestas",
  captura: "Captura de Compras",
  comite: "Comité",
  presentar: "Presentación",
  proveedores: "Proveedores",
  oportunidades: "Oportunidades",
  radar: "Radar de tendencias",
  conocimiento: "Base de conocimiento",
  corridas: "Corridas",
  tabla: "Tabla",
  producto: "Producto",
  contraloria: "Contraloría",
  diot: "DIOT",
  metodos: "Métodos",
  borradores: "Borradores",
  documentos: "Manuales",
  datos: "Datos",
  tiendas: "Mapa de tiendas",
  inventario: "Salud de inventario",
  etl: "ETL de ventas",
  admin: "Administración",
  usuarios: "Usuarios",
  roles: "Roles y permisos",
  ia: "Inteligencia artificial",
  bitacora: "Bitácora",
  configuracion: "Configuración",
  sistema: "Estado del sistema",
  perfil: "Mi perfil",
  senal: "Señal",
  fuentes: "Fuentes",
  destinatarios: "Destinatarios",
  historico: "Histórico",
  tendencias: "Tendencias",
  politicas: "Políticas",
  criterios: "Criterios",
  pesos: "Peso de cada factor",
  casos: "Casos",
  exito: "Éxito",
  rechazo: "Rechazo",
  proceso: "Proceso",
};

export const sinAcentos = (t: string) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// Rutas que sí tienen pantalla (sin las de detalle con número). La barra de arriba solo liga a estas; un tramo
// intermedio sin pantalla (p. ej. /admin o /compras/precios/producto) se muestra como texto.
export const RUTAS_CON_PANTALLA = new Set<string>([
  "/admin/bitacora",
  "/admin/configuracion",
  "/admin/ia",
  "/admin/modulos",
  "/admin/roles",
  "/admin/sistema",
  "/admin/usuarios",
  "/compras/conocimiento",
  "/compras/conocimiento/casos",
  "/compras/conocimiento/criterios",
  "/compras/conocimiento/exito",
  "/compras/conocimiento/pesos",
  "/compras/conocimiento/politicas",
  "/compras/conocimiento/proceso",
  "/compras/conocimiento/rechazo",
  "/compras/precios",
  "/compras/precios/corridas",
  "/compras/precios/productos",
  "/compras/precios/tabla",
  "/compras/productos",
  "/compras/productos/oportunidades",
  "/compras/propuestas",
  "/compras/propuestas/comite",
  "/compras/propuestas/proveedores",
  "/compras/radar",
  "/compras/radar/conocimiento",
  "/compras/radar/corridas",
  "/compras/radar/destinatarios",
  "/compras/radar/fuentes",
  "/compras/radar/historico",
  "/compras/radar/tendencias",
  "/contraloria/conocimiento",
  "/contraloria/diot",
  "/datos",
  "/datos/etl",
  "/datos/inventario",
  "/datos/productos",
  "/datos/proveedores",
  "/datos/tiendas",
  "/inicio",
  "/kiosco",
  "/login",
  "/metodos",
  "/perfil",
  "/proveedores",
]);
