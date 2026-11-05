"""Tablas de las propuestas de productos nuevos que mandan los proveedores (esquema compras).

Fuente: docs/modelos/compras_propuestas_v0.dbml. Lo capturado va completo en `respuestas` (JSON); lo que se filtra
o alimenta al radar de productos sale a columnas y a propuesta_presentacion.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nucleo.modelos import Base, ahora

ESQUEMA = "compras"
N = "nucleo"


class Propuesta(Base):
    __tablename__ = "propuesta"
    __table_args__ = {"schema": ESQUEMA}

    propuesta_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    folio: Mapped[str | None] = mapped_column(Unicode(20))  # único entre los que tienen folio (índice filtrado)
    organizacion_id: Mapped[int] = mapped_column(ForeignKey(f"{N}.organizacion_externa.organizacion_id"))
    creada_por: Mapped[int] = mapped_column(ForeignKey(f"{N}.usuario.usuario_id"))
    estado: Mapped[str] = mapped_column(Unicode(20), default="borrador")
    producto: Mapped[str | None] = mapped_column(Unicode(300))
    marca: Mapped[str | None] = mapped_column(Unicode(120))
    departamento: Mapped[str | None] = mapped_column(Unicode(300))
    presentaciones: Mapped[int] = mapped_column(Integer, default=0)
    respuestas: Mapped[str] = mapped_column(UnicodeText)
    revisiones: Mapped[str | None] = mapped_column(UnicodeText)
    alertas: Mapped[int] = mapped_column(Integer, default=0)
    comentario: Mapped[str | None] = mapped_column(Unicode(1000))
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)

    filas_presentacion: Mapped[list["PropuestaPresentacion"]] = relationship(
        order_by="PropuestaPresentacion.orden", cascade="all, delete-orphan")
    adjuntos: Mapped[list["PropuestaAdjunto"]] = relationship(order_by="PropuestaAdjunto.adjunto_id",
                                                             cascade="all, delete-orphan")


class PropuestaPresentacion(Base):
    __tablename__ = "propuesta_presentacion"
    __table_args__ = {"schema": ESQUEMA}

    presentacion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    propuesta_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.propuesta.propuesta_id"))
    orden: Mapped[int] = mapped_column(Integer)
    codigo_barras: Mapped[str | None] = mapped_column(Unicode(14), index=True)
    descripcion: Mapped[str | None] = mapped_column(Unicode(180))
    forma: Mapped[str | None] = mapped_column(Unicode(60))
    contenido_neto: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unidad_medida: Mapped[str | None] = mapped_column(Unicode(20))
    costo_sin_iva: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pvp_sugerido: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    tasa_iva: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    tasa_ieps: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    margen_calculado: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    ya_en_catalogo: Mapped[bool] = mapped_column(Boolean, default=False)


class PropuestaAdjunto(Base):
    __tablename__ = "propuesta_adjunto"
    __table_args__ = {"schema": ESQUEMA}

    adjunto_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    propuesta_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.propuesta.propuesta_id"))
    archivo_id: Mapped[int] = mapped_column(BigInteger, ForeignKey(f"{N}.archivo.archivo_id"))
    tipo: Mapped[str] = mapped_column(Unicode(40))
    etiqueta: Mapped[str | None] = mapped_column(Unicode(40))
    agregado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class PropuestaEvento(Base):
    __tablename__ = "propuesta_evento"
    __table_args__ = {"schema": ESQUEMA}

    evento_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    propuesta_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.propuesta.propuesta_id"))
    estado_antes: Mapped[str | None] = mapped_column(Unicode(20))
    estado_despues: Mapped[str] = mapped_column(Unicode(20))
    comentario: Mapped[str | None] = mapped_column(Unicode(1000))
    usuario_id: Mapped[int] = mapped_column(ForeignKey(f"{N}.usuario.usuario_id"))
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
