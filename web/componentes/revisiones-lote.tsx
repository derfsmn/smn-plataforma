"use client";

// Revisiones por lote del radar de productos, para no ir producto por producto (Diego, 25 y 26 nov 2026): cuántas
// evaluaciones se quedaron con pocos parecidos y cómo va la prueba de precios de afuera. Cada una baja su Excel.
import { Download, Layers } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { descargar } from "@/lib/precios";

type Parecidos = { evaluaciones: number; sin_parecidos: number; uno: number; dos: number; tres_o_mas: number; afectadas: number };
type Afuera = { regla: number; corriendo: boolean; avance: { hechos: number; total: number }; resultado: { total: number; encontrados: number; pct: number | null } | null; excel: boolean; error: string | null };

function Boton({ onClick, children, deshabilitado }: { onClick: () => void; children: React.ReactNode; deshabilitado?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={deshabilitado}
      className="inline-flex items-center gap-1.5 rounded-full border border-smn-gris-300 px-3 py-1.5 text-sm font-semibold hover:bg-smn-gris-50 disabled:opacity-50"
    >
      <Download className="h-4 w-4" /> {children}
    </button>
  );
}

function Dato({ n, texto, alerta }: { n: number | string; texto: string; alerta?: boolean }) {
  return (
    <div className={`rounded-xl px-3 py-2 ${alerta ? "bg-aviso-fondo text-aviso-texto" : "bg-smn-gris-50"}`}>
      <p className="text-xl font-semibold tabular-nums">{n}</p>
      <p className="text-[13px] opacity-80">{texto}</p>
    </div>
  );
}

export function RevisionesLote() {
  const [par, setPar] = useState<Parecidos | null>(null);
  const [afu, setAfu] = useState<Afuera | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bajando, setBajando] = useState<string | null>(null);

  useEffect(() => {
    api<Parecidos>("/api/compras/productos/revision-parecidos").then(setPar).catch((e: Error) => setError(e.message));
    api<Afuera>("/api/compras/productos/prueba-afuera").then(setAfu).catch(() => undefined);
  }, []);

  const bajar = (ruta: string, nombre: string) => {
    setBajando(nombre);
    descargar(ruta, nombre)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBajando(null));
  };

  return (
    <section className="mt-8 rounded-2xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
      <div className="flex items-center gap-2">
        <Layers className="h-5 w-5 text-smn-naranja" />
        <h2 className="text-lg font-semibold">Revisiones por lote del radar de productos</h2>
      </div>
      <p className="mt-0.5 mb-4 text-sm text-smn-gris-500">Para ver de un jalón qué evaluaciones salieron mal y por qué, sin abrirlas una por una.</p>
      {error && <p className="mb-3 rounded-xl bg-aviso-fondo px-3 py-2 text-sm text-aviso-texto">{error}</p>}
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="font-semibold">Parecidos de cada evaluación</h3>
          <p className="mb-3 text-sm text-smn-gris-500">
            «Afectadas» son las que tienen menos de 3 parecidos aunque vendemos productos con su ingrediente principal (como los colágenos). Después de «Recalcular todas» deben quedar en casi cero.
          </p>
          {par ? (
            <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Dato n={par.evaluaciones} texto="evaluaciones vigentes" />
              <Dato n={par.sin_parecidos} texto="sin ningún parecido" alerta={par.sin_parecidos > 0} />
              <Dato n={par.uno + par.dos} texto="con 1 o 2" />
              <Dato n={par.afectadas} texto="afectadas" alerta={par.afectadas > 0} />
            </div>
          ) : (
            !error && <p className="mb-3 text-sm text-smn-gris-500">Contando…</p>
          )}
          <Boton onClick={() => bajar("/api/compras/productos/revision-parecidos/excel", "revision_parecidos.xlsx")} deshabilitado={bajando !== null}>
            {bajando === "revision_parecidos.xlsx" ? "Armando…" : "Descargar Excel"}
          </Boton>
        </div>
        <div>
          <h3 className="font-semibold">Precios de afuera</h3>
          <p className="mb-3 text-sm text-smn-gris-500">60 productos buscados en Google y las tiendas, en la noche; cuántos encontró y por qué no los demás.</p>
          {afu && (
            <p className="mb-3 text-sm">
              {afu.resultado
                ? `Con precio de afuera: ${afu.resultado.encontrados} de ${afu.resultado.total}${afu.resultado.pct !== null ? ` (${afu.resultado.pct} %)` : ""}.`
                : afu.corriendo
                  ? `Corriendo: ${afu.avance.hechos} de ${afu.avance.total}.`
                  : afu.error ?? "Todavía no corre: empieza sola en la noche, cuando no haya evaluaciones."}
            </p>
          )}
          <Boton onClick={() => bajar("/api/compras/productos/prueba-afuera/excel", `prueba_precios_afuera_regla${afu?.regla ?? ""}.xlsx`)} deshabilitado={!afu?.excel || bajando !== null}>
            Descargar Excel
          </Boton>
        </div>
      </div>
    </section>
  );
}
