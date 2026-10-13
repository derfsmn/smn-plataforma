"use client";

import { useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { iniciales } from "@/componentes/marco-interno";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { MedidorContrasena } from "@/componentes/medidor-contrasena";
import { TarjetasTema } from "@/componentes/selector-tema";
import { Boton, Campo, Encabezado, Entrada } from "@/componentes/ui";

export default function Perfil() {
  const avisar = useAvisos();
  const { yo, recargar } = useSesion();
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [confirmar, setConfirmar] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const u = yo.usuario;

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!actual || nueva.length < 10 || nueva !== confirmar) return;
    setCargando(true);
    setError(null);
    try {
      await api("/api/auth/cambiar-contrasena", { cuerpo: { actual, nueva } });
      setActual(""); setNueva(""); setConfirmar("");
      avisar("Contraseña actualizada. Se cerraron tus otras sesiones.");
      recargar();
    } catch (err) {
      setError(mensajeDe(err));
    }
    setCargando(false);
  };

  const filas: [string, string][] = [
    ["Tipo de cuenta", u.tipo === "interno" ? "Colaborador SMN" : "Proveedor"],
    ["Área", u.area ?? "—"],
    ["Rol", u.roles.map((r) => r.nombre).join(", ") || "—"],
    ["Inicio de sesión", "Correo y contraseña"],
  ];

  return (
    <>
      <Encabezado titulo="Mi perfil" descripcion="Tus datos, tu contraseña y la apariencia de la plataforma." />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <Entrada className="rounded-3xl border border-smn-gris-100 bg-superficie p-6">
          <div className="flex items-center gap-4">
            <span className="grid h-16 w-16 shrink-0 place-items-center rounded-2xl bg-smn-naranja text-xl font-extrabold text-smn-negro">{iniciales(u.nombre)}</span>
            <div className="min-w-0">
              <p className="text-lg font-extrabold">{u.nombre}</p>
              <p className="truncate text-sm text-smn-gris-500">{u.correo}</p>
            </div>
          </div>
          <dl className="mt-6 space-y-3 text-sm">
            {filas.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4">
                <dt className="text-smn-gris-500">{k}</dt>
                <dd className="text-right font-bold">{v}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-6 border-t border-smn-gris-100 pt-5">
            <h2 className="mb-3 font-extrabold">Apariencia</h2>
            <TarjetasTema />
          </div>
        </Entrada>

        <Entrada retraso={0.1} className="rounded-3xl border border-smn-gris-100 bg-superficie p-6">
          <h2 className="text-lg font-extrabold">Cambiar contraseña</h2>
          <form onSubmit={guardar} className="mt-4 space-y-4">
            <Campo etiqueta="Contraseña actual" type="password" value={actual} onChange={(e) => setActual(e.target.value)} autoComplete="current-password" />
            <Campo etiqueta="Nueva contraseña" type="password" value={nueva} onChange={(e) => setNueva(e.target.value)} autoComplete="new-password" />
            <MedidorContrasena contrasena={nueva} />
            <Campo
              etiqueta="Confirma la nueva contraseña"
              type="password"
              value={confirmar}
              onChange={(e) => setConfirmar(e.target.value)}
              error={confirmar && confirmar !== nueva ? "No coincide con la nueva contraseña." : undefined}
              autoComplete="new-password"
            />
            {error && <p role="alert" className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm font-semibold text-red-600 dark:text-red-400">{error}</p>}
            <Boton type="submit" cargando={cargando} disabled={!actual || nueva.length < 10 || nueva !== confirmar}>
              Guardar contraseña
            </Boton>
          </form>
        </Entrada>
      </div>
    </>
  );
}
