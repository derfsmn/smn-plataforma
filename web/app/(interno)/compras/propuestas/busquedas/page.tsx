"use client";
// Búsqueda de proveedores: lo que salió bien en el semáforo y no tiene quién nos lo surta. Quien busca proveedores toma
// cada una, registra a quién contactó y la cierra con o sin proveedor.

import { Imagen } from "@/componentes/imagen";
import Link from "next/link";
import { motion } from "motion/react";
import { ChevronRight, PackageSearch, Phone, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { InsigniaColor } from "@/componentes/semaforo-producto";
import { useSesion } from "@/componentes/sesion";
import { Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { PUERTA, RUTA, type Bandeja, type Vista } from "@/lib/busquedas";

const VISTAS: { valor: Vista; texto: string; conteo: keyof Bandeja["conteos"] | null }[] = [
  { valor: "abiertas", texto: "Abiertas", conteo: null },
  { valor: "mias", texto: "Las mías", conteo: "mias" },
  { valor: "cerradas", texto: "Cerradas", conteo: "cerradas" },
];

const fecha = (f: string) => fechaLocal(f, { dateStyle: "medium" });

/** Agrupa por estado en el orden en que llegan (la API ya las ordena). */
function grupos(lista: Bandeja["busquedas"]) {
  const m = new Map<string, [string, string, Bandeja["busquedas"]]>();
  for (const b of lista) {
    if (!m.has(b.estado)) m.set(b.estado, [b.estado, b.estado_texto, []]);
    m.get(b.estado)![2].push(b);
  }
  return [...m.values()];
}

export default function Busquedas() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [vista, setVista] = useState<Vista>("abiertas");
  const [datos, setDatos] = useState<Bandeja | null>(null);

  useEffect(() => {
    const v = new URLSearchParams(window.location.search).get("vista");
    if (v === "mias" || v === "cerradas") setVista(v);
  }, []);

  useEffect(() => {
    setDatos(null);
    api<Bandeja>(`${RUTA}?vista=${vista}`).then(setDatos).catch((e) => avisar(mensajeDe(e), "info"));
  }, [vista, avisar]);

  const cambiar = (v: Vista) => {
    setVista(v);
    window.history.replaceState(null, "", v === "abiertas" ? "/compras/propuestas/busquedas" : `/compras/propuestas/busquedas?vista=${v}`);
  };

  const colores = datos?.colores_automaticos ?? [];
  const regla = colores.length === 0
    ? "Hoy no se abren solas: Compras las pide desde cada producto."
    : `Llegan solas cuando una oportunidad (por tendencia, de lo más vendido o capturada por Compras) sale ${colores.join(" o ")} en el semáforo y no tiene proveedor; Compras también las pide desde cada producto.`;

  return (
    <>
      <Entrada className="mb-5">
        <p className="max-w-3xl text-smn-gris-500">
          {regla} {puede("compras.busquedas.atender") ? "Toma una, registra a quién contactas y ciérrala con el proveedor que encontraste." : "Las atienden quienes buscan proveedores."}
        </p>
        {datos && (
          <p className="mt-2 text-sm text-smn-gris-700">
            <b className="text-tinta">{datos.conteos.sin_tomar}</b> sin responsable · <b className="text-tinta">{datos.conteos.buscando}</b> buscando ·{" "}
            <b className="text-tinta">{datos.conteos.encontrado}</b> con proveedor encontrado
          </p>
        )}
      </Entrada>

      <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="Qué búsquedas ver">
        {VISTAS.filter((v) => v.valor !== "mias" || puede("compras.busquedas.atender")).map((v) => (
          <button
            key={v.valor}
            role="tab"
            aria-selected={vista === v.valor}
            onClick={() => cambiar(v.valor)}
            className={`rounded-xl px-3 py-1.5 text-sm font-semibold transition-colors ${vista === v.valor ? "bg-tinta text-superficie" : "bg-smn-gris-100 text-smn-gris-700 hover:text-tinta"}`}
          >
            {v.texto}
            {v.conteo && datos ? <span className="ml-1.5 tabular-nums opacity-70">{datos.conteos[v.conteo]}</span> : null}
          </button>
        ))}
      </div>

      {datos === null ? (
        <div className="space-y-2">
          <Esqueleto className="h-20" />
          <Esqueleto className="h-20" />
          <Esqueleto className="h-20" />
        </div>
      ) : datos.busquedas.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-smn-gris-500">
          <PackageSearch className="mx-auto mb-3 h-8 w-8" aria-hidden />
          {vista === "abiertas" ? (
            <>
              No hay búsquedas abiertas. Llegan aquí desde{" "}
              <Link href="/compras/productos/oportunidades" className="underline underline-offset-2 hover:text-tinta">Buscar oportunidades</Link> y el radar de productos.
            </>
          ) : vista === "mias" ? "No tienes búsquedas abiertas." : "Todavía no se ha cerrado ninguna."}
        </div>
      ) : (
        // Agrupadas por estado: así «Sin responsable» y «0 proveedores contactados» no se repiten en cada renglón
        <div className="space-y-6">
          {grupos(datos.busquedas).map(([estado, texto, lista]) => (
        <section key={estado}>
          <h2 className="mb-2 text-[13px] font-semibold tracking-wide text-smn-gris-500 uppercase">
            {texto} <span className="tabular-nums">({lista.length})</span>
          </h2>
        <ul className="space-y-2">
          {lista.map((b, i) => (
            <motion.li key={b.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.3) }}>
              <Link
                href={`/compras/propuestas/busquedas/${b.id}`}
                className={`group flex items-center gap-4 rounded-2xl border bg-superficie p-4 transition hover:border-smn-naranja ${b.estado === "sin_tomar" ? "border-smn-naranja/60" : "border-smn-gris-100"}`}
              >
                <div className="hidden h-14 w-14 shrink-0 overflow-hidden rounded-xl bg-smn-gris-50 sm:block">
                  {b.imagen ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <Imagen src={b.imagen} alt="" className="h-full w-full object-contain" loading="lazy" referrerPolicy="no-referrer" />
                  ) : (
                    <PackageSearch className="m-4 h-6 w-6 text-smn-gris-300" aria-hidden />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold">{b.nombre}</p>
                    {b.puertas.map((p) => (
                      <Insignia key={p} className="bg-smn-gris-100 text-smn-gris-700">{PUERTA[p] ?? p}</Insignia>
                    ))}
                  </div>
                  <p className="mt-0.5 text-sm text-smn-gris-500">
                    {[b.marca, b.departamento].filter(Boolean).join(" · ") || "Sin marca ni departamento"}
                    {" · "}
                    {b.origen === "automatica" ? "abierta sola" : "pedida por Compras"} el {fecha(b.creada_en)}
                  </p>
                  {(b.responsable || b.contactos > 0 || b.proveedor) && (
                    <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[13px] text-smn-gris-700">
                      {b.responsable && (
                        <span className="inline-flex items-center gap-1">
                          <UserRound className="h-3.5 w-3.5" aria-hidden /> {b.responsable.nombre}
                        </span>
                      )}
                      {b.contactos > 0 && (
                        <span className="inline-flex items-center gap-1">
                          <Phone className="h-3.5 w-3.5" aria-hidden /> {b.contactos} {b.contactos === 1 ? "proveedor contactado" : "proveedores contactados"}
                        </span>
                      )}
                      {b.proveedor && <span className="font-medium text-tinta">Proveedor: {b.proveedor}</span>}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <InsigniaColor color={b.color} />
                  {b.puntaje !== null && <span className="text-sm tabular-nums text-smn-gris-500">{b.puntaje} de 100</span>}
                </div>
                <ChevronRight className="h-5 w-5 shrink-0 text-smn-gris-300 transition group-hover:translate-x-0.5 group-hover:text-tinta" aria-hidden />
              </Link>
            </motion.li>
          ))}
        </ul>
        </section>
          ))}
        </div>
      )}
    </>
  );
}
