"""Mantener la base sana: huellas pendientes, contradicciones entre manuales, sugerencias de qué manual escribir o
actualizar, reporte del mes y la prueba de preguntas con su calificación contra las metas."""
import json
import logging
import threading
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import false, select, true
from sqlalchemy.orm import Session

from core.seguridad import Contexto
from ia import puerta
from modulos.metodos import indice, respuestas
from modulos.metodos.documentos import viejo
from modulos.metodos.modelos import Alerta, Documento, Fragmento, Pregunta, PruebaCorrida, PruebaPregunta
from nucleo.modelos import ahora

log = logging.getLogger(__name__)
TAREA_CONTRADICCIONES = "metodos.contradicciones"
PARES_MAXIMO = 40
PARECIDO_COSENO = 0.80
PARECIDO_PALABRAS = 0.35
# Metas para abrir la base a todos (plan aprobado por Diego, 2026-10-30), escaladas al número de preguntas
META_CORRECTAS = 0.80  # 32 de 40
META_SEGUNDOS = 15


def completar_huellas(bd: Session, usuario_id: int | None) -> dict:
    pendientes = list(bd.scalars(select(Fragmento).join(Documento).where(
        Documento.estado == "vigente", Fragmento.vector.is_(None))))
    hechas = indice.poner_huellas(bd, pendientes, usuario_id=usuario_id)
    bd.commit()
    indice.olvidar_cache()
    return {"pendientes": len(pendientes), "hechas": hechas}


# ---------------------------------------------------------------- contradicciones

def _pares(bd: Session) -> list[tuple[indice.Entrada, indice.Entrada, float]]:
    """Fragmentos de documentos distintos que hablan de lo mismo."""
    entradas = indice.indice(bd).entradas
    pares = []
    for i, a in enumerate(entradas):
        pa = set(a.terminos)
        for b in entradas[i + 1:]:
            if a.documento_id == b.documento_id:
                continue
            if a.vector and b.vector and a.modelo == b.modelo and len(a.vector) == len(b.vector):
                parecido = sum(x * y for x, y in zip(a.vector, b.vector))
                if parecido >= PARECIDO_COSENO:
                    pares.append((a, b, parecido))
                continue
            pb = set(b.terminos)
            union = len(pa | pb)
            if union and len(pa & pb) / union >= PARECIDO_PALABRAS:
                pares.append((a, b, len(pa & pb) / union))
    pares.sort(key=lambda p: p[2], reverse=True)
    return pares[:PARES_MAXIMO]


INSTRUCCIONES_CONTRADICCION = """Comparas dos fragmentos de manuales de Súper Mayoreo Naturista que hablan de lo mismo.
Di si se contradicen: si piden cosas distintas para el mismo caso (otro plazo, otro monto, otro puesto, otro paso o
un paso que uno exige y el otro prohíbe). Que uno diga más que el otro NO es contradicción.
Responde solo JSON: {"contradicen": true o false, "explicacion": "una o dos oraciones en palabras simples"}"""


def buscar_contradicciones(bd: Session, usuario_id: int | None) -> dict:
    revisados, nuevas = 0, 0
    docs = {d.documento_id: d for d in bd.scalars(select(Documento).where(Documento.estado == "vigente"))}
    for a, b, _ in _pares(bd):
        ya = bd.scalar(select(Alerta.alerta_id).where(
            Alerta.fragmento_id.in_([a.fragmento_id, b.fragmento_id]),
            Alerta.otro_fragmento_id.in_([a.fragmento_id, b.fragmento_id])))
        if ya:
            continue
        da, db = docs[a.documento_id], docs[b.documento_id]
        r = puerta.ejecutar(bd, TAREA_CONTRADICCIONES, proveedor="ollama", usuario_id=usuario_id, instrucciones=INSTRUCCIONES_CONTRADICCION,
                            mensaje=f"Fragmento A («{da.titulo}», {a.seccion or 'sin sección'}):\n{a.texto[:1800]}\n\n"
                                    f"Fragmento B («{db.titulo}», {b.seccion or 'sin sección'}):\n{b.texto[:1800]}",
                            max_tokens=300, contexto=4096)
        revisados += 1
        try:
            datos = json.loads(r.texto[r.texto.index("{"):r.texto.rindex("}") + 1])
        except ValueError:
            continue
        if datos.get("contradicen") is True:
            bd.add(Alerta(tipo="contradiccion", documento_id=a.documento_id, otro_documento_id=b.documento_id,
                          fragmento_id=a.fragmento_id, otro_fragmento_id=b.fragmento_id, estado="abierta",
                          detalle=str(datos.get("explicacion") or "Dicen cosas distintas sobre lo mismo.")[:2000]))
            nuevas += 1
            bd.commit()
    bd.commit()
    return {"revisados": revisados, "nuevas": nuevas}


_en_curso: set[str] = set()


def en_segundo_plano(nombre: str, funcion, usuario_id: int | None) -> bool:
    """Corre una revisión larga aparte; no deja correr dos iguales a la vez."""
    if nombre in _en_curso:
        return False
    _en_curso.add(nombre)

    def tarea():
        from core.bd import _fabrica

        try:
            with _fabrica()() as bd:
                funcion(bd, usuario_id)
        except Exception:  # noqa: BLE001
            log.exception("Falló %s", nombre)
        finally:
            _en_curso.discard(nombre)

    threading.Thread(target=tarea, name=f"metodos-{nombre}", daemon=True).start()
    return True


def corriendo(nombre: str) -> bool:
    return nombre in _en_curso


# ---------------------------------------------------------------- sugerencias y reporte

def _grupos(preguntas: list[Pregunta]) -> list[list[Pregunta]]:
    """Junta las preguntas que dicen casi lo mismo («¿cómo doy de alta un proveedor?» y «alta de proveedor»)."""
    grupos: list[tuple[set[str], list[Pregunta]]] = []
    for p in preguntas:
        t = set(indice.palabras(p.texto))
        for clave, lista in grupos:
            if t and clave and len(t & clave) / len(t | clave) >= 0.5:
                lista.append(p)
                clave |= t
                break
        else:
            grupos.append((t, [p]))
    return sorted((g for _, g in grupos), key=len, reverse=True)


def sugerencias(bd: Session, ctx: Contexto, dias: int = 90) -> dict:
    desde = ahora() - timedelta(days=dias)
    flojas = list(bd.scalars(select(Pregunta).where(
        Pregunta.creado_en >= desde, Pregunta.es_prueba == false(),
        (Pregunta.encontrada == false()) | (Pregunta.util == false())).order_by(Pregunta.creado_en.desc())))
    temas = []
    for grupo in _grupos(flojas)[:20]:
        hallazgos, _ = indice.buscar(bd, ctx, grupo[0].texto, limite=1, con_significado=False)
        doc = bd.get(Documento, hallazgos[0].entrada.documento_id) if hallazgos else None
        temas.append({
            "preguntas": [p.texto for p in grupo[:5]], "veces": len(grupo),
            "sin_respuesta": sum(1 for p in grupo if not p.encontrada), "no_sirvio": sum(1 for p in grupo if p.util is False),
            "documento_id": doc.documento_id if doc and doc.origen in ("cargado", "ia") else None,
            "documento": doc.titulo if doc else None, "area": doc.area if doc else None,
            "accion": "actualizacion" if doc and doc.origen in ("cargado", "ia") else "nuevo",
        })
    viejos = [{"documento_id": d.documento_id, "titulo": d.titulo, "area": d.area, "version": d.version,
               "motivo": motivo}
              for d in bd.scalars(select(Documento).where(Documento.estado == "vigente",
                                                          Documento.origen.in_(["cargado", "ia"])))
              if (motivo := viejo(d))]
    criterios = []
    try:
        from modulos.contraloria.modelos_diot import FiscalCriterio

        # solo los que aprobó una persona; la carga inicial no cuenta como cambio de regla
        for c in bd.scalars(select(FiscalCriterio).where(FiscalCriterio.estado == "aprobado",
                                                         FiscalCriterio.aprobado_por.is_not(None),
                                                         FiscalCriterio.aprobado_en >= desde)
                            .order_by(FiscalCriterio.aprobado_en.desc()).limit(15)):
            hallazgos, _ = indice.buscar(bd, ctx, c.titulo, limite=1, con_significado=False)
            doc = bd.get(Documento, hallazgos[0].entrada.documento_id) if hallazgos else None
            criterios.append({"titulo": c.titulo, "aprobado_en": c.aprobado_en.date().isoformat(),
                              "documento_id": doc.documento_id if doc and doc.area.startswith("Contralor") else None,
                              "documento": doc.titulo if doc and doc.area.startswith("Contralor") else None})
    except Exception:  # noqa: BLE001 - sin el módulo fiscal no hay criterios que revisar
        bd.rollback()
    return {"temas": temas, "viejos": viejos, "criterios": criterios}


def reporte(bd: Session, mes: str) -> dict:
    inicio = datetime.strptime(mes + "-01", "%Y-%m-%d")
    fin = (inicio + timedelta(days=32)).replace(day=1)
    preguntas = list(bd.scalars(select(Pregunta).where(Pregunta.creado_en >= inicio, Pregunta.creado_en < fin,
                                                       Pregunta.es_prueba == false())))
    total = len(preguntas)
    encontradas = sum(1 for p in preguntas if p.encontrada)
    calificadas = [p for p in preguntas if p.util is not None]
    origenes = Counter(p.origen or "Métodos y procedimientos" for p in preguntas)
    citados: Counter = Counter()
    for p in preguntas:
        for c in json.loads(p.citas or "[]"):
            citados[(c["documento_id"], c["titulo"])] += 1
    return {
        "mes": mes, "total": total, "encontradas": encontradas,
        "sin_respuesta": [{"preguntas": [p.texto for p in g[:5]], "veces": len(g)}
                          for g in _grupos([p for p in preguntas if not p.encontrada])[:30]],
        "calificadas": len(calificadas), "utiles": sum(1 for p in calificadas if p.util),
        "no_sirvieron": [{"pregunta": p.texto, "respuesta": (p.respuesta or "")[:400], "comentario": p.comentario}
                         for p in calificadas if not p.util][:30],
        "promedio_ms": int(sum(p.duracion_ms for p in preguntas) / total) if total else 0,
        "mas_citados": [{"documento_id": d, "titulo": t, "veces": n} for (d, t), n in citados.most_common(10)],
        "por_origen": [{"origen": o, "veces": n} for o, n in origenes.most_common()],
    }


# ---------------------------------------------------------------- prueba de preguntas

def correr_prueba(bd: Session, corrida: PruebaCorrida, ctx: Contexto) -> None:
    preguntas = list(bd.scalars(select(PruebaPregunta).where(PruebaPregunta.activa == true())
                                .order_by(PruebaPregunta.prueba_pregunta_id)))
    corrida.total = len(preguntas)
    corrida.no_esta_total = sum(1 for p in preguntas if not p.debe_contestar)
    bd.commit()
    detalle, tiempos, modos = [], [], Counter()
    try:
        for p in preguntas:
            r = respuestas.responder(bd, ctx, p.pregunta, origen="prueba", es_prueba=True)
            modos[r.modo] += 1
            tiempos.append(r.duracion_ms)
            docs_citados = {c.documento_id for c in r.citas}
            if p.debe_contestar:
                if not r.encontrada:
                    calificacion = "no_encontro"
                elif p.documento_id is None or p.documento_id in docs_citados:
                    calificacion = "correcta"
                    corrida.correctas += 1
                else:
                    calificacion = "otra_cita"
            elif r.encontrada:
                calificacion = "inventada"
                corrida.inventadas += 1
            else:
                calificacion = "no_esta_bien"
                corrida.no_esta_bien += 1
            detalle.append({"id": p.prueba_pregunta_id, "pregunta": p.pregunta, "esperada": p.respuesta_esperada,
                            "documento_esperado": p.documento.titulo if p.documento else None,
                            "debe_contestar": p.debe_contestar, "respuesta": r.texto, "modo": r.modo,
                            "citas": [{"titulo": c.titulo, "seccion": c.seccion, "version": c.version} for c in r.citas],
                            "calificacion": calificacion, "ms": r.duracion_ms})
            corrida.hechas += 1
            corrida.detalle = json.dumps(detalle, ensure_ascii=False)
            corrida.promedio_ms = int(sum(tiempos) / len(tiempos))
            bd.commit()
        corrida.modo = modos.most_common(1)[0][0] if modos else None
        corrida.estado = "terminada"
    except Exception as e:  # noqa: BLE001
        log.exception("Falló la prueba de preguntas")
        bd.rollback()
        corrida = bd.get(PruebaCorrida, corrida.corrida_id)
        corrida.estado, corrida.error = "error", f"Error inesperado: {e.__class__.__name__}"
    corrida.terminada_en = ahora()
    bd.commit()


def metas(c: PruebaCorrida) -> dict:
    """Si la corrida pasa las metas para abrir la base a todos."""
    contestables = c.total - c.no_esta_total
    minimo = -(-contestables * 8 // 10)  # 80 % redondeado hacia arriba (32 de 40)
    return {
        "correctas": {"valor": c.correctas, "meta": minimo, "de": contestables, "pasa": c.correctas >= minimo},
        "inventadas": {"valor": c.inventadas, "meta": 0, "pasa": c.inventadas == 0},
        "no_esta": {"valor": c.no_esta_bien, "meta": c.no_esta_total, "pasa": c.no_esta_bien == c.no_esta_total},
        "segundos": {"valor": round(c.promedio_ms / 1000, 1), "meta": META_SEGUNDOS,
                     "pasa": c.promedio_ms < META_SEGUNDOS * 1000},
        "con_ia": c.modo == "ia",
        "pasa": (c.estado == "terminada" and c.total > 0 and c.correctas >= minimo and c.inventadas == 0
                 and c.no_esta_bien == c.no_esta_total and c.promedio_ms < META_SEGUNDOS * 1000 and c.modo == "ia"),
    }


def correr_prueba_aparte(corrida_id: int, usuario_id: int) -> None:
    def tarea():
        from core.bd import _fabrica
        from core.seguridad import permisos_de
        from nucleo.modelos import Usuario

        with _fabrica()() as bd:
            usuario = bd.get(Usuario, usuario_id)
            correr_prueba(bd, bd.get(PruebaCorrida, corrida_id), Contexto(usuario, permisos_de(bd, usuario_id)))

    threading.Thread(target=tarea, name=f"metodos-prueba-{corrida_id}", daemon=True).start()
