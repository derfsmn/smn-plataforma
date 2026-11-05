"use client";
// Liga desde cualquier módulo a los manuales de métodos y procedimientos, con la pregunta ya escrita.

import Link from "next/link";
import { BookOpen } from "lucide-react";
import { useSesion } from "@/componentes/sesion";
import { PERMISO_CONSULTAR } from "@/lib/metodos";

export function PreguntaManuales({ origen, pregunta, texto = "¿Cómo se hace? Pregunta a los manuales" }: { origen: string; pregunta?: string; texto?: string }) {
  const { puede } = useSesion();
  if (!puede(PERMISO_CONSULTAR)) return null;
  const q = new URLSearchParams({ origen, ...(pregunta ? { q: pregunta } : {}) });
  return (
    <Link href={`/metodos?${q}`} className="inline-flex items-center gap-1.5 text-sm font-semibold text-naranja-tinta hover:underline">
      <BookOpen className="h-4 w-4" /> {texto}
    </Link>
  );
}
