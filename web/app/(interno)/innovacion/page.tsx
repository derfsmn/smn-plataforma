"use client";
// Inicio de Innovación Vidanat: lo que espera de mí (fuentes por revisar, dictámenes, reglas por publicar,
// decisiones del Filtro), los expedientes que se movieron y una búsqueda rápida en la base de conocimiento.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, BookOpen, Cpu, FolderKanban, Gavel, ScanText, Search, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Encabezado, Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, haceCuanto, mensajeDe } from "@/lib/api";
import { ETAPAS, P, RUTA, TIPOS, fecha, type Resumen } from "@/lib/innovacion";
import { AREA, MenuModulo, SinAcceso, TARJETA, Vacio } from "./comunes";

export default function InicioInnovacion() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const router = useRouter();
  const [r, setR] = useState<Resumen | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    if (puede(P.ver)) api<Resumen>(`${RUTA}/resumen`).then(setR).catch((e) => avisar(mensajeDe(e), "info"));
  }, [puede, avisar]);

  if (!puede(P.ver)) return <SinAcceso />;
  const etapasActivas = ["investigacion", "filtro", "desarrollo", "salida_comercial", "validacion"];
  return (
    <>
      <Encabezado
        titulo="Innovación Vidanat"
        descripcion="Investigación, base de conocimiento y reglas para los productos nuevos de marca propia. Todo lo que se dice lleva su fuente y versión."
      />
      <MenuModulo />
      {!r ? (
        <Esqueleto className="h-64" />
      ) : (
        <div className="grid gap-5">
          <Entrada className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-smn-gris-500">
            <span className="inline-flex items-center gap-1.5"><BookOpen className="h-4 w-4" /> {r.fuentes.revisado ?? 0} fuentes revisadas · {r.fuentes.pendiente ?? 0} pendientes</span>
            <span className="inline-flex items-center gap-1.5"><Cpu className="h-4 w-4" /> {r.ia_local ? "IA local prendida" : "IA local apagada: se busca por palabras"}</span>
            <span className="inline-flex items-center gap-1.5"><ScanText className="h-4 w-4" /> {r.ocr ? "Lectura de escaneados lista" : "Sin lector de escaneados (OCR)"}</span>
            {r.trabajos_con_error > 0 && (
              <span className="inline-flex items-center gap-1.5 text-amber-700 dark:text-amber-400"><AlertTriangle className="h-4 w-4" /> {r.trabajos_con_error} lecturas con error</span>
            )}
          </Entrada>

          <form
            className={TARJETA}
            onSubmit={(e) => {
              e.preventDefault();
              if (q.trim().length >= 2) router.push(`/innovacion/fuentes?q=${encodeURIComponent(q.trim())}`);
            }}
          >
            <label htmlFor="buscar" className="text-sm font-semibold text-smn-gris-700">Buscar en la base de conocimiento</label>
            <div className="mt-1.5 flex gap-2">
              <input id="buscar" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ingrediente, forma química, estudio, norma…" className={AREA} />
              <button type="submit" aria-label="Buscar" className="rounded-lg bg-[var(--resalte)] px-4 text-[var(--resalte-tinta)]"><Search className="h-4 w-4" /></button>
            </div>
          </form>

          <div className="grid gap-5 lg:grid-cols-2">
            {r.por_decidir.length > 0 && (
              <Bandeja titulo="Esperan decisión del Filtro" icono={Gavel}>
                {r.por_decidir.map((x) => (
                  <Fila key={x.folio} href={`/innovacion/expedientes/${x.folio}?vista=filtro`} titulo={x.nombre} detalle={x.folio} />
                ))}
              </Bandeja>
            )}
            {r.dictamenes.length > 0 && (
              <Bandeja titulo="Reglas que te toca dictaminar" icono={ShieldCheck}>
                {r.dictamenes.map((x) => (
                  <Fila key={x.revision_id} href={`/innovacion/revisiones/${x.revision_id}`} titulo={`${x.regla} · ${x.proposito}`}
                    detalle={`${x.folio} ${x.expediente}${x.vence_en ? ` · vence ${fecha(x.vence_en)}` : ""}`} />
                ))}
              </Bandeja>
            )}
            {r.por_revisar.length > 0 && (
              <Bandeja titulo="Fuentes por revisar" icono={BookOpen}>
                {r.por_revisar.map((x) => (
                  <Fila key={`${x.recurso_id}-${x.version}`} href={`/innovacion/fuentes/${x.recurso_id}`} titulo={x.titulo}
                    detalle={`${TIPOS[x.tipo] ?? x.tipo} · versión ${x.version} · ${haceCuanto(x.desde)}`} />
                ))}
              </Bandeja>
            )}
            {r.por_publicar.length > 0 && (
              <Bandeja titulo="Reglas por publicar" icono={ShieldCheck}>
                {r.por_publicar.map((x) => (
                  <Fila key={`${x.regla_id}-${x.version}`} href={`/innovacion/reglas/${x.regla_id}`} titulo={`${x.codigo} v${x.version}`} detalle={x.proposito} />
                ))}
              </Bandeja>
            )}
          </div>

          {puede(P.expVer) && (
            <Bandeja titulo="Expedientes" icono={FolderKanban} accion={<Link href="/innovacion/expedientes" className="text-sm font-semibold text-smn-naranja">Ver todos</Link>}>
              <div className="mb-3 flex flex-wrap gap-2">
                {etapasActivas.map((e) => (
                  <Insignia key={e} className="bg-smn-gris-100 text-smn-gris-700">{ETAPAS[e]}: {r.etapas[e] ?? 0}</Insignia>
                ))}
              </div>
              {r.expedientes.length === 0 ? (
                <Vacio>Todavía no hay expedientes. Crea el primero en Expedientes.</Vacio>
              ) : (
                r.expedientes.map((x) => (
                  <Fila key={x.folio} href={`/innovacion/expedientes/${x.folio}`} titulo={x.nombre}
                    detalle={`${x.folio} · ${ETAPAS[x.etapa] ?? x.etapa} · ${haceCuanto(x.actualizado_en)}`} />
                ))
              )}
            </Bandeja>
          )}
          {Object.values(r.reglas).reduce((a, b) => a + b, 0) === 0 && (
            <p className="text-sm text-smn-gris-500">
              Aún no hay reglas publicadas: los expedientes se trabajan igual y la evaluación dirá «sin reglas que apliquen» hasta que se publiquen.
            </p>
          )}
        </div>
      )}
    </>
  );
}

function Bandeja({ titulo, icono: Icono, accion, children }: { titulo: string; icono: typeof BookOpen; accion?: React.ReactNode; children: React.ReactNode }) {
  return (
    <Entrada className={TARJETA}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="inline-flex items-center gap-2 text-[17px] font-semibold"><Icono className="h-4 w-4 text-smn-naranja" /> {titulo}</h2>
        {accion}
      </div>
      <div className="divide-y divide-smn-gris-100">{children}</div>
    </Entrada>
  );
}

function Fila({ href, titulo, detalle }: { href: string; titulo: string; detalle: string }) {
  return (
    <Link href={href} className="block py-2.5 hover:text-smn-naranja">
      <span className="block text-[15px] font-medium">{titulo}</span>
      <span className="block text-[13px] text-smn-gris-500">{detalle}</span>
    </Link>
  );
}
