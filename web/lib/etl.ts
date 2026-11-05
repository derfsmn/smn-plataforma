// Tipos y llamadas del ETL de ventas del Centro de datos (/api/datos/etl)

import { ErrorApi, urlApi } from "@/lib/api";

export type EstadoCargaEtl = "en_curso" | "completa" | "fallida" | "detenida";
export type PasoEtl = "conectar" | "extraer" | "transformar" | "cargar" | "cuadrar";

export const PASOS: { codigo: PasoEtl; texto: string }[] = [
  { codigo: "conectar", texto: "Conectar" },
  { codigo: "extraer", texto: "Extraer" },
  { codigo: "transformar", texto: "Transformar" },
  { codigo: "cargar", texto: "Cargar" },
  { codigo: "cuadrar", texto: "Cuadrar" },
];

export type CargaEtl = {
  id: number;
  disparada_por: "programador" | "manual";
  usuario: string | null;
  estado: EstadoCargaEtl;
  archivo: string | null;
  desde: string | null;
  hasta: string | null;
  paso: PasoEtl | null;
  mes_actual: string | null;
  meses_total: number;
  meses_hechos: number;
  leidos: number;
  cargados: number;
  fuera: number;
  detener: boolean;
  error: string | null;
  cuadra: boolean | null;
  inicio_en: string;
  fin_en: string | null;
};

export type PasoCarga = {
  mes: string | null;
  paso: PasoEtl;
  estado: "en_curso" | "hecho" | "detenido" | "fallido";
  filas: number | null;
  nota: string | null;
  inicio_en: string;
  fin_en: string | null;
};

export type Cuadre = {
  mes: string;
  empresa: string;
  importe_origen: string | null;
  importe_cargado: string;
  piezas_origen: string | null;
  piezas_cargadas: string;
  renglones_fuera: number | null;
  cuadra: boolean | null;
};

export type CargaDetalle = CargaEtl & { pasos: PasoCarga[]; cuadre: Cuadre[] };

export type UltimaCargaSmnbi = {
  id: number;
  estado: "en_curso" | "completa" | "fallida" | "detenida";
  archivo: string | null;
  nota: string | null; // lo que dejó la carga, o por qué falló
  cargados: number;
  fuera: number;
  fin_en: string | null;
  inicio_en: string;
};

export type FuenteEtl = {
  codigo: string;
  nombre: string;
  tablas: string[];
  estado: "lista" | "en_curso";
  nota: string;
  columnas: number | null; // tablas de SMNBI: cuántas columnas trae su consulta
  filas: number | null;
  ultima_carga: string | null; // ventas: la última buena
  ultima: UltimaCargaSmnbi | null; // tablas de SMNBI
};

export type EstadoEtl = {
  conexion: { configurada: boolean; falta: string[]; servidor: string; base: string };
  factura_electronica: boolean;
  programado: boolean;
  hora: number;
  dias_semana: number[];
  proximos_meses: string[];
  en_curso: CargaEtl | null;
  resumen: { filas: number; semana_desde: string | null; semana_hasta: string | null; meses: number; ultima_buena: string | null };
  fuentes: FuenteEtl[];
  cargas: CargaEtl[];
};

export type PruebaConexion = { desde: string | null; hasta: string | null; ventas: number; articulos: number };

// Las fechas de mes llegan como "2026-09-01"; se leen sin zona horaria para que no se recorran un día
export function nombreMes(fecha: string, corto = false): string {
  const [a, m] = fecha.split("-").map(Number);
  const texto = new Date(a, m - 1, 1).toLocaleDateString("es-MX", { month: corto ? "short" : "long", year: "numeric" });
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

export function fechaDia(fecha: string): string {
  const [a, m, d] = fecha.slice(0, 10).split("-").map(Number);
  return new Date(a, m - 1, d).toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "numeric" });
}

// Subida del CSV con avance (fetch no informa el progreso de subida)
export function subirCsvVentas(archivo: File, alAvanzar?: (porcentaje: number) => void): Promise<CargaEtl> {
  return subirCsv<CargaEtl>("/api/datos/etl/archivo", archivo, alAvanzar);
}

// Una tabla de SMNBI (artículos, tiendas, proveedores, compras, costos o inventario)
export function subirCsvSmnbi(codigo: string, archivo: File, alAvanzar?: (porcentaje: number) => void): Promise<UltimaCargaSmnbi> {
  return subirCsv<UltimaCargaSmnbi>(`/api/datos/etl/smnbi/${codigo}/archivo`, archivo, alAvanzar);
}

// «Revisar si hay cambios»: el resultado de la consulta de revisión contra lo cargado. Solo lee.
export type RenglonRevision = { fuente: string; que: string; smnbi: string; plataforma: string; estado: "igual" | "cambio" | "nuevo" | "sobra"; accion: string | null };
export type RevisionSmnbi = { resumen: string; renglones: RenglonRevision[] };
export function subirRevisionSmnbi(archivo: File): Promise<RevisionSmnbi> {
  return subirCsv<RevisionSmnbi>("/api/datos/etl/smnbi/revision", archivo);
}

function subirCsv<T>(ruta: string, archivo: File, alAvanzar?: (porcentaje: number) => void): Promise<T> {
  return new Promise((resolver, rechazar) => {
    const datos = new FormData();
    datos.append("archivo", archivo);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${urlApi()}${ruta}`);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => e.lengthComputable && alAvanzar?.(Math.round((e.loaded / e.total) * 100));
    xhr.onerror = () => rechazar(new ErrorApi(0, "No hay conexión con la API. Revisa que esté corriendo."));
    xhr.onload = () => {
      let cuerpo: { detail?: unknown } | null = null;
      try {
        cuerpo = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) return resolver(cuerpo as T);
      rechazar(new ErrorApi(xhr.status, typeof cuerpo?.detail === "string" ? cuerpo.detail : "No se pudo subir el archivo."));
    };
    xhr.send(datos);
  });
}
