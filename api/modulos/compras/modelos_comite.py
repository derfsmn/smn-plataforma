"""Comité de producto nuevo (esquema compras). Fuente: docs/modelos/compras_comite_v0.dbml (migración 0040).

Cada reunión abre un ciclo: se suben productos (propuestas o ideas), se evalúan con el semáforo, Compras hace el pre-filtro
y el comité decide Aceptado, Denegado o En espera. Lo que queda en espera pasa a la siguiente reunión.
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nucleo.modelos import Base, ahora

ESQUEMA = "compras"
USUARIO = "nucleo.usuario.usuario_id"
REUNION = f"{ESQUEMA}.comite_reunion.reunion_id"
ITEM = f"{ESQUEMA}.comite_producto.item_id"


class ComiteReunion(Base):
    __tablename__ = "comite_reunion"
    __table_args__ = {"schema": ESQUEMA}

    reunion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date)
    notas: Mapped[str | None] = mapped_column(Unicode(2000))
    estado: Mapped[str] = mapped_column(Unicode(20), default="abierta")  # abierta / prefiltro / comite / cerrada
    aprendizajes: Mapped[str | None] = mapped_column(UnicodeText)
    creada_por: Mapped[int] = mapped_column(ForeignKey(USUARIO))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    prefiltro_en: Mapped[datetime | None] = mapped_column(DateTime)
    comite_en: Mapped[datetime | None] = mapped_column(DateTime)
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime)
    cerrada_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))

    productos: Mapped[list["ComiteProducto"]] = relationship(order_by="ComiteProducto.orden", cascade="all, delete-orphan")
    asistentes: Mapped[list["ComiteAsistente"]] = relationship(order_by="ComiteAsistente.asistente_id",
                                                               cascade="all, delete-orphan")


class ComiteProducto(Base):
    __tablename__ = "comite_producto"
    __table_args__ = {"schema": ESQUEMA}

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reunion_id: Mapped[int] = mapped_column(ForeignKey(REUNION))
    propuesta_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.propuesta.propuesta_id"))
    idea_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.producto_idea.idea_id"))
    origen: Mapped[str] = mapped_column(Unicode(20))  # captura / propuesta / idea / espera
    viene_de: Mapped[int | None] = mapped_column(ForeignKey(ITEM))
    orden: Mapped[int] = mapped_column(Integer)
    agregado_por: Mapped[int] = mapped_column(ForeignKey(USUARIO))
    agregado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    prefiltro: Mapped[str | None] = mapped_column(Unicode(10))  # pasa / no_pasa
    prefiltro_motivo: Mapped[str | None] = mapped_column(Unicode(1000))
    criterios: Mapped[str | None] = mapped_column(UnicodeText)  # JSON [{criterio, valor, nota}]
    prefiltro_color: Mapped[str | None] = mapped_column(Unicode(10))
    prefiltro_puntaje: Mapped[int | None] = mapped_column(Integer)
    prefiltro_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    prefiltro_en: Mapped[datetime | None] = mapped_column(DateTime)
    decision: Mapped[str | None] = mapped_column(Unicode(12))  # aceptado / denegado / en_espera
    decision_motivo: Mapped[str | None] = mapped_column(Unicode(1000))
    decision_color: Mapped[str | None] = mapped_column(Unicode(10))
    decision_puntaje: Mapped[int | None] = mapped_column(Integer)
    decision_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    decision_en: Mapped[datetime | None] = mapped_column(DateTime)

    revisiones: Mapped[list["ComiteRevision"]] = relationship(cascade="all, delete-orphan")


class ComiteRevision(Base):
    """Revisión después de aceptar: ¿hay espacio en el inventario? y después regulación."""
    __tablename__ = "comite_revision"
    __table_args__ = {"schema": ESQUEMA}

    item_id: Mapped[int] = mapped_column(ForeignKey(ITEM), primary_key=True)
    tipo: Mapped[str] = mapped_column(Unicode(20), primary_key=True)  # inventario / regulacion
    resultado: Mapped[str] = mapped_column(Unicode(20))  # pendiente / aprobada / rechazada
    nota: Mapped[str | None] = mapped_column(Unicode(1000))
    actualizada_por: Mapped[int] = mapped_column(ForeignKey(USUARIO))
    actualizada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class ComiteAsistente(Base):
    __tablename__ = "comite_asistente"
    __table_args__ = {"schema": ESQUEMA}

    asistente_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reunion_id: Mapped[int] = mapped_column(ForeignKey(REUNION))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    nombre: Mapped[str] = mapped_column(Unicode(200))
    puesto: Mapped[str | None] = mapped_column(Unicode(120))
    agregado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class ComitePeticion(Base):
    """Lo que pidió un asistente en la reunión (una muestra, un dato), para darle seguimiento."""
    __tablename__ = "comite_peticion"
    __table_args__ = {"schema": ESQUEMA}

    peticion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reunion_id: Mapped[int] = mapped_column(ForeignKey(REUNION))
    item_id: Mapped[int | None] = mapped_column(ForeignKey(ITEM))
    asistente_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.comite_asistente.asistente_id"))
    texto: Mapped[str] = mapped_column(Unicode(1000))
    estado: Mapped[str] = mapped_column(Unicode(10), default="abierta")  # abierta / atendida
    respuesta: Mapped[str | None] = mapped_column(Unicode(1000))
    atendida_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    atendida_en: Mapped[datetime | None] = mapped_column(DateTime)
    creada_por: Mapped[int] = mapped_column(ForeignKey(USUARIO))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
