"use client";
// Dictamen de una regla manual o asistida: la persona del rol que toca decide con evidencia citada del expediente.
// La IA local puede sugerir, marcado como sugerencia; nunca cambia el resultado por sí sola.

import Link from "next/link";
import { useParams } from "next/navigation";
import { Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Encabezado, Esqueleto, Insignia } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { P, RUTA, SEVERIDAD, fecha, partesConCitas, type Revision } from "@/lib/innovacion";
import { ChipResultado, MenuModulo, SinAcceso, TARJETA, Texto, Vacio, Volver } from "../../comunes";

const DICTAMEN: Record<string, string> = { cumple: "Cumple", incumple: "No cumple", no_aplica: "No aplica" };

export default function PaginaRevision() {
  const { id } = useParams<{ id: string }>();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [r, setR] = useState<Revision | null>(null);
  const [dictamen, setDictamen] = useState("");
  const [motivo, setMotivo] = useState("");
  const [respaldo, setRespaldo] = useState<number[]>([]);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const cargar = useCallback(() => api<Revision>(`${RUTA}/revisiones/${id}`).then(setR).catch((e) => avisar(mensajeDe(e), "info")), [id, avisar]);
  useEffect(() => {
    if (puede(P.expVer)) cargar();
  }, [puede, cargar]);

  if (!puede(P.expVer)) return <SinAcceso />;
  if (!r) return <Esqueleto className="h-64" />;
  const sugerir = async () => {
    setOcupado("sugerir");
    try {
      const s = await api<Revision["sugerencia_ia"]>(`${RUTA}/revisiones/${r.id}/sugerencia`, { metodo: "POST", cuerpo: {} });
      setR({ ...r, sugerencia_ia: s });
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };
  const dictaminar = async () => {
    setOcupado("dictaminar");
    try {
      await api(`${RUTA}/revisiones/${r.id}/dictamen`, { cuerpo: { dictamen, motivo: motivo.trim(), respaldo } });
      avisar("Dictamen guardado. El expediente se volvió a evaluar.", "exito");
      await cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };
  const s = r.sugerencia_ia;
  const evidenciaPorNumero = r.evidencia.filter((x) => x.recurso_id);
  return (
    <>
      <Volver href={`/innovacion/expedientes/${r.folio}`} texto={`${r.folio} ${r.expediente}`} />
      <Encabezado titulo={`Dictamen · ${r.regla.codigo} v${r.regla.version}`} descripcion={r.regla.proposito} />
      <MenuModulo />
      <div className="mb-4 flex flex-wrap gap-2 text-sm">
        <Insignia className="bg-smn-gris-100 text-smn-gris-700">{SEVERIDAD[r.regla.severidad]}</Insignia>
        {r.rol && <Insignia className="bg-smn-gris-100 text-smn-gris-700">Le toca a {r.rol.replace("innovacion_", "")}</Insignia>}
        {r.vence_en && r.estado === "asignada" && <Insignia className="bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">Vence {fecha(r.vence_en)}</Insignia>}
        {r.regla.fuente && <Link href={`/innovacion/fuentes/${r.regla.fuente.recurso_id}`} className="text-smn-naranja underline">Fuente: {r.regla.fuente.titulo} v{r.regla.fuente.version}{r.regla.fuente.ubicacion ? ` · ${r.regla.fuente.ubicacion}` : ""}</Link>}
      </div>
      <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
        <div className="grid content-start gap-5">
          <div className={TARJETA}>
            <h2 className="mb-2 font-semibold">Ficha que se revisa{r.ficha ? ` · versión ${r.ficha.numero}` : ""}</h2>
            {!r.ficha ? <Vacio>Sin ficha.</Vacio> : (
              <>
                <dl className="grid gap-2 text-sm sm:grid-cols-2">
                  {Object.entries(r.ficha.datos).map(([k, v]) => <div key={k}><dt className="text-smn-gris-500">{k.replace(/_/g, " ")}</dt><dd className="whitespace-pre-line">{String(v)}</dd></div>)}
                </dl>
                <ul className="mt-3 text-sm">{r.ficha.ingredientes.map((i, n) => <li key={n}>{i.nombre}{i.forma ? ` (${i.forma})` : ""}: {i.cantidad_activa ?? "—"} {i.unidad_activa ?? ""}</li>)}</ul>
              </>
            )}
          </div>
          <div className={TARJETA}>
            <h2 className="mb-2 font-semibold">Evidencia citada en el expediente</h2>
            {r.evidencia.length === 0 ? <Vacio>No hay evidencia citada. Cita una fuente en el expediente para poder dictaminar.</Vacio> : (
              <ul className="grid gap-2">
                {r.evidencia.map((x, n) => (
                  <li key={x.id}>
                    <label className="flex gap-3 rounded-lg border border-smn-gris-100 p-3 text-sm">
                      <input type="checkbox" disabled={r.estado !== "asignada" || !x.recurso_id} checked={respaldo.includes(x.id) || r.respaldo.includes(x.id)}
                        onChange={(e) => setRespaldo((y) => (e.target.checked ? [...y, x.id] : y.filter((z) => z !== x.id)))} className="mt-1" />
                      <span>
                        <span className="font-semibold">[{n + 1}] {x.titulo} v{x.version}{x.pagina ? ` · pág. ${x.pagina}` : ""}</span>
                        <span className="block">{x.respalda}</span>
                        {x.estado_fuente !== "revisado" && <span className="block text-amber-700 dark:text-amber-400">Fuente sin revisar</span>}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="grid content-start gap-5">
          {r.estado !== "asignada" ? (
            <div className={TARJETA}>
              <h2 className="mb-2 font-semibold">Dictaminada</h2>
              <p className="text-sm"><ChipResultado valor={r.dictamen ?? ""} /> · {r.dictaminada_por} · {fecha(r.dictaminada_en)}</p>
              <p className="mt-2 text-sm">{r.motivo}</p>
            </div>
          ) : !r.puede_dictaminar ? (
            <Vacio>Este dictamen le toca a {r.rol ?? "otro rol"}.</Vacio>
          ) : (
            <>
              <div className={`${TARJETA} grid gap-2`}>
                <div className="flex items-center justify-between gap-2">
                  <h2 className="font-semibold">Sugerencia de la IA local</h2>
                  <Boton variante="secundario" className="min-h-8" onClick={sugerir} cargando={ocupado === "sugerir"} disabled={evidenciaPorNumero.length === 0}><Sparkles className="h-4 w-4" /> {s ? "Otra vez" : "Pedir"}</Boton>
                </div>
                {s ? (
                  <div className="rounded-lg bg-smn-gris-50 p-3 text-sm">
                    <p className="font-semibold">Sugiere: {s.sugerencia === "no_se_puede" ? "no se puede decir con la evidencia" : DICTAMEN[s.sugerencia]}</p>
                    <p className="mt-1">{partesConCitas(s.razon).map((p, i) => (typeof p === "number" ? <b key={i}>[{p}]</b> : <span key={i}>{p}</span>))}</p>
                    {s.falta && <p className="mt-1 text-smn-gris-500">Falta: {s.falta}</p>}
                    <p className="mt-2 text-[12px] text-smn-gris-500">Es una sugerencia. El dictamen lo decides tú.</p>
                  </div>
                ) : <p className="text-[13px] text-smn-gris-500">Corre en el servidor con la IA local; no sale nada a internet.</p>}
              </div>
              <div className={`${TARJETA} grid gap-3`}>
                <h2 className="font-semibold">Tu dictamen</h2>
                {Object.entries(DICTAMEN).map(([valor, texto]) => (
                  <label key={valor} className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-[15px] ${dictamen === valor ? "border-smn-naranja" : "border-smn-gris-100"}`}>
                    <input type="radio" name="dictamen" checked={dictamen === valor} onChange={() => setDictamen(valor)} /> {texto}
                  </label>
                ))}
                <Texto etiqueta="Motivo" valor={motivo} cambiar={setMotivo} filas={4} />
                <p className="text-[13px] text-smn-gris-500">Marca a la izquierda la evidencia que lo respalda (al menos una).</p>
                <Boton onClick={dictaminar} cargando={ocupado === "dictaminar"} disabled={!dictamen || motivo.trim().length < 10 || respaldo.length === 0}>Guardar dictamen</Boton>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
