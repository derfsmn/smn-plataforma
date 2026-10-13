"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { motion } from "motion/react";
import { ArrowLeft, Construction, ExternalLink } from "lucide-react";
import { estadoModulo } from "@/lib/api";
import { useSesion } from "@/componentes/sesion";
import { IconoModulo } from "@/componentes/icono-modulo";
import { Entrada, Insignia } from "@/componentes/ui";

export default function PaginaModulo() {
  const { codigo } = useParams<{ codigo: string }>();
  const { yo } = useSesion();
  const m = yo.modulos.find((x) => x.codigo === codigo);
  if (!m) return <p className="text-smn-gris-500">Este módulo no existe o no tienes acceso.</p>;

  return (
    <>
      <Link href="/inicio" className="mb-6 inline-flex items-center gap-1 text-sm font-semibold text-smn-gris-500 hover:text-tinta">
        <ArrowLeft className="h-4 w-4" /> Inicio
      </Link>
      <Entrada className="overflow-hidden rounded-3xl bg-smn-negro p-8 text-white">
        <div className="flex flex-wrap items-center gap-4">
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-smn-naranja text-smn-negro">
            <IconoModulo icono={m.icono} className="h-7 w-7" />
          </span>
          <div>
            <p className="text-xs font-bold tracking-widest text-smn-naranja uppercase">{m.area} · {m.iniciativa ?? "Por asignar"}</p>
            <h1 className="text-2xl font-extrabold sm:text-3xl">{m.nombre}</h1>
          </div>
          <Insignia className="ml-auto bg-white/10 text-white">{estadoModulo[m.estado].texto}</Insignia>
        </div>
        <p className="mt-4 max-w-2xl text-white/70">{m.descripcion}</p>
      </Entrada>

      <Entrada retraso={0.15} className="mt-6 grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col items-center justify-center rounded-3xl border border-smn-gris-100 bg-superficie p-10 text-center sm:col-span-2">
          <motion.div animate={{ rotate: [0, -8, 8, 0] }} transition={{ duration: 2.4, repeat: Infinity, repeatDelay: 1.5 }}>
            <Construction className="h-12 w-12 text-smn-naranja" />
          </motion.div>
          <p className="mt-4 text-lg font-extrabold">Módulo en construcción</p>
          <p className="mt-1 max-w-md text-sm text-smn-gris-500">
            Aquí vivirán las pantallas de {m.area}. El cascarón ya le da usuarios, permisos, notificaciones e IA.
          </p>
        </div>
        <div className="rounded-3xl border border-smn-gris-100 bg-superficie p-6">
          <p className="text-xs font-bold text-smn-gris-500 uppercase">Responsable</p>
          <p className="mt-1 font-bold">{m.responsable ?? "Por asignar"}</p>
        </div>
        <div className="rounded-3xl border border-smn-gris-100 bg-superficie p-6">
          <p className="text-xs font-bold text-smn-gris-500 uppercase">Portal externo</p>
          <p className="mt-1 flex items-center gap-2 font-bold">
            {m.tiene_portal_externo ? <>Sí <ExternalLink className="h-4 w-4 text-smn-naranja" /></> : "No"}
          </p>
        </div>
      </Entrada>
    </>
  );
}
