"use client";

import { useEffect, useState } from "react";
import { urlApi } from "@/lib/api";

type Salud = { api: string; base_de_datos: string; correo: string; entorno: string; version?: string };


export function EstadoApi() {
  const [salud, setSalud] = useState<Salud | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch(`${urlApi()}/api/salud`)
      .then((r) => r.json())
      .then(setSalud)
      .catch(() => setError(true));
  }, []);

  const filas: [string, string][] = salud
    ? [["API", salud.api], ["Base de datos", salud.base_de_datos], ["Correo de salida", salud.correo], ["Entorno", salud.entorno], ["Versión", salud.version ?? "—"]]
    : [["API", error ? "sin conexión" : "consultando…"]];

  return (
    <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {filas.map(([nombre, valor]) => (
        <div key={nombre} className="rounded-xl border border-smn-gris-100 bg-superficie p-4">
          <dt className="text-sm text-smn-gris-500">{nombre}</dt>
          <dd className="mt-1 font-semibold">
            <span
              className={`mr-2 inline-block h-2.5 w-2.5 rounded-full ${
                valor === "ok" || valor === "desarrollo" || valor === "produccion" ? "bg-smn-naranja" : "bg-smn-gris-300"
              }`}
            />
            {valor}
          </dd>
        </div>
      ))}
    </dl>
  );
}
