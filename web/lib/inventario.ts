// Datos → Salud de inventario: foto de inventario contra la venta de las últimas 13 semanas por tienda y producto.

export const RUTA = "/api/datos/inventario";

export type Tipo = "sin_venta" | "exceso" | "en_cero";

export type Sumas = {
  valor: number;
  valor_sin_venta: number;
  valor_exceso: number;
  existencia: number;
  piezas: number;
  dias: number | null;
  sin_venta: number;
  exceso: number;
  en_cero: number;
  con_existencia: number;
};

export type ResumenInventario = {
  corte: string | null;
  venta?: { desde: string; hasta: string; texto: string };
  reglas?: { semanas: number; dias_exceso: number; min_piezas_faltante: number };
  total?: Sumas;
  por_tienda?: ({ almacen: string; nombre: string; categoria: string | null } & Sumas)[];
  por_departamento?: ({ departamento: string } & Sumas)[];
  otros_almacenes?: { almacen: string; nombre: string; categoria: string | null; valor: number; existencia: number }[];
};

export type RenglonInventario = {
  almacen: string;
  tienda: string;
  sku: string;
  descripcion: string | null;
  departamento: string | null;
  proveedor: string | null;
  existencia: number;
  costo: number | null;
  valor: number;
  piezas: number;
  por_semana: number;
  dias: number | null;
  en_cero_en?: string[];
};

export const TIPO: Record<Tipo, { texto: string; explica: string }> = {
  sin_venta: { texto: "Sin venta", explica: "Tienen existencia y no vendieron ni una pieza en 13 semanas." },
  exceso: { texto: "Exceso", explica: "Les alcanza para más de 180 días al ritmo de las últimas 13 semanas." },
  en_cero: { texto: "En cero", explica: "Venden al menos una pieza por semana y en la foto no tenían existencia." },
};
