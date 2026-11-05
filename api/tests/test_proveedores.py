"""Datos → Proveedores: calificación con compras, venta, costo e inventario de SMNBI (todo con datos ficticios)."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from core.bd import motor
from datos import proveedores as pv
from datos.modelos import (Carga, CompraOrden, CostoArticulo, Inventario, Producto, Proveedor, ProveedorCalificacion,
                           ProveedorEvaluacion, Tienda, VentaSemanal)
from modulos.compras.modelos_conocimiento import ConocimientoPesoProveedor
from tests.conftest import alta_usuario

R = "/api/datos/proveedores"
FIN = date(2027, 5, 31)  # lunes; más reciente que la venta de otras pruebas


def test_escalas_y_condiciones():
    assert pv.dias_credito("30 DIAS") == 30 and pv.dias_credito("CONTADO") == 0 and pv.dias_credito("ESPECIAL") is None
    assert pv._lineal(84, 70, 98) == pytest.approx(50) and pv._lineal(0, 10, 0) == 100 and pv._lineal(12, 10, 0) == 0
    assert pv._tramos(0, [(-10, 0), (0, 70), (10, 100)]) == 70 and pv._tramos(5, [(-10, 0), (0, 70), (10, 100)]) == 85
    assert pv.color_de(85, "alta") == "verde" and pv.color_de(85, "baja") == "amarillo" and pv.color_de(59, "alta") == "rojo"
    assert pv.color_de(None, "sin_datos") is None


@pytest.fixture
def datos_ficticios():
    """Dos proveedores: uno que cumple y vende bien, y otro que surte poco, tarda, vende poco y tiene exceso."""
    h = uuid.uuid4().hex[:6]
    bueno, malo = f"PB{h}", f"PM{h}"
    with Session(motor()) as bd:
        carga = Carga(fuente="ETL_VENTAS", disparada_por="manual", estado="completa")
        bd.add(carga)
        bd.flush()
        cid = carga.carga_id
        bd.add_all([Tienda(almacen=f"T{h}{i}", nombre=f"Tienda ficticia {i}", categoria="C", carga_id=cid) for i in range(4)])
        bd.add_all([Proveedor(proveedor=bueno, nombre="Proveedor Cumplido Ficticio", condicion="60 DIAS", dias_entrega=7,
                              agente=f"AG{h}"[:10], rfc="XAXX010101000", carga_id=cid),
                    Proveedor(proveedor=malo, nombre="Proveedor Tardado Ficticio", condicion="CONTADO", dias_entrega=5,
                              carga_id=cid)])
        skus = {bueno: [], malo: []}
        for prov, n, ritmo, precio, costo in ((bueno, 4, 8, 100, 55), (malo, 4, 0.1, 100, 85)):
            for i in range(n):
                p = Producto(sku=f"PV-{uuid.uuid4().hex[:8]}", descripcion=f"Producto ficticio {prov} {i}",
                             departamento="Depto ficticio", codigo_proveedor=prov, origen="ETL", activo=True)
                bd.add(p)
                skus[prov].append(p.sku)
                for semana in range(26):
                    lunes = FIN - timedelta(weeks=semana)
                    for t in range(4):
                        pz = Decimal(str(ritmo))
                        bd.add(VentaSemanal(mes=lunes.replace(day=1), sku=p.sku, tienda=f"T{h}{t}", semana=lunes,
                                            empresa="EJ", piezas=pz, piezas_devueltas=Decimal(0), importe_bruto=pz * precio,
                                            descuento=Decimal(0), importe=pz * precio, costo=pz * costo, tickets=1,
                                            carga_id=cid))
                bd.add(Inventario(fecha_corte=FIN, empresa="EJ", almacen=f"T{h}0", sku=p.sku,
                                  existencia=Decimal(150 if prov == bueno else 400), carga_id=cid))
                bd.add(CostoArticulo(sku=p.sku, proveedor=prov, costo_ultimo=Decimal(costo) * (1 if prov == bueno else Decimal("1.12")),
                                     costo_12m=Decimal(costo), piezas_12m=Decimal(100), compras_12m=4, carga_id=cid))
        for i in range(6):
            bd.add(CompraOrden(empresa="EJ", orden=f"OB{h}{i}", proveedor=bueno, almacen=f"T{h}0",
                               fecha_orden=FIN - timedelta(days=30 + i), piezas_pedidas=Decimal(100), importe_pedido=Decimal(5500),
                               primera_entrada=FIN - timedelta(days=24 + i), piezas_recibidas=Decimal(99),
                               piezas_perdidas=Decimal(0), piezas_rechazadas=Decimal(0), carga_id=cid))
            bd.add(CompraOrden(empresa="EJ", orden=f"OM{h}{i}", proveedor=malo, almacen=f"T{h}0",
                               fecha_orden=FIN - timedelta(days=30 + i), piezas_pedidas=Decimal(100), importe_pedido=Decimal(8500),
                               primera_entrada=FIN - timedelta(days=12 + i), piezas_recibidas=Decimal(70),
                               piezas_perdidas=Decimal(10), piezas_rechazadas=Decimal(5), carga_id=cid))
        bd.commit()
    yield bueno, malo, skus
    with Session(motor()) as bd:
        for tabla in (VentaSemanal, Inventario, CompraOrden, CostoArticulo, Tienda, Proveedor):
            bd.execute(delete(tabla).where(tabla.carga_id == cid))
        bd.execute(delete(Carga).where(Carga.carga_id == cid))
        bd.execute(update(Producto).where(Producto.sku.like("PV-%")).values(activo=False, codigo_proveedor=None))
        bd.execute(delete(ProveedorCalificacion))
        bd.execute(delete(ProveedorEvaluacion))
        bd.execute(delete(ConocimientoPesoProveedor))
        bd.commit()


@pytest.fixture
def sincrono(monkeypatch):
    def correr(evaluacion_id: int) -> None:
        with Session(motor()) as bd:
            pv.evaluar(bd, evaluacion_id)

    monkeypatch.setattr(pv, "en_hilo", correr)


def test_calificacion_lista_ficha_y_pesos(admin: TestClient, datos_ficticios, sincrono):
    bueno, malo, _ = datos_ficticios
    assert admin.post(f"{R}/calcular").status_code == 202
    lista = admin.get(R, params={"orden": "puntaje"}).json()
    assert lista["evaluacion"]["estado"] == "completa" and lista["pesos_de"] == "provisionales"
    assert [b["peso"] for b in lista["bloques"]] == [35, 30, 20, 15]
    filas = {f["proveedor"]: f for f in lista["filas"]}
    b, m = filas[bueno], filas[malo]
    assert b["color"] == "verde" and b["confianza"] == "alta" and b["puntaje"] > 80, b
    assert m["color"] == "rojo" and m["puntaje"] < 60, m
    assert b["cumplimiento"] > m["cumplimiento"] and b["costo"] > m["costo"] and b["inventario"] > m["inventario"]
    assert lista["evaluacion"]["contexto"]["margen_empresa"] is not None

    f = admin.get(f"{R}/{malo}").json()
    met = f["metricas"]
    assert met["cumplimiento"]["surtido_pct"] == 70 and met["cumplimiento"]["perdidas_rechazadas_pct"] == 15
    assert met["cumplimiento"]["retraso_dias"] > 6  # tarda ~18 días naturales (~13 hábiles) contra 5 prometidos
    assert met["costo"]["dias_credito"] == 0 and met["costo"]["alza_costo_pct"] == pytest.approx(12, abs=0.1)
    assert met["comercial"]["debajo_permanencia"] == 4  # 0.1 piezas por tienda a la semana ≈ 0.43 al mes < 0.75
    assert met["inventario"]["skus_exceso"] == 4 and len(met["skus"]) == 4
    assert f["ordenes_por_mes"] and f["condicion"] == "CONTADO"
    assert admin.get(f"{R}/NOEXISTE").status_code == 404
    assert [x["proveedor"] for x in admin.get(R, params={"q": "Tardado"}).json()["filas"]] == [malo]
    assert all(x["color"] == "rojo" for x in admin.get(R, params={"color": "rojo"}).json()["filas"])
    # Agente y RFC para filtrar (Diego, 2026-11-03)
    ag = filas[bueno]["agente"]
    assert ag and ag in lista["agentes"] and f["agente"] is None and f["rfc"] is None
    assert bueno in [x["proveedor"] for x in admin.get(R, params={"agente": ag}).json()["filas"]]
    sin_agente = [x["proveedor"] for x in admin.get(R, params={"agente": "-"}).json()["filas"]]
    assert malo in sin_agente and bueno not in sin_agente
    sin_rfc = [x["proveedor"] for x in admin.get(R, params={"rfc": "sin"}).json()["filas"]]
    assert malo in sin_rfc and bueno not in sin_rfc

    # Compras pone sus pesos en la Base de conocimiento; cuentan desde el siguiente cálculo
    C = "/api/compras/conocimiento/pesos-proveedor"
    assert admin.get(C).json()["de"] == "provisionales"
    malos = [{"factor": "cumplimiento", "puntos": 50}]
    assert admin.put(C, json=malos).status_code == 422
    nuevos = [{"factor": "cumplimiento", "puntos": 100}, {"factor": "comercial", "puntos": 0},
              {"factor": "costo", "puntos": 0}, {"factor": "inventario", "puntos": 0}]
    assert admin.put(C, json=nuevos).json()["de"] == "compras"
    admin.post(f"{R}/calcular")
    filas = {x["proveedor"]: x for x in admin.get(R).json()["filas"]}
    assert filas[malo]["puntaje"] == filas[malo]["cumplimiento"]


def test_el_semaforo_usa_la_calificacion_del_proveedor(admin: TestClient, datos_ficticios, sincrono):
    from modulos.compras import radar_productos as rp

    bueno, _, _ = datos_ficticios
    admin.post(f"{R}/calcular")
    with Session(motor()) as bd:
        cal = pv.calificacion_de(bd, bueno)
        s = rp.Sujeto(tipo="propuesta", nombre="Otro ficticio", proveedor_nombres=["Proveedor Cumplido Ficticio"])
        f = rp.f_proveedor(bd, s, [])
    assert f.puntaje == cal.puntaje and "Datos → Proveedores" in f.detalle


def test_permisos(admin: TestClient):
    # Otras pruebas cambian los permisos de los roles de Compras; aquí se dejan como los da la semilla
    permisos = ["compras.solicitud.ver", "compras.propuestas.ver", "compras.proveedores.invitar", "datos.proveedores.ver"]
    assert admin.put("/api/nucleo/roles/compras_comite/permisos", json={"permisos": permisos}).status_code == 200
    _, comite, _ = alta_usuario(admin, rol="compras_comite")
    assert comite.get(R).status_code == 200
    assert comite.post(f"{R}/calcular").status_code == 403
    _, kiosco, _ = alta_usuario(admin, rol="kiosco_tienda")
    assert kiosco.get(R).status_code == 403


def test_excel_para_compras_solo_alta_con_agente(admin: TestClient, datos_ficticios, sincrono):
    import io

    from openpyxl import load_workbook

    bueno, malo, _ = datos_ficticios
    with Session(motor()) as bd:
        b = bd.get(Proveedor, bueno)
        agente, cid = b.agente, b.carga_id
        b.estatus = " alta "
        bd.get(Proveedor, malo).estatus = "ALTA"  # sin agente: no entra
        h = uuid.uuid4().hex[:6]
        baja, solo = f"PX{h}", f"PS{h}"
        bd.add_all([Proveedor(proveedor=baja, nombre="Proveedor de Baja Ficticio", estatus="BAJA", agente=agente, carga_id=cid),
                    Proveedor(proveedor=solo, nombre="Proveedor Sin Movimientos Ficticio", estatus="ALTA", agente=agente,
                              rfc="XAXX010101000", carga_id=cid)])
        bd.commit()
    assert admin.post(f"{R}/calcular").status_code == 202
    lista = admin.get(R, params={"agente": agente}).json()
    assert lista["reporte"]["proveedores"] == 2

    r = admin.get(f"{R}/excel", params={"agente": agente})
    assert r.status_code == 200, r.text
    assert "spreadsheetml" in r.headers["content-type"] and "filename*=UTF-8''" in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Proveedores", "Resumen por agente", "Cómo se calcula"]
    ws = wb["Proveedores"]
    enc = [c.value for c in ws[1]]
    assert not any("RFC" in (e or "") for e in enc)
    filas = [dict(zip(enc, (c.value for c in fila))) for fila in ws.iter_rows(min_row=2)]
    assert [f["Clave"] for f in filas] == [bueno, solo]  # los sin calificación, al final de su agente
    assert filas[0]["Semáforo"] == "Verde" and filas[0]["Puntaje (0-100)"] > 80 and filas[0]["Días de entrega prometidos"] == 7
    assert filas[1]["Semáforo"] == "Sin datos" and filas[1]["Motivo sin calificación"] and filas[1]["Puntaje (0-100)"] is None
    resumen = [c.value for c in wb["Resumen por agente"][2]]
    assert resumen[:6] == [agente, 2, 1, 0, 0, 1]
    assert all("XAXX" not in str(c.value or "") for hoja in wb for fila in hoja.iter_rows() for c in fila)
