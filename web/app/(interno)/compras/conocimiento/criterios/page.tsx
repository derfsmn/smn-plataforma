"use client";
// Base de conocimiento · Criterios y umbrales: los valores que revisa Compras y desde cuánto son aceptables.

import { SlidersHorizontal } from "lucide-react";
import { ListaReglas } from "../piezas";

export default function Criterios() {
  return <ListaReglas tipo="umbral" icono={<SlidersHorizontal className="h-10 w-10" />} />;
}
