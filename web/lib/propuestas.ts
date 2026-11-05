// Propuestas de productos nuevos (portal de proveedores y bandeja de Compras). API: api/modulos/compras/rutas_propuestas.py

import { urlApi } from "./api";

export type Estado = "borrador" | "recibida" | "en_revision" | "devuelta" | "lista" | "rechazada";

export type Presentacion = {
  codigo_barras: string | null;
  registro_sanitario: string | null;
  forma: string | null;
  forma_otro: string | null;
  ingrediente_principal: string | null;
  descripcion: string | null;
  contenido_neto: string | null;
  unidad_medida: string | null;
  piezas_caja_master: string | null;
  costo_neto_sin_iva: string | null;
  pvp_sugerido: string | null;
  margen_propuesto_pct: string | null;
  tasa_iva: string | null;
  tasa_ieps: string | null;
};

export type Respuestas = {
  aviso: { acepta_aviso_privacidad: boolean; declara_veracidad: boolean };
  proveedor: {
    marca: string | null;
    razon_social: string | null;
    nombre_comercial: string | null;
    rfc: string | null;
    es_proveedor_smn: string | null;
    publico_objetivo: string[];
    publico_objetivo_otro: string | null;
    inscrito_gs1: string | null;
    cuenta_registro_marca: string | null;
    contacto_nombre: string | null;
    contacto_cargo: string | null;
    contacto_correo: string | null;
    contacto_telefono: string | null;
    contacto_alterno_nombre: string | null;
    contacto_alterno_telefono: string | null;
    contacto_alterno_correo: string | null;
  };
  general: {
    fabricante: string | null;
    pais_origen: string | null;
    pais_origen_otro: string | null;
    diferenciador: string | null;
    diferenciador_otro: string | null;
    necesidad_atendida: string | null;
    necesidad_atendida_otro: string | null;
    departamento: string | null;
  };
  presentaciones: Presentacion[];
  mercado: {
    canal_actual: string | null;
    comercios_actuales: string[];
    comercios_actuales_otro: string | null;
    sin_datos_desempeno: boolean;
    desempeno: { tipo: string | null; cifra: string | null; canal: string | null; periodo: string | null; fuente: string | null }[];
    sin_comparables: boolean;
    competidores: { producto: string | null; presentacion: string | null; precio: string | null; comercio: string | null }[];
    similares_en_smn: string | null;
    similares_cuales: string | null;
  };
  logistica: {
    manejo_especial: string[];
    manejo_especial_otro: string | null;
    vida_util_total_dias: string | null;
    vida_util_minima_no_aplica: boolean;
    vida_util_minima_dias: string | null;
  };
  lanzamiento: {
    apoyos: { tipo: string | null; detalle: string | null; inicio: string | null; fin: string | null }[];
    apoyos_otro: string | null;
    argumento_principal: string | null;
    sustento: string | null;
  };
};

export type Adjunto = { id: number; tipo: string; etiqueta: string | null; nombre: string; tipo_contenido: string; tamano_bytes: number };
export type Falta = { seccion: string; campo: string; mensaje: string };
export type Revision = { nivel: "alerta" | "info"; texto: string };
export type Evento = { estado_antes: string | null; estado_despues: Estado; comentario: string | null; usuario: string; ocurrido_en: string };
export type Fila = { orden: number; codigo_barras: string | null; descripcion: string | null; margen_calculado: number | null; ya_en_catalogo: boolean };

export type PropuestaBreve = {
  id: number;
  folio: string | null;
  estado: Estado;
  estado_texto: string;
  producto: string | null;
  marca: string | null;
  departamento: string | null;
  empresa: string;
  presentaciones: number;
  alertas: number;
  enviada_en: string | null;
  actualizada_en: string;
  capturada_por_compras: boolean; // la capturó Compras por el proveedor
};

export type Propuesta = PropuestaBreve & {
  editable: boolean;
  comentario: string | null;
  respuestas: Respuestas;
  adjuntos: Adjunto[];
  faltantes: Falta[];
  revisiones: Revision[];
  eventos: Evento[];
  filas: Fila[];
  creada_por: string;
};

export type Opcion = { valor: string; texto: string };
export type ReglaAdjunto = { seccion: string; tipos: string[]; mb: number; minimo: number; maximo: number };
export type Catalogos = {
  opciones: Record<string, Opcion[]>;
  secciones: Opcion[];
  estados: Opcion[];
  adjuntos: Record<string, ReglaAdjunto>;
  departamentos: string[];
};

export type Bandeja = { propuestas: PropuestaBreve[]; por_estado: Partial<Record<Estado, number>> };
export type Proveedor = {
  id: number;
  nombre: string;
  correo: string;
  empresa: string | null;
  rfc: string | null;
  estatus: "invitado" | "activo" | "inactivo";
  propuestas: number;
  ultimo_acceso_en: string | null;
  creado_en: string;
};

export const RUTA = "/api/compras/propuestas";
export const urlAdjunto = (propuesta: number, adjunto: number) => `${urlApi()}${RUTA}/${propuesta}/adjuntos/${adjunto}`;

// Naranja para lo que espera a alguien; negro para lo cerrado. Sin verde: no es un semáforo.
export const estiloEstado: Record<Estado, string> = {
  borrador: "bg-smn-gris-100 text-smn-gris-700",
  recibida: "bg-smn-naranja/15 text-aviso-texto",
  en_revision: "bg-smn-naranja/15 text-aviso-texto",
  devuelta: "bg-aviso-fondo text-aviso-texto",
  lista: "bg-tinta text-superficie",
  rechazada: "bg-smn-gris-100 text-smn-gris-500",
};

export const NOMBRE_ADJUNTO: Record<string, string> = {
  imagen_producto: "Fotos del producto",
  imagen_etiquetado: "Fotos del etiquetado",
  carta_gs1: "Carta de incorporación al GS1",
  evidencia_registro_funcionamiento: "Registro de funcionamiento",
  evidencia_titulo_marca: "Título de marca",
  ficha_tecnica: "Ficha técnica",
  documento_adicional: "Documentos adicionales",
};

export const presentacionVacia = (): Presentacion => ({
  codigo_barras: null,
  registro_sanitario: null,
  forma: null,
  forma_otro: null,
  ingrediente_principal: null,
  descripcion: null,
  contenido_neto: null,
  unidad_medida: null,
  piezas_caja_master: null,
  costo_neto_sin_iva: null,
  pvp_sugerido: null,
  margen_propuesto_pct: null,
  tasa_iva: null,
  tasa_ieps: null,
});

// Margen informativo (misma fórmula que el servidor): precio sin impuestos = pvp / (1 + IVA) / (1 + IEPS)
export function margenDe(p: Presentacion): number | null {
  const costo = Number(p.costo_neto_sin_iva), pvp = Number(p.pvp_sugerido), iva = Number(p.tasa_iva), ieps = Number(p.tasa_ieps);
  if (!costo || !pvp || p.tasa_iva === null || p.tasa_iva === "" || p.tasa_ieps === null || p.tasa_ieps === "" || isNaN(iva) || isNaN(ieps)) return null;
  const base = pvp / (1 + iva / 100) / (1 + ieps / 100);
  return Math.round(((base - costo) / base) * 10000) / 100;
}
