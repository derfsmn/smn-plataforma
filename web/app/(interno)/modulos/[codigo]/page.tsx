"use client";
// Pantalla de cada iniciativa con el diseño sobrio: encabezado, lo que está por atender en esta área (pendientes
// reales según permisos) y sus herramientas en bloques, igual que el Inicio.

import Link from "next/link";
import { useParams } from "next/navigation";
import { motion } from "motion/react";
import { ArrowRight, ArrowUpRight, BookOpen, Construction, FileSpreadsheet, Gauge, MessageCircle, PackagePlus, Radar, Tags } from "lucide-react";
import { useEffect, useState } from "react";
import { api, estadoModulo, type Modulo } from "@/lib/api";
import type { DatosInicio, Pendiente } from "@/lib/inicio";
import { PERMISO_KIOSCO } from "@/lib/kiosco";
import { PERMISO_CONSULTAR as PERMISO_CONSULTAR_METODOS } from "@/lib/metodos";
import { useSesion } from "@/componentes/sesion";
import { IconoModulo } from "@/componentes/icono-modulo";

type Herramienta = { modulo: string; permiso: string; href: string; titulo: string; texto: string; icono: typeof Radar; piloto?: boolean };

const HERRAMIENTAS: Herramienta[] = [
  { modulo: "compras", permiso: "compras.propuestas.ver", href: "/compras/propuestas", titulo: "Productos nuevos", icono: PackagePlus,
    texto: "Propuestas que mandan los proveedores desde su portal: revisión, folio y estado. Aquí se invita a los proveedores." },
  { modulo: "compras", permiso: "compras.productos.ver", href: "/compras/productos", titulo: "Radar de productos", icono: Gauge,
    texto: "Semáforo con explicación para cada producto nuevo: propuestas de proveedores e ideas que captura Compras con fotos." },
  { modulo: "compras", permiso: "compras.radar.ver", href: "/compras/radar", titulo: "Radar de tendencias", icono: Radar,
    texto: "Lo que se mueve en suplementos y naturistas, cada mañana, con fuentes y decisiones." },
  { modulo: "compras", permiso: "compras.precios.ver", href: "/compras/precios", titulo: "Radar de precios", icono: Tags,
    texto: "Nuestro precio contra la competencia en Google Shopping y en Walmart, Chedraui, San Pablo y Soriana, producto por producto." },
  { modulo: "compras", permiso: "compras.conocimiento.ver", href: "/compras/conocimiento", titulo: "Base de conocimiento", icono: BookOpen,
    texto: "Cómo decide Compras: políticas, motivos de rechazo, criterios, pesos y casos pasados que usa el semáforo de productos." },
  { modulo: "contraloria", permiso: "contraloria.diot.ver", href: "/contraloria/diot", titulo: "Proceso de la DIOT", icono: FileSpreadsheet, piloto: true,
    texto: "Sube los reportes del mes, procesa, revisa las excepciones y descarga el TXT para el SAT con su evidencia." },
  { modulo: "contraloria", permiso: "contraloria.diot.ver", href: "/contraloria/conocimiento", titulo: "Base de conocimiento fiscal", icono: BookOpen,
    texto: "Los criterios con que se arma la DIOT, los catálogos del SAT y los documentos de soporte. Fiscal los aprueba y los prueba con un mes antes de usarlos." },
  { modulo: "metodos", permiso: PERMISO_CONSULTAR_METODOS, href: "/metodos", titulo: "Preguntar a los manuales", icono: BookOpen, piloto: true,
    texto: "Pregunta cómo se hace algo y recibe la respuesta con la cita del manual vigente. Las áreas cargan sus manuales y la IA local les ayuda a redactarlos." },
  { modulo: "kiosco", permiso: PERMISO_KIOSCO, href: "/kiosco", titulo: "Abrir el kiosco con Naturi", icono: MessageCircle,
    texto: "Asistente de voz y texto a pantalla completa para orientar a clientes en tienda." },
];

const punto: Record<Modulo["estado"], string> = {
  en_diseno: "bg-smn-gris-300",
  piloto: "bg-smn-naranja",
  activo: "bg-emerald-500",
  retirado: "bg-smn-gris-300",
};

const contenedor = { oculto: {}, visible: { transition: { staggerChildren: 0.06, delayChildren: 0.08 } } };
const elemento = { oculto: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] as const } } };

function BloqueHerramienta({ h, n, ancho }: { h: Herramienta; n: number; ancho?: boolean }) {
  const Icono = h.icono;
  return (
    <motion.div variants={elemento} className={`h-full ${ancho ? "md:col-span-2" : ""}`}>
      <Link
        href={h.href}
        className="group relative flex h-full min-h-[220px] flex-col overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie p-7 transition-colors duration-300 hover:border-[var(--resalte)] hover:bg-[var(--resalte)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-smn-naranja"
      >
        <Icono className="pointer-events-none absolute -right-10 -bottom-14 h-40 w-40 -rotate-12 stroke-[1.25] text-smn-gris-100 transition-all duration-500 group-hover:-rotate-6 group-hover:text-[color-mix(in_srgb,var(--resalte-tinta)_15%,transparent)]" />
        <div className="relative flex items-baseline justify-between gap-3 text-sm">
          <span className="font-mono text-smn-gris-500 transition-colors group-hover:text-[color-mix(in_srgb,var(--resalte-tinta)_70%,transparent)]">{String(n).padStart(2, "0")}</span>
          {h.piloto && <span className="text-smn-gris-500 transition-colors group-hover:text-[color-mix(in_srgb,var(--resalte-tinta)_70%,transparent)]">Piloto</span>}
        </div>
        <h3 className="relative mt-6 text-2xl leading-tight font-semibold tracking-[-0.02em] transition-colors group-hover:text-[var(--resalte-tinta)]">{h.titulo}</h3>
        <p className="relative mt-2 max-w-[42ch] flex-1 text-[15px] leading-relaxed text-smn-gris-700 transition-colors group-hover:text-[color-mix(in_srgb,var(--resalte-tinta)_80%,transparent)]">{h.texto}</p>
        <div className="relative mt-6 flex justify-end">
          <span className="grid h-10 w-10 place-items-center rounded-full border border-smn-gris-100 bg-superficie transition-all duration-300 group-hover:border-[var(--resalte-tinta)] group-hover:bg-[var(--resalte-tinta)] group-hover:text-[var(--resalte)]">
            <ArrowUpRight className="h-5 w-5 transition-transform duration-300 group-hover:rotate-45" />
          </span>
        </div>
      </Link>
    </motion.div>
  );
}

export default function PaginaModulo() {
  const { codigo } = useParams<{ codigo: string }>();
  const { yo, puede } = useSesion();
  const [pendientes, setPendientes] = useState<Pendiente[] | null>(null);
  const m = yo.modulos.find((x) => x.codigo === codigo);

  useEffect(() => {
    api<DatosInicio>("/api/nucleo/inicio")
      .then((d) => setPendientes(d.pendientes.filter((p) => p.modulo === codigo)))
      .catch(() => setPendientes([]));
  }, [codigo]);

  if (!m) return <p className="font-sobria text-[15px] text-smn-gris-500">Esta iniciativa no existe o no tienes acceso.</p>;
  const herramientas = HERRAMIENTAS.filter((h) => h.modulo === codigo && puede(h.permiso));

  return (
    <div className="font-sobria">
      {/* Encabezado */}
      <motion.header initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="relative">
        <IconoModulo icono={m.icono} className="pointer-events-none absolute -top-4 right-0 hidden h-36 w-36 -rotate-12 stroke-[1.1] text-smn-gris-100 md:block" />
        <p className="relative flex flex-wrap items-center gap-x-3 gap-y-1 text-[15px] text-smn-gris-500">
          {m.iniciativa && <span className="font-mono">{m.iniciativa}</span>}
          <span>{m.area}</span>
          <span className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${punto[m.estado]}`} />
            {estadoModulo[m.estado].texto}
          </span>
        </p>
        <h1 className="relative mt-2 max-w-3xl text-3xl leading-tight font-semibold tracking-tight sm:text-[40px]">{m.nombre}</h1>
        {m.descripcion && <p className="relative mt-3 max-w-2xl text-[17px] leading-relaxed text-smn-gris-700">{m.descripcion}</p>}
        <p className="relative mt-4 text-sm text-smn-gris-500">
          Responsable: <span className="text-tinta">{m.responsable ?? "por asignar"}</span>
          {m.tiene_portal_externo && " · Tiene portal para proveedores"}
        </p>
      </motion.header>

      {/* Por atender */}
      {pendientes && pendientes.length > 0 && (
        <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.05 }} className="mt-10">
          <h2 className="mb-3 text-lg font-semibold">Por atender</h2>
          <ul className="overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie">
            {pendientes.map((p) => (
              <li key={p.clave} className="border-b border-smn-gris-100 last:border-0">
                <Link href={p.href} className="group flex items-center gap-4 px-5 py-4 transition-colors hover:bg-smn-gris-50">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${p.urgente ? "bg-smn-naranja" : "bg-smn-gris-300"}`} />
                  <span className="min-w-12 shrink-0 text-right text-xl font-semibold tabular-nums">{p.cantidad.toLocaleString("es-MX")}</span>
                  <span className="min-w-0 flex-1 text-base">{p.texto}</span>
                  <span
                    className={`inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg px-3.5 text-sm font-medium transition-colors ${
                      p.urgente ? "bg-smn-naranja text-smn-negro" : "border border-smn-gris-100 group-hover:border-smn-gris-300"
                    }`}
                  >
                    {p.accion}
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </motion.section>
      )}

      {/* Herramientas */}
      <section className="mt-10">
        <h2 className="mb-4 text-lg font-semibold">Herramientas</h2>
        {herramientas.length === 0 ? (
          <div className="flex flex-col items-center rounded-2xl border border-dashed border-smn-gris-300 px-6 py-14 text-center">
            <Construction className="h-10 w-10 text-smn-naranja" />
            <p className="mt-4 text-lg font-semibold">En construcción</p>
            <p className="mt-1 max-w-md text-[15px] text-smn-gris-500">Aquí aparecerán las pantallas de {m.area} cuando estén listas o cuando tengas permiso para verlas.</p>
          </div>
        ) : (
          <motion.div className="grid gap-5 md:grid-cols-2" variants={contenedor} initial="oculto" animate="visible">
            {herramientas.map((h, i) => (
              <BloqueHerramienta key={h.href} h={h} n={i + 1} ancho={herramientas.length % 2 === 1 && i === herramientas.length - 1} />
            ))}
          </motion.div>
        )}
      </section>
    </div>
  );
}
