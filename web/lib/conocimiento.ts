// Base de conocimiento de Compras: tipos y textos compartidos por sus pantallas.

export type Tema = "alta_productos" | "proveedores" | "regulatorio" | "precios" | "comite" | "proceso" | "otra";
export type EstadoPolitica = "borrador" | "vigente" | "archivada";
export type TipoRegla = "rechazo" | "umbral" | "exito";
export type Decision = "aprobado" | "rechazado" | "condicionado";
export type Resultado = "funciono" | "no_funciono" | "sin_dato" | "no_aplica";

export type Seccion = { clave: string; titulo: string; cuantos: number; lista: boolean; falta: string | null };
export type Resumen = { secciones: Seccion[]; listas: number; total: number; actualizado_en: string | null };

export type Politica = {
  id: number;
  tema: Tema;
  titulo: string;
  contenido: string;
  departamento: string | null;
  estado: EstadoPolitica;
  version: number;
  actualizado_por: string | null;
  actualizado_en: string;
};

export type Regla = {
  id: number;
  tipo: TipoRegla;
  criterio: string;
  departamento: string | null;
  minimo: string | null;
  maximo: string | null;
  unidad: string | null;
  periodo_meses: number | null;
  descripcion: string | null;
  activa: boolean;
  actualizado_por: string | null;
  actualizado_en: string;
};

export type Peso = { factor: string; nombre: string; que_mide: string; puntos: number; nota: string | null };
export type Pesos = { factores: Peso[]; total: number; actualizado_por: string | null; actualizado_en: string | null };
export type PesosProveedor = { bloques: Peso[]; total: number; de: "compras" | "provisionales" };

export type Caso = {
  id: number;
  producto: string;
  sku: string | null;
  proveedor: string | null;
  departamento: string | null;
  fecha_decision: string | null;
  decision: Decision;
  motivo: string | null;
  resultado: Resultado;
  notas: string | null;
  actualizado_por: string | null;
  actualizado_en: string;
};

export const TEMAS: { valor: Tema; texto: string }[] = [
  { valor: "alta_productos", texto: "Alta de productos nuevos" },
  { valor: "proveedores", texto: "Proveedores" },
  { valor: "regulatorio", texto: "Regulatorio y etiquetado" },
  { valor: "precios", texto: "Precio, margen y condiciones" },
  { valor: "comite", texto: "Comité y aprobación" },
  { valor: "otra", texto: "Otra" },
];
export const TEXTO_TEMA: Record<Tema, string> = {
  ...(Object.fromEntries(TEMAS.map((t) => [t.valor, t.texto])) as Record<Exclude<Tema, "proceso">, string>),
  proceso: "Cómo se decide hoy",
};

export const TEXTO_ESTADO: Record<EstadoPolitica, string> = { borrador: "Borrador", vigente: "Vigente", archivada: "Archivada" };
export const CLASE_ESTADO: Record<EstadoPolitica, string> = {
  borrador: "bg-smn-gris-100 text-smn-gris-700",
  vigente: "bg-smn-naranja/15 text-aviso-texto",
  archivada: "bg-smn-gris-100 text-smn-gris-500",
};

export const TEXTO_DECISION: Record<Decision, string> = { aprobado: "Aprobado", rechazado: "Rechazado", condicionado: "Condicionado" };
export const TEXTO_RESULTADO: Record<Resultado, string> = {
  funciono: "Funcionó",
  no_funciono: "No funcionó",
  sin_dato: "Sin dato",
  no_aplica: "No aplica (no se lanzó)",
};

// Qué pide cada tipo de regla en pantalla
export const TIPOS_REGLA: Record<TipoRegla, { titulo: string; explicacion: string; criterio: string; ejemplo: string; nuevo: string }> = {
  rechazo: {
    titulo: "Rechazo directo",
    explicacion: "Lo que hace que un producto se rechace sin importar lo demás. En el semáforo sale en rojo directo, con este motivo.",
    criterio: "Motivo de rechazo",
    ejemplo: "Ej. No tiene registro o aviso sanitario vigente",
    nuevo: "Agregar motivo",
  },
  umbral: {
    titulo: "Criterios y umbrales",
    explicacion: "Los valores que se revisan y a partir de cuánto algo es aceptable. Si cambian por departamento, agrega una línea por departamento.",
    criterio: "Criterio",
    ejemplo: "Ej. Margen, vida útil al recibir, pedido mínimo, días de crédito",
    nuevo: "Agregar criterio",
  },
  exito: {
    titulo: "Lanzamiento exitoso",
    explicacion: "Cómo sabe Compras que un producto nuevo funcionó: qué se mide, cuánto y en cuánto tiempo. Con esto el semáforo aprende a distinguir un buen candidato.",
    criterio: "Qué se mide",
    ejemplo: "Ej. Piezas vendidas por tienda al mes",
    nuevo: "Agregar meta",
  },
};

export const numero = (v: string | null) => (v == null ? "" : Number(v).toLocaleString("es-MX", { maximumFractionDigits: 4 }));

export function rango(r: Regla): string {
  const u = r.unidad ? ` ${r.unidad}` : "";
  const min = r.minimo != null ? numero(r.minimo) : null;
  const max = r.maximo != null ? numero(r.maximo) : null;
  const valor = min && max ? `de ${min} a ${max}${u}` : min ? `${r.tipo === "exito" ? "" : "mínimo "}${min}${u}` : max ? `máximo ${max}${u}` : "";
  const periodo = r.periodo_meses ? ` en ${r.periodo_meses} ${r.periodo_meses === 1 ? "mes" : "meses"}` : "";
  return `${valor}${periodo}`.trim();
}
