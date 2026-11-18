"use client";
// Piezas del Comité de producto nuevo que usan la lista, el ciclo y el modo presentación.

import { ImageOff, Plus, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { InsigniaColor } from "@/componentes/semaforo-producto";
import { Boton, Campo, Insignia } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import {
  DECISION, FACTORES_RADAR, INDICADORES, RUTA, urlFoto, VALOR, type Candidato, type Criterio, type Criterios, type Decision,
  type Indicador, type Item, type Peticion, type Reunion, type TiendaPrueba, type UsuarioBreve, type ValorCriterio,
} from "@/lib/comite";

const CAJA = "w-full rounded-lg border border-smn-gris-100 bg-superficie px-3.5 py-2.5 text-[15px] outline-none hover:border-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15";

export function Atender({ p, cerrar, listo }: { p: Peticion; cerrar: () => void; listo: () => void }) {
  const avisar = useAvisos();
  const [respuesta, setRespuesta] = useState("");
  const [guardando, setGuardando] = useState(false);
  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    setGuardando(true);
    try {
      await api(`${RUTA}/peticiones/${p.id}`, { metodo: "PATCH", cuerpo: { estado: "atendida", respuesta: respuesta.trim() || null } });
      avisar("Petición atendida");
      listo();
    } catch (err) {
      avisar(mensajeDe(err), "info");
      setGuardando(false);
    }
  };
  return (
    <Modal titulo="Marcar como atendida" cerrar={cerrar}>
      <form onSubmit={guardar} className="space-y-4">
        <p className="text-sm text-smn-gris-700">«{p.texto}»{p.asistente && ` · ${p.asistente}`}</p>
        <Campo etiqueta="¿Qué se hizo? (opcional)" value={respuesta} onChange={(e) => setRespuesta(e.target.value)} maxLength={1000} />
        <div className="flex justify-end gap-2">
          <Boton type="button" variante="fantasma" onClick={cerrar}>Cancelar</Boton>
          <Boton type="submit" cargando={guardando}>Marcar atendida</Boton>
        </div>
      </form>
    </Modal>
  );
}

/** La foto n del producto (las del cuestionario o de la idea); si no hay, la de internet de la oportunidad o un hueco. */
export function Foto({ i, n = 0, className = "", ancho = 160 }: { i: Item; n?: number; className?: string; ancho?: number }) {
  const [rota, setRota] = useState(false);
  const src = i.fotos > n ? urlFoto(i.id, n, ancho) : n === 0 ? i.foto_externa : null;
  if (!src || rota)
    return (
      <div className={`grid place-items-center bg-smn-gris-50 text-smn-gris-500 ${className}`}>
        <ImageOff className="h-6 w-6" aria-label="Sin foto" />
      </div>
    );
  // eslint-disable-next-line @next/next/no-img-element -- la foto sale de la API con la sesión
  return <img src={src} alt={i.nombre} loading="lazy" decoding="async" onError={() => setRota(true)} className={`bg-smn-gris-50 object-contain ${className}`} />;
}

/** Pre-filtro de Compras: pasa o no pasa, con motivo y los criterios que se revisaron (políticas y criterios nuevos). */
export function Prefiltrar({ i, cerrar, listo }: { i: Item; cerrar: () => void; listo: (r: Reunion) => void }) {
  const avisar = useAvisos();
  const [ref, setRef] = useState<Criterios | null>(null);
  const [resultado, setResultado] = useState<"pasa" | "no_pasa" | null>(i.prefiltro);
  const [motivo, setMotivo] = useState(i.prefiltro_motivo ?? "");
  const [criterios, setCriterios] = useState<Criterio[]>(i.criterios);
  const [nuevo, setNuevo] = useState("");
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    api<Criterios>(`${RUTA}/criterios`).then(setRef).catch(() => setRef({ politicas: [], usados: [] }));
  }, []);

  const agregar = (nombre: string) => {
    const n = nombre.trim();
    if (!n || criterios.some((c) => c.criterio.toLowerCase() === n.toLowerCase())) return;
    setCriterios([...criterios, { criterio: n, valor: "bien", nota: null }]);
    setNuevo("");
  };
  const poner = (k: number, c: Partial<Criterio>) => setCriterios(criterios.map((x, j) => (j === k ? { ...x, ...c } : x)));
  const sugeridos = [...(ref?.usados ?? []), ...(ref?.politicas.map((p) => p.titulo) ?? [])].filter(
    (s, k, todos) => todos.indexOf(s) === k && !criterios.some((c) => c.criterio.toLowerCase() === s.toLowerCase()),
  );

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resultado) return avisar("Elige si pasa o no pasa al comité.", "info");
    setGuardando(true);
    try {
      const r = await api<Reunion>(`${RUTA}/productos/${i.id}/prefiltro`, { metodo: "PUT", cuerpo: { resultado, motivo, criterios } });
      avisar(resultado === "pasa" ? "Pasa al comité" : "No pasa; queda guardado con su motivo");
      listo(r);
    } catch (err) {
      avisar(mensajeDe(err), "info");
      setGuardando(false);
    }
  };

  return (
    <Modal titulo={`Pre-filtro: ${i.nombre}`} cerrar={cerrar} ancho="max-w-2xl">
      <form onSubmit={guardar} className="space-y-5">
        <div className="flex flex-wrap items-center gap-2 text-sm text-smn-gris-700">
          Semáforo: <InsigniaColor color={i.evaluacion?.color ?? null} />
          {i.evaluacion?.puntaje != null && <span>{i.evaluacion.puntaje} de 100</span>}
          {!i.evaluacion || i.evaluacion.estado !== "lista" ? <span className="text-aviso-texto">todavía no tiene semáforo</span> : null}
        </div>

        <fieldset>
          <legend className="mb-1.5 text-sm font-medium text-smn-gris-700">Criterios que revisaste</legend>
          {criterios.length > 0 && (
            <ul className="mb-2 space-y-2">
              {criterios.map((c, k) => (
                <li key={c.criterio} className="flex flex-wrap items-center gap-2 rounded-xl border border-smn-gris-100 p-2">
                  <span className="min-w-0 flex-1 text-[15px] font-medium">{c.criterio}</span>
                  <div className="flex gap-1" role="radiogroup" aria-label={`Cómo sale en ${c.criterio}`}>
                    {(Object.keys(VALOR) as ValorCriterio[]).map((v) => (
                      <button
                        key={v}
                        type="button"
                        role="radio"
                        aria-checked={c.valor === v}
                        onClick={() => poner(k, { valor: v })}
                        className={`rounded-lg px-2.5 py-1 text-[13px] font-semibold ${c.valor === v ? VALOR[v].clase + " ring-1 ring-current" : "text-smn-gris-500 hover:bg-smn-gris-50"}`}
                      >
                        {VALOR[v].texto}
                      </button>
                    ))}
                  </div>
                  <input
                    value={c.nota ?? ""}
                    onChange={(e) => poner(k, { nota: e.target.value || null })}
                    placeholder="Nota"
                    maxLength={300}
                    className="h-9 w-full rounded-lg border border-smn-gris-100 bg-superficie px-2.5 text-sm outline-none focus:border-smn-naranja sm:w-44"
                  />
                  <button type="button" onClick={() => setCriterios(criterios.filter((_, j) => j !== k))} aria-label={`Quitar ${c.criterio}`} className="rounded-full p-1 text-smn-gris-500 hover:bg-smn-gris-100">
                    <X className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex gap-2">
            <input
              value={nuevo}
              onChange={(e) => setNuevo(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  agregar(nuevo);
                }
              }}
              placeholder="Criterio nuevo, p. ej. Gusto del empaque"
              maxLength={200}
              className="h-10 min-w-0 flex-1 rounded-lg border border-smn-gris-100 bg-superficie px-3 text-[15px] outline-none focus:border-smn-naranja"
            />
            <Boton type="button" variante="secundario" onClick={() => agregar(nuevo)} disabled={!nuevo.trim()}>
              <Plus className="h-4 w-4" /> Agregar
            </Boton>
          </div>
          {sugeridos.length > 0 && (
            <div className="mt-2">
              <p className="mb-1 text-[13px] text-smn-gris-500">
                Políticas vigentes de Compras y criterios que ya se usaron{ref && ref.politicas.length === 0 ? " (Compras todavía no marca políticas vigentes)" : ""}:
              </p>
              <div className="flex max-h-28 flex-wrap gap-1.5 overflow-y-auto">
                {sugeridos.map((s) => (
                  <button key={s} type="button" onClick={() => agregar(s)} className="rounded-full border border-smn-gris-100 px-2.5 py-0.5 text-[13px] text-smn-gris-700 hover:border-smn-naranja hover:text-tinta">
                    + {s}
                  </button>
                ))}
              </div>
            </div>
          )}
        </fieldset>

        <div className="grid grid-cols-2 gap-2">
          {(["pasa", "no_pasa"] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={resultado === v}
              onClick={() => setResultado(v)}
              className={`rounded-xl border p-3 text-left text-[15px] font-semibold transition-colors ${resultado === v ? "border-tinta bg-tinta text-superficie" : "border-smn-gris-100 hover:border-smn-gris-300"}`}
            >
              {v === "pasa" ? "Pasa al comité" : "No pasa"}
            </button>
          ))}
        </div>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-smn-gris-700">Motivo *</span>
          <textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={3} maxLength={1000} required className={CAJA} placeholder="Por qué sí o por qué no; se muestra en la presentación" />
        </label>
        <div className="flex justify-end gap-2">
          <Boton type="button" variante="fantasma" onClick={cerrar}>Cancelar</Boton>
          <Boton type="submit" cargando={guardando} disabled={!resultado || !motivo.trim()}>Guardar pre-filtro</Boton>
        </div>
      </form>
    </Modal>
  );
}

/** Aceptar, Aceptar a prueba, Denegar o En espera, siempre con motivo. Además, qué indicador pesó y si el radar se
 * equivocó (memoria del comité, 17 nov 2026), y para la prueba: tiendas, precio de introducción, fecha y condición. */
export function FormDecision({ i, listo, grande = false }: { i: Item; listo: (r: Reunion) => void; grande?: boolean }) {
  const avisar = useAvisos();
  const [decision, setDecision] = useState<Decision | null>(i.decision);
  const [motivo, setMotivo] = useState(i.decision_motivo ?? "");
  const [pesos, setPesos] = useState<Record<string, Indicador["sentido"]>>({});
  const [error, setError] = useState(i.radar_error_factor ?? "");
  const [errorMotivo, setErrorMotivo] = useState(i.radar_error_motivo ?? "");
  const [sugeridas, setSugeridas] = useState<TiendaPrueba[] | null>(null);
  const [tiendas, setTiendas] = useState<string[]>(i.prueba_tiendas ?? []);
  const [precio, setPrecio] = useState(i.prueba_precio ?? "");
  const [revision, setRevision] = useState(i.prueba_revision ?? new Date(Date.now() + 56 * 86400000).toISOString().slice(0, 10));
  const [condicion, setCondicion] = useState(i.prueba_condicion ?? "");
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    setDecision(i.decision);
    setMotivo(i.decision_motivo ?? "");
    setPesos(Object.fromEntries((i.indicadores ?? []).map((x) => [x.factor, x.sentido])));
    setError(i.radar_error_factor ?? "");
    setErrorMotivo(i.radar_error_motivo ?? "");
    setTiendas(i.prueba_tiendas ?? []);
  }, [i.id, i.decision, i.decision_motivo, i.indicadores, i.radar_error_factor, i.radar_error_motivo, i.prueba_tiendas]);

  useEffect(() => {
    if (decision !== "a_prueba" || sugeridas) return;
    api<TiendaPrueba[]>(`${RUTA}/productos/${i.id}/tiendas-prueba`)
      .then((t) => {
        setSugeridas(t);
        setTiendas((x) => (x.length ? x : t.map((y) => y.almacen)));
      })
      .catch(() => setSugeridas([]));
  }, [decision, sugeridas, i.id]);

  const sentidoInicial: Indicador["sentido"] = decision === "denegado" ? "en_contra" : "a_favor";
  const alternar = (f: string) =>
    setPesos((p) => {
      const x = { ...p };
      if (!x[f]) x[f] = sentidoInicial;
      else if (x[f] === sentidoInicial) x[f] = sentidoInicial === "a_favor" ? "en_contra" : "a_favor";
      else delete x[f];
      return x;
    });

  const guardar = async () => {
    if (!decision) return;
    setGuardando(true);
    try {
      const cuerpo = {
        decision,
        motivo,
        indicadores: Object.entries(pesos).map(([factor, sentido]) => ({ factor, sentido })),
        radar_error_factor: error || null,
        radar_error_motivo: error ? errorMotivo || null : null,
        ...(decision === "a_prueba" ? { prueba_tiendas: tiendas, prueba_precio: precio || null, prueba_revision: revision || null, prueba_condicion: condicion || null } : {}),
      };
      const r = await api<Reunion>(`${RUTA}/productos/${i.id}/decision`, { metodo: "PUT", cuerpo });
      avisar(`${DECISION[decision].texto}: ${i.nombre}`);
      listo(r);
    } catch (err) {
      avisar(mensajeDe(err), "info");
    } finally {
      setGuardando(false);
    }
  };

  const faltaPrueba = decision === "a_prueba" && (!tiendas.length || !revision);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {(Object.keys(DECISION) as Decision[]).map((d) => (
          <button
            key={d}
            type="button"
            aria-pressed={decision === d}
            onClick={() => setDecision(d)}
            className={`rounded-xl border font-semibold transition-colors ${grande ? "p-3 text-lg" : "p-2.5 text-[15px]"} ${decision === d ? "border-tinta bg-tinta text-superficie" : "border-smn-gris-100 hover:border-smn-gris-300"}`}
          >
            {DECISION[d].boton}
          </button>
        ))}
      </div>
      <textarea
        value={motivo}
        onChange={(e) => setMotivo(e.target.value)}
        rows={2}
        maxLength={1000}
        aria-label="Motivo de la decisión"
        placeholder="Motivo de la decisión *"
        className={CAJA}
      />
      {decision && decision !== "en_espera" && (
        <div>
          <p className="mb-1.5 text-sm font-medium text-smn-gris-700">¿Qué pesó? <span className="font-normal text-smn-gris-500">Toca una vez a favor o en contra, otra para cambiarlo, otra para quitarlo.</span></p>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(INDICADORES).map(([f, nombre]) => (
              <button
                key={f}
                type="button"
                onClick={() => alternar(f)}
                className={`rounded-full border px-3 py-1 text-[13px] font-semibold transition-colors ${
                  pesos[f] === "a_favor" ? "border-green-600/40 bg-green-600/10 text-green-700 dark:text-green-400"
                  : pesos[f] === "en_contra" ? "border-red-600/40 bg-red-600/10 text-red-700 dark:text-red-400"
                  : "border-smn-gris-100 text-smn-gris-700 hover:border-smn-gris-300"}`}
              >
                {nombre}{pesos[f] && ` · ${pesos[f] === "a_favor" ? "a favor" : "en contra"}`}
              </button>
            ))}
          </div>
        </div>
      )}
      {decision && decision !== "en_espera" && (
        <div className="grid gap-2 sm:grid-cols-[minmax(0,14rem)_1fr]">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-smn-gris-700">El radar se equivocó en</span>
            <select value={error} onChange={(e) => setError(e.target.value)} className={CAJA}>
              <option value="">No se equivocó</option>
              {Object.entries(FACTORES_RADAR).map(([f, n]) => <option key={f} value={f}>{n}</option>)}
            </select>
          </label>
          {error && (
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-smn-gris-700">¿En qué?</span>
              <input value={errorMotivo} onChange={(e) => setErrorMotivo(e.target.value)} maxLength={500} className={CAJA} placeholder="Ej. el precio de afuera era de otra presentación" />
            </label>
          )}
        </div>
      )}
      {decision === "a_prueba" && (
        <div className="space-y-2 rounded-xl border border-smn-gris-100 p-3">
          <p className="text-sm font-semibold">Prueba en pocas tiendas</p>
          {sugeridas === null ? (
            <p className="text-[13px] text-smn-gris-500">Buscando tiendas sugeridas…</p>
          ) : sugeridas.length === 0 ? (
            <p className="text-[13px] text-smn-gris-500">No hay grupos de tiendas calculados. Calcúlalos en Datos → Mapa de tiendas para sugerir tiendas.</p>
          ) : (
            <ul className="grid gap-1 sm:grid-cols-2">
              {sugeridas.map((t) => (
                <li key={t.almacen}>
                  <label className="flex items-start gap-2 text-[13px]">
                    <input
                      type="checkbox"
                      checked={tiendas.includes(t.almacen)}
                      onChange={(e) => setTiendas((x) => (e.target.checked ? [...x, t.almacen] : x.filter((y) => y !== t.almacen)))}
                      className="mt-0.5"
                    />
                    <span>
                      <b>{t.nombre}</b> · {t.region ?? "sin región"}
                      <span className="block text-smn-gris-500">{t.grupo_nombre}{t.vende_parecidos ? " · ya vende sus parecidos" : ""}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="block">
              <span className="mb-1 block text-[13px] text-smn-gris-700">Precio de introducción</span>
              <input value={precio} onChange={(e) => setPrecio(e.target.value.replace(/[^\d.]/g, ""))} inputMode="decimal" className={CAJA} placeholder="$" />
            </label>
            <label className="block">
              <span className="mb-1 block text-[13px] text-smn-gris-700">Se revisa el *</span>
              <input type="date" value={revision} onChange={(e) => setRevision(e.target.value)} className={CAJA} />
            </label>
            <label className="block">
              <span className="mb-1 block text-[13px] text-smn-gris-700">Condición con el proveedor</span>
              <input value={condicion} onChange={(e) => setCondicion(e.target.value)} maxLength={500} className={CAJA} placeholder="Ej. devuelve lo que no se venda" />
            </label>
          </div>
        </div>
      )}
      <div className="flex items-center justify-between gap-2">
        {i.decision ? (
          <Insignia className={DECISION[i.decision].clase}>Registrado: {DECISION[i.decision].texto}</Insignia>
        ) : (
          <span className="text-[13px] text-smn-gris-500">Sin decisión todavía</span>
        )}
        <Boton onClick={guardar} cargando={guardando} disabled={!decision || !motivo.trim() || faltaPrueba}>
          Registrar
        </Boton>
      </div>
    </div>
  );
}

/** Subir una propuesta, idea u oportunidad que ya existe. */
export function AgregarExistente({ reunion, cerrar, listo }: { reunion: number; cerrar: () => void; listo: (r: Reunion) => void }) {
  const avisar = useAvisos();
  const [q, setQ] = useState("");
  const [lista, setLista] = useState<Candidato[] | null>(null);
  const [subiendo, setSubiendo] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      api<Candidato[]>(`${RUTA}/candidatos?q=${encodeURIComponent(q.trim())}`).then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
    }, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [q, avisar]);

  const subir = async (c: Candidato) => {
    setSubiendo(`${c.tipo}-${c.id}`);
    try {
      const r = await api<Reunion>(`${RUTA}/reuniones/${reunion}/productos`, { cuerpo: c.tipo === "idea" ? { idea_id: c.id } : { propuesta_id: c.id } });
      avisar(`Subiste «${c.nombre}» al ciclo`);
      listo(r);
    } catch (err) {
      avisar(mensajeDe(err), "info");
    } finally {
      setSubiendo(null);
    }
  };

  return (
    <Modal titulo="Agregar un producto que ya existe" cerrar={cerrar} ancho="max-w-xl">
      <label className="relative block">
        <span className="sr-only">Buscar</span>
        <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Producto, folio o proveedor" className="h-11 w-full rounded-lg border border-smn-gris-100 bg-superficie pr-3 pl-9 text-[15px] outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15" />
      </label>
      <p className="mt-1.5 text-[13px] text-smn-gris-700">Propuestas de proveedores, capturas de Compras, ideas y oportunidades que mandaste a evaluar.</p>
      <ul className="mt-3 max-h-80 overflow-y-auto rounded-xl border border-smn-gris-100">
        {lista === null ? (
          <li className="p-3 text-sm text-smn-gris-700">Buscando…</li>
        ) : lista.length === 0 ? (
          <li className="p-3 text-sm text-smn-gris-700">No hay productos con ese nombre.</li>
        ) : (
          lista.map((c) => (
            <li key={`${c.tipo}-${c.id}`} className="flex items-center gap-3 border-b border-smn-gris-100 px-3 py-2.5 last:border-b-0">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] font-medium">{c.nombre}</span>
                <span className="block truncate text-[13px] text-smn-gris-700">{c.detalle}</span>
              </span>
              {c.color && <InsigniaColor color={c.color} />}
              {c.en_otra ? (
                <span className="text-[13px] text-smn-gris-500">Ya está</span>
              ) : (
                <Boton variante="secundario" onClick={() => subir(c)} cargando={subiendo === `${c.tipo}-${c.id}`}>Subir</Boton>
              )}
            </li>
          ))
        )}
      </ul>
    </Modal>
  );
}

/** Asistente: un colaborador con cuenta (con su puesto) o un nombre escrito. */
export function AgregarAsistente({ reunion, cerrar, listo }: { reunion: Reunion; cerrar: () => void; listo: (r: Reunion) => void }) {
  const avisar = useAvisos();
  const [q, setQ] = useState("");
  const [lista, setLista] = useState<UsuarioBreve[]>([]);
  const [manual, setManual] = useState({ nombre: "", puesto: "" });
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      api<UsuarioBreve[]>(`${RUTA}/usuarios?q=${encodeURIComponent(q.trim())}`).then(setLista).catch(() => setLista([]));
    }, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [q]);

  const agregar = async (cuerpo: object) => {
    setGuardando(true);
    try {
      listo(await api<Reunion>(`${RUTA}/reuniones/${reunion.id}/asistentes`, { cuerpo }));
      setManual({ nombre: "", puesto: "" });
    } catch (err) {
      avisar(mensajeDe(err), "info");
    } finally {
      setGuardando(false);
    }
  };
  const ya = new Set(reunion.asistentes.map((a) => a.usuario_id));

  return (
    <Modal titulo="¿Quién asiste?" cerrar={cerrar} ancho="max-w-lg">
      <p className="mb-3 text-sm text-smn-gris-700">Sirve para saber quién tomó cada decisión, por puesto, y darle seguimiento a lo que pidió.</p>
      {reunion.asistentes.length > 0 && (
        <ul className="mb-4 flex flex-wrap gap-1.5">
          {reunion.asistentes.map((a) => (
            <li key={a.id} className="rounded-full bg-smn-gris-100 px-2.5 py-1 text-[13px]">
              {a.nombre}{a.puesto && <span className="text-smn-gris-500"> · {a.puesto}</span>}
            </li>
          ))}
        </ul>
      )}
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar colaborador por nombre o puesto" className="h-11 w-full rounded-lg border border-smn-gris-100 bg-superficie px-3 text-[15px] outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15" />
      <ul className="mt-2 max-h-56 overflow-y-auto rounded-xl border border-smn-gris-100">
        {lista.filter((u) => !ya.has(u.id)).map((u) => (
          <li key={u.id} className="flex items-center gap-3 border-b border-smn-gris-100 px-3 py-2 last:border-b-0">
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[15px]">{u.nombre}</span>
              <span className="block truncate text-[13px] text-smn-gris-500">{u.puesto ?? "Sin puesto registrado"}{u.area && ` · ${u.area}`}</span>
            </span>
            <Boton variante="secundario" disabled={guardando} onClick={() => agregar({ usuario_id: u.id })}>Agregar</Boton>
          </li>
        ))}
        {lista.length === 0 && <li className="p-3 text-sm text-smn-gris-700">Nadie con ese nombre. Escríbelo abajo.</li>}
      </ul>
      <form
        className="mt-4 grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          agregar({ nombre: manual.nombre, puesto: manual.puesto || null });
        }}
      >
        <Campo etiqueta="Nombre (si no tiene cuenta)" value={manual.nombre} onChange={(e) => setManual({ ...manual, nombre: e.target.value })} maxLength={200} />
        <Campo etiqueta="Puesto" value={manual.puesto} onChange={(e) => setManual({ ...manual, puesto: e.target.value })} maxLength={120} />
        <Boton type="submit" variante="secundario" disabled={manual.nombre.trim().length < 2 || guardando}>Agregar</Boton>
      </form>
      <div className="mt-5 flex justify-end">
        <Boton onClick={cerrar}>Listo</Boton>
      </div>
    </Modal>
  );
}

/** Lo que pidió un asistente en la reunión, sobre un producto o en general. */
export function NuevaPeticion({ reunion, item, listo, compacta = false }: { reunion: Reunion; item?: Item; listo: (r: Reunion) => void; compacta?: boolean }) {
  const avisar = useAvisos();
  const [texto, setTexto] = useState("");
  const [quien, setQuien] = useState("");
  const [guardando, setGuardando] = useState(false);
  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    setGuardando(true);
    try {
      const r = await api<Reunion>(`${RUTA}/reuniones/${reunion.id}/peticiones`, {
        cuerpo: { texto, item_id: item?.id ?? null, asistente_id: quien ? Number(quien) : null },
      });
      setTexto("");
      avisar("Petición anotada");
      listo(r);
    } catch (err) {
      avisar(mensajeDe(err), "info");
    } finally {
      setGuardando(false);
    }
  };
  return (
    <form onSubmit={guardar} className={`grid gap-2 ${compacta ? "" : "sm:grid-cols-[12rem_1fr_auto]"}`}>
      <select value={quien} onChange={(e) => setQuien(e.target.value)} aria-label="Quién lo pidió" className="h-10 rounded-lg border border-smn-gris-100 bg-superficie px-2 text-[15px] outline-none focus:border-smn-naranja">
        <option value="">¿Quién lo pidió?</option>
        {reunion.asistentes.map((a) => (
          <option key={a.id} value={a.id}>{a.nombre}{a.puesto ? ` (${a.puesto})` : ""}</option>
        ))}
      </select>
      <input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder={item ? "Qué pidió sobre este producto (una muestra, un dato…)" : "Qué se pidió"} maxLength={1000} aria-label="Petición" className="h-10 min-w-0 rounded-lg border border-smn-gris-100 bg-superficie px-3 text-[15px] outline-none focus:border-smn-naranja" />
      <Boton type="submit" variante="secundario" cargando={guardando} disabled={texto.trim().length < 2}>Anotar</Boton>
    </form>
  );
}

export function ListaPeticiones({ peticiones, atender }: { peticiones: Peticion[]; atender?: (p: Peticion) => void }) {
  if (peticiones.length === 0) return <p className="text-sm text-smn-gris-500">Sin peticiones.</p>;
  return (
    <ul className="space-y-1.5">
      {peticiones.map((p) => (
        <li key={p.id} className="flex flex-wrap items-center gap-2 text-sm">
          <Insignia className={p.estado === "abierta" ? "bg-smn-naranja/15 text-tinta" : "bg-green-600/10 text-green-700 dark:text-green-400"}>
            {p.estado === "abierta" ? "Abierta" : "Atendida"}
          </Insignia>
          <span className="min-w-0 flex-1">
            {p.texto}
            <span className="text-smn-gris-500">
              {p.asistente && ` · ${p.asistente}${p.puesto ? ` (${p.puesto})` : ""}`}
              {p.producto && ` · ${p.producto}`}
              {p.respuesta && ` · ${p.respuesta}`}
            </span>
          </span>
          {atender && p.estado === "abierta" && (
            <button type="button" onClick={() => atender(p)} className="text-[13px] font-semibold text-smn-gris-700 underline-offset-2 hover:underline">
              Marcar atendida
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
