"use client";
// Portal de proveedores (externo): proponer productos nuevos y ver el estado de cada propuesta. Solo ve las de su empresa.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import { ChevronRight, FilePlus2, Loader2, PackageSearch } from "lucide-react";
import { useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, haceCuanto, mensajeDe } from "@/lib/api";
import { estiloEstado, RUTA, type Propuesta, type PropuestaBreve } from "@/lib/propuestas";

export default function Portal() {
  const { yo } = useSesion();
  const avisar = useAvisos();
  const router = useRouter();
  const u = yo.usuario;
  const [propuestas, setPropuestas] = useState<PropuestaBreve[] | null>(null);
  const [creando, setCreando] = useState(false);

  useEffect(() => {
    api<PropuestaBreve[]>(`${RUTA}/mias`).then(setPropuestas).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);

  const nueva = async () => {
    setCreando(true);
    try {
      const p = await api<Propuesta>(RUTA, { metodo: "POST" });
      router.push(`/proveedores/propuesta/${p.id}`);
    } catch (e) {
      avisar(mensajeDe(e), "info");
      setCreando(false);
    }
  };

  const pendientes = propuestas?.filter((p) => p.estado === "borrador" || p.estado === "devuelta").length ?? 0;

  return (
    <>
      <Entrada>
        <p className="text-sm font-medium text-naranja-tinta">Bienvenido</p>
        <h1 className="mt-1 text-3xl leading-tight font-semibold tracking-tight sm:text-[34px]">{u.empresa ?? u.nombre}</h1>
        <p className="mt-1 text-sm text-smn-gris-500">{u.nombre} · {u.correo}</p>
        <p className="mt-3 text-smn-gris-500">Desde aquí propones productos nuevos a Súper Naturista y das seguimiento a cada propuesta con su folio.</p>
      </Entrada>

      <Entrada retraso={0.1} className="mt-8 grid gap-4 sm:grid-cols-2">
        <motion.button
          whileHover={{ y: -4 }}
          onClick={nueva}
          disabled={creando}
          className="group flex flex-col items-start rounded-2xl bg-smn-naranja p-6 text-left text-smn-negro shadow-sm shadow-smn-naranja/20 disabled:opacity-70"
        >
          {creando ? <Loader2 className="h-8 w-8 animate-spin" /> : <FilePlus2 className="h-8 w-8 transition-transform group-hover:scale-110" />}
          <span className="mt-6 text-xl font-semibold">Proponer producto nuevo</span>
          <span className="mt-1 text-sm text-smn-negro/70">Un producto por propuesta, con todas sus presentaciones. Se guarda solo mientras escribes.</span>
        </motion.button>
        <div className="flex flex-col items-start rounded-2xl border border-smn-gris-100 bg-superficie p-6">
          <PackageSearch className="h-8 w-8 text-smn-gris-500" />
          <span className="mt-6 text-xl font-semibold">Mis propuestas</span>
          <span className="mt-1 text-sm text-smn-gris-500">
            {propuestas === null
              ? "Cargando…"
              : propuestas.length === 0
                ? "Aún no tienes propuestas."
                : `${propuestas.length} en total${pendientes ? `, ${pendientes} por completar` : ""}.`}
          </span>
        </div>
      </Entrada>

      <Entrada retraso={0.15} className="mt-8">
        <h2 className="mb-3 text-lg font-semibold">Mis propuestas</h2>
        {propuestas === null ? (
          <div className="space-y-2">
            <Esqueleto className="h-20" />
            <Esqueleto className="h-20" />
          </div>
        ) : propuestas.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-smn-gris-300 p-8 text-center text-smn-gris-500">
            Cuando propongas un producto aparecerá aquí con su folio y su estado.
          </p>
        ) : (
          <ul className="space-y-2">
            {propuestas.map((p, i) => (
              <motion.li key={p.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.3) }}>
                <Link
                  href={`/proveedores/propuesta/${p.id}`}
                  className="group flex items-center gap-4 rounded-2xl border border-smn-gris-100 bg-superficie p-4 transition hover:border-smn-naranja"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">{p.producto ?? "Producto sin nombre"}</p>
                    <p className="text-sm text-smn-gris-500">
                      {p.folio ?? "Sin enviar"} · {p.presentaciones} {p.presentaciones === 1 ? "presentación" : "presentaciones"} · {haceCuanto(p.actualizada_en)}
                    </p>
                  </div>
                  <Insignia className={estiloEstado[p.estado]}>{p.estado_texto}</Insignia>
                  <ChevronRight className="h-5 w-5 shrink-0 text-smn-gris-500 transition group-hover:translate-x-0.5 group-hover:text-smn-naranja" />
                </Link>
              </motion.li>
            ))}
          </ul>
        )}
      </Entrada>
    </>
  );
}
