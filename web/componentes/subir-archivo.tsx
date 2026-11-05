"use client";
// Zona para subir archivos (arrastrar o elegir), con avance. Cualquier módulo la reutiliza.

import { AnimatePresence, motion } from "motion/react";
import { CloudUpload, FileCheck2, FileWarning } from "lucide-react";
import { useRef, useState } from "react";
import { mensajeDe, subirArchivo, type Archivo } from "@/lib/api";

const ACEPTA = ".pdf,.png,.jpg,.jpeg,.webp,.xlsx,.docx,.csv";

type Carga = { nombre: string; avance: number; error?: string; listo?: boolean };

export function SubirArchivo({
  modulo,
  entidad,
  entidadId,
  alSubir,
  maximoMb = 10,
}: {
  modulo?: string;
  entidad?: string;
  entidadId?: string;
  alSubir?: (a: Archivo) => void;
  maximoMb?: number;
}) {
  const entrada = useRef<HTMLInputElement>(null);
  const [encima, setEncima] = useState(false);
  const [cargas, setCargas] = useState<Carga[]>([]);

  const subir = (archivos: FileList | null) => {
    if (!archivos) return;
    Array.from(archivos).forEach((archivo) => {
      const nombre = archivo.name;
      const poner = (c: Partial<Carga>) => setCargas((cs) => cs.map((x) => (x.nombre === nombre ? { ...x, ...c } : x)));
      setCargas((cs) => [{ nombre, avance: 0 }, ...cs.filter((x) => x.nombre !== nombre)].slice(0, 5));
      if (archivo.size > maximoMb * 1024 * 1024) return poner({ error: `Pasa de ${maximoMb} MB.` });
      subirArchivo(archivo, { modulo, entidad, entidad_id: entidadId }, (avance) => poner({ avance }))
        .then((a) => {
          poner({ avance: 100, listo: true });
          alSubir?.(a);
        })
        .catch((e) => poner({ error: mensajeDe(e) }));
    });
    if (entrada.current) entrada.current.value = "";
  };

  return (
    <div>
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
        className={`flex w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-4 py-8 text-center transition-colors ${
          encima ? "border-smn-naranja bg-smn-naranja/10" : "border-smn-gris-300 hover:border-smn-naranja hover:bg-smn-gris-50"
        }`}
      >
        <motion.span animate={{ y: encima ? -4 : 0 }}>
          <CloudUpload className="h-8 w-8 text-smn-naranja" />
        </motion.span>
        <span className="font-semibold">Arrastra aquí o elige un archivo</span>
        <span className="text-[13px] text-smn-gris-500">PDF, imagen, Excel, Word o CSV · hasta {maximoMb} MB</span>
      </motion.button>
      <input ref={entrada} type="file" accept={ACEPTA} multiple className="hidden" onChange={(e) => subir(e.target.files)} />

      <ul className="mt-3 space-y-2">
        <AnimatePresence initial={false}>
          {cargas.map((c) => (
            <motion.li
              key={c.nombre}
              layout
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="rounded-xl border border-smn-gris-100 px-3 py-2"
            >
              <div className="flex items-center gap-2 text-sm">
                {c.error ? <FileWarning className="h-4 w-4 shrink-0 text-red-500" /> : <FileCheck2 className={`h-4 w-4 shrink-0 ${c.listo ? "text-smn-naranja" : "text-smn-gris-500"}`} />}
                <span className="min-w-0 flex-1 truncate font-semibold">{c.nombre}</span>
                <span className="text-[13px] text-smn-gris-500">{c.error ? "" : c.listo ? "Listo" : `${c.avance} %`}</span>
              </div>
              {c.error ? (
                <p className="mt-1 text-[13px] font-semibold text-red-700 dark:text-red-400">{c.error}</p>
              ) : (
                !c.listo && (
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-smn-gris-100">
                    <motion.div className="h-full bg-smn-naranja" animate={{ width: `${c.avance}%` }} />
                  </div>
                )
              )}
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </div>
  );
}
