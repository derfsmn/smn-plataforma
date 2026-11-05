"""Demografía de la zona de cada tienda con el Censo de Población y Vivienda 2020 del INEGI (datos públicos).

Pedido de Diego, 2026-10-29: agrupar tiendas también «por demográficos». El archivo nacional «Principales resultados
por localidad» (ITER, `iter_00_cpv2020_csv.zip`) se descarga a mano del sitio del INEGI y se reduce con
`python -m scripts.preparar_inegi --zip <archivo>` a `datos/inegi/localidades_2020.csv`: solo localidades urbanas
(2,500 habitantes o más) con sus coordenadas y unos cuantos indicadores. Nada de SMN sale a internet.

A cada tienda se le asigna la localidad urbana cuyo borde aproximado queda más cerca (máximo 25 km). El borde se estima
como un círculo con la población de la localidad a 5,000 habitantes por km²: así una tienda en la periferia de
Guadalajara queda con Guadalajara y no con un pueblo pegado de 3,000 habitantes. El Censo no trae ingreso:
el «nivel socioeconómico aproximado» es el promedio de escolaridad y de viviendas con auto, internet y computadora.
"""
import bisect
import csv
import io
import math
import re
import zipfile
from functools import lru_cache
from pathlib import Path

ARCHIVO = Path(__file__).parent / "inegi" / "localidades_2020.csv"
MIN_HABITANTES = 2500
MAX_KM = 25.0
DENSIDAD = 5000  # habitantes por km² para estimar el tamaño de una localidad urbana
FUENTE = "Censo de Población y Vivienda 2020, INEGI (principales resultados por localidad)"

COLUMNAS = ["clave", "localidad", "municipio", "estado", "lat", "lon", "poblacion", "pct_60_mas", "pct_0_14",
            "escolaridad", "pct_auto", "pct_internet", "pct_computadora", "pct_sin_salud"]


def _numero(v: str | None) -> float | None:
    """El ITER pone «*» o «N/D» cuando el dato es confidencial o no aplica."""
    try:
        return float(str(v).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def coordenada(v: str | None) -> float | None:
    """«102°17'45.768" W» o «-102.296» a grados decimales (oeste y sur negativos)."""
    if not v:
        return None
    s = str(v).strip()
    try:
        return float(s)
    except ValueError:
        pass
    partes = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    if not partes:
        return None
    g = partes[0] + (partes[1] / 60 if len(partes) > 1 else 0) + (partes[2] / 3600 if len(partes) > 2 else 0)
    return -g if re.search(r"[WwOoSs]\s*$", s) or s.startswith("-") else g


def _filas_iter(ruta: Path):
    """Renglones del CSV del ITER, venga suelto o dentro del .zip."""
    if ruta.suffix.lower() == ".zip":
        with zipfile.ZipFile(ruta) as z:
            # El de datos es el CSV más grande (también trae catálogos y diccionario)
            nombre = max((i for i in z.infolist() if i.filename.lower().endswith(".csv")), key=lambda i: i.file_size).filename
            crudo = z.read(nombre)
    else:
        crudo = ruta.read_bytes()
    try:
        texto = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = crudo.decode("latin-1")
    yield from csv.DictReader(io.StringIO(texto))


def preparar(origen: Path, destino: Path = ARCHIVO) -> dict:
    """Reduce el ITER nacional a las localidades urbanas. Regresa cuántas quedaron y cuántas se descartaron."""
    salida, sin_coordenadas = [], 0
    for f in _filas_iter(origen):
        f = {k.strip().upper(): v for k, v in f.items() if k}
        loc = _numero(f.get("LOC"))
        if not loc or loc in (9998, 9999) or not _numero(f.get("MUN")):
            continue  # totales nacionales, estatales, municipales y de localidades chicas agrupadas
        pob = _numero(f.get("POBTOT"))
        if not pob or pob < MIN_HABITANTES:
            continue
        lat, lon = coordenada(f.get("LATITUD")), coordenada(f.get("LONGITUD"))
        if lat is None or lon is None:
            sin_coordenadas += 1
            continue
        viv = _numero(f.get("VIVPARH_CV")) or _numero(f.get("TVIVPARHAB"))

        def pct(campo, base):
            v = _numero(f.get(campo))
            return round(v / base * 100, 1) if v is not None and base else None

        salida.append({
            "clave": f"{int(_numero(f.get('ENTIDAD')) or 0):02d}{int(_numero(f.get('MUN')) or 0):03d}{int(loc):04d}",
            "localidad": (f.get("NOM_LOC") or "").strip(), "municipio": (f.get("NOM_MUN") or "").strip(),
            "estado": (f.get("NOM_ENT") or "").strip(), "lat": round(lat, 5), "lon": round(lon, 5),
            "poblacion": int(pob), "pct_60_mas": pct("P_60YMAS", pob), "pct_0_14": pct("POB0_14", pob),
            "escolaridad": _numero(f.get("GRAPROES")), "pct_auto": pct("VPH_AUTOM", viv),
            "pct_internet": pct("VPH_INTER", viv), "pct_computadora": pct("VPH_PC", viv),
            "pct_sin_salud": pct("PSINDER", pob),
        })
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", newline="", encoding="utf-8") as a:
        w = csv.DictWriter(a, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(salida)
    cargar.cache_clear()
    nse_por_clave.cache_clear()
    return {"localidades": len(salida), "sin_coordenadas": sin_coordenadas}


@lru_cache(maxsize=1)
def cargar(ruta: Path = ARCHIVO) -> tuple[dict, ...]:
    if not ruta.exists():
        return ()
    with ruta.open(encoding="utf-8") as a:
        filas = []
        for f in csv.DictReader(a):
            filas.append({k: (f[k] if k in ("clave", "localidad", "municipio", "estado") else _numero(f[k]))
                          for k in COLUMNAS})
        return tuple(filas)


def disponible() -> bool:
    return bool(cargar())


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def radio_km(poblacion: float) -> float:
    return math.sqrt(poblacion / DENSIDAD / math.pi)


def cercana(lat: float | None, lon: float | None) -> tuple[dict, float] | None:
    """La localidad urbana más cercana a la tienda (distancia a su borde aproximado), si está a 25 km o menos.
    Regresa (localidad, km al centro)."""
    if lat is None or lon is None:
        return None
    mejor = None
    for loc in cargar():
        if abs(loc["lat"] - lat) > 0.5 or abs(loc["lon"] - lon) > 0.5:
            continue  # ~50 km: ni vale la pena medir
        d = km(lat, lon, loc["lat"], loc["lon"])
        r = max(radio_km(loc["poblacion"] or 0), 0.1)
        # Primero la que tiene su borde más cerca; si queda dentro de varias, la que la tiene más al centro
        orden = (max(0.0, d - r), d / r)
        if mejor is None or orden < mejor[2]:
            mejor = (loc, d, orden)
    return (mejor[0], mejor[1]) if mejor and mejor[2][0] <= MAX_KM else None


@lru_cache(maxsize=1)
def nse_por_clave() -> dict[str, float]:
    """Nivel socioeconómico aproximado de cada localidad urbana: percentil (0 a 100) del promedio estandarizado de
    escolaridad y viviendas con auto, internet y computadora, contra todas las localidades urbanas del país."""
    filas = cargar()
    campos = ("escolaridad", "pct_auto", "pct_internet", "pct_computadora")
    stats = {}
    for c in campos:
        vals = [f[c] for f in filas if f[c] is not None]
        if len(vals) < 2:
            continue
        m = sum(vals) / len(vals)
        stats[c] = (m, math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)) or 1.0)
    indice = {}
    for f in filas:
        zs = [(f[c] - m) / s for c, (m, s) in stats.items() if f[c] is not None]
        if zs:
            indice[f["clave"]] = sum(zs) / len(zs)
    orden = sorted(indice.values())
    n = len(orden)
    return {k: round(100 * bisect.bisect_left(orden, v) / max(1, n - 1), 1) for k, v in indice.items()}
