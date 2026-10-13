"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { ArrowUpRight, Plus, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { api, estadoModulo, type Resumen } from "@/lib/api";
import { useSesion } from "@/componentes/sesion";
import { IconoModulo } from "@/componentes/icono-modulo";
import { Contador } from "@/componentes/contador";
import { Entrada, Insignia } from "@/componentes/ui";

const saludo = () => {
  const h = new Date().getHours();
  return h < 12 ? "Buenos días" : h < 19 ? "Buenas tardes" : "Buenas noches";
};

const contenedor = { oculto: {}, visible: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } } };
const elemento = { oculto: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] as const } } };

export default function Inicio() {
  const { yo, puede } = useSesion();
  const [resumen, setResumen] = useState<Resumen | null>(null);
  useEffect(() => {
    api<Resumen>("/api/nucleo/resumen").then(setResumen).catch(() => {});
  }, []);
  const nombre = yo.usuario.nombre.split(" ")[0];
  const esAdmin = puede("nucleo.modulos.administrar");
  const modulos = yo.modulos;

  const indicadores = [
    { texto: "Iniciativas a tu alcance", valor: resumen?.iniciativas },
    { texto: "Usuarios activos", valor: resumen?.usuarios_activos },
    { texto: "Proveedores con cuenta", valor: resumen?.proveedores },
    { texto: "Invitaciones sin aceptar", valor: resumen?.invitaciones_pendientes },
  ];

  return (
    <>
      <Entrada>
        <p className="text-sm font-bold tracking-widest text-smn-naranja uppercase">{saludo()}</p>
        <h1 className="mt-1 text-3xl font-extrabold tracking-tight sm:text-4xl">Hola{nombre && `, ${nombre}`}</h1>
        <p className="mt-2 max-w-xl text-smn-gris-500">Estas son las iniciativas de Transformación Digital a las que tienes acceso.</p>
      </Entrada>

      <Entrada retraso={0.1} className="mt-8">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {indicadores.map((i) => (
            <div key={i.texto} className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
              <p className="text-3xl font-extrabold tabular-nums">
                {i.valor === undefined ? <span className="text-smn-gris-300">–</span> : <Contador valor={i.valor} />}
              </p>
              <p className="mt-1 text-xs font-semibold text-smn-gris-500">{i.texto}</p>
            </div>
          ))}
        </div>
      </Entrada>

      <h2 className="mt-10 mb-4 text-lg font-extrabold">Iniciativas</h2>
      {modulos.length === 0 && !esAdmin && (
        <p className="rounded-3xl border border-dashed border-smn-gris-300 p-8 text-center text-sm text-smn-gris-500">
          Aún no tienes iniciativas disponibles. Aparecen aquí cuando su módulo entra a piloto y tienes un rol en él.
        </p>
      )}
      <motion.div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" variants={contenedor} initial="oculto" animate="visible">
        {modulos.map((m) => (
          <motion.div key={m.codigo} variants={elemento} whileHover={{ y: -4 }} transition={{ type: "spring", stiffness: 400, damping: 30 }}>
            <Link
              href={`/modulos/${m.codigo}`}
              className="group relative flex h-full flex-col overflow-hidden rounded-3xl border border-smn-gris-100 bg-superficie p-6 shadow-sm transition-shadow hover:shadow-xl hover:shadow-smn-naranja/10"
            >
              <span aria-hidden className="absolute -top-16 -right-16 h-40 w-40 rounded-full bg-smn-naranja/0 blur-2xl transition-colors duration-500 group-hover:bg-smn-naranja/25" />
              <div className="relative flex items-start justify-between">
                <span className="grid h-12 w-12 place-items-center rounded-2xl bg-smn-negro text-smn-naranja transition-transform dark:bg-smn-gris-100 duration-300 group-hover:scale-110 group-hover:-rotate-6">
                  <IconoModulo icono={m.icono} />
                </span>
                <Insignia className={estadoModulo[m.estado].clase}>{estadoModulo[m.estado].texto}</Insignia>
              </div>
              <p className="relative mt-5 text-xs font-bold tracking-wide text-smn-gris-500 uppercase">
                {m.area} · {m.iniciativa ?? "Por asignar"}
              </p>
              <h3 className="relative mt-1 text-xl font-extrabold">{m.nombre}</h3>
              <p className="relative mt-2 flex-1 text-sm text-smn-gris-700">{m.descripcion}</p>
              <span className="relative mt-5 inline-flex items-center gap-1 text-sm font-bold">
                Abrir
                <ArrowUpRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </span>
            </Link>
          </motion.div>
        ))}
        {esAdmin && (
          <motion.div variants={elemento}>
            <Link
              href="/admin/modulos"
              className="flex h-full min-h-56 flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed border-smn-gris-300 p-6 text-smn-gris-500 transition-colors hover:border-smn-naranja hover:text-tinta"
            >
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-smn-gris-100">
                <Plus className="h-6 w-6" />
              </span>
              <span className="font-bold">Registrar iniciativa</span>
              <span className="text-center text-xs">Cada nueva área entra como módulo del cascarón.</span>
            </Link>
          </motion.div>
        )}
      </motion.div>

      <Entrada retraso={0.3} className="mt-10">
        <div className="flex items-start gap-4 rounded-3xl bg-smn-negro p-6 text-white dark:ring-1 dark:ring-white/10">
          <Sparkles className="mt-0.5 h-6 w-6 shrink-0 text-smn-naranja" />
          <div>
            <p className="font-bold">Asistente de IA</p>
            <p className="mt-1 text-sm text-white/60">
              Cada módulo usará IA local (Ollama) o externa con tope de gasto. Se conecta en la etapa 4.
            </p>
          </div>
        </div>
      </Entrada>
    </>
  );
}
