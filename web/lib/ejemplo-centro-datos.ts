// DATOS FICTICIOS para la maqueta del Centro de datos y modelos (propuesta, 2026-10-14).
// Tablas y campos salen de docs/modelos/modelo_semaforo_v3.dbml (sin validar con Compras).
// Cifras, fechas y ejecuciones son de ejemplo: no representan a SMN. Se reemplazan por la API cuando se construya.

export type Dominio = "cat" | "mov" | "nuc" | "ext";
export type EstadoCarga = "cargado" | "parcial" | "sin";

export type Tabla = {
  id: string;
  nombre: string;
  tabla: string;
  dominio: Dominio;
  x: number;
  y: number;
  registros: string;
  estado: EstadoCarga;
  descripcion: string;
  origen: string;
  responsable: string;
  frecuencia: string;
  ultimaCarga: string;
  campos: [string, string][];
};

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
  ejecuciones: { fecha: string; caso: string; calificacion: number; color: "verde" | "amarillo" | "rojo" }[];
};

export const DOMINIOS: Record<Dominio, { nombre: string; clase: string }> = {
  cat: { nombre: "Catálogos", clase: "bg-smn-naranja" },
  mov: { nombre: "Movimientos", clase: "bg-smn-gris-500" },
  nuc: { nombre: "Núcleo", clase: "bg-tinta" },
  ext: { nombre: "Externos", clase: "border-2 border-smn-gris-500 bg-transparent" },
};

export const TABLAS: Tabla[] = [
  {
    id: "estructura", nombre: "Estructura", tabla: "departamento · rama · subcategoría", dominio: "cat", x: 16, y: 40,
    registros: "312", estado: "cargado",
    descripcion: "Árbol de departamentos, ramas, subcategorías y segmentos. Hace que los filtros sean iguales en todas las iniciativas.",
    origen: "Excel de estructura", responsable: "Por definir", frecuencia: "Cuando cambie", ultimaCarga: "12 oct 2026",
    campos: [["departamento", "texto"], ["rama", "texto"], ["subcategoria", "texto"], ["segmento", "texto"]],
  },
  {
    id: "marca", nombre: "Marcas", tabla: "marca", dominio: "cat", x: 16, y: 176,
    registros: "486", estado: "cargado",
    descripcion: "Lista única de marcas, para que una marca no aparezca escrita de tres formas.",
    origen: "Excel de productos", responsable: "Por definir", frecuencia: "Semanal", ultimaCarga: "12 oct 2026",
    campos: [["marca_id", "llave"], ["nombre", "texto"], ["es_marca_propia", "sí / no"]],
  },
  {
    id: "producto", nombre: "Productos", tabla: "producto", dominio: "cat", x: 210, y: 200,
    registros: "8,940", estado: "cargado",
    descripcion: "Ficha maestra de cada artículo. Es la tabla que más iniciativas van a usar.",
    origen: "Excel exportado a mano", responsable: "Por definir", frecuencia: "Semanal", ultimaCarga: "12 oct 2026",
    campos: [
      ["sku", "llave"], ["nombre", "texto"], ["descripcion", "texto"], ["marca", "→ Marcas"], ["departamento", "→ Estructura"],
      ["rama", "→ Estructura"], ["subcategoria", "→ Estructura"], ["segmento", "texto"], ["clasificacion", "texto"],
      ["codigo_barras", "texto"], ["estatus", "activo / baja"],
    ],
  },
  {
    id: "proveedor", nombre: "Proveedores", tabla: "proveedor", dominio: "cat", x: 404, y: 40,
    registros: "634", estado: "parcial",
    descripcion: "Proveedores actuales y prospectos. Se liga por RFC con las empresas que entran al portal de proveedores.",
    origen: "Captura y Excel", responsable: "Por definir", frecuencia: "Semanal", ultimaCarga: "10 oct 2026",
    campos: [["codigo_proveedor", "llave"], ["razon_social", "texto"], ["rfc", "único"], ["es_prospecto", "sí / no"], ["estatus", "activo / baja"]],
  },
  {
    id: "contacto", nombre: "Contactos", tabla: "proveedor_contacto", dominio: "cat", x: 598, y: 40,
    registros: "1,102", estado: "parcial",
    descripcion: "Personas de contacto de cada proveedor.",
    origen: "Captura", responsable: "Por definir", frecuencia: "Continua", ultimaCarga: "10 oct 2026",
    campos: [["proveedor", "→ Proveedores"], ["nombre", "texto"], ["correo", "texto"], ["telefono", "texto"], ["puesto", "texto"]],
  },
  {
    id: "tienda", nombre: "Tiendas", tabla: "tienda", dominio: "cat", x: 16, y: 480,
    registros: "—", estado: "sin",
    descripcion: "Sucursales con su zona y formato.",
    origen: "Sin fuente", responsable: "Por definir", frecuencia: "—", ultimaCarga: "—",
    campos: [["clave_tienda", "llave"], ["nombre", "texto"], ["zona", "texto"], ["ciudad", "texto"], ["formato", "texto"], ["estatus", "abierta / cerrada"]],
  },
  {
    id: "venta", nombre: "Ventas", tabla: "venta", dominio: "mov", x: 210, y: 400,
    registros: "—", estado: "sin",
    descripcion: "Venta por producto, tienda y día. Es el dato que alimenta casi cualquier modelo.",
    origen: "Sin fuente", responsable: "Por definir", frecuencia: "Diaria (propuesta)", ultimaCarga: "—",
    campos: [["fecha", "fecha"], ["tienda", "→ Tiendas"], ["sku", "→ Productos"], ["unidades", "número"], ["importe", "$"]],
  },
  {
    id: "inventario", nombre: "Inventario", tabla: "inventario", dominio: "mov", x: 16, y: 330,
    registros: "—", estado: "sin",
    descripcion: "Existencias por producto y tienda.",
    origen: "Sin fuente", responsable: "Por definir", frecuencia: "Diaria (propuesta)", ultimaCarga: "—",
    campos: [["fecha", "fecha"], ["tienda", "→ Tiendas"], ["sku", "→ Productos"], ["existencia", "número"]],
  },
  {
    id: "costo", nombre: "Costos y precios", tabla: "costo_precio_historico", dominio: "mov", x: 210, y: 40,
    registros: "—", estado: "sin",
    descripcion: "Historial de costo y precio de venta de cada producto.",
    origen: "Sin fuente", responsable: "Por definir", frecuencia: "Al cambiar", ultimaCarga: "—",
    campos: [["sku", "→ Productos"], ["vigente_desde", "fecha"], ["costo", "$"], ["precio_venta", "$"]],
  },
  {
    id: "oc", nombre: "Órdenes de compra", tabla: "orden_compra", dominio: "mov", x: 404, y: 200,
    registros: "—", estado: "sin",
    descripcion: "Compras hechas a cada proveedor.",
    origen: "Sin fuente", responsable: "Por definir", frecuencia: "Diaria (propuesta)", ultimaCarga: "—",
    campos: [["folio", "llave"], ["proveedor", "→ Proveedores"], ["sku", "→ Productos"], ["cantidad", "número"], ["costo", "$"], ["fecha", "fecha"]],
  },
  {
    id: "org", nombre: "Empresas del portal", tabla: "nucleo.organizacion_externa", dominio: "nuc", x: 598, y: 220,
    registros: "3", estado: "cargado",
    descripcion: "Empresas con acceso al portal de proveedores. Esta tabla ya existe en la plataforma.",
    origen: "Plataforma", responsable: "Administración", frecuencia: "Continua", ultimaCarga: "14 oct 2026",
    campos: [["id", "llave"], ["nombre", "texto"], ["rfc", "único"], ["tipo", "proveedor / candidato"]],
  },
  {
    id: "competencia", nombre: "Precios de competencia", tabla: "precio_competencia", dominio: "ext", x: 404, y: 400,
    registros: "—", estado: "sin",
    descripcion: "Precios observados en otras cadenas. Hoy viven en el radar de precios (MySQL) y se migrarían.",
    origen: "Radar de precios", responsable: "Por definir", frecuencia: "Semanal", ultimaCarga: "—",
    campos: [["sku", "→ Productos"], ["competidor", "texto"], ["precio", "$"], ["fecha", "fecha"]],
  },
];

export const RELACIONES: [string, string][] = [
  ["producto", "marca"], ["producto", "estructura"], ["contacto", "proveedor"], ["proveedor", "org"],
  ["venta", "producto"], ["venta", "tienda"], ["inventario", "producto"], ["inventario", "tienda"],
  ["costo", "producto"], ["oc", "proveedor"], ["oc", "producto"], ["competencia", "producto"],
];

export const MODELOS: Modelo[] = [
  {
    id: "semaforo", sigla: "TD1", nombre: "Semáforo de producto nuevo", tipo: "Reglas y score", iniciativa: "Compras · TD001", estado: "En diseño",
    descripcion: "Califica un producto candidato de 0 a 100: rojo hasta 59, amarillo de 60 a 80, verde arriba de 80. Los bloqueos mandan a rojo y con pocos datos queda en amarillo. La IA solo explica; decide el comité.",
    usa: ["producto", "proveedor", "venta", "costo", "competencia"], motor: "Python (motor de reglas)", salida: "Calificación, color y motivos",
    ejecuciones: [
      { fecha: "14 oct 2026 09:12", caso: "Producto candidato A", calificacion: 84, color: "verde" },
      { fecha: "13 oct 2026 17:40", caso: "Producto candidato B", calificacion: 71, color: "amarillo" },
      { fecha: "13 oct 2026 11:05", caso: "Producto candidato C", calificacion: 52, color: "rojo" },
    ],
  },
  {
    id: "demanda", sigla: "f(t)", nombre: "Pronóstico de demanda", tipo: "Estadístico", iniciativa: "Sin iniciativa", estado: "Idea",
    descripcion: "Estima unidades por producto y tienda para las próximas semanas, a partir de la venta histórica.",
    usa: ["venta", "producto", "tienda", "inventario"], motor: "Python (series de tiempo)", salida: "Unidades esperadas por semana", ejecuciones: [],
  },
  {
    id: "tiendas", sigla: "k·n", nombre: "Segmentación de tiendas", tipo: "Analítico", iniciativa: "Sin iniciativa", estado: "Idea",
    descripcion: "Agrupa tiendas que venden parecido, para dar surtidos y promociones por grupo.",
    usa: ["venta", "tienda", "estructura"], motor: "Python (agrupamiento)", salida: "Grupo de cada tienda", ejecuciones: [],
  },
  {
    id: "resumen", sigla: "IA", nombre: "Resumen de proveedor", tipo: "IA", iniciativa: "Compras · TD001", estado: "Idea",
    descripcion: "Redacta una ficha corta de cada proveedor con lo que hay en la plataforma. Pasa por la puerta de IA con su tope de gasto.",
    usa: ["proveedor", "contacto", "oc"], motor: "Puerta de IA (Ollama primero)", salida: "Texto de resumen", ejecuciones: [],
  },
];

// Filas FICTICIAS para el visor de datos. Se generan siempre iguales (semilla fija) para que la búsqueda se pueda probar.
// SKU, folios y RFC llevan el prefijo EJ / XEXX para que no se confundan con datos reales.
const DEPTOS: [string, string[]][] = [
  ["Suplementos", ["Vitaminas", "Minerales", "Proteínas"]],
  ["Herbolaria", ["Tés", "Extractos", "Cápsulas"]],
  ["Alimentos", ["Semillas", "Cereales", "Endulzantes"]],
  ["Cuidado personal", ["Piel", "Cabello", "Higiene"]],
];
const PRODUCTOS = ["Té verde", "Avena integral", "Chía", "Linaza", "Miel de abeja", "Colágeno", "Vitamina C", "Magnesio", "Spirulina", "Cúrcuma",
  "Jabón de avena", "Shampoo de romero", "Amaranto", "Stevia", "Proteína vegetal", "Omega 3", "Moringa", "Aceite de coco"];
const PRESENTACIONES = ["250 g", "500 g", "1 kg", "60 cápsulas", "120 tabletas", "250 ml"];
const MARCAS = ["Marca Ejemplo A", "Marca Ejemplo B", "Marca Ejemplo C", "Marca Ejemplo D", "Marca Ejemplo E", "Marca Ejemplo F"];
const RAZONES = ["Distribuidora Ejemplo", "Naturales Ejemplo", "Laboratorio Ejemplo", "Comercializadora Ejemplo", "Herbolaria Ejemplo"];
const NOMBRES = ["Ana", "Luis", "Carmen", "Jorge", "Sofía", "Miguel", "Laura", "Pedro"];
const APELLIDOS = ["Pérez", "García", "López", "Martínez", "Hernández", "Ramírez"];
const PUESTOS = ["Ventas", "Gerente de cuenta", "Cobranza", "Logística"];

function azar(semilla: number) {
  let s = semilla;
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648;
    return s / 2147483648;
  };
}
const elige = <T,>(r: () => number, xs: T[]) => xs[Math.floor(r() * xs.length)];
const num = (n: number, ancho: number) => String(n).padStart(ancho, "0");

export function filasEjemplo(id: string): Record<string, string>[] {
  const r = azar(id.length * 7919 + id.charCodeAt(0));
  const filas: Record<string, string>[] = [];
  if (id === "estructura") {
    for (const [d, ramas] of DEPTOS)
      for (const rama of ramas)
        for (const sub of ["General", "Premium"]) filas.push({ departamento: d, rama, subcategoria: `${rama} ${sub.toLowerCase()}`, segmento: elige(r, ["Básico", "Medio", "Alto"]) });
  } else if (id === "marca") {
    MARCAS.forEach((m, i) => filas.push({ marca_id: `EJ-M${num(i + 1, 3)}`, nombre: m, es_marca_propia: i < 2 ? "sí" : "no" }));
  } else if (id === "producto") {
    for (let i = 1; i <= 120; i++) {
      const [d, ramas] = elige(r, DEPTOS);
      const rama = elige(r, ramas);
      filas.push({
        sku: `EJ-${num(1000 + i, 5)}`, nombre: `${elige(r, PRODUCTOS)} ${elige(r, PRESENTACIONES)}`, descripcion: "Descripción de ejemplo",
        marca: elige(r, MARCAS), departamento: d, rama, subcategoria: `${rama} general`, segmento: elige(r, ["Básico", "Medio", "Alto"]),
        clasificacion: elige(r, ["A", "B", "C"]), codigo_barras: `750000${num(Math.floor(r() * 9999999), 7)}`, estatus: r() < 0.9 ? "activo" : "baja",
      });
    }
  } else if (id === "proveedor") {
    for (let i = 1; i <= 40; i++)
      filas.push({
        codigo_proveedor: `EJ-P${num(i, 4)}`, razon_social: `${elige(r, RAZONES)} ${num(i, 2)} S.A. de C.V.`, rfc: `XEXX${num(i, 6)}EJ${i % 10}`,
        es_prospecto: r() < 0.2 ? "sí" : "no", estatus: r() < 0.9 ? "activo" : "baja",
      });
  } else if (id === "contacto") {
    for (let i = 1; i <= 60; i++) {
      const n = `${elige(r, NOMBRES)} ${elige(r, APELLIDOS)}`;
      filas.push({
        proveedor: `EJ-P${num(1 + Math.floor(r() * 40), 4)}`, nombre: n, correo: `${n.split(" ")[0].toLowerCase()}${i}@ejemplo.mx`,
        telefono: `55 0000 ${num(i, 4)}`, puesto: elige(r, PUESTOS),
      });
    }
  } else if (id === "org") {
    for (let i = 1; i <= 3; i++) filas.push({ id: String(i), nombre: `Proveedor de prueba ${i}`, rfc: `XEXX${num(i, 6)}EJ${i}`, tipo: "proveedor" });
  }
  return filas;
}
