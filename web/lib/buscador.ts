// Buscador de productos de Compras (22 nov 2026): tipos de la API y a dónde lleva cada resultado.

export const RUTA_BUSCADOR = "/api/compras/buscador";
/** Quien tenga alguno de estos permisos puede buscar (igual que la API). */
export const PERMISOS_BUSCADOR = ["compras.productos.ver", "compras.precios.ver", "compras.propuestas.ver", "datos.productos.ver"];

export type Color = "verde" | "amarillo" | "rojo";

export type Resultado = {
  tipo: "catalogo" | "idea" | "propuesta";
  id: number;
  titulo: string;
  detalle: string;
  imagen: string | null;
  precio: string | null;
  color: Color | null;
  activo: boolean;
};

export type Busqueda = { q: string; catalogo: Resultado[]; catalogo_total: number; nuevos: Resultado[] };

export const hrefDe = (r: Pick<Resultado, "tipo" | "id">) =>
  r.tipo === "catalogo" ? `/compras/buscar/${r.id}` : r.tipo === "idea" ? `/compras/productos/${r.id}` : `/compras/propuestas/${r.id}`;

export type Ficha = {
  id: number;
  sku: string;
  descripcion: string | null;
  marca: string | null;
  departamento: string | null;
  rama: string | null;
  subcategoria: string | null;
  clasificacion: string | null;
  codigo_barras: string | null;
  imagen: string | null;
  liga_producto: string | null;
  activo: boolean;
  precio_lista: string | null;
  precio_membresia: string | null;
  precio_tienda_en_linea: string | null;
  iva_pct: string | null;
  venta: {
    desde: string;
    hasta: string;
    nota: string;
    semanas: { semana: string; piezas: number; importe: number }[];
    piezas: number;
    importe: number;
    al_mes: number | null;
    recientes: number;
    anteriores: number;
    tendencia_pct: number | null;
    tiendas: number;
    margen_real_pct: number | null;
    mejores: { almacen: string; nombre: string; piezas: number }[];
  } | null;
  inventario: {
    corte: string;
    existencia: number;
    tiendas_con: number;
    tiendas_en_cero: number;
    dias: number | null;
    mayores: { almacen: string; nombre: string; existencia: number }[];
  } | null;
  costo: { ultimo: string | null; fecha_ultima: string | null; promedio_12m: string | null; piezas_12m: string | null; margen_pct: number | null } | null;
  proveedor: {
    codigo: string;
    nombre: string | null;
    dias_entrega: number | null;
    condicion: string | null;
    puntaje: number | null;
    color: Color | null;
    surtido_pct: number | null;
    dias_reales: number | null;
  } | null;
  mercado: {
    fecha: string;
    mediana: string | null;
    minimo: string | null;
    maximo: string | null;
    vendedores: number;
    diferencia_pct: string | null;
    color: Color | null;
    vigilado: boolean;
  } | null;
  relacionados: { tipo: "idea" | "propuesta"; id: number; titulo: string; color: Color | null; puntaje: number | null }[];
};

export const piezas = (n: number) => n.toLocaleString("es-MX", { maximumFractionDigits: n < 10 ? 1 : 0 });
