"""ETL de ventas contra una SMNBI simulada (base smnbi_prueba en el mismo SQL Server, datos ficticios)."""
import time
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.orm import Session

from core.bd import motor
from core.config import configuracion
from datos import etl
from datos.modelos import Carga, CargaPaso, VentaCuadre, VentaSemanal

BASE = "smnbi_prueba"
TABLAS = """
CREATE TABLE dbo.tblArticulos (Articulo varchar(20) NOT NULL, Descripcion varchar(100), Departamento varchar(20), Codigo varchar(30),
    IVA float, IEPS float, Estatus varchar(15));
CREATE TABLE dbo.tblVenta (ID int NOT NULL, Empresa varchar(5), TipoMov varchar(20), NumMov varchar(20), FechaMov datetime,
    Almacen varchar(10), Cliente varchar(10), Sucursal varchar(5), Estatus varchar(15), Importe money, DescuentoGlobal float);
CREATE TABLE dbo.tblVentaD (ID int NOT NULL, Renglon float NOT NULL, Articulo varchar(20), Cantidad float, Unidad varchar(50),
    Factor float, Precio float, Costo money, DescuentoLinea float);
"""
# (id, empresa, tipo, fecha, almacén (la tienda), estatus, [(artículo, cantidad, unidad, factor, precio, costo, descuento %)])
VENTAS = [
    (1, "PS", "Nota", "2026-09-01T10:00:00", "001", "CONCLUIDO",
     [("A1", 2, "PIEZA", 1, 100, 50, 5), ("A2", 1, "PAQUETE 3", 3, 90, 60, 0)]),  # 5 % de 200 = 10
    (2, "PS", "Nota", "2026-09-02T11:00:00", "001", "CONCLUIDO", [("A1", 1, "PIEZA", 1, 100, 50, 0), ("A1", 1, "FLETETV", 1, 50, 0, 0)]),
    # Como en SMNBI: la Nota Devolucion trae la cantidad en negativo
    (3, "PS", "Nota Devolucion", "2026-09-03T12:00:00", "001", "CONCLUIDO", [("A1", -1, "PIEZA", 1, 100, 50, 0)]),
    (4, "VCE", "Factura Electronica", "2026-09-08T09:00:00", "002", "CONCLUIDO", [("A1", 5, "PIEZA", 1, 100, 50, 0)]),
    (5, "VCE", "Nota", "2026-08-31T18:00:00", "002", "CONCLUIDO", [("A1", 4, "PIEZA", 1, 100, 50, 0)]),
    (6, "PS", "Nota", "2026-09-10T10:00:00", "001", "PROCESAR", [("A1", 9, "PIEZA", 1, 100, 50, 0)]),
    (7, "PS", "Nota", "2026-09-04T10:00:00", "001", "CONCLUIDO", [("ZZ", 1, "PIEZA", 1, 30, 10, 0)]),
    (8, "PS", "Nota", "2026-10-01T10:00:00", "001", "CONCLUIDO", [("A2", 1, "PIEZA", 1, 30, 20, 0)]),
]
AGO, SEP, OCT = date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)


@pytest.fixture
def smnbi(base_de_pruebas):
    cfg = configuracion()
    maestro = create_engine(cfg.url_bd("master"), isolation_level="AUTOCOMMIT")
    with maestro.connect() as c:
        c.execute(text(f"IF DB_ID('{BASE}') IS NOT NULL BEGIN ALTER DATABASE [{BASE}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
                       f"DROP DATABASE [{BASE}] END"))
        c.execute(text(f"CREATE DATABASE [{BASE}]"))
    with create_engine(cfg.url_bd(BASE)).begin() as c:
        for sentencia in TABLAS.strip().split(";"):
            if sentencia.strip():
                c.execute(text(sentencia))
        c.execute(text("INSERT INTO dbo.tblArticulos (Articulo, Descripcion, Estatus) VALUES ('A1', 'Colágeno', 'ALTA'), ('A2', 'Magnesio', 'ALTA')"))
        for vid, empresa, tipo, fecha, almacen, estatus, renglones in VENTAS:
            # Sucursal vacía, como en el 99 % de las ventas reales: la tienda sale del Almacen
            c.execute(text("INSERT INTO dbo.tblVenta (ID, Empresa, TipoMov, FechaMov, Almacen, Estatus) VALUES (:i, :e, :t, :f, :a, :x)"),
                      {"i": vid, "e": empresa, "t": tipo, "f": fecha, "a": almacen, "x": estatus})
            for n, (art, cant, unidad, factor, precio, costo, desc) in enumerate(renglones, 1):
                c.execute(text("INSERT INTO dbo.tblVentaD VALUES (:i, :n, :a, :c, :u, :fa, :p, :co, :d)"),
                          {"i": vid, "n": n, "a": art, "c": cant, "u": unidad, "fa": factor, "p": precio, "co": costo, "d": desc})
    antes = {k: getattr(cfg, k) for k in ("smnbi_servidor", "smnbi_puerto", "smnbi_base", "smnbi_usuario", "smnbi_contrasena",
                                          "etl_primer_mes", "etl_meses_refresco", "etl_factura_electronica")}
    cfg.smnbi_servidor, cfg.smnbi_puerto, cfg.smnbi_base = cfg.bd_servidor, cfg.bd_puerto, BASE
    cfg.smnbi_usuario, cfg.smnbi_contrasena = cfg.bd_usuario, cfg.mssql_sa_password
    cfg.etl_primer_mes, cfg.etl_meses_refresco, cfg.etl_factura_electronica = "2026-08", 2, False
    with Session(motor()) as bd:  # cada prueba empieza sin ventas ni cargas del ETL
        for tabla in (VentaSemanal, VentaCuadre, CargaPaso):
            bd.execute(delete(tabla))
        bd.execute(delete(Carga).where(Carga.fuente == etl.FUENTE))
        bd.commit()
    yield cfg
    for k, v in antes.items():
        setattr(cfg, k, v)


def _correr(bd: Session, meses: list[date]) -> Carga:
    carga = etl.iniciar(bd, "manual", None, meses)
    return etl.ejecutar(bd, carga.carga_id, meses)


def _filas(bd: Session, mes: date) -> dict:
    return {(v.sku, v.tienda, v.semana, v.empresa): v for v in bd.scalars(select(VentaSemanal).where(VentaSemanal.mes == mes))}


def test_meses_y_transformar():
    assert etl.meses_de(date(2026, 8, 15), date(2026, 10, 2)) == [AGO, SEP, OCT]
    assert etl.lunes(date(2026, 9, 3)) == date(2026, 8, 31)
    filas, fuera, motivos = etl.transformar([
        ("A1", "001", "2026-08-31", "PS", "3", "1", "200", "10", "100", "2"),
        ("A1", "001", "2026-08-24", "PS", "1", "0", "1", "0", "0", "1"),  # semana de agosto en el archivo de septiembre
        ("", "001", "2026-09-07", "PS", "1", "0", "1", "0", "0", "1"),
        ("A2", None, "2026-09-08", "PS", "1", "0", "1", "0", "0", "1"),  # no es lunes
    ], SEP, 1)
    assert len(filas) == 1 and fuera == 3 and len(motivos) == 3
    assert filas[0][9] == Decimal("190.00") and filas[0][2] == "001"
    assert etl.leer_csv(b"sku,tienda,semana,empresa,piezas,piezas_devueltas,importe_bruto,descuento_linea,costo,tickets\n"
                        b"A1,001,2026-09-07,PS,1,0,10,0,5,1\n")[0][0] == "A1"
    assert etl.leer_csv("A1;001;2026-09-07;PS;1;0;10;0;5;1\n".encode())[0][3] == "PS"
    with pytest.raises(etl.ErrorEtl):
        etl.leer_csv(b"A1,001\n")
    assert etl.mes_del_archivo([("A1", "001", "2026-08-31"), ("A1", "001", "2026-09-28")]) == SEP


def test_carga_desde_smnbi_cuadra_y_no_duplica(smnbi):
    with Session(motor()) as bd:
        assert etl.meses_a_cargar(bd, date(2026, 10, 15)) == [AGO, SEP, OCT]
        carga = _correr(bd, [AGO, SEP, OCT])
        assert carga.estado == "completa", carga.error
        assert carga.meses_hechos == 3 and carga.paso is None
        sep = _filas(bd, SEP)
        a1 = sep[("A1", "001", date(2026, 8, 31), "PS")]
        # 2 + 1 vendidas, 1 devuelta; 200 + 100 - 100 bruto, menos 10 de descuento; el flete no cuenta
        assert (a1.piezas, a1.piezas_devueltas, a1.importe_bruto, a1.importe, a1.tickets) == (3, 1, 200, 190, 2)
        assert sep[("A2", "001", date(2026, 8, 31), "PS")].piezas == 3  # paquete de 3
        assert len(sep) == 2  # sin Factura Electronica, sin PROCESAR, sin artículo desconocido
        # La semana del 31 de agosto queda partida: agosto lleva la venta del lunes 31
        assert _filas(bd, AGO)[("A1", "002", date(2026, 8, 31), "VCE")].importe == 400
        cuadre = bd.scalars(select(VentaCuadre).where(VentaCuadre.carga_id == carga.carga_id)).all()
        assert cuadre and all(q.cuadra for q in cuadre)
        ps_sep = next(q for q in cuadre if q.mes == SEP and q.empresa == "PS")
        assert (ps_sep.importe_origen, ps_sep.piezas_cargadas, ps_sep.renglones_fuera) == (280, 5, 2)
        pasos = bd.scalars(select(CargaPaso.paso).where(CargaPaso.carga_id == carga.carga_id)).all()
        assert pasos[0] == "conectar" and pasos.count("cuadrar") == 3
        total = bd.scalar(select(func.count()).select_from(VentaSemanal))
        # Ya cargado, la siguiente solo repite los últimos meses; correrla otra vez no duplica
        assert etl.meses_a_cargar(bd, date(2026, 10, 15)) == [SEP, OCT]
        assert _correr(bd, [SEP, OCT]).estado == "completa"
        assert bd.scalar(select(func.count()).select_from(VentaSemanal)) == total


def test_factura_electronica_se_puede_prender(smnbi):
    smnbi.etl_factura_electronica = True
    with Session(motor()) as bd:
        assert _correr(bd, [SEP]).estado == "completa"
        assert _filas(bd, SEP)[("A1", "002", date(2026, 9, 7), "VCE")].importe == 500


def test_detener_y_errores_de_conexion(smnbi):
    with Session(motor()) as bd:
        carga = etl.iniciar(bd, "manual", None, [SEP])
        assert etl.iniciar(bd, "manual", None, [SEP]) is None  # una a la vez
        etl.pedir_detener(bd)
        assert etl.ejecutar(bd, carga.carga_id, [SEP]).estado == "detenida"
        smnbi.smnbi_contrasena = "Clave-Equivocada-123"
        fallida = _correr(bd, [SEP])
        assert fallida.estado == "fallida" and "No se pudo conectar" in fallida.error
        assert "Clave-Equivocada-123" not in fallida.error
        smnbi.smnbi_servidor = ""
        assert etl.falta_conexion() == ["servidor de SMNBI"]


def test_rutas_y_carga_con_archivo(smnbi, admin: TestClient):
    r = admin.post("/api/datos/etl/probar")
    assert r.status_code == 200, r.text
    assert r.json()["articulos"] == 2 and r.json()["desde"] == "2026-08-31"
    estado = admin.get("/api/datos/etl").json()
    assert estado["conexion"]["configurada"] and estado["fuentes"][0]["codigo"] == "ventas"
    csv = ("sku,tienda,semana,empresa,piezas,piezas_devueltas,importe_bruto,descuento_linea,costo,tickets\n"
           "A1,001,2026-08-31,PS,3,1,200,10,100,2\nA2,001,2026-09-07,PS,1,0,30,0,20,1\nmala,fila\n")
    r = admin.post("/api/datos/etl/archivo", files={"archivo": ("venta_sep.csv", csv.encode(), "text/csv")})
    assert r.status_code == 202, r.text
    cid = r.json()["id"]
    for _ in range(50):
        detalle = admin.get(f"/api/datos/etl/cargas/{cid}").json()
        if detalle["estado"] != "en_curso":
            break
        time.sleep(0.2)
    assert detalle["estado"] == "completa", detalle
    assert detalle["cargados"] == 2 and detalle["fuera"] == 1 and detalle["cuadra"] is True
    assert {p["paso"] for p in detalle["pasos"]} == {"extraer", "transformar", "cargar", "cuadrar"}
    assert detalle["cuadre"][0]["importe_cargado"] == "220.00"
    assert admin.post("/api/datos/etl/archivo", files={"archivo": ("x.pdf", b"%PDF", "application/pdf")}).status_code == 400
    assert admin.post("/api/datos/etl/detener").status_code == 409
