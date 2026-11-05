"""Base de conocimiento de Compras: políticas, reglas, pesos, casos y el avance de cada sección."""
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.bd import motor
from modulos.compras.modelos_conocimiento import ConocimientoCaso, ConocimientoPeso, ConocimientoPolitica, ConocimientoRegla
from tests.conftest import alta_usuario

R = "/api/compras/conocimiento"


def _limpio():
    with Session(motor()) as bd:
        for t in (ConocimientoCaso, ConocimientoPeso, ConocimientoPolitica, ConocimientoRegla):
            bd.execute(delete(t))
        bd.commit()


def _seccion(c: TestClient, clave: str) -> dict:
    return next(s for s in c.get(f"{R}/resumen").json()["secciones"] if s["clave"] == clave)


def test_politicas_versiones_y_avance(admin: TestClient):
    _limpio()
    assert admin.get(f"{R}/resumen").json()["listas"] == 0
    p = admin.post(f"{R}/politicas", json={"tema": "alta_productos", "titulo": "Alta de productos nuevos",
                                           "contenido": "Primer borrador"}).json()
    assert p["estado"] == "borrador" and p["version"] == 1 and p["actualizado_por"]
    assert not _seccion(admin, "politicas")["lista"]  # un borrador no cuenta
    p = admin.put(f"{R}/politicas/{p['id']}", json={**p, "contenido": "Texto final", "estado": "vigente"}).json()
    assert p["version"] == 2
    assert _seccion(admin, "politicas")["lista"]
    assert not _seccion(admin, "proceso")["lista"]  # «cómo se decide hoy» es aparte
    admin.post(f"{R}/politicas", json={"tema": "proceso", "titulo": "Cómo se decide hoy", "contenido": "...", "estado": "vigente"})
    assert _seccion(admin, "proceso")["lista"]
    assert admin.delete(f"{R}/politicas/{p['id']}").status_code == 204
    assert admin.post(f"{R}/politicas", json={"tema": "inventado", "titulo": "X"}).status_code == 422


def test_reglas_por_tipo(admin: TestClient):
    _limpio()
    r = admin.post(f"{R}/reglas", json={"tipo": "rechazo", "criterio": "Sin registro sanitario", "minimo": 5, "unidad": "x"}).json()
    assert r["minimo"] is None and r["unidad"] is None  # el rechazo directo es solo texto
    u = admin.post(f"{R}/reglas", json={"tipo": "umbral", "criterio": "Margen mínimo", "minimo": 35, "unidad": "%",
                                        "departamento": "Suplementos", "periodo_meses": 3}).json()
    assert float(u["minimo"]) == 35 and u["periodo_meses"] is None
    e = admin.post(f"{R}/reglas", json={"tipo": "exito", "criterio": "Piezas por tienda al mes", "minimo": 10,
                                        "unidad": "piezas", "periodo_meses": 6}).json()
    assert e["periodo_meses"] == 6
    assert admin.post(f"{R}/reglas", json={"tipo": "umbral", "criterio": "Precio", "minimo": 5, "maximo": 1}).status_code == 422
    assert [x["id"] for x in admin.get(f"{R}/reglas", params={"tipo": "umbral"}).json()] == [u["id"]]
    assert all(_seccion(admin, k)["lista"] for k in ("rechazo", "criterios", "exito"))
    admin.put(f"{R}/reglas/{u['id']}", json={**u, "activa": False})
    assert not _seccion(admin, "criterios")["lista"]  # una regla apagada no cuenta


def test_pesos_suman_cien(admin: TestClient):
    _limpio()
    p = admin.get(f"{R}/pesos").json()
    assert len(p["factores"]) == 6 and p["total"] == 0
    malos = [{"factor": f["factor"], "puntos": 10} for f in p["factores"]]
    assert admin.put(f"{R}/pesos", json=malos).status_code == 422
    assert admin.put(f"{R}/pesos", json=malos[:5]).status_code == 422
    buenos = [{"factor": f["factor"], "puntos": n} for f, n in zip(p["factores"], (30, 25, 15, 10, 10, 10))]
    p = admin.put(f"{R}/pesos", json=buenos).json()
    assert p["total"] == 100 and p["actualizado_por"]
    assert _seccion(admin, "pesos")["lista"]


def test_casos_y_permisos(admin: TestClient):
    _limpio()
    for i in range(20):
        c = admin.post(f"{R}/casos", json={"producto": f"Producto {i}", "decision": "aprobado" if i % 2 else "rechazado",
                                           "motivo": "Margen bajo", "fecha_decision": "2025-03-01"})
        assert c.status_code == 201
    assert not _seccion(admin, "casos")["lista"]  # faltan resultados
    caso = c.json()
    admin.put(f"{R}/casos/{caso['id']}", json={**caso, "resultado": "funciono"})
    assert _seccion(admin, "casos")["lista"]

    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    admin.put("/api/nucleo/roles/compras_consulta/permisos",
              json={"permisos": ["compras.solicitud.ver", "compras.conocimiento.ver"]})
    assert consulta.get(f"{R}/casos").status_code == 200
    assert consulta.post(f"{R}/casos", json={"producto": "X", "decision": "aprobado"}).status_code == 403
    assert consulta.put(f"{R}/pesos", json=[]).status_code == 403



def test_carga_del_consolidado_de_politicas(admin: TestClient):
    """El script del consolidado del 28 oct: políticas en borrador, reglas sin usar, pesos que suman 100; no duplica."""
    from scripts import cargar_politicas_compras as cp

    assert cp.promedio_entero(cp.RESPUESTAS) == {"demanda": 17, "rentabilidad": 22, "precio": 22, "tendencia": 16,
                                                  "categoria": 10, "proveedor": 13}
    _limpio()
    with Session(motor()) as bd:
        primera = cp.cargar(bd)
        bd.commit()
        segunda = cp.cargar(bd, con_pesos=False)
        bd.commit()
    assert primera["politicas"] == len(cp.POLITICAS) + 1 and primera["reglas"] == len(cp.REGLAS)
    assert segunda["politicas"] == 0 and segunda["reglas"] == 0 and segunda["politicas_ya"] == len(cp.POLITICAS) + 1
    politicas = admin.get(f"{R}/politicas").json()
    assert len(politicas) == len(cp.POLITICAS) + 1 and {p["estado"] for p in politicas} == {"borrador"}
    reglas = admin.get(f"{R}/reglas").json()
    assert not any(r["activa"] for r in reglas)  # no cambian el semáforo hasta que Compras las confirme
    pesos = admin.get(f"{R}/pesos").json()
    assert pesos["total"] == 100 and "20, 10, 20" in next(f["nota"] for f in pesos["factores"] if f["factor"] == "demanda")
    with Session(motor()) as bd:
        assert cp.volver_vigentes(bd) == len(cp.POLITICAS) + 1
        bd.commit()
    assert {p["estado"] for p in admin.get(f"{R}/politicas").json()} == {"vigente"}
    _limpio()


def test_carga_de_los_documentos_de_compras(admin: TestClient):
    """El script de los documentos del 29 oct: políticas en borrador, solo las reglas sin duda activas; no duplica."""
    from modulos.compras import radar_productos as rp
    from scripts import cargar_documentos_compras as cd

    _limpio()
    with Session(motor()) as bd:
        primera = cd.cargar(bd)
        bd.commit()
        segunda = cd.cargar(bd)
        bd.commit()
        assert rp.margen_minimo(bd, "CUALQUIER DEPARTAMENTO") == (Decimal("31"), False)  # todos con la lista A
    assert primera == {"politicas": len(cd.POLITICAS), "politicas_ya": 0, "reglas": len(cd.REGLAS), "reglas_ya": 0}
    assert segunda["politicas"] == 0 and segunda["reglas"] == 0
    politicas = admin.get(f"{R}/politicas").json()
    assert {p["estado"] for p in politicas} == {"borrador"}
    assert not any("@" in p["contenido"] for p in politicas)  # sin correos de personas
    activas = {r["criterio"] for r in admin.get(f"{R}/reglas").json() if r["activa"]}
    assert "Margen mínimo (lista A, precio lista)" in activas
    assert "Proveedor sin titularidad ni licencia de la marca" not in activas
    _limpio()
