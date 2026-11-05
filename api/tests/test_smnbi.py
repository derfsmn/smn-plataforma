"""Tablas de SMNBI cargadas desde CSV (artículos, tiendas, proveedores, compras, costos e inventario). Datos ficticios."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from datos import smnbi
from datos.modelos import CompraOrden, CostoArticulo, Inventario, Producto, Proveedor, Tienda

R = "/api/datos/etl/smnbi"


@pytest.fixture
def sincrono(monkeypatch):
    monkeypatch.setattr(smnbi, "en_hilo", lambda trabajo: trabajo(Session(motor())))


def subir(cliente: TestClient, codigo: str, texto: str):
    return cliente.post(f"{R}/{codigo}/archivo", files={"archivo": (f"{codigo}.csv", texto.encode("utf-8-sig"), "text/csv")})


def ultima(cliente: TestClient, codigo: str) -> dict:
    return next(f for f in cliente.get("/api/datos/etl").json()["fuentes"] if f["codigo"] == codigo)


def test_leer_csv_de_ssms():
    f = smnbi.FUENTES["proveedores"]
    # Sin encabezado, con NULL y punto y coma
    filas = smnbi.leer("P1;Proveedor Uno;ALTA;30 DIAS;NULL;0;7;NULL;NULL;NULL\n".encode("utf-8-sig"), f)
    assert filas == [["P1", "Proveedor Uno", "ALTA", "30 DIAS", None, "0", "7", None, None, None]]
    with pytest.raises(smnbi.ErrorArchivo):  # el archivo de antes, sin Agente ni RFC
        smnbi.leer(b"P1;Proveedor Uno;ALTA;30 DIAS;NULL;0;7;NULL\n", f)
    with pytest.raises(smnbi.ErrorArchivo):
        smnbi.leer(b"P1,Uno\n", f)  # le faltan columnas
    # «Texto delimitado por tabulaciones» de SSMS, en UTF-16: la coma de un nombre no recorre columnas
    tab = "P2\tProveedor, Dos\tALTA\t30 DIAS\tNULL\t0\t7\tNULL\tAG1\tNULL\r\n".encode("utf-16")
    assert smnbi.leer(tab, f)[0][:3] == ["P2", "Proveedor, Dos", "ALTA"]
    assert "AAAAMMDD" in smnbi.__doc__ and "'Orden Compra'" in smnbi.consultas_sql()


def test_cargar_tablas_de_smnbi(admin: TestClient, sincrono):
    sku = f"SM-{uuid.uuid4().hex[:6]}"
    # Tiendas: con encabezado; un renglón sin nombre queda fuera
    r = subir(admin, "tiendas", "Almacen,Nombre,Poblacion,Estado,CodigoPostal,Grupo,Ruta,Sucursal,Estatus,Region,Categoria,FechaApertura,Lat,Lon\n"
              "T-EJ1,TIENDA EJEMPLO,Puebla,Puebla,72000,VENTAS,TIENDAS,5,ALTA,Centro,C,2020-12-22,19.0,-98.2\n"
              "T-EJ2,NULL,Puebla,Puebla,72000,VENTAS,TIENDAS,5,ALTA,Centro,C,NULL,NULL,NULL\n")
    assert r.status_code == 202, r.text
    t = ultima(admin, "tiendas")
    assert t["ultima"]["estado"] == "completa" and t["ultima"]["cargados"] == 1 and t["ultima"]["fuera"] == 1

    # Agente y RFC se guardan aunque vengan vacíos (Diego, 2026-11-03); RFC ficticio
    assert subir(admin, "proveedores", "PX1,Proveedor Ejemplo,ALTA,30 DIAS,NULL,0,7,0,AG1,xaxx-010101 000\n"
                                       "PX2,Proveedor Sin Datos,ALTA,NULL,NULL,0,NULL,0,NULL,NULL\n").status_code == 202
    assert subir(admin, "compras", "PS,OC-1,PX1,T-EJ1,2026-01-05,CONCLUIDO,100,1000.5,2026-01-12,2026-01-15,90,10,0\n"
                                   "PS,OC-2,PX1,T-EJ1,2026-02-01,CONCLUIDO,50,500,NULL,NULL,0,0,0\n").status_code == 202
    assert subir(admin, "costos", f"{sku},PX1,2026-09-30,45.5,44.25,1200,12\n").status_code == 202
    assert subir(admin, "inventario", f"2026-10-22,PS,T-EJ1,{sku},8,31.97\n2026-10-22,PS,T-EJ1,OTRO,0,1\n").status_code == 202
    # Otra fecha de corte se agrega sin borrar la anterior
    assert subir(admin, "inventario", f"2026-10-29,PS,T-EJ1,{sku},5,31.97\n").status_code == 202

    with Session(motor()) as bd:
        assert bd.get(Tienda, "T-EJ1").categoria == "C" and bd.get(Tienda, "T-EJ1").fecha_apertura == date(2020, 12, 22)
        assert bd.get(Proveedor, "PX1").dias_entrega == 7
        assert (bd.get(Proveedor, "PX1").agente, bd.get(Proveedor, "PX1").rfc) == ("AG1", "XAXX010101000")
        assert (bd.get(Proveedor, "PX2").agente, bd.get(Proveedor, "PX2").rfc) == (None, None)
        oc = bd.get(CompraOrden, ("PS", "OC-1"))
        assert oc.piezas_recibidas == Decimal("90") and oc.piezas_perdidas == Decimal("10") and oc.primera_entrada == date(2026, 1, 12)
        assert bd.get(CostoArticulo, sku).costo_ultimo == Decimal("45.5")
        cortes = bd.scalars(select(Inventario.fecha_corte).where(Inventario.sku == sku)).all()
        assert sorted(cortes) == [date(2026, 10, 22), date(2026, 10, 29)]

    # Un archivo que no es de la fuente se rechaza antes de cargar
    assert subir(admin, "compras", "uno,dos\n").status_code == 400
    assert admin.get(f"{R}/consultas").text.startswith("-- Tablas de SMNBI")


def test_articulos_completan_el_catalogo(admin: TestClient, sincrono):
    nuevo, viejo = f"SA-{uuid.uuid4().hex[:6]}", f"SD-{uuid.uuid4().hex[:6]}"
    csv = (f"{nuevo},COLAGENO EJEMPLO 300 G,PREVENCION Y SALUD,SUPLEMENTOS,CAT,Colágeno,Polvo,FAB,PX1,MARCAEJ,NACIONAL,A,ALTA,7500000000099\n"
           f"{viejo},PRODUCTO VIEJO,ABARROTES,X,CAT,Otra,Seg,FAB,PX1,MARCAEJ,NACIONAL,C,DESCONTINUADO,NULL\n")
    assert subir(admin, "articulos", csv).status_code == 202, ultima(admin, "articulos")
    f = ultima(admin, "articulos")
    assert f["ultima"]["estado"] == "completa", f
    with Session(motor()) as bd:
        p = bd.scalar(select(Producto).where(Producto.sku == nuevo))
        assert p.subcategoria == "Colágeno" and p.estatus_erp == "ALTA" and p.codigo_proveedor == "PX1" and p.activo
        assert p.origen == "ETL" and p.codigo_barras == "7500000000099"
        # Solo en SMNBI y descontinuado: existe para ligar ventas, pero no es activo
        assert not bd.scalar(select(Producto).where(Producto.sku == viejo)).activo
        pid = p.producto_id
    # El detalle del catálogo abre con un producto que solo viene de SMNBI
    r = admin.get(f"/api/datos/productos/{pid}")
    assert r.status_code == 200, r.text


def test_revisar_si_hay_cambios_en_smnbi(admin: TestClient, sincrono):
    from datos import revision_smnbi as rv

    q = admin.get(f"{R}/revision/consulta").text
    assert "SOLO LEE" in q and "DATEFROMPARTS" in q and "'Nota Devolucion'" in q and not any("?" in l for l in q.splitlines() if not l.startswith("--"))
    with Session(motor()) as bd:
        hoy = {r.que: r for r in rv.comparar(bd, rv.leer(b"articulos,total,,0,NULL,NULL,NULL\n"))}
    articulos = int(hoy["Artículos"].plataforma.replace(",", ""))
    tiendas = admin.get("/api/datos/etl").status_code  # la plataforma responde
    assert tiendas == 200

    csv = (f"fuente,clave,empresa,filas,piezas,importe,fecha\n"
           f"articulos,total,,{articulos},NULL,NULL,NULL\n"
           f"articulos,total2,,1,NULL,NULL,NULL\n"
           f"inventario,corte,,3,NULL,NULL,2099-01-31\n"
           f"venta,2098-12-01,PS,10,5.5,1234.50,2098-12-31\n")
    r = admin.post(f"{R}/revision", files={"archivo": ("revision.csv", csv.encode("utf-8-sig"), "text/csv")})
    assert r.status_code == 200, r.text
    filas = {x["que"]: x for x in r.json()["renglones"]}
    assert filas["Artículos"]["estado"] == "igual" and filas["Artículos"]["accion"] is None
    assert filas["Corte de inventario"]["estado"] == "nuevo" and "corte más nuevo" in filas["Corte de inventario"]["accion"]
    dic = filas["Venta de Diciembre 2098"]
    assert dic["estado"] == "nuevo" and dic["plataforma"] == "Sin cargar" and "31/12/2098" in dic["smnbi"]
    assert "cambiaron" in r.json()["resumen"]

    # Punto y coma con coma decimal, como lo guarda SSMS en español
    h = rv.leer("venta;2098-12-01;PS;10;5,5;1234,50;2098-12-31\narticulos;total;;1;NULL;NULL;NULL\n".encode())
    assert h[0].importe == Decimal("1234.50") and h[0].piezas == Decimal("5.5")
    assert admin.post(f"{R}/revision", files={"archivo": ("x.csv", b"uno,dos\n", "text/csv")}).status_code == 400
