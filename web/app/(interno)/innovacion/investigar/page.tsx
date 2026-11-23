"use client";
// Investigar en internet: «actuar como investigador científico, químico y experto» (Diego, 2026-11-21).
// Paso 1 propone preguntas y términos; nada sale a internet hasta confirmar. Solo términos generales, nunca la fórmula.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Telescope } from "lucide-react";
import { useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo, Encabezado, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { api, haceCuanto, mensajeDe } from "@/lib/api";
import { ESTADO_INV, P, RUTA, type FilaExpediente, type FilaInvestigacion } from "@/lib/innovacion";
import { MenuModulo, SinAcceso, TARJETA, Vacio } from "../comunes";

export default function Investigar() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const router = useRouter();
  const [filas, setFilas] = useState<FilaInvestigacion[] | null>(null);
  const [expedientes, setExpedientes] = useState<FilaExpediente[]>([]);
  const [tema, setTema] = useState("");
  const [folio, setFolio] = useState("");
  const [enviando, setEnviando] = useState(false);
  useEffect(() => {
    if (!puede(P.investigar)) return;
    api<FilaInvestigacion[]>(`${RUTA}/investigaciones`).then(setFilas).catch((e) => avisar(mensajeDe(e), "info"));
    if (puede(P.expVer)) api<FilaExpediente[]>(`${RUTA}/expedientes`).then(setExpedientes).catch(() => {});
  }, [puede, avisar]);

  if (!puede(P.investigar)) return <SinAcceso texto="No tienes permiso para investigar en internet." />;
  const proponer = async () => {
    setEnviando(true);
    try {
      const r = await api<{ id: number }>(`${RUTA}/investigaciones`, { cuerpo: { tema: tema.trim(), folio: folio || null } });
      router.push(`/innovacion/investigar/${r.id}`);
    } catch (e) {
      avisar(mensajeDe(e), "info");
      setEnviando(false);
    }
  };
  return (
    <>
      <Encabezado titulo="Investigar en internet"
        descripcion="Busca en PubMed, Europe PMC, ClinicalTrials.gov, OpenAlex y Crossref (gratis), lee lo de acceso abierto y redacta un informe con citas. Lo que sirva entra a la base como pendiente de revisión." />
      <MenuModulo />
      <div className={`${TARJETA} grid gap-3`}>
        <Campo etiqueta="¿Qué quieres investigar?" value={tema} onChange={(e) => setTema(e.target.value)} placeholder="Bisglicinato de magnesio para sueño y relajación" />
        {expedientes.length > 0 && (
          <Selector etiqueta="Del expediente (toma sus ingredientes y forma, nunca la fórmula)" valor={folio} cambiar={setFolio}
            opciones={[{ valor: "", texto: "Ninguno" }, ...expedientes.map((e) => ({ valor: e.folio, texto: `${e.folio} · ${e.nombre}` }))]} />
        )}
        <Boton onClick={proponer} cargando={enviando} disabled={tema.trim().length < 3} className="justify-self-start"><Telescope className="h-4 w-4" /> Proponer preguntas</Boton>
        <p className="text-[13px] text-smn-gris-500">Todavía no sale nada a internet: primero revisas las preguntas y los términos.</p>
      </div>
      <div className="mt-5">
        {!filas ? <Esqueleto className="h-32" /> : filas.length === 0 ? <Vacio>Sin investigaciones todavía.</Vacio> : (
          <div className={`${TARJETA} divide-y divide-smn-gris-100 p-0`}>
            {filas.map((i) => (
              <Link key={i.id} href={`/innovacion/investigar/${i.id}`} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 hover:bg-smn-gris-50">
                <span>
                  <span className="block font-medium">{i.tema}</span>
                  <span className="block text-[13px] text-smn-gris-500">{i.folio ? `${i.folio} · ` : ""}{i.creado_por} · {haceCuanto(i.creado_en)}{i.costo_usd ? ` · US$${i.costo_usd.toFixed(2)}` : ""}</span>
                </span>
                <Insignia className={ESTADO_INV[i.estado]?.clase ?? ""}>{ESTADO_INV[i.estado]?.texto ?? i.estado}</Insignia>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
