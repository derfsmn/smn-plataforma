"use client";

// Markdown sencillo de los borradores: títulos, listas y negritas
export function Markdown({ texto }: { texto: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      {texto.split(/\n+/).map((linea, i) => {
        const l = linea.trim();
        if (!l) return null;
        const h = l.match(/^(#{1,6})\s+(.*)$/);
        const contenido = (t: string) =>
          t.split(/(\*\*[^*]+\*\*|\[PREGUNTA:[^\]]+\])/).map((p, j) =>
            p.startsWith("**") ? <strong key={j}>{p.slice(2, -2)}</strong> : p.startsWith("[PREGUNTA:") ? <mark key={j} className="rounded bg-amber-100 px-1 text-amber-900 dark:bg-amber-500/20 dark:text-amber-200">{p}</mark> : p,
          );
        if (h) {
          const n = h[1].length;
          return <p key={i} className={n === 1 ? "pt-2 text-lg font-semibold" : n === 2 ? "pt-2 font-semibold text-naranja-tinta" : "font-semibold"}>{contenido(h[2])}</p>;
        }
        if (/^([-*•]|\d+[.)])\s+/.test(l)) return <p key={i} className="pl-4">{contenido(l)}</p>;
        return <p key={i}>{contenido(l)}</p>;
      })}
    </div>
  );
}
