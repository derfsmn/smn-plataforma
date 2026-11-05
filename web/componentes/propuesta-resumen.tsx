"use client";
// Lo que capturó el proveedor en una propuesta, de solo lectura. Lo usan el portal (ya enviada) y la bandeja de Compras.

import { FileText } from "lucide-react";
import { tamanoLegible } from "@/lib/api";
import { margenDe, NOMBRE_ADJUNTO, urlAdjunto, type Catalogos, type Propuesta } from "@/lib/propuestas";

function Dato({ titulo, valor, ancho }: { titulo: string; valor: React.ReactNode; ancho?: boolean }) {
  const vacio = valor === null || valor === undefined || valor === "" || (Array.isArray(valor) && !valor.length);
  return (
    <div className={ancho ? "sm:col-span-2" : ""}>
      <dt className="text-[13px] font-medium text-smn-gris-500">{titulo}</dt>
      <dd className={`mt-0.5 break-words ${vacio ? "text-smn-gris-500" : ""}`}>{vacio ? "—" : valor}</dd>
    </div>
  );
}

function Bloque({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5 sm:p-6">
      <h2 className="mb-4 font-semibold">{titulo}</h2>
      {children}
    </section>
  );
}

const Rejilla = ({ children }: { children: React.ReactNode }) => <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">{children}</dl>;

export function ResumenPropuesta({ p, cat }: { p: Propuesta; cat: Catalogos }) {
  const r = p.respuestas;
  const texto = (lista: string, v: string | null) => cat.opciones[lista]?.find((o) => o.valor === v)?.texto ?? v;
  const varios = (lista: string, vs: string[], otro?: string | null) =>
    vs.map((v) => (v === "otro" && otro ? `Otro: ${otro}` : texto(lista, v))).join(", ");
  const conOtro = (v: string | null, otro: string | null) => (v && ["otro", "otra"].includes(v.toLowerCase()) && otro ? `${v}: ${otro}` : v);
  const siNo = (v: string | null) => (v === "si" ? "Sí" : v === "no" ? "No" : null);
  const archivos = (tipos: string[]) => p.adjuntos.filter((a) => tipos.includes(a.tipo));
  const fotos = archivos(["imagen_producto", "imagen_etiquetado"]);
  const docs = archivos(["carta_gs1", "evidencia_registro_funcionamiento", "evidencia_titulo_marca", "ficha_tecnica", "documento_adicional"]);

  return (
    <div className="space-y-4">
      <Bloque titulo="Proveedor">
        <Rejilla>
          <Dato titulo="Marca" valor={r.proveedor.marca} />
          <Dato titulo="Razón social" valor={r.proveedor.razon_social} />
          <Dato titulo="Nombre comercial" valor={r.proveedor.nombre_comercial} />
          <Dato titulo="RFC" valor={r.proveedor.rfc} />
          <Dato titulo="¿Ya es proveedor de SMN?" valor={siNo(r.proveedor.es_proveedor_smn)} />
          <Dato titulo="Público objetivo" valor={varios("publico_objetivo", r.proveedor.publico_objetivo, r.proveedor.publico_objetivo_otro)} />
          <Dato titulo="Inscrito al GS1" valor={siNo(r.proveedor.inscrito_gs1)} />
          <Dato titulo="Registro de funcionamiento y título de marca" valor={siNo(r.proveedor.cuenta_registro_marca)} />
          <Dato titulo="Contacto" valor={[r.proveedor.contacto_nombre, r.proveedor.contacto_cargo].filter(Boolean).join(" · ")} />
          <Dato titulo="Correo y teléfono" valor={[r.proveedor.contacto_correo, r.proveedor.contacto_telefono].filter(Boolean).join(" · ")} />
          <Dato titulo="Contacto alterno" valor={[r.proveedor.contacto_alterno_nombre, r.proveedor.contacto_alterno_correo, r.proveedor.contacto_alterno_telefono].filter(Boolean).join(" · ")} ancho />
        </Rejilla>
      </Bloque>

      <Bloque titulo="Producto">
        <Rejilla>
          <Dato titulo="Fabricante" valor={r.general.fabricante} />
          <Dato titulo="País de origen" valor={conOtro(r.general.pais_origen, r.general.pais_origen_otro)} />
          <Dato titulo="Principal diferenciador" valor={conOtro(r.general.diferenciador, r.general.diferenciador_otro)} />
          <Dato titulo="Necesidad que atiende" valor={conOtro(r.general.necesidad_atendida, r.general.necesidad_atendida_otro)} />
          <Dato titulo="Departamento que propone" valor={r.general.departamento} />
        </Rejilla>
        <div className="mt-5 space-y-3">
          {r.presentaciones.map((x, i) => {
            const fila = p.filas.find((f) => f.orden === i + 1);
            const m = fila?.margen_calculado ?? margenDe(x);
            return (
              <div key={i} className="rounded-2xl bg-smn-gris-50 p-4">
                <p className="mb-3 font-semibold">
                  Presentación {i + 1}
                  {fila?.ya_en_catalogo && <span className="ml-2 rounded-full bg-aviso-fondo px-2 py-0.5 text-[13px] text-aviso-texto">Código ya en el catálogo</span>}
                </p>
                <Rejilla>
                  <Dato titulo="Descripción" valor={x.descripcion} ancho />
                  <Dato titulo="Código de barras" valor={x.codigo_barras} />
                  <Dato titulo="Registro o aviso sanitario" valor={x.registro_sanitario} />
                  <Dato titulo="Presentación" valor={conOtro(x.forma, x.forma_otro)} />
                  <Dato titulo="Ingrediente principal" valor={x.ingrediente_principal} />
                  <Dato titulo="Contenido" valor={[x.contenido_neto, x.unidad_medida].filter(Boolean).join(" ")} />
                  <Dato titulo="Piezas por caja master" valor={x.piezas_caja_master} />
                  <Dato titulo="Costo neto antes de IVA" valor={x.costo_neto_sin_iva && `${x.costo_neto_sin_iva} MXN`} />
                  <Dato titulo="Precio al público sugerido" valor={x.pvp_sugerido && `${x.pvp_sugerido} MXN`} />
                  <Dato titulo="IVA / IEPS" valor={[x.tasa_iva && `IVA ${x.tasa_iva} %`, x.tasa_ieps && `IEPS ${x.tasa_ieps} %`].filter(Boolean).join(" · ")} />
                  <Dato titulo="Margen" valor={[m !== null && `${Number(m).toFixed(2)} % calculado`, x.margen_propuesto_pct && `${x.margen_propuesto_pct} % propuesto`].filter(Boolean).join(" · ")} />
                </Rejilla>
              </div>
            );
          })}
        </div>
      </Bloque>

      {fotos.length > 0 && (
        <Bloque titulo="Imágenes">
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {fotos.map((a) => (
              <li key={a.id} className="overflow-hidden rounded-2xl border border-smn-gris-100">
                <a href={urlAdjunto(p.id, a.id)} target="_blank" rel="noreferrer" className="block aspect-square bg-smn-gris-50">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={urlAdjunto(p.id, a.id)} alt={a.nombre} className="h-full w-full object-contain" />
                </a>
                <p className="border-t border-smn-gris-100 px-2 py-1.5 text-[13px] font-semibold">
                  {a.tipo === "imagen_producto" ? "Producto" : "Etiquetado"} · {a.etiqueta}
                </p>
              </li>
            ))}
          </ul>
        </Bloque>
      )}

      <Bloque titulo="Mercado y competencia">
        <Rejilla>
          <Dato titulo="Dónde se comercializa" valor={texto("canal_actual", r.mercado.canal_actual)} />
          <Dato titulo="Comercios" valor={varios("comercios_actuales", r.mercado.comercios_actuales, r.mercado.comercios_actuales_otro)} />
          <Dato titulo="Datos de desempeño" ancho
            valor={r.mercado.sin_datos_desempeno ? "No cuenta con datos" : r.mercado.desempeno.map((d) => `${texto("desempeno", d.tipo)}: ${[d.cifra, d.canal, d.periodo, d.fuente && `fuente: ${d.fuente}`].filter(Boolean).join(", ")}`).join(" · ")} />
          <Dato titulo="Competidores" ancho
            valor={r.mercado.sin_comparables ? "No identifica comparables" : r.mercado.competidores.map((c) => [c.producto, c.presentacion, c.precio && `${c.precio} MXN`, c.comercio].filter(Boolean).join(", ")).join(" · ")} />
          <Dato titulo="Similares en el catálogo SMN" valor={[siNo(r.mercado.similares_en_smn), r.mercado.similares_cuales].filter(Boolean).join(": ")} ancho />
        </Rejilla>
      </Bloque>

      <Bloque titulo="Entrega, vida útil y lanzamiento">
        <Rejilla>
          <Dato titulo="Manejo especial" valor={varios("manejo_especial", r.logistica.manejo_especial, r.logistica.manejo_especial_otro)} />
          <Dato titulo="Vida útil total" valor={r.logistica.vida_util_total_dias && `${r.logistica.vida_util_total_dias} días`} />
          <Dato titulo="Vida útil mínima al entregar" valor={r.logistica.vida_util_minima_no_aplica ? "No aplica" : r.logistica.vida_util_minima_dias && `${r.logistica.vida_util_minima_dias} días`} />
          <Dato titulo="Apoyos" ancho
            valor={r.lanzamiento.apoyos.map((a) => [a.tipo === "otro" && r.lanzamiento.apoyos_otro ? `Otro: ${r.lanzamiento.apoyos_otro}` : texto("apoyos", a.tipo), a.detalle, a.inicio && `del ${a.inicio}`, a.fin && `al ${a.fin}`].filter(Boolean).join(" ")).join(" · ")} />
          <Dato titulo="Argumento principal" valor={r.lanzamiento.argumento_principal} />
          <Dato titulo="Sustento" valor={r.lanzamiento.sustento} />
        </Rejilla>
      </Bloque>

      {docs.length > 0 && (
        <Bloque titulo="Documentos">
          <ul className="space-y-2">
            {docs.map((a) => (
              <li key={a.id}>
                <a href={urlAdjunto(p.id, a.id)} target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded-xl border border-smn-gris-100 px-3 py-2 text-sm hover:border-smn-naranja">
                  <FileText className="h-4 w-4 shrink-0 text-smn-naranja" />
                  <span className="font-semibold">{NOMBRE_ADJUNTO[a.tipo]}</span>
                  <span className="min-w-0 flex-1 truncate text-smn-gris-500">{a.nombre}</span>
                  <span className="text-[13px] text-smn-gris-500">{tamanoLegible(a.tamano_bytes)}</span>
                </a>
              </li>
            ))}
          </ul>
        </Bloque>
      )}
    </div>
  );
}
