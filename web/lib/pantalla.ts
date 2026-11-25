// Pantalla del comité de producto nuevo (plan aprobado por Diego el 20 nov 2026). API: api/modulos/compras/pantalla_comite.py
// Cuatro niveles: ¿cómo salió? · ¿por qué? · ¿cómo se calculó? · ¿con qué datos?

import type { Color } from "./precios";

// 25 nov 2026 (Diego): el Precio en dos temas, contra anaquel y contra afuera; las evaluaciones de antes traen «precio»
export type FactorClave = "demanda" | "categoria" | "rentabilidad" | "precio" | "precio_anaquel" | "precio_afuera";

export type FactorPantalla = {
  factor: FactorClave;
  nombre: string;
  peso: number;
  puntaje: number | null;
  color: Color | null;
  de: number | null; // puntos que puede aportar (su peso entre los factores con datos)
  aporte: number | null;
  valor: string | null;
  detalle: string | null;
  calculo: string | null;
  mejora: string | null;
  provisional?: boolean;
};

export type Titular = { antes: string; resaltado: string; despues: string };
export type Paso = { titulo: string; pregunta?: string; cifra?: string; sub?: string; puntos?: string[]; texto?: string };

export type Escenario = {
  clave: "pesimista" | "esperado" | "optimista";
  nombre: string;
  por_tienda: number;
  piezas: number;
  venta: number | null;
  utilidad: number | null;
  clase: string;
  acumulado: (number | null)[];
  piezas_mes: number[];
};

export type ParecidoPantalla = {
  producto_id: number;
  sku: string;
  descripcion: string;
  marca: string | null;
  imagen: string | null;
  clasificacion: string | null;
  departamento: string | null;
  subcategoria: string | null;
  forma: string | null;
  formato?: string | null;
  al_mes: number | null;
  tiendas: number | null;
  por_tienda: number | null;
  clase: string;
  cambio: number | null;
  precio: number | null;
  precio_lista: number | null;
  margen: number | null;
  tamano: string | null;
  porciones: number | null;
  por_porcion: number | null;
  cuenta: boolean | null; // null: no es parecido (lo más vendido, un lanzamiento)
  por_que: string | null;
  similitud: number | null;
  meses: { mes: string; etiqueta: string; piezas: number }[];
};

export type Afuera = {
  titulo: string;
  vendedor: string;
  precio: number;
  liga: string | null;
  fuente: string;
  mercado_libre: boolean;
  cuenta?: boolean; // false: la página de la marca o lo que vio Compras; se enseña y no califica (22 nov 2026)
  por_porcion: number | null;
  venta?: string | null; // señal de venta: «Más vendido · +2,000 comprados el mes pasado» (22 nov 2026)
  venta_fuerte?: boolean;
};

/** 22 nov 2026: el Precio también con el precio de membresía (pesa la mitad). */
export type MembresiaPrecio = {
  precio: number | null;
  calculado: boolean;
  puntaje: number | null;
  color: Color | null;
  valor: string | null;
  afuera: MitadPrecio | null;
  anaquel: MitadPrecio | null;
};

export type PorUnidad = { propio: number; medio: number; unidad: string; toma?: { piezas: number; tomas: number; por_toma: number; si_de_1_pct: number } | null };
export type MitadPrecio = { puntaje: number | null; color: Color | null; valor: string | null; detalle: string; diferencia_pct: number | null; referencia: number | null; por_unidad?: PorUnidad | null; provisional?: boolean };

type Comun = { titular: Titular; a_favor: string[]; en_contra: string[]; subiria: string | null; pasos: Paso[] };

export type Pantalla = {
  evaluacion_id: number;
  producto: {
    nombre: string;
    marca: string | null;
    presentacion: string;
    proveedor: string | null;
    clasificacion: string | null;
    departamento: string | null;
    subcategoria: string | null;
    tipo: "idea" | "propuesta";
    codigo_barras: string | null;
    forma: string | null;
    contenido: string | null;
    fotos: string[];
  };
  puntaje: number | null;
  color: Color | null;
  color_radar: Color | null;
  confianza: string | null;
  veredicto: string;
  dictamen: string;
  pesos_direccion: boolean;
  cifras: {
    precio: number | null;
    costo: number | null;
    margen: number | null;
    minimo: number | null;
    porciones: number | null;
    por_porcion: number | null;
    venta_3m: number | null;
    venta_3m_texto: string | null;
    clase_esperada: string | null;
    tiendas: number | null;
    venta_cadena_texto?: string | null;
    tiendas_cadena?: number | null;
    precio_membresia?: number | null;
    margen_membresia?: number | null;
    lista?: string | null;
  };
  factores: FactorPantalla[];
  proveedor: { nombre: string | null; valor: string | null; puntaje: number | null; detalle: string | null };
  demanda: Comun & {
    rango: number[] | null;
    tiendas: number | null;
    escenarios: Escenario[];
    lugar: number | null;
    lanzamientos: number[];
    del_depto: boolean;
    misma_sub: { sku: string; descripcion: string; por_tienda: number }[];
    tendencia: { smn: number | null; senal: string | null; puntos: number; por: string[] };
    venta_afuera?: { fuente: string; vendedor: string | null; texto: string; liga: string | null; puntos: number }[];
    prueba: { probados: number; color: number; clase: number; en_rango?: number } | null;
    venta_3m: number | null;
    cadena?: { tiendas: number; venta: number | null; piezas: number; utilidad: number | null } | null;
  };
  precio: PrecioPantalla & { referencia: number | null; diferencia_pct: number | null };
  precio_anaquel?: PrecioPantalla & { lado: "anaquel"; provisional: boolean };
  precio_afuera?: PrecioPantalla & { lado: "afuera"; provisional: boolean };
  categoria: Comun & {
    productos: number | null;
    tipica: number | null;
    dias_inventario: number | null;
    mas_vendidos: { sku: string; descripcion: string; al_mes: number | null; por_tienda: number | null; imagen: string | null }[];
    detalle: string;
  };
  rentabilidad: Comun & {
    margen: number | null;
    minimo: number | null;
    margen_sub: number | null;
    lista?: string | null;
    membresia?: { precio: number | null; calculado: boolean; margen: number | null; minimo: number | null } | null;
    utilidad_pieza: number | null;
    escenarios: { nombre: string; precio: number | null; costo: number | null; margen: number | null }[];
    detalle: string;
  };
  parecidos: ParecidoPantalla[];
  catalogo?: Record<string, ParecidoPantalla>; // todo producto que menciona la pantalla, para picarlo
  nuevo: { descripcion: string; precio: number | null; porciones: number | null; por_porcion: number | null; por_tienda: number | null; clase: string | null };
  ventana: string | null;
  desde: string | null;
  hasta: string | null;
  venta_al?: string | null; // se armó con la venta hasta esta fecha y se está rearmando con la nueva
  fuentes: string[];
};

type PrecioPantalla = Comun & {
    referencia?: number | null;
    diferencia_pct?: number | null;
    afuera: Afuera[];
    mercado_libre: Afuera[];
    mercado_libre_nota?: string | null;
    mitades?: { afuera: MitadPrecio | null; anaquel: MitadPrecio | null; membresia?: MembresiaPrecio | null };
    membresia?: MembresiaPrecio | null;
    compite?: { sku: string; descripcion: string; imagen: string | null; clase: string; clasificacion?: string | null; por_tienda: number | null; precio: number | null; por_porcion: number | null; tamano: string | null }[];
    por_porcion: number | null;
    porciones: number | null;
    veces: number | null;
    barras: { nombre: string; valor: number; tipo: "nuevo" | "afuera" | "parecido"; sku?: string; imagen?: string | null }[];
    barras_nota?: string | null;
    se_lleva: { monto: number; unidad: string; filas: { nombre: string; cantidad: number; tipo: "nuevo" | "parecido"; sku?: string; imagen?: string | null }[] } | null;
};

export const HEX: Record<Color, string> = { verde: "#2e8b57", amarillo: "#d99a1b", rojo: "#c8412f" };
export const hexDe = (c: Color | null) => (c ? HEX[c] : "#9b9b96");
export const colorPuntaje = (p: number | null): Color | null => (p == null ? null : p > 80 ? "verde" : p >= 60 ? "amarillo" : "rojo");

export const num = (x: number | null | undefined, d = 1) =>
  x == null ? "—" : Math.abs(x - Math.round(x)) < 0.05 ? Math.round(x).toLocaleString("es-MX") : x.toLocaleString("es-MX", { minimumFractionDigits: d, maximumFractionDigits: d });
export const pesos = (x: number | null | undefined, d = 2) =>
  x == null ? "—" : `$${x.toLocaleString("es-MX", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
export const miles = (x: number | null | undefined) =>
  x == null ? "—" : Math.abs(x) >= 10000 ? `$${Math.round(x / 1000).toLocaleString("es-MX")} mil` : pesos(x, 0);
export const siglas = (texto: string) =>
  texto
    .replace(/[^A-Za-zÁÉÍÓÚÑáéíóúñ ]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 1)
    .slice(0, 1)
    .map((w) => w.slice(0, 3).toUpperCase())
    .join("") || "·";
