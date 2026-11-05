"use client";
// Proveedores invitados al portal: quién ya entró, cuántas propuestas ha enviado su empresa y reenvío de la invitación.

import { AnimatePresence } from "motion/react";
import { Send, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Esqueleto, Insignia } from "@/componentes/ui";
import { api, haceCuanto, mensajeDe, type Liga } from "@/lib/api";
import type { Proveedor } from "@/lib/propuestas";
import { Invitar } from "../invitar";

const ESTATUS = {
  invitado: { texto: "Invitado", clase: "bg-smn-naranja/15 text-aviso-texto" },
  activo: { texto: "Activo", clase: "bg-tinta text-superficie" },
  inactivo: { texto: "Inactivo", clase: "bg-smn-gris-100 text-smn-gris-500" },
};

export default function Proveedores() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const invita = puede("compras.proveedores.invitar");
  const [lista, setLista] = useState<Proveedor[] | null>(null);
  const [invitando, setInvitando] = useState(false);
  const [ocupado, setOcupado] = useState<number | null>(null);

  const cargar = useCallback(() => {
    api<Proveedor[]>("/api/compras/proveedores").then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  useEffect(cargar, [cargar]);

  const reenviar = async (p: Proveedor) => {
    setOcupado(p.id);
    try {
      const r = await api<Liga>(`/api/compras/proveedores/${p.id}/reenviar`, { metodo: "POST" });
      if (r.correo_enviado) avisar(`Se reenvió la invitación a ${p.correo}`);
      else {
        await navigator.clipboard.writeText(r.liga).catch(() => {});
        avisar("El correo no está configurado: copiamos la liga nueva para que se la mandes", "info");
      }
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };

  return (
    <>
      {invita && (
        <div className="mb-4 flex justify-end">
          <Boton onClick={() => setInvitando(true)}>
            <UserPlus className="h-4 w-4" /> Invitar proveedor
          </Boton>
        </div>
      )}
      {lista === null ? (
        <Esqueleto className="h-40" />
      ) : lista.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-smn-gris-500">Aún no hay proveedores invitados.</p>
      ) : (
        <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
          {lista.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{p.empresa ?? "Sin empresa"}</p>
                <p className="truncate text-sm text-smn-gris-500">
                  {p.nombre} · {p.correo}
                  {p.rfc && ` · ${p.rfc}`}
                </p>
                <p className="text-[13px] text-smn-gris-500">
                  {p.propuestas} {p.propuestas === 1 ? "propuesta enviada" : "propuestas enviadas"} · Último acceso: {haceCuanto(p.ultimo_acceso_en)}
                </p>
              </div>
              <Insignia className={ESTATUS[p.estatus].clase}>{ESTATUS[p.estatus].texto}</Insignia>
              {invita && p.estatus === "invitado" && (
                <Boton variante="secundario" cargando={ocupado === p.id} onClick={() => reenviar(p)}>
                  <Send className="h-4 w-4" /> Reenviar
                </Boton>
              )}
            </li>
          ))}
        </ul>
      )}
      <AnimatePresence>{invitando && <Invitar cerrar={() => setInvitando(false)} listo={cargar} />}</AnimatePresence>
    </>
  );
}
