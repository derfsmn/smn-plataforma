"use client";
// TD003 · Base de conocimiento fiscal: los criterios, catálogos y layout que usa el proceso de la DIOT, con su documento
// de soporte, vigencia y aprobación de Fiscal. Pedido de Diego, 2026-10-30.

import Link from "next/link";
import { AnimatePresence } from "motion/react";
import { AlertTriangle, ArrowLeft, Download, FileUp, FlaskConical, History, Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo, Encabezado, Entrada, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import {
  ACCIONES_HISTORIAL, CATALOGOS, ESTADOS, PERMISO_APROBAR, RUTA_BASE, fecha, inicioDeMes, valorParametro,
  type BaseFiscal, type CambioHistorial, type Catalogo, type Criterio, type ResultadoPrueba,
} from "@/lib/conocimiento-fiscal";
import { PERMISO_OPERAR, PERMISO_VER, RUTA, subir, type PeriodoResumen } from "@/lib/diot";
import { descargar } from "@/lib/precios";

const TARJETA = "rounded-2xl border border-smn-gris-100 bg-superficie p-5";
const AREA = "w-full rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 text-sm outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20";
const PESTANAS = [
  { valor: "criterios", texto: "Criterios" },
  { valor: "catalogos", texto: "Catálogos y layout" },
  { valor: "documentos", texto: "Documentos de soporte" },
] as const;
type Pestana = (typeof PESTANAS)[number]["valor"];

export default function BaseConocimientoFiscal() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [b, setB] = useState<BaseFiscal | null>(null);
  const [pestana, setPestana] = useState<Pestana>("criterios");
  const cargar = useCallback(() => api<BaseFiscal>(RUTA_BASE).then(setB).catch((e) => avisar(mensajeDe(e), "info")), [avisar]);
  useEffect(() => {
    cargar();
  }, [cargar]);

  if (!puede(PERMISO_VER)) return <p className="text-smn-gris-500">No tienes acceso a la Base de conocimiento fiscal.</p>;
  if (!b) return <Esqueleto className="h-64" />;
  return (
    <>
      <Link href="/modulos/contraloria" className="mb-6 inline-flex items-center gap-1 text-sm font-semibold text-smn-gris-500 hover:text-tinta">
        <ArrowLeft className="h-4 w-4" /> Contraloría y Fiscal
      </Link>
      <Encabezado
        titulo="Base de conocimiento fiscal"
        descripcion="Los criterios, catálogos y layout que usa el proceso de la DIOT, cada uno con su documento de soporte, desde cuándo vale y quién lo aprobó. Si cambia una regla, se cambia aquí, no en el sistema."
      />
      <Entrada className={`${TARJETA} grid gap-4 sm:grid-cols-4`}>
        <Dato titulo="Criterios aprobados" valor={b.resumen.aprobados} />
        <Dato titulo="Pendientes de aprobar" valor={b.resumen.pendientes} alerta={b.resumen.pendientes > 0} />
        <Dato titulo="En borrador" valor={b.resumen.borradores} />
        <Dato titulo="Contradicciones abiertas" valor={b.resumen.contradicciones} alerta={b.resumen.contradicciones > 0} />
        <div className="text-sm text-smn-gris-500 sm:col-span-4">
          <p className="font-semibold text-tinta">Cómo funciona</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            <li>Cada cambio crea una versión nueva desde la fecha que elijas. Las anteriores se guardan para volver a procesar meses pasados con lo que valía entonces.</li>
            <li>Un cambio queda pendiente hasta que alguien con permiso de aprobar lo revisa. Antes de aprobarlo puedes usar «Probar con un periodo» para ver cómo cambiaría un TXT ya procesado.</li>
            <li>Un criterio del sistema pendiente se sigue aplicando, pero el mes en que cambia el resultado sale una incidencia que hay que revisar antes de descargar el TXT. Un criterio propio pendiente no se aplica.</li>
            <li>Nada de esto usa IA: los cálculos y la clasificación son reglas fijas que se pueden revisar.</li>
          </ul>
        </div>
      </Entrada>

      <div className="mt-6 flex flex-wrap gap-2">
        {PESTANAS.map((x) => (
          <button
            key={x.valor}
            onClick={() => setPestana(x.valor)}
            className={`rounded-full px-4 py-2 text-sm font-semibold transition ${pestana === x.valor ? "bg-tinta text-superficie" : "bg-smn-gris-100 text-smn-gris-700 hover:bg-smn-gris-300/50"}`}
          >
            {x.texto}
          </button>
        ))}
      </div>
      <div className="mt-4">
        {pestana === "criterios" && <Criterios b={b} poner={setB} />}
        {pestana === "catalogos" && <Catalogos b={b} poner={setB} />}
        {pestana === "documentos" && <Documentos b={b} poner={setB} />}
      </div>
    </>
  );
}

function Dato({ titulo, valor, alerta }: { titulo: string; valor: number; alerta?: boolean }) {
  return (
    <div>
      <p className="text-[13px] font-medium text-smn-gris-500">{titulo}</p>
      <p className={`text-2xl font-semibold tabular-nums ${alerta ? "text-amber-700" : ""}`}>{valor}</p>
    </div>
  );
}

// ---------------------------------------------------------------- criterios

type Ventana =
  | { tipo: "editar"; c: Criterio }
  | { tipo: "nuevo" }
  | { tipo: "estado"; c: Criterio; accion: "aprobar" | "regresar" | "enviar" | "retirar" }
  | { tipo: "probar"; c: Criterio | null }
  | { tipo: "historial"; c: Criterio };

function Criterios({ b, poner }: { b: BaseFiscal; poner: (x: BaseFiscal) => void }) {
  const { puede } = useSesion();
  const edita = puede(PERMISO_OPERAR);
  const aprueba = puede(PERMISO_APROBAR);
  const [filtro, setFiltro] = useState("");
  const [ventana, setVentana] = useState<Ventana | null>(null);
  const vistos = b.criterios.filter((c) => !filtro || (filtro === "pendientes" ? c.ultima.estado === "pendiente" || c.ultima.estado === "borrador" : c.categoria === filtro));
  const grupos = useMemo(() => {
    const g: Record<string, Criterio[]> = {};
    vistos.forEach((c) => (g[c.categoria] ??= []).push(c));
    return g;
  }, [vistos]);

  return (
    <>
      <div className="flex flex-wrap items-end gap-3">
        <Selector
          etiqueta="Ver"
          valor={filtro}
          cambiar={setFiltro}
          className="min-w-64"
          opciones={[
            { valor: "", texto: `Todos (${b.criterios.length})` },
            { valor: "pendientes", texto: `Por aprobar (${b.resumen.pendientes + b.resumen.borradores})` },
            ...Object.entries(b.opciones.categorias).map(([valor, texto]) => ({ valor, texto })),
          ]}
        />
        <Boton variante="secundario" onClick={() => setVentana({ tipo: "probar", c: null })}>
          <FlaskConical className="h-4 w-4" /> Probar con un periodo
        </Boton>
        {edita && (
          <Boton onClick={() => setVentana({ tipo: "nuevo" })}>
            <Plus className="h-4 w-4" /> Nuevo criterio propio
          </Boton>
        )}
      </div>
      {Object.entries(grupos).map(([cat, lista]) => (
        <section key={cat} className="mt-6">
          <h2 className="mb-2 text-sm font-medium text-smn-gris-500">{b.opciones.categorias[cat] ?? cat}</h2>
          <div className="grid gap-3">
            {lista.map((c) => (
              <TarjetaCriterio key={c.clave} c={c} edita={edita} aprueba={aprueba} abrir={setVentana} />
            ))}
          </div>
        </section>
      ))}
      {vistos.length === 0 && <p className="mt-4 text-sm text-smn-gris-500">No hay criterios con ese filtro.</p>}
      <AnimatePresence>
        {ventana?.tipo === "editar" && <EditarCriterio b={b} c={ventana.c} cerrar={() => setVentana(null)} poner={poner} />}
        {ventana?.tipo === "nuevo" && <EditarCriterio b={b} c={null} cerrar={() => setVentana(null)} poner={poner} />}
        {ventana?.tipo === "estado" && <CambiarEstado c={ventana.c} accion={ventana.accion} cerrar={() => setVentana(null)} poner={poner} />}
        {ventana?.tipo === "probar" && <Probar c={ventana.c} cerrar={() => setVentana(null)} />}
        {ventana?.tipo === "historial" && <Historial c={ventana.c} cerrar={() => setVentana(null)} />}
      </AnimatePresence>
    </>
  );
}

function TarjetaCriterio({ c, edita, aprueba, abrir }: { c: Criterio; edita: boolean; aprueba: boolean; abrir: (v: Ventana) => void }) {
  const u = c.ultima;
  const otra = c.vigente.id !== u.id;
  const abierta = u.estado === "pendiente" || u.estado === "borrador";
  return (
    <div className={`${TARJETA} ${u.estado === "retirado" ? "opacity-60" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-semibold">{c.titulo}</p>
        <span className="text-[13px] font-medium text-smn-gris-500">{c.clave}</span>
        <Insignia className={ESTADOS[u.estado].clase}>{ESTADOS[u.estado].texto}</Insignia>
        <span className="text-[13px] text-smn-gris-500">
          versión {u.version} · vale desde {fecha(u.vigente_desde)}
          {otra && <> · hoy aplica la versión {c.vigente.version} ({ESTADOS[c.vigente.estado].texto.toLowerCase()})</>}
        </span>
      </div>
      <p className="mt-2 text-sm">{c.descripcion}</p>

      {c.campos.length > 0 && u.parametros && (
        <dl className="mt-3 grid gap-1 text-sm sm:grid-cols-[max-content_1fr] sm:gap-x-4">
          {c.campos.map((k) => (
            <div key={k.nombre} className="contents">
              <dt className="font-semibold text-smn-gris-700">{k.etiqueta}</dt>
              <dd>{valorParametro(k, u.parametros?.[k.nombre])}</dd>
            </div>
          ))}
        </dl>
      )}
      {c.tipo === "propio" && u.condicion && u.accion && <p className="mt-2 text-sm"><CondicionTexto c={c} /></p>}

      {c.contradiccion && u.estado !== "aprobado" && (
        <div className="mt-3 flex gap-2 rounded-2xl bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-semibold">Contradicción por resolver</p>
            <p>{c.contradiccion}</p>
          </div>
        </div>
      )}
      {c.evidencia && <p className="mt-2 text-sm text-smn-gris-500">{c.evidencia}</p>}
      {abierta && <p className="mt-2 text-[13px] text-smn-gris-500">{c.si_pendiente}</p>}

      <p className="mt-3 text-[13px] text-smn-gris-500">
        Soporte: {c.documento ?? "sin documento"}
        {c.referencia && <> · {c.referencia}</>}
        {u.aprobado_en && (
          <>
            {" "}
            · aprobado {u.aprobado_por ? `por ${u.aprobado_por}` : "en la carga inicial"} el {fechaLocal(u.aprobado_en)}
            {u.nota_aprobacion && <> («{u.nota_aprobacion}»)</>}
          </>
        )}
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        {edita && u.estado !== "retirado" && (c.campos.length > 0 || c.tipo === "propio") && (
          <Boton variante="secundario" className="py-1.5" onClick={() => abrir({ tipo: "editar", c })}>
            Cambiar
          </Boton>
        )}
        {aprueba && abierta && (
          <Boton className="py-1.5" onClick={() => abrir({ tipo: "estado", c, accion: "aprobar" })}>
            Aprobar
          </Boton>
        )}
        {aprueba && u.estado === "pendiente" && (
          <Boton variante="secundario" className="py-1.5" onClick={() => abrir({ tipo: "estado", c, accion: "regresar" })}>
            Regresar
          </Boton>
        )}
        {edita && u.estado === "borrador" && (
          <Boton variante="secundario" className="py-1.5" onClick={() => abrir({ tipo: "estado", c, accion: "enviar" })}>
            Mandar a aprobar
          </Boton>
        )}
        <Boton variante="fantasma" className="py-1.5" onClick={() => abrir({ tipo: "probar", c })}>
          <FlaskConical className="h-4 w-4" /> Probar
        </Boton>
        <Boton variante="fantasma" className="py-1.5" onClick={() => abrir({ tipo: "historial", c })}>
          <History className="h-4 w-4" /> Historial ({c.versiones} {c.versiones === 1 ? "versión" : "versiones"})
        </Boton>
        {edita && c.tipo === "propio" && u.estado !== "retirado" && (
          <Boton variante="fantasma" className="py-1.5" onClick={() => abrir({ tipo: "estado", c, accion: "retirar" })}>
            Retirar
          </Boton>
        )}
      </div>
    </div>
  );
}

function CondicionTexto({ c }: { c: Criterio }) {
  const k = c.ultima.condicion!;
  const a = c.ultima.accion!;
  const lugar = { tesoreria: "En pagos de tesorería", comprobantes: "En gastos comprobados", cualquiera: "En cualquier documento" }[k.fuente] ?? k.fuente;
  const campo = { concepto: "el concepto", referencia: "la referencia", nombre: "el nombre del proveedor", rfc: "el RFC" }[k.campo] ?? k.campo;
  const op = { contiene: "contiene", empieza: "empieza con", igual: "es igual a" }[k.operador] ?? k.operador;
  const que = { excluir: "no se declara", tasa0: "va a tasa 0 %", no_objeto: "va como no objeto", exento: "va como exento", tipo_operacion: `va con tipo de operación ${a.tipo_operacion}` }[a.accion] ?? a.accion;
  return (
    <>
      <span className="font-semibold">Regla:</span> {lugar}, si {campo} {op} «{k.valor}», {que}. Prioridad {c.prioridad} (menor se revisa primero).
    </>
  );
}

function EditarCriterio({ b, c, cerrar, poner }: { b: BaseFiscal; c: Criterio | null; cerrar: () => void; poner: (x: BaseFiscal) => void }) {
  const avisar = useAvisos();
  const u = c?.ultima;
  const [params, setParams] = useState<Record<string, string>>(() =>
    Object.fromEntries((c?.campos ?? []).map((k) => {
      const v = u?.parametros?.[k.nombre];
      return [k.nombre, Array.isArray(v) ? v.join("\n") : String(v ?? "")];
    })),
  );
  const [f, setF] = useState({
    titulo: c?.titulo ?? "",
    descripcion: c?.descripcion ?? "",
    fuente: u?.condicion?.fuente ?? "comprobantes",
    campo: u?.condicion?.campo ?? "concepto",
    operador: u?.condicion?.operador ?? "contiene",
    valor: u?.condicion?.valor ?? "",
    accion: u?.accion?.accion ?? "no_objeto",
    tipo_operacion: u?.accion?.tipo_operacion ?? "85",
    prioridad: String(c?.prioridad ?? 100),
    referencia: c?.referencia ?? "",
    documento_id: c?.documento_id ? String(c.documento_id) : "",
    desde: inicioDeMes(),
    motivo: "",
    borrador: false,
  });
  const [ocupado, setOcupado] = useState(false);
  const propio = !c || c.tipo === "propio";

  const guardar = async () => {
    setOcupado(true);
    try {
      const comunes = {
        vigente_desde: f.desde,
        motivo: f.motivo,
        borrador: f.borrador,
        referencia: f.referencia || null,
        documento_id: f.documento_id ? Number(f.documento_id) : null,
      };
      const propios = propio
        ? {
            titulo: f.titulo,
            descripcion: f.descripcion,
            prioridad: Number(f.prioridad) || 100,
            condicion: { fuente: f.fuente, campo: f.campo, operador: f.operador, valor: f.valor },
            accion: f.accion === "tipo_operacion" ? { accion: f.accion, tipo_operacion: f.tipo_operacion } : { accion: f.accion },
          }
        : {};
      const parametros = c && !propio
        ? { parametros: Object.fromEntries(c.campos.map((k) => [k.nombre, k.tipo === "lista" ? params[k.nombre].split("\n").map((x) => x.trim()).filter(Boolean) : params[k.nombre]])) }
        : {};
      const r = c
        ? await api<BaseFiscal>(`${RUTA_BASE}/criterios/${c.clave}/versiones`, { cuerpo: { ...comunes, ...propios, ...parametros } })
        : await api<BaseFiscal>(`${RUTA_BASE}/criterios`, { cuerpo: { ...comunes, ...propios } });
      poner(r);
      avisar(f.borrador ? "Quedó en borrador." : "Quedó pendiente de aprobar.", "exito");
      cerrar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(false);
    }
  };

  return (
    <Modal titulo={c ? `Cambiar «${c.titulo}»` : "Nuevo criterio propio"} cerrar={cerrar} ancho="max-w-2xl">
      <div className="grid gap-3">
        {c && !propio &&
          c.campos.map((k) =>
            k.tipo === "opcion" && k.opciones ? (
              <Selector key={k.nombre} etiqueta={k.etiqueta} valor={params[k.nombre]} cambiar={(v) => setParams({ ...params, [k.nombre]: v })} opciones={Object.entries(k.opciones).map(([valor, texto]) => ({ valor, texto }))} />
            ) : k.tipo === "lista" ? (
              <label key={k.nombre} className="block">
                <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">{k.etiqueta} (uno por renglón)</span>
                <textarea rows={3} value={params[k.nombre]} onChange={(e) => setParams({ ...params, [k.nombre]: e.target.value })} className={AREA} />
              </label>
            ) : (
              <Campo key={k.nombre} etiqueta={k.etiqueta} value={params[k.nombre]} onChange={(e) => setParams({ ...params, [k.nombre]: e.target.value })} />
            ),
          )}
        {propio && (
          <>
            <Campo etiqueta="Título" value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} placeholder="Ej. Predial como no objeto" />
            <label className="block">
              <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">Explicación</span>
              <textarea rows={2} value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} className={AREA} />
            </label>
            <div className="grid gap-3 sm:grid-cols-3">
              <Selector etiqueta="Dónde" valor={f.fuente} cambiar={(v) => setF({ ...f, fuente: v })} opciones={Object.entries(b.opciones.fuentes).map(([valor, texto]) => ({ valor, texto }))} />
              <Selector etiqueta="Si" valor={f.campo} cambiar={(v) => setF({ ...f, campo: v })} opciones={Object.entries(b.opciones.campos_condicion).map(([valor, texto]) => ({ valor, texto }))} />
              <Selector etiqueta="Comparación" valor={f.operador} cambiar={(v) => setF({ ...f, operador: v })} opciones={Object.entries(b.opciones.operadores).map(([valor, texto]) => ({ valor, texto }))} />
            </div>
            <Campo etiqueta="Valor" value={f.valor} onChange={(e) => setF({ ...f, valor: e.target.value })} placeholder="Ej. PREDIAL" />
            <div className="grid gap-3 sm:grid-cols-3">
              <Selector etiqueta="Entonces" valor={f.accion} cambiar={(v) => setF({ ...f, accion: v })} opciones={Object.entries(b.opciones.acciones).map(([valor, texto]) => ({ valor, texto }))} />
              {f.accion === "tipo_operacion" && <Campo etiqueta="Tipo de operación" value={f.tipo_operacion} onChange={(e) => setF({ ...f, tipo_operacion: e.target.value })} />}
              <Campo etiqueta="Prioridad" type="number" value={f.prioridad} onChange={(e) => setF({ ...f, prioridad: e.target.value })} />
            </div>
          </>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Selector
            etiqueta="Documento de soporte"
            valor={f.documento_id}
            cambiar={(v) => setF({ ...f, documento_id: v })}
            opciones={[{ valor: "", texto: "Sin documento" }, ...b.documentos.filter((d) => d.activo).map((d) => ({ valor: String(d.id), texto: d.titulo }))]}
          />
          <Campo etiqueta="Párrafo o sección" value={f.referencia} onChange={(e) => setF({ ...f, referencia: e.target.value })} />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo etiqueta="Vale desde" type="date" value={f.desde} onChange={(e) => setF({ ...f, desde: e.target.value })} />
          <label className="mt-7 flex items-center gap-2 text-sm font-semibold">
            <input type="checkbox" checked={f.borrador} onChange={(e) => setF({ ...f, borrador: e.target.checked })} /> Guardar como borrador
          </label>
        </div>
        <Campo etiqueta="Motivo del cambio" value={f.motivo} onChange={(e) => setF({ ...f, motivo: e.target.value })} placeholder="Ej. Fiscal confirmó en la junta del 30 de octubre" />
        <p className="text-[13px] text-smn-gris-500">Se guarda como versión nueva. Los meses anteriores a «Vale desde» siguen con la versión que tenían.</p>
        <div className="flex justify-end gap-2">
          <Boton variante="secundario" onClick={cerrar}>
            Cancelar
          </Boton>
          <Boton onClick={guardar} cargando={ocupado} disabled={f.motivo.trim().length < 3}>
            Guardar
          </Boton>
        </div>
      </div>
    </Modal>
  );
}

function CambiarEstado({ c, accion, cerrar, poner }: { c: Criterio; accion: "aprobar" | "regresar" | "enviar" | "retirar"; cerrar: () => void; poner: (x: BaseFiscal) => void }) {
  const avisar = useAvisos();
  const [nota, setNota] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const textos = {
    aprobar: { titulo: "Aprobar", ayuda: "Desde su fecha, el proceso lo aplica sin generar incidencia.", obligatoria: false },
    regresar: { titulo: "Regresar a borrador", ayuda: "Escribe qué hay que corregir.", obligatoria: true },
    enviar: { titulo: "Mandar a aprobar", ayuda: "Queda pendiente hasta que alguien con permiso lo apruebe.", obligatoria: false },
    retirar: { titulo: "Retirar", ayuda: "Deja de aplicarse. Escribe por qué.", obligatoria: true },
  }[accion];
  const enviar = async () => {
    setOcupado(true);
    try {
      poner(await api<BaseFiscal>(`${RUTA_BASE}/criterios/version/${c.ultima.id}/estado`, { cuerpo: { accion, nota: nota || null } }));
      avisar("Listo.", "exito");
      cerrar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(false);
    }
  };
  return (
    <Modal titulo={`${textos.titulo}: ${c.titulo} (versión ${c.ultima.version})`} cerrar={cerrar}>
      <p className="text-sm text-smn-gris-500">{textos.ayuda}</p>
      {accion === "aprobar" && c.contradiccion && (
        <p className="mt-2 rounded-2xl bg-amber-50 p-3 text-sm text-amber-900">Al aprobarlo, la contradicción queda resuelta con lo que dice este criterio: {c.contradiccion}</p>
      )}
      <div className="mt-3">
        <Campo etiqueta={textos.obligatoria ? "Nota (obligatoria)" : "Nota (opcional)"} value={nota} onChange={(e) => setNota(e.target.value)} />
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <Boton variante="secundario" onClick={cerrar}>
          Cancelar
        </Boton>
        <Boton onClick={enviar} cargando={ocupado} disabled={textos.obligatoria && !nota.trim()}>
          {textos.titulo}
        </Boton>
      </div>
    </Modal>
  );
}

function Probar({ c, cerrar }: { c: Criterio | null; cerrar: () => void }) {
  const avisar = useAvisos();
  const [periodos, setPeriodos] = useState<PeriodoResumen[]>([]);
  const [pid, setPid] = useState("");
  const [r, setR] = useState<ResultadoPrueba | null>(null);
  const [ocupado, setOcupado] = useState(false);
  useEffect(() => {
    api<PeriodoResumen[]>(`${RUTA}/periodos`)
      .then((l) => {
        setPeriodos(l);
        setPid((x) => x || String(l.find((p) => p.procesado_en)?.id ?? l[0]?.id ?? ""));
      })
      .catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  const correr = async () => {
    setOcupado(true);
    setR(null);
    try {
      setR(await api<ResultadoPrueba>(`${RUTA_BASE}/probar`, { cuerpo: { periodo_id: Number(pid), criterio_id: c?.ultima.id ?? null } }));
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(false);
    }
  };
  return (
    <Modal titulo={c ? `Probar «${c.titulo}» (versión ${c.ultima.version})` : "Probar con un periodo"} cerrar={cerrar} ancho="max-w-3xl">
      <p className="text-sm text-smn-gris-500">
        Corre el proceso del periodo con lo vigente en la base{c && c.ultima.estado !== "aprobado" ? ", tomando este criterio como si ya estuviera aprobado," : ""} sin guardar nada, y lo compara contra lo último que se procesó.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <Selector etiqueta="Periodo" valor={pid} cambiar={setPid} className="min-w-64" opciones={periodos.map((p) => ({ valor: String(p.id), texto: `${p.empresa.codigo} · ${p.nombre}${p.procesado_en ? "" : " (sin procesar)"}` }))} />
        <Boton onClick={correr} cargando={ocupado} disabled={!pid}>
          <FlaskConical className="h-4 w-4" /> Probar
        </Boton>
      </div>
      {r && (
        <div className="mt-4 space-y-3 text-sm">
          <p>
            <span className="font-semibold">{r.periodo}:</span>{" "}
            {!r.procesado
              ? "el periodo no se había procesado, así que todo sale como nuevo."
              : r.cambios.length === 0
                ? "el TXT quedaría igual."
                : `${r.cambios.length} ${r.cambios.length === 1 ? "cambio" : "cambios"} en el TXT.`}{" "}
            Terceros: {r.terceros_antes} antes, {r.terceros_despues} con esta prueba. {r.txt ? "El TXT se generaría." : "El TXT no se generaría."} Incidencias con posible impacto: {r.incidencias_posibles}.
          </p>
          {r.cambios.length > 0 && (
            <div className="max-h-72 overflow-auto rounded-2xl border border-smn-gris-100">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-superficie text-[13px] text-smn-gris-500">
                  <tr>
                    <th className="p-2">RFC</th>
                    <th className="p-2">Qué cambia</th>
                    <th className="p-2 text-right">Antes</th>
                    <th className="p-2 text-right">Con la prueba</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-smn-gris-100">
                  {r.cambios.map((x, i) => (
                    <tr key={i}>
                      <td className="p-2 font-semibold">{x.rfc}</td>
                      <td className="p-2">{x.que}</td>
                      <td className="p-2 text-right tabular-nums">{x.antes ?? "—"}</td>
                      <td className="p-2 text-right tabular-nums">{x.despues ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {r.criterios_pendientes.length > 0 && (
            <div className="rounded-2xl bg-amber-50 p-3 text-amber-900">
              <p className="font-semibold">Seguirían saliendo estas incidencias por criterios pendientes:</p>
              <ul className="mt-1 list-disc pl-5">
                {r.criterios_pendientes.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

function Historial({ c, cerrar }: { c: Criterio; cerrar: () => void }) {
  const avisar = useAvisos();
  const [h, setH] = useState<CambioHistorial[] | null>(null);
  useEffect(() => {
    api<CambioHistorial[]>(`${RUTA_BASE}/criterios/${c.clave}/historial`).then(setH).catch((e) => avisar(mensajeDe(e), "info"));
  }, [c.clave, avisar]);
  return (
    <Modal titulo={`Historial · ${c.titulo}`} cerrar={cerrar} ancho="max-w-2xl">
      {!h ? (
        <Esqueleto className="h-24" />
      ) : (
        <ul className="divide-y divide-smn-gris-100 text-sm">
          {h.map((x, i) => (
            <li key={i} className="py-2">
              <p>
                <span className="font-semibold">{ACCIONES_HISTORIAL[x.accion] ?? x.accion}</span> · versión {x.version} · {x.usuario} · {fechaLocal(x.momento)}
              </p>
              {x.motivo && <p className="text-smn-gris-500">{x.motivo}</p>}
              {x.detalle?.desde ? <p className="text-[13px] text-smn-gris-500">Vale desde {fecha(String(x.detalle.desde))}</p> : null}
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------- catálogos y layout

function Catalogos({ b, poner }: { b: BaseFiscal; poner: (x: BaseFiscal) => void }) {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const aprueba = puede(PERMISO_APROBAR);
  const [ver, setVer] = useState(false);
  const [f, setF] = useState({ catalogo: "tipo_operacion", clave: "", descripcion: "", valor: "", desde: inicioDeMes() });
  const [ocupado, setOcupado] = useState(false);
  const hoy = new Date().toISOString().slice(0, 10);
  const vigente = (c: Catalogo) => c.vigente_desde <= hoy && (!c.vigente_hasta || c.vigente_hasta >= hoy);

  const guardar = async () => {
    setOcupado(true);
    try {
      poner(await api<BaseFiscal>(`${RUTA_BASE}/catalogos`, { cuerpo: { catalogo: f.catalogo, clave: f.clave, descripcion: f.descripcion, valor: f.valor || null, vigente_desde: f.desde } }));
      avisar("Guardado. Los meses anteriores siguen con lo que tenían.", "exito");
      setF({ ...f, clave: "", descripcion: "", valor: "" });
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(false);
    }
  };
  const baja = async (c: Catalogo) => {
    try {
      poner(await api<BaseFiscal>(`${RUTA_BASE}/catalogos/${c.id}/baja`, { cuerpo: { vigente_hasta: hoy } }));
      avisar("Dado de baja desde hoy.", "exito");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  return (
    <>
      <label className="flex items-center gap-2 text-sm font-semibold">
        <input type="checkbox" checked={ver} onChange={(e) => setVer(e.target.checked)} /> Ver también lo que ya no vale
      </label>
      <div className="mt-3 grid gap-4 lg:grid-cols-3">
        {(Object.keys(CATALOGOS) as Catalogo["catalogo"][]).map((k) => {
          const filas = b.catalogos
            .filter((c) => c.catalogo === k && (ver || vigente(c)))
            .sort((x, y) => (k === "layout" ? Number(x.clave) - Number(y.clave) || x.clave.localeCompare(y.clave) : x.clave.localeCompare(y.clave)));
          return (
            <div key={k} className={TARJETA}>
              <p className="font-semibold">{CATALOGOS[k].titulo}</p>
              <p className="text-[13px] text-smn-gris-500">{CATALOGOS[k].ayuda}</p>
              <ul className="mt-3 divide-y divide-smn-gris-100 text-sm">
                {filas.map((c) => (
                  <li key={c.id} className={`py-2 ${vigente(c) ? "" : "opacity-50"}`}>
                    <p>
                      <span className="font-semibold">{k === "layout" && /^\d+$/.test(c.clave) ? `Campo ${c.clave}` : c.clave === "campos" ? "Campos por renglón" : c.clave === "efectos" ? "Valor del campo de requisitos" : c.clave}</span>
                      {k === "layout" ? <> · {/^\d+$/.test(c.clave) ? b.opciones.que_lleva[c.valor ?? ""] ?? c.valor : c.valor}</> : <> · {c.descripcion}</>}
                    </p>
                    <p className="text-[13px] text-smn-gris-500">
                      {fecha(c.vigente_desde)} a {c.vigente_hasta ? fecha(c.vigente_hasta) : "hoy"}
                      {aprueba && vigente(c) && !c.vigente_hasta && (
                        <button onClick={() => baja(c)} className="ml-2 font-semibold underline">
                          Dar de baja
                        </button>
                      )}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
      {aprueba && (
        <div className={`${TARJETA} mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_2fr_1fr_auto] sm:items-end`}>
          <Selector etiqueta="Catálogo" valor={f.catalogo} cambiar={(v) => setF({ ...f, catalogo: v, valor: "" })} opciones={(Object.keys(CATALOGOS) as Catalogo["catalogo"][]).map((k) => ({ valor: k, texto: CATALOGOS[k].titulo }))} />
          <Campo etiqueta={f.catalogo === "layout" ? "Número de campo" : "Clave (dos dígitos)"} value={f.clave} onChange={(e) => setF({ ...f, clave: e.target.value })} />
          {f.catalogo === "layout" ? (
            <Selector etiqueta="Qué lleva" valor={f.valor} cambiar={(v) => setF({ ...f, valor: v, descripcion: b.opciones.que_lleva[v] ?? "" })} opciones={[{ valor: "", texto: "Elige" }, ...Object.entries(b.opciones.que_lleva).map(([valor, texto]) => ({ valor, texto }))]} />
          ) : (
            <Campo etiqueta="Descripción" value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} />
          )}
          <Campo etiqueta="Vale desde" type="date" value={f.desde} onChange={(e) => setF({ ...f, desde: e.target.value })} />
          <Boton onClick={guardar} cargando={ocupado} disabled={!f.clave}>
            Agregar o cambiar
          </Boton>
          <p className="text-[13px] text-smn-gris-500 sm:col-span-5">Si la clave ya existe, la anterior vale hasta un día antes. Para cambiar el número de campos o el valor del campo de requisitos, usa «campos» o «efectos» como clave en el layout.</p>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------- documentos

function Documentos({ b, poner }: { b: BaseFiscal; poner: (x: BaseFiscal) => void }) {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const edita = puede(PERMISO_OPERAR);
  const [f, setF] = useState({ titulo: "", tipo: "reglas", version: "", desde: "", notas: "", reemplaza: "" });
  const [archivo, setArchivo] = useState<File | null>(null);
  const [avance, setAvance] = useState<number | null>(null);
  const usados = (id: number) => b.criterios.filter((c) => c.documento_id === id).length;

  const cargar = async () => {
    if (!archivo) return;
    setAvance(0);
    try {
      const extra: Record<string, string> = { titulo: f.titulo, tipo: f.tipo };
      if (f.version) extra.version = f.version;
      if (f.desde) extra.vigente_desde = f.desde;
      if (f.notas) extra.notas = f.notas;
      if (f.reemplaza) extra.reemplaza = f.reemplaza;
      poner(await subir<BaseFiscal>(`${RUTA_BASE}/documentos`, archivo, extra, setAvance));
      avisar("Documento guardado.", "exito");
      setF({ titulo: "", tipo: "reglas", version: "", desde: "", notas: "", reemplaza: "" });
      setArchivo(null);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setAvance(null);
    }
  };

  return (
    <>
      <div className={TARJETA}>
        <ul className="divide-y divide-smn-gris-100 text-sm">
          {b.documentos.map((d) => (
            <li key={d.id} className={`flex flex-wrap items-center gap-3 py-3 ${d.activo ? "" : "opacity-50"}`}>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {d.titulo} {d.version && <span className="font-normal text-smn-gris-500">· versión {d.version}</span>} {!d.activo && <Insignia className="bg-smn-gris-100 text-smn-gris-500">Reemplazado</Insignia>}
                </p>
                <p className="text-[13px] text-smn-gris-500">
                  {b.opciones.tipos_documento[d.tipo] ?? d.tipo}
                  {d.vigente_desde && <> · vale desde {fecha(d.vigente_desde)}</>} · lo citan {usados(d.id)} criterio(s)
                  {d.sha256 && <> · huella {d.sha256.slice(0, 12)}…</>}
                  {d.cargado_por && <> · {d.cargado_por}</>}
                </p>
                {d.notas && <p className="mt-1 text-smn-gris-500">{d.notas}</p>}
              </div>
              {d.archivo ? (
                <Boton variante="secundario" className="py-1.5" onClick={() => descargar(`${RUTA_BASE}/documentos/${d.id}/archivo`, d.archivo!).catch((e) => avisar(mensajeDe(e), "info"))}>
                  <Download className="h-4 w-4" /> {d.archivo}
                </Boton>
              ) : (
                <span className="text-[13px] text-smn-gris-500">Sin archivo cargado</span>
              )}
            </li>
          ))}
        </ul>
      </div>
      {edita && (
        <div className={`${TARJETA} mt-4 grid gap-3 sm:grid-cols-2`}>
          <p className="font-semibold sm:col-span-2">Subir un documento o una versión nueva</p>
          <Selector
            etiqueta="Es versión nueva de"
            valor={f.reemplaza}
            cambiar={(v) => {
              const d = b.documentos.find((x) => String(x.id) === v);
              setF({ ...f, reemplaza: v, titulo: d?.titulo ?? f.titulo, tipo: d?.tipo ?? f.tipo });
            }}
            opciones={[{ valor: "", texto: "Ninguno: es un documento nuevo" }, ...b.documentos.filter((d) => d.activo).map((d) => ({ valor: String(d.id), texto: d.titulo }))]}
          />
          <Campo etiqueta="Título" value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} />
          <Selector etiqueta="Tipo" valor={f.tipo} cambiar={(v) => setF({ ...f, tipo: v })} opciones={Object.entries(b.opciones.tipos_documento).map(([valor, texto]) => ({ valor, texto }))} />
          <div className="grid grid-cols-2 gap-3">
            <Campo etiqueta="Versión" value={f.version} onChange={(e) => setF({ ...f, version: e.target.value })} />
            <Campo etiqueta="Vale desde" type="date" value={f.desde} onChange={(e) => setF({ ...f, desde: e.target.value })} />
          </div>
          <Campo etiqueta="Notas" value={f.notas} onChange={(e) => setF({ ...f, notas: e.target.value })} />
          <label className="block">
            <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">Archivo</span>
            <input type="file" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} className="block w-full text-sm" />
          </label>
          <div className="flex items-center justify-end gap-3 sm:col-span-2">
            {avance !== null && <span className="text-sm tabular-nums text-smn-gris-500">{avance} %</span>}
            <Boton onClick={cargar} cargando={avance !== null} disabled={!archivo || !f.titulo.trim()}>
              <FileUp className="h-4 w-4" /> Subir
            </Boton>
          </div>
          <p className="text-[13px] text-smn-gris-500 sm:col-span-2">Si es versión nueva, los criterios que citaban la anterior pasan a citar esta, y la anterior queda en el historial.</p>
        </div>
      )}
    </>
  );
}
