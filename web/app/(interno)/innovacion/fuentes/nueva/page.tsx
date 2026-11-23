"use client";
// Cargar una fuente: enlace, archivos (hasta 10) o texto, con su clasificación y vínculos. La lectura, el OCR y los
// datos sugeridos por la IA local corren después; la persona los confirma en la ficha de la fuente.

import { useRouter } from "next/navigation";
import { CloudUpload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo, Encabezado, Selector } from "@/componentes/ui";
import { api, mensajeDe, tamanoLegible } from "@/lib/api";
import { CLASIFICACION, P, RUTA, TIPOS, enviarFuente, type FilaExpediente, type Ingrediente } from "@/lib/innovacion";
import { ETIQUETA, MenuModulo, SinAcceso, TARJETA, Texto, Volver } from "../../comunes";

const ACEPTA = ".pdf,.docx,.pptx,.xlsx,.txt,.png,.jpg,.jpeg,.webp";

export default function CargarFuente() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const router = useRouter();
  const entrada = useRef<HTMLInputElement>(null);
  const [archivos, setArchivos] = useState<File[]>([]);
  const [d, setD] = useState({ titulo: "", tipo: "articulo", clasificacion: "general", folio: "", url: "", doi: "", texto: "", vigente_desde: "", vigente_hasta: "" });
  const [elegidos, setElegidos] = useState<number[]>([]);
  const [categorias, setCategorias] = useState("");
  const [ingredientes, setIngredientes] = useState<Ingrediente[]>([]);
  const [expedientes, setExpedientes] = useState<FilaExpediente[]>([]);
  const [enviando, setEnviando] = useState(false);
  const poner = (k: keyof typeof d) => (v: string) => setD((x) => ({ ...x, [k]: v }));

  useEffect(() => {
    api<Ingrediente[]>(`${RUTA}/ingredientes`).then(setIngredientes).catch(() => {});
    if (puede(P.expVer)) api<FilaExpediente[]>(`${RUTA}/expedientes`).then(setExpedientes).catch(() => {});
  }, [puede]);

  if (!puede(P.cargar)) return <SinAcceso texto="No tienes permiso para cargar fuentes." />;

  const sumar = (lista: FileList | null) => {
    if (!lista) return;
    const nuevos = Array.from(lista).filter((f) => f.size <= 40 * 1024 * 1024);
    if (nuevos.length < lista.length) avisar("Un archivo pasa de 40 MB y no se agregó.", "info");
    setArchivos((a) => [...a, ...nuevos].slice(0, 10));
    if (!d.titulo && nuevos[0]) setD((x) => ({ ...x, titulo: nuevos[0].name.replace(/\.[^.]+$/, "") }));
    if (entrada.current) entrada.current.value = "";
  };

  const guardar = async () => {
    if (d.titulo.trim().length < 3) return avisar("Ponle un título a la fuente.", "info");
    if (!archivos.length && !d.url.trim() && !d.texto.trim()) return avisar("Pon un enlace, un archivo o el texto de la fuente.", "info");
    if (d.clasificacion === "formula" && !d.folio) return avisar("Una fuente de fórmula debe ser de un folio.", "info");
    setEnviando(true);
    try {
      const r = await enviarFuente<{ id: number }>(`${RUTA}/recursos`, {
        titulo: d.titulo.trim(),
        tipo: d.tipo,
        clasificacion: d.clasificacion,
        folio: d.folio || null,
        url: d.url.trim() || null,
        doi: d.doi.trim() || null,
        texto: d.texto.trim() || null,
        vigente_desde: d.vigente_desde || null,
        vigente_hasta: d.vigente_hasta || null,
        ingredientes: elegidos,
        categorias: categorias.split(",").map((c) => c.trim()).filter(Boolean),
      }, archivos);
      avisar("Fuente cargada. Se está leyendo; revisa los datos que sugiera la IA local.", "exito");
      router.push(`/innovacion/fuentes/${r.id}`);
    } catch (e) {
      avisar(mensajeDe(e), "info");
      setEnviando(false);
    }
  };

  const mios = expedientes.filter((e) => e.soy_del_equipo);
  return (
    <>
      <Volver href="/innovacion/fuentes" texto="Fuentes" />
      <Encabezado titulo="Cargar fuente" descripcion="Todo lo que se carga es comprado o propio: se guarda el archivo completo. Lo de fórmula se guarda cifrado." />
      <MenuModulo />
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div className={`${TARJETA} grid gap-4`}>
          <button
            type="button"
            onClick={() => entrada.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              sumar(e.dataTransfer.files);
            }}
            className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-smn-gris-300 px-4 py-8 text-center text-sm text-smn-gris-500 hover:border-smn-naranja"
          >
            <CloudUpload className="h-7 w-7 text-smn-naranja" />
            <span><b className="text-tinta">Arrastra o elige archivos</b> · PDF (también escaneado), Word, PowerPoint, Excel, texto o imágenes · hasta 10</span>
          </button>
          <input ref={entrada} type="file" multiple accept={ACEPTA} className="hidden" onChange={(e) => sumar(e.target.files)} />
          {archivos.length > 0 && (
            <ul className="grid gap-1.5">
              {archivos.map((a, i) => (
                <li key={`${a.name}-${i}`} className="flex items-center justify-between rounded-lg bg-smn-gris-50 px-3 py-2 text-sm">
                  <span>{a.name} <span className="text-smn-gris-500">· {tamanoLegible(a.size)}{i === 0 ? " · principal" : ""}</span></span>
                  <button type="button" aria-label={`Quitar ${a.name}`} onClick={() => setArchivos((x) => x.filter((_, j) => j !== i))}><X className="h-4 w-4" /></button>
                </li>
              ))}
            </ul>
          )}
          <Campo etiqueta="Título" value={d.titulo} onChange={(e) => poner("titulo")(e.target.value)} maxLength={500} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Selector etiqueta="Tipo de fuente" valor={d.tipo} cambiar={poner("tipo")} opciones={Object.entries(TIPOS).map(([valor, texto]) => ({ valor, texto }))} />
            <Campo etiqueta="DOI (si tiene)" value={d.doi} onChange={(e) => poner("doi")(e.target.value)} placeholder="10.1000/xyz123" />
          </div>
          <Campo etiqueta="Enlace (si tiene)" value={d.url} onChange={(e) => poner("url")(e.target.value)} placeholder="https://…" />
          <Texto etiqueta="Texto (si no hay archivo)" valor={d.texto} cambiar={poner("texto")} filas={5} ayuda="Pega aquí el texto de una nota o de una página. Usa # para los títulos de sección." />
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo etiqueta="Vigente desde (normas y guías)" type="date" value={d.vigente_desde} onChange={(e) => poner("vigente_desde")(e.target.value)} />
            <Campo etiqueta="Vigente hasta" type="date" value={d.vigente_hasta} onChange={(e) => poner("vigente_hasta")(e.target.value)} />
          </div>
        </div>

        <div className="grid content-start gap-5">
          <div className={`${TARJETA} grid gap-3`}>
            <span className={ETIQUETA}>¿Quién la puede ver?</span>
            {Object.entries(CLASIFICACION).map(([valor, c]) => (
              <label key={valor} className={`flex cursor-pointer gap-3 rounded-lg border p-3 ${d.clasificacion === valor ? "border-smn-naranja" : "border-smn-gris-100"}`}>
                <input type="radio" name="clasificacion" checked={d.clasificacion === valor} onChange={() => poner("clasificacion")(valor)} className="mt-1" />
                <span><span className="block text-[15px] font-medium">{c.texto}</span><span className="block text-[13px] text-smn-gris-500">{c.ayuda}</span></span>
              </label>
            ))}
            {d.clasificacion !== "general" && (
              <Selector etiqueta={d.clasificacion === "formula" ? "Folio (obligatorio)" : "Folio (opcional)"} valor={d.folio} cambiar={poner("folio")}
                opciones={[{ valor: "", texto: "Sin folio" }, ...mios.map((e) => ({ valor: e.folio, texto: `${e.folio} · ${e.nombre}` }))]} />
            )}
          </div>
          <div className={`${TARJETA} grid gap-3`}>
            <span className={ETIQUETA}>¿De qué ingredientes habla?</span>
            <div className="flex max-h-56 flex-wrap gap-2 overflow-y-auto">
              {ingredientes.length === 0 && <span className="text-sm text-smn-gris-500">Aún no hay ingredientes en el catálogo.</span>}
              {ingredientes.map((i) => {
                const si = elegidos.includes(i.id);
                return (
                  <button key={i.id} type="button" aria-pressed={si} onClick={() => setElegidos((x) => (si ? x.filter((y) => y !== i.id) : [...x, i.id]))}
                    className={`rounded-full px-3 py-1 text-[13px] font-semibold ${si ? "bg-tinta text-superficie" : "bg-smn-gris-100 text-smn-gris-700"}`}>
                    {i.nombre}
                  </button>
                );
              })}
            </div>
            <Campo etiqueta="Categorías (separadas por coma)" value={categorias} onChange={(e) => setCategorias(e.target.value)} placeholder="sueño, relajación" />
          </div>
          <Boton onClick={guardar} cargando={enviando}>Cargar y leer</Boton>
        </div>
      </div>
    </>
  );
}
