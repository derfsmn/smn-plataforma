// TD003 · Proceso de la DIOT (api/modulos/contraloria/rutas_diot.py)

import { ErrorApi, urlApi } from "@/lib/api";

export const RUTA = "/api/contraloria/diot";
export const PERMISO_VER = "contraloria.diot.ver";
export const PERMISO_OPERAR = "contraloria.diot.operar";

export type Empresa = { id: number; codigo: string; nombre: string; rfc: string | null };
export type TipoDoc = { codigo: string; nombre: string; obligatorio: boolean; para_que: string; columnas: string[]; comprobar?: boolean; varios?: boolean };
export type Catalogos = {
  empresas: Empresa[];
  tipos: TipoDoc[];
  reglas: Record<string, string>;
  campos: string[];
  tipos_tercero: Record<string, string>; // vigentes en la Base de conocimiento fiscal
  tipos_operacion: Record<string, string>;
};

export type Documento = {
  id: number;
  tipo: string;
  tipo_nombre: string;
  archivo: string;
  filas: number;
  tamano: number;
  cargado_por: string | null;
  cargado_en: string;
};

export type PeriodoResumen = {
  id: number;
  empresa: Empresa;
  anio: number;
  mes: number;
  nombre: string;
  estado: "abierto" | "procesado" | "cerrado";
  procesado_en: string | null;
  terceros: number;
  pendientes: number;
};

export type Cuadre = { concepto: string; importe: string; auxiliar?: string; diferencia?: string; nota?: string };
export type Validacion = { verificacion: string; ok: boolean; detalle: string };

export type EstadoCorrida = "en_curso" | "terminada" | "detenida" | "fallida";
export type EstadoPaso = "pendiente" | "en_curso" | "ok" | "aviso" | "detenido" | "no_ejecutado";
export type CorridaResumen = {
  id: number;
  estado: EstadoCorrida;
  resultado: string | null;
  iniciada_por: string | null;
  iniciada_en: string;
  terminada_en: string | null;
};
export type PasoCorrida = {
  orden: number;
  nombre: string;
  que_hace: string;
  estado: EstadoPaso;
  resumen: string | null;
  inicio_en: string | null;
  fin_en: string | null;
};
export type LineaBitacora = { id: number; paso: number; momento: string; nivel: "info" | "ok" | "aviso" | "error"; mensaje: string };
export type Corrida = CorridaResumen & { pasos: PasoCorrida[]; lineas: LineaBitacora[] };
export type Diferencia = { rfc: string; campo: string; generado: string | null; referencia: string | null };
export type Comparacion = {
  renglones_generados: number;
  renglones_referencia: number;
  renglones_iguales: number;
  formato_igual: boolean;
  diferencias: Diferencia[];
  totales: Record<string, { generado: number; referencia: number; diferencia: number }>;
};

export type Periodo = PeriodoResumen & {
  documentos: Documento[];
  faltan: string[];
  resumen: { faltantes: string[]; cuadres: Cuadre[]; validaciones?: Validacion[]; operaciones: number; incluidas: number; terceros: number } | null;
  conteo_incidencias: Record<string, { pendiente: number; revisada: number }>;
  puede_txt: boolean;
  motivo_sin_txt: string | null;
  referencia: string | null;
  comparacion: Comparacion | null;
  corrida: CorridaResumen | null; // la última
};

export type ResultadoArchivo = {
  archivo: string;
  resultado: "documento" | "referencia" | "no_se_usa" | "error";
  tipo: string | null;
  tipo_nombre: string | null;
  mensaje: string;
};
export type Carga = { periodo: Periodo; archivos: ResultadoArchivo[] };

export type Tercero = {
  id: number;
  rfc: string;
  nombre: string | null;
  tipo_tercero: string;
  tipo_operacion: string;
  exactos: Record<string, string>;
  redondeados: Record<string, number>;
  operaciones: number;
  fuentes: string[];
  estado: "ok" | "revisar";
  ajustado: boolean;
};

export type Operacion = {
  id: number;
  fuente: string;
  fuente_nombre: string;
  renglon: number;
  referencia: string;
  rfc: string | null;
  nombre: string | null;
  regla: string;
  regla_texto: string;
  incluida: boolean;
  tasa: string | null;
  tipo_cambio: string;
  base16: string;
  iva16: string;
  base8: string;
  iva8: string;
  base0: string;
  exento: string;
  no_objeto: string;
  iva_retenido: string;
  monto: string | null;
  nota: string | null;
};

export type Impacto = "sin_impacto" | "controlado" | "posible_impacto";
export type Incidencia = {
  id: number;
  impacto: Impacto;
  codigo: string;
  mensaje: string;
  fuente: string | null;
  renglon: number | null;
  rfc: string | null;
  importe: string | null;
  estado: "pendiente" | "revisada";
  nota_revision: string | null;
  revisada_por: string | null;
  revisada_en: string | null;
};

export type Ajuste = {
  id: number;
  rfc: string;
  nombre: string | null;
  campo: string | null;
  importe: string | null;
  excluir: boolean;
  tipo_tercero: string | null;
  tipo_operacion: string | null;
  motivo: string;
  creado_por: string | null;
  creado_en: string;
};

export const IMPACTOS: Record<Impacto, { texto: string; clase: string }> = {
  posible_impacto: { texto: "Posible impacto", clase: "bg-red-100 text-red-700" },
  controlado: { texto: "Controlado", clase: "bg-amber-100 text-amber-800" },
  sin_impacto: { texto: "Sin impacto", clase: "bg-smn-gris-100 text-smn-gris-500" },
};

export const CAMPOS: Record<string, string> = {
  base16: "Base 16 %",
  iva16: "IVA 16 %",
  base8: "Base 8 %",
  iva8: "IVA 8 %",
  base0: "Base 0 %",
  exento: "Exento",
  no_objeto: "No objeto",
  iva_retenido: "IVA retenido",
};

export const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

export const pesos = (v: number | string | null | undefined) =>
  v === null || v === undefined ? "—" : (Math.round(Number(v) * 100) / 100 || 0).toLocaleString("es-MX", { maximumFractionDigits: 2, minimumFractionDigits: 0 });

/** Sube un archivo (documento de Fiscal o TXT de referencia) con su avance. */
export function subir<T>(ruta: string, archivo: File, extra: Record<string, string> = {}, alAvanzar?: (p: number) => void): Promise<T> {
  return new Promise((resolver, rechazar) => {
    const datos = new FormData();
    datos.append("archivo", archivo);
    Object.entries(extra).forEach(([k, v]) => datos.append(k, v));
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
