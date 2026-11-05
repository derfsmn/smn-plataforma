"use client";

import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import { api, fechaLocal, tamanoLegible, urlArchivo, type Archivo } from "@/lib/api";
import { EstadoApi } from "@/componentes/estado-api";
import { SubirArchivo } from "@/componentes/subir-archivo";
import { Encabezado, Entrada } from "@/componentes/ui";

export default function Sistema() {
  const [mios, setMios] = useState<Archivo[]>([]);
  useEffect(() => {
    api<Archivo[]>("/api/archivos/mios").then(setMios).catch(() => {});
  }, []);

  return (
    <>
      <Encabezado titulo="Estado del sistema" descripcion="Conexión real con la API, SQL Server y el correo de salida (no es dato de ejemplo)." />
      <EstadoApi />

      <Entrada retraso={0.1} className="mt-8 grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
          <h2 className="text-lg font-semibold">Prueba de archivos</h2>
          <p className="mt-0.5 mb-4 text-sm text-smn-gris-500">Sube un archivo para revisar el almacén. Los módulos usan esta misma pieza.</p>
          <SubirArchivo alSubir={(a) => setMios((m) => [a, ...m])} />
        </section>
        <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
          <h2 className="text-lg font-semibold">Mis archivos</h2>
          <p className="mt-0.5 mb-4 text-sm text-smn-gris-500">Los últimos que subiste.</p>
          {mios.length === 0 ? (
            <p className="py-8 text-center text-sm text-smn-gris-500">Todavía no subes archivos.</p>
          ) : (
            <ul className="divide-y divide-smn-gris-100">
              {mios.map((a) => (
                <li key={a.id} className="flex items-center gap-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{a.nombre}</p>
                    <p className="text-[13px] text-smn-gris-500">
                      {tamanoLegible(a.tamano_bytes)} · {fechaLocal(a.subido_en)}
                    </p>
                  </div>
                  <a href={urlArchivo(a.id)} className="rounded-full p-2 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta" aria-label={`Descargar ${a.nombre}`}>
                    <Download className="h-4 w-4" />
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>
      </Entrada>
    </>
  );
}
