// Datos → Clientes: tipos de cliente según cómo compran. API: api/datos/rutas_clientes.py
// Sin datos de personas: de SMNBI sale un CSV con códigos que cambian en cada corrida; aquí solo llegan los perfiles.

import { ErrorApi, urlApi } from "./api";

export const RUTA = "/api/datos/clientes";

export type Rango = { p25: number; p50: number; p75: number; p90: number; p95: number };

export type TipoCliente = {
  tipo: number;
  nombre: string;
  descripcion: string | null;
  acciones: string[];
  clientes: number;
  parte_clientes: number;
  notas: number;
  parte_notas: number;
  parte_venta: number;
  compras_al_mes: number;
  gasto_al_mes: number;
  ticket: number;
  precio_por_pieza: number;
  meses_que_compra: number;
  mezcla: { departamento: string; parte: number; empresa: number }[];
  de_mas: string[];
  precios: Record<string, Rango>;
  regiones: { region: string; parte: number }[];
};

export type Resumen = {
  clientes: number;
  notas_identificadas: number;
  venta_identificada: number;
  cuentas_genericas: number;
  notas_genericas: number;
  venta_generica: number;
  parte_notas_identificadas: number | null;
  precios_por_departamento: Record<string, Rango>;
  precio_generico_por_departamento: Record<string, number>;
  parte_venta_por_departamento?: Record<string, number>;
  opciones: { tipos: number; calidad: number }[];
};

export type Corrida = {
  id: number;
  estado: "en_curso" | "completa" | "fallida";
  paso: string | null;
  archivo: string | null;
  renglones: number | null;
  clientes: number | null;
  tipos: number | null;
  calidad: number | null;
  nota_ia: string | null;
  error: string | null;
  iniciada_en: string;
  terminada_en: string | null;
};

export type Estado = {
  corrida: Corrida | null;
  en_curso: Corrida | null;
  fallida: Corrida | null;
  resumen: Resumen | null;
  tipos: TipoCliente[];
  hay_archivo: boolean;
  objetivo: Objetivo | null;
  borrador_objetivo: string | null; // lo que dicen las compras; la IA lo recibe junto con la descripción
  niveles: string[];
};

// «Nuestro cliente»: nivel socioeconómico al que le vendemos; «Buscar oportunidades» valida contra él
export type Objetivo = { nivel: string; descripcion: string | null; actualizado_en: string | null };

export function subirClientes(archivo: File, tipos: number | null, alAvanzar?: (p: number) => void): Promise<Corrida> {
  return new Promise((resolver, rechazar) => {
    const datos = new FormData();
    datos.append("archivo", archivo);
    if (tipos) datos.append("tipos", String(tipos));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${urlApi()}${RUTA}/cargar`);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => e.lengthComputable && alAvanzar?.(Math.round((e.loaded / e.total) * 100));
    xhr.onerror = () => rechazar(new ErrorApi(0, "No hay conexión con la API. Revisa que esté corriendo."));
    xhr.onload = () => {
      let cuerpo: { detail?: unknown } | null = null;
      try {
        cuerpo = JSON.parse(xhr.responseText);
      } catch {}
      if (xhr.status >= 200 && xhr.status < 300) return resolver(cuerpo as Corrida);
      rechazar(new ErrorApi(xhr.status, typeof cuerpo?.detail === "string" ? cuerpo.detail : "No se pudo subir el archivo."));
    };
    xhr.send(datos);
  });
}

export const pesos = (n: number) => n.toLocaleString("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });
export const numero = (n: number) => n.toLocaleString("es-MX");
