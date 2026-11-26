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


def test_monitor_salud_hoy_y_lo_que_sigue(admin):
    d = admin.get("/api/nucleo/en-vivo/monitor").json()
    claves = [c["clave"] for c in d["salud"]]
    assert claves == ["api", "base", "correo", "ia", "dataforseo", "disco", "respaldo"]
    assert all(c["estado"] in ("ok", "ocupado", "aviso", "mal", "apagado") for c in d["salud"])
    assert next(c for c in d["salud"] if c["clave"] == "base")["estado"] == "ok"
    assert "evaluaciones" in d["hoy"] and "busquedas" in d["hoy"]
    assert isinstance(d["sigue"], list) and isinstance(d["grupos"], list)


def test_avisos_que_dicen_lo_mismo_se_juntan():
    lineas = [{"nivel": "error", "origen": "radar", "mensaje": "No se pudo enviar el correo a 3 personas — refused", "hora": "a"},
              {"nivel": "error", "origen": "radar", "mensaje": "No se pudo enviar el correo a 5 personas", "hora": "b"},
              {"nivel": "aviso", "origen": "mercado producto", "mensaje": "Google no aceptó «BDM Life»", "hora": "c"},
              {"nivel": "info", "origen": "radar", "mensaje": "listo", "hora": "d"}]
    g = en_vivo.avisos_agrupados(lineas)
    assert [(x["nivel"], x["veces"]) for x in g] == [("error", 2), ("aviso", 1)]
    assert g[0]["mensaje"] == "No se pudo enviar el correo a 5 personas"


def test_grafica_en_vivo_cuenta_busquedas_e_ia(admin):
    from nucleo import actividad

    actividad.muestra()  # deja lista la lectura anterior del procesador
    actividad.contar(3)
    with actividad.ia_ocupada():
        m = actividad.muestra(gpu=None)
    assert m["busquedas"] >= 3
    assert m["cpu"] is None or 0 <= m["cpu"] <= 100
    assert 0 <= m["ia"] <= 100
    s = admin.get("/api/nucleo/en-vivo/monitor/serie").json()
    assert s["cada"] == 2.0 and s["muestras"] and "busquedas" in s["muestras"][-1]


def test_sesion_ligera_devuelve_la_conexion_sin_lock_timeout():
    """26 nov 2026: el Monitor se rinde a los 2 s ante un bloqueo, y la conexión regresa a la bolsa como estaba."""
    from sqlalchemy import text

    from core.bd import motor, obtener_bd_ligera

    gen = obtener_bd_ligera()
    bd = next(gen)
    assert bd.execute(text("SELECT @@LOCK_TIMEOUT")).scalar() == 2000
    gen.close()
    assert motor().pool.size() == 10
    with motor().connect() as c:
        assert c.execute(text("SELECT @@LOCK_TIMEOUT")).scalar() == -1


def test_sesion_ligera_mantiene_el_limite_despues_de_rollback():
    from sqlalchemy import text

    from core.bd import obtener_bd_ligera

    gen = obtener_bd_ligera()
    bd = next(gen)
    bd.rollback()
    assert bd.execute(text("SELECT @@LOCK_TIMEOUT")).scalar() == 2000
    gen.close()
