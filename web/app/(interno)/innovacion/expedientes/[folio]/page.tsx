"use client";
// Expediente de un producto nuevo: etapas, reglas (última evaluación y compuerta), composición (ficha y fórmula),
// evidencia citada, mercado y pendientes, historial (evaluaciones, decisiones, excepciones) y decisión del Filtro.

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Check, FileDown, Play, Send } from "lucide-react";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Encabezado, Esqueleto, Insignia } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { ESTADO_EXP, ETAPAS, P, RUTA, descargar, postConDetalle, type Expediente } from "@/lib/innovacion";
import { MenuModulo, SinAcceso, Volver } from "../../comunes";
import { Composicion } from "./composicion";
import { EvidenciaCitada } from "./evidencia";
import { Filtro } from "./filtro";
import { Historial } from "./historial";
import { Mercado } from "./mercado";
import { Reglas } from "./reglas";

const PESTANAS = [
  { valor: "reglas", texto: "Reglas" },
  { valor: "composicion", texto: "Composición" },
  { valor: "evidencia", texto: "Evidencia" },
  { valor: "mercado", texto: "Mercado y pendientes" },
  { valor: "historial", texto: "Historial" },
  { valor: "filtro", texto: "Filtro" },
] as const;
type Pestana = (typeof PESTANAS)[number]["valor"];
const LINEA = ["investigacion", "filtro", "desarrollo", "salida_comercial", "validacion"];

export default function Pagina() {
  return (
    <Suspense fallback={<Esqueleto className="h-64" />}>
      <DetalleExpediente />
    </Suspense>
  );
}

function DetalleExpediente() {
  const { folio } = useParams<{ folio: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [e, setE] = useState<Expediente | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const pestana = (params.get("vista") as Pestana) || "reglas";
  const cargar = useCallback(
    () => api<Expediente>(`${RUTA}/expedientes/${folio}`).then(setE).catch((x) => avisar(mensajeDe(x), "info")),
    [folio, avisar],
  );
  useEffect(() => {
    if (puede(P.expVer)) cargar();
  }, [puede, cargar]);

  if (!puede(P.expVer)) return <SinAcceso />;
  if (!e) return <Esqueleto className="h-64" />;
  const ir = (v: Pestana) => router.replace(`/innovacion/expedientes/${folio}${v === "reglas" ? "" : `?vista=${v}`}`);

  const evaluar = async () => {
    setOcupado("evaluar");
    try {
      await api(`${RUTA}/expedientes/${folio}/evaluaciones`, { metodo: "POST", cuerpo: {} });
      await cargar();
      avisar("Evaluación nueva guardada.", "exito");
    } catch (x) {
      avisar(mensajeDe(x), "info");
    } finally {
      setOcupado(null);
    }
  };
  const enviar = async () => {
    setOcupado("enviar");
    const r = await postConDetalle(`${RUTA}/expedientes/${folio}/enviar`, { etapa: e.siguiente_etapa });
    setOcupado(null);
    if (!r.ok) return avisar(r.mensaje, "info");
    avisar(`Enviado a ${ETAPAS[e.siguiente_etapa]}.`, "exito");
    await cargar();
  };
  const pdf = () => {
    setOcupado("pdf");
    descargar(`${RUTA}/expedientes/${folio}/pdf`, `${folio}.pdf`)
      .catch((x) => avisar(mensajeDe(x), "info"))
      .finally(() => setOcupado(null));
  };

  // Del Filtro a desarrollo lo decide un directivo en la pestaña «Filtro», no con «Enviar».
  const puedeEnviar = e.puede.editar && e.estado === "activo" && e.etapa !== "filtro" && e.etapa !== e.siguiente_etapa;
  return (
    <>
      <Volver href="/innovacion/expedientes" texto="Expedientes" />
      <Encabezado
        titulo={e.nombre}
        descripcion={`${e.folio} · ${e.categoria_comercial ?? "sin categoría"} · ${e.jurisdiccion} · responsable ${e.responsable ?? "—"}`}
        accion={
          <div className="flex flex-wrap gap-2">
            {e.puede.evaluar && <Boton variante="secundario" onClick={evaluar} cargando={ocupado === "evaluar"}><Play className="h-4 w-4" /> Evaluar ahora</Boton>}
            {e.puede.exportar && <Boton variante="secundario" onClick={pdf} cargando={ocupado === "pdf"}><FileDown className="h-4 w-4" /> PDF</Boton>}
            {puedeEnviar && (
              <Boton onClick={enviar} cargando={ocupado === "enviar"} disabled={!e.compuerta.puede_avanzar}
                title={e.compuerta.puede_avanzar ? undefined : e.compuerta.motivo ?? undefined}>
                <Send className="h-4 w-4" /> Enviar a {ETAPAS[e.siguiente_etapa]}
              </Boton>
            )}
          </div>
        }
      />
      <MenuModulo />
      <ol className="mb-5 flex flex-wrap items-center gap-1.5 text-[13px]" aria-label="Etapas">
        {LINEA.map((x, i) => {
          const pos = LINEA.indexOf(e.etapa);
          const hecho = i < pos;
          const actual = i === pos;
          return (
            <li key={x} className="flex items-center gap-1.5">
              <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 font-semibold ${actual ? "bg-[var(--resalte)] text-[var(--resalte-tinta)]" : hecho ? "bg-smn-gris-100 text-smn-gris-700" : "text-smn-gris-500"}`}>
                {hecho && <Check className="h-3 w-3" />} {ETAPAS[x]}
              </span>
              {i < LINEA.length - 1 && <span className="text-smn-gris-300">›</span>}
            </li>
          );
        })}
        {e.estado !== "activo" && <Insignia className="ml-2 bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">{ESTADO_EXP[e.estado]}</Insignia>}
      </ol>
      <div className="mb-5 flex flex-wrap gap-2">
        {PESTANAS.map((x) => (
          <button key={x.valor} onClick={() => ir(x.valor)}
            className={`rounded-full px-4 py-2 text-sm font-semibold transition ${pestana === x.valor ? "bg-tinta text-superficie" : "bg-smn-gris-100 text-smn-gris-700 hover:bg-smn-gris-300/50"}`}>
            {x.texto}
            {x.valor === "filtro" && e.etapa === "filtro" && e.estado === "activo" && <span className="ml-1.5 inline-block h-2 w-2 rounded-full bg-smn-naranja" aria-label="espera decisión" />}
          </button>
        ))}
      </div>
      {pestana === "reglas" && <Reglas e={e} alCambiar={cargar} />}
      {pestana === "composicion" && <Composicion e={e} alCambiar={cargar} />}
      {pestana === "evidencia" && <EvidenciaCitada e={e} alCambiar={cargar} />}
      {pestana === "mercado" && <Mercado e={e} alCambiar={cargar} />}
      {pestana === "historial" && <Historial e={e} alCambiar={cargar} />}
      {pestana === "filtro" && <Filtro e={e} alCambiar={cargar} />}
    </>
  );
}
