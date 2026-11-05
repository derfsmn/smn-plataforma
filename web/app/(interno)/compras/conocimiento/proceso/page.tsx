"use client";
// Base de conocimiento · Cómo se decide hoy: el proceso actual de Compras, en texto.

import { AnimatePresence } from "motion/react";
import { Pencil, Workflow } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { CLASE_ESTADO, TEXTO_ESTADO, type Politica } from "@/lib/conocimiento";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Esqueleto, Insignia } from "@/componentes/ui";
import { EDITAR, Pie, Vacio } from "../piezas";
import { VentanaPolitica, aFormaPolitica } from "../politica";

const GUIA = `Algunas preguntas para guiarte:
• ¿Quién propone un producto nuevo y cómo llega a Compras?
• ¿Quién lo revisa y qué información tiene a la mano?
• ¿Quién aprueba? ¿Hay comité, cada cuánto se reúne?
• ¿Qué se le pide al proveedor y en qué momento?
• Después de aprobarlo, ¿cómo se da de alta y en qué tiendas entra?`;

export default function Proceso() {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const editar = puede(EDITAR);
  const [actual, setActual] = useState<Politica | null | undefined>(undefined);
  const [abierta, setAbierta] = useState(false);

  const cargar = useCallback(() => {
    api<Politica[]>("/api/compras/conocimiento/politicas")
      .then((l) => setActual(l.find((p) => p.tema === "proceso") ?? null))
      .catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  useEffect(cargar, [cargar]);

  if (actual === undefined) return <Esqueleto className="h-48" />;
  const inicial = actual ? aFormaPolitica(actual) : { tema: "proceso" as const, titulo: "Cómo se decide hoy", contenido: "", departamento: "", estado: "borrador" as const };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-2xl text-sm text-smn-gris-500">El proceso actual, de punta a punta: quién propone, quién revisa, quién aprueba y con qué información. Sirve para que el semáforo encaje en ese proceso y no lo cambie.</p>
        {editar && (
          <Boton onClick={() => setAbierta(true)}>
            <Pencil className="h-4 w-4" /> {actual ? "Editar" : "Escribir"}
          </Boton>
        )}
      </div>
      {!actual ? (
        <Vacio icono={<Workflow className="h-10 w-10" />} titulo="Todavía no está descrito" texto={<span className="whitespace-pre-line">{GUIA}</span>} />
      ) : (
        <article className="rounded-2xl border border-smn-gris-100 bg-superficie p-6">
          <p className="flex flex-wrap items-center gap-2 font-semibold">
            {actual.titulo} <Insignia className={CLASE_ESTADO[actual.estado]}>{TEXTO_ESTADO[actual.estado]}</Insignia>
          </p>
          <p className="mt-0.5 text-[13px] text-smn-gris-500">
            Versión {actual.version} · <Pie por={actual.actualizado_por} en={actual.actualizado_en} />
          </p>
          <div className="mt-4 text-sm whitespace-pre-line text-smn-gris-700">{actual.contenido || "Sin texto todavía."}</div>
        </article>
      )}
      <AnimatePresence>
        {abierta && <VentanaPolitica id={actual?.id} inicial={inicial} departamentos={[]} guia={GUIA} cerrar={() => setAbierta(false)} alGuardar={cargar} />}
      </AnimatePresence>
    </div>
  );
}
