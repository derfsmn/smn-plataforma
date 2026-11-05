"use client";
// Radar · Destinatarios: a quién le llega el reporte diario por correo.

import { AnimatePresence } from "motion/react";
import { Mail, Pencil, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { type Destinatario, type TipoCorreo } from "@/lib/radar";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { Boton, Campo, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { Vacio } from "../piezas";

type Forma = Omit<Destinatario, "id">;
const TIPOS: { valor: TipoCorreo; texto: string }[] = [
  { valor: "decision", texto: "Con botones de decisión" },
  { valor: "informativo", texto: "Solo informativo (sin botones)" },
];

export default function Destinatarios() {
  const avisar = useAvisos();
  const [lista, setLista] = useState<Destinatario[] | null>(null);
  const [editar, setEditar] = useState<{ id?: number; datos: Forma } | null>(null);
  const [borrar, setBorrar] = useState<Destinatario | null>(null);

  const cargar = useCallback(() => {
    api<Destinatario[]>("/api/compras/radar/destinatarios").then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  useEffect(cargar, [cargar]);

  const cambiar = async (d: Destinatario) => {
    try {
      await api(`/api/compras/radar/destinatarios/${d.id}`, { metodo: "PUT", cuerpo: { nombre: d.nombre, correo: d.correo, area: d.area, activo: !d.activo, tipo_correo: d.tipo_correo } });
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };
  const quitar = async () => {
    if (!borrar) return;
    try {
      await api(`/api/compras/radar/destinatarios/${borrar.id}`, { metodo: "DELETE" });
      avisar("Destinatario quitado", "exito");
      setBorrar(null);
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  if (!lista) return <Esqueleto className="h-48" />;
  const nuevo = () => setEditar({ datos: { nombre: "", correo: "", area: "", activo: true, tipo_correo: "decision" } });

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-2xl text-sm text-smn-gris-500">
          Reciben el reporte cada mañana. Elige para cada uno si le llega con los botones Abrir iniciativa, Vigilar y Descartar, o solo informativo. No necesitan cuenta para recibirlo; sí la necesitan para decidir desde los botones.
        </p>
        <Boton onClick={nuevo}>
          <Plus className="h-4 w-4" /> Agregar
        </Boton>
      </div>
      {!lista.length ? (
        <Vacio icono={<Mail className="h-10 w-10" />} titulo="Sin destinatarios" texto="Agrega a dirección, compras y quien deba recibir el reporte." />
      ) : (
        <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
          {lista.map((d) => (
            <li key={d.id} className={`flex items-center gap-3 p-4 ${d.activo ? "" : "opacity-60"}`}>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {d.nombre}{" "}
                  <Insignia className={`ml-1 ${d.tipo_correo === "informativo" ? "bg-smn-gris-100 text-smn-gris-700" : "bg-smn-naranja/15 text-aviso-texto"}`}>
                    {d.tipo_correo === "informativo" ? "Informativo" : "Con decisiones"}
                  </Insignia>
                  {!d.activo && <Insignia className="ml-1 bg-smn-gris-100 text-smn-gris-500">Pausado</Insignia>}
                </p>
                <p className="truncate text-sm text-smn-gris-500">
                  {d.correo}
                  {d.area ? ` · ${d.area}` : ""}
                </p>
              </div>
              <button
                role="switch"
                aria-checked={d.activo}
                aria-label={d.activo ? "Pausar envío" : "Reanudar envío"}
                onClick={() => cambiar(d)}
                className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${d.activo ? "bg-smn-naranja" : "bg-smn-gris-300"}`}
              >
                <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${d.activo ? "right-0.5" : "left-0.5"}`} />
              </button>
              <button onClick={() => setEditar({ id: d.id, datos: { nombre: d.nombre, correo: d.correo, area: d.area ?? "", activo: d.activo, tipo_correo: d.tipo_correo } })} className="rounded-lg p-1.5 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta" aria-label={`Editar ${d.nombre}`}>
                <Pencil className="h-4 w-4" />
              </button>
              <button onClick={() => setBorrar(d)} className="rounded-lg p-1.5 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta" aria-label={`Quitar ${d.nombre}`}>
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <AnimatePresence>
        {editar && <VentanaDestinatario id={editar.id} inicial={editar.datos} cerrar={() => setEditar(null)} alGuardar={cargar} />}
        {borrar && (
          <Modal titulo="Quitar de la lista" cerrar={() => setBorrar(null)}>
            <p>
              <b>{borrar.nombre}</b> ({borrar.correo}) dejará de recibir el reporte.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Boton variante="fantasma" onClick={() => setBorrar(null)}>
                Cancelar
              </Boton>
              <Boton onClick={quitar}>Quitar</Boton>
            </div>
          </Modal>
        )}
      </AnimatePresence>
    </div>
  );
}

function VentanaDestinatario({ id, inicial, cerrar, alGuardar }: { id?: number; inicial: Forma; cerrar: () => void; alGuardar: () => void }) {
  const avisar = useAvisos();
  const [d, setD] = useState<Forma>(inicial);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      await api(id ? `/api/compras/radar/destinatarios/${id}` : "/api/compras/radar/destinatarios", { metodo: id ? "PUT" : "POST", cuerpo: { ...d, area: d.area || null } });
      avisar(id ? "Destinatario actualizado" : "Destinatario agregado", "exito");
      alGuardar();
      cerrar();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setGuardando(false);
    }
  };
  return (
    <Modal titulo={id ? "Editar destinatario" : "Agregar destinatario"} cerrar={cerrar}>
      <div className="space-y-4">
        <Campo etiqueta="Nombre" value={d.nombre} onChange={(e) => setD({ ...d, nombre: e.target.value })} autoFocus />
        <Campo etiqueta="Correo" type="email" value={d.correo} onChange={(e) => setD({ ...d, correo: e.target.value })} />
        <Campo etiqueta="Área (opcional)" value={d.area ?? ""} onChange={(e) => setD({ ...d, area: e.target.value })} />
        <Selector etiqueta="Tipo de correo" valor={d.tipo_correo} cambiar={(v) => setD({ ...d, tipo_correo: v as TipoCorreo })} opciones={TIPOS} />
      </div>
      {error && (
        <p role="alert" className="mt-4 rounded-xl bg-red-500/10 px-3 py-2 text-sm font-semibold text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
      <div className="mt-5 flex justify-end gap-2">
        <Boton variante="fantasma" onClick={cerrar}>
          Cancelar
        </Boton>
        <Boton onClick={guardar} cargando={guardando}>
          Guardar
        </Boton>
      </div>
    </Modal>
  );
}
