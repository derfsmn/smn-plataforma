"""Radar de productos (esquema compras): ideas que captura Compras y la evaluación con semáforo de cada producto nuevo.

Plan del radar de productos (2026-10-26). Una evaluación califica una propuesta de proveedor o una idea de Compras;
recalcular crea otra y deja la anterior como no vigente, así queda la historia.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nucleo.modelos import Base, ahora

ESQUEMA = "compras"
USUARIO = "nucleo.usuario.usuario_id"
EVALUACION = f"{ESQUEMA}.producto_evaluacion.evaluacion_id"


class ProductoIdea(Base):
    """Producto que Compras captura con el cuestionario corto (fotos y lo que se sepa), con o sin proveedor."""
    __tablename__ = "producto_idea"
    __table_args__ = {"schema": ESQUEMA}

    idea_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(300))
    marca: Mapped[str | None] = mapped_column(Unicode(120))
    descripcion: Mapped[str | None] = mapped_column(Unicode(2000))
    departamento: Mapped[str | None] = mapped_column(Unicode(300))
    ingrediente: Mapped[str | None] = mapped_column(Unicode(200))
    forma: Mapped[str | None] = mapped_column(Unicode(60))
    contenido: Mapped[str | None] = mapped_column(Unicode(60))  # texto libre: «60 cápsulas», «500 g»
    precio_visto: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))  # con impuestos, donde lo vio
    donde_se_vio: Mapped[str | None] = mapped_column(Unicode(300))
    costo_estimado: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))  # sin IVA, si alguien lo sabe
    # Captura corta con proveedor (migración 0041): su clave en Intelisis, o el nombre si es nuevo
    proveedor_intelisis: Mapped[str | None] = mapped_column(Unicode(10))
    proveedor_nuevo: Mapped[str | None] = mapped_column(Unicode(200))
    estado: Mapped[str] = mapped_column(Unicode(20), default="nueva")  # nueva / buscar_proveedor / vigilar / descartada
    creada_por: Mapped[int] = mapped_column(ForeignKey(USUARIO))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)

    fotos: Mapped[list["ProductoIdeaFoto"]] = relationship(cascade="all, delete-orphan")


class ProductoIdeaFoto(Base):
    __tablename__ = "producto_idea_foto"
    __table_args__ = {"schema": ESQUEMA}

    idea_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.producto_idea.idea_id"), primary_key=True)
    archivo_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("nucleo.archivo.archivo_id"), primary_key=True)


class ProductoEvaluacion(Base):
    __tablename__ = "producto_evaluacion"
    __table_args__ = {"schema": ESQUEMA}

    evaluacion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    propuesta_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.propuesta.propuesta_id"))
    idea_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.producto_idea.idea_id"))
    estado: Mapped[str] = mapped_column(Unicode(20), default="en_curso")  # en_curso / lista / fallida
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    departamento: Mapped[str | None] = mapped_column(Unicode(300))
    rama: Mapped[str | None] = mapped_column(Unicode(300))
    subcategoria: Mapped[str | None] = mapped_column(Unicode(300))
    segmento: Mapped[str | None] = mapped_column(Unicode(300))
    clasificacion_origen: Mapped[str | None] = mapped_column(Unicode(20))  # ia / compras / parecidos / sin_clasificar
    puntaje: Mapped[int | None] = mapped_column(Integer)  # 0 a 100
    color: Mapped[str | None] = mapped_column(Unicode(10))  # el que dio el radar
    confianza: Mapped[str | None] = mapped_column(Unicode(10))  # alta / media / baja
    pesos_origen: Mapped[str | None] = mapped_column(Unicode(20))  # compras / iguales
    modelo: Mapped[str | None] = mapped_column(Unicode(20))  # con_proveedor / sin_proveedor (migración 0040)
    explicacion: Mapped[str | None] = mapped_column(UnicodeText)
    explicacion_ia: Mapped[bool] = mapped_column(Boolean, default=False)
    mercado: Mapped[str | None] = mapped_column(UnicodeText)  # JSON de mercado_producto.Mercado
    politicas: Mapped[str | None] = mapped_column(UnicodeText)  # JSON de politicas_producto.Revision
    color_final: Mapped[str | None] = mapped_column(Unicode(10))  # el que puso Compras, con motivo
    motivo_cambio: Mapped[str | None] = mapped_column(Unicode(1000))
    cambiado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    cambiado_en: Mapped[datetime | None] = mapped_column(DateTime)
    avance: Mapped[str | None] = mapped_column(Unicode(200))  # en qué paso va mientras está en curso
    error: Mapped[str | None] = mapped_column(Unicode(1000))
    disparada_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime)

    factores: Mapped[list["EvaluacionFactor"]] = relationship(cascade="all, delete-orphan")
    comparables: Mapped[list["EvaluacionComparable"]] = relationship(order_by="EvaluacionComparable.rango",
                                                                     cascade="all, delete-orphan")


class EvaluacionFactor(Base):
    __tablename__ = "producto_evaluacion_factor"
    __table_args__ = {"schema": ESQUEMA}

    evaluacion_id: Mapped[int] = mapped_column(ForeignKey(EVALUACION), primary_key=True)
    factor: Mapped[str] = mapped_column(Unicode(20), primary_key=True)  # los 6 de la base de conocimiento
    peso: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    puntaje: Mapped[int | None] = mapped_column(Integer)  # vacío = sin datos
    valor: Mapped[str | None] = mapped_column(Unicode(300))  # el dato crudo, p. ej. «margen 38 %»
    detalle: Mapped[str | None] = mapped_column(Unicode(1000))  # de dónde salió y con qué regla
    provisional: Mapped[bool] = mapped_column(Boolean, default=False)  # regla provisional, no de Compras
    calculo: Mapped[str | None] = mapped_column(Unicode(1000))  # cómo se llegó a la calificación, con sus números
    mejora: Mapped[str | None] = mapped_column(Unicode(600))  # qué tendría que pasar para que suba


class EvaluacionComparable(Base):
    __tablename__ = "producto_evaluacion_comparable"
    __table_args__ = {"schema": ESQUEMA}

    evaluacion_id: Mapped[int] = mapped_column(ForeignKey(EVALUACION), primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("datos.producto.producto_id"), primary_key=True)
    rango: Mapped[int] = mapped_column(Integer)
    similitud: Mapped[Decimal] = mapped_column(Numeric(5, 3))
    origen: Mapped[str] = mapped_column(Unicode(10))  # sistema / compras


class OportunidadCorrida(Base):
    """Una vez que alguien picó «Buscar oportunidades»: qué fuentes se juntaron y qué salió."""
    __tablename__ = "oportunidad_corrida"
    __table_args__ = {"schema": ESQUEMA}

    corrida_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estado: Mapped[str] = mapped_column(Unicode(20), default="en_curso")  # en_curso / lista / fallida
    paso: Mapped[str | None] = mapped_column(Unicode(300))  # en qué va, para la pantalla
    competencia: Mapped[bool] = mapped_column(Boolean, default=False)  # se buscó en Google Shopping
    fuentes: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: lo que se le dio a la IA, con sus claves
    notas: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: lista de avisos
    con_ia: Mapped[bool] = mapped_column(Boolean, default=False)
    costo_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))  # DataForSEO
    error: Mapped[str | None] = mapped_column(Unicode(1000))
    disparada_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime)

    oportunidades: Mapped[list["Oportunidad"]] = relationship(order_by="Oportunidad.orden", cascade="all, delete-orphan")


class Oportunidad(Base):
    """Un producto que no tenemos y convendría buscar, con la evidencia que lo respalda."""
    __tablename__ = "oportunidad"
    __table_args__ = {"schema": ESQUEMA}

    oportunidad_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    corrida_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.oportunidad_corrida.corrida_id"))
    orden: Mapped[int] = mapped_column(Integer)
    nombre: Mapped[str] = mapped_column(Unicode(300))
    marca: Mapped[str | None] = mapped_column(Unicode(120))
    departamento: Mapped[str | None] = mapped_column(Unicode(300))
    subcategoria: Mapped[str | None] = mapped_column(Unicode(300))
    forma: Mapped[str | None] = mapped_column(Unicode(60))
    por_que: Mapped[str] = mapped_column(Unicode(1000))
    prioridad: Mapped[str] = mapped_column(Unicode(10))  # alta / media / baja
    evidencia: Mapped[str] = mapped_column(UnicodeText)  # JSON: [{clave, fuente, texto}]
    precio_visto: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))  # mediana de la competencia, con impuestos
    donde_se_vio: Mapped[str | None] = mapped_column(Unicode(300))
    imagen: Mapped[str | None] = mapped_column(Unicode(800))  # liga de la foto (página del producto, Google o nuestra)
    imagen_de: Mapped[str | None] = mapped_column(Unicode(300))  # de dónde salió la foto
    estado: Mapped[str] = mapped_column(Unicode(20), default="nueva")  # nueva / evaluada / descartada
    idea_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.producto_idea.idea_id"))
    actualizada_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    actualizada_en: Mapped[datetime | None] = mapped_column(DateTime)
