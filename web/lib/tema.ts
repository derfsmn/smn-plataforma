"use client";
// Tema claro / oscuro / color / según el sistema. La preferencia vive en localStorage
// y el tema resuelto se escribe en <html data-tema="claro|oscuro|marca">. «Marca» es el tema «Con color»: claro, con el
// menú del color que escoja cada persona (naranja de marca por omisión) y el fondo teñido de ese color.

export type Preferencia = "claro" | "oscuro" | "marca" | "sistema";
export const CLAVE_TEMA = "smn_td_tema";
export const CLAVE_COLOR = "smn_td_color";
export const COLOR_MARCA = "#de951b";
const EVENTO = "smn-tema";

// Colores sugeridos para el tema «Con color»; también se puede escoger cualquier otro
export const COLORES: { valor: string; texto: string }[] = [
  { valor: "#de951b", texto: "Naranja SMN" },
  { valor: "#3f8f5b", texto: "Verde" },
  { valor: "#1f9a97", texto: "Turquesa" },
  { valor: "#2f6fb0", texto: "Azul" },
  { valor: "#7b5ea7", texto: "Morado" },
  { valor: "#c2453d", texto: "Rojo" },
  { valor: "#d4699a", texto: "Rosa" },
  { valor: "#5b6168", texto: "Gris" },
];

// Letra negra o blanca según qué tan claro es el color (luminancia relativa)
const JS_COLOR = `function(c){var n=parseInt(c.slice(1),16),r=n>>16&255,g=n>>8&255,b=n&255;var f=function(v){v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)};var l=.2126*f(r)+.7152*f(g)+.0722*f(b);var s=document.documentElement.style;s.setProperty('--acento',c);s.setProperty('--acento-tinta',l>.179?'#222221':'#ffffff');s.setProperty('--acento-contra',l>.179?'#ffffff':'#222221')}`;
const pintarColor = new Function("c", `(${JS_COLOR})(c)`) as (c: string) => void;
const esColor = (c: string | null): c is string => !!c && /^#[0-9a-f]{6}$/i.test(c);

// Corre antes de pintar (ver app/layout.tsx) para evitar el parpadeo
export const scriptTema = `(function(){try{var p=localStorage.getItem('${CLAVE_TEMA}')||'sistema';var o=p==='oscuro'||(p==='sistema'&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.dataset.tema=p==='marca'?'marca':o?'oscuro':'claro';var c=localStorage.getItem('${CLAVE_COLOR}');(${JS_COLOR})(/^#[0-9a-f]{6}$/i.test(c||'')?c:'${COLOR_MARCA}')}catch(e){}})()`;

export function leerColor(): string {
  try {
    const c = localStorage.getItem(CLAVE_COLOR);
    return esColor(c) ? c.toLowerCase() : COLOR_MARCA;
  } catch {
    return COLOR_MARCA;
  }
}

export function cambiarColor(c: string) {
  if (!esColor(c)) return;
  try {
    localStorage.setItem(CLAVE_COLOR, c.toLowerCase());
  } catch {}
  pintarColor(c);
  window.dispatchEvent(new CustomEvent(EVENTO + "-color", { detail: c }));
}

export function leerPreferencia(): Preferencia {
  try {
    const p = localStorage.getItem(CLAVE_TEMA);
    return p === "claro" || p === "oscuro" || p === "marca" ? p : "sistema";
  } catch {
    return "sistema";
  }
}

const resolver = (p: Preferencia) =>
  p === "sistema" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "oscuro" : "claro") : p;

export function aplicarResuelto(p: Preferencia) {
  document.documentElement.dataset.tema = resolver(p);
}

export function cambiarTema(p: Preferencia, origen?: { x: number; y: number }) {
  try {
    localStorage.setItem(CLAVE_TEMA, p);
  } catch {}
  window.dispatchEvent(new CustomEvent(EVENTO, { detail: p }));

  const reducir = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const doc = document as Document & { startViewTransition?: (cb: () => void) => { ready: Promise<void> } };
  if (!doc.startViewTransition || reducir || resolver(p) === document.documentElement.dataset.tema) {
    aplicarResuelto(p);
    return;
  }
  const x = origen?.x ?? innerWidth / 2;
  const y = origen?.y ?? 0;
  const radio = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  doc.startViewTransition(() => aplicarResuelto(p)).ready.then(() => {
    document.documentElement.animate(
      { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radio}px at ${x}px ${y}px)`] },
      { duration: 500, easing: "ease-in-out", pseudoElement: "::view-transition-new(root)" },
    );
  });
}

export function escucharTema(alCambiar: (p: Preferencia) => void) {
  const porEvento = (e: Event) => alCambiar((e as CustomEvent<Preferencia>).detail);
  const media = matchMedia("(prefers-color-scheme: dark)");
  const porSistema = () => {
    if (leerPreferencia() === "sistema") aplicarResuelto("sistema");
  };
  window.addEventListener(EVENTO, porEvento);
  media.addEventListener("change", porSistema);
  return () => {
    window.removeEventListener(EVENTO, porEvento);
    media.removeEventListener("change", porSistema);
  };
}
