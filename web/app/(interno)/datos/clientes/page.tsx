"use client";
// Datos → Clientes: tipos de cliente según cómo compran (k-medias en Python, nombres con la IA local). Sin datos de
// personas: el CSV de SMNBI trae códigos que cambian en cada corrida y aquí solo se ven los perfiles de cada tipo.

import { motion } from "motion/react";
import { Download, FileUp, RefreshCw, Sparkles, Store, UsersRound } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Encabezado, Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe, urlApi } from "@/lib/api";
import { numero, pesos, RUTA, subirClientes, type Estado, type Objetivo, type TipoCliente } from "@/lib/clientes";

const COMANDO = `docker run --rm -it -v ~/clientes:/c --entrypoint /opt/mssql-tools18/bin/sqlcmd mcr.microsoft.com/mssql/server:2022-latest -S 172.31.102.70 -d SMNBI -U TU_USUARIO -C -i /c/q.sql -o /c/clientes.csv -s "," -W -h -1`;

export default function Clientes() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [estado, setEstado] = useState<Estado | null>(null);
  const [tipos, setTipos] = useState<number | null>(null);
  const [avance, setAvance] = useState<number | null>(null);
  const archivo = useRef<HTMLInputElement>(null);
  const calcula = puede("datos.clientes.calcular");

  const cargar = useCallback(() => api<Estado>(RUTA).then(setEstado).catch((e) => avisar(mensajeDe(e), "info")), [avisar]);
  useEffect(() => {
    cargar();
  }, [cargar]);
  useEffect(() => {
    if (!estado?.en_curso) return;
    const t = setInterval(cargar, 3000);
    return () => clearInterval(t);
  }, [estado?.en_curso, cargar]);

  async function subir(f: File) {
    setAvance(0);
    try {
      await subirClientes(f, tipos, setAvance);
      avisar("Archivo recibido. Calculando los tipos de cliente…", "exito");
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setAvance(null);
      if (archivo.current) archivo.current.value = "";
    }
  }

  async function recalcular() {
    try {
      await api(`${RUTA}/calcular`, { metodo: "POST", cuerpo: { tipos } });
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  }

  async function descargarConsulta() {
    const r = await fetch(`${urlApi()}${RUTA}/consulta`, { credentials: "include" });
    if (!r.ok) return avisar("No se pudo descargar la consulta.", "info");
    const url = URL.createObjectURL(new Blob([await r.text()], { type: "text/plain" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "consulta_clientes.sql" });
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!estado) return <Esqueleto className="h-96" />;
  const { corrida, en_curso, fallida, resumen } = estado;

  return (
    <>
      <Encabezado
        titulo="Clientes"
        descripcion="Tipos de cliente según cómo compran en nuestras tiendas: qué tan seguido, cuánto gastan, qué compran y a qué precio. Sin nombres ni datos de personas. «Buscar oportunidades» los usa para no proponer lo que nuestro cliente no compraría."
      />

      <NuestroCliente estado={estado} edita={calcula} alGuardar={cargar} />

      {calcula && (
        <Entrada className="mb-8 rounded-2xl border border-smn-gris-100 bg-superficie p-5">
          <h2 className="text-lg font-semibold">Cargar la venta por cliente</h2>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-[15px] text-smn-gris-700">
            <li>
              En el servidor, guarda la consulta en <code className="font-mono text-[13px]">~/clientes/q.sql</code> y
              dale permisos con <code className="font-mono text-[13px]">chmod 777 ~/clientes</code>.
            </li>
            <li>
              Córrela con tu usuario de SMNBI (no saca nombres ni números de cliente):
              <pre className="mt-1 overflow-x-auto rounded-lg bg-smn-gris-50 p-2 font-mono text-[12px] text-tinta">{COMANDO}</pre>
            </li>
            <li>Copia <code className="font-mono text-[13px]">~/clientes/clientes.csv</code> a tu equipo y súbelo aquí.</li>
          </ol>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Boton variante="secundario" onClick={descargarConsulta}>
              <Download className="h-4 w-4" /> Descargar la consulta
            </Boton>
            <label className="flex items-center gap-2 text-[14px] text-smn-gris-700">
              Tipos
              <select
                value={tipos ?? ""}
                onChange={(e) => setTipos(e.target.value ? Number(e.target.value) : null)}
                className="h-10 rounded-lg border border-smn-gris-100 bg-superficie px-2 text-[14px]"
              >
                <option value="">Los que mejor separan</option>
                {[2, 3, 4, 5, 6, 7, 8].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <input ref={archivo} type="file" accept=".csv,.txt" className="hidden" onChange={(e) => e.target.files?.[0] && subir(e.target.files[0])} />
            <Boton onClick={() => archivo.current?.click()} cargando={avance !== null} disabled={!!en_curso}>
              <FileUp className="h-4 w-4" /> {avance !== null ? `Subiendo ${avance} %` : "Subir el archivo"}
            </Boton>
            {estado.hay_archivo && (
              <Boton variante="fantasma" onClick={recalcular} disabled={!!en_curso}>
                <RefreshCw className="h-4 w-4" /> Recalcular con el último archivo
              </Boton>
            )}
          </div>
        </Entrada>
      )}

      {en_curso && (
        <p className="mb-6 flex items-center gap-2 rounded-xl bg-smn-gris-50 px-4 py-3 text-[15px] text-smn-gris-700">
          <RefreshCw className="h-4 w-4 animate-spin" /> {en_curso.paso ?? "Calculando"}…
        </p>
      )}
      {fallida && <p className="mb-6 rounded-xl bg-aviso-fondo px-4 py-3 text-[15px] text-aviso-texto">{fallida.error}</p>}

      {!corrida || !resumen ? (
        !en_curso && (
          <p className="rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-[15px] text-smn-gris-700">
            <UsersRound className="mx-auto mb-3 h-8 w-8" aria-hidden />
            Todavía no se han calculado los tipos de cliente. Sube el archivo de la consulta.
          </p>
        )
      ) : (
        <>
          <Entrada className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Cifra titulo="Clientes identificados" valor={numero(resumen.clientes)} nota={`${numero(resumen.notas_identificadas)} compras`} />
            <Cifra
              titulo="Compras con cliente identificado"
              valor={resumen.parte_notas_identificadas !== null ? `${resumen.parte_notas_identificadas} %` : "—"}
              nota="El resto va a cuentas genéricas"
            />
            <Cifra titulo="Público en general" valor={`${numero(resumen.cuentas_genericas)} cuentas`} nota={`${numero(resumen.notas_genericas)} compras · ${pesos(resumen.venta_generica)}`} />
            <Cifra titulo="Venta identificada" valor={pesos(resumen.venta_identificada)} nota="Sin IVA, ene a sep" />
          </Entrada>
          <p className="mb-4 text-[14px] text-smn-gris-700">
            {corrida.tipos} tipos · calculado el {fechaLocal(corrida.terminada_en ?? corrida.iniciada_en)}
            {corrida.archivo && ` con ${corrida.archivo}`}
            {corrida.calidad !== null && ` · separación ${corrida.calidad.toFixed(2)} (de −1 a 1)`}.
            {corrida.nota_ia && <span className="block text-aviso-texto">{corrida.nota_ia}</span>}
          </p>

          <div className="mb-10 grid gap-4 lg:grid-cols-2">
            {estado.tipos.map((t, i) => <Tarjeta key={t.tipo} t={t} i={i} />)}
          </div>

          <Entrada className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
            <h2 className="text-lg font-semibold">Lo que paga nuestro cliente por pieza</h2>
            <p className="mt-1 text-[14px] text-smn-gris-700">
              Sin IVA, pesado por piezas. «Buscar oportunidades» quita lo que queda arriba del porcentaje que elijas en Configuración (90 % de fábrica). Los departamentos con menos de 1 % de la venta no ponen tope.
            </p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[560px] text-[14px]">
                <thead className="text-left text-smn-gris-500">
                  <tr>
                    <th className="py-2 font-medium">Departamento</th>
                    {["Venta", "25 %", "Mitad", "75 %", "90 %", "Público en general"].map((h) => <th key={h} className="py-2 text-right font-medium">{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(resumen.precios_por_departamento).map(([d, p]) => {
                    const parte = resumen.parte_venta_por_departamento?.[d];
                    const sinTope = parte !== undefined && parte < 1;
                    return (
                    <tr key={d} className={`border-t border-smn-gris-100 ${sinTope ? "text-smn-gris-500" : ""}`}>
                      <td className="py-2">{d}{sinTope && <span className="ml-2 text-[12px]">· no pone tope</span>}</td>
                      <td className="py-2 text-right tabular-nums">{parte === undefined ? "—" : `${parte.toLocaleString("es-MX")} %`}</td>
                      {[p.p25, p.p50, p.p75, p.p90].map((v, j) => <td key={j} className="py-2 text-right tabular-nums">{pesos(v)}</td>)}
                      <td className="py-2 text-right tabular-nums text-smn-gris-500">
                        {resumen.precio_generico_por_departamento[d] ? pesos(resumen.precio_generico_por_departamento[d]) : "—"}
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Entrada>
        </>
      )}
    </>
  );
}

function NuestroCliente({ estado, edita, alGuardar }: { estado: Estado; edita: boolean; alGuardar: () => void }) {
  const avisar = useAvisos();
  const [nivel, setNivel] = useState(estado.objetivo?.nivel ?? "");
  const [descripcion, setDescripcion] = useState(estado.objetivo?.descripcion ?? "");
  const [guardando, setGuardando] = useState(false);
  const cambio = nivel !== (estado.objetivo?.nivel ?? "") || descripcion.trim() !== (estado.objetivo?.descripcion ?? "");

  async function guardar() {
    setGuardando(true);
    try {
      await api<Objetivo>(`${RUTA}/objetivo`, { metodo: "PUT", cuerpo: { nivel, descripcion } });
      avisar("Guardado. La siguiente búsqueda de oportunidades ya lo usa.", "exito");
      alGuardar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setGuardando(false);
    }
  }

  if (!edita && !estado.objetivo) return null;
  return (
    <Entrada className="mb-8 rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <h2 className="text-lg font-semibold">Nuestro cliente</h2>
      <p className="mt-1 max-w-3xl text-[15px] text-smn-gris-700">
        A quién le vendemos. «Buscar oportunidades» revisa cada producto contra esto: quita los que no encajan y marca los dudosos.
      </p>
      <div className="mt-4 grid gap-5 lg:grid-cols-2">
        <div>
          <label className="block text-[14px] font-medium" htmlFor="nivel-cliente">Nivel socioeconómico</label>
          {edita ? (
            <select
              id="nivel-cliente"
              value={nivel}
              onChange={(e) => setNivel(e.target.value)}
              className="mt-1 h-11 rounded-lg border border-smn-gris-100 bg-superficie px-3 text-[15px]"
            >
              {!nivel && <option value="">Elige</option>}
              {estado.niveles.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          ) : (
            <p className="mt-1 text-2xl font-semibold">{estado.objetivo?.nivel}</p>
          )}
          <label className="mt-4 block text-[14px] font-medium" htmlFor="descripcion-cliente">Cómo es, en sus palabras</label>
          {edita ? (
            <textarea
              id="descripcion-cliente"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              maxLength={3000}
              rows={6}
              placeholder="Qué busca, cuánto puede gastar, qué no compraría. Lo escribe Compras o Transformación Digital."
              className="mt-1 w-full rounded-lg border border-smn-gris-100 bg-superficie p-3 text-[15px]"
            />
          ) : (
            <p className="mt-1 whitespace-pre-line text-[15px] text-smn-gris-700">{estado.objetivo?.descripcion || "Todavía no se ha escrito."}</p>
          )}
          {edita && (
            <Boton className="mt-3" onClick={guardar} cargando={guardando} disabled={!nivel || !cambio}>Guardar</Boton>
          )}
        </div>
        <div>
          <p className="text-[14px] font-medium">Lo que dicen sus compras</p>
          {estado.borrador_objetivo ? (
            <p className="mt-1 whitespace-pre-line text-[15px] text-smn-gris-700">{estado.borrador_objetivo}</p>
          ) : (
            <p className="mt-1 text-[15px] text-smn-gris-700">Sale solo al calcular los tipos de cliente.</p>
          )}
          <p className="mt-3 text-[13px] text-smn-gris-500">La IA recibe el nivel, lo que escriban a la izquierda y estas cifras.</p>
        </div>
      </div>
    </Entrada>
  );
}

function Cifra({ titulo, valor, nota }: { titulo: string; valor: string; nota: string }) {
  return (
    <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
      <p className="text-[13px] text-smn-gris-500">{titulo}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{valor}</p>
      <p className="mt-0.5 text-[13px] text-smn-gris-700">{nota}</p>
    </div>
  );
}

function Tarjeta({ t, i }: { t: TipoCliente; i: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(i * 0.05, 0.3) }}
      className="rounded-2xl border border-smn-gris-100 bg-superficie p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-[17px] font-semibold">{t.nombre}</h3>
        <div className="flex gap-1.5">
          <Insignia className="bg-smn-gris-100 text-smn-gris-700">{t.parte_clientes} % de clientes</Insignia>
          <Insignia className="bg-smn-naranja/15 text-tinta">{t.parte_venta} % de la venta</Insignia>
        </div>
      </div>
      {t.descripcion && <p className="mt-2 text-[15px] text-smn-gris-700">{t.descripcion}</p>}
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[14px] sm:grid-cols-3">
        <Dato t="Compras al mes" v={t.compras_al_mes.toLocaleString("es-MX")} />
        <Dato t="Gasto al mes" v={pesos(t.gasto_al_mes)} />
        <Dato t="Ticket" v={pesos(t.ticket)} />
        <Dato t="Precio por pieza" v={pesos(t.precio_por_pieza)} />
        <Dato t="Meses que compra" v={`${t.meses_que_compra} de 9`} />
        <Dato t="Clientes" v={numero(t.clientes)} />
      </dl>
      <div className="mt-4 space-y-1.5">
        {t.mezcla.slice(0, 4).map((m) => (
          <div key={m.departamento} className="text-[13px]">
            <div className="flex justify-between text-smn-gris-700">
              <span>{m.departamento}</span>
              <span className="tabular-nums">{m.parte} % <span className="text-smn-gris-500">(todos {m.empresa} %)</span></span>
            </div>
            <div className="mt-0.5 h-1.5 rounded-full bg-smn-gris-100">
              <div className="h-1.5 rounded-full bg-smn-naranja" style={{ width: `${Math.min(m.parte, 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
      {Object.keys(t.precios).length > 0 && (
        <p className="mt-3 text-[13px] text-smn-gris-700">
          <b className="font-medium text-tinta">Paga por pieza:</b>{" "}
          {Object.entries(t.precios).map(([d, p]) => `${d} ${pesos(p.p25)}–${pesos(p.p75)}`).join(" · ")}
        </p>
      )}
      {t.regiones.length > 0 && (
        <p className="mt-1 flex items-center gap-1 text-[13px] text-smn-gris-700">
          <Store className="h-3.5 w-3.5" aria-hidden /> {t.regiones.map((r) => `${r.region} ${r.parte} %`).join(" · ")}
        </p>
      )}
      {t.acciones.length > 0 && (
        <ul className="mt-3 space-y-1 text-[14px]">
          {t.acciones.map((a) => (
            <li key={a} className="flex gap-1.5"><Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-naranja-tinta" aria-hidden />{a}</li>
          ))}
        </ul>
      )}
    </motion.article>
  );
}

function Dato({ t, v }: { t: string; v: string }) {
  return (
    <div>
      <dt className="text-smn-gris-500">{t}</dt>
      <dd className="font-medium tabular-nums">{v}</dd>
    </div>
  );
}
