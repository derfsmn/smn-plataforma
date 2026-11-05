"""Centro de datos y modelos: tablas y modelos reales, sin datos de personas en «Ver datos» (datos ficticios)."""
import uuid

from sqlalchemy.orm import Session

from core.bd import motor
from datos import centro
from datos.modelos import Carga, Proveedor
from tests.conftest import alta_usuario

R = "/api/datos/centro"


def test_cada_tabla_y_relacion_existe():
    ids = {t.id for t in centro.TABLAS}
    assert len(ids) == len(centro.TABLAS)
    for a, b in centro.relaciones():
        assert a in ids and b in ids
    for m in centro.MODELOS:
        assert set(m.usa) <= ids
    for t in centro.TABLAS:
        assert {n for n, _ in centro.campos(t)} <= {c.name for c in t.modelo.__table__.columns}


def test_resumen_con_registros_reales(admin):
    h = uuid.uuid4().hex[:6]
    with Session(motor()) as bd:
        carga = Carga(fuente="SMNBI_PROVEEDORES", disparada_por="manual", estado="completa")
        bd.add(carga)
        bd.flush()
        bd.add(Proveedor(proveedor=f"CD{h}", nombre="Proveedor ficticio del centro", carga_id=carga.carga_id))
        bd.commit()
    r = admin.get(R)
    assert r.status_code == 200, r.text
    d = r.json()
    prov = next(t for t in d["tablas"] if t["id"] == "proveedor")
    assert prov["registros"] >= 1 and prov["estado"] == "cargado"
    assert ["venta", "producto"] in d["relaciones"]
    assert {m["id"] for m in d["modelos"]} >= {"semaforo", "proveedores", "oportunidades", "diot"}
    assert all(isinstance(m["ejecuciones"], list) for m in d["modelos"])

    v = admin.get(f"{R}/tablas/proveedor/filas").json()
    assert "nombre" in v["columnas"] and "carga_id" not in v["columnas"]
    assert any(f["proveedor"] == f"CD{h}" for f in v["filas"])


def test_contraloria_no_se_ve_desde_aqui(admin):
    assert admin.get(f"{R}/tablas/diot_tercero/filas").status_code == 403
    assert admin.get(f"{R}/tablas/no_existe/filas").status_code == 404


def test_todas_las_tablas_visibles_abren(admin):
    for t in centro.TABLAS:
        if t.ver_datos:
            r = admin.get(f"{R}/tablas/{t.id}/filas")
            assert r.status_code == 200, t.id
            assert not set(r.json()["columnas"]) & centro.OCULTAS, t.id


def test_permisos(admin):
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    assert consulta.get(R).status_code == 403
    assert consulta.get(f"{R}/tablas/producto/filas").status_code == 403
