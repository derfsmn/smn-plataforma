"use client";
// Compras empieza la captura de un producto nuevo: con un proveedor que ya tenemos en Intelisis o con uno nuevo.
// No pide contactos; se completan después en el cuestionario.

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Modal } from "@/componentes/modal";
import { ElegirIntelisis, type Intelisis } from "@/componentes/proveedor-intelisis";
import { Boton, Campo } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { RUTA, type Propuesta } from "@/lib/propuestas";

// alCrear: el Comité de producto nuevo la sube a su reunión antes de abrir la captura; destino: a dónde ir después.
export function Capturar({ cerrar, alCrear, destino }: { cerrar: () => void; alCrear?: (p: Propuesta) => Promise<void>; destino?: (p: Propuesta) => string }) {
  const router = useRouter();
  const [tipo, setTipo] = useState<"actual" | "nuevo">("actual");
  const [elegido, setElegido] = useState<Intelisis | null>(null);
  const [nuevo, setNuevo] = useState({ nombre: "", rfc: "" });
  const [error, setError] = useState<string | null>(null);
  const [creando, setCreando] = useState(false);

  const crear = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (tipo === "actual" && !elegido) return setError("Elige el proveedor de la lista.");
    if (tipo === "nuevo" && nuevo.nombre.trim().length < 2) return setError("Escribe la razón social o el nombre del proveedor.");
    setCreando(true);
    try {
      const cuerpo = tipo === "actual" ? { proveedor_codigo: elegido!.codigo } : { nombre: nuevo.nombre.trim(), rfc: nuevo.rfc.trim() || null };
      const p = await api<Propuesta>(`${RUTA}/captura`, { cuerpo });
      if (alCrear) await alCrear(p);
      router.push(destino ? destino(p) : `/compras/propuestas/captura/${p.id}`);
    } catch (err) {
      setError(mensajeDe(err));
      setCreando(false);
    }
  };

  const opcion = (valor: "actual" | "nuevo", titulo: string, texto: string) => (
    <button
      type="button"
      onClick={() => {
        setTipo(valor);
        setError(null);
      }}
      aria-pressed={tipo === valor}
      className={`flex-1 rounded-xl border p-3 text-left transition-colors ${tipo === valor ? "border-tinta bg-tinta text-superficie" : "border-smn-gris-100 hover:border-smn-gris-300"}`}
    >
      <span className="block text-[15px] font-semibold">{titulo}</span>
      <span className={`block text-[13px] ${tipo === valor ? "opacity-80" : "text-smn-gris-700"}`}>{texto}</span>
    </button>
  );

  return (
    <Modal titulo="Capturar producto nuevo" cerrar={cerrar} ancho="max-w-lg">
      <form onSubmit={crear}>
        <p className="mb-4 text-sm text-smn-gris-700">
          Llenas el mismo cuestionario que el proveedor. Los datos de contacto son opcionales por ahora.
        </p>
        <div className="mb-4 flex gap-2">
          {opcion("actual", "Proveedor actual", "Ya nos surte; está en Intelisis")}
          {opcion("nuevo", "Proveedor nuevo", "Todavía no le compramos")}
        </div>

        {tipo === "actual" ? (
          <ElegirIntelisis elegido={elegido} elegir={setElegido} />
        ) : (
          <div className="grid gap-4">
            <Campo etiqueta="Razón social o nombre" autoFocus value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} maxLength={200} />
            <Campo
              etiqueta="RFC (opcional)"
              value={nuevo.rfc}
              onChange={(e) => setNuevo({ ...nuevo, rfc: e.target.value.toUpperCase().replace(/[^A-ZÑ&0-9]/g, "") })}
              maxLength={13}
              autoComplete="off"
            />
          </div>
        )}

        {error && <p className="mt-3 text-sm font-medium text-red-700 dark:text-red-400">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Boton type="button" variante="fantasma" onClick={cerrar}>Cancelar</Boton>
          <Boton type="submit" cargando={creando}>Empezar captura</Boton>
        </div>
      </form>
    </Modal>
  );
}
