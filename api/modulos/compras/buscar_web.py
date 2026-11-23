"""Buscar en internet sin API externa (Diego, 18 nov 2026; plan https://claude.ai/artifact/RHCo6njb6SqZvLUfeMF2sB).

DataForSEO trae los resultados de Google México y la IA local (Ollama) solo propone qué buscar y lee lo que llega. Lo
usan el radar de noticias (notas de sitios sin RSS y de los temas) y «Buscar oportunidades» (los más vendidos).
Nada cuenta si no salió de Google; en los más vendidos, la prueba de venta además debe estar escrita en la página.

Gasto: cada búsqueda queda como corrida «web» del radar de precios (cuenta para su tope del mes) y además tiene su
propio tope al mes (`busqueda_web_tope_usd`, US$ 2 por omisión)."""
import json
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import configuracion
from ia import puerta
from modulos.compras import dataforseo as dfs
from modulos.compras import investigar as iv
from modulos.compras import precios as pc
from modulos.compras.modelos_precios import PrecioCorrida, PrecioEnvio
from nucleo.modelos import IaTarea, ahora

log = logging.getLogger("smn.compras.buscar_web")

ORIGEN = pc.WEB
MAX_CONSULTAS = 3  # frases de búsqueda por tema
MAX_PAGINAS = 5  # páginas que se leen por tema (más vendidos)
A_LA_VEZ = 2  # temas a la vez con Ollama, para no frenar al resto de la plataforma
MAX_TEXTO = 6000  # letras de cada página que lee la IA


@dataclass
class Resultado:
    url: str
    titulo: str
    descripcion: str
    consulta: str
    fecha: date | None = None
    dominio: str = ""


@dataclass
class Busqueda:
    resultados: list[Resultado] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    costo_usd: Decimal = Decimal("0")


def usar_web(bd: Session, tarea: str) -> bool:
    """La tarea busca con DataForSEO + Ollama salvo que en Administración > IA siga marcada como «api»."""
    t = bd.scalar(select(IaTarea).where(IaTarea.codigo == tarea))
    return not t or t.proveedor_ia != "api"


# ---------------------------------------------------------------- gasto

def tope() -> Decimal:
    return Decimal(str(configuracion().busqueda_web_tope_usd))


def gasto_mes(bd: Session) -> Decimal:
    web = select(PrecioCorrida.corrida_id).where(PrecioCorrida.origen == ORIGEN)
    return dfs._gastado(bd, (PrecioEnvio.creado_en >= dfs.inicio_de_mes()) & PrecioEnvio.corrida_id.in_(web))


# ---------------------------------------------------------------- Google por DataForSEO

def _fecha(item: dict) -> date | None:
    valor = str(item.get("timestamp") or item.get("time_published") or "")[:10]
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def _dominio(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def dominios_propios() -> list[str]:
    """Nuestra tienda en línea y sitios propios (Configuración → Radar de precios)."""
    propios = [d.strip().lower().removeprefix("www.") for d in configuracion().precios_dominios_propios.split(",")]
    return [d for d in dict.fromkeys(propios + ["supernaturista.com"]) if d]


def es_propio(dominio: str) -> bool:
    """Diego, 18 nov 2026: Google regresó páginas de supernaturista.com y salieron como «más vendido en internet»."""
    d = dominio.lower()
    return "supernaturista" in d or any(d == p or d.endswith("." + p) for p in dominios_propios())


def google(bd: Session, consultas: list[str], tipo: str, referencia: str, profundidad: int = 10) -> Busqueda:
    """Resultados de Google México de cada consulta. tipo: «noticias» (Google Noticias, trae fecha) u «organico».
    Nunca lanza: lo que falla queda en las notas."""
    b = Busqueda()
    consultas = [c for c in dict.fromkeys(" ".join(str(c).split())[:300] for c in consultas) if c][:MAX_CONSULTAS]
    if not consultas:
        return b
    if falta := dfs.configurado():
        b.notas.append("No se buscó en internet: falta " + ", ".join(falta) + " en Configuración.")
        return b
    maximo = dfs.maximo_tarea(tipo, profundidad) * len(consultas)
    if gasto_mes(bd) + maximo > tope():
        b.notas.append(f"No se buscó en internet: se llegó al tope del mes para buscar en internet (US$ {tope():.2f}).")
        return b
    if tipo == "organico":  # nuestras propias páginas no le dicen nada a Compras: ni se piden
        quitar = " ".join(f"-site:{d}" for d in dominios_propios())
        consultas = [f"{c} {quitar}" for c in consultas]
    corrida = PrecioCorrida(fecha=pc.hoy_local(), origen=ORIGEN, estado="en_curso", productos=0,
                            lista=json.dumps({"buscar": referencia, "consultas": consultas}, ensure_ascii=False))
    bd.add(corrida)
    bd.commit()
    tipos = ("news_search",) if tipo == "noticias" else ("organic",)
    try:
        ids = dfs.enviar(bd, corrida, tipo, [{"keyword": c, "depth": profundidad, "tag": str(i)}
                                             for i, c in enumerate(consultas)])
        for tag, items in dfs.recoger(tipo, ids).items():
            if isinstance(items, str):
                b.notas.append(f"Google: {items}.")
                continue
            for it in items:
                url = str(it.get("url") or "")
                if it.get("type") in tipos and url.startswith(("http://", "https://")) and not es_propio(_dominio(url)):
                    b.resultados.append(Resultado(url=url, titulo=str(it.get("title") or "")[:300],
                                                  descripcion=str(it.get("description") or it.get("snippet") or "")[:500],
                                                  consulta=consultas[int(tag)], fecha=_fecha(it), dominio=_dominio(url)))
        corrida.estado = "completa"
    except dfs.ErrorDataForSEO as e:
        b.notas.append(f"Google: {e}")
        corrida.estado, corrida.error = "fallida", str(e)[:1000]
    corrida.terminado_en = ahora()
    b.costo_usd = corrida.costo_usd or Decimal("0")
    bd.commit()
    return b


def elegir(resultados: list[Resultado], maximo: int = MAX_PAGINAS) -> list[Resultado]:
    """Páginas de sitios distintos, en el orden en que Google las dio, alternando las consultas."""
    elegidas = iv._elegir_paginas([{"url": r.url, "titulo": r.titulo, "consulta": r.consulta, "r": r} for r in resultados])
    return [e["r"] for e in elegidas[:maximo]]


# ---------------------------------------------------------------- páginas e IA local

def leer(url: str) -> str | None:
    """Texto legible de la página, o None si no se deja leer (Mercado Libre y Amazon casi nunca)."""
    html = iv.bajar(url)
    return iv.texto_de(html) if html else None


def recorte(texto: str, palabras: str) -> str:
    return iv._recorte(texto, {p for p in iv._limpio(palabras).split() if len(p) > 3})[:MAX_TEXTO]


def palabras(texto: str | None) -> list[str]:
    """Las palabras del texto sin acentos, mayúsculas ni signos."""
    return re.findall(r"[a-z0-9ñ]+", iv._limpio(texto))


def cita_ok(cita: str | None, texto: str) -> bool:
    """La frase que la IA copió está de verdad en la página, sin importar acentos, mayúsculas ni signos. Se perdona que
    la IA cambie o se salte alguna palabra: basta con que el 70 % de la frase (2 palabras o más) esté seguido en la página.
    Diego, 18 nov 2026: con la comparación exacta se quitaron casi todos (un punto o unas comillas de más bastaban)."""
    c = palabras(cita)
    if len(c) < 2:
        return False
    p = palabras(texto)
    m = SequenceMatcher(None, p, c, autojunk=False).find_longest_match(0, len(p), 0, len(c))
    return m.size >= max(2, math.ceil(len(c) * 0.7))


INSTRUCCIONES_FRASES = """Te digo qué necesita encontrar el área de Compras de una cadena de tiendas naturistas en México.
Escribe de 2 a 3 búsquedas para Google, cortas (de 3 a 8 palabras), en español, como las escribiría una persona.
No pongas comillas ni operadores. Responde solo JSON: {"busquedas": ["...", "..."]}"""


def frases(bd: Session, tarea: str, que: str, fijas: list[str]) -> list[str]:
    """Las búsquedas que propone la IA local; si no contesta, las fijas."""
    try:
        r = puerta.ejecutar(bd, tarea, usuario_id=None, instrucciones=INSTRUCCIONES_FRASES, mensaje=que[:1500],
                            max_tokens=300)
        from modulos.compras import radar

        propuestas = [" ".join(str(x).replace('"', " ").split())[:120]
                      for x in ((radar._json_de(r.texto) or {}).get("busquedas") or []) if str(x).strip()]
    except (puerta.ErrorIA, ValueError, TypeError, AttributeError) as e:
        log.info("Buscar en internet: la IA no propuso búsquedas (%s); se usan las fijas", e)
        propuestas = []
    return (propuestas or fijas)[:MAX_CONSULTAS]
