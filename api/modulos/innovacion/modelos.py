"""Innovación y desarrollo Vidanat (TD005), esquema innovacion.

Fuente: docs/modelos/innovacion_vidanat_v0.dbml y el plan v2 aprobado por Diego el 2026-11-22.

Reglas de diseño que no se rompen:
- Las versiones (fuente, ficha, fórmula, regla) no se editan: guardar crea la siguiente.
- Una evaluación y sus resultados no se editan ni se borran.
- La fórmula técnica se guarda cifrada (Fernet) y solo la ve quien tiene permiso y es del equipo del folio.
- Cada sección (fragmento) hereda la clasificación y el folio de su fuente para filtrar antes de buscar.
- El texto leído de las fuentes, el texto pegado, las descripciones de imágenes y las respuestas de la consulta se guardan
  cifrados en la base (TextoProtegido): quien entra directo a la base o a un respaldo no lee fórmulas (seguridad, A3).
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, Unicode,
                        UnicodeText, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from core import cifrado
from nucleo.modelos import Base, ahora

PREFIJO_CIFRADO = "cif1:"
ILEGIBLE = "[Texto cifrado con otra llave: no se puede leer. Revisa CLAVE_CIFRADO.]"


class TextoProtegido(TypeDecorator):
    """Texto que se guarda cifrado (Fernet, llave de Innovación) y se lee en claro. Lo que ya estaba guardado sin cifrar
    se sigue leyendo; scripts/rotar_llave.py lo cifra. No sirve para buscar con SQL (WHERE/LIKE): se busca en Python."""
    impl = UnicodeText
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value.startswith(PREFIJO_CIFRADO):
            return value
        return PREFIJO_CIFRADO + cifrado.fernet(cifrado.INNOVACION).encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        return abrir(value)


def abrir(value: str | None) -> str | None:
    if value is None or not value.startswith(PREFIJO_CIFRADO):
        return value
    try:
        return cifrado.fernet(cifrado.INNOVACION).decrypt(value[len(PREFIJO_CIFRADO):].encode()).decode()
    except cifrado.InvalidToken:
        return ILEGIBLE

ESQUEMA = "innovacion"
USUARIO = "nucleo.usuario.usuario_id"
E = ESQUEMA

ETAPAS = ("idea", "prefiltro", "investigacion", "filtro", "desarrollo", "salida_comercial", "validacion")
TIPOS_RECURSO = ("articulo", "ensayo_clinico", "revision", "guia_regulatoria", "norma", "ficha_tecnica", "certificado",
                 "patente", "libro", "presentacion", "imagen", "prueba_interna", "nota", "informe_ia", "otro")
CLASIFICACIONES = ("general", "restringido", "formula")
SEVERIDADES = ("bloqueante", "mayor", "menor")
RESULTADOS = ("cumple", "incumple", "pendiente", "no_aplica")


class Ingrediente(Base):
    __tablename__ = "ingrediente"
    __table_args__ = {"schema": E}

    ingrediente_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(200), unique=True)  # nombre canónico
    tipo: Mapped[str] = mapped_column(Unicode(20), default="otro")  # mineral / vitamina / botanico / aminoacido / probiotico / otro
    forma_quimica: Mapped[str | None] = mapped_column(Unicode(200))
    sinonimos: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: lista de textos
    factor_ui_ug: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))  # µg por cada UI; solo con fuente revisada
    factor_version_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.recurso_version.version_id", use_alter=True,
                                                                     name="fk_innovacion_ingrediente_factor"))
    estado: Mapped[str] = mapped_column(Unicode(20), default="activo")  # activo / retirado
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Expediente(Base):
    __tablename__ = "expediente"
    __table_args__ = {"schema": E}

    expediente_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    folio: Mapped[str] = mapped_column(Unicode(20), unique=True)  # VID-AAAA-NNNN
    nombre: Mapped[str] = mapped_column(Unicode(200))
    descripcion: Mapped[str | None] = mapped_column(UnicodeText)
    jurisdiccion: Mapped[str] = mapped_column(Unicode(10), default="MX")
    categoria_sanitaria: Mapped[str | None] = mapped_column(Unicode(60))
    categoria_comercial: Mapped[str | None] = mapped_column(Unicode(120))
    presentacion: Mapped[str | None] = mapped_column(Unicode(60))
    etapa: Mapped[str] = mapped_column(Unicode(20), default="investigacion")
    estado: Mapped[str] = mapped_column(Unicode(20), default="activo")  # activo / en_espera / cerrado
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)

    equipo: Mapped[list["ExpedienteEquipo"]] = relationship(cascade="all, delete-orphan")


class ExpedienteEquipo(Base):
    __tablename__ = "expediente_equipo"
    __table_args__ = {"schema": E}

    expediente_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey(USUARIO), primary_key=True)
    papel: Mapped[str | None] = mapped_column(Unicode(60))
    agregado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Recurso(Base):
    __tablename__ = "recurso"
    __table_args__ = {"schema": E}

    recurso_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(Unicode(500))
    tipo: Mapped[str] = mapped_column(Unicode(30))
    clasificacion: Mapped[str] = mapped_column(Unicode(20), default="general")
    expediente_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))  # dueño si es restringido
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    estado: Mapped[str] = mapped_column(Unicode(20), default="activo")  # activo / retirado
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    versiones: Mapped[list["RecursoVersion"]] = relationship(back_populates="recurso", order_by="RecursoVersion.numero")


class RecursoVersion(Base):
    __tablename__ = "recurso_version"
    __table_args__ = (UniqueConstraint("recurso_id", "numero", name="uq_innovacion_recurso_version"), {"schema": E})

    version_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recurso_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.recurso.recurso_id"))
    numero: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(Unicode(20), default="pendiente")  # pendiente / revisado / sustituido
    url: Mapped[str | None] = mapped_column(Unicode(1000))
    doi: Mapped[str | None] = mapped_column(Unicode(200))
    pmid: Mapped[str | None] = mapped_column(Unicode(20))
    autores: Mapped[str | None] = mapped_column(Unicode(1000))
    anio: Mapped[int | None] = mapped_column(Integer)
    publicado_en: Mapped[str | None] = mapped_column(Unicode(300))  # revista, editorial o emisor
    idioma: Mapped[str | None] = mapped_column(Unicode(10))
    resumen: Mapped[str | None] = mapped_column(UnicodeText)
    texto: Mapped[str | None] = mapped_column(TextoProtegido)  # texto pegado a mano (si no hay archivo)
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    datos: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: población, cantidad, duración, diseño…
    sugerencias: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: datos propuestos por la IA local
    procesado: Mapped[str] = mapped_column(Unicode(20), default="pendiente")  # pendiente / listo / error
    respalda: Mapped[str | None] = mapped_column(UnicodeText)
    limites: Mapped[str | None] = mapped_column(UnicodeText)
    corresponde: Mapped[str | None] = mapped_column(Unicode(20))  # ingrediente / producto / ambos
    tipo_revision: Mapped[str | None] = mapped_column(Unicode(20))  # cientifica / regulatoria / calidad
    revisado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    revisado_en: Mapped[datetime | None] = mapped_column(DateTime)
    interpretacion: Mapped[str | None] = mapped_column(UnicodeText)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    recurso: Mapped[Recurso] = relationship(back_populates="versiones")
    archivos: Mapped[list["RecursoArchivo"]] = relationship(cascade="all, delete-orphan")


class RecursoArchivo(Base):
    __tablename__ = "recurso_archivo"
    __table_args__ = {"schema": E}

    version_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.recurso_version.version_id"), primary_key=True)
    archivo_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nucleo.archivo.archivo_id"), primary_key=True)
    rol: Mapped[str] = mapped_column(Unicode(20), default="principal")  # principal / anexo / imagen
    cifrado: Mapped[bool] = mapped_column(Boolean, default=False)
    descripcion: Mapped[str | None] = mapped_column(TextoProtegido)  # de una imagen; la sugiere la IA y la confirma una persona
    descripcion_confirmada: Mapped[bool] = mapped_column(Boolean, default=False)


class Seccion(Base):
    __tablename__ = "fragmento"
    __table_args__ = {"schema": E}

    fragmento_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.recurso_version.version_id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer)
    pagina: Mapped[int | None] = mapped_column(Integer)
    seccion: Mapped[str | None] = mapped_column(Unicode(400))
    texto: Mapped[str] = mapped_column(TextoProtegido)
    origen: Mapped[str] = mapped_column(Unicode(20), default="texto")  # texto / ocr / imagen / captura
    vector: Mapped[bytes | None] = mapped_column(LargeBinary)
    modelo_vector: Mapped[str | None] = mapped_column(Unicode(80))


class Vinculo(Base):
    __tablename__ = "vinculo"
    __table_args__ = {"schema": E}

    vinculo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.recurso_version.version_id"))
    tipo: Mapped[str] = mapped_column(Unicode(20))  # ingrediente / categoria / expediente
    ingrediente_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.ingrediente.ingrediente_id"))
    categoria: Mapped[str | None] = mapped_column(Unicode(120))
    expediente_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Trabajo(Base):
    """Trabajo en segundo plano. (tipo, objeto_id) no se repite mientras esté pendiente o corriendo."""
    __tablename__ = "trabajo"
    __table_args__ = {"schema": E}

    trabajo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(Unicode(20))  # leer / huellas / sugerir / describir / investigar / evaluar
    objeto_id: Mapped[int] = mapped_column(Integer)  # version_id, investigacion_id o expediente_id según el tipo
    estado: Mapped[str] = mapped_column(Unicode(20), default="pendiente")  # pendiente / corriendo / listo / error
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    siguiente_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    detalle: Mapped[str | None] = mapped_column(UnicodeText)  # JSON con parámetros
    error: Mapped[str | None] = mapped_column(Unicode(1000))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    iniciado_en: Mapped[datetime | None] = mapped_column(DateTime)
    terminado_en: Mapped[datetime | None] = mapped_column(DateTime)


class FormulaVersion(Base):
    __tablename__ = "formula_version"
    __table_args__ = (UniqueConstraint("expediente_id", "numero", name="uq_innovacion_formula_version"), {"schema": E})

    formula_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    numero: Mapped[int] = mapped_column(Integer)
    contenido: Mapped[bytes] = mapped_column(LargeBinary)  # JSON cifrado con Fernet
    nota: Mapped[str | None] = mapped_column(Unicode(1000))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class FichaVersion(Base):
    __tablename__ = "ficha_version"
    __table_args__ = (UniqueConstraint("expediente_id", "numero", name="uq_innovacion_ficha_version"), {"schema": E})

    ficha_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    numero: Mapped[int] = mapped_column(Integer)
    datos: Mapped[str] = mapped_column(UnicodeText)  # JSON: presentación, porción, declaraciones, población…
    formula_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.formula_version.formula_id"))
    nota: Mapped[str | None] = mapped_column(Unicode(1000))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    ingredientes: Mapped[list["FichaIngrediente"]] = relationship(order_by="FichaIngrediente.orden",
                                                                  cascade="all, delete-orphan")


class FichaIngrediente(Base):
    __tablename__ = "ficha_ingrediente"
    __table_args__ = {"schema": E}

    renglon_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ficha_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.ficha_version.ficha_id"))
    orden: Mapped[int] = mapped_column(Integer)
    ingrediente_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.ingrediente.ingrediente_id"))
    nombre: Mapped[str] = mapped_column(Unicode(200))
    tipo: Mapped[str | None] = mapped_column(Unicode(20))
    forma: Mapped[str | None] = mapped_column(Unicode(200))
    en_compuesto: Mapped[bool] = mapped_column(Boolean, default=False)  # viene como sal o compuesto
    cantidad_compuesto: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    unidad_compuesto: Mapped[str | None] = mapped_column(Unicode(20))
    cantidad_activa: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    unidad_activa: Mapped[str | None] = mapped_column(Unicode(20))
    fraccion_activa: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))  # de la ficha técnica (0–1)
    fuente_version_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.recurso_version.version_id"))
    nota: Mapped[str | None] = mapped_column(Unicode(500))


class Evidencia(Base):
    __tablename__ = "evidencia"
    __table_args__ = {"schema": E}

    evidencia_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    version_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.recurso_version.version_id"))
    fragmento_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.fragmento.fragmento_id"))
    pagina: Mapped[int | None] = mapped_column(Integer)
    seccion: Mapped[str | None] = mapped_column(Unicode(400))
    respalda: Mapped[str] = mapped_column(Unicode(1000))
    limites: Mapped[str | None] = mapped_column(Unicode(1000))
    aplica: Mapped[str] = mapped_column(Unicode(20), default="por_dictaminar")  # si / parcial / no / por_dictaminar
    sentido: Mapped[str] = mapped_column(Unicode(20), default="a_favor")  # a_favor / contradictoria
    retirada: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Comparable(Base):
    __tablename__ = "comparable"
    __table_args__ = {"schema": E}

    comparable_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    origen: Mapped[str] = mapped_column(Unicode(20), default="manual")  # manual / catalogo / radar
    producto: Mapped[str] = mapped_column(Unicode(300))
    marca: Mapped[str | None] = mapped_column(Unicode(120))
    presentacion: Mapped[str | None] = mapped_column(Unicode(120))
    precio: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sku: Mapped[str | None] = mapped_column(Unicode(40))
    url: Mapped[str | None] = mapped_column(Unicode(1000))
    fuente: Mapped[str | None] = mapped_column(Unicode(300))
    nota: Mapped[str | None] = mapped_column(Unicode(1000))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Escenario(Base):
    __tablename__ = "escenario"
    __table_args__ = {"schema": E}

    escenario_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    nombre: Mapped[str] = mapped_column(Unicode(120))
    costo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    precio: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    supuestos: Mapped[str | None] = mapped_column(UnicodeText)
    confianza: Mapped[str | None] = mapped_column(Unicode(20))  # alta / media / baja
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Pendiente(Base):
    __tablename__ = "pendiente"
    __table_args__ = {"schema": E}

    pendiente_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    descripcion: Mapped[str] = mapped_column(Unicode(1000))
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    fecha_limite: Mapped[date | None] = mapped_column(Date)
    determinante: Mapped[bool] = mapped_column(Boolean, default=False)
    estado: Mapped[str] = mapped_column(Unicode(20), default="abierto")  # abierto / cerrado
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    cerrado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime)


class Regla(Base):
    __tablename__ = "regla"
    __table_args__ = {"schema": E}

    regla_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(Unicode(30), unique=True)  # R-ÁREA-NNN
    area: Mapped[str] = mapped_column(Unicode(20))  # REG / COMP / EVI / DOC / BOT / CAL…
    nombre: Mapped[str] = mapped_column(Unicode(300))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    versiones: Mapped[list["ReglaVersion"]] = relationship(back_populates="regla", foreign_keys="ReglaVersion.regla_id", order_by="ReglaVersion.numero")


class ReglaVersion(Base):
    __tablename__ = "regla_version"
    __table_args__ = (UniqueConstraint("regla_id", "numero", name="uq_innovacion_regla_version"), {"schema": E})

    regla_version_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    regla_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.regla.regla_id"))
    numero: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(Unicode(20), default="borrador")  # borrador / en_revision / publicada / sustituida / retirada
    proposito: Mapped[str] = mapped_column(Unicode(1000))
    modo: Mapped[str] = mapped_column(Unicode(20), default="automatica")  # automatica / manual / asistida
    alcance: Mapped[str | None] = mapped_column(UnicodeText)  # JSON
    condicion: Mapped[str | None] = mapped_column(UnicodeText)  # JSON (solo automáticas)
    severidad: Mapped[str] = mapped_column(Unicode(20), default="mayor")
    si_falta: Mapped[str] = mapped_column(Unicode(20), default="pendiente")  # pendiente / incumple
    admite_excepcion: Mapped[bool] = mapped_column(Boolean, default=False)
    exige_fuente_vigente: Mapped[bool] = mapped_column(Boolean, default=False)
    sustituye_a: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.regla.regla_id"))
    fuente_version_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.recurso_version.version_id"))
    fuente_ubicacion: Mapped[str | None] = mapped_column(Unicode(300))
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    rol_revisor: Mapped[str | None] = mapped_column(Unicode(60))  # para reglas manuales
    plazo_dias: Mapped[int] = mapped_column(Integer, default=5)
    campos_relevantes: Mapped[str | None] = mapped_column(Unicode(1000))  # JSON; si cambian, el dictamen no se arrastra
    autor_id: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime)
    aprobador_id: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime)
    retirado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    retirado_en: Mapped[datetime | None] = mapped_column(DateTime)
    motivo_retiro: Mapped[str | None] = mapped_column(Unicode(1000))

    regla: Mapped[Regla] = relationship(back_populates="versiones", foreign_keys=[regla_id])


class Evaluacion(Base):
    """Corrida del motor de reglas. No se edita."""
    __tablename__ = "evaluacion"
    __table_args__ = (UniqueConstraint("expediente_id", "numero", name="uq_innovacion_evaluacion"), {"schema": E})

    evaluacion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    numero: Mapped[int] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(Unicode(20))  # ficha / formula / regla / manual
    regla_version_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.regla_version.regla_version_id"))
    ficha_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.ficha_version.ficha_id"))
    formula_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.formula_version.formula_id"))
    etapa: Mapped[str] = mapped_column(Unicode(20))
    motor: Mapped[str] = mapped_column(Unicode(20))
    resumen: Mapped[str] = mapped_column(Unicode(1000))  # JSON con conteos
    creada_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    resultados: Mapped[list["EvaluacionResultado"]] = relationship(order_by="EvaluacionResultado.resultado_id")


class EvaluacionResultado(Base):
    __tablename__ = "evaluacion_resultado"
    __table_args__ = (UniqueConstraint("evaluacion_id", "regla_version_id", name="uq_innovacion_resultado"),
                      {"schema": E})

    resultado_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evaluacion_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.evaluacion.evaluacion_id"))
    regla_version_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.regla_version.regla_version_id"))
    resultado: Mapped[str] = mapped_column(Unicode(20))
    severidad: Mapped[str] = mapped_column(Unicode(20))
    motivo: Mapped[str] = mapped_column(Unicode(1000))
    datos_usados: Mapped[str | None] = mapped_column(UnicodeText)  # JSON; los campos de fórmula se enmascaran al leer
    faltantes: Mapped[str | None] = mapped_column(Unicode(2000))  # JSON
    aviso_fuente: Mapped[str | None] = mapped_column(Unicode(300))


class Revision(Base):
    """Revisión manual (dictamen) de una regla manual o asistida."""
    __tablename__ = "revision"
    __table_args__ = {"schema": E}

    revision_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    resultado_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.evaluacion_resultado.resultado_id"))
    regla_version_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.regla_version.regla_version_id"))
    ficha_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.ficha_version.ficha_id"))
    rol: Mapped[str | None] = mapped_column(Unicode(60))
    estado: Mapped[str] = mapped_column(Unicode(20), default="asignada")  # asignada / dictaminada / sustituida
    dictamen: Mapped[str | None] = mapped_column(Unicode(20))  # cumple / incumple / no_aplica
    motivo: Mapped[str | None] = mapped_column(UnicodeText)
    respaldo: Mapped[str | None] = mapped_column(Unicode(1000))  # JSON: ids de evidencia
    sugerencia_ia: Mapped[str | None] = mapped_column(UnicodeText)
    asignada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    vence_en: Mapped[datetime | None] = mapped_column(DateTime)
    dictaminada_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    dictaminada_en: Mapped[datetime | None] = mapped_column(DateTime)


class Excepcion(Base):
    __tablename__ = "excepcion"
    __table_args__ = {"schema": E}

    excepcion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    resultado_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.evaluacion_resultado.resultado_id"))
    regla_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.regla.regla_id"))
    justificacion: Mapped[str] = mapped_column(UnicodeText)
    estado: Mapped[str] = mapped_column(Unicode(20), default="solicitada")  # solicitada / aprobada / rechazada
    vence_en: Mapped[date] = mapped_column(Date)
    solicitada_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    solicitada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    resuelta_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    resuelta_en: Mapped[datetime | None] = mapped_column(DateTime)
    nota: Mapped[str | None] = mapped_column(Unicode(1000))


class Decision(Base):
    __tablename__ = "decision"
    __table_args__ = {"schema": E}

    decision_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    etapa: Mapped[str] = mapped_column(Unicode(20))
    evaluacion_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.evaluacion.evaluacion_id"))
    resultado: Mapped[str] = mapped_column(Unicode(20))  # avanzar / ajustar / espera / cerrar
    motivo: Mapped[str] = mapped_column(UnicodeText)
    condiciones: Mapped[str | None] = mapped_column(UnicodeText)
    congelado: Mapped[str] = mapped_column(UnicodeText)  # JSON: versiones de ficha, fórmula, evidencia y excepciones
    decidida_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    decidida_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Consulta(Base):
    __tablename__ = "consulta"
    __table_args__ = {"schema": E}

    consulta_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    expediente_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    pregunta: Mapped[str] = mapped_column(Unicode(1000))
    respuesta: Mapped[str | None] = mapped_column(TextoProtegido)
    citas: Mapped[str | None] = mapped_column(TextoProtegido)  # JSON
    insuficiente: Mapped[bool] = mapped_column(Boolean, default=False)
    clasificacion: Mapped[str] = mapped_column(Unicode(20), default="general")  # la más alta de sus citas
    duracion_ms: Mapped[int] = mapped_column(Integer, default=0)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Investigacion(Base):
    __tablename__ = "investigacion"
    __table_args__ = {"schema": E}

    investigacion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expediente_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.expediente.expediente_id"))
    tema: Mapped[str] = mapped_column(Unicode(500))
    preguntas: Mapped[str] = mapped_column(UnicodeText)  # JSON: lista de preguntas
    terminos: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: lo único que sale a internet
    fuentes: Mapped[str] = mapped_column(Unicode(500))  # JSON: pubmed, europepmc, ctgov, openalex, oficial, web
    usar_web: Mapped[bool] = mapped_column(Boolean, default=False)
    estado: Mapped[str] = mapped_column(Unicode(20), default="propuesta")  # propuesta / corriendo / lista / error
    pasos: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: bitácora por paso
    informe: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: por pregunta, texto con citas y vacíos
    costo_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    error: Mapped[str | None] = mapped_column(Unicode(1000))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime)


class Hallazgo(Base):
    __tablename__ = "hallazgo"
    __table_args__ = {"schema": E}

    hallazgo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigacion_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.investigacion.investigacion_id"))
    origen: Mapped[str] = mapped_column(Unicode(20))  # pubmed / europepmc / ctgov / openalex / crossref / oficial / web
    identificador: Mapped[str | None] = mapped_column(Unicode(200))  # doi:… / pmid:… / nct:…
    titulo: Mapped[str] = mapped_column(Unicode(1000))
    autores: Mapped[str | None] = mapped_column(Unicode(1000))
    anio: Mapped[int | None] = mapped_column(Integer)
    publicado_en: Mapped[str | None] = mapped_column(Unicode(300))
    url: Mapped[str | None] = mapped_column(Unicode(1000))
    tipo_estudio: Mapped[str | None] = mapped_column(Unicode(40))
    resumen: Mapped[str | None] = mapped_column(UnicodeText)
    texto_abierto: Mapped[str | None] = mapped_column(UnicodeText)
    puntaje: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    seleccionado: Mapped[bool] = mapped_column(Boolean, default=False)
    extraccion: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: material, población, cantidad, duración…
    recurso_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.recurso.recurso_id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
