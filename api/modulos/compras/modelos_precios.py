"""Tablas del Radar de precios (esquema compras, tablas precio_*).

Fuente: docs/modelos/compras_precios_v0.dbml. Los productos salen del catálogo del Centro de datos (datos.producto).
Fechas en UTC sin zona; `fecha` de la corrida es el día local (zona del radar de precios).
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column

import datos.modelos  # noqa: F401 - registra datos.producto para las llaves foráneas
from nucleo.modelos import Base, ahora

E = "compras"
PRODUCTO = "datos.producto.producto_id"
USUARIO = "nucleo.usuario.usuario_id"
VIGENTES = ("automatica", "ia", "persona")  # estados de una coincidencia que se usa


class PrecioVigilado(Base):
    __tablename__ = "precio_vigilado"
    __table_args__ = {"schema": E}

    vigilado_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey(PRODUCTO), unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    consulta: Mapped[str | None] = mapped_column(Unicode(300))  # búsqueda escrita a mano
    limite_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # semáforo: rojo arriba de este %; vacío = el general
    origen: Mapped[str] = mapped_column(Unicode(20), default="pantalla")  # pantalla / migracion
    agregado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class PrecioCoincidencia(Base):
    """Qué producto de Google Shopping es el nuestro."""
    __tablename__ = "precio_coincidencia"
    __table_args__ = {"schema": E}

    coincidencia_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey(PRODUCTO))
    google_id: Mapped[str | None] = mapped_column(Unicode(80))
    titulo: Mapped[str | None] = mapped_column(Unicode(400))
    liga: Mapped[str | None] = mapped_column(Unicode(800))
    imagen: Mapped[str | None] = mapped_column(Unicode(800))
    estado: Mapped[str] = mapped_column(Unicode(20))  # automatica / ia / persona / rechazada / invalidada
    confianza: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    motivo: Mapped[str | None] = mapped_column(Unicode(600))
    estrategia: Mapped[str | None] = mapped_column(Unicode(40))  # codigo_barras / descripcion / consulta
    fallos_seguidos: Mapped[int] = mapped_column(Integer, default=0)
    candidato: Mapped[str | None] = mapped_column(UnicodeText)  # JSON
    iguales: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: otras publicaciones del mismo producto
    decidido_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    verificado_en: Mapped[datetime | None] = mapped_column(DateTime)


class PrecioTiendaCoincidencia(Base):
    """Qué producto del sitio de una tienda clave es el nuestro (búsqueda directa, Diego 2026-10-20)."""
    __tablename__ = "precio_tienda_coincidencia"
    __table_args__ = {"schema": E}

    tienda_coincidencia_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey(PRODUCTO))
    tienda: Mapped[str] = mapped_column(Unicode(40))
    clave: Mapped[str] = mapped_column(Unicode(120))
    titulo: Mapped[str | None] = mapped_column(Unicode(400))
    liga: Mapped[str | None] = mapped_column(Unicode(800))
    imagen: Mapped[str | None] = mapped_column(Unicode(800))
    ean: Mapped[str | None] = mapped_column(Unicode(20))
    estado: Mapped[str] = mapped_column(Unicode(20))  # automatica / ia / persona / rechazada / invalidada
    motivo: Mapped[str | None] = mapped_column(Unicode(600))
    decidido_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    verificado_en: Mapped[datetime | None] = mapped_column(DateTime)


class PrecioCorrida(Base):
    __tablename__ = "precio_corrida"
    __table_args__ = {"schema": E}

    corrida_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)  # varias por día: cada «Correr ahora» es una corrida nueva
    origen: Mapped[str] = mapped_column(Unicode(20))  # programado / tardio / manual / prueba / producto (radar de productos) / oportunidad
    estado: Mapped[str] = mapped_column(Unicode(20), default="en_curso")  # en_curso / completa / parcial / fallida
    intentos: Mapped[int] = mapped_column(Integer, default=1)
    iniciado_por: Mapped[int | None] = mapped_column(ForeignKey(USUARIO))
    productos: Mapped[int] = mapped_column(Integer, default=0)
    con_coincidencia: Mapped[int] = mapped_column(Integer, default=0)
    sin_coincidencia: Mapped[int] = mapped_column(Integer, default=0)
    con_precios: Mapped[int] = mapped_column(Integer, default=0)
    fallidos: Mapped[int] = mapped_column(Integer, default=0)
    alertas: Mapped[int] = mapped_column(Integer, default=0)
    tope_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    costo_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    avisos: Mapped[str | None] = mapped_column(UnicodeText)  # JSON
    lista: Mapped[str | None] = mapped_column(UnicodeText)  # prueba con Excel, JSON: archivo, producto_ids, no_encontrados
    error: Mapped[str | None] = mapped_column(Unicode(1000))
    iniciado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    terminado_en: Mapped[datetime | None] = mapped_column(DateTime)


class PrecioCorridaProducto(Base):
    __tablename__ = "precio_corrida_producto"
    __table_args__ = {"schema": E}

    corrida_producto_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    corrida_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.precio_corrida.corrida_id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey(PRODUCTO))
    coincidencia_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.precio_coincidencia.coincidencia_id"))
    estado: Mapped[str] = mapped_column(Unicode(30), default="pendiente")
    mensaje: Mapped[str | None] = mapped_column(Unicode(400))
    precio_lista: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))  # con impuestos
    precio_membresia: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    precio_tienda: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    vendedores: Mapped[int] = mapped_column(Integer, default=0)
    minimo: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    maximo: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    promedio: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    mediana: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    dif_lista_mediana_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    dif_membresia_mediana_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    dif_lista_minimo_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    candidatos: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: lo que regresó Google en la búsqueda, con su calificación
    tiendas: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: qué pasó en el sitio de cada tienda clave


class PrecioObservacion(Base):
    """Solo inserción."""
    __tablename__ = "precio_observacion"
    __table_args__ = {"schema": E}

    observacion_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    corrida_id: Mapped[int] = mapped_column(ForeignKey(f"{E}.precio_corrida.corrida_id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey(PRODUCTO))
    coincidencia_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.precio_coincidencia.coincidencia_id"))  # vacío: del sitio de una tienda
    tienda_coincidencia_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.precio_tienda_coincidencia.tienda_coincidencia_id"))
    vendedor: Mapped[str] = mapped_column(Unicode(200))
    vendedor_original: Mapped[str | None] = mapped_column(Unicode(200))
    dominio: Mapped[str | None] = mapped_column(Unicode(200))
    liga: Mapped[str | None] = mapped_column(Unicode(800))
    precio: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    envio: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    precio_comparable: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    moneda: Mapped[str] = mapped_column(Unicode(5))
    disponibilidad: Mapped[str | None] = mapped_column(Unicode(120))
    es_propia: Mapped[bool] = mapped_column(Boolean, default=False)
    datos: Mapped[str] = mapped_column(UnicodeText)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class PrecioEnvio(Base):
    """Cada envío pagado a DataForSEO. Se guarda antes de enviar."""
    __tablename__ = "precio_envio"
    __table_args__ = {"schema": E}

    envio_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    corrida_id: Mapped[int | None] = mapped_column(ForeignKey(f"{E}.precio_corrida.corrida_id"))
    tipo: Mapped[str] = mapped_column(Unicode(20))  # productos / vendedores
    tareas: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(Unicode(20), default="reservado")  # reservado / confirmado / incierto / rechazado
    estimado_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    costo_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    respuesta: Mapped[str | None] = mapped_column(UnicodeText)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    confirmado_en: Mapped[datetime | None] = mapped_column(DateTime)


class PrecioVendedor(Base):
    __tablename__ = "precio_vendedor"
    __table_args__ = {"schema": E}

    vendedor_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(120), unique=True)
    alias: Mapped[str | None] = mapped_column(Unicode(1000))
    es_propio: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
