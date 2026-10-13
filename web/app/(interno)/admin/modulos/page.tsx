"use client";

import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { api, estadoModulo, mensajeDe, type EstadoModulo, type Modulo } from "@/lib/api";
import { IconoModulo } from "@/componentes/icono-modulo";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Encabezado, Entrada, Esqueleto } from "@/componentes/ui";

const ciclo: EstadoModulo[] = ["en_diseno", "piloto", "activo", "retirado"];

export default function AdminModulos() {
  const avisar = useAvisos();
  const { recargar } = useSesion();
  const [modulos, setModulos] = useState<Modulo[] | null>(null);

  useEffect(() => {
    api<Modulo[]>("/api/nucleo/modulos").then(setModulos).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);

  const cambiar = async (codigo: string, estado: EstadoModulo) => {
    const anterior = modulos;
    setModulos((ms) => ms?.map((m) => (m.codigo === codigo ? { ...m, estado } : m)) ?? null);
    try {
      await api(`/api/nucleo/modulos/${codigo}`, { metodo: "PATCH", cuerpo: { estado } });
      avisar(`Módulo ${codigo}: ${estadoModulo[estado].texto}`, "info");
      recargar();
    } catch (e) {
      setModulos(anterior);
      avisar(mensajeDe(e), "info");
    }
  };

  return (
    <>
      <Encabezado titulo="Módulos" descripcion="Cada iniciativa se registra aquí. Los usuarios solo ven los módulos en piloto o activos donde tienen un rol." />
      {!modulos ? (
        <Esqueleto className="h-60" />
      ) : (
        <div className="space-y-4">
          {modulos.map((m, i) => (
            <Entrada key={m.codigo} retraso={i * 0.08} className="rounded-3xl border border-smn-gris-100 bg-superficie p-6">
              <div className="flex flex-wrap items-center gap-4">
                <span className="grid h-12 w-12 place-items-center rounded-2xl bg-smn-negro text-smn-naranja dark:bg-smn-gris-100"><IconoModulo icono={m.icono} /></span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-bold tracking-wide text-smn-gris-500 uppercase">
                    {m.area} · {m.iniciativa ?? "Por asignar"} · esquema <code>{m.codigo}</code>
                  </p>
                  <p className="text-lg font-extrabold">{m.nombre}</p>
                  <p className="text-sm text-smn-gris-500">Responsable: {m.responsable ?? "Por asignar"}</p>
                </div>
              </div>
              <div className="mt-5 grid grid-cols-2 gap-1 rounded-xl bg-smn-gris-100 p-1 sm:grid-cols-4">
                {ciclo.map((e) => (
                  <button key={e} onClick={() => m.estado !== e && cambiar(m.codigo, e)} className={`relative rounded-lg py-2 text-sm font-bold ${m.estado === e ? "" : "text-smn-gris-500"}`}>
                    {m.estado === e && <motion.span layoutId={`estado-${m.codigo}`} className="absolute inset-0 rounded-lg bg-superficie shadow-sm" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
                    <span className="relative">{estadoModulo[e].texto}</span>
                  </button>
                ))}
              </div>
            </Entrada>
          ))}
          <p className="text-xs text-smn-gris-500">Para dar de alta un módulo nuevo se sigue el contrato descrito en AGENTS.md (esquema SQL, permisos, rutas e indicadores).</p>
        </div>
      )}
    </>
  );
}
