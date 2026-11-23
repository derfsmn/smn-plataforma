"""Investigador en internet de Vidanat: trabaja en pasos fijos y deja rastro de cada uno (plan v2, sección 3).

1 Preguntas: se arman desde la ficha con una plantilla por tema (química, eficacia, seguridad, regulación, mercado);
  la persona las edita y ve los términos que saldrán a internet ANTES de mandarlos.
2 Búsqueda: cada término en cada fuente elegida (PubMed, Europe PMC, ClinicalTrials.gov, OpenAlex, Crossref y, si se
  activa, sitios oficiales y web con DataForSEO y su tope).
3 Selección: quita repetidos por DOI, PMID o NCT y ordena por relevancia, tipo de estudio y fecha.
4 Lectura: baja solo texto de acceso abierto; la IA local extrae material, población, cantidad, duración, resultado y
  límites, y solo se queda lo que trae una frase que sí está en el texto.
5 Informe: por pregunta, con citas a las fuentes leídas, evidencia a favor y en contra, y vacíos.
6 A la base: la persona elige qué hallazgos agregar; entran como «pendiente de revisión».

La IA local no decide: busca, lee, cita y avisa lo que falta. A internet solo salen términos: nunca la fórmula,
cantidades exactas ni el folio (`limpiar_termino`).
"""
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from modulos.innovacion import fuentes_externas as fx
from modulos.innovacion import ia_local
from modulos.innovacion.modelos import Hallazgo, Ingrediente, Investigacion
from nucleo import busqueda
from nucleo.modelos import ahora

MAX_TERMINOS = 8
MAX_SELECCION = 10
MAX_TEXTO_IA = 6000
PESO_ESTUDIO = {"metaanalisis": 1.0, "revision": 0.9, "ensayo": 0.85, "oficial": 0.8, "observacional": 0.55,
                "preclinico": 0.35, "web": 0.3, "otro": 0.3}
TEMAS = ("quimica", "eficacia", "seguridad", "regulacion", "mercado")

EXTRAER = f"""Eres investigador científico y químico de Desarrollo e Innovación de Vidanat (suplementos naturistas).
Te doy una pregunta y el texto de un estudio o documento. Extrae SOLO lo que el texto dice. Regresa un JSON:
{{"material": "sustancia y forma química estudiada", "poblacion": "quiénes y cuántos", "cantidad": "dosis o cantidad",
"duracion": "", "resultado": "lo que encontró, en español", "limites": "limitaciones que reconoce",
"responde": "si" | "parcial" | "no", "cita": "frase copiada tal cual del texto que respalda el resultado"}}
- Si un dato no viene, pon null. No inventes. Copia la cita exactamente como aparece.
{ia_local.REGLA_SEGURIDAD}"""

INFORME = f"""Eres investigador científico y químico de Desarrollo e Innovación de Vidanat. Redacta en español el informe de
una pregunta usando SOLO las fuentes numeradas que te doy (ya leídas). Estructura:
Respuesta corta (2 a 3 frases). Evidencia a favor. Evidencia en contra o dudas. Vacíos: qué no se encontró.
- Cita cada afirmación con el número de la fuente entre corchetes, por ejemplo [3].
- Distingue estudios en humanos, en animales o in vitro, y de qué forma química y cantidad hablan.
- No es una recomendación ni un dictamen: eso lo decide el equipo.
- Si las fuentes no alcanzan, dilo con claridad.
{ia_local.REGLA_SEGURIDAD}"""


# ---------------------------------------------------------------- 1 · preguntas y términos

def limpiar_termino(termino: str) -> str:
    """Quita lo que nunca debe salir: folios, cantidades con unidad y números largos."""
    t = re.sub(r"\bVID-\d{4}-\d{3,5}\b", " ", termino, flags=re.I)
    t = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|µg|ug|mcg|ui|iu|ml|%|kg|ufc|cfu)\b", " ", t, flags=re.I)
    t = re.sub(r"\b\d{3,}\b", " ", t)
    return " ".join(t.split())[:200]


def _sinonimos(bd: Session, nombre: str) -> list[str]:
    ing = bd.scalar(select(Ingrediente).where(Ingrediente.nombre == nombre))
    if not ing or not ing.sinonimos:
        return []
    try:
        return [s for s in json.loads(ing.sinonimos) if isinstance(s, str)]
    except ValueError:
        return []


def proponer(bd: Session, ficha: dict | None, tema: str) -> dict:
    """Preguntas y términos sugeridos desde los datos GENERALES de la ficha (ingrediente, forma, categoría)."""
    ingredientes = [i for i in (ficha or {}).get("ingredientes", []) if i.get("nombre")][:4]
    categoria = (ficha or {}).get("categoria_comercial") or (ficha or {}).get("categoria_sanitaria") or "suplemento"
    beneficio = (ficha or {}).get("beneficio") or tema
    preguntas, terminos = [], []
    for i in ingredientes:
        nombre, forma = i["nombre"], i.get("forma") or ""
        preguntas += [
            {"tema": "quimica", "texto": f"¿Qué forma química de {nombre} tiene mejor biodisponibilidad y cuál es su contenido activo{' en ' + forma if forma else ''}?"},
            {"tema": "eficacia", "texto": f"¿Qué evidencia clínica hay de {nombre} para {beneficio}?"},
            {"tema": "seguridad", "texto": f"¿Qué cantidades se han estudiado de {nombre} y qué efectos adversos o interacciones se reportan?"},
            {"tema": "regulacion", "texto": f"¿Qué dice la regulación mexicana (COFEPRIS) sobre {nombre} en {categoria}?"},
        ]
        base = [nombre] + _sinonimos(bd, nombre)[:2]
        for b in base:
            terminos += [f"{b} {forma}".strip() + " bioavailability", f"{b} randomized controlled trial",
                         f"{b} safety adverse effects"]
    if not ingredientes:
        preguntas = [{"tema": "eficacia", "texto": f"¿Qué evidencia científica hay sobre {tema}?"},
                     {"tema": "seguridad", "texto": f"¿Qué riesgos o efectos adversos se reportan sobre {tema}?"},
                     {"tema": "regulacion", "texto": f"¿Qué dice la regulación mexicana sobre {tema}?"}]
        terminos = [tema]
    terminos = [t for t in dict.fromkeys(limpiar_termino(t) for t in terminos) if t][:MAX_TERMINOS]
    return {"preguntas": preguntas[:12], "terminos": terminos}


# ---------------------------------------------------------------- pasos 2 a 5

def _paso(inv: Investigacion, paso: str, texto: str) -> None:
    pasos = json.loads(inv.pasos) if inv.pasos else []
    pasos.append({"paso": paso, "texto": texto, "en": ahora().isoformat(timespec="seconds")})
    inv.pasos = json.dumps(pasos, ensure_ascii=False)


def _puntaje(texto_busqueda: str, r: Hallazgo, df: Counter, n: int) -> float:
    consulta = set(busqueda.palabras(texto_busqueda))
    doc = Counter(busqueda.palabras(f"{r.titulo} {r.titulo} {r.resumen or ''}"))
    if not consulta:
        return 0.0
    import math
    relevancia = sum(math.log(1 + n / (1 + df[t])) for t in consulta if doc.get(t)) / sum(
        math.log(1 + n / (1 + df[t])) for t in consulta)
    reciente = 0.0
    if r.anio:
        reciente = max(0.0, 1 - (date.today().year - r.anio) / 20)
    return round(0.6 * relevancia + 0.3 * PESO_ESTUDIO.get(r.tipo_estudio or "otro", 0.3) + 0.1 * reciente, 4)


def buscar(bd: Session, inv: Investigacion) -> None:
    terminos = [limpiar_termino(t) for t in json.loads(inv.terminos or "[]")]
    terminos = [t for t in terminos if t]
    fuentes = json.loads(inv.fuentes or "[]")
    vistos: set[str] = {h.identificador for h in bd.scalars(select(Hallazgo).where(
        Hallazgo.investigacion_id == inv.investigacion_id)) if h.identificador}
    notas, nuevos, costo = [], 0, Decimal(inv.costo_usd or 0)
    registros: list[fx.Registro] = []
    for f in fuentes:
        if f in fx.CLIENTES:
            for t in terminos:
                r = fx.CLIENTES[f](t)
                registros += r.registros
                notas += r.notas
        elif f in fx.CON_GASTO and inv.usar_web:
            r = fx.web(bd, terminos[:3], oficiales=(f == "oficial"), referencia=f"investigacion {inv.investigacion_id}")
            registros += r.registros
            notas += r.notas
            costo += Decimal(str(r.costo_usd))
    for x in registros:
        clave = x.identificador
        if not clave or clave in vistos or not x.titulo:
            continue
        vistos.add(clave)
        bd.add(Hallazgo(investigacion_id=inv.investigacion_id, origen=x.origen, identificador=clave[:200],
                        titulo=x.titulo[:1000], autores=x.autores, anio=x.anio, publicado_en=(x.publicado_en or "")[:300] or None,
                        url=x.url, tipo_estudio=x.tipo_estudio, resumen=x.resumen,
                        extraccion=json.dumps({"pmcid": x.pmcid, "acceso_abierto": x.acceso_abierto}) if x.pmcid or x.acceso_abierto else None))
        nuevos += 1
    inv.costo_usd = costo
    unicas = list(dict.fromkeys(notas))
    _paso(inv, "busqueda", f"{nuevos} resultados sin repetir de {len(fuentes)} fuentes con {len(terminos)} términos."
          + (" " + " ".join(unicas[:4]) if unicas else ""))
    bd.commit()


def seleccionar(bd: Session, inv: Investigacion) -> list[Hallazgo]:
    todos = list(bd.scalars(select(Hallazgo).where(Hallazgo.investigacion_id == inv.investigacion_id)))
    df: Counter = Counter()
    for h in todos:
        df.update(set(busqueda.palabras(f"{h.titulo} {h.resumen or ''}")))
    consulta = " ".join(p["texto"] for p in json.loads(inv.preguntas)) + " " + " ".join(json.loads(inv.terminos or "[]"))
    for h in todos:
        h.puntaje = Decimal(str(_puntaje(consulta, h, df, len(todos) or 1)))
    elegidos = sorted(todos, key=lambda h: h.puntaje or 0, reverse=True)[:MAX_SELECCION]
    for h in todos:
        h.seleccionado = h in elegidos
    _paso(inv, "seleccion", f"{len(elegidos)} de {len(todos)} elegidos por relevancia, tipo de estudio y fecha.")
    bd.commit()
    return elegidos


def leer(bd: Session, inv: Investigacion, elegidos: list[Hallazgo]) -> None:
    preguntas = " ".join(p["texto"] for p in json.loads(inv.preguntas))
    leidos = abiertos = 0
    for h in elegidos:
        meta = json.loads(h.extraccion) if h.extraccion else {}
        texto = None
        if meta.get("pmcid") and meta.get("acceso_abierto"):
            texto = fx.texto_completo_europepmc(meta["pmcid"])
        elif h.origen in ("oficial", "web") and h.url:
            texto = fx.texto_de_pagina(h.url)
            if texto is None:
                meta["bloqueado"] = True  # el sitio no deja leer: queda como enlace para una persona
        if texto:
            h.texto_abierto, abiertos = texto, abiertos + 1
        fuente = (texto or h.resumen or "")
        if not fuente:
            h.extraccion = json.dumps(meta, ensure_ascii=False)
            continue
        try:
            d = ia_local.json_de(ia_local._ejecutar(
                bd, "innovacion.investigar", inv.creado_por, EXTRAER,
                f"Pregunta(s): {preguntas[:1500]}\n\nTítulo: {h.titulo}\n\nTexto:\n{_recorte(fuente, preguntas)}",
                max_tokens=700, contexto=8192))
        except (ia_local.RespuestaInvalida, Exception) as e:  # noqa: BLE001 - sin IA, el hallazgo queda con su resumen
            meta["aviso"] = "La IA local no pudo leerlo." if not isinstance(e, ia_local.RespuestaInvalida) else str(e)
            h.extraccion = json.dumps(meta, ensure_ascii=False)
            continue
        if isinstance(d, dict):
            from modulos.compras.buscar_web import cita_ok
            if not cita_ok(str(d.get("cita") or ""), fuente):
                d["cita"] = None
                d["aviso"] = "La frase citada por la IA no está en el texto: el resultado no se usa."
                d["resultado"] = None
            meta.update({k: d.get(k) for k in ("material", "poblacion", "cantidad", "duracion", "resultado", "limites",
                                               "responde", "cita", "aviso") if d.get(k) is not None})
            leidos += 1
        h.extraccion = json.dumps(meta, ensure_ascii=False)
        bd.commit()
    _paso(inv, "lectura", f"{leidos} leídos por la IA local; {abiertos} con texto completo de acceso abierto, los demás por su resumen.")
    bd.commit()


def _recorte(texto: str, preguntas: str) -> str:
    if len(texto) <= MAX_TEXTO_IA:
        return texto
    claves = set(busqueda.palabras(preguntas))
    parrafos = texto.split("\n")
    marcados = sorted(parrafos, key=lambda p: -len(claves & set(busqueda.palabras(p))))
    salida, largo = [], 0
    for p in marcados:
        if largo + len(p) > MAX_TEXTO_IA:
            break
        salida.append(p)
        largo += len(p)
    return "\n".join(salida) or texto[:MAX_TEXTO_IA]


def informe(bd: Session, inv: Investigacion, elegidos: list[Hallazgo]) -> None:
    fuentes = []
    for h in elegidos:
        meta = json.loads(h.extraccion) if h.extraccion else {}
        if meta.get("resultado") or h.resumen:
            fuentes.append((h, meta))
    salida = []
    for p in json.loads(inv.preguntas):
        if not fuentes:
            salida.append({"pregunta": p["texto"], "tema": p.get("tema"), "texto": "No se encontraron fuentes que leer para esta pregunta.",
                           "citas": [], "insuficiente": True})
            continue
        bloque = "\n\n".join(
            f"[{n}] {h.titulo} ({h.anio or 's/f'}; {h.tipo_estudio or 'otro'}). "
            + (f"Resultado: {m.get('resultado')}. Población: {m.get('poblacion')}. Cantidad: {m.get('cantidad')}. "
               f"Límites: {m.get('limites')}." if m.get("resultado") else f"Resumen: {(h.resumen or '')[:1200]}")
            for n, (h, m) in enumerate(fuentes, start=1))
        try:
            texto = ia_local._ejecutar(bd, "innovacion.investigar", inv.creado_por, INFORME,
                                       f"Pregunta: {p['texto']}\n\nFuentes:\n{bloque}", max_tokens=1200, contexto=8192)
            texto, usados = ia_local.citas_validas(texto, len(fuentes))
        except Exception:  # noqa: BLE001 - sin IA, el informe lista las fuentes
            texto, usados = "", []
        if not usados:
            salida.append({"pregunta": p["texto"], "tema": p.get("tema"), "insuficiente": True, "citas": [],
                           "texto": "La IA local no pudo redactar con citas. Revisa las fuentes elegidas abajo."})
            continue
        salida.append({"pregunta": p["texto"], "tema": p.get("tema"), "texto": texto, "insuficiente": False,
                       "citas": [{"n": n, "hallazgo_id": fuentes[n - 1][0].hallazgo_id, "titulo": fuentes[n - 1][0].titulo,
                                  "url": fuentes[n - 1][0].url} for n in usados]})
    inv.informe = json.dumps(salida, ensure_ascii=False)
    _paso(inv, "informe", f"Informe de {len(salida)} preguntas.")
    bd.commit()


def correr(bd: Session, investigacion_id: int, *, usuario_id: int | None = None) -> None:
    inv = bd.get(Investigacion, investigacion_id)
    if not inv or inv.estado not in ("corriendo",):
        return
    try:
        buscar(bd, inv)
        elegidos = seleccionar(bd, inv)
        leer(bd, inv, elegidos)
        informe(bd, inv, elegidos)
    except Exception as e:
        bd.rollback()
        inv = bd.get(Investigacion, investigacion_id)
        inv.estado, inv.error, inv.terminada_en = "error", str(e)[:1000], ahora()
        bd.commit()
        raise
    inv.estado, inv.terminada_en = "lista", ahora()
    bd.commit()
