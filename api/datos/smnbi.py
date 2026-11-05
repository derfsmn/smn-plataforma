"""Tablas de SMNBI que necesita el semáforo de productos, cargadas desde el CSV que sale de SSMS (Diego, 2026-10-26).

Cada fuente tiene su consulta (la misma que va en docs/sistemas/consultas_catalogos_smnbi.sql) y su carga:
- articulos: al catálogo de productos como fuente ETL (completa lo que no trae el API: subcategoría, estatus...).
- tiendas, proveedores, compras (una fila por orden) y costos (por artículo): se reemplaza la tabla completa.
- inventario: se reemplaza la fecha de corte que trae el archivo; las fotos de otras fechas se quedan.

Reglas de SMNBI que usan las consultas (revision_smnbi_2026-10-26.md): fechas como 'AAAAMMDD' (el servidor está en
español), piezas = Cantidad × Factor, costos por pieza sin IVA, solo movimientos CONCLUIDO.
"""
import csv
import io
import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable

from sqlalchemy import delete, func, select, true
from sqlalchemy.orm import Session

from datos import catalogo
from datos.modelos import Carga, CompraOrden, CostoArticulo, Inventario, ProductoFuente, Proveedor, Tienda
from nucleo.modelos import ahora

log = logging.getLogger("smn.datos.smnbi")

LOTE = 5000
CATALOGO_LOTE = 500


class ErrorArchivo(ValueError):
    pass


@dataclass(frozen=True)
class Fuente:
    codigo: str
    nombre: str
    carga: str  # datos.carga.fuente
    tablas: tuple[str, ...]
    columnas: tuple[str, ...]
    consulta: str
    nota: str


FACTOR = "ISNULL(NULLIF(d.Factor, 0), 1)"

FUENTES: dict[str, Fuente] = {f.codigo: f for f in (
    Fuente("articulos", "Artículos", "SMNBI_ARTICULOS", ("tblArticulos",),
           tuple(c for c, _ in catalogo.COLUMNAS_ETL),
           """SELECT Articulo, Descripcion, Departamento, Rama, Categoria, SubCategoria, Segmento, Fabricante, Proveedor,
       Marca, TipoCompra, Clasificacion, Estatus, Codigo
FROM dbo.tblArticulos
ORDER BY Articulo;""",
           "Completa el catálogo: subcategoría, estatus (ALTA o DESCONTINUADO), proveedor y fabricante."),
    Fuente("tiendas", "Tiendas y almacenes", "SMNBI_TIENDAS", ("tblAlmacenes",),
           ("almacen", "nombre", "poblacion", "estado", "codigo_postal", "grupo", "ruta", "sucursal", "estatus", "region",
            "categoria", "fecha_apertura", "latitud", "longitud"),
           """SELECT Almacen, Nombre, Poblacion, Estado, CodigoPostal, Grupo, Ruta, Sucursal, Estatus, Region, Categoria,
       CONVERT(char(10), FechaApertura, 23), MapaLatitud, MapaLongitud
FROM dbo.tblAlmacenes
ORDER BY Almacen;""",
           "Nombre, región, categoría (AA a E; MAY es mayoreo) y apertura de cada almacén de la venta."),
    Fuente("proveedores", "Proveedores", "SMNBI_PROVEEDORES", ("tblProveedores",),
           ("proveedor", "nombre", "estatus", "condicion", "descuento", "descuento_adicional", "dias_entrega", "penalizacion",
            "agente", "rfc"),
           """-- Agente y RFC se traen aunque vengan vacíos: sirven para filtrar (Diego, 2026-11-03)
SELECT Proveedor, Nombre, Estatus, Condicion, Descuento, DescuentoAdicional, DiasEntrega, Penalizacion, Agente, RFC
FROM dbo.tblProveedores
ORDER BY Proveedor;""",
           "Días de entrega que promete cada proveedor, condición de pago, descuentos, agente y RFC."),
    Fuente("compras", "Compras por orden", "SMNBI_COMPRAS", ("tblCompra", "tblCompraD"),
           ("empresa", "orden", "proveedor", "almacen", "fecha_orden", "estatus", "piezas_pedidas", "importe_pedido",
            "primera_entrada", "ultima_entrada", "piezas_recibidas", "piezas_perdidas", "piezas_rechazadas"),
           f"""-- Una fila por orden de compra con lo que llegó (Entrada Compra), se perdió o se rechazó, ligados por Origen/OrigenID
WITH o AS (
    SELECT ID, Empresa, NumMov, Proveedor, Almacen, FechaMov, Estatus FROM dbo.tblCompra
    WHERE TipoMov = 'Orden Compra' AND Estatus IN ('CONCLUIDO', 'PENDIENTE')
), pedido AS (
    SELECT d.ID, SUM(d.Cantidad * {FACTOR}) AS piezas, SUM(d.Cantidad * d.Costo) AS importe
    FROM dbo.tblCompraD d JOIN o ON o.ID = d.ID GROUP BY d.ID
), mov AS (
    SELECT c.Empresa, c.OrigenID, c.TipoMov, MIN(c.FechaMov) AS primera, MAX(c.FechaMov) AS ultima,
           SUM(ABS(d.Cantidad) * {FACTOR}) AS piezas
    FROM dbo.tblCompra c JOIN dbo.tblCompraD d ON d.ID = c.ID
    WHERE c.Origen = 'Orden Compra' AND c.Estatus = 'CONCLUIDO'
      AND c.TipoMov IN ('Entrada Compra', 'Compra Perdida', 'Compra Rechazada')
    GROUP BY c.Empresa, c.OrigenID, c.TipoMov
)
SELECT o.Empresa, o.NumMov, o.Proveedor, o.Almacen, CONVERT(char(10), o.FechaMov, 23), o.Estatus,
       pedido.piezas, pedido.importe,
       CONVERT(char(10), e.primera, 23), CONVERT(char(10), e.ultima, 23),
       ISNULL(e.piezas, 0), ISNULL(p.piezas, 0), ISNULL(r.piezas, 0)
FROM o
LEFT JOIN pedido ON pedido.ID = o.ID
LEFT JOIN mov e ON e.Empresa = o.Empresa AND e.OrigenID = o.NumMov AND e.TipoMov = 'Entrada Compra'
LEFT JOIN mov p ON p.Empresa = o.Empresa AND p.OrigenID = o.NumMov AND p.TipoMov = 'Compra Perdida'
LEFT JOIN mov r ON r.Empresa = o.Empresa AND r.OrigenID = o.NumMov AND r.TipoMov = 'Compra Rechazada'
ORDER BY o.Empresa, o.NumMov;""",
           "Cada orden de compra con lo que llegó y cuándo: tiempo de entrega y cumplimiento real de cada proveedor."),
    Fuente("costos", "Costo de compra por artículo", "SMNBI_COSTOS", ("tblCompra", "tblCompraD"),
           ("sku", "proveedor", "fecha_ultima", "costo_ultimo", "costo_12m", "piezas_12m", "compras_12m"),
           f"""-- Costo por pieza sin IVA de las entradas de compra: la última y el promedio de los últimos 12 meses
WITH e AS (
    SELECT d.Articulo, c.Proveedor, c.FechaMov, d.Costo / {FACTOR} AS costo_pieza, d.Cantidad * {FACTOR} AS piezas,
           ROW_NUMBER() OVER (PARTITION BY d.Articulo ORDER BY c.FechaMov DESC, c.ID DESC) AS n
    FROM dbo.tblCompra c JOIN dbo.tblCompraD d ON d.ID = c.ID
    WHERE c.TipoMov = 'Entrada Compra' AND c.Estatus = 'CONCLUIDO' AND d.Cantidad > 0 AND d.Costo > 0
), ultimos AS (
    SELECT Articulo, SUM(costo_pieza * piezas) / NULLIF(SUM(piezas), 0) AS costo, SUM(piezas) AS piezas, COUNT(*) AS compras
    FROM e WHERE FechaMov >= DATEADD(MONTH, -12, (SELECT MAX(FechaMov) FROM e))
    GROUP BY Articulo
)
SELECT u.Articulo, u.Proveedor, CONVERT(char(10), u.FechaMov, 23), u.costo_pieza, a.costo, a.piezas, a.compras
FROM e u LEFT JOIN ultimos a ON a.Articulo = u.Articulo
WHERE u.n = 1
ORDER BY u.Articulo;""",
           "Lo que nos cuesta cada artículo: la última compra y el promedio de 12 meses, por pieza y sin IVA."),
    Fuente("inventario", "Inventario", "SMNBI_INVENTARIO", ("tblInventario",),
           ("fecha_corte", "empresa", "almacen", "sku", "existencia", "costo_promedio"),
           """SELECT CONVERT(char(10), FechaCorte, 23), Empresa, Almacen, Articulo, Existencia, CostoPromedio
FROM dbo.tblInventario
ORDER BY Almacen, Articulo;""",
           "Existencia por almacén y artículo en la fecha de corte. Cada fecha se guarda aparte para ver quiebres después."),
)}


def consultas_sql() -> str:
    """El archivo para SSMS con todas las consultas (docs/sistemas/consultas_catalogos_smnbi.sql)."""
    partes = ["-- Tablas de SMNBI para el semáforo de productos (Centro de datos -> ETL -> Fuentes de Sistemas).",
              "-- SOLO LEEN. Corre cada consulta, guarda su resultado como CSV (clic derecho en la tabla > «Guardar resultados",
              "-- como...») y súbelo en la tarjeta de su fuente. Con o sin encabezados.", "", "USE SMNBI;", "SET NOCOUNT ON;"]
    for n, f in enumerate(FUENTES.values(), 1):
        partes += ["", f"-- {n}. {f.nombre} ({', '.join(f.tablas)}): {len(f.columnas)} columnas. {f.nota}", f.consulta]
    return "\n".join(partes) + "\n"


PLANTILLA_PS = r"""# Saca las 6 tablas de SMNBI para el semáforo de productos en CSV, de una sola vez (pedido de Diego, 2026-10-27).
# SOLO LEE. Se corre en el equipo que tiene acceso a SMNBI:
#   powershell -ExecutionPolicy Bypass -File exportar_smnbi.ps1 -Servidor NOMBRE_DEL_SERVIDOR
# Con usuario de SQL (pide la contraseña en pantalla, no se guarda):
#   powershell -ExecutionPolicy Bypass -File exportar_smnbi.ps1 -Servidor NOMBRE_DEL_SERVIDOR -Usuario TU_USUARIO
# Deja articulos.csv, tiendas.csv, proveedores.csv, compras.csv, costos.csv e inventario.csv en una carpeta nueva en
# Documentos. Cada uno se sube en su tarjeta de Centro de datos > ETL, en ese orden.
# Archivo generado por api/datos/smnbi.py (script_powershell): si cambia una consulta, se regenera.
param(
    [Parameter(Mandatory = $true)][string]$Servidor,
    [string]$Usuario,
    [string]$Base = "SMNBI",
    [string]$Carpeta = (Join-Path ([Environment]::GetFolderPath("MyDocuments")) ("SMNBI-" + (Get-Date -Format "yyyyMMdd-HHmm")))
)
$ErrorActionPreference = "Stop"
$inv = [Globalization.CultureInfo]::InvariantCulture

if ($Usuario) {
    $clave = Read-Host "Contraseña de $Usuario" -AsSecureString
    $plano = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($clave))
    $cadena = "Server=$Servidor;Database=$Base;User ID=$Usuario;Password=$plano;TrustServerCertificate=True;Application Name=Exportar SMNBI"
} else {
    $cadena = "Server=$Servidor;Database=$Base;Integrated Security=True;TrustServerCertificate=True;Application Name=Exportar SMNBI"
}
New-Item -ItemType Directory -Force -Path $Carpeta | Out-Null

function Valor($v) {
    if ($v -is [DBNull] -or $null -eq $v) { return "" }
    if ($v -is [datetime]) { return $v.ToString("yyyy-MM-dd", $inv) }
    if ($v -is [decimal] -or $v -is [double] -or $v -is [single]) { return $v.ToString($inv) }
    $t = ([string]$v).Trim()
    if ($t -match '[",\r\n]') { return '"' + $t.Replace('"', '""') + '"' }
    return $t
}

function Exportar($nombre, $consulta) {
    $archivo = Join-Path $Carpeta "$nombre.csv"
    Write-Host ("{0,-12} corriendo..." -f $nombre) -NoNewline
    $reloj = [Diagnostics.Stopwatch]::StartNew()
    $con = New-Object System.Data.SqlClient.SqlConnection $cadena
    $con.Open()
    try {
        $cmd = $con.CreateCommand()
        $cmd.CommandText = "SET NOCOUNT ON; SET DATEFORMAT ymd; " + $consulta
        $cmd.CommandTimeout = 0
        $lector = $cmd.ExecuteReader()
        $salida = New-Object System.IO.StreamWriter($archivo, $false, (New-Object System.Text.UTF8Encoding($true)))
        $n = 0
        try {
            $campos = New-Object object[] $lector.FieldCount
            while ($lector.Read()) {
                [void]$lector.GetValues($campos)
                $linea = foreach ($c in $campos) { Valor $c }
                $salida.WriteLine($linea -join ",")
                $n++
                if ($n % 50000 -eq 0) { Write-Host -NoNewline "." }
            }
        } finally { $salida.Close(); $lector.Close() }
    } finally { $con.Close() }
    Write-Host (" {0:N0} renglones en {1:N0} s -> {2}" -f $n, $reloj.Elapsed.TotalSeconds, $archivo)
}

__CONSULTAS__
Write-Host ""
Write-Host "Listo. Sube los archivos de $Carpeta en Centro de datos > ETL, en el orden de arriba."
"""


def script_powershell() -> str:
    """El script que saca las 6 tablas a CSV de una vez (docs/sistemas/exportar_smnbi.ps1)."""
    partes = []
    for n, f in enumerate(FUENTES.values(), 1):
        partes += [f"# {n}. {f.nombre}: {len(f.columnas)} columnas", f"Exportar \"{f.codigo}\" @'", f.consulta.strip(), "'@", ""]
    return PLANTILLA_PS.replace("__CONSULTAS__", "\n".join(partes))


# ---------------------------------------------------------------- lectura del CSV

def leer(contenido: bytes, fuente: Fuente) -> list[list[str | None]]:
    """CSV de SSMS con o sin encabezados; coma, punto y coma o tabulador. NULL y vacío cuentan como vacío."""
    if contenido[:2] in (b"\xff\xfe", b"\xfe\xff"):  # SSMS puede guardar en «Unicode» (UTF-16)
        texto = contenido.decode("utf-16")
    else:
        try:
            texto = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = contenido.decode("latin-1")
    muestra = texto[:4096]
    separador = max((",", ";", "\t"), key=muestra.count)
    filas = [f for f in csv.reader(io.StringIO(texto), delimiter=separador) if any(c.strip() for c in f)]
    if not filas:
        raise ErrorArchivo("El archivo está vacío.")
    n = len(fuente.columnas)
    if len(filas[0]) < n:
        raise ErrorArchivo(f"El archivo trae {len(filas[0])} columnas y para {fuente.nombre} se esperan {n}. "
                           "¿Es el resultado de la consulta de esta fuente?")
    primera = filas[0][0].strip().lower()
    if primera in (fuente.columnas[0], fuente.columnas[0].replace("_", ""), "articulo", "almacen", "proveedor", "empresa",
                   "fechacorte", "fecha_corte"):
        filas = filas[1:]  # encabezado
    return [[None if (v := c.strip()) == "" or v.upper() == "NULL" else v for c in f[:n]] for f in filas]


def _texto(v: str | None, largo: int) -> str | None:
    return " ".join(v.split())[:largo] or None if v else None


def _numero(v: str | None) -> Decimal | None:
    if v is None:
        return None
    try:
        n = Decimal(v.replace(",", "") if v.count(",") and v.count(".") else v.replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"«{v}» no es un número") from None
    if not n.is_finite():
        raise ValueError(f"«{v}» no es un número")
    return n


def _entero(v: str | None) -> int | None:
    n = _numero(v)
    return None if n is None else int(n)


def _fecha(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.strip()[:10]).date()
    except ValueError:
        raise ValueError(f"«{v}» no es una fecha AAAA-MM-DD") from None


def _redondear(n: Decimal | None, lugares: str) -> Decimal | None:
    return None if n is None else n.quantize(Decimal(lugares))


# ---------------------------------------------------------------- transformación por fuente

def _tienda(f: list) -> dict:
    if not f[0] or not f[1]:
        raise ValueError("almacén sin clave o sin nombre")
    return {"almacen": _texto(f[0], 10), "nombre": _texto(f[1], 100), "poblacion": _texto(f[2], 100),
            "estado": _texto(f[3], 30), "codigo_postal": _texto(f[4], 15), "grupo": _texto(f[5], 50), "ruta": _texto(f[6], 50),
            "sucursal": _entero(f[7]), "estatus": _texto(f[8], 15), "region": _texto(f[9], 50), "categoria": _texto(f[10], 50),
            "fecha_apertura": _fecha(f[11]), "latitud": float(f[12]) if f[12] else None,
            "longitud": float(f[13]) if f[13] else None}


def _proveedor(f: list) -> dict:
    if not f[0]:
        raise ValueError("proveedor sin clave")
    return {"proveedor": _texto(f[0], 10), "nombre": _texto(f[1], 100), "estatus": _texto(f[2], 15),
            "condicion": _texto(f[3], 30), "descuento": _texto(f[4], 30),
            "descuento_adicional": _redondear(_numero(f[5]), "0.0001"), "dias_entrega": _entero(f[6]),
            "penalizacion": _redondear(_numero(f[7]), "0.0001"), "agente": _texto(f[8], 10),
            "rfc": _texto((f[9] or "").replace(" ", "").replace("-", "").upper(), 15)}


def _compra(f: list) -> dict:
    if not f[0] or not f[1]:
        raise ValueError("orden sin empresa o sin número")
    fecha = _fecha(f[4])
    if not fecha:
        raise ValueError("orden sin fecha")
    return {"empresa": _texto(f[0], 5), "orden": _texto(f[1], 20), "proveedor": _texto(f[2], 10), "almacen": _texto(f[3], 10),
            "fecha_orden": fecha, "estatus": _texto(f[5], 15), "piezas_pedidas": _redondear(_numero(f[6]), "0.001"),
            "importe_pedido": _redondear(_numero(f[7]), "0.01"), "primera_entrada": _fecha(f[8]),
            "ultima_entrada": _fecha(f[9]), "piezas_recibidas": _redondear(_numero(f[10]) or Decimal(0), "0.001"),
            "piezas_perdidas": _redondear(_numero(f[11]) or Decimal(0), "0.001"),
            "piezas_rechazadas": _redondear(_numero(f[12]) or Decimal(0), "0.001")}


def _costo(f: list) -> dict:
    if not f[0]:
        raise ValueError("costo sin artículo")
    return {"sku": _texto(f[0], 80), "proveedor": _texto(f[1], 10), "fecha_ultima": _fecha(f[2]),
            "costo_ultimo": _redondear(_numero(f[3]), "0.0001"), "costo_12m": _redondear(_numero(f[4]), "0.0001"),
            "piezas_12m": _redondear(_numero(f[5]), "0.001"), "compras_12m": _entero(f[6])}


def _inventario(f: list) -> dict:
    fecha = _fecha(f[0])
    if not fecha or not f[1] or not f[2] or not f[3]:
        raise ValueError("renglón sin fecha de corte, empresa, almacén o artículo")
    return {"fecha_corte": fecha, "empresa": _texto(f[1], 5), "almacen": _texto(f[2], 10), "sku": _texto(f[3], 80),
            "existencia": _redondear(_numero(f[4]) or Decimal(0), "0.001"),
            "costo_promedio": _redondear(_numero(f[5]), "0.0001")}


TABLAS = {"tiendas": (Tienda, _tienda, ("almacen",)), "proveedores": (Proveedor, _proveedor, ("proveedor",)),
          "compras": (CompraOrden, _compra, ("empresa", "orden")), "costos": (CostoArticulo, _costo, ("sku",)),
          "inventario": (Inventario, _inventario, ("fecha_corte", "empresa", "almacen", "sku"))}


def transformar(codigo: str, filas: list[list]) -> tuple[list[dict], int, list[str]]:
    """(filas listas, cuántas quedaron fuera, los primeros motivos). Una clave repetida cuenta como fuera."""
    _, convertir, llave = TABLAS[codigo]
    salida, vistas, fuera, motivos = [], set(), 0, []
    for i, f in enumerate(filas, 1):
        try:
            d = convertir(f)
            clave = tuple(d[k] for k in llave)
            if clave in vistas:
                raise ValueError("clave repetida en el archivo")
        except (ValueError, TypeError, IndexError) as e:
            fuera += 1
            if len(motivos) < 5:
                motivos.append(f"Renglón {i}: {e}")
            continue
        vistas.add(clave)
        salida.append(d)
    return salida, fuera, motivos


# ---------------------------------------------------------------- carga

def en_curso(bd: Session, fuente: Fuente) -> Carga | None:
    return bd.scalars(select(Carga).where(Carga.fuente == fuente.carga, Carga.estado == "en_curso")).first()


def iniciar(bd: Session, fuente: Fuente, usuario_id: int | None, archivo: str) -> Carga | None:
    if en_curso(bd, fuente):
        return None
    carga = Carga(fuente=fuente.carga, disparada_por="manual", usuario_id=usuario_id, estado="en_curso", inicio_en=ahora(),
                  archivo=archivo, paso="cargar", detener=False)
    bd.add(carga)
    bd.commit()
    return carga


def _insertar(bd: Session, modelo, filas: list[dict], carga_id: int) -> None:
    """Envío por lotes de pyodbc, como el ETL de ventas."""
    if not filas:
        return
    columnas = [*filas[0], "carga_id"]
    tabla = f"{modelo.__table__.schema}.{modelo.__tablename__}"
    sql = f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({', '.join('?' * len(columnas))})"
    cursor = bd.connection().connection.driver_connection.cursor()
    cursor.fast_executemany = True
    for i in range(0, len(filas), LOTE):
        cursor.executemany(sql, [(*f.values(), carga_id) for f in filas[i:i + LOTE]])


def _cargar_tabla(bd: Session, codigo: str, carga: Carga, filas: list[list]) -> str:
    modelo = TABLAS[codigo][0]
    listas, fuera, motivos = transformar(codigo, filas)
    if not listas:
        raise ErrorArchivo("Ningún renglón sirvió. " + " ".join(motivos))
    if codigo == "inventario":  # se reemplaza solo la fecha de corte del archivo
        fechas = sorted({f["fecha_corte"] for f in listas})
        bd.execute(delete(modelo).where(modelo.fecha_corte.in_(fechas)))
        nota = "Corte del " + ", ".join(f"{d:%d/%m/%Y}" for d in fechas) + "."
    else:
        bd.execute(delete(modelo))
        nota = ""
    _insertar(bd, modelo, listas, carga.carga_id)
    carga.leidos, carga.creados, carga.invalidos = len(filas), len(listas), fuera
    return (nota + (" Fuera: " + " ".join(motivos) if motivos else "")).strip()


def _cargar_articulos(bd: Session, carga: Carga, filas: list[list]) -> str:
    vistos: set[str] = set()
    for i in range(0, len(filas), CATALOGO_LOTE):
        catalogo.procesar(bd, carga, filas[i:i + CATALOGO_LOTE], vistos, fuente_producto="ETL")
    catalogo.marcar_ausentes(bd, carga, fuente_producto="ETL")
    return (f"{carga.creados} artículos nuevos en el catálogo, {carga.actualizados} actualizados, "
            f"{carga.sin_cambios} sin cambios.")


def ejecutar(bd: Session, carga_id: int, codigo: str, filas: list[list]) -> Carga:
    carga = bd.get(Carga, carga_id)
    try:
        nota = _cargar_articulos(bd, carga, filas) if codigo == "articulos" else _cargar_tabla(bd, codigo, carga, filas)
        carga.estado, carga.completa, carga.error = "completa", True, nota[:1000] or None
    except Exception as e:  # noqa: BLE001 - la carga queda fallida con el motivo
        log.exception("Falló la carga %s de SMNBI (%s)", carga_id, codigo)
        bd.rollback()
        carga = bd.get(Carga, carga_id)
        carga.estado = "fallida"
        carga.error = (str(e) if isinstance(e, (ErrorArchivo, ValueError)) else f"Error inesperado: {e.__class__.__name__}")[:1000]
    carga.fin_en, carga.paso = ahora(), None
    bd.commit()
    return carga


def en_hilo(trabajo: Callable[[Session], object]) -> None:
    from core.bd import _fabrica

    def correr():
        with _fabrica()() as bd:
            trabajo(bd)

    threading.Thread(target=correr, daemon=True, name="smnbi-carga").start()


def cerrar_huerfanas(bd: Session) -> int:
    filas = bd.scalars(select(Carga).where(Carga.fuente.like("SMNBI[_]%"), Carga.estado == "en_curso")).all()
    for c in filas:
        c.estado, c.error, c.fin_en = "fallida", "La plataforma se reinició a media carga. Vuelve a subir el archivo.", ahora()
    bd.commit()
    return len(filas)


def resumen(bd: Session) -> dict[str, dict]:
    """Por fuente: la última carga y cuántas filas hay hoy."""
    conteos = {
        "articulos": bd.scalar(select(func.count()).select_from(ProductoFuente).where(
            ProductoFuente.fuente == "ETL", ProductoFuente.presente == true())),
        **{c: bd.scalar(select(func.count()).select_from(m)) for c, (m, _, _) in TABLAS.items()},
    }
    salida = {}
    for f in FUENTES.values():
        ultima = bd.scalars(select(Carga).where(Carga.fuente == f.carga).order_by(Carga.carga_id.desc())).first()
        salida[f.codigo] = {"filas": conteos[f.codigo] or 0, "ultima": ultima}
    return salida
