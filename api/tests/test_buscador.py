"""Buscador de productos de Compras y su ficha, con datos ficticios (se borran al terminar para no mover la última
semana ni el último corte que usan otras pruebas)."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.bd import motor
from datos.modelos import Carga, CostoArticulo, Inventario, Producto, Proveedor, Tienda, VentaSemanal
from nucleo.modelos import Usuario
from tests.conftest import alta_usuario

R = "/api/compras/buscador"
FIN = date(2028, 3, 6)  # lunes; más reciente que la venta de otras pruebas
CORTE = date(2028, 3, 12)


@pytest.fixture
def datos():
    h = uuid.uuid4().hex[:5]
    t1, t2 = f"B{h}1", f"B{h}2"
    sku = f"BUS-{h}"
    barras = f"75099{uuid.uuid4().int % 10**8:08d}"
    with Session(motor()) as bd:
        c = Carga(fuente="SMNBI_INVENTARIO", disparada_por="manual", estado="completa")
        bd.add(c)
        bd.flush()
        bd.add_all([Tienda(almacen=t1, nombre="Tienda buscador uno", categoria="A", carga_id=c.carga_id),
                    Tienda(almacen=t2, nombre="Tienda buscador dos", categoria="B", carga_id=c.carga_id),
                    Proveedor(proveedor=f"P{h}", nombre="Proveedor buscador S.A.", dias_entrega=5, carga_id=c.carga_id)])
        p = Producto(sku=sku, descripcion=f"Té de manzanilla {h} 25 sobres", marca="MARCAPRUEBA", departamento="Tés",
                     codigo_barras=barras, origen="ETL", activo=True, precio_lista=Decimal(100),
                     precio_lista_con_impuestos=Decimal(116), precio_membresia_con_impuestos=Decimal(104))
        bd.add(p)
        bd.add(CostoArticulo(sku=sku, proveedor=f"P{h}", costo_ultimo=Decimal(60), carga_id=c.carga_id))
        for i in range(26):
            lunes = FIN - timedelta(weeks=i)
            pz = Decimal(4 if i < 13 else 2)  # vende el doble en las últimas 13 semanas
            bd.add(VentaSemanal(mes=lunes.replace(day=1), sku=sku, tienda=t1, semana=lunes, empresa="EJ", piezas=pz,
                                piezas_devueltas=Decimal(0), importe_bruto=pz * 100, descuento=Decimal(0), importe=pz * 100,
                                costo=pz * 60, tickets=1, carga_id=c.carga_id))
        bd.add(VentaSemanal(mes=FIN.replace(day=1), sku=sku, tienda=t2, semana=FIN, empresa="EJ", piezas=Decimal(1),
                            piezas_devueltas=Decimal(0), importe_bruto=Decimal(100), descuento=Decimal(0),
                            importe=Decimal(100), costo=Decimal(60), tickets=1, carga_id=c.carga_id))
        bd.add_all([Inventario(fecha_corte=CORTE, empresa="EJ", almacen=t1, sku=sku, existencia=Decimal(26),
                               carga_id=c.carga_id),
                    Inventario(fecha_corte=CORTE, empresa="EJ", almacen=t2, sku=sku, existencia=Decimal(0),
                               carga_id=c.carga_id)])
        bd.commit()
        pid = p.producto_id
    yield {"sku": sku, "h": h, "id": pid, "barras": barras}
    with Session(motor()) as bd:
        bd.execute(delete(VentaSemanal).where(VentaSemanal.sku == sku))
        bd.execute(delete(Inventario).where(Inventario.fecha_corte == CORTE))
        bd.commit()


def test_busca_sin_acentos_y_por_palabras(admin, datos):
    _, c, _ = alta_usuario(admin, rol="compras_responsable")
    for q in (f"te manzanilla {datos['h']}", datos["sku"], datos["barras"], f"MANZANILLA {datos['h']} marcaprueba"):
        r = c.get(R, params={"q": q})
        assert r.status_code == 200, r.text
        assert [x["id"] for x in r.json()["catalogo"]] == [datos["id"]], q
    assert c.get(R, params={"q": f"manzanilla {datos['h']} chocolate"}).json()["catalogo"] == []
    assert c.get(R, params={"q": "a"}).json()["catalogo"] == []  # una letra no busca
    assert c.get(R, params={"q": "100%"}).status_code == 200  # los comodines se escapan


def test_ficha_completa(admin, datos):
    _, c, _ = alta_usuario(admin, rol="compras_responsable")
    f = c.get(f"{R}/producto/{datos['id']}").json()
    assert f["sku"] == datos["sku"] and Decimal(f["precio_lista"]) == 116 and Decimal(f["precio_membresia"]) == 104
    v = f["venta"]
    assert len(v["semanas"]) == 26 and v["piezas"] == 13 * 4 + 13 * 2 + 1
    assert v["recientes"] == 53 and v["anteriores"] == 26 and round(v["tendencia_pct"]) == 104
    assert [t["nombre"] for t in v["mejores"]] == ["Tienda buscador uno", "Tienda buscador dos"]
    assert round(v["margen_real_pct"]) == 40
    i = f["inventario"]
    assert i["existencia"] == 26 and i["tiendas_con"] == 1 and i["tiendas_en_cero"] == 1
    assert round(i["dias"]) == round(26 / (53 / 91))
    assert Decimal(f["costo"]["ultimo"]) == 60 and round(f["costo"]["margen_pct"]) == 40
    assert f["proveedor"]["nombre"] == "Proveedor buscador S.A." and f["proveedor"]["dias_entrega"] == 5
    assert f["mercado"] is None and f["relacionados"] == []


def test_permisos(admin, datos):
    _, externo, _ = alta_usuario(admin, tipo="externo", rol="proveedor")
    assert externo.get(R, params={"q": "manzanilla"}).status_code == 403
    assert externo.get(f"{R}/producto/{datos['id']}").status_code == 403
    _, c, _ = alta_usuario(admin, rol="compras_responsable")
    assert c.get(f"{R}/producto/999999999").status_code == 404


def test_costo_y_margen_solo_con_permiso(datos):
    """Revisión de seguridad 2026-11-22, B1: sin compras.costos.ver, la ficha no trae costo ni margen."""
    from core.seguridad import Contexto
    from modulos.compras.rutas_buscador import ficha

    with Session(motor()) as bd:
        u = bd.scalars(select(Usuario)).first()
        con = ficha(datos["id"], Contexto(usuario=u, permisos={"compras.productos.ver", "compras.costos.ver"}), bd)
        sin = ficha(datos["id"], Contexto(usuario=u, permisos={"datos.productos.ver"}), bd)
    assert con.costo is not None and con.venta.margen_real_pct is not None
    assert sin.costo is None and sin.venta.margen_real_pct is None
