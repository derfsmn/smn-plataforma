"""Base de conocimiento de métodos y procedimientos (esquema metodos).

Un documento se carga una vez por versión; al cargarlo se parte en fragmentos por sección, con su huella de significado
(vector) cuando Ollama está prendido. Solo los documentos vigentes se usan para contestar.
"""
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nucleo.modelos import Base, ahora

ESQUEMA = "metodos"
USUARIO = "nucleo.usuario.usuario_id"
DOCUMENTO = f"{ESQUEMA}.documento.documento_id"


class Documento(Base):
    __tablename__ = "documento"
    __table_args__ = {"schema": ESQUEMA}

    documento_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clave: Mapped[str | None] = mapped_column(Unicode(40))  # la del área, si tiene (p. ej. MP-COM-001)
    titulo: Mapped[str] = mapped_column(Unicode(300))
    tipo: Mapped[str] = mapped_column(Unicode(20))  # manual / politica / instructivo / formato / preguntas / otro
    area: Mapped[str] = mapped_column(Unicode(120))  # área dueña
    version: Mapped[str] = mapped_column(Unicode(30))
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    revisar_antes: Mapped[date | None] = mapped_column(Date)
    sistema: Mapped[str | None] = mapped_column(Unicode(120))  # Intelisis, plataforma...
    roles: Mapped[str | None] = mapped_column(Unicode(1000))  # JSON con códigos de rol; vacío = todos los que consultan
    permiso: Mapped[str | None] = mapped_column(Unicode(120))  # para los que vienen de otra base (Compras, Fiscal)
    estado: Mapped[str] = mapped_column(Unicode(20), default="vigente")  # borrador / vigente / reemplazado / retirado
    origen: Mapped[str] = mapped_column(Unicode(20), default="cargado")  # cargado / ia / compras / fiscal
    origen_id: Mapped[int | None] = mapped_column(Integer)
    archivo_id: Mapped[int | None] = mapped_column(ForeignKey("nucleo.archivo.archivo_id"))
    reemplaza_a: Mapped[int | None] = mapped_column(ForeignKey(DOCUMENTO))
    texto: Mapped[str | None] = mapped_column(UnicodeText)
    avisos: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: datos personales encontrados al cargar
    flujo: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: diagrama de flujo (ver flujo.py)
    cargado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    cargado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    aprobado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    aprobado_en: Mapped[datetime | None] = mapped_column(DateTime)

    fragmentos: Mapped[list["Fragmento"]] = relationship(back_populates="documento", order_by="Fragmento.orden",
                                                         cascade="all, delete-orphan", passive_deletes=True)


class Fragmento(Base):
    __tablename__ = "fragmento"
    __table_args__ = {"schema": ESQUEMA}

    fragmento_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey(DOCUMENTO, ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer)
    seccion: Mapped[str | None] = mapped_column(Unicode(400))
    pagina: Mapped[int | None] = mapped_column(Integer)
    texto: Mapped[str] = mapped_column(UnicodeText)
    vector: Mapped[bytes | None] = mapped_column(LargeBinary)  # float32 normalizado
    modelo_vector: Mapped[str | None] = mapped_column(Unicode(80))

    documento: Mapped[Documento] = relationship(back_populates="fragmentos")


class Pregunta(Base):
    __tablename__ = "pregunta"
    __table_args__ = {"schema": ESQUEMA}

    pregunta_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    texto: Mapped[str] = mapped_column(Unicode(1000))
    respuesta: Mapped[str | None] = mapped_column(UnicodeText)
    citas: Mapped[str | None] = mapped_column(UnicodeText)  # JSON
    encontrada: Mapped[bool] = mapped_column(Boolean)
    modo: Mapped[str] = mapped_column(Unicode(20))  # ia / palabras
    origen: Mapped[str | None] = mapped_column(Unicode(60))  # desde qué pantalla (p. ej. contraloria.diot)
    duracion_ms: Mapped[int] = mapped_column(Integer, default=0)
    util: Mapped[bool | None] = mapped_column(Boolean)
    comentario: Mapped[str | None] = mapped_column(Unicode(500))
    es_prueba: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Borrador(Base):
    __tablename__ = "borrador"
    __table_args__ = {"schema": ESQUEMA}

    borrador_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(Unicode(20))  # nuevo / actualizacion / formato
    documento_id: Mapped[int | None] = mapped_column(ForeignKey(DOCUMENTO))  # el manual que se actualiza
    titulo: Mapped[str] = mapped_column(Unicode(300))
    area: Mapped[str] = mapped_column(Unicode(120))
    instrucciones: Mapped[str | None] = mapped_column(UnicodeText)
    fuentes: Mapped[str | None] = mapped_column(Unicode(1000))  # JSON con documento_id usados
    archivos: Mapped[str | None] = mapped_column(Unicode(1000))  # JSON con archivo_id subidos como apoyo
    flujo: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: diagrama de flujo (ver flujo.py)
    texto: Mapped[str | None] = mapped_column(UnicodeText)
    cambios: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: cambios contra la versión anterior
    preguntas_abiertas: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: lo que la IA no supo
    estado: Mapped[str] = mapped_column(Unicode(20), default="generando")
    error: Mapped[str | None] = mapped_column(Unicode(1000))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    revisado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    revisado_en: Mapped[datetime | None] = mapped_column(DateTime)
    nota: Mapped[str | None] = mapped_column(Unicode(1000))
    publicado_id: Mapped[int | None] = mapped_column(ForeignKey(DOCUMENTO))

    documento: Mapped[Documento | None] = relationship(foreign_keys=[documento_id])


class Alerta(Base):
    __tablename__ = "alerta"
    __table_args__ = {"schema": ESQUEMA}

    alerta_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(Unicode(20))  # contradiccion
    documento_id: Mapped[int] = mapped_column(ForeignKey(DOCUMENTO))
    otro_documento_id: Mapped[int | None] = mapped_column(ForeignKey(DOCUMENTO))
    fragmento_id: Mapped[int | None] = mapped_column(Integer)
    otro_fragmento_id: Mapped[int | None] = mapped_column(Integer)
    detalle: Mapped[str] = mapped_column(Unicode(2000))
    estado: Mapped[str] = mapped_column(Unicode(20), default="abierta")
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    atendida_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    atendida_en: Mapped[datetime | None] = mapped_column(DateTime)
    nota: Mapped[str | None] = mapped_column(Unicode(1000))

    documento: Mapped[Documento] = relationship(foreign_keys=[documento_id])
    otro_documento: Mapped[Documento | None] = relationship(foreign_keys=[otro_documento_id])


class PruebaPregunta(Base):
    __tablename__ = "prueba_pregunta"
    __table_args__ = {"schema": ESQUEMA}

    prueba_pregunta_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pregunta: Mapped[str] = mapped_column(Unicode(1000))
    respuesta_esperada: Mapped[str | None] = mapped_column(Unicode(2000))
    documento_id: Mapped[int | None] = mapped_column(ForeignKey(DOCUMENTO))  # de dónde debe salir
    debe_contestar: Mapped[bool] = mapped_column(Boolean, default=True)  # False: debe decir «no está»
    area: Mapped[str | None] = mapped_column(Unicode(120))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    documento: Mapped[Documento | None] = relationship()


class PruebaCorrida(Base):
    __tablename__ = "prueba_corrida"
    __table_args__ = {"schema": ESQUEMA}

    corrida_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estado: Mapped[str] = mapped_column(Unicode(20), default="en_curso")
    modo: Mapped[str | None] = mapped_column(Unicode(20))
    total: Mapped[int] = mapped_column(Integer, default=0)
    hechas: Mapped[int] = mapped_column(Integer, default=0)
    correctas: Mapped[int] = mapped_column(Integer, default=0)
    inventadas: Mapped[int] = mapped_column(Integer, default=0)
    no_esta_bien: Mapped[int] = mapped_column(Integer, default=0)
    no_esta_total: Mapped[int] = mapped_column(Integer, default=0)
    promedio_ms: Mapped[int] = mapped_column(Integer, default=0)
    detalle: Mapped[str | None] = mapped_column(UnicodeText)  # JSON por pregunta
    error: Mapped[str | None] = mapped_column(Unicode(1000))
    corrido_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    iniciada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime)
