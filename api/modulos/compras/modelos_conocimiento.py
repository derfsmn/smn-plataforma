"""Base de conocimiento de Compras (esquema compras): lo que Compras sabe y aplica al decidir si un producto entra.

Pedido de Diego (2026-10-21): Compras no tiene sus políticas por escrito, así que las escribe aquí. El semáforo de
productos (docs/modelos/modelo_semaforo_v3.dbml) tomará de aquí los bloqueos, umbrales, pesos y casos para calibrar.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column

from nucleo.modelos import Base, ahora

ESQUEMA = "compras"
USUARIO = "nucleo.usuario.usuario_id"


class ConocimientoPolitica(Base):
    """Política escrita por Compras. tema=proceso es «cómo se decide hoy»."""
    __tablename__ = "conocimiento_politica"
    __table_args__ = {"schema": ESQUEMA}

    politica_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tema: Mapped[str] = mapped_column(Unicode(30))  # alta_productos / proveedores / regulatorio / precios / comite / proceso / otra
    titulo: Mapped[str] = mapped_column(Unicode(200))
    contenido: Mapped[str] = mapped_column(UnicodeText, default="")
    departamento: Mapped[str | None] = mapped_column(Unicode(300))  # vacío = aplica a todos
    estado: Mapped[str] = mapped_column(Unicode(20), default="borrador")  # borrador / vigente / archivada
    version: Mapped[int] = mapped_column(Integer, default=1)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)


class ConocimientoRegla(Base):
    """Regla que el semáforo puede aplicar: rechazo directo, umbral de un criterio o meta de un lanzamiento exitoso."""
    __tablename__ = "conocimiento_regla"
    __table_args__ = {"schema": ESQUEMA}

    regla_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(Unicode(20))  # rechazo / umbral / exito
    criterio: Mapped[str] = mapped_column(Unicode(200))
    departamento: Mapped[str | None] = mapped_column(Unicode(300))  # vacío = aplica a todos
    minimo: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    maximo: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    unidad: Mapped[str | None] = mapped_column(Unicode(40))  # %, días, meses, piezas, MXN...
    periodo_meses: Mapped[int | None] = mapped_column(Integer)  # solo exito: en cuánto tiempo
    descripcion: Mapped[str | None] = mapped_column(Unicode(1000))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)


class ConocimientoPeso(Base):
    """Cuánto pesa cada factor del semáforo en la decisión de Compras (suman 100)."""
    __tablename__ = "conocimiento_peso"
    __table_args__ = {"schema": ESQUEMA}

    factor: Mapped[str] = mapped_column(Unicode(30), primary_key=True)
    puntos: Mapped[int] = mapped_column(Integer)
    nota: Mapped[str | None] = mapped_column(Unicode(600))
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)


class ConocimientoCaso(Base):
    """Producto que Compras ya evaluó: sirve para calibrar el semáforo contra lo que se decidió de verdad."""
    __tablename__ = "conocimiento_caso"
    __table_args__ = {"schema": ESQUEMA}

    caso_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto: Mapped[str] = mapped_column(Unicode(300))
    sku: Mapped[str | None] = mapped_column(Unicode(60))
    proveedor: Mapped[str | None] = mapped_column(Unicode(200))
    departamento: Mapped[str | None] = mapped_column(Unicode(300))
    fecha_decision: Mapped[date | None] = mapped_column(Date)
    decision: Mapped[str] = mapped_column(Unicode(20))  # aprobado / rechazado / condicionado
    motivo: Mapped[str | None] = mapped_column(Unicode(1000))
    resultado: Mapped[str] = mapped_column(Unicode(20), default="sin_dato")  # funciono / no_funciono / sin_dato / no_aplica
    notas: Mapped[str | None] = mapped_column(Unicode(1000))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)


class ConocimientoPesoProveedor(Base):
    """Cuánto pesa cada bloque en la calificación de proveedores (suman 100). Migración 0027."""
    __tablename__ = "conocimiento_peso_proveedor"
    __table_args__ = {"schema": ESQUEMA}

    bloque: Mapped[str] = mapped_column(Unicode(30), primary_key=True)
    puntos: Mapped[int] = mapped_column(Integer)
    nota: Mapped[str | None] = mapped_column(Unicode(600))
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)
