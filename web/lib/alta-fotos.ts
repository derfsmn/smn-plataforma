// Alta con fotos (26 nov 2026): lo que la IA leyó de la etiqueta solo llena lo vacío; lo que la persona ya escribió manda.

/** Llena los campos vacíos con lo leído. Regresa el formulario nuevo y qué campos se llenaron. */
export function llenarVacios<T extends Record<string, string>>(d: T, leidos: Record<string, string>): { d: T; llenos: string[] } {
  const y: Record<string, string> = { ...d };
  const llenos: string[] = [];
  for (const [k, v] of Object.entries(leidos)) {
    if (k in y && !String(y[k] ?? "").trim() && String(v ?? "").trim()) {
      y[k] = String(v).trim();
      llenos.push(k);
    }
  }
  return { d: y as T, llenos };
}

/** Lo que falta capturar a mano (lo que una etiqueta no trae o no se alcanzó a leer). */
export function pendientes(d: Record<string, string>, sinProveedor: boolean): string[] {
  return [
    !d.nombre?.trim() && "nombre del producto",
    !d.marca?.trim() && "marca",
    !d.contenido?.trim() && "contenido",
    !d.precio_nuestro?.trim() && "nuestro precio de venta",
    !d.costo_estimado?.trim() && "costo sin IVA",
    !d.lista_margen && "tipo de producto",
    sinProveedor && "proveedor (si ya lo sabes)",
  ].filter(Boolean) as string[];
}
