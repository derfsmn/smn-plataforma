"use client";

import { motion } from "motion/react";

function fortaleza(c: string) {
  let p = 0;
  if (c.length >= 10) p++;
  if (c.length >= 14) p++;
  if (/[A-Z]/.test(c) && /[a-z]/.test(c)) p++;
  if (/\d/.test(c) && /[^A-Za-z0-9]/.test(c)) p++;
  return c.length < 10 ? Math.min(p, 1) : p;
}
const nivel = ["Muy débil", "Débil", "Regular", "Buena", "Excelente"];

export function MedidorContrasena({ contrasena }: { contrasena: string }) {
  const puntos = fortaleza(contrasena);
  return (
    <div>
      <div className="grid grid-cols-4 gap-1.5">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-1.5 overflow-hidden rounded-full bg-smn-gris-100">
            <motion.div className="h-full bg-smn-naranja" initial={false} animate={{ width: i < puntos ? "100%" : "0%" }} transition={{ duration: 0.3 }} />
          </div>
        ))}
      </div>
      <p className="mt-1 text-xs text-smn-gris-500">
        {contrasena ? (contrasena.length < 10 ? `Faltan ${10 - contrasena.length} caracteres` : nivel[puntos]) : "Usa 10 caracteres o más; mezcla letras, números y símbolos."}
      </p>
    </div>
  );
}
