"use client";
// Campo de número (dinero, gramos, porciones). Se teclea libre; al salir del campo se lee con lib/numeros y se muestra con
// coma de miles. El papá siempre recibe el número limpio («1234.50»), así lo que se ve es lo que se guarda
// (revisión de formularios, 26 nov 2026: «1234,50» se guardaba como 123450).

import { useState } from "react";
import { Campo } from "@/componentes/ui";
import { leerNumero, teclearNumero, verNumero } from "@/lib/numeros";

export function CampoNumero({
  etiqueta,
  valor,
  cambiar,
  decimales = 2,
  placeholder,
  ayuda,
  alError,
}: {
  etiqueta: string;
  valor: string; // número limpio o ""
  cambiar: (v: string) => void;
  decimales?: number;
  placeholder?: string;
  ayuda?: string;
  alError?: (hay: boolean) => void;
}) {
  const [texto, setTexto] = useState<string | null>(null); // lo tecleado mientras el campo tiene el foco
  const [error, setError] = useState<string | undefined>();
  const leer = (t: string, mostrar: boolean) => {
    const l = leerNumero(t, decimales);
    if (mostrar || !l.error) setError(l.error); // el error se enseña al salir del campo, no a media captura
    alError?.(!!l.error);
    cambiar(l.error ? "" : l.valor ?? "");
    return l;
  };
  return (
    <div>
      <Campo
        etiqueta={etiqueta}
        value={texto ?? verNumero(valor)}
        inputMode="decimal"
        placeholder={placeholder}
        error={error}
        onFocus={() => setTexto(verNumero(valor))}
        onChange={(e) => {
          const t = teclearNumero(e.target.value);
          setTexto(t);
          leer(t, false); // el papá tiene el número aunque se guarde con Enter sin salir del campo
        }}
        onBlur={() => {
          const l = leer(texto ?? "", true);
          setTexto(l.error ? texto : null); // si no se entiende se deja lo escrito para corregirlo
        }}
      />
      {ayuda && !error && <p className="mt-1 text-[13px] text-smn-gris-500">{ayuda}</p>}
    </div>
  );
}
