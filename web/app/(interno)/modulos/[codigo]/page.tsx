"use client";
// Pantalla de cada iniciativa con el diseño sobrio: encabezado, lo que está por atender en esta área (pendientes
// reales según permisos) y sus herramientas en bloques, igual que el Inicio.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { motion } from "motion/react";
import { ArrowRight, ArrowUpRight, BookOpen, Construction, FlaskConical, FolderKanban, Search, Telescope, FileSpreadsheet, Gauge, MessageCircle, PackagePlus, Radar, Tags } from "lucide-react";
import { useEffect, useState } from "react";
import { api, estadoModulo, type Modulo } from "@/lib/api";
import type { DatosInicio, Pendiente } from "@/lib/inicio";
import { PERMISO_KIOSCO } from "@/lib/kiosco";
import { PERMISOS_BUSCADOR } from "@/lib/buscador";
import { PERMISO_CONSULTAR as PERMISO_CONSULTAR_METODOS } from "@/lib/metodos";
import { useSesion } from "@/componentes/sesion";
import { IconoModulo } from "@/componentes/icono-modulo";

type Herramienta = { modulo: string; permiso: string; href: string; titulo: string; texto: string; icono: typeof Radar; piloto?: boolean };

const HERRAMIENTAS: Herramienta[] = [
  // Compras: en el orden en que se usan en el día (propuesta de diseño 22 nov 2026)
  { modulo: "compras", permiso: "compras.precios.ver", href: "/compras/precios", titulo: "Radar de precios", icono: Tags,
    texto: "Dónde estamos más caros que Walmart, Chedraui, San Pablo, Soriana y el resto de internet, y qué conviene hacer." },
  { modulo: "compras", permiso: "compras.productos.ver", href: "/compras/productos", titulo: "Radar de productos", icono: Gauge,
    texto: "El semáforo de cada producto nuevo, con la razón y los números que lo mueven." },
  { modulo: "compras", permiso: "compras.propuestas.ver", href: "/compras/propuestas", titulo: "Productos nuevos", icono: PackagePlus,
    texto: "Propuestas del portal de proveedores, el comité de producto nuevo y la búsqueda de proveedor." },
  { modulo: "compras", permiso: "compras.radar.ver", href: "/compras/radar", titulo: "Radar de tendencias", icono: Radar,
    texto: "Lo que se mueve en suplementos y naturistas cada mañana, con su fuente." },
  { modulo: "compras", permiso: "compras.conocimiento.ver", href: "/compras/conocimiento", titulo: "Base de conocimiento", icono: BookOpen,
    texto: "Las políticas, reglas y pesos con que el semáforo califica cada producto." },
  { modulo: "contraloria", permiso: "contraloria.diot.ver", href: "/contraloria/diot", titulo: "Proceso de la DIOT", icono: FileSpreadsheet, piloto: true,
    texto: "Sube los reportes del mes, procesa, revisa las excepciones y descarga el TXT para el SAT con su evidencia." },
  { modulo: "contraloria", permiso: "contraloria.diot.ver", href: "/contraloria/conocimiento", titulo: "Base de conocimiento fiscal", icono: BookOpen,
    texto: "Los criterios con que se arma la DIOT, los catálogos del SAT y los documentos de soporte. Fiscal los aprueba y los prueba con un mes antes de usarlos." },
  { modulo: "metodos", permiso: PERMISO_CONSULTAR_METODOS, href: "/metodos", titulo: "Preguntar a los manuales", icono: BookOpen, piloto: true,
    texto: "Pregunta cómo se hace algo y recibe la respuesta con la cita del manual vigente. Las áreas cargan sus manuales y la IA local les ayuda a redactarlos." },
  { modulo: "innovacion", permiso: "innovacion.recurso.ver", href: "/innovacion", titulo: "Inicio de Innovación Vidanat", icono: FlaskConical, piloto: true,
    texto: "Lo que espera de ti: fuentes por revisar, dictámenes, reglas por publicar y expedientes que esperan el Filtro." },
  { modulo: "innovacion", permiso: "innovacion.recurso.ver", href: "/innovacion/fuentes", titulo: "Base de conocimiento", icono: Search, piloto: true,
    texto: "Artículos, ensayos, normas y fichas técnicas con su versión, revisadas por el rol que toca. Búsqueda por palabras y por significado." },
  { modulo: "innovacion", permiso: "innovacion.expediente.ver", href: "/innovacion/expedientes", titulo: "Expedientes", icono: FolderKanban, piloto: true,
    texto: "Un folio por producto nuevo: ficha, fórmula cifrada, evidencia citada, reglas y la decisión del Filtro." },
  { modulo: "innovacion", permiso: "innovacion.investigacion.correr", href: "/innovacion/investigar", titulo: "Investigar en internet", icono: Telescope, piloto: true,
    texto: "PubMed, Europe PMC, ClinicalTrials.gov, OpenAlex y Crossref: busca, lee lo abierto y redacta un informe con citas." },
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
        className="group relative flex h-full min-h-[184px] flex-col overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie p-6 transition-colors duration-300 hover:border-[var(--resalte)] hover:bg-[var(--resalte)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-smn-naranja"
      >
        <Icono className="pointer-events-none absolute -right-10 -bottom-14 h-40 w-40 -rotate-12 stroke-[1.25] text-smn-gris-100 transition-all duration-500 group-hover:-rotate-6 group-hover:text-[color-mix(in_srgb,var(--resalte-tinta)_15%,transparent)]" />
        <div className="relative flex items-baseline justify-between gap-3 text-sm">
          <span className="font-mono text-smn-gris-500 transition-colors group-hover:text-[color-mix(in_srgb,var(--resalte-tinta)_70%,transparent)]">{String(n).padStart(2, "0")}</span>
          {h.piloto && <span className="text-smn-gris-500 transition-colors group-hover:text-[color-mix(in_srgb,var(--resalte-tinta)_70%,transparent)]">Piloto</span>}
        </div>
        <h3 className="relative mt-4 text-2xl leading-tight font-semibold tracking-[-0.02em] transition-colors group-hover:text-[var(--resalte-tinta)]">{h.titulo}</h3>
        <p className="relative mt-2 max-w-[42ch] flex-1 text-[15px] leading-relaxed text-smn-gris-700 transition-colors group-hover:text-[color-mix(in_srgb,var(--resalte-tinta)_80%,transparent)]">{h.texto}</p>
        <div className="relative mt-4 flex justify-end">
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

      {/* Buscador de productos (22 nov 2026): lo primero que se ve en Compras */}
      {codigo === "compras" && PERMISOS_BUSCADOR.some((p) => puede(p)) && <BuscadorCompras />}

      {/* Por atender */}
      {pendientes && pendientes.length > 0 && (
        <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.05 }} className="mt-10">
          <h2 className="mb-3 text-lg font-semibold">Por atender</h2>
          <ul className="overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie">
            {pendientes.map((p) => (
              <li key={p.clave} className="border-b border-smn-gris-100 last:border-0">
                <Link href={p.href} className="group flex items-center gap-3 px-4 py-4 transition-colors hover:bg-smn-gris-50 sm:gap-4 sm:px-5">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${p.urgente ? "bg-smn-naranja" : "bg-smn-gris-300"}`} />
                  <span className="min-w-10 shrink-0 text-right text-xl font-semibold tabular-nums sm:min-w-12">{p.cantidad.toLocaleString("es-MX")}</span>
                  <span className="min-w-0 flex-1 text-[15px] leading-snug sm:text-base">{p.texto}</span>
                  <span
                    className={`inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg px-3.5 text-sm font-medium transition-colors ${
                      p.urgente ? "bg-smn-naranja text-smn-negro" : "border border-smn-gris-100 group-hover:border-smn-gris-300"
                    }`}
                  >
                    <span className="hidden sm:inline">{p.accion}</span>
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

function BuscadorCompras() {
  const router = useRouter();
  const [q, setQ] = useState("");
  return (
    <motion.form
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.03 }}
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        router.push(q.trim() ? `/compras/buscar?q=${encodeURIComponent(q.trim())}` : "/compras/buscar");
      }}
      className="relative mt-8 max-w-2xl"
    >
      <Search className="pointer-events-none absolute top-1/2 left-4 h-5 w-5 -translate-y-1/2 text-smn-gris-500" />
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Busca un producto: nombre, SKU, código de barras o marca"
        aria-label="Buscar productos"
        enterKeyHint="search"
        className="h-14 w-full rounded-2xl border border-smn-gris-300 bg-superficie pr-28 pl-12 text-[16px] outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
      />
      <button type="submit" className="absolute top-1/2 right-2 h-10 -translate-y-1/2 rounded-xl bg-tinta px-4 text-sm font-semibold text-superficie hover:opacity-90">
        Buscar
      </button>
    </motion.form>
  );
}
