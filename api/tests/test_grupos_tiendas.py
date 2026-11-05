"""Datos → Grupos de tiendas: k-medias en Python y texto de cada grupo con la IA local (simulada). Datos ficticios que
se borran al terminar para no mover la última semana que usan otras pruebas."""
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.bd import motor
from datos import grupos_tiendas as gt
from datos.modelos import Carga, Producto, Tienda, VentaSemanal
from ia import puerta
from tests.conftest import alta_usuario

R = "/api/datos/grupos-tiendas"
FIN = date(2027, 10, 4)  # lunes; más reciente que la venta de otras pruebas


def test_kmedias_separa_grupos_claros():
    x = [[0, 0], [0.1, 0], [0, 0.1], [5, 5], [5.1, 5], [5, 5.1], [10, 0], [10.1, 0], [10, 0.1]]
    k, etiquetas, s, opciones = gt.elegir_k(x)
    assert k == 3 and s > 0.9 and [o["grupos"] for o in opciones] == [2, 3]
    assert len({etiquetas[0], etiquetas[3], etiquetas[6]}) == 3 and etiquetas[0] == etiquetas[1] == etiquetas[2]


@pytest.fixture
def tiendas(monkeypatch):
    """9 tiendas en 3 perfiles: fuertes en A, en B o en C."""
    monkeypatch.setattr(gt, "en_hilo", lambda i, g=None, c=None: _correr(i, g, c))
    h = uuid.uuid4().hex[:4]
    deptos = [f"Depto G{h}{x}" for x in "ABC"]
    skus = [f"GT-{h}-{x}" for x in "ABC"]
    almacenes = [f"G{h}{i}" for i in range(9)]
    with Session(motor()) as bd:
        c = Carga(fuente="SMNBI_TIENDAS", disparada_por="manual", estado="completa")
        bd.add(c)
        bd.flush()
        for s, d in zip(skus, deptos):
            bd.add(Producto(sku=s, descripcion=f"Producto {d}", departamento=d, origen="ETL", activo=True))
        for i, a in enumerate(almacenes):
            perfil = i // 3
            bd.add(Tienda(almacen=a, nombre=f"Tienda grupo {i}", region=f"Región {perfil}", categoria="B",
                          carga_id=c.carga_id))
            for j, s in enumerate(skus):
                piezas = Decimal(80 if j == perfil else 10) + i % 3  # pequeñas diferencias dentro del perfil
                for w in range(12):
                    lunes = FIN - timedelta(weeks=w)
                    bd.add(VentaSemanal(mes=lunes.replace(day=1), sku=s, tienda=a, semana=lunes, empresa="EJ",
                                        piezas=piezas, piezas_devueltas=Decimal(0), importe_bruto=piezas * 10,
                                        descuento=Decimal(0), importe=piezas * 10, costo=piezas * 5, tickets=1,
                                        carga_id=c.carga_id))
        bd.commit()
    yield {"almacenes": almacenes, "deptos": deptos}
    with Session(motor()) as bd:
        bd.execute(delete(VentaSemanal).where(VentaSemanal.sku.in_(skus)))
        bd.commit()


def _correr(corrida_id, grupos=None, criterios=None):
    from core.bd import _fabrica
    with _fabrica()() as bd:
        gt.calcular(bd, corrida_id, grupos, criterios)


def test_grupos_con_ia_local(admin, tiendas, monkeypatch):
    llamadas = []

    def falsa(bd, tarea, **kw):
        llamadas.append((tarea, kw.get("proveedor")))
        grupos = json.loads(kw["mensaje"])["grupos"]
        return puerta.Respuesta(texto=json.dumps({"grupos": [
            {"grupo": g["grupo"], "nombre": f"Nombre {g['grupo']}", "descripcion": "Descripción ficticia",
             "acciones": ["Acción ficticia"]} for g in grupos] + [{"grupo": 99, "nombre": "Inventado"}]}),
            proveedor="ollama", modelo="x", tokens_entrada=1, tokens_salida=1, costo_mxn=Decimal(0), duracion_ms=1,
            completa=True, llamada_id=1)
    monkeypatch.setattr(puerta, "ejecutar", falsa)

    r = admin.post(f"{R}/calcular", json={"criterios": {"mezcla": 1}})
    assert r.status_code == 202, r.text
    d = admin.get(R).json()
    assert d["corrida"]["estado"] == "completa", d
    assert llamadas == [("datos.tiendas_grupos", "ollama")]  # siempre IA local
    grupo = {t["almacen"]: t["grupo"] for t in d["tiendas"]}
    a = tiendas["almacenes"]
    for p in range(3):
        assert grupo[a[3 * p]] == grupo[a[3 * p + 1]] == grupo[a[3 * p + 2]]
    assert len({grupo[a[0]], grupo[a[3]], grupo[a[6]]}) == 3
    nombres = {g["grupo"]: g for g in d["grupos"]}
    assert not any(g["nombre"] == "Inventado" for g in d["grupos"])
    g0 = nombres[grupo[a[0]]]
    assert g0["nombre"].startswith("Nombre") and g0["acciones"] == ["Acción ficticia"]
    assert g0["de_mas"][0]["departamento"] == tiendas["deptos"][0]


def test_si_la_ia_local_falla_quedan_con_numero(admin, tiendas, monkeypatch):
    def falla(*a, **kw):
        raise puerta.ErrorIA("Ollama no responde")
    monkeypatch.setattr(puerta, "ejecutar", falla)
    admin.post(f"{R}/calcular", json={"criterios": {"mezcla": 1}})
    d = admin.get(R).json()
    assert d["corrida"]["estado"] == "completa"
    assert "Ollama no responde" in d["corrida"]["nota_ia"]
    assert all(g["nombre"].startswith("Grupo ") for g in d["grupos"])


def test_pedir_cuantos_grupos(admin, tiendas, monkeypatch):
    monkeypatch.setattr(puerta, "ejecutar", lambda *a, **kw: (_ for _ in ()).throw(puerta.ErrorIA("apagado")))
    assert admin.post(f"{R}/calcular", json={"grupos": 1}).status_code == 422
    assert admin.post(f"{R}/calcular", json={"grupos": 2, "criterios": {"mezcla": 1}}).status_code == 202
    d = admin.get(R).json()
    assert d["corrida"]["grupos"] == 2 and len(d["grupos"]) == 2
    ctx = d["corrida"]["contexto"]
    assert ctx["pedidos"] == 2 and {o["grupos"] for o in ctx["opciones"]} >= {2, 3}


def test_por_ventas_y_criterios_sin_datos(admin, tiendas, monkeypatch):
    monkeypatch.setattr(puerta, "ejecutar", lambda *a, **kw: (_ for _ in ()).throw(puerta.ErrorIA("apagado")))
    assert admin.post(f"{R}/calcular", json={"criterios": {"nada": 1}}).status_code == 422
    assert admin.post(f"{R}/calcular", json={"criterios": {"ventas": 0}}).status_code == 422
    # Por ventas: las tiendas se juntan por tamaño (i % 3), no por departamento
    admin.post(f"{R}/calcular", json={"criterios": {"ventas": 1}, "grupos": 3})
    d = admin.get(R).json()
    assert d["corrida"]["estado"] == "completa", d
    grupo = {t["almacen"]: t["grupo"] for t in d["tiendas"]}
    a = tiendas["almacenes"]
    assert grupo[a[0]] == grupo[a[3]] == grupo[a[6]] and grupo[a[1]] == grupo[a[4]] == grupo[a[7]]
    assert d["grupos"][0]["distintivos"][0]["criterio"] == "ventas"
    assert d["tiendas"][0]["metricas"]["venta_semanal"] > 0
    # Tendencia plana y tiendas sin coordenadas: se avisa que no se usaron y se agrupa con lo demás
    admin.post(f"{R}/calcular", json={"criterios": {"mezcla": 2, "tendencia": 1, "demografia": 1}})
    ctx = admin.get(R).json()["corrida"]["contexto"]
    assert ctx["criterios"] == {"mezcla": 2}
    assert any("Tendencia" in x for x in ctx["avisos"]) and any("Demograf" in x for x in ctx["avisos"])


def test_abajo_de_sus_pares():
    met = {"a": {"venta_semanal": 500.0, "cambio": -20.0, "margen": 30.0},
           "b": {"venta_semanal": 1000.0, "cambio": -2.0, "margen": 40.0},
           "c": {"venta_semanal": 1100.0, "cambio": 0.0, "margen": 41.0}}
    tipos = [x["tipo"] for x in gt._alertas("a", ["b", "c"], met)]
    assert tipos == ["venta", "cambio", "margen"]
    assert gt._alertas("b", ["a", "c"], met) == []
    assert gt._alertas("a", ["b"], met) == []  # con un solo par no se compara


def test_localidad_del_censo(monkeypatch):
    from datos import demografia
    assert demografia.coordenada("102°17'45.768\" W") == pytest.approx(-102.29605, abs=1e-4)
    assert demografia.coordenada("21°52'47.362\" N") == pytest.approx(21.87982, abs=1e-4)
    base = {"municipio": "M", "estado": "E", "pct_60_mas": 10.0, "pct_0_14": 25.0, "escolaridad": 10.0,
            "pct_auto": 50.0, "pct_internet": 60.0, "pct_computadora": 40.0, "pct_sin_salud": 20.0}
    locs = ({"clave": "1", "localidad": "Ciudad grande", "lat": 20.0, "lon": -103.0, "poblacion": 1_500_000} | base,
            {"clave": "2", "localidad": "Pueblo", "lat": 20.0, "lon": -103.12, "poblacion": 3000} | base)
    monkeypatch.setattr(demografia, "cargar", lambda: locs)
    # A 9 km del centro de la ciudad grande y a 2 km del pueblo: queda en la ciudad (está dentro de su mancha)
    loc, km = demografia.cercana(20.0, -103.086)
    assert loc["localidad"] == "Ciudad grande" and km == pytest.approx(9, abs=0.5)
    assert demografia.cercana(20.0, -103.15)[0]["localidad"] == "Pueblo"
    assert demografia.cercana(25.0, -100.0) is None


def test_permisos(admin):
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    assert consulta.get(R).status_code in (200, 403)
    assert consulta.post(f"{R}/calcular").status_code == 403
