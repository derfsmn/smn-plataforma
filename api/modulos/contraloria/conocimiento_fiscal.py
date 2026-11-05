"""Base de conocimiento fiscal: carga inicial, lo vigente en un periodo, versiones con aprobación y «Probar con un periodo».

Pedido de Diego, 2026-10-30: que los criterios de la DIOT vivan con su documento de soporte, vigencia y aprobación de
Fiscal, para cambiarlos sin tocar el código. Cada cambio a un criterio es una versión nueva (la anterior se conserva
para reprocesar meses pasados con lo que estaba vigente) y queda en el historial con quién y por qué.
"""
import hashlib
import json
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from modulos.contraloria import diot_criterios as crit
from modulos.contraloria.modelos_diot import (
    DiotPeriodo, DiotTercero, FiscalCatalogo, FiscalCriterio, FiscalCriterioCambio, FiscalDocumento,
)
from nucleo.modelos import ahora

INICIO = date(2026, 1, 1)  # vigencia de la carga inicial
NOTA_INICIAL = ("Carga inicial: es como Fiscal trabaja hoy, reconstruido del papel de trabajo y los TXT presentados de "
                "agosto y septiembre de 2026.")
TIPOS_DOCUMENTO = {"reglas": "Reglas o criterios de Fiscal", "matriz": "Matriz de tasas", "layout": "Layout del SAT",
                   "aviso": "Aviso o disposición del SAT", "cuestionario": "Cuestionario o minuta", "otro": "Otro"}
DOCUMENTOS_INICIALES = (
    (crit.DOC_PAPEL, "reglas", "Hojas «AMARRE VS CFDI-COMPLEMENTO-BCOS», «DIOT AL PESO» y TXT presentados. El archivo "
                               "real no se guarda aquí; vive con Fiscal."),
    (crit.DOC_FISCAL, "reglas", "03 servicios profesionales, 06 arrendamiento, 07 extranjero, 85 otros; tercero 04 "
                                "nacional, 05 extranjero, 15 global."),
    (crit.DOC_MATRIZ, "matriz", "Tasas 16 %, 0 %, exentos, no objeto y conceptos fuera de la ley del IVA."),
    (crit.DOC_SAT, "aviso", "De 1 a 50 centavos se ajustan al peso anterior; de 51 a 99, al siguiente."),
    (crit.DOC_REQUERIMIENTOS, "reglas", "Reglas operativas: IMSS e INFONAVIT, FONACOT, agua, anticipos, RFC genérico."),
    (crit.DOC_RESPUESTAS, "cuestionario", "1 se suma todo y se redondea al final; 2 extranjero 05 con operación 07; 3 "
                                          "INFONAVIT se descarta, IMSS no objeto; 4 ISN no se declara, predial y "
                                          "derechos no objeto; 5 agua de tiendas y oficinas 16 % (8 % frontera); 6 global con RFC genérico, tope 10 % del total de "
                                          "pagos; 8 sin 8 %, exento ni importación; 9 layout vigente."),
)


def _json(x) -> str | None:
    return json.dumps(x, ensure_ascii=False) if x is not None else None


def _carga(x: str | None):
    return json.loads(x) if x else None


def historial(bd: Session, clave: str, version: int, accion: str, usuario_id: int | None, motivo: str | None = None,
              detalle: dict | None = None) -> None:
    bd.add(FiscalCriterioCambio(clave=clave, version=version, accion=accion, motivo=(motivo or "")[:1000] or None,
                                detalle=_json(detalle), usuario_id=usuario_id, momento=ahora()))


# ---------------------------------------------------------------- carga inicial (la corre scripts.semilla)

def sembrar(bd: Session) -> None:
    """Idempotente: agrega lo que falte (documentos por título, criterios del sistema por clave, catálogos vacíos)."""
    docs = {d.titulo: d for d in bd.scalars(select(FiscalDocumento))}
    for titulo, tipo, notas in DOCUMENTOS_INICIALES:
        if titulo not in docs:
            docs[titulo] = FiscalDocumento(titulo=titulo, tipo=tipo, notas=notas, activo=True, cargado_en=ahora())
            bd.add(docs[titulo])
    bd.flush()
    existentes = set(bd.scalars(select(FiscalCriterio.clave)))
    for d in crit.SISTEMA:
        if d.clave in existentes:
            continue
        bd.add(FiscalCriterio(clave=d.clave, version=1, tipo="sistema", categoria=d.categoria, titulo=d.titulo,
                              descripcion=d.descripcion, parametros=_json(d.parametros) if d.parametros else None,
                              contradiccion=d.contradiccion, documento_id=docs[d.documento].documento_id,
                              referencia=d.referencia, evidencia=d.evidencia, prioridad=100, vigente_desde=INICIO,
                              estado=d.estado, aprobado_en=ahora() if d.estado == crit.APROBADO else None,
                              nota_aprobacion=NOTA_INICIAL if d.estado == crit.APROBADO else None, creado_en=ahora()))
        historial(bd, d.clave, 1, "creado", None, NOTA_INICIAL + (" Queda pendiente: " + d.contradiccion
                                                                  if d.contradiccion else ""))
    if not bd.scalar(select(FiscalCatalogo.catalogo_id)):
        fiscal = docs[crit.DOC_FISCAL].documento_id
        for clave, desc in crit.TIPOS_TERCERO.items():
            bd.add(FiscalCatalogo(catalogo="tipo_tercero", clave=clave, descripcion=desc, vigente_desde=INICIO,
                                  documento_id=fiscal, creado_en=ahora()))
        for clave, desc in crit.TIPOS_OPERACION.items():
            bd.add(FiscalCatalogo(catalogo="tipo_operacion", clave=clave, descripcion=desc, vigente_desde=INICIO,
                                  documento_id=fiscal, creado_en=ahora()))
        papel = docs[crit.DOC_PAPEL].documento_id
        bd.add(FiscalCatalogo(catalogo="layout", clave="campos", valor=str(crit.CAMPOS_LAYOUT), vigente_desde=INICIO,
                              descripcion="Campos por renglón, separados por «|» (como los TXT presentados)",
                              documento_id=papel, creado_en=ahora()))
        bd.add(FiscalCatalogo(catalogo="layout", clave="efectos", valor=crit.VALOR_EFECTOS, vigente_desde=INICIO,
                              descripcion="Valor del campo de cumplimiento de requisitos fiscales (Fiscal); va en todos "
                                          "los renglones, como en los TXT presentados", documento_id=papel,
                              creado_en=ahora()))
        for n, que in crit.MAPA_LAYOUT.items():
            bd.add(FiscalCatalogo(catalogo="layout", clave=str(n), valor=que, descripcion=crit.QUE_LLEVA[que],
                                  vigente_desde=INICIO, documento_id=papel, creado_en=ahora()))
    bd.commit()


# ---------------------------------------------------------------- lo vigente

def _vigente(desde: date, hasta: date | None, dia: date) -> bool:
    return desde <= dia and (hasta is None or hasta >= dia)


def criterios_vigentes(bd: Session, dia: date, empresa_id: int | None = None) -> dict[str, FiscalCriterio]:
    """La versión vigente de cada criterio en ese día: la de número más alto cuya vigencia lo cubre."""
    q = select(FiscalCriterio).where(FiscalCriterio.vigente_desde <= dia,
                                     or_(FiscalCriterio.vigente_hasta.is_(None), FiscalCriterio.vigente_hasta >= dia))
    if empresa_id is not None:
        q = q.where(or_(FiscalCriterio.empresa_id.is_(None), FiscalCriterio.empresa_id == empresa_id))
    else:
        q = q.where(FiscalCriterio.empresa_id.is_(None))
    vig: dict[str, FiscalCriterio] = {}
    for c in bd.scalars(q.order_by(FiscalCriterio.clave, FiscalCriterio.version)):
        vig[c.clave] = c
    return vig


def catalogos_vigentes(bd: Session, dia: date) -> list[FiscalCatalogo]:
    q = select(FiscalCatalogo).where(FiscalCatalogo.vigente_desde <= dia, or_(FiscalCatalogo.vigente_hasta.is_(None),
                                                                              FiscalCatalogo.vigente_hasta >= dia))
    ultimo: dict[tuple[str, str], FiscalCatalogo] = {}
    for c in bd.scalars(q.order_by(FiscalCatalogo.catalogo_id)):
        ultimo[(c.catalogo, c.clave)] = c  # si hay dos vigentes, el más reciente
    return list(ultimo.values())


def a_criterio(c: FiscalCriterio) -> crit.Criterio:
    return crit.Criterio(clave=c.clave, titulo=c.titulo, estado=c.estado, parametros=_carga(c.parametros) or {},
                         version=c.version, tipo=c.tipo, condicion=_carga(c.condicion), accion=_carga(c.accion),
                         prioridad=c.prioridad, descripcion=c.descripcion)


def config(bd: Session, dia: date, empresa_id: int | None = None) -> crit.Config:
    cfg = crit.inicial()
    vig = criterios_vigentes(bd, dia, empresa_id)
    if vig:
        cfg.criterios = {k: a_criterio(c) for k, c in vig.items() if c.estado != crit.RETIRADO}
        cfg.origen = f"vigente al {dia:%d/%m/%Y}"
    cats = catalogos_vigentes(bd, dia)
    tt = {c.clave: c.descripcion for c in cats if c.catalogo == "tipo_tercero"}
    to = {c.clave: c.descripcion for c in cats if c.catalogo == "tipo_operacion"}
    lay = [c for c in cats if c.catalogo == "layout"]
    if tt:
        cfg.tipos_tercero = dict(sorted(tt.items()))
    if to:
        cfg.tipos_operacion = dict(sorted(to.items()))
    if lay:
        cfg.mapa = {int(c.clave): c.valor for c in lay if c.clave.isdigit() and c.valor}
        for c in lay:
            if c.clave == "campos" and (c.valor or "").isdigit():
                cfg.campos_layout = int(c.valor)
            elif c.clave == "efectos":
                cfg.efectos = c.valor or ""
    return cfg


def config_periodo(bd: Session, periodo: DiotPeriodo) -> crit.Config:
    return config(bd, date(periodo.anio, periodo.mes, 1), periodo.empresa_id)


# ---------------------------------------------------------------- cambios

class ErrorCriterio(Exception):
    pass


def ultima(bd: Session, clave: str) -> FiscalCriterio | None:
    return bd.scalars(select(FiscalCriterio).where(FiscalCriterio.clave == clave)
                      .order_by(FiscalCriterio.version.desc())).first()


def validar_parametros(clave: str, parametros: dict) -> dict:
    d = crit.POR_CLAVE.get(clave)
    if not d:
        raise ErrorCriterio("Ese criterio no es del sistema.")
    limpios = {}
    for nombre, etiqueta, tipo, opciones in d.campos:
        v = parametros.get(nombre, d.parametros.get(nombre))
        if tipo == "lista":
            if not isinstance(v, list):
                raise ErrorCriterio(f"«{etiqueta}» debe ser una lista.")
            v = [str(x).strip() for x in v if str(x).strip()]
        elif tipo == "opcion":
            if v not in opciones:
                raise ErrorCriterio(f"«{etiqueta}»: opción no válida.")
        else:
            v = str(v or "").strip()
            if clave == "TER-TIPO-OPERACION" and not (v.isdigit() and len(v) <= 2):
                raise ErrorCriterio(f"«{etiqueta}» debe ser una clave de dos dígitos.")
            if nombre == "tope_global" and not v.replace(".", "", 1).isdigit():
                raise ErrorCriterio(f"«{etiqueta}» debe ser un número.")
        limpios[nombre] = v
    return limpios


def validar_propio(condicion: dict, accion: dict) -> tuple[dict, dict]:
    cond = {k: str(condicion.get(k) or "").strip() for k in ("fuente", "campo", "operador", "valor")}
    if cond["fuente"] not in crit.FUENTES_PROPIAS or cond["campo"] not in crit.CAMPOS_CONDICION \
            or cond["operador"] not in crit.OPERADORES or not cond["valor"]:
        raise ErrorCriterio("La condición necesita documento, campo, comparación y un valor.")
    acc = {"accion": str(accion.get("accion") or "")}
    if acc["accion"] not in crit.ACCIONES:
        raise ErrorCriterio("Elige qué hace el criterio.")
    if acc["accion"] == "tipo_operacion":
        to = str(accion.get("tipo_operacion") or "").zfill(2)
        if cond["campo"] != "rfc" or cond["operador"] != "igual":
            raise ErrorCriterio("Para cambiar el tipo de operación, la condición debe ser «RFC es igual a».")
        acc["tipo_operacion"] = to
    return cond, acc


def nueva_version(bd: Session, clave: str, cambios: dict, usuario_id: int, motivo: str, desde: date,
                  borrador: bool = False) -> FiscalCriterio:
    """Copia la última versión con los cambios; queda pendiente (o en borrador) hasta que alguien con permiso la
    apruebe. Las versiones anteriores se conservan para los meses que ya cubrían."""
    prev = ultima(bd, clave)
    if not prev:
        raise ErrorCriterio("Ese criterio no existe.")
    if prev.estado == crit.RETIRADO:
        raise ErrorCriterio("Ese criterio está retirado.")
    if not motivo.strip():
        raise ErrorCriterio("Escribe el motivo del cambio.")
    nueva = FiscalCriterio(**{c.name: getattr(prev, c.name) for c in FiscalCriterio.__table__.columns
                              if c.name not in ("criterio_id",)})
    nueva.version = prev.version + 1
    antes = {}
    for k, v in cambios.items():
        if k == "parametros":
            v = _json(validar_parametros(clave, v))
        elif k in ("condicion", "accion"):
            continue
        if getattr(nueva, k) != v:
            antes[k] = getattr(nueva, k)
            setattr(nueva, k, v)
    if "condicion" in cambios or "accion" in cambios:
        cond, acc = validar_propio(cambios.get("condicion") or _carga(prev.condicion) or {},
                                   cambios.get("accion") or _carga(prev.accion) or {})
        nueva.condicion, nueva.accion = _json(cond), _json(acc)
    nueva.vigente_desde, nueva.vigente_hasta = desde, None
    nueva.estado = crit.BORRADOR if borrador else crit.PENDIENTE
    nueva.aprobado_por = nueva.aprobado_en = nueva.nota_aprobacion = None
    nueva.creado_por, nueva.creado_en = usuario_id, ahora()
    for v in bd.scalars(select(FiscalCriterio).where(FiscalCriterio.clave == clave,
                                                     FiscalCriterio.vigente_hasta.is_(None))):
        if v.vigente_desde < desde:
            v.vigente_hasta = desde - timedelta(days=1)
    bd.add(nueva)
    historial(bd, clave, nueva.version, "editado", usuario_id, motivo,
              {"antes": {k: (_carga(v) if k == "parametros" else str(v) if isinstance(v, date) else v)
                         for k, v in antes.items()}, "desde": desde.isoformat()})
    return nueva


def nuevo_propio(bd: Session, datos: dict, usuario_id: int, desde: date, borrador: bool = False) -> FiscalCriterio:
    cond, acc = validar_propio(datos.get("condicion") or {}, datos.get("accion") or {})
    if not (datos.get("titulo") or "").strip():
        raise ErrorCriterio("Ponle un título al criterio.")
    n = len(set(bd.scalars(select(FiscalCriterio.clave).where(FiscalCriterio.tipo == "propio")))) + 1
    clave = f"PROPIO-{n:03d}"
    while ultima(bd, clave):
        n += 1
        clave = f"PROPIO-{n:03d}"
    c = FiscalCriterio(clave=clave, version=1, tipo="propio", categoria="propio", titulo=datos["titulo"].strip()[:200],
                       descripcion=(datos.get("descripcion") or "").strip()[:2000], condicion=_json(cond),
                       accion=_json(acc), documento_id=datos.get("documento_id"), referencia=datos.get("referencia"),
                       evidencia=datos.get("evidencia"), prioridad=int(datos.get("prioridad") or 100),
                       empresa_id=datos.get("empresa_id"), vigente_desde=desde,
                       estado=crit.BORRADOR if borrador else crit.PENDIENTE, creado_por=usuario_id, creado_en=ahora())
    bd.add(c)
    historial(bd, clave, 1, "creado", usuario_id, datos.get("motivo"))
    return c


def cambiar_estado(bd: Session, c: FiscalCriterio, accion: str, usuario_id: int, nota: str | None) -> None:
    if accion == "aprobar":
        if c.estado not in (crit.PENDIENTE, crit.BORRADOR):
            raise ErrorCriterio("Solo se aprueba un criterio pendiente o en borrador.")
        c.estado, c.aprobado_por, c.aprobado_en, c.nota_aprobacion = crit.APROBADO, usuario_id, ahora(), nota
        historial(bd, c.clave, c.version, "aprobado", usuario_id, nota)
    elif accion == "regresar":
        if c.estado != crit.PENDIENTE or not (nota or "").strip():
            raise ErrorCriterio("Solo se regresa un criterio pendiente, con el motivo.")
        c.estado = crit.BORRADOR
        historial(bd, c.clave, c.version, "regresado", usuario_id, nota)
    elif accion == "enviar":
        if c.estado != crit.BORRADOR:
            raise ErrorCriterio("Solo se manda a aprobar un criterio en borrador.")
        c.estado = crit.PENDIENTE
        historial(bd, c.clave, c.version, "enviado", usuario_id, nota)
    elif accion == "retirar":
        if c.tipo != "propio" or not (nota or "").strip():
            raise ErrorCriterio("Solo se retiran criterios propios, con el motivo. Los del sistema se cambian.")
        c.estado = crit.RETIRADO
        historial(bd, c.clave, c.version, "retirado", usuario_id, nota)
    else:
        raise ErrorCriterio("Acción no válida.")


def catalogo_nuevo(bd: Session, catalogo: str, clave: str, descripcion: str, valor: str | None, desde: date,
                   documento_id: int | None, usuario_id: int) -> FiscalCatalogo:
    """Alta o cambio de un renglón de catálogo desde una fecha; el anterior con la misma clave queda hasta un día
    antes."""
    if catalogo not in ("tipo_tercero", "tipo_operacion", "layout"):
        raise ErrorCriterio("Catálogo no válido.")
    clave = clave.strip()
    if catalogo == "layout":
        if clave not in ("campos", "efectos") and not (clave.isdigit() and 1 <= int(clave) <= 200):
            raise ErrorCriterio("En el layout, la clave es el número de campo.")
        if clave.isdigit() and valor not in crit.QUE_LLEVA:
            raise ErrorCriterio("Elige qué lleva el campo.")
        if clave == "campos" and not (valor or "").isdigit():
            raise ErrorCriterio("El número de campos debe ser un número.")
    elif not (clave.isdigit() and len(clave) == 2):
        raise ErrorCriterio("La clave es de dos dígitos.")
    for v in bd.scalars(select(FiscalCatalogo).where(FiscalCatalogo.catalogo == catalogo, FiscalCatalogo.clave == clave,
                                                     FiscalCatalogo.vigente_hasta.is_(None))):
        v.vigente_hasta = max(v.vigente_desde, desde - timedelta(days=1))
    c = FiscalCatalogo(catalogo=catalogo, clave=clave, descripcion=descripcion.strip()[:500] or clave, valor=valor,
                       vigente_desde=desde, documento_id=documento_id, creado_por=usuario_id, creado_en=ahora())
    bd.add(c)
    return c


def documento_nuevo(bd: Session, titulo: str, tipo: str, nombre: str | None, contenido: bytes | None,
                    version: str | None, desde: date | None, notas: str | None, usuario_id: int,
                    reemplaza: FiscalDocumento | None = None) -> FiscalDocumento:
    if tipo not in TIPOS_DOCUMENTO:
        raise ErrorCriterio("Tipo de documento no válido.")
    d = FiscalDocumento(titulo=titulo.strip()[:300], tipo=tipo, version=version, vigente_desde=desde, notas=notas,
                        nombre_archivo=(nombre or "")[:260] or None, contenido=contenido,
                        tamano=len(contenido) if contenido else None,
                        sha256=hashlib.sha256(contenido).hexdigest() if contenido else None, activo=True,
                        reemplaza_a=reemplaza.documento_id if reemplaza else None, cargado_por=usuario_id,
                        cargado_en=ahora())
    if reemplaza:
        reemplaza.activo = False
    bd.add(d)
    return d


# ---------------------------------------------------------------- probar con un periodo

def probar(bd: Session, periodo: DiotPeriodo, criterio: FiscalCriterio | None = None) -> dict:
    """Corre el proceso con lo vigente (y, si se da, con ese criterio como si estuviera aprobado) sin guardar nada, y lo
    compara contra el último resultado guardado del periodo."""
    from modulos.contraloria import diot
    from modulos.contraloria import diot_motor as motor

    cfg = config_periodo(bd, periodo)
    if criterio is not None:
        k = a_criterio(criterio)
        k.estado = crit.APROBADO
        cfg.criterios[criterio.clave] = k
    docs = diot.leer_documentos(bd, periodo)
    if not docs:
        raise ErrorCriterio("Ese periodo no tiene documentos cargados.")
    r = motor.procesar(docs, periodo.empresa.rfc or "", diot.ajustes_de(bd, periodo.periodo_id), cfg=cfg)
    antes = {t.rfc: t for t in bd.scalars(select(DiotTercero).where(DiotTercero.periodo_id == periodo.periodo_id))}
    despues = {t.rfc: t for t in r.terceros}
    cambios = []
    for rfc in sorted(set(antes) | set(despues)):
        a, d = antes.get(rfc), despues.get(rfc)
        if a is None or d is None:
            cambios.append({"rfc": rfc, "que": "entra a la DIOT" if d else "sale de la DIOT", "antes": None,
                            "despues": None})
            continue
        ra = json.loads(a.redondeados)
        for k in motor.CAMPOS:
            if int(ra.get(k, 0)) != d.redondeados[k]:
                cambios.append({"rfc": rfc, "que": crit.QUE_LLEVA[k], "antes": str(ra.get(k, 0)),
                                "despues": str(d.redondeados[k])})
        for k, nombre in (("tipo_tercero", "Tipo de tercero"), ("tipo_operacion", "Tipo de operación")):
            if getattr(a, k) != getattr(d, k):
                cambios.append({"rfc": rfc, "que": nombre, "antes": getattr(a, k), "despues": getattr(d, k)})
    pendientes = [i.mensaje for i in r.incidencias if i.codigo == "CRITERIO-PENDIENTE"]
    return {"periodo": f"{diot.MESES[periodo.mes - 1]} {periodo.anio}", "procesado": bool(antes),
            "terceros_antes": len(antes), "terceros_despues": len(despues), "cambios": cambios,
            "txt": bool(r.txt), "bloqueado": r.bloqueado,
            "incidencias_posibles": sum(1 for i in r.incidencias if i.impacto == motor.POSIBLE),
            "criterios_pendientes": pendientes}
