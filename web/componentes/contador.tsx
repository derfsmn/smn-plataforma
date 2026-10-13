"use client";
// Número que sube de 0 al valor al aparecer en pantalla

import { animate, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

export function Contador({ valor }: { valor: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const visible = useInView(ref, { once: true });
  const reducir = useReducedMotion();
  const [actual, setActual] = useState(0);

  useEffect(() => {
    if (!visible) return;
    if (reducir) return setActual(valor);
    const control = animate(0, valor, { duration: 0.9, ease: "easeOut", onUpdate: (v) => setActual(Math.round(v)) });
    return () => control.stop();
  }, [visible, valor, reducir]);

  return <span ref={ref}>{actual.toLocaleString("es-MX")}</span>;
}
