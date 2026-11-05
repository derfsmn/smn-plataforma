"use client";
// Puerta de IA: estado de Ollama y de la API externa, topes de gasto, tareas, prueba y últimas llamadas.

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { Cpu, Cloud, Send, CircleAlert, CircleCheck, Save, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  api, dolares, fechaLocal, mensajeDe, pesos,
  type CostosReales, type EstadoIA, type LlamadaIA, type ResultadoPrueba, type TareaIA, type Tope,
} from "@/lib/api";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Encabezado, Entrada, Esqueleto, Insignia, Selector } from "@/componentes/ui";

const PROVEEDORES = [
  { valor: "ollama", texto: "Ollama (local)" },
  { valor: "api", texto: "API externa" },
  { valor: "ollama_y_api_respaldo", texto: "Ollama y API de respaldo" },
];
const RESULTADOS: Record<string, { texto: string; clase: string }> = {
  ok: { texto: "Bien", clase: "bg-smn-gris-100 text-smn-gris-700" },
  error: { texto: "Error", clase: "bg-red-500/10 text-red-700 dark:text-red-400" },
  rechazada_por_tope: { texto: "Tope", clase: "bg-smn-naranja/15 text-aviso-texto" },
  rechazada_por_modelo: { texto: "Declinó", clase: "bg-smn-naranja/15 text-aviso-texto" },
};

type FormaTope = { tope: string; aviso: string; al_superar: Tope["al_superar"] };
const vacio: FormaTope = { tope: "", aviso: "80", al_superar: "rechazar" };
const llave = (alcance: string, modulo: string | null) => (modulo ? `modulo:${modulo}` : alcance);

export default function AdminIA() {
  const avisar = useAvisos();
  const [estado, setEstado] = useState<EstadoIA | null>(null);
  const [topes, setTopes] = useState<Record<string, FormaTope>>({});
  const [tareas, setTareas] = useState<TareaIA[]>([]);
  const [llamadas, setLlamadas] = useState<LlamadaIA[] | null>(null);
  const [guardando, setGuardando] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const [e, t, ts, ll] = await Promise.all([
        api<EstadoIA>("/api/ia/estado"),
        api<Tope[]>("/api/ia/topes"),
        api<TareaIA[]>("/api/ia/tareas"),
        api<LlamadaIA[]>("/api/ia/llamadas?limite=20"),
      ]);
      setEstado(e);
      setTopes(Object.fromEntries(t.map((x) => [llave(x.alcance, x.modulo), { tope: String(Number(x.tope_mxn)), aviso: String(x.aviso_pct), al_superar: x.al_superar }])));
      setTareas(ts);
      setLlamadas(ll);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  }, [avisar]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const guardarTopes = async () => {
    const lista: Tope[] = [];
    for (const [k, f] of Object.entries(topes)) {
      if (f.tope.trim() === "") continue;
      const monto = Number(f.tope);
      if (!(monto >= 0)) return avisar("Revisa los montos: deben ser números de 0 en adelante.", "info");
      const [alcance, modulo] = k.startsWith("modulo:") ? ["modulo", k.slice(7)] : [k, null];
      lista.push({ alcance: alcance as Tope["alcance"], modulo, tope_mxn: monto.toFixed(2), aviso_pct: Number(f.aviso) || 80, al_superar: f.al_superar });
    }
    setGuardando(true);
    try {
      await api("/api/ia/topes", { metodo: "PUT", cuerpo: lista });
      avisar("Topes guardados", "exito");
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setGuardando(false);
    }
  };

  const cambiarTarea = async (codigo: string, cambio: Partial<TareaIA>) => {
    const anterior = tareas;
    setTareas((ts) => ts.map((t) => (t.codigo === codigo ? { ...t, ...cambio } : t)));
    try {
      await api(`/api/ia/tareas/${codigo}`, { metodo: "PATCH", cuerpo: cambio });
    } catch (e) {
      setTareas(anterior);
      avisar(mensajeDe(e), "info");
    }
  };

  if (!estado) {
    return (
      <>
        <Encabezado titulo="Inteligencia artificial" />
        <div className="grid gap-4 md:grid-cols-2">
          <Esqueleto className="h-48" />
          <Esqueleto className="h-48" />
        </div>
      </>
    );
  }

  const filasTope = [
    { k: "plataforma", nombre: "Plataforma", periodo: "al mes", nota: "Sin este tope la API externa queda apagada." },
    { k: "usuario_dia", nombre: "Por persona", periodo: "al día", nota: "Cada persona por separado." },
    ...estado.gastos.filter((g) => g.modulo).map((g) => ({ k: `modulo:${g.modulo}`, nombre: g.nombre.replace(" (mes)", ""), periodo: "al mes", nota: "" })),
  ];

  return (
    <>
      <Encabezado
        titulo="Inteligencia artificial"
        descripcion="Toda llamada a una IA pasa por aquí: se elige Ollama o la API externa, se revisa el tope y se registra."
      />

      <div className="grid gap-4 md:grid-cols-2">
        <Entrada>
          <Tarjeta icono={<Cpu className="h-5 w-5" />} titulo="Ollama (local)" encendida={estado.ollama_disponible && !!estado.ollama_modelo} etiqueta={estado.ollama_disponible ? (estado.ollama_modelo ? "Disponible" : "Sin modelo") : "Sin conexión"}>
            <Dato nombre="Dirección" valor={estado.ollama_url} />
            <Dato nombre="Modelo" valor={estado.ollama_modelo ?? "Sin configurar"} />
            <Dato nombre="Modelos descargados" valor={estado.ollama_modelos.length ? estado.ollama_modelos.join(", ") : "—"} />
            <p className="mt-3 text-[13px] text-smn-gris-500">
              Sin costo por llamada. Corre en el equipo; para producción hace falta un equipo con GPU.{" "}
              <Link href="/admin/configuracion" className="font-semibold text-tinta underline-offset-2 hover:underline">Cambiar en Configuración</Link>
            </p>
          </Tarjeta>
        </Entrada>
        <Entrada retraso={0.05}>
          <Tarjeta icono={<Cloud className="h-5 w-5" />} titulo={`API externa (${estado.api_proveedor})`} encendida={estado.api_encendida} etiqueta={estado.api_encendida ? "Encendida" : "Apagada"}>
            <Dato nombre="Proveedor" valor={estado.api_proveedor} />
            <Dato nombre="Modelo" valor={estado.api_modelo} />
            <Dato nombre="Precio por millón de tokens" valor={`${dolares(estado.precio_entrada_usd_mtok)} entrada · ${dolares(estado.precio_salida_usd_mtok)} salida`} />
            <Dato nombre="Tipo de cambio" valor={estado.tipo_cambio_mxn ? `${pesos(estado.tipo_cambio_mxn)} por dólar` : "Sin capturar"} />
            {estado.api_motivos.length > 0 && (
              <ul className="mt-3 space-y-1 rounded-xl bg-aviso-fondo p-3 text-sm text-aviso-texto">
                {estado.api_motivos.map((m) => (
                  <li key={m} className="flex gap-2">
                    <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" /> {m}
                  </li>
                ))}
              </ul>
            )}
            <Link href="/admin/configuracion" className="mt-3 inline-block text-[13px] font-semibold underline-offset-2 hover:underline">Cambiar llave, modelo, precios o tipo de cambio en Configuración</Link>
          </Tarjeta>
        </Entrada>
      </div>

      <Entrada retraso={0.1} className="mt-6">
        <Seccion
          titulo="Gasto de la API externa este mes"
          descripcion={estado.costo_real_activo
            ? "El tope de plataforma usa el costo real de OpenAI en los días ya cerrados y la estimación en los días que aún no llegan. Los topes por módulo y por persona usan la estimación."
            : "El costo se estima con los tokens que reporta la API, los precios y el tipo de cambio configurados. Con OpenAI puedes usar el costo real capturando la llave de administrador en Configuración."}
        >
          <div className="space-y-4">
            {estado.gastos.map((g) => (
              <Barra key={g.nombre} nombre={g.nombre} gastado={Number(g.gastado_mxn)} tope={g.tope_mxn === null ? null : Number(g.tope_mxn)} aviso={Number(topes[llave(g.alcance, g.modulo)]?.aviso ?? 80)} />
            ))}
          </div>
        </Seccion>
      </Entrada>

      {estado.api_proveedor.toLowerCase() === "openai" && (
        <Entrada retraso={0.12} className="mt-6">
          <CostoReal />
        </Entrada>
      )}

      <Entrada retraso={0.15} className="mt-6">
        <Seccion titulo="Topes de gasto" descripcion="En pesos. Deja vacío para no poner tope. Al llegar al aviso, la campana avisa a quien administra la IA.">
          <div className="space-y-3">
            {filasTope.map(({ k, nombre, periodo, nota }) => {
              const f = topes[k] ?? vacio;
              const poner = (cambio: Partial<FormaTope>) => setTopes((t) => ({ ...t, [k]: { ...f, ...cambio } }));
              return (
                <div key={k} className="grid items-end gap-3 rounded-xl border border-smn-gris-100 p-3 sm:grid-cols-[1.3fr_1fr_0.7fr_1.2fr]">
                  <div>
                    <p className="font-semibold">{nombre}</p>
                    <p className="text-[13px] text-smn-gris-500">{nota || `Tope ${periodo}`}</p>
                  </div>
                  <label className="block">
                    <span className="mb-1 block text-[13px] font-semibold text-smn-gris-700">Tope {periodo} (MXN)</span>
                    <input inputMode="decimal" value={f.tope} onChange={(e) => poner({ tope: e.target.value })} placeholder="Sin tope" className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3 py-2 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20" />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-[13px] font-semibold text-smn-gris-700">Aviso (%)</span>
                    <input inputMode="numeric" value={f.aviso} onChange={(e) => poner({ aviso: e.target.value })} className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3 py-2 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20" />
                  </label>
                  <Selector
                    etiqueta="Al llegar al tope"
                    valor={f.al_superar}
                    cambiar={(v) => poner({ al_superar: v as FormaTope["al_superar"] })}
                    opciones={[
                      { valor: "rechazar", texto: "Rechazar la llamada" },
                      { valor: "usar_ollama", texto: "Usar Ollama" },
                    ]}
                  />
                </div>
              );
            })}
          </div>
          <div className="mt-4 flex justify-end">
            <Boton onClick={guardarTopes} cargando={guardando}>
              <Save className="h-4 w-4" /> Guardar topes
            </Boton>
          </div>
        </Seccion>
      </Entrada>

      <Entrada retraso={0.2} className="mt-6 grid gap-6 lg:grid-cols-2">
        <Seccion titulo="Tareas de IA" descripcion="Cada módulo registra sus tareas. Aquí se elige qué IA usa cada una.">
          <ul className="space-y-3">
            {tareas.map((t) => (
              <li key={t.codigo} className="rounded-xl border border-smn-gris-100 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-mono text-sm font-semibold">{t.codigo}</p>
                    <p className="text-sm text-smn-gris-500">{t.descripcion}</p>
                  </div>
                  <button
                    role="switch"
                    aria-checked={t.activa}
                    aria-label={`Tarea ${t.codigo} ${t.activa ? "encendida" : "apagada"}`}
                    onClick={() => cambiarTarea(t.codigo, { activa: !t.activa })}
                    className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${t.activa ? "bg-smn-naranja" : "bg-smn-gris-300"}`}
                  >
                    <motion.span layout className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow ${t.activa ? "right-0.5" : "left-0.5"}`} />
                  </button>
                </div>
                <Selector className="mt-3" etiqueta="Usa" valor={t.proveedor_ia} cambiar={(v) => cambiarTarea(t.codigo, { proveedor_ia: v as TareaIA["proveedor_ia"] })} opciones={PROVEEDORES} />
                {t.proveedor_ia === "ollama" && (
                  // Modelo propio de la tarea (p. ej. uno con visión para comparar fotos); vacío = el general de Configuración
                  <Selector
                    className="mt-3"
                    etiqueta="Modelo de Ollama"
                    valor={t.modelo ?? ""}
                    cambiar={(v) => cambiarTarea(t.codigo, { modelo: v || null })}
                    opciones={[
                      { valor: "", texto: `El general (${estado?.ollama_modelo ?? "sin configurar"})` },
                      ...[...new Set([...(estado?.ollama_modelos ?? []), ...(t.modelo ? [t.modelo] : [])])].map((m) => ({ valor: m, texto: m })),
                    ]}
                  />
                )}
              </li>
            ))}
          </ul>
        </Seccion>
        <Probar alTerminar={cargar} estado={estado} />
      </Entrada>

      <Entrada retraso={0.25} className="mt-6">
        <Seccion titulo="Últimas llamadas">
          {!llamadas ? (
            <Esqueleto className="h-24" />
          ) : llamadas.length === 0 ? (
            <p className="py-6 text-center text-sm text-smn-gris-500">Todavía no hay llamadas.</p>
          ) : (
            <div className="-mx-4 overflow-x-auto sm:mx-0">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-smn-gris-100 text-left text-[13px] text-smn-gris-500">
                    <th className="px-4 py-2 font-semibold sm:pl-0">Cuándo</th>
                    <th className="px-2 py-2 font-semibold">Tarea</th>
                    <th className="px-2 py-2 font-semibold">IA</th>
                    <th className="px-2 py-2 text-right font-semibold">Tokens</th>
                    <th className="px-2 py-2 text-right font-semibold">Costo</th>
                    <th className="px-2 py-2 font-semibold">Resultado</th>
                  </tr>
                </thead>
                <tbody>
                  {llamadas.map((l) => (
                    <tr key={l.id} className="border-b border-smn-gris-100 last:border-0" title={l.detalle ?? undefined}>
                      <td className="px-4 py-2 whitespace-nowrap text-smn-gris-500 sm:pl-0">{fechaLocal(l.ocurrido_en)}</td>
                      <td className="px-2 py-2 font-mono text-[13px]">{l.tarea}</td>
                      <td className="px-2 py-2">{l.proveedor_ia === "api" ? "API" : "Ollama"} <span className="text-[13px] text-smn-gris-500">{l.modelo}</span></td>
                      <td className="px-2 py-2 text-right tabular-nums">{(l.tokens_entrada + l.tokens_salida).toLocaleString("es-MX")}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{pesos(l.costo_mxn)}</td>
                      <td className="px-2 py-2">
                        <Insignia className={RESULTADOS[l.resultado]?.clase ?? ""}>{RESULTADOS[l.resultado]?.texto ?? l.resultado}</Insignia>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Seccion>
      </Entrada>
    </>
  );
}

function Probar({ alTerminar, estado }: { alTerminar: () => void; estado: EstadoIA }) {
  const [mensaje, setMensaje] = useState("Escribe en una línea qué es Súper Naturista.");
  const [proveedor, setProveedor] = useState<"ollama" | "api">("ollama");
  const [resultado, setResultado] = useState<ResultadoPrueba | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  const probar = async () => {
    setCargando(true);
    setError(null);
    setResultado(null);
    try {
      setResultado(await api<ResultadoPrueba>("/api/ia/probar", { cuerpo: { mensaje, proveedor } }));
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setCargando(false);
      alTerminar();
    }
  };

  return (
    <Seccion titulo="Probar" descripcion="Manda un mensaje corto para revisar la conexión. Queda registrado como cualquier llamada.">
      <div className="mb-3 grid grid-cols-2 gap-2">
        {(["ollama", "api"] as const).map((p) => (
          <button
            key={p}
            onClick={() => setProveedor(p)}
            className={`rounded-xl border-2 p-2.5 text-sm font-semibold transition-colors ${proveedor === p ? "border-smn-naranja bg-smn-naranja/10" : "border-smn-gris-100"}`}
          >
            {p === "ollama" ? "Ollama" : "API externa"}
          </button>
        ))}
      </div>
      <textarea
        value={mensaje}
        onChange={(e) => setMensaje(e.target.value)}
        rows={3}
        maxLength={2000}
        className="w-full resize-none rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
      />
      {proveedor === "api" && !estado.api_encendida && <p className="mt-2 text-[13px] text-smn-gris-500">La API externa está apagada; la prueba te dirá qué falta.</p>}
      <Boton onClick={probar} cargando={cargando} disabled={!mensaje.trim()} className="mt-3 w-full">
        <Send className="h-4 w-4" /> Probar
      </Boton>
      <AnimatePresence mode="wait">
        {error && (
          <motion.p key="e" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} role="alert" className="mt-3 rounded-xl bg-red-500/10 px-3 py-2.5 text-sm font-semibold text-red-700 dark:text-red-400">
            {error}
          </motion.p>
        )}
        {resultado && (
          <motion.div key="r" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-3 rounded-xl bg-smn-gris-50 p-3">
            <p className="text-sm whitespace-pre-wrap">{resultado.texto || "(sin texto)"}</p>
            <p className="mt-2 text-[13px] text-smn-gris-500">
              {resultado.proveedor === "api" ? "API" : "Ollama"} · {resultado.modelo} · {resultado.tokens_entrada + resultado.tokens_salida} tokens · {pesos(resultado.costo_mxn)} · {(resultado.duracion_ms / 1000).toFixed(1)} s
              {!resultado.completa && " · cortada por largo"}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </Seccion>
  );
}

const fechaCorta = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("es-MX", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
const conSigno = (n: number) => `${n > 0 ? "+" : ""}${pesos(n)}`;

function CostoReal() {
  const avisar = useAvisos();
  const [datos, setDatos] = useState<CostosReales | null>(null);
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    api<CostosReales>("/api/ia/costos-reales").then(setDatos).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);

  const actualizar = async () => {
    setCargando(true);
    try {
      setDatos(await api<CostosReales>("/api/ia/costos-reales/sincronizar", { metodo: "POST" }));
      avisar("Costo real actualizado", "exito");
    } catch (e) {
      avisar(mensajeDe(e), "info");
      api<CostosReales>("/api/ia/costos-reales").then(setDatos).catch(() => {});
    } finally {
      setCargando(false);
    }
  };

  if (!datos) return <Esqueleto className="h-40" />;
  const conReal = datos.dias.filter((d) => d.real_mxn !== null);
  const totalReal = conReal.reduce((a, d) => a + Number(d.real_mxn), 0);
  const totalEstimado = conReal.reduce((a, d) => a + Number(d.estimado_mxn), 0);

  return (
    <Seccion
      titulo="Costo real de OpenAI"
      descripcion="Lo que OpenAI cobró por día (sus días van en horario UTC y llegan con unas horas de retraso). Se actualiza solo cada 6 horas; el día de hoy aparece cuando cierra."
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-smn-gris-500">
          {datos.proyecto ? <>Proyecto <span className="font-semibold text-tinta">{datos.proyecto}</span> · </> : datos.activo ? <>Toda la organización · </> : null}
          {datos.ultimo_intento ? `Última revisión ${fechaLocal(datos.ultimo_intento)}` : "Sin revisar desde que se encendió la plataforma"}
        </div>
        {datos.activo && (
          <Boton variante="secundario" onClick={actualizar} disabled={cargando}>
            <RefreshCw className={`mr-1.5 h-4 w-4 ${cargando ? "animate-spin" : ""}`} /> Actualizar
          </Boton>
        )}
      </div>
      {(datos.motivo || datos.error) && (
        <p className="mb-4 flex gap-2 rounded-xl bg-aviso-fondo p-3 text-sm text-aviso-texto">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {datos.motivo ?? datos.error}
            {datos.motivo && (
              <Link href="/admin/configuracion" className="ml-1 font-semibold underline-offset-2 hover:underline">Ir a Configuración</Link>
            )}
          </span>
        </p>
      )}
      {datos.activo && !datos.proyecto && (
        <p className="mb-4 text-[13px] text-smn-gris-500">Sin ID de proyecto se suma el costo de toda la organización de OpenAI, no solo el de la plataforma.</p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-smn-gris-100 text-left text-[13px] text-smn-gris-500">
              <th className="py-2 font-semibold">Día</th>
              <th className="py-2 text-right font-semibold">Estimado</th>
              <th className="py-2 text-right font-semibold">Real</th>
              <th className="hidden py-2 text-right font-semibold sm:table-cell">Diferencia</th>
            </tr>
          </thead>
          <tbody>
            {datos.dias.map((d) => {
              const real = d.real_mxn === null ? null : Number(d.real_mxn);
              return (
                <tr key={d.fecha} className="border-b border-smn-gris-100 last:border-0">
                  <td className="py-1.5">{fechaCorta(d.fecha)}</td>
                  <td className="py-1.5 text-right tabular-nums">{pesos(Number(d.estimado_mxn))}</td>
                  <td className="py-1.5 text-right font-semibold tabular-nums">
                    {real === null ? <span className="font-normal text-smn-gris-500">Pendiente</span> : (
                      <span title={dolares(Number(d.real_usd), 4)}>{pesos(real)}</span>
                    )}
                  </td>
                  <td className="hidden py-1.5 text-right tabular-nums text-smn-gris-500 sm:table-cell">{real === null ? "—" : conSigno(real - Number(d.estimado_mxn))}</td>
                </tr>
              );
            })}
          </tbody>
          {conReal.length > 0 && (
            <tfoot>
              <tr className="font-semibold">
                <td className="pt-2">Días con real</td>
                <td className="pt-2 text-right tabular-nums">{pesos(totalEstimado)}</td>
                <td className="pt-2 text-right tabular-nums">{pesos(totalReal)}</td>
                <td className="hidden pt-2 text-right tabular-nums sm:table-cell">{conSigno(totalReal - totalEstimado)}</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </Seccion>
  );
}

function Seccion({ titulo, descripcion, children }: { titulo: string; descripcion?: string; children: React.ReactNode }) {
  return (
    <section className="min-w-0 rounded-2xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
      <h2 className="text-lg font-semibold">{titulo}</h2>
      {descripcion && <p className="mt-0.5 mb-4 text-sm text-smn-gris-500">{descripcion}</p>}
      {!descripcion && <div className="mb-3" />}
      {children}
    </section>
  );
}

function Tarjeta({ icono, titulo, encendida, etiqueta, children }: { icono: React.ReactNode; titulo: string; encendida: boolean; etiqueta: string; children: React.ReactNode }) {
  return (
    <section className="h-full min-w-0 rounded-2xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 font-semibold">
          <span className="grid h-9 w-9 place-items-center rounded-xl border border-smn-gris-100 bg-superficie text-smn-naranja">{icono}</span>
          {titulo}
        </h2>
        <Insignia className={encendida ? "bg-tinta text-superficie" : "bg-smn-gris-100 text-smn-gris-700"}>
          {encendida ? <CircleCheck className="mr-1 h-3.5 w-3.5" /> : <CircleAlert className="mr-1 h-3.5 w-3.5" />}
          {etiqueta}
        </Insignia>
      </div>
      {children}
    </section>
  );
}

function Dato({ nombre, valor }: { nombre: string; valor: string }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-4 border-b border-smn-gris-100 py-1.5 text-sm last:border-0">
      <span className="text-smn-gris-500">{nombre}</span>
      <span className="min-w-0 font-semibold break-all">{valor}</span>
    </div>
  );
}

function Barra({ nombre, gastado, tope, aviso }: { nombre: string; gastado: number; tope: number | null; aviso: number }) {
  const pct = tope ? Math.min(100, (gastado / tope) * 100) : 0;
  const color = tope !== null && gastado >= tope ? "bg-red-500" : tope && pct >= aviso ? "bg-amber-500" : "bg-smn-naranja";
  return (
    <div>
      <div className="mb-1 flex flex-wrap justify-between gap-x-4 text-sm">
        <span className="font-semibold">{nombre}</span>
        <span className="text-smn-gris-500 tabular-nums">
          {pesos(gastado)} {tope !== null ? `de ${pesos(tope)}` : "· sin tope"}
        </span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-smn-gris-100">
        <motion.div className={`h-full rounded-full ${color}`} initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }} />
      </div>
    </div>
  );
}
