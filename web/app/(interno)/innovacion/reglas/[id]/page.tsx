"use client";
// Una regla: sus versiones, el editor del borrador (alcance, condición, fuente, vigencia), «Probar» contra los
// expedientes abiertos sin guardar nada, y el flujo borrador → en revisión → publicada → sustituida o retirada.

import { useParams } from "next/navigation";
import { FlaskConical, Send, Undo2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo, Encabezado, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import {
  ESTADO_REGLA, MODO_REGLA, P, RUTA, SEVERIDAD, fecha, postConDetalle,
  type CatalogoReglas, type FilaRecurso, type FilaRegla, type Regla, type VersionRegla,
} from "@/lib/innovacion";
import { AREA, ChipResultado, ETIQUETA, MenuModulo, SinAcceso, TARJETA, Texto, Volver } from "../../comunes";

const EJEMPLOS: { texto: string; condicion: unknown }[] = [
  { texto: "Que exista un dato", condicion: { existe: "porcion" } },
  { texto: "Rango de cantidad por ingrediente", condicion: { para_cada: { lista: "ingredientes", donde: { igual: ["nombre", "Magnesio"] } }, rango: { campo: "cantidad_activa", min: 50, max: 350, unidad: "mg" } } },
  { texto: "Compuesto y activo coherentes", condicion: { para_cada: { lista: "ingredientes", donde: { igual: ["en_compuesto", true] } }, todas: [{ existe: "cantidad_compuesto" }, { existe: "cantidad_activa" }, { comparar: ["cantidad_activa", "<=", "cantidad_compuesto"], convertir_a: "mg" }] } },
  { texto: "Documento vigente", condicion: { documento: { tipo: "certificado", vigente: true } } },
  { texto: "Frases prohibidas en la etiqueta", condicion: { texto_no_contiene: ["declaraciones", ["cura", "previene", "elimina"]] } },
];
const ROLES = [
  ["innovacion_regulatorio", "Regulatorio"], ["innovacion_calidad", "Calidad"], ["innovacion_formulacion", "Formulación"],
  ["innovacion_lider", "Líder de I+D"], ["innovacion_marketing", "Marketing"],
];

type Borrador = {
  proposito: string; modo: string; severidad: string; si_falta: string; admite_excepcion: boolean; exige_fuente_vigente: boolean;
  sustituye_a: string; fuente_version_id: number | null; fuente_titulo: string; fuente_ubicacion: string; vigente_desde: string; vigente_hasta: string;
  rol_revisor: string; plazo_dias: number; campos_relevantes: string; condicion: string; alcance: Record<string, string>;
};
const aBorrador = (v: VersionRegla): Borrador => ({
  proposito: v.proposito, modo: v.modo, severidad: v.severidad, si_falta: v.si_falta, admite_excepcion: v.admite_excepcion,
  exige_fuente_vigente: v.exige_fuente_vigente, sustituye_a: v.sustituye_a ?? "", fuente_version_id: v.fuente?.version_id ?? null,
  fuente_titulo: v.fuente ? `${v.fuente.titulo} v${v.fuente.version}` : "", fuente_ubicacion: v.fuente_ubicacion ?? "",
  vigente_desde: v.vigente_desde ?? "", vigente_hasta: v.vigente_hasta ?? "", rol_revisor: v.rol_revisor ?? "", plazo_dias: v.plazo_dias,
  campos_relevantes: v.campos_relevantes.join(", "), condicion: v.condicion ? JSON.stringify(v.condicion, null, 2) : "",
  alcance: Object.fromEntries(Object.entries(v.alcance).map(([k, x]) => [k, Array.isArray(x) ? x.join(", ") : String(x)])),
});

export default function PaginaRegla() {
  const { id } = useParams<{ id: string }>();
  const { puede, yo } = useSesion();
  const avisar = useAvisos();
  const [r, setR] = useState<Regla | null>(null);
  const [cat, setCat] = useState<CatalogoReglas | null>(null);
  const [otras, setOtras] = useState<FilaRegla[]>([]);
  const [b, setB] = useState<Borrador | null>(null);
  const [prueba, setPrueba] = useState<{ folio: string; nombre: string; resultado: string; motivo: string; faltantes?: string[] }[] | null>(null);
  const [aviso, setAviso] = useState<string[] | null>(null);
  const [retiro, setRetiro] = useState("");
  const [ocupado, setOcupado] = useState<string | null>(null);
  const cargar = useCallback(async () => {
    try {
      const x = await api<Regla>(`${RUTA}/reglas/${id}`);
      setR(x);
      const borrador = x.versiones.find((v) => v.estado === "borrador");
      setB(borrador ? aBorrador(borrador) : null);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  }, [id, avisar]);
  useEffect(() => {
    if (!puede(P.ver)) return;
    cargar();
    api<CatalogoReglas>(`${RUTA}/reglas-catalogo`).then(setCat).catch(() => {});
    api<FilaRegla[]>(`${RUTA}/reglas`).then(setOtras).catch(() => {});
  }, [puede, cargar]);

  if (!puede(P.ver)) return <SinAcceso />;
  if (!r || !cat) return <Esqueleto className="h-64" />;
  const borrador = r.versiones.find((v) => v.estado === "borrador");
  const enRevision = r.versiones.find((v) => v.estado === "en_revision");
  const publicada = r.versiones.find((v) => v.estado === "publicada");
  const esAutor = (v: VersionRegla) => v.autor_id === yo.usuario.id;

  const cuerpo = () => {
    let condicion = null;
    if (b!.modo === "automatica") {
      try {
        condicion = JSON.parse(b!.condicion || "null");
      } catch {
        throw new Error("La condición no es un JSON válido.");
      }
    }
    return {
      proposito: b!.proposito.trim(), modo: b!.modo, severidad: b!.severidad, si_falta: b!.si_falta, admite_excepcion: b!.admite_excepcion,
      exige_fuente_vigente: b!.exige_fuente_vigente, sustituye_a: b!.sustituye_a || null, fuente_version_id: b!.fuente_version_id,
      fuente_ubicacion: b!.fuente_ubicacion.trim() || null, vigente_desde: b!.vigente_desde || null, vigente_hasta: b!.vigente_hasta || null,
      rol_revisor: b!.rol_revisor || null, plazo_dias: b!.plazo_dias, condicion,
      campos_relevantes: b!.campos_relevantes.split(",").map((x) => x.trim()).filter(Boolean),
      alcance: Object.fromEntries(Object.entries(b!.alcance).map(([k, x]) => [k, x.split(",").map((y) => y.trim()).filter(Boolean)]).filter(([, x]) => (x as string[]).length)),
    };
  };
  const accion = async (nombre: string, f: () => Promise<unknown>, exito?: string) => {
    setOcupado(nombre);
    setAviso(null);
    try {
      await f();
      if (exito) avisar(exito, "exito");
      await cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };
  const guardar = () => accion("guardar", () => api(`${RUTA}/reglas/${r.id}/versiones/${borrador!.numero}`, { metodo: "PUT", cuerpo: cuerpo() }), "Borrador guardado.");
  const nuevaVersion = () => {
    const base = publicada ?? r.versiones[0];
    return accion("nueva", () => api(`${RUTA}/reglas/${r.id}/versiones`, { cuerpo: { ...cuerpoDe(base) } }), "Borrador de versión nueva creado.");
  };
  const probar = async (numero: number) => {
    setOcupado("probar");
    try {
      setPrueba(await api(`${RUTA}/reglas/${r.id}/versiones/${numero}/probar`, { metodo: "POST", cuerpo: {} }));
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };
  const publicar = async (numero: number) => {
    setOcupado("publicar");
    const x = await postConDetalle<{ reevaluados: number }>(`${RUTA}/reglas/${r.id}/versiones/${numero}/publicar`, {});
    setOcupado(null);
    if (!x.ok) {
      setAviso([x.mensaje, ...((x.detalle?.choques as string[]) ?? [])]);
      return;
    }
    avisar(`Publicada. Se volvieron a evaluar ${x.datos.reevaluados} expedientes.`, "exito");
    await cargar();
  };

  return (
    <>
      <Volver href="/innovacion/reglas" texto="Reglas" />
      <Encabezado titulo={`${r.codigo} · ${r.nombre}`} descripcion={`${r.area_nombre} · ${r.vigente ? `vigente la versión ${r.vigente}` : "sin versión vigente"}`}
        accion={r.puede_proponer && !borrador && !enRevision && <Boton variante="secundario" onClick={nuevaVersion} cargando={ocupado === "nueva"}>Proponer versión nueva</Boton>} />
      <MenuModulo />
      {aviso && (
        <div className={`${TARJETA} mb-5 border-red-300 text-sm dark:border-red-500/40`}>
          {aviso.map((t, i) => <p key={i} className={i === 0 ? "font-semibold" : ""}>{t}</p>)}
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        <div className="grid content-start gap-5">
          {borrador && b && esAutor(borrador) ? (
            <Editor b={b} setB={setB} cat={cat} otras={otras.filter((o) => o.id !== r.id)} guardar={guardar} guardando={ocupado === "guardar"}
              enviar={() => accion("enviar", async () => { await api(`${RUTA}/reglas/${r.id}/versiones/${borrador.numero}`, { metodo: "PUT", cuerpo: cuerpo() }); await api(`${RUTA}/reglas/${r.id}/versiones/${borrador.numero}/enviar`, { metodo: "POST", cuerpo: {} }); }, "Enviada a revisión. La publica otra persona de su área.")}
              probar={() => accion("probar", async () => { await api(`${RUTA}/reglas/${r.id}/versiones/${borrador.numero}`, { metodo: "PUT", cuerpo: cuerpo() }); await probar(borrador.numero); })}
              ocupado={ocupado} />
          ) : (
            r.versiones.slice(0, 1).map((v) => <VistaVersion key={v.numero} v={v} />)
          )}
          {enRevision && (
            <div className={`${TARJETA} grid gap-3`}>
              <h2 className="font-semibold">Versión {enRevision.numero} en revisión · propuso {enRevision.autor}</h2>
              {borrador === undefined && r.versiones[0].numero !== enRevision.numero && <VistaVersion v={enRevision} />}
              <div className="flex flex-wrap gap-2">
                <Boton variante="secundario" onClick={() => probar(enRevision.numero)} cargando={ocupado === "probar"}><FlaskConical className="h-4 w-4" /> Probar</Boton>
                {r.puede_publicar && !esAutor(enRevision) && (
                  <>
                    <Boton onClick={() => publicar(enRevision.numero)} cargando={ocupado === "publicar"}><Send className="h-4 w-4" /> Publicar</Boton>
                    <Boton variante="fantasma" onClick={() => accion("regresar", () => api(`${RUTA}/reglas/${r.id}/versiones/${enRevision.numero}/regresar`, { metodo: "POST", cuerpo: {} }), "Regresada a su autor.")}>
                      <Undo2 className="h-4 w-4" /> Regresar al autor
                    </Boton>
                  </>
                )}
              </div>
              {esAutor(enRevision) && <p className="text-[13px] text-smn-gris-500">Tú la propusiste: la publica otra persona de su área.</p>}
            </div>
          )}
          {prueba && (
            <div className={TARJETA}>
              <h2 className="mb-2 font-semibold">Prueba contra los expedientes abiertos (no se guardó nada)</h2>
              {prueba.length === 0 ? <p className="text-sm text-smn-gris-500">No hay expedientes abiertos con ficha.</p> : (
                <ul className="divide-y divide-smn-gris-100 text-sm">
                  {prueba.map((p) => (
                    <li key={p.folio} className="flex flex-wrap items-start gap-2 py-2"><ChipResultado valor={p.resultado} /> <b>{p.folio}</b> {p.nombre} · {p.motivo}{p.faltantes?.length ? ` · falta ${p.faltantes.join(", ")}` : ""}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {publicada && r.puede_publicar && (
            <div className={`${TARJETA} grid gap-2`}>
              <h2 className="font-semibold">Retirar la versión {publicada.numero}</h2>
              <Campo etiqueta="Motivo" value={retiro} onChange={(e) => setRetiro(e.target.value)} />
              <Boton variante="secundario" disabled={retiro.trim().length < 5} cargando={ocupado === "retirar"}
                onClick={() => accion("retirar", () => api(`${RUTA}/reglas/${r.id}/versiones/${publicada.numero}/retirar`, { cuerpo: { motivo: retiro.trim() } }), "Retirada. Se volvieron a evaluar los expedientes abiertos.")}>
                Retirar
              </Boton>
            </div>
          )}
        </div>
        <div className={TARJETA}>
          <h2 className="mb-2 font-semibold">Versiones</h2>
          <ul className="grid gap-2 text-sm">
            {r.versiones.map((v) => (
              <li key={v.numero} className="border-t border-smn-gris-100 pt-2 first:border-0 first:pt-0">
                <span className="flex items-center justify-between gap-2"><b>v{v.numero}</b><Insignia className={ESTADO_REGLA[v.estado]?.clase ?? ""}>{ESTADO_REGLA[v.estado]?.texto ?? v.estado}</Insignia></span>
                <span className="block text-[13px] text-smn-gris-500">
                  propuso {v.autor}{v.aprobador ? ` · publicó ${v.aprobador}` : ""} · {v.vigente_desde ? `${fecha(v.vigente_desde)} a ${v.vigente_hasta ? fecha(v.vigente_hasta) : "sin fin"}` : "sin vigencia"}
                </span>
                {v.motivo_retiro && <span className="block text-[13px]">Retirada: {v.motivo_retiro}</span>}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}

function cuerpoDe(v: VersionRegla) {
  return {
    proposito: v.proposito, modo: v.modo, severidad: v.severidad, si_falta: v.si_falta, admite_excepcion: v.admite_excepcion,
    exige_fuente_vigente: v.exige_fuente_vigente, sustituye_a: v.sustituye_a, fuente_version_id: v.fuente?.version_id ?? null,
    fuente_ubicacion: v.fuente_ubicacion, vigente_desde: null, vigente_hasta: null, rol_revisor: v.rol_revisor, plazo_dias: v.plazo_dias,
    campos_relevantes: v.campos_relevantes, condicion: v.condicion, alcance: v.alcance,
  };
}

function VistaVersion({ v }: { v: VersionRegla }) {
  return (
    <div className={TARJETA}>
      <h2 className="mb-2 font-semibold">Versión {v.numero}</h2>
      <dl className="grid gap-2 text-sm">
        <div><dt className="text-smn-gris-500">Qué pide</dt><dd>{v.proposito}</dd></div>
        <div><dt className="text-smn-gris-500">Cómo se revisa</dt><dd>{MODO_REGLA[v.modo]}{v.rol_revisor ? ` · revisa ${v.rol_revisor}` : ""}</dd></div>
        <div><dt className="text-smn-gris-500">Severidad</dt><dd>{SEVERIDAD[v.severidad]} · si falta un dato: {v.si_falta === "incumple" ? "no cumple" : "pendiente"}{v.admite_excepcion ? " · admite excepción" : ""}</dd></div>
        {Object.keys(v.alcance).length > 0 && <div><dt className="text-smn-gris-500">Alcance</dt><dd>{Object.entries(v.alcance).map(([k, x]) => `${k.replace("_", " ")}: ${Array.isArray(x) ? x.join(", ") : x}`).join(" · ")}</dd></div>}
        {v.fuente && <div><dt className="text-smn-gris-500">Fuente</dt><dd>{v.fuente.titulo} v{v.fuente.version}{v.fuente_ubicacion ? ` · ${v.fuente_ubicacion}` : ""}</dd></div>}
        {v.condicion && <div><dt className="text-smn-gris-500">Condición</dt><dd><pre className="overflow-x-auto rounded-lg bg-smn-gris-50 p-2 text-[12px]">{JSON.stringify(v.condicion, null, 2)}</pre></dd></div>}
      </dl>
    </div>
  );
}

function Editor({ b, setB, cat, otras, guardar, guardando, enviar, probar, ocupado }: {
  b: Borrador; setB: (b: Borrador) => void; cat: CatalogoReglas; otras: FilaRegla[]; guardar: () => void; guardando: boolean;
  enviar: () => void; probar: () => void; ocupado: string | null;
}) {
  const [q, setQ] = useState("");
  const [fuentes, setFuentes] = useState<FilaRecurso[]>([]);
  const poner = <K extends keyof Borrador>(k: K, v: Borrador[K]) => setB({ ...b, [k]: v });
  useEffect(() => {
    if (q.trim().length < 2) return setFuentes([]);
    const t = setTimeout(() => api<{ recursos: FilaRecurso[] }>(`${RUTA}/recursos?estado=revisado&q=${encodeURIComponent(q.trim())}`).then((x) => setFuentes(x.recursos.slice(0, 8))).catch(() => {}), 300);
    return () => clearTimeout(t);
  }, [q]);
  const elegirFuente = async (f: FilaRecurso) => {
    const d = await api<{ versiones: { version_id: number; numero: number; estado: string }[] }>(`${RUTA}/recursos/${f.id}`);
    const v = d.versiones.find((x) => x.estado === "revisado");
    if (v) setB({ ...b, fuente_version_id: v.version_id, fuente_titulo: `${f.titulo} v${v.numero}` });
    setQ("");
  };
  return (
    <div className={`${TARJETA} grid gap-4`}>
      <h2 className="font-semibold">Borrador</h2>
      <Texto etiqueta="Qué pide la regla" valor={b.proposito} cambiar={(v) => poner("proposito", v)} filas={2} />
      <div className="grid gap-3 sm:grid-cols-3">
        <Selector etiqueta="Cómo se revisa" valor={b.modo} cambiar={(v) => poner("modo", v)} opciones={Object.entries(MODO_REGLA).map(([valor, texto]) => ({ valor, texto: texto.split(" (")[0] }))} />
        <Selector etiqueta="Severidad" valor={b.severidad} cambiar={(v) => poner("severidad", v)} opciones={Object.entries(SEVERIDAD).map(([valor, texto]) => ({ valor, texto }))} />
        <Selector etiqueta="Si falta un dato" valor={b.si_falta} cambiar={(v) => poner("si_falta", v)} opciones={[{ valor: "pendiente", texto: "Queda pendiente" }, { valor: "incumple", texto: "No cumple" }]} />
      </div>
      {b.modo === "automatica" ? (
        <div>
          <span className={ETIQUETA}>Condición (la evalúa el motor, sin IA)</span>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {EJEMPLOS.map((x) => (
              <button key={x.texto} type="button" onClick={() => poner("condicion", JSON.stringify(x.condicion, null, 2))} className="rounded-full bg-smn-gris-100 px-3 py-1 text-[12px] font-semibold text-smn-gris-700">{x.texto}</button>
            ))}
          </div>
          <textarea rows={10} value={b.condicion} onChange={(e) => poner("condicion", e.target.value)} className={`${AREA} font-mono text-[13px]`} spellCheck={false} />
          <p className="mt-1 text-[13px] text-smn-gris-500">Operadores: {cat.operadores.join(", ")}. Unidades: {cat.unidades.join(", ")}.</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <Selector etiqueta="Quién dictamina" valor={b.rol_revisor} cambiar={(v) => poner("rol_revisor", v)} opciones={[{ valor: "", texto: "Elige un rol" }, ...ROLES.map(([valor, texto]) => ({ valor, texto }))]} />
          <Campo etiqueta="Días para dictaminar" type="number" min={1} max={60} value={b.plazo_dias} onChange={(e) => poner("plazo_dias", Number(e.target.value) || 5)} />
          <div className="sm:col-span-2"><Campo etiqueta="Datos que, si cambian, piden dictamen nuevo (separados por coma)" value={b.campos_relevantes} onChange={(e) => poner("campos_relevantes", e.target.value)} placeholder="declaraciones, beneficio" /></div>
        </div>
      )}
      <div>
        <span className={ETIQUETA}>Alcance (vacío = aplica a todos; varios valores separados por coma)</span>
        <div className="grid gap-2 sm:grid-cols-2">
          {cat.alcance.filter((k) => k !== "etapa_destino").map((k) => (
            <Campo key={k} etiqueta={k.replace("_", " ")} value={b.alcance[k] ?? ""} onChange={(e) => setB({ ...b, alcance: { ...b.alcance, [k]: e.target.value } })} />
          ))}
          <Selector etiqueta="Se exige para pasar a" valor={b.alcance.etapa_destino ?? ""} cambiar={(v) => setB({ ...b, alcance: { ...b.alcance, etapa_destino: v } })}
            opciones={[{ valor: "", texto: "Cualquier etapa" }, { valor: "filtro", texto: "Filtro" }, { valor: "desarrollo", texto: "Desarrollo" }, { valor: "salida_comercial", texto: "Salida comercial" }]} />
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <span className={ETIQUETA}>Fuente revisada que la respalda</span>
          {b.fuente_version_id ? (
            <p className="text-sm">{b.fuente_titulo} <button className="ml-2 font-semibold text-smn-naranja" onClick={() => setB({ ...b, fuente_version_id: null, fuente_titulo: "" })}>Cambiar</button></p>
          ) : (
            <>
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Busca la fuente por título o DOI" className={AREA} />
              {fuentes.map((f) => <button key={f.id} onClick={() => elegirFuente(f)} className="mt-1 block w-full rounded-lg px-2 py-1.5 text-left text-sm hover:bg-smn-gris-50">{f.titulo}</button>)}
            </>
          )}
        </div>
        <div className="sm:col-span-2"><Campo etiqueta="Dónde lo dice (artículo, página, tabla)" value={b.fuente_ubicacion} onChange={(e) => poner("fuente_ubicacion", e.target.value)} /></div>
        <Campo etiqueta="Vigente desde" type="date" value={b.vigente_desde} onChange={(e) => poner("vigente_desde", e.target.value)} />
        <Campo etiqueta="Vigente hasta (opcional)" type="date" value={b.vigente_hasta} onChange={(e) => poner("vigente_hasta", e.target.value)} />
        <Selector etiqueta="Sustituye a" valor={b.sustituye_a} cambiar={(v) => poner("sustituye_a", v)} opciones={[{ valor: "", texto: "Ninguna" }, ...otras.map((o) => ({ valor: o.codigo, texto: `${o.codigo} ${o.nombre}` }))]} />
        <div className="grid content-end gap-1 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={b.admite_excepcion} onChange={(e) => poner("admite_excepcion", e.target.checked)} /> Admite excepción</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={b.exige_fuente_vigente} onChange={(e) => poner("exige_fuente_vigente", e.target.checked)} /> Exige que su fuente siga vigente</label>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Boton variante="secundario" onClick={guardar} cargando={guardando}>Guardar borrador</Boton>
        <Boton variante="secundario" onClick={probar} cargando={ocupado === "probar"}><FlaskConical className="h-4 w-4" /> Probar</Boton>
        <Boton onClick={enviar} cargando={ocupado === "enviar"}><Send className="h-4 w-4" /> Enviar a revisión</Boton>
      </div>
    </div>
  );
}
