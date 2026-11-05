"use client";
// Formulario para crear contraseña desde una liga de un solo uso (invitación o restablecimiento)

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { CircleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { api, mensajeDe, type DatosLiga } from "@/lib/api";
import { Boton, Campo, Esqueleto } from "./ui";
import { MedidorContrasena } from "./medidor-contrasena";

export function CrearContrasena({
  ruta,
  titulo,
  boton,
  alTerminar,
  pedirAviso = false,
}: {
  ruta: string;
  titulo: (d: DatosLiga) => string;
  boton: string;
  alTerminar: (respuesta: unknown) => void;
  pedirAviso?: boolean; // solo en la invitación de externos
}) {
  const [datos, setDatos] = useState<DatosLiga | null>(null);
  const [errorLiga, setErrorLiga] = useState<string | null>(null);
  const [contrasena, setContrasena] = useState("");
  const [confirmar, setConfirmar] = useState("");
  const [aviso, setAviso] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    api<DatosLiga>(ruta).then(setDatos).catch((e) => setErrorLiga(mensajeDe(e)));
  }, [ruta]);

  const externo = pedirAviso && datos?.tipo === "externo";
  const valido = contrasena.length >= 10 && contrasena === confirmar && (!externo || aviso);

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valido) return;
    setCargando(true);
    setError(null);
    try {
      alTerminar(await api(ruta, { cuerpo: { contrasena, acepta_aviso_privacidad: aviso } }));
    } catch (err) {
      setError(mensajeDe(err));
      setCargando(false);
    }
  };

  if (errorLiga)
    return (
      <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-8 text-center">
        <CircleAlert className="mx-auto h-10 w-10 text-smn-naranja" />
        <p className="mt-3 font-semibold">{errorLiga}</p>
        <Link href="/login" className="mt-5 inline-block text-sm font-semibold underline underline-offset-4">Ir a iniciar sesión</Link>
      </div>
    );
  if (!datos) return <Esqueleto className="h-80" />;

  return (
    <>
      <h1 className="text-[26px] leading-tight font-semibold tracking-tight">{titulo(datos)}</h1>
      <p className="mt-1 text-sm text-smn-gris-500">
        {datos.correo}
        {datos.empresa && ` · ${datos.empresa}`}
      </p>
      <form onSubmit={enviar} className="mt-6 space-y-4">
        <Campo etiqueta="Contraseña nueva" type="password" autoComplete="new-password" value={contrasena} onChange={(e) => setContrasena(e.target.value)} />
        <MedidorContrasena contrasena={contrasena} />
        <Campo
          etiqueta="Repite la contraseña"
          type="password"
          autoComplete="new-password"
          value={confirmar}
          onChange={(e) => setConfirmar(e.target.value)}
          error={confirmar && confirmar !== contrasena ? "No coincide." : undefined}
        />
        {externo && (
          <label className="flex items-start gap-3 rounded-lg border border-smn-gris-100 bg-smn-gris-50 p-3 text-sm">
            <input type="checkbox" checked={aviso} onChange={(e) => setAviso(e.target.checked)} className="mt-0.5 h-4 w-4 accent-smn-naranja" />
            <span>
              Acepto el aviso de privacidad de Súper Mayoreo Naturista.
              <span className="block text-[13px] text-smn-gris-500">El texto del aviso está pendiente de Jurídico.</span>
            </span>
          </label>
        )}
        <AnimatePresence>
          {error && (
            <motion.p role="alert" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="rounded-lg bg-red-500/10 px-3 py-2.5 text-sm font-medium text-red-700 dark:text-red-400">
              {error}
            </motion.p>
          )}
        </AnimatePresence>
        <Boton type="submit" disabled={!valido} cargando={cargando} className="h-11 w-full">{boton}</Boton>
      </form>
    </>
  );
}
