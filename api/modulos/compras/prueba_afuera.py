"""Prueba por lote de los precios de afuera (Diego, 25 nov 2026: «tenemos que evaluar muchos productos, no podemos ir
uno por uno»).

Busca afuera, con la misma búsqueda del radar de productos (mercado_producto.buscar), las ideas y propuestas de Compras
con evaluación vigente y una muestra de productos que ya vendemos, y deja un Excel con cuántos encontró y, de los que
no, por qué, agrupado. Se corre sola una vez por cada regla de búsqueda (mercado_producto.REGLA) al publicar; no toca
las evaluaciones.
"""
import json
import logging
import random
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from datos.modelos import Producto
from modulos.compras import mercado_producto as mp
from modulos.compras import radar_productos as rp
from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
from modulos.compras.modelos_propuestas import Propuesta

log = logging.getLogger("smn.compras.prueba_afuera")

MAX_COMPRAS = 40  # ideas y propuestas de Compras
MAX_CATALOGO = 20  # productos que ya vendemos (con código de barras)

# Motivos, de lo mejor a lo peor; el primero que aplica es el del producto
ENCONTRADO = "Encontrado"
RECHAZADA = "DataForSEO no aceptó la búsqueda"
SIN_RESULTADOS = "Google no regresó resultados"
PARECIDOS = "Google regresó resultados, ninguno era el mismo"
SIN_GOOGLE = "No se buscó en Google"
ERROR = "Falló la búsqueda"
ARREGLO = {
    RECHAZADA: "Código: cómo se arma la búsqueda.",
    SIN_RESULTADOS: "Otra fuente (Mercado Libre, Amazon) o el nombre con que se vende.",
    PARECIDOS: "Revisar los títulos rechazados: si alguno era el mismo, es código (reglas de coincidencia).",
    SIN_GOOGLE: "Configuración: usuario de DataForSEO o tope del mes.",
    ERROR: "Código: revisar el mensaje.",
}


@dataclass
class Caso:
    origen: str  # idea / propuesta / catálogo
    referencia: str
    nombre: str
    marca: str | None
    codigo_barras: str | None
    motivo: str = ""
    precios: int = 0
    fuentes: str = ""
    publicacion: str | None = None
    notas: list[str] = field(default_factory=list)


def casos(bd: Session, max_compras: int = MAX_COMPRAS, max_catalogo: int = MAX_CATALOGO, semilla: int = 2026) -> list[Caso]:
    salida: list[Caso] = []
    vistos: set[str] = set()
    evals = bd.scalars(select(ProductoEvaluacion).where(ProductoEvaluacion.vigente == true(), ProductoEvaluacion.estado == "lista")
                       .order_by(ProductoEvaluacion.evaluacion_id.desc()))
    for e in evals:
        if len(salida) >= max_compras:
            break
        try:
            if e.idea_id:
                s, ref = rp.sujeto_de_idea(bd.get(ProductoIdea, e.idea_id)), f"idea {e.idea_id}"
            elif e.propuesta_id:
                s, ref = rp.sujeto_de_propuesta(bd.get(Propuesta, e.propuesta_id)), f"propuesta {e.propuesta_id}"
            else:
                continue
        except Exception:  # noqa: BLE001 - una captura rara no detiene la prueba
            continue
        if ref in vistos:
            continue
        vistos.add(ref)
        nombre = s.nombre if not s.contenido or rp._norm(s.contenido) in rp._norm(s.nombre) else f"{s.nombre} {s.contenido}"
        salida.append(Caso(ref.split()[0], ref, nombre, s.marca, s.codigo_barras))
    catalogo = [p for p in bd.scalars(select(Producto).where(Producto.activo == true(), Producto.codigo_barras.is_not(None),
                                                            Producto.descripcion.is_not(None)).order_by(Producto.sku))]
    for p in random.Random(semilla).sample(catalogo, min(max_catalogo, len(catalogo))):
        salida.append(Caso("catálogo", f"SKU {p.sku}", p.descripcion, p.marca, p.codigo_barras))
    return salida


def motivo(m: mp.Mercado | None) -> str:
    if m is None:
        return ERROR
    if m.precios:
        return ENCONTRADO
    notas = " ".join(m.notas)
    if "no aceptó la búsqueda" in notas:
        return RECHAZADA
    if "Google Shopping: no se buscó" in notas or "Google Shopping falló" in notas:
        return SIN_GOOGLE
    if "no regresó resultados" in notas:
        return SIN_RESULTADOS
    return PARECIDOS


def probar(bd: Session, lista: list[Caso], avance=None) -> list[Caso]:
    for i, c in enumerate(lista, 1):
        try:
            m = mp.buscar(bd, c.nombre, c.marca, c.codigo_barras, f"prueba afuera {c.referencia}")
        except Exception as ex:  # noqa: BLE001
            bd.rollback()
            log.exception("Prueba de precios de afuera: falló %s", c.referencia)
            m, c.notas = None, [f"Error: {ex}"]
        c.motivo = motivo(m)
        if m:
            c.precios, c.notas, c.publicacion = len(m.precios), list(m.notas), m.publicacion
            c.fuentes = ", ".join(sorted({p.get("fuente") or "" for p in m.precios}))
        if avance:
            avance(i, len(lista))
    return lista


def resumen(lista: list[Caso]) -> dict:
    total = len(lista)
    por = Counter(c.motivo for c in lista)
    por_origen = {o: {"total": sum(1 for c in lista if c.origen == o),
                      "encontrados": sum(1 for c in lista if c.origen == o and c.motivo == ENCONTRADO)}
                  for o in sorted({c.origen for c in lista})}
    return {"total": total, "encontrados": por[ENCONTRADO],
            "pct": round(100 * por[ENCONTRADO] / total, 1) if total else None,
            "motivos": dict(por.most_common()), "por_origen": por_origen}


def a_excel(ruta: Path, lista: list[Caso], res: dict, regla: int) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    wb = Workbook()
    h = wb.active
    h.title = "Resumen"
    h.append([f"Prueba de precios de afuera · regla de búsqueda {regla}"])
    h["A1"].font = Font(bold=True, size=14)
    h.append([])
    h.append(["Productos probados", res["total"]])
    h.append(["Con precio de afuera", res["encontrados"], f"{res['pct']} %" if res["pct"] is not None else ""])
    h.append([])
    h.append(["Por origen", "Probados", "Encontrados"])
    for o, d in res["por_origen"].items():
        h.append([o, d["total"], d["encontrados"]])
    h.append([])
    h.append(["Por qué no", "Productos", "Qué lo arregla"])
    fila_motivos = h.max_row
    for mtv, n in res["motivos"].items():
        if mtv != ENCONTRADO:
            h.append([mtv, n, ARREGLO.get(mtv, "")])
    h.column_dimensions["A"].width = 48
    h.column_dimensions["C"].width = 80
    d = wb.create_sheet("Detalle")
    d.append(["Origen", "Referencia", "Nombre", "Marca", "Código de barras", "Resultado", "Precios", "De dónde",
              "Publicación tomada", "Qué se buscó y qué se vio"])
    for c in lista:
        d.append([c.origen, c.referencia, c.nombre, c.marca, c.codigo_barras, c.motivo, c.precios, c.fuentes,
                  c.publicacion, "\n".join(c.notas)[:32000]])
    for col, ancho in zip("ABCDEFGHIJ", (10, 16, 50, 18, 16, 40, 8, 18, 50, 120)):
        d.column_dimensions[col].width = ancho
    for fila in d.iter_rows(min_row=2):
        fila[9].alignment = Alignment(wrap_text=True, vertical="top")
    for fila in (d[1], h[6], h[fila_motivos]):
        for celda in fila:
            celda.font = Font(bold=True)
    wb.save(ruta)


# ---------------------------------------------------------------- corrida sola en el servidor

_corriendo = threading.Event()
AVANCE: dict = {"hechos": 0, "total": 0}


def carpeta() -> Path:
    from core.config import configuracion

    c = Path(configuracion().archivos_ruta) / "examenes"
    c.mkdir(parents=True, exist_ok=True)
    return c


def ruta(ext: str = "xlsx", regla: int | None = None) -> Path:
    return carpeta() / f"prueba_precios_afuera_regla{regla or mp.REGLA}.{ext}"


def _publicada() -> bool:
    from core.config import configuracion

    v = configuracion().plataforma_version
    return bool(v and v != "local")


def correr(bd: Session) -> dict:
    lista = probar(bd, casos(bd), lambda i, n: AVANCE.update(hechos=i, total=n))
    res = resumen(lista)
    a_excel(ruta(), lista, res, mp.REGLA)
    ruta("json").write_text(json.dumps(res, ensure_ascii=False))
    return res


def revisar_programa(bd: Session) -> None:  # noqa: ARG001 - el trabajo abre su propia sesión
    """Lo llama el programador cada minuto: con una versión publicada, si falta la prueba de esta regla, la corre."""
    if _corriendo.is_set() or not _publicada() or ruta().exists() or _intentos() >= 2:
        return

    def trabajo() -> None:
        from core.bd import _fabrica

        try:
            with _fabrica()() as s:
                correr(s)
        except Exception:  # noqa: BLE001
            ruta("intentos").write_text(str(_intentos() + 1))
            log.exception("Prueba de precios de afuera falló")
        finally:
            _corriendo.clear()

    _corriendo.set()
    threading.Thread(target=trabajo, daemon=True, name="prueba-afuera").start()


def _intentos() -> int:
    try:
        return int(ruta("intentos").read_text())
    except (OSError, ValueError):
        return 0


def estado() -> dict:
    j = ruta("json")
    try:
        res = json.loads(j.read_text()) if j.exists() else None
    except (OSError, ValueError):
        res = None
    return {"regla": mp.REGLA, "corriendo": _corriendo.is_set(), "avance": dict(AVANCE), "resultado": res,
            "excel": ruta().exists(), "error": "falló dos veces; revisa los mensajes de la API" if _intentos() >= 2 and not res else None}
