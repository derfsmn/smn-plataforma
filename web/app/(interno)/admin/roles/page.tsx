"use client";

import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { api, mensajeDe, type Permiso, type Rol } from "@/lib/api";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Encabezado, Entrada, Esqueleto, Insignia } from "@/componentes/ui";

function Interruptor({ encendido, cambiar, etiqueta, bloqueado }: { encendido: boolean; cambiar: () => void; etiqueta: string; bloqueado?: boolean }) {
  return (
    <button
      role="switch"
      aria-checked={encendido}
      aria-label={etiqueta}
      onClick={cambiar}
      disabled={bloqueado}
      title={bloqueado ? "El administrador siempre conserva este permiso" : undefined}
      className={`flex h-6 w-11 shrink-0 items-center rounded-full p-0.5 transition-colors disabled:opacity-50 ${encendido ? "justify-end bg-smn-naranja" : "justify-start bg-smn-gris-300"}`}
    >
      <motion.span layout transition={{ type: "spring", stiffness: 600, damping: 35 }} className="h-5 w-5 rounded-full bg-superficie shadow" />
    </button>
  );
}

const FIJOS_ADMIN = ["nucleo.usuarios.administrar", "nucleo.roles.administrar"];

export default function AdminRoles() {
  const avisar = useAvisos();
  const { recargar } = useSesion();
  const [roles, setRoles] = useState<Rol[] | null>(null);
  const [permisos, setPermisos] = useState<Permiso[]>([]);
  const [elegido, setElegido] = useState("admin");

  useEffect(() => {
    api<Rol[]>("/api/nucleo/roles").then(setRoles).catch((e) => avisar(mensajeDe(e), "info"));
    api<Permiso[]>("/api/nucleo/permisos").then(setPermisos).catch(() => {});
  }, [avisar]);

  if (!roles) return <><Encabezado titulo="Roles y permisos" /><Esqueleto className="h-96" /></>;
  const rol = roles.find((r) => r.codigo === elegido) ?? roles[0];
  const grupos = [...new Set(permisos.map((p) => p.modulo))];

  const alternar = async (codigo: string) => {
    const tiene = rol.permisos.includes(codigo);
    const nuevos = tiene ? rol.permisos.filter((p) => p !== codigo) : [...rol.permisos, codigo];
    const anterior = roles;
    setRoles(roles.map((r) => (r.codigo === rol.codigo ? { ...r, permisos: nuevos } : r))); // optimista
    try {
      const guardado = await api<Rol>(`/api/nucleo/roles/${rol.codigo}/permisos`, { metodo: "PUT", cuerpo: { permisos: nuevos } });
      setRoles((rs) => rs?.map((r) => (r.codigo === guardado.codigo ? guardado : r)) ?? null);
      avisar(`${tiene ? "Quitado" : "Agregado"}: ${codigo}`, "info");
      recargar(); // por si cambió algo de lo que puedo ver yo
    } catch (e) {
      setRoles(anterior);
      avisar(mensajeDe(e), "info");
    }
  };

  return (
    <>
      <Encabezado titulo="Roles y permisos" descripcion="Cada permiso se escribe como módulo.entidad.acción. Los cambios se guardan al momento." />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.6fr]">
        <Entrada className="space-y-2">
          {roles.map((r) => (
            <button
              key={r.codigo}
              onClick={() => setElegido(r.codigo)}
              className={`relative w-full rounded-2xl border p-4 text-left transition-colors ${rol.codigo === r.codigo ? "border-transparent" : "border-smn-gris-100 bg-superficie hover:border-smn-gris-300"}`}
            >
              {rol.codigo === r.codigo && <motion.span layoutId="rol-elegido" className="absolute inset-0 rounded-2xl bg-smn-negro dark:ring-1 dark:ring-white/10" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
              <span className="relative flex items-center justify-between gap-2">
                <span className={`font-bold ${rol.codigo === r.codigo ? "text-white" : ""}`}>{r.nombre}</span>
                <Insignia className={r.para === "externo" ? "bg-smn-naranja text-smn-negro" : rol.codigo === r.codigo ? "bg-white/10 text-white" : "bg-smn-gris-100 text-smn-gris-700"}>{r.para}</Insignia>
              </span>
              <span className={`relative mt-1 block text-sm ${rol.codigo === r.codigo ? "text-white/60" : "text-smn-gris-500"}`}>
                {r.descripcion} · {r.permisos.length} {r.permisos.length === 1 ? "permiso" : "permisos"}
              </span>
            </button>
          ))}
        </Entrada>

        <Entrada retraso={0.1} className="rounded-3xl border border-smn-gris-100 bg-superficie p-6">
          <h2 className="text-lg font-extrabold">{rol.nombre}</h2>
          {grupos.map((g) => (
            <div key={g} className="mt-5">
              <p className="mb-2 text-xs font-bold tracking-widest text-smn-gris-500 uppercase">{g}</p>
              <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100">
                {permisos.filter((p) => p.modulo === g).map((p) => (
                  <li key={p.codigo} className="flex items-center justify-between gap-4 px-4 py-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold">{p.descripcion}</p>
                      <code className="text-xs break-all text-smn-gris-500">{p.codigo}</code>
                    </div>
                    <Interruptor
                      encendido={rol.permisos.includes(p.codigo)}
                      cambiar={() => alternar(p.codigo)}
                      etiqueta={p.descripcion}
                      bloqueado={rol.codigo === "admin" && FIJOS_ADMIN.includes(p.codigo)}
                    />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </Entrada>
      </div>
    </>
  );
}
