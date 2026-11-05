// Centro de datos y modelos: tablas reales de la base, sus relaciones y los modelos que corren sobre ellas.

export const RUTA = "/api/datos/centro";

export type Dominio = "cat" | "mov" | "ext" | "com" | "res" | "fis";

export type Tabla = {
  id: string;
  nombre: string;
  tabla: string;
  dominio: Dominio;
  x: number;
  y: number;
  registros: number;
  estado: "cargado" | "sin";
  descripcion: string;
  origen: string;
  frecuencia: string;
  ruta: string | null;
  ultima_carga: string | null;
  campos: [string, string][];
  ver_datos: boolean;
};

export type Ejecucion = { fecha: string | null; caso: string; calificacion: number | null; color: string | null; estado: string | null };

export type Modelo = {
  id: string;
  sigla: string;
  nombre: string;
  tipo: string;
  iniciativa: string;
  estado: "Idea" | "En diseño" | "Piloto" | "Activo";
  descripcion: string;
  usa: string[];
  motor: string;
  salida: string;
  ruta: string | null;
  ejecuciones: Ejecucion[];
};

export type Centro = {
  dominios: Record<Dominio, string>;
  tablas: Tabla[];
  relaciones: [string, string][];
  modelos: Modelo[];
};

export type Filas = { columnas: string[]; filas: Record<string, string>[]; maximo: number };

export const CLASE_DOMINIO: Record<Dominio, string> = {
  cat: "bg-smn-naranja",
  mov: "bg-smn-gris-500",
  ext: "border-2 border-smn-gris-500 bg-transparent",
  com: "bg-tinta",
  res: "bg-emerald-600",
  fis: "bg-sky-600",
};

// Estados de las corridas de cada módulo, en palabras
export const ESTADO_CORRIDA: Record<string, string> = {
  completa: "Terminó",
  lista: "Terminó",
  terminada: "Terminó",
  en_curso: "En curso",
  pendiente: "En curso",
  fallida: "Falló",
  error: "Falló",
  cancelada: "Cancelada",
};
