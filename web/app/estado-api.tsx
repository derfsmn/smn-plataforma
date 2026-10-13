"use client";

import { useEffect, useState } from "react";

type Salud = { api: string; base_de_datos: string; entorno: string };

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function EstadoApi() {
  const [salud, setSalud] = useState<Salud | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/salud`)
      .then((r) => r.json())
      .then(setSalud)
      .catch(() => setError(true));
  }, []);

  const filas: [string, string][] = salud
    ? [["API", salud.api], ["Base de datos", salud.base_de_datos], ["Entorno", salud.entorno]]
    : [["API", error ? "sin conexión" : "consultando…"]];

  return (
    <dl className="grid gap-3 sm:grid-cols-3">
      {filas.map(([nombre, valor]) => (
        <div key={nombre} className="rounded-xl border border-smn-gris-100 bg-white p-4">
          <dt className="text-sm text-smn-gris-500">{nombre}</dt>
          <dd className="mt-1 font-bold">
            <span
              className={`mr-2 inline-block h-2.5 w-2.5 rounded-full ${
                valor === "ok" || valor === "desarrollo" ? "bg-smn-naranja" : "bg-smn-gris-300"
              }`}
            />
            {valor}
          </dd>
        </div>
      ))}
    </dl>
  );
}
