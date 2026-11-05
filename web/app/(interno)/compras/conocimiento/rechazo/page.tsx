"use client";
// Base de conocimiento · Rechazo directo: lo que pone un producto en rojo sin importar lo demás.

import { OctagonX } from "lucide-react";
import { ListaReglas } from "../piezas";

export default function Rechazo() {
  return <ListaReglas tipo="rechazo" icono={<OctagonX className="h-10 w-10" />} />;
}
