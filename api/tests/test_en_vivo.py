"""Qué está corriendo y bitácora en vivo en Estado del sistema (26 nov 2026)."""
import logging

from nucleo import en_vivo


def test_bitacora_en_vivo_y_procesos(admin):
    en_vivo.instalar()
    logging.getLogger("smn.compras.radar_productos").info("Radar de productos: evaluación 7, Paso 3 de 6: buscando")
    logging.getLogger("uvicorn.access").info('"GET /api/algo HTTP/1.1" 200')  # las consultas de pantallas no van
    r = admin.get("/api/nucleo/en-vivo")
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d["procesos"], list)
    mensajes = [x["mensaje"] for x in d["bitacora"]]
    assert any("Paso 3 de 6" in m for m in mensajes)
    assert not any("GET /api/algo" in m for m in mensajes)
    ultima = d["bitacora"][-1]["n"]
    assert admin.get(f"/api/nucleo/en-vivo?desde={ultima}").json()["bitacora"] == []


def test_evaluacion_en_curso_sale_con_su_paso(admin):
    from datetime import timedelta

    from core.bd import _fabrica
    from sqlalchemy import select

    from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
    from nucleo.modelos import Usuario, ahora

    with _fabrica()() as bd:
        i = ProductoIdea(nombre="BDM Life Berberina prueba en vivo", creada_por=bd.scalar(select(Usuario.usuario_id).limit(1)))
        bd.add(i)
        bd.flush()
        e = ProductoEvaluacion(idea_id=i.idea_id, estado="en_curso", avance="Paso 3 de 6: buscando precios",
                               creada_en=ahora() - timedelta(minutes=12))
        bd.add(e)
        bd.commit()
        try:
            procs = en_vivo.procesos(bd)
            mio = next(p for p in procs if p["detalle"] == "Paso 3 de 6: buscando precios")
            assert mio["minutos"] >= 12 and mio["lento"] and mio["tipo"] == "evaluacion"
            assert mio["nombre"] == "Radar de productos: BDM Life Berberina prueba en vivo"
        finally:
            bd.delete(e)
            bd.delete(i)
            bd.commit()


def test_sin_permiso_no_ve(cliente):
    assert cliente.get("/api/nucleo/en-vivo").status_code in (401, 403)
