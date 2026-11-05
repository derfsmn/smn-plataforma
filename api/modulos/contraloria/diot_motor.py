"""DIOT: cruces, clasificación fiscal y consolidado por tercero, a partir de los reportes de Intelisis.

Reglas reconstruidas del papel de trabajo de Fiscal de ODP (agosto y septiembre de 2026); cada una tiene su clave para
que cada importe se pueda rastrear hasta el renglón del documento que lo originó. El cálculo es determinista (Decimal);
la IA no participa. Lo que no tiene regla verificada no se convierte en cero: queda como incidencia para Fiscal.
"""
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_DOWN, ROUND_HALF_UP, Decimal

from modulos.contraloria import diot_criterios as crit
from modulos.contraloria.diot_lectura import TIPOS, Tabla, decimal, es_error, texto

CERO = Decimal("0")
UNO = Decimal("1")
T16, T8 = Decimal("0.16"), Decimal("0.08")

# Impacto de una incidencia (instrucciones de Fiscal / Transformación Digital, TD003)
SIN_IMPACTO, CONTROLADO, POSIBLE = "sin_impacto", "controlado", "posible_impacto"

# Texto de cada criterio del sistema (la Base de conocimiento fiscal guarda los vigentes y sus parámetros)
REGLAS = {d.clave: f"{crit.CATEGORIAS[d.categoria]}: {d.descripcion}" for d in crit.SISTEMA}

# Los pasos del proceso de Fiscal (diagrama AS-IS de TD003). La plataforma los sigue en el mismo orden y deja bitácora.
PASOS = (
    (1, "Extraer reportes", "Revisa que estén los reportes del mes y que cada uno traiga sus columnas."),
    (2, "Consolidar y organizar", "Junta la información de la empresa: catálogo de proveedores, tipos de cambio, "
                                  "tipos de operación y renglones de cada reporte."),
    (3, "Limpiar y clasificar", "Depura registros, detecta duplicados, aplica la regla fiscal a cada renglón y "
                                "valida el RFC de cada tercero."),
    (4, "Conciliar IVA acreditable", "Compara el IVA de cada movimiento contra el auxiliar de IVA acreditable."),
    (5, "Revisar diferencias", "Cada diferencia de la conciliación queda para que Fiscal la revise."),
    (6, "Generar archivo DIOT (TXT)", "Consolida por RFC, aplica los ajustes de Fiscal, redondea al peso y arma el "
                                      "layout de 54 campos."),
    (7, "Validar archivo DIOT", "Revisa estructura, importes y registros del TXT."),
    (8, "Entregar archivo", "Deja el TXT validado y la evidencia listos para presentar en el portal del SAT."),
)
TOLERANCIA_CONCILIACION = Decimal("1.00")  # pesos por movimiento


class Bitacora:
    """Lo que hace el proceso, paso por paso. `al_registrar(evento, datos)` permite guardarlo mientras corre."""

    def __init__(self, al_registrar=None):
        self.pasos = {n: {"orden": n, "nombre": nom, "estado": "pendiente", "resumen": None} for n, nom, _ in PASOS}
        self.lineas: list[dict] = []
        self.actual = 0
        self._registrar = al_registrar or (lambda evento, datos: None)

    def inicio(self, n: int) -> None:
        self.actual = n
        if self.pasos[n]["estado"] != "en_curso":
            self.pasos[n]["estado"] = "en_curso"
            self._registrar("paso", self.pasos[n])

    def linea(self, mensaje: str, nivel: str = "info", datos: dict | None = None) -> None:
        ln = {"paso": self.actual, "nivel": nivel, "mensaje": mensaje, "datos": datos}
        self.lineas.append(ln)
        self._registrar("linea", ln)

    def fin(self, estado: str, resumen: str) -> None:
        self.pasos[self.actual].update(estado=estado, resumen=resumen)
        self._registrar("paso", self.pasos[self.actual])

    def no_ejecutados(self, motivo: str) -> None:
        for p in self.pasos.values():
            if p["estado"] == "pendiente":
                p.update(estado="no_ejecutado", resumen=motivo)
                self._registrar("paso", p)

RFC_IMSS = "IMS421231I45"  # el de la carga inicial (el vigente está en la Base de conocimiento fiscal)
RFC_INFONAVIT = "INF7205011ZA"
CAMPOS = ("base16", "iva16", "base8", "iva8", "base0", "exento", "no_objeto", "iva_retenido")


@dataclass
class Operacion:
    fuente: str  # tipo de documento
    renglon: int  # renglón del documento (1 = primer renglón de datos)
    referencia: str
    rfc: str | None
    nombre: str
    regla: str
    incluida: bool
    tasa: str | None = None  # 16 / 8 / 0 / exento / no_objeto
    tipo_cambio: Decimal = UNO
    base16: Decimal = CERO
    iva16: Decimal = CERO
    base8: Decimal = CERO
    iva8: Decimal = CERO
    base0: Decimal = CERO
    exento: Decimal = CERO
    no_objeto: Decimal = CERO
    iva_retenido: Decimal = CERO
    nota: str | None = None
    clave: str | None = None  # el movimiento en el auxiliar de IVA acreditable (para conciliar)
    monto: Decimal | None = None  # lo que mueve el renglón (subtotal + IVA, en pesos), entre o no a la DIOT


@dataclass
class Incidencia:
    impacto: str
    codigo: str
    mensaje: str
    fuente: str | None = None
    renglon: int | None = None
    rfc: str | None = None
    importe: Decimal | None = None


@dataclass
class Tercero:
    rfc: str
    nombre: str
    tipo_tercero: str
    tipo_operacion: str
    exactos: dict[str, Decimal]
    redondeados: dict[str, int]
    operaciones: int
    fuentes: list[str]
    estado: str = "ok"  # ok / revisar
    ajustes: list[dict] = field(default_factory=list)


@dataclass
class Resultado:
    operaciones: list[Operacion]
    terceros: list[Tercero]
    incidencias: list[Incidencia]
    cuadres: list[dict]
    faltantes: list[str]
    txt: str | None = None
    validaciones: list[dict] = field(default_factory=list)
    bitacora: "Bitacora | None" = None

    @property
    def bloqueado(self) -> bool:
        return bool(self.faltantes)


def redondear(x: Decimal, metodo: str = "mitad_arriba") -> int:
    """Al peso. «art20»: de 1 a 50 centavos baja y de 51 a 99 sube (art. 20 CFF); «mitad_arriba»: 50 centavos suben."""
    return int(x.quantize(UNO, rounding=ROUND_HALF_DOWN if metodo == "art20" else ROUND_HALF_UP))


def con_medio_peso(x: Decimal) -> bool:
    """¿El importe termina exactamente en 50 centavos? Ahí es donde los dos métodos de redondeo dan distinto."""
    return abs(x) % 1 == Decimal("0.5")


def rfc_valido(rfc: str) -> bool:
    import re
    return bool(re.fullmatch(r"[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}", rfc or ""))


class _Contexto:
    def __init__(self, docs: dict[str, Tabla], rfc_empresa: str, cfg: crit.Config):
        self.docs, self.rfc_empresa, self.cfg = docs, rfc_empresa.upper(), cfg
        self.ops: list[Operacion] = []
        self.inc: list[Incidencia] = []
        self.catalogo: dict[str, tuple[str, str]] = {}
        for f in docs["proveedores"].filas if "proveedores" in docs else []:
            clave = texto(f.get("Clave")).upper()
            if clave and clave not in self.catalogo:
                self.catalogo[clave] = (texto(f.get("RFC")).upper(), texto(f.get("Nombre")))

    def num(self, fuente: str, renglon: int, fila: dict, col: str, referencia: str) -> Decimal | None:
        try:
            return decimal(fila.get(col))
        except ValueError as e:
            self.inc.append(Incidencia(POSIBLE, "VALOR", f"«{col}» trae «{e}» en {referencia}; el renglón no se "
                                       "calculó.", fuente, renglon))
            return None

    @staticmethod
    def monto(fila: dict, columnas: tuple[str, ...], tc: Decimal, respaldo: str | None = None) -> Decimal | None:
        """Suma de las columnas por el tipo de cambio; sin esas columnas, la de respaldo. Solo para mostrar de dónde
        sale el resultado (el embudo): no entra a ningún cálculo y un valor raro da None, no cero."""
        try:
            partes = [decimal(fila.get(c)) for c in columnas]
            if any(x is not None for x in partes):
                return sum((x or CERO for x in partes), CERO) * tc
            return decimal(fila.get(respaldo)) * tc if respaldo and decimal(fila.get(respaldo)) is not None else None
        except ValueError:
            return None

    def rfc_de_clave(self, clave: str) -> tuple[str | None, str]:
        rfc, nombre = self.catalogo.get(clave.upper(), (None, ""))
        return (rfc or None), nombre


# ---------------------------------------------------------------- criterios propios de Fiscal

def _propio(c: _Contexto, fuente: str, valores: dict[str, str]) -> crit.Criterio | None:
    """El primer criterio propio aprobado (por prioridad) que aplica al renglón."""
    for k in c.cfg.propios():
        cond = k.condicion or {}
        if (k.accion or {}).get("accion") != "tipo_operacion" and cond.get("fuente") in (fuente, "cualquiera") \
                and crit.coincide(cond, valores):
            return k
    return None


def _aplicar_propio(op: Operacion, k: crit.Criterio, base: Decimal) -> None:
    accion = (k.accion or {}).get("accion")
    op.regla = k.clave
    if accion == "excluir":
        op.incluida = False
        return
    op.incluida = True
    op.tasa = {"tasa0": "0", "no_objeto": "no_objeto", "exento": "exento"}[accion]
    setattr(op, {"tasa0": "base0", "no_objeto": "no_objeto", "exento": "exento"}[accion], base)


def texto_regla(cfg: crit.Config, clave: str) -> str:
    k = cfg.criterios.get(clave)
    if k and k.tipo == "propio":
        return f"Criterio propio de Fiscal: {k.titulo}."
    return REGLAS.get(clave, "")


# ---------------------------------------------------------------- Tesorería

def _tesoreria(c: _Contexto) -> None:
    vistos: dict[tuple, int] = {}
    for i, f in enumerate(c.docs["tesoreria"].filas, 1):
        mov, movid = texto(f.get("Mov")), texto(f.get("MovID"))
        ref = f"{mov} {movid}".strip()
        concepto, referencia = texto(f.get("Concepto")).upper(), texto(f.get("Referencia")).upper()
        nombre = texto(f.get("BeneficiarioNombre"))
        rfc = texto(f.get("RFCReceptor")).upper() or None
        if not rfc and texto(f.get("Contacto")):
            rfc = c.rfc_de_clave(texto(f.get("Contacto")))[0]
        tc = c.num("tesoreria", i, f, "TipoCambio", ref) or UNO
        tasa = c.num("tesoreria", i, f, "Impuesto1", ref)
        op = Operacion("tesoreria", i, ref, rfc, nombre, "", False, tipo_cambio=tc, clave=ref,
                       monto=c.monto(f, ("SubTotal", "Importe1"), tc, "Importe"))
        firma = tuple(texto(f.get(k)) for k in sorted(f))
        if firma in vistos:  # se cuenta (un pago puede traer dos renglones iguales); la conciliación lo confirma
            op.nota = f"Igual al renglón {vistos[firma]}."
            c.inc.append(Incidencia(CONTROLADO, "POSIBLE-DUPLICADO", f"{ref}: renglón idéntico al {vistos[firma]} del "
                                    "reporte de tesorería; se cuentan los dos. La conciliación contra el auxiliar dice "
                                    "si sobra.", "tesoreria", i, rfc))
        vistos.setdefault(firma, i)
        propio = _propio(c, "tesoreria", {"concepto": concepto, "referencia": referencia, "nombre": nombre,
                                           "rfc": rfc or ""})
        g = c.cfg
        if propio:
            _aplicar_propio(op, propio, (c.num("tesoreria", i, f, "SubTotal", ref) or CERO) * tc)
        elif mov.upper() in g.lista("TES-BANCO", "movimientos"):
            op.regla = "TES-BANCO"
        elif concepto.startswith(tuple(g.lista("TES-ANTICIPO-SF", "prefijos"))):
            op.regla = "TES-ANTICIPO-SF"
            c.inc.append(Incidencia(CONTROLADO, "ANTICIPO-SF", f"{ref}: anticipo a {nombre} sin factura; se declara "
                                    "cuando se aplique. Revisa que su aplicación esté en el mes.", "tesoreria", i, rfc,
                                    c.num("tesoreria", i, f, "SubTotal", ref)))
        elif concepto in g.lista("TES-ANTICIPO", "conceptos"):
            op.regla = "TES-ANTICIPO"
        elif (any(x in referencia for x in g.lista("TES-CAJA-CHICA", "contiene"))
              or referencia.startswith(tuple(g.lista("TES-CAJA-CHICA", "empieza")))):
            op.regla = "TES-CAJA-CHICA"
        elif rfc in g.lista("TES-IMSS", "rfcs") or any(x in nombre.upper() for x in g.lista("TES-IMSS", "nombres")):
            op.rfc = rfc = rfc if rfc in g.lista("TES-IMSS", "rfcs") else (g.lista("TES-IMSS", "rfcs") or [RFC_IMSS])[0]
            op.regla = "TES-IMSS"
            if g.p("TES-IMSS", "tratamiento") != "excluir":
                op.incluida, op.tasa = True, "no_objeto"
                op.no_objeto = (c.num("tesoreria", i, f, "SubTotal", ref) or CERO) * tc
                if "RETIRO" in concepto:
                    c.inc.append(Incidencia(POSIBLE, "IMSS-INFONAVIT", f"{ref}: el pago bimestral al IMSS "
                                            f"({concepto.lower()}) puede incluir la parte del INFONAVIT, que no se declara. "
                                            "Si la incluye, réstala con un ajuste al no objeto del IMSS.",
                                            "tesoreria", i, rfc, op.no_objeto))
        elif (referencia.startswith(tuple(g.lista("TES-NOMINA", "referencia_empieza")))
              or concepto.startswith(tuple(g.lista("TES-NOMINA", "concepto_empieza")))
              or any(x in concepto for x in g.lista("TES-NOMINA", "concepto_contiene"))):
            op.regla = "TES-NOMINA"
        elif rfc and rfc == c.rfc_empresa:
            op.regla = "TES-PROPIA"
        elif tasa is None:
            op.regla = "TES-SIN-TASA"
            c.inc.append(Incidencia(POSIBLE, "SIN-TASA", f"{ref}: pago a {nombre} sin tasa de IVA ni clasificación.",
                                    "tesoreria", i, rfc, c.num("tesoreria", i, f, "SubTotal", ref)))
        else:
            iva = (c.num("tesoreria", i, f, "Importe1", ref) or CERO) * tc
            sub = (c.num("tesoreria", i, f, "SubTotal", ref) or CERO) * tc
            t = tasa.quantize(UNO, rounding=ROUND_HALF_UP)
            op.regla, op.incluida = "TES-TASA", True
            if t == 16:
                op.tasa, op.iva16, op.base16 = "16", iva, iva / T16
            elif t == 8:
                op.tasa, op.iva8, op.base8 = "8", iva, iva / T8
            elif t == 0:
                op.tasa, op.base0 = "0", sub
            else:
                op.regla, op.incluida = "TES-SIN-TASA", False
                c.inc.append(Incidencia(POSIBLE, "TASA-RARA", f"{ref}: tasa {tasa} no reconocida.", "tesoreria", i,
                                        rfc))
            if tasa != t:
                op.nota = f"Tasa del reporte {tasa}, se tomó {t}."
        c.ops.append(op)


# ---------------------------------------------------------------- Aplicaciones de CxP

def _tipos_de_cambio(c: _Contexto) -> dict[str, Decimal]:
    tcs = {}
    for f in c.docs["auxiliar_iva"].filas:
        m = texto(f.get("Movimiento"))
        try:
            tc = decimal(f.get("OrigenTipoCambio"))
        except ValueError:
            tc = None
        if m and tc and m not in tcs:
            tcs[m] = tc
    return tcs


def _aplicaciones(c: _Contexto) -> None:
    tcs = _tipos_de_cambio(c)
    for i, f in enumerate(c.docs["aplicaciones"].filas, 1):
        movimiento = texto(f.get("Movimiento"))
        ref = f"{movimiento} ({texto(f.get('Mov'))} {texto(f.get('MovID'))})"
        rfc = texto(f.get("RFC")).upper() or None
        op = Operacion("aplicaciones", i, ref, rfc, texto(f.get("nombre")), "APL-OTRO", False, clave=movimiento,
                       monto=c.monto(f, ("SubTotal", "Importe1", "Importe2"), UNO))
        tasa = c.num("aplicaciones", i, f, "Impuesto1", ref)
        if texto(f.get("Origen")) == "Aplicacion" and tasa and tasa > 0:
            tc = tcs.get(movimiento)
            if tc is None:
                tc = c.num("aplicaciones", i, f, "OrigenTipoCambio", ref) or UNO
                c.inc.append(Incidencia(CONTROLADO, "APL-TC", f"{ref}: la póliza no está en el auxiliar de IVA; se "
                                        f"usó el tipo de cambio del propio reporte ({tc}).", "aplicaciones", i, rfc))
            base = ((c.num("aplicaciones", i, f, "SubTotal", ref) or CERO)
                    + (c.num("aplicaciones", i, f, "Importe2", ref) or CERO)) * tc
            iva = (c.num("aplicaciones", i, f, "Importe1", ref) or CERO) * tc
            op.regla, op.incluida, op.tipo_cambio = "APL-APLICACION", True, tc
            op.monto = base + iva
            if tasa.quantize(UNO) == 8:
                op.tasa, op.base8, op.iva8 = "8", base, iva
            else:
                op.tasa, op.base16, op.iva16 = "16", base, iva
        c.ops.append(op)


# ---------------------------------------------------------------- Explorador de gastos

def _comprobantes(c: _Contexto) -> dict[str, tuple[str | None, str]]:
    """Agrega las operaciones de los comprobantes y regresa, por póliza, el acreedor (para el IVA retenido)."""
    en_auxiliar = {texto(f.get("Movimiento")) for f in c.docs["auxiliar_iva"].filas}
    por_poliza: dict[str, tuple[str | None, str]] = {}
    vistos: dict[tuple, int] = {}
    columnas = TIPOS["comprobantes"].columnas
    for i, f in enumerate(c.docs["comprobantes"].filas, 1):
        ref = texto(f.get("Movimiento"))
        poliza = f"{texto(f.get('Poliza'))} {texto(f.get('PolizaID'))}".strip()
        rfc, nombre = c.rfc_de_clave(texto(f.get("Acreedor")))
        nombre = nombre or texto(f.get("Nombre"))
        concepto = texto(f.get("Concepto")).upper()
        op = Operacion("comprobantes", i, f"{ref} · {texto(f.get('Concepto'))}", rfc, nombre, "", False, clave=poliza)
        # Una «Devolucion Gasto» regresa un gasto ya comprobado: en el auxiliar va al Haber, así que resta.
        signo = -UNO if ref.upper().startswith("DEVOLUCION") else UNO
        try:
            op.monto = signo * ((decimal(f.get("Cantidad")) or CERO) * (decimal(f.get("Precio")) or CERO)
                                * (1 + (decimal(f.get("% IVA")) or CERO) / 100) * (decimal(f.get("TipoCambio")) or UNO))
        except ValueError:
            op.monto = None
        firma = tuple(texto(f.get(k)) for k in columnas)
        if firma in vistos:
            op.nota = f"Igual al renglón {vistos[firma]}."
            c.inc.append(Incidencia(CONTROLADO, "POSIBLE-DUPLICADO", f"{ref}: renglón idéntico al {vistos[firma]} del "
                                    "Explorador de gastos; se cuentan los dos. Revisa que no esté repetido.",
                                    "comprobantes", i, rfc))
        vistos.setdefault(firma, i)
        if rfc and poliza not in por_poliza:
            por_poliza[poliza] = (rfc, nombre)
        if texto(f.get("Estatus")).upper() not in ("CONCLUIDO", ""):
            op.regla = "COM-CANCELADO"
        elif poliza not in en_auxiliar:
            op.regla = "COM-AUXILIAR"
            op.nota = f"La póliza {poliza or '(sin póliza)'} no está en el auxiliar de IVA acreditable."
        elif rfc and rfc == c.rfc_empresa:
            op.regla = "COM-PROPIA"
        else:
            tc = c.num("comprobantes", i, f, "TipoCambio", ref) or UNO
            base = signo * (c.num("comprobantes", i, f, "Cantidad", ref) or CERO) * (
                c.num("comprobantes", i, f, "Precio", ref) or CERO) * tc
            tasa = c.num("comprobantes", i, f, "% IVA", ref) or CERO
            op.incluida, op.tipo_cambio = True, tc
            propio = _propio(c, "comprobantes", {"concepto": concepto, "referencia": ref.upper(),
                                                 "nombre": nombre, "rfc": rfc or ""})
            if propio:
                _aplicar_propio(op, propio, base)
            elif tasa > 0:
                op.regla = "COM-TASA"
                iva = base * tasa / 100
                if tasa.quantize(UNO) == 8:
                    op.tasa, op.base8, op.iva8 = "8", base, iva
                else:
                    op.tasa, op.base16, op.iva16 = "16", base, iva
            elif any(k in concepto for k in c.cfg.lista("COM-TASA0", "conceptos")):
                op.regla, op.tasa, op.base0 = "COM-TASA0", "0", base
            elif c.cfg.p("COM-NO-OBJETO", "tratamiento") == "incidencia":
                op.regla, op.incluida = "COM-NO-OBJETO", False
                c.inc.append(Incidencia(POSIBLE, "SIN-IVA", f"{ref}: «{texto(f.get('Concepto'))}» sin IVA y sin "
                                        "criterio de tasa 0 %; no se declaró. Clasifícalo con un criterio o un ajuste.",
                                        "comprobantes", i, rfc, base))
            else:
                op.regla, op.tasa, op.no_objeto = "COM-NO-OBJETO", "no_objeto", base
                if any(k in concepto for k in c.cfg.lista("COM-NO-OBJETO", "revisar")):
                    c.inc.append(Incidencia(POSIBLE, "DEBERIA-IVA", f"{ref}: «{texto(f.get('Concepto'))}» llegó sin "
                                            "IVA y debería traer 16 % (8 % en zona fronteriza). Se declaró como no "
                                            "objeto; revisa el CFDI.", "comprobantes", i, rfc, base))
                else:
                    c.inc.append(Incidencia(CONTROLADO, "NO-OBJETO", f"{ref}: «{texto(f.get('Concepto'))}» sin IVA "
                                            "se declaró como no objeto.", "comprobantes", i, rfc, base))
            if not rfc:
                c.inc.append(Incidencia(POSIBLE, "SIN-RFC", f"{ref}: el acreedor {texto(f.get('Acreedor'))} no está "
                                        "en el catálogo de proveedores.", "comprobantes", i, None, base))
        c.ops.append(op)
    return por_poliza


def _iva_retenido(c: _Contexto, por_poliza: dict[str, tuple[str | None, str]]) -> None:
    for i, f in enumerate(c.docs["iva_retenido"].filas, 1):
        mov = texto(f.get("Movimiento"))
        haber = c.num("iva_retenido", i, f, "Haber", mov) or CERO
        debe = c.num("iva_retenido", i, f, "Debe", mov) or CERO
        if not mov or (haber == 0 and debe == 0):
            continue
        rfc, nombre = por_poliza.get(mov, (None, ""))
        op = Operacion("iva_retenido", i, mov, rfc, nombre, "RET-AUXILIAR", bool(rfc), tasa="retencion",
                       iva_retenido=haber - debe)
        if not rfc:
            c.inc.append(Incidencia(POSIBLE, "RET-SIN-ACREEDOR", f"{mov}: IVA retenido de {haber - debe} sin "
                                    "comprobante en el Explorador de gastos; no se pudo asignar a un proveedor.",
                                    "iva_retenido", i, None, haber - debe))
        c.ops.append(op)


# ---------------------------------------------------------------- consolidado

def _sin_acentos(t: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", t.upper()) if unicodedata.category(ch) != "Mn")


def _clave_tipo(valor: str, catalogo: dict[str, str]) -> str | None:
    """La clave del tipo de operación: el número tal cual («6» → «06») o, si la lista trae el nombre
    («ARRENDAMIENTO»), la única clave del catálogo vigente cuya descripción lo contiene. Si no hay una sola, None."""
    v = valor.strip()
    if v.isdigit() and len(v) <= 2:
        return v.zfill(2)
    n = _sin_acentos(v)
    if len(n) < 4:
        return None
    claves = [k for k, d in catalogo.items() if n in _sin_acentos(d)]
    return claves[0] if len(claves) == 1 else None


def _tipos_operacion(docs: dict[str, Tabla], catalogo: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Tipos de operación por RFC de la lista de Fiscal, y los que no se pudieron leer (RFC → lo que decía)."""
    t, no_leidos = {}, {}
    for f in docs["tipos_operacion"].filas if "tipos_operacion" in docs else []:
        rfc, tipo = texto(f.get("RFC")).upper(), texto(f.get("TIPO DE OPERACIÓN"))
        if rfc and tipo:
            clave = _clave_tipo(tipo, catalogo)
            if clave:
                t[rfc] = clave
            else:
                no_leidos[rfc] = tipo
    return t, no_leidos


def _tipo_tercero(cfg: crit.Config, rfc: str) -> str:
    """04 si el RFC es mexicano válido; 05 o 15 si está en esas listas; vacío si el RFC no es válido (por revisar)."""
    if rfc in cfg.lista("TER-TIPO-TERCERO", "globales"):
        return "15"
    if rfc in cfg.lista("TER-TIPO-TERCERO", "extranjeros"):
        return "05"
    return "04" if rfc_valido(rfc) else ""


def _consolidar(c: _Contexto, ajustes: list[dict]) -> list[Tercero]:
    cfg = c.cfg
    tipos, no_leidos = _tipos_operacion(c.docs, cfg.tipos_operacion)
    omision = str(cfg.p("TER-TIPO-OPERACION", "omision")).zfill(2)
    por_criterio = {}  # criterios propios que fijan el tipo de operación de un RFC
    for k in cfg.propios():
        if (k.accion or {}).get("accion") == "tipo_operacion" and (k.condicion or {}).get("campo") == "rfc":
            por_criterio[(k.condicion.get("valor") or "").upper().strip()] = (str(k.accion.get("tipo_operacion"))
                                                                              .zfill(2), k.clave)
    grupos: dict[str, list[Operacion]] = defaultdict(list)
    for o in c.ops:
        if o.incluida and o.rfc:
            grupos[o.rfc].append(o)
    terceros, con_omision = [], []
    for rfc, ops in sorted(grupos.items()):
        exactos = {k: sum((getattr(o, k) for o in ops), CERO) for k in CAMPOS}
        tt = _tipo_tercero(cfg, rfc)
        if rfc in por_criterio:
            to = por_criterio[rfc][0]
        elif tt == "15":
            to = str(cfg.p("TER-TIPO-OPERACION", "global")).zfill(2)
        elif tt == "05":
            to = str(cfg.p("TER-TIPO-OPERACION", "extranjero")).zfill(2)
        elif rfc in tipos:
            to = tipos[rfc]
        else:
            to = omision
            con_omision.append(rfc)
        if rfc in no_leidos and rfc not in por_criterio:
            c.inc.append(Incidencia(POSIBLE, "TIPO-NO-LEIDO", f"La lista de tipos de operación dice «{no_leidos[rfc]}» "
                                    f"para {rfc} y no corresponde a una clave del catálogo; se usó {to}. Corrige la "
                                    "lista con la clave (03, 06, 85…) o pide a Fiscal un ajuste.", rfc=rfc))
        t = Tercero(rfc=rfc, nombre=next((o.nombre for o in ops if o.nombre), ""), tipo_tercero=tt, tipo_operacion=to,
                    exactos=exactos, redondeados={}, operaciones=len(ops), fuentes=sorted({o.fuente for o in ops}))
        if not tt:
            t.estado = "revisar"
            c.inc.append(Incidencia(POSIBLE, "RFC-INVALIDO", f"El RFC «{rfc}» no tiene formato válido: no se le asigna "
                                    "tipo de tercero. Corrígelo en el catálogo o captura un ajuste.", rfc=rfc))
        terceros.append(t)
    # Ajustes de Fiscal (con motivo) sobre el consolidado
    por_rfc = {t.rfc: t for t in terceros}
    for a in ajustes:
        t = por_rfc.get(a["rfc"])
        if a.get("excluir"):
            if t:
                terceros.remove(t)
                por_rfc.pop(t.rfc)
            continue
        if not t:
            t = Tercero(rfc=a["rfc"], nombre=a.get("nombre") or "",
                        tipo_tercero=a.get("tipo_tercero") or _tipo_tercero(cfg, a["rfc"]) or "04",
                        tipo_operacion=a.get("tipo_operacion") or omision, exactos={k: CERO for k in CAMPOS},
                        redondeados={}, operaciones=0, fuentes=["ajuste"])
            terceros.append(t)
            por_rfc[t.rfc] = t
        if a.get("campo") in CAMPOS:
            t.exactos[a["campo"]] += Decimal(str(a["importe"]))
        if a.get("tipo_operacion"):
            t.tipo_operacion = a["tipo_operacion"]
            if t.rfc in con_omision:
                con_omision.remove(t.rfc)
        if a.get("tipo_tercero"):
            t.tipo_tercero = a["tipo_tercero"]
            if t.estado == "revisar" and rfc_valido(t.rfc):
                t.estado = "ok"
        t.ajustes.append(a)
    metodo = cfg.p("TER-REDONDEO", "metodo")
    en_layout = set(cfg.mapa.values())
    medios = []
    for t in terceros:
        t.redondeados = {k: redondear(v, metodo) for k, v in t.exactos.items()}
        medios += [(t.rfc, k, v) for k, v in t.exactos.items() if v and con_medio_peso(v)]
        if any(v < 0 for v in t.redondeados.values()):
            t.estado = "revisar"
            c.inc.append(Incidencia(POSIBLE, "NEGATIVO", f"{t.rfc}: importe negativo en el consolidado (devolución o "
                                    "nota de crédito); revisa antes de declarar.", rfc=t.rfc))
        sin_campo = [crit.QUE_LLEVA[k] for k in CAMPOS if t.redondeados[k] and k not in en_layout]
        if sin_campo:
            t.estado = "revisar"
            c.inc.append(Incidencia(POSIBLE, "LAYOUT", f"{t.rfc}: tiene importes de {', '.join(sin_campo)}, que no "
                                    "tienen campo en el layout de la Base de conocimiento fiscal. No se genera el TXT "
                                    "hasta registrar en qué campo van.", rfc=t.rfc))
        if t.tipo_tercero and t.tipo_tercero not in cfg.tipos_tercero:
            t.estado = "revisar"
            c.inc.append(Incidencia(POSIBLE, "CATALOGO", f"{t.rfc}: el tipo de tercero {t.tipo_tercero} no está en el "
                                    "catálogo vigente.", rfc=t.rfc))
        if t.tipo_operacion not in cfg.tipos_operacion:
            t.estado = "revisar"
            c.inc.append(Incidencia(POSIBLE, "CATALOGO", f"{t.rfc}: el tipo de operación {t.tipo_operacion} no está en "
                                    "el catálogo vigente.", rfc=t.rfc))
    # Tope del tercero global: un porcentaje del total de pagos del mes (respuesta 6 de Fiscal)
    importes = ("base16", "base8", "base0", "exento", "no_objeto")
    total = sum((t.exactos[k] for t in terceros for k in importes), CERO)
    globales = sum((t.exactos[k] for t in terceros if t.tipo_tercero == "15" for k in importes), CERO)
    try:
        tope = Decimal(str(cfg.p("TER-TIPO-TERCERO", "tope_global")))
    except ArithmeticError:
        tope = None
    if tope is not None and total > 0 and globales > total * tope / 100:
        c.inc.append(Incidencia(POSIBLE, "TOPE-GLOBAL", f"El tercero global (15) suma {_pesos(globales)}, "
                                f"{globales / total * 100:.1f} % del total de pagos del mes ({_pesos(total)}); el tope "
                                f"es {tope} %. Identifica a los proveedores del excedente.", importe=globales))
    # Criterios pendientes que cambian el resultado del mes
    if con_omision and not cfg.aprobado("TER-TIPO-OPERACION"):
        c.inc.append(_pendiente(cfg, "TER-TIPO-OPERACION", f"{len(con_omision)} tercero(s) van con el tipo de "
                                f"operación por omisión ({omision})"))
    if medios and not cfg.aprobado("TER-REDONDEO"):
        ej = ", ".join(f"{r} {crit.QUE_LLEVA[k]} {v:,.2f}" for r, k, v in medios[:5])
        c.inc.append(_pendiente(cfg, "TER-REDONDEO", f"{len(medios)} importe(s) terminan exactamente en 50 centavos "
                                f"y el resultado depende del criterio ({ej})"))
    terceros.sort(key=lambda t: (t.tipo_tercero, t.rfc))
    return [t for t in terceros if any(t.redondeados.values()) or t.ajustes]


def _pendiente(cfg: crit.Config, clave: str, que: str, importe: Decimal | None = None) -> Incidencia:
    estado = "en borrador" if cfg.estado(clave) == crit.BORRADOR else "pendiente de aprobación"
    return Incidencia(POSIBLE, "CRITERIO-PENDIENTE", f"El criterio «{cfg.titulo(clave)}» ({clave}) está {estado} en la "
                      f"Base de conocimiento fiscal y este mes se usó: {que}. Revisa que esté bien o pide "
                      "a Fiscal que lo apruebe.", importe=importe)


def _pendientes_de_clasificacion(c: _Contexto) -> None:
    """Una incidencia por criterio del sistema pendiente que se aplicó a algún renglón del mes."""
    por_regla: dict[str, list[Operacion]] = defaultdict(list)
    for o in c.ops:
        por_regla[o.regla].append(o)
    for clave, ops in sorted(por_regla.items()):
        if clave not in crit.POR_CLAVE or clave.startswith("TER-") or c.cfg.aprobado(clave):
            continue
        importe = sum((o.base16 + o.base8 + o.base0 + o.exento + o.no_objeto for o in ops), CERO)
        c.inc.append(_pendiente(c.cfg, clave, f"se aplicó a {len(ops)} renglón(es)"
                                + (f" por {_pesos(importe)}" if importe else ""), importe or None))


# ---------------------------------------------------------------- conciliación contra el auxiliar

def _grupo_auxiliar(f: dict) -> tuple[str, str] | None:
    """(documento con el que se concilia, clave del movimiento) de un renglón del auxiliar de IVA acreditable."""
    origen, tipo = texto(f.get("Origen")), texto(f.get("OrigenTipo")).upper()
    if origen == "Pago Prov Imptos":
        return None  # el pago del IVA del mes anterior: no es de proveedores
    if origen == "Aplicacion" or (tipo == "CXP" and origen != "Pago Prov Imptos"):
        return "aplicaciones", texto(f.get("Movimiento"))
    if tipo == "GAS" or origen in ("Comprobante", "Caja Chica", "Devolucion Gasto"):
        return "comprobantes", texto(f.get("Movimiento"))
    return "tesoreria", f"{origen} {texto(f.get('OrigenID'))}".strip()


NOMBRE_GRUPO = {"tesoreria": "Pagos de tesorería (cheques y transferencias)",
                "aplicaciones": "Aplicaciones de anticipos (CxP)",
                "comprobantes": "Gastos comprobados y caja chica"}


def _conciliar(c: _Contexto) -> tuple[list[dict], list[dict], Decimal]:
    """IVA de las operaciones contra el auxiliar, por grupo y por movimiento. Regresa grupos, diferencias y lo que el
    auxiliar trae fuera de proveedores (el pago del IVA del mes anterior)."""
    aux: dict[tuple[str, str], Decimal] = defaultdict(lambda: CERO)
    fuera = CERO
    for f in c.docs["auxiliar_iva"].filas:
        try:
            neto = (decimal(f.get("Debe")) or CERO) - (decimal(f.get("Haber")) or CERO)
        except ValueError:
            continue
        g = _grupo_auxiliar(f)
        if g is None:
            fuera += neto
        else:
            aux[g] += neto
    ops: dict[tuple[str, str], Decimal] = defaultdict(lambda: CERO)
    for o in c.ops:
        if o.incluida and o.fuente in NOMBRE_GRUPO and o.clave is not None:
            ops[(o.fuente, o.clave)] += o.iva16 + o.iva8
    grupos, difs = [], []
    for g, nombre in NOMBRE_GRUPO.items():
        claves = {k for k in set(aux) | set(ops) if k[0] == g}
        a = sum((aux[k] for k in claves), CERO)
        o = sum((ops[k] for k in claves), CERO)
        malas = 0
        for k in sorted(claves, key=lambda k: k[1]):
            d = ops[k] - aux[k]
            if abs(d) > TOLERANCIA_CONCILIACION:
                malas += 1
                difs.append({"grupo": g, "movimiento": k[1], "operaciones": ops[k], "auxiliar": aux[k], "diferencia": d})
        compensadas = abs(o - a) <= TOLERANCIA_CONCILIACION and malas > 0
        for d in difs[len(difs) - malas:]:
            d["compensada"] = compensadas  # las diferencias por póliza se anulan entre sí: el total del grupo cuadra
        grupos.append({"grupo": g, "concepto": nombre, "operaciones": o, "auxiliar": a, "diferencia": o - a,
                       "movimientos": len(claves), "con_diferencia": malas, "compensadas": compensadas})
    return grupos, difs, fuera


def _pesos(x) -> str:
    x = Decimal(x).quantize(Decimal("0.01")) + 0  # sin «-0.00»
    return f"{'-' if x < 0 else ''}${abs(x):,.2f}"


def procesar(docs: dict[str, Tabla], rfc_empresa: str, ajustes: list[dict] | None = None,
             bitacora: Bitacora | None = None, cfg: crit.Config | None = None) -> Resultado:
    """Los pasos del proceso de Fiscal, en orden, dejando en la bitácora lo que se hace en cada uno. `cfg`: criterios,
    catálogos y layout vigentes (Base de conocimiento fiscal); sin ella, los de la carga inicial."""
    from modulos.contraloria import diot_layout as layout  # aquí para no importar en círculo

    b = bitacora or Bitacora()
    cfg = cfg or crit.inicial()
    c = _Contexto(docs, rfc_empresa, cfg)
    omision = str(cfg.p("TER-TIPO-OPERACION", "omision")).zfill(2)

    # ---- Paso 1. Extraer reportes
    b.inicio(1)
    faltantes = []
    for t in TIPOS.values():
        if t.comprobar:
            continue
        tabla = docs.get(t.codigo)
        if tabla is None:
            if t.obligatorio:
                faltantes.append(t.nombre)
                b.linea(f"Falta «{t.nombre}» (obligatorio). Sin él no se puede seguir.", "error")
            else:
                b.linea(f"No se subió «{t.nombre}» (opcional): "
                        + ("el IVA retenido saldrá en cero." if t.codigo == "iva_retenido"
                           else f"todos los proveedores irán con el tipo de operación por omisión ({omision})."),
                        "aviso")
            continue
        faltan = [col for col in t.columnas if col.upper() not in {x.upper() for x in tabla.columnas}]
        if faltan:
            faltantes.append(f"{t.nombre}: le faltan las columnas {', '.join(faltan)}")
            b.linea(f"«{t.nombre}» no trae las columnas {', '.join(faltan)}.", "error")
            continue
        propias = {col.upper() for col in t.columnas}  # los errores en otras columnas (fórmulas del libro) no cuentan
        errores = sum(1 for f in tabla.filas for k, v in f.items() if k.upper() in propias and es_error(v))
        b.linea(f"«{t.nombre}»: {len(tabla.filas):,} renglones con las {len(t.columnas)} columnas que se usan"
                + (f" (hoja «{tabla.hoja}»)" if tabla.hoja else "") + ".", "ok")
        if errores:
            c.inc.append(Incidencia(SIN_IMPACTO if t.codigo in ("proveedores",) else POSIBLE, "ERROR-EXCEL",
                                    f"{t.nombre}: {errores} celda(s) con errores de Excel (#N/A, #REF!…).", t.codigo))
            b.linea(f"«{t.nombre}» trae {errores} celda(s) con errores de Excel; no se convierten en cero, quedan "
                    "como incidencia.", "aviso")
    if faltantes:
        b.fin("detenido", f"Faltan documentos o columnas: {'; '.join(faltantes)}.")
        b.no_ejecutados("No se ejecutó porque faltan documentos.")
        return Resultado([], [], c.inc, [], faltantes, bitacora=b)
    b.fin("ok", f"{len(docs)} documentos completos.")

    # ---- Paso 2. Consolidar y organizar
    b.inicio(2)
    b.linea(f"Empresa con RFC {c.rfc_empresa}: sus propios pagos y gastos no se declaran.")
    sistema = [k for k in cfg.criterios.values() if k.tipo == "sistema"]
    pend = sorted(k.clave for k in sistema if k.estado != crit.APROBADO)
    b.linea(f"Base de conocimiento fiscal ({cfg.origen}): {len(sistema) - len(pend)} criterios del sistema aprobados"
            + (f", {len(pend)} pendientes ({', '.join(pend)}): se aplican, y si cambian el resultado del mes sale una "
               "incidencia para revisar" if pend else "") + f"; {len(cfg.propios())} criterio(s) propio(s) de Fiscal "
            f"aprobado(s). Layout de {cfg.campos_layout} campos.", "aviso" if pend else "ok")
    sin_rfc_cat = sum(1 for rfc, _ in c.catalogo.values() if not rfc)
    b.linea(f"Catálogo de proveedores: {len(c.catalogo):,} claves ({sin_rfc_cat:,} sin RFC). Se usa para poner el RFC "
            "a los pagos y gastos que solo traen la clave del proveedor.")
    tcs = _tipos_de_cambio(c)
    otras = sum(1 for v in tcs.values() if v != UNO)
    b.linea(f"Tipos de cambio por póliza en el auxiliar de IVA: {len(tcs):,} pólizas, {otras} en moneda extranjera.")
    tipos, _ = _tipos_operacion(docs, c.cfg.tipos_operacion)
    if tipos:
        conteo = defaultdict(int)
        for v in tipos.values():
            conteo[v] += 1
        b.linea("Tipos de operación de Fiscal: " + ", ".join(f"{n} RFC con {k}" for k, n in sorted(conteo.items()))
                + f"; los demás proveedores van con {omision}.")
    for codigo in ("tesoreria", "aplicaciones", "comprobantes", "iva_retenido"):
        if codigo in docs:
            b.linea(f"Por clasificar: {len(docs[codigo].filas):,} renglones de «{TIPOS[codigo].nombre}».")
    b.fin("ok", f"Catálogo de {len(c.catalogo):,} proveedores y {sum(len(t.filas) for t in docs.values()):,} renglones "
                "listos para clasificar.")

    # ---- Paso 3. Limpiar y clasificar
    b.inicio(3)
    _tesoreria(c)
    _aplicaciones(c)
    por_poliza = _comprobantes(c)
    if "iva_retenido" in docs:
        _iva_retenido(c, por_poliza)
    else:
        retenciones = [o for o in c.ops if o.fuente == "comprobantes"]
        c.inc.append(Incidencia(POSIBLE if retenciones else SIN_IMPACTO, "SIN-RETENIDO",
                                "No se cargó el auxiliar de IVA retenido (2500-002-007); el IVA retenido sale en cero."))
    if "tipos_operacion" not in docs:
        c.inc.append(Incidencia(CONTROLADO, "SIN-TIPOS", "No se cargó la lista de tipos de operación; todos los "
                                f"proveedores van con el tipo por omisión ({omision})."))
    _pendientes_de_clasificacion(c)
    for codigo in ("tesoreria", "aplicaciones", "comprobantes", "iva_retenido"):
        ops_doc = [o for o in c.ops if o.fuente == codigo]
        if not ops_doc and codigo not in docs:
            continue
        por_regla: dict[str, list[Operacion]] = defaultdict(list)
        for o in ops_doc:
            por_regla[o.regla].append(o)
        entran = sum(1 for o in ops_doc if o.incluida)
        b.linea(f"«{TIPOS[codigo].nombre}»: {len(ops_doc):,} renglones, {entran:,} entran a la DIOT.", "ok")
        for regla, ops in sorted(por_regla.items(), key=lambda x: -len(x[1])):
            iva = sum((o.iva16 + o.iva8 for o in ops), CERO)
            b.linea(f"  {regla}: {len(ops):,} renglón(es){', IVA ' + _pesos(iva) if iva else ''} · "
                    f"{'entran' if ops[0].incluida else 'no entran'}. {texto_regla(cfg, regla)}",
                    datos={"regla": regla, "renglones": [o.renglon for o in ops][:200]})
    duplicados = [i for i in c.inc if i.codigo == "POSIBLE-DUPLICADO"]
    b.linea(f"Duplicados: {len(duplicados)} renglón(es) idénticos a otro. Se cuentan, como en el papel de trabajo; la "
            "conciliación del paso 4 dice si alguno sobra." if duplicados else "Duplicados: ninguno.",
            "aviso" if duplicados else "ok", datos={"renglones": [(i.fuente, i.renglon) for i in duplicados]})
    sin_rfc: dict[tuple[str, str], list[Operacion]] = defaultdict(list)
    for o in c.ops:
        if o.incluida and not o.rfc:
            sin_rfc[(o.fuente, o.referencia)].append(o)
    for (fuente, ref), ops in sin_rfc.items():
        iva = sum((o.iva16 + o.iva8 for o in ops), CERO)
        c.inc.append(Incidencia(POSIBLE, "SIN-RFC", f"{ref}: {ops[0].nombre or 'sin nombre'} sin RFC ({len(ops)} "
                                f"renglón(es), IVA {iva:,.2f}); no entra al consolidado.", fuente, ops[0].renglon,
                                importe=iva))
    rfcs = {o.rfc for o in c.ops if o.incluida and o.rfc}
    invalidos = sorted(r for r in rfcs if not rfc_valido(r))
    b.linea(f"Terceros con RFC: {len(rfcs):,}; con formato inválido: {len(invalidos)}"
            + (f" ({', '.join(invalidos[:10])})" if invalidos else "") + f"; movimientos sin RFC: {len(sin_rfc)}.",
            "aviso" if invalidos or sin_rfc else "ok")
    b.fin("aviso" if invalidos or sin_rfc or duplicados else "ok",
          f"{sum(1 for o in c.ops if o.incluida):,} de {len(c.ops):,} renglones entran, de {len(rfcs):,} terceros.")

    # ---- Paso 4. Conciliar IVA acreditable vs auxiliar
    b.inicio(4)
    grupos, difs, fuera = _conciliar(c)
    for g in grupos:
        b.linea(f"{g['concepto']}: operaciones {_pesos(g['operaciones'])} contra auxiliar {_pesos(g['auxiliar'])}, "
                f"diferencia {_pesos(g['diferencia'])} · {g['movimientos']} movimientos, {g['con_diferencia']} con "
                f"diferencia de más de {_pesos(TOLERANCIA_CONCILIACION)}.", "ok" if not g["con_diferencia"] else "aviso",
                datos={k: str(v) if isinstance(v, Decimal) else v for k, v in g.items()})
    if fuera:
        b.linea(f"El auxiliar también trae {_pesos(fuera)} que no son de proveedores (pago provisional del IVA); no se "
                "concilian.")
    abiertas = [d for d in difs if not d["compensada"]]
    compensadas = [d for d in difs if d["compensada"]]
    correcta = not abiertas
    b.linea(f"¿Conciliación correcta? {'Sí' if correcta else 'No'}: "
            + ("cada grupo cuadra con el auxiliar" if correcta else f"{len(abiertas)} movimiento(s) no cuadran")
            + (f"; {len(compensadas)} movimiento(s) tienen diferencias que se compensan entre pólizas" if compensadas
               else "") + ".", "ok" if correcta else "aviso")
    b.fin("ok" if correcta else "aviso",
          ("Conciliación correcta." + (f" {len(compensadas)} diferencia(s) se compensan entre pólizas." if compensadas
                                       else "")) if correcta else
          f"{len(abiertas)} diferencia(s) por revisar, {len(compensadas)} compensada(s).")

    # ---- Paso 5. Revisar diferencias
    b.inicio(5)
    if not difs:
        b.linea("No hay diferencias de conciliación que revisar.", "ok")
        b.fin("ok", "Sin diferencias.")
    else:
        for d in difs:
            msg = (f"{NOMBRE_GRUPO[d['grupo']]} · {d['movimiento']}: IVA de las operaciones {_pesos(d['operaciones'])} "
                   f"contra auxiliar {_pesos(d['auxiliar'])} (diferencia {_pesos(d['diferencia'])}). ")
            if d["compensada"]:
                msg += "Se compensa con otra póliza del mismo grupo (por ejemplo, una devolución registrada aparte)."
            else:
                msg += "Identifica la causa y, si hace falta, captura un ajuste."
            c.inc.append(Incidencia(CONTROLADO if d["compensada"] else POSIBLE, "CONCILIACION", msg, d["grupo"],
                                    importe=d["diferencia"]))
            b.linea(msg, "info" if d["compensada"] else "aviso")
        if abiertas:
            b.linea("Las diferencias que no se compensan quedan como incidencias con posible impacto: el TXT no se "
                    "entrega hasta que Fiscal las revise.", "aviso")
        b.fin("aviso" if abiertas else "ok", f"{len(abiertas)} diferencia(s) para Fiscal"
              + (f"; {len(compensadas)} compensada(s), quedan como controladas." if compensadas else "."))

    # ---- Paso 6. Generar archivo DIOT (TXT)
    b.inicio(6)
    for a in ajustes or []:
        cambio = ("se quita de la DIOT" if a.get("excluir") else
                  ", ".join(x for x in (f"{a['campo']} {Decimal(str(a['importe'])):+,.2f}" if a.get("campo") else "",
                                         f"tipo de tercero {a['tipo_tercero']}" if a.get("tipo_tercero") else "",
                                         f"tipo de operación {a['tipo_operacion']}" if a.get("tipo_operacion") else "")
                            if x))
        b.linea(f"Ajuste de Fiscal a {a['rfc']}: {cambio}. Motivo: {a.get('motivo')}", datos={"ajuste": a.get("id")})
    terceros = _consolidar(c, ajustes or [])
    por_tipo = defaultdict(int)
    for t in terceros:
        por_tipo[(t.tipo_tercero, t.tipo_operacion)] += 1
    b.linea(f"Consolidado por RFC: {len(terceros)} terceros ("
            + ", ".join(f"{n} tipo {k[0]}/{k[1]}" for k, n in sorted(por_tipo.items())) + ").")
    b.linea("Cada importe se sumó con todos sus decimales y se redondeó al peso: "
            + crit.OPCIONES_REDONDEO.get(cfg.p("TER-REDONDEO", "metodo"), "") + ".")
    revisar = [t.rfc for t in terceros if t.estado != "ok"]
    txt = None
    if revisar:
        b.linea(f"{len(revisar)} tercero(s) por revisar ({', '.join(revisar[:10])}): no se genera el TXT hasta "
                "resolverlo.", "error")
        b.fin("detenido", "TXT no generado: hay terceros por revisar.")
    else:
        txt = layout.generar(terceros, cfg)
        b.linea(f"TXT generado: {len(terceros)} renglones de {cfg.campos_layout} campos separados por «|». Campos "
                "llenos: " + ", ".join(f"{n} {crit.QUE_LLEVA.get(v, v)}" for n, v in sorted(cfg.mapa.items())) + ".",
                "ok")
        b.fin("ok", f"TXT de {len(terceros)} renglones.")

    # ---- Paso 7. Validar archivo DIOT
    b.inicio(7)
    validaciones = []
    if txt is None:
        b.linea("No hay TXT que validar.", "aviso")
        b.fin("detenido", "Sin TXT.")
    else:
        validaciones = layout.validar(txt, terceros, cfg)
        for v in validaciones:
            b.linea(f"{v['verificacion']}: {v['detalle']}", "ok" if v["ok"] else "error")
        malas = [v for v in validaciones if not v["ok"]]
        if malas:
            txt = None
            b.fin("detenido", f"{len(malas)} validación(es) no pasaron; el TXT no se entrega.")
        else:
            b.fin("ok", f"Las {len(validaciones)} validaciones pasaron.")

    cuadres = [{"concepto": g["concepto"], "importe": g["operaciones"], "auxiliar": g["auxiliar"],
                "diferencia": g["diferencia"]} for g in grupos]
    return Resultado(c.ops, terceros, c.inc, cuadres, [], txt=txt, validaciones=validaciones, bitacora=b)
