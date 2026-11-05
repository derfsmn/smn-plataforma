# Saca las 6 tablas de SMNBI para el semáforo de productos en CSV, de una sola vez (pedido de Diego, 2026-10-27).
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

# 1. Artículos: 14 columnas
Exportar "articulos" @'
SELECT Articulo, Descripcion, Departamento, Rama, Categoria, SubCategoria, Segmento, Fabricante, Proveedor,
       Marca, TipoCompra, Clasificacion, Estatus, Codigo
FROM dbo.tblArticulos
ORDER BY Articulo;
'@

# 2. Tiendas y almacenes: 14 columnas
Exportar "tiendas" @'
SELECT Almacen, Nombre, Poblacion, Estado, CodigoPostal, Grupo, Ruta, Sucursal, Estatus, Region, Categoria,
       CONVERT(char(10), FechaApertura, 23), MapaLatitud, MapaLongitud
FROM dbo.tblAlmacenes
ORDER BY Almacen;
'@

# 3. Proveedores: 8 columnas
Exportar "proveedores" @'
-- Sin RFC: no se necesita y puede ser de una persona física
SELECT Proveedor, Nombre, Estatus, Condicion, Descuento, DescuentoAdicional, DiasEntrega, Penalizacion
FROM dbo.tblProveedores
ORDER BY Proveedor;
'@

# 4. Compras por orden: 13 columnas
Exportar "compras" @'
-- Una fila por orden de compra con lo que llegó (Entrada Compra), se perdió o se rechazó, ligados por Origen/OrigenID
WITH o AS (
    SELECT ID, Empresa, NumMov, Proveedor, Almacen, FechaMov, Estatus FROM dbo.tblCompra
    WHERE TipoMov = 'Orden Compra' AND Estatus IN ('CONCLUIDO', 'PENDIENTE')
), pedido AS (
    SELECT d.ID, SUM(d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1)) AS piezas, SUM(d.Cantidad * d.Costo) AS importe
    FROM dbo.tblCompraD d JOIN o ON o.ID = d.ID GROUP BY d.ID
), mov AS (
    SELECT c.Empresa, c.OrigenID, c.TipoMov, MIN(c.FechaMov) AS primera, MAX(c.FechaMov) AS ultima,
           SUM(ABS(d.Cantidad) * ISNULL(NULLIF(d.Factor, 0), 1)) AS piezas
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
ORDER BY o.Empresa, o.NumMov;
'@

# 5. Costo de compra por artículo: 7 columnas
Exportar "costos" @'
-- Costo por pieza sin IVA de las entradas de compra: la última y el promedio de los últimos 12 meses
WITH e AS (
    SELECT d.Articulo, c.Proveedor, c.FechaMov, d.Costo / ISNULL(NULLIF(d.Factor, 0), 1) AS costo_pieza, d.Cantidad * ISNULL(NULLIF(d.Factor, 0), 1) AS piezas,
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
ORDER BY u.Articulo;
'@

# 6. Inventario: 6 columnas
Exportar "inventario" @'
SELECT CONVERT(char(10), FechaCorte, 23), Empresa, Almacen, Articulo, Existencia, CostoPromedio
FROM dbo.tblInventario
ORDER BY Almacen, Articulo;
'@

Write-Host ""
Write-Host "Listo. Sube los archivos de $Carpeta en Centro de datos > ETL, en el orden de arriba."
