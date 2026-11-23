"""Clientes de fuentes científicas y oficiales para el investigador de Vidanat.

Gratis: PubMed (E-utilities), Europe PMC (REST, con texto completo de acceso abierto), ClinicalTrials.gov (API v2),
OpenAlex y Crossref. Con gasto (DataForSEO, con el tope del mes de «buscar en internet»): sitios oficiales (COFEPRIS,
DOF, FDA, EFSA, NIH ODS) y la web en general.

A estas fuentes solo salen términos de búsqueda. Cada cliente regresa una lista de `Registro` y nunca lanza: lo que
falla queda en `notas`. Hay una pausa entre llamadas al mismo sitio y un caché de un día por dirección.
"""
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from xml.etree import ElementTree

log = logging.getLogger("innovacion.fuentes")

AGENTE = "SMN-TD-Investigacion/1.0"
PAUSA_S = 0.4  # NCBI pide máximo 3 por segundo sin llave
CACHE_S = 24 * 3600
MAX_BYTES = 3 * 1024 * 1024
POR_TERMINO = 8

FUENTES = {
    "pubmed": "PubMed", "europepmc": "Europe PMC", "ctgov": "ClinicalTrials.gov", "openalex": "OpenAlex",
    "crossref": "Crossref", "oficial": "Sitios oficiales (COFEPRIS, DOF, FDA, EFSA, NIH)", "web": "Web en general",
}
GRATIS = ("pubmed", "europepmc", "ctgov", "openalex", "crossref")
CON_GASTO = ("oficial", "web")
SITIOS_OFICIALES = ("gob.mx/cofepris", "dof.gob.mx", "fda.gov", "efsa.europa.eu", "ods.od.nih.gov")


@dataclass
class Registro:
    origen: str
    titulo: str
    url: str | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    nct: str | None = None
    autores: str | None = None
    anio: int | None = None
    publicado_en: str | None = None
    resumen: str | None = None
    tipo_estudio: str | None = None
    acceso_abierto: bool = False

    @property
    def identificador(self) -> str | None:
        if self.doi:
            return f"doi:{self.doi.lower()}"
        if self.pmid:
            return f"pmid:{self.pmid}"
        if self.nct:
            return f"nct:{self.nct}"
        return f"url:{self.url}" if self.url else None


@dataclass
class Resultado:
    registros: list[Registro] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
    costo_usd: float = 0.0


_cache: dict[str, tuple[float, bytes]] = {}
_ultimo: dict[str, float] = {}
_lock = threading.Lock()


def _bajar(url: str, *, aceptar: str = "application/json") -> bytes:
    """GET con caché y pausa por sitio. Lanza OSError si falla."""
    ahora = time.time()
    with _lock:
        if (c := _cache.get(url)) and ahora - c[0] < CACHE_S:
            return c[1]
        host = urllib.parse.urlparse(url).hostname or ""
        espera = PAUSA_S - (ahora - _ultimo.get(host, 0))
    if espera > 0:
        time.sleep(espera)
    peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": aceptar})
    with urllib.request.urlopen(peticion, timeout=20) as r:
        datos = r.read(MAX_BYTES)
    with _lock:
        _ultimo[host] = time.time()
        _cache[url] = (time.time(), datos)
    return datos


def _json(url: str) -> dict:
    return json.loads(_bajar(url).decode("utf-8", "replace"))


def _q(texto: str) -> str:
    return urllib.parse.quote(texto)


def tipo_por_titulo(titulo: str, tipos_pub: list[str] | None = None) -> str:
    t = (" ".join(tipos_pub or []) + " " + (titulo or "")).lower()
    if "meta-analys" in t or "metaanális" in t or "meta-anális" in t:
        return "metaanalisis"
    if "systematic review" in t or "revisión sistemática" in t or "review" in t:
        return "revision"
    if "randomized" in t or "randomised" in t or "clinical trial" in t or "aleatorizado" in t:
        return "ensayo"
    if "cohort" in t or "cross-sectional" in t or "case-control" in t or "observational" in t:
        return "observacional"
    if "in vitro" in t or "rats" in t or "mice" in t or "animal" in t:
        return "preclinico"
    return "otro"


# ---------------------------------------------------------------- PubMed

def pubmed(termino: str, maximo: int = POR_TERMINO) -> Resultado:
    r = Resultado()
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    try:
        ids = _json(f"{base}/esearch.fcgi?db=pubmed&retmode=json&sort=relevance&retmax={maximo}&term={_q(termino)}"
                    )["esearchresult"].get("idlist", [])
        if not ids:
            return r
        xml = _bajar(f"{base}/efetch.fcgi?db=pubmed&retmode=xml&id={','.join(ids)}", aceptar="application/xml")
        raiz = ElementTree.fromstring(xml)
        for art in raiz.iter("PubmedArticle"):
            pmid = art.findtext(".//PMID")
            titulo = "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else ""
            resumen = " ".join("".join(a.itertext()) for a in art.iter("AbstractText")) or None
            anio = art.findtext(".//PubDate/Year") or (art.findtext(".//PubDate/MedlineDate") or "")[:4]
            autores = ", ".join(f"{a.findtext('LastName') or ''} {a.findtext('Initials') or ''}".strip()
                                for a in art.iter("Author") if a.findtext("LastName"))[:900]
            doi = next((i.text for i in art.iter("ArticleId") if i.get("IdType") == "doi"), None)
            pmc = next((i.text for i in art.iter("ArticleId") if i.get("IdType") == "pmc"), None)
            tipos = [p.text or "" for p in art.iter("PublicationType")]
            r.registros.append(Registro("pubmed", titulo[:1000], f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", doi, pmid,
                                        pmc, None, autores or None, int(anio) if str(anio).isdigit() else None,
                                        art.findtext(".//Journal/Title"), resumen, tipo_por_titulo(titulo, tipos),
                                        bool(pmc)))
    except (OSError, ValueError, KeyError, ElementTree.ParseError) as e:
        r.notas.append(f"PubMed no respondió ({type(e).__name__}).")
    return r


# ---------------------------------------------------------------- Europe PMC

def europepmc(termino: str, maximo: int = POR_TERMINO) -> Resultado:
    r = Resultado()
    try:
        d = _json("https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json&resultType=core"
                  f"&pageSize={maximo}&query={_q(termino)}")
        for x in d.get("resultList", {}).get("result", []):
            tipos = (x.get("pubTypeList") or {}).get("pubType") or []
            r.registros.append(Registro(
                "europepmc", str(x.get("title") or "")[:1000],
                f"https://europepmc.org/article/{x.get('source')}/{x.get('id')}", x.get("doi"), x.get("pmid"),
                x.get("pmcid"), None, str(x.get("authorString") or "")[:900] or None,
                int(x["pubYear"]) if str(x.get("pubYear", "")).isdigit() else None,
                (x.get("journalInfo") or {}).get("journal", {}).get("title"), x.get("abstractText"),
                tipo_por_titulo(str(x.get("title") or ""), tipos), x.get("isOpenAccess") == "Y" and bool(x.get("pmcid"))))
    except (OSError, ValueError, KeyError) as e:
        r.notas.append(f"Europe PMC no respondió ({type(e).__name__}).")
    return r


def texto_completo_europepmc(pmcid: str) -> str | None:
    """Texto de un artículo de acceso abierto, por sección («## Título» + párrafos)."""
    try:
        xml = _bajar(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{_q(pmcid)}/fullTextXML", aceptar="application/xml")
        raiz = ElementTree.fromstring(xml)
    except (OSError, ElementTree.ParseError):
        return None
    partes = []
    for sec in raiz.iter("sec"):
        titulo = sec.findtext("title")
        parrafos = [" ".join("".join(p.itertext()).split()) for p in sec.findall("p")]
        if parrafos:
            partes.append((f"## {titulo}\n" if titulo else "") + "\n\n".join(parrafos))
    return "\n\n".join(partes)[:400_000] or None


# ---------------------------------------------------------------- ClinicalTrials.gov

def ctgov(termino: str, maximo: int = POR_TERMINO) -> Resultado:
    r = Resultado()
    try:
        d = _json(f"https://clinicaltrials.gov/api/v2/studies?format=json&pageSize={maximo}&query.term={_q(termino)}")
        for s in d.get("studies", []):
            p = s.get("protocolSection", {})
            ident = p.get("identificationModule", {})
            nct = ident.get("nctId")
            desc = p.get("descriptionModule", {}).get("briefSummary")
            fecha = (p.get("statusModule", {}).get("startDateStruct") or {}).get("date", "")
            r.registros.append(Registro("ctgov", str(ident.get("briefTitle") or "")[:1000],
                                        f"https://clinicaltrials.gov/study/{nct}", None, None, None, nct, None,
                                        int(fecha[:4]) if fecha[:4].isdigit() else None, "ClinicalTrials.gov", desc,
                                        "ensayo", True))
    except (OSError, ValueError, KeyError) as e:
        r.notas.append(f"ClinicalTrials.gov no respondió ({type(e).__name__}).")
    return r


# ---------------------------------------------------------------- OpenAlex y Crossref

def _resumen_openalex(invertido: dict | None) -> str | None:
    if not invertido:
        return None
    posiciones = sorted((p, palabra) for palabra, ps in invertido.items() for p in ps)
    return " ".join(p for _, p in posiciones)[:6000]


def openalex(termino: str, maximo: int = POR_TERMINO) -> Resultado:
    r = Resultado()
    try:
        d = _json(f"https://api.openalex.org/works?per-page={maximo}&search={_q(termino)}")
        for w in d.get("results", []):
            doi = (w.get("doi") or "").removeprefix("https://doi.org/") or None
            autores = ", ".join(a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])[:8])
            fuente = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
            r.registros.append(Registro("openalex", str(w.get("title") or "")[:1000], w.get("doi") or w.get("id"), doi,
                                        None, None, None, autores or None, w.get("publication_year"), fuente,
                                        _resumen_openalex(w.get("abstract_inverted_index")),
                                        tipo_por_titulo(str(w.get("title") or ""), [w.get("type") or ""]),
                                        bool((w.get("open_access") or {}).get("is_oa"))))
    except (OSError, ValueError, KeyError) as e:
        r.notas.append(f"OpenAlex no respondió ({type(e).__name__}).")
    return r


def crossref(termino: str, maximo: int = POR_TERMINO) -> Resultado:
    r = Resultado()
    try:
        d = _json(f"https://api.crossref.org/works?rows={maximo}&query={_q(termino)}")
        for w in d.get("message", {}).get("items", []):
            titulo = " ".join(w.get("title") or [])
            partes = (w.get("issued") or {}).get("date-parts") or [[None]]
            resumen = re.sub(r"<[^>]+>", " ", w.get("abstract") or "").strip() or None
            autores = ", ".join(f"{a.get('family', '')} {a.get('given', '')[:1]}".strip() for a in (w.get("author") or [])[:8])
            r.registros.append(Registro("crossref", titulo[:1000], w.get("URL"), w.get("DOI"), None, None, None,
                                        autores or None, partes[0][0], " ".join(w.get("container-title") or []) or None,
                                        resumen, tipo_por_titulo(titulo, [w.get("type") or ""])))
    except (OSError, ValueError, KeyError) as e:
        r.notas.append(f"Crossref no respondió ({type(e).__name__}).")
    return r


# ---------------------------------------------------------------- sitios oficiales y web (DataForSEO, con gasto)

def web(bd, terminos: list[str], *, oficiales: bool, referencia: str) -> Resultado:
    from modulos.compras import buscar_web

    r = Resultado()
    if oficiales:
        sitios = " OR ".join(f"site:{s}" for s in SITIOS_OFICIALES)
        consultas = [f"{t} ({sitios})" for t in terminos]
    else:
        consultas = list(terminos)
    b = buscar_web.google(bd, consultas, "organico", referencia)
    r.notas += b.notas
    r.costo_usd = float(b.costo_usd or 0)
    for x in b.resultados:
        r.registros.append(Registro("oficial" if oficiales else "web", x.titulo or x.url, x.url, resumen=x.descripcion,
                                    publicado_en=x.dominio, tipo_estudio="oficial" if oficiales else "web"))
    return r


def permitido_por_robots(url: str) -> bool:
    """Se respeta el bloqueo a robots: si el sitio no deja, la fuente queda como enlace para una persona."""
    partes = urllib.parse.urlparse(url)
    from modulos.compras.imagenes import _host_publico

    # Solo sitios públicos de internet: nunca se consulta la red interna (revisión de seguridad 2026-11-22, B2)
    if partes.scheme != "https" or not partes.hostname or not _host_publico(partes.hostname):
        return False
    rp = urllib.robotparser.RobotFileParser()
    try:  # con el abridor que solo sigue redirecciones a https públicos
        from modulos.compras import investigar as iv

        peticion = urllib.request.Request(f"https://{partes.netloc}/robots.txt", headers={"User-Agent": AGENTE, "Accept": "text/plain"})
        with iv._abridor.open(peticion, timeout=10) as r:
            rp.parse(r.read(MAX_BYTES).decode("utf-8", "replace").splitlines())
    except (OSError, ValueError):
        return True  # sin robots.txt, se puede
    return rp.can_fetch(AGENTE, url)


def texto_de_pagina(url: str) -> str | None:
    from modulos.compras import investigar as iv

    if not permitido_por_robots(url):
        return None
    html = iv.bajar(url)
    return iv.texto_de(html)[:200_000] if html else None


CLIENTES = {"pubmed": pubmed, "europepmc": europepmc, "ctgov": ctgov, "openalex": openalex, "crossref": crossref}
