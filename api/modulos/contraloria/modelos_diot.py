"""DIOT (esquema contraloria): empresas, periodos, documentos que entrega Fiscal y el resultado de cada proceso.

Cada «Procesar» borra y vuelve a escribir operaciones, terceros e incidencias del periodo a partir de los documentos
vigentes; la revisión que Fiscal hizo de una incidencia se conserva si la incidencia vuelve a salir igual.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nucleo.modelos import Base, ahora

ESQUEMA = "contraloria"
USUARIO = "nucleo.usuario.usuario_id"
PERIODO = f"{ESQUEMA}.diot_periodo.periodo_id"
IMPORTE = Numeric(20, 6)


class DiotEmpresa(Base):
    __tablename__ = "diot_empresa"
    __table_args__ = {"schema": ESQUEMA}

    empresa_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(Unicode(20), unique=True)
    nombre: Mapped[str] = mapped_column(Unicode(200))
    rfc: Mapped[str | None] = mapped_column(Unicode(13))  # vacío hasta que Fiscal lo confirme
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class DiotPeriodo(Base):
    __tablename__ = "diot_periodo"
    __table_args__ = {"schema": ESQUEMA}

    periodo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.diot_empresa.empresa_id"))
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(Unicode(20), default="abierto")  # abierto / procesado / cerrado
    resumen: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: cuadres, faltantes, conteos
    txt: Mapped[str | None] = mapped_column(UnicodeText)  # el TXT generado en el último proceso
    referencia_nombre: Mapped[str | None] = mapped_column(Unicode(200))
    referencia_txt: Mapped[str | None] = mapped_column(UnicodeText)  # TXT de Fiscal para comparar
    comparacion: Mapped[str | None] = mapped_column(UnicodeText)  # JSON
    iva_declarado: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))  # IVA acreditable de la declaración mensual
    iva_declarado_nota: Mapped[str | None] = mapped_column(Unicode(500))
    iva_declarado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    iva_declarado_en: Mapped[datetime | None] = mapped_column(DateTime)
    procesado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    procesado_en: Mapped[datetime | None] = mapped_column(DateTime)
    creado_por: Mapped[int] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    empresa: Mapped[DiotEmpresa] = relationship()


class DiotDocumento(Base):
    __tablename__ = "diot_documento"
    __table_args__ = {"schema": ESQUEMA}

    documento_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey(PERIODO))
    tipo: Mapped[str] = mapped_column(Unicode(30))
    nombre_archivo: Mapped[str] = mapped_column(Unicode(260))
    contenido: Mapped[bytes] = mapped_column(LargeBinary)
    tamano: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(Unicode(64))
    filas: Mapped[int] = mapped_column(Integer)
    hoja: Mapped[str | None] = mapped_column(Unicode(100))
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)  # al subir otro del mismo tipo, este deja de serlo
    cargado_por: Mapped[int] = mapped_column(ForeignKey(USUARIO))
    cargado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class DiotOperacion(Base):
    """Un renglón de un documento con la regla que se le aplicó; de aquí sale cada importe del consolidado."""
    __tablename__ = "diot_operacion"
    __table_args__ = {"schema": ESQUEMA}

    operacion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey(PERIODO))
    fuente: Mapped[str] = mapped_column(Unicode(30))
    renglon: Mapped[int] = mapped_column(Integer)
    referencia: Mapped[str] = mapped_column(Unicode(300))
    rfc: Mapped[str | None] = mapped_column(Unicode(20))
    nombre: Mapped[str | None] = mapped_column(Unicode(300))
    regla: Mapped[str] = mapped_column(Unicode(30))
    incluida: Mapped[bool] = mapped_column(Boolean)
    tasa: Mapped[str | None] = mapped_column(Unicode(20))
    tipo_cambio: Mapped[Decimal] = mapped_column(IMPORTE)
    base16: Mapped[Decimal] = mapped_column(IMPORTE)
    iva16: Mapped[Decimal] = mapped_column(IMPORTE)
    base8: Mapped[Decimal] = mapped_column(IMPORTE)
    iva8: Mapped[Decimal] = mapped_column(IMPORTE)
    base0: Mapped[Decimal] = mapped_column(IMPORTE)
    exento: Mapped[Decimal] = mapped_column(IMPORTE)
    no_objeto: Mapped[Decimal] = mapped_column(IMPORTE)
    iva_retenido: Mapped[Decimal] = mapped_column(IMPORTE)
    nota: Mapped[str | None] = mapped_column(Unicode(500))
    monto: Mapped[Decimal | None] = mapped_column(IMPORTE)  # lo que mueve el renglón (subtotal + IVA), entre o no


class DiotTercero(Base):
    __tablename__ = "diot_tercero"
    __table_args__ = {"schema": ESQUEMA}

    tercero_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey(PERIODO))
    rfc: Mapped[str] = mapped_column(Unicode(20))
    nombre: Mapped[str | None] = mapped_column(Unicode(300))
    tipo_tercero: Mapped[str] = mapped_column(Unicode(2))
    tipo_operacion: Mapped[str] = mapped_column(Unicode(2))
    exactos: Mapped[str] = mapped_column(UnicodeText)  # JSON con decimales
    redondeados: Mapped[str] = mapped_column(UnicodeText)  # JSON al peso: lo que va al TXT
    operaciones: Mapped[int] = mapped_column(Integer)
    fuentes: Mapped[str] = mapped_column(Unicode(200))
    estado: Mapped[str] = mapped_column(Unicode(20))  # ok / revisar
    ajustado: Mapped[bool] = mapped_column(Boolean, default=False)


class DiotIncidencia(Base):
    __tablename__ = "diot_incidencia"
    __table_args__ = {"schema": ESQUEMA}

    incidencia_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey(PERIODO))
    huella: Mapped[str] = mapped_column(Unicode(64))  # para conservar la revisión entre procesos
    impacto: Mapped[str] = mapped_column(Unicode(20))  # sin_impacto / controlado / posible_impacto
    codigo: Mapped[str] = mapped_column(Unicode(30))
    mensaje: Mapped[str] = mapped_column(Unicode(1000))
    fuente: Mapped[str | None] = mapped_column(Unicode(30))
    renglon: Mapped[int | None] = mapped_column(Integer)
    rfc: Mapped[str | None] = mapped_column(Unicode(20))
    importe: Mapped[Decimal | None] = mapped_column(IMPORTE)
    estado: Mapped[str] = mapped_column(Unicode(20), default="pendiente")  # pendiente / revisada
    nota_revision: Mapped[str | None] = mapped_column(Unicode(1000))
    revisada_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    revisada_en: Mapped[datetime | None] = mapped_column(DateTime)


class DiotAjuste(Base):
    """Ajuste de Fiscal sobre el consolidado, siempre con motivo: sumar a un campo, cambiar tipo o quitar un tercero."""
    __tablename__ = "diot_ajuste"
    __table_args__ = {"schema": ESQUEMA}

    ajuste_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey(PERIODO))
    rfc: Mapped[str] = mapped_column(Unicode(20))
    nombre: Mapped[str | None] = mapped_column(Unicode(300))
    campo: Mapped[str | None] = mapped_column(Unicode(20))
    importe: Mapped[Decimal | None] = mapped_column(IMPORTE)
    excluir: Mapped[bool] = mapped_column(Boolean, default=False)
    tipo_tercero: Mapped[str | None] = mapped_column(Unicode(2))
    tipo_operacion: Mapped[str | None] = mapped_column(Unicode(2))
    motivo: Mapped[str] = mapped_column(Unicode(1000))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_por: Mapped[int] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class DiotCorrida(Base):
    """Un «Procesar»: los 8 pasos del proceso de Fiscal con su bitácora. Se guardan todas."""
    __tablename__ = "diot_corrida"
    __table_args__ = {"schema": ESQUEMA}

    corrida_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey(PERIODO))
    estado: Mapped[str] = mapped_column(Unicode(20))  # en_curso / terminada / detenida / fallida
    resultado: Mapped[str | None] = mapped_column(Unicode(500))
    iniciada_por: Mapped[int] = mapped_column(ForeignKey(USUARIO))
    iniciada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime)
    criterios: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: versión de cada criterio y layout usados


class DiotCorridaPaso(Base):
    __tablename__ = "diot_corrida_paso"
    __table_args__ = {"schema": ESQUEMA}

    paso_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    corrida_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.diot_corrida.corrida_id"))
    orden: Mapped[int] = mapped_column(Integer)
    nombre: Mapped[str] = mapped_column(Unicode(100))
    estado: Mapped[str] = mapped_column(Unicode(20))  # pendiente / en_curso / ok / aviso / detenido / no_ejecutado
    resumen: Mapped[str | None] = mapped_column(Unicode(1000))
    inicio_en: Mapped[datetime | None] = mapped_column(DateTime)
    fin_en: Mapped[datetime | None] = mapped_column(DateTime)


class DiotCorridaLog(Base):
    __tablename__ = "diot_corrida_log"
    __table_args__ = {"schema": ESQUEMA}

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    corrida_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.diot_corrida.corrida_id"))
    orden_paso: Mapped[int] = mapped_column(Integer)
    momento: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    nivel: Mapped[str] = mapped_column(Unicode(10))  # info / ok / aviso / error
    mensaje: Mapped[str] = mapped_column(Unicode(1000))
    detalle: Mapped[str | None] = mapped_column(UnicodeText)  # JSON


class DiotRevision(Base):
    """Una marca de quien revisa: proveedor de la muestra revisado, o motivo de una diferencia contra lo presentado.
    `huella` guarda lo que se vio; si al reprocesar cambia, la marca ya no cuenta."""
    __tablename__ = "diot_revision"
    __table_args__ = {"schema": ESQUEMA}

    revision_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey(PERIODO))
    tipo: Mapped[str] = mapped_column(Unicode(20))  # muestra / diferencia
    clave: Mapped[str] = mapped_column(Unicode(40))  # RFC
    motivo: Mapped[str | None] = mapped_column(Unicode(30))
    nota: Mapped[str | None] = mapped_column(Unicode(1000))
    huella: Mapped[str | None] = mapped_column(Unicode(64))
    usuario_id: Mapped[int] = mapped_column(ForeignKey(USUARIO))
    momento: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class DiotFirma(Base):
    """Quién revisó los cuadres y quién de Fiscal dio el visto bueno, sobre qué TXT (huella)."""
    __tablename__ = "diot_firma"
    __table_args__ = {"schema": ESQUEMA}

    firma_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey(PERIODO))
    tipo: Mapped[str] = mapped_column(Unicode(20))  # revision / fiscal
    usuario_id: Mapped[int] = mapped_column(ForeignKey(USUARIO))
    momento: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    nota: Mapped[str | None] = mapped_column(Unicode(1000))
    huella_txt: Mapped[str] = mapped_column(Unicode(64))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------- Base de conocimiento fiscal (2026-10-30)

class FiscalDocumento(Base):
    """Documento de soporte de los criterios: matriz de tasas, reglas de Fiscal, layout del SAT. Con versión y huella."""
    __tablename__ = "fiscal_documento"
    __table_args__ = {"schema": ESQUEMA}

    documento_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(Unicode(300))
    tipo: Mapped[str] = mapped_column(Unicode(30))  # matriz / reglas / layout / cuestionario / aviso / otro
    version: Mapped[str | None] = mapped_column(Unicode(50))
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    notas: Mapped[str | None] = mapped_column(Unicode(1000))
    nombre_archivo: Mapped[str | None] = mapped_column(Unicode(260))
    contenido: Mapped[bytes | None] = mapped_column(LargeBinary)
    tamano: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(Unicode(64))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    reemplaza_a: Mapped[int | None] = mapped_column(Integer)  # versión anterior del mismo documento
    cargado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    cargado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class FiscalCatalogo(Base):
    """Catálogos del SAT con vigencia: tipos de tercero, tipos de operación y el layout del TXT (campo -> qué lleva)."""
    __tablename__ = "fiscal_catalogo"
    __table_args__ = {"schema": ESQUEMA}

    catalogo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalogo: Mapped[str] = mapped_column(Unicode(20))  # tipo_tercero / tipo_operacion / layout
    clave: Mapped[str] = mapped_column(Unicode(20))  # «04», «85»; en layout el número de campo o «campos»/«efectos»
    descripcion: Mapped[str] = mapped_column(Unicode(500))
    valor: Mapped[str | None] = mapped_column(Unicode(50))  # layout: qué lleva el campo
    vigente_desde: Mapped[date] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    documento_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.fiscal_documento.documento_id"))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class FiscalCriterio(Base):
    """Una versión de un criterio fiscal. Cada cambio es una versión nueva; la vigente en un periodo es la última
    versión con vigencia que lo cubre. Los del sistema los sabe aplicar el motor; los propios los define Fiscal."""
    __tablename__ = "fiscal_criterio"
    __table_args__ = {"schema": ESQUEMA}

    criterio_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clave: Mapped[str] = mapped_column(Unicode(40))
    version: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(Unicode(10))  # sistema / propio
    categoria: Mapped[str] = mapped_column(Unicode(20))
    titulo: Mapped[str] = mapped_column(Unicode(200))
    descripcion: Mapped[str] = mapped_column(Unicode(2000))
    parametros: Mapped[str | None] = mapped_column(UnicodeText)  # JSON (sistema)
    condicion: Mapped[str | None] = mapped_column(UnicodeText)  # JSON (propio): fuente, campo, operador, valor
    accion: Mapped[str | None] = mapped_column(UnicodeText)  # JSON (propio): accion, tipo_operacion
    contradiccion: Mapped[str | None] = mapped_column(Unicode(2000))
    documento_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.fiscal_documento.documento_id"))
    referencia: Mapped[str | None] = mapped_column(Unicode(500))  # párrafo o hoja del documento
    evidencia: Mapped[str | None] = mapped_column(Unicode(1000))
    prioridad: Mapped[int] = mapped_column(Integer, default=100)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.diot_empresa.empresa_id"))  # vacío = todas
    vigente_desde: Mapped[date] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(Unicode(20))  # borrador / pendiente / aprobado / retirado
    aprobado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    aprobado_en: Mapped[datetime | None] = mapped_column(DateTime)
    nota_aprobacion: Mapped[str | None] = mapped_column(Unicode(1000))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class FiscalCriterioCambio(Base):
    """Historial: quién creó, cambió, aprobó, regresó o retiró cada criterio, con motivo."""
    __tablename__ = "fiscal_criterio_cambio"
    __table_args__ = {"schema": ESQUEMA}

    cambio_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clave: Mapped[str] = mapped_column(Unicode(40))
    version: Mapped[int] = mapped_column(Integer)
    accion: Mapped[str] = mapped_column(Unicode(20))  # creado / editado / enviado / aprobado / regresado / retirado
    motivo: Mapped[str | None] = mapped_column(Unicode(1000))
    detalle: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: qué cambió
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    momento: Mapped[datetime] = mapped_column(DateTime, default=ahora)
