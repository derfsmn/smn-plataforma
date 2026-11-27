// Números que se capturan a mano o se pegan de Excel (revisión de formularios, 26 nov 2026). Estilo México: punto decimal
// y coma de miles, pero sin cambiar en silencio lo que la persona quiso decir:
//   «1,234.50» → 1234.50   «$459» → 459   «459.» → 459   «.5» → 0.5   «1 234.50» → 1234.50
//   «1234,50» → 1234.50 (coma que no separa miles = decimal)   «1.234,50» → 1234.50 (el último separador es el decimal)
// Antes «1234,50» se guardaba como 123450 y «1.234,50» como 1.2345.
// Mientras se teclea no se cambia nada (el cursor no brinca); se lee al salir del campo y al guardar.

export type Lectura = { valor: string | null; error?: string };

const MILES = /^\d{1,3}([,.]\d{3})+$/;

/** Texto capturado → número limpio («1234.50»), null si está vacío, o el error en palabras de negocio. */
export function leerNumero(texto: string | null | undefined, decimales = 2): Lectura {
  let t = (texto ?? "").replace(/[\s $]/g, "").replace(/MXN|mxn|%/g, "");
  if (!t) return { valor: null };
  if (/e[+-]?\d/i.test(t)) return { valor: null, error: "Se pegó como número de Excel (con «E+»); escríbelo completo." };
  if (/[^\d.,]/.test(t)) return { valor: null, error: "Escribe solo números, por ejemplo 1,234.50." };
  const comas = (t.match(/,/g) ?? []).length;
  const puntos = (t.match(/\./g) ?? []).length;
  if (comas && puntos) {
    // El que va al final es el decimal; el otro separa miles
    const decimal = t.lastIndexOf(".") > t.lastIndexOf(",") ? "." : ",";
    const miles = decimal === "." ? "," : ".";
    const partes = t.split(decimal);
    const entero = partes[0];
    const gruposOk = !entero.includes(miles) || MILES.test(entero.split(miles).join(","));
    if (partes.length !== 2 || !gruposOk) return { valor: null, error: "No se entiende el número; escríbelo como 1,234.50." };
    t = entero.split(miles).join("") + "." + partes[1];
  } else if (comas) {
    // Solo comas: si todas separan grupos de 3 son miles («1,234»); una sola que no, es decimal («1234,50»)
    if (MILES.test(t)) t = t.replace(/,/g, "");
    else if (comas === 1) t = t.replace(",", ".");
    else return { valor: null, error: "No se entiende el número; escríbelo como 1,234.50." };
  } else if (puntos > 1) {
    if (MILES.test(t)) t = t.replace(/\./g, "");
    else return { valor: null, error: "No se entiende el número; escríbelo como 1,234.50." };
  }
  if (t.startsWith(".")) t = "0" + t;
  if (t.endsWith(".")) t = t.slice(0, -1);
  if (!/^\d+(\.\d+)?$/.test(t)) return { valor: null, error: "Escribe solo números, por ejemplo 1,234.50." };
  t = t.replace(/^0+(?=\d)/, "");
  const dec = t.split(".")[1] ?? "";
  if (dec.length > decimales)
    return { valor: null, error: decimales ? `Máximo ${decimales} decimales.` : "Escribe un número entero, sin decimales." };
  return { valor: t };
}

/** Número limpio → como se ve en pantalla, con coma de miles y los mismos decimales («1234.5» → «1,234.5»). */
export function verNumero(valor: string | number | null | undefined): string {
  if (valor === null || valor === undefined || valor === "") return "";
  const [entero, dec] = String(valor).split(".");
  return entero.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (dec !== undefined ? "." + dec : "");
}

/** Mientras se teclea solo se quitan letras: el texto queda como lo escribió la persona y el cursor no se mueve. */
export function teclearNumero(texto: string): string {
  // La «E» y el «+» se quedan para avisar que Excel lo pegó en notación científica (antes «1.5E+3» quedaba en 1.53)
  return texto.replace(/[^\d.,$\s%eE+]/g, "").slice(0, 24);
}

/** Código de barras: solo dígitos, con sus ceros a la izquierda (nunca se vuelve número). */
export function leerCodigoBarras(texto: string | null | undefined): Lectura {
  const t = (texto ?? "").trim();
  if (!t) return { valor: null };
  if (/e[+-]?\d/i.test(t)) return { valor: null, error: "Excel lo pegó como número (con «E+») y perdió dígitos; cópialo como texto." };
  const d = t.replace(/[\s-]/g, "");
  if (/\D/.test(d)) return { valor: null, error: "El código de barras lleva solo números." };
  if (d.length < 6 || d.length > 14) return { valor: d, error: "El código de barras lleva de 6 a 14 números." };
  return { valor: d };
}
