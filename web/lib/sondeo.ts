// Preguntar a la API cada cierto tiempo sin encimar peticiones (revisión del 26 nov 2026): con la base lenta, setInterval
// lanzaba otra consulta aunque la anterior no hubiera terminado y se acababan las conexiones de la API. Aquí la siguiente
// consulta se programa hasta que termina la anterior, igual que en el monitor.
"use client";

import { useEffect, useRef } from "react";

/** Mientras `activo` sea verdadero, llama `traer` cada `cadaMs` contando desde que terminó la llamada anterior. */
export function useSondeo(traer: () => unknown, cadaMs: number, activo: boolean): void {
  const ultimo = useRef(traer);
  ultimo.current = traer;
  useEffect(() => {
    if (!activo) return;
    let vivo = true;
    let t: ReturnType<typeof setTimeout> | undefined;
    const ciclo = () => {
      t = setTimeout(() => {
        Promise.resolve()
          .then(() => ultimo.current())
          .catch(() => undefined)
          .finally(() => { if (vivo) ciclo(); });
      }, cadaMs);
    };
    ciclo();
    return () => {
      vivo = false;
      clearTimeout(t);
    };
  }, [activo, cadaMs]);
}
