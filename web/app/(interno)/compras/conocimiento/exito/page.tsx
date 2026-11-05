"use client";
// Base de conocimiento · Lanzamiento exitoso: qué se mide para saber que un producto nuevo funcionó.

import { Trophy } from "lucide-react";
import { ListaReglas } from "../piezas";

export default function Exito() {
  return <ListaReglas tipo="exito" icono={<Trophy className="h-10 w-10" />} />;
}
