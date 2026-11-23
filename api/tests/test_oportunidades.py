"""«Buscar oportunidades»: productos que no tenemos y convendría buscar (Diego, 2026-10-27; datos ficticios)."""
import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, text, update
from sqlalchemy.orm import Session

from core.bd import motor
from core.config import configuracion
from datos.modelos import Carga, Producto, VentaSemanal
from ia import puerta
from modulos.compras import dataforseo as dfs
from modulos.compras import imagenes as img
from modulos.compras import oportunidades as op
from modulos.compras import radar_productos as rp
from modulos.compras.modelos import RadarSenal

R = "/api/compras/oportunidades"
FIN = date(2027, 3, 29)  # lunes; la misma última semana que usan las pruebas del semáforo


@pytest.fixture(autouse=True)
def agente_con_api(monkeypatch):
    """Estas pruebas simulan el agente con API externa; la búsqueda sin API (18 nov 2026) tiene la suya al final."""
    monkeypatch.setattr("modulos.compras.buscar_web.usar_web", lambda bd, tarea: False)


@pytest.fixture
def sincrono(monkeypatch):
    """La corrida y la evaluación corren en la misma petición, para revisar el resultado."""
    def corrida(corrida_id: int) -> None:
        with op._sesion() as bd:
            op.correr(bd, corrida_id)

    def evaluacion(evaluacion_id: int) -> None:
        with rp._sesion() as bd:
            rp.evaluar(bd, evaluacion_id)

    monkeypatch.setattr(op, "en_hilo", corrida)
    monkeypatch.setattr(rp, "en_hilo", evaluacion)


@pytest.fixture
def datos(monkeypatch):
    """Una subcategoría que vende mucho con un solo producto, un descontinuado que vendía, una tendencia alta y lo que
    vende la competencia en Google Shopping (simulado)."""
    h = uuid.uuid4().hex[:6]
    sub, berberina = f"Sub hueco {h}", f"Berberina{h} 500 mg 60 cápsulas"
    with Session(motor()) as bd:
        carga = Carga(fuente="ETL_VENTAS", disparada_por="manual", estado="completa")
        bd.add(carga)
        bd.flush()
        unico = Producto(sku=f"OP-{h}A", descripcion=f"Cúrcuma{h} con pimienta y berberina 90 caps", departamento=f"Depto {h}",
                         subcategoria=sub, marca=f"MARCA{h}", origen="ETL", activo=True)
        viejo = Producto(sku=f"OP-{h}B", descripcion=f"Espirulina{h} 100 tabletas", departamento=f"Depto {h}",
                         subcategoria=sub, origen="ETL", activo=False, estatus_erp="DESCONTINUADO")
        bd.add_all([unico, viejo, RadarSenal(titulo=f"Ashwagandha{h} en gomitas para dormir", nivel="ALTA", tipo="tendencia",
                                             primera_vez=FIN, ultima_vez=date.today(), veces_reportada=5, estado="nueva")])
        for semana in range(26):
            lunes = FIN - timedelta(weeks=semana)
            for p, piezas in ((unico, 500), (viejo, 300)):
                bd.add(VentaSemanal(mes=lunes.replace(day=1), sku=p.sku, tienda=f"T{h}", semana=lunes, empresa="EJ",
                                    piezas=Decimal(piezas), piezas_devueltas=Decimal(0), importe_bruto=Decimal(piezas * 100),
                                    descuento=Decimal(0), importe=Decimal(piezas * 100), costo=Decimal(piezas * 60),
                                    tickets=1, carga_id=carga.carga_id))
        bd.commit()
        unico_desc, viejo_desc = unico.descripcion, viejo.descripcion

    items = [{"product_id": f"g1{h}", "title": berberina, "seller": "Walmart", "price": 300, "currency": "MXN",
              "image_url": "https://encrypted-tbn0.gstatic.com/berberina.jpg"},
             {"product_id": f"g2{h}", "title": berberina, "seller": "San Pablo", "price": 320, "currency": "MXN"},
             {"product_id": f"g3{h}", "title": berberina, "seller": "Súper Naturista", "price": 250, "currency": "MXN"},
             {"product_id": f"g4{h}", "title": f"MARCA{h} Cúrcuma{h} con pimienta 90 cápsulas", "seller": "Chedraui",
              "price": 199, "currency": "MXN"},
             # No se parece a lo que vendemos en la subcategoría: fuera aunque lo vendan dos tiendas
             {"product_id": f"g5{h}", "title": "Aceite Mobil Super 1 L", "seller": "Refaccionaria", "price": 150, "currency": "MXN"},
             {"product_id": f"g6{h}", "title": "Aceite Mobil Super 1 L", "seller": "Walmart", "price": 160, "currency": "MXN"},
             # Dos vendedores de eBay son una sola tienda
             {"product_id": f"g7{h}", "title": f"Berberina{h} con canela 30 sobres", "seller": "eBay - uno", "price": 99,
              "currency": "MXN"},
             {"product_id": f"g8{h}", "title": f"Berberina{h} con canela 30 sobres", "seller": "eBay - dos", "price": 98,
              "currency": "MXN"}]
    enviadas = []

    def enviar(bd, corrida, tipo, tareas):
        enviadas.extend(tareas)
        return {t["tag"]: f"id{t['tag']}" for t in tareas}

    monkeypatch.setattr(dfs, "configurado", lambda: [])
    # Nunca sale a internet: la foto de la página del producto se simula
    monkeypatch.setattr(img, "de_pagina", lambda url: "https://ejemplo.mx/foto-creatina.jpg" if "creatina" in url else None)
    monkeypatch.setattr(dfs, "enviar", enviar)
    monkeypatch.setattr(dfs, "recoger", lambda tipo, ids, *a, **k: {tag: items for tag in ids})
    monkeypatch.setattr(configuracion(), "oportunidades_busquedas", 3)
    yield {"h": h, "sub": sub, "berberina": berberina, "unico": unico_desc, "viejo": viejo_desc,
           "enviadas": enviadas}
    # Su venta sale de la ventana para no mover las cuentas de tiendas de otras pruebas
    with Session(motor()) as bd:
        bd.execute(delete(VentaSemanal).where(VentaSemanal.tienda == f"T{h}"))
        bd.execute(update(Producto).where(Producto.sku.like(f"OP-{h}%")).values(activo=False))
        bd.commit()


class Respuesta:
    def __init__(self, texto):
        self.texto = texto


def _clave(fuentes: list[dict], letra: str, campo: str, valor: str) -> str:
    return next(d["clave"] for d in fuentes if d["clave"][0] == letra and d.get(campo) == valor)


def test_oportunidades_con_ia_citan_evidencia_y_pasan_al_semaforo(admin: TestClient, sincrono, datos, monkeypatch):
    vistos = []

    def ia(bd, tarea, **kw):
        if tarea != op.TAREA_IA:
            raise puerta.ErrorIA("sin IA en pruebas")
        fuentes = json.loads(kw["mensaje"])["datos"]
        vistos.append(fuentes)
        h = _clave(fuentes, "H", "subcategoria", datos["sub"])
        c = _clave(fuentes, "C", "titulo", datos["berberina"])
        t = next(d["clave"] for d in fuentes if d["clave"][0] == "T")
        return Respuesta(json.dumps({"oportunidades": [
            {"nombre": datos["berberina"], "por_que": "La venden 2 tiendas (ficticio).", "evidencia": [c, h],
             "prioridad": "alta", "subcategoria": datos["sub"], "forma": "Cápsulas"},
            {"nombre": "Producto sin evidencia", "por_que": "Inventado", "evidencia": ["X9"], "prioridad": "alta"},
            {"nombre": datos["unico"], "por_que": "Ya lo tenemos (ficticio).", "evidencia": [c], "prioridad": "media"},
            # Un hueco o una tendencia solo respaldan: sin prueba de venta no se propone
            {"nombre": f"Más opciones de {datos['sub']}", "por_que": "Hueco (ficticio).", "evidencia": [h], "prioridad": "alta"},
            {"nombre": "Gomitas de ashwagandha", "por_que": "Tendencia (ficticio).", "evidencia": [t], "prioridad": "alta"},
        ]}))

    monkeypatch.setattr(puerta, "ejecutar", ia)
    r = admin.post(R, json={"competencia": True})
    assert r.status_code == 202, r.text
    c = admin.get(f"{R}/corridas/{r.json()['id']}").json()
    assert c["estado"] == "lista", c["error"]
    assert c["con_ia"] and c["competencia"]
    # Se buscaron las subcategorías que más venden, a lo más las de Configuración
    assert len(datos["enviadas"]) <= 3 and datos["sub"].lower() in [t["keyword"] for t in datos["enviadas"]]

    fuentes = vistos[0]
    # Diego (2026-10-28): las tendencias respaldan; los descontinuados ya no entran («los quitamos por algo»)
    assert any(d["clave"][0] == "T" and d["titulo"].startswith(f"Ashwagandha{datos['h']}") for d in fuentes)
    assert not any(d["clave"][0] in "DN" for d in fuentes)
    titulos = [d["titulo"] for d in fuentes if d["clave"][0] == "C"]
    # Lo que ya vendemos y lo de nuestro propio sitio no cuentan como competencia
    assert datos["berberina"] in titulos and not any(f"Cúrcuma{datos['h']}" in t for t in titulos)
    assert not any("Mobil" in t for t in titulos) and not any("canela" in t for t in titulos)
    berb = next(d for d in fuentes if d["clave"][0] == "C" and d["titulo"] == datos["berberina"])
    assert berb["tiendas"] == ["San Pablo", "Walmart"] and berb["precio_mediana"] == 310.0

    # Solo queda la que cita evidencia que existe y no vendemos
    assert [o["nombre"] for o in c["oportunidades"]] == [datos["berberina"]]
    o = c["oportunidades"][0]
    assert o["prioridad"] == "alta" and Decimal(o["precio_visto"]) == Decimal("310.00")
    assert o["donde_se_vio"] == "San Pablo, Walmart"
    assert o["imagen"] == "https://encrypted-tbn0.gstatic.com/berberina.jpg" and o["imagen_de"] == "Google Shopping"
    assert {e["fuente"] for e in o["evidencia"]} == {"Competencia", "Hueco del surtido"}
    assert any("ya lo vendemos" in n for n in c["notas"])

    # «Evaluar» la manda al semáforo como idea de Compras
    r = admin.post(f"{R}/{o['id']}/evaluar")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "evaluada" and r.json()["evaluacion_id"]
    e = admin.get(f"/api/compras/productos/evaluaciones/{r.json()['evaluacion_id']}").json()
    assert e["estado"] == "lista", e["error"]
    assert e["sujeto"]["nombre"] == datos["berberina"] and "Buscar oportunidades" in e["descripcion"]
    # Sin costo ni proveedor: se califica como oportunidad, sin bajarle la confianza por eso
    fac = {x["factor"]: x for x in e["factores"]}
    assert fac["rentabilidad"]["valor"] == "Se califica al conseguir proveedor" and fac["rentabilidad"]["puntaje"] is None
    assert "Es una oportunidad" in e["explicacion"]
    # Ya evaluada, no se descarta desde aquí
    assert admin.patch(f"{R}/{o['id']}", json={"estado": "descartada"}).status_code == 400


def test_oportunidades_sin_ia_salen_directo_de_las_fuentes(admin: TestClient, sincrono, datos, monkeypatch):
    def sin_ia(bd, tarea, **kw):
        raise puerta.ErrorIA("sin IA en pruebas")

    monkeypatch.setattr(puerta, "ejecutar", sin_ia)
    r = admin.post(R, json={"competencia": True})
    c = admin.get(f"{R}/corridas/{r.json()['id']}").json()
    assert c["estado"] == "lista", c["error"]
    assert not c["con_ia"] and any("La IA no contestó" in n for n in c["notas"])
    nombres = [o["nombre"] for o in c["oportunidades"]]
    assert datos["berberina"] in nombres and datos["viejo"] not in nombres
    # Sin IA tampoco salen ideas sueltas: ni huecos como «Más opciones de…» ni tendencias ni descontinuados
    assert not any(n.startswith("Más opciones de") or n.startswith(f"Ashwagandha{datos['h']}") for n in nombres)
    assert c["fuentes"]["Competencia"] >= 1 and c["fuentes"]["Hueco del surtido"] >= 1

    # Llegan evaluadas solas (2026-11-09): ya no se descartan aquí sino en el radar, y no regresan en otra corrida
    o = next(x for x in c["oportunidades"] if x["nombre"] == datos["berberina"])
    assert o["estado"] == "evaluada" and o["evaluacion_id"]
    assert admin.patch(f"{R}/{o['id']}", json={"estado": "descartada"}).status_code == 400
    idea = admin.get(f"/api/compras/productos/evaluaciones/{o['evaluacion_id']}").json()["sujeto"]["id"]
    assert admin.patch(f"/api/compras/productos/ideas/{idea}/estado", json={"estado": "descartada"}).status_code == 200
    otra = admin.get(f"{R}/corridas/{admin.post(R, json={'competencia': True}).json()['id']}").json()
    assert datos["berberina"] not in [x["nombre"] for x in otra["oportunidades"]]
    assert any("ya la descartó" in n for n in otra["notas"])
    estado = admin.get(R).json()
    assert estado["corridas"][0]["id"] == otra["id"] and Decimal(estado["costo_maximo_competencia_usd"]) > 0


def test_sin_competencia_no_busca_en_google(admin: TestClient, sincrono, datos, monkeypatch):
    monkeypatch.setattr(puerta, "ejecutar", lambda *a, **k: (_ for _ in ()).throw(puerta.ErrorIA("sin IA")))
    r = admin.post(R, json={"competencia": False})
    c = admin.get(f"{R}/corridas/{r.json()['id']}").json()
    assert c["estado"] == "lista" and not datos["enviadas"] and c["fuentes"]["Competencia"] == 0


def test_tienda_de_junta_marketplaces():
    assert op.tienda_de("eBay - herbsproonline") == op.tienda_de("eBay - nutri_mart") == "eBay"
    assert op.tienda_de("Amazon MX") == "Amazon" and op.tienda_de("mercadolibre.com.mx") == "Mercado Libre"
    assert op.tienda_de("San Pablo") == "San Pablo"


class ConCitas(Respuesta):
    def __init__(self, texto, citas):
        super().__init__(texto)
        self.citas = citas


def test_mas_vendidos_del_agente_con_liga_y_prueba_de_venta(admin: TestClient, sincrono, datos, monkeypatch):
    h = datos["h"]
    vendido, inventado, sin_prueba = f"Creatina{h} monohidratada 300 g", f"Colágeno{h} inventado", f"Omega{h} 60 caps"
    temas: list[str] = []

    def ia(bd, tarea, **kw):
        if tarea != op.TAREA_VENDIDOS:
            raise puerta.ErrorIA("sin IA en pruebas")
        assert kw["busqueda_web"] and "más vendidos" in kw["instrucciones"]
        mensaje = json.loads(kw["mensaje"])
        assert datos["unico"] in mensaje["lo_que_mas_vendemos"]
        # Dos puertas (2026-11-09): una búsqueda por tendencia y otra por departamento
        temas.append(mensaje.get("tendencia") or ("depto:" + mensaje["departamento"]))
        return ConCitas(json.dumps({"productos": [
            {"nombre": vendido, "marca": "Marca ficticia", "prueba_de_venta": "Lugar 2 en más vendidos (ficticio), +5 mil vendidos",
             "tendencia": "Creatina para mujeres (ficticio)",
             "tienda": "Mercado Libre", "precio": 399, "url": f"https://ejemplo.mx/creatina-{h}"},
            {"nombre": inventado, "prueba_de_venta": "Lugar 1 (ficticio)", "url": f"https://otro.mx/{h}"},
            {"nombre": sin_prueba, "prueba_de_venta": "", "url": f"https://ejemplo.mx/omega-{h}"},
            {"nombre": datos["unico"], "marca": f"MARCA{h}", "prueba_de_venta": "Lugar 3 (ficticio)",
             "url": f"https://ejemplo.mx/curcuma-{h}"},
        ]}), [{"url": f"https://ejemplo.mx/creatina-{h}", "titulo": "x"}, {"url": f"https://ejemplo.mx/omega-{h}", "titulo": "z"},
              {"url": f"https://ejemplo.mx/curcuma-{h}", "titulo": "y"}])

    monkeypatch.setattr(puerta, "ejecutar", ia)
    r = admin.post(R, json={"competencia": False})
    c = admin.get(f"{R}/corridas/{r.json()['id']}").json()
    assert c["estado"] == "lista", c["error"]
    assert c["fuentes"]["Más vendido en internet"] == 1
    nombres = [o["nombre"] for o in c["oportunidades"]]
    # Sin IA para proponer, los más vendidos salen primero
    assert nombres[0] == vendido and inventado not in nombres and sin_prueba not in nombres
    assert any("no salió de su búsqueda" in n for n in c["notas"]) and any("sin prueba de venta" in n for n in c["notas"])
    assert any("ya vendemos" in n for n in c["notas"])
    o = c["oportunidades"][0]
    assert Decimal(o["precio_visto"]) == Decimal("399.00") and o["donde_se_vio"] == "Mercado Libre"
    assert o["imagen"] == "https://ejemplo.mx/foto-creatina.jpg" and o["imagen_de"] == "Página del producto en ejemplo.mx"
    ev = o["evidencia"][0]
    assert ev["fuente"] == "Más vendido en internet" and "+5 mil vendidos" in ev["texto"]
    assert any(x.startswith(f"Ashwagandha{h}") for x in temas) and any(x.startswith("depto:") for x in temas)
    # Salió por las dos puertas: se junta en uno con las dos
    assert o["puertas"] == ["tendencia", "mas_vendido"] and "Es de lo más vendido en" in ev["texto"]
    # Llega evaluada sola; si sale verde o amarilla, abre su búsqueda de proveedor
    assert o["estado"] == "evaluada" and o["evaluacion_id"] and o["evaluacion_estado"] == "lista"
    assert (o["busqueda_id"] is not None) == (o["color"] in ("verde", "amarillo"))


def test_foto_de_la_pagina_solo_de_sitios_publicos(monkeypatch):
    html = (b'<html><head><meta property="og:image" content="//http2.mlstatic.com/foto.jpg">'
            b"<meta name='twitter:image' content='https://otra.mx/x.jpg'></head></html>")

    class Pagina:
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return html

    pedidas = []
    monkeypatch.setattr(img._abridor, "open", lambda req, timeout: pedidas.append(req.full_url) or Pagina())
    monkeypatch.setattr(img, "_host_publico", lambda host: host != "interno.local")
    assert img.de_pagina("https://www.mercadolibre.com.mx/p/1") == "https://http2.mlstatic.com/foto.jpg"
    # Ni http ni la red interna: no se pide nada
    assert img.de_pagina("http://www.mercadolibre.com.mx/p/1") is None
    assert img.de_pagina("https://interno.local/x") is None
    assert pedidas == ["https://www.mercadolibre.com.mx/p/1"]


def test_host_publico_no_deja_ips_ni_red_interna():
    assert not img._host_publico("127.0.0.1") and not img._host_publico("10.0.0.5") and not img._host_publico("localhost")


def test_si_el_agente_contesta_en_texto_se_pasa_a_lista_sin_inventar(admin: TestClient, sincrono, datos, monkeypatch):
    """29 oct: «La IA no respondió JSON». Otra llamada sin internet lo pasa a JSON; las ligas se comprueban igual."""
    h = datos["h"]
    llamadas = []

    def ia(bd, tarea, **kw):
        if tarea != op.TAREA_VENDIDOS:
            raise puerta.ErrorIA("sin IA en pruebas")
        llamadas.append(kw.get("busqueda_web", False))
        if kw.get("busqueda_web"):
            return ConCitas(f"Encontré Magnesio{h} 120 caps, lugar 4 en Amazon México: https://ejemplo.mx/mag-{h}",
                            [{"url": f"https://ejemplo.mx/mag-{h}", "titulo": "x"}])
        return Respuesta(json.dumps({"productos": [
            {"nombre": f"Magnesio{h} 120 caps", "prueba_de_venta": "Lugar 4 en Amazon México (ficticio)",
             "url": f"https://ejemplo.mx/mag-{h}"},
            {"nombre": f"Inventado{h}", "prueba_de_venta": "Lugar 1", "url": f"https://inventado.mx/{h}"}]}))

    monkeypatch.setattr(puerta, "ejecutar", ia)
    c = admin.get(f"{R}/corridas/{admin.post(R, json={'competencia': False}).json()['id']}").json()
    assert True in llamadas and False in llamadas and llamadas.count(True) == llamadas.count(False)
    assert [o["nombre"] for o in c["oportunidades"]] == [f"Magnesio{h} 120 caps"]
    assert any("contestó en texto" in n for n in c["notas"]) and any("no salió de su búsqueda" in n for n in c["notas"])


def test_instrucciones_de_la_ia_se_pueden_ver(admin: TestClient):
    """Diego, 2026-11-03: «en donde puedo ver la descripción del agente?»."""
    from modulos.compras import oportunidades as op

    lista = admin.get(f"{R}/instrucciones").json()
    # El mismo texto que recibe la IA, solo sin los cortes de línea del código
    sin_espacios = lambda t: "".join(t.split())  # noqa: E731
    assert [sin_espacios(x["texto"]) for x in lista] == [sin_espacios(t) for t in
                                                         (op.INSTRUCCIONES_TENDENCIA, op.INSTRUCCIONES_DEPARTAMENTO,
                                                          op.INSTRUCCIONES, op.INSTRUCCIONES_A_JSON)]
    assert all(x["paso"] and x["que_hace"] for x in lista)


def test_corrida_programada_desde_configuracion(admin: TestClient, monkeypatch):
    """Diego, 2026-11-09: «buscar oportunidades sí debería correr, pero cada que yo decida en configuración»."""
    from modulos.compras.modelos_productos import OportunidadCorrida

    lanzadas: list[int] = []
    monkeypatch.setattr(op, "en_hilo", lanzadas.append)
    with Session(motor()) as bd:  # las corridas de otras pruebas quedan como de hace 10 días
        bd.execute(update(OportunidadCorrida).values(estado="lista",
                                                     creada_en=func.dateadd(text("day"), -10, OportunidadCorrida.creada_en)))
        bd.commit()
        assert op.revisar_programa(bd) is None  # apagado de fábrica
    assert admin.get(R).json()["programa"] is None

    yo = admin.get("/api/auth/yo").json()["usuario"]["id"]
    try:
        r = admin.put("/api/nucleo/configuracion", json={"cambios": {
            "oportunidades_activo": True, "oportunidades_frecuencia": "dias", "oportunidades_dias_semana": "1,3",
            "oportunidades_hora": 0}})
        assert r.status_code == 200, r.text
        assert admin.get(R).json()["programa"] == "Corre sola los lunes y miércoles a las 0:00"
        hoy = datetime.now(op.zona()).date()
        admin.put("/api/nucleo/configuracion", json={"cambios": {
            "oportunidades_dias_semana": str((hoy + timedelta(days=1)).isoweekday())}})
        with Session(motor()) as bd:
            assert op.revisar_programa(bd) is None  # hoy no toca
        admin.put("/api/nucleo/configuracion", json={"cambios": {"oportunidades_frecuencia": "diario"}})
        with Session(motor()) as bd:
            c = op.revisar_programa(bd)
            assert c and lanzadas == [c.corrida_id] and op.es_programada(c) and not c.competencia
            assert c.disparada_por == yo  # las ideas quedan a nombre de quien lo encendió
            assert op.revisar_programa(bd) is None  # en curso
            c.estado = "lista"
            bd.commit()
            assert op.revisar_programa(bd) is None  # ya corrió hoy
        lista = admin.get(R).json()["corridas"]
        assert lista[0]["programada"] is True

        # Cada N días se cuenta desde la última que terminó
        admin.put("/api/nucleo/configuracion", json={"cambios": {"oportunidades_frecuencia": "cada_n",
                                                                "oportunidades_cada_dias": 7}})
        assert op.toca(hoy, hoy - timedelta(days=3)) is False and op.toca(hoy, hoy - timedelta(days=7)) is True
    finally:
        admin.put("/api/nucleo/configuracion", json={"cambios": {
            k: None for k in ("oportunidades_activo", "oportunidades_frecuencia", "oportunidades_dias_semana",
                              "oportunidades_hora", "oportunidades_cada_dias")}})
    assert configuracion().oportunidades_activo is False


def test_se_quita_lo_que_no_paga_nuestro_cliente(admin: TestClient, sincrono, datos, monkeypatch):
    """Diego, 2026-11-09: «me dicen que el target de público que tenemos difícilmente los compraría». Con los tipos de
    cliente de Datos → Clientes, lo que cuesta más de lo que paga nuestro cliente en su departamento se quita."""
    from datos import clientes as cl

    h = datos["h"]
    caro = f"Creatina{h} importada 1 kg"
    mensajes: list[dict] = []
    perfil = {"tipos": [{"nombre": "Tipo ficticio", "descripcion": None, "parte_de_la_venta": 50.0}], "precios": {}}
    monkeypatch.setattr(cl, "para_oportunidades", lambda bd: perfil)
    monkeypatch.setattr(cl, "tope_de_precio", lambda p, d, pct: 100.0 if p and d and pct else None)

    def ia(bd, tarea, **kw):
        if tarea != op.TAREA_VENDIDOS:
            raise puerta.ErrorIA("sin IA en pruebas")
        mensajes.append(json.loads(kw["mensaje"]))
        return ConCitas(json.dumps({"productos": [
            {"nombre": caro, "marca": "Marca ficticia", "prueba_de_venta": "Lugar 2 en más vendidos (ficticio)",
             "tienda": "Mercado Libre", "precio": 899, "url": f"https://ejemplo.mx/caro-{h}"}]}),
            [{"url": f"https://ejemplo.mx/caro-{h}", "titulo": "x"}])

    monkeypatch.setattr(puerta, "ejecutar", ia)
    r = admin.post(R, json={"competencia": False})
    c = admin.get(f"{R}/corridas/{r.json()['id']}").json()
    assert c["estado"] == "lista", c["error"]
    por_depto = [m for m in mensajes if m.get("departamento")]
    assert por_depto and por_depto[0]["precio_que_paga_nuestro_cliente"]["a"] == 100.0
    assert caro not in [o["nombre"] for o in c["oportunidades"]]
    assert any(f"Se quitó «{caro}»: cuesta $899.00" in n for n in c["notas"])


def test_se_quita_lo_que_no_encaja_con_nuestro_cliente(admin: TestClient, sincrono, datos, monkeypatch):
    """Diego, 2026-11-10: «nuestro sector de clientes lo denominan C-… que el radar de oportunidades también valide eso».
    La IA marca cada producto contra «Nuestro cliente»: los «no» se quitan con su motivo y los «dudoso» salen marcados."""
    from datos import clientes as cl

    h = datos["h"]
    lujo, duda = f"Colageno{h} marino premium 300 g", f"Zarzaparrilla{h} raiz molida 90 g"
    monkeypatch.setattr(cl, "objetivo", lambda bd: {"nivel": "C-", "descripcion": "Cuida el gasto (ficticio)", "actualizado_en": None})
    monkeypatch.setattr(cl, "objetivo_para_ia", lambda bd: {"nivel_socioeconomico": "C-"})
    vistos: dict = {}

    def ia(bd, tarea, **kw):
        m = json.loads(kw["mensaje"])
        if tarea == op.TAREA_VENDIDOS:
            vistos["agente"] = m.get("cliente_objetivo")
            if not m.get("departamento"):
                return ConCitas(json.dumps({"productos": []}), [])
            return ConCitas(json.dumps({"productos": [
                {"nombre": n, "marca": "Marca ficticia", "prueba_de_venta": "Lugar 2 en más vendidos (ficticio)",
                 "tienda": "Mercado Libre", "precio": 150, "url": f"https://ejemplo.mx/{i}-{h}"}
                for i, n in enumerate((lujo, duda))]}),
                [{"url": f"https://ejemplo.mx/{i}-{h}", "titulo": "x"} for i in range(2)])
        if tarea == op.TAREA_IA:
            vistos["comprador"] = m.get("cliente_objetivo")
            claves = {d["producto"]: d["clave"] for d in m["datos"] if d["clave"].startswith("V")}
            return ConCitas(json.dumps({"oportunidades": [
                {"nombre": lujo, "por_que": "Se vende (ficticio)", "evidencia": [claves[lujo]], "encaje": "no",
                 "encaje_motivo": "Es de lujo para un cliente C- (ficticio)."},
                {"nombre": duda, "por_que": "Se vende (ficticio)", "evidencia": [claves[duda]], "encaje": "Dudoso",
                 "encaje_motivo": "No queda claro (ficticio)."}]}), [])
        raise puerta.ErrorIA("sin IA en pruebas")

    monkeypatch.setattr(puerta, "ejecutar", ia)
    r = admin.post(R, json={"competencia": False})
    c = admin.get(f"{R}/corridas/{r.json()['id']}").json()
    assert c["estado"] == "lista", c["error"]
    assert vistos["agente"] == {"nivel_socioeconomico": "C-"} == vistos["comprador"]
    salieron = {o["nombre"]: o for o in c["oportunidades"]}
    assert lujo not in salieron and salieron[duda]["encaje"] == "dudoso"
    assert any(f"Se quitó «{lujo}»: no encaja con nuestro cliente (C-). Es de lujo" in n for n in c["notas"])


def test_mas_vendidos_sin_api_con_google_y_la_ia_local(admin: TestClient, sincrono, datos, monkeypatch):
    """18 nov 2026: sin API externa. Google (DataForSEO, simulado) da las páginas y la IA local lee cada una; solo
    cuenta la prueba de venta que está escrita en la página, y la liga es la de esa página."""
    from modulos.compras import buscar_web as bw

    h = datos["h"]
    vendido, inventado = f"Creatina{h} monohidratada 300 g", f"Inventado{h} 60 caps"
    pagina = (f"<html><body><nav>Menú</nav><h1>Más vendidos en Suplementos</h1><p>1. {vendido} Marca ficticia</p>"
              "<p>Más de 5 mil vendidos · $399</p></body></html>")
    buscadas = []

    def google(bd, consultas, tipo, referencia, profundidad=10):
        buscadas.append((tipo, consultas))
        return bw.Busqueda(resultados=[
            bw.Resultado(url=f"https://ejemplo.mx/creatina-{h}", titulo="Más vendidos", descripcion="",
                         consulta=consultas[0], dominio="ejemplo.mx"),
            bw.Resultado(url=f"https://cerrada.mx/{h}", titulo="Lo más vendido", descripcion="No deja leer",
                         consulta=consultas[0], dominio="cerrada.mx")])

    def ia(bd, tarea, **kw):
        if tarea != op.TAREA_VENDIDOS:
            raise puerta.ErrorIA("sin IA en pruebas")
        assert not kw.get("busqueda_web")
        if kw["instrucciones"] == bw.INSTRUCCIONES_FRASES:
            return Respuesta(json.dumps({"busquedas": ["más vendidos creatina México"]}))
        m = json.loads(kw["mensaje"])
        if m["sitio"] == "ejemplo.mx":
            assert "Menú" not in m["texto"] and "Más de 5 mil vendidos" in m["texto"]
            return Respuesta(json.dumps({"productos": [
                {"nombre": vendido, "marca": "Marca ficticia", "prueba_de_venta": "Más de 5 mil vendidos", "precio": 399},
                {"nombre": inventado, "prueba_de_venta": "Número 1 en ventas del país"}]}))  # la frase no está
        return Respuesta(json.dumps({"productos": []}))

    monkeypatch.setattr(bw, "usar_web", lambda bd, tarea: True)
    monkeypatch.setattr(bw, "google", google)
    monkeypatch.setattr(bw.iv, "bajar", lambda url: pagina if "ejemplo.mx" in url else None)
    monkeypatch.setattr(puerta, "ejecutar", ia)
    c = admin.get(f"{R}/corridas/{admin.post(R, json={'competencia': False}).json()['id']}").json()
    assert c["estado"] == "lista", c["error"]
    nombres = [o["nombre"] for o in c["oportunidades"]]
    assert vendido in nombres and inventado not in nombres
    assert any("no está escrita en la página" in n for n in c["notas"])
    assert buscadas and all(t == "organico" and q == ["más vendidos creatina México"] for t, q in buscadas)
    o = next(o for o in c["oportunidades"] if o["nombre"] == vendido)
    assert "Más de 5 mil vendidos" in o["evidencia"][0]["texto"] and Decimal(o["precio_visto"]) == Decimal("399.00")
