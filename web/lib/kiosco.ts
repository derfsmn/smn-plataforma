// Kiosco Digital (Tiendas · TD002): tipos del contrato con la API y lectura de la herramienta de catálogo.
// Las tarjetas de productos salen solo del JSON de `buscar_productos_smn`; nunca de la prosa del modelo.

export const PERMISO_KIOSCO = "kiosco.naturi.usar";

export type ModoKiosco = "voz" | "texto";

// GET /api/kiosco/configuracion
export type ConfigKiosco = { disponible: boolean; terminos: string; version_terminos: string; texto: boolean; fotos: boolean };
// POST /api/kiosco/sesion
export type SesionKiosco = { signed_url: string; modo: string };

export const HERRAMIENTA_CATALOGO = "buscar_productos_smn";
export const CDN_FOTOS = "https://supernaturista.com/cdn/shop/files/";

export type ProductoKiosco = {
  sku: string; // texto: conserva ceros iniciales
  nombre: string;
  marca: string;
  precio_lista: string | null;
  precio_membresia: string | null;
};

export type Catalogo =
  | { estado: "no_disponible"; productos: []; consulta: "" }
  | {
      estado: "listo" | "vacio" | "agotado";
      productos: ProductoKiosco[];
      consulta: string;
      total: number;
      filtros: Record<string, string>;
    };

// Lo que llega en onAgentToolResponse (respuesta simple o con resultado completo)
export type RespuestaHerramienta = {
  tool_name: string;
  tool_call_id: string;
  is_error: boolean;
  is_called?: boolean;
  is_blocked?: boolean;
  truncated?: boolean;
  full_tool_result?: string;
};

const formatoPesos = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", minimumFractionDigits: 2, maximumFractionDigits: 8 });
export const importe = (valor: string) => `${formatoPesos.format(Number(valor))} MXN`;

function precioValido(valor: unknown): string | null {
  return typeof valor === "string" && /^\d{1,10}(\.\d{1,8})?$/.test(valor) && Number.isFinite(Number(valor)) && Number(valor) > 0 ? valor : null;
}

export const fotoProducto = (sku: string) => `${CDN_FOTOS}${encodeURIComponent(sku)}.jpg`;

type Crudo = Record<string, unknown>;

export function leerCatalogo(r: RespuestaHerramienta): Catalogo {
  const noDisponible: Catalogo = { estado: "no_disponible", productos: [], consulta: "" };
  if (r.is_error || r.is_blocked || r.is_called === false || r.truncated || typeof r.full_tool_result !== "string" || r.full_tool_result.length > 65536)
    return noDisponible;
  try {
    const datos = JSON.parse(r.full_tool_result) as Crudo | null;
    if (
      !datos ||
      typeof datos.consulta !== "string" ||
      !Array.isArray(datos.resultados) ||
      datos.resultados.length > 10 ||
      !Number.isInteger(datos.total_coincidencias) ||
      (datos.total_coincidencias as number) < datos.resultados.length
    )
      return noDisponible;
    const conPrecios = datos.precios_habilitados === true;
    const vistos = new Set<string>();
    const productos: ProductoKiosco[] = [];
    for (const p of datos.resultados as (Crudo | null)[]) {
      if (!p || typeof p.sku !== "string" || !p.sku.trim() || p.sku.length > 80 || typeof p.nombre !== "string" || !p.nombre.trim()) return noDisponible;
      if (vistos.has(p.sku)) continue;
      vistos.add(p.sku);
      productos.push({
        sku: p.sku,
        nombre: p.nombre.slice(0, 300),
        marca: typeof p.marca === "string" ? p.marca.slice(0, 160) : "",
        precio_lista: conPrecios ? precioValido(p.precio_lista) : null,
        precio_membresia: conPrecios ? precioValido(p.precio_membresia) : null,
      });
    }
    const filtrosCrudos = (datos.filtros ?? {}) as Crudo;
    const filtros = Object.fromEntries(
      ["marca", "presentacion", "tipo_precio", "orden", "precio_maximo", "precio_menor_que"]
        .filter((k) => typeof filtrosCrudos[k] === "string")
        .map((k) => [k, (filtrosCrudos[k] as string).slice(0, 160)]),
    );
    const excluidos = filtrosCrudos.excluir_skus;
    const estado = productos.length
      ? "listo"
      : (typeof datos.desplazamiento === "number" && datos.desplazamiento > 0) || (Array.isArray(excluidos) && excluidos.length > 0)
        ? "agotado"
        : "vacio";
    return { estado, productos, consulta: datos.consulta.slice(0, 200), total: datos.total_coincidencias as number, filtros };
  } catch {
    return noDisponible;
  }
}
