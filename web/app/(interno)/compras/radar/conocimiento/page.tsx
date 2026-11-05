"use client";
// Radar · Documentos de apoyo: documentos de SMN que la IA usa como contexto al armar el reporte.

import { AnimatePresence } from "motion/react";
import { BookOpen, FileText } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, mensajeDe, urlApi, type Archivo } from "@/lib/api";
import { fechaHora, type Documento } from "@/lib/radar";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Modal } from "@/componentes/modal";
import { SubirArchivo } from "@/componentes/subir-archivo";
import { Boton, Campo, Esqueleto, Insignia } from "@/componentes/ui";
import { Vacio } from "../piezas";

export default function Conocimiento() {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const admin = puede("compras.radar.administrar");
  const [lista, setLista] = useState<Documento[] | null>(null);
  const [subido, setSubido] = useState<Archivo | null>(null);

  const cargar = useCallback(() => {
    api<Documento[]>("/api/compras/radar/documentos").then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  useEffect(cargar, [cargar]);

  const cambiar = async (d: Documento) => {
    try {
      await api(`/api/compras/radar/documentos/${d.id}`, { metodo: "PUT", cuerpo: { activo: !d.activo } });
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  if (!lista) return <Esqueleto className="h-48" />;
  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-sm text-smn-gris-500">
        Estudios, presentaciones o reportes que Compras ya tiene. No se leen a diario: la IA los consulta al armar el reporte para decir cuándo un hallazgo
        confirma algo que SMN ya sabía. Se lee el texto de PDF, Word, Excel y CSV.
      </p>
      {admin && (
        <div className="max-w-xl">
          <SubirArchivo modulo="compras" entidad="radar_documento" alSubir={setSubido} />
        </div>
      )}
      {!lista.length ? (
        <Vacio icono={<BookOpen className="h-10 w-10" />} titulo="Sin documentos" texto="Sube el primero para que la IA lo tome en cuenta." />
      ) : (
        <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
          {lista.map((d) => (
            <li key={d.id} className={`flex items-start gap-3 p-4 ${d.activo ? "" : "opacity-60"}`}>
              <FileText className="mt-0.5 h-5 w-5 shrink-0 text-smn-naranja" />
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {d.titulo} {!d.activo && <Insignia className="ml-1 bg-smn-gris-100 text-smn-gris-500">No se usa</Insignia>}
                </p>
                {d.descripcion && <p className="text-sm text-smn-gris-700">{d.descripcion}</p>}
                <p className="text-[13px] text-smn-gris-500">
                  <a href={`${urlApi()}/api/archivos/${d.archivo_id}`} className="hover:underline">
                    {d.nombre_archivo}
                  </a>{" "}
                  · {d.caracteres ? `${d.caracteres.toLocaleString("es-MX")} caracteres leídos` : "no se pudo leer texto"} · {d.subido_por} · {fechaHora(d.subido_en)}
                </p>
              </div>
              {admin && (
                <button
                  role="switch"
                  aria-checked={d.activo}
                  aria-label={d.activo ? "Dejar de usar" : "Usar"}
                  onClick={() => cambiar(d)}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${d.activo ? "bg-smn-naranja" : "bg-smn-gris-300"}`}
                >
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${d.activo ? "right-0.5" : "left-0.5"}`} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <AnimatePresence>{subido && <VentanaDocumento archivo={subido} cerrar={() => setSubido(null)} alGuardar={cargar} />}</AnimatePresence>
    </div>
  );
}

function VentanaDocumento({ archivo, cerrar, alGuardar }: { archivo: Archivo; cerrar: () => void; alGuardar: () => void }) {
  const avisar = useAvisos();
  const [titulo, setTitulo] = useState(archivo.nombre.replace(/\.[^.]+$/, ""));
  const [descripcion, setDescripcion] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      const d = await api<Documento>("/api/compras/radar/documentos", { metodo: "POST", cuerpo: { archivo_id: archivo.id, titulo, descripcion: descripcion || null } });
      avisar(d.caracteres ? "Documento agregado" : "Documento agregado, pero no se pudo leer su texto", d.caracteres ? "exito" : "info");
      alGuardar();
      cerrar();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setGuardando(false);
    }
  };
  return (
    <Modal titulo="Agregar documento de apoyo" cerrar={cerrar}>
      <p className="mb-4 text-sm text-smn-gris-500">{archivo.nombre}</p>
      <div className="space-y-4">
        <Campo etiqueta="Título" value={titulo} onChange={(e) => setTitulo(e.target.value)} autoFocus />
        <Campo etiqueta="De qué trata (opcional)" value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
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
        <Boton onClick={guardar} cargando={guardando} disabled={titulo.trim().length < 2}>
          Agregar
        </Boton>
      </div>
    </Modal>
  );
}
