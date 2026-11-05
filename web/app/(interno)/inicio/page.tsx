"use client";
// Inicio con el diseño sobrio: saludo, la pregunta a los manuales y las iniciativas.
// Los pendientes viven en las notificaciones y dentro de cada iniciativa (Diego, 2026-11-01).
// Las iniciativas se pueden ver en tres estilos para compararlos; la elección se recuerda en el navegador.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import { ArrowRight, ArrowUpRight, LayoutGrid, Rows3, Sparkles, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { estadoModulo, type Modulo } from "@/lib/api";
import { useSesion } from "@/componentes/sesion";
import { IconoModulo } from "@/componentes/icono-modulo";

type Vista = "bloques" | "indice" | "tarjetas";
const CLAVE_VISTA = "smn_td_vista_inicio";
const vistas: { valor: Vista; texto: string; icono: typeof Rows3 }[] = [
  { valor: "bloques", texto: "Bloques", icono: Square },
  { valor: "indice", texto: "Índice", icono: Rows3 },
  { valor: "tarjetas", texto: "Tarjetas", icono: LayoutGrid },
];

const saludo = () => {
  const h = new Date().getHours();
  return h < 12 ? "Buenos días" : h < 19 ? "Buenas tardes" : "Buenas noches";
};

const hoy = () => {
  const t = new Date().toLocaleDateString("es-MX", { weekday: "long", day: "numeric", month: "long" });
  return t.charAt(0).toUpperCase() + t.slice(1);
};

const contenedor = { oculto: {}, visible: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } } };
const elemento = { oculto: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] as const } } };

// Piloto y activo se distinguen con un punto de color; el texto siempre dice el estado
const punto: Record<Modulo["estado"], string> = {
  en_diseno: "bg-smn-gris-300",
  piloto: "bg-smn-naranja",
  activo: "bg-emerald-500",
  retirado: "bg-smn-gris-300",
};

// ---------------------------------------------------------------- Bloques: tipografía grande; al pasar el mouse se llena de naranja

function Bloque({ m }: { m: Modulo }) {
  return (
    <motion.div variants={elemento} className="h-full">
      <Link
        href={`/modulos/${m.codigo}`}
        className="group relative flex h-full min-h-[260px] flex-col overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie p-7 transition-colors duration-300 hover:border-[var(--resalte)] hover:bg-[var(--resalte)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-smn-naranja"
      >
        <IconoModulo
          icono={m.icono}
          className="pointer-events-none absolute -right-10 -bottom-14 h-40 w-40 -rotate-12 stroke-[1.25] text-smn-gris-100 transition-all duration-500 group-hover:-rotate-6 group-hover:text-[color-mix(in_srgb,var(--resalte-tinta)_15%,transparent)]"
        />
        <div className="relative flex items-baseline justify-between gap-3 text-sm">
          <span className="font-mono tracking-tight text-smn-gris-500 transition-colors group-hover:text-[color-mix(in_srgb,var(--resalte-tinta)_70%,transparent)]">{m.iniciativa ?? "—"}</span>
          <span className="text-smn-gris-500 transition-colors group-hover:text-[color-mix(in_srgb,var(--resalte-tinta)_70%,transparent)]">{m.area}</span>
        </div>
        <h2 className="relative mt-8 max-w-[14ch] text-[28px] leading-[1.1] font-semibold tracking-[-0.02em] transition-colors group-hover:text-[var(--resalte-tinta)]">
          {m.nombre}
        </h2>
        {m.descripcion && (
          <p className="relative mt-3 line-clamp-2 max-w-[34ch] flex-1 text-[15px] leading-relaxed text-smn-gris-700 transition-colors group-hover:text-[color-mix(in_srgb,var(--resalte-tinta)_80%,transparent)]">
            {m.descripcion}
          </p>
        )}
        <div className="relative mt-6 flex items-center justify-between border-t border-smn-gris-100 pt-4 transition-colors group-hover:border-[color-mix(in_srgb,var(--resalte-tinta)_15%,transparent)]">
          <span className="flex items-center gap-2 text-sm text-smn-gris-700 transition-colors group-hover:text-[var(--resalte-tinta)]">
            <span className={`h-2 w-2 rounded-full ${punto[m.estado]} group-hover:bg-[var(--resalte-tinta)]`} />
            {estadoModulo[m.estado].texto}
          </span>
          <span className="grid h-10 w-10 place-items-center rounded-full border border-smn-gris-100 bg-superficie transition-all duration-300 group-hover:border-[var(--resalte-tinta)] group-hover:bg-[var(--resalte-tinta)] group-hover:text-[var(--resalte)]">
            <ArrowUpRight className="h-5 w-5 transition-transform duration-300 group-hover:rotate-45" />
          </span>
        </div>
      </Link>
    </motion.div>
  );
}

// ---------------------------------------------------------------- Índice: renglones grandes, como el índice de un libro

function Renglon({ m, n }: { m: Modulo; n: number }) {
  return (
    <motion.li variants={elemento} className="border-b border-smn-gris-100 last:border-0">
      <Link href={`/modulos/${m.codigo}`} className="group relative flex items-center gap-5 px-2 py-6 sm:gap-8 sm:px-4">
        <span aria-hidden className="absolute inset-y-2 left-0 w-1 origin-top scale-y-0 rounded-full bg-smn-naranja transition-transform duration-300 group-hover:scale-y-100" />
        <span className="w-10 shrink-0 font-mono text-2xl font-light text-smn-gris-500 tabular-nums transition-colors group-hover:text-naranja-tinta sm:w-14 sm:text-4xl">
          {String(n).padStart(2, "0")}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-xl font-semibold tracking-tight sm:text-2xl">{m.nombre}</span>
            <span className="text-sm text-smn-gris-500">
              {m.area}
              {m.iniciativa && ` · ${m.iniciativa}`}
            </span>
          </span>
          {m.descripcion && <span className="mt-1 block text-[15px] text-smn-gris-700">{m.descripcion}</span>}
        </span>
        <span className="hidden shrink-0 items-center gap-2 text-sm text-smn-gris-700 md:flex">
          <span className={`h-2 w-2 rounded-full ${punto[m.estado]}`} />
          {estadoModulo[m.estado].texto}
        </span>
        <ArrowRight className="h-6 w-6 shrink-0 text-smn-gris-500 transition-all duration-300 group-hover:translate-x-1 group-hover:text-tinta" />
      </Link>
    </motion.li>
  );
}

// ---------------------------------------------------------------- Tarjetas: la versión anterior

function Tarjeta({ m }: { m: Modulo }) {
  const estado = estadoModulo[m.estado];
  return (
    <motion.div variants={elemento} className="h-full">
      <Link
        href={`/modulos/${m.codigo}`}
        className="group relative flex h-full min-h-[232px] flex-col overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie p-7 transition-[border-color,box-shadow,transform] duration-300 hover:border-smn-naranja/40 hover:shadow-[0_12px_32px_-12px_rgba(0,0,0,0.18)]"
      >
        <div className="flex items-start justify-between gap-3">
          <span className="grid h-12 w-12 place-items-center rounded-xl border border-smn-gris-100 bg-smn-gris-50 transition-colors group-hover:text-smn-naranja">
            <IconoModulo icono={m.icono} className="h-6 w-6" />
          </span>
          <span className={`rounded-full px-2.5 py-1 text-[13px] font-medium ${estado.clase}`}>{estado.texto}</span>
        </div>
        <p className="mt-6 text-sm text-smn-gris-500">
          {m.area}
          {m.iniciativa && ` · ${m.iniciativa}`}
        </p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">{m.nombre}</h2>
        {m.descripcion && <p className="mt-2 line-clamp-3 flex-1 text-[15px] leading-relaxed text-smn-gris-700">{m.descripcion}</p>}
        <span className="mt-6 inline-flex items-center gap-1.5 text-[15px] font-medium">
          Entrar <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
        </span>
      </Link>
    </motion.div>
  );
}

export default function Inicio() {
  const { yo, puede } = useSesion();
  const router = useRouter();
  const [pregunta, setPregunta] = useState("");
  const [vista, setVista] = useState<Vista>("bloques");

  useEffect(() => {
    try {
      const v = localStorage.getItem(CLAVE_VISTA);
      if (v === "bloques" || v === "indice" || v === "tarjetas") setVista(v);
    } catch {}
  }, []);

  const elegir = (v: Vista) => {
    setVista(v);
    try {
      localStorage.setItem(CLAVE_VISTA, v);
    } catch {}
  };

  const nombre = yo.usuario.nombre.replace(/\(.*\)/, "").trim().split(" ")[0];
  const preguntar = puede("metodos.consultar");
  const modulos = yo.modulos;

  return (
    <div className="font-sobria">
      <motion.header initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
        <p className="text-[15px] text-smn-gris-500">{hoy()}</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-[34px]">
          {saludo()}
          {nombre && `, ${nombre}`}
        </h1>
        <p className="mt-2 text-base text-smn-gris-500">Elige la iniciativa en la que vas a trabajar.</p>
      </motion.header>

      {preguntar && (
        <motion.form
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.05 }}
          onSubmit={(e) => {
            e.preventDefault();
            if (pregunta.trim().length >= 3) router.push(`/metodos?q=${encodeURIComponent(pregunta.trim())}`);
          }}
          className="mt-8 flex flex-wrap items-center gap-3 rounded-2xl border border-smn-gris-100 bg-superficie p-3 pl-4 transition-[border-color,box-shadow] focus-within:border-smn-naranja focus-within:ring-4 focus-within:ring-smn-naranja/15 sm:flex-nowrap"
        >
          <Sparkles className="h-5 w-5 shrink-0 text-smn-naranja" />
          <label htmlFor="pregunta-inicio" className="sr-only">
            Pregunta a los manuales
          </label>
          <input
            id="pregunta-inicio"
            value={pregunta}
            onChange={(e) => setPregunta(e.target.value)}
            placeholder="Pregunta a los manuales, por ejemplo: ¿cómo se recibe la mercancía?"
            className="h-11 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-smn-gris-500"
          />
          <button
            type="submit"
            disabled={pregunta.trim().length < 3}
            className="inline-flex h-11 items-center gap-2 rounded-xl bg-smn-negro px-5 text-[15px] font-semibold text-white transition-opacity disabled:opacity-40 dark:bg-smn-naranja dark:text-smn-negro"
          >
            Preguntar <ArrowRight className="h-4 w-4" />
          </button>
        </motion.form>
      )}

      <section className="mt-10">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Tus iniciativas</h2>
          {modulos.length > 0 && (
            <div role="radiogroup" aria-label="Cómo ver las iniciativas" className="flex rounded-lg border border-smn-gris-100 bg-superficie p-0.5">
              {vistas.map(({ valor, texto, icono: Icono }) => (
                <button
                  key={valor}
                  role="radio"
                  aria-checked={vista === valor}
                  onClick={() => elegir(valor)}
                  className={`relative flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors ${vista === valor ? "text-tinta" : "text-smn-gris-500 hover:text-tinta"}`}
                >
                  {vista === valor && <motion.span layoutId="vista-inicio" className="absolute inset-0 rounded-md bg-smn-gris-50 ring-1 ring-smn-gris-100" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
                  <Icono className="relative h-4 w-4" />
                  <span className="relative">{texto}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {modulos.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-[15px] text-smn-gris-500">
            Aún no tienes iniciativas. Aparecen aquí cuando su módulo entra a piloto y tienes un rol en él.
          </p>
        ) : vista === "indice" ? (
          <motion.ol key="indice" className="rounded-2xl border border-smn-gris-100 bg-superficie px-2 sm:px-4" variants={contenedor} initial="oculto" animate="visible">
            {modulos.map((m, i) => (
              <Renglon key={m.codigo} m={m} n={i + 1} />
            ))}
          </motion.ol>
        ) : (
          <motion.div key={vista} className="grid gap-5 md:grid-cols-2" variants={contenedor} initial="oculto" animate="visible">
            {modulos.map((m) => (vista === "bloques" ? <Bloque key={m.codigo} m={m} /> : <Tarjeta key={m.codigo} m={m} />))}
          </motion.div>
        )}
      </section>
    </div>
  );
}
