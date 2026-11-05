"""DIOT: criterios fiscales, catálogos del SAT y layout del TXT, tal como los guarda la Base de conocimiento fiscal.

Pedido de Diego, 2026-10-30: «si cambian las reglas se cambien documentos o criterios», sin tocar el código. El motor
(diot_motor.py) recibe una `Config` armada con lo vigente en el periodo; aquí están las definiciones de los criterios
del sistema (los que el motor sabe aplicar), sus parámetros editables y la carga inicial.

Estados de un criterio:
- aprobado: se aplica sin más.
- pendiente: el criterio del sistema se aplica igual (el proceso no puede saltárselo), pero cuando cambia el resultado
  del mes sale una incidencia con posible impacto: el TXT no se entrega hasta que Fiscal la revise o apruebe el criterio.
  Un criterio propio pendiente no se aplica.
- borrador: como pendiente, pero todavía no se manda a aprobar.
- retirado: solo para criterios propios; ya no se aplica.

Este módulo no sabe de la base de datos ni usa IA: es determinista.
"""
from dataclasses import dataclass, field

APROBADO, PENDIENTE, BORRADOR, RETIRADO = "aprobado", "pendiente", "borrador", "retirado"
ESTADOS = (BORRADOR, PENDIENTE, APROBADO, RETIRADO)

# Documentos de soporte de la carga inicial (se registran en la base con estos títulos)
DOC_PAPEL = "Papel de trabajo «MMAA DIOT ODP.xlsx» y TXT presentados (agosto y septiembre de 2026)"
DOC_FISCAL = "Mensaje de Fiscal del 30 de octubre de 2026 (tipos de operación y de tercero)"
DOC_MATRIZ = "Tasas del IVA y conceptos 2026 (matriz de Fiscal)"
DOC_SAT = "Aviso del portal del SAT: ajuste de montos con fracciones de peso (art. 20 CFF)"
DOC_REQUERIMIENTOS = "Requerimientos de automatización de la DIOT (Fiscal, 30 de octubre de 2026)"
DOC_RESPUESTAS = "Respuestas de Fiscal a las preguntas del plan (30 de octubre de 2026)"

CATEGORIAS = {
    "tesoreria": "Pagos de tesorería",
    "aplicaciones": "Aplicaciones de CxP",
    "comprobantes": "Gastos comprobados y caja chica",
    "retenciones": "IVA retenido",
    "consolidado": "Consolidado y tipos",
    "redondeo": "Redondeo",
    "propio": "Criterios propios de Fiscal",
}

# Parámetro editable: (nombre, etiqueta, tipo, opciones). tipo: lista (de textos) / opcion / texto
OPCIONES_IMSS = {"no_objeto": "Se declara como no objeto (campo de no objeto)", "excluir": "No se declara"}
OPCIONES_SIN_IVA = {"no_objeto": "Se declara como no objeto",
                    "incidencia": "No se declara y sale como incidencia para que Fiscal la clasifique"}
OPCIONES_REDONDEO = {"mitad_arriba": "50 centavos suben al peso siguiente (como se presentó en agosto y septiembre)",
                     "art20": "Artículo 20 del CFF: de 1 a 50 centavos bajan, de 51 a 99 suben"}


@dataclass(frozen=True)
class Definicion:
    """Un criterio que el motor sabe aplicar. Los parámetros se editan en la base; la lógica, no."""
    clave: str
    categoria: str
    titulo: str
    descripcion: str
    parametros: dict = field(default_factory=dict)  # valores iniciales
    campos: tuple = ()  # (nombre, etiqueta, tipo, opciones)
    estado: str = APROBADO  # estado de la carga inicial
    documento: str = DOC_PAPEL
    referencia: str | None = None
    contradiccion: str | None = None
    evidencia: str | None = None


SISTEMA: tuple[Definicion, ...] = (
    Definicion("TES-BANCO", "tesoreria", "Movimientos del banco no van",
               "Abonos y cargos bancarios (intereses, ISR retenido por el banco) no son operaciones con proveedores.",
               {"movimientos": ["Abono Bancario", "Cargo Bancario"]},
               (("movimientos", "Movimientos de tesorería que no van", "lista", None),)),
    Definicion("TES-ANTICIPO-SF", "tesoreria", "Anticipo sin factura: se declara al aplicarse",
               "Un anticipo a proveedor sin factura no se declara al pagarse; se declara cuando se aplica contra su "
               "factura (Aplicaciones de CxP).", {"prefijos": ["ANTICIPO SF"]},
               (("prefijos", "El concepto empieza con", "lista", None),),
               referencia="Hoja «AMARRE VS CFDI-COMPLEMENTO-BCOS»",
               evidencia="En septiembre Fiscal declaró un «ANTICIPO SF PROVEEDOR» (GAL070220T56) como base 0 con su "
                         "CFDI; el documento de requerimientos dice que ese caso no es una regla para todos los "
                         "anticipos. Se registra como ajuste de Fiscal."),
    Definicion("TES-ANTICIPO", "tesoreria", "Gastos a comprobar: se declaran con su comprobante",
               "El concepto exactamente «ANTICIPO» (gastos a comprobar) no se declara al pagarse; se declara cuando "
               "llega su comprobante en el Explorador de gastos. «ANTICIPO PROVEEDOR» y «ANTICIPO ACREEDOR» sí se "
               "declaran con su tasa.", {"conceptos": ["ANTICIPO"]},
               (("conceptos", "Concepto exactamente igual a", "lista", None),)),
    Definicion("TES-CAJA-CHICA", "tesoreria", "Reembolsos de caja chica: se declaran sus comprobantes",
               "El reembolso de caja chica no se declara; se declaran los comprobantes que lo forman (Explorador de "
               "gastos), con el proveedor real de cada uno.",
               {"contiene": ["CAJA CHICA"], "empieza": ["REEM CC", "CC "]},
               (("contiene", "La referencia contiene", "lista", None),
                ("empieza", "La referencia empieza con", "lista", None))),
    Definicion("TES-IMSS", "tesoreria", "Pago al IMSS",
               "El pago de cuotas al IMSS se declara como no objeto. El INFONAVIT no se declara: si el concepto dice "
               "«retiro», el pago bimestral puede traer la parte del INFONAVIT, que se resta con un ajuste.",
               {"rfcs": ["IMS421231I45"], "nombres": ["SEGURO SOCIAL"], "tratamiento": "no_objeto"},
               (("rfcs", "RFC del IMSS", "lista", None), ("nombres", "El beneficiario contiene", "lista", None),
                ("tratamiento", "Cómo se declara", "opcion", OPCIONES_IMSS)),
               documento=DOC_RESPUESTAS, referencia="Respuesta 3: «El Infonavit se descarta y el IMSS se dejaría "
                                                    "como no objeto»",
               evidencia="La matriz «Tasas del IVA y conceptos 2026» pone IMSS e INFONAVIT fuera de la ley del IVA; "
                         "Fiscal decidió declarar el IMSS como no objeto y no declarar el INFONAVIT. En septiembre se "
                         "había presentado un renglón de INFONAVIT (INF7205011ZA)."),
    Definicion("TES-NOMINA", "tesoreria", "Nómina, impuestos y retenciones no van",
               "Nómina, finiquitos, ISR, IMSS de nómina, FONACOT, caja de ahorro e impuesto sobre nómina no son "
               "operaciones con proveedores.",
               {"referencia_empieza": ["NOMINA", "FINIQUITO"], "concepto_empieza": ["ISR", "IMSS", "FONACOT"],
                "concepto_contiene": ["CAJA AHORRO", "SOBRE NOMINA", "SOBRE NÓMINA"]},
               (("referencia_empieza", "La referencia empieza con", "lista", None),
                ("concepto_empieza", "El concepto empieza con", "lista", None),
                ("concepto_contiene", "El concepto contiene", "lista", None)),
               documento=DOC_REQUERIMIENTOS,
               referencia="Sección 9: «FONACOT … no se incluye en la DIOT»; respuesta 4: «Impuestos sobre nómina "
                          "no se declaran»"),
    Definicion("TES-PROPIA", "tesoreria", "Pagos a la propia empresa no van",
               "Los pagos cuyo RFC es el de la propia empresa no son operaciones con terceros."),
    Definicion("TES-TASA", "tesoreria", "Pago con tasa de IVA",
               "IVA = Importe1 × tipo de cambio; base 16 % = IVA / 0.16; base 0 % = SubTotal × tipo de cambio."),
    Definicion("TES-SIN-TASA", "tesoreria", "Pago sin tasa ni criterio",
               "Un pago sin tasa de IVA ni criterio que lo clasifique no se declara; queda como incidencia para que "
               "Fiscal lo clasifique."),
    Definicion("APL-APLICACION", "aplicaciones", "Aplicación de anticipo con IVA",
               "Base = (SubTotal + IEPS) × tipo de cambio del auxiliar; IVA = Importe1 × tipo de cambio del auxiliar."),
    Definicion("APL-OTRO", "aplicaciones", "Otros renglones de aplicaciones no van",
               "Renglones que no son «Aplicacion» con IVA (pago provisional, anticipo) no van."),
    Definicion("COM-CANCELADO", "comprobantes", "Solo comprobantes concluidos",
               "Los comprobantes cancelados o pendientes no se declaran."),
    Definicion("COM-AUXILIAR", "comprobantes", "Solo comprobantes en el auxiliar de IVA del mes",
               "Solo cuenta el comprobante cuya póliza (Poliza + PolizaID) está en el auxiliar de IVA acreditable."),
    Definicion("COM-PROPIA", "comprobantes", "Gastos a nombre de la propia empresa no van",
               "Gastos a nombre de la propia empresa (no deducibles) no se declaran."),
    Definicion("COM-TASA", "comprobantes", "Comprobante con IVA",
               "Base = Cantidad × Precio × tipo de cambio; IVA = base × % IVA."),
    Definicion("COM-TASA0", "comprobantes", "Conceptos a tasa 0 %",
               "Comprobantes sin IVA cuyo concepto está en esta lista van a tasa 0 %. La matriz pone a 0 % el agua "
               "natural en envases de 10 litros o más; en menos de 10 litros, gaseosa o saborizada va a 16 %.",
               {"conceptos": ["AGUA DE GARRAFON"]},
               (("conceptos", "El concepto contiene", "lista", None),),
               documento=DOC_MATRIZ, referencia="Art. 2-A, fracc. I, inciso c) LIVA"),
    Definicion("COM-NO-OBJETO", "comprobantes", "Comprobantes sin IVA que no son tasa 0 %",
               "Comprobantes sin IVA que no están en la lista de tasa 0 % (predial, derechos, DAP, donativos) van "
               "como no objeto. El recibo de agua de tiendas y oficinas debe traer IVA 16 % (8 % en zona fronteriza): "
               "si llega sin IVA, sale como incidencia para revisarlo.",
               {"tratamiento": "no_objeto", "revisar": ["AGUA"]},
               (("tratamiento", "Cómo se declaran", "opcion", OPCIONES_SIN_IVA),
                ("revisar", "Conceptos que deberían traer IVA (sale incidencia si llegan sin IVA)", "lista", None)),
               documento=DOC_RESPUESTAS,
               referencia="Respuestas 4 y 5: predial y derechos no objeto; agua de tiendas y oficinas al 16 % (8 % en "
                          "frontera)",
               evidencia="La matriz pone predial y derechos fuera de la ley del IVA y el agua de uso doméstico a 0 %; "
                         "Fiscal decidió no objeto para predial y derechos, y 16 % u 8 % para el agua de tiendas y "
                         "oficinas."),
    Definicion("RET-AUXILIAR", "retenciones", "IVA retenido del auxiliar 2500-002-007",
               "Haber menos debe del auxiliar, asignado al acreedor del comprobante de la misma póliza."),
    Definicion("TER-TIPO-TERCERO", "consolidado", "Tipo de tercero",
               "04 nacional: RFC mexicano válido. 05 extranjero: reside en el extranjero y no tiene RFC mexicano. 15 "
               "global: operaciones agrupadas (gastos menores o público en general). Un RFC con formato inválido no "
               "recibe tipo: queda por revisar.",
               {"extranjeros": ["XEXX010101000"], "globales": ["XAXX010101000"], "tope_global": "10"},
               (("extranjeros", "RFC que van como 05 extranjero", "lista", None),
                ("globales", "RFC que van como 15 global", "lista", None),
                ("tope_global", "Tope del global: % del total de pagos del mes", "texto", None)),
               documento=DOC_RESPUESTAS,
               referencia="Respuestas 2 y 6: extranjero es 05 con operación 07; el global usa el RFC genérico con "
                          "tope del 10 % del total de los pagos"),
    Definicion("TER-TIPO-OPERACION", "consolidado", "Tipo de operación por omisión",
               "Tipo de operación del proveedor que no está en la lista de Fiscal (hoja RETENCIONES).",
               {"omision": "02", "global": "85", "extranjero": "07"},
               (("omision", "Tipo de operación si el RFC no está en la lista", "texto", None),
                ("global", "Tipo de operación del tercero 15 global", "texto", None),
                ("extranjero", "Tipo de operación del tercero 05 extranjero", "texto", None)),
               estado=PENDIENTE, documento=DOC_FISCAL,
               contradiccion="Fiscal dijo el 30 de octubre que compras de mercancías, activos y gastos van como 85 "
                             "(Otros) y no mencionó el 02. Pero en los TXT presentados de agosto y septiembre, 80 de "
                             "81 y 68 de 69 renglones van como 02. Fiscal confirma cuál corresponde al layout que "
                             "usan."),
    Definicion("TER-REDONDEO", "redondeo", "Redondeo al peso",
               "Se suma todo con decimales y se redondea al final, por tercero y campo, para subir al layout "
               "(respuesta 1 de Fiscal). Falta decidir qué pasa con los 50 centavos exactos.",
               {"metodo": "mitad_arriba"},
               (("metodo", "Cómo se redondean los 50 centavos", "opcion", OPCIONES_REDONDEO),),
               estado=PENDIENTE, documento=DOC_SAT, referencia="Art. 20, décimo párrafo, CFF",
               contradiccion="El aviso del SAT dice que de 1 a 50 centavos se ajustan al peso anterior. En los TXT "
                             "presentados los importes con 50 centavos exactos se subieron (FLE021121LP9 145,025.50 → "
                             "145,026 y GOSS861008T33 10,452.50 → 10,453 en agosto; GOSS861008T33, INS180206187 y "
                             "TTO220111195 en septiembre). Solo sale incidencia el mes en que haya un importe con 50 "
                             "centavos exactos."),
)
POR_CLAVE = {d.clave: d for d in SISTEMA}

# Criterios propios de Fiscal: condición sobre un renglón y qué hacer con él
FUENTES_PROPIAS = {"tesoreria": "Pagos de tesorería", "comprobantes": "Gastos comprobados y caja chica",
                   "cualquiera": "Cualquiera de los dos"}
CAMPOS_CONDICION = {"concepto": "Concepto", "referencia": "Referencia", "nombre": "Nombre del proveedor",
                    "rfc": "RFC"}
OPERADORES = {"contiene": "contiene", "empieza": "empieza con", "igual": "es igual a"}
ACCIONES = {"excluir": "No se declara", "tasa0": "Va a tasa 0 %", "no_objeto": "Va como no objeto",
            "exento": "Va como exento", "tipo_operacion": "Cambia el tipo de operación del proveedor"}

# Catálogos del SAT y layout (carga inicial; cada uno tiene vigencia en la base)
TIPOS_TERCERO = {"04": "Nacional: proveedor inscrito en México con RFC",
                 "05": "Extranjero: reside en el extranjero y no tiene RFC mexicano",
                 "15": "Global: operaciones agrupadas cuando las reglas de la DIOT lo permiten"}
TIPOS_OPERACION = {"02": "Enajenación de bienes (así van los TXT presentados de agosto y septiembre; Fiscal no lo "
                         "incluyó en su lista del 30 de octubre)",
                   "03": "Prestación de servicios profesionales",
                   "06": "Arrendamiento de inmuebles",
                   "07": "Extranjero: va con el tipo de tercero 05",
                   "85": "Otros: adquisición de bienes, mercancías, activos fijos, gastos generales"}
CAMPOS_LAYOUT = 54
# número de campo -> qué lleva (observado en los TXT presentados por Fiscal)
MAPA_LAYOUT = {1: "tipo_tercero", 2: "tipo_operacion", 3: "rfc", 12: "base16", 22: "iva16", 48: "iva_retenido",
               51: "base0", 52: "no_objeto", 54: "efectos"}
VALOR_EFECTOS = "01"
QUE_LLEVA = {"tipo_tercero": "Tipo de tercero", "tipo_operacion": "Tipo de operación", "rfc": "RFC",
             "base16": "Base 16 %", "iva16": "IVA 16 %", "base8": "Base 8 %", "iva8": "IVA 8 %", "base0": "Base 0 %",
             "exento": "Exento", "no_objeto": "Base no objeto", "iva_retenido": "IVA retenido",
             "efectos": "Campo 54 (cumplimiento de requisitos fiscales)"}


@dataclass
class Criterio:
    clave: str
    titulo: str
    estado: str
    parametros: dict
    version: int = 1
    tipo: str = "sistema"  # sistema / propio
    condicion: dict | None = None  # propios: fuente, campo, operador, valor
    accion: dict | None = None  # propios: accion, tipo_operacion
    prioridad: int = 100
    descripcion: str = ""


@dataclass
class Config:
    """Lo vigente para un periodo. `version` describe qué se usó (queda en la corrida)."""
    criterios: dict[str, Criterio]
    tipos_tercero: dict[str, str]
    tipos_operacion: dict[str, str]
    campos_layout: int = CAMPOS_LAYOUT
    mapa: dict[int, str] = field(default_factory=lambda: dict(MAPA_LAYOUT))
    efectos: str = VALOR_EFECTOS
    origen: str = "carga inicial"

    def p(self, clave: str, nombre: str):
        c = self.criterios.get(clave)
        if c and nombre in c.parametros:
            return c.parametros[nombre]
        return POR_CLAVE[clave].parametros[nombre]

    def lista(self, clave: str, nombre: str) -> list[str]:
        return [str(x).upper() for x in self.p(clave, nombre) or [] if str(x).strip()]

    def estado(self, clave: str) -> str:
        c = self.criterios.get(clave)
        return c.estado if c else APROBADO

    def aprobado(self, clave: str) -> bool:
        return self.estado(clave) == APROBADO

    def titulo(self, clave: str) -> str:
        c = self.criterios.get(clave)
        return c.titulo if c else (POR_CLAVE[clave].titulo if clave in POR_CLAVE else clave)

    def propios(self) -> list[Criterio]:
        """Criterios propios aprobados, en orden de prioridad (menor primero)."""
        return sorted((c for c in self.criterios.values() if c.tipo == "propio" and c.estado == APROBADO),
                      key=lambda c: (c.prioridad, c.clave))

    def resumen(self) -> dict:
        return {"origen": self.origen,
                "criterios": {k: {"version": c.version, "estado": c.estado} for k, c in sorted(self.criterios.items())},
                "layout": {"campos": self.campos_layout, "mapa": {str(k): v for k, v in sorted(self.mapa.items())}}}


def inicial() -> Config:
    """La carga inicial, igual a lo que la base trae recién creada (también la usa el motor sin base)."""
    return Config(criterios={d.clave: Criterio(d.clave, d.titulo, d.estado, dict(d.parametros), descripcion=d.descripcion)
                             for d in SISTEMA},
                  tipos_tercero=dict(TIPOS_TERCERO), tipos_operacion=dict(TIPOS_OPERACION))


def todo_aprobado() -> Config:
    c = inicial()
    for x in c.criterios.values():
        x.estado = APROBADO
    return c


def coincide(condicion: dict, valores: dict[str, str]) -> bool:
    """¿El renglón cumple la condición de un criterio propio? `valores` trae concepto, referencia, nombre y rfc."""
    v = (valores.get(condicion.get("campo", "")) or "").upper().strip()
    buscado = (condicion.get("valor") or "").upper().strip()
    if not buscado:
        return False
    op = condicion.get("operador")
    return (op == "contiene" and buscado in v) or (op == "empieza" and v.startswith(buscado)) or (
        op == "igual" and v == buscado)
