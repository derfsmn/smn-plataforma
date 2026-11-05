"""Tablas del Radar de tendencias (esquema compras).

Fuente: docs/modelos/compras_radar_v0.dbml. Las fechas se guardan en UTC sin zona; `fecha` del reporte es
el día local (zona del radar) al que corresponde.
"""
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nucleo.modelos import Base, ahora

ESQUEMA = "compras"
N = "nucleo"


class RadarFuente(Base):
    __tablename__ = "radar_fuente"
    __table_args__ = {"schema": ESQUEMA}

    fuente_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(160))
    liga: Mapped[str] = mapped_column(Unicode(400))  # página principal, para abrirla
    tipo: Mapped[str] = mapped_column(Unicode(30))  # oficial / especializada / negocios / estudios
    pais: Mapped[str] = mapped_column(Unicode(20))  # MX / EUA / UE / global
    idioma: Mapped[str] = mapped_column(Unicode(5))  # es / en
    metodo: Mapped[str] = mapped_column(Unicode(20))  # rss / busqueda / manual
    # rss: dirección del feed. busqueda: dominio donde busca la IA (p. ej. gob.mx)
    lectura: Mapped[str | None] = mapped_column(Unicode(600))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    notas: Mapped[str | None] = mapped_column(Unicode(400))
    ultima_lectura_en: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_resultado: Mapped[str | None] = mapped_column(Unicode(300))
    ultimos_articulos: Mapped[int | None] = mapped_column(Integer)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)


class RadarTema(Base):
    """Tema de la búsqueda abierta en internet."""
    __tablename__ = "radar_tema"
    __table_args__ = {"schema": ESQUEMA}

    tema_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(120))
    descripcion: Mapped[str] = mapped_column(Unicode(600))  # qué buscar, en palabras
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(Integer, default=100)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class RadarReporte(Base):
    """Una corrida del radar y su reporte del día."""
    __tablename__ = "radar_reporte"
    __table_args__ = {"schema": ESQUEMA}

    reporte_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, unique=True)
    estado: Mapped[str] = mapped_column(Unicode(20), default="en_curso")  # en_curso / listo / error
    origen: Mapped[str] = mapped_column(Unicode(20))  # programado / tardio / manual
    intentos: Mapped[int] = mapped_column(Integer, default=1)
    iniciado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    terminado_en: Mapped[datetime | None] = mapped_column(DateTime)
    iniciado_por: Mapped[int | None] = mapped_column(ForeignKey(f"{N}.usuario.usuario_id"))
    fuentes_leidas: Mapped[int] = mapped_column(Integer, default=0)
    fuentes_con_error: Mapped[int] = mapped_column(Integer, default=0)
    busquedas: Mapped[int] = mapped_column(Integer, default=0)
    articulos_nuevos: Mapped[int] = mapped_column(Integer, default=0)
    articulos_relevantes: Mapped[int] = mapped_column(Integer, default=0)
    resumen: Mapped[str | None] = mapped_column(UnicodeText)
    radar_ejecutivo: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: lista de líneas
    avisos: Mapped[str | None] = mapped_column(UnicodeText)  # JSON: lista de avisos de la corrida
    correos_enviados: Mapped[int] = mapped_column(Integer, default=0)
    correos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Unicode(1000))

    hallazgos: Mapped[list["RadarHallazgo"]] = relationship(order_by="RadarHallazgo.orden", back_populates="reporte")


class RadarArticulo(Base):
    __tablename__ = "radar_articulo"
    __table_args__ = {"schema": ESQUEMA}

    articulo_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reporte_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.radar_reporte.reporte_id"))
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.radar_fuente.fuente_id"))
    tema_id: Mapped[int | None] = mapped_column(ForeignKey(f"{ESQUEMA}.radar_tema.tema_id"))
    origen: Mapped[str] = mapped_column(Unicode(20))  # lista / busqueda
    url: Mapped[str] = mapped_column(Unicode(1000))
    url_hash: Mapped[str] = mapped_column(Unicode(64), unique=True)
    titulo_hash: Mapped[str] = mapped_column(Unicode(64))
    sitio: Mapped[str] = mapped_column(Unicode(200))  # dominio, para contar fuentes independientes
    titulo: Mapped[str] = mapped_column(Unicode(500))
    extracto: Mapped[str | None] = mapped_column(UnicodeText)
    publicado_en: Mapped[date | None] = mapped_column(Date)
    leido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    en_ventana: Mapped[bool] = mapped_column(Boolean, default=True)
    # Clasificación de la IA (nula si no se clasificó)
    relevante: Mapped[bool | None] = mapped_column(Boolean)
    categoria: Mapped[str | None] = mapped_column(Unicode(40))
    nivel: Mapped[str | None] = mapped_column(Unicode(10))  # ALTA / MEDIA / TEMPRANA
    departamento: Mapped[str | None] = mapped_column(Unicode(80))
    pais: Mapped[str | None] = mapped_column(Unicode(20))
    por_que: Mapped[str | None] = mapped_column(Unicode(600))
    clasificado_en: Mapped[datetime | None] = mapped_column(DateTime)

    fuente: Mapped[RadarFuente | None] = relationship()


class RadarSenal(Base):
    """Un tema que aparece en uno o más artículos. Emergente o tendencia lo decide la regla, no la IA."""
    __tablename__ = "radar_senal"
    __table_args__ = {"schema": ESQUEMA}

    senal_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(Unicode(300))
    descripcion: Mapped[str | None] = mapped_column(Unicode(1000))
    tipo: Mapped[str] = mapped_column(Unicode(20), default="emergente")  # emergente / tendencia
    nivel: Mapped[str] = mapped_column(Unicode(10))
    categoria: Mapped[str | None] = mapped_column(Unicode(40))
    departamento: Mapped[str | None] = mapped_column(Unicode(80))
    paises: Mapped[str | None] = mapped_column(Unicode(60))  # p. ej. "EUA, MX"
    sitios_distintos: Mapped[int] = mapped_column(Integer, default=1)
    primera_vez: Mapped[date] = mapped_column(Date)
    ultima_vez: Mapped[date] = mapped_column(Date)
    veces_reportada: Mapped[int] = mapped_column(Integer, default=0)
    estado: Mapped[str] = mapped_column(Unicode(20), default="nueva")  # nueva / vigilar / descartada / iniciativa
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    articulos: Mapped[list[RadarArticulo]] = relationship(
        secondary=f"{ESQUEMA}.radar_senal_articulo", order_by="RadarArticulo.publicado_en.desc()", viewonly=True)


class RadarSenalArticulo(Base):
    __tablename__ = "radar_senal_articulo"
    __table_args__ = {"schema": ESQUEMA}

    senal_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.radar_senal.senal_id"), primary_key=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.radar_articulo.articulo_id"), primary_key=True)


class RadarHallazgo(Base):
    """Lo que salió en el reporte de un día: una señal con el texto de ese día."""
    __tablename__ = "radar_hallazgo"
    __table_args__ = {"schema": ESQUEMA}

    hallazgo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporte_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.radar_reporte.reporte_id"))
    senal_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.radar_senal.senal_id"))
    orden: Mapped[int] = mapped_column(Integer)
    titulo: Mapped[str] = mapped_column(Unicode(300))
    por_que: Mapped[str] = mapped_column(Unicode(1000))
    nivel: Mapped[str] = mapped_column(Unicode(10))
    tipo: Mapped[str] = mapped_column(Unicode(20))
    departamento: Mapped[str | None] = mapped_column(Unicode(80))
    paises: Mapped[str | None] = mapped_column(Unicode(60))

    reporte: Mapped[RadarReporte] = relationship(back_populates="hallazgos")
    senal: Mapped[RadarSenal] = relationship()


class RadarAccion(Base):
    __tablename__ = "radar_accion"
    __table_args__ = {"schema": ESQUEMA}

    accion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    senal_id: Mapped[int] = mapped_column(ForeignKey(f"{ESQUEMA}.radar_senal.senal_id"))
    accion: Mapped[str] = mapped_column(Unicode(20))  # iniciativa / vigilar / descartar
    motivo: Mapped[str | None] = mapped_column(Unicode(600))
    usuario_id: Mapped[int] = mapped_column(ForeignKey(f"{N}.usuario.usuario_id"))
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class RadarDestinatario(Base):
    __tablename__ = "radar_destinatario"
    __table_args__ = {"schema": ESQUEMA}

    destinatario_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(160))
    correo: Mapped[str] = mapped_column(Unicode(254), unique=True)
    area: Mapped[str | None] = mapped_column(Unicode(120))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # decision: correo con botones Abrir iniciativa / Vigilar / Descartar; informativo: sin botones
    tipo_correo: Mapped[str] = mapped_column(Unicode(20), default="decision", server_default="decision")
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class RadarDocumento(Base):
    """Archivo de la base de conocimiento. El texto se extrae al subirlo y la IA lo usa como contexto."""
    __tablename__ = "radar_documento"
    __table_args__ = {"schema": ESQUEMA}

    documento_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archivo_id: Mapped[int] = mapped_column(ForeignKey(f"{N}.archivo.archivo_id"))
    titulo: Mapped[str] = mapped_column(Unicode(200))
    descripcion: Mapped[str | None] = mapped_column(Unicode(600))
    texto: Mapped[str | None] = mapped_column(UnicodeText)
    caracteres: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    subido_por: Mapped[int] = mapped_column(ForeignKey(f"{N}.usuario.usuario_id"))
    subido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
