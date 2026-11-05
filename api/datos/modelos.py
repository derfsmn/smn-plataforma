"""Catálogo de productos del Centro de datos (esquema datos).

Fuente: docs/modelos/datos_catalogo_v0.dbml. Lo usan el radar de precios, el semáforo de Compras y lo que venga.
Hoy lo alimentan el API de artículos de SMN y la tienda en línea; después, el ETL de la base de Sistemas en Azure.
Fechas en UTC sin zona.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nucleo.modelos import Base, ahora

ESQUEMA = "datos"


class Producto(Base):
    """Una fila por SKU. Cada campo toma el valor de la fuente con más prioridad (ETL > API > tienda)."""
    __tablename__ = "producto"
    __table_args__ = {"schema": ESQUEMA}

    producto_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(Unicode(80), unique=True)  # texto: respeta ceros iniciales
    descripcion: Mapped[str | None] = mapped_column(Unicode(1000))
    marca: Mapped[str | None] = mapped_column(Unicode(300))
    departamento: Mapped[str | None] = mapped_column(Unicode(300))
    rama: Mapped[str | None] = mapped_column(Unicode(300))
    subcategoria: Mapped[str | None] = mapped_column(Unicode(300))
    segmento: Mapped[str | None] = mapped_column(Unicode(300))
    clasificacion: Mapped[str | None] = mapped_column(Unicode(100))
    codigo_proveedor: Mapped[str | None] = mapped_column(Unicode(150))
    nombre_proveedor: Mapped[str | None] = mapped_column(Unicode(500))
    codigo_barras: Mapped[str | None] = mapped_column(Unicode(60))
    precio_lista: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))  # sin impuestos
    precio_membresia: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))  # sin impuestos
    iva_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    ieps_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    precio_lista_con_impuestos: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    precio_membresia_con_impuestos: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    precio_tienda_en_linea: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    disponible_en_linea: Mapped[bool | None] = mapped_column(Boolean)
    liga_producto: Mapped[str | None] = mapped_column(Unicode(600))
    liga_imagen: Mapped[str | None] = mapped_column(Unicode(600))
    imagen_cdn: Mapped[str | None] = mapped_column(Unicode(600))  # foto publicada con el SKU como nombre
    imagen_revisada_en: Mapped[datetime | None] = mapped_column(DateTime)
    # Solo de SMNBI (tblArticulos)
    categoria: Mapped[str | None] = mapped_column(Unicode(300))
    fabricante: Mapped[str | None] = mapped_column(Unicode(300))
    tipo_compra: Mapped[str | None] = mapped_column(Unicode(100))
    estatus_erp: Mapped[str | None] = mapped_column(Unicode(30))  # ALTA / DESCONTINUADO
    origen: Mapped[str] = mapped_column(Unicode(20))  # API / TIENDA / AMBOS / ETL / ARCHIVADO
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    con_diferencias: Mapped[bool] = mapped_column(Boolean, default=False)
    datos_incompletos: Mapped[bool] = mapped_column(Boolean, default=False)
    diferencias: Mapped[str | None] = mapped_column(UnicodeText)  # JSON
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    fuentes: Mapped[list["ProductoFuente"]] = relationship(back_populates="producto")


class ProductoFuente(Base):
    """Lo que dijo cada fuente sobre un producto, tal como llegó."""
    __tablename__ = "producto_fuente"
    __table_args__ = {"schema": ESQUEMA}

    producto_fuente_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.producto.producto_id"))
    fuente: Mapped[str] = mapped_column(Unicode(20))  # API / TIENDA / ETL
    clave_externa: Mapped[str] = mapped_column(Unicode(120), default="")
    presente: Mapped[bool] = mapped_column(Boolean, default=True)
    datos: Mapped[str] = mapped_column(UnicodeText)  # JSON tal como llegó
    huella: Mapped[str] = mapped_column(String(64))  # SHA-256 de datos
    visto_por_ultima_vez_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    producto: Mapped[Producto] = relationship(back_populates="fuentes")


class ProductoPrecioHistorial(Base):
    """Solo inserción: una fila cada vez que cambia algún precio o tasa."""
    __tablename__ = "producto_precio_historial"
    __table_args__ = {"schema": ESQUEMA}

    historial_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.producto.producto_id"))
    precio_lista: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    precio_membresia: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    iva_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    ieps_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    precio_tienda_en_linea: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    vigente_desde: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    carga_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.carga.carga_id"))


class Carga(Base):
    """Cada corrida de carga de una fuente."""
    __tablename__ = "carga"
    __table_args__ = {"schema": ESQUEMA}

    carga_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fuente: Mapped[str] = mapped_column(Unicode(20))  # API / TIENDA / ETL
    disparada_por: Mapped[str] = mapped_column(Unicode(20))  # programador / manual
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("nucleo.usuario.usuario_id"))
    estado: Mapped[str] = mapped_column(Unicode(20), default="en_curso")  # en_curso / completa / fallida
    completa: Mapped[bool] = mapped_column(Boolean, default=False)  # recorrió toda la fuente
    paginas: Mapped[int] = mapped_column(Integer, default=0)
    leidos: Mapped[int] = mapped_column(Integer, default=0)
    creados: Mapped[int] = mapped_column(Integer, default=0)
    actualizados: Mapped[int] = mapped_column(Integer, default=0)
    sin_cambios: Mapped[int] = mapped_column(Integer, default=0)
    ausentes: Mapped[int] = mapped_column(Integer, default=0)
    invalidos: Mapped[int] = mapped_column(Integer, default=0)
    precios_cambiados: Mapped[int] = mapped_column(Integer, default=0)
    total_fuente: Mapped[int | None] = mapped_column(Integer)  # lo que dice la fuente que tiene (count)
    error: Mapped[str | None] = mapped_column(Unicode(1000))
    inicio_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    fin_en: Mapped[datetime | None] = mapped_column(DateTime)
    # Solo el ETL: qué meses trae y por dónde va (lo lee la pantalla para mostrar el avance)
    desde: Mapped[date | None] = mapped_column(Date)
    hasta: Mapped[date | None] = mapped_column(Date)
    paso: Mapped[str | None] = mapped_column(Unicode(20))  # conectar / extraer / transformar / cargar / cuadrar
    mes_actual: Mapped[date | None] = mapped_column(Date)
    meses_total: Mapped[int | None] = mapped_column(Integer)
    meses_hechos: Mapped[int | None] = mapped_column(Integer)
    detener: Mapped[bool] = mapped_column(Boolean, default=False)
    archivo: Mapped[str | None] = mapped_column(Unicode(260))  # carga desde CSV: nombre del archivo


class VentaSemanal(Base):
    """Venta sumada por producto, tienda, semana y empresa, separada por mes de la venta: una semana que cruza
    de mes queda en dos filas, así cada carga reemplaza meses completos sin tocar el mes vecino."""
    __tablename__ = "venta_semanal"
    __table_args__ = {"schema": ESQUEMA}

    mes: Mapped[date] = mapped_column(Date, primary_key=True)
    sku: Mapped[str] = mapped_column(Unicode(80), primary_key=True)
    tienda: Mapped[str] = mapped_column(Unicode(10), primary_key=True)  # tblVenta.Sucursal
    semana: Mapped[date] = mapped_column(Date, primary_key=True)  # lunes
    empresa: Mapped[str] = mapped_column(Unicode(5), primary_key=True)
    piezas: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    piezas_devueltas: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    importe_bruto: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    descuento: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    importe: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    costo: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    tickets: Mapped[int] = mapped_column(Integer)
    carga_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.carga.carga_id"))


class VentaCuadre(Base):
    """Prueba de cada mes cargado: lo que suma SMNBI contra lo que quedó en la plataforma."""
    __tablename__ = "venta_cuadre"
    __table_args__ = {"schema": ESQUEMA}

    cuadre_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carga_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.carga.carga_id"))
    mes: Mapped[date] = mapped_column(Date)
    empresa: Mapped[str] = mapped_column(Unicode(5))
    importe_origen: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))  # vacío en cargas con archivo
    importe_cargado: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    piezas_origen: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    piezas_cargadas: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    renglones_fuera: Mapped[int | None] = mapped_column(Integer)
    cuadra: Mapped[bool | None] = mapped_column(Boolean)


class CargaPaso(Base):
    """Bitácora de pasos de una carga del ETL: cuándo empezó y terminó cada paso de cada mes."""
    __tablename__ = "carga_paso"
    __table_args__ = {"schema": ESQUEMA}

    paso_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carga_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.carga.carga_id"))
    mes: Mapped[date | None] = mapped_column(Date)
    paso: Mapped[str] = mapped_column(Unicode(20))
    estado: Mapped[str] = mapped_column(Unicode(20))  # en_curso / hecho / fallido / detenido
    filas: Mapped[int | None] = mapped_column(Integer)
    nota: Mapped[str | None] = mapped_column(Unicode(500))
    inicio_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    fin_en: Mapped[datetime | None] = mapped_column(DateTime)


# ---------------------------------------------------------------- tablas de SMNBI (migración 0022)

class Tienda(Base):
    """tblAlmacenes: cada almacén, sea tienda (ruta TIENDAS) o mayoreo (categoría MAY)."""
    __tablename__ = "tienda"
    __table_args__ = {"schema": ESQUEMA}

    almacen: Mapped[str] = mapped_column(Unicode(10), primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(100))
    poblacion: Mapped[str | None] = mapped_column(Unicode(100))
    estado: Mapped[str | None] = mapped_column(Unicode(30))
    codigo_postal: Mapped[str | None] = mapped_column(Unicode(15))
    grupo: Mapped[str | None] = mapped_column(Unicode(50))
    ruta: Mapped[str | None] = mapped_column(Unicode(50))
    sucursal: Mapped[int | None] = mapped_column(Integer)
    estatus: Mapped[str | None] = mapped_column(Unicode(15))
    region: Mapped[str | None] = mapped_column(Unicode(50))
    categoria: Mapped[str | None] = mapped_column(Unicode(50))
    fecha_apertura: Mapped[date | None] = mapped_column(Date)
    latitud: Mapped[float | None] = mapped_column(Float)
    longitud: Mapped[float | None] = mapped_column(Float)
    carga_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.carga.carga_id"))


class Proveedor(Base):
    """tblProveedores. Agente y RFC se guardan aunque vengan vacíos para filtrar (Diego, 2026-11-03)."""
    __tablename__ = "proveedor"
    __table_args__ = {"schema": ESQUEMA}

    proveedor: Mapped[str] = mapped_column(Unicode(10), primary_key=True)
    nombre: Mapped[str | None] = mapped_column(Unicode(100))
    estatus: Mapped[str | None] = mapped_column(Unicode(15))
    condicion: Mapped[str | None] = mapped_column(Unicode(30))
    descuento: Mapped[str | None] = mapped_column(Unicode(30))
    descuento_adicional: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    dias_entrega: Mapped[int | None] = mapped_column(Integer)
    penalizacion: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    agente: Mapped[str | None] = mapped_column(Unicode(10))  # clave del agente (comprador) en Intelisis
    rfc: Mapped[str | None] = mapped_column(Unicode(15))
    carga_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.carga.carga_id"))


class CompraOrden(Base):
    """Una orden de compra y lo que llegó, se perdió o se rechazó después."""
    __tablename__ = "compra_orden"
    __table_args__ = {"schema": ESQUEMA}

    empresa: Mapped[str] = mapped_column(Unicode(5), primary_key=True)
    orden: Mapped[str] = mapped_column(Unicode(20), primary_key=True)
    proveedor: Mapped[str | None] = mapped_column(Unicode(10))
    almacen: Mapped[str | None] = mapped_column(Unicode(10))
    fecha_orden: Mapped[date] = mapped_column(Date)
    estatus: Mapped[str | None] = mapped_column(Unicode(15))
    piezas_pedidas: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    importe_pedido: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    primera_entrada: Mapped[date | None] = mapped_column(Date)
    ultima_entrada: Mapped[date | None] = mapped_column(Date)
    piezas_recibidas: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    piezas_perdidas: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    piezas_rechazadas: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    carga_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.carga.carga_id"))


class CostoArticulo(Base):
    """Costo de compra por pieza sin IVA: última entrada y promedio de 12 meses."""
    __tablename__ = "costo_articulo"
    __table_args__ = {"schema": ESQUEMA}

    sku: Mapped[str] = mapped_column(Unicode(80), primary_key=True)
    proveedor: Mapped[str | None] = mapped_column(Unicode(10))
    fecha_ultima: Mapped[date | None] = mapped_column(Date)
    costo_ultimo: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    costo_12m: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    piezas_12m: Mapped[Decimal | None] = mapped_column(Numeric(16, 3))
    compras_12m: Mapped[int | None] = mapped_column(Integer)
    carga_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.carga.carga_id"))


class Inventario(Base):
    """Foto del inventario por fecha de corte, almacén y artículo."""
    __tablename__ = "inventario"
    __table_args__ = {"schema": ESQUEMA}

    fecha_corte: Mapped[date] = mapped_column(Date, primary_key=True)
    empresa: Mapped[str] = mapped_column(Unicode(5), primary_key=True)
    almacen: Mapped[str] = mapped_column(Unicode(10), primary_key=True)
    sku: Mapped[str] = mapped_column(Unicode(80), primary_key=True)
    existencia: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    costo_promedio: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    carga_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.carga.carga_id"))


# ---------------------------------------------------------------- calificación de proveedores (migración 0027)

class ProveedorEvaluacion(Base):
    """Un cálculo de la calificación de todos los proveedores con lo cargado de SMNBI en ese momento."""
    __tablename__ = "proveedor_evaluacion"
    __table_args__ = {"schema": ESQUEMA}

    evaluacion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estado: Mapped[str] = mapped_column(Unicode(20))  # en_curso / completa / fallida
    iniciada_por: Mapped[int | None] = mapped_column(ForeignKey("nucleo.usuario.usuario_id"))
    iniciada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime)
    proveedores: Mapped[int | None] = mapped_column(Integer)
    calificados: Mapped[int | None] = mapped_column(Integer)
    contexto: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: ventanas, pesos y metas usadas
    error: Mapped[str | None] = mapped_column(Unicode(1000))


class ProveedorCalificacion(Base):
    """La calificación de un proveedor en una evaluación: puntaje, bloques y las métricas de donde salen."""
    __tablename__ = "proveedor_calificacion"
    __table_args__ = {"schema": ESQUEMA}

    evaluacion_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.proveedor_evaluacion.evaluacion_id"),
                                               primary_key=True)
    proveedor: Mapped[str] = mapped_column(Unicode(10), primary_key=True)
    nombre: Mapped[str | None] = mapped_column(Unicode(100))
    puntaje: Mapped[int | None] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(Unicode(10))  # verde / amarillo / rojo; vacío sin datos
    confianza: Mapped[str] = mapped_column(Unicode(10))  # alta / media / baja / sin_datos
    cumplimiento: Mapped[int | None] = mapped_column(Integer)
    comercial: Mapped[int | None] = mapped_column(Integer)
    costo: Mapped[int | None] = mapped_column(Integer)
    inventario: Mapped[int | None] = mapped_column(Integer)
    skus_activos: Mapped[int] = mapped_column(Integer, default=0)
    venta: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))  # sin IVA, en la ventana de venta
    compra: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))  # importe pedido en la ventana de compras
    metricas: Mapped[str | None] = mapped_column(UnicodeText)  # JSON


# ---------------------------------------------------------------- grupos de tiendas (migración 0029)

class TiendaGrupoCorrida(Base):
    """Un cálculo de los grupos de tiendas que venden parecido (k-medias en Python; texto de cada grupo con Ollama)."""
    __tablename__ = "tienda_grupo_corrida"
    __table_args__ = {"schema": ESQUEMA}

    corrida_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estado: Mapped[str] = mapped_column(Unicode(20))  # en_curso / completa / fallida
    iniciada_por: Mapped[int | None] = mapped_column(ForeignKey("nucleo.usuario.usuario_id"))
    iniciada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime)
    tiendas: Mapped[int | None] = mapped_column(Integer)
    grupos: Mapped[int | None] = mapped_column(Integer)
    calidad: Mapped[float | None] = mapped_column(Float)  # silueta promedio, de -1 a 1
    contexto: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: ventana, departamentos, fuera
    perfiles: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: un perfil por grupo con su nombre y texto
    nota_ia: Mapped[str | None] = mapped_column(Unicode(500))
    error: Mapped[str | None] = mapped_column(Unicode(1000))


class TiendaGrupo(Base):
    """El grupo de una tienda en una corrida y en qué se sale de su grupo."""
    __tablename__ = "tienda_grupo"
    __table_args__ = {"schema": ESQUEMA}

    corrida_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.tienda_grupo_corrida.corrida_id"), primary_key=True)
    almacen: Mapped[str] = mapped_column(Unicode(10), primary_key=True)
    grupo: Mapped[int] = mapped_column(Integer)
    tipicidad: Mapped[int | None] = mapped_column(Integer)  # 0 a 100: qué tanto se parece al centro de su grupo
    rasgos: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: rasgos donde más se sale de su grupo
    alertas: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: en qué va abajo de sus pares (None si en nada)
    metricas: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: sus rasgos medidos y su localidad del Censo
