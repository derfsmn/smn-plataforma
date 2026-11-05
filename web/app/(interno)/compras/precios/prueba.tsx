"use client";
// Prueba con Excel (Diego, 2026-10-26): subir una lista de SKU, ver cuáles se encontraron y cuánto costaría, y correr el radar
// solo con esos. No cambia los productos vigilados ni lo que muestra el radar; la salida se descarga en Excel.

import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, Download, FileSpreadsheet, FlaskConical, Play, TriangleAlert, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { Boton, Insignia } from "@/componentes/ui";
import { dolares, haceCuanto, mensajeDe } from "@/lib/api";
import { descargar, excelCorrida, subirPrueba, type Corrida, type Prueba } from "@/lib/precios";

export function PruebaExcel({ cerrar, lanzada }: { cerrar: () => void; lanzada: () => void }) {
  const avisar = useAvisos();
  const entrada = useRef<HTMLInputElement>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [revision, setRevision] = useState<Prueba | null>(null);
  const [leyendo, setLeyendo] = useState(false);
  const [lanzando, setLanzando] = useState(false);
  const [verTodos, setVerTodos] = useState(false);

  const elegir = async (f: File | undefined) => {
    if (!f) return;
    setArchivo(f);
    setRevision(null);
    setLeyendo(true);
    try {
      setRevision(await subirPrueba(f, true));
    } catch (e) {
      avisar(mensajeDe(e), "info");
      setArchivo(null);
    } finally {
      setLeyendo(false);
      if (entrada.current) entrada.current.value = "";
    }
  };

  const correr = async () => {
    if (!archivo) return;
    setLanzando(true);
    try {
      const r = await subirPrueba(archivo, false);
      avisar(`Prueba iniciada con ${r.encontrados.length} productos`, "exito");
      lanzada();
      cerrar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
      setLanzando(false);
    }
  };

  const plantilla = () => descargar("/api/compras/precios/prueba/plantilla", "plantilla-prueba-radar-precios.xlsx").catch((e) => avisar(mensajeDe(e), "info"));
  const visibles = revision ? (verTodos ? revision.encontrados : revision.encontrados.slice(0, 6)) : [];

  return (
    <Modal titulo="Prueba con Excel" cerrar={cerrar} ancho="max-w-xl">
      <p className="text-sm text-smn-gris-500">
        Sube un Excel con una columna <b className="text-tinta">SKU</b> (también acepta códigos de barras). El radar corre solo con esos productos y al terminar descargas el resultado en Excel. No cambia
        los productos vigilados ni lo que muestra la pantalla principal.
      </p>
      <button type="button" onClick={plantilla} className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-naranja-tinta hover:underline">
        <Download className="h-4 w-4" /> Descargar plantilla
      </button>

      <button
        type="button"
        onClick={() => entrada.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          elegir(e.dataTransfer.files[0]);
        }}
        className="mt-4 flex w-full items-center gap-3 rounded-2xl border-2 border-dashed border-smn-gris-300 px-4 py-5 text-left transition-colors hover:border-smn-naranja hover:bg-smn-gris-50"
      >
        <FileSpreadsheet className="h-8 w-8 shrink-0 text-smn-naranja" />
        <span className="min-w-0">
          <span className="block truncate font-semibold">{archivo ? archivo.name : "Arrastra aquí o elige el archivo"}</span>
          <span className="text-[13px] text-smn-gris-500">{leyendo ? "Leyendo…" : "Excel (.xlsx) o CSV · hasta 300 SKU"}</span>
        </span>
        <Upload className="ml-auto h-5 w-5 shrink-0 text-smn-gris-500" />
      </button>
      <input ref={entrada} type="file" accept=".xlsx,.csv" className="hidden" onChange={(e) => elegir(e.target.files?.[0])} />

      <AnimatePresence>
        {revision && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-4 space-y-3">
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-2xl bg-smn-gris-50 p-3">
                <p className="text-2xl font-semibold tabular-nums">{revision.skus}</p>
                <p className="text-[13px] text-smn-gris-500">SKU en el archivo</p>
              </div>
              <div className="rounded-2xl bg-smn-gris-50 p-3">
                <p className="text-2xl font-semibold tabular-nums">{revision.encontrados.length}</p>
                <p className="text-[13px] text-smn-gris-500">en el catálogo</p>
              </div>
              <div className="rounded-2xl bg-smn-gris-50 p-3">
                <p className="text-2xl font-semibold tabular-nums">{dolares(revision.estimado_usd, 3)}</p>
                <p className="text-[13px] text-smn-gris-500">costo máximo</p>
              </div>
            </div>

            {revision.encontrados.length > 0 && (
              <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 px-3 text-sm">
                {visibles.map((p) => (
                  <li key={p.producto_id} className="flex items-center gap-2 py-2">
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-smn-naranja" />
                    <span className="min-w-0 flex-1 truncate">{p.descripcion}</span>
                    <span className="text-[13px] text-smn-gris-500">{p.sku}</span>
                    {p.vigilado && <Insignia className="bg-smn-gris-100 text-smn-gris-700">vigilado</Insignia>}
                  </li>
                ))}
                {revision.encontrados.length > 6 && (
                  <li className="py-2">
                    <button type="button" onClick={() => setVerTodos(!verTodos)} className="text-[13px] font-semibold text-naranja-tinta hover:underline">
                      {verTodos ? "Ver menos" : `Ver los ${revision.encontrados.length}`}
                    </button>
                  </li>
                )}
              </ul>
            )}

            {revision.no_encontrados.length > 0 && (
              <p className="flex gap-2 rounded-2xl bg-aviso-fondo p-3 text-sm text-aviso-texto">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  {revision.no_encontrados.length} no están en el catálogo y se dejan fuera: {revision.no_encontrados.slice(0, 12).join(", ")}
                  {revision.no_encontrados.length > 12 && "…"}. Saldrán en la hoja «No encontrados».
                </span>
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-5 flex justify-end gap-2">
        <Boton variante="fantasma" onClick={cerrar}>Cancelar</Boton>
        <Boton onClick={correr} cargando={lanzando} disabled={!revision || revision.encontrados.length === 0}>
          <Play className="h-4 w-4" /> {revision?.encontrados.length ? `Correr prueba con ${revision.encontrados.length}` : "Correr prueba"}
        </Boton>
      </div>
    </Modal>
  );
}

/** La última prueba con Excel, con su descarga. */
export function UltimaPrueba({ c }: { c: Corrida }) {
  const avisar = useAvisos();
  const [bajando, setBajando] = useState(false);
  const bajar = async () => {
    setBajando(true);
    await excelCorrida(c).catch((e) => avisar(mensajeDe(e), "info"));
    setBajando(false);
  };
  return (
    <div className="mb-5 flex flex-wrap items-center gap-3 rounded-2xl border border-smn-gris-100 bg-superficie px-4 py-3 text-sm">
      <FlaskConical className="h-5 w-5 shrink-0 text-smn-naranja" />
      <p className="min-w-0 flex-1">
        <b>Última prueba con Excel</b>
        {c.archivo && ` · ${c.archivo}`} · {haceCuanto(c.terminado_en ?? c.iniciado_en).toLowerCase()}:{" "}
        <span className="text-smn-gris-500">
          {c.con_precios} de {c.productos} con precios{c.no_encontrados.length > 0 && `, ${c.no_encontrados.length} SKU no encontrados`}
          {c.estado === "fallida" && ` · falló: ${c.error}`}
        </span>
      </p>
      <Boton variante="secundario" onClick={bajar} cargando={bajando} className="px-3 py-1.5">
        <Download className="h-4 w-4" /> Descargar Excel
      </Boton>
    </div>
  );
}
