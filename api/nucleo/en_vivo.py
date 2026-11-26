"""Qué está corriendo ahora y bitácora en vivo de la API, para verlo en Estado del sistema sin entrar al servidor
(Diego, 26 nov 2026: «podemos tener un log visible en el sitio para ver qué se está corriendo»).

- La bitácora en vivo guarda en memoria las últimas líneas que escribe la API (sin las consultas de las pantallas).
  Se pierde al reiniciar, como `docker logs` de un contenedor nuevo.
- «Qué está corriendo» junta los procesos pesados que comparten el servidor (DataForSEO, tiendas, IA local).
"""
import json
import logging
import os
import re
import shutil
import subprocess
import urllib.request
import threading
from collections import deque
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import obtener_bd_ligera
from core.seguridad import Contexto, requiere
from nucleo import actividad
from nucleo.modelos import ahora

router = APIRouter(prefix="/api/nucleo/en-vivo", tags=["sistema"])
VER = "nucleo.bitacora.ver"
LINEAS = 300
# Minutos a partir de los cuales un proceso sale en ámbar
LENTO = {"evaluacion": 10, "precios": 60, "tendencias": 30, "oportunidades": 30, "examen": 180, "prueba": 90}
NIVELES = {"DEBUG": "detalle", "INFO": "info", "WARNING": "aviso", "ERROR": "error", "CRITICAL": "error"}


class _Memoria(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lineas: deque[dict] = deque(maxlen=LINEAS)
        self._n = 0
        self._candado = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name.startswith("uvicorn.access"):
                return
            mensaje = record.getMessage()
            if record.exc_info and record.levelno >= logging.ERROR:
                mensaje += f" — {record.exc_info[1]}"
            with self._candado:
                self._n += 1
                self.lineas.append({"n": self._n, "hora": datetime.fromtimestamp(record.created, UTC).isoformat(),
                                    "nivel": NIVELES.get(record.levelname, "info"), "origen": _origen(record.name),
                                    "mensaje": mensaje[:2000]})
        except Exception:  # noqa: BLE001 - la bitácora nunca tira la API
            pass

    def desde(self, n: int) -> list[dict]:
        with self._candado:
            return [x for x in self.lineas if x["n"] > n]


def _origen(nombre: str) -> str:
    partes = nombre.split(".")
    return partes[-1].replace("_", " ") if nombre.startswith("smn") else ("API" if nombre.startswith("uvicorn") else partes[0])


MEMORIA = _Memoria()


ARRANCO: datetime | None = None


def instalar() -> None:
    """Se llama al arrancar: escucha a la raíz y a uvicorn (que no se propaga), deja pasar los INFO de «smn» y empieza a
    tomar las muestras de la gráfica en vivo del Monitor."""
    global ARRANCO
    ARRANCO = ARRANCO or ahora()
    actividad.iniciar()
    for nombre in ("", "uvicorn.error"):
        lg = logging.getLogger(nombre)
        if MEMORIA not in lg.handlers:
            lg.addHandler(MEMORIA)
    logging.getLogger("smn").setLevel(logging.INFO)


def _minutos(desde: datetime | None) -> int | None:
    return int((ahora() - desde).total_seconds() // 60) if desde else None


def _proceso(tipo: str, nombre: str, detalle: str | None, desde: datetime | None, progreso: float | None = None) -> dict:
    m = _minutos(desde)
    limite = LENTO.get(tipo, 30)
    return {"tipo": tipo, "nombre": nombre, "detalle": detalle, "minutos": m,
            "lento": m is not None and m >= limite, "muy_lento": m is not None and m >= 2 * limite,
            "progreso": None if progreso is None else max(0.0, min(1.0, progreso))}


def _fraccion(hechos, total) -> float | None:
    try:
        return float(hechos) / float(total) if total else None
    except (TypeError, ValueError):
        return None


def _paso(avance: str | None) -> float | None:
    m = re.match(r"Paso (\d+) de (\d+)", avance or "")
    return (int(m.group(1)) - 0.5) / int(m.group(2)) if m else None


def procesos(bd: Session) -> list[dict]:
    salida: list[dict] = []
    # Cada fuente por separado: si una tabla falta en una base vieja, las demás se ven igual
    try:
        from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
        from modulos.compras.modelos_propuestas import Propuesta

        q = (select(ProductoEvaluacion, ProductoIdea.nombre, Propuesta.producto)
             .outerjoin(ProductoIdea, ProductoIdea.idea_id == ProductoEvaluacion.idea_id)
             .outerjoin(Propuesta, Propuesta.propuesta_id == ProductoEvaluacion.propuesta_id)
             .where(ProductoEvaluacion.estado == "en_curso").order_by(ProductoEvaluacion.creada_en))
        for e, idea, propuesta in bd.execute(q):
            salida.append(_proceso("evaluacion", f"Radar de productos: {idea or propuesta or f'evaluación {e.evaluacion_id}'}",
                                   e.avance or "empezando", e.creada_en, _paso(e.avance)))
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras.modelos_precios import PrecioCorrida

        nombres = {"programado": "Radar de precios (programado)", "tardio": "Radar de precios (programado)",
                   "manual": "Radar de precios («Correr ahora»)", "prueba": "Radar de precios (prueba con Excel)",
                   "producto": "Precios de afuera de un producto nuevo", "oportunidad": "Buscar oportunidades (precios)",
                   "nocturna": "Radar de precios (lote de noche)"}
        for c in bd.scalars(select(PrecioCorrida).where(PrecioCorrida.estado == "en_curso").order_by(PrecioCorrida.iniciado_en)):
            hechos = (c.con_coincidencia or 0) + (c.sin_coincidencia or 0) + (c.fallidos or 0)
            salida.append(_proceso("precios", nombres.get(c.origen, f"Radar de precios ({c.origen})"),
                                   f"{hechos:,} de {c.productos or 0:,} producto(s)", c.iniciado_en,
                                   _fraccion(hechos, c.productos)))
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras.modelos import RadarReporte

        for r in bd.scalars(select(RadarReporte).where(RadarReporte.estado == "en_curso")):
            salida.append(_proceso("tendencias", "Radar de tendencias", f"corrida {r.origen} del {r.fecha:%d/%m}", r.iniciado_en))
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras.modelos_productos import OportunidadCorrida

        for o in bd.scalars(select(OportunidadCorrida).where(OportunidadCorrida.estado == "en_curso")):
            salida.append(_proceso("oportunidades", "Buscar oportunidades", None, getattr(o, "creada_en", None)
                                   or getattr(o, "iniciada_en", None)))
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras import examen_clasificacion as ex

        est = ex.estado()
        if est.get("corriendo"):
            a = est.get("avance") or {}
            salida.append(_proceso("examen", f"Examen de clasificación ({est.get('clasificador')})",
                                   f"corrida {a.get('corrida')}: {a.get('hechos', 0):,} de {a.get('total', 0):,}", None,
                                   _fraccion(a.get("hechos"), a.get("total"))))
    except Exception:  # noqa: BLE001
        pass
    try:
        from modulos.compras import prueba_afuera as pa

        est = pa.estado()
        if est.get("corriendo"):
            a = est.get("avance") or {}
            salida.append(_proceso("prueba", "Prueba por lote de precios de afuera",
                                   f"{a.get('hechos', 0)} de {a.get('total', 0)} productos", None,
                                   _fraccion(a.get("hechos"), a.get("total"))))
    except Exception:  # noqa: BLE001
        pass
    return salida


@router.get("")
def en_vivo(desde: int = 0, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd_ligera)) -> dict:
    """Procesos que están corriendo y líneas nuevas de la bitácora (después de la línea `desde`)."""
    return {"procesos": procesos(bd), "bitacora": MEMORIA.desde(desde), "ahora": ahora().replace(tzinfo=UTC).isoformat(),
            "guarda": LINEAS, "ultima": MEMORIA._n}


# ---------------------------------------------------------------- Monitor de pantalla completa (26 nov 2026)

HORAS_LINEA = 12
CARRILES = ("Evaluaciones del radar de productos", "Radar de precios", "Radar de tendencias", "Buscar oportunidades")


def _sistema() -> dict:
    """Procesador, memoria y tarjeta de video como los ve el contenedor de la API. Lo que no se pueda leer va en None."""
    salida: dict = {"cpu_pct": None, "memoria_pct": None, "memoria_gb": None, "gpu": []}
    try:
        carga = os.getloadavg()[0]
        salida["cpu_pct"] = round(min(100.0, 100 * carga / (os.cpu_count() or 1)))
    except (OSError, AttributeError):
        pass
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for linea in f:
                k, v = linea.split(":", 1)
                info[k] = int(v.split()[0])
        total, libre = info["MemTotal"], info.get("MemAvailable", info.get("MemFree", 0))
        salida["memoria_pct"] = round(100 * (total - libre) / total)
        salida["memoria_gb"] = round(total / 1024 / 1024, 1)
    except (OSError, KeyError, ValueError, ZeroDivisionError):
        pass
    if shutil.which("nvidia-smi"):
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
            for linea in r.stdout.strip().splitlines():
                nombre, uso, usada, total = [x.strip() for x in linea.split(",")]
                salida["gpu"].append({"nombre": nombre, "uso_pct": int(uso), "memoria_pct": round(100 * int(usada) / int(total))})
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return salida


def _ia_local() -> dict:
    """¿Responde Ollama y qué modelos tiene cargados ahora (cargado = lo está usando o lo usó hace poco)?"""
    from core.config import configuracion

    url = (configuracion().ollama_url or "").rstrip("/")
    if not url:
        return {"responde": None, "modelos": []}
    try:
        with urllib.request.urlopen(f"{url}/api/ps", timeout=3) as r:
            datos = json.loads(r.read().decode() or "{}")
        modelos = [{"nombre": m.get("name"), "en_video_gb": round((m.get("size_vram") or 0) / 1e9, 1)}
                   for m in datos.get("models") or []]
        return {"responde": True, "modelos": modelos}
    except Exception:  # noqa: BLE001
        return {"responde": False, "modelos": []}


def _dataforseo(bd: Session) -> dict:
    try:
        from core.config import configuracion
        from modulos.compras import dataforseo as dfs

        return {"gasto_mes": float(dfs.gasto_mes(bd)), "tope_mes": float(configuracion().precios_tope_mensual_usd or 0),
                "falta": dfs.configurado()}
    except Exception:  # noqa: BLE001
        bd.rollback()
        return {"gasto_mes": None, "tope_mes": None}


def _barra(carril: str, nombre: str, inicio: datetime | None, fin: datetime | None, estado: str) -> dict | None:
    if not inicio:
        return None
    return {"carril": carril, "nombre": nombre, "inicio": inicio.replace(tzinfo=UTC).isoformat(),
            "fin": fin.replace(tzinfo=UTC).isoformat() if fin else None, "estado": estado}


def linea_de_tiempo(bd: Session, horas: int = HORAS_LINEA) -> list[dict]:
    desde = ahora() - timedelta(hours=horas)
    barras: list[dict | None] = []
    try:
        from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
        from modulos.compras.modelos_propuestas import Propuesta

        q = (select(ProductoEvaluacion, ProductoIdea.nombre, Propuesta.producto)
             .outerjoin(ProductoIdea, ProductoIdea.idea_id == ProductoEvaluacion.idea_id)
             .outerjoin(Propuesta, Propuesta.propuesta_id == ProductoEvaluacion.propuesta_id)
             .where((ProductoEvaluacion.terminada_en.is_(None)) | (ProductoEvaluacion.terminada_en >= desde),
                    ProductoEvaluacion.creada_en >= desde - timedelta(hours=6))
             .order_by(ProductoEvaluacion.creada_en.desc()).limit(150))
        for e, idea, prop in bd.execute(q):
            barras.append(_barra(CARRILES[0], idea or prop or f"evaluación {e.evaluacion_id}", e.creada_en, e.terminada_en, e.estado))
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras.modelos_precios import PrecioCorrida

        q = (select(PrecioCorrida).where((PrecioCorrida.terminado_en.is_(None)) | (PrecioCorrida.terminado_en >= desde),
                                         PrecioCorrida.iniciado_en >= desde - timedelta(hours=12))
             .order_by(PrecioCorrida.iniciado_en.desc()).limit(150))
        for c in bd.scalars(q):
            carril = CARRILES[0] if c.origen == "producto" else CARRILES[3] if c.origen == "oportunidad" else CARRILES[1]
            if c.origen == "producto":
                continue  # ya va dentro de la evaluación
            barras.append(_barra(carril, f"{c.origen} · {c.productos or 0:,} productos", c.iniciado_en, c.terminado_en, c.estado))
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras.modelos import RadarReporte

        for r in bd.scalars(select(RadarReporte).where(RadarReporte.iniciado_en >= desde - timedelta(hours=6))):
            barras.append(_barra(CARRILES[2], f"corrida {r.origen}", r.iniciado_en, r.terminado_en, r.estado))
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras.modelos_productos import OportunidadCorrida

        for o in bd.scalars(select(OportunidadCorrida).where(OportunidadCorrida.creada_en >= desde - timedelta(hours=6))):
            barras.append(_barra(CARRILES[3], "Buscar oportunidades", o.creada_en, o.terminada_en, o.estado))
    except Exception:  # noqa: BLE001
        bd.rollback()
    return [b for b in barras if b]


# ---------------------------------------------------------------- Monitor v0.6.5: salud, números de hoy, lo que sigue

def _cuadro(clave: str, nombre: str, estado: str, detalle: str) -> dict:
    """Un cuadro de salud. estado: ok / ocupado / aviso / mal / apagado."""
    return {"clave": clave, "nombre": nombre, "estado": estado, "detalle": detalle}


def _correo_salud(errores: int) -> dict:
    import socket

    from core.config import configuracion

    cfg = configuracion()
    extra = f" · {errores} correo(s) sin enviar" if errores else ""
    if not cfg.smtp_servidor:
        return _cuadro("correo", "Correo de salida", "aviso", "sin configurar: los correos no salen" + extra)
    try:
        socket.create_connection((cfg.smtp_servidor, cfg.smtp_puerto), timeout=1).close()
    except OSError:
        return _cuadro("correo", "Correo de salida", "mal", "no conecta" + extra)
    return _cuadro("correo", "Correo de salida", "aviso" if errores else "ok", ("conecta" + extra) if errores else f"conecta con {cfg.smtp_servidor}")


def _base_salud(bd: Session) -> tuple[dict, dict]:
    import time as _t

    from sqlalchemy import text

    try:
        t0 = _t.monotonic()
        bd.execute(text("SELECT 1"))
        ms = round(1000 * (_t.monotonic() - t0))
    except Exception:  # noqa: BLE001
        bd.rollback()
        return (_cuadro("base", "Base de datos", "mal", "no responde"),
                _cuadro("respaldo", "Respaldo de la base", "apagado", "no se pudo revisar"))
    detalle = f"respondió en {ms} ms"
    try:
        gb = bd.execute(text("SELECT SUM(CAST(size AS bigint)) * 8 / 1024.0 / 1024 FROM sys.database_files")).scalar()
        detalle = f"{float(gb):.1f} GB · {detalle}" if gb is not None else detalle
    except Exception:  # noqa: BLE001
        bd.rollback()
    estado = "aviso" if ms > 1000 else "ok"
    # Conexiones en uso (26 nov 2026: la plataforma se pasmó cuando se acabaron); se avisa antes de que se llenen
    from core.bd import CONEXIONES, EXTRA, motor

    tope = CONEXIONES + EXTRA
    try:
        uso = motor().pool.checkedout()
    except Exception:  # noqa: BLE001
        uso = None
    if uso is not None:
        detalle = f"{detalle} · {uso} de {tope} conexiones"
        if uso >= tope * 0.9:
            estado = "mal"
        elif uso >= tope * 0.6:
            estado = "aviso"
    base = _cuadro("base", "Base de datos", estado, detalle)
    try:
        ultimo = bd.execute(text("SELECT MAX(backup_finish_date) FROM msdb.dbo.backupset WHERE database_name = DB_NAME()")).scalar()
    except Exception:  # noqa: BLE001
        bd.rollback()
        return base, _cuadro("respaldo", "Respaldo de la base", "apagado", "no se pudo revisar")
    if not ultimo:
        return base, _cuadro("respaldo", "Respaldo de la base", "aviso", "la base no tiene ningún respaldo")
    dias = (datetime.now() - ultimo).days  # msdb guarda la hora local del servidor de SQL
    texto_dias = "hoy" if dias <= 0 else "ayer" if dias == 1 else f"hace {dias} días"
    return base, _cuadro("respaldo", "Respaldo de la base", "aviso" if dias >= 2 else "ok", f"último {texto_dias}")


def _disco_salud() -> dict:
    from core.config import configuracion

    try:
        u = shutil.disk_usage(configuracion().archivos_ruta)
    except OSError:
        return _cuadro("disco", "Disco de archivos", "apagado", "no se pudo revisar")
    pct = round(100 * u.used / u.total)
    return _cuadro("disco", "Disco de archivos", "mal" if pct >= 90 else "aviso" if pct >= 80 else "ok",
                   f"{pct} % usado · {u.free / 1e9:,.0f} GB libres")


def salud(bd: Session, ia: dict, dfs: dict, errores_correo: int) -> list[dict]:
    hora = ARRANCO.replace(tzinfo=UTC).isoformat() if ARRANCO else None
    base, respaldo = _base_salud(bd)
    if ia.get("responde") is None:
        ia_c = _cuadro("ia", "IA local", "apagado", "sin configurar")
    elif not ia.get("responde"):
        ia_c = _cuadro("ia", "IA local", "mal", "Ollama no contesta")
    elif ia.get("modelos"):
        ia_c = _cuadro("ia", "IA local", "ocupado", "trabajando · " + ", ".join(m["nombre"] or "" for m in ia["modelos"]))
    else:
        ia_c = _cuadro("ia", "IA local", "ok", "lista, sin trabajo ahora")
    gasto, tope = dfs.get("gasto_mes"), dfs.get("tope_mes")
    if dfs.get("falta"):
        dfs_c = _cuadro("dataforseo", "DataForSEO", "apagado", "sin configurar")
    elif gasto is None:
        dfs_c = _cuadro("dataforseo", "DataForSEO", "apagado", "no se pudo revisar")
    else:
        lleno = bool(tope) and gasto >= 0.9 * tope
        dfs_c = _cuadro("dataforseo", "DataForSEO", "aviso" if lleno else "ok",
                        f"US${gasto:,.2f} de {tope:,.0f} este mes" if tope else f"US${gasto:,.2f} este mes")
    return [{**_cuadro("api", "API", "ok", "responde"), "desde": hora}, base, _correo_salud(errores_correo), ia_c, dfs_c,
            _disco_salud(), respaldo]


def _inicio_de_hoy() -> datetime:
    """Medianoche de hoy en México, en UTC sin zona como se guardan las fechas."""
    from modulos.compras import precios as pc

    local = datetime.now(pc.zona()).replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(UTC).replace(tzinfo=None)


def numeros_de_hoy(bd: Session) -> dict:
    from sqlalchemy import func

    inicio = _inicio_de_hoy()
    salida: dict = {}
    try:
        from modulos.compras.modelos_productos import ProductoEvaluacion

        filas = bd.execute(select(ProductoEvaluacion.estado, ProductoEvaluacion.creada_en, ProductoEvaluacion.terminada_en)
                           .where((ProductoEvaluacion.terminada_en >= inicio) | (ProductoEvaluacion.estado == "en_curso"))).all()
        listas = [(t - c).total_seconds() / 60 for e, c, t in filas if e == "lista" and c and t]
        salida["evaluaciones"] = {"terminadas": sum(1 for e, _, t in filas if t and e != "en_curso"),
                                  "en_curso": sum(1 for e, _, _ in filas if e == "en_curso"),
                                  "con_error": sum(1 for e, _, t in filas if t and e == "error"),
                                  "minutos_promedio": round(sum(listas) / len(listas), 1) if listas else None}
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from core.config import configuracion
        from modulos.compras import nocturno_precios as noc
        from modulos.compras import precios as pc
        from modulos.compras.modelos_precios import PrecioCorrida

        noche = noc.inicio_noche(datetime.now(pc.zona()), configuracion().precios_nocturno_desde)
        fila = bd.execute(select(func.count(), func.sum(PrecioCorrida.productos), func.sum(PrecioCorrida.con_coincidencia))
                          .where(PrecioCorrida.origen == noc.ORIGEN, PrecioCorrida.iniciado_en >= noche)).one()
        salida["noche"] = {"lotes": int(fila[0] or 0), "productos": int(fila[1] or 0), "con_precio": int(fila[2] or 0)}
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras.modelos_precios import PrecioEnvio

        envios = bd.execute(select(PrecioEnvio.estado, PrecioEnvio.tareas, PrecioEnvio.costo_usd, PrecioEnvio.respuesta)
                            .where(PrecioEnvio.creado_en >= inicio)).all()
        aceptadas = rechazadas = 0
        for estado, tareas, _, respuesta in envios:
            if estado == "rechazado":
                rechazadas += tareas or 0
                continue
            try:
                for t in json.loads(respuesta or "[]"):
                    if int(t.get("estado") or 0) >= 40000:
                        rechazadas += 1
                    else:
                        aceptadas += 1
            except (ValueError, TypeError, AttributeError):
                aceptadas += tareas or 0
        salida["busquedas"] = {"aceptadas": aceptadas, "rechazadas": rechazadas,
                               "gasto_usd": round(float(sum((c or 0) for _, _, c, _ in envios)), 2)}
    except Exception:  # noqa: BLE001
        bd.rollback()
    return salida


def lo_que_sigue(bd: Session) -> list[dict]:
    """Lo programado que viene, con la hora local en que empieza (o «ahora» si ya está en su ventana)."""
    from core.config import configuracion
    from modulos.compras import nocturno_precios as noc
    from modulos.compras import precios as pc

    cfg = configuracion()
    local = datetime.now(pc.zona())
    en_noche = noc.en_ventana(local.hour, cfg.precios_nocturno_desde, cfg.precios_nocturno_hasta)
    hoy_noche = local.replace(hour=cfg.precios_nocturno_desde, minute=0, second=0, microsecond=0)
    if not en_noche and local >= hoy_noche:
        hoy_noche += timedelta(days=1)
    noche = None if en_noche else hoy_noche.isoformat()
    salida: list[dict] = []
    try:
        if cfg.precios_nocturno_activo:
            av = noc.avance(bd)
            if av.noches_faltan != 0:
                salida.append({"cuando": noche, "que": "Lote de precios de noche",
                               "detalle": f"{av.validados:,} de {av.total:,} productos validados"
                               + (f" · faltan unas {av.noches_faltan} noches" if av.noches_faltan else "")})
    except Exception:  # noqa: BLE001
        bd.rollback()
    try:
        from modulos.compras import prueba_afuera as pa

        if pa._publicada() and not pa.ruta().exists() and pa._intentos() < 2 and not pa._corriendo.is_set():
            salida.append({"cuando": noche, "que": "Prueba por lote de precios de afuera",
                           "detalle": "60 productos, cuando no haya evaluaciones corriendo"})
    except Exception:  # noqa: BLE001
        pass
    try:
        from modulos.compras import examen_clasificacion as ex

        v = ex.clave()
        faltan = ex.pendientes(v) if v else []
        if faltan and not ex._corriendo.is_set():
            salida.append({"cuando": noche, "que": "Examen de clasificación",
                           "detalle": f"{len(faltan)} corrida(s) pendiente(s), cuando no haya evaluaciones"})
    except Exception:  # noqa: BLE001
        pass
    try:
        from modulos.compras import radar

        if cfg.radar_activo:
            salida.append({"cuando": radar.proxima_corrida(bd).isoformat(), "que": "Radar de tendencias", "detalle": None})
    except Exception:  # noqa: BLE001
        bd.rollback()
    return sorted(salida, key=lambda x: x["cuando"] or "")


def avisos_agrupados(lineas: list[dict], maximo: int = 6) -> list[dict]:
    """Avisos y errores de la bitácora, juntando los que dicen lo mismo con distinto número o nombre."""
    grupos: dict[tuple, dict] = {}
    for x in lineas:
        if x["nivel"] not in ("aviso", "error"):
            continue
        base = re.sub(r"«[^»]*»|\d[\d,.:]*", "…", x["mensaje"].split(" — ")[0])[:140]
        g = grupos.setdefault((x["nivel"], x["origen"], base), {"nivel": x["nivel"], "origen": x["origen"], "veces": 0})
        g["veces"] += 1
        g["mensaje"], g["hora"] = x["mensaje"], x["hora"]  # el más reciente
    # Primero los errores, y dentro de cada nivel lo más reciente
    orden = sorted(grupos.values(), key=lambda g: g["hora"], reverse=True)
    return sorted(orden, key=lambda g: g["nivel"] != "error")[:maximo]


@router.get("/monitor/serie")
def monitor_serie(_: Contexto = Depends(requiere(VER))) -> dict:
    """Las muestras de la gráfica en vivo (cada 2 s, últimos 5 min). Ligera: no toca la base."""
    return {"cada": actividad.CADA, "puntos": actividad.PUNTOS, "muestras": actividad.serie()}


@router.get("/monitor")
def monitor(_: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd_ligera)) -> dict:
    """Todo lo de la pantalla Monitor en una sola consulta (la gráfica en vivo va aparte, en /monitor/serie)."""
    lineas = MEMORIA.desde(0)
    avisos = [x for x in lineas if x["nivel"] in ("aviso", "error")][-8:][::-1]
    errores_correo = sum(1 for x in lineas if x["nivel"] == "error" and "correo" in x["mensaje"].lower())
    ia, dfs = _ia_local(), _dataforseo(bd)
    from core.config import configuracion

    return {"ahora": ahora().replace(tzinfo=UTC).isoformat(), "horas": HORAS_LINEA, "carriles": list(CARRILES),
            "version": configuracion().plataforma_version,
            "servidor": {"sistema": _sistema(), "ia": ia, "dataforseo": dfs},
            "salud": salud(bd, ia, dfs, errores_correo), "hoy": numeros_de_hoy(bd), "sigue": lo_que_sigue(bd),
            "grupos": avisos_agrupados(lineas), "procesos": procesos(bd), "linea": linea_de_tiempo(bd), "avisos": avisos}
