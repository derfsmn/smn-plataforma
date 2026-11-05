"use client";
// TD003 · DIOT para quien no es fiscalista: la respuesta en una frase, los pendientes que dicen qué hacer, las 7
// comprobaciones con semáforo, los proveedores en palabras y las firmas antes de descargar.

import { AnimatePresence } from "motion/react";
import { Check, CheckCircle2, ChevronDown, Download, HelpCircle, Lock, MessageCircleQuestion, PenLine, Search, Unlock, Wrench, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { MESES, PERMISO_OPERAR, RUTA, type Incidencia, type Operacion, type Periodo, type Tercero } from "@/lib/diot";
import {
  ESTADO, GLOSARIO, PASOS, PERMISO_APROBAR, QUE_HACER, RESUELTO, pesosEnteros,
  type Comprobacion, type Comprobaciones, type DiferenciaProveedor, type Embudo, type ProveedorMuestra,
} from "@/lib/diot-validacion";
import { descargar } from "@/lib/precios";

const TARJETA = "rounded-2xl border border-smn-gris-100 bg-superficie p-5";
const ENTRADA = "w-full rounded-xl border border-smn-gris-300 bg-superficie px-3 py-2 text-sm outline-none focus:border-smn-naranja";

/** Una palabra fiscal con su explicación al pasar el cursor (o al tocarla). */
export function Termino({ t, children }: { t: keyof typeof GLOSARIO | string; children?: React.ReactNode }) {
  return (
    <abbr title={GLOSARIO[t] ?? ""} className="cursor-help underline decoration-smn-gris-300 decoration-dotted underline-offset-2 [text-decoration-line:underline]">
      {children ?? t}
    </abbr>
  );
}

export function Glosario() {
  const [abierto, setAbierto] = useState(false);
  return (
    <div className="mt-3">
      <button onClick={() => setAbierto(!abierto)} className="inline-flex items-center gap-1 text-sm font-semibold text-smn-gris-500 hover:text-tinta">
        <HelpCircle className="h-4 w-4" /> ¿Qué significa cada palabra?
        <ChevronDown className={`h-4 w-4 transition ${abierto ? "rotate-180" : ""}`} />
      </button>
      {abierto && (
        <dl className="mt-2 grid gap-x-6 gap-y-2 rounded-2xl bg-smn-gris-100/60 p-4 text-sm sm:grid-cols-2">
          {Object.entries(GLOSARIO).map(([k, v]) => (
            <div key={k}>
              <dt className="font-semibold">{k}</dt>
              <dd className="text-smn-gris-700">{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- cabecera: la frase y los 4 pasos

export type Vista = 1 | 2 | 3 | 4 | "proveedores" | "fiscal";

export function Cabecera({ p, c, vista, setVista }: { p: Periodo; c: Comprobaciones | null; vista: Vista; setVista: (v: Vista) => void }) {
  const paso = c?.paso ?? 1;
  const estados = c?.comprobaciones ?? [];
  return (
    <div className={`${TARJETA} mt-6`}>
      <p className="text-[13px] font-medium text-smn-gris-500">
        {p.empresa.codigo} · {p.nombre}
      </p>
      {c ? <p className="mt-1 text-xl font-semibold leading-snug">{c.frase}</p> : <Esqueleto className="mt-2 h-7 w-2/3" />}
      {estados.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
          {estados.map((x) => (
            <span key={x.clave} className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-smn-gris-700" title={x.frase}>
              <span className={`h-2.5 w-2.5 rounded-full ${ESTADO[x.estado].punto}`} /> {x.titulo}
            </span>
          ))}
        </div>
      )}
      <ol className="mt-5 grid gap-2 sm:grid-cols-4">
        {PASOS.map((s) => {
          const hecho = paso > s.n;
          const actual = vista === s.n;
          return (
            <li key={s.n}>
              <button
                onClick={() => setVista(s.n)}
                className={`flex w-full items-center gap-3 rounded-2xl border p-3 text-left transition ${actual ? "border-smn-naranja bg-smn-naranja/10" : "border-smn-gris-100 hover:border-smn-gris-300"}`}
              >
                <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-semibold ${hecho ? "bg-emerald-500 text-white" : paso === s.n ? "bg-smn-naranja text-smn-negro" : "bg-smn-gris-100 text-smn-gris-500"}`}>
                  {hecho ? <Check className="h-4 w-4" /> : s.n}
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">
                    {s.titulo}
                    {s.n === 2 && c && c.pendientes > 0 && <span className="ml-1 text-red-700">({c.pendientes})</span>}
                  </span>
                  <span className="block truncate text-[13px] text-smn-gris-500">{s.ayuda}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <div className="mt-3 flex flex-wrap gap-2">
        {(
          [
            ["proveedores", "Proveedores en palabras"],
            ["fiscal", "Vista para Fiscal"],
          ] as const
        ).map(([v, texto]) => (
          <button
            key={v}
            onClick={() => setVista(v)}
            className={`rounded-xl px-3 py-1.5 text-sm font-semibold transition ${vista === v ? "bg-tinta text-superficie" : "bg-smn-gris-100/70 text-smn-gris-700 hover:bg-smn-gris-100"}`}
          >
            {texto}
          </button>
        ))}
      </div>
      <Glosario />
    </div>
  );
}

// ---------------------------------------------------------------- paso 2: pendientes

export function Pendientes({ p, alCambiar, irAjustes }: { p: Periodo; alCambiar: () => void; irAjustes: () => void }) {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const opera = puede(PERMISO_OPERAR) && p.estado !== "cerrado";
  const [filas, setFilas] = useState<Incidencia[] | null>(null);
  const [abierta, setAbierta] = useState<{ clave: string; ids: number[]; modo: "bien" | "fiscal" } | null>(null);
  const [nota, setNota] = useState("");
  const [verResueltas, setVerResueltas] = useState(false);
  const [expandido, setExpandido] = useState<Record<string, boolean>>({});
  const cargar = () => api<Incidencia[]>(`${RUTA}/periodos/${p.id}/incidencias`).then(setFilas).catch((e) => avisar(mensajeDe(e), "info"));
  useEffect(() => {
    cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.id, p.procesado_en]);
  const guardar = async (ids: number[], estado: "revisada" | "pendiente", texto: string | null) => {
    try {
      if (ids.length === 1) await api<Incidencia>(`${RUTA}/incidencias/${ids[0]}`, { metodo: "PATCH", cuerpo: { estado, nota: texto } });
      else await api(`${RUTA}/periodos/${p.id}/incidencias/lote`, { cuerpo: { ids, estado, nota: texto } });
      setAbierta(null);
      setNota("");
      await cargar();
      alCambiar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };
  if (!p.procesado_en) return <p className={`${TARJETA} mt-6 text-sm text-smn-gris-500`}>Primero sube los reportes y procesa el mes (paso 1).</p>;
  if (!filas) return <Esqueleto className="mt-6 h-40" />;
  const decidir = filas.filter((i) => i.impacto === "posible_impacto" && i.estado === "pendiente");
  const decididas = filas.filter((i) => i.impacto === "posible_impacto" && i.estado === "revisada");
  const resueltas = filas.filter((i) => i.impacto !== "posible_impacto");
  const porCodigo = resueltas.reduce<Record<string, number>>((a, i) => ({ ...a, [i.codigo]: (a[i.codigo] ?? 0) + 1 }), {});
  const mueve = (i: Incidencia) => Math.abs(Number(i.importe ?? 0));
  // Los pendientes del mismo tipo se deciden juntos; primero el tipo que mueve más dinero.
  const grupos = Object.values(
    decidir.reduce<Record<string, { codigo: string; filas: Incidencia[]; total: number }>>((a, i) => {
      const g = (a[i.codigo] ??= { codigo: i.codigo, filas: [], total: 0 });
      g.filas.push(i);
      g.total += mueve(i);
      return a;
    }, {}),
  )
    .map((g) => ({ ...g, filas: [...g.filas].sort((x, y) => mueve(y) - mueve(x)) }))
    .sort((x, y) => y.total - x.total || y.filas.length - x.filas.length);
  const editor = (clave: string) =>
    abierta?.clave === clave && (
      <div className="mt-3 flex flex-wrap gap-2">
        <input
          autoFocus
          value={nota}
          onChange={(e) => setNota(e.target.value)}
          placeholder={
            abierta.modo === "bien"
              ? abierta.ids.length > 1
                ? `Qué revisaste y por qué los ${abierta.ids.length} están bien (obligatorio)`
                : "Qué revisaste y por qué está bien (obligatorio)"
              : "Qué le preguntaste a Fiscal"
          }
          className={`${ENTRADA} min-w-0 flex-1`}
        />
        <Boton
          className="py-1.5"
          disabled={nota.trim().length < 3}
          onClick={() => (abierta.modo === "bien" ? guardar(abierta.ids, "revisada", nota) : guardar(abierta.ids, "pendiente", `En espera de Fiscal: ${nota.trim()}`))}
        >
          Guardar{abierta.ids.length > 1 ? ` (${abierta.ids.length})` : ""}
        </Boton>
        <Boton variante="fantasma" className="py-1.5" onClick={() => setAbierta(null)}>
          Cancelar
        </Boton>
      </div>
    );
  return (
    <div className="mt-6 space-y-6">
      <section>
        <h2 className="text-lg font-semibold">
          Necesitan tu decisión ({decidir.length}
          {grupos.length > 1 ? ` en ${grupos.length} tipos` : ""})
        </h2>
        <p className="text-sm text-smn-gris-500">
          Los del mismo tipo se deciden juntos; arriba el tipo que mueve más dinero. Mientras haya alguno aquí, el TXT no se puede descargar.
        </p>
        {decidir.length === 0 && (
          <p className={`${TARJETA} mt-3 flex items-center gap-2 text-sm font-semibold text-emerald-700`}>
            <CheckCircle2 className="h-5 w-5" /> No hay nada que decidir. Sigue con el paso 3.
          </p>
        )}
        <ul className="mt-3 space-y-3">
          {grupos.map((g) => {
            const q = QUE_HACER[g.codigo] ?? { titulo: g.codigo, importa: "", hacer: "" };
            const ids = g.filas.map((i) => i.id);
            const todas = expandido[g.codigo] || g.filas.length <= 5;
            const vistas = todas ? g.filas : g.filas.slice(0, 5);
            return (
              <li key={g.codigo} className={`${TARJETA} border-amber-200`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="font-semibold">
                    {q.titulo}
                    {g.filas.length > 1 && <span className="ml-2 text-smn-gris-500">× {g.filas.length}</span>}
                  </p>
                  {g.total > 0 && <Insignia className="bg-smn-gris-100 text-smn-gris-700">Mueven {pesosEnteros(g.total)}</Insignia>}
                </div>
                <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-[13px] font-medium text-smn-gris-500">Por qué importa</dt>
                    <dd>{q.importa}</dd>
                  </div>
                  <div>
                    <dt className="text-[13px] font-medium text-smn-gris-500">Qué hacer</dt>
                    <dd>{q.hacer}</dd>
                  </div>
                </dl>
                <ul className="mt-3 divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 text-sm">
                  {vistas.map((i) => (
                    <li key={i.id} className="px-3 py-2">
                      <div className="flex flex-wrap items-start gap-2">
                        <span className="min-w-0 flex-1">{i.mensaje}</span>
                        {i.importe !== null && <span className="shrink-0 tabular-nums text-smn-gris-500">{pesosEnteros(mueve(i))}</span>}
                        {opera && g.filas.length > 1 && abierta?.clave !== `i${i.id}` && (
                          <span className="flex shrink-0 gap-2 text-[13px] font-medium text-smn-gris-500">
                            <button className="underline" onClick={() => (setAbierta({ clave: `i${i.id}`, ids: [i.id], modo: "bien" }), setNota(""))}>
                              Está bien
                            </button>
                            <button className="underline" onClick={() => (setAbierta({ clave: `i${i.id}`, ids: [i.id], modo: "fiscal" }), setNota(""))}>
                              Preguntar
                            </button>
                          </span>
                        )}
                      </div>
                      {i.nota_revision && (
                        <p className="mt-1 rounded-lg bg-sky-50 px-2 py-1 text-[13px] text-sky-900 dark:bg-sky-950/40 dark:text-sky-200">
                          {i.nota_revision} {i.revisada_por && <>· {i.revisada_por} {i.revisada_en && fechaLocal(i.revisada_en)}</>}
                        </p>
                      )}
                      {editor(`i${i.id}`)}
                    </li>
                  ))}
                </ul>
                {!todas && (
                  <button onClick={() => setExpandido({ ...expandido, [g.codigo]: true })} className="mt-2 text-sm font-semibold text-smn-gris-500 underline">
                    Ver los {g.filas.length}
                  </button>
                )}
                {opera && abierta?.clave !== g.codigo && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Boton variante="secundario" className="py-1.5" onClick={() => (setAbierta({ clave: g.codigo, ids, modo: "bien" }), setNota(""))}>
                      <Check className="h-4 w-4" /> {g.filas.length > 1 ? `Todos están bien así (${g.filas.length})` : "Está bien así"}
                    </Boton>
                    <Boton variante="secundario" className="py-1.5" onClick={irAjustes}>
                      <Wrench className="h-4 w-4" /> Hacer un ajuste
                    </Boton>
                    <Boton variante="fantasma" className="py-1.5" onClick={() => (setAbierta({ clave: g.codigo, ids, modo: "fiscal" }), setNota(""))}>
                      <MessageCircleQuestion className="h-4 w-4" /> {g.filas.length > 1 ? "Preguntar a Fiscal por todos" : "Preguntar a Fiscal"}
                    </Boton>
                  </div>
                )}
                {editor(g.codigo)}
              </li>
            );
          })}
        </ul>
      </section>

      {decididas.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold">Ya decididas ({decididas.length})</h2>
          <ul className={`${TARJETA} mt-3 divide-y divide-smn-gris-100`}>
            {decididas.map((i) => (
              <li key={i.id} className="flex flex-wrap items-start gap-2 py-2 text-sm">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                <span className="min-w-0 flex-1">
                  <span className="font-semibold">{QUE_HACER[i.codigo]?.titulo ?? i.codigo}.</span> «{i.nota_revision}»
                  <span className="block text-[13px] text-smn-gris-500">
                    {i.revisada_por} {i.revisada_en && fechaLocal(i.revisada_en)} · {i.mensaje}
                  </span>
                </span>
                {opera && (
                  <button onClick={() => guardar([i.id], "pendiente", null)} className="text-[13px] font-medium text-smn-gris-500 underline">
                    Volver a decidir
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <button onClick={() => setVerResueltas(!verResueltas)} className="flex items-center gap-1 text-lg font-semibold">
          El sistema ya lo resolvió ({resueltas.length}) <ChevronDown className={`h-5 w-5 transition ${verResueltas ? "rotate-180" : ""}`} />
        </button>
        <p className="text-sm text-smn-gris-500">Avisos que el sistema explicó solo. No piden nada; están para que sepas que se vieron.</p>
        {verResueltas && (
          <div className={`${TARJETA} mt-3 space-y-3 text-sm`}>
            {Object.entries(porCodigo).map(([codigo, n]) => (
              <details key={codigo}>
                <summary className="cursor-pointer font-semibold">
                  {n} × {RESUELTO[codigo] ?? codigo}
                </summary>
                <ul className="mt-1 list-disc space-y-1 pl-6 text-smn-gris-700">
                  {resueltas
                    .filter((i) => i.codigo === codigo)
                    .map((i) => (
                      <li key={i.id}>{i.mensaje}</li>
                    ))}
                </ul>
              </details>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- paso 3: comprobaciones

export function Validar({ p, c, setC }: { p: Periodo; c: Comprobaciones | null; setC: (c: Comprobaciones) => void }) {
  const [abierta, setAbierta] = useState<Comprobacion["clave"] | null>(null);
  if (!p.procesado_en) return <p className={`${TARJETA} mt-6 text-sm text-smn-gris-500`}>Primero sube los reportes y procesa el mes (paso 1).</p>;
  if (!c) return <Esqueleto className="mt-6 h-64" />;
  const sel = c.comprobaciones.find((x) => x.clave === abierta);
  return (
    <div className="mt-6">
      <p className="text-sm text-smn-gris-500">
        Cada tarjeta contesta una pregunta con el número que la respalda. Verde: bien. Amarillo: alguien tiene que mirarlo. Rojo: no cuadra. Gris: falta un dato. Azul: solo para mirar.
        Toca una tarjeta para ver el detalle.
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {c.comprobaciones.map((x, k) => (
          <button
            key={x.clave}
            onClick={() => setAbierta(abierta === x.clave ? null : x.clave)}
            className={`rounded-2xl border p-4 text-left transition hover:border-smn-gris-300 ${ESTADO[x.estado].caja} ${abierta === x.clave ? "ring-2 ring-smn-naranja" : ""}`}
          >
            <span className="flex items-center gap-2 text-[13px] font-medium text-smn-gris-500">
              <span className={`h-3 w-3 rounded-full ${ESTADO[x.estado].punto}`} /> {k + 1}. {ESTADO[x.estado].texto}
            </span>
            <span className="mt-1 block font-semibold">{x.titulo}</span>
            <span className="mt-1 block text-sm">{x.frase}</span>
          </button>
        ))}
      </div>
      {sel && (
        <div className={`${TARJETA} mt-4`}>
          <p className="text-[13px] font-medium text-smn-gris-500">{sel.pregunta}</p>
          <p className="mt-1 font-semibold">{sel.frase}</p>
          <div className="mt-4">
            {sel.clave === "contabilidad" && <DetalleContabilidad d={sel.detalle} />}
            {sel.clave === "pagos" && <DetalleEmbudo embudo={sel.detalle.embudo ?? []} />}
            {sel.clave === "declaracion" && <DetalleDeclaracion p={p} d={sel.detalle} setC={setC} />}
            {sel.clave === "muestra" && <DetalleMuestra p={p} muestra={sel.detalle.muestra ?? []} setC={setC} />}
            {sel.clave === "banco" && <DetalleBanco d={sel.detalle} />}
            {sel.clave === "sat" && <DetalleSat d={sel.detalle} />}
            {sel.clave === "mes_anterior" && <DetalleMesAnterior d={sel.detalle} />}
            {sel.clave === "formato" && <DetalleFormato lista={sel.detalle.verificaciones ?? []} />}
            {sel.clave === "presentado" && <DetallePresentado p={p} d={sel.detalle} setC={setC} />}
          </div>
        </div>
      )}
    </div>
  );
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function DetalleContabilidad({ d }: { d: any }) {
  if (!d.grupos) return null;
  return (
    <>
      <p className="text-sm text-smn-gris-700">
        Contabilidad registra el <Termino t="IVA acreditable" /> de cada póliza en el <Termino t="Auxiliar de IVA">auxiliar de IVA</Termino>. La plataforma calcula el
        mismo IVA desde los reportes de pagos y gastos, sin verlo. Si los dos coinciden, el IVA del TXT es el de contabilidad. La diferencia permitida es de hasta 50
        centavos por proveedor, porque el SAT pide pesos enteros.
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[32rem] text-sm">
          <thead className="text-left text-[13px] text-smn-gris-500">
            <tr>
              <th className="py-1">De dónde viene el IVA</th>
              <th className="text-right">Calculado</th>
              <th className="text-right">Contabilidad</th>
              <th className="text-right">Diferencia</th>
            </tr>
          </thead>
          <tbody>
            {d.grupos.map((g: any) => (
              <tr key={g.concepto} className="border-t border-smn-gris-100">
                <td className="py-1.5">{g.concepto}</td>
                <td className="text-right tabular-nums">{pesosEnteros(g.calculado)}</td>
                <td className="text-right tabular-nums">{pesosEnteros(g.contabilidad)}</td>
                <td className={`text-right tabular-nums ${Math.abs(g.diferencia) > 1 ? "font-semibold text-red-700" : "text-smn-gris-500"}`}>{pesosEnteros(g.diferencia)}</td>
              </tr>
            ))}
            <tr className="border-t-2 border-smn-gris-300 font-semibold">
              <td className="py-1.5">IVA del TXT (al peso)</td>
              <td className="text-right tabular-nums">{pesosEnteros(d.iva_txt)}</td>
              <td className="text-right tabular-nums">{pesosEnteros(d.iva_contabilidad)}</td>
              <td className="text-right tabular-nums">{pesosEnteros(d.diferencia)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {d.por_ajustes ? <p className="mt-2 text-sm">Los ajustes de Fiscal mueven {pesosEnteros(d.por_ajustes)} de IVA a propósito.</p> : null}
    </>
  );
}
/* eslint-enable @typescript-eslint/no-explicit-any */

function DetalleEmbudo({ embudo }: { embudo: Embudo[] }) {
  const color = { entra: "bg-emerald-500", sin_explicar: "bg-red-500", no_entra: "bg-smn-gris-300" } as const;
  return (
    <div className="space-y-6">
      <p className="text-sm text-smn-gris-700">
        De todo lo que trae cada reporte, cuánto entra a la DIOT y por qué lo demás no entra. Los montos son subtotal más IVA de cada renglón, solo para ubicarse; no se usan en el cálculo.
      </p>
      {embudo.map((f) => (
        <div key={f.fuente}>
          <p className="font-semibold">
            {f.nombre}: {f.renglones.toLocaleString("es-MX")} renglones, {pesosEnteros(f.monto)}
          </p>
          <div className="mt-2 flex h-4 w-full overflow-hidden rounded-full bg-smn-gris-100">
            {f.grupos.map((g) => (
              <div key={g.concepto} className={color[g.tipo]} style={{ width: `${f.monto ? (g.monto / f.monto) * 100 : 0}%` }} title={`${g.concepto}: ${pesosEnteros(g.monto)}`} />
            ))}
          </div>
          <ul className="mt-2 space-y-1 text-sm">
            {f.grupos.map((g) => (
              <li key={g.concepto} className="flex items-start gap-2">
                <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${color[g.tipo]}`} />
                <span className="min-w-0 flex-1">
                  <span className={g.tipo === "entra" ? "font-semibold" : ""}>{g.tipo === "entra" ? `Entra · ${g.concepto}` : g.concepto}</span>
                  <span className="text-smn-gris-500"> · {g.renglones} renglón(es)</span>
                </span>
                <span className="shrink-0 tabular-nums">{pesosEnteros(g.monto)}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function DetalleDeclaracion({ p, d, setC }: { p: Periodo; d: any; setC: (c: Comprobaciones) => void }) {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const [importe, setImporte] = useState(d.iva_declarado !== undefined ? String(d.iva_declarado) : "");
  const [nota, setNota] = useState(d.nota ?? "");
  const [ocupado, setOcupado] = useState(false);
  const guardar = async () => {
    setOcupado(true);
    try {
      setC(await api<Comprobaciones>(`${RUTA}/periodos/${p.id}/iva-declarado`, { metodo: "PUT", cuerpo: { importe: importe === "" ? null : importe, nota: nota || null } }));
      avisar("Guardado.", "exito");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(false);
    }
  };
  return (
    <>
      <p className="text-sm text-smn-gris-700">
        Cada mes Fiscal presenta la declaración de IVA (pago provisional) con el total de <Termino t="IVA acreditable" />. Ese total debe ser el mismo que el del TXT. Pide a
        Fiscal el número del renglón «IVA acreditable» de la declaración de {MESES[p.mes - 1].toLowerCase()} y captúralo aquí.
      </p>
      {d.capturado_por && (
        <p className="mt-2 text-[13px] text-smn-gris-500">
          Capturado por {d.capturado_por} {d.capturado_en && fechaLocal(d.capturado_en)}
        </p>
      )}
      {puede(PERMISO_OPERAR) && (
        <div className="mt-3 grid gap-2 sm:grid-cols-[12rem_1fr_auto]">
          <input type="number" step="0.01" min="0" value={importe} onChange={(e) => setImporte(e.target.value)} placeholder="IVA acreditable declarado" className={ENTRADA} />
          <input value={nota} onChange={(e) => setNota(e.target.value)} placeholder="De dónde sale (por ejemplo, acuse de la declaración)" className={ENTRADA} />
          <Boton onClick={guardar} cargando={ocupado}>
            Guardar
          </Boton>
        </div>
      )}
    </>
  );
}
/* eslint-enable @typescript-eslint/no-explicit-any */

function DetalleMuestra({ p, muestra, setC }: { p: Periodo; muestra: ProveedorMuestra[]; setC: (c: Comprobaciones) => void }) {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const [rastreo, setRastreo] = useState<{ rfc: string; nombre: string | null } | null>(null);
  const marcar = async (m: ProveedorMuestra, revisado: boolean) => {
    try {
      setC(await api<Comprobaciones>(`${RUTA}/periodos/${p.id}/muestra/${encodeURIComponent(m.rfc)}`, { cuerpo: { revisado } }));
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };
  return (
    <>
      <p className="text-sm text-smn-gris-700">
        Abre cada proveedor con «Ver de dónde sale» y compara sus pagos y facturas contra lo que tú conoces (o contra Intelisis). Si cuadra, márcalo. Son los 10 con más IVA y 5 al azar.
        Si el mes se vuelve a procesar y un proveedor cambia, hay que revisarlo otra vez.
      </p>
      <ul className="mt-3 divide-y divide-smn-gris-100">
        {muestra.map((m) => (
          <li key={m.rfc} className="flex flex-wrap items-center gap-3 py-2 text-sm">
            <span className="min-w-0 flex-1">
              <span className="font-semibold">{m.nombre ?? m.rfc}</span>{" "}
              <Insignia className={m.motivo === "grande" ? "bg-smn-naranja/15 text-smn-negro" : "bg-smn-gris-100 text-smn-gris-700"}>{m.motivo === "grande" ? "De los más grandes" : "Al azar"}</Insignia>
              <span className="block text-[13px] text-smn-gris-500">
                {m.rfc} · IVA {pesosEnteros(m.iva)} · total {pesosEnteros(m.monto)} · {m.operaciones} movimiento(s)
                {m.revisado && ` · revisó ${m.revisado_por} ${m.revisado_en ? fechaLocal(m.revisado_en) : ""}`}
                {m.cambio_desde_revision && " · cambió desde que se revisó"}
              </span>
            </span>
            <button onClick={() => setRastreo({ rfc: m.rfc, nombre: m.nombre })} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[13px] font-semibold hover:bg-smn-gris-100">
              <Search className="h-3.5 w-3.5" /> Ver de dónde sale
            </button>
            {puede(PERMISO_OPERAR) ? (
              <label className="inline-flex items-center gap-2 text-[13px] font-semibold">
                <input type="checkbox" checked={m.revisado} onChange={(e) => marcar(m, e.target.checked)} /> Cuadra
              </label>
            ) : (
              m.revisado && <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            )}
          </li>
        ))}
      </ul>
      <AnimatePresence>{rastreo && <Rastreo p={p} rfc={rastreo.rfc} nombre={rastreo.nombre} cerrar={() => setRastreo(null)} />}</AnimatePresence>
    </>
  );
}

/* eslint-disable @typescript-eslint/no-explicit-any */
const centavos = (n: number) => n.toLocaleString("es-MX", { style: "currency", currency: "MXN" });

function DetalleSat({ d }: { d: any }) {
  if (d.proveedores === undefined) return <p className="text-sm text-smn-gris-500">Sube los 3 archivos del «Visor de CFDI» del SAT (Ingreso, Egreso y Pago, recibidos) en la lista de documentos y aquí se compara el IVA de cada proveedor.</p>;
  const lista = (titulo: string, ayuda: string, filas: any[], texto: (x: any) => React.ReactNode) =>
    filas.length > 0 && (
      <div className="mt-3">
        <p className="font-semibold">
          {titulo} ({filas.length})
        </p>
        <p className="text-[13px] text-smn-gris-500">{ayuda}</p>
        <ul className="mt-1 max-h-64 space-y-1 overflow-auto text-sm">
          {filas.slice(0, 100).map((x) => (
            <li key={x.rfc} className="flex justify-between gap-3">{texto(x)}</li>
          ))}
        </ul>
      </div>
    );
  const nombre = (x: any) => <span className="min-w-0 truncate">{x.nombre || x.rfc}</span>;
  return (
    <div className="space-y-3">
      <p className="text-sm text-smn-gris-700">
        La DIOT va por lo pagado. Del SAT se toma, por proveedor: facturas de contado (PUE) del mes, menos notas de crédito del mes, más complementos de pago con fecha de pago del mes. Extranjeros y global (XAXX) no se comparan porque no tienen factura con RFC. Es informativo: no cambia el cálculo ni frena la firma.
      </p>
      <p className="text-sm">
        {d.iguales} de {d.proveedores} proveedores tienen el mismo IVA que el SAT. IVA del SAT {centavos(d.iva_sat)} contra {centavos(d.iva_diot)} del TXT.
      </p>
      {lista("Sin factura del mes en el SAT", "Puede ser que la factura sea de otro mes, que esté a nombre de otra empresa o que el proveedor facturó a crédito (PPD) y no ha mandado su complemento de pago. Sin factura o complemento, ese IVA podría no ser acreditable: pregúntale a Fiscal.", d.sin_factura, (x) => (
        <>
          {nombre(x)}
          <span className="shrink-0 text-right tabular-nums">{centavos(x.diot)} en el TXT{x.ppd > 0 && <span className="block text-[13px] text-smn-gris-500">facturó {centavos(x.ppd)} de IVA a crédito este mes, sin complemento de pago</span>}</span>
        </>
      ))}
      {lista("Con diferencia mayor", "El SAT tiene otro IVA pagado en el mes. Puede ser un pago registrado en otro mes, un complemento con otra fecha o un error de captura.", d.grandes, (x) => (
        <>
          {nombre(x)}
          <span className="shrink-0 tabular-nums">{centavos(x.diot)} en el TXT, {centavos(x.sat)} en el SAT</span>
        </>
      ))}
      {lista("Con diferencia pequeña", "Hasta $50 o 1 % del IVA. Casi siempre es tipo de cambio (proveedores en dólares) o redondeo.", d.chicas, (x) => (
        <>
          {nombre(x)}
          <span className="shrink-0 tabular-nums">{centavos(x.diot)} en el TXT, {centavos(x.sat)} en el SAT</span>
        </>
      ))}
      {lista("En el SAT pero no en la DIOT", "Proveedores con IVA pagado en el mes según el SAT que no aparecen en el TXT.", d.solo_sat, (x) => (
        <>
          {nombre(x)}
          <span className="shrink-0 tabular-nums">{centavos(x.sat)}</span>
        </>
      ))}
    </div>
  );
}

function DetalleBanco({ d }: { d: any }) {
  if (!d.cuentas) return <p className="text-sm text-smn-gris-500">Sube el estado de cuenta del banco (un archivo por cuenta) en la lista de documentos y aquí se compara cada pago de tesorería contra sus cargos.</p>;
  const lista = (titulo: string, filas: any[], texto: (x: any) => React.ReactNode, llave: (x: any) => string) =>
    filas.length > 0 && (
      <div className="mt-3">
        <p className="font-semibold">
          {titulo} ({filas.length})
        </p>
        <ul className="mt-1 max-h-64 space-y-1 overflow-auto text-sm">
          {filas.slice(0, 100).map((x) => (
            <li key={llave(x)} className="flex justify-between gap-3">{texto(x)}</li>
          ))}
        </ul>
      </div>
    );
  return (
    <div className="space-y-5">
      <p className="text-sm text-smn-gris-700">
        Cada pago del reporte de tesorería se busca en el estado de cuenta por su folio de Intelisis (el banco lo trae en «Folio Aceptación»). Si un pago salió en varios cargos, se suman. No cambia el cálculo de la DIOT.
      </p>
      {d.cuentas.map((c: any) => (
        <div key={c.archivo} className="rounded-xl border border-smn-gris-100 p-3">
          <p className="font-semibold break-all">{c.archivo}</p>
          {c.cuenta ? (
            <p className="text-sm text-smn-gris-700">
              Cuenta {c.cuenta} de tesorería: {c.confirmados} de {c.pagos} pagos salen del banco por el mismo importe.
            </p>
          ) : (
            <p className="text-sm text-red-700">Ningún pago de tesorería aparece en este estado de cuenta. Revisa que sea de esta empresa y de este mes.</p>
          )}
          {lista("Con otro importe en el banco", c.diferencias, (x) => (
            <>
              <span className="min-w-0 truncate">{x.movid} · {x.beneficiario || x.mov}</span>
              <span className="shrink-0 tabular-nums">{centavos(x.importe)} en tesorería, {centavos(x.banco)} en el banco</span>
            </>
          ), (x) => x.movid)}
          {lista("No aparecen en el banco", c.no_encontrados, (x) => (
            <>
              <span className="min-w-0 truncate">{x.movid} · {x.fecha} · {x.beneficiario || x.mov}</span>
              <span className="shrink-0 tabular-nums">{centavos(x.importe)}</span>
            </>
          ), (x) => x.movid)}
          {lista("Encontrados con otro folio en el banco (mismo día e importe)", c.otro_folio ?? [], (x) => (
            <>
              <span className="min-w-0 truncate">{x.movid} en tesorería, {x.folio_banco} en el banco · {x.fecha} · {x.beneficiario || x.mov}</span>
              <span className="shrink-0 tabular-nums">{centavos(x.importe)}</span>
            </>
          ), (x) => x.movid)}
          {(c.otro_folio ?? []).length > 0 && <p className="mt-1 text-[13px] text-smn-gris-500">Se dan por buenos: el folio del banco probablemente está mal escrito. Si quieres, avisa a Tesorería para que lo corrija.</p>}
          {lista("Cargos del banco que no están en el reporte de tesorería", c.solo_banco, (x) => (
            <>
              <span className="min-w-0 truncate">{x.folio} · {x.descripcion}</span>
              <span className="shrink-0 tabular-nums">{centavos(x.importe)}</span>
            </>
          ), (x) => x.folio)}
          {c.solo_banco.length > 0 && <p className="mt-1 text-[13px] text-smn-gris-500">Informativo: pueden ser traspasos, inversiones u otros movimientos que no son pagos a proveedores.</p>}
        </div>
      ))}
      {d.sin_estado.length > 0 && (
        <p className="text-sm text-smn-gris-700">
          Sin estado de cuenta: {d.sin_estado.map((x: any) => `${x.cuenta} (${x.pagos} pagos, ${centavos(x.importe)})`).join(", ")}. Súbelos para compararlos también.
        </p>
      )}
    </div>
  );
}

function DetalleMesAnterior({ d }: { d: any }) {
  if (!d.mes) return <p className="text-sm text-smn-gris-500">Cuando haya un mes anterior procesado, aquí saldrán los proveedores nuevos, los que ya no aparecen y los que cambiaron mucho.</p>;
  const lista = (titulo: string, filas: any[], texto: (x: any) => string) => (
    <div>
      <p className="font-semibold">
        {titulo} ({filas.length})
      </p>
      <ul className="mt-1 max-h-64 space-y-1 overflow-auto text-sm">
        {filas.slice(0, 50).map((x) => (
          <li key={x.rfc} className="flex justify-between gap-2">
            <span className="min-w-0 truncate">{x.nombre ?? x.rfc}</span>
            <span className="shrink-0 tabular-nums text-smn-gris-700">{texto(x)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
  return (
    <>
      <p className="text-sm text-smn-gris-700">
        No son errores: son los cambios que vale la pena entender antes de firmar. IVA de {d.mes}: {pesosEnteros(d.iva_antes)}; este mes: {pesosEnteros(d.iva_ahora)}.
      </p>
      <div className="mt-3 grid gap-6 sm:grid-cols-3">
        {lista("Nuevos este mes", d.nuevos, (x) => pesosEnteros(x.monto))}
        {lista("Ya no aparecen", d.se_fueron, (x) => pesosEnteros(x.monto))}
        {lista("Cambiaron más de 30 %", d.cambios, (x) => `${pesosEnteros(x.antes)} → ${pesosEnteros(x.ahora)}`)}
      </div>
    </>
  );
}
/* eslint-enable @typescript-eslint/no-explicit-any */

function DetalleFormato({ lista }: { lista: { nombre: string; texto: string; ok: boolean; detalle: string }[] }) {
  return (
    <ul className="space-y-1.5 text-sm">
      {lista.map((v) => (
        <li key={v.nombre} className="flex items-start gap-2" title={v.detalle}>
          {v.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-700" />}
          <span>
            {v.texto}
            {!v.ok && <span className="block text-[13px] text-red-700">{v.detalle}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function DetallePresentado({ p, d, setC }: { p: Periodo; d: any; setC: (c: Comprobaciones) => void }) {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const [edicion, setEdicion] = useState<Record<string, { motivo: string; nota: string }>>({});
  if (!d.diferencias) return <p className="text-sm text-smn-gris-500">Sube el TXT que presentó Fiscal en la «Vista para Fiscal» → «Comparar con TXT presentado». Solo hace falta durante el piloto.</p>;
  const guardar = async (x: DiferenciaProveedor) => {
    const e = edicion[x.rfc];
    try {
      setC(await api<Comprobaciones>(`${RUTA}/periodos/${p.id}/diferencias/${encodeURIComponent(x.rfc)}`, { cuerpo: { motivo: e.motivo, nota: e.nota || null } }));
      setEdicion(({ [x.rfc]: _, ...resto }) => resto);
    } catch (err) {
      avisar(mensajeDe(err), "info");
    }
  };
  const totales = Object.entries(d.totales ?? {}) as [string, { generado: number; referencia: number; diferencia: number }][];
  return (
    <>
      <p className="text-sm text-smn-gris-700">
        {d.iguales} de {d.presentados} renglones son idénticos al TXT que Fiscal subió al SAT. Cada proveedor con diferencia necesita un motivo, para saber si es un ajuste a mano de
        Fiscal, una regla distinta o un error.
      </p>
      {totales.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[28rem] text-sm">
            <thead className="text-left text-[13px] text-smn-gris-500">
              <tr>
                <th className="py-1">Total</th>
                <th className="text-right">Plataforma</th>
                <th className="text-right">Presentado</th>
                <th className="text-right">Diferencia</th>
              </tr>
            </thead>
            <tbody>
              {totales.map(([k, v]) => (
                <tr key={k} className="border-t border-smn-gris-100">
                  <td className="py-1">{k.replace(/^\d+ · /, "")}</td>
                  <td className="text-right tabular-nums">{pesosEnteros(v.generado)}</td>
                  <td className="text-right tabular-nums">{pesosEnteros(v.referencia)}</td>
                  <td className={`text-right tabular-nums ${v.diferencia ? "font-semibold" : "text-smn-gris-500"}`}>{pesosEnteros(v.diferencia)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ul className="mt-4 space-y-3">
        {(d.diferencias as DiferenciaProveedor[]).map((x) => {
          const e = edicion[x.rfc];
          return (
            <li key={x.rfc} className="rounded-2xl border border-smn-gris-100 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{x.nombre ?? x.rfc}</span>
                <span className="text-[13px] text-smn-gris-500">{x.rfc}</span>
                <Insignia className="bg-smn-gris-100 text-smn-gris-700">{x.que}</Insignia>
                {x.motivo ? <Insignia className="bg-emerald-100 text-emerald-800">Con motivo</Insignia> : <Insignia className="bg-amber-100 text-amber-800">Falta motivo</Insignia>}
              </div>
              {x.campos.length > 0 && (
                <ul className="mt-1 text-[13px] text-smn-gris-700">
                  {x.campos.map((f, k) => (
                    <li key={k}>
                      {f.campo.replace(/^\d+ · /, "")}: plataforma {f.generado || "vacío"}, presentado {f.referencia || "vacío"}
                    </li>
                  ))}
                </ul>
              )}
              {x.motivo && !e && (
                <p className="mt-1">
                  <span className="font-semibold">{x.motivo_texto}</span>
                  {x.nota && <> · «{x.nota}»</>}
                  <span className="text-[13px] text-smn-gris-500">
                    {" "}
                    · {x.por} {x.en && fechaLocal(x.en)}
                  </span>
                </p>
              )}
              {puede(PERMISO_OPERAR) &&
                (e ? (
                  <div className="mt-2 grid gap-2 sm:grid-cols-[16rem_1fr_auto_auto]">
                    <Selector etiqueta="Motivo" valor={e.motivo} cambiar={(v) => setEdicion({ ...edicion, [x.rfc]: { ...e, motivo: v } })} opciones={Object.entries(d.motivos as Record<string, string>).map(([valor, texto]) => ({ valor, texto }))} />
                    <input value={e.nota} onChange={(ev) => setEdicion({ ...edicion, [x.rfc]: { ...e, nota: ev.target.value } })} placeholder="Nota (obligatoria si es «Otro»)" className={`${ENTRADA} self-end`} />
                    <Boton className="self-end" onClick={() => guardar(x)}>
                      Guardar
                    </Boton>
                    <Boton variante="fantasma" className="self-end" onClick={() => setEdicion(({ [x.rfc]: _, ...resto }) => resto)}>
                      Cancelar
                    </Boton>
                  </div>
                ) : (
                  <button onClick={() => setEdicion({ ...edicion, [x.rfc]: { motivo: x.motivo ?? "ajuste_fiscal", nota: x.nota ?? "" } })} className="mt-2 inline-flex items-center gap-1 text-[13px] font-semibold underline">
                    <PenLine className="h-3.5 w-3.5" /> {x.motivo ? "Cambiar motivo" : "Poner motivo"}
                  </button>
                ))}
            </li>
          );
        })}
      </ul>
    </>
  );
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// ---------------------------------------------------------------- proveedor en palabras

const TASA_TEXTO: Record<string, string> = { "16": "con IVA 16 %", "8": "con IVA 8 %", "0": "a tasa 0 %", no_objeto: "sin IVA por ley (no objeto)", exento: "exento", retencion: "IVA retenido" };

export function Rastreo({ p, rfc, nombre, cerrar }: { p: Periodo; rfc: string; nombre: string | null; cerrar: () => void }) {
  const avisar = useAvisos();
  const [ops, setOps] = useState<Operacion[] | null>(null);
  useEffect(() => {
    api<Operacion[]>(`${RUTA}/periodos/${p.id}/operaciones?rfc=${encodeURIComponent(rfc)}`).then(setOps).catch((e) => avisar(mensajeDe(e), "info"));
  }, [p.id, rfc, avisar]);
  const resumen = useMemo(() => {
    if (!ops) return null;
    const entran = ops.filter((o) => o.incluida);
    const total = entran.reduce((s, o) => s + Number(o.monto ?? 0), 0);
    const iva = entran.reduce((s, o) => s + Number(o.iva16) + Number(o.iva8), 0);
    const porTasa = entran.reduce<Record<string, number>>((a, o) => ({ ...a, [o.tasa ?? "?"]: (a[o.tasa ?? "?"] ?? 0) + 1 }), {});
    return { entran, total, iva, porTasa, fuera: ops.length - entran.length };
  }, [ops]);
  return (
    <Modal titulo={`${nombre ?? rfc}`} cerrar={cerrar} ancho="max-w-4xl">
      {!ops || !resumen ? (
        <Esqueleto className="h-32" />
      ) : (
        <>
          <p className="text-base">
            En {MESES[p.mes - 1].toLowerCase()} {p.anio} se declaran {resumen.entran.length} movimiento(s) de este proveedor por {pesosEnteros(resumen.total)}, con {pesosEnteros(resumen.iva)} de IVA:{" "}
            {Object.entries(resumen.porTasa)
              .map(([t, n]) => `${n} ${TASA_TEXTO[t] ?? t}`)
              .join(", ")}
            .{resumen.fuera > 0 && ` Otros ${resumen.fuera} movimiento(s) no entran; abajo dice por qué.`}
          </p>
          <p className="mt-1 text-[13px] text-smn-gris-500">RFC {rfc}. Cada renglón dice de qué reporte y de qué renglón salió, para buscarlo en Intelisis.</p>
          <div className="mt-4 max-h-[55vh] overflow-auto">
            <table className="w-full min-w-[40rem] text-sm">
              <thead className="text-left text-[13px] text-smn-gris-500">
                <tr>
                  <th className="py-1">Movimiento</th>
                  <th>Qué se hizo</th>
                  <th className="text-right">Monto</th>
                  <th className="text-right">IVA</th>
                </tr>
              </thead>
              <tbody>
                {ops.map((o) => (
                  <tr key={o.id} className={`border-t border-smn-gris-100 align-top ${o.incluida ? "" : "text-smn-gris-500"}`}>
                    <td className="py-1.5">
                      {o.referencia}
                      <span className="block text-[13px] text-smn-gris-500">
                        {o.fuente_nombre}, renglón {o.renglon}
                      </span>
                    </td>
                    <td>
                      {o.incluida ? `Entra ${TASA_TEXTO[o.tasa ?? ""] ?? ""}` : "No entra"}
                      <span className="block text-[13px] text-smn-gris-500">{o.regla_texto.split(": ").slice(1).join(": ") || o.regla_texto}</span>
                      {o.nota && <span className="block text-[13px] text-smn-gris-500">{o.nota}</span>}
                    </td>
                    <td className="text-right tabular-nums">{pesosEnteros(o.monto)}</td>
                    <td className="text-right tabular-nums">{pesosEnteros(Number(o.iva16) + Number(o.iva8))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {ops.length === 0 && <p className="text-sm text-smn-gris-500">Este proveedor viene solo de ajustes de Fiscal.</p>}
          </div>
        </>
      )}
    </Modal>
  );
}

export function Proveedores({ p }: { p: Periodo }) {
  const avisar = useAvisos();
  const [filas, setFilas] = useState<Tercero[] | null>(null);
  const [buscar, setBuscar] = useState("");
  const [rastreo, setRastreo] = useState<Tercero | null>(null);
  useEffect(() => {
    api<Tercero[]>(`${RUTA}/periodos/${p.id}/terceros`).then(setFilas).catch((e) => avisar(mensajeDe(e), "info"));
  }, [p.id, p.procesado_en, avisar]);
  if (!p.procesado_en) return <p className={`${TARJETA} mt-6 text-sm text-smn-gris-500`}>Primero procesa el mes.</p>;
  if (!filas) return <Esqueleto className="mt-6 h-40" />;
  const r = (t: Tercero, c: string) => t.redondeados[c] ?? 0;
  const iva = (t: Tercero) => r(t, "iva16") + r(t, "iva8");
  const total = (t: Tercero) => r(t, "base16") + r(t, "base8") + r(t, "base0") + r(t, "exento") + r(t, "no_objeto") + iva(t);
  const grupo = (t: Tercero) =>
    [r(t, "base16") + r(t, "base8") ? "con IVA" : "", r(t, "base0") ? "tasa 0 %" : "", r(t, "no_objeto") + r(t, "exento") ? "sin IVA por ley" : "", r(t, "iva_retenido") ? "con IVA retenido" : ""].filter(Boolean).join(", ");
  const q = buscar.trim().toUpperCase();
  const vistas = filas.filter((t) => !q || t.rfc.includes(q) || (t.nombre ?? "").toUpperCase().includes(q)).sort((a, b) => iva(b) - iva(a) || total(b) - total(a));
  return (
    <div className={`${TARJETA} mt-6`}>
      <h2 className="text-lg font-semibold">A quién le pagamos y cuánto IVA nos acreditamos</h2>
      <p className="text-sm text-smn-gris-500">
        {filas.length} proveedores. Ordenados por <Termino t="IVA acreditable" />. Toca uno para ver de qué pagos y facturas sale.
      </p>
      <input value={buscar} onChange={(e) => setBuscar(e.target.value)} placeholder="Buscar por nombre o RFC" className={`${ENTRADA} mt-3 max-w-sm`} />
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[40rem] text-sm">
          <thead className="text-left text-[13px] text-smn-gris-500">
            <tr>
              <th className="py-1">Proveedor</th>
              <th>Cómo va</th>
              <th className="text-right">Se le pagó</th>
              <th className="text-right">IVA</th>
            </tr>
          </thead>
          <tbody>
            {vistas.map((t) => (
              <tr key={t.id} onClick={() => setRastreo(t)} className="cursor-pointer border-t border-smn-gris-100 hover:bg-smn-gris-100/50">
                <td className="py-2">
                  <span className="font-semibold">{t.nombre || t.rfc}</span>
                  <span className="block text-[13px] text-smn-gris-500">
                    {t.rfc}
                    {t.ajustado && " · con ajuste de Fiscal"}
                  </span>
                </td>
                <td className="text-[13px]">{grupo(t)}</td>
                <td className="text-right tabular-nums">{pesosEnteros(total(t))}</td>
                <td className="text-right font-semibold tabular-nums">{pesosEnteros(iva(t))}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-smn-gris-300 font-semibold">
              <td className="py-2">Total</td>
              <td />
              <td className="text-right tabular-nums">{pesosEnteros(filas.reduce((s, t) => s + total(t), 0))}</td>
              <td className="text-right tabular-nums">{pesosEnteros(filas.reduce((s, t) => s + iva(t), 0))}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <AnimatePresence>{rastreo && <Rastreo p={p} rfc={rastreo.rfc} nombre={rastreo.nombre} cerrar={() => setRastreo(null)} />}</AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------- paso 4: firmas y descarga

export function Firmar({
  p,
  c,
  setC,
  accion,
  ocupado,
}: {
  p: Periodo;
  c: Comprobaciones | null;
  setC: (c: Comprobaciones) => void;
  accion: (clave: string, f: () => Promise<Periodo | void>, exito?: string) => void;
  ocupado: string | null;
}) {
  const avisar = useAvisos();
  const { puede, yo } = useSesion();
  const [notas, setNotas] = useState({ revision: "", fiscal: "" });
  if (!p.procesado_en) return <p className={`${TARJETA} mt-6 text-sm text-smn-gris-500`}>Primero sube los reportes y procesa el mes (paso 1).</p>;
  if (!c) return <Esqueleto className="mt-6 h-40" />;
  const archivo = (sufijo: string) => `DIOT ${p.empresa.codigo} ${p.nombre.toLowerCase()} ${sufijo}`;
  const cerrado = p.estado === "cerrado";
  const firmar = async (tipo: "revision" | "fiscal") => {
    try {
      setC(await api<Comprobaciones>(`${RUTA}/periodos/${p.id}/firmas`, { cuerpo: { tipo, nota: notas[tipo] || null } }));
      avisar("Firma guardada.", "exito");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };
  const retirar = async (tipo: "revision" | "fiscal") => {
    try {
      setC(await api<Comprobaciones>(`${RUTA}/periodos/${p.id}/firmas/${tipo}`, { metodo: "DELETE" }));
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };
  const rev = c.firmas.revision;
  const fis = c.firmas.fiscal;
  const faltan = c.comprobaciones.filter((x) => x.estado === "falla" || x.estado === "revisar");
  const caja = (titulo: string, ayuda: string, tipo: "revision" | "fiscal", f: typeof rev, puedeFirmar: boolean, porQueNo: string | null) => (
    <div className={`rounded-2xl border p-4 ${f.firmada ? "border-emerald-200 bg-emerald-50/60 dark:border-emerald-900 dark:bg-emerald-950/30" : "border-smn-gris-100"}`}>
      <p className="font-semibold">{titulo}</p>
      <p className="text-sm text-smn-gris-500">{ayuda}</p>
      {f.firmada ? (
        <p className="mt-2 text-sm">
          <CheckCircle2 className="mr-1 inline h-4 w-4 text-emerald-600" />
          Firmó <span className="font-semibold">{f.por}</span> el {f.en && fechaLocal(f.en)}
          {f.nota && <> · «{f.nota}»</>}
          {puede(PERMISO_OPERAR) && !cerrado && (
            <button onClick={() => retirar(tipo)} className="ml-2 text-[13px] font-medium text-smn-gris-500 underline">
              Quitar firma
            </button>
          )}
        </p>
      ) : (
        <>
          {f.anterior_invalida && <p className="mt-2 text-[13px] text-amber-700">Había una firma, pero el TXT cambió al volver a procesar; hay que firmar otra vez.</p>}
          {puedeFirmar ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <input value={notas[tipo]} onChange={(e) => setNotas({ ...notas, [tipo]: e.target.value })} placeholder="Nota (opcional)" className={`${ENTRADA} min-w-0 flex-1`} />
              <Boton onClick={() => firmar(tipo)}>
                <PenLine className="h-4 w-4" /> Firmar
              </Boton>
            </div>
          ) : (
            <p className="mt-2 text-sm text-smn-gris-500">{porQueNo}</p>
          )}
        </>
      )}
    </div>
  );
  const porQueRevision = !p.resumen
    ? "Todavía no hay TXT."
    : c.pendientes
      ? `Faltan ${c.pendientes} decisión(es) del paso 2.`
      : faltan.length
        ? `Faltan por revisar: ${faltan.map((x) => x.titulo.toLowerCase()).join(", ")}.`
        : !puede(PERMISO_OPERAR)
          ? "Necesitas permiso para operar la DIOT."
          : null;
  const porQueFiscal = !rev.firmada
    ? "Primero firma quien revisó las comprobaciones."
    : !puede(PERMISO_APROBAR)
      ? "Lo firma alguien de Fiscal con permiso de aprobar criterios."
      : rev.usuario_id === yo.usuario.id
        ? "Lo firma una persona distinta de quien revisó."
        : null;
  return (
    <div className="mt-6 space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        {caja("1. Revisé las comprobaciones", "Quien opera la DIOT: los cuadres están bien y nada quedó sin explicar.", "revision", rev, !cerrado && !porQueRevision && c.puede_firmar_revision, porQueRevision)}
        {caja("2. Visto bueno de Fiscal", "Fiscal: los criterios y las decisiones del mes son correctos.", "fiscal", fis, !cerrado && !porQueFiscal, porQueFiscal)}
      </div>
      <div className={TARJETA}>
        <p className="font-semibold">Descargar</p>
        {!(rev.firmada && fis.firmada) && (
          <p className="mt-1 text-sm text-amber-700">
            {c.firmas_obligatorias ? "El TXT se descarga cuando estén las dos firmas." : "Todavía no están las dos firmas. Mientras dure el piloto el TXT se puede descargar, pero la evidencia dirá que no se firmó."}
          </p>
        )}
        {p.motivo_sin_txt && <p className="mt-1 text-sm text-smn-gris-500">TXT pendiente: {p.motivo_sin_txt}</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          {puede(PERMISO_OPERAR) && (
            <Boton disabled={!p.puede_txt} onClick={() => accion("txt", () => descargar(`${RUTA}/periodos/${p.id}/txt`, archivo("carga SAT.txt")))} cargando={ocupado === "txt"}>
              <Download className="h-4 w-4" /> TXT para el SAT
            </Boton>
          )}
          <Boton variante="secundario" onClick={() => accion("ev", () => descargar(`${RUTA}/periodos/${p.id}/evidencia`, archivo("evidencia.xlsx")))} cargando={ocupado === "ev"}>
            <Download className="h-4 w-4" /> Evidencia con resumen (Excel)
          </Boton>
          {puede(PERMISO_OPERAR) && p.estado !== "abierto" && (
            <Boton
              variante="fantasma"
              className="ml-auto"
              disabled={!cerrado && !p.puede_txt}
              onClick={() => accion("cerrar", () => api<Periodo>(`${RUTA}/periodos/${p.id}`, { metodo: "PATCH", cuerpo: { estado: cerrado ? "procesado" : "cerrado" } }))}
              cargando={ocupado === "cerrar"}
            >
              {cerrado ? <Unlock className="h-4 w-4" /> : <Lock className="h-4 w-4" />} {cerrado ? "Reabrir" : "Cerrar el mes (ya se presentó)"}
            </Boton>
          )}
        </div>
        <p className="mt-3 text-[13px] text-smn-gris-500">La evidencia trae en su primera hoja las 9 comprobaciones, las firmas y dónde están los ajustes con su motivo. Sirve si el SAT pregunta.</p>
      </div>
    </div>
  );
}
