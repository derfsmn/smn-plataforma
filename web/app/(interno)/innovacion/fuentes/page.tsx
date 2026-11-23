"use client";
// Fuentes de la base de conocimiento: búsqueda por sección (palabras + significado, solo lo que la persona puede ver)
// y la lista con filtros por tipo, estado e ingrediente.

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FilePlus2, Search } from "lucide-react";
import { Suspense, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Encabezado, Esqueleto, Selector } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { P, RUTA, TIPOS, type Busqueda, type FilaRecurso, type Ingrediente } from "@/lib/innovacion";
import { AREA, ChipClasificacion, ChipFuente, MenuModulo, SinAcceso, TARJETA, Vacio } from "../comunes";

export default function Pagina() {
  return (
    <Suspense fallback={<Esqueleto className="h-64" />}>
      <Fuentes />
    </Suspense>
  );
}

function Fuentes() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const params = useSearchParams();
  const router = useRouter();
  const q = params.get("q") ?? "";
  const [texto, setTexto] = useState(q);
  const [tipo, setTipo] = useState(params.get("tipo") ?? "");
  const [estado, setEstado] = useState(params.get("estado") ?? "");
  const [ingrediente, setIngrediente] = useState(params.get("ingrediente") ?? "");
  const [ingredientes, setIngredientes] = useState<Ingrediente[]>([]);
  const [busqueda, setBusqueda] = useState<Busqueda | null>(null);
  const [lista, setLista] = useState<{ total: number; recursos: FilaRecurso[] } | null>(null);

  useEffect(() => {
    if (puede(P.ver)) api<Ingrediente[]>(`${RUTA}/ingredientes`).then(setIngredientes).catch(() => {});
  }, [puede]);

  useEffect(() => {
    if (!puede(P.ver)) return;
    const p = new URLSearchParams();
    if (tipo) p.set("tipo", tipo);
    if (estado) p.set("estado", estado);
    if (ingrediente) p.set("ingrediente", ingrediente);
    if (q.length >= 2) {
      p.set("q", q);
      setBusqueda(null);
      api<Busqueda>(`${RUTA}/buscar?${p}`).then(setBusqueda).catch((e) => avisar(mensajeDe(e), "info"));
    } else {
      setBusqueda(null);
      api<{ total: number; recursos: FilaRecurso[] }>(`${RUTA}/recursos?${p}`).then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
    }
  }, [q, tipo, estado, ingrediente, puede, avisar]);

  if (!puede(P.ver)) return <SinAcceso />;
  return (
    <>
      <Encabezado
        titulo="Fuentes"
        descripcion="Artículos, ensayos, normas, fichas técnicas y pruebas internas. Una fuente solo respalda algo cuando ya está revisada."
        accion={
          puede(P.cargar) && (
            <Link href="/innovacion/fuentes/nueva" className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[var(--resalte)] px-4 py-2 text-[15px] font-medium text-[var(--resalte-tinta)]">
              <FilePlus2 className="h-4 w-4" /> Cargar fuente
            </Link>
          )
        }
      />
      <MenuModulo />
      <form
        className={`${TARJETA} grid gap-3`}
        onSubmit={(e) => {
          e.preventDefault();
          router.replace(texto.trim().length >= 2 ? `/innovacion/fuentes?q=${encodeURIComponent(texto.trim())}` : "/innovacion/fuentes");
        }}
      >
        <div className="flex gap-2">
          <input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Busca por ingrediente, sinónimo, forma química o tema" aria-label="Buscar" className={AREA} />
          <button type="submit" aria-label="Buscar" className="rounded-lg bg-[var(--resalte)] px-4 text-[var(--resalte-tinta)]"><Search className="h-4 w-4" /></button>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Selector etiqueta="Tipo" valor={tipo} cambiar={setTipo} opciones={[{ valor: "", texto: "Todos" }, ...Object.entries(TIPOS).map(([valor, texto]) => ({ valor, texto }))]} />
          <Selector etiqueta="Estado" valor={estado} cambiar={setEstado}
            opciones={[{ valor: "", texto: "Todos" }, { valor: "revisado", texto: "Revisadas" }, { valor: "pendiente", texto: "Pendientes de revisión" }]} />
          <Selector etiqueta="Ingrediente" valor={ingrediente} cambiar={setIngrediente}
            opciones={[{ valor: "", texto: "Todos" }, ...ingredientes.map((i) => ({ valor: String(i.id), texto: i.nombre }))]} />
        </div>
      </form>

      <div className="mt-5">
        {q.length >= 2 ? (
          !busqueda ? (
            <Esqueleto className="h-40" />
          ) : (
            <>
              <p className="mb-3 text-sm text-smn-gris-500">
                {busqueda.total} secciones para «{q}» · {busqueda.con_significado ? "por palabras y por significado" : "solo por palabras (IA local apagada)"}
              </p>
              {busqueda.resultados.length === 0 ? (
                <Vacio>No hay secciones que hablen de eso. Prueba con un sinónimo o investiga en internet.</Vacio>
              ) : (
                <div className="grid gap-3">
                  {busqueda.resultados.map((h) => (
                    <Link key={h.fragmento_id} href={`/innovacion/fuentes/${h.recurso_id}?seccion=${h.fragmento_id}`} className={`${TARJETA} block hover:border-smn-gris-300`}>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold">{h.titulo}</span>
                        <ChipFuente estado={h.estado} />
                        <ChipClasificacion valor={h.clasificacion} />
                      </div>
                      <p className="mt-0.5 text-[13px] text-smn-gris-500">
                        {TIPOS[h.tipo] ?? h.tipo} · versión {h.version}{h.pagina ? ` · pág. ${h.pagina}` : ""}{h.seccion ? ` · ${h.seccion}` : ""}{h.folio ? ` · ${h.folio}` : ""}
                      </p>
                      <p className="mt-2 line-clamp-3 text-[15px] text-smn-gris-700">{h.extracto}</p>
                    </Link>
                  ))}
                </div>
              )}
            </>
          )
        ) : !lista ? (
          <Esqueleto className="h-40" />
        ) : lista.recursos.length === 0 ? (
          <Vacio>No hay fuentes con esos filtros.</Vacio>
        ) : (
          <div className={`${TARJETA} divide-y divide-smn-gris-100 p-0`}>
            {lista.recursos.map((r) => (
              <Link key={r.id} href={`/innovacion/fuentes/${r.id}`} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 hover:bg-smn-gris-50">
                <span>
                  <span className="block font-medium">{r.titulo}</span>
                  <span className="block text-[13px] text-smn-gris-500">
                    {TIPOS[r.tipo] ?? r.tipo}{r.anio ? ` · ${r.anio}` : ""} · versión {r.version}{r.folio ? ` · ${r.folio}` : ""}
                    {r.procesado !== "listo" ? ` · lectura: ${r.procesado}` : ""}
                  </span>
                </span>
                <span className="flex gap-2"><ChipClasificacion valor={r.clasificacion} /><ChipFuente estado={r.estado} /></span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
