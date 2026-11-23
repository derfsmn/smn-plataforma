"""Carga datos FICTICIOS para probar Innovación Vidanat (TD005) antes de tener los reales.

- 12 fuentes «EJEMPLO …» (9 revisadas, 3 pendientes), 2 expedientes «[EJEMPLO] …» y 8 reglas «[EJEMPLO] …»
  (5 publicadas, 3 en borrador o revisión). Ninguna describe un estudio, una norma ni un producto real.
- Las cantidades son de ejemplo: NO son dosis recomendadas ni límites regulatorios.

Uso (en el equipo donde corre la plataforma):
    docker compose exec api python -m scripts.ejemplos_innovacion
    docker compose exec api python -m scripts.ejemplos_innovacion --quitar
Los ingredientes del catálogo (Magnesio, Vitamina D3, Ashwagandha, Melatonina) se quedan al quitar los ejemplos.
"""
import json
import sys
from datetime import date, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from core.bd import motor
from modulos.innovacion import acceso as A
from modulos.innovacion import evaluacion as evs
from modulos.innovacion import expedientes as ex
from modulos.innovacion import indice, trabajos
from modulos.innovacion import motor as motor_reglas
from modulos.innovacion.modelos import (Comparable, Consulta, Decision, Escenario, Evaluacion, EvaluacionResultado,
                                        Evidencia, Excepcion, Expediente, ExpedienteEquipo, FichaIngrediente,
                                        FichaVersion, FormulaVersion, Hallazgo, Ingrediente, Investigacion, Pendiente,
                                        Recurso, RecursoArchivo, RecursoVersion, Regla, ReglaVersion, Revision, Seccion,
                                        Trabajo, Vinculo)
from nucleo.modelos import Rol, UsuarioRol, ahora

AVISO = "Texto FICTICIO para probar la plataforma. No es un estudio, norma ni ficha real."
INGREDIENTES = [
    ("Magnesio", "mineral", "bisglicinato de magnesio", ["magnesium", "bisglicinato de magnesio", "glicinato de magnesio", "óxido de magnesio"]),
    ("Vitamina D3", "vitamina", "colecalciferol", ["colecalciferol", "cholecalciferol", "vitamina D"]),
    ("Ashwagandha", "botanico", "extracto de raíz", ["Withania somnifera", "withania"]),
    ("Melatonina", "otro", None, ["melatonin"]),
]
# (título, tipo, revisada, ingredientes, texto)
FUENTES = [
    ("EJEMPLO Absorción de dos formas de magnesio", "ensayo_clinico", True, ["Magnesio"],
     "# Resumen\nEn 40 adultos [EJEMPLO], el bisglicinato de magnesio se absorbió mejor que el óxido de magnesio.\n"
     "# Métodos\nEstudio cruzado de 8 semanas con 140 mg de magnesio elemental al día.\n"
     "# Limitaciones\nMuestra pequeña y de un solo centro."),
    ("EJEMPLO Revisión de magnesio y calidad de sueño", "revision", True, ["Magnesio"],
     "# Resumen\nRevisión [EJEMPLO] de 9 ensayos: el magnesio mostró una mejora pequeña en la calidad de sueño autorreportada.\n"
     "# Conclusión\nLa evidencia es de certeza baja; se necesitan ensayos más grandes."),
    ("EJEMPLO Guía de etiquetado de suplementos", "guia_regulatoria", True, [],
     "# Declaraciones\nUn suplemento no puede declarar que cura, previene o trata enfermedades [EJEMPLO].\n"
     "# Porción\nLa etiqueta debe declarar la porción y las porciones por envase."),
    ("EJEMPLO Norma de contenido de vitaminas y minerales", "norma", True, ["Magnesio", "Vitamina D3"],
     "# Magnesio\nPara este ejemplo, la cantidad de magnesio elemental por porción no debe pasar de 350 mg.\n"
     "# Vitamina D\nLa vitamina D se declara en µg; 1 UI equivale a 0.025 µg de colecalciferol."),
    ("EJEMPLO Ficha técnica de bisglicinato de magnesio", "ficha_tecnica", True, ["Magnesio"],
     "# Especificación\nBisglicinato de magnesio con 14 % de magnesio elemental [EJEMPLO].\n# Almacenamiento\nLugar fresco y seco."),
    ("EJEMPLO Ensayo de ashwagandha y estrés percibido", "ensayo_clinico", True, ["Ashwagandha"],
     "# Resumen\n60 adultos [EJEMPLO] con estrés percibido moderado tomaron 600 mg de extracto de raíz por 8 semanas.\n"
     "# Resultados\nBajó el puntaje de estrés percibido frente a placebo.\n# Seguridad\nSin eventos adversos graves."),
    ("EJEMPLO Seguridad de la ashwagandha", "revision", True, ["Ashwagandha"],
     "# Resumen\nRevisión [EJEMPLO]: se reportaron casos aislados de molestias hepáticas; se sugiere precaución en embarazo."),
    ("EJEMPLO Melatonina y latencia de sueño", "revision", True, ["Melatonina"],
     "# Resumen\nRevisión [EJEMPLO]: la melatonina redujo unos minutos el tiempo para quedarse dormido en adultos."),
    ("EJEMPLO Certificado de análisis lote 001", "certificado", True, ["Magnesio"],
     "# Resultado\nLote 001 [EJEMPLO]: contenido de magnesio dentro de especificación. Vigente 12 meses."),
    ("EJEMPLO Vitamina D3 y niveles en sangre", "articulo", False, ["Vitamina D3"],
     "# Resumen\nEstudio observacional [EJEMPLO] de niveles de vitamina D en adultos de ciudad."),
    ("EJEMPLO Glicinato de magnesio y sueño profundo", "articulo", False, ["Magnesio"],
     "# Resumen\nPiloto [EJEMPLO] de 20 adultos mayores con glicinato de magnesio y sueño profundo."),
    ("EJEMPLO Presentación de tendencias de relajación", "presentacion", False, [],
     "# Tendencias\nPresentación [EJEMPLO] sobre productos de relajación y sueño en tiendas naturistas."),
]
# «para_cada» dice a qué renglones aplica; la condición que cumple cada renglón va a su lado («todas», «rango»…).
MAGNESIO_COHERENTE = {"para_cada": {"lista": "ingredientes", "donde": {"igual": ["en_compuesto", True]}}, "todas": [
    {"existe": "cantidad_compuesto"}, {"existe": "cantidad_activa"},
    {"unidades_compatibles": ["unidad_compuesto", "unidad_activa"], "dimension": "masa"},
    {"comparar": ["cantidad_activa", "<=", "cantidad_compuesto"], "convertir_a": "mg"}]}
MAGNESIO_TOPE = {"para_cada": {"lista": "ingredientes", "donde": {"igual": ["nombre", "Magnesio"]}},
                 "rango": {"campo": "cantidad_activa", "max": 350, "unidad": "mg"}}
# (código, área, nombre, propósito, modo, severidad, condición, estado, fuente)
REGLAS = [
    ("R-COMP-901", "COMP", "[EJEMPLO] Compuesto y activo coherentes", "Si un ingrediente viene en compuesto, se captura la cantidad del compuesto y la del activo, y el activo no pasa del compuesto.",
     "automatica", "bloqueante", MAGNESIO_COHERENTE, "publicada", "EJEMPLO Ficha técnica de bisglicinato de magnesio"),
    ("R-COMP-902", "COMP", "[EJEMPLO] Tope de magnesio elemental", "El magnesio elemental por porción no pasa de 350 mg (cantidad de ejemplo).",
     "automatica", "mayor", MAGNESIO_TOPE, "publicada", "EJEMPLO Norma de contenido de vitaminas y minerales"),
    ("R-ETQ-901", "ETQ", "[EJEMPLO] Sin promesas de curar", "Las declaraciones de etiqueta no dicen que el producto cura, previene o trata enfermedades.",
     "automatica", "bloqueante", {"texto_no_contiene": ["declaraciones", ["cura", "previene", "trata", "elimina"]]}, "publicada", "EJEMPLO Guía de etiquetado de suplementos"),
    ("R-DOC-901", "DOC", "[EJEMPLO] Porción declarada", "La ficha declara la porción.",
     "automatica", "menor", {"existe": "porcion"}, "publicada", "EJEMPLO Guía de etiquetado de suplementos"),
    ("R-EVI-901", "EVI", "[EJEMPLO] Beneficio con evidencia", "El beneficio que se comunica está respaldado por evidencia citada y revisada.",
     "asistida", "mayor", None, "publicada", "EJEMPLO Revisión de magnesio y calidad de sueño"),
    ("R-REG-901", "REG", "[EJEMPLO] Categoría sanitaria confirmada", "Regulatorio confirma la categoría sanitaria del producto antes del Filtro.",
     "manual", "bloqueante", None, "en_revision", "EJEMPLO Guía de etiquetado de suplementos"),
    ("R-CAL-901", "CAL", "[EJEMPLO] Certificado de análisis vigente", "Hay un certificado de análisis vigente del activo principal.",
     "automatica", "mayor", {"documento": {"tipo": "certificado", "vigente": True}}, "borrador", "EJEMPLO Certificado de análisis lote 001"),
    ("R-BOT-901", "BOT", "[EJEMPLO] Ashwagandha con advertencia de embarazo", "Si lleva ashwagandha, las advertencias mencionan embarazo.",
     "manual", "mayor", None, "borrador", "EJEMPLO Seguridad de la ashwagandha"),
]


def _admin(bd: Session) -> int:
    uid = bd.scalar(select(UsuarioRol.usuario_id).join(Rol, Rol.rol_id == UsuarioRol.rol_id).where(Rol.codigo == "admin"))
    if not uid:
        sys.exit("No hay un usuario administrador. Corre primero scripts.crear_admin.")
    return uid


def cargar() -> None:
    with Session(motor()) as bd:
        if bd.scalar(select(Recurso).where(Recurso.titulo.like("EJEMPLO %"))):
            sys.exit("Los ejemplos ya están cargados. Quítalos con --quitar antes de volver a cargarlos.")
        yo = _admin(bd)
        ingredientes = {}
        for nombre, tipo, forma, sinonimos in INGREDIENTES:
            i = bd.scalar(select(Ingrediente).where(Ingrediente.nombre == nombre))
            if not i:
                i = Ingrediente(nombre=nombre, tipo=tipo, forma_quimica=forma, sinonimos=json.dumps(sinonimos, ensure_ascii=False), creado_por=yo)
                bd.add(i)
                bd.flush()
            ingredientes[nombre] = i
        versiones = {}
        for titulo, tipo, revisada, ings, texto in FUENTES:
            r = Recurso(titulo=titulo, tipo=tipo, clasificacion="general", responsable_id=yo, creado_por=yo)
            bd.add(r)
            bd.flush()
            v = RecursoVersion(recurso_id=r.recurso_id, numero=1, texto=f"{texto}\n# Aviso\n{AVISO}", anio=2026, idioma="es",
                               resumen=AVISO, creado_por=yo, tipo_revision=A.tipo_revision(tipo),
                               vigente_desde=date.today() - timedelta(days=30) if tipo in ("norma", "guia_regulatoria", "certificado") else None,
                               vigente_hasta=date.today() + timedelta(days=335) if tipo == "certificado" else None)
            if revisada:
                v.estado, v.revisado_por, v.revisado_en = "revisado", yo, ahora()
                v.respalda = texto.split("\n")[1][:500]
                v.limites = "Datos de ejemplo."
                v.corresponde = "ingrediente"
            bd.add(v)
            bd.flush()
            for n in ings:
                bd.add(Vinculo(version_id=v.version_id, tipo="ingrediente", ingrediente_id=ingredientes[n].ingrediente_id, creado_por=yo))
            trabajos.encolar(bd, "leer", v.version_id, usuario_id=yo)
            versiones[titulo] = v
        bd.commit()
        trabajos.procesar(bd, limite=60)  # lectura y secciones; las huellas esperan a Ollama si está apagado

        for codigo, area, nombre, proposito, modo, severidad, condicion, estado, fuente in REGLAS:
            if condicion:
                motor_reglas.validar(condicion)
            r = Regla(codigo=codigo, area=area, nombre=nombre, creado_por=yo)
            bd.add(r)
            bd.flush()
            rv = ReglaVersion(regla_id=r.regla_id, numero=1, estado=estado, proposito=proposito, modo=modo, severidad=severidad,
                              condicion=json.dumps(condicion, ensure_ascii=False) if condicion else None,
                              fuente_version_id=versiones[fuente].version_id, fuente_ubicacion="Sección 1 [EJEMPLO]",
                              vigente_desde=date.today() - timedelta(days=1) if estado != "borrador" else None,
                              rol_revisor={"manual": "innovacion_regulatorio", "asistida": "innovacion_lider"}.get(modo),
                              campos_relevantes=json.dumps(["beneficio", "declaraciones"]) if modo == "asistida" else None,
                              autor_id=yo, aprobador_id=yo if estado == "publicada" else None,
                              publicado_en=ahora() if estado == "publicada" else None,
                              enviado_en=ahora() if estado != "borrador" else None,
                              alcance=json.dumps({"categoria_sanitaria": ["suplemento"]}) if area in ("ETQ", "EVI") else None)
            bd.add(rv)
        bd.flush()

        fichas = [
            ("[EJEMPLO] Magnesio para relajación", "Cápsula de bisglicinato de magnesio para relajación y descanso.", "sueño",
             {"nombre_comercial": "[EJEMPLO] Vidanat Magnesio Relax", "presentacion": "60 cápsulas", "porcion": "2", "unidad_porcion": "cápsulas",
              "porciones_dia": "1", "beneficio": "Ayuda a la relajación", "declaraciones": "Ayuda a la relajación y al descanso",
              "categoria_sanitaria": "suplemento", "categoria_comercial": "sueño", "precio_objetivo": "289"},
             [{"nombre": "Magnesio", "ingrediente_id": ingredientes["Magnesio"].ingrediente_id, "tipo": "mineral", "forma": "bisglicinato de magnesio",
               "en_compuesto": True, "cantidad_compuesto": 1000, "unidad_compuesto": "mg", "cantidad_activa": 140, "unidad_activa": "mg", "fraccion_activa": 0.14}],
             ["EJEMPLO Absorción de dos formas de magnesio", "EJEMPLO Revisión de magnesio y calidad de sueño"]),
            ("[EJEMPLO] Ashwagandha con melatonina", "Tableta para estrés y sueño.", "estrés",
             {"nombre_comercial": "[EJEMPLO] Vidanat Calma Noche", "presentacion": "30 tabletas", "beneficio": "Ayuda con el estrés",
              "declaraciones": "Cura el insomnio y baja el estrés", "categoria_sanitaria": "suplemento", "categoria_comercial": "estrés"},
             [{"nombre": "Ashwagandha", "ingrediente_id": ingredientes["Ashwagandha"].ingrediente_id, "tipo": "botanico", "forma": "extracto de raíz",
               "en_compuesto": False, "cantidad_activa": 600, "unidad_activa": "mg"},
              {"nombre": "Melatonina", "ingrediente_id": ingredientes["Melatonina"].ingrediente_id, "tipo": "otro",
               "en_compuesto": False, "cantidad_activa": 3, "unidad_activa": "mg"}],
             ["EJEMPLO Ensayo de ashwagandha y estrés percibido"]),
        ]
        for nombre, descripcion, categoria, datos, ings, citas in fichas:
            e = Expediente(folio=ex.nuevo_folio(bd), nombre=nombre, descripcion=f"{descripcion} {AVISO}", jurisdiccion="MX",
                           categoria_sanitaria="suplemento", categoria_comercial=categoria, presentacion="capsula",
                           etapa="investigacion", responsable_id=yo, creado_por=yo)
            bd.add(e)
            bd.flush()
            e.equipo.append(ExpedienteEquipo(usuario_id=yo, papel="responsable"))
            ex.guardar_ficha(bd, e, datos, ings, usuario_id=yo, nota="[EJEMPLO]")
            for t in citas:
                v = versiones[t]
                sec = bd.scalar(select(Seccion).where(Seccion.version_id == v.version_id).order_by(Seccion.orden))
                bd.add(Evidencia(expediente_id=e.expediente_id, version_id=v.version_id, fragmento_id=sec.fragmento_id if sec else None,
                                 pagina=sec.pagina if sec else None, seccion=sec.seccion if sec else None,
                                 respalda=v.respalda or t, aplica="parcial", creado_por=yo))
            bd.add(Comparable(expediente_id=e.expediente_id, origen="manual", producto=f"Producto comparable {categoria} [EJEMPLO]",
                              marca="Marca de ejemplo", presentacion="60 cápsulas", precio=310, fuente="Captura de ejemplo", creado_por=yo))
            bd.add(Escenario(expediente_id=e.expediente_id, nombre="Base [EJEMPLO]", costo_unitario=95, precio=289,
                             supuestos="Costos de ejemplo, no cotizados.", confianza="baja", creado_por=yo))
            bd.add(Pendiente(expediente_id=e.expediente_id, descripcion="Confirmar proveedor del activo [EJEMPLO]", responsable_id=yo,
                             fecha_limite=date.today() + timedelta(days=14), determinante=True, creado_por=yo))
            bd.flush()
            evs.evaluar(bd, e, motivo="ficha", usuario_id=yo)
        bd.commit()
        indice.olvidar()
        print(f"Listo: {len(FUENTES)} fuentes, {len(REGLAS)} reglas y {len(fichas)} expedientes [EJEMPLO].")


def quitar() -> None:
    with Session(motor()) as bd:
        exps = list(bd.scalars(select(Expediente.expediente_id).where(Expediente.nombre.like("[[]EJEMPLO]%"))))
        recs = list(bd.scalars(select(Recurso.recurso_id).where(Recurso.titulo.like("EJEMPLO %"))))
        vers = list(bd.scalars(select(RecursoVersion.version_id).where(RecursoVersion.recurso_id.in_(recs or [0]))))
        reglas = list(bd.scalars(select(Regla.regla_id).where(Regla.nombre.like("[[]EJEMPLO]%"))))
        rvs = list(bd.scalars(select(ReglaVersion.regla_version_id).where(ReglaVersion.regla_id.in_(reglas or [0]))))
        e_ = exps or [0]
        evals = list(bd.scalars(select(Evaluacion.evaluacion_id).where(or_(Evaluacion.expediente_id.in_(e_), Evaluacion.regla_version_id.in_(rvs or [0])))))
        res = list(bd.scalars(select(EvaluacionResultado.resultado_id).where(or_(
            EvaluacionResultado.evaluacion_id.in_(evals or [0]), EvaluacionResultado.regla_version_id.in_(rvs or [0])))))
        fichas = list(bd.scalars(select(FichaVersion.ficha_id).where(FichaVersion.expediente_id.in_(e_))))
        invs = list(bd.scalars(select(Investigacion.investigacion_id).where(Investigacion.expediente_id.in_(e_))))
        for consulta in (
            delete(Revision).where(or_(Revision.resultado_id.in_(res or [0]), Revision.expediente_id.in_(e_))),
            delete(Excepcion).where(or_(Excepcion.resultado_id.in_(res or [0]), Excepcion.expediente_id.in_(e_))),
            delete(Decision).where(Decision.expediente_id.in_(e_)),
            delete(EvaluacionResultado).where(EvaluacionResultado.resultado_id.in_(res or [0])),
            delete(Evaluacion).where(Evaluacion.evaluacion_id.in_(evals or [0])),
            delete(Evidencia).where(or_(Evidencia.expediente_id.in_(e_), Evidencia.version_id.in_(vers or [0]))),
            delete(Comparable).where(Comparable.expediente_id.in_(e_)),
            delete(Escenario).where(Escenario.expediente_id.in_(e_)),
            delete(Pendiente).where(Pendiente.expediente_id.in_(e_)),
            delete(FichaIngrediente).where(FichaIngrediente.ficha_id.in_(fichas or [0])),
            delete(FichaVersion).where(FichaVersion.ficha_id.in_(fichas or [0])),
            delete(FormulaVersion).where(FormulaVersion.expediente_id.in_(e_)),
            delete(Hallazgo).where(Hallazgo.investigacion_id.in_(invs or [0])),
            delete(Investigacion).where(Investigacion.investigacion_id.in_(invs or [0])),
            delete(Consulta).where(Consulta.expediente_id.in_(e_)),
            delete(ExpedienteEquipo).where(ExpedienteEquipo.expediente_id.in_(e_)),
            delete(ReglaVersion).where(ReglaVersion.regla_version_id.in_(rvs or [0])),
            delete(Regla).where(Regla.regla_id.in_(reglas or [0])),
            delete(Vinculo).where(or_(Vinculo.version_id.in_(vers or [0]), Vinculo.expediente_id.in_(e_))),
            delete(Seccion).where(Seccion.version_id.in_(vers or [0])),
            delete(RecursoArchivo).where(RecursoArchivo.version_id.in_(vers or [0])),
            delete(Trabajo).where(Trabajo.tipo.in_(("leer", "huellas", "sugerir", "describir")), Trabajo.objeto_id.in_(vers or [0])),
            delete(RecursoVersion).where(RecursoVersion.version_id.in_(vers or [0])),
            delete(Recurso).where(Recurso.recurso_id.in_(recs or [0])),
            delete(Expediente).where(Expediente.expediente_id.in_(e_)),
        ):
            bd.execute(consulta)
        bd.commit()
        indice.olvidar()
        print(f"Quitados: {len(recs)} fuentes, {len(reglas)} reglas y {len(exps)} expedientes [EJEMPLO].")


if __name__ == "__main__":
    quitar() if "--quitar" in sys.argv else cargar()
