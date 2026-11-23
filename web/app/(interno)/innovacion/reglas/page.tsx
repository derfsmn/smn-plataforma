"use client";
// Reglas de Vidanat: catálogo por área con su versión vigente y alta de reglas nuevas (en borrador).
// Las reglas «apenas se están pensando» (Diego, 2026-11-21): el módulo funciona sin reglas publicadas.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence } from "motion/react";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo, Encabezado, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { ESTADO_REGLA, MODO_REGLA, P, RUTA, SEVERIDAD, type CatalogoReglas, type FilaRegla, type Regla } from "@/lib/innovacion";
import { MenuModulo, SinAcceso, TARJETA, Texto, Vacio } from "../comunes";

export default function Reglas() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [filas, setFilas] = useState<FilaRegla[] | null>(null);
  const [cat, setCat] = useState<CatalogoReglas | null>(null);
  const [area, setArea] = useState("");
  const [alta, setAlta] = useState(false);
  useEffect(() => {
    if (!puede(P.ver)) return;
    api<FilaRegla[]>(`${RUTA}/reglas`).then(setFilas).catch((e) => avisar(mensajeDe(e), "info"));
    api<CatalogoReglas>(`${RUTA}/reglas-catalogo`).then(setCat).catch(() => {});
  }, [puede, avisar]);

  if (!puede(P.ver)) return <SinAcceso />;
  const visibles = (filas ?? []).filter((r) => !area || r.area === area);
  return (
    <>
      <Encabezado
        titulo="Reglas"
        descripcion="Lo que debe cumplir un producto nuevo, con su fuente y vigencia. Quien propone una regla no la publica: la publica otra persona de su área."
        accion={puede(P.reglaProponer) && cat && <Boton onClick={() => setAlta(true)}><Plus className="h-4 w-4" /> Nueva regla</Boton>}
      />
      <MenuModulo />
      {cat && (
        <div className="mb-4 flex flex-wrap gap-2">
          {[["", "Todas"], ...Object.entries(cat.areas)].map(([k, t]) => (
            <button key={k} onClick={() => setArea(k)} className={`rounded-full px-3.5 py-1.5 text-sm font-semibold ${area === k ? "bg-tinta text-superficie" : "bg-smn-gris-100 text-smn-gris-700"}`}>{t}</button>
          ))}
        </div>
      )}
      {!filas ? (
        <Esqueleto className="h-48" />
      ) : visibles.length === 0 ? (
        <Vacio>
          Todavía no hay reglas{area ? " en esta área" : ""}. Los expedientes se trabajan igual: su evaluación dirá «sin reglas que apliquen» hasta que se publique la primera.
        </Vacio>
      ) : (
        <div className={`${TARJETA} divide-y divide-smn-gris-100 p-0`}>
          {visibles.map((r) => (
            <Link key={r.id} href={`/innovacion/reglas/${r.id}`} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 hover:bg-smn-gris-50">
              <span>
                <span className="block font-medium"><span className="font-mono text-[13px] text-smn-gris-500">{r.codigo}</span> {r.nombre}</span>
                <span className="block text-[13px] text-smn-gris-500">
                  {r.area_nombre} · {SEVERIDAD[r.severidad ?? ""] ?? "—"} · {r.modo ?? "—"} · {r.vigente ? `vigente v${r.vigente}` : "sin versión vigente"}
                </span>
              </span>
              {r.estado && <Insignia className={ESTADO_REGLA[r.estado]?.clase ?? ""}>v{r.ultima} {ESTADO_REGLA[r.estado]?.texto ?? r.estado}</Insignia>}
            </Link>
          ))}
        </div>
      )}
      <AnimatePresence>{alta && cat && <Alta cat={cat} cerrar={() => setAlta(false)} />}</AnimatePresence>
    </>
  );
}

function Alta({ cat, cerrar }: { cat: CatalogoReglas; cerrar: () => void }) {
  const avisar = useAvisos();
  const router = useRouter();
  const [area, setArea] = useState(Object.keys(cat.areas)[0]);
  const [nombre, setNombre] = useState("");
  const [proposito, setProposito] = useState("");
  const [modo, setModo] = useState("manual");
  const [severidad, setSeveridad] = useState("mayor");
  const [enviando, setEnviando] = useState(false);
  const crear = async () => {
    setEnviando(true);
    try {
      // Una regla automática necesita su condición: se crea con una de ejemplo para editarla en el borrador.
      const r = await api<Regla>(`${RUTA}/reglas`, {
        cuerpo: { area, nombre: nombre.trim(), proposito: proposito.trim(), modo, severidad, condicion: modo === "automatica" ? { existe: "porcion" } : null },
      });
      router.push(`/innovacion/reglas/${r.id}`);
    } catch (e) {
      avisar(mensajeDe(e), "info");
      setEnviando(false);
    }
  };
  return (
    <Modal titulo="Nueva regla" cerrar={cerrar} ancho="max-w-lg">
      <div className="grid gap-3">
        <Selector etiqueta="Área" valor={area} cambiar={setArea} opciones={Object.entries(cat.areas).map(([valor, texto]) => ({ valor, texto }))} />
        <Campo etiqueta="Nombre corto" value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Magnesio elemental declarado" />
        <Texto etiqueta="Qué pide la regla, en palabras" valor={proposito} cambiar={setProposito} filas={3} />
        <Selector etiqueta="Cómo se revisa" valor={modo} cambiar={setModo} opciones={Object.entries(MODO_REGLA).map(([valor, texto]) => ({ valor, texto }))} />
        <Selector etiqueta="Severidad" valor={severidad} cambiar={setSeveridad} opciones={Object.entries(SEVERIDAD).map(([valor, texto]) => ({ valor, texto }))} />
        <p className="text-[13px] text-smn-gris-500">Queda en borrador con código automático. Después agregas su fuente, alcance y vigencia, y la envías a revisión.</p>
        <Boton onClick={crear} cargando={enviando} disabled={nombre.trim().length < 3 || proposito.trim().length < 5}>Crear borrador</Boton>
      </div>
    </Modal>
  );
}
