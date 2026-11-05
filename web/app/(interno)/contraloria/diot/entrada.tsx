"use client";
// TD003 · Entrada de la DIOT: primero la empresa, luego el año y el mes; el mes abre la corrida en 4 pasos.

import { AnimatePresence } from "motion/react";
import { Building2, ChevronRight, Lock, Plus } from "lucide-react";
import { useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { MESES, RUTA, type Empresa, type PeriodoResumen } from "@/lib/diot";
import { PERMISO_APROBAR } from "@/lib/diot-validacion";

const TARJETA = "rounded-2xl border border-smn-gris-100 bg-superficie";
const ESTADO: Record<PeriodoResumen["estado"], { texto: string; punto: string }> = {
  abierto: { texto: "Abierto, falta procesar", punto: "bg-smn-gris-500" },
  procesado: { texto: "Procesado, por cerrar", punto: "bg-amber-500" },
  cerrado: { texto: "Cerrado", punto: "bg-emerald-600" },
};
const RE_RFC = /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/;

const ordenar = (a: PeriodoResumen, b: PeriodoResumen) => b.anio - a.anio || b.mes - a.mes;

// ---------------------------------------------------------------- ruta de regreso

export function Ruta({ partes }: { partes: { texto: string; ir?: () => void }[] }) {
  return (
    <nav aria-label="Dónde estás" className="mt-6 flex flex-wrap items-center gap-1 text-[15px]">
      {partes.map((x, i) => (
        <span key={i} className="inline-flex items-center gap-1">
          {i > 0 && <ChevronRight className="h-4 w-4 text-smn-gris-500" />}
          {x.ir ? (
            <button onClick={x.ir} className="rounded-md px-1 font-medium text-smn-gris-700 underline-offset-4 hover:text-tinta hover:underline">
              {x.texto}
            </button>
          ) : (
            <span className="px-1 font-semibold text-tinta">{x.texto}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

// ---------------------------------------------------------------- nivel 1: empresas

export function Empresas({ empresas, periodos, elegir, alAgregar }: {
  empresas: Empresa[];
  periodos: PeriodoResumen[];
  elegir: (e: Empresa) => void;
  alAgregar: (e: Empresa) => void;
}) {
  const { puede } = useSesion();
  const [nueva, setNueva] = useState(false);
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold">Elige la empresa</h2>
      <p className="mt-1 text-[15px] text-smn-gris-700">Cada empresa presenta su propia DIOT. Después eliges el año y el mes.</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {empresas.map((e) => {
          const suyos = periodos.filter((x) => x.empresa.id === e.id).sort(ordenar);
          const ultimo = suyos[0];
          const pendientes = suyos.reduce((s, x) => s + (x.estado === "cerrado" ? 0 : x.pendientes), 0);
          return (
            <button
              key={e.id}
              onClick={() => elegir(e)}
              className={`${TARJETA} group flex flex-col p-5 text-left transition hover:border-smn-gris-300 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-smn-naranja/20`}
            >
              <span className="flex items-start justify-between gap-3">
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium text-smn-gris-500">{e.codigo}</span>
                  <span className="mt-0.5 block text-[17px] font-semibold leading-snug">{e.nombre}</span>
                </span>
                <ChevronRight className="mt-1 h-5 w-5 shrink-0 text-smn-gris-500 transition group-hover:translate-x-0.5 group-hover:text-tinta" />
              </span>
              <span className="mt-3 block text-[14px] text-smn-gris-700">
                {e.rfc ? (
                  <>RFC {e.rfc}</>
                ) : (
                  <span className="inline-flex items-center gap-1.5 font-medium text-amber-800 dark:text-amber-300">
                    <span className="h-2 w-2 rounded-full bg-amber-500" /> Falta el RFC
                  </span>
                )}
              </span>
              <span className="mt-4 block border-t border-smn-gris-100 pt-3 text-[14px] text-smn-gris-700">
                {ultimo ? (
                  <>
                    <span className="flex items-center gap-1.5">
                      <span className={`h-2 w-2 rounded-full ${ESTADO[ultimo.estado].punto}`} />
                      Último mes: {MESES[ultimo.mes - 1]} {ultimo.anio} · {ESTADO[ultimo.estado].texto.toLowerCase()}
                    </span>
                    <span className="mt-1 block text-[13px] text-smn-gris-500">
                      {suyos.length} {suyos.length === 1 ? "mes trabajado" : "meses trabajados"}
                      {pendientes > 0 && <span className="text-red-700 dark:text-red-400"> · {pendientes} por decidir</span>}
                    </span>
                  </>
                ) : (
                  <span className="text-smn-gris-500">Todavía sin meses trabajados</span>
                )}
              </span>
            </button>
          );
        })}
        {puede(PERMISO_APROBAR) && (
          <button
            onClick={() => setNueva(true)}
            className="flex min-h-40 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-smn-gris-300 p-5 text-smn-gris-700 transition hover:border-smn-naranja hover:text-tinta"
          >
            <span className="flex h-10 w-10 items-center justify-center rounded-full border border-smn-gris-100 bg-superficie">
              <Plus className="h-5 w-5" />
            </span>
            <span className="text-[15px] font-semibold">Agregar empresa</span>
            <span className="text-[13px] text-smn-gris-500">Otra razón social que presenta DIOT</span>
          </button>
        )}
      </div>
      <AnimatePresence>
        {nueva && (
          <AltaEmpresa
            cerrar={() => setNueva(false)}
            alGuardar={(e) => {
              setNueva(false);
              alAgregar(e);
            }}
          />
        )}
      </AnimatePresence>
    </section>
  );
}

function AltaEmpresa({ cerrar, alGuardar }: { cerrar: () => void; alGuardar: (e: Empresa) => void }) {
  const avisar = useAvisos();
  const [codigo, setCodigo] = useState("");
  const [nombre, setNombre] = useState("");
  const [rfc, setRfc] = useState("");
  const [guardando, setGuardando] = useState(false);
  const rfcMalo = rfc.length > 0 && !RE_RFC.test(rfc);
  const listo = /^[A-Z0-9_-]{2,20}$/.test(codigo) && nombre.trim().length >= 3 && !rfcMalo;
  const guardar = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!listo) return;
    setGuardando(true);
    try {
      const e = await api<Empresa>(`${RUTA}/empresas`, { cuerpo: { codigo, nombre: nombre.trim(), rfc: rfc || null } });
      avisar(`${e.nombre} quedó dada de alta.`, "exito");
      alGuardar(e);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setGuardando(false);
    }
  };
  return (
    <Modal titulo="Agregar empresa" cerrar={cerrar}>
      <form onSubmit={guardar} className="space-y-4">
        <Campo
          etiqueta="Clave corta"
          value={codigo}
          onChange={(e) => setCodigo(e.target.value.toUpperCase().replace(/\s/g, ""))}
          placeholder="Por ejemplo, ODP"
          maxLength={20}
          autoFocus
        />
        <Campo etiqueta="Razón social" value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Como aparece en la constancia fiscal" maxLength={200} />
        <Campo
          etiqueta="RFC (si ya lo tienes)"
          value={rfc}
          onChange={(e) => setRfc(e.target.value.toUpperCase().trim())}
          placeholder="12 caracteres"
          maxLength={13}
          error={rfcMalo ? "Ese RFC no tiene el formato del SAT." : undefined}
        />
        <p className="text-[14px] text-smn-gris-700">
          Sin RFC la empresa se da de alta, pero no se puede procesar su DIOT hasta que Fiscal lo confirme.
        </p>
        <div className="flex justify-end gap-2 pt-2">
          <Boton type="button" variante="secundario" onClick={cerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" cargando={guardando} disabled={!listo}>
            Dar de alta
          </Boton>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------- nivel 2: año y mes

export function Meses({ empresa, periodos, anio, setAnio, opera, ocupado, abrir, crear, children }: {
  empresa: Empresa;
  periodos: PeriodoResumen[];
  anio: number;
  setAnio: (a: number) => void;
  opera: boolean;
  ocupado: number | null;
  abrir: (id: number) => void;
  crear: (mes: number) => void;
  children?: React.ReactNode;
}) {
  const hoy = new Date();
  const suyos = periodos.filter((x) => x.empresa.id === empresa.id);
  const anios = [...new Set([hoy.getFullYear(), hoy.getFullYear() - 1, hoy.getFullYear() - 2, ...suyos.map((x) => x.anio)])].sort((a, b) => b - a);
  const delAnio = new Map(suyos.filter((x) => x.anio === anio).map((x) => [x.mes, x]));
  return (
    <section className="mt-4">
      <div className={`${TARJETA} p-5`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-smn-gris-100 bg-superficie text-smn-naranja">
              <Building2 className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <p className="text-[13px] font-medium text-smn-gris-500">{empresa.codigo}</p>
              <p className="text-[17px] font-semibold leading-snug">{empresa.nombre}</p>
            </div>
          </div>
          <div role="tablist" aria-label="Año" className="flex max-w-full gap-1 overflow-x-auto rounded-lg border border-smn-gris-100 p-1">
            {anios.map((a) => (
              <button
                key={a}
                role="tab"
                aria-selected={a === anio}
                onClick={() => setAnio(a)}
                className={`rounded-md px-3.5 py-1.5 text-[15px] font-medium transition ${a === anio ? "bg-tinta text-superficie" : "text-smn-gris-700 hover:bg-smn-gris-100"}`}
              >
                {a}
              </button>
            ))}
          </div>
        </div>
        {children}
      </div>

      <h2 className="mt-8 text-lg font-semibold">Elige el mes de {anio}</h2>
      <p className="mt-1 text-[15px] text-smn-gris-700">Un mes sin abrir se abre al elegirlo; uno ya trabajado regresa a donde se quedó.</p>
      <ol className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {MESES.map((nombre, i) => {
          const mes = i + 1;
          const x = delAnio.get(mes);
          const futuro = anio > hoy.getFullYear() || (anio === hoy.getFullYear() && mes > hoy.getMonth());
          const bloqueado = !x && (futuro || !opera);
          return (
            <li key={mes}>
              <button
                disabled={bloqueado || ocupado !== null}
                onClick={() => (x ? abrir(x.id) : crear(mes))}
                title={futuro && !x ? "Ese mes todavía no termina." : !x && !opera ? "No tienes permiso para abrir meses." : undefined}
                className={`flex h-full min-h-24 w-full flex-col justify-between rounded-xl border p-4 text-left transition focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-smn-naranja/20 ${
                  x ? "border-smn-gris-100 bg-superficie hover:border-smn-gris-300" : "border-dashed border-smn-gris-100 hover:border-smn-gris-300"
                } disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-smn-gris-100`}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="text-[16px] font-semibold">{nombre}</span>
                  {x?.estado === "cerrado" && <Lock className="h-4 w-4 text-smn-gris-500" />}
                </span>
                <span className="mt-3 text-[13px] text-smn-gris-700">
                  {ocupado === mes ? (
                    "Abriendo…"
                  ) : x ? (
                    <>
                      <span className="flex items-center gap-1.5">
                        <span className={`h-2 w-2 shrink-0 rounded-full ${ESTADO[x.estado].punto}`} /> {ESTADO[x.estado].texto}
                      </span>
                      {x.estado !== "cerrado" && x.pendientes > 0 && (
                        <span className="mt-0.5 block font-medium text-red-700 dark:text-red-400">{x.pendientes} por decidir</span>
                      )}
                    </>
                  ) : futuro ? (
                    <span className="text-smn-gris-500">Aún no termina</span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-smn-gris-500">
                      <span className="h-2 w-2 shrink-0 rounded-full border border-smn-gris-500" /> Sin abrir
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
