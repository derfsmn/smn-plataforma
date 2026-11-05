// TD003 · DIOT: comprobaciones para validar el TXT sin ser fiscalista (api/modulos/contraloria/diot_validacion.py)

export type EstadoComprobacion = "ok" | "revisar" | "falla" | "sin_datos" | "info";

export type GrupoEmbudo = { tipo: "entra" | "sin_explicar" | "no_entra"; concepto: string; renglones: number; monto: number; sin_monto: number };
export type Embudo = { fuente: string; nombre: string; renglones: number; monto: number; grupos: GrupoEmbudo[] };
export type ProveedorMuestra = {
  rfc: string;
  nombre: string | null;
  motivo: "grande" | "azar";
  iva: number;
  monto: number;
  operaciones: number;
  revisado: boolean;
  revisado_por: string | null;
  revisado_en: string | null;
  nota: string | null;
  cambio_desde_revision: boolean;
};
export type DiferenciaProveedor = {
  rfc: string;
  nombre: string | null;
  que: string;
  campos: { campo: string; generado: string | null; referencia: string | null }[];
  motivo: string | null;
  motivo_texto: string | null;
  nota: string | null;
  por: string | null;
  en: string | null;
};
export type Movimiento = { rfc: string; nombre: string | null; monto: number };
export type Cambio = { rfc: string; nombre: string | null; antes: number; ahora: number; cambio: number | null };

/* eslint-disable @typescript-eslint/no-explicit-any */
export type Comprobacion = {
  clave: "contabilidad" | "pagos" | "declaracion" | "muestra" | "banco" | "sat" | "mes_anterior" | "formato" | "presentado";
  titulo: string;
  pregunta: string;
  estado: EstadoComprobacion;
  frase: string;
  detalle: any;
};
/* eslint-enable @typescript-eslint/no-explicit-any */

export type Firma = { firmada: boolean; por: string | null; usuario_id: number | null; en: string | null; nota: string | null; anterior_invalida: boolean };
export type Comprobaciones = {
  frase: string;
  paso: number; // 1 subir, 2 pendientes, 3 validar, 4 firmar, 5 listo
  proveedores: number;
  iva: number;
  pendientes: number;
  resueltas: number;
  comprobaciones: Comprobacion[];
  firmas: { revision: Firma; fiscal: Firma };
  puede_firmar_revision: boolean;
  firmas_obligatorias: boolean;
};

export const PERMISO_APROBAR = "contraloria.criterios.aprobar";

export const ESTADO: Record<EstadoComprobacion, { texto: string; punto: string; caja: string }> = {
  ok: { texto: "Bien", punto: "bg-emerald-500", caja: "border-emerald-200 bg-emerald-50/60 dark:border-emerald-900 dark:bg-emerald-950/30" },
  revisar: { texto: "Por revisar", punto: "bg-amber-500", caja: "border-amber-200 bg-amber-50/60 dark:border-amber-900 dark:bg-amber-950/30" },
  falla: { texto: "No cuadra", punto: "bg-red-500", caja: "border-red-200 bg-red-50/60 dark:border-red-900 dark:bg-red-950/30" },
  sin_datos: { texto: "Sin datos", punto: "bg-smn-gris-300", caja: "border-smn-gris-100 bg-superficie" },
  info: { texto: "Para mirar", punto: "bg-sky-500", caja: "border-sky-200 bg-sky-50/60 dark:border-sky-900 dark:bg-sky-950/30" },
};

export const PASOS = [
  { n: 1, titulo: "Subir y procesar", ayuda: "Los reportes del mes" },
  { n: 2, titulo: "Resolver pendientes", ayuda: "Lo que necesita una decisión" },
  { n: 3, titulo: "Validar", ayuda: "Las 9 comprobaciones" },
  { n: 4, titulo: "Firmar y descargar", ayuda: "Revisión y visto bueno" },
] as const;

/** Palabras fiscales explicadas en una línea. */
export const GLOSARIO: Record<string, string> = {
  "DIOT": "Declaración que le dice al SAT a qué proveedores les pagamos en el mes y cuánto IVA nos acreditamos.",
  "IVA acreditable": "El IVA que pagamos a proveedores y que restamos del IVA que cobramos. La DIOT dice de quién viene.",
  "Base": "Lo que se le pagó al proveedor sin IVA.",
  "Tasa 0 %": "Productos que llevan IVA pero al 0 %, como el agua de garrafón. Se declaran, pero no generan IVA.",
  "No objeto": "Pagos a los que la ley no les cobra IVA, como el IMSS o los derechos del municipio. Se declaran sin IVA.",
  "Exento": "Operaciones que la ley libera de IVA, como algunos servicios médicos.",
  "IVA retenido": "IVA que nosotros le retenemos a un proveedor (por ejemplo, a personas físicas por servicios) y pagamos al SAT por él.",
  "Tipo de tercero": "Si el proveedor es nacional (04), extranjero (05) o un renglón global de gastos menores (15).",
  "Tipo de operación": "Qué le compramos: servicios profesionales (03), renta (06), bienes y otros (85), etc.",
  "Auxiliar de IVA": "El reporte de contabilidad con cada póliza de IVA acreditable del mes. Es contra lo que se cuadra.",
  "Ajuste de Fiscal": "Un cambio a mano que decide Fiscal sobre el resultado. Siempre lleva su motivo y queda en la evidencia.",
  "Criterio": "Una regla de la Base de conocimiento fiscal: por ejemplo, «el agua de garrafón va a tasa 0 %».",
};

/** Qué hacer con cada tipo de pendiente, en palabras. */
export const QUE_HACER: Record<string, { titulo: string; importa: string; hacer: string }> = {
  "SIN-TASA": { titulo: "Un pago no dice si lleva IVA", importa: "Si lleva IVA y no se declara, el IVA del mes queda corto.", hacer: "Revisa la factura. Si lleva IVA, pide a Fiscal un ajuste; si no, márcalo como revisado con la razón." },
  "TASA-RARA": { titulo: "Un pago trae una tasa de IVA que no existe", importa: "Puede ser un error de captura en Intelisis.", hacer: "Revisa la factura y pide a Fiscal el ajuste con la tasa correcta." },
  "SIN-IVA": { titulo: "Un gasto llegó sin IVA y no hay regla para él", importa: "No se declaró. Si sí lleva IVA, falta en la DIOT.", hacer: "Pregunta a Fiscal si va a tasa 0 %, como no objeto o con IVA, y que lo registre como criterio o ajuste." },
  "DEBERIA-IVA": { titulo: "Un gasto debería traer IVA y llegó sin él", importa: "Se declaró sin IVA; si el CFDI sí trae IVA, el IVA del mes queda corto.", hacer: "Revisa el CFDI. Si trae IVA, pide a Fiscal el ajuste; si de verdad no lo trae, márcalo como revisado." },
  "SIN-RFC": { titulo: "Un proveedor no tiene RFC en el catálogo", importa: "Sin RFC no puede ir a la DIOT y su IVA se queda fuera.", hacer: "Que den de alta el RFC en el catálogo de Intelisis y vuelve a procesar." },
  "RFC-INVALIDO": { titulo: "Un RFC está mal escrito", importa: "El SAT rechaza el archivo con un RFC mal escrito.", hacer: "Corrige el RFC en el catálogo o pide a Fiscal un ajuste." },
  "IMSS-INFONAVIT": { titulo: "El pago al IMSS puede incluir INFONAVIT", importa: "El INFONAVIT no se declara; si va incluido, el no objeto queda inflado.", hacer: "Pide a Fiscal la parte del INFONAVIT (cédula o SUA) y que la reste con un ajuste." },
  "CRITERIO-PENDIENTE": { titulo: "Se usó una regla que Fiscal no ha aprobado", importa: "El resultado depende de una regla que todavía se está decidiendo.", hacer: "Pregunta a Fiscal. Si está de acuerdo, que apruebe el criterio en la Base de conocimiento fiscal." },
  "CONCILIACION": { titulo: "Un movimiento no cuadra con contabilidad", importa: "El IVA de ese movimiento es distinto al que registró contabilidad.", hacer: "Pregunta a Fiscal o a contabilidad cuál está bien y, si hace falta, que capturen un ajuste." },
  "TOPE-GLOBAL": { titulo: "El renglón global pasa del tope", importa: "Fiscal fijó que lo global no pase del 10 % del total.", hacer: "Pide a Fiscal que revise qué gastos van en el global." },
  "RET-SIN-ACREEDOR": { titulo: "Hay IVA retenido sin proveedor", importa: "Ese IVA retenido no se declara si no se sabe de quién es.", hacer: "Busca el comprobante en Intelisis y pide a Fiscal el ajuste." },
  "NEGATIVO": { titulo: "Un proveedor quedó en negativo", importa: "El SAT no acepta importes negativos.", hacer: "Suele ser una devolución. Pide a Fiscal cómo declararla." },
  "VALOR": { titulo: "Un reporte trae un dato que no es número", importa: "Ese renglón no se calculó.", hacer: "Revisa el reporte en Intelisis y vuelve a subirlo." },
  "ERROR-EXCEL": { titulo: "Un reporte trae errores de Excel", importa: "Las celdas con #N/A o #REF! no se cuentan.", hacer: "Vuelve a exportar el reporte de Intelisis sin fórmulas." },
  "LAYOUT": { titulo: "Hay un importe que el layout no sabe dónde va", importa: "Puede quedar fuera del TXT.", hacer: "Pregunta a Fiscal en qué campo va y que lo registre en el layout de la base." },
  "TIPO-NO-LEIDO": { titulo: "La lista de tipos de operación trae un nombre que no se reconoce", importa: "A ese proveedor se le puso el tipo por omisión; si es otro, la DIOT lo declara mal.", hacer: "Corrige la lista con la clave (03 servicios profesionales, 06 arrendamiento, 85 otros) y vuelve a subirla, o pide a Fiscal un ajuste." },
  "CATALOGO": { titulo: "Una clave no está en el catálogo del SAT", importa: "El SAT rechaza claves que no existen.", hacer: "Pide a Fiscal que revise el tipo de tercero u operación." },
  "SIN-RETENIDO": { titulo: "No se subió el auxiliar de IVA retenido", importa: "El IVA retenido sale en cero.", hacer: "Sube el auxiliar 2500-002-007 o confirma con Fiscal que no hubo retenciones." },
};

/** Lo que el sistema resolvió solo, en palabras. */
export const RESUELTO: Record<string, string> = {
  "POSIBLE-DUPLICADO": "Renglón igual a otro; se contaron los dos y la conciliación con contabilidad confirma si sobra.",
  "NO-OBJETO": "Gasto sin IVA que se declaró como no objeto.",
  "ANTICIPO-SF": "Anticipo sin factura: se declara cuando se aplique.",
  "CONCILIACION": "Diferencias entre pólizas que se compensan: el total cuadra.",
  "APL-TC": "Se usó el tipo de cambio del propio reporte.",
  "SIN-TIPOS": "No se subió la lista de tipos de operación; se usó el tipo por omisión.",
};

export const pesosEnteros = (n: number | string | null | undefined) =>
  n === null || n === undefined ? "—" : `$${Math.round(Number(n)).toLocaleString("es-MX")}`;
