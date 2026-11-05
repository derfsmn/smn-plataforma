"use client";
// Centro de datos · ETL de ventas: trae de SMNBI (base de Sistemas) la venta sumada por producto, tienda y semana,
// muestra en vivo cada paso de la carga y el cuadre contra el origen. Nada se carga hasta que alguien lo lanza.

import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, CircleDashed, Clock, CloudUpload, Database, FileText, Hourglass, Loader2, OctagonX, Play, PlugZap, Settings, Square, XCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, fechaLocal, mensajeDe, pesos } from "@/lib/api";
import { fechaDia, nombreMes, PASOS, subirCsvSmnbi, subirCsvVentas, subirRevisionSmnbi, type CargaDetalle, type CargaEtl, type EstadoEtl, type FuenteEtl, type PruebaConexion, type RevisionSmnbi } from "@/lib/etl";
import { descargar } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Encabezado, Entrada, Esqueleto, Insignia } from "@/componentes/ui";

const DIAS = ["", "lun", "mar", "mié", "jue", "vie", "sáb", "dom"];
const MB_ARCHIVO = 300;
const num = (v: number | string | null, decimales = 0) =>
  v === null ? "—" : Number(v).toLocaleString("es-MX", { minimumFractionDigits: decimales, maximumFractionDigits: decimales });

const ESTADOS: Record<CargaEtl["estado"], { texto: string; clase: string }> = {
  completa: { texto: "Completa", clase: "bg-tinta text-superficie" },
  fallida: { texto: "Falló", clase: "bg-red-500/10 text-red-700 dark:text-red-400" },
  detenida: { texto: "Detenida", clase: "bg-smn-gris-100 text-smn-gris-700" },
  en_curso: { texto: "En curso", clase: "bg-aviso-fondo text-aviso-texto" },
};

const FUENTE_ESTADO: Record<FuenteEtl["estado"], { texto: string; clase: string }> = {
  lista: { texto: "Lista", clase: "bg-smn-naranja text-smn-negro" },
  en_curso: { texto: "Cargando", clase: "bg-aviso-fondo text-aviso-texto" },
};

function periodo(c: { desde: string | null; hasta: string | null }) {
  if (!c.desde) return "—";
  return c.desde === c.hasta || !c.hasta ? nombreMes(c.desde) : `${nombreMes(c.desde, true)} a ${nombreMes(c.hasta, true)}`;
}

export default function Etl() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const corre = puede("datos.etl.correr");
  const [estado, setEstado] = useState<EstadoEtl | null>(null);
  const [confirmar, setConfirmar] = useState(false);
  const [lanzando, setLanzando] = useState(false);
  const [probando, setProbando] = useState(false);
  const [prueba, setPrueba] = useState<PruebaConexion | null>(null);
  const [deteniendo, setDeteniendo] = useState(false);
  const [detalle, setDetalle] = useState<number | null>(null);
  const [subida, setSubida] = useState<{ nombre: string; avance: number } | null>(null);
  const entrada = useRef<HTMLInputElement>(null);
  const enCursoAntes = useRef<number | null>(null);

  const cargar = useCallback(() => {
    api<EstadoEtl>("/api/datos/etl").then(setEstado).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  useEffect(cargar, [cargar]);

  // Mientras hay una carga en curso se revisa cada 3 segundos; al terminar se avisa cómo quedó
  const enCurso = estado?.en_curso;
  useEffect(() => {
    if (enCurso) {
      enCursoAntes.current = enCurso.id;
      const t = setTimeout(cargar, 3000);
      return () => clearTimeout(t);
    }
    if (enCursoAntes.current !== null && estado) {
      const ultima = estado.cargas.find((c) => c.id === enCursoAntes.current);
      enCursoAntes.current = null;
      if (ultima?.estado === "completa") avisar(ultima.cuadra === false ? "Carga terminada, pero un mes no cuadra: revisa el detalle" : "Ventas cargadas y cuadradas", ultima.cuadra === false ? "info" : "exito");
      else if (ultima) avisar(ultima.estado === "detenida" ? "Carga detenida" : "La carga falló; revisa el detalle", "info");
    }
  }, [enCurso, estado, cargar, avisar]);

  const correr = async () => {
    setLanzando(true);
    try {
      await api("/api/datos/etl/correr", { metodo: "POST" });
      setConfirmar(false);
      avisar("Carga iniciada", "exito");
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setLanzando(false);
    }
  };

  const probar = async () => {
    setProbando(true);
    setPrueba(null);
    try {
      setPrueba(await api<PruebaConexion>("/api/datos/etl/probar", { metodo: "POST" }));
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setProbando(false);
    }
  };

  const detener = async () => {
    setDeteniendo(true);
    try {
      await api("/api/datos/etl/detener", { metodo: "POST" });
      avisar("Se detendrá al terminar lo que está guardando", "info");
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setDeteniendo(false);
    }
  };

  const subir = (archivos: FileList | null) => {
    const archivo = archivos?.[0];
    if (entrada.current) entrada.current.value = "";
    if (!archivo) return;
    if (archivo.size > MB_ARCHIVO * 1024 * 1024) return avisar(`El archivo pasa de ${MB_ARCHIVO} MB. Sube un mes por archivo.`, "info");
    setSubida({ nombre: archivo.name, avance: 0 });
    subirCsvVentas(archivo, (avance) => setSubida({ nombre: archivo.name, avance }))
      .then((c) => {
        avisar(`Cargando ${c.desde ? nombreMes(c.desde) : "el archivo"}`, "exito");
        cargar();
      })
      .catch((e) => avisar(mensajeDe(e), "info"))
      .finally(() => setSubida(null));
  };

  if (!estado) return <Esqueleto className="h-96" />;
  const { conexion, resumen } = estado;
  const dias = estado.dias_semana.length === 7 ? "todos los días" : estado.dias_semana.map((d) => DIAS[d]).join(", ");
  const primera = !resumen.filas;

  return (
    <>
      <Encabezado
        titulo="ETL de ventas"
        descripcion="Trae de SMNBI la venta por producto, tienda y semana, y comprueba que lo cargado sume lo mismo que el origen."
        accion={
          corre && (
            <div className="flex flex-wrap gap-2">
              <Boton onClick={() => setConfirmar(true)} disabled={!!enCurso || !conexion.configurada}>
                <Play className="h-4 w-4" /> Correr ahora
              </Boton>
              <Boton variante="secundario" onClick={probar} cargando={probando} disabled={!conexion.configurada}>
                <PlugZap className="h-4 w-4" /> Probar conexión
              </Boton>
              <Boton variante="secundario" onClick={() => entrada.current?.click()} cargando={!!subida} disabled={!!enCurso}>
                <CloudUpload className="h-4 w-4" /> Subir CSV
              </Boton>
              <input ref={entrada} type="file" accept=".csv,.txt" className="hidden" onChange={(e) => subir(e.target.files)} />
            </div>
          )
        }
      />

      {!conexion.configurada && (
        <Entrada className="mb-5 flex flex-wrap items-center gap-3 rounded-2xl border border-dashed border-smn-naranja bg-aviso-fondo px-4 py-3 text-sm text-aviso-texto">
          <Settings className="h-5 w-5 shrink-0" />
          <p className="min-w-0 flex-1">
            Sin conexión a SMNBI. Falta capturar en Configuración, sección «ETL de ventas (SMNBI)»: <b>{conexion.falta.join(", ")}</b>. Mientras tanto puedes subir el CSV
            que sale de la consulta <span className="font-mono text-[13px]">consulta_venta_semanal.sql</span> en SSMS, un mes por archivo.
          </p>
          {puede("nucleo.configuracion.administrar") && (
            <Link href="/admin/configuracion" className="font-semibold underline underline-offset-2">
              Ir a Configuración
            </Link>
          )}
        </Entrada>
      )}

      {subida && (
        <Entrada className="mb-5 rounded-2xl border border-smn-gris-100 bg-superficie p-4 text-sm">
          <p className="mb-2 font-semibold">
            Subiendo {subida.nombre}… {subida.avance} %
          </p>
          <div className="h-2 overflow-hidden rounded-full bg-smn-gris-100">
            <motion.div className="h-full rounded-full bg-smn-naranja" animate={{ width: `${subida.avance}%` }} />
          </div>
        </Entrada>
      )}

      {prueba && (
        <Entrada className="mb-5 flex flex-wrap items-center gap-3 rounded-2xl border border-smn-gris-100 bg-superficie px-4 py-3 text-sm">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-smn-naranja" />
          <p className="min-w-0 flex-1">
            Conexión correcta a <b>{conexion.base}</b>. Ve {num(prueba.ventas)} ventas{prueba.desde && prueba.hasta && ` del ${fechaDia(prueba.desde)} al ${fechaDia(prueba.hasta)}`} y{" "}
            {num(prueba.articulos)} artículos. Solo se leyó; no se cargó nada.
          </p>
          <button onClick={() => setPrueba(null)} className="text-[13px] font-medium text-smn-gris-500 underline underline-offset-2">
            Cerrar
          </button>
        </Entrada>
      )}

      <AnimatePresence>{enCurso && <EnVivo key={enCurso.id} carga={enCurso} detener={corre ? detener : undefined} deteniendo={deteniendo} />}</AnimatePresence>

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { t: "Filas de venta semanal", v: num(resumen.filas), icono: Database },
          { t: "Meses cargados", v: num(resumen.meses), icono: FileText },
          { t: "Semanas", v: resumen.semana_desde && resumen.semana_hasta ? `${fechaDia(resumen.semana_desde)} a ${fechaDia(resumen.semana_hasta)}` : "—", icono: Clock, chico: true },
          { t: "Última carga buena", v: resumen.ultima_buena ? fechaLocal(resumen.ultima_buena) : "Ninguna", icono: CheckCircle2, chico: true },
        ].map(({ t, v, icono: Icono, chico }, i) => (
          <Entrada key={t} retraso={i * 0.04} className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
            <Icono className="mb-2 h-5 w-5 text-smn-gris-500" />
            <p className={`font-semibold tabular-nums ${chico ? "text-base leading-snug" : "text-2xl"}`}>{v}</p>
            <p className="text-sm text-smn-gris-500">{t}</p>
          </Entrada>
        ))}
      </div>

      <section className="mb-8">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Fuentes de Sistemas</h2>
            <p className="text-sm text-smn-gris-500">
              Las tablas de SMNBI que usa el semáforo de productos. Corre su consulta en SSMS, guarda el resultado como CSV y súbelo en su tarjeta.
            </p>
          </div>
          <Boton variante="secundario" onClick={() => descargar("/api/datos/etl/smnbi/consultas", "consultas_catalogos_smnbi.sql").catch((e) => avisar(mensajeDe(e), "info"))}>
            <FileText className="h-4 w-4" /> Descargar consultas
          </Boton>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {estado.fuentes.map((f, i) => (
            <TarjetaFuente key={f.codigo} f={f} retraso={i * 0.03} corre={corre} alCargar={cargar} />
          ))}
        </div>
      </section>

      <RevisarCambios />

      <section>
        <h2 className="text-lg font-semibold">Historial de cargas</h2>
        <p className="mb-3 text-sm text-smn-gris-500">
          {estado.programado ? `Corre solo ${dias} a las ${estado.hora}:00 y recarga los últimos meses.` : "La carga programada está apagada; solo corre con el botón."}{" "}
          Cada carga reemplaza completos los meses que trae, así que repetirla no duplica nada.
          {!estado.factura_electronica && " «Factura Electronica» queda fuera hasta que Sistemas confirme si duplica a «Nota»."}
        </p>
        {!estado.cargas.length ? (
          <p className="rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-4 py-6 text-center text-sm text-smn-gris-500">
            Todavía no hay cargas. Nada se carga hasta que alguien presiona «Correr ahora» o sube un CSV.
          </p>
        ) : (
          <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
            {estado.cargas.map((c) => (
              <li key={c.id}>
                <button onClick={() => setDetalle(c.id)} className="flex w-full flex-wrap items-start gap-x-4 gap-y-1 p-4 text-left text-sm hover:bg-smn-gris-100/40">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">
                      {periodo(c)}
                      <Insignia className={`ml-2 ${ESTADOS[c.estado].clase}`}>{ESTADOS[c.estado].texto}</Insignia>
                      {c.cuadra === false && <Insignia className="ml-2 bg-red-500/10 text-red-700 dark:text-red-400">No cuadra</Insignia>}
                      {c.cuadra === true && <Insignia className="ml-2 bg-smn-gris-100 text-smn-gris-700">Cuadra</Insignia>}
                    </p>
                    <p className="text-smn-gris-500">
                      <Clock className="mr-1 inline h-3.5 w-3.5" />
                      {fechaLocal(c.inicio_en)} · {c.archivo ? `CSV ${c.archivo}` : "SMNBI"} ·{" "}
                      {c.disparada_por === "manual" ? `a mano${c.usuario ? ` por ${c.usuario}` : ""}` : "programada"}
                      {c.fin_en && ` · ${duracion(c.inicio_en, c.fin_en)}`}
                    </p>
                    {c.error && <p className="mt-1 text-red-700 dark:text-red-400">{c.error}</p>}
                  </div>
                  <p className="text-smn-gris-700 tabular-nums">
                    {num(c.leidos)} leídas · {num(c.cargados)} cargadas{c.fuera > 0 && ` · ${num(c.fuera)} fuera`}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <AnimatePresence>
        {confirmar && (
          <Modal titulo="Correr el ETL de ventas" cerrar={() => setConfirmar(false)}>
            <div className="space-y-4 text-sm">
              <p>
                {primera ? "Es la primera carga: trae todos los meses desde el primero configurado." : "Recarga los meses recientes y cualquiera que no haya cuadrado."} Va a traer{" "}
                <b>{estado.proximos_meses.length === 1 ? "1 mes" : `${estado.proximos_meses.length} meses`}</b>:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {estado.proximos_meses.map((m) => (
                  <Insignia key={m} className="bg-smn-gris-100 text-smn-gris-700">
                    {nombreMes(m, true)}
                  </Insignia>
                ))}
              </div>
              <p className="text-smn-gris-500">Solo lee SMNBI. Cada mes se reemplaza completo al terminar de cargarse; si la detienes, los meses terminados se quedan.</p>
              <div className="flex justify-end gap-2">
                <Boton variante="secundario" onClick={() => setConfirmar(false)}>
                  Cancelar
                </Boton>
                <Boton onClick={correr} cargando={lanzando}>
                  <Play className="h-4 w-4" /> Correr
                </Boton>
              </div>
            </div>
          </Modal>
        )}
      </AnimatePresence>

      <AnimatePresence>{detalle !== null && <Detalle id={detalle} vivo={enCurso?.id === detalle} cerrar={() => setDetalle(null)} />}</AnimatePresence>
    </>
  );
}

function duracion(inicio: string, fin: string) {
  const s = Math.max(1, Math.round((new Date(fin).getTime() - new Date(inicio).getTime()) / 1000));
  return s < 60 ? `${s} s` : s < 3600 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
}

function EnVivo({ carga, detener, deteniendo }: { carga: CargaEtl; detener?: () => void; deteniendo: boolean }) {
  // El avance es por meses; dentro del mes, por paso (5 pasos)
  const indice = Math.max(0, PASOS.findIndex((p) => p.codigo === carga.paso));
  const total = Math.max(1, carga.meses_total);
  const dentro = carga.paso === "conectar" ? 0 : indice / PASOS.length;
  const avance = Math.min(100, Math.round(((carga.meses_hechos + dentro) / total) * 100));
  const mesActual = Math.min(total, carga.meses_hechos + 1);
  return (
    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mb-6 overflow-hidden">
      <div className="rounded-2xl border border-smn-naranja/60 bg-superficie p-4 sm:p-5">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="flex items-center gap-2 font-semibold">
              <Loader2 className="h-4 w-4 animate-spin text-smn-naranja" />
              {carga.detener ? "Deteniendo…" : carga.archivo ? `Cargando ${carga.archivo}` : "Cargando ventas de SMNBI"}
            </p>
            <p className="text-sm text-smn-gris-500">
              {carga.mes_actual ? `${nombreMes(carga.mes_actual)} · mes ${mesActual} de ${total}` : `Mes ${mesActual} de ${total}`} · empezó {fechaLocal(carga.inicio_en, { timeStyle: "short" })}
            </p>
          </div>
          {detener && (
            <Boton variante="secundario" onClick={detener} cargando={deteniendo} disabled={carga.detener}>
              <Square className="h-4 w-4" /> Detener
            </Boton>
          )}
        </div>

        <div className="mb-4 h-2 overflow-hidden rounded-full bg-smn-gris-100" role="progressbar" aria-valuenow={avance} aria-valuemin={0} aria-valuemax={100}>
          <motion.div className="h-full rounded-full bg-smn-naranja" animate={{ width: `${Math.max(3, avance)}%` }} transition={{ duration: 0.5 }} />
        </div>

        <ol className="mb-4 grid grid-cols-5 gap-1.5 sm:gap-3">
          {PASOS.map((p, i) => {
            const hecho = i < indice;
            const actual = i === indice;
            return (
              <li key={p.codigo} className="min-w-0 text-center">
                <span
                  className={`mx-auto mb-1 flex h-8 w-8 items-center justify-center rounded-full border-2 ${hecho ? "border-smn-negro bg-tinta text-superficie dark:border-smn-gris-700 dark:bg-smn-gris-700 dark:text-smn-negro" : actual ? "border-smn-naranja text-smn-naranja" : "border-smn-gris-300 text-smn-gris-500"}`}
                >
                  {hecho ? <CheckCircle2 className="h-4 w-4" /> : actual ? <Loader2 className="h-4 w-4 animate-spin" /> : <CircleDashed className="h-4 w-4" />}
                </span>
                <span className={`block truncate text-[13px] font-semibold sm:text-[13px] ${actual ? "text-tinta" : "text-smn-gris-500"}`}>{p.texto}</span>
              </li>
            );
          })}
        </ol>

        <dl className="grid grid-cols-3 gap-3 text-center text-sm">
          {[
            ["Filas leídas", carga.leidos],
            ["Cargadas", carga.cargados],
            ["Fuera por reglas", carga.fuera],
          ].map(([t, v]) => (
            <div key={t} className="rounded-xl bg-smn-gris-100/60 px-2 py-2">
              <dd className="text-lg font-semibold tabular-nums">{num(v)}</dd>
              <dt className="text-[13px] text-smn-gris-500">{t}</dt>
            </div>
          ))}
        </dl>
      </div>
    </motion.div>
  );
}

const ICONO_PASO = { hecho: CheckCircle2, en_curso: Loader2, detenido: OctagonX, fallido: XCircle } as const;

function Detalle({ id, vivo, cerrar }: { id: number; vivo: boolean; cerrar: () => void }) {
  const avisar = useAvisos();
  const [c, setC] = useState<CargaDetalle | null>(null);
  const traer = useCallback(() => {
    api<CargaDetalle>(`/api/datos/etl/cargas/${id}`).then(setC).catch((e) => avisar(mensajeDe(e), "info"));
  }, [id, avisar]);
  useEffect(traer, [traer]);
  useEffect(() => {
    if (!vivo) return;
    const t = setInterval(traer, 3000);
    return () => clearInterval(t);
  }, [vivo, traer]);

  return (
    <Modal titulo={c ? `Carga de ${periodo(c)}` : "Carga"} cerrar={cerrar} ancho="max-w-3xl">
      {!c ? (
        <Esqueleto className="h-64" />
      ) : (
        <div className="space-y-5 text-sm">
          <p className="text-smn-gris-500">
            <Insignia className={`mr-2 ${ESTADOS[c.estado].clase}`}>{ESTADOS[c.estado].texto}</Insignia>
            {fechaLocal(c.inicio_en)} · {c.archivo ? `CSV ${c.archivo}` : "SMNBI"} · {c.disparada_por === "manual" ? `a mano${c.usuario ? ` por ${c.usuario}` : ""}` : "programada"}
            {c.fin_en && ` · ${duracion(c.inicio_en, c.fin_en)}`}
          </p>
          {c.error && <p className="rounded-xl bg-red-500/10 p-3 text-red-700 dark:text-red-400">{c.error}</p>}

          <div>
            <h3 className="mb-2 font-semibold">Cuadre</h3>
            <p className="mb-2 text-[13px] text-smn-gris-500">
              Lo cargado contra {c.archivo ? "lo que suma el archivo" : "lo que suma SMNBI con las mismas reglas"}, por mes y empresa. Cuadra si la diferencia es menor a 0.01 %.
            </p>
            {!c.cuadre.length ? (
              <p className="text-smn-gris-500">{c.estado === "en_curso" ? "Se llena al terminar cada mes." : "Sin cuadre."}</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-smn-gris-100">
                <table className="w-full text-[13px]">
                  <thead className="bg-smn-gris-100/60 text-left font-semibold text-smn-gris-500">
                    <tr>
                      <th className="px-3 py-2">Mes</th>
                      <th className="px-3 py-2">Empresa</th>
                      <th className="px-3 py-2 text-right">Importe origen</th>
                      <th className="px-3 py-2 text-right">Importe cargado</th>
                      <th className="px-3 py-2 text-right">Piezas origen</th>
                      <th className="px-3 py-2 text-right">Piezas cargadas</th>
                      <th className="px-3 py-2 text-right">Renglones fuera</th>
                      <th className="px-3 py-2">Cuadra</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-smn-gris-100">
                    {c.cuadre.map((q) => (
                      <tr key={`${q.mes}-${q.empresa}`}>
                        <td className="px-3 py-2 whitespace-nowrap">{nombreMes(q.mes, true)}</td>
                        <td className="px-3 py-2 font-mono">{q.empresa}</td>
                        <td className="px-3 py-2 text-right whitespace-nowrap tabular-nums">{q.importe_origen === null ? "—" : pesos(q.importe_origen)}</td>
                        <td className="px-3 py-2 text-right whitespace-nowrap tabular-nums">{pesos(q.importe_cargado)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{num(q.piezas_origen, 0)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{num(q.piezas_cargadas, 0)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{num(q.renglones_fuera)}</td>
                        <td className="px-3 py-2">
                          {q.cuadra === null ? "—" : q.cuadra ? <span className="font-semibold">Sí</span> : <span className="font-semibold text-red-700 dark:text-red-400">No</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div>
            <h3 className="mb-2 font-semibold">Pasos</h3>
            <ol className="space-y-1.5">
              {c.pasos.map((p, i) => {
                const Icono = ICONO_PASO[p.estado];
                return (
                  <li key={i} className="flex items-start gap-3 rounded-xl border border-smn-gris-100 px-3 py-2">
                    <Icono
                      className={`mt-0.5 h-4 w-4 shrink-0 ${p.estado === "en_curso" ? "animate-spin text-smn-naranja" : p.estado === "fallido" ? "text-red-700 dark:text-red-400" : "text-smn-gris-500"}`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold">
                        {PASOS.find((x) => x.codigo === p.paso)?.texto ?? p.paso}
                        {p.mes && <span className="font-normal text-smn-gris-500"> · {nombreMes(p.mes, true)}</span>}
                      </p>
                      {p.nota && <p className="text-[13px] text-smn-gris-500">{p.nota}</p>}
                    </div>
                    <p className="text-right text-[13px] text-smn-gris-500 tabular-nums">
                      {p.filas !== null && (
                        <>
                          {num(p.filas)} {p.filas === 1 ? "fila" : "filas"}
                          <br />
                        </>
                      )}
                      {p.fin_en ? duracion(p.inicio_en, p.fin_en) : <Hourglass className="inline h-3 w-3" />}
                    </p>
                  </li>
                );
              })}
            </ol>
          </div>
        </div>
      )}
    </Modal>
  );
}

/** Una fuente de SMNBI: qué trae, cuántas filas hay, la última carga y el botón para subir su CSV. */
function TarjetaFuente({ f, retraso, corre, alCargar }: { f: FuenteEtl; retraso: number; corre: boolean; alCargar: () => void }) {
  const avisar = useAvisos();
  const entrada = useRef<HTMLInputElement>(null);
  const [avance, setAvance] = useState<number | null>(null);
  const u = f.ultima;
  const cargando = f.estado === "en_curso" || avance !== null;

  // Mientras se carga, se revisa cada 3 segundos
  useEffect(() => {
    if (f.estado !== "en_curso") return;
    const t = setTimeout(alCargar, 3000);
    return () => clearTimeout(t);
  }, [f, alCargar]);

  const subir = async (archivo: File | undefined) => {
    if (!archivo) return;
    if (archivo.size > MB_ARCHIVO * 1024 * 1024) return avisar(`El archivo pasa de ${MB_ARCHIVO} MB.`, "info");
    setAvance(0);
    try {
      await subirCsvSmnbi(f.codigo, archivo, setAvance);
      avisar(`${f.nombre}: archivo recibido, cargando`, "exito");
      alCargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setAvance(null);
      if (entrada.current) entrada.current.value = "";
    }
  };

  return (
    <Entrada retraso={retraso} className={`flex flex-col rounded-2xl border bg-superficie p-4 text-sm ${f.estado === "lista" && (f.filas || f.ultima_carga) ? "border-smn-naranja/60" : "border-smn-gris-100"}`}>
      <div className="mb-1 flex items-start justify-between gap-2">
        <p className="font-semibold">{f.nombre}</p>
        <Insignia className={`shrink-0 whitespace-nowrap ${FUENTE_ESTADO[f.estado].clase}`}>{FUENTE_ESTADO[f.estado].texto}</Insignia>
      </div>
      <p className="mb-2 font-mono text-[13px] text-smn-gris-500">
        {f.tablas.join(", ")}
        {f.columnas ? ` · ${f.columnas} columnas` : ""}
      </p>
      <p className="text-smn-gris-700">{f.nota}</p>
      {f.codigo === "ventas" ? (
        <p className="mt-2 text-[13px] text-smn-gris-500">{f.ultima_carga ? `Última carga buena: ${fechaLocal(f.ultima_carga)}` : "Todavía sin cargar"}</p>
      ) : (
        <>
          <p className="mt-2 text-[13px] text-smn-gris-500">
            {u ? (
              <>
                {u.estado === "completa" && <CheckCircle2 className="mr-1 inline h-3.5 w-3.5 text-smn-naranja" />}
                {u.estado === "fallida" && <XCircle className="mr-1 inline h-3.5 w-3.5 text-red-500" />}
                {u.estado === "en_curso" ? "Cargando" : u.estado === "fallida" ? "Falló" : "Cargado"} {u.archivo && `«${u.archivo}»`}
                {u.estado !== "en_curso" && ` ${fechaLocal(u.fin_en ?? u.inicio_en)}`}
                {u.estado === "completa" && ` · ${num(u.cargados)} renglones${u.fuera ? `, ${num(u.fuera)} fuera` : ""}`}
              </>
            ) : (
              "Todavía sin cargar"
            )}
            {f.filas ? ` · hoy hay ${num(f.filas)}` : ""}
          </p>
          {u?.nota && <p className={`mt-1 text-[13px] ${u.estado === "fallida" ? "text-red-700 dark:text-red-400" : "text-smn-gris-500"}`}>{u.nota}</p>}
          {corre && (
            <div className="mt-auto pt-3">
              <Boton variante="secundario" className="w-full py-1.5" cargando={cargando} disabled={cargando} onClick={() => entrada.current?.click()}>
                <CloudUpload className="h-4 w-4" /> {avance !== null ? `Subiendo ${avance} %` : cargando ? "Cargando…" : "Subir CSV"}
              </Boton>
              <input ref={entrada} type="file" accept=".csv,.txt" className="hidden" onChange={(e) => subir(e.target.files?.[0])} />
            </div>
          )}
        </>
      )}
    </Entrada>
  );
}

// ---------------------------------------------------------------- ¿hay cambios en SMNBI?

const REVISION: Record<RevisionSmnbi["renglones"][number]["estado"], { texto: string; punto: string }> = {
  igual: { texto: "Igual", punto: "bg-emerald-600" },
  cambio: { texto: "Cambió", punto: "bg-amber-500" },
  nuevo: { texto: "Nuevo", punto: "bg-smn-naranja" },
  sobra: { texto: "Revisar", punto: "bg-red-600" },
};

function RevisarCambios() {
  const avisar = useAvisos();
  const entrada = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [r, setR] = useState<RevisionSmnbi | null>(null);
  const [verIguales, setVerIguales] = useState(false);
  const subir = async (archivo: File) => {
    setSubiendo(true);
    try {
      setR(await subirRevisionSmnbi(archivo));
      setVerIguales(false);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setSubiendo(false);
      if (entrada.current) entrada.current.value = "";
    }
  };
  const cambios = r?.renglones.filter((x) => x.estado !== "igual") ?? [];
  const visibles = r ? (verIguales ? r.renglones : cambios) : [];
  const acciones = [...new Set(cambios.map((x) => x.accion).filter((x): x is string => !!x))];
  return (
    <section className="mb-8 rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-2xl">
          <h2 className="text-lg font-semibold">Revisar si hay cambios</h2>
          <p className="mt-1 text-[15px] text-smn-gris-700">
            Compara cómo está SMNBI hoy con lo que tiene cargado la plataforma y dice qué volver a cargar. Solo lee: no carga ni borra nada.
          </p>
        </div>
      </div>
      <ol className="mt-4 grid gap-3 md:grid-cols-3">
        {[
          "Descarga la consulta de revisión.",
          "Córrela en SSMS y guarda el resultado como CSV.",
          "Sube el CSV aquí y revisa qué cambió.",
        ].map((t, i) => (
          <li key={t} className="flex items-start gap-3 rounded-xl border border-smn-gris-100 p-3 text-[15px]">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-smn-gris-300 text-[13px] font-semibold">{i + 1}</span>
            {t}
          </li>
        ))}
      </ol>
      <div className="mt-4 flex flex-wrap gap-2">
        <Boton variante="secundario" onClick={() => descargar("/api/datos/etl/smnbi/revision/consulta", "revisar_cambios_smnbi.sql").catch((e) => avisar(mensajeDe(e), "info"))}>
          <FileText className="h-4 w-4" /> Descargar consulta de revisión
        </Boton>
        <Boton onClick={() => entrada.current?.click()} cargando={subiendo}>
          <CloudUpload className="h-4 w-4" /> Subir resultado
        </Boton>
        <input ref={entrada} type="file" accept=".csv,.txt" className="hidden" onChange={(e) => e.target.files?.[0] && subir(e.target.files[0])} />
      </div>

      {r && (
        <div className="mt-5 border-t border-smn-gris-100 pt-4">
          <p className="text-[16px] font-semibold">{r.resumen}</p>
          {acciones.length > 0 && (
            <div className="mt-2">
              <p className="text-[14px] font-medium text-smn-gris-700">Qué cargar, en este orden:</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[15px]">
                {acciones.map((a) => <li key={a}>{a}</li>)}
              </ul>
            </div>
          )}
          {visibles.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-[14px]">
                <thead className="text-[13px] text-smn-gris-500">
                  <tr className="border-b border-smn-gris-100">
                    <th className="py-2 pr-3 font-medium">Qué</th>
                    <th className="py-2 pr-3 font-medium">En SMNBI</th>
                    <th className="py-2 pr-3 font-medium">En la plataforma</th>
                    <th className="py-2 font-medium">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {visibles.map((x) => (
                    <tr key={x.fuente + x.que} className="border-b border-smn-gris-100 last:border-0">
                      <td className="py-2 pr-3 font-medium">{x.que}</td>
                      <td className="py-2 pr-3 tabular-nums">{x.smnbi}</td>
                      <td className="py-2 pr-3 tabular-nums text-smn-gris-700">{x.plataforma}</td>
                      <td className="py-2">
                        <span className="inline-flex items-center gap-1.5">
                          <span className={`h-2 w-2 rounded-full ${REVISION[x.estado].punto}`} /> {REVISION[x.estado].texto}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {r.renglones.length > cambios.length && (
            <button onClick={() => setVerIguales((v) => !v)} className="mt-3 text-[15px] font-medium text-smn-gris-700 hover:text-tinta">
              {verIguales ? "Ver solo lo que cambió" : `Ver también lo que está igual (${r.renglones.length - cambios.length})`}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
