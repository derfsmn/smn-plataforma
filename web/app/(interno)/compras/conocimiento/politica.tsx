"use client";
// Ventana para escribir o editar una política (también «Cómo se decide hoy», que es una política con tema proceso).

import { useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { TEMAS, type EstadoPolitica, type Politica, type Tema } from "@/lib/conocimiento";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { Boton, Campo, Selector } from "@/componentes/ui";
import { AreaTexto, CampoDepartamento, MensajeError } from "./piezas";

export type FormaPolitica = { tema: Tema; titulo: string; contenido: string; departamento: string; estado: EstadoPolitica };

export const aFormaPolitica = (p: Politica): FormaPolitica => ({
  tema: p.tema,
  titulo: p.titulo,
  contenido: p.contenido,
  departamento: p.departamento ?? "",
  estado: p.estado,
});

const ESTADOS: { valor: EstadoPolitica; texto: string }[] = [
  { valor: "borrador", texto: "Borrador (todavía no se usa)" },
  { valor: "vigente", texto: "Vigente (así se aplica hoy)" },
  { valor: "archivada", texto: "Archivada (ya no se aplica)" },
];

export function VentanaPolitica({
  id,
  inicial,
  departamentos,
  guia,
  cerrar,
  alGuardar,
}: {
  id?: number;
  inicial: FormaPolitica;
  departamentos: string[];
  guia?: string;
  cerrar: () => void;
  alGuardar: () => void;
}) {
  const avisar = useAvisos();
  const [d, setD] = useState<FormaPolitica>(inicial);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fijo = inicial.tema === "proceso";
  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      await api(id ? `/api/compras/conocimiento/politicas/${id}` : "/api/compras/conocimiento/politicas", {
        metodo: id ? "PUT" : "POST",
        cuerpo: { ...d, departamento: d.departamento || null },
      });
      avisar("Guardado", "exito");
      alGuardar();
      cerrar();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setGuardando(false);
    }
  };
  return (
    <Modal titulo={id ? "Editar" : fijo ? "Describir cómo se decide hoy" : "Escribir política"} cerrar={cerrar} ancho="max-w-3xl">
      <div className="space-y-4">
        <Campo etiqueta="Título" value={d.titulo} onChange={(e) => setD({ ...d, titulo: e.target.value })} maxLength={200} autoFocus={!fijo} />
        {!fijo && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Selector etiqueta="Tema" valor={d.tema} cambiar={(v) => setD({ ...d, tema: v as Tema })} opciones={TEMAS} />
            <CampoDepartamento valor={d.departamento} cambiar={(v) => setD({ ...d, departamento: v })} departamentos={departamentos} />
          </div>
        )}
        {guia && <p className="rounded-xl bg-smn-naranja/10 px-3.5 py-2.5 text-sm whitespace-pre-line text-aviso-texto">{guia}</p>}
        <AreaTexto
          etiqueta="Texto"
          valor={d.contenido}
          cambiar={(v) => setD({ ...d, contenido: v })}
          filas={14}
          max={60000}
          ayuda="Escríbelo como se lo explicarías a alguien nuevo en Compras. Cada cambio guarda una versión nueva."
        />
        <Selector etiqueta="Estado" valor={d.estado} cambiar={(v) => setD({ ...d, estado: v as EstadoPolitica })} opciones={ESTADOS} />
      </div>
      <MensajeError texto={error} />
      <div className="mt-5 flex justify-end gap-2">
        <Boton variante="fantasma" onClick={cerrar}>
          Cancelar
        </Boton>
        <Boton onClick={guardar} cargando={guardando} disabled={d.titulo.trim().length < 2}>
          Guardar
        </Boton>
      </div>
    </Modal>
  );
}
