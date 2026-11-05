"""DIOT: guarda los documentos de un periodo, corre el motor y deja el resultado en la base.

El motor (diot_motor.py) no sabe de la base; aquí se leen los documentos vigentes, se aplican los ajustes de Fiscal y
se guarda lo que salió, conservando la revisión de las incidencias que se repiten. Cada «Procesar» es una corrida que
sigue los 8 pasos del proceso de Fiscal en un hilo aparte y guarda su bitácora mientras avanza, para verla en vivo.
"""
import hashlib
import io
import json
import logging
import threading
from datetime import date
from decimal import Decimal

import openpyxl
from sqlalchemy import delete, select, true
from sqlalchemy.orm import Session

from modulos.contraloria import conocimiento_fiscal as conocimiento
from modulos.contraloria import diot_criterios as crit
from modulos.contraloria import diot_layout as layout
from modulos.contraloria import diot_lectura as lectura
from modulos.contraloria import diot_motor as motor
from modulos.contraloria.modelos_diot import (
    DiotAjuste, DiotCorrida, DiotCorridaLog, DiotCorridaPaso, DiotDocumento, DiotIncidencia, DiotOperacion, DiotPeriodo,
    DiotTercero,
)
from nucleo.modelos import ahora

log = logging.getLogger(__name__)
MB_DOCUMENTO = 40
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")


def _json(x) -> str:
    return json.dumps(x, ensure_ascii=False, default=lambda v: str(v) if isinstance(v, Decimal) else v)


def vigentes(bd: Session, periodo_id: int) -> list[DiotDocumento]:
    return list(bd.scalars(select(DiotDocumento).where(DiotDocumento.periodo_id == periodo_id,
                                                       DiotDocumento.vigente == true())
                           .order_by(DiotDocumento.documento_id)))


def guardar_documento(bd: Session, periodo: DiotPeriodo, nombre: str, contenido: bytes, usuario_id: int,
                      tipo: str | None = None) -> tuple[DiotDocumento, lectura.Tabla]:
    """Lee el documento, reconoce su tipo y lo guarda como vigente de ese tipo (el anterior queda en la historia)."""
    tabla = lectura.leer(nombre, contenido, tipo)
    if tipo and tipo != tabla.tipo:
        t = lectura.TIPOS.get(tipo)
        if not t:
            raise lectura.ErrorLectura("Ese tipo de documento no existe.")
        faltan = [c for c in t.columnas if c.upper() not in {x.upper() for x in tabla.columnas}]
        if faltan and tabla.tipo in lectura.TIPOS:
            raise lectura.ErrorLectura(f"Este archivo es «{lectura.TIPOS[tabla.tipo].nombre}», no «{t.nombre}». "
                                       "Súbelo en su renglón o con «Subir reportes», que lo acomoda solo.")
        if faltan:
            raise lectura.ErrorLectura(f"No parece «{t.nombre}»: le faltan las columnas {', '.join(faltan)}.")
        tabla.tipo = tipo
    if not tabla.tipo:
        raise lectura.ErrorLectura("No se reconoció qué reporte es por sus columnas. Revisa que sea uno de los de la "
                                   "lista o elige el tipo a mano.")
    varios = lectura.TIPOS[tabla.tipo].varios
    for d in vigentes(bd, periodo.periodo_id):
        # De los que pueden ser varios (un estado de cuenta por cuenta), solo se reemplaza el del mismo nombre
        if d.tipo == tabla.tipo and (not varios or d.nombre_archivo == nombre[:260]):
            d.vigente = False
    doc = DiotDocumento(periodo_id=periodo.periodo_id, tipo=tabla.tipo, nombre_archivo=nombre[:260],
                        contenido=contenido, tamano=len(contenido), sha256=hashlib.sha256(contenido).hexdigest(),
                        filas=len(tabla.filas), hoja=tabla.hoja, vigente=True, cargado_por=usuario_id,
                        cargado_en=ahora())
    bd.add(doc)
    periodo.estado = "abierto"
    return doc, tabla


def ajustes_de(bd: Session, periodo_id: int) -> list[dict]:
    q = select(DiotAjuste).where(DiotAjuste.periodo_id == periodo_id, DiotAjuste.activo == true())
    return [{"id": a.ajuste_id, "rfc": a.rfc, "nombre": a.nombre, "campo": a.campo, "importe": a.importe,
             "excluir": a.excluir, "tipo_tercero": a.tipo_tercero, "tipo_operacion": a.tipo_operacion,
             "motivo": a.motivo} for a in bd.scalars(q.order_by(DiotAjuste.ajuste_id))]


def _huella(i: motor.Incidencia) -> str:
    return hashlib.sha256(f"{i.codigo}|{i.fuente}|{i.renglon}|{i.rfc}|{i.mensaje}".encode()).hexdigest()


def leer_documentos(bd: Session, periodo: DiotPeriodo, b: motor.Bitacora | None = None) -> dict[str, lectura.Tabla]:
    docs = {}
    for d in vigentes(bd, periodo.periodo_id):
        if lectura.TIPOS[d.tipo].comprobar:  # el banco no entra al cálculo; lo lee su comprobación
            continue
        if b:
            b.linea(f"Leyendo «{d.nombre_archivo}» ({lectura.TIPOS[d.tipo].nombre}, {d.tamano / 1024 / 1024:,.1f} MB, "
                    f"huella {d.sha256[:12]}…).")
        t = lectura.leer(d.nombre_archivo, d.contenido, d.tipo)
        t.tipo = d.tipo
        docs[d.tipo] = t
    return docs


def procesar(bd: Session, periodo: DiotPeriodo, usuario_id: int, bitacora: motor.Bitacora | None = None,
             cfg: crit.Config | None = None) -> motor.Resultado:
    b = bitacora or motor.Bitacora()
    b.inicio(1)
    docs = leer_documentos(bd, periodo, b)
    ajustes = ajustes_de(bd, periodo.periodo_id)
    cfg = cfg or conocimiento.config_periodo(bd, periodo)
    r = motor.procesar(docs, periodo.empresa.rfc, ajustes, b, cfg)
    previas = {i.huella: i for i in bd.scalars(select(DiotIncidencia).where(DiotIncidencia.periodo_id ==
                                                                            periodo.periodo_id))}
    for tabla in (DiotOperacion, DiotTercero, DiotIncidencia):
        bd.execute(delete(tabla).where(tabla.periodo_id == periodo.periodo_id))
    for o in r.operaciones:
        bd.add(DiotOperacion(periodo_id=periodo.periodo_id, fuente=o.fuente, renglon=o.renglon,
                             referencia=o.referencia[:300], rfc=o.rfc, nombre=(o.nombre or "")[:300] or None,
                             regla=o.regla, incluida=o.incluida, tasa=o.tasa, tipo_cambio=o.tipo_cambio,
                             base16=o.base16, iva16=o.iva16, base8=o.base8, iva8=o.iva8, base0=o.base0,
                             exento=o.exento, no_objeto=o.no_objeto, iva_retenido=o.iva_retenido,
                             nota=(o.nota or "")[:500] or None, monto=o.monto))
    for t in r.terceros:
        bd.add(DiotTercero(periodo_id=periodo.periodo_id, rfc=t.rfc, nombre=t.nombre[:300], tipo_tercero=t.tipo_tercero,
                           tipo_operacion=t.tipo_operacion, exactos=_json(t.exactos), redondeados=_json(t.redondeados),
                           operaciones=t.operaciones, fuentes=",".join(t.fuentes), estado=t.estado,
                           ajustado=bool(t.ajustes)))
    vistas = set()
    for i in r.incidencias:
        h = _huella(i)
        if h in vistas:
            continue
        vistas.add(h)
        p = previas.get(h)
        bd.add(DiotIncidencia(periodo_id=periodo.periodo_id, huella=h, impacto=i.impacto, codigo=i.codigo,
                              mensaje=i.mensaje[:1000], fuente=i.fuente, renglon=i.renglon, rfc=i.rfc,
                              importe=i.importe, estado=p.estado if p else "pendiente",
                              nota_revision=p.nota_revision if p else None, revisada_por=p.revisada_por if p else None,
                              revisada_en=p.revisada_en if p else None))
    txt = r.txt
    periodo.txt = txt
    periodo.resumen = _json({"faltantes": r.faltantes, "cuadres": r.cuadres, "validaciones": r.validaciones,
                             "operaciones": len(r.operaciones), "incluidas": sum(1 for o in r.operaciones if o.incluida),
                             "terceros": len(r.terceros)})
    periodo.estado = "procesado" if not r.bloqueado else "abierto"
    periodo.procesado_por, periodo.procesado_en = usuario_id, ahora()
    if periodo.referencia_txt and txt:
        periodo.comparacion = _json(layout.comparar(txt, periodo.referencia_txt, cfg))
    else:
        periodo.comparacion = None
    bd.flush()
    if not r.bloqueado:
        _entregar(bd, periodo, r, b)
    return r


def _entregar(bd: Session, periodo: DiotPeriodo, r: motor.Resultado, b: motor.Bitacora) -> None:
    """Paso 8: deja el TXT validado y la evidencia, o dice qué falta para entregarlos."""
    b.inicio(8)
    pendientes = pendientes_que_bloquean(bd, periodo.periodo_id)
    total = len(list(bd.scalars(select(DiotIncidencia.incidencia_id).where(DiotIncidencia.periodo_id ==
                                                                          periodo.periodo_id))))
    b.linea(f"Incidencias: {total}; con posible impacto sin revisar: {pendientes}.", "aviso" if pendientes else "ok")
    if periodo.comparacion:
        c = json.loads(periodo.comparacion)
        b.linea(f"Contra el TXT presentado ({periodo.referencia_nombre}): {c['renglones_iguales']} de "
                f"{c['renglones_referencia']} renglones idénticos; {len(c['diferencias'])} diferencia(s) de campo.")
    b.linea("Evidencia en Excel lista: consolidado, operaciones con su regla, incidencias, ajustes, documentos, reglas "
            "y esta bitácora.", "ok")
    if r.txt is None:
        b.linea("No hay TXT validado para entregar; revisa los pasos 6 y 7.", "error")
        b.fin("detenido", "Sin TXT validado.")
    elif pendientes:
        b.linea(f"El TXT está generado y validado, pero no se entrega hasta revisar las {pendientes} incidencia(s) con "
                "posible impacto. Al marcarlas revisadas se puede descargar sin volver a procesar.", "aviso")
        b.fin("aviso", f"Falta revisar {pendientes} incidencia(s).")
    else:
        b.linea(f"TXT listo para descargar: «{nombre_archivo(periodo, 'carga SAT.txt')}».", "ok")
        b.fin("ok", "TXT validado y evidencia listos.")
    b.linea("Siguiente paso, fuera de la plataforma: validar el TXT con la herramienta del SAT y presentarlo.")


# ---------------------------------------------------------------- corridas (un «Procesar» visible en vivo)

def corrida_en_curso(bd: Session, periodo_id: int) -> DiotCorrida | None:
    return bd.scalars(select(DiotCorrida).where(DiotCorrida.periodo_id == periodo_id,
                                               DiotCorrida.estado == "en_curso")).first()


def iniciar_corrida(bd: Session, periodo: DiotPeriodo, usuario_id: int) -> DiotCorrida:
    co = DiotCorrida(periodo_id=periodo.periodo_id, estado="en_curso", iniciada_por=usuario_id, iniciada_en=ahora())
    bd.add(co)
    bd.flush()
    for n, nombre, _ in motor.PASOS:
        bd.add(DiotCorridaPaso(corrida_id=co.corrida_id, orden=n, nombre=nombre, estado="pendiente"))
    return co


class _Registro:
    """Guarda cada paso y cada renglón de la bitácora en cuanto ocurre (commit), para que la pantalla lo vea."""

    def __init__(self, bd: Session, corrida_id: int):
        self.bd, self.corrida_id = bd, corrida_id
        self.pasos = {p.orden: p for p in bd.scalars(select(DiotCorridaPaso).where(
            DiotCorridaPaso.corrida_id == corrida_id))}
        self.actual = 1

    def __call__(self, evento: str, datos: dict) -> None:
        if evento == "paso":
            p = self.pasos[datos["orden"]]
            p.estado, p.resumen = datos["estado"], (datos["resumen"] or "")[:1000] or None
            if datos["estado"] == "en_curso":
                p.inicio_en = ahora()
                self.actual = datos["orden"]
            elif datos["estado"] != "pendiente":
                p.fin_en = ahora()
        else:
            self.bd.add(DiotCorridaLog(corrida_id=self.corrida_id, orden_paso=datos["paso"] or self.actual,
                                       momento=ahora(), nivel=datos["nivel"], mensaje=datos["mensaje"][:1000],
                                       detalle=_json(datos["datos"]) if datos["datos"] else None))
        self.bd.commit()


def correr_corrida(bd: Session, corrida_id: int) -> None:
    co = bd.get(DiotCorrida, corrida_id)
    periodo = bd.get(DiotPeriodo, co.periodo_id)
    registro = _Registro(bd, corrida_id)
    b = motor.Bitacora(registro)
    try:
        cfg = conocimiento.config_periodo(bd, periodo)
        co.criterios = _json(cfg.resumen())
        r = procesar(bd, periodo, co.iniciada_por, b, cfg)
        detenido = [p for p in b.pasos.values() if p["estado"] == "detenido"]
        co.estado = "detenida" if detenido else "terminada"
        co.resultado = (f"Se detuvo en el paso {detenido[0]['orden']}: {detenido[0]['resumen']}" if detenido else
                        f"{len(r.terceros)} terceros; TXT {'validado' if r.txt else 'no generado'}.")[:500]
    except Exception as e:  # noqa: BLE001 - la corrida se cierra y dice qué pasó
        log.exception("DIOT: la corrida %s falló", corrida_id)
        bd.rollback()
        b.linea(f"Error inesperado: {str(e)[:300]}. No se guardó el resultado de esta corrida.", "error")
        b.fin("detenido", "Error inesperado.")
        b.no_ejecutados("No se ejecutó por el error.")
        co = bd.get(DiotCorrida, corrida_id)
        co.estado, co.resultado = "fallida", f"Error inesperado: {str(e)[:300]}"
    co.terminada_en = ahora()
    bd.commit()


def en_hilo(corrida_id: int) -> None:
    from core.bd import _fabrica

    def correr():
        with _fabrica()() as bd:
            correr_corrida(bd, corrida_id)

    threading.Thread(target=correr, daemon=True, name=f"diot-corrida-{corrida_id}").start()


def cerrar_huerfanas(bd: Session) -> int:
    """Al arrancar la API: una corrida «en curso» murió con el reinicio."""
    abiertas = list(bd.scalars(select(DiotCorrida).where(DiotCorrida.estado == "en_curso")))
    for co in abiertas:
        co.estado, co.terminada_en = "fallida", ahora()
        co.resultado = "La plataforma se reinició a media corrida; vuelve a procesar."
    bd.commit()
    return len(abiertas)


def pendientes_que_bloquean(bd: Session, periodo_id: int) -> int:
    q = select(DiotIncidencia).where(DiotIncidencia.periodo_id == periodo_id, DiotIncidencia.estado == "pendiente",
                                     DiotIncidencia.impacto == motor.POSIBLE)
    return len(list(bd.scalars(q)))


def nombre_archivo(periodo: DiotPeriodo, sufijo: str) -> str:
    return f"DIOT {periodo.empresa.codigo} {MESES[periodo.mes - 1]} {periodo.anio} {sufijo}"


def evidencia(bd: Session, periodo: DiotPeriodo) -> bytes:
    """Excel con el consolidado, cada operación con su regla, las incidencias, los ajustes y las reglas."""
    from modulos.contraloria import diot_validacion as validacion  # aquí para no importar en círculo

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resumen"
    c = validacion.comprobaciones(bd, periodo)
    ws.append([f"DIOT {periodo.empresa.nombre} · {MESES[periodo.mes - 1]} {periodo.anio}"])
    ws.append([c["frase"]])
    ws.append([])
    ws.append(["Comprobación", "Resultado", "Qué dice"])
    textos = {"ok": "Bien", "revisar": "Por revisar", "falla": "No cuadra", "sin_datos": "Sin datos", "info": "Para mirar"}
    for x in c["comprobaciones"]:
        ws.append([x["titulo"], textos.get(x["estado"], x["estado"]), x["frase"]])
    ws.append([])
    ws.append(["Firma", "Quién", "Cuándo", "Nota"])
    for tipo, nombre in (("revision", "Revisó las comprobaciones"), ("fiscal", "Visto bueno de Fiscal")):
        f = c["firmas"][tipo]
        ws.append([nombre, f["por"] or "Sin firma", f["en"], f["nota"]])
    ws.append([])
    ws.append(["Ajustes de Fiscal con su motivo: hoja «Ajustes de Fiscal». Cada importe y de dónde sale: hojas "
               "«Consolidado» y «Operaciones»."])
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width, ws.column_dimensions["C"].width = 34, 22, 110
    ws = wb.create_sheet("Consolidado")
    campos = motor.CAMPOS
    ws.append(["RFC", "Nombre", "Tipo de tercero", "Tipo de operación", *[f"{c} (exacto)" for c in campos],
               *[f"{c} (al peso)" for c in campos], "Operaciones", "Fuentes", "Estado", "Ajustado"])
    for t in bd.scalars(select(DiotTercero).where(DiotTercero.periodo_id == periodo.periodo_id)
                        .order_by(DiotTercero.tipo_tercero, DiotTercero.rfc)):
        ex, rd = json.loads(t.exactos), json.loads(t.redondeados)
        ws.append([t.rfc, t.nombre, t.tipo_tercero, t.tipo_operacion, *[float(Decimal(ex[c])) for c in campos],
                   *[rd[c] for c in campos], t.operaciones, t.fuentes, t.estado, "sí" if t.ajustado else ""])
    ws = wb.create_sheet("Operaciones")
    ws.append(["Documento", "Renglón", "Referencia", "RFC", "Nombre", "Regla", "Incluida", "Tasa", "Tipo de cambio",
               *campos, "Nota"])
    for o in bd.scalars(select(DiotOperacion).where(DiotOperacion.periodo_id == periodo.periodo_id)
                        .order_by(DiotOperacion.fuente, DiotOperacion.renglon)):
        ws.append([lectura.TIPOS[o.fuente].nombre if o.fuente in lectura.TIPOS else o.fuente, o.renglon, o.referencia,
                   o.rfc, o.nombre, o.regla, "sí" if o.incluida else "no", o.tasa, float(o.tipo_cambio),
                   *[float(getattr(o, c)) for c in campos], o.nota])
    ws = wb.create_sheet("Incidencias")
    ws.append(["Impacto", "Código", "Mensaje", "Documento", "Renglón", "RFC", "Importe", "Estado", "Nota de revisión"])
    for i in bd.scalars(select(DiotIncidencia).where(DiotIncidencia.periodo_id == periodo.periodo_id)
                        .order_by(DiotIncidencia.incidencia_id)):
        ws.append([i.impacto, i.codigo, i.mensaje, i.fuente, i.renglon, i.rfc,
                   float(i.importe) if i.importe is not None else None, i.estado, i.nota_revision])
    ws = wb.create_sheet("Ajustes de Fiscal")
    ws.append(["RFC", "Nombre", "Campo", "Importe", "Quitar tercero", "Tipo de tercero", "Tipo de operación",
               "Motivo", "Activo"])
    for a in bd.scalars(select(DiotAjuste).where(DiotAjuste.periodo_id == periodo.periodo_id)):
        ws.append([a.rfc, a.nombre, a.campo, float(a.importe) if a.importe is not None else None,
                   "sí" if a.excluir else "", a.tipo_tercero, a.tipo_operacion, a.motivo, "sí" if a.activo else "no"])
    ws = wb.create_sheet("Documentos")
    ws.append(["Tipo", "Archivo", "Renglones", "SHA-256", "Cargado"])
    for d in vigentes(bd, periodo.periodo_id):
        ws.append([lectura.TIPOS[d.tipo].nombre, d.nombre_archivo, d.filas, d.sha256, d.cargado_en])
    ws = wb.create_sheet("Bitácora")
    co = bd.scalars(select(DiotCorrida).where(DiotCorrida.periodo_id == periodo.periodo_id)
                    .order_by(DiotCorrida.corrida_id.desc())).first()
    ws.append(["Paso", "Nombre", "Estado", "Momento", "Nivel", "Mensaje"])
    if co:
        nombres = {n: nom for n, nom, _ in motor.PASOS}
        for p in bd.scalars(select(DiotCorridaPaso).where(DiotCorridaPaso.corrida_id == co.corrida_id)
                            .order_by(DiotCorridaPaso.orden)):
            ws.append([p.orden, p.nombre, p.estado, p.fin_en, "resumen", p.resumen])
        for ln in bd.scalars(select(DiotCorridaLog).where(DiotCorridaLog.corrida_id == co.corrida_id)
                             .order_by(DiotCorridaLog.log_id)):
            ws.append([ln.orden_paso, nombres.get(ln.orden_paso), "", ln.momento, ln.nivel, ln.mensaje])
    ws = wb.create_sheet("Criterios")
    ws.append(["Clave", "Versión", "Estado", "Criterio", "Descripción", "Parámetros", "Contradicción registrada",
               "Vigente desde", "Aprobado en", "Nota de aprobación"])
    dia = date(periodo.anio, periodo.mes, 1)
    for k in conocimiento.criterios_vigentes(bd, dia, periodo.empresa_id).values():
        ws.append([k.clave, k.version, k.estado, k.titulo, k.descripcion, k.parametros or k.condicion, k.contradiccion,
                   k.vigente_desde, k.aprobado_en, k.nota_aprobacion])
    ws = wb.create_sheet("Layout y catálogos")
    ws.append(["Catálogo", "Clave", "Qué lleva", "Descripción", "Vigente desde"])
    for c in sorted(conocimiento.catalogos_vigentes(bd, dia), key=lambda c: (c.catalogo, c.clave.zfill(3))):
        ws.append([c.catalogo, c.clave, c.valor, c.descripcion, c.vigente_desde])
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()
