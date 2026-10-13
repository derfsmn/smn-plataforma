"use client";
// Tema claro / oscuro / según el sistema. La preferencia vive en localStorage
// y el tema resuelto se escribe en <html data-tema="claro|oscuro">.

export type Preferencia = "claro" | "oscuro" | "sistema";
export const CLAVE_TEMA = "smn_td_tema";
const EVENTO = "smn-tema";

// Corre antes de pintar (ver app/layout.tsx) para evitar el parpadeo
export const scriptTema = `(function(){try{var p=localStorage.getItem('${CLAVE_TEMA}')||'sistema';var o=p==='oscuro'||(p==='sistema'&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.dataset.tema=o?'oscuro':'claro'}catch(e){}})()`;

export function leerPreferencia(): Preferencia {
  try {
    const p = localStorage.getItem(CLAVE_TEMA);
    return p === "claro" || p === "oscuro" ? p : "sistema";
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
