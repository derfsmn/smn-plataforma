"""«Buscar oportunidades»: productos que no tenemos y convendría buscar (Diego, 2026-10-27; datos ficticios)."""
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
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

    o = next(x for x in c["oportunidades"] if x["nombre"] == datos["berberina"])
    r = admin.patch(f"{R}/{o['id']}", json={"estado": "descartada"})
    assert r.status_code == 200 and r.json()["estado"] == "descartada"
    estado = admin.get(R).json()
    assert estado["corridas"][0]["id"] == c["id"] and Decimal(estado["costo_maximo_competencia_usd"]) > 0


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

    def ia(bd, tarea, **kw):
        if tarea != op.TAREA_VENDIDOS:
            raise puerta.ErrorIA("sin IA en pruebas")
        assert kw["busqueda_web"] and "más vendidos" in kw["instrucciones"]
        mensaje = json.loads(kw["mensaje"])
        assert datos["unico"] in mensaje["lo_que_mas_vendemos"]
        assert any(x.startswith(f"Ashwagandha{h}") for x in mensaje["tendencias_del_radar"])  # las tendencias guían
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
    assert ev["fuente"] == "Más vendido en internet" and "+5 mil vendidos" in ev["texto"] and "Creatina para mujeres" in ev["texto"]


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
    assert llamadas == [True, False]
    assert [o["nombre"] for o in c["oportunidades"]] == [f"Magnesio{h} 120 caps"]
    assert any("contestó en texto" in n for n in c["notas"]) and any("no salió de su búsqueda" in n for n in c["notas"])


def test_instrucciones_de_la_ia_se_pueden_ver(admin: TestClient):
    """Diego, 2026-11-03: «en donde puedo ver la descripción del agente?»."""
    from modulos.compras import oportunidades as op

    lista = admin.get(f"{R}/instrucciones").json()
    # El mismo texto que recibe la IA, solo sin los cortes de línea del código
    sin_espacios = lambda t: "".join(t.split())  # noqa: E731
    assert [sin_espacios(x["texto"]) for x in lista] == [sin_espacios(t) for t in
                                                         (op.INSTRUCCIONES_VENDIDOS, op.INSTRUCCIONES, op.INSTRUCCIONES_A_JSON)]
    assert all(x["paso"] and x["que_hace"] for x in lista)
