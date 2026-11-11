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
from functools import lru_cache
from pathlib import Path

APROBADO, PENDIENTE, BORRADOR, RETIRADO = "aprobado", "pendiente", "borrador", "retirado"
ESTADOS = (BORRADOR, PENDIENTE, APROBADO, RETIRADO)

# Documentos de soporte de la carga inicial (se registran en la base con estos títulos)
DOC_PAPEL = "Papel de trabajo «MMAA DIOT ODP.xlsx» y TXT presentados (agosto y septiembre de 2026)"
DOC_FISCAL = "Mensaje de Fiscal del 30 de octubre de 2026 (tipos de operación y de tercero)"
DOC_MATRIZ = "Tasas del IVA y conceptos 2026 (matriz de Fiscal)"
DOC_SAT = "Aviso del portal del SAT: ajuste de montos con fracciones de peso (art. 20 CFF)"
DOC_REQUERIMIENTOS = "Requerimientos de automatización de la DIOT (Fiscal, 30 de octubre de 2026)"
DOC_RESPUESTAS = "Respuestas de Fiscal a las preguntas del plan (30 de octubre de 2026)"
DOC_LAYOUT_FISCAL = "Layout de la DIOT de Fiscal («0926 LAYOUT DIOT OPD.xlsx», hoja DIOT)"
DOC_TXT_PRESENTADOS = "TXT presentados de ODP (ago y sep 2026), SMN (feb 2026) y PS (sep 2026)"
DOC_JUNTA_NOV = "Respuestas de Fiscal en la junta del 10 de noviembre de 2026 (SMN, PS y ODP)"

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
OPCIONES_SIN_TASA = {"tasa0": "Va a tasa 0 % (sale un aviso para revisarlo)",
                     "incidencia": "No se declara y sale como incidencia para que Fiscal lo clasifique"}
# Lo que Fiscal resolvió el 10 de noviembre sobre criterios que la carga inicial dejó pendientes. sembrar() lo aplica
# a una base ya cargada solo si el criterio sigue pendiente como lo dejó la carga (nadie lo ha tocado).
RESUELTOS_JUNTA_NOV = ("TER-TIPO-OPERACION", "TER-REDONDEO")
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
               "factura (Aplicaciones de CxP). Un «ANTICIPO PROVEEDOR» o «ANTICIPO ACREEDOR» sin tasa de IVA tampoco: sin "
               "factura no hay IVA (Fiscal, 10 de noviembre).",
               {"prefijos": ["ANTICIPO SF"], "sin_tasa": ["ANTICIPO PROVEEDOR", "ANTICIPO ACREEDOR"]},
               (("prefijos", "El concepto empieza con", "lista", None),
                ("sin_tasa", "Si viene sin tasa de IVA, el concepto empieza con", "lista", None)),
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
    Definicion("TES-CLIENTE", "tesoreria", "Pagos a clientes no van",
               "Un pago cuyo contacto es un Cliente (devoluciones, anticipos de clientes, liquidaciones de ventas) es "
               "IVA causado, no acreditable: no se declara en la DIOT.",
               {"contacto_tipo": ["Cliente"]},
               (("contacto_tipo", "Tipo de contacto en tesorería", "lista", None),),
               documento=DOC_JUNTA_NOV, referencia="«Si es cliente no es IVA acreditable, es IVA causado y no se declara "
                                                   "en la DIOT»"),
    Definicion("TES-IMPUESTOS", "tesoreria", "Pagos de impuestos al SAT no van",
               "Los pagos a la Tesorería de la Federación (ISR, IVA, IEPS, retenciones) son entero de impuestos, no "
               "operaciones con proveedores.",
               {"beneficiarios": ["TESORERIA DE LA FEDERACION", "TESORERÍA DE LA FEDERACIÓN",
                                  "SERVICIO DE ADMINISTRACION TRIBUTARIA"]},
               (("beneficiarios", "El beneficiario contiene", "lista", None),),
               documento=DOC_JUNTA_NOV, referencia="Respuesta 8b"),
    Definicion("TES-PRESTAMO", "tesoreria", "Pago de capital de préstamos no va",
               "El pago de capital de un préstamo (sin tasa de IVA) no se declara. Los intereses sí llevan IVA y se "
               "declaran con su tasa cuando el reporte la trae.",
               {"conceptos": ["PRESTAMO", "PRÉSTAMO"]},
               (("conceptos", "Sin tasa de IVA y el concepto contiene", "lista", None),),
               documento=DOC_JUNTA_NOV, referencia="Respuesta 8c: «si es préstamo con interés sí debe tener», los "
                                                   "intereses llevan IVA"),
    Definicion("TES-PROPIA", "tesoreria", "Pagos a la propia empresa no van",
               "Los pagos cuyo RFC es el de la propia empresa no son operaciones con terceros."),
    Definicion("TES-TASA", "tesoreria", "Pago con tasa de IVA",
               "IVA = Importe1 × tipo de cambio; base 16 % = IVA / 0.16; base 0 % = SubTotal × tipo de cambio."),
    Definicion("TES-SIN-TASA", "tesoreria", "Pago sin tasa de IVA",
               "Un pago a proveedor o acreedor sin tasa de IVA, que no cae en otro criterio (impuestos, nómina, "
               "préstamos, clientes, anticipos), se declara a tasa 0 %: base 0 = SubTotal × tipo de cambio.",
               {"tratamiento": "tasa0"},
               (("tratamiento", "Cómo se declara", "opcion", OPCIONES_SIN_TASA),),
               documento=DOC_JUNTA_NOV, referencia="Respuesta 8a: «si no tiene tasa 16 o tasa 8 debe ser tasa 0»"),
    Definicion("TES-SIN-RFC", "tesoreria", "Pagos sin RFC van al RFC genérico",
               "Un pago de tesorería que entra a la DIOT pero no tiene RFC (personas a las que no se les capturó) se "
               "declara con el RFC genérico, dentro del tercero global y su tope.",
               {"rfc": "XAXX010101000"},
               (("rfc", "RFC genérico", "texto", None),),
               documento=DOC_JUNTA_NOV, referencia="Respuesta 9: «se quedan en el genérico»"),
    Definicion("TES-COMISIONES", "tesoreria", "Comisiones bancarias van al RFC genérico",
               "El IVA de las comisiones de bancos y plataformas (renglones «Cargo Bancario» del auxiliar de IVA "
               "acreditable) se declara con el RFC genérico: IVA = debe − haber; base 16 % = IVA / 0.16.",
               {"origenes": ["Cargo Bancario"], "rfc": "XAXX010101000"},
               (("origenes", "Origen en el auxiliar de IVA acreditable", "lista", None),
                ("rfc", "RFC con el que se declaran", "texto", None)),
               documento=DOC_JUNTA_NOV, referencia="Respuesta 6: «se registra en un RFC común, el genérico "
                                                   "XAXX010101000 para nacionales»"),
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
               {"tratamiento": "no_objeto", "revisar": ["AGUA"], "avisar_tipos": ["Proveedor"]},
               (("tratamiento", "Cómo se declaran", "opcion", OPCIONES_SIN_IVA),
                ("revisar", "Conceptos que deberían traer IVA (sale incidencia si llegan sin IVA)", "lista", None),
                ("avisar_tipos", "Avisar a Fiscal si el tercero es de este tipo en el catálogo", "lista", None)),
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
               "Tipo de operación del proveedor que no está en la lista de Fiscal (hoja RETENCIONES). Las compras "
               "van como 02.",
               {"omision": "02", "global": "85", "extranjero": "07"},
               (("omision", "Tipo de operación si el RFC no está en la lista", "texto", None),
                ("global", "Tipo de operación del tercero 15 global", "texto", None),
                ("extranjero", "Tipo de operación del tercero 05 extranjero", "texto", None)),
               documento=DOC_JUNTA_NOV, referencia="Respuesta 2: «las compras son 02» (SMN y PS presentaban 85)"),
    Definicion("TER-REDONDEO", "redondeo", "Redondeo al peso",
               "Se suma todo con decimales y se redondea al final, por tercero y campo, para subir al layout "
               "(respuesta 1 de Fiscal). Los 50 centavos se redondean como dice el artículo 20 del CFF.",
               {"metodo": "art20"},
               (("metodo", "Cómo se redondean los 50 centavos", "opcion", OPCIONES_REDONDEO),),
               documento=DOC_JUNTA_NOV, referencia="Respuesta 2: «déjala como dice el CFF» (art. 20, décimo "
                                                    "párrafo: de 1 a 50 centavos al peso anterior)"),
    Definicion("TER-TIPO-REGLA", "consolidado", "Tipo de operación de proveedores nuevos",
               "Sin la hoja de Fiscal, el tipo de operación sale de lo que se declaró en meses anteriores para ese "
               "proveedor en esa empresa. Si es un proveedor nuevo: 06 si sus gastos son arrendamiento, 03 si son "
               "honorarios o es persona física con retención de ISR del 10 %; si no, el tipo por omisión.",
               {"conceptos_06": ["ARRENDAMIENTO PERSONAS"], "conceptos_03": ["HONORARIO", "SERVICIOS PROFESIONALES"],
                "retencion_isr_03": "10"},
               (("conceptos_06", "Conceptos del gasto que son arrendamiento de inmuebles (empiezan con)", "lista", None),
                ("conceptos_03", "Conceptos que son servicios profesionales (contienen)", "lista", None),
                ("retencion_isr_03", "Retención de ISR (%) de persona física que la hace servicio profesional",
                 "texto", None)),
               documento=DOC_JUNTA_NOV,
               referencia="Diego, 10 nov: regla con CFDI y lista guardada; 03 servicios profesionales, 06 "
                          "arrendamiento de inmuebles, 07 extranjero, 85 otros"),
    Definicion("TES-TARJETA", "tesoreria", "El pago de la tarjeta de crédito no va",
               "Un pago de tesorería a la tarjeta (American Express) cuyo acreedor es el «Acreedor/Responsable» de "
               "gastos «Gasto T/Credito» no se declara: cada gasto ya entra con su proveedor real desde el Explorador "
               "de gastos, y la póliza del pago no lleva IVA. Contarlo duplicaría el IVA.",
               {"movimientos_gasto": ["Gasto T/Credito"]},
               (("movimientos_gasto", "Movimientos del Explorador de gastos pagados con tarjeta", "lista", None),),
               documento=DOC_JUNTA_NOV,
               referencia="Respuesta 7: «Gasto T/Crédito: el proveedor sale del Explorador de gastos». PS octubre "
                          "2026: PS49781 a American Express $833,105 por luz, internet y teléfono; IVA $108,585 sin "
                          "póliza de IVA"),
    Definicion("TES-TASA-ERRONEA", "tesoreria", "Tasa mal capturada",
               "Una tasa de IVA que no existe (19 %) es error de captura: se toma como 16 % con el IVA del reporte "
               "(el que está en el auxiliar).",
               {"tasas": ["19"], "corregir_a": "16"},
               (("tasas", "Tasas que son error de captura", "lista", None),
                ("corregir_a", "Se toman como", "texto", None)),
               documento=DOC_JUNTA_NOV, referencia="Diego, 10 nov: SMN147931 tasa 19 «debe ser error de escritura»"),
    Definicion("COM-SIN-RFC", "comprobantes", "Gastos sin proveedor en el catálogo van al genérico",
               "Un gasto o caja chica cuyo acreedor no está en el catálogo de proveedores (o no tiene RFC) se declara "
               "con el RFC genérico.",
               {"rfc": "XAXX010101000"},
               (("rfc", "RFC genérico", "texto", None),),
               documento=DOC_JUNTA_NOV, referencia="Diego, 10 nov: cajas chicas SMN1470 y SMN1578 «es genérico»"),
    Definicion("TER-RFC-CFDI", "consolidado", "RFC mal capturado se corrige con el CFDI",
               "Si el RFC del catálogo no tiene formato válido y en los CFDI del SAT hay un solo emisor cuyo RFC "
               "difiere en un carácter, se declara con el RFC del CFDI y se avisa para corregir el catálogo.",
               {"diferencia_max": "1"},
               (("diferencia_max", "Caracteres distintos como máximo", "texto", None),),
               documento=DOC_JUNTA_NOV,
               referencia="Diego, 10 nov: PV1230615EX2 «hay que validarlo»; el CFDI dice PVI230615EX2 Pinturas VIM"),
    Definicion("TER-REGION-GENERICO", "consolidado", "Región del 8 % del RFC genérico",
               "El RFC genérico no tiene CFDI con código postal: su 8 % va a la región que se indica por empresa "
               "(RFC de la empresa=norte o sur).",
               {"regiones": ["SMN890629150=norte"]},
               (("regiones", "RFC de la empresa = región", "lista", None),),
               documento=DOC_JUNTA_NOV, referencia="Diego, 10 nov: el genérico de SMN «sí es del norte»"),
)
POR_CLAVE = {d.clave: d for d in SISTEMA}
ARCHIVO_OPERACION_APRENDIDA = Path(__file__).with_name("datos") / "tipos_operacion_aprendidos.csv"


@lru_cache(maxsize=1)
def operacion_aprendida() -> dict[tuple[str, str], str]:
    """(RFC de la empresa, RFC del proveedor) → tipo de operación declarado en los TXT presentados (03, 06, 07 u
    «omision»). Es la carga inicial del catálogo «operacion_rfc» de la Base de conocimiento."""
    t = {}
    with open(ARCHIVO_OPERACION_APRENDIDA, encoding="utf-8") as f:
        for linea in f:
            if linea.startswith("#") or linea.startswith("empresa,"):
                continue
            empresa, rfc, tipo = linea.strip().split(",")[:3]
            t[(empresa, rfc)] = tipo
    return t

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
MAPA_LAYOUT = {1: "tipo_tercero", 2: "tipo_operacion", 3: "rfc", 8: "base8_norte", 10: "base8_sur", 12: "base16",
               18: "iva8_norte", 20: "iva8_sur", 22: "iva16", 48: "iva_retenido", 51: "base0", 52: "no_objeto",
               54: "efectos"}
# Campos del 8 % por región fronteriza: no estaban en los TXT de ODP; salen del layout de Fiscal (hoja DIOT: «ACTOS
# PAGADOS RFN/RFS», «8% Frontera Norte/Sur»). sembrar() los agrega a una base ya cargada.
CAMPOS_8_REGION = (8, 10, 18, 20)
VALOR_EFECTOS = "01"
QUE_LLEVA = {"tipo_tercero": "Tipo de tercero", "tipo_operacion": "Tipo de operación", "rfc": "RFC",
             "base16": "Base 16 %", "iva16": "IVA 16 %", "base8": "Base 8 %", "iva8": "IVA 8 %", "base0": "Base 0 %",
             "base8_norte": "Base 8 % región fronteriza norte", "iva8_norte": "IVA 8 % región fronteriza norte",
             "base8_sur": "Base 8 % región fronteriza sur", "iva8_sur": "IVA 8 % región fronteriza sur",
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
    # (RFC empresa, RFC proveedor) → tipo de operación que Fiscal ya le dio (catálogo «operacion_rfc»)
    operacion_rfc: dict[tuple[str, str], str] = field(default_factory=lambda: dict(operacion_aprendida()))

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
