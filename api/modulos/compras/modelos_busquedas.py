"""Búsqueda de proveedor (esquema compras, migración 0042).

Una oportunidad o idea que salió bien en el semáforo y todavía no tiene quién la surta se vuelve una búsqueda: les llega
a las personas con el permiso `compras.busquedas.atender`, una la toma, registra a quién contactó y la cierra con el
proveedor encontrado (la idea se vuelve a evaluar con él y puede subir al comité) o sin proveedor, con motivo. Pedido de
Diego, 2026-11-09.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Unicode
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nucleo.modelos import Base, ahora

ESQUEMA = "compras"
USUARIO = "nucleo.usuario.usuario_id"
BUSQUEDA = f"{ESQUEMA}.busqueda_proveedor.busqueda_id"


class BusquedaProveedor(Base):
    __tablename__ = "busqueda_proveedor"
    __table_args__ = {"schema": ESQUEMA}

    busqueda_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.producto_idea.idea_id"))
    evaluacion_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.producto_evaluacion.evaluacion_id"))
    origen: Mapped[str] = mapped_column(Unicode(12))  # automatica (salió bien en el semáforo) / compras (a mano)
    # sin_tomar / buscando / encontrado / sin_proveedor / cancelada
    estado: Mapped[str] = mapped_column(Unicode(15), default="sin_tomar")
    color: Mapped[str | None] = mapped_column(Unicode(10))  # con el que se abrió
    puntaje: Mapped[int | None] = mapped_column(Integer)
    nota: Mapped[str | None] = mapped_column(Unicode(1000))  # por qué se abrió a mano
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    tomada_en: Mapped[datetime | None] = mapped_column(DateTime)
    proveedor_intelisis: Mapped[str | None] = mapped_column(Unicode(10))  # el encontrado, si ya está en Intelisis
    proveedor_nuevo: Mapped[str | None] = mapped_column(Unicode(200))
    costo: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))  # sin IVA, el que dio el proveedor
    motivo_cierre: Mapped[str | None] = mapped_column(Unicode(1000))
    cerrada_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime)
    creada_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    avances: Mapped[list["BusquedaAvance"]] = relationship(order_by="BusquedaAvance.avance_id",
                                                           cascade="all, delete-orphan")


class BusquedaAvance(Base):
    """Lo que va pasando: a quién se contactó y qué dijo, o un cambio de estado."""
    __tablename__ = "busqueda_avance"
    __table_args__ = {"schema": ESQUEMA}

    avance_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    busqueda_id: Mapped[int] = mapped_column(ForeignKey(BUSQUEDA))
    tipo: Mapped[str] = mapped_column(Unicode(12))  # nota / contacto / estado
    texto: Mapped[str] = mapped_column(Unicode(1000))
    proveedor: Mapped[str | None] = mapped_column(Unicode(200))  # a quién se contactó
    resultado: Mapped[str | None] = mapped_column(Unicode(15))  # sin_respuesta / interesado / cotizo / no_surte
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
