"use client";
// Fotos y documentos de una propuesta. Se suben con /api/archivos y luego se ligan a la propuesta.

import { AnimatePresence, motion } from "motion/react";
import { CloudUpload, FileText, Loader2, X } from "lucide-react";
import { useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { api, mensajeDe, subirArchivo, tamanoLegible } from "@/lib/api";
import { RUTA, urlAdjunto, type Adjunto, type Opcion, type Propuesta, type ReglaAdjunto } from "@/lib/propuestas";
import { Error, Etiqueta } from "./campos";

const EXTENSION: Record<string, string> = {
  "image/jpeg": ".jpg,.jpeg",
  "image/png": ".png",
  "image/webp": ".webp",
  "application/pdf": ".pdf",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
  "text/csv": ".csv",
};
const FORMATO: Record<string, string> = {
  "image/jpeg": "JPG",
  "image/png": "PNG",
  "image/webp": "WEBP",
  "application/pdf": "PDF",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
  "text/csv": "CSV",
};

export function Archivos({
  propuesta,
  tipo,
  regla,
  etiqueta,
  ayuda,
  etiquetas,
  error,
  cambio,
}: {
  propuesta: Propuesta;
  tipo: string;
  regla: ReglaAdjunto;
  etiqueta: string;
  ayuda?: string;
  etiquetas?: Opcion[];
  error?: string;
  cambio: (p: Propuesta) => void;
}) {
  const avisar = useAvisos();
  const entrada = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState<string[]>([]);
  const [encima, setEncima] = useState(false);
  const mios = propuesta.adjuntos.filter((a) => a.tipo === tipo);
  const fotos = regla.tipos.every((t) => t.startsWith("image/"));
  const formatos = [...new Set(regla.tipos.map((t) => FORMATO[t]))].join(", ");
  const lleno = regla.maximo > 1 && mios.length >= regla.maximo;

  const subir = async (lista: FileList | null) => {
    if (!lista) return;
    let restantes = regla.maximo > 1 ? regla.maximo - mios.length : 1;
    for (const archivo of Array.from(lista)) {
      if (restantes <= 0) {
        avisar(`Máximo ${regla.maximo} archivos.`, "info");
        break;
      }
      if (!regla.tipos.includes(archivo.type) && !(archivo.type === "" && archivo.name.toLowerCase().endsWith(".csv"))) {
        avisar(`${archivo.name}: formato no permitido (${formatos}).`, "info");
        continue;
      }
      if (archivo.size > regla.mb * 1024 * 1024) {
        avisar(`${archivo.name}: pasa de ${regla.mb} MB.`, "info");
        continue;
      }
      restantes--;
      setSubiendo((s) => [...s, archivo.name]);
      try {
        const a = await subirArchivo(archivo, { modulo: "compras", entidad: "propuesta", entidad_id: String(propuesta.id) });
        // La primera foto del producto es el frente y la segunda el reverso, como en el cuestionario
        const usadas = new Set(propuesta.adjuntos.filter((x) => x.tipo === tipo).map((x) => x.etiqueta));
        const sugerida = tipo === "imagen_producto" ? ["Frente", "Reverso"].find((e) => !usadas.has(e)) : undefined;
        const p = await api<Propuesta>(`${RUTA}/${propuesta.id}/adjuntos`, { cuerpo: { archivo_id: a.id, tipo, etiqueta: sugerida } });
        propuesta = p;
        cambio(p);
      } catch (e) {
        avisar(`${archivo.name}: ${mensajeDe(e)}`, "info");
      } finally {
        setSubiendo((s) => s.filter((x) => x !== archivo.name));
      }
    }
    if (entrada.current) entrada.current.value = "";
  };

  const quitar = async (a: Adjunto) => {
    try {
      cambio(await api<Propuesta>(`${RUTA}/${propuesta.id}/adjuntos/${a.id}`, { metodo: "DELETE" }));
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  const etiquetar = async (a: Adjunto, valor: string) => {
    try {
      cambio(await api<Propuesta>(`${RUTA}/${propuesta.id}/adjuntos/${a.id}`, { metodo: "PATCH", cuerpo: { etiqueta: valor } }));
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  const limites =
    regla.maximo > 1
      ? `${formatos} · hasta ${regla.mb} MB cada uno · ${regla.minimo ? `mínimo ${regla.minimo}, ` : ""}máximo ${regla.maximo}`
      : `${formatos} · hasta ${regla.mb} MB`;

  return (
    <div>
      <Etiqueta texto={etiqueta} requerido={regla.minimo > 0} ayuda={ayuda} />
      {!lleno && (
        <motion.button
          type="button"
          onClick={() => entrada.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setEncima(true);
          }}
          onDragLeave={() => setEncima(false)}
          onDrop={(e) => {
            e.preventDefault();
            setEncima(false);
            subir(e.dataTransfer.files);
          }}
          animate={{ scale: encima ? 1.01 : 1 }}
          className={`flex w-full flex-col items-center justify-center gap-1.5 rounded-2xl border-2 border-dashed px-4 py-6 text-center transition-colors ${
            encima ? "border-smn-naranja bg-smn-naranja/10" : error ? "border-red-400" : "border-smn-gris-300 hover:border-smn-naranja hover:bg-smn-gris-50"
          }`}
        >
          <CloudUpload className="h-7 w-7 text-smn-naranja" />
          <span className="font-semibold">{mios.length && regla.maximo === 1 ? "Reemplazar archivo" : "Arrastra aquí o elige"}</span>
          <span className="text-[13px] text-smn-gris-500">{limites}</span>
        </motion.button>
      )}
      <input
        ref={entrada}
        type="file"
        accept={regla.tipos.map((t) => EXTENSION[t]).join(",")}
        multiple={regla.maximo > 1}
        className="hidden"
        onChange={(e) => subir(e.target.files)}
      />
      {regla.maximo > 1 && <p className="mt-1 text-[13px] text-smn-gris-500">{mios.length} de {regla.maximo}</p>}
      <Error mensaje={error} />

      {fotos ? (
        <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <AnimatePresence initial={false}>
            {mios.map((a) => (
              <motion.li key={a.id} layout initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
                className="overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie">
                <div className="relative aspect-square bg-smn-gris-50">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={urlAdjunto(propuesta.id, a.id)} alt={a.nombre} className="h-full w-full object-contain" />
                  {propuesta.editable && (
                    <button type="button" onClick={() => quitar(a)} aria-label={`Quitar ${a.nombre}`}
                      className="absolute top-1.5 right-1.5 rounded-full bg-smn-negro/70 p-1 text-white hover:bg-smn-negro">
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
                {etiquetas && (
                  <select value={a.etiqueta ?? ""} disabled={!propuesta.editable} onChange={(e) => etiquetar(a, e.target.value)} aria-label="Qué muestra la foto"
                    className="w-full border-t border-smn-gris-100 bg-superficie px-2 py-1.5 text-sm font-semibold outline-none">
                    {etiquetas.map((o) => (
                      <option key={o.valor} value={o.valor}>{o.texto}</option>
                    ))}
                  </select>
                )}
              </motion.li>
            ))}
          </AnimatePresence>
          {subiendo.map((n) => (
            <li key={n} className="grid aspect-square place-items-center rounded-2xl border border-dashed border-smn-gris-300">
              <Loader2 className="h-6 w-6 animate-spin text-smn-naranja" />
            </li>
          ))}
        </ul>
      ) : (
        <ul className="mt-3 space-y-2">
          {mios.map((a) => (
            <li key={a.id} className="flex items-center gap-2 rounded-xl border border-smn-gris-100 px-3 py-2 text-sm">
              <FileText className="h-4 w-4 shrink-0 text-smn-naranja" />
              <a href={urlAdjunto(propuesta.id, a.id)} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate font-semibold hover:underline">
                {a.nombre}
              </a>
              <span className="text-[13px] text-smn-gris-500">{tamanoLegible(a.tamano_bytes)}</span>
              {propuesta.editable && (
                <button type="button" onClick={() => quitar(a)} aria-label={`Quitar ${a.nombre}`} className="rounded-full p-1 hover:bg-smn-gris-100">
                  <X className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
          {subiendo.map((n) => (
            <li key={n} className="flex items-center gap-2 rounded-xl border border-dashed border-smn-gris-300 px-3 py-2 text-sm text-smn-gris-500">
              <Loader2 className="h-4 w-4 animate-spin text-smn-naranja" /> {n}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
