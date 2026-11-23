"""Trabajos en segundo plano de Innovación Vidanat: leer (y OCR), huellas, datos sugeridos, descripción de imágenes e
investigación en internet.

- Se guardan en innovacion.trabajo, así que no se pierden si la API se reinicia (al arrancar, los «corriendo» vuelven
  a «pendiente»).
- Un trabajo que falla se reintenta a los 1, 5 y 30 minutos; después queda en «error» con el motivo en palabras y el
  botón «Reintentar».
- Leer vuelve a escribir las secciones de la versión, así que repetirlo no duplica nada.
- Se procesan al encolarlos (tarea de fondo de la petición), cada minuto con el programador del servidor y cada vez
  que la pantalla pregunta por su avance.
"""
import json
import logging
import threading
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.bd import _fabrica
from ia import puerta
from modulos.innovacion import almacen, ia_local, indice, lectura
from modulos.innovacion.modelos import Evidencia, Seccion, RecursoArchivo, RecursoVersion, Trabajo
from nucleo import busqueda
from nucleo.lectura import Bloque, bloques_de_texto
from nucleo.modelos import Archivo, ahora

log = logging.getLogger("innovacion.trabajos")

ESPERAS_MIN = (1, 5, 30)
NOMBRES = {"leer": "Leer el archivo y partirlo por sección y página", "huellas": "Huella de significado de cada sección",
           "sugerir": "Datos sugeridos por la IA local", "describir": "Descripción de imágenes",
           "investigar": "Investigación en internet"}
_lock = threading.Lock()


class Reintentable(Exception):
    """Falla que vale la pena reintentar (Ollama apagado, red caída)."""


def encolar(bd: Session, tipo: str, objeto_id: int, *, usuario_id: int | None = None, detalle: dict | None = None) -> Trabajo:
    """Encola sin repetir: si ya hay uno igual pendiente o corriendo, regresa ese."""
    if t := bd.scalar(select(Trabajo).where(Trabajo.tipo == tipo, Trabajo.objeto_id == objeto_id,
                                            Trabajo.estado.in_(("pendiente", "corriendo")))):
        return t
    t = Trabajo(tipo=tipo, objeto_id=objeto_id, creado_por=usuario_id, siguiente_en=ahora(),
                detalle=json.dumps(detalle, ensure_ascii=False) if detalle else None)
    bd.add(t)
    bd.flush()
    return t


def reintentar(bd: Session, t: Trabajo) -> None:
    t.estado, t.intentos, t.error, t.siguiente_en = "pendiente", 0, None, ahora()


def cerrar_huerfanas(bd: Session) -> int:
    n = bd.execute(update(Trabajo).where(Trabajo.estado == "corriendo").values(estado="pendiente")).rowcount
    bd.commit()
    return n


def _tomar(bd: Session) -> Trabajo | None:
    t = bd.scalar(select(Trabajo).where(Trabajo.estado == "pendiente", Trabajo.siguiente_en <= ahora())
                  .order_by(Trabajo.siguiente_en, Trabajo.trabajo_id))
    if not t:
        return None
    # solo uno lo toma aunque haya dos procesos
    if bd.execute(update(Trabajo).where(Trabajo.trabajo_id == t.trabajo_id, Trabajo.estado == "pendiente")
                  .values(estado="corriendo", iniciado_en=ahora(), intentos=Trabajo.intentos + 1)).rowcount != 1:
        bd.rollback()
        return None
    bd.commit()
    bd.refresh(t)
    return t


def correr(bd: Session, t: Trabajo) -> None:
    try:
        HACER[t.tipo](bd, t)
    except Exception as e:  # noqa: BLE001 - cualquier falla queda en el trabajo con su motivo
        bd.rollback()
        t = bd.get(Trabajo, t.trabajo_id)
        mensaje = str(e) if isinstance(e, (Reintentable, puerta.ErrorIA, almacen.ArchivoInvalido, ValueError)) else \
            "Falla inesperada al procesar; avisa a Sistemas."
        if not isinstance(e, (Reintentable, puerta.ErrorIA)):
            log.exception("Trabajo %s (%s) falló", t.trabajo_id, t.tipo)
        t.error = mensaje[:1000]
        if isinstance(e, (Reintentable, puerta.ErrorIA)) and t.intentos <= len(ESPERAS_MIN):
            t.estado, t.siguiente_en = "pendiente", ahora() + timedelta(minutes=ESPERAS_MIN[t.intentos - 1])
        else:
            t.estado, t.terminado_en = "error", ahora()
        bd.commit()
        return
    t.estado, t.error, t.terminado_en = "listo", None, ahora()
    bd.commit()


def procesar(bd: Session, limite: int = 20) -> int:
    hechos = 0
    while hechos < limite and (t := _tomar(bd)):
        correr(bd, t)
        hechos += 1
    return hechos


def procesar_en_fondo() -> None:
    """Para las tareas de fondo de una petición y el programador: no corre dos a la vez en el mismo proceso."""
    if not _lock.acquire(blocking=False):
        return
    try:
        with _fabrica()() as bd:
            procesar(bd)
    finally:
        _lock.release()


# ---------------------------------------------------------------- lo que hace cada tipo

def _version(bd: Session, t: Trabajo) -> RecursoVersion:
    v = bd.get(RecursoVersion, t.objeto_id)
    if not v:
        raise ValueError("La versión de la fuente ya no existe.")
    return v


def leer(bd: Session, t: Trabajo) -> None:
    v = _version(bd, t)
    if bd.scalar(select(Evidencia.evidencia_id).join(Seccion, Seccion.fragmento_id == Evidencia.fragmento_id)
                 .where(Seccion.version_id == v.version_id)):
        raise ValueError("Esta versión ya se cita en un expediente; no se vuelve a partir. Carga una versión nueva.")
    bloques: list[Bloque] = []
    resumen_lectura = {"archivos": 0, "ocr_paginas": 0, "imagenes": 0, "sin_texto": []}
    imagenes = []
    if v.resumen:
        bloques.append(Bloque("Resumen", 1, None))
        bloques.append(Bloque(v.resumen, 0, None))
    for ra in v.archivos:
        a = bd.get(Archivo, ra.archivo_id)
        with almacen.en_disco(a, ra.cifrado) as ruta:
            leidos, info = lectura.leer(ruta, a.tipo_contenido)
        resumen_lectura["archivos"] += 1
        resumen_lectura["ocr_paginas"] += info.get("ocr_paginas", 0)
        if a.tipo_contenido in almacen.IMAGENES:
            resumen_lectura["imagenes"] += 1
            imagenes.append(ra.archivo_id)
            if ra.descripcion and ra.descripcion_confirmada:
                leidos = leidos + [Bloque(ra.descripcion, 0, None)]
        if not leidos and a.tipo_contenido not in almacen.IMAGENES:
            resumen_lectura["sin_texto"].append(a.nombre_original)
        if leidos and len(v.archivos) > 1:
            bloques.append(Bloque(a.nombre_original, 1, None))
        bloques += leidos
    if v.texto:
        bloques += bloques_de_texto(v.texto)
    bd.query(Seccion).filter(Seccion.version_id == v.version_id).delete(synchronize_session=False)
    nuevos = []
    for n, p in enumerate(busqueda.partir(bloques, por_pagina=True)):
        texto, _ = busqueda.ocultar_personales(p.texto)
        nuevos.append(Seccion(version_id=v.version_id, orden=n, seccion=p.seccion, pagina=p.pagina, texto=texto,
                                origen="ocr" if resumen_lectura["ocr_paginas"] else "texto"))
    bd.add_all(nuevos)
    v.procesado = "listo" if nuevos or imagenes else "error"
    datos = json.loads(v.datos) if v.datos else {}
    datos["lectura"] = resumen_lectura
    v.datos = json.dumps(datos, ensure_ascii=False)
    bd.flush()
    indice.olvidar()
    if nuevos:
        encolar(bd, "huellas", v.version_id)
        encolar(bd, "sugerir", v.version_id)
    for archivo_id in imagenes:
        encolar(bd, "describir", v.version_id, detalle={"archivo_id": archivo_id})
    if not nuevos and not imagenes:
        bd.commit()
        raise ValueError("No se pudo leer texto de la fuente" + (
            f" ({', '.join(resumen_lectura['sin_texto'])})" if resumen_lectura["sin_texto"] else "")
            + ". Si es un escaneo, revisa que el OCR esté instalado; si no, pega el texto a mano.")


def huellas(bd: Session, t: Trabajo) -> None:
    v = _version(bd, t)
    faltan = list(bd.scalars(select(Seccion).where(Seccion.version_id == v.version_id, Seccion.vector.is_(None))
                             .order_by(Seccion.orden)))
    if not faltan:
        return
    titulo = v.recurso.titulo
    modelo, vectores = busqueda.huellas(bd, indice.TAREA_HUELLA,
                                        [f"{titulo}. {f.seccion or ''}\n{f.texto}"[:4000] for f in faltan],
                                        usuario_id=t.creado_por)
    hechos = 0
    for f, vec in zip(faltan, vectores):
        if vec is not None:
            f.vector, f.modelo_vector = vec, modelo
            hechos += 1
    bd.commit()
    indice.olvidar()
    if hechos < len(faltan):
        raise Reintentable(f"La IA local no respondió: {len(faltan) - hechos} secciones siguen sin huella "
                           "(la búsqueda por palabras ya funciona).")


def sugerir(bd: Session, t: Trabajo) -> None:
    v = _version(bd, t)
    texto = "\n".join(f.texto for f in bd.scalars(select(Seccion).where(Seccion.version_id == v.version_id)
                                                     .order_by(Seccion.orden).limit(12)))
    if not texto:
        return
    try:
        v.sugerencias = json.dumps(ia_local.sugerir_datos(bd, texto, t.creado_por), ensure_ascii=False)
    except ia_local.RespuestaInvalida as e:
        raise Reintentable(str(e)) from e
    bd.commit()


def describir(bd: Session, t: Trabajo) -> None:
    v = _version(bd, t)
    archivo_id = json.loads(t.detalle or "{}").get("archivo_id")
    ra = bd.get(RecursoArchivo, (v.version_id, archivo_id))
    if not ra:
        return
    contenido = almacen.leer(bd.get(Archivo, archivo_id), ra.cifrado)
    ra.descripcion = ia_local.describir_imagen(bd, contenido, t.creado_por)
    ra.descripcion_confirmada = False
    bd.commit()


def investigar(bd: Session, t: Trabajo) -> None:
    from modulos.innovacion import investigador

    investigador.correr(bd, t.objeto_id, usuario_id=t.creado_por)


HACER = {"leer": leer, "huellas": huellas, "sugerir": sugerir, "describir": describir, "investigar": investigar}
