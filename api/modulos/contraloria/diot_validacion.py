"""DIOT: las comprobaciones que dicen, en palabras, si el TXT de un mes está bien (plan «Plan DIOT: validar el TXT sin
ser fiscalista», aprobado por Diego el 2026-10-30).

Todo sale de lo que ya guardó el último «Procesar» (operaciones, terceros, incidencias, cuadres) más lo que captura
quien revisa (muestra de proveedores, motivo de cada diferencia contra lo presentado, IVA de la declaración mensual).
Nada de esto cambia el resultado: si algo no cuadra, se corrige con un ajuste de Fiscal o un criterio de la base.
Sin IA.
"""
import hashlib
import json
import random
import re
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from modulos.contraloria import diot
from modulos.contraloria import diot_lectura as lectura
from modulos.contraloria import diot_motor as motor
from modulos.contraloria.modelos_diot import (
    DiotAjuste, DiotFirma, DiotIncidencia, DiotOperacion, DiotPeriodo, DiotRevision, DiotTercero,
)
from nucleo.modelos import Usuario

CERO = Decimal("0")
OK, REVISAR, FALLA, SIN_DATOS, INFO = "ok", "revisar", "falla", "sin_datos", "info"
MUESTRA_GRANDES, MUESTRA_AZAR = 10, 5
CAMBIO_MES = Decimal("0.30")  # cambio contra el mes anterior que vale la pena mirar
CAMBIO_MINIMO = Decimal("10000")  # y que mueva al menos esto en pesos
CAMPOS_MONTO = ("base16", "base8", "base0", "exento", "no_objeto")

# Si es True, el TXT solo se descarga con las dos firmas. Lo enciende Transformación Digital cuando Fiscal lo acepte.
FIRMAS_OBLIGATORIAS = False

MOTIVOS_DIFERENCIA = {
    "ajuste_fiscal": "Ajuste a mano de Fiscal (se debe capturar como ajuste con su motivo)",
    "criterio": "La regla es distinta: hay que cambiar un criterio en la base",
    "error_plataforma": "Error de la plataforma: hay que corregirlo",
    "error_presentado": "Error en lo que se presentó",
    "otro": "Otro (explícalo en la nota)",
}

# Las 12 verificaciones del formato (diot_layout.validar), dichas sin términos técnicos.
FORMATO = {
    "Fin de renglón": "Cada renglón termina como lo pide el portal del SAT.",
    "Caracteres": "No hay acentos ni ñ, que el portal rechaza.",
    "Número de campos": "Cada renglón trae todos los datos que pide el SAT.",
    "Renglones contra consolidado": "Hay un renglón por cada proveedor que se calculó.",
    "Tipo de tercero": "Cada proveedor dice si es nacional, extranjero o global con una clave que el SAT acepta.",
    "Tipo de operación": "Cada proveedor dice qué tipo de compra es con una clave que el SAT acepta.",
    "RFC": "Los RFC de los proveedores nacionales están bien escritos.",
    "Registros únicos": "Ningún proveedor aparece dos veces.",
    "Importes": "Los importes son pesos enteros, sin centavos ni negativos.",
    "Renglones con importe": "Ningún proveedor va en ceros.",
    "IVA contra base": "En cada proveedor, el IVA es el 16 % (u 8 %) de lo que se le pagó sin IVA.",
    "Totales": "Los totales del archivo son los mismos que los del cálculo.",
}

# Embudo: por qué cada renglón de los reportes entra o no a la DIOT, en palabras.
NO_ENTRA = {
    "TES-BANCO": "Movimientos del banco (intereses, comisiones, ISR retenido): no son pagos a proveedores",
    "TES-NOMINA": "Nómina, finiquitos e impuestos de nómina: no se declaran",
    "TES-ANTICIPO-SF": "Anticipos sin factura: se declaran cuando se aplican",
    "TES-ANTICIPO": "Gastos a comprobar: se declaran con su comprobante",
    "TES-CAJA-CHICA": "Reembolsos de caja chica: se declaran sus comprobantes, no el reembolso",
    "TES-PROPIA": "Pagos a la propia empresa",
    "COM-PROPIA": "Gastos a nombre de la propia empresa",
    "TES-IMSS": "IMSS (cuando Fiscal decide no declararlo)",
    "COM-AUXILIAR": "Gastos cuya póliza no está en el IVA acreditable del mes",
    "COM-CANCELADO": "Comprobantes cancelados",
    "APL-OTRO": "Movimientos de cuentas por pagar que no son aplicación de anticipo con IVA",
    "RET-AUXILIAR": "IVA retenido sin proveedor",
}
SIN_EXPLICAR = {"TES-SIN-TASA", "COM-NO-OBJETO"}  # no entran porque falta una decisión
ENTRA = {"16": "Con IVA (16 % u 8 %)", "8": "Con IVA (16 % u 8 %)", "0": "A tasa 0 %",
         "no_objeto": "Sin IVA por ley (no objeto) o exentos", "exento": "Sin IVA por ley (no objeto) o exentos"}
CODIGOS_SIN_CLASIFICAR = ("SIN-TASA", "TASA-RARA", "SIN-IVA", "SIN-RFC", "RET-SIN-ACREEDOR", "VALOR")


def _pesos(x) -> str:
    x = Decimal(x).quantize(Decimal("1")) + 0
    return f"{'-' if x < 0 else ''}${abs(x):,.0f}"


def _huella(x) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def huella_txt(p: DiotPeriodo) -> str | None:
    return hashlib.sha256(p.txt.encode()).hexdigest() if p.txt else None


def _nombre(bd: Session, uid: int | None) -> str | None:
    u = bd.get(Usuario, uid) if uid else None
    return u.nombre if u else None


def _terceros(bd: Session, periodo_id: int) -> list[DiotTercero]:
    return list(bd.scalars(select(DiotTercero).where(DiotTercero.periodo_id == periodo_id)))


def _iva(t: DiotTercero) -> int:
    r = json.loads(t.redondeados)
    return int(r.get("iva16", 0)) + int(r.get("iva8", 0))


def _monto(t: DiotTercero) -> int:
    r = json.loads(t.redondeados)
    return sum(int(r.get(c, 0)) for c in CAMPOS_MONTO) + _iva(t)


def _anterior(bd: Session, p: DiotPeriodo) -> DiotPeriodo | None:
    anio, mes = (p.anio, p.mes - 1) if p.mes > 1 else (p.anio - 1, 12)
    return bd.scalars(select(DiotPeriodo).where(DiotPeriodo.empresa_id == p.empresa_id, DiotPeriodo.anio == anio,
                                                DiotPeriodo.mes == mes)).first()


def _revisiones(bd: Session, periodo_id: int, tipo: str) -> dict[str, DiotRevision]:
    return {r.clave: r for r in bd.scalars(select(DiotRevision).where(DiotRevision.periodo_id == periodo_id,
                                                                      DiotRevision.tipo == tipo))}


# ---------------------------------------------------------------- 1. contabilidad

def _contabilidad(bd: Session, p: DiotPeriodo, resumen: dict, ok: list[DiotTercero]) -> dict:
    c = {"clave": "contabilidad", "titulo": "Cuadra con contabilidad",
         "pregunta": "¿El IVA del TXT es el mismo que registró contabilidad?"}
    cuadres = resumen.get("cuadres") or []
    if not cuadres or not p.txt:
        return {**c, "estado": SIN_DATOS, "frase": "Todavía no hay TXT que comparar.", "detalle": {}}
    iva_txt = sum(_iva(t) for t in ok)
    auxiliar = sum((Decimal(str(x["auxiliar"])) for x in cuadres), CERO)
    # Lo que los ajustes de Fiscal mueven a propósito: sumas al IVA y terceros quitados.
    ajustes = list(bd.scalars(select(DiotAjuste).where(DiotAjuste.periodo_id == p.periodo_id,
                                                       DiotAjuste.activo == true())))
    por_ajuste = sum((a.importe or CERO for a in ajustes if a.campo in ("iva16", "iva8")), CERO)
    quitados = {a.rfc for a in ajustes if a.excluir}
    if quitados:
        por_ajuste -= sum((o.iva16 + o.iva8 for o in bd.scalars(select(DiotOperacion).where(
            DiotOperacion.periodo_id == p.periodo_id, DiotOperacion.incluida == true(),
            DiotOperacion.rfc.in_(quitados)))), CERO)
    diferencia = Decimal(iva_txt) - auxiliar
    tolerancia = Decimal("0.5") * len(ok) + 1  # cada proveedor se redondea al peso: hasta 50 centavos cada uno
    detalle = {"iva_txt": iva_txt, "iva_contabilidad": float(auxiliar), "diferencia": float(diferencia),
               "por_ajustes": float(por_ajuste), "tolerancia": float(tolerancia),
               "grupos": [{"concepto": x["concepto"], "calculado": float(Decimal(str(x["importe"]))),
                           "contabilidad": float(Decimal(str(x["auxiliar"]))),
                           "diferencia": float(Decimal(str(x["diferencia"])))} for x in cuadres]}
    if abs(diferencia) <= tolerancia:
        return {**c, "estado": OK, "detalle": detalle,
                "frase": f"Sí. IVA del TXT {_pesos(iva_txt)} contra {_pesos(auxiliar)} en contabilidad: "
                         f"{_pesos(abs(diferencia))} de diferencia por redondear cada proveedor al peso."}
    if por_ajuste and abs(diferencia - por_ajuste) <= tolerancia:
        return {**c, "estado": OK, "detalle": detalle,
                "frase": f"Sí, con ajustes. IVA del TXT {_pesos(iva_txt)} contra {_pesos(auxiliar)} en contabilidad; "
                         f"la diferencia ({_pesos(diferencia)}) son los ajustes de Fiscal ({_pesos(por_ajuste)}), "
                         "cada uno con su motivo."}
    return {**c, "estado": FALLA, "detalle": detalle,
            "frase": f"No. IVA del TXT {_pesos(iva_txt)} contra {_pesos(auxiliar)} en contabilidad: "
                     f"{_pesos(diferencia)} de diferencia que no explican ni el redondeo ni los ajustes. "
                     "Revisa la conciliación por grupo."}


# ---------------------------------------------------------------- 2. pagos explicados (embudo)

def embudo(bd: Session, periodo_id: int) -> list[dict]:
    """Por reporte: cuánto trae, cuánto entra a la DIOT y por qué lo demás no entra."""
    salida = []
    por_fuente: dict[str, list[DiotOperacion]] = defaultdict(list)
    for o in bd.scalars(select(DiotOperacion).where(DiotOperacion.periodo_id == periodo_id)):
        por_fuente[o.fuente].append(o)
    for fuente in ("tesoreria", "aplicaciones", "comprobantes"):
        ops = por_fuente.get(fuente, [])
        if not ops:
            continue
        grupos: dict[tuple[str, str], list] = {}
        for o in ops:
            if o.incluida and o.rfc:
                k = ("entra", ENTRA.get(o.tasa or "", "Entra a la DIOT"))
            elif o.incluida:
                k = ("sin_explicar", "Sin RFC: falta saber de qué proveedor es")
            elif o.regla in SIN_EXPLICAR:
                k = ("sin_explicar", "Sin clasificar: falta decidir si lleva IVA")
            elif o.regla.startswith("PROPIO-"):
                k = ("no_entra", "Quitados por un criterio propio de Fiscal")
            else:
                k = ("no_entra", NO_ENTRA.get(o.regla, f"No entra ({o.regla})"))
            g = grupos.setdefault(k, [0, CERO, 0])
            g[0] += 1
            g[1] += o.monto or CERO
            g[2] += 0 if o.monto is not None else 1
        orden = {"entra": 0, "sin_explicar": 1, "no_entra": 2}
        filas = [{"tipo": k[0], "concepto": k[1], "renglones": v[0], "monto": float(v[1]), "sin_monto": v[2]}
                 for k, v in sorted(grupos.items(), key=lambda x: (orden[x[0][0]], -x[1][1]))]
        salida.append({"fuente": fuente, "nombre": lectura.TIPOS[fuente].nombre, "renglones": len(ops),
                       "monto": float(sum((o.monto or CERO for o in ops), CERO)), "grupos": filas})
    return salida


def _pagos(bd: Session, p: DiotPeriodo) -> dict:
    c = {"clave": "pagos", "titulo": "Ningún pago sin explicar",
         "pregunta": "¿Cada renglón de los reportes entra a la DIOT o tiene una razón escrita para no entrar?"}
    e = embudo(bd, p.periodo_id)
    if not e:
        return {**c, "estado": SIN_DATOS, "frase": "Procesa el mes para ver de dónde sale el resultado.",
                "detalle": {"embudo": []}}
    pendientes = list(bd.scalars(select(DiotIncidencia).where(
        DiotIncidencia.periodo_id == p.periodo_id, DiotIncidencia.estado == "pendiente",
        DiotIncidencia.codigo.in_(CODIGOS_SIN_CLASIFICAR))))
    total = sum(f["renglones"] for f in e)
    entran = sum(g["renglones"] for f in e for g in f["grupos"] if g["tipo"] == "entra")
    if pendientes:
        return {**c, "estado": FALLA, "detalle": {"embudo": e},
                "frase": f"No. {len(pendientes)} renglón(es) no tienen clasificación y nadie ha decidido qué hacer "
                         "con ellos. Están en «Necesitan tu decisión»."}
    return {**c, "estado": OK, "detalle": {"embudo": e},
            "frase": f"Sí. De {total:,} renglones, {entran:,} entran a la DIOT y los demás tienen su razón "
                     "(nómina, banco, anticipos, caja chica…)."}


# ---------------------------------------------------------------- 3. declaración de IVA

def _declaracion(bd: Session, p: DiotPeriodo, ok: list[DiotTercero]) -> dict:
    c = {"clave": "declaracion", "titulo": "Cuadra con la declaración de IVA",
         "pregunta": "¿El IVA acreditable del TXT es el que Fiscal puso en la declaración mensual?"}
    if p.iva_declarado is None:
        return {**c, "estado": SIN_DATOS, "detalle": {},
                "frase": "Falta un número que da Fiscal: cuánto IVA de proveedores puso en la declaración de IVA del mes. "
                          "Toca aquí para capturarlo."}
    iva_txt = sum(_iva(t) for t in ok)
    dif = Decimal(iva_txt) - p.iva_declarado
    tol = Decimal("0.5") * len(ok) + 1
    detalle = {"iva_txt": iva_txt, "iva_declarado": float(p.iva_declarado), "diferencia": float(dif),
               "nota": p.iva_declarado_nota, "capturado_por": _nombre(bd, p.iva_declarado_por),
               "capturado_en": p.iva_declarado_en}
    if abs(dif) <= tol:
        return {**c, "estado": OK, "detalle": detalle,
                "frase": f"Sí. {_pesos(iva_txt)} en el TXT contra {_pesos(p.iva_declarado)} declarados."}
    return {**c, "estado": REVISAR, "detalle": detalle,
            "frase": f"No. {_pesos(iva_txt)} en el TXT contra {_pesos(p.iva_declarado)} declarados "
                     f"({_pesos(dif)}). Pregunta a Fiscal de dónde sale la diferencia."}


# ---------------------------------------------------------------- 4. muestra de proveedores

def _huella_tercero(t: DiotTercero) -> str:
    return _huella([t.rfc, t.tipo_tercero, t.tipo_operacion, json.loads(t.redondeados)])


def muestra(bd: Session, p: DiotPeriodo, ok: list[DiotTercero]) -> list[dict]:
    """Los 10 proveedores con más IVA y 5 al azar (el azar es fijo por periodo para que no cambie al recargar)."""
    orden = sorted(ok, key=lambda t: (-_iva(t), -_monto(t), t.rfc))
    grandes = orden[:MUESTRA_GRANDES]
    resto = sorted(orden[MUESTRA_GRANDES:], key=lambda t: t.rfc)
    azar = random.Random(p.periodo_id).sample(resto, min(MUESTRA_AZAR, len(resto)))
    marcas = _revisiones(bd, p.periodo_id, "muestra")
    salida = []
    for motivo, lista in (("grande", grandes), ("azar", azar)):
        for t in lista:
            m = marcas.get(t.rfc)
            vigente = bool(m and m.huella == _huella_tercero(t))
            salida.append({"rfc": t.rfc, "nombre": t.nombre, "motivo": motivo, "iva": _iva(t), "monto": _monto(t),
                           "operaciones": t.operaciones, "revisado": vigente,
                           "revisado_por": _nombre(bd, m.usuario_id) if vigente else None,
                           "revisado_en": m.momento if vigente else None, "nota": m.nota if vigente else None,
                           "cambio_desde_revision": bool(m and not vigente)})
    return salida


def _muestra(bd: Session, p: DiotPeriodo, ok: list[DiotTercero]) -> dict:
    c = {"clave": "muestra", "titulo": "Cada proveedor se puede rastrear",
         "pregunta": "¿Los proveedores más grandes y unos al azar cuadran con sus pagos y facturas?"}
    if not ok:
        return {**c, "estado": SIN_DATOS, "frase": "No hay proveedores que revisar.", "detalle": {"muestra": []}}
    m = muestra(bd, p, ok)
    faltan = sum(1 for x in m if not x["revisado"])
    cubre = sum(x["iva"] for x in m)
    total = sum(_iva(t) for t in ok) or 1
    detalle = {"muestra": m, "porcentaje_iva": round(cubre * 100 / total)}
    if faltan:
        return {**c, "estado": REVISAR, "detalle": detalle,
                "frase": f"Faltan {faltan} de {len(m)} proveedores por revisar. La muestra cubre el "
                         f"{detalle['porcentaje_iva']} % del IVA del mes."}
    return {**c, "estado": OK, "detalle": detalle,
            "frase": f"Sí. Se revisaron los {len(m)} proveedores de la muestra ({detalle['porcentaje_iva']} % del IVA "
                     "del mes)."}


# ---------------------------------------------------------------- 4b. pagos contra el banco

FOLIO = re.compile(r"\b([A-Z]{2,5}\d+)\b")
TOLERANCIA_BANCO = Decimal("0.05")
_banco_cache: dict[tuple, dict] = {}


def _num(v) -> Decimal | None:
    try:
        return lectura.decimal(v)
    except ValueError:
        return None


def _dia(v) -> str:
    """La fecha como AAAA-MM-DD, venga como fecha de Excel, «2026/08/04» o «2026-08-04 00:00:00»."""
    return lectura.texto(v).replace("/", "-")[:10]


def _cargos_del_banco(t: lectura.Tabla) -> tuple[dict[str, list[Decimal]], list[dict], dict[str, str], dict[str, str]]:
    """Cargos del estado de cuenta con el folio de Intelisis (MovID) que trae la columna «Folio Aceptación»."""
    con_folio: dict[str, list[Decimal]] = defaultdict(list)
    descripcion: dict[str, str] = {}
    fecha: dict[str, str] = {}
    sin_folio = []
    for f in t.filas:
        if lectura.texto(f.get("Tipo de Movimiento")).upper() != "CARGO":
            continue
        imp = _num(f.get("Importe"))
        if imp is None:
            continue
        m = FOLIO.search(lectura.texto(f.get("Folio Aceptación")).upper())
        if m:
            con_folio[m.group(1)].append(abs(imp))
            descripcion.setdefault(m.group(1), " ".join(x for x in (lectura.texto(f.get("Transacción")),
                                                                     lectura.texto(f.get("Referencia"))) if x))
            fecha.setdefault(m.group(1), _dia(f.get("Fecha Operación") or f.get("Fecha Valor")))
        else:
            sin_folio.append({"descripcion": lectura.texto(f.get("Transacción")), "importe": float(abs(imp)),
                              "fecha": lectura.texto(f.get("Fecha Operación") or f.get("Fecha Valor"))})
    return con_folio, sin_folio, descripcion, fecha


def comparar_banco(tesoreria: lectura.Tabla, estados: list[tuple[str, lectura.Tabla]]) -> dict:
    """Cada pago de tesorería (uno por MovID; el reporte repite el pago en cada renglón de impuesto) contra los cargos
    del banco con ese folio. Un pago puede salir en varios cargos (se suman). La cuenta de cada estado de cuenta es la
    CtaDinero de tesorería con más folios encontrados en él."""
    pagos: dict[str, dict] = {}
    for f in tesoreria.filas:
        mov = lectura.texto(f.get("Mov"))
        movid = lectura.texto(f.get("MovID")).upper()
        if not movid or mov.upper().startswith("ABONO"):
            continue
        imp = _num(f.get("Importe"))
        if imp is None:
            continue
        pagos.setdefault(movid, {"movid": movid, "mov": mov, "cuenta": lectura.texto(f.get("CtaDinero")),
                                 "beneficiario": lectura.texto(f.get("BeneficiarioNombre")),
                                 "fecha": lectura.texto(f.get("FechaEmision"))[:10], "importe": abs(imp)})
    por_cuenta: dict[str, list[dict]] = defaultdict(list)
    for x in pagos.values():
        por_cuenta[x["cuenta"]].append(x)
    cuentas, cubiertas = [], set()
    for nombre, t in estados:
        cargos, sin_folio, descripcion, fecha = _cargos_del_banco(t)
        cuenta = max(por_cuenta, key=lambda c: sum(1 for x in por_cuenta[c] if x["movid"] in cargos), default=None)
        if cuenta is None or not any(x["movid"] in cargos for x in por_cuenta[cuenta]):
            cuentas.append({"archivo": nombre, "cuenta": None, "pagos": 0, "confirmados": 0, "diferencias": [],
                            "no_encontrados": [], "otro_folio": [], "solo_banco": [], "sin_folio": len(sin_folio)})
            continue
        cubiertas.add(cuenta)
        confirmados, diferencias, no_encontrados = 0, [], []
        for x in sorted(por_cuenta[cuenta], key=lambda x: x["movid"]):
            en_banco = cargos.get(x["movid"])
            if en_banco is None:
                no_encontrados.append({**x, "importe": float(x["importe"])})
            elif abs(sum(en_banco) - x["importe"]) <= TOLERANCIA_BANCO:
                confirmados += 1
            else:
                diferencias.append({**x, "importe": float(x["importe"]), "banco": float(sum(en_banco)),
                                    "cargos": len(en_banco)})
        propios = {x["movid"] for x in pagos.values()}
        ajenos = {k: v for k, v in sorted(cargos.items()) if k not in propios}
        # Un pago sin su folio en el banco se da por encontrado si hay un solo cargo con otro folio que no es de ningún
        # pago, el mismo día y por el mismo importe (ODP agosto 2026: LAB3400 salió en el banco como LAB4000).
        otro_folio, sigue = [], []
        for x in no_encontrados:
            candidatos = [k for k, v in ajenos.items() if fecha.get(k) == _dia(x["fecha"])
                          and abs(sum(v) - Decimal(str(x["importe"]))) <= TOLERANCIA_BANCO]
            if len(candidatos) == 1:
                k = candidatos[0]
                otro_folio.append({**x, "folio_banco": k, "descripcion": descripcion.get(k, "")})
                del ajenos[k]
                confirmados += 1
            else:
                sigue.append(x)
        solo_banco = [{"folio": k, "importe": float(sum(v)), "descripcion": descripcion.get(k, "")}
                      for k, v in ajenos.items()]
        cuentas.append({"archivo": nombre, "cuenta": cuenta, "pagos": len(por_cuenta[cuenta]),
                        "confirmados": confirmados, "diferencias": diferencias, "no_encontrados": sigue,
                        "otro_folio": otro_folio, "solo_banco": solo_banco, "sin_folio": len(sin_folio)})
    sin_estado = [{"cuenta": c, "pagos": len(v), "importe": float(sum(x["importe"] for x in v))}
                  for c, v in sorted(por_cuenta.items()) if c not in cubiertas]
    return {"cuentas": cuentas, "sin_estado": sin_estado}


def _banco(bd: Session, p: DiotPeriodo) -> dict:
    c = {"clave": "banco", "titulo": "Los pagos salieron del banco",
         "pregunta": "¿Cada pago del reporte de tesorería aparece en el estado de cuenta, por el mismo importe?"}
    docs = diot.vigentes(bd, p.periodo_id)
    estados = [d for d in docs if d.tipo == "estado_cuenta"]
    tes = next((d for d in docs if d.tipo == "tesoreria"), None)
    if not estados:
        return {**c, "estado": SIN_DATOS, "detalle": {},
                "frase": "No se subió ningún estado de cuenta, así que no se comparó contra el banco. Es opcional."}
    if not tes:
        return {**c, "estado": SIN_DATOS, "detalle": {}, "frase": "Falta el reporte de impuestos de tesorería."}
    llave = (tes.documento_id, *sorted(d.documento_id for d in estados))
    if llave not in _banco_cache:
        tabla = lectura.leer(tes.nombre_archivo, tes.contenido, tes.tipo)
        _banco_cache.clear()
        _banco_cache[llave] = comparar_banco(
            tabla, [(d.nombre_archivo, lectura.leer(d.nombre_archivo, d.contenido, d.tipo)) for d in estados])
    d = _banco_cache[llave]
    leidas = [x for x in d["cuentas"] if x["cuenta"]]
    confirmados = sum(x["confirmados"] for x in leidas)
    pagos = sum(x["pagos"] for x in leidas)
    revisar = sum(len(x["diferencias"]) + len(x["no_encontrados"]) for x in leidas)
    falta = (" No hay estado de cuenta de " + ", ".join(f"{x['cuenta']} ({x['pagos']} pagos)" for x in d["sin_estado"])
             + ".") if d["sin_estado"] else ""
    ajenos = [x["archivo"] for x in d["cuentas"] if not x["cuenta"]]
    if ajenos:
        falta += f" {len(ajenos)} estado(s) de cuenta no coinciden con ningún pago de tesorería."
    if not leidas:
        return {**c, "estado": REVISAR, "detalle": d,
                "frase": "Ningún pago de tesorería aparece en los estados de cuenta subidos. Revisa que sean de "
                         "esta empresa y de este mes." + falta}
    otros = sum(len(x["otro_folio"]) for x in leidas)
    if otros:
        falta = (f" {otros} se encontró con otro folio en el banco (mismo día e importe)." if otros == 1
                 else f" {otros} se encontraron con otro folio en el banco (mismo día e importe).") + falta
    if revisar:
        return {**c, "estado": REVISAR, "detalle": d,
                "frase": f"{confirmados} de {pagos} pagos salen del banco por el mismo importe; "
                         + ("1 no aparece o tiene otro importe." if revisar == 1
                            else f"{revisar} no aparecen o tienen otro importe.") + falta}
    return {**c, "estado": OK if not d["sin_estado"] else INFO, "detalle": d,
            "frase": f"Sí. Los {pagos} pagos de " + ", ".join(x["cuenta"] for x in leidas)
                     + " salen del banco por el mismo importe." + falta}


# ---------------------------------------------------------------- 5. mes anterior

def _mes_anterior(bd: Session, p: DiotPeriodo, ok: list[DiotTercero]) -> dict:
    c = {"clave": "mes_anterior", "titulo": "Cambios contra el mes anterior",
         "pregunta": "¿Qué cambió contra el mes pasado? No es un error: es lo que vale la pena mirar."}
    ant = _anterior(bd, p)
    previos = [t for t in _terceros(bd, ant.periodo_id) if t.estado == "ok"] if ant and ant.procesado_en else []
    if not previos:
        return {**c, "estado": SIN_DATOS, "detalle": {},
                "frase": "No hay un mes anterior procesado de esta empresa para comparar."}
    hoy = {t.rfc: t for t in ok}
    antes = {t.rfc: t for t in previos}
    nuevos = [{"rfc": r, "nombre": hoy[r].nombre, "monto": _monto(hoy[r])} for r in sorted(set(hoy) - set(antes))]
    se_fueron = [{"rfc": r, "nombre": antes[r].nombre, "monto": _monto(antes[r])} for r in sorted(set(antes) - set(hoy))]
    cambios = []
    for r in sorted(set(hoy) & set(antes)):
        a, b = _monto(antes[r]), _monto(hoy[r])
        if abs(b - a) >= CAMBIO_MINIMO and (a == 0 or abs(Decimal(b - a) / a) >= CAMBIO_MES):
            cambios.append({"rfc": r, "nombre": hoy[r].nombre, "antes": a, "ahora": b,
                            "cambio": round((b - a) * 100 / a) if a else None})
    nuevos.sort(key=lambda x: -x["monto"])
    se_fueron.sort(key=lambda x: -x["monto"])
    cambios.sort(key=lambda x: -abs(x["ahora"] - x["antes"]))
    iva_antes, iva_hoy = sum(_iva(t) for t in previos), sum(_iva(t) for t in ok)
    nombre_ant = f"{diot.MESES[ant.mes - 1]} {ant.anio}"
    return {**c, "estado": INFO,
            "detalle": {"mes": nombre_ant, "nuevos": nuevos, "se_fueron": se_fueron, "cambios": cambios,
                        "iva_antes": iva_antes, "iva_ahora": iva_hoy},
            "frase": f"Contra {nombre_ant}: {len(nuevos)} proveedor(es) nuevo(s), {len(se_fueron)} que ya no "
                     f"aparecen y {len(cambios)} con cambios de más de 30 %. IVA {_pesos(iva_antes)} → "
                     f"{_pesos(iva_hoy)}."}


# ---------------------------------------------------------------- 6. formato

def _formato(p: DiotPeriodo, resumen: dict) -> dict:
    c = {"clave": "formato", "titulo": "Formato que acepta el SAT",
         "pregunta": "¿El archivo está armado como lo pide el portal del SAT?"}
    v = resumen.get("validaciones") or []
    if not v:
        return {**c, "estado": SIN_DATOS if not p.procesado_en else FALLA, "detalle": {"verificaciones": []},
                "frase": "No se generó el TXT; revisa los pendientes." if p.procesado_en else "Procesa el mes."}
    lista = [{"nombre": x["verificacion"], "texto": FORMATO.get(x["verificacion"], x["verificacion"]), "ok": x["ok"],
              "detalle": x["detalle"]} for x in v]
    malas = [x for x in lista if not x["ok"]]
    if malas or not p.txt:
        return {**c, "estado": FALLA, "detalle": {"verificaciones": lista},
                "frase": f"No. {len(malas)} de {len(lista)} verificaciones fallaron; el TXT no se entrega."}
    return {**c, "estado": OK, "detalle": {"verificaciones": lista},
            "frase": f"Sí. Pasó las {len(lista)} verificaciones. Al presentarlo, el portal del SAT hace las suyas."}


# ---------------------------------------------------------------- 7. contra lo presentado

def diferencias(bd: Session, p: DiotPeriodo) -> list[dict]:
    """Diferencias contra el TXT presentado, agrupadas por proveedor, con el motivo que se les puso."""
    if not p.comparacion:
        return []
    comp = json.loads(p.comparacion)
    por_rfc: dict[str, list[dict]] = defaultdict(list)
    for d in comp["diferencias"]:
        por_rfc[d["rfc"]].append(d)
    nombres = {t.rfc: t.nombre for t in _terceros(bd, p.periodo_id)}
    marcas = _revisiones(bd, p.periodo_id, "diferencia")
    salida = []
    for rfc, difs in sorted(por_rfc.items()):
        h = _huella(difs)
        m = marcas.get(rfc)
        vigente = bool(m and m.huella == h)
        falta_aqui = any(d["campo"] == "renglón" and d["generado"] is None for d in difs)
        sobra_aqui = any(d["campo"] == "renglón" and d["referencia"] is None for d in difs)
        salida.append({"rfc": rfc, "nombre": nombres.get(rfc),
                       "que": ("Fiscal lo declaró y la plataforma no" if falta_aqui else
                               "La plataforma lo declara y Fiscal no" if sobra_aqui else "Importes o tipos distintos"),
                       "campos": [d for d in difs if d["campo"] != "renglón"], "motivo": m.motivo if vigente else None,
                       "motivo_texto": MOTIVOS_DIFERENCIA.get(m.motivo) if vigente else None,
                       "nota": m.nota if vigente else None, "por": _nombre(bd, m.usuario_id) if vigente else None,
                       "en": m.momento if vigente else None, "huella": h})
    return salida


def _presentado(bd: Session, p: DiotPeriodo) -> dict:
    c = {"clave": "presentado", "titulo": "Contra lo que presentó Fiscal",
         "pregunta": "Solo en el piloto: ¿cada diferencia contra el TXT que Fiscal subió al SAT tiene un motivo?"}
    if not p.comparacion:
        return {**c, "estado": SIN_DATOS, "detalle": {},
                "frase": "No se subió el TXT que presentó Fiscal. Solo hace falta mientras dure el piloto."}
    comp = json.loads(p.comparacion)
    d = diferencias(bd, p)
    faltan = sum(1 for x in d if not x["motivo"])
    detalle = {"diferencias": d, "iguales": comp["renglones_iguales"], "presentados": comp["renglones_referencia"],
               "generados": comp["renglones_generados"], "totales": comp.get("totales", {}),
               "motivos": MOTIVOS_DIFERENCIA}
    base = f"{comp['renglones_iguales']} de {comp['renglones_referencia']} renglones idénticos"
    if not d:
        return {**c, "estado": OK, "detalle": detalle, "frase": f"Sí. {base}: no hay diferencias."}
    if faltan:
        return {**c, "estado": REVISAR, "detalle": detalle,
                "frase": f"{base}. Faltan motivos en {faltan} de {len(d)} proveedores con diferencias."}
    return {**c, "estado": OK, "detalle": detalle,
            "frase": f"Sí. {base}; las {len(d)} diferencias tienen su motivo."}


# ---------------------------------------------------------------- todo junto

def firmas(bd: Session, p: DiotPeriodo) -> dict:
    h = huella_txt(p)
    salida = {}
    for tipo in ("revision", "fiscal"):
        f = bd.scalars(select(DiotFirma).where(DiotFirma.periodo_id == p.periodo_id, DiotFirma.tipo == tipo,
                                               DiotFirma.activa == true())
                       .order_by(DiotFirma.firma_id.desc())).first()
        vigente = bool(f and h and f.huella_txt == h)
        salida[tipo] = {"firmada": vigente, "por": _nombre(bd, f.usuario_id) if vigente else None,
                        "usuario_id": f.usuario_id if vigente else None, "en": f.momento if vigente else None,
                        "nota": f.nota if vigente else None, "anterior_invalida": bool(f and not vigente)}
    return salida


def comprobaciones(bd: Session, p: DiotPeriodo) -> dict:
    resumen = json.loads(p.resumen) if p.resumen else {}
    ok = [t for t in _terceros(bd, p.periodo_id) if t.estado == "ok"]
    lista = [_contabilidad(bd, p, resumen, ok), _pagos(bd, p), _declaracion(bd, p, ok), _muestra(bd, p, ok),
             _banco(bd, p), _mes_anterior(bd, p, ok), _formato(p, resumen), _presentado(bd, p)]
    pendientes = diot.pendientes_que_bloquean(bd, p.periodo_id)
    resueltas = len(list(bd.scalars(select(DiotIncidencia.incidencia_id).where(
        DiotIncidencia.periodo_id == p.periodo_id, DiotIncidencia.impacto != motor.POSIBLE))))
    iva = sum(_iva(t) for t in ok)
    fallas = [c for c in lista if c["estado"] == FALLA]
    revisar = [c for c in lista if c["estado"] == REVISAR]
    f = firmas(bd, p)
    nombre = f"{diot.MESES[p.mes - 1].capitalize()} {p.anio} de {p.empresa.codigo}"
    if p.procesado_en is None:
        frase = f"{nombre}: sube los reportes del mes y procésalo."
        paso = 1
    elif pendientes:
        frase = (f"{nombre}: {len(ok)} proveedores, {_pesos(iva)} de IVA acreditable. "
                 f"Faltan {pendientes} decisión(es) antes de validar.")
        paso = 2
    elif fallas or revisar:
        frase = (f"{nombre}: {len(ok)} proveedores, {_pesos(iva)} de IVA acreditable. "
                 + (lista[0]["frase"].split(". ")[0] + ". " if lista[0]["estado"] == OK else "")
                 + f"Faltan {len(fallas) + len(revisar)} comprobación(es) por revisar.")
        paso = 3
    elif not (f["revision"]["firmada"] and f["fiscal"]["firmada"]):
        frase = (f"{nombre}: {len(ok)} proveedores, {_pesos(iva)} de IVA acreditable. Las comprobaciones están "
                 "bien; falta firmar.")
        paso = 4
    else:
        frase = (f"{nombre}: {len(ok)} proveedores, {_pesos(iva)} de IVA acreditable. Revisado y con visto bueno "
                 "de Fiscal; listo para presentar.")
        paso = 5
    return {"frase": frase, "paso": paso, "proveedores": len(ok), "iva": iva, "pendientes": pendientes,
            "resueltas": resueltas, "comprobaciones": lista, "firmas": f,
            "puede_firmar_revision": bool(p.txt) and not pendientes and not fallas and not revisar,
            "firmas_obligatorias": FIRMAS_OBLIGATORIAS}
