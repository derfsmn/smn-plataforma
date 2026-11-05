"""Datos → Salud de inventario: sin venta, exceso y en cero con datos ficticios (se borran al terminar para no mover
la última semana ni el último corte que usan otras pruebas)."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.bd import motor
from datos.modelos import Carga, CostoArticulo, Inventario, Producto, Tienda, VentaSemanal
from tests.conftest import alta_usuario

R = "/api/datos/inventario"
FIN = date(2027, 9, 6)  # lunes; más reciente que la venta de otras pruebas
CORTE = date(2027, 9, 20)


@pytest.fixture
def datos():
    h = uuid.uuid4().hex[:5]
    t1, t2, cedis = f"I{h}1", f"I{h}2", f"I{h}C"
    sku = {k: f"INV-{h}-{k}" for k in ("parado", "exceso", "sano", "cero")}
    with Session(motor()) as bd:
        c = Carga(fuente="SMNBI_INVENTARIO", disparada_por="manual", estado="completa")
        bd.add(c)
        bd.flush()
        bd.add_all([Tienda(almacen=t1, nombre="Tienda inventario uno", categoria="A", carga_id=c.carga_id),
                    Tienda(almacen=t2, nombre="Tienda inventario dos", categoria="B", carga_id=c.carga_id),
                    Tienda(almacen=cedis, nombre="Almacén ficticio", categoria="CEDIS", carga_id=c.carga_id)])
        for k, s in sku.items():
            bd.add(Producto(sku=s, descripcion=f"Producto {k} ficticio", departamento="Depto inventario", origen="ETL",
                            activo=True))
        bd.add(CostoArticulo(sku=sku["cero"], costo_ultimo=Decimal(40), carga_id=c.carga_id))

        def venta(tienda, s, piezas_semana):
            for i in range(13):
                lunes = FIN - timedelta(weeks=i)
                pz = Decimal(piezas_semana)
                bd.add(VentaSemanal(mes=lunes.replace(day=1), sku=s, tienda=tienda, semana=lunes, empresa="EJ",
                                    piezas=pz, piezas_devueltas=Decimal(0), importe_bruto=pz * 100, descuento=Decimal(0),
                                    importe=pz * 100, costo=pz * 50, tickets=1, carga_id=c.carga_id))

        venta(t1, sku["exceso"], 1)  # 13 piezas en 91 días, 100 en existencia = 700 días
        venta(t1, sku["sano"], 7)  # 1 por día, 30 en existencia = 30 días
        venta(t2, sku["cero"], 2)  # vende y no hay
        venta(t2, sku["sano"], 7)

        def inv(almacen, s, ex, costo):
            bd.add(Inventario(fecha_corte=CORTE, empresa="EJ", almacen=almacen, sku=s, existencia=Decimal(ex),
                              costo_promedio=Decimal(costo) if costo is not None else None, carga_id=c.carga_id))

        inv(t1, sku["parado"], 10, 20)  # 200 pesos detenidos
        inv(t1, sku["exceso"], 100, 5)  # 500 pesos
        inv(t1, sku["sano"], 30, 10)
        inv(t2, sku["sano"], 30, 10)
        inv(t2, sku["cero"], 0, None)
        inv(cedis, sku["parado"], 1000, 20)  # no vende: va aparte
        bd.commit()
    yield {"t1": t1, "t2": t2, "cedis": cedis, "sku": sku}
    with Session(motor()) as bd:
        bd.execute(delete(VentaSemanal).where(VentaSemanal.sku.in_(sku.values())))
        bd.execute(delete(Inventario).where(Inventario.fecha_corte == CORTE))
        bd.commit()


def test_resumen_y_productos(admin, datos):
    r = admin.get(R)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["corte"] == str(CORTE)
    uno = next(x for x in d["por_tienda"] if x["almacen"] == datos["t1"])
    assert uno["valor_sin_venta"] == 200 and uno["valor_exceso"] == 500 and uno["valor"] == 1000
    assert uno["sin_venta"] == 1 and uno["exceso"] == 1
    dos = next(x for x in d["por_tienda"] if x["almacen"] == datos["t2"])
    assert dos["en_cero"] == 1 and dos["valor_sin_venta"] == 0
    assert not any(x["almacen"] == datos["cedis"] for x in d["por_tienda"])
    assert next(x for x in d["otros_almacenes"] if x["almacen"] == datos["cedis"])["valor"] == 20000

    parados = admin.get(f"{R}/productos", params={"tipo": "sin_venta", "tienda": datos["t1"]}).json()
    assert [p["sku"] for p in parados] == [datos["sku"]["parado"]] and parados[0]["valor"] == 200
    exceso = admin.get(f"{R}/productos", params={"tipo": "exceso", "tienda": datos["t1"]}).json()
    assert exceso[0]["dias"] == 700
    cero = admin.get(f"{R}/productos", params={"tipo": "en_cero", "departamento": "Depto inventario"}).json()
    assert [(p["almacen"], p["sku"]) for p in cero] == [(datos["t2"], datos["sku"]["cero"])]
    assert cero[0]["costo"] == 40 and cero[0]["por_semana"] == 2

    t = admin.get(R, params={"tienda": datos["t2"]}).json()
    assert [x["almacen"] for x in t["por_tienda"]] == [datos["t2"]]


def test_permisos(admin):
    _, kiosco, _ = alta_usuario(admin, rol="kiosco_tienda")
    assert kiosco.get(R).status_code == 403
