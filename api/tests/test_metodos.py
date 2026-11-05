"""Métodos y procedimientos: carga, búsqueda con cita, «no está», permisos por rol, borradores de la IA con cambios
marcados y aprobación del área, prueba de preguntas, reporte y documentos de otras bases.

Todos los manuales de aquí son ficticios (EJEMPLO); no describen procesos reales de SMN."""
import hashlib
import io
import json
import zipfile

import pytest

from tests.conftest import alta_usuario
from ia import puerta
from modulos.metodos import indice, redaccion, revision
from nucleo.lectura import bloques_de_texto, extraer_bloques

RECEPCION = """# EJEMPLO Recepción de mercancía en tienda
## 1. Objetivo
Recibir la mercancía del proveedor en tienda revisando cantidades y caducidades antes de firmar la remisión.
## 2. Responsables
El encargado de tienda recibe y firma. El auxiliar de almacén cuenta las piezas.
## 3. Procedimiento
1. El auxiliar de almacén cuenta las piezas contra la remisión del proveedor.
2. El encargado revisa que la caducidad sea mayor a 6 meses.
3. Si falta mercancía, el encargado anota el faltante en la remisión antes de firmar.
4. El encargado captura la entrada en Intelisis el mismo día.
## 4. Contacto
Dudas con soporte al correo soporte.ficticio@ejemplo.mx o al 55 1234 5678.
"""

ALTA = """# EJEMPLO Alta de proveedor
## 1. Objetivo
Registrar a un proveedor nuevo con sus documentos completos.
## 2. Procedimiento
1. El comprador pide al proveedor su constancia de situación fiscal y su estado de cuenta bancario.
2. El comprador captura el alta en Intelisis.
3. El jefe de Compras autoriza el alta.
"""

DEVOLUCIONES = """# EJEMPLO Devoluciones de clientes
## Procedimiento
1. El cajero pide el ticket de compra.
2. Solo se aceptan devoluciones dentro de los 30 días posteriores a la compra.
"""


def _subir(c, nombre: str, texto: str):
    contenido = redaccion.word(nombre, texto, "Documento ficticio para pruebas")
    r = c.post("/api/archivos", files={"archivo": (f"{nombre}.docx", contenido)}, data={"modulo": "metodos"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _cargar(c, titulo, texto, area="Operaciones", version="1.0", **extra):
    archivo_id = _subir(c, titulo, texto)
    r = c.post("/api/metodos/documentos", json={"archivo_id": archivo_id, "titulo": titulo, "area": area,
                                                 "version": version, **extra})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def sin_ollama(monkeypatch):
    def apagado(*a, **k):
        raise puerta.ErrorIA("No hay conexión con Ollama.")
    monkeypatch.setattr(puerta, "vectores", apagado)
    monkeypatch.setattr(puerta, "ejecutar", apagado)
    monkeypatch.setattr(puerta, "estado_ollama", lambda: {"disponible": False, "modelos": []})


def _huella_ficticia(bd, tarea, textos, usuario_id=None):
    """Huella de prueba: cuenta palabras parecidas en 64 cajones; «registrar» y «alta» caen juntas a propósito."""
    sinonimos = {"registr": "alta", "registro": "alta", "nuevo": "alta"}
    salida = []
    for t in textos:
        v = [0.0] * 64
        for p in indice.palabras(t):
            p = next((s for k, s in sinonimos.items() if p.startswith(k)), p)
            v[int(hashlib.md5(p.encode()).hexdigest(), 16) % 64] += 1
        salida.append(v)
    return "ficticio", salida


def test_lectura_y_fragmentos_por_seccion():
    bloques = bloques_de_texto(RECEPCION)
    piezas = indice.partir(bloques)
    assert [p.seccion for p in piezas] == [
        "EJEMPLO Recepción de mercancía en tienda > 1. Objetivo", "EJEMPLO Recepción de mercancía en tienda > 2. Responsables",
        "EJEMPLO Recepción de mercancía en tienda > 3. Procedimiento", "EJEMPLO Recepción de mercancía en tienda > 4. Contacto"]
    texto, cuenta = indice.ocultar_personales("Escribe a ana@ejemplo.mx, tel. 55 1234 5678, RFC XAXX010101000. "
                                              "El tope es de $1,500.00 y la clave 2026-10.")
    assert "@" not in texto and "1234" not in texto and "XAXX" not in texto
    assert "$1,500.00" in texto and "2026-10" in texto
    assert cuenta == {"correo": 1, "telefono": 1, "rfc": 1}
    # el Word que hace la plataforma se vuelve a leer con sus títulos
    contenido = redaccion.word("x", RECEPCION, "pie")
    assert zipfile.ZipFile(io.BytesIO(contenido)).testzip() is None


def test_word_se_lee_con_titulos(tmp_path):
    ruta = tmp_path / "m.docx"
    ruta.write_bytes(redaccion.word("x", ALTA, "pie"))
    bloques = extraer_bloques(ruta, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert [b.texto for b in bloques if b.nivel] == ["EJEMPLO Alta de proveedor", "1. Objetivo", "2. Procedimiento"]


def test_cargar_y_preguntar_sin_ollama(admin, sin_ollama):
    r = _cargar(admin, "EJEMPLO Recepción de mercancía", RECEPCION, clave="EJ-OPE-001")
    assert r["fragmentos"] == 4 and r["con_huella"] == 0
    assert r["datos_personales"] == {"correo": 1, "telefono": 1}
    assert "datos de personas" in r["documento"]["avisos"][0]
    doc_id = r["documento"]["id"]
    detalle = admin.get(f"/api/metodos/documentos/{doc_id}").json()
    assert "soporte.ficticio" not in json.dumps(detalle["secciones"])

    # el mismo archivo otra vez no se carga dos veces
    archivo = _subir(admin, "EJEMPLO Recepción de mercancía", RECEPCION)
    assert admin.post("/api/metodos/documentos", json={"archivo_id": archivo, "titulo": "Otra vez", "area": "Operaciones",
                                                       "version": "1"}).status_code == 409

    r = admin.post("/api/metodos/preguntar", json={"pregunta": "¿Qué caducidad debe tener la mercancía al recibirla?"}).json()
    assert r["encontrada"] and r["modo"] == "palabras"
    assert {c["documento_id"] for c in r["citas"]} == {doc_id}
    assert any(c["seccion"].endswith("3. Procedimiento") for c in r["citas"])
    assert r["citas"][0]["version"] == "1.0" and r["citas"][0]["clave"] == "EJ-OPE-001"

    r = admin.post("/api/metodos/preguntar", json={"pregunta": "¿Cuántos días de vacaciones me tocan?"}).json()
    assert not r["encontrada"] and r["citas"] == [] and "No está en los manuales" in r["texto"]

    # calificar solo la pregunta propia
    assert admin.patch(f"/api/metodos/preguntas/{r['pregunta_id']}", json={"util": False, "comentario": "falta"}).status_code == 204
    _, otro, _ = alta_usuario(admin, rol="metodos_consulta")
    assert otro.patch(f"/api/metodos/preguntas/{r['pregunta_id']}", json={"util": True}).status_code == 404


def test_respuesta_de_la_ia_con_cita_y_sin_inventar(admin, monkeypatch):
    monkeypatch.setattr(puerta, "vectores", _huella_ficticia)
    _cargar(admin, "EJEMPLO Alta de proveedor", ALTA, area="Compras")
    respuestas = []

    def ia(bd, tarea, **k):
        assert tarea == "metodos.responder" and "Fragmentos:" in k["mensaje"]
        return puerta.Respuesta(respuestas.pop(0), "ollama", "m", 1, 1, 0, 5, True, 1)
    monkeypatch.setattr(puerta, "ejecutar", ia)
    monkeypatch.setattr(puerta, "estado_ollama", lambda: {"disponible": True, "modelos": []})

    respuestas.append("1. Pide la constancia de situación fiscal y el estado de cuenta [1]. Lo autoriza el jefe [1] [7].")
    r = admin.post("/api/metodos/preguntar", json={"pregunta": "¿Cómo registro un proveedor nuevo?"}).json()
    assert r["encontrada"] and r["modo"] == "ia"
    assert "[7]" not in r["texto"]  # una cita a un fragmento que no existe se quita
    assert [c["titulo"] for c in r["citas"]] == ["EJEMPLO Alta de proveedor"]

    respuestas.append("NO_ESTA")
    r = admin.post("/api/metodos/preguntar", json={"pregunta": "¿Qué documentos pide el alta de proveedor extranjero?"}).json()
    assert not r["encontrada"] and r["preguntar_a"] == "Compras"

    respuestas.append("El alta la autoriza el director general.")  # sin cita: no tiene respaldo
    r = admin.post("/api/metodos/preguntar", json={"pregunta": "¿Quién autoriza el alta de proveedor?"}).json()
    assert not r["encontrada"]


def test_roles_que_ven_cada_documento(admin, sin_ollama):
    d = _cargar(admin, "EJEMPLO Devoluciones restringido", DEVOLUCIONES, area="Tiendas", roles=["contraloria_fiscal"])
    _, compras, _ = alta_usuario(admin, rol="metodos_consulta")
    _, fiscal, _ = alta_usuario(admin, rol="contraloria_fiscal")
    pregunta = {"pregunta": "¿Cuántos días hay para devoluciones de clientes con ticket?"}
    assert not compras.post("/api/metodos/preguntar", json=pregunta).json()["encontrada"]
    assert compras.get(f"/api/metodos/documentos/{d['documento']['id']}").status_code == 404
    assert d["documento"]["id"] not in [x["id"] for x in compras.get("/api/metodos/documentos").json()]
    r = fiscal.post("/api/metodos/preguntar", json=pregunta).json()
    assert r["encontrada"] and r["citas"][0]["documento_id"] == d["documento"]["id"]
    # consulta no carga ni aprueba
    assert compras.post("/api/metodos/borradores", json={"tipo": "nuevo"}).status_code == 403
    _, sin, _ = alta_usuario(admin, rol="kiosco_tienda")
    assert sin.post("/api/metodos/preguntar", json=pregunta).status_code == 403


def _en_linea(monkeypatch):
    from core.bd import _fabrica
    from modulos.metodos.modelos import Borrador

    def inline(borrador_id):
        with _fabrica()() as bd:
            redaccion.redactar(bd, bd.get(Borrador, borrador_id))
    monkeypatch.setattr(redaccion, "redactar_aparte", inline)
    monkeypatch.setattr(puerta, "estado_ollama", lambda: {"disponible": True, "modelos": []})


def test_borrador_de_actualizacion_con_cambios_y_aprobacion(admin, monkeypatch):
    monkeypatch.setattr(puerta, "vectores", lambda *a, **k: (_ for _ in ()).throw(puerta.ErrorIA("apagado")))
    _en_linea(monkeypatch)
    base = _cargar(admin, "EJEMPLO Alta de proveedor v1", ALTA, area="Compras", clave="EJ-COM-002")["documento"]
    nuevo = ALTA.replace("su estado de cuenta bancario.", "su estado de cuenta bancario y su opinión de cumplimiento.") \
        .replace("3. El jefe de Compras autoriza el alta.", "3. El jefe de Compras autoriza el alta en 2 días.")
    monkeypatch.setattr(puerta, "ejecutar", lambda bd, tarea, **k: puerta.Respuesta(
        "```markdown\n" + nuevo + "\n```", "ollama", "m", 1, 1, 0, 5, True, 1))
    r = admin.post("/api/metodos/borradores", json={"tipo": "actualizacion", "documento_id": base["id"],
                                                     "instrucciones": "Ahora se pide la opinión de cumplimiento."})
    assert r.status_code == 201, r.text
    b = admin.get(f"/api/metodos/borradores/{r.json()['id']}").json()
    assert b["estado"] == "listo" and b["version_sugerida"] == "2.0"
    assert [c["tipo"] for c in b["cambios"]] == ["cambia", "cambia"]
    assert b["cambios"][0]["seccion"] == "2. Procedimiento"

    # su perfil dice otra área: no aprueba
    _, otro, otro_id = alta_usuario(admin, rol="metodos_responsable")
    from core.bd import _fabrica
    from nucleo.modelos import Usuario
    with _fabrica()() as bd:
        bd.get(Usuario, otro_id).area = "Tiendas"
        bd.commit()
    assert otro.post(f"/api/metodos/borradores/{b['id']}/aprobar", json={"version": "2.0"}).status_code == 403

    # acepta el primer cambio y rechaza el segundo
    r = admin.post(f"/api/metodos/borradores/{b['id']}/aprobar", json={"version": "2.0", "rechazados": [1]})
    assert r.status_code == 200, r.text
    publicado = admin.get(f"/api/metodos/documentos/{r.json()['publicado_id']}").json()
    assert publicado["estado"] == "vigente" and publicado["origen"] == "ia" and publicado["version"] == "2.0"
    assert publicado["clave"] == "EJ-COM-002" and publicado["reemplaza_a"] == base["id"]
    texto = " ".join(s["texto"] for s in publicado["secciones"])
    assert "opinión de cumplimiento" in texto and "en 2 días" not in texto
    assert [v["version"] for v in publicado["versiones"]] == ["1.0"]
    assert admin.get(f"/api/metodos/documentos/{base['id']}").json()["estado"] == "reemplazado"
    word = admin.get(f"/api/metodos/documentos/{publicado['id']}/archivo")
    assert word.status_code == 200 and zipfile.ZipFile(io.BytesIO(word.content)).testzip() is None


def test_borrador_nuevo_con_preguntas_abiertas(admin, monkeypatch, sin_ollama):
    _en_linea(monkeypatch)
    texto = ("# EJEMPLO Inventario cíclico\n## 1. Objetivo\nContar una parte del inventario cada semana.\n"
             "## 6. Procedimiento\n1. El auxiliar cuenta los pasillos que toquen [PREGUNTA: ¿cuántos pasillos por semana?]\n")
    monkeypatch.setattr(puerta, "ejecutar", lambda bd, tarea, **k: puerta.Respuesta(texto, "ollama", "m", 1, 1, 0, 5, True, 1))
    assert admin.post("/api/metodos/borradores", json={"tipo": "nuevo", "titulo": "EJEMPLO Inventario cíclico",
                                                        "area": "Operaciones"}).status_code == 422
    r = admin.post("/api/metodos/borradores", json={"tipo": "nuevo", "titulo": "EJEMPLO Inventario cíclico",
                                                     "area": "Operaciones", "instrucciones": "Contamos cada lunes."})
    b = admin.get(f"/api/metodos/borradores/{r.json()['id']}").json()
    assert b["preguntas_abiertas"] == ["¿cuántos pasillos por semana?"] and b["cambios"] == []
    r = admin.post(f"/api/metodos/borradores/{b['id']}/aprobar", json={"version": "1.0"})
    assert r.status_code == 422 and "PREGUNTA" in r.text
    corregido = texto.replace(" [PREGUNTA: ¿cuántos pasillos por semana?]", ", tres pasillos por semana.")
    r = admin.post(f"/api/metodos/borradores/{b['id']}/aprobar", json={"version": "1.0", "texto": corregido})
    assert r.status_code == 200, r.text
    assert admin.get(f"/api/metodos/borradores/{b['id']}/word").status_code == 200


def test_prueba_de_preguntas_y_metas(admin, monkeypatch, sin_ollama):
    from core.bd import _fabrica
    from core.seguridad import Contexto, permisos_de
    from modulos.metodos.modelos import PruebaCorrida
    from nucleo.modelos import Usuario

    def inline(corrida_id, usuario_id):
        with _fabrica()() as bd:
            u = bd.get(Usuario, usuario_id)
            revision.correr_prueba(bd, bd.get(PruebaCorrida, corrida_id), Contexto(u, permisos_de(bd, usuario_id)))
    monkeypatch.setattr(revision, "correr_prueba_aparte", inline)
    d = _cargar(admin, "EJEMPLO Devoluciones", DEVOLUCIONES, area="Tiendas")["documento"]
    assert admin.post("/api/metodos/prueba/preguntas", json={"pregunta": "¿Hasta cuántos días acepto devoluciones?",
                                                              "documento_id": d["id"]}).status_code == 201
    assert admin.post("/api/metodos/prueba/preguntas", json={"pregunta": "¿Cuál es el sueldo del gerente?",
                                                              "debe_contestar": False}).status_code == 201
    assert admin.post("/api/metodos/prueba/preguntas", json={"pregunta": "x x x", "debe_contestar": False,
                                                              "documento_id": d["id"]}).status_code == 422
    r = admin.post("/api/metodos/prueba/correr")
    assert r.status_code == 202, r.text
    c = admin.get(f"/api/metodos/prueba/corridas/{r.json()['id']}").json()
    assert c["estado"] == "terminada" and c["hechas"] == c["total"]
    assert c["inventadas"] == 0 and c["no_esta_bien"] == c["no_esta_total"]
    assert {x["calificacion"] for x in c["detalle"] if x["pregunta"].startswith("¿Hasta")} == {"correcta"}
    assert c["metas"]["con_ia"] is False and c["metas"]["pasa"] is False  # sin IA no se abre a todos
    # las preguntas de prueba no cuentan en el reporte del mes
    mes = c["iniciada_en"][:7]
    reporte = admin.get(f"/api/metodos/reporte?mes={mes}").json()
    assert all("sueldo del gerente" not in json.dumps(g) for g in reporte["sin_respuesta"])


def test_reporte_sugerencias_y_avisos(admin, sin_ollama):
    d = _cargar(admin, "EJEMPLO Manual viejo", "# EJEMPLO Manual viejo\n## Cierre de caja\nSe cuenta el efectivo al cierre.\n",
                area="Tiendas", vigente_desde="2020-01-01")["documento"]
    assert d["viejo"] and "no tiene fecha de revisión" in d["viejo"]
    for _ in range(2):
        admin.post("/api/metodos/preguntar", json={"pregunta": "¿Cómo pido uniformes nuevos para la tienda?"})
    r = admin.post("/api/metodos/preguntar", json={"pregunta": "¿Cómo se hace el cierre de caja?"}).json()
    assert r["encontrada"]
    mes = __import__("datetime").date.today().strftime("%Y-%m")
    rep = admin.get(f"/api/metodos/reporte?mes={mes}").json()
    assert any(g["veces"] >= 2 and "uniformes" in g["preguntas"][0] for g in rep["sin_respuesta"])
    assert admin.get("/api/metodos/reporte?mes=2026-13").status_code == 422
    sug = admin.get("/api/metodos/sugerencias").json()
    assert any("uniformes" in t["preguntas"][0] for t in sug["temas"])
    assert d["id"] in [v["documento_id"] for v in sug["viejos"]]
    # retirar: ya no contesta
    assert admin.post(f"/api/metodos/documentos/{d['id']}/retirar", json={}).status_code == 200
    assert not admin.post("/api/metodos/preguntar", json={"pregunta": "¿Cómo se hace el cierre de caja?"}).json()["encontrada"]


def test_documentos_de_compras_y_fiscal(admin, sin_ollama):
    from core.bd import _fabrica
    from modulos.compras.modelos import RadarDocumento
    from modulos.contraloria.modelos_diot import FiscalDocumento
    from nucleo.modelos import Archivo

    with _fabrica()() as bd:
        a = bd.query(Archivo).first()
        rd = RadarDocumento(archivo_id=a.archivo_id, titulo="EJEMPLO Política de margen mínimo", subido_por=a.subido_por,
                            texto="El margen mínimo de la lista A es de 31 % sobre precio lista.", caracteres=60)
        fd = FiscalDocumento(titulo="EJEMPLO Reglas de redondeo", tipo="reglas", nombre_archivo="reglas.csv",
                             contenido="regla,detalle\nredondeo,El IVA se calcula sobre la base redondeada\n".encode())
        bd.add_all([rd, fd])
        bd.commit()
        rd_id = rd.documento_id
    r = admin.post("/api/metodos/sincronizar").json()
    assert r.get("nuevo", 0) >= 2
    assert admin.post("/api/metodos/sincronizar").json().get("nuevo", 0) == 0
    _, fiscal, _ = alta_usuario(admin, rol="contraloria_fiscal")
    _, compras, _ = alta_usuario(admin, rol="compras_responsable")
    p = {"pregunta": "¿Cuál es el margen mínimo de la lista A?"}
    assert compras.post("/api/metodos/preguntar", json=p).json()["encontrada"]
    assert not fiscal.post("/api/metodos/preguntar", json=p).json()["encontrada"]  # no ve el radar de Compras
    assert fiscal.post("/api/metodos/preguntar", json={"pregunta": "¿El IVA se calcula sobre la base redondeada?"}).json()["encontrada"]
    with _fabrica()() as bd:
        bd.get(RadarDocumento, rd_id).activo = False
        bd.commit()
    assert admin.post("/api/metodos/sincronizar").json().get("retirado") == 1
    assert not compras.post("/api/metodos/preguntar", json=p).json()["encontrada"]


def test_busqueda_por_significado(admin, monkeypatch):
    monkeypatch.setattr(puerta, "vectores", _huella_ficticia)
    monkeypatch.setattr(puerta, "ejecutar", lambda *a, **k: (_ for _ in ()).throw(puerta.ErrorIA("apagado")))
    r = _cargar(admin, "EJEMPLO Alta de proveedor significado", ALTA, area="Compras")
    assert r["con_huella"] == r["fragmentos"]
    from core.bd import _fabrica
    from core.seguridad import Contexto, permisos_de
    from nucleo.modelos import Usuario
    with _fabrica()() as bd:
        u = bd.query(Usuario).filter(Usuario.correo == "admin-pruebas@ejemplo.mx").one()
        hallazgos, usada = indice.buscar(bd, Contexto(u, permisos_de(bd, u.usuario_id)), "registrar proveedor")
    assert usada and any(h.coseno is not None for h in hallazgos)


def test_flujo_desde_los_pasos_y_validacion():
    from modulos.metodos import flujo
    from scripts.ejemplos_metodos import EJEMPLOS

    f = flujo.desde_texto(EJEMPLOS[0][2])
    assert f["carriles"] == ["Auxiliar de almacén", "Encargado de tienda"]
    assert [p["tipo"] for p in f["pasos"]] == ["inicio", "paso", "paso", "paso", "paso", "fin"]
    assert f["pasos"][1]["sig"] == [{"a": "p2", "etiqueta": None}]
    with pytest.raises(flujo.FlujoInvalido, match="dos salidas"):
        flujo.validar({"pasos": [{"id": "a", "tipo": "decision", "texto": "¿Llegó?", "sig": [{"a": "b"}]},
                                 {"id": "b", "texto": "Firma"}]})
    with pytest.raises(flujo.FlujoInvalido, match="no existe"):
        flujo.validar({"pasos": [{"id": "a", "texto": "Cuenta", "sig": [{"a": "zz"}]}]})
    with pytest.raises(flujo.FlujoInvalido, match="Procedimiento"):
        flujo.desde_texto("# Algo\n## Objetivo\nNada.")


FLUJO_IA = {"carriles": ["Comprador", "Jefe de Compras"], "pasos": [
    {"id": "i", "tipo": "inicio", "texto": "Inicio", "carril": "Comprador", "sig": [{"a": "p1"}]},
    {"id": "p1", "texto": "Pide constancia y estado de cuenta", "carril": "Comprador", "sig": [{"a": "d"}]},
    {"id": "d", "tipo": "decision", "texto": "¿Coinciden los datos?", "carril": "Comprador",
     "sig": [{"a": "p2", "etiqueta": "Sí"}, {"a": "p1", "etiqueta": "No"}]},
    {"id": "p2", "texto": "Autoriza el alta", "carril": "Jefe de Compras", "sig": [{"a": "f"}]},
    {"id": "f", "tipo": "fin", "texto": "Fin", "carril": "Jefe de Compras"}]}


def test_borrador_con_archivo_diagrama_pdf_y_word(admin, monkeypatch):
    monkeypatch.setattr(puerta, "vectores", lambda *a, **k: (_ for _ in ()).throw(puerta.ErrorIA("apagado")))
    _en_linea(monkeypatch)
    mensajes = []

    def ia(bd, tarea, **k):
        mensajes.append(k["mensaje"])
        texto = json.dumps(FLUJO_IA) if "diagramas de flujo" in k["instrucciones"] else (
            ALTA + "## 3. Responsables\n- Comprador: pide documentos.\n- Jefe de Compras: autoriza.\n")
        return puerta.Respuesta(texto, "ollama", "m", 1, 1, 0, 5, True, 1)
    monkeypatch.setattr(puerta, "ejecutar", ia)

    apoyo = _subir(admin, "Notas del alta", "## Notas\nEl comprador escribe a compras.ficticio@ejemplo.mx y revisa datos.")
    _, otro, _ = alta_usuario(admin, rol="metodos_responsable")
    ajeno = _subir(otro, "Ajeno", "Nada")
    pedir = {"tipo": "nuevo", "titulo": "EJEMPLO Alta con diagrama", "area": "Compras"}
    assert admin.post("/api/metodos/borradores", json={**pedir, "archivos": [ajeno]}).status_code == 404
    r = admin.post("/api/metodos/borradores", json={**pedir, "archivos": [apoyo]})
    assert r.status_code == 201, r.text
    assert "Archivo de apoyo «Notas del alta.docx»" in mensajes[0] and "ejemplo.mx" not in mensajes[0]

    b = admin.get(f"/api/metodos/borradores/{r.json()['id']}").json()
    assert b["archivos"] == [{"id": apoyo, "nombre": "Notas del alta.docx"}]
    assert b["flujo"]["origen"] == "ia" and b["diagrama_svg"].startswith("<svg") and "¿Coinciden" in b["diagrama_svg"]

    # la persona corrige: una decisión con una sola salida no pasa; con dos, sí
    malo = {**b["flujo"], "pasos": [dict(p, sig=p["sig"][:1]) if p["id"] == "d" else p for p in b["flujo"]["pasos"]]}
    r = admin.put(f"/api/metodos/borradores/{b['id']}/flujo", json={"flujo": malo})
    assert r.status_code == 422 and "dos salidas" in r.text
    assert admin.post("/api/metodos/diagrama", json={"flujo": malo}).status_code == 422
    bueno = {**b["flujo"], "pasos": [dict(p, texto="Autoriza el alta en Intelisis") if p["id"] == "p2" else p
                                     for p in b["flujo"]["pasos"]]}
    r = admin.put(f"/api/metodos/borradores/{b['id']}/flujo", json={"flujo": bueno})
    assert r.status_code == 200 and r.json()["flujo"]["origen"] == "persona" and "en Intelisis" in r.json()["svg"]
    sacado = admin.post(f"/api/metodos/borradores/{b['id']}/flujo/sacar", json={"usar_ia": False}).json()
    assert sacado["flujo"]["origen"] == "texto"

    borrador_pdf = admin.get(f"/api/metodos/borradores/{b['id']}/pdf")
    assert borrador_pdf.status_code == 200 and borrador_pdf.content.startswith(b"%PDF")
    word = zipfile.ZipFile(io.BytesIO(admin.get(f"/api/metodos/borradores/{b['id']}/word").content))
    assert "word/media/diagrama.png" in word.namelist()

    r = admin.post(f"/api/metodos/borradores/{b['id']}/aprobar", json={"version": "1.0"})
    assert r.status_code == 200, r.text
    doc = admin.get(f"/api/metodos/documentos/{r.json()['publicado_id']}").json()
    assert doc["pdf"] and "en Intelisis" in doc["diagrama_svg"]
    oficial = admin.get(f"/api/metodos/documentos/{doc['id']}/pdf")
    assert oficial.status_code == 200
    from pypdf import PdfReader
    texto = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(oficial.content)).pages)
    assert "EJEMPLO Alta con diagrama" in texto and "Diagrama de flujo" in texto and "Autoriza el alta en" in texto
    assert "BORRADOR" not in texto
