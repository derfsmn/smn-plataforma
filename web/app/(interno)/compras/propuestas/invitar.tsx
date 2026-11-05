"use client";
// Invitar a un proveedor (actual o nuevo) al portal. Le llega un correo con la liga para crear su contraseña.

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Modal } from "@/componentes/modal";
import { Boton, Campo } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import type { Proveedor } from "@/lib/propuestas";

type Invitado = { proveedor: Proveedor; liga: string; expira_en: string; correo_enviado: boolean };

export function Invitar({ cerrar, listo }: { cerrar: () => void; listo: (p: Proveedor) => void }) {
  const [datos, setDatos] = useState({ nombre: "", correo: "", empresa: "", rfc: "", puesto: "" });
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [hecho, setHecho] = useState<Invitado | null>(null);
  const [copiada, setCopiada] = useState(false);
  const poner = (k: keyof typeof datos) => (e: React.ChangeEvent<HTMLInputElement>) => setDatos({ ...datos, [k]: e.target.value });

  const invitar = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      const r = await api<Invitado>("/api/compras/proveedores/invitar", {
        cuerpo: { ...datos, rfc: datos.rfc.trim() || null, puesto: datos.puesto.trim() || null },
      });
      setHecho(r);
      listo(r.proveedor);
    } catch (err) {
      setError(mensajeDe(err));
    } finally {
      setEnviando(false);
    }
  };

  if (hecho)
    return (
      <Modal titulo="Invitación lista" cerrar={cerrar}>
        <p className="text-sm">
          {hecho.correo_enviado
            ? `Le mandamos un correo a ${hecho.proveedor.correo} con la liga para crear su contraseña.`
            : "El correo no está configurado en esta computadora, así que no se envió. Copia la liga y mándasela."}
        </p>
        <div className="mt-4 flex items-center gap-2 rounded-xl bg-smn-gris-50 p-3">
          <code className="min-w-0 flex-1 truncate text-[13px]">{hecho.liga}</code>
          <Boton
            variante="secundario"
            onClick={() => {
              navigator.clipboard.writeText(hecho.liga);
              setCopiada(true);
            }}
          >
            {copiada ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} {copiada ? "Copiada" : "Copiar"}
          </Boton>
        </div>
        <p className="mt-2 text-[13px] text-smn-gris-500">Vence el {fechaLocal(hecho.expira_en, { dateStyle: "long" })} y solo se puede usar una vez.</p>
        <div className="mt-5 flex justify-end">
          <Boton onClick={cerrar}>Listo</Boton>
        </div>
      </Modal>
    );

  return (
    <Modal titulo="Invitar proveedor" cerrar={cerrar}>
      <form onSubmit={invitar} className="space-y-3">
        <p className="text-sm text-smn-gris-500">Le llega un correo con una liga para crear su contraseña y entrar al portal, donde propone uno o varios productos.</p>
        <Campo etiqueta="Nombre de la persona" required minLength={2} value={datos.nombre} onChange={poner("nombre")} />
        <Campo etiqueta="Correo" type="email" required value={datos.correo} onChange={poner("correo")} />
        <Campo etiqueta="Empresa (razón social)" required minLength={2} value={datos.empresa} onChange={poner("empresa")} />
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo etiqueta="RFC (opcional)" maxLength={13} value={datos.rfc} onChange={(e) => setDatos({ ...datos, rfc: e.target.value.toUpperCase() })} />
          <Campo etiqueta="Puesto (opcional)" value={datos.puesto} onChange={poner("puesto")} />
        </div>
        <p className="text-[13px] text-smn-gris-500">Con el RFC, si la empresa ya tiene gente en el portal, esta persona verá las mismas propuestas.</p>
        {error && <p className="text-sm font-semibold text-red-700 dark:text-red-400">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Boton type="button" variante="fantasma" onClick={cerrar}>Cancelar</Boton>
          <Boton type="submit" cargando={enviando}>Invitar</Boton>
        </div>
      </form>
    </Modal>
  );
}
