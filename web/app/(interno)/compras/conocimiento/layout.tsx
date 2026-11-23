"use client";
// Base de conocimiento de Compras (TD001): lo que Compras sabe y aplica al decidir. Pestañas comunes.

import { useSesion } from "@/componentes/sesion";
import { CabeceraCompras } from "@/componentes/cabecera-compras";

const PESTANAS = [
  { href: "/compras/conocimiento", texto: "Avance" },
  { href: "/compras/conocimiento/politicas", texto: "Políticas" },
  { href: "/compras/conocimiento/rechazo", texto: "Rechazo directo" },
  { href: "/compras/conocimiento/criterios", texto: "Criterios y umbrales" },
  { href: "/compras/conocimiento/pesos", texto: "Peso de cada factor" },
  { href: "/compras/conocimiento/exito", texto: "Lanzamiento exitoso" },
  { href: "/compras/conocimiento/casos", texto: "Casos pasados" },
  { href: "/compras/conocimiento/proceso", texto: "Cómo se decide hoy" },
];

export default function LayoutConocimiento({ children }: { children: React.ReactNode }) {
  const { puede } = useSesion();
  if (!puede("compras.conocimiento.ver")) return <p className="text-smn-gris-500">No tienes acceso a la Base de conocimiento.</p>;
  return (
    <>
      <CabeceraCompras id="conocimiento" titulo="Base de conocimiento" descripcion="Cómo decide Compras: lo que usa el semáforo para calificar cada producto nuevo." pestanas={PESTANAS} />
      {children}
    </>
  );
}
