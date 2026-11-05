"""Radar de tendencias: la corrida diaria.

1. Lee las fuentes activas: RSS directo (sin costo) y, para sitios sin RSS, búsqueda de la IA dentro del sitio.
2. Búsqueda abierta en internet por cada tema activo.
3. Guarda cada nota una sola vez (misma liga, o mismo título en los últimos 30 días, cuenta como repetida).
   La fecha de la nota sale de la fuente; las que pasan de la ventana de días se guardan pero no se analizan.
4. La IA clasifica las notas nuevas (relevante, categoría, nivel, área, país).
5. La IA agrupa en señales y elige los hallazgos del día. Si es emergente o tendencia lo decide la regla:
   tendencia = 2 o más sitios distintos, o aparece en EUA y en México.
6. Se guarda el reporte y se manda por correo a la lista de destinatarios.

Una liga que da la búsqueda de la IA solo se acepta si salió de las páginas que la búsqueda consultó.
Nada de aquí inventa datos: si la IA no está disponible, el reporte lo dice y no trae hallazgos.
"""
import hashlib
import html
import json
import logging
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import feedparser
from sqlalchemy import func, select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.config import configuracion
from core.correo import NARANJA, NEGRO, enviar
from ia import puerta
from modulos.compras.modelos import (RadarAccion, RadarArticulo, RadarDestinatario, RadarDocumento, RadarFuente, RadarHallazgo,
                                     RadarReporte, RadarSenal, RadarSenalArticulo, RadarTema)
from nucleo.modelos import Modulo, Permiso, RolPermiso, Usuario, UsuarioRol, ahora
from nucleo.notificaciones import notificar

log = logging.getLogger("uvicorn.error")

ADMINISTRAR = "compras.radar.administrar"
CATEGORIAS = ["PRODUCTO", "INGREDIENTE", "PROVEEDOR", "TENDENCIA", "REGULACIÓN", "CONSUMIDOR", "COMPETENCIA",
              "MERCADO", "INNOVACIÓN"]
NIVELES = ["ALTA", "MEDIA", "TEMPRANA"]
POR_LOTE = 20
MAX_EXTRACTO = 1200
AGENTE = "Mozilla/5.0 (compatible; SMN-Radar/1.0; +https://supernaturista.mx)"

REGLAS = """Reglas que no se rompen:
- Usa solo lo que dicen las notas que se te dan. No inventes empresas, productos, ingredientes, cifras ni fechas.
- No afirmes propiedades médicas, no diagnostiques y no presentes ingredientes como tratamientos.
- Describe tendencias comerciales, regulatorias, de consumo o de innovación.
- Escribe en español de México, claro y ejecutivo.
- Responde solo con JSON válido, sin texto antes ni después."""

CONTEXTO_SMN = """Trabajas para el área de Compras de Súper Naturista (Súper Mayoreo Naturista, SMN), cadena mexicana de
tiendas naturistas. Compras busca señales tempranas de productos, ingredientes, formatos, proveedores y regulación
que podrían convertirse en productos nuevos para sus tiendas. El equipo mira lo que pasa en EUA para anticipar
lo que viene a México."""


class ErrorRadar(Exception):
    pass


# ---------------------------------------------------------------- utilidades

def zona() -> ZoneInfo:
    return ZoneInfo(configuracion().radar_zona_horaria)


def hoy_local() -> date:
    return datetime.now(zona()).date()


def normalizar_url(url: str) -> str:
    partes = urlsplit(url.strip())
    consulta = [(k, v) for k, v in parse_qsl(partes.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    ruta = partes.path.rstrip("/") or "/"
    return urlunsplit((partes.scheme.lower() or "https", partes.netloc.lower(), ruta, urlencode(consulta), ""))


def _clave_url(url: str) -> str:
    """Para comparar ligas: sin esquema ni www."""
    n = normalizar_url(url)
    return re.sub(r"^https?://(www\.)?", "", n)


def sitio_de(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def _titulo_hash(titulo: str) -> str:
    t = unicodedata.normalize("NFKD", titulo.lower())
    t = "".join(c for c in t if c.isalnum() or c == " ")
    return _hash(" ".join(t.split()))


def _texto_plano(html_texto: str | None, maximo: int = MAX_EXTRACTO) -> str | None:
    if not html_texto:
        return None
    t = html.unescape(re.sub(r"<[^>]+>", " ", html_texto))
    t = " ".join(t.replace("<![CDATA[", "").replace("]]>", "").split())
    return t[:maximo] or None


def _json_de(texto: str):
    """Saca el JSON de la respuesta de la IA (a veces viene entre ```)."""
    t = texto.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t)
    inicio = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
    if inicio < 0:
        raise ValueError("La IA no respondió JSON.")
    return json.loads(t[inicio:t.rfind("}" if t[inicio] == "{" else "]") + 1])


def _fecha(valor) -> date | None:
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        try:
            return parsedate_to_datetime(str(valor)).date()
        except (TypeError, ValueError):
            return None


# ---------------------------------------------------------------- lectura

def leer_rss(direccion: str) -> list[dict]:
    peticion = urllib.request.Request(direccion, headers={"User-Agent": AGENTE, "Accept": "application/rss+xml, */*"})
    try:
        with urllib.request.urlopen(peticion, timeout=25) as r:
            contenido = r.read(5 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        bloqueo = " El sitio bloquea lectores automáticos; si sigue igual, cambia esta fuente a «Búsqueda en su sitio»." \
            if e.code in (401, 403, 429) else ""
        raise ErrorRadar(f"El sitio respondió con error {e.code}.{bloqueo}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErrorRadar("No se pudo conectar con el sitio.") from e
    feed = feedparser.parse(contenido)
    if feed.bozo and not feed.entries:
        raise ErrorRadar("La dirección no devolvió un RSS válido (a veces es una página de captcha). "
                         "Si sigue igual, cambia esta fuente a «Búsqueda en su sitio».")
    notas = []
    for e in feed.entries:
        liga = e.get("link")
        titulo = _texto_plano(e.get("title"), 500)
        if not liga or not titulo:
            continue
        publicado = None
        for campo in ("published_parsed", "updated_parsed"):
            if e.get(campo):
                publicado = date(*e[campo][:3])
                break
        notas.append({"url": liga, "titulo": titulo, "extracto": _texto_plano(e.get("summary")),
                      "publicado_en": publicado})
    return notas


INSTRUCCIONES_BUSQUEDA = f"""{CONTEXTO_SMN}

Busca en internet notas recientes (noticias, comunicados, publicaciones) y devuelve las que encontraste.
- Solo notas que hayas visto en los resultados de tu búsqueda, con su liga exacta. Nunca inventes ni armes ligas.
- Solo notas publicadas en la ventana de fechas indicada. Si no sabes la fecha de publicación, no la incluyas.
- Prefiere fuentes oficiales, medios especializados y medios de negocios. Evita blogs de opinión y tiendas.
- Máximo 8 notas.
{REGLAS}

Formato: {{"notas": [{{"titulo": "...", "url": "https://...", "fecha": "AAAA-MM-DD", "resumen": "2 o 3 líneas de lo que dice la nota", "pais": "MX|EUA|UE|global"}}]}}
Si no encuentras nada que cumpla, responde {{"notas": []}}."""


def buscar_con_ia(bd: Session, consulta: str, desde: date, dominios: list[str] | None = None) -> tuple[list[dict], int]:
    """Devuelve (notas comprobadas, notas descartadas por liga no comprobada)."""
    mensaje = (f"Qué buscar: {consulta}\nVentana: notas publicadas del {desde.isoformat()} a hoy "
               f"({hoy_local().isoformat()}).")
    if dominios:
        mensaje += "\nBusca solo dentro de estos sitios: " + ", ".join(dominios)
    r = puerta.ejecutar(bd, "compras.radar_buscar", usuario_id=None, instrucciones=INSTRUCCIONES_BUSQUEDA,
                        mensaje=mensaje, max_tokens=6000, esfuerzo="low", busqueda_web=True, dominios=dominios)
    vistas = {_clave_url(c["url"]) for c in r.citas if c.get("url")}
    notas, descartadas = [], 0
    for n in (_json_de(r.texto).get("notas") or [])[:8]:
        url, titulo = str(n.get("url") or "").strip(), _texto_plano(str(n.get("titulo") or ""), 500)
        if not url.startswith(("http://", "https://")) or not titulo:
            continue
        if _clave_url(url) not in vistas:
            descartadas += 1  # la liga no salió de la búsqueda: no se puede verificar
            continue
        notas.append({"url": url, "titulo": titulo, "extracto": _texto_plano(str(n.get("resumen") or "")),
                      "publicado_en": _fecha(n.get("fecha")), "pais": n.get("pais")})
    return notas, descartadas


def _cuantas(n: int) -> str:
    return "1 nota" if n == 1 else f"{n} notas"


def guardar_notas(bd: Session, reporte: RadarReporte, notas: list[dict], *, origen: str,
                  fuente_id: int | None = None, tema_id: int | None = None) -> int:
    """Guarda las notas que no se habían visto. Devuelve cuántas fueron nuevas."""
    cfg = configuracion()
    limite = hoy_local() - timedelta(days=cfg.radar_ventana_dias)
    hace_un_mes = ahora() - timedelta(days=30)
    nuevas = 0
    for n in notas:
        url = n["url"].strip()[:1000]
        url_hash = _hash(_clave_url(url))
        t_hash = _titulo_hash(n["titulo"])
        if bd.scalar(select(RadarArticulo.articulo_id).where(RadarArticulo.url_hash == url_hash)):
            continue
        if bd.scalar(select(RadarArticulo.articulo_id).where(RadarArticulo.titulo_hash == t_hash,
                                                              RadarArticulo.leido_en >= hace_un_mes)):
            continue
        publicado = n.get("publicado_en")
        if publicado and publicado > hoy_local():
            publicado = hoy_local()
        en_ventana = publicado >= limite if publicado else origen == "lista"
        try:
            with bd.begin_nested():
                bd.add(RadarArticulo(reporte_id=reporte.reporte_id, fuente_id=fuente_id, tema_id=tema_id,
                                     origen=origen, url=url, url_hash=url_hash, titulo_hash=t_hash,
                                     sitio=sitio_de(url)[:200], titulo=n["titulo"][:500], extracto=n.get("extracto"),
                                     publicado_en=publicado, en_ventana=en_ventana, pais=(n.get("pais") or None)))
        except IntegrityError:  # la misma liga ya la guardó otra corrida al mismo tiempo
            continue
        nuevas += 1
    bd.commit()
    return nuevas


def leer_fuentes(bd: Session, reporte: RadarReporte, avisos: list[str]) -> None:
    cfg = configuracion()
    desde = hoy_local() - timedelta(days=cfg.radar_ventana_dias)
    api_apagada = puerta.motivos_api_apagada(bd)
    busquedas_restantes = cfg.radar_busquedas_por_dia

    fuentes = bd.scalars(select(RadarFuente).where(RadarFuente.activa).order_by(RadarFuente.fuente_id)).all()
    for f in (x for x in fuentes if x.metodo == "rss" and x.lectura):
        try:
            notas = leer_rss(f.lectura)
            nuevas = guardar_notas(bd, reporte, notas, origen="lista", fuente_id=f.fuente_id)
            f.ultimo_resultado = f"Bien: {_cuantas(len(notas))} en el RSS, {nuevas} sin ver antes."
            f.ultimos_articulos = nuevas
            reporte.fuentes_leidas += 1
        except ErrorRadar as e:
            f.ultimo_resultado = f"Error: {e}"[:300]
            f.ultimos_articulos = 0
            reporte.fuentes_con_error += 1
        f.ultima_lectura_en = ahora()
        bd.commit()

    # Sitios sin RSS: una búsqueda por tipo de fuente, limitada a sus sitios
    por_tipo: dict[str, list[RadarFuente]] = {}
    for f in (x for x in fuentes if x.metodo == "busqueda" and x.lectura):
        por_tipo.setdefault(f.tipo, []).append(f)
    if por_tipo and api_apagada:
        avisos.append("No se buscó en los sitios sin RSS ni en internet porque la API externa está apagada: "
                      + " ".join(api_apagada))
    temas = bd.scalars(select(RadarTema).where(RadarTema.activo).order_by(RadarTema.orden, RadarTema.tema_id)).all()
    if api_apagada:
        return

    nombres_tipo = {"oficial": "dependencias oficiales", "especializada": "medios especializados",
                    "negocios": "medios de negocios", "estudios": "empresas de estudios de mercado"}
    for tipo, grupo in por_tipo.items():
        if busquedas_restantes <= 0:
            avisos.append("Se llegó al límite de búsquedas por día; quedaron sitios sin revisar.")
            break
        busquedas_restantes -= 1
        dominios = sorted({d.strip() for f in grupo for d in (f.lectura or "").split(",") if d.strip()})
        consulta = (f"Notas de {nombres_tipo.get(tipo, tipo)} ({', '.join(f.nombre for f in grupo)}) sobre suplementos, "
                    "productos naturistas, ingredientes, bienestar, nutrición, regulación sanitaria y consumo.")
        try:
            notas, descartadas = buscar_con_ia(bd, consulta, desde, dominios)
            reporte.busquedas += 1
            for f in grupo:
                propias = [n for n in notas if any(sitio_de(n["url"]).endswith(d) for d in (f.lectura or "").split(","))]
                nuevas = guardar_notas(bd, reporte, propias, origen="lista", fuente_id=f.fuente_id)
                f.ultimo_resultado = f"Bien: {_cuantas(len(propias))} en la búsqueda, {nuevas} sin ver antes."
                f.ultimos_articulos = nuevas
                f.ultima_lectura_en = ahora()
                reporte.fuentes_leidas += 1
            if descartadas:
                avisos.append(f"Se descartaron {descartadas} ligas de {nombres_tipo.get(tipo, tipo)} que no se pudieron verificar.")
        except (puerta.ErrorIA, ValueError) as e:
            for f in grupo:
                f.ultimo_resultado = f"Error: {e}"[:300]
                f.ultima_lectura_en = ahora()
            reporte.fuentes_con_error += len(grupo)
            avisos.append(f"Falló la búsqueda en {nombres_tipo.get(tipo, tipo)}: {e}")
        bd.commit()

    for t in temas:
        if busquedas_restantes <= 0:
            avisos.append("Se llegó al límite de búsquedas por día; quedaron temas sin buscar.")
            break
        busquedas_restantes -= 1
        try:
            notas, descartadas = buscar_con_ia(bd, f"{t.nombre}. {t.descripcion}", desde)
            reporte.busquedas += 1
            guardar_notas(bd, reporte, notas, origen="busqueda", tema_id=t.tema_id)
            if descartadas:
                avisos.append(f"En el tema «{t.nombre}» se descartaron {descartadas} ligas que no se pudieron verificar.")
        except (puerta.ErrorIA, ValueError) as e:
            avisos.append(f"Falló la búsqueda del tema «{t.nombre}»: {e}")
        bd.commit()


# ---------------------------------------------------------------- IA: clasificar y resumir

INSTRUCCIONES_CLASIFICAR = f"""{CONTEXTO_SMN}

Para cada nota decide si es relevante para Compras de SMN y clasifícala.
- relevante: true solo si habla de suplementos, productos naturistas, ingredientes, alimentos funcionales,
  bienestar, proveedores o fabricantes del sector, regulación sanitaria aplicable o consumo de estos productos.
- categoria: una de {", ".join(CATEGORIAS)}.
- nivel: ALTA (evidencia fuerte o movimiento importante), MEDIA (señal relevante para vigilar) o TEMPRANA (primera evidencia).
- area: el área de producto a la que le toca, en pocas palabras (p. ej. "Suplementos deportivos", "Herbolaria").
- pais: MX, EUA, UE o global, según de dónde es la noticia.
- por_que: una línea sobre por qué importa a SMN (vacío si no es relevante).
{REGLAS}

Formato: {{"notas": [{{"id": 1, "relevante": true, "categoria": "INGREDIENTE", "nivel": "MEDIA", "area": "...", "pais": "EUA", "por_que": "..."}}]}}"""


def clasificar(bd: Session, reporte: RadarReporte, avisos: list[str]) -> None:
    pendientes = bd.scalars(select(RadarArticulo).where(
        RadarArticulo.reporte_id == reporte.reporte_id, RadarArticulo.en_ventana,
        RadarArticulo.clasificado_en.is_(None)).order_by(RadarArticulo.articulo_id)).all()
    lotes = [pendientes[i:i + POR_LOTE] for i in range(0, len(pendientes), POR_LOTE)]
    while lotes:
        lote = lotes.pop(0)
        mensaje = json.dumps([{"id": a.articulo_id, "titulo": a.titulo, "extracto": a.extracto or "",
                               "sitio": a.sitio, "fecha": a.publicado_en.isoformat() if a.publicado_en else None}
                              for a in lote], ensure_ascii=False)
        try:
            r = puerta.ejecutar(bd, "compras.radar_clasificar", usuario_id=None, instrucciones=INSTRUCCIONES_CLASIFICAR,
                                mensaje=mensaje, max_tokens=4000, esfuerzo="low")
            por_id = {int(x["id"]): x for x in (_json_de(r.texto).get("notas") or []) if str(x.get("id", "")).isdigit()}
        except (ValueError, TypeError, KeyError) as e:
            # La IA a veces devuelve JSON mal formado: se reintenta en dos mitades antes de rendirse
            if len(lote) > 1:
                mitad = len(lote) // 2
                lotes[:0] = [lote[:mitad], lote[mitad:]]
                continue
            avisos.append(f"No se pudieron clasificar {len(lote)} notas: {e}")
            continue
        except puerta.ErrorIA as e:
            avisos.append(f"No se pudieron clasificar {len(lote)} notas: {e}")
            continue
        for a in lote:
            x = por_id.get(a.articulo_id)
            if not x:
                continue
            a.relevante = bool(x.get("relevante"))
            a.categoria = str(x.get("categoria") or "").upper()[:40] if x.get("categoria") else None
            a.nivel = x.get("nivel") if x.get("nivel") in NIVELES else None
            a.departamento = (str(x.get("area") or "")[:80]) or None
            a.pais = (str(x.get("pais") or "")[:20]) or a.pais
            a.por_que = (str(x.get("por_que") or "")[:600]) or None
            a.clasificado_en = ahora()
        bd.commit()


def contexto_conocimiento(bd: Session, maximo: int = 24000) -> str:
    docs = bd.scalars(select(RadarDocumento).where(RadarDocumento.activo, RadarDocumento.caracteres > 0)
                      .order_by(RadarDocumento.subido_en.desc())).all()
    partes, total = [], 0
    for d in docs:
        porcion = min(len(d.texto or ""), max(0, maximo - total), 6000)
        if porcion <= 0:
            break
        partes.append(f"## {d.titulo}\n{(d.texto or '')[:porcion]}")
        total += porcion
    return "\n\n".join(partes)


def ultimas_decisiones(bd: Session, senal_ids: list[int]) -> dict[int, str]:
    """Último comentario de Compras por señal (motivo de su decisión más reciente que tenga motivo)."""
    if not senal_ids:
        return {}
    notas: dict[int, str] = {}
    for a in bd.scalars(select(RadarAccion).where(RadarAccion.senal_id.in_(senal_ids), RadarAccion.motivo.is_not(None))
                        .order_by(RadarAccion.ocurrido_en.desc())):
        notas.setdefault(a.senal_id, a.motivo[:300])
    return notas


def instrucciones_resumen(maximo: int) -> str:
    return f"""{CONTEXTO_SMN}

Te doy las notas relevantes de hoy y las señales que el radar ya sigue. Arma el reporte del día:
- Agrupa las notas que hablan de lo mismo. Si una nota encaja con una señal que ya existe, usa su senal_id.
- Elige como máximo {maximo} hallazgos, los más importantes para Compras; prioriza variedad.
- Cada hallazgo cita los ids de las notas que lo respaldan (solo ids de la lista de hoy).
- titulo: ejecutivo, en español. por_que: 2 o 3 líneas sobre qué pasa y por qué le importa a SMN.
- categoria: una de {", ".join(CATEGORIAS)}. nivel: ALTA, MEDIA o TEMPRANA. area: área de producto.
- resumen: 2 o 3 líneas sobre lo más importante del día.
- radar_ejecutivo: hasta 4 líneas cortas sobre hacia dónde se mueve el mercado según las notas y las señales.
- Si te doy una base de conocimiento de SMN, menciona en por_que cuando un hallazgo confirme algo de ahí.
- Toma en cuenta lo que ya decidió Compras (decision_de_compras: nueva = sin decidir, vigilar = la están
  vigilando, iniciativa = ya abrieron una iniciativa; nota_de_compras es su comentario):
  - Si hay novedades de una señal en vigilancia o con iniciativa, dale prioridad y di qué cambió.
  - No propongas algo parecido a descartadas_por_compras. Solo inclúyelo si las notas de hoy traen algo
    claramente nuevo que cambie el motivo del descarte, y dilo en por_que.
{REGLAS}

Formato: {{"resumen": "...", "hallazgos": [{{"titulo": "...", "por_que": "...", "categoria": "...", "nivel": "...", "area": "...", "senal_id": null, "notas": [1, 2]}}], "radar_ejecutivo": ["..."]}}"""


def _es_tendencia(senal: RadarSenal, articulos: list[RadarArticulo]) -> tuple[bool, int, str]:
    sitios = {a.sitio for a in articulos}
    paises = sorted({(a.pais or "").upper() for a in articulos if a.pais})
    tendencia = len(sitios) >= 2 or ("EUA" in paises and "MX" in paises)
    return tendencia, len(sitios), ", ".join(paises)[:60]


def resumir(bd: Session, reporte: RadarReporte, avisos: list[str]) -> None:
    cfg = configuracion()
    relevantes = bd.scalars(select(RadarArticulo).where(
        RadarArticulo.reporte_id == reporte.reporte_id, RadarArticulo.relevante == true())
        .order_by(RadarArticulo.publicado_en.desc())).all()
    reporte.articulos_relevantes = len(relevantes)
    if not relevantes:
        reporte.resumen = "Hoy no hubo notas nuevas relevantes en las fuentes revisadas."
        return
    hace_tiempo = hoy_local() - timedelta(days=45)
    vivas = bd.scalars(select(RadarSenal).where(RadarSenal.ultima_vez >= hace_tiempo,
                                                RadarSenal.estado != "descartada")
                       .order_by(RadarSenal.ultima_vez.desc()).limit(60)).all()
    descartadas = bd.scalars(select(RadarSenal).where(RadarSenal.estado == "descartada",
                                                      RadarSenal.ultima_vez >= hoy_local() - timedelta(days=180))
                             .order_by(RadarSenal.ultima_vez.desc()).limit(40)).all()
    decisiones = ultimas_decisiones(bd, [s.senal_id for s in [*vivas, *descartadas]])
    mensaje = {
        "fecha": hoy_local().isoformat(),
        "notas": [{"id": a.articulo_id, "titulo": a.titulo, "extracto": a.extracto or "", "sitio": a.sitio,
                   "fecha": a.publicado_en.isoformat() if a.publicado_en else None, "pais": a.pais,
                   "categoria": a.categoria, "nivel": a.nivel, "por_que": a.por_que} for a in relevantes[:80]],
        "senales_existentes": [{"senal_id": s.senal_id, "titulo": s.titulo, "tipo": s.tipo,
                                "desde": s.primera_vez.isoformat(), "decision_de_compras": s.estado,
                                "nota_de_compras": decisiones.get(s.senal_id)} for s in vivas],
        "descartadas_por_compras": [{"titulo": s.titulo, "motivo": decisiones.get(s.senal_id)} for s in descartadas],
    }
    texto = json.dumps(mensaje, ensure_ascii=False)
    if conocimiento := contexto_conocimiento(bd):
        texto += "\n\nBase de conocimiento de SMN (documentos que subió Compras):\n" + conocimiento
    r = puerta.ejecutar(bd, "compras.radar_resumen", usuario_id=None,
                        instrucciones=instrucciones_resumen(cfg.radar_max_hallazgos), mensaje=texto,
                        max_tokens=8000, esfuerzo="medium")
    datos = _json_de(r.texto)

    por_id = {a.articulo_id: a for a in relevantes}
    senales_por_id = {s.senal_id: s for s in vivas}
    bd.execute(RadarHallazgo.__table__.delete().where(RadarHallazgo.reporte_id == reporte.reporte_id))
    orden = 0
    usadas: set[int] = set()
    for h in (datos.get("hallazgos") or []):
        if orden >= cfg.radar_max_hallazgos:
            break
        notas = [por_id[i] for i in (h.get("notas") or []) if isinstance(i, int) and i in por_id]
        if not notas or not h.get("titulo"):
            continue  # un hallazgo sin notas de respaldo no sale
        nivel = h.get("nivel") if h.get("nivel") in NIVELES else (notas[0].nivel or "TEMPRANA")
        senal = senales_por_id.get(h.get("senal_id")) if isinstance(h.get("senal_id"), int) else None
        if senal and senal.senal_id in usadas:
            continue
        if not senal:
            senal = RadarSenal(titulo=str(h["titulo"])[:300], nivel=nivel, primera_vez=hoy_local(),
                               ultima_vez=hoy_local(), estado="nueva")
            bd.add(senal)
            bd.flush()
        senal.descripcion = str(h.get("por_que") or "")[:1000] or senal.descripcion
        senal.nivel = nivel
        senal.categoria = str(h.get("categoria") or senal.categoria or "")[:40] or None
        senal.departamento = str(h.get("area") or senal.departamento or "")[:80] or None
        senal.ultima_vez = hoy_local()
        senal.veces_reportada += 1
        ya = set(bd.scalars(select(RadarSenalArticulo.articulo_id).where(RadarSenalArticulo.senal_id == senal.senal_id)))
        for a in notas:
            if a.articulo_id not in ya:
                bd.add(RadarSenalArticulo(senal_id=senal.senal_id, articulo_id=a.articulo_id))
        bd.flush()
        todos = bd.scalars(select(RadarArticulo).join(
            RadarSenalArticulo, RadarSenalArticulo.articulo_id == RadarArticulo.articulo_id)
            .where(RadarSenalArticulo.senal_id == senal.senal_id)).all()
        tendencia, sitios, paises = _es_tendencia(senal, list(todos))
        senal.tipo = "tendencia" if tendencia else "emergente"
        senal.sitios_distintos = sitios
        senal.paises = paises or None
        orden += 1
        usadas.add(senal.senal_id)
        bd.add(RadarHallazgo(reporte_id=reporte.reporte_id, senal_id=senal.senal_id, orden=orden,
                             titulo=str(h["titulo"])[:300], por_que=str(h.get("por_que") or "")[:1000],
                             nivel=nivel, tipo=senal.tipo, departamento=senal.departamento, paises=senal.paises))
    reporte.resumen = str(datos.get("resumen") or "")[:4000] or None
    lineas = [str(x)[:400] for x in (datos.get("radar_ejecutivo") or []) if x][:4]
    reporte.radar_ejecutivo = json.dumps(lineas, ensure_ascii=False) if lineas else None
    bd.commit()


# ---------------------------------------------------------------- correo

def _liga(ruta: str) -> str:
    return f"{configuracion().web_url.rstrip('/')}{ruta}"


def cuerpo_correo(bd: Session, reporte: RadarReporte, con_decisiones: bool = True) -> tuple[str, str]:
    """(html, texto) del reporte para el correo. Todo lo que viene de fuera se escapa.
    Sin decisiones es la versión informativa: mismo contenido, sin botones de decisión ni liga a la plataforma."""
    e = html.escape
    filas_html, filas_texto = [], []
    for h in reporte.hallazgos:
        articulos = bd.scalars(select(RadarArticulo).join(
            RadarSenalArticulo, RadarSenalArticulo.articulo_id == RadarArticulo.articulo_id)
            .where(RadarSenalArticulo.senal_id == h.senal_id, RadarArticulo.reporte_id == reporte.reporte_id)
            .order_by(RadarArticulo.publicado_en.desc())).all()
        fuentes = "".join(
            f'<div style="margin:4px 0;font-size:13px">• <a href="{e(a.url)}" style="color:{NEGRO}">{e(a.titulo)}</a>'
            f' <span style="color:#77776f">({e(a.sitio)}{", " + a.publicado_en.strftime("%d/%m/%Y") if a.publicado_en else ""})</span></div>'
            for a in articulos)
        etiqueta = "Tendencia" if h.tipo == "tendencia" else "Señal emergente"
        boton = (lambda texto, accion, fondo, color: f'<a href="{e(_liga(f"/compras/radar/senal/{h.senal_id}?accion={accion}"))}" '
                 f'style="display:inline-block;margin:4px 6px 0 0;padding:8px 14px;border-radius:10px;font-size:13px;'
                 f'font-weight:800;text-decoration:none;background:{fondo};color:{color}">{texto}</a>')
        filas_html.append(
            f'<div style="border:1px solid #e7e7e2;border-radius:14px;padding:16px;margin:0 0 14px">'
            f'<div style="font-size:11px;font-weight:800;letter-spacing:.06em;color:#77776f;text-transform:uppercase">'
            f'#{h.orden:02d} · <span style="color:{NARANJA}">{e(h.nivel)}</span> · {etiqueta}'
            f'{" · " + e(h.departamento) if h.departamento else ""}{" · " + e(h.paises) if h.paises else ""}</div>'
            f'<div style="font-size:16px;font-weight:800;margin:6px 0 8px">{e(h.titulo)}</div>'
            f'<div style="font-size:14px;line-height:1.55;margin:0 0 8px">{e(h.por_que)}</div>{fuentes}'
            + (f'<div style="margin-top:10px">{boton("Abrir iniciativa", "iniciativa", NARANJA, NEGRO)}'
               f'{boton("Vigilar", "vigilar", "#f3f3f0", NEGRO)}{boton("Descartar", "descartar", "#f3f3f0", "#77776f")}</div>'
               if con_decisiones else "")
            + '</div>')
        filas_texto.append(f"#{h.orden:02d} {h.nivel} · {etiqueta}\n{h.titulo}\n{h.por_que}\n"
                           + "\n".join(f"- {a.titulo} ({a.url})" for a in articulos))
    ejecutivo = json.loads(reporte.radar_ejecutivo) if reporte.radar_ejecutivo else []
    if ejecutivo:
        filas_html.append(
            f'<div style="background:{NEGRO};color:#fff;border-radius:14px;padding:16px;margin:4px 0 14px">'
            f'<div style="font-size:11px;font-weight:800;letter-spacing:.06em;color:{NARANJA};text-transform:uppercase">Radar ejecutivo</div>'
            + "".join(f'<div style="font-size:14px;line-height:1.5;margin-top:6px">• {e(x)}</div>' for x in ejecutivo)
            + "</div>")
        filas_texto.append("Radar ejecutivo:\n" + "\n".join(f"- {x}" for x in ejecutivo))
    if con_decisiones:  # el informativo no lleva ligas a la plataforma
        filas_html.append(
            f'<p style="margin:18px 0"><a href="{e(_liga(f"/compras/radar?fecha={reporte.fecha.isoformat()}"))}" '
            f'style="background:{NARANJA};color:{NEGRO};text-decoration:none;font-weight:800;padding:12px 22px;'
            f'border-radius:12px;display:inline-block">Ver en la plataforma</a></p>')
    return "".join(filas_html), "\n\n".join(filas_texto)


def enviar_reporte(bd: Session, reporte: RadarReporte, solo_a: str | None = None) -> tuple[int, int]:
    """Manda el reporte. Devuelve (enviados, fallidos)."""
    versiones = {tipo: cuerpo_correo(bd, reporte, con_decisiones=tipo == "decision") for tipo in ("decision", "informativo")}
    fecha = reporte.fecha.strftime("%d/%m/%Y")
    parrafos = [reporte.resumen or "Reporte del día."]
    parrafos.append(f"{reporte.fuentes_leidas} fuentes revisadas · {reporte.articulos_nuevos} notas nuevas · "
                    f"{reporte.articulos_relevantes} relevantes · {len(reporte.hallazgos)} hallazgos.")
    nota = ("Información pública resumida con IA a partir de las fuentes citadas. Revisa la fuente antes de decidir; "
            "no sustituye una evaluación regulatoria ni médica.")
    # "Enviármelo" lo pide alguien que puede decidir: va con botones
    para = [(solo_a, "decision")] if solo_a else [
        (d.correo, d.tipo_correo) for d in bd.scalars(select(RadarDestinatario).where(RadarDestinatario.activo))]
    enviados = fallidos = 0
    for correo, tipo in para:
        cuerpo, texto = versiones.get(tipo, versiones["decision"])
        if enviar(correo, f"Radar de tendencias · {fecha}", f"Radar de tendencias · {fecha}", parrafos, nota=nota,
                  cuerpo_html=cuerpo, texto_extra=texto, ancho=640):
            enviados += 1
        else:
            fallidos += 1
    return enviados, fallidos


# ---------------------------------------------------------------- corrida

def _administradores(bd: Session) -> list[int]:
    return list(bd.scalars(
        select(Usuario.usuario_id).distinct()
        .join(UsuarioRol, UsuarioRol.usuario_id == Usuario.usuario_id)
        .join(RolPermiso, RolPermiso.rol_id == UsuarioRol.rol_id)
        .join(Permiso, Permiso.permiso_id == RolPermiso.permiso_id)
        .where(Permiso.codigo == ADMINISTRAR, Usuario.estatus == "activo")))


def tomar_reporte(bd: Session, fecha: date, origen: str, usuario_id: int | None = None,
                  forzar: bool = False) -> RadarReporte | None:
    """Reserva la corrida del día. Devuelve None si otra ya corre o ya terminó (y no se forzó).
    Con varias copias de la API, la fecha única de radar_reporte evita que corran dos a la vez."""
    existente = bd.scalar(select(RadarReporte).where(RadarReporte.fecha == fecha))
    if not existente:
        r = RadarReporte(fecha=fecha, origen=origen, iniciado_por=usuario_id, estado="en_curso")
        bd.add(r)
        try:
            bd.commit()
        except IntegrityError:
            bd.rollback()
            return None
        return r
    atorado = existente.estado == "en_curso" and existente.iniciado_en < ahora() - timedelta(hours=3)
    if existente.estado == "en_curso" and not atorado:
        return None
    if existente.estado == "listo" and not forzar:
        return None
    # Reintento (error, atorado o corrida manual): solo gana quien cambie la fila primero
    cambio = bd.execute(update(RadarReporte).where(
        RadarReporte.reporte_id == existente.reporte_id, RadarReporte.estado == existente.estado,
        RadarReporte.intentos == existente.intentos,
    ).values(estado="en_curso", origen=origen, iniciado_en=ahora(), terminado_en=None, iniciado_por=usuario_id,
             intentos=existente.intentos + 1, error=None))
    bd.commit()
    if cambio.rowcount != 1:
        return None
    bd.refresh(existente)
    return existente


def correr(bd: Session, reporte: RadarReporte, enviar_correo: bool = True) -> RadarReporte:
    """Corre todos los pasos sobre un reporte ya reservado. Nunca lanza: los errores quedan en el reporte."""
    avisos: list[str] = []
    reporte.fuentes_leidas = reporte.fuentes_con_error = reporte.busquedas = 0
    bd.commit()
    try:
        leer_fuentes(bd, reporte, avisos)
        reporte.articulos_nuevos = bd.scalar(select(func.count()).select_from(RadarArticulo)
                                             .where(RadarArticulo.reporte_id == reporte.reporte_id)) or 0
        bd.commit()
        clasificar(bd, reporte, avisos)
        sin_ia = False
        try:
            resumir(bd, reporte, avisos)
        except (puerta.ErrorIA, ValueError, TypeError, KeyError) as e:
            bd.rollback()
            sin_ia = True
            avisos.append(f"No se pudo armar el reporte con IA: {e}")
            reporte.resumen = ("Hoy no se pudo usar la IA para analizar las notas. Las notas nuevas quedaron guardadas "
                               "en el histórico de la plataforma.")
        reporte.avisos = json.dumps(avisos, ensure_ascii=False) if avisos else None
        reporte.estado = "listo"
        reporte.terminado_en = ahora()
        bd.commit()
        bd.refresh(reporte)
        if sin_ia:
            # Sin IA no hay reporte que valga la pena mandar: se avisa a quien administra y se puede reenviar a mano
            modulo = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "compras"))
            for admin in _administradores(bd):
                notificar(bd, admin, "Radar de tendencias sin IA",
                          f"El reporte del {reporte.fecha:%d/%m/%Y} no se armó y no se envió a los destinatarios. "
                          "Revisa los avisos de la corrida.", liga="/compras/radar/corridas", modulo_id=modulo,
                          clave=f"radar-sin-ia:{reporte.fecha}:{reporte.intentos}")
            bd.commit()
        elif enviar_correo:
            reporte.correos_enviados, reporte.correos_fallidos = enviar_reporte(bd, reporte)
            bd.commit()
    except Exception as e:  # noqa: BLE001 - la corrida automática no debe tumbar la API
        log.exception("Falló el radar de tendencias")
        bd.rollback()
        reporte.estado = "error"
        reporte.error = str(e)[:1000] or e.__class__.__name__
        reporte.avisos = json.dumps(avisos, ensure_ascii=False) if avisos else None
        reporte.terminado_en = ahora()
        modulo = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "compras"))
        for admin in _administradores(bd):
            notificar(bd, admin, "Falló el Radar de tendencias",
                      f"La corrida del {reporte.fecha:%d/%m/%Y} falló: {reporte.error[:300]}. Se reintenta sola.",
                      liga="/compras/radar/corridas", modulo_id=modulo,
                      clave=f"radar-error:{reporte.fecha}:{reporte.intentos}")
        bd.commit()
    return reporte


# ---------------------------------------------------------------- programación

MAX_INTENTOS = 3


DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def _dias_semana() -> set[int]:
    return {int(d) for d in (configuracion().radar_dias_semana or "").split(",") if d.strip().isdigit()} or set(range(1, 8))


def _ultima_buena(bd: Session) -> date | None:
    return bd.scalar(select(func.max(RadarReporte.fecha)).where(RadarReporte.estado == "listo"))


def toca(bd: Session, fecha: date, ultima_buena: date | None = None) -> bool:
    """¿Este día le toca corrida automática según la frecuencia configurada?"""
    cfg = configuracion()
    if cfg.radar_frecuencia == "dias":
        return fecha.isoweekday() in _dias_semana()
    if cfg.radar_frecuencia == "cada_n":
        ultima = ultima_buena if ultima_buena is not None else _ultima_buena(bd)
        return ultima is None or ultima >= fecha or (fecha - ultima).days >= max(cfg.radar_cada_dias, 1)
    return True


def texto_frecuencia() -> str:
    cfg = configuracion()
    if cfg.radar_frecuencia == "dias":
        dias = sorted(_dias_semana())
        if dias == [1, 2, 3, 4, 5]:
            return "De lunes a viernes"
        return "Todos los días" if len(dias) == 7 else ", ".join(DIAS[d - 1] for d in dias)
    if cfg.radar_frecuencia == "cada_n":
        return f"Cada {cfg.radar_cada_dias} días"
    return "Todos los días"


def proxima_corrida(bd: Session) -> datetime:
    cfg = configuracion()
    ahora_local = datetime.now(zona())
    hoy_hora = ahora_local.replace(hour=cfg.radar_hora, minute=0, second=0, microsecond=0)
    ultima = _ultima_buena(bd)
    hoy = ahora_local.date()
    ya_hoy = bd.scalar(select(RadarReporte.reporte_id).where(RadarReporte.fecha == hoy)) is not None
    for n in range(0, 60):
        dia = hoy_hora + timedelta(days=n)
        if n == 0 and ya_hoy:  # una corrida por día: hoy ya hubo
            continue
        if toca(bd, dia.date(), ultima):
            return dia
    return hoy_hora + timedelta(days=1)


def revisar_programa(bd: Session) -> RadarReporte | None:
    """Lo llama el programador cada minuto. Corre el radar del día si ya es la hora y no ha corrido.
    Si la plataforma estuvo apagada a la hora, corre en cuanto vuelve (marcado como tardío).
    Si falla, reintenta cada 30 minutos hasta 3 veces."""
    cfg = configuracion()
    if not cfg.radar_activo:
        return None
    ahora_local = datetime.now(zona())
    if ahora_local.hour < cfg.radar_hora:
        return None
    fecha = ahora_local.date()
    existente = bd.scalar(select(RadarReporte).where(RadarReporte.fecha == fecha))
    if not existente and not toca(bd, fecha):
        return None
    if existente and existente.estado == "error":
        if existente.intentos >= MAX_INTENTOS or (existente.terminado_en or ahora()) > ahora() - timedelta(minutes=30):
            return None
    origen = "programado" if ahora_local.hour == cfg.radar_hora else "tardio"
    reporte = tomar_reporte(bd, fecha, origen)
    if not reporte:
        return None
    log.info("Radar de tendencias: corrida %s del %s", origen, fecha)
    return correr(bd, reporte)
