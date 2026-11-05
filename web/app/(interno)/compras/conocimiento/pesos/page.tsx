"use client";
// Base de conocimiento · Peso de cada factor: Compras reparte 100 puntos entre los seis factores del semáforo
// y otros 100 entre los cuatro bloques de la calificación de proveedores (Datos → Proveedores).

import { Save } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { type Peso, type Pesos, type PesosProveedor } from "@/lib/conocimiento";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Esqueleto, Insignia } from "@/componentes/ui";
import { EDITAR, MensajeError, Pie } from "../piezas";

export default function PaginaPesos() {
  const avisar = useAvisos();
  const [p, setP] = useState<Pesos | null>(null);
  const [pv, setPv] = useState<PesosProveedor | null>(null);

  useEffect(() => {
    api<Pesos>("/api/compras/conocimiento/pesos").then(setP).catch((e) => avisar(mensajeDe(e), "info"));
    api<PesosProveedor>("/api/compras/conocimiento/pesos-proveedor").then(setPv).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);

  if (!p || !pv) return <Esqueleto className="h-64" />;
  return (
    <div className="max-w-3xl space-y-10">
      <section>
        <p className="mb-4 text-sm text-smn-gris-500">
          El semáforo califica cada producto en seis factores. Reparte 100 puntos según cuánto pesa cada uno cuando Compras decide. Si un factor no se toma en cuenta hoy, déjalo en 0.
        </p>
        <Reparto
          inicial={p.factores}
          ruta="/api/compras/conocimiento/pesos"
          guardado={(n: Pesos) => {
            setP(n);
            return n.factores;
          }}
        />
        <p className="mt-2 text-[13px] text-smn-gris-500">
          <Pie por={p.actualizado_por} en={p.actualizado_en} />
        </p>
      </section>

      <section>
        <h2 className="flex flex-wrap items-center gap-2 text-lg font-semibold">
          Calificación de proveedores
          <Insignia className={pv.de === "compras" ? "bg-emerald-100 text-emerald-700" : "bg-aviso-fondo text-aviso-texto"}>
            {pv.de === "compras" ? "Pesos de Compras" : "Pesos provisionales"}
          </Insignia>
        </h2>
        <p className="mt-1 mb-4 text-sm text-smn-gris-500">
          Cada proveedor en{" "}
          <Link href="/datos/proveedores" className="font-semibold text-naranja-tinta hover:underline">
            Datos → Proveedores
          </Link>{" "}
          tiene una calificación de 0 a 100 con cuatro bloques. Reparte 100 puntos entre ellos. Los nuevos pesos cuentan desde el siguiente «Calcular»; esa calificación
          también es el factor «Proveedor» del semáforo.
        </p>
        <Reparto
          inicial={pv.bloques}
          ruta="/api/compras/conocimiento/pesos-proveedor"
          guardado={(n: PesosProveedor) => {
            setPv(n);
            return n.bloques;
          }}
        />
      </section>
    </div>
  );
}

function Reparto<T>({ inicial, ruta, guardado }: { inicial: Peso[]; ruta: string; guardado: (nuevo: T) => Peso[] }) {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const editar = puede(EDITAR);
  const [lista, setLista] = useState(inicial);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const total = lista.reduce((s, f) => s + (Number(f.puntos) || 0), 0);
  const cambiar = (factor: string, cambios: { puntos?: number; nota?: string }) => setLista(lista.map((f) => (f.factor === factor ? { ...f, ...cambios } : f)));

  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      const nuevo = await api<T>(ruta, {
        metodo: "PUT",
        cuerpo: lista.map((f) => ({ factor: f.factor, puntos: Number(f.puntos) || 0, nota: f.nota || null })),
      });
      setLista(guardado(nuevo));
      avisar("Pesos guardados", "exito");
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setGuardando(false);
    }
  };

  return (
    <>
      <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
        {lista.map((f) => (
          <li key={f.factor} className="grid gap-3 p-4 sm:grid-cols-[1fr_auto] sm:items-center">
            <div className="min-w-0">
              <p className="font-semibold">{f.nombre}</p>
              <p className="text-sm text-smn-gris-500">{f.que_mide}</p>
              {editar ? (
                <input
                  value={f.nota ?? ""}
                  onChange={(e) => cambiar(f.factor, { nota: e.target.value })}
                  maxLength={600}
                  placeholder="Nota (opcional): cómo lo revisan hoy"
                  className="mt-2 w-full rounded-lg border border-smn-gris-300 bg-superficie px-3 py-1.5 text-sm outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
                />
              ) : (
                f.nota && <p className="mt-1 text-sm text-smn-gris-700">{f.nota}</p>
              )}
            </div>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={f.puntos}
                disabled={!editar}
                onChange={(e) => cambiar(f.factor, { puntos: Number(e.target.value) })}
                className="w-40 accent-[var(--color-smn-naranja)]"
                aria-label={`Puntos de ${f.nombre}`}
              />
              <input
                type="number"
                min={0}
                max={100}
                value={f.puntos}
                disabled={!editar}
                onChange={(e) => cambiar(f.factor, { puntos: Math.max(0, Math.min(100, Number(e.target.value) || 0)) })}
                className="w-16 rounded-lg border border-smn-gris-300 bg-superficie px-2 py-1.5 text-right font-semibold outline-none focus:border-smn-naranja"
                aria-label={`Puntos de ${f.nombre} (número)`}
              />
            </div>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className={`font-semibold ${total === 100 ? "" : "text-red-700 dark:text-red-400"}`}>
          Total: {total} de 100 {total !== 100 && <span className="text-sm font-semibold">({total > 100 ? `sobran ${total - 100}` : `faltan ${100 - total}`})</span>}
        </p>
        {editar && (
          <Boton onClick={guardar} cargando={guardando} disabled={total !== 100}>
            <Save className="h-4 w-4" /> Guardar pesos
          </Boton>
        )}
      </div>
      <MensajeError texto={error} />
    </>
  );
}
