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


def test_monitor_trae_todo_en_una_consulta(admin):
    from datetime import date, timedelta

    from core.bd import _fabrica
    from modulos.compras.modelos import RadarReporte
    from nucleo.modelos import ahora

    with _fabrica()() as bd:
        r = RadarReporte(fecha=date(2031, 3, 4), origen="programado", estado="listo",
                         iniciado_en=ahora() - timedelta(hours=1), terminado_en=ahora() - timedelta(minutes=20))
        bd.add(r)
        bd.commit()
        try:
            d = admin.get("/api/nucleo/en-vivo/monitor").json()
            assert set(d) >= {"servidor", "procesos", "linea", "avisos", "carriles", "horas"}
            assert {"sistema", "ia", "dataforseo"} <= set(d["servidor"])
            assert any(b["carril"] == "Radar de tendencias" and b["estado"] == "listo" for b in d["linea"])
        finally:
            bd.delete(r)
            bd.commit()


def test_avance_por_paso():
    assert en_vivo._paso("Paso 3 de 6: buscando") == 2.5 / 6
    p = en_vivo._proceso("evaluacion", "x", None, None, 0.4)
    assert p["progreso"] == 0.4 and not p["lento"]
