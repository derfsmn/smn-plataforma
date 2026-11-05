"use client";
// TD003 · Proceso de la DIOT en 4 pasos (subir y procesar, pendientes, validar, firmar) y la vista técnica para Fiscal.

import Link from "next/link";
import { AnimatePresence } from "motion/react";
import { AlertTriangle, ArrowLeft, CheckCircle2, CircleDashed, FileUp, Play, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { PreguntaManuales } from "@/componentes/pregunta-manuales";
import { Boton, Campo, Encabezado, Entrada, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { PERMISO_APROBAR, type Comprobaciones } from "@/lib/diot-validacion";
import { PasosDelProceso } from "./corrida";
import { Empresas, Meses, Ruta } from "./entrada";
import { Cabecera, Firmar, Pendientes, Proveedores, Validar, type Vista } from "./guia";
import {
  CAMPOS, IMPACTOS, MESES, PERMISO_OPERAR, RUTA, pesos, subir,
  type Ajuste, type Carga, type Empresa, type Catalogos, type Impacto, type Incidencia, type Operacion, type Periodo, type PeriodoResumen, type ResultadoArchivo, type Tercero,
} from "@/lib/diot";

const TARJETA = "rounded-2xl border border-smn-gris-100 bg-superficie p-5";
const PESTANAS = [
  { valor: "incidencias", texto: "Incidencias" },
  { valor: "consolidado", texto: "Consolidado por tercero" },
  { valor: "ajustes", texto: "Ajustes de Fiscal" },
  { valor: "comparacion", texto: "Comparar con TXT presentado" },
] as const;
type Pestana = (typeof PESTANAS)[number]["valor"];

export default function ProcesoDiot() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const opera = puede(PERMISO_OPERAR);
  const [cat, setCat] = useState<Catalogos | null>(null);
  const [lista, setLista] = useState<PeriodoResumen[]>([]);
  const [empresaId, setEmpresaId] = useState<number | null>(null);
  const [anio, setAnio] = useState(new Date().getFullYear());
  const [abriendo, setAbriendo] = useState<number | null>(null); // mes que se está abriendo
  const [p, setP] = useState<Periodo | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [pestana, setPestana] = useState<Pestana>("incidencias");
  const [version, setVersion] = useState(0); // cambia cada vez que el periodo se reprocesa
  const [vista, setVista] = useState<Vista>(1);
  const [c, setC] = useState<Comprobaciones | null>(null);
  const abierto = useRef<number | null>(null); // periodo cuyo paso inicial ya se eligió

  const cargarLista = useCallback(
    () => api<PeriodoResumen[]>(`${RUTA}/periodos`).then(setLista).catch((e) => avisar(mensajeDe(e), "info")),
    [avisar],
  );
  useEffect(() => {
    api<Catalogos>(`${RUTA}/catalogos`)
      .then(setCat)
      .catch((e) => avisar(mensajeDe(e), "info"));
    cargarLista();
  }, [avisar, cargarLista]);

  const poner = (x: Periodo) => {
    if (x.id !== p?.id) setC(null);
    setP(x);
    setVersion((v) => v + 1);
    cargarLista();
  };
  const abrir = (id: number) => api<Periodo>(`${RUTA}/periodos/${id}`).then(poner).catch((e) => avisar(mensajeDe(e), "info"));
  const accion = async (clave: string, f: () => Promise<Periodo | void>, exito?: string) => {
    setOcupado(clave);
    try {
      const r = await f();
      if (r) poner(r);
      if (exito) avisar(exito, "exito");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };

  // Las comprobaciones se recalculan cada vez que cambia el periodo; al abrir uno se va al paso en que va.
  const pid = p?.id;
  useEffect(() => {
    if (!pid) return;
    api<Comprobaciones>(`${RUTA}/periodos/${pid}/comprobaciones`)
      .then((x) => {
        setC(x);
        if (abierto.current !== pid) {
          abierto.current = pid;
          setVista(Math.min(x.paso, 4) as Vista);
        }
      })
      .catch((e) => avisar(mensajeDe(e), "info"));
  }, [pid, version, avisar]);

  const crear = async (mes: number) => {
    if (!empresaId) return;
    setAbriendo(mes);
    try {
      poner(await api<Periodo>(`${RUTA}/periodos`, { cuerpo: { empresa_id: empresaId, anio, mes } }));
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setAbriendo(null);
    }
  };
  const cerrarPeriodo = () => {
    setP(null);
    setC(null);
    abierto.current = null;
  };
  const elegirEmpresa = (id: number) => {
    const suyos = lista.filter((x) => x.empresa.id === id);
    setAnio(suyos.length ? Math.max(...suyos.map((x) => x.anio)) : new Date().getFullYear());
    setEmpresaId(id);
  };

  if (!cat) return <Esqueleto className="h-64" />;
  const empresa = cat.empresas.find((e) => e.id === empresaId) ?? null;
  const irEmpresas = () => {
    cerrarPeriodo();
    setEmpresaId(null);
  };
  return (
    <>
      <Link href="/modulos/contraloria" className="mb-6 inline-flex items-center gap-1 text-sm font-semibold text-smn-gris-500 hover:text-tinta">
        <ArrowLeft className="h-4 w-4" /> Contraloría y Fiscal
      </Link>
      <Encabezado
        titulo="Proceso de la DIOT"
        descripcion="Cuatro pasos: sube y procesa los reportes del mes, resuelve lo que pide una decisión, valida el resultado con 9 comprobaciones en palabras y firma antes de descargar el TXT para el SAT."
        accion={<PreguntaManuales origen="contraloria.diot" texto="¿Dudas del proceso? Pregunta a los manuales" />}
      />

      {!empresa ? (
        <Empresas
          empresas={cat.empresas}
          periodos={lista}
          elegir={(e) => elegirEmpresa(e.id)}
          alAgregar={(e) => setCat({ ...cat, empresas: [...cat.empresas, e].sort((a, b) => a.codigo.localeCompare(b.codigo)) })}
        />
      ) : !p ? (
        <>
          <Ruta partes={[{ texto: "Empresas", ir: irEmpresas }, { texto: empresa.codigo }]} />
          <Meses empresa={empresa} periodos={lista} anio={anio} setAnio={setAnio} opera={opera} ocupado={abriendo} abrir={abrir} crear={crear}>
            <div className="mt-4">
              <RfcEmpresa empresa={empresa} alGuardar={(e) => setCat({ ...cat, empresas: cat.empresas.map((x) => (x.id === e.id ? e : x)) })} />
            </div>
          </Meses>
        </>
      ) : (
        <Ruta
          partes={[
            { texto: "Empresas", ir: irEmpresas },
            { texto: p.empresa.codigo, ir: () => { setAnio(p.anio); cerrarPeriodo(); } },
            { texto: String(p.anio), ir: () => { setAnio(p.anio); cerrarPeriodo(); } },
            { texto: MESES[p.mes - 1] },
          ]}
        />
      )}

      {p && (
        <>
          <Cabecera p={p} c={c} vista={vista} setVista={setVista} />
          {vista === 1 && (
            <>
              <Documentos p={p} cat={cat} opera={opera} poner={poner} />
              <Proceso
                p={p}
                opera={opera}
                ocupado={ocupado}
                accion={accion}
                alBorrar={() => {
                  cerrarPeriodo();
                  cargarLista();
                }}
              />
              <PasosDelProceso p={p} alTerminar={() => abrir(p.id)} />
            </>
          )}
          {vista === 2 && <Pendientes key={version} p={p} alCambiar={() => abrir(p.id)} irAjustes={() => { setPestana("ajustes"); setVista("fiscal"); }} />}
          {vista === 3 && <Validar p={p} c={c} setC={setC} />}
          {vista === 4 && <Firmar p={p} c={c} setC={setC} accion={accion} ocupado={ocupado} />}
          {vista === "proveedores" && <Proveedores key={version} p={p} />}
          {vista === "fiscal" && (
            <Entrada retraso={0.05} className="mt-6">
              {!p.procesado_en ? (
                <p className={`${TARJETA} text-sm text-smn-gris-500`}>Primero sube los reportes y procesa el mes (paso 1).</p>
              ) : (
                <>
                  <Cuadres p={p} />
                  <div className="mb-4 mt-6 flex flex-wrap gap-2">
                    {PESTANAS.map((t) => (
                      <button
                        key={t.valor}
                        onClick={() => setPestana(t.valor)}
                        className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${pestana === t.valor ? "bg-tinta text-superficie" : "bg-superficie text-smn-gris-700 hover:bg-smn-gris-100"}`}
                      >
                        {t.texto}
                        {t.valor === "incidencias" && p.pendientes > 0 && <span className="ml-1.5 text-red-400">{p.pendientes}</span>}
                      </button>
                    ))}
                  </div>
                  {pestana === "incidencias" && <Incidencias key={version} p={p} opera={opera} alCambiar={() => abrir(p.id)} />}
                  {pestana === "consolidado" && <Consolidado key={version} p={p} />}
                  {pestana === "ajustes" && <Ajustes p={p} cat={cat} opera={opera} alCambiar={() => abrir(p.id)} />}
                  {pestana === "comparacion" && <Comparar p={p} opera={opera} poner={poner} />}
                </>
              )}
            </Entrada>
          )}
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------- RFC de la empresa

function RfcEmpresa({ empresa, alGuardar }: { empresa: Empresa | undefined; alGuardar: (e: Empresa) => void }) {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [rfc, setRfc] = useState("");
  const [guardando, setGuardando] = useState(false);
  if (!empresa) return null;
  if (empresa.rfc) return <p className="text-[13px] text-smn-gris-500 sm:col-span-4">RFC de {empresa.codigo}: {empresa.rfc}</p>;
  const guardar = async () => {
    setGuardando(true);
    try {
      alGuardar(await api<Empresa>(`${RUTA}/empresas/${empresa.id}`, { metodo: "PATCH", cuerpo: { rfc: rfc.trim().toUpperCase() } }));
      setRfc("");
      avisar("RFC guardado.", "exito");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setGuardando(false);
    }
  };
  return (
    <div className="rounded-2xl bg-amber-50 p-3 text-sm text-amber-900 sm:col-span-4 dark:bg-amber-950/30 dark:text-amber-200">
      <p>
        Falta el RFC de {empresa.nombre}. Sin él no se puede procesar, porque con el RFC se separan los pagos de la empresa a sí misma. Pídelo a Fiscal.
      </p>
      {puede(PERMISO_APROBAR) && (
        <div className="mt-2 flex flex-wrap gap-2">
          <input value={rfc} onChange={(e) => setRfc(e.target.value.toUpperCase())} placeholder="RFC (12 caracteres)" maxLength={13} className="w-48 rounded-xl border border-smn-gris-300 bg-superficie px-3 py-1.5 text-sm text-tinta outline-none focus:border-smn-naranja" />
          <Boton variante="secundario" className="py-1.5" onClick={guardar} cargando={guardando} disabled={rfc.trim().length < 12}>
            Guardar RFC
          </Boton>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- documentos

function Documentos({ p, cat, opera, poner }: { p: Periodo; cat: Catalogos; opera: boolean; poner: (x: Periodo) => void }) {
  const avisar = useAvisos();
  const entrada = useRef<HTMLInputElement>(null);
  const [tipoManual, setTipoManual] = useState<string>("");
  const [avance, setAvance] = useState<string | null>(null);
  const [resultados, setResultados] = useState<ResultadoArchivo[]>([]);
  const cerrado = p.estado === "cerrado";
  const porTipo = useMemo(() => Object.fromEntries(p.documentos.map((d) => [d.tipo, d])), [p.documentos]);
  const todosDe = (tipo: string) => p.documentos.filter((d) => d.tipo === tipo);

  const elegir = (tipo = "") => {
    setTipoManual(tipo);
    entrada.current?.click();
  };
  const subirTodos = async (archivos: FileList | null) => {
    if (!archivos) return;
    const todos: ResultadoArchivo[] = [];
    for (const a of Array.from(archivos)) {
      setAvance(`${a.name}: 0 %`);
      try {
        const r = await subir<Carga>(`${RUTA}/periodos/${p.id}/documentos`, a, tipoManual ? { tipo: tipoManual } : {}, (x) =>
          setAvance(x < 100 ? `${a.name}: ${x} %` : `Leyendo ${a.name}…`),
        );
        poner(r.periodo);
        todos.push(...r.archivos);
      } catch (e) {
        todos.push({ archivo: a.name, resultado: "error", tipo: null, tipo_nombre: null, mensaje: mensajeDe(e) });
      }
    }
    setResultados(todos);
    setAvance(null);
    if (entrada.current) entrada.current.value = "";
  };
  const quitar = (id: number) =>
    api<Periodo>(`${RUTA}/periodos/${p.id}/documentos/${id}`, { metodo: "DELETE" }).then(poner).catch((e) => avisar(mensajeDe(e), "info"));

  return (
    <Entrada retraso={0.03} className={`${TARJETA} mt-6`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">
            {p.empresa.codigo} · {p.nombre}
          </h2>
          <p className="text-sm text-smn-gris-500">
            Sube los archivos como los entrega Fiscal: los reportes del portal, el papel de trabajo completo, los estados de cuenta, los archivos del SAT, el TXT presentado o un .zip con todo.
            El sistema reconoce cada uno y del papel de trabajo toma solo las hojas que vienen tal cual de Intelisis.
            {p.faltan.length > 0 && <span className="font-semibold text-red-700"> Faltan {p.faltan.length} obligatorios.</span>}
          </p>
        </div>
        {opera && !cerrado && (
          <Boton variante="secundario" onClick={() => elegir()} cargando={!!avance}>
            <FileUp className="h-4 w-4" /> {avance ?? "Subir reportes"}
          </Boton>
        )}
        <input ref={entrada} type="file" multiple accept=".xls,.xlsx,.csv,.txt,.zip" className="hidden" onChange={(e) => subirTodos(e.target.files)} />
      </div>
      {resultados.length > 0 && (
        <div className="mt-4 rounded-2xl bg-smn-gris-100/60 p-3 text-sm">
          <div className="mb-1 flex items-center justify-between">
            <p className="font-semibold">Última carga</p>
            <button onClick={() => setResultados([])} className="text-[13px] font-medium text-smn-gris-500 hover:text-tinta">
              Ocultar
            </button>
          </div>
          <ul className="space-y-1">
            {resultados.map((r, k) => (
              <li key={k} className="flex gap-2">
                <span className={`shrink-0 font-semibold ${r.resultado === "error" ? "text-red-700" : r.resultado === "no_se_usa" ? "text-smn-gris-500" : "text-green-700"}`}>
                  {r.resultado === "documento" ? "✓" : r.resultado === "referencia" ? "↔" : r.resultado === "no_se_usa" ? "–" : "✕"}
                </span>
                <span className="min-w-0">
                  <span className="font-semibold break-all">{r.archivo}</span>
                  <span className="text-smn-gris-500"> · {r.mensaje}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <ul className="mt-4 divide-y divide-smn-gris-100">
        {cat.tipos.map((t) => {
          const d = porTipo[t.codigo];
          return (
            <li key={t.codigo} className="flex flex-wrap items-center gap-3 py-3">
              {d ? (
                <CheckCircle2 className="h-5 w-5 shrink-0 text-green-600" />
              ) : t.obligatorio ? (
                <AlertTriangle className="h-5 w-5 shrink-0 text-red-500" />
              ) : (
                <CircleDashed className="h-5 w-5 shrink-0 text-smn-gris-500" />
              )}
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {t.nombre} {!t.obligatorio && <span className="text-[13px] font-normal text-smn-gris-500">(opcional)</span>}
                </p>
                {t.varios ? (
                  <>
                    <p className="text-sm text-smn-gris-500">{t.para_que}</p>
                    {todosDe(t.codigo).map((x) => (
                      <p key={x.id} className="mt-1 flex items-center gap-2 text-sm text-smn-gris-700">
                        <span className="min-w-0 truncate" title={x.archivo}>
                          {x.archivo} · {x.filas.toLocaleString("es-MX")} renglones
                        </span>
                        {opera && !cerrado && (
                          <button onClick={() => quitar(x.id)} className="shrink-0 rounded-lg p-1 text-smn-gris-500 hover:bg-smn-gris-100" aria-label={`Quitar ${x.archivo}`}>
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </p>
                    ))}
                  </>
                ) : (
                  <p className="truncate text-sm text-smn-gris-500" title={d ? d.archivo : t.para_que}>
                    {d ? `${d.archivo} · ${d.filas.toLocaleString("es-MX")} renglones · ${d.cargado_por ?? ""} ${fechaLocal(d.cargado_en)}` : t.para_que}
                  </p>
                )}
              </div>
              {opera && !cerrado && (
                <div className="flex gap-1 self-start">
                  <button onClick={() => elegir(t.codigo)} className="rounded-lg px-2 py-1 text-[13px] font-medium text-smn-gris-500 hover:bg-smn-gris-100" title="Subir este documento eligiendo el tipo a mano">
                    {t.varios ? (d ? "Agregar otro" : "Subir") : d ? "Reemplazar" : "Subir"}
                  </button>
                  {d && !t.varios && (
                    <button onClick={() => quitar(d.id)} className="rounded-lg p-1 text-smn-gris-500 hover:bg-smn-gris-100" aria-label="Quitar documento">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Entrada>
  );
}

// ---------------------------------------------------------------- paso 1: procesar

function Proceso({
  p,
  opera,
  ocupado,
  accion,
  alBorrar,
}: {
  p: Periodo;
  opera: boolean;
  ocupado: string | null;
  accion: (clave: string, f: () => Promise<Periodo | void>, exito?: string) => void;
  alBorrar: () => void;
}) {
  const avisar = useAvisos();
  const [confirmar, setConfirmar] = useState(false);
  const [borrando, setBorrando] = useState(false);
  const cerrado = p.estado === "cerrado";
  const corriendo = p.corrida?.estado === "en_curso";
  const borrar = async () => {
    setBorrando(true);
    try {
      await api(`${RUTA}/periodos/${p.id}`, { metodo: "DELETE" });
      avisar(`Se borró ${p.empresa.codigo} · ${p.nombre}.`, "exito");
      setConfirmar(false);
      alBorrar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setBorrando(false);
    }
  };
  return (
    <Entrada retraso={0.04} className={`${TARJETA} mt-6`}>
      <div className="flex flex-wrap items-center gap-3">
        {opera && !cerrado && (
          <Boton onClick={() => accion("procesar", () => api<Periodo>(`${RUTA}/periodos/${p.id}/procesar`, { metodo: "POST" }), "Procesando: abajo se ve cada paso")} cargando={ocupado === "procesar" || corriendo} disabled={p.faltan.length > 0 || corriendo}>
            <Play className="h-4 w-4" /> {corriendo ? "Procesando…" : p.procesado_en ? "Volver a procesar" : "Procesar"}
          </Boton>
        )}
        <p className="text-sm text-smn-gris-500">
          {p.faltan.length > 0
            ? "Sube los reportes obligatorios para poder procesar."
            : p.procesado_en
              ? `Procesado ${fechaLocal(p.procesado_en)}. Si cambias un reporte o un ajuste, vuelve a procesar; las firmas se piden otra vez si el TXT cambia.`
              : "Al procesar se siguen los 8 pasos de Fiscal y queda una bitácora de cada uno."}
        </p>
        {opera && !cerrado && !corriendo && (
          <Boton variante="fantasma" className="ml-auto" onClick={() => setConfirmar(true)}>
            <Trash2 className="h-4 w-4" /> Borrar este periodo
          </Boton>
        )}
      </div>
      <AnimatePresence>
        {confirmar && (
          <Modal titulo={`¿Borrar ${p.empresa.codigo} · ${p.nombre}?`} cerrar={() => setConfirmar(false)}>
            <p className="text-sm">
              Se borran los reportes que subiste, el resultado, las decisiones, los ajustes, las firmas y las corridas de este mes. No se puede deshacer; queda anotado en la
              bitácora. Después puedes volver a abrir el mismo mes desde cero.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Boton variante="secundario" onClick={() => setConfirmar(false)}>
                Cancelar
              </Boton>
              <Boton onClick={borrar} cargando={borrando}>
                <Trash2 className="h-4 w-4" /> Sí, borrar
              </Boton>
            </div>
          </Modal>
        )}
      </AnimatePresence>
      {p.resumen && (
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <Dato titulo="Renglones leídos" valor={p.resumen.operaciones} />
          <Dato titulo="Entran a la DIOT" valor={p.resumen.incluidas} />
          <Dato titulo="Proveedores" valor={p.resumen.terceros} />
        </div>
      )}
      {p.resumen?.faltantes?.length ? (
        <ul className="mt-3 list-disc pl-5 text-sm text-red-700">
          {p.resumen.faltantes.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      ) : null}
    </Entrada>
  );
}

function Cuadres({ p }: { p: Periodo }) {
  const conteo = (i: Impacto) => p.conteo_incidencias[i] ?? { pendiente: 0, revisada: 0 };
  return (
    <div className={TARJETA}>
      {p.resumen && (
        <div className="grid gap-3 sm:grid-cols-4">
          <Dato titulo="Renglones leídos" valor={p.resumen.operaciones} />
          <Dato titulo="Entran a la DIOT" valor={p.resumen.incluidas} />
          <Dato titulo="Terceros" valor={p.resumen.terceros} />
          <Dato titulo="Por revisar (posible impacto)" valor={conteo("posible_impacto").pendiente} alerta={conteo("posible_impacto").pendiente > 0} />
        </div>
      )}
      {p.resumen?.cuadres?.length ? (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm">
            <thead>
              <tr className="text-left text-[13px] text-smn-gris-500">
                <th className="py-1 pr-3 font-semibold">Conciliación del IVA acreditable</th>
                <th className="py-1 text-right font-semibold">IVA de las operaciones</th>
                <th className="py-1 pl-3 text-right font-semibold">Auxiliar de IVA</th>
                <th className="py-1 pl-3 text-right font-semibold">Diferencia</th>
              </tr>
            </thead>
            <tbody>
              {p.resumen.cuadres.map((c) => (
                <tr key={c.concepto} className="border-t border-smn-gris-100">
                  <td className="py-2 pr-3">
                    {c.concepto}
                    {c.nota && <span className="block text-[13px] text-smn-gris-500">{c.nota}</span>}
                  </td>
                  <td className="py-2 text-right font-semibold tabular-nums">{pesos(c.importe)}</td>
                  <td className="py-2 pl-3 text-right tabular-nums">{pesos(c.auxiliar)}</td>
                  <td className={`py-2 pl-3 text-right tabular-nums ${Math.abs(Number(c.diferencia ?? 0)) > 1 ? "font-semibold text-red-700" : "text-smn-gris-500"}`}>{pesos(c.diferencia)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function Dato({ titulo, valor, alerta }: { titulo: string; valor: number; alerta?: boolean }) {
  return (
    <div className={`rounded-2xl p-3 ${alerta ? "bg-red-50" : "bg-smn-gris-100/60"}`}>
      <p className="text-[13px] font-medium text-smn-gris-500">{titulo}</p>
      <p className={`text-2xl font-semibold tabular-nums ${alerta ? "text-red-700" : ""}`}>{valor.toLocaleString("es-MX")}</p>
    </div>
  );
}

// ---------------------------------------------------------------- incidencias

function Incidencias({ p, opera, alCambiar }: { p: Periodo; opera: boolean; alCambiar: () => void }) {
  const avisar = useAvisos();
  const [filas, setFilas] = useState<Incidencia[] | null>(null);
  const [filtro, setFiltro] = useState<"" | Impacto>("");
  const [notas, setNotas] = useState<Record<number, string>>({});
  useEffect(() => {
    api<Incidencia[]>(`${RUTA}/periodos/${p.id}/incidencias`).then(setFilas).catch((e) => avisar(mensajeDe(e), "info"));
  }, [p.id, avisar]);
  const marcar = async (i: Incidencia, estado: "revisada" | "pendiente") => {
    try {
      const r = await api<Incidencia>(`${RUTA}/incidencias/${i.id}`, { metodo: "PATCH", cuerpo: { estado, nota: notas[i.id] ?? i.nota_revision } });
      setFilas((fs) => fs?.map((x) => (x.id === r.id ? r : x)) ?? null);
      alCambiar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };
  if (!filas) return <Esqueleto className="h-40" />;
  const vistas = filas.filter((i) => !filtro || i.impacto === filtro);
  return (
    <div className={TARJETA}>
      <Selector
        etiqueta="Impacto"
        valor={filtro}
        cambiar={(v) => setFiltro(v as "" | Impacto)}
        className="max-w-xs"
        opciones={[{ valor: "", texto: `Todas (${filas.length})` }, ...(Object.keys(IMPACTOS) as Impacto[]).map((k) => ({ valor: k, texto: `${IMPACTOS[k].texto} (${filas.filter((i) => i.impacto === k).length})` }))]}
      />
      {vistas.length === 0 && <p className="mt-4 text-sm text-smn-gris-500">Sin incidencias.</p>}
      <ul className="mt-4 divide-y divide-smn-gris-100">
        {vistas.map((i) => (
          <li key={i.id} className={`py-3 ${i.estado === "revisada" ? "opacity-60" : ""}`}>
            <div className="flex flex-wrap items-center gap-2">
              <Insignia className={IMPACTOS[i.impacto].clase}>{IMPACTOS[i.impacto].texto}</Insignia>
              <span className="text-[13px] font-medium text-smn-gris-500">{i.codigo}</span>
              {i.rfc && <span className="text-[13px] font-semibold">{i.rfc}</span>}
              {i.importe !== null && <span className="text-[13px] tabular-nums text-smn-gris-500">${pesos(i.importe)}</span>}
              {i.estado === "revisada" && <Insignia className="bg-green-100 text-green-700">Revisada</Insignia>}
            </div>
            <p className="mt-1 text-sm">{i.mensaje}</p>
            {i.estado === "revisada" ? (
              <p className="mt-1 text-[13px] text-smn-gris-500">
                {i.nota_revision && <>«{i.nota_revision}» · </>}
                {i.revisada_por} {i.revisada_en && fechaLocal(i.revisada_en)}
                {opera && p.estado !== "cerrado" && (
                  <button onClick={() => marcar(i, "pendiente")} className="ml-2 font-semibold underline">
                    Regresar a pendiente
                  </button>
                )}
              </p>
            ) : (
              opera &&
              p.estado !== "cerrado" && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <input
                    value={notas[i.id] ?? ""}
                    onChange={(e) => setNotas((n) => ({ ...n, [i.id]: e.target.value }))}
                    placeholder={i.impacto === "posible_impacto" ? "Qué revisaste (obligatorio)" : "Nota (opcional)"}
                    className="min-w-0 flex-1 rounded-xl border border-smn-gris-300 bg-superficie px-3 py-1.5 text-sm outline-none focus:border-smn-naranja"
                  />
                  <Boton variante="secundario" className="py-1.5" onClick={() => marcar(i, "revisada")}>
                    Marcar revisada
                  </Boton>
                </div>
              )
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------- consolidado y trazabilidad

function Consolidado({ p }: { p: Periodo }) {
  const avisar = useAvisos();
  const [filas, setFilas] = useState<Tercero[] | null>(null);
  const [buscar, setBuscar] = useState("");
  const [detalle, setDetalle] = useState<{ t: Tercero; ops: Operacion[] | null } | null>(null);
  useEffect(() => {
    api<Tercero[]>(`${RUTA}/periodos/${p.id}/terceros`).then(setFilas).catch((e) => avisar(mensajeDe(e), "info"));
  }, [p.id, avisar]);
  const ver = (t: Tercero) => {
    setDetalle({ t, ops: null });
    api<Operacion[]>(`${RUTA}/periodos/${p.id}/operaciones?rfc=${encodeURIComponent(t.rfc)}`)
      .then((ops) => setDetalle({ t, ops }))
      .catch((e) => avisar(mensajeDe(e), "info"));
  };
  if (!filas) return <Esqueleto className="h-40" />;
  const q = buscar.trim().toUpperCase();
  const vistas = filas.filter((t) => !q || t.rfc.includes(q) || (t.nombre ?? "").toUpperCase().includes(q));
  const columnas = ["base16", "iva16", "base0", "no_objeto", "iva_retenido"];
  const total = (c: string) => filas.reduce((s, t) => s + (t.redondeados[c] ?? 0), 0);
  return (
    <div className={TARJETA}>
      <Campo etiqueta="Buscar RFC o nombre" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="text-left text-[13px] text-smn-gris-500">
            <tr>
              <th className="py-2">RFC</th>
              <th>Tipo</th>
              {columnas.map((c) => (
                <th key={c} className="text-right">
                  {CAMPOS[c]}
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {vistas.map((t) => (
              <tr key={t.id} onClick={() => ver(t)} className="cursor-pointer border-t border-smn-gris-100 hover:bg-smn-gris-100/50">
                <td className="py-2">
                  <span className="font-semibold">{t.rfc}</span>
                  <span className="block max-w-[16rem] truncate text-[13px] text-smn-gris-500">{t.nombre}</span>
                </td>
                <td className="text-[13px]">
                  {t.tipo_tercero} / {t.tipo_operacion}
                </td>
                {columnas.map((c) => (
                  <td key={c} className="text-right tabular-nums">
                    {t.redondeados[c] ? pesos(t.redondeados[c]) : ""}
                  </td>
                ))}
                <td className="pl-2 text-right">
                  {t.ajustado && <Insignia className="bg-smn-naranja/15 text-smn-negro">Ajustado</Insignia>}
                  {t.estado === "revisar" && <Insignia className="bg-red-100 text-red-700">Revisar</Insignia>}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-smn-gris-300 font-semibold">
              <td className="py-2">Total ({filas.length})</td>
              <td />
              {columnas.map((c) => (
                <td key={c} className="text-right tabular-nums">
                  {pesos(total(c))}
                </td>
              ))}
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
      <AnimatePresence>
        {detalle && (
          <Modal titulo={`${detalle.t.rfc} · ${detalle.t.nombre ?? ""}`} cerrar={() => setDetalle(null)} ancho="max-w-4xl">
            <p className="text-sm text-smn-gris-500">
              Cada renglón de los reportes que formó este tercero, con la regla que se aplicó. Fuentes: {detalle.t.fuentes.join(", ")}.
            </p>
            {!detalle.ops ? (
              <Esqueleto className="mt-4 h-32" />
            ) : (
              <div className="mt-4 max-h-[60vh] overflow-auto">
                <table className="w-full text-[13px]">
                  <thead className="text-left text-smn-gris-500">
                    <tr>
                      <th className="py-1">Documento · renglón</th>
                      <th>Referencia</th>
                      <th>Regla</th>
                      <th className="text-right">Base</th>
                      <th className="text-right">IVA</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detalle.ops.map((o) => {
                      const base = Number(o.base16) + Number(o.base8) + Number(o.base0) + Number(o.exento) + Number(o.no_objeto);
                      return (
                        <tr key={o.id} className={`border-t border-smn-gris-100 ${o.incluida ? "" : "text-smn-gris-500 line-through"}`}>
                          <td className="py-1.5">
                            {o.fuente_nombre} · {o.renglon}
                          </td>
                          <td>{o.referencia}</td>
                          <td title={o.regla_texto}>
                            {o.regla}
                            {o.nota && <span className="block text-smn-gris-500">{o.nota}</span>}
                          </td>
                          <td className="text-right tabular-nums">{pesos(base)}</td>
                          <td className="text-right tabular-nums">{pesos(Number(o.iva16) + Number(o.iva8) || Number(o.iva_retenido) || 0)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {detalle.ops.length === 0 && <p className="text-sm text-smn-gris-500">Este tercero viene solo de ajustes de Fiscal.</p>}
              </div>
            )}
          </Modal>
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------- ajustes de Fiscal

function Ajustes({ p, cat, opera, alCambiar }: { p: Periodo; cat: Catalogos; opera: boolean; alCambiar: () => void }) {
  const avisar = useAvisos();
  const [filas, setFilas] = useState<Ajuste[] | null>(null);
  const vacio = { rfc: "", nombre: "", campo: "", importe: "", excluir: false, tipo_tercero: "", tipo_operacion: "", motivo: "" };
  const [f, setF] = useState(vacio);
  const [guardando, setGuardando] = useState(false);
  useEffect(() => {
    api<Ajuste[]>(`${RUTA}/periodos/${p.id}/ajustes`).then(setFilas).catch((e) => avisar(mensajeDe(e), "info"));
  }, [p.id, avisar]);
  const guardar = async () => {
    setGuardando(true);
    try {
      const r = await api<Ajuste[]>(`${RUTA}/periodos/${p.id}/ajustes`, {
        cuerpo: {
          rfc: f.rfc,
          nombre: f.nombre || null,
          campo: f.campo || null,
          importe: f.campo && f.importe ? f.importe : null,
          excluir: f.excluir,
          tipo_tercero: f.tipo_tercero || null,
          tipo_operacion: f.tipo_operacion || null,
          motivo: f.motivo,
        },
      });
      setFilas(r);
      setF(vacio);
      alCambiar();
      avisar("Ajuste guardado. Vuelve a procesar para aplicarlo.", "exito");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setGuardando(false);
    }
  };
  const quitar = (id: number) =>
    api<Ajuste[]>(`${RUTA}/periodos/${p.id}/ajustes/${id}`, { metodo: "DELETE" })
      .then((r) => {
        setFilas(r);
        alCambiar();
      })
      .catch((e) => avisar(mensajeDe(e), "info"));
  if (!filas) return <Esqueleto className="h-40" />;
  const editable = opera && p.estado !== "cerrado";
  return (
    <div className={TARJETA}>
      <p className="text-sm text-smn-gris-500">
        Los cambios que Fiscal decide a mano (redondeos, separar un pago, quitar o agregar un tercero). Cada uno lleva su motivo, queda en la bitácora y sale en la evidencia.
      </p>
      {filas.length > 0 && (
        <ul className="mt-4 divide-y divide-smn-gris-100">
          {filas.map((a) => (
            <li key={a.id} className="flex items-start gap-3 py-3 text-sm">
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {a.rfc}{" "}
                  {a.excluir
                    ? "· se quita de la DIOT"
                    : [a.campo && `${CAMPOS[a.campo]} ${Number(a.importe) >= 0 ? "+" : ""}${pesos(a.importe)}`, a.tipo_tercero && `tipo de tercero ${a.tipo_tercero}`, a.tipo_operacion && `tipo de operación ${a.tipo_operacion}`]
                        .filter(Boolean)
                        .join(" · ")}
                </p>
                <p className="text-smn-gris-500">
                  {a.motivo} · {a.creado_por} {fechaLocal(a.creado_en)}
                </p>
              </div>
              {editable && (
                <button onClick={() => quitar(a.id)} className="rounded-lg p-1 text-smn-gris-500 hover:bg-smn-gris-100" aria-label="Quitar ajuste">
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {editable && (
        <div className="mt-4 grid gap-3 border-t border-smn-gris-100 pt-4 sm:grid-cols-3">
          <Campo etiqueta="RFC" value={f.rfc} onChange={(e) => setF({ ...f, rfc: e.target.value.toUpperCase() })} />
          <Campo etiqueta="Nombre (si es un tercero nuevo)" value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} />
          <label className="flex items-center gap-2 self-end pb-3 text-sm font-semibold">
            <input type="checkbox" checked={f.excluir} onChange={(e) => setF({ ...f, excluir: e.target.checked })} /> Quitar este tercero de la DIOT
          </label>
          <Selector etiqueta="Campo" valor={f.campo} cambiar={(v) => setF({ ...f, campo: v })} opciones={[{ valor: "", texto: "Sin cambio de importe" }, ...Object.entries(CAMPOS).map(([valor, texto]) => ({ valor, texto }))]} />
          <Campo etiqueta="Importe a sumar (negativo para restar)" type="number" step="0.01" value={f.importe} onChange={(e) => setF({ ...f, importe: e.target.value })} />
          <div className="grid grid-cols-2 gap-3">
            <Selector etiqueta="Tipo tercero" valor={f.tipo_tercero} cambiar={(v) => setF({ ...f, tipo_tercero: v })} opciones={[{ valor: "", texto: "Igual" }, ...Object.keys(cat.tipos_tercero).map((valor) => ({ valor, texto: `${valor} · ${cat.tipos_tercero[valor].split(":")[0]}` }))]} />
            <Selector etiqueta="Tipo operación" valor={f.tipo_operacion} cambiar={(v) => setF({ ...f, tipo_operacion: v })} opciones={[{ valor: "", texto: "Igual" }, ...Object.keys(cat.tipos_operacion).map((valor) => ({ valor, texto: `${valor} · ${cat.tipos_operacion[valor].split(/[:(]/)[0].trim()}` }))]} />
          </div>
          <div className="sm:col-span-3">
            <Campo etiqueta="Motivo (obligatorio)" value={f.motivo} onChange={(e) => setF({ ...f, motivo: e.target.value })} placeholder="Por qué Fiscal hace este cambio" />
          </div>
          <Boton onClick={guardar} cargando={guardando} disabled={!f.rfc || f.motivo.trim().length < 5} className="sm:col-start-3">
            Guardar ajuste
          </Boton>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- comparación contra el TXT presentado

function Comparar({ p, opera, poner }: { p: Periodo; opera: boolean; poner: (x: Periodo) => void }) {
  const avisar = useAvisos();
  const entrada = useRef<HTMLInputElement>(null);
  const c = p.comparacion;
  const subirRef = async (archivos: FileList | null) => {
    const a = archivos?.[0];
    if (!a) return;
    try {
      poner(await subir<Periodo>(`${RUTA}/periodos/${p.id}/referencia`, a));
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
    if (entrada.current) entrada.current.value = "";
  };
  return (
    <div className={TARJETA}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-smn-gris-500">
          Sube el TXT que Fiscal ya presentó para compararlo campo por campo. Solo se usa para comparar; nunca se copia al resultado.
          {p.referencia && <span className="block font-semibold text-tinta">Referencia: {p.referencia}</span>}
        </p>
        {opera && (
          <Boton variante="secundario" onClick={() => entrada.current?.click()}>
            <FileUp className="h-4 w-4" /> {p.referencia ? "Cambiar TXT" : "Subir TXT presentado"}
          </Boton>
        )}
        <input ref={entrada} type="file" accept=".txt" className="hidden" onChange={(e) => subirRef(e.target.files)} />
      </div>
      {p.referencia && !c && <p className="mt-4 text-sm text-smn-gris-500">El TXT del sistema todavía no se genera; resuelve las incidencias y vuelve a procesar.</p>}
      {c && (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-4">
            <Dato titulo="Renglones del sistema" valor={c.renglones_generados} />
            <Dato titulo="Renglones presentados" valor={c.renglones_referencia} />
            <Dato titulo="Renglones idénticos" valor={c.renglones_iguales} />
            <Dato titulo="Diferencias de campo" valor={c.diferencias.length} alerta={c.diferencias.length > 0} />
          </div>
          <table className="mt-4 w-full text-sm">
            <thead className="text-left text-[13px] text-smn-gris-500">
              <tr>
                <th className="py-1">Total</th>
                <th className="text-right">Sistema</th>
                <th className="text-right">Presentado</th>
                <th className="text-right">Diferencia</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(c.totales).map(([k, v]) => (
                <tr key={k} className="border-t border-smn-gris-100">
                  <td className="py-1.5">{k}</td>
                  <td className="text-right tabular-nums">{pesos(v.generado)}</td>
                  <td className="text-right tabular-nums">{pesos(v.referencia)}</td>
                  <td className={`text-right font-semibold tabular-nums ${v.diferencia ? "text-red-700" : ""}`}>{pesos(v.diferencia)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {c.diferencias.length > 0 && (
            <div className="mt-4 max-h-96 overflow-auto">
              <table className="w-full text-[13px]">
                <thead className="text-left text-smn-gris-500">
                  <tr>
                    <th className="py-1">RFC</th>
                    <th>Campo</th>
                    <th className="text-right">Sistema</th>
                    <th className="text-right">Presentado</th>
                  </tr>
                </thead>
                <tbody>
                  {c.diferencias.map((d, k) => (
                    <tr key={k} className="border-t border-smn-gris-100">
                      <td className="py-1.5 font-semibold">{d.rfc}</td>
                      <td>{d.campo}</td>
                      <td className="text-right tabular-nums">{d.generado ?? "—"}</td>
                      <td className="text-right tabular-nums">{d.referencia ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
