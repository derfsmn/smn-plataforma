"""ETL de ventas: de SMNBI (base de Sistemas, solo lectura) a datos.venta_semanal.

Diseño en docs/sistemas/diseno_etl_ventas.md. Cada carga va mes por mes y en cada mes hace cinco pasos:
1. Conectar a SMNBI (usuario de solo lectura, conexión de solo lectura).
2. Extraer: SMNBI ya entrega la venta sumada por producto, tienda, semana y empresa (no se traen tickets ni clientes).
3. Transformar: revisa cada fila y la deja en el formato de la plataforma; lo que no sirve se cuenta como «fuera».
4. Cargar: borra e inserta el mes completo en una sola transacción; repetir una carga no duplica nada.
5. Cuadrar: suma lo mismo en SMNBI y en la plataforma por empresa; si no cuadra, la carga queda marcada y avisa.

También acepta el CSV que sale de docs/sistemas/consulta_venta_semanal.sql (un mes por archivo), con los mismos pasos;
ahí el cuadre es contra el archivo.

El avance se guarda en datos.carga y datos.carga_paso con su propia sesión, para que la pantalla lo vea mientras
corre sin esperar a que termine la transacción del mes. Solo corre una carga del ETL a la vez.
"""
import csv
import io
import logging
import threading
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from core.config import configuracion
from datos.modelos import Carga, CargaPaso, VentaCuadre, VentaSemanal
from nucleo.modelos import Permiso, RolPermiso, Usuario, UsuarioRol, ahora

log = logging.getLogger("smn.datos.etl")

FUENTE = "ETL_VENTAS"
PASOS = ("conectar", "extraer", "transformar", "cargar", "cuadrar")
TOLERANCIA = Decimal("0.0001")  # 0.01 %
LOTE = 5000
CORRER = "datos.etl.correr"

# Columnas en el orden de consulta_venta_semanal.sql (y del CSV que sale de ella)
COLUMNAS = ("sku", "tienda", "semana", "empresa", "piezas", "piezas_devueltas", "importe_bruto", "descuento_linea", "costo", "tickets")
UNIDADES_FUERA = ("FLETETV", "Actividad", "SERVICIO")
DEVOLUCIONES = ("Nota Devolucion", "Devolucion Venta")
# Resultados de SMNBI del 2026-10-26 (docs/sistemas/revision_smnbi_2026-10-26.md):
# - La tienda es el Almacen: Sucursal viene vacía en el 99 % de las ventas. Almacen liga con tblAlmacenes.
# - «Nota Devolucion» ya trae la cantidad en negativo y «Devolucion Venta» en positivo: se toma el valor absoluto
#   y se resta, para que las dos resten igual.
# - DescuentoLinea y DescuentoGlobal son PORCENTAJES (consultas 14 y 15): el importe del encabezado cuadra al centavo con
#   Cantidad × Precio × (1 − DescuentoLinea/100). DescuentoGlobal solo viene en facturas (2 a 7 %). El descuento en pesos
#   del renglón es Cantidad × Precio × (1 − (1 − línea/100) × (1 − global/100)).


class ErrorEtl(Exception):
    pass


class Detenida(Exception):
    pass


# ---------------------------------------------------------------- consultas a SMNBI

def tipos_venta() -> tuple[str, ...]:
    tipos = ("Nota", *DEVOLUCIONES)
    return (*tipos, "Factura Electronica") if configuracion().etl_factura_electronica else tipos


def _lista(valores: Iterable[str]) -> str:
    # Solo constantes de este archivo, nunca texto de una persona
    return ", ".join("'" + v.replace("'", "''") + "'" for v in valores)


def _filtro() -> str:
    return f"""
        v.FechaMov >= ? AND v.FechaMov < ?
        AND v.Estatus = 'CONCLUIDO'
        AND v.TipoMov IN ({_lista(tipos_venta())})
        AND ISNULL(d.Unidad, '') NOT IN ({_lista(UNIDADES_FUERA)})"""


def _dev(expr: str) -> str:
    """En devoluciones, el valor absoluto (luego se resta con el signo)."""
    return f"(CASE WHEN v.TipoMov IN ({_lista(DEVOLUCIONES)}) THEN ABS({expr}) ELSE {expr} END)"


DESCUENTO = ("d.Cantidad * d.Precio * (1 - (1 - ISNULL(d.DescuentoLinea, 0) / 100.0)"
             " * (1 - ISNULL(v.DescuentoGlobal, 0) / 100.0))")


def sql_ventas() -> str:
    """La misma lógica que consulta_venta_semanal.sql. La semana es el lunes (1900-01-01 fue lunes), sin depender de DATEFIRST."""
    return f"""
    WITH renglones AS (
        SELECT v.ID, v.Empresa, ISNULL(v.Almacen, '') AS Tienda, d.Articulo,
               CAST(DATEADD(DAY, -(DATEDIFF(DAY, '19000101', v.FechaMov) % 7), CAST(v.FechaMov AS date)) AS date) AS semana,
               CASE WHEN v.TipoMov IN ({_lista(DEVOLUCIONES)}) THEN -1 ELSE 1 END AS signo,
               {_dev("d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1)")} AS piezas,
               {_dev("d.Cantidad * d.Precio")} AS bruto,
               {_dev(DESCUENTO)} AS descuento_linea,  -- en pesos: línea y global
               {_dev("d.Cantidad * d.Costo")} AS costo
        FROM dbo.tblVenta v
        JOIN dbo.tblVentaD d ON d.ID = v.ID
        JOIN dbo.tblArticulos a ON a.Articulo = d.Articulo
        WHERE {_filtro()}
    )
    SELECT Articulo, Tienda, semana, Empresa,
           SUM(CASE WHEN signo = 1 THEN piezas ELSE 0 END),
           SUM(CASE WHEN signo = -1 THEN piezas ELSE 0 END),
           SUM(signo * bruto), SUM(signo * descuento_linea), SUM(signo * costo),
           COUNT(DISTINCT CASE WHEN signo = 1 THEN ID END)
    FROM renglones
    GROUP BY Articulo, Tienda, semana, Empresa"""


def sql_cuadre() -> str:
    """Totales del mes por empresa con las mismas reglas, directo de los renglones, y cuántos renglones quedaron fuera."""
    return f"""
    SELECT v.Empresa,
           SUM(CASE WHEN a.Articulo IS NOT NULL AND {_filtro_sin_fecha()} THEN
               (CASE WHEN v.TipoMov IN ({_lista(DEVOLUCIONES)}) THEN -1 ELSE 1 END)
               * ({_dev("d.Cantidad * d.Precio")} - {_dev(DESCUENTO)}) ELSE 0 END),
           SUM(CASE WHEN a.Articulo IS NOT NULL AND {_filtro_sin_fecha()} THEN
               (CASE WHEN v.TipoMov IN ({_lista(DEVOLUCIONES)}) THEN -1 ELSE 1 END)
               * {_dev("d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1)")} ELSE 0 END),
           SUM(CASE WHEN a.Articulo IS NOT NULL AND {_filtro_sin_fecha()} THEN 0 ELSE 1 END)
    FROM dbo.tblVenta v
    JOIN dbo.tblVentaD d ON d.ID = v.ID
    LEFT JOIN dbo.tblArticulos a ON a.Articulo = d.Articulo
    WHERE v.FechaMov >= ? AND v.FechaMov < ? AND v.Estatus = 'CONCLUIDO'
    GROUP BY v.Empresa"""


def _filtro_sin_fecha() -> str:
    return f"v.TipoMov IN ({_lista(tipos_venta())}) AND ISNULL(d.Unidad, '') NOT IN ({_lista(UNIDADES_FUERA)})"


def falta_conexion() -> list[str]:
    cfg = configuracion()
    nombres = {"smnbi_servidor": "servidor de SMNBI", "smnbi_usuario": "usuario de SMNBI", "smnbi_contrasena": "contraseña de SMNBI"}
    return [texto for clave, texto in nombres.items() if not getattr(cfg, clave)]


def conectar():
    """Conexión de solo lectura a SMNBI. La contraseña no se escribe en ningún mensaje."""
    import pyodbc

    cfg = configuracion()
    if falta := falta_conexion():
        raise ErrorEtl("Falta capturar en Configuración: " + ", ".join(falta) + ".")
    odbc = (f"DRIVER={{{cfg.bd_driver}}};SERVER={cfg.smnbi_servidor},{cfg.smnbi_puerto};DATABASE={cfg.smnbi_base};"
            f"UID={cfg.smnbi_usuario};PWD={cfg.smnbi_contrasena};TrustServerCertificate=yes;Encrypt=yes;ApplicationIntent=ReadOnly")
    try:
        conexion = pyodbc.connect(odbc, timeout=15, readonly=True)
    except pyodbc.Error as e:
        raise ErrorEtl(f"No se pudo conectar a SMNBI ({cfg.smnbi_servidor}): {_sin_secretos(e)}") from None
    conexion.timeout = 30 * 60  # una consulta de un mes puede tardar minutos
    return conexion


def _sin_secretos(e: Exception) -> str:
    texto = str(e.args[-1] if getattr(e, "args", None) else e)
    if clave := configuracion().smnbi_contrasena:
        texto = texto.replace(clave, "****")
    return texto[:300]


def probar_conexion() -> dict:
    """Para el botón «Probar conexión»: confirma acceso y cuenta qué hay en las tablas que usa el ETL."""
    with conectar() as conexion:
        cursor = conexion.cursor()
        cursor.execute("SELECT MIN(FechaMov), MAX(FechaMov), COUNT_BIG(*) FROM dbo.tblVenta")
        desde, hasta, ventas = cursor.fetchone()
        cursor.execute("SELECT COUNT_BIG(*) FROM dbo.tblArticulos")
        articulos = cursor.fetchone()[0]
    return {"desde": desde.date() if desde else None, "hasta": hasta.date() if hasta else None,
            "ventas": int(ventas or 0), "articulos": int(articulos or 0)}


# ---------------------------------------------------------------- transformar

def _decimal(valor, nombre: str, lugares: str) -> Decimal:
    if valor is None or valor == "" or valor == "NULL":
        return Decimal(0)
    try:
        n = Decimal(str(valor).strip())
    except InvalidOperation:
        raise ValueError(f"{nombre} no es número") from None
    if not n.is_finite() or abs(n) > Decimal("99999999999"):
        raise ValueError(f"{nombre} fuera de rango")
    return n.quantize(Decimal(lugares), rounding=ROUND_HALF_UP)


def _fecha(valor) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor).strip()[:10])


def lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def inicio_mes(d: date) -> date:
    return d.replace(day=1)


def siguiente_mes(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def transformar(filas: Iterable[tuple], mes: date, carga_id: int) -> tuple[list[tuple], int, list[str]]:
    """Filas de SMNBI o del CSV (orden de COLUMNAS) -> tuplas para venta_semanal. Devuelve (filas, fuera, motivos)."""
    salida, fuera, motivos = [], 0, []
    primera_semana, fin = lunes(mes), siguiente_mes(mes)
    for i, f in enumerate(filas, 1):
        try:
            sku = str(f[0] or "").strip()
            tienda = str(f[1] or "").strip() or "SIN"
            semana = _fecha(f[2])
            empresa = str(f[3] or "").strip()
            if not sku or not empresa:
                raise ValueError("sin artículo o empresa")
            if len(sku) > 80 or len(tienda) > 10 or len(empresa) > 5:
                raise ValueError("un código es demasiado largo")
            if semana.weekday() != 0 or not primera_semana <= semana < fin:
                raise ValueError(f"la semana {semana} no es lunes o no es de {mes:%Y-%m}")
            piezas = _decimal(f[4], "piezas", "0.001")
            devueltas = _decimal(f[5], "piezas devueltas", "0.001")
            bruto = _decimal(f[6], "importe bruto", "0.01")
            descuento = _decimal(f[7], "descuento", "0.01")
            costo = _decimal(f[8], "costo", "0.01")
            tickets = int(_decimal(f[9], "tickets", "1"))
        except (ValueError, TypeError, IndexError) as e:
            fuera += 1
            if len(motivos) < 5:
                motivos.append(f"Fila {i}: {e}")
            continue
        salida.append((mes, sku, tienda, semana, empresa, piezas, devueltas, bruto, descuento, bruto - descuento, costo,
                       tickets, carga_id))
    return salida, fuera, motivos


def leer_csv(contenido: bytes) -> list[tuple]:
    """CSV de SSMS con o sin encabezados; separador coma, punto y coma o tabulador. NULL cuenta como vacío."""
    if contenido[:2] in (b"\xff\xfe", b"\xfe\xff"):  # SSMS puede guardar en «Unicode» (UTF-16)
        texto = contenido.decode("utf-16")
    else:
        texto = contenido.decode("utf-8-sig", errors="replace")
    muestra = texto[:4096]
    separador = max((",", ";", "\t"), key=muestra.count)
    lector = csv.reader(io.StringIO(texto), delimiter=separador)
    filas = [f for f in lector if any(c.strip() for c in f)]
    if not filas:
        raise ErrorEtl("El archivo está vacío.")
    encabezado = [c.strip().lower() for c in filas[0]]
    if "sku" in encabezado:
        faltan = [c for c in COLUMNAS if c not in encabezado]
        if faltan:
            raise ErrorEtl("Al archivo le faltan columnas: " + ", ".join(faltan) + ".")
        pos = [encabezado.index(c) for c in COLUMNAS]
        return [tuple(f[p] if p < len(f) else None for p in pos) for f in filas[1:]]
    if len(filas[0]) < len(COLUMNAS):
        raise ErrorEtl(f"El archivo trae {len(filas[0])} columnas y se esperan {len(COLUMNAS)} "
                       "(las de consulta_venta_semanal.sql, en el mismo orden).")
    return [tuple(f[: len(COLUMNAS)]) for f in filas]


def mes_del_archivo(filas: list[tuple]) -> date:
    """El mes de un CSV de un mes: el de su última semana (todo mes tiene al menos un lunes)."""
    semanas = []
    for f in filas:
        try:
            semanas.append(_fecha(f[2]))
        except (ValueError, TypeError, IndexError):
            continue
    if not semanas:
        raise ErrorEtl("No se encontró ninguna semana válida en el archivo.")
    return inicio_mes(max(semanas))


# ---------------------------------------------------------------- avance (sesión aparte)

def _sesion() -> Session:
    from core.bd import _fabrica

    return _fabrica()()


def _actualizar(carga_id: int, **campos) -> bool:
    """Guarda el avance al momento y devuelve si alguien pidió detener."""
    with _sesion() as s:
        c = s.get(Carga, carga_id)
        for k, v in campos.items():
            setattr(c, k, v)
        s.commit()
        return bool(c.detener)


class Paso:
    """Registra un paso de un mes en datos.carga_paso y en la carga."""

    def __init__(self, carga_id: int, mes: date | None, paso: str):
        self.carga_id, self.mes, self.paso, self.filas, self.nota = carga_id, mes, paso, None, None

    def __enter__(self):
        if _actualizar(self.carga_id, paso=self.paso, mes_actual=self.mes):
            raise Detenida
        with _sesion() as s:
            p = CargaPaso(carga_id=self.carga_id, mes=self.mes, paso=self.paso, estado="en_curso", inicio_en=ahora())
            s.add(p)
            s.commit()
            self.paso_id = p.paso_id
        return self

    def __exit__(self, tipo, error, _):
        estado = "hecho" if tipo is None else "detenido" if tipo is Detenida else "fallido"
        with _sesion() as s:
            p = s.get(CargaPaso, self.paso_id)
            p.estado, p.filas, p.fin_en = estado, self.filas, ahora()
            p.nota = (self.nota or (str(error) if error and tipo is not Detenida else None) or None)
            if p.nota:
                p.nota = p.nota[:500]
            s.commit()
        return False


# ---------------------------------------------------------------- un mes

def _cargar_mes(bd: Session, carga_id: int, mes: date, filas: list[tuple]) -> int:
    """Borra e inserta el mes en una sola transacción. Usa el envío por lotes de pyodbc (miles de filas por viaje)."""
    bd.execute(delete(VentaSemanal).where(VentaSemanal.mes == mes))
    cursor = bd.connection().connection.driver_connection.cursor()
    cursor.fast_executemany = True
    sql = ("INSERT INTO datos.venta_semanal (mes, sku, tienda, semana, empresa, piezas, piezas_devueltas, importe_bruto, "
           "descuento, importe, costo, tickets, carga_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)")
    for i in range(0, len(filas), LOTE):
        cursor.executemany(sql, filas[i:i + LOTE])
        if _actualizar(carga_id, creados=_cargados_antes(carga_id) + min(i + LOTE, len(filas))):
            raise Detenida
    cursor.close()
    return len(filas)


_BASE_CREADOS: dict[int, int] = {}  # filas cargadas en meses anteriores de la carga, para mostrar el total


def _cargados_antes(carga_id: int) -> int:
    return _BASE_CREADOS.get(carga_id, 0)


def _totales_cargados(bd: Session, mes: date) -> dict[str, tuple[Decimal, Decimal]]:
    filas = bd.execute(select(VentaSemanal.empresa, func.sum(VentaSemanal.importe),
                              func.sum(VentaSemanal.piezas - VentaSemanal.piezas_devueltas))
                       .where(VentaSemanal.mes == mes).group_by(VentaSemanal.empresa)).all()
    return {e: (Decimal(i or 0), Decimal(p or 0)) for e, i, p in filas}


def _cuadra(origen: Decimal | None, cargado: Decimal) -> bool | None:
    if origen is None:
        return None
    base = max(abs(origen), Decimal(1))
    return abs(origen - cargado) / base <= TOLERANCIA


def _cuadrar(bd: Session, carga_id: int, mes: date, origen: dict[str, tuple[Decimal, Decimal, int]], fuera_archivo: int | None) -> bool:
    """Guarda el cuadre del mes por empresa. `origen`: empresa -> (importe, piezas, renglones fuera)."""
    cargados = _totales_cargados(bd, mes)
    todo_cuadra = True
    for empresa in sorted(set(origen) | set(cargados)):
        imp_o, pz_o, fuera = origen.get(empresa, (Decimal(0), Decimal(0), 0))
        imp_c, pz_c = cargados.get(empresa, (Decimal(0), Decimal(0)))
        cuadra = bool(_cuadra(imp_o, imp_c) and _cuadra(pz_o, pz_c))
        todo_cuadra &= cuadra
        bd.add(VentaCuadre(carga_id=carga_id, mes=mes, empresa=empresa, importe_origen=imp_o.quantize(Decimal("0.01")),
                           importe_cargado=imp_c, piezas_origen=pz_o.quantize(Decimal("0.001")), piezas_cargadas=pz_c,
                           renglones_fuera=fuera if fuera_archivo is None else fuera_archivo, cuadra=cuadra))
    bd.commit()
    return todo_cuadra


def _mes_desde_smnbi(bd: Session, conexion, carga: Carga, mes: date) -> tuple[bool, int]:
    cid = carga.carga_id
    fin = siguiente_mes(mes)
    with Paso(cid, mes, "extraer") as p:
        cursor = conexion.cursor()
        cursor.execute(sql_ventas(), datetime.combine(mes, datetime.min.time()), datetime.combine(fin, datetime.min.time()))
        crudas, leidas = [], 0
        while lote := cursor.fetchmany(LOTE):
            crudas.extend(tuple(f) for f in lote)
            leidas += len(lote)
            if _actualizar(cid, leidos=_LEIDOS.get(cid, 0) + leidas):
                raise Detenida
        _LEIDOS[cid] = _LEIDOS.get(cid, 0) + leidas
        p.filas = leidas
    with Paso(cid, mes, "transformar") as p:
        filas, fuera, motivos = transformar(crudas, mes, cid)
        p.filas, p.nota = len(filas), ("; ".join(motivos) if motivos else None)
        _FUERA[cid] = _FUERA.get(cid, 0) + fuera
        _actualizar(cid, invalidos=_FUERA[cid])
    with Paso(cid, mes, "cargar") as p:
        p.filas = _cargar_mes(bd, cid, mes, filas)
        bd.commit()
        _BASE_CREADOS[cid] = _cargados_antes(cid) + p.filas
    with Paso(cid, mes, "cuadrar") as p:
        cursor = conexion.cursor()
        cursor.execute(sql_cuadre(), datetime.combine(mes, datetime.min.time()), datetime.combine(fin, datetime.min.time()))
        origen = {str(e).strip(): (Decimal(str(i or 0)), Decimal(str(z or 0)), int(n or 0)) for e, i, z, n in cursor.fetchall()}
        cuadra = _cuadrar(bd, cid, mes, origen, None)
        p.nota = "Cuadra con SMNBI" if cuadra else "No cuadra con SMNBI"
    return cuadra, fuera


_LEIDOS: dict[int, int] = {}
_FUERA: dict[int, int] = {}


# ---------------------------------------------------------------- cargas

def meses_de(desde: date, hasta: date) -> list[date]:
    meses, m = [], inicio_mes(desde)
    while m <= hasta:
        meses.append(m)
        m = siguiente_mes(m)
    return meses


def meses_a_cargar(bd: Session, hoy: date | None = None) -> list[date]:
    """Primera carga: desde etl_primer_mes hasta el mes en curso. Después: el mes en curso y los anteriores que diga
    etl_meses_refresco, más cualquier mes que nunca se haya cargado bien."""
    cfg = configuracion()
    hoy = hoy or date.today()
    primero = date.fromisoformat(cfg.etl_primer_mes + "-01")
    todos = meses_de(primero, inicio_mes(hoy))
    cargados = set(bd.scalars(select(VentaCuadre.mes).distinct()))
    recientes = set(todos[-cfg.etl_meses_refresco:])
    return [m for m in todos if m not in cargados or m in recientes]


def en_curso(bd: Session) -> Carga | None:
    return bd.scalars(select(Carga).where(Carga.fuente == FUENTE, Carga.estado == "en_curso")).first()


def iniciar(bd: Session, disparada_por: str, usuario_id: int | None, meses: list[date], archivo: str | None = None) -> Carga | None:
    if en_curso(bd) or not meses:
        return None
    carga = Carga(fuente=FUENTE, disparada_por=disparada_por, usuario_id=usuario_id, estado="en_curso", inicio_en=ahora(),
                  desde=meses[0], hasta=meses[-1], meses_total=len(meses), meses_hechos=0, paso="conectar", archivo=archivo,
                  detener=False)
    bd.add(carga)
    bd.commit()
    return carga


def _terminar(bd: Session, carga_id: int, estado: str, error: str | None = None) -> None:
    bd.rollback()
    c = bd.get(Carga, carga_id)
    bd.refresh(c)
    c.estado, c.fin_en, c.completa = estado, ahora(), estado == "completa"
    c.paso = None if estado == "completa" else c.paso
    if error:
        c.error = error[:1000]
    bd.commit()
    for d in (_LEIDOS, _FUERA, _BASE_CREADOS):
        d.pop(carga_id, None)


def ejecutar(bd: Session, carga_id: int, meses: list[date]) -> Carga:
    """Corre una carga desde SMNBI mes por mes."""
    no_cuadran = []
    try:
        with Paso(carga_id, None, "conectar") as p:
            conexion = conectar()
            p.nota = f"{configuracion().smnbi_servidor} · {configuracion().smnbi_base}"
        with conexion:
            for i, mes in enumerate(meses):
                cuadra, _ = _mes_desde_smnbi(bd, conexion, bd.get(Carga, carga_id), mes)
                if not cuadra:
                    no_cuadran.append(mes)
                if _actualizar(carga_id, meses_hechos=i + 1):
                    raise Detenida
    except Detenida:
        _terminar(bd, carga_id, "detenida", "Se detuvo a petición. Los meses que ya terminaron quedaron cargados.")
        return bd.get(Carga, carga_id)
    except ErrorEtl as e:
        _terminar(bd, carga_id, "fallida", str(e))
        _avisar(bd, carga_id, f"La carga de ventas falló: {e}")
        return bd.get(Carga, carga_id)
    except Exception as e:  # noqa: BLE001 - cualquier error deja la carga cerrada y avisada
        log.exception("ETL de ventas: la carga %s falló", carga_id)
        _terminar(bd, carga_id, "fallida", f"Error inesperado: {_sin_secretos(e)}")
        _avisar(bd, carga_id, "La carga de ventas falló por un error inesperado. El detalle está en la carga.")
        return bd.get(Carga, carga_id)
    _cerrar_bien(bd, carga_id, no_cuadran)
    return bd.get(Carga, carga_id)


def _cerrar_bien(bd: Session, carga_id: int, no_cuadran: list[date]) -> None:
    if no_cuadran:
        meses = ", ".join(f"{m:%Y-%m}" for m in no_cuadran)
        _terminar(bd, carga_id, "completa", f"No cuadra: {meses}. Revisa el cuadre antes de usar esos meses.")
        _avisar(bd, carga_id, f"La carga de ventas terminó pero no cuadra en {meses}.")
    else:
        _terminar(bd, carga_id, "completa")


def ejecutar_archivo(bd: Session, carga_id: int, filas: list[tuple], mes: date) -> Carga:
    """Carga un mes desde el CSV de consulta_venta_semanal.sql. El cuadre es contra lo que suma el archivo."""
    try:
        with Paso(carga_id, mes, "extraer") as p:
            p.filas = len(filas)
            p.nota = "Leído del archivo"
            _actualizar(carga_id, leidos=len(filas))
        with Paso(carga_id, mes, "transformar") as p:
            limpias, fuera, motivos = transformar(filas, mes, carga_id)
            p.filas, p.nota = len(limpias), ("; ".join(motivos) if motivos else None)
            _actualizar(carga_id, invalidos=fuera)
            if not limpias:
                raise ErrorEtl("Ninguna fila del archivo sirvió. " + ("; ".join(motivos) if motivos else ""))
        with Paso(carga_id, mes, "cargar") as p:
            p.filas = _cargar_mes(bd, carga_id, mes, limpias)
            bd.commit()
        with Paso(carga_id, mes, "cuadrar") as p:
            origen: dict[str, tuple[Decimal, Decimal, int]] = {}
            for f in limpias:
                imp, pz, n = origen.get(f[4], (Decimal(0), Decimal(0), 0))
                origen[f[4]] = (imp + f[9], pz + f[5] - f[6], n)
            cuadra = _cuadrar(bd, carga_id, mes, origen, fuera)
            p.nota = "Cuadra con el archivo" if cuadra else "No cuadra con el archivo"
        _actualizar(carga_id, meses_hechos=1)
    except Detenida:
        _terminar(bd, carga_id, "detenida", "Se detuvo a petición.")
        return bd.get(Carga, carga_id)
    except ErrorEtl as e:
        _terminar(bd, carga_id, "fallida", str(e))
        return bd.get(Carga, carga_id)
    except Exception as e:  # noqa: BLE001
        log.exception("ETL de ventas: la carga con archivo %s falló", carga_id)
        _terminar(bd, carga_id, "fallida", f"Error inesperado: {str(e)[:300]}")
        return bd.get(Carga, carga_id)
    _cerrar_bien(bd, carga_id, [] if cuadra else [mes])
    return bd.get(Carga, carga_id)


def en_hilo(trabajo: Callable[[Session], object]) -> None:
    def correr():
        with _sesion() as bd:
            trabajo(bd)

    threading.Thread(target=correr, daemon=True, name="etl-ventas").start()


def pedir_detener(bd: Session) -> Carga | None:
    if c := en_curso(bd):
        c.detener = True
        bd.commit()
    return c


def cerrar_huerfanas(bd: Session) -> int:
    """Al arrancar la API: una carga del ETL «en curso» murió con el reinicio. Lo ya cargado por mes quedó completo."""
    abiertas = bd.scalars(select(Carga).where(Carga.fuente == FUENTE, Carga.estado == "en_curso")).all()
    for c in abiertas:
        c.estado, c.fin_en = "fallida", ahora()
        c.error = "La plataforma se reinició a media carga. Los meses que alcanzaron a terminar quedaron cargados; vuelve a correrla."
    bd.commit()
    return len(abiertas)


# ---------------------------------------------------------------- avisos y programa

def _encargados(bd: Session) -> list[int]:
    return list(bd.scalars(
        select(Usuario.usuario_id).distinct()
        .join(UsuarioRol, UsuarioRol.usuario_id == Usuario.usuario_id)
        .join(RolPermiso, RolPermiso.rol_id == UsuarioRol.rol_id)
        .join(Permiso, Permiso.permiso_id == RolPermiso.permiso_id)
        .where(Permiso.codigo == CORRER, Usuario.tipo == "interno", Usuario.estatus == "activo")))


def _avisar(bd: Session, carga_id: int, mensaje: str) -> None:
    from nucleo.notificaciones import notificar

    for uid in _encargados(bd):
        notificar(bd, uid, "ETL de ventas", mensaje, liga="/datos/etl", clave=f"etl-{carga_id}")
    bd.commit()


def revisar_programa(bd: Session) -> Carga | None:
    """Lo llama el programador cada minuto: una carga al día en los días y la hora elegidos, si está prendido y conectado."""
    cfg = configuracion()
    if not cfg.etl_activo or falta_conexion() or en_curso(bd):
        return None
    local = datetime.now(ZoneInfo(cfg.catalogo_zona_horaria))
    dias = {d.strip() for d in cfg.etl_dias_semana.split(",")}
    if local.hour < cfg.etl_hora or str(local.isoweekday()) not in dias:
        return None
    inicio_dia = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    if bd.scalar(select(func.count()).select_from(Carga).where(
            Carga.fuente == FUENTE, Carga.disparada_por == "programador", Carga.inicio_en >= inicio_dia)):
        return None  # una por día; si falló, avisa y se corre a mano
    meses = meses_a_cargar(bd, local.date())
    if carga := iniciar(bd, "programador", None, meses):
        cid = carga.carga_id
        en_hilo(lambda s: ejecutar(s, cid, meses))
    return carga
