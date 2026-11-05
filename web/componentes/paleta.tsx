"use client";
// Buscador de comandos (Ctrl + K / ⌘ K): brinca a cualquier pantalla que la persona puede ver, pregunta a los
// manuales o cambia el tema. Solo lista lo que su menú ya le permite; no consulta datos.

import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { CornerDownLeft, LogOut, Moon, Search, Sparkles, Sun, UserRound } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cambiarTema } from "@/lib/tema";
import { sinAcentos } from "@/lib/inicio";

export type EntradaPaleta = { texto: string; grupo: string; href: string; icono: typeof Search; palabras?: string };

type Opcion = { id: string; texto: string; grupo: string; icono: typeof Search; hacer: () => void; detalle?: string };

export function usePaleta() {
  const [abierta, setAbierta] = useState(false);
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setAbierta((v) => !v);
      }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, []);
  return { abierta, abrir: () => setAbierta(true), cerrar: () => setAbierta(false) };
}

export function Paleta({
  abierta,
  cerrar,
  entradas,
  preguntar,
  salir,
}: {
  abierta: boolean;
  cerrar: () => void;
  entradas: EntradaPaleta[];
  preguntar: boolean;
  salir: () => void;
}) {
  const router = useRouter();
  const [texto, setTexto] = useState("");
  const [indice, setIndice] = useState(0);
  const refLista = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (abierta) {
      setTexto("");
      setIndice(0);
    }
  }, [abierta]);

  const ir = useCallback(
    (href: string) => {
      cerrar();
      router.push(href);
    },
    [cerrar, router],
  );

  const opciones = useMemo<Opcion[]>(() => {
    const q = sinAcentos(texto.trim());
    const coincide = (t: string) => !q || q.split(/\s+/).every((p) => sinAcentos(t).includes(p));
    const lista: Opcion[] = entradas
      .filter((e) => coincide(`${e.texto} ${e.grupo} ${e.palabras ?? ""}`))
      .map((e) => ({ id: e.href, texto: e.texto, grupo: e.grupo, icono: e.icono, hacer: () => ir(e.href) }));
    if (preguntar && q.length >= 3) {
      lista.push({
        id: "preguntar",
        texto: `Preguntar a los manuales: «${texto.trim()}»`,
        grupo: "Acciones",
        icono: Sparkles,
        detalle: "IA local, responde con cita",
        hacer: () => ir(`/metodos?q=${encodeURIComponent(texto.trim())}`),
      });
    }
    const acciones: Opcion[] = [
      { id: "claro", texto: "Cambiar a modo claro", grupo: "Acciones", icono: Sun, hacer: () => { cambiarTema("claro"); cerrar(); } },
      { id: "oscuro", texto: "Cambiar a modo oscuro", grupo: "Acciones", icono: Moon, hacer: () => { cambiarTema("oscuro"); cerrar(); } },
      { id: "perfil", texto: "Mi perfil", grupo: "Acciones", icono: UserRound, hacer: () => ir("/perfil") },
      { id: "salir", texto: "Cerrar sesión", grupo: "Acciones", icono: LogOut, hacer: () => { cerrar(); salir(); } },
    ];
    return [...lista, ...acciones.filter((a) => coincide(a.texto))];
  }, [entradas, texto, preguntar, ir, cerrar, salir]);

  useEffect(() => setIndice(0), [texto]);
  useEffect(() => {
    refLista.current?.querySelector(`[data-i="${indice}"]`)?.scrollIntoView({ block: "nearest" });
  }, [indice]);

  const tecla = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIndice((i) => Math.min(i + 1, opciones.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIndice((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      opciones[indice]?.hacer();
    } else if (e.key === "Escape") {
      cerrar();
    }
  };

  let grupoAnterior = "";
  return (
    <AnimatePresence>
      {abierta && (
        <motion.div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh] font-sobria" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
          <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={cerrar} />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Buscar o ir a"
            className="relative w-full max-w-xl overflow-hidden rounded-xl border border-smn-gris-100 bg-superficie shadow-2xl shadow-black/20"
            initial={{ opacity: 0, scale: 0.98, y: -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: -6 }}
            transition={{ duration: 0.15 }}
          >
            <div className="flex items-center gap-3 border-b border-smn-gris-100 px-4">
              <Search className="h-4 w-4 shrink-0 text-smn-gris-500" />
              <input
                autoFocus
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={tecla}
                placeholder={preguntar ? "Busca una pantalla o escribe una pregunta…" : "Busca una pantalla…"}
                className="h-12 flex-1 bg-transparent text-[15px] outline-none placeholder:text-smn-gris-500"
                aria-controls="paleta-lista"
              />
              <kbd className="rounded border border-smn-gris-100 px-1.5 text-[13px] text-smn-gris-500">Esc</kbd>
            </div>
            <ul id="paleta-lista" ref={refLista} role="listbox" className="max-h-[50vh] overflow-y-auto p-1.5">
              {opciones.length === 0 && <li className="px-3 py-8 text-center text-sm text-smn-gris-500">No encontré nada con «{texto}».</li>}
              {opciones.map((o, i) => {
                const titulo = o.grupo !== grupoAnterior ? o.grupo : null;
                grupoAnterior = o.grupo;
                const Icono = o.icono;
                return (
                  <li key={o.id} role="presentation">
                    {titulo && <p className="px-2.5 pt-2.5 pb-1 text-[13px] font-medium text-smn-gris-500">{titulo}</p>}
                    <button
                      role="option"
                      aria-selected={i === indice}
                      data-i={i}
                      onMouseMove={() => setIndice(i)}
                      onClick={o.hacer}
                      className={`flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left text-sm ${i === indice ? "bg-smn-gris-50 text-tinta" : "text-smn-gris-700"}`}
                    >
                      <Icono className={`h-4 w-4 shrink-0 ${i === indice ? "text-smn-naranja" : "text-smn-gris-500"}`} />
                      <span className="min-w-0 flex-1 truncate">{o.texto}</span>
                      {o.detalle && <span className="text-[13px] text-smn-gris-500">{o.detalle}</span>}
                      {i === indice && <CornerDownLeft className="h-3.5 w-3.5 text-smn-gris-500" />}
                    </button>
                  </li>
                );
              })}
            </ul>
            <div className="flex items-center gap-4 border-t border-smn-gris-100 px-4 py-2 text-[13px] text-smn-gris-500">
              <span>↑ ↓ para moverte</span>
              <span>Enter para abrir</span>
              <span className="ml-auto">Ctrl K para abrir o cerrar</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
