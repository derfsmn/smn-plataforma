"""Innovación Vidanat (TD005), Entrega 1: los 6 casos mínimos del documento y las pruebas de diseño T10–T17.

Todo es [EJEMPLO]. La IA local y las fuentes de internet se simulan: las pruebas no salen del contenedor.
"""
import hashlib
import io
import uuid
import json
import shutil
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.conftest import alta_usuario
from core.bd import motor as motor_bd
from ia import puerta
from modulos.innovacion import evaluacion as evs
from modulos.innovacion import fuentes_externas as fx
from modulos.innovacion import indice, investigador, trabajos
from modulos.innovacion import motor
from modulos.innovacion.modelos import Expediente, Seccion, Trabajo
from nucleo import busqueda

API = "/api/innovacion"
MAGNESIO = {"para_cada": {"lista": "ingredientes", "donde": {
    "alguna": [{"igual": ["tipo", "mineral"]}, {"igual": ["tipo", "vitamina"]}], "y": {"igual": ["en_compuesto", True]}}},
    "todas": [{"existe": "cantidad_compuesto"}, {"existe": "cantidad_activa"},
              {"unidades_compatibles": ["unidad_compuesto", "unidad_activa"], "dimension": "masa"},
              {"comparar": ["cantidad_activa", "<=", "cantidad_compuesto"], "convertir_a": "mg"}]}


# ---------------------------------------------------------------- IA y fuentes simuladas

def _huella(bd, tarea, textos, usuario_id=None):
    salida = []
    for t in textos:
        v = [0.0] * 64
        for p in busqueda.palabras(t):
            v[int(hashlib.md5(p.encode()).hexdigest(), 16) % 64] += 1
        salida.append(v)
    return "ficticio", salida


def _ia(bd, tarea, *, mensaje="", **k):
    if tarea == "innovacion.responder":
        if "insomnio" in mensaje.lower() and "melatonina" not in mensaje.lower():
            return SimpleNamespace(texto="EVIDENCIA_INSUFICIENTE")
        return SimpleNamespace(texto="El bisglicinato de magnesio se absorbe mejor que el óxido [1]. Dato inventado [9].")
    if tarea == "innovacion.sugerir_datos":
        return SimpleNamespace(texto=json.dumps({"titulo": "Absorción de magnesio", "anio": 2021, "tipo": "ensayo_clinico",
                                                 "resumen": "Ensayo [EJEMPLO]"}))
    if tarea == "innovacion.investigar":
        if "Fuentes:" in mensaje:
            return SimpleNamespace(texto="El bisglicinato tiene buena biodisponibilidad [1]. Falta evidencia en sueño.")
        return SimpleNamespace(texto=json.dumps({"material": "bisglicinato de magnesio", "poblacion": "40 adultos",
                                                 "cantidad": "300 mg", "resultado": "mayor absorción",
                                                 "responde": "si", "cita": "magnesium bisglycinate showed higher absorption"}))
    if tarea == "innovacion.sugerir_dictamen":
        return SimpleNamespace(texto=json.dumps({"sugerencia": "cumple", "razon": "La fuente respalda la forma [1].", "falta": None}))
    raise puerta.ErrorIA("tarea no simulada")


@pytest.fixture
def ia(monkeypatch):
    monkeypatch.setattr(puerta, "vectores", _huella)
    monkeypatch.setattr(puerta, "ejecutar", _ia)
    monkeypatch.setattr(puerta, "estado_ollama", lambda: {"disponible": True, "modelos": []})
    indice.olvidar()


@pytest.fixture
def sin_ia(monkeypatch):
    def apagado(*a, **k):
        raise puerta.ErrorIA("No hay conexión con Ollama.")
    monkeypatch.setattr(puerta, "vectores", apagado)
    monkeypatch.setattr(puerta, "ejecutar", apagado)
    monkeypatch.setattr(puerta, "estado_ollama", lambda: {"disponible": False, "modelos": []})
    indice.olvidar()


# ---------------------------------------------------------------- personas [EJEMPLO]

@pytest.fixture
def equipo(admin):
    """Investigador y formulación del equipo; líder, directivo y un investigador ajeno al folio."""
    gente = {}
    for clave, rol in (("inv", "innovacion_investigador"), ("form", "innovacion_formulacion"), ("lider", "innovacion_lider"),
                       ("dir", "innovacion_directivo"), ("ajeno", "innovacion_investigador"), ("lider2", "innovacion_lider")):
        _, c, uid = alta_usuario(admin, rol=rol)
        gente[clave] = SimpleNamespace(c=c, id=uid)
    return gente


def _pdf(paginas: list[list[str]]) -> bytes:
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=letter)
    for lineas in paginas:
        y = 720
        for linea in lineas:
            c.drawString(60, y, linea)
            y -= 18
        c.showPage()
    c.save()
    return b.getvalue()


ESTUDIO = _pdf([["EJEMPLO Absorption of magnesium forms", "", "1. Introducción",
                 "Ensayo ficticio para pruebas sobre formas de magnesio en adultos sanos."],
                ["2. Resultados", "magnesium bisglycinate showed higher absorption than magnesium oxide",
                 "El bisglicinato de magnesio mostró mayor absorción que el óxido en 40 adultos."],
                ["3. Limitaciones", "Muestra pequeña y duración de 8 semanas."]])


def _cargar(c, datos: dict, archivos=None):
    files = [("archivos", (n, b, "application/octet-stream")) for n, b in (archivos or [])]
    return c.post(f"{API}/recursos", data={"datos": json.dumps(datos)}, files=files or None)


def _ingrediente(c, nombre, tipo, sinonimos=()):
    r = c.post(f"{API}/ingredientes", json={"nombre": nombre, "tipo": tipo, "sinonimos": list(sinonimos)})
    if r.status_code == 409:
        return next(i["id"] for i in c.get(f"{API}/ingredientes", params={"q": nombre}).json() if i["nombre"] == nombre)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _expediente(c, nombre, equipo_ids=(), categoria="suplemento_alimenticio"):
    r = c.post(f"{API}/expedientes", json={"nombre": nombre, "categoria_sanitaria": categoria, "equipo": list(equipo_ids)})
    assert r.status_code == 201, r.text
    return r.json()["folio"]


def _ficha(c, folio, ingredientes, declaraciones=None):
    r = c.post(f"{API}/expedientes/{folio}/fichas", json={"datos": {"declaraciones": declaraciones or ["Ayuda a la relajación"]},
                                                        "ingredientes": ingredientes})
    assert r.status_code == 201, r.text
    return r.json()


def _revisar(c, recurso_id, numero=1):
    r = c.post(f"{API}/recursos/{recurso_id}/versiones/{numero}/revision",
               json={"respalda": "Mayor absorción del bisglicinato [EJEMPLO]", "limites": "Muestra pequeña"})
    assert r.status_code == 200, r.text


def _regla(autor, aprobador, codigo, condicion, *, alcance=None, severidad="bloqueante", fuente_version_id, desde=None,
           modo="automatica", admite_excepcion=False, rol_revisor=None, publicar=True):
    datos = {"area": codigo.split("-")[1], "codigo": codigo, "nombre": f"[EJEMPLO] {codigo}", "proposito": f"Prueba {codigo}",
             "modo": modo, "alcance": alcance or {}, "condicion": condicion, "severidad": severidad,
             "fuente_version_id": fuente_version_id, "fuente_ubicacion": "pág. 2",
             "vigente_desde": (desde or date.today() - timedelta(days=1)).isoformat(), "admite_excepcion": admite_excepcion,
             "rol_revisor": rol_revisor}
    r = autor.post(f"{API}/reglas", json=datos)
    assert r.status_code == 201, r.text
    regla = r.json()
    assert autor.post(f"{API}/reglas/{regla['id']}/versiones/1/enviar").status_code == 200
    if publicar:
        r = aprobador.post(f"{API}/reglas/{regla['id']}/versiones/1/publicar")
        assert r.status_code == 200, r.text
    return regla


@pytest.fixture
def fuente(equipo, ia):
    """Un ensayo [EJEMPLO] cargado con enlace y PDF, leído, revisado y ligado al magnesio."""
    inv, lider = equipo["inv"].c, equipo["lider"].c
    mg = _ingrediente(inv, "Magnesio", "mineral", ["bisglicinato de magnesio", "magnesium"])
    r = _cargar(inv, {"titulo": f"EJEMPLO Absorción de magnesio {hashlib.md5(str(id(equipo)).encode()).hexdigest()[:6]}",
                      "tipo": "ensayo_clinico", "url": "https://ejemplo.mx/estudio", "ingredientes": [mg]},
                [("estudio.pdf", ESTUDIO + str(id(equipo)).encode())])
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    _revisar(lider, rid)
    d = inv.get(f"{API}/recursos/{rid}").json()
    return SimpleNamespace(id=rid, version_id=d["versiones"][0]["version_id"], mg=mg, detalle=d)


# ---------------------------------------------------------------- caso 1 · fuente con URL y archivo, citar sección

def test_caso1_cargar_vincular_y_citar(equipo, fuente):
    inv = equipo["inv"].c
    v = fuente.detalle["versiones"][0]
    assert v["url"] == "https://ejemplo.mx/estudio" and v["archivos"][0]["sha256"]
    assert v["estado"] == "revisado" and v["procesado"] == "listo" and v["secciones"] >= 3
    assert any(x["tipo"] == "ingrediente" and x["ingrediente"] == "Magnesio" for x in v["vinculos"])
    assert v["sugerencias"]["tipo"] == "ensayo_clinico"  # la IA local sugirió; la persona confirma
    # buscar por sinónimo y citar la sección de la página 2
    r = inv.get(f"{API}/buscar", params={"q": "absorción bisglicinato", "ingrediente": fuente.mg}).json()
    hit = next(h for h in r["resultados"] if h["recurso_id"] == fuente.id and h["pagina"] == 2)
    folio = _expediente(inv, "[EJEMPLO] Magnesio relajación")
    r = inv.post(f"{API}/expedientes/{folio}/evidencia", json={"version_id": hit["version_id"], "fragmento_id": hit["fragmento_id"],
                                                             "respalda": "Mejor absorción del bisglicinato"})
    assert r.status_code == 201 and r.json()["pagina"] == 2 and r.json()["version"] == 1
    sec = inv.get(f"{API}/secciones/{hit['fragmento_id']}").json()
    assert sec["pagina"] == 2 and sec["version"] == 1 and "bisglicinato" in sec["texto"]
    # el mismo archivo otra vez no entra dos veces
    r = _cargar(inv, {"titulo": "Otra vez", "tipo": "ensayo_clinico"}, [("x.pdf", ESTUDIO + str(id(equipo)).encode())])
    assert r.status_code == 409
    # una versión nueva sustituye a la anterior solo al revisarse; la anterior se conserva
    r = inv.post(f"{API}/recursos/{fuente.id}/versiones", data={"datos": json.dumps({"texto": "# Fe de erratas\nSin cambios de fondo."})})
    assert r.status_code == 201
    _revisar(equipo["lider"].c, fuente.id, 2)
    d = inv.get(f"{API}/recursos/{fuente.id}").json()
    assert [x["estado"] for x in d["versiones"]] == ["revisado", "sustituido"]
    assert d["versiones"][1]["uso"]["citas"][0]["folio"] == folio


# ---------------------------------------------------------------- caso 2 · alcance, vigencia, dato faltante y compuerta

def test_caso2_alcance_vigencia_faltante_y_bloqueo(equipo, fuente):
    inv, lider = equipo["inv"].c, equipo["lider"].c
    regla = _regla(inv, lider, "R-COMP-901", MAGNESIO, alcance={"categoria_sanitaria": "suplemento_alimenticio",
                                                                "etapa_destino": "filtro"},
                   fuente_version_id=fuente.version_id)
    dentro = _expediente(inv, "[EJEMPLO] Dentro de alcance")
    fuera = _expediente(inv, "[EJEMPLO] Fuera de alcance", categoria="alimento")
    ings = [{"nombre": "Magnesio (bisglicinato)", "tipo": "mineral", "en_compuesto": True, "cantidad_compuesto": 1986,
             "unidad_compuesto": "mg", "cantidad_activa": 280, "unidad_activa": "mg", "ingrediente_id": fuente.mg},
            {"nombre": "Vitamina B6 (piridoxina HCl)", "tipo": "vitamina", "en_compuesto": True, "cantidad_compuesto": 2.4,
             "unidad_compuesto": "mg"}]
    _ficha(inv, dentro, ings)
    _ficha(inv, fuera, ings)
    d = inv.get(f"{API}/expedientes/{dentro}").json()
    res = next(r for r in d["evaluacion"]["resultados"] if r["regla"] == "R-COMP-901")
    assert res["resultado"] == "pendiente"  # T03: dato faltante con la ruta exacta
    assert "ingredientes[2].cantidad_activa" in res["faltantes"] and "Vitamina B6" in res["motivo"]
    assert res["datos_usados"]["ingredientes[1].cantidad_compuesto"] == "1986 mg"
    f = inv.get(f"{API}/expedientes/{fuera}").json()
    assert next(r for r in f["evaluacion"]["resultados"] if r["regla"] == "R-COMP-901")["resultado"] == "no_aplica"
    # evaluada antes de su vigencia, la regla no aplica
    with Session(motor_bd()) as bd:
        e = bd.scalar(select(Expediente).where(Expediente.folio == dentro))
        antes = evs.evaluar(bd, e, motivo="manual", usuario_id=None, dia=date.today() - timedelta(days=30))
        assert all(bd.get(evs.ReglaVersion, r.regla_version_id).regla.codigo != "R-COMP-901" for r in antes.resultados)
        bd.commit()
    _ficha(inv, dentro, ings)  # la evaluación vigente vuelve a ser de hoy
    # T04: el bloqueante impide avanzar
    r = inv.post(f"{API}/expedientes/{dentro}/enviar", json={"etapa": "filtro"})
    assert r.status_code == 409 and "R-COMP-901" in json.dumps(r.json())
    ings[1].update(cantidad_activa=2, unidad_activa="mg")
    _ficha(inv, dentro, ings)
    assert inv.post(f"{API}/expedientes/{dentro}/enviar", json={"etapa": "filtro"}).status_code == 200
    assert regla["codigo"] == "R-COMP-901"


# ---------------------------------------------------------------- caso 3 · otra evaluación sin tocar la anterior

def test_caso3_evaluaciones_inmutables_y_decision(equipo, fuente):
    inv, lider, form, directivo = equipo["inv"].c, equipo["lider"].c, equipo["form"].c, equipo["dir"].c
    folio = _expediente(inv, "[EJEMPLO] Historial", [equipo["form"].id])
    ings = [{"nombre": "Magnesio", "tipo": "mineral", "cantidad_activa": 280, "unidad_activa": "mg"}]
    _ficha(inv, folio, ings)
    primera = inv.get(f"{API}/expedientes/{folio}/evaluaciones/1").json()
    _regla(inv, lider, "R-COMP-902", {"para_cada": {"lista": "ingredientes", "donde": {"igual": ["tipo", "mineral"]}},
                                      "rango": {"campo": "cantidad_activa", "max": 350, "unidad": "mg"}},
           fuente_version_id=fuente.version_id, severidad="mayor")
    lista = inv.get(f"{API}/expedientes/{folio}/evaluaciones").json()
    assert lista[0]["motivo"] == "regla" and lista[0]["regla"] == "R-COMP-902"
    assert inv.get(f"{API}/expedientes/{folio}/evaluaciones/1").json() == primera
    # cambiar la fórmula registra otra evaluación
    r = form.post(f"{API}/expedientes/{folio}/formulas", json={"componentes": [{"nombre": "Bisglicinato de magnesio",
                                                                               "cantidad": 1986, "unidad": "mg"}]})
    assert r.status_code == 201
    ultima = inv.get(f"{API}/expedientes/{folio}/evaluaciones").json()[0]
    assert ultima["motivo"] == "formula"
    comp = inv.get(f"{API}/expedientes/{folio}/comparar", params={"a": 1, "b": ultima["numero"]}).json()
    assert any(c["regla"] == "R-COMP-902" and c["antes"] is None for c in comp["cambios"])
    # la decisión queda ligada a su evaluación y su versión congelada
    assert inv.post(f"{API}/expedientes/{folio}/enviar", json={"etapa": "filtro"}).status_code == 200
    assert inv.post(f"{API}/expedientes/{folio}/decisiones", json={"resultado": "avanzar", "motivo": "No me toca"}).status_code == 403
    r = directivo.post(f"{API}/expedientes/{folio}/decisiones", json={"resultado": "avanzar", "motivo": "Aprobado con condiciones [EJEMPLO]",
                                                                      "condiciones": "Confirmar estabilidad"})
    assert r.status_code == 201, r.text
    d = directivo.get(f"{API}/expedientes/{folio}/decisiones/{r.json()['id']}").json()
    assert d["evaluacion"] == ultima["numero"] and d["congelado"]["formula_id"]
    _ficha(inv, folio, ings + [{"nombre": "Ashwagandha", "tipo": "botanico"}])
    d2 = directivo.get(f"{API}/expedientes/{folio}/decisiones/{r.json()['id']}").json()
    assert d2["evaluacion"] == d["evaluacion"] and d2["ficha"] == d["ficha"]


# ---------------------------------------------------------------- caso 4 · sin acceso a la fórmula: nada en ninguna salida

def test_caso4_formula_fuera_de_busqueda_ia_descargas_y_pdf(equipo, ia):
    inv, form, ajeno = equipo["inv"].c, equipo["form"].c, equipo["ajeno"].c
    folio = _expediente(inv, "[EJEMPLO] Secreto", [equipo["form"].id])
    r = _cargar(form, {"titulo": "EJEMPLO Fórmula maestra zafiro", "tipo": "prueba_interna", "clasificacion": "formula",
                       "folio": folio, "texto": "# Fórmula\nLa mezcla zafiro lleva 37 partes de excipiente turquesa."})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    pdf_formula = _cargar(form, {"titulo": "EJEMPLO Hoja de fórmula", "tipo": "prueba_interna", "clasificacion": "formula",
                                 "folio": folio}, [("formula.pdf", _pdf([["Excipiente turquesa zafiro"]]))])
    archivo = pdf_formula.json()["archivos"][0]["id"]
    form.post(f"{API}/expedientes/{folio}/formulas", json={"componentes": [{"nombre": "Excipiente turquesa", "cantidad": 37,
                                                                           "unidad": "mg"}]})
    # quien es del equipo sí lo encuentra
    assert any(h["recurso_id"] == rid for h in form.get(f"{API}/buscar", params={"q": "zafiro turquesa"}).json()["resultados"])
    # 1) búsqueda: ni el resultado ni el total
    r = ajeno.get(f"{API}/buscar", params={"q": "zafiro turquesa"}).json()
    assert r["total"] == 0 and "zafiro" not in json.dumps(r)
    assert ajeno.get(f"{API}/recursos/{rid}").status_code == 404
    # 2) IA: evidencia insuficiente, sin datos
    r = ajeno.post(f"{API}/consultar", json={"pregunta": "¿Qué lleva la mezcla zafiro?"}).json()
    assert r["insuficiente"] and "37" not in r["texto"] and not r["citas"]
    # 3) descargas: ni por el módulo ni por la ruta general de archivos (aunque sea admin)
    assert ajeno.get(f"{API}/recursos/{pdf_formula.json()['id']}/archivos/{archivo}").status_code == 404
    assert form.get(f"/api/archivos/{archivo}").status_code == 404
    r = form.get(f"{API}/recursos/{pdf_formula.json()['id']}/archivos/{archivo}")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")  # descifrado y con marca de agua
    # el archivo en disco está cifrado
    from nucleo.archivos import _raiz
    from nucleo.modelos import Archivo
    with Session(motor_bd()) as bd:
        a = bd.get(Archivo, archivo)
        assert not (_raiz() / a.ruta_almacenamiento).read_bytes().startswith(b"%PDF")
    # 4) evaluación y PDF: la fórmula no va
    assert ajeno.get(f"{API}/expedientes/{folio}/formulas/1").status_code in (403, 404)
    r = ajeno.get(f"{API}/expedientes/{folio}/pdf")
    assert r.status_code == 200
    from pypdf import PdfReader
    texto = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "turquesa" not in texto.lower() and "Restringida" in texto
    r = form.get(f"{API}/expedientes/{folio}/pdf")
    texto = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "turquesa" in texto.lower()


# ---------------------------------------------------------------- caso 5 · consulta con citas, insuficiente y dictamen

def test_caso5_consulta_y_dictamen(equipo, fuente):
    inv, lider, lider2 = equipo["inv"].c, equipo["lider"].c, equipo["lider2"].c
    r = inv.post(f"{API}/consultar", json={"pregunta": "¿Qué forma de magnesio se absorbe mejor, bisglicinato u óxido?"}).json()
    # otras pruebas cargaron el mismo estudio [EJEMPLO]; cualquiera de ellos es una cita válida
    assert not r["insuficiente"] and r["citas"] and r["citas"][0]["titulo"].startswith("EJEMPLO Absorción de magnesio")
    assert "[9]" not in r["texto"]  # la cita inventada se quita
    r = inv.post(f"{API}/consultar", json={"pregunta": "¿El magnesio cura el insomnio crónico?"}).json()
    assert r["insuficiente"] and not r["citas"]
    # una fuente pendiente de revisión no se usa y se menciona
    # (26 nov 2026: con una marca propia de esta corrida; las anteriores dejan el mismo estudio ya revisado en la base)
    marca = uuid.uuid4().hex[:6]
    _cargar(inv, {"titulo": f"EJEMPLO Glicinato y sueño profundo {marca}", "tipo": "articulo",
                  "texto": f"# Sueño\nEl glicinato de magnesio y el sueño profundo en adultos mayores {marca}."})
    r = inv.post(f"{API}/consultar", json={"pregunta": f"glicinato sueño profundo adultos mayores {marca}"}).json()
    assert any(marca in x["titulo"] for x in r["no_usadas"]) and not any(marca in c["titulo"] for c in r["citas"])
    # dictamen con respaldo obligatorio
    folio = _expediente(inv, "[EJEMPLO] Dictamen")
    _regla(inv, lider, "R-EVI-903", None, modo="manual", rol_revisor="innovacion_lider", severidad="mayor",
           fuente_version_id=fuente.version_id)
    _ficha(inv, folio, [{"nombre": "Magnesio", "tipo": "mineral", "cantidad_activa": 280, "unidad_activa": "mg"}])
    d = inv.get(f"{API}/expedientes/{folio}").json()
    res = next(x for x in d["evaluacion"]["resultados"] if x["regla"] == "R-EVI-903")
    assert res["resultado"] == "pendiente" and res["revision"]["estado"] == "asignada"
    rev = res["revision"]["id"]
    sug = lider2.post(f"{API}/revisiones/{rev}/sugerencia").json()
    assert sug["sugerencia"] == "cumple"  # sugerencia de la IA, marcada; no cambia nada
    r = lider2.post(f"{API}/revisiones/{rev}/dictamen", json={"dictamen": "cumple", "motivo": "El estudio aplica a la forma", "respaldo": []})
    assert r.status_code == 422
    sec = inv.get(f"{API}/buscar", params={"q": "bisglicinato absorción"}).json()["resultados"][0]
    ev = inv.post(f"{API}/expedientes/{folio}/evidencia", json={"version_id": sec["version_id"], "fragmento_id": sec["fragmento_id"],
                                                              "respalda": "Absorción"}).json()
    assert inv.post(f"{API}/revisiones/{rev}/dictamen", json={"dictamen": "cumple", "motivo": "No me toca dictaminar",
                                                            "respaldo": [ev["id"]]}).status_code == 403
    r = lider2.post(f"{API}/revisiones/{rev}/dictamen", json={"dictamen": "cumple", "motivo": "El estudio aplica a la forma propuesta",
                                                              "respaldo": [ev["id"]]})
    assert r.status_code == 200, r.text
    d = inv.get(f"{API}/expedientes/{folio}").json()
    assert next(x for x in d["evaluacion"]["resultados"] if x["regla"] == "R-EVI-903")["resultado"] == "cumple"
    v = lider2.get(f"{API}/revisiones/{rev}").json()
    assert v["dictaminada_por"] and v["dictaminada_en"] and v["respaldo"] == [ev["id"]] and v["ficha"]["numero"] == 1


# ---------------------------------------------------------------- caso 6 · sin integraciones

def test_caso6_expediente_sin_radar(equipo, sin_ia):
    inv = equipo["inv"].c
    folio = _expediente(inv, "[EJEMPLO] Sin integraciones")
    assert inv.post(f"{API}/expedientes/{folio}/comparables", json={"producto": "Magnesio X 60 cápsulas"}).status_code == 422
    assert inv.post(f"{API}/expedientes/{folio}/comparables", json={"producto": "Magnesio X 60 cápsulas", "precio": 289,
                                                                  "fuente": "Visita a tienda [EJEMPLO]"}).status_code == 201
    s = inv.post(f"{API}/expedientes/{folio}/escenarios", json={"nombre": "Base", "costo_unitario": 95, "precio": 289}).json()
    assert s["margen_pct"] == 67.1
    assert inv.post(f"{API}/expedientes/{folio}/pendientes", json={"descripcion": "Cotizar materia prima",
                                                                 "determinante": True}).status_code == 201
    d = inv.get(f"{API}/expedientes/{folio}").json()
    assert d["comparables"][0]["origen"] == "manual" and d["pendientes"][0]["determinante"]
    # sin Ollama la búsqueda por palabras sigue y una fuente se carga
    r = _cargar(inv, {"titulo": "EJEMPLO Nota sin IA", "tipo": "nota", "texto": "# Nota\nMagnesio y estrés laboral."})
    assert r.status_code == 201
    assert inv.get(f"{API}/buscar", params={"q": "estrés laboral"}).json()["total"] >= 1


# ---------------------------------------------------------------- T10 choques · T11 UI · T12 separación de funciones

def test_t10_choque_t12_separacion(equipo, fuente):
    inv, lider, lider2 = equipo["inv"].c, equipo["lider"].c, equipo["lider2"].c
    cond = lambda mn, mx: {"para_cada": {"lista": "ingredientes", "donde": {"igual": ["tipo", "mineral"]}},  # noqa: E731
                           "rango": {"campo": "cantidad_activa", **({"min": mn} if mn else {}), **({"max": mx} if mx else {}), "unidad": "mg"}}
    _regla(inv, lider, "R-COMP-904", cond(None, 350), fuente_version_id=fuente.version_id)
    otra = _regla(inv, lider, "R-COMP-905", cond(400, None), fuente_version_id=fuente.version_id, publicar=False)
    r = lider.post(f"{API}/reglas/{otra['id']}/versiones/1/publicar")
    assert r.status_code == 409 and "R-COMP-904" in json.dumps(r.json())
    # el autor no publica su propia regla
    propia = _regla(lider, lider, "R-DOC-906", {"existe": "presentacion"}, fuente_version_id=fuente.version_id, publicar=False)
    assert lider.post(f"{API}/reglas/{propia['id']}/versiones/1/publicar").status_code == 403
    assert lider2.post(f"{API}/reglas/{propia['id']}/versiones/1/publicar").status_code == 200
    # sin fuente revisada no se publica
    p = inv.post(f"{API}/reglas", json={"area": "DOC", "nombre": "[EJEMPLO] sin fuente", "proposito": "Prueba sin fuente",
                                        "condicion": {"existe": "porcion"}, "vigente_desde": date.today().isoformat()}).json()
    inv.post(f"{API}/reglas/{p['id']}/versiones/1/enviar")
    assert lider.post(f"{API}/reglas/{p['id']}/versiones/1/publicar").status_code == 422
    # excepción: solo si la regla la admite, y quien la pide no la aprueba
    _regla(inv, lider, "R-REG-907", {"texto_no_contiene": ["declaraciones", ["cura", "trata"]]}, fuente_version_id=fuente.version_id,
           admite_excepcion=True, alcance={"etapa_destino": "filtro"})
    folio = _expediente(inv, "[EJEMPLO] Excepción")
    _ficha(inv, folio, [], declaraciones=["Trata el insomnio"])
    d = inv.get(f"{API}/expedientes/{folio}").json()
    res = next(x for x in d["evaluacion"]["resultados"] if x["regla"] == "R-REG-907")
    assert res["resultado"] == "incumple" and "trata" in res["motivo"]
    x = inv.post(f"{API}/resultados/{res['id']}/excepcion", json={"justificacion": "Texto en revisión con Regulatorio [EJEMPLO]",
                                                                "vence_en": (date.today() + timedelta(days=30)).isoformat()}).json()
    assert inv.post(f"{API}/excepciones/{x['id']}/resolver", json={"aprobar": True}).status_code == 403
    assert lider.post(f"{API}/excepciones/{x['id']}/resolver", json={"aprobar": True}).status_code == 200
    c = inv.get(f"{API}/expedientes/{folio}/compuerta", params={"etapa": "filtro"}).json()
    assert "R-REG-907" not in json.dumps(c["bloqueantes_abiertos"]) and c["excepciones_vigentes"]
    no_admite = next(x for x in d["evaluacion"]["resultados"] if x["regla"] == "R-COMP-904")
    assert inv.post(f"{API}/resultados/{no_admite['id']}/excepcion", json={"justificacion": "No debería pasar nunca",
                                                                          "vence_en": "2030-01-01"}).status_code == 409


def test_t11_ui_sin_factor_nunca_cumple():
    cond = {"para_cada": {"lista": "ingredientes", "donde": {"igual": ["tipo", "vitamina"]}},
            "rango": {"campo": "cantidad_activa", "max": 100, "unidad": "µg"}}
    datos = {"ingredientes": [{"nombre": "Vitamina D3", "tipo": "vitamina", "cantidad_activa": 1000, "unidad_activa": "UI"}]}
    r = motor.evaluar(cond, datos)
    assert r.valor == "pendiente" and "factor UI" in r.motivo()
    datos["ingredientes"][0]["factor_ui_ug"] = "0.025"
    assert motor.evaluar(cond, datos).valor == "cumple"
    datos["ingredientes"][0]["cantidad_activa"] = 5000
    assert motor.evaluar(cond, datos).valor == "incumple"
    # lógica de tres valores
    p, c, i = {"existe": "x"}, {"igual": ["y", 1]}, {"igual": ["y", 2]}
    assert motor.evaluar({"todas": [p, c]}, {"y": 1}).valor == "pendiente"
    assert motor.evaluar({"todas": [p, i]}, {"y": 1}).valor == "incumple"
    assert motor.evaluar({"alguna": [p, c]}, {"y": 1}).valor == "cumple"
    assert motor.evaluar({"alguna": [p, i]}, {"y": 1}).valor == "pendiente"
    assert motor.evaluar({"no": p}, {}).valor == "pendiente"
    with pytest.raises(motor.CondicionInvalida):
        motor.validar({"magia": 1})


# ---------------------------------------------------------------- T13 reintentos · T14 candado · T15 investigador · T16 OCR

def test_t13_reintentos_sin_ollama(equipo, sin_ia, monkeypatch):
    inv = equipo["inv"].c
    rid = _cargar(inv, {"titulo": "EJEMPLO Reintentos", "tipo": "nota", "texto": "# Uno\nTexto de prueba para reintentos."}).json()["id"]
    with Session(motor_bd()) as bd:
        for _ in range(3):  # tres reintentos (1, 5 y 30 min) y luego «error»
            bd.execute(Trabajo.__table__.update().where(Trabajo.tipo == "huellas", Trabajo.estado == "pendiente")
                       .values(siguiente_en=trabajos.ahora() - timedelta(minutes=1)))
            bd.commit()
            trabajos.procesar(bd)
    ts = inv.get(f"{API}/recursos/{rid}/trabajos").json()
    h = next(t for t in ts if t["tipo"] == "huellas")
    assert h["estado"] == "error" and h["intentos"] == 4 and "IA local" in h["error"]
    assert next(t for t in ts if t["tipo"] == "leer")["estado"] == "listo"  # leer no depende de la IA
    monkeypatch.setattr(puerta, "vectores", _huella)
    assert inv.post(f"{API}/trabajos/{h['id']}/reintentar").status_code == 200
    assert next(t for t in inv.get(f"{API}/recursos/{rid}/trabajos").json() if t["tipo"] == "huellas")["estado"] == "listo"
    # leer otra vez no duplica secciones
    with Session(motor_bd()) as bd:
        from modulos.innovacion.modelos import RecursoVersion
        v = bd.scalar(select(RecursoVersion).where(RecursoVersion.recurso_id == rid))
        antes = len(list(bd.scalars(select(Seccion).where(Seccion.version_id == v.version_id))))
        trabajos.correr(bd, trabajos.encolar(bd, "leer", v.version_id))
        assert len(list(bd.scalars(select(Seccion).where(Seccion.version_id == v.version_id)))) == antes


def test_t14_candado_solo_ia_local(base_de_pruebas):
    from nucleo.modelos import IaLlamada, IaTarea
    with Session(motor_bd()) as bd:
        t = bd.scalar(select(IaTarea).where(IaTarea.codigo == "innovacion.responder"))
        t.proveedor_ia = "api"
        bd.commit()
        try:
            with pytest.raises(puerta.ErrorIA, match="solo puede correr con la IA local"):
                puerta.ejecutar(bd, "innovacion.responder", usuario_id=None, instrucciones="x", mensaje="fórmula secreta")
            with pytest.raises(puerta.ErrorIA):
                puerta.ejecutar(bd, "innovacion.responder", usuario_id=None, instrucciones="x", mensaje="y", proveedor="api")
            assert bd.scalar(select(IaLlamada).where(IaLlamada.tarea_id == t.tarea_id).order_by(IaLlamada.llamada_id.desc())).resultado == "error"
        finally:
            t.proveedor_ia = "ollama"
            bd.commit()


def test_t15_investigador_con_fuentes_simuladas(equipo, ia, monkeypatch):
    inv = equipo["inv"].c
    enviados = []

    def pubmed(termino, maximo=8):
        enviados.append(termino)
        return fx.Resultado([fx.Registro("pubmed", "Magnesium bisglycinate absorption: randomized controlled trial", "https://pubmed.ncbi.nlm.nih.gov/1/",
                                         doi="10.1/ej", pmid="1", pmcid="PMC1", anio=2022, resumen="magnesium bisglycinate showed higher absorption in adults",
                                         tipo_estudio="ensayo", acceso_abierto=True)])

    def europepmc(termino, maximo=8):
        enviados.append(termino)
        return fx.Resultado([fx.Registro("europepmc", "Same trial (duplicate by DOI)", doi="10.1/EJ"),
                             fx.Registro("europepmc", "Magnesium oxide in rats", doi="10.1/rata", anio=2001, tipo_estudio="preclinico")])

    monkeypatch.setitem(fx.CLIENTES, "pubmed", pubmed)
    monkeypatch.setitem(fx.CLIENTES, "europepmc", europepmc)
    monkeypatch.setattr(fx, "texto_completo_europepmc", lambda pmcid: "## Results\nmagnesium bisglycinate showed higher absorption than oxide.")
    folio = _expediente(inv, "[EJEMPLO] Investigar")
    _ficha(inv, folio, [{"nombre": "Magnesio", "tipo": "mineral", "forma": "bisglicinato", "cantidad_activa": 280, "unidad_activa": "mg"}])
    p = inv.post(f"{API}/investigaciones", json={"tema": "relajación", "folio": folio}).json()
    assert p["estado"] == "propuesta" and p["preguntas"] and p["terminos"]
    r = inv.patch(f"{API}/investigaciones/{p['id']}", json={"fuentes": ["pubmed", "europepmc"],
                                                            "terminos": p["terminos"][:2] + [f"magnesio 280 mg {folio}"]}).json()
    assert all("280" not in t and folio not in t for t in r["terminos"])  # nunca salen cantidades ni el folio
    r = inv.post(f"{API}/investigaciones/{p['id']}/correr").json()
    d = inv.get(f"{API}/investigaciones/{p['id']}").json()
    assert d["estado"] == "lista", d
    assert all("280" not in t and folio not in t for t in enviados)
    assert len(d["hallazgos"]) == 2  # el repetido por DOI no entra
    mejor = d["hallazgos"][0]
    assert mejor["tipo_estudio"] == "ensayo" and mejor["extraccion"]["cita"] and mejor["texto_abierto"]
    inf = d["informe"][0]
    assert not inf["insuficiente"] and inf["citas"][0]["hallazgo_id"] == mejor["id"]
    assert [x["paso"] for x in d["pasos"]] == ["preguntas", "busqueda", "seleccion", "lectura", "informe"]
    r = inv.post(f"{API}/investigaciones/{p['id']}/hallazgos/{mejor['id']}/agregar")
    assert r.status_code == 201
    nuevo = inv.get(f"{API}/recursos/{r.json()['id']}").json()
    assert nuevo["versiones"][0]["estado"] == "pendiente" and nuevo["versiones"][0]["doi"] == "10.1/ej"
    assert investigador.limpiar_termino("VID-2026-0003 magnesio 1986 mg 300mg") == "magnesio"


@pytest.mark.skipif(not shutil.which("tesseract") or not shutil.which("pdftoppm"), reason="sin OCR instalado")
def test_t16_pdf_escaneado_queda_citable(equipo, sin_ia):
    from PIL import Image, ImageDraw, ImageFont
    inv = equipo["inv"].c
    img = Image.new("RGB", (1700, 2200), "white")
    letra = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 56)
    ImageDraw.Draw(img).text((120, 200), "Guia de suplementos\nEl zinc quelado se absorbe bien", fill="black", font=letra)
    b = io.BytesIO()
    img.save(b, "PDF", resolution=200)
    r = _cargar(inv, {"titulo": "EJEMPLO Guía escaneada", "tipo": "guia_regulatoria"}, [("escaneo.pdf", b.getvalue())])
    assert r.status_code == 201
    d = inv.get(f"{API}/recursos/{r.json()['id']}").json()
    assert d["versiones"][0]["datos"]["lectura"]["ocr_paginas"] == 1
    hit = inv.get(f"{API}/buscar", params={"q": "zinc quelado"}).json()["resultados"]
    assert hit and hit[0]["pagina"] == 1


def test_t17_permisos_del_modulo(admin, equipo):
    _, sin_rol, _ = alta_usuario(admin, rol="metodos_consulta")
    assert sin_rol.get(f"{API}/resumen").status_code == 403
    assert sin_rol.get(f"{API}/buscar", params={"q": "magnesio"}).status_code == 403
    r = equipo["dir"].c.get(f"{API}/resumen")
    assert r.status_code == 200 and "por_decidir" in r.json()
    assert equipo["dir"].c.post(f"{API}/expedientes", json={"nombre": "No debería"}).status_code == 403
    m = admin.get("/api/nucleo/modulos").json() if admin.get("/api/nucleo/modulos").status_code == 200 else []
    assert not m or any(x.get("codigo") == "innovacion" for x in m)
