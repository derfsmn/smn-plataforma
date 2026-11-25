"""Comparación v0.5.3 contra v0.5.4 y candado de la reclasificación nocturna (Diego, 24 nov 2026: «revisa bien todo»)."""
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.bd import motor
from datos import fichas as fi
from modulos.compras import comparar_versiones as cv
from modulos.compras import examen_clasificacion as ex
from modulos.compras import reclasificar
from modulos.compras.modelos_productos import ProductoEvaluacion
from tests.test_productos import R, catalogo_ficticio, sincrono  # noqa: F401 - sincrono es fixture


def _idea(admin, depto: str) -> int:
    datos = {"nombre": "Citrato de magnesio en polvo", "marca": f"Marca Comparar {depto[-4:]}", "departamento": depto,
             "ingrediente": "Magnesio", "forma": "Polvo", "precio_visto": "150", "costo_estimado": "80",
             "donde_se_vio": "Tienda de ejemplo"}
    r = admin.post(f"{R}/ideas", json=datos)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_comparacion_no_toca_evaluaciones_y_explica_cada_cambio(admin, sincrono, tmp_path):  # noqa: F811
    depto, _ = catalogo_ficticio()
    eid = _idea(admin, depto)
    antes = admin.get(f"{R}/evaluaciones/{eid}").json()
    assert antes["estado"] == "lista"
    with Session(motor(), expire_on_commit=False) as bd:
        total = bd.scalar(select(func.count()).select_from(ProductoEvaluacion))
        filas = cv.comparar(bd, [eid])
        assert bd.scalar(select(func.count()).select_from(ProductoEvaluacion)) == total  # los borradores se borran
        assert not cv.EN_BORRADOR
        f = filas[0]
        assert "error" not in f, f.get("error")
        a, d = f["v053"], f["v054"]
        # La v0.5.4 recalculada da lo mismo que la evaluación guardada (se hizo con la v0.5.4)
        assert (d.puntaje, d.color, d.subcategoria) == (antes["puntaje"], antes["color"], antes["subcategoria"])
        # Rentabilidad no depende de la clasificación: igual en las dos versiones
        assert a.factores["rentabilidad"] == d.factores["rentabilidad"]
        # Como la v0.5.3 clasificaba (ingrediente o la IA; sin IA en la prueba queda por parecidos)
        assert a.origen in {"parecidos", "sin_clasificar", "ingrediente"} and d.origen == "votos"
        assert f["explicado"], f["por_que"]
        res = cv.a_excel(str(tmp_path / "c.xlsx"), "prueba", filas)
        assert res["evaluaciones"] == 1 and res["sin_explicar"] == 0
        assert load_workbook(tmp_path / "c.xlsx").sheetnames == ["Resumen", "Cambios", "Todas"]
        # La evaluación real sigue vigente y sin cambios
        e = bd.get(ProductoEvaluacion, eid)
        bd.refresh(e)
        assert e.vigente and e.puntaje == antes["puntaje"]
    despues = admin.get(f"{R}/evaluaciones/{eid}").json()
    assert [h["id"] for h in despues["historial"]] == [eid]


def test_como_v053_no_conoce_la_crema_ni_quita_el_bono_de_marca():
    assert fi.formato("Crema de colágeno 50 g") == "crema"
    m = fi.COMO_V053.set(True)
    try:
        assert fi.formato("Crema de colágeno 50 g") == "polvo"  # así la leía la v0.5.3 (por los gramos)
    finally:
        fi.COMO_V053.reset(m)


def test_reclasificacion_espera_la_comparacion(monkeypatch, tmp_path):
    from core import config

    class C:
        plataforma_version = "v9.9.9-prueba"
        archivos_ruta = str(tmp_path)

    monkeypatch.setattr(config, "configuracion", lambda: C())
    assert ex.clave() == ex.CLASIFICADOR  # va con el clasificador, no con la versión de la plataforma (25 nov 2026)
    assert not reclasificar.comparacion_lista()
    assert [c for c, _ in ex.pendientes(ex.clave())] == ["100", "comparacion", "completo"]
    ex.ruta(ex.clave(), "comparacion", "xlsx").write_text("")
    ex.ruta(ex.clave(), "comparacion", "json").write_text("{}")
    assert reclasificar.comparacion_lista()
    assert [c for c, _ in ex.pendientes(ex.clave())] == ["100", "completo"]
    C.plataforma_version = "v9.9.10-otra"  # otra versión de la plataforma con el mismo clasificador: no se repite
    assert [c for c, _ in ex.pendientes(ex.clave())] == ["100", "completo"] and reclasificar.comparacion_lista()
