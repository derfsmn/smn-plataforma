"""Datos → Mapa de tiendas: ubicación de tblAlmacenes y venta de las últimas 13 semanas (datos ficticios)."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from core.bd import motor
from datos.modelos import Carga, Producto, Tienda, VentaSemanal
from datos.rutas_tiendas import ubicacion
from tests.conftest import alta_usuario

R = "/api/datos/tiendas"
FIN = date(2027, 6, 7)  # lunes; más reciente que la venta de otras pruebas


def test_ubicacion():
    assert ubicacion(Tienda(latitud=19.43, longitud=-99.13)) == "ok"
    assert ubicacion(Tienda(latitud=None, longitud=-99.13)) == "falta"
    assert ubicacion(Tienda(latitud=0, longitud=0)) == "falta"
    assert ubicacion(Tienda(latitud=-99.13, longitud=19.43)) == "fuera"  # volteadas


def test_lista_y_ficha(admin):
    h = uuid.uuid4().hex[:5]
    a, b = f"M{h}A", f"M{h}B"
    sku = f"MT-{h}"
    with Session(motor()) as bd:
        carga = Carga(fuente="SMNBI_TIENDAS", disparada_por="manual", estado="completa")
        bd.add(carga)
        bd.flush()
        bd.add_all([Tienda(almacen=a, nombre="Tienda ficticia centro", estado="CDMX", region="Ficticia", categoria="A",
                           latitud=19.43, longitud=-99.13, carga_id=carga.carga_id),
                    Tienda(almacen=b, nombre="Tienda ficticia sin mapa", categoria="C", carga_id=carga.carga_id),
                    Producto(sku=sku, descripcion="Producto ficticio del mapa", departamento="Depto ficticio",
                             origen="ETL", activo=True)])
        for s in range(26):
            lunes = FIN - timedelta(weeks=s)
            importe = Decimal(200 if s < 13 else 100)
            bd.add(VentaSemanal(mes=lunes.replace(day=1), sku=sku, tienda=a, semana=lunes, empresa="EJ", piezas=Decimal(2),
                                piezas_devueltas=Decimal(0), importe_bruto=importe, descuento=Decimal(0), importe=importe,
                                costo=Decimal(50), tickets=2, carga_id=carga.carga_id))
        bd.commit()
    d = admin.get(R).json()
    assert d["periodo"]["semanas"] == 13
    ta = next(t for t in d["tiendas"] if t["almacen"] == a)
    tb = next(t for t in d["tiendas"] if t["almacen"] == b)
    assert ta["ubicacion"] == "ok" and ta["venta"] == 2600 and ta["cambio_pct"] == 100.0 and ta["tickets"] == 26
    assert tb["ubicacion"] == "falta" and tb["venta"] is None
    f = admin.get(f"{R}/{a}").json()
    assert f["productos"][0]["descripcion"] == "Producto ficticio del mapa" and f["productos"][0]["venta"] == 2600
    assert sum(m["venta"] for m in f["por_mes"]) == 13 * 200 + 13 * 100
    assert admin.get(f"{R}/NOEXISTE").status_code == 404


def test_permisos(admin):
    _, kiosco, _ = alta_usuario(admin, rol="kiosco_tienda")
    assert kiosco.get(R).status_code == 403
