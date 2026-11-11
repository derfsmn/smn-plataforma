"""Datos → Clientes: tipos de cliente con k-medias y nombres con la IA local (simulada). Datos ficticios: 3 tipos de
cliente inventados (frecuente de suplementos, de abarrotes una vez, de cuidado personal caro) y cuentas genéricas."""
import json
import random
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.bd import motor
from datos import clientes as cl
from datos.modelos import ClienteCorrida
from ia import puerta
from tests.conftest import alta_usuario

R = "/api/datos/clientes"
SUP, ABA, CUI = "Prevención y salud", "Abarrotes comestible", "Cuidado personal"


def csv_ficticio(n: int = 60) -> bytes:
    azar = random.Random(3)
    filas = []
    for i in range(n):
        filas.append(f"F{i:05d},TDA1,1,9,{18 + azar.randint(0, 4)},{SUP},{18},{40 + azar.randint(0, 5)},{8000 + azar.randint(0, 300)}")
        filas.append(f"F{i:05d},TDA1,1,9,{18 + azar.randint(0, 4)},{ABA},{3},{5},{300}")
    for i in range(n):
        filas.append(f"A{i:05d},TDA2,1,1,1,{ABA},1,{6 + azar.randint(0, 3)},{150 + azar.randint(0, 30)}")
    for i in range(n):
        filas.append(f"C{i:05d},TDA3,2,4,{5 + azar.randint(0, 2)},{CUI},5,{6},{2400 + azar.randint(0, 200)}")
    filas += [f"GENERICO,,120,9,400000,{SUP},200000,900000,90000000", f"GENERICO,,120,9,400000,{ABA},150000,600000,20000000"]
    return ("cliente,tienda_principal,tiendas,meses,notas,departamento,notas_depto,piezas,importe\n"
            + "\n".join(filas) + "\n").encode()


def test_leer_y_tipos_sin_base():
    clientes, gen, leidos = cl.leer(csv_ficticio())
    assert len(clientes) == 180 and leidos == 242 and gen["cuentas"] == 120 and gen["notas"] == 400000
    r = cl.calcular_tipos(clientes, gen, {"TDA1": "Norte", "TDA2": "Centro", "TDA3": "Sur"})
    assert r["tipos"] == 3 and r["calidad"] > 0.5
    por_depto = {p["mezcla"][0]["departamento"]: p for p in r["perfiles"]}
    assert set(por_depto) == {SUP, ABA, CUI}
    assert por_depto[SUP]["compras_al_mes"] > 1 and por_depto[ABA]["compras_al_mes"] == 1
    assert por_depto[SUP]["regiones"][0] == {"region": "Norte", "parte": 100.0}
    assert por_depto[CUI]["precios"][CUI]["p50"] > 300  # ~400 la pieza
    res = r["resumen"]
    assert res["clientes"] == 180 and res["parte_notas_identificadas"] < 1  # casi todo es genérico
    assert res["precios_por_departamento"][ABA]["p90"] <= 61  # los frecuentes pagan 60 la pieza
    assert set(res["parte_venta_por_departamento"]) == {SUP, ABA, CUI}
    assert abs(sum(res["parte_venta_por_departamento"].values()) - 100) < 0.1
    with pytest.raises(ValueError, match="columnas"):
        cl.leer(b"a,b,c\n")


def test_departamento_chico_no_pone_tope():
    # Caso real del 9 nov: SUPLEMENTOS salía a $1 la pieza y habría quitado todo lo de ese departamento
    resumen = {"precios_por_departamento": {"SUPLEMENTOS": {"p90": 1}, ABA: {"p90": 60}},
               "parte_venta_por_departamento": {"SUPLEMENTOS": 0.2, ABA: 17.8}}
    assert set(cl.precios_con_tope(resumen)) == {ABA}
    assert cl.precios_con_tope({"precios_por_departamento": {ABA: {"p90": 60}}}) == {}  # corrida vieja: sin tope


def test_percentiles_pesados_por_piezas():
    p = cl.percentiles([(10, 90), (100, 10)])
    assert p["p50"] == 10 and p["p95"] == 100


@pytest.fixture
def sincrono(monkeypatch):
    def correr(corrida_id, pedido=None):
        from core.bd import _fabrica
        with _fabrica()() as bd:
            cl.calcular(bd, corrida_id, pedido)
    monkeypatch.setattr(cl, "en_hilo", correr)
    yield
    with Session(motor()) as bd:
        bd.execute(delete(ClienteCorrida))
        bd.commit()


def test_subir_calcular_y_nombres_con_ia_local(admin, sincrono, monkeypatch):
    llamadas = []

    def falsa(bd, tarea, **kw):
        llamadas.append((tarea, kw.get("proveedor")))
        tipos = json.loads(kw["mensaje"])["tipos"]
        assert "F00001" not in kw["mensaje"]  # los códigos de cliente no salen a la IA
        return puerta.Respuesta(texto=json.dumps({"tipos": [
            {"tipo": t["tipo"], "nombre": f"Tipo ficticio {t['tipo']}", "descripcion": "Descripción ficticia",
             "acciones": ["Acción ficticia"]} for t in tipos]}),
            proveedor="ollama", modelo="x", tokens_entrada=1, tokens_salida=1, costo_mxn=Decimal(0), duracion_ms=1,
            completa=True, llamada_id=1)
    monkeypatch.setattr(puerta, "ejecutar", falsa)

    (cl._carpeta() / "clientes.csv.gz").unlink(missing_ok=True)
    assert admin.post(f"{R}/calcular").status_code == 409  # sin archivo no hay qué recalcular
    assert admin.post(f"{R}/cargar", files={"archivo": ("malo.csv", b"x,y\n1,2\n", "text/csv")}).status_code == 400
    r = admin.post(f"{R}/cargar", files={"archivo": ("clientes.csv", csv_ficticio(), "text/csv")})
    assert r.status_code == 202, r.text
    d = admin.get(R).json()
    assert d["corrida"]["estado"] == "completa", d
    assert llamadas == [("datos.clientes_tipos", "ollama")]
    assert len(d["tipos"]) == 3 and all(t["nombre"].startswith("Tipo ficticio") for t in d["tipos"])
    assert d["resumen"]["cuentas_genericas"] == 120 and d["hay_archivo"]
    assert "HASHBYTES" in admin.get(f"{R}/consulta").text

    r = admin.post(f"{R}/calcular", json={"tipos": 2})
    assert r.status_code == 202 and admin.get(R).json()["corrida"]["tipos"] == 2

    # Para «Buscar oportunidades»: el tope de precio con IVA del departamento
    with Session(motor()) as bd:
        perfil = cl.para_oportunidades(bd)
    assert len(perfil["tipos"]) == 2
    tope = cl.tope_de_precio(perfil, "abarrotes COMESTIBLE", 90)
    assert tope and tope <= 61 * cl.IVA
    assert cl.tope_de_precio(perfil, "Inventado", 90) is None and cl.tope_de_precio(perfil, ABA, 0) is None


def test_permisos(admin):
    _, kiosco, _ = alta_usuario(admin, rol="kiosco_tienda")
    assert kiosco.get(R).status_code == 403
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    assert consulta.post(f"{R}/calcular").status_code == 403


def test_nuestro_cliente_se_define_y_llega_a_la_ia(admin):
    """Diego, 2026-11-10: «nuestro sector de clientes lo denominan C-»."""
    with Session(motor()) as bd:
        antes = cl.objetivo(bd)
    try:
        d = admin.get(R).json()
        assert d["objetivo"]["nivel"] == "C-" and "C-" in d["niveles"]  # la migración lo deja en C-
        assert admin.put(f"{R}/objetivo", json={"nivel": "Z"}).status_code == 422
        r = admin.put(f"{R}/objetivo", json={"nivel": "D+", "descripcion": "  Cuida el gasto (ficticio)  "})
        assert r.status_code == 200 and r.json()["descripcion"] == "Cuida el gasto (ficticio)"
        with Session(motor()) as bd:
            ia = cl.objetivo_para_ia(bd)
        assert ia["nivel_socioeconomico"] == "D+" and ia["descripcion_de_compras"] == "Cuida el gasto (ficticio)"
        _, kiosco, _ = alta_usuario(admin, rol="kiosco_tienda")
        assert kiosco.put(f"{R}/objetivo", json={"nivel": "C"}).status_code == 403
    finally:
        with Session(motor()) as bd:
            cl.guardar_objetivo(bd, antes["nivel"], antes["descripcion"], None)
            bd.commit()


def test_borrador_de_nuestro_cliente_sale_de_los_datos():
    clientes, gen, _ = cl.leer(csv_ficticio())
    r = cl.calcular_tipos(clientes, gen, {})

    class Corrida:
        perfiles, resumen = json.dumps(r["perfiles"]), json.dumps(r["resumen"])

    original, cl.ultima = cl.ultima, lambda bd: Corrida
    try:
        texto = cl.borrador_objetivo(None)
    finally:
        cl.ultima = original
    assert "veces al mes" in texto and "Prevención y salud" in texto and "por pieza" in texto


def test_el_asistente_del_producto_conoce_a_nuestro_cliente(monkeypatch):
    """Diego, 2026-11-10: «Pregúntale a la IA» contestaba qué compraría un cliente C- con el semáforo. Ahora la ficha
    trae la sección «Nuestro cliente» con lo que paga en el departamento contra el precio del producto."""
    from modulos.compras import asistente_comite as ac

    monkeypatch.setattr(cl, "objetivo", lambda bd: {"nivel": "C-", "descripcion": "Cuida el gasto (ficticio)", "actualizado_en": None})
    monkeypatch.setattr(cl, "borrador_objetivo", lambda bd: None)
    monkeypatch.setattr(cl, "para_oportunidades", lambda bd: {"tipos": [], "precios": {}})
    monkeypatch.setattr(cl, "tope_de_precio", lambda p, d, pct: {75: 100.0, 90: 150.0}[pct] if d else None)
    with Session(motor()) as bd:
        (s,) = ac._cliente(bd, {"departamento": SUP, "precio": "320"}, None)
        assert s.titulo == "Nuestro cliente" and "C-" in s.texto and "Cuida el gasto" in s.texto
        assert s.texto.startswith("VEREDICTO POR PRECIO (calculado con sus compras, con IVA): NO, por precio") and "$320" in s.texto
        (s,) = ac._cliente(bd, {"departamento": SUP, "precio": "90"}, None)
        assert "SÍ le alcanza" in s.texto
        (s,) = ac._cliente(bd, {"departamento": SUP, "precio": "120"}, None)
        assert "DUDOSO por precio" in s.texto
        monkeypatch.setattr(cl, "objetivo", lambda bd: None)
        assert ac._cliente(bd, {"departamento": SUP}, None) == []
    assert "El semáforo NO dice quién compra" in ac.INSTRUCCIONES_PRODUCTOS and "No lo cambies ni lo suavices" in ac.INSTRUCCIONES
