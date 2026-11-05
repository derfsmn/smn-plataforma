"""Carga a la Base de conocimiento de Compras el «Consolidado de políticas de Compras» (juntas del 27 y 28 de octubre de
2026) y los pesos del semáforo que contestó Compras (pedido de Diego, 2026-10-28: «colocarlos en la base de conocimiento
desglosadas»).

- Las 42 políticas entran una por una, como **borrador**: el consolidado dice que no acredita aprobación formal. Compras
  las revisa y marca «vigente» las que ya aplican; solo las vigentes las usa el semáforo.
- Las reglas con número (rotación) y los bloqueos que Compras llamó indispensables entran como reglas **sin usar**
  (activa = no), con la duda que dejó el consolidado. Compras las activa cuando las confirme.
- Los pesos son el promedio de las 3 respuestas de Compras, redondeado a enteros que suman 100.

No borra ni cambia lo que ya exista: una política o regla con el mismo título se salta.

Uso con Docker:  docker compose exec api python -m scripts.cargar_politicas_compras
Opciones:        --sin-pesos  (no toca los pesos)   --revisar  (solo dice qué haría)
                 --vigentes   (marca vigentes las políticas del consolidado que sigan en borrador)
"""
import argparse
from decimal import Decimal
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from modulos.compras.modelos_conocimiento import ConocimientoPeso, ConocimientoPolitica, ConocimientoRegla
from nucleo.bitacora import registrar

FUENTE = "Consolidado de políticas de Compras (28 oct 2026)"

# (No., tema de la plataforma, título, política o regla, observación del consolidado, origen)
POLITICAS = [
    (1, "proveedores", "Situación legal del proveedor",
     "Acreditar la constitución de la persona moral o la actividad empresarial y alta correspondiente de la persona "
     "física. No aceptar proveedores sin acreditar su situación legal.",
     "Expresada. Confirmar documentos por tipo de persona.", "27 y 28 oct"),
    (2, "regulatorio", "Aviso de funcionamiento",
     "Se señaló que, sin aviso de funcionamiento, el producto o proveedor no puede avanzar.",
     "Expresada como bloqueante.", "27 oct"),
    (3, "regulatorio", "Registro o aviso sanitario",
     "Se mencionó devolver o detener propuestas que carezcan del documento sanitario aplicable o no cumplan con él.",
     "Expresada; mezcla conceptos. Confirmar documento exigible según producto, sin asumir aplicación universal.",
     "27 oct"),
    (4, "regulatorio", "GS1 y códigos de barras",
     "Contar con código de barras y evidencia de acreditación GS1; revisar cómo obtener la documentación del proveedor.",
     "Expresada como indispensable. El prefijo 750 no se considera prueba suficiente de acreditación.", "27 oct"),
    (5, "regulatorio", "Registro de marca",
     "Solicitar documentación de registro o trámite de marca para revisión. Se describió como limitativa, aún no "
     "bloqueante en todos los casos.",
     "Expresada con intención de formalizar.", "27 oct"),
    (6, "proveedores", "Titularidad y comercialización",
     "Revisar diferencias entre titular de marca y persona que factura; se mencionó permiso de comercialización como "
     "respaldo.",
     "Expresada.", "27 oct"),
    (7, "regulatorio", "Soporte de importación",
     "Pedir documentos adicionales a proveedores de importados: se menciona «LOA» o factura con referencia del "
     "pedimento.",
     "Expresada como indispensable. Confirmar el significado de LOA y la documentación que se acepta junto con la "
     "referencia al pedimento.", "27 oct"),
    (8, "alta_productos", "Certificado y capacidad de calidad",
     "Requerir certificado de calidad del producto nuevo en la primera entrega. Se admite emisión por el área de "
     "calidad del fabricante o por un tercero. Preguntar si el proveedor cuenta con área propia o certificación externa.",
     "Expresada como condición de recepción. No se exige exclusivamente tercero. Precisar alcance por producto o lote, "
     "evidencia y validación. Las revisiones aleatorias posteriores no sustituyen la primera entrega.", "27 oct"),
    (9, "alta_productos", "Ficha técnica",
     "Subir la ficha técnica de cada producto nuevo al enlace habilitado para revisión de Calidad.",
     "Práctica reciente descrita. Confirmar enlace, responsable y momento de carga.", "27 oct"),
    (10, "alta_productos", "Vida útil de recepción",
     "Usar la ficha técnica para conocer vida desde fabricación y remanente al recibir. Aplicar el mínimo "
     "correspondiente a la categoría conforme a la tabla que Compras indicó tener.",
     "Expresada y complementada el 28 oct. Tabla y valores no aportados; no fijar seis meses como mínimo universal.",
     "27 y 28 oct"),
    (11, "proveedores", "Fumigación de la unidad",
     "Exigir certificado de fumigación de la unidad de entrega e informar el requisito al proveedor nuevo.",
     "Regla de recibo descrita y mejora de comunicación propuesta. Confirmar vigencia del certificado.", "27 oct"),
    (12, "proveedores", "Limpieza y revisiones",
     "Solicitar unidades limpias; se describen verificaciones aleatorias de Calidad y revisión posterior de "
     "proveedores existentes.",
     "Expresada. Precisar frecuencia y criterios.", "27 oct"),
    (13, "regulatorio", "Información en español",
     "Requerir descripción e información del producto en español; el nombre comercial puede estar en otro idioma. El "
     "área competente revisa el etiquetado.",
     "Expresada. Precisar alcance por categoría.", "28 oct"),
    (14, "regulatorio", "Información básica del empaque",
     "Se mencionó rechazo por ausencia de tabla nutrimental, lote o caducidad. Los requisitos de código de barras e "
     "idioma se concentran en sus reglas específicas.",
     "Expresada como filtro. Validar aplicabilidad por categoría; no asumir obligación idéntica para todo producto.",
     "28 oct"),
    (15, "regulatorio", "Afirmaciones terapéuticas",
     "Rechazar suplementos con nombres, promesas o alusiones terapéuticas improcedentes para su clasificación; "
     "distinguir medicamentos, remedios y homeopáticos.",
     "Expresada como filtro. Aplicabilidad a confirmar con Regulatorio.", "28 oct"),
    (16, "regulatorio", "Stickers y correcciones",
     "Se señalaron como motivo de rechazo stickers en lote, caducidad, código o para cubrir errores. Revisar "
     "físicamente cuando la foto sea insuficiente.",
     "Expresada. Alcance y excepciones pendientes, incluidos importados.", "28 oct"),
    (17, "regulatorio", "Ingredientes restringidos",
     "Consultar al área regulatoria y contar con una lista validada para detectar ingredientes incompatibles con la "
     "categoría y el canal.",
     "Propuesta de formalización. No existe lista consolidada en lo aportado.", "28 oct"),
    (18, "alta_productos", "Categorías sin permiso",
     "No incorporar la categoría de mascotas bajo las condiciones actuales de permisos descritas.",
     "Expresada como limitación actual. Verificar permisos y alcance; no asumir prohibición perpetua.", "28 oct"),
    (19, "alta_productos", "Limpieza del hogar",
     "Los productos de limpieza doméstica generalmente no se presentan a evaluación.",
     "Criterio implícito, sin prohibición formal documentada.", "28 oct"),
    (20, "proveedores", "Veto e historial del proveedor",
     "Considerar vetos y antecedentes graves al evaluar al proveedor. Un veto no impide buscar el producto con otro "
     "proveedor.",
     "Expresada con propuesta de registro. Sin lista consolidada ni umbral formal de veto aportados.", "28 oct"),
    (21, "proveedores", "Origen y excepciones de abastecimiento",
     "Preferir compra directa al fabricante. Si sus mínimos u otras condiciones lo impiden, seleccionar distribuidor. "
     "El uso excepcional de distribuidores o clubes de precio se describió para productos necesarios, masivos o "
     "probados con demanda, procurando que sean pocos.",
     "Preferencia expresada, no prohibición absoluta. No se definió cuota de excepciones ni autoridad que las autoriza.",
     "28 oct"),
    (22, "proveedores", "Abastecimiento de importados",
     "El abastecimiento se realiza mediante proveedores o distribuidores; se indicó que SMN no importa directamente.",
     "Práctica descrita, no prohibición de productos importados. Complementa el requisito documental de importación.",
     "28 oct"),
    (23, "proveedores", "Canales de comercialización",
     "Revisar desde la negociación los canales permitidos y las restricciones del proveedor: tiendas, mayoreo, canal "
     "moderno, e-commerce y marketplaces.",
     "Expresada. Documentar restricciones por proveedor y producto.", "28 oct"),
    (24, "alta_productos", "Tendencias por categoría",
     "Buscar oportunidades en tendencia y valorar tempranamente los productos que llegan a SMN.",
     "Criterio comercial expresado. No sustituye requisitos de cumplimiento.", "27 oct"),
    (25, "alta_productos", "Comparación con el surtido",
     "Comparar precio, presentación, productos ya catalogados, diferenciación y respaldo de marketing antes de "
     "incorporar otro de la misma categoría.",
     "Expresada. Sin ponderaciones o tolerancias definidas.", "27 oct"),
    (26, "alta_productos", "Preferencias personales",
     "Evaluar lo que pide el mercado y el ecosistema de consumo, separándolo del gusto personal por empaques clásicos o "
     "modernos.",
     "Orientación expresada. No se aprobó preferencia universal por empaques modernos o clásicos.", "27 oct"),
    (27, "precios", "Presencia en mercado y precio competitivo",
     "Valorar productos presentes en otros puntos de venta que SMN aún no tiene y buscar precio igual o mejor que el "
     "mercado. Si no se logra, negociar; se describieron casos que compiten con membresía y otros en los que se "
     "descarta el alta.",
     "Criterio expresado en ambas reuniones. Pendiente definir si rige precio público o membresía y la tolerancia "
     "aceptable. No supone alta automática por presencia en retail.", "27 y 28 oct"),
    (28, "precios", "Margen por categoría",
     "Aplicar la lista de márgenes de cada categoría y negociar las mejores condiciones para cumplirla.",
     "Expresada. Lista de márgenes por categoría solicitada, no aportada. El ejemplo de margen de 30 % no constituye "
     "un margen general.", "28 oct"),
    (29, "precios", "Excepción de margen",
     "Considerar menor margen para productos de alto interés, buena evaluación, demanda o tendencia. Justificar el caso "
     "específico.",
     "Excepción comercial expresada. Sin piso, autorización ni procedimiento definidos.", "28 oct"),
    (30, "precios", "Precio para comparación",
     "Usar el precio final proyectado de SMN con impuestos para compararlo con el precio observado en mercado.",
     "Aclaración de trabajo. Costo de compra y precio externo no equivalen al precio final de SMN.", "28 oct"),
    (31, "comite", "Categorías nuevas",
     "Presentar al comité y Dirección las propuestas de categoría nueva con estudio de mercado, tendencia significativa "
     "y cifras que sustenten la oportunidad.",
     "Criterio planteado. Afinidad naturista debatida, no cerrada como filtro absoluto.", "28 oct"),
    (32, "proveedores", "Condiciones comerciales",
     "Revisar pedidos mínimos, días de crédito y tiempos de entrega conforme a condiciones escritas.",
     "Expresada. Sin mínimos, plazos o condiciones universales definidos en las fuentes.", "28 oct"),
    (33, "proveedores", "Apoyos y devoluciones",
     "Considerar consignación, cambios o devoluciones por bajo desplazamiento, apoyo comercial y ofertas estacionales.",
     "Criterios mencionados. Reglas específicas de consignación, devoluciones y apoyos pendientes de entregar.",
     "28 oct"),
    (34, "alta_productos", "Buena rotación de impulso",
     "Al menos 6 piezas por sucursal al mes.",
     "Parámetro expresado; confirmar ventana y cálculo oficial.", "28 oct"),
    (35, "alta_productos", "Buena rotación del resto",
     "Entre 3 y 5 piezas por sucursal al mes, excluyendo impulso y suplementos deportivos.",
     "Rango expresado; falta criterio por categoría y tratamiento por encima del rango.", "28 oct"),
    (36, "alta_productos", "Buena rotación deportiva",
     "Entre 1.75 y 2.5 piezas por sucursal; por contexto, mensual. Se menciona evaluación durante 6 meses.",
     "Parámetro expresado; confirmar unidad temporal y ventana para todos los grupos.", "28 oct"),
    (37, "alta_productos", "Permanencia de impulso",
     "Se escucha «menos de 1.5» piezas como condición de permanencia.",
     "Pendiente por ambigüedad. No convertir a ≥1.5 ni automatizar hasta confirmar con Compras y Category.", "28 oct"),
    (38, "alta_productos", "Permanencia del resto y deportivos",
     "Se indicó 0.75 piezas al mes por sucursal para el resto del catálogo y suplementos deportivos.",
     "Referencia expresada. Confirmar si es mínimo, promedio, redondeo y exclusiones.", "28 oct"),
    (39, "proceso", "Revisión posterior al alta",
     "Category revisa desempeño. Se propone revisar mensualmente los nuevos que cumplan 6 meses y cubrir todas las "
     "categorías.",
     "Responsabilidad descrita; automatización y cobertura total propuestas.", "28 oct"),
    (40, "comite", "Intervención del comité",
     "Mantener al comité y llevarle propuestas sustentadas en investigación, regulación, presentación y evidencia.",
     "Continuidad expresada. Menor intervención es una intención, no eliminación de su aprobación.", "27 oct"),
    (41, "proceso", "Registro de decisiones",
     "Registrar motivos de rechazo o excepción y utilizar esa información para futuras evaluaciones y recomendaciones.",
     "Propuesta expresada. Falta definir bitácora, responsable y autorización.", "27 oct"),
    (42, "proceso", "Criterio experto frente a IA",
     "Compras podrá sostener una conclusión distinta de la recomendación de IA con su experiencia; la herramienta se "
     "concibe como apoyo.",
     "Orientación expresada. Formalizar revisión y evidencia; no implica autorización automática.", "27 oct"),
]

PRECISIONES = (
    "Puntos que el consolidado deja abiertos antes de convertir las políticas en reglas:\n\n"
    "- Precio competitivo: resolver precio público frente a membresía antes de fijar alertas. El ejemplo de margen de "
    "30 % no constituye un margen general.\n"
    "- Permanencia de impulso: la expresión «menos de 1.5» es ambigua. No se cambia el signo ni se establece un mínimo "
    "hasta confirmar con Compras y Category.\n"
    "- Rotación: conservar separados buena rotación y permanencia. Confirmar ventana de seis meses, unidad temporal, "
    "promedio, sucursales incluidas e impacto de desabasto.\n"
    "- GS1, sanidad y empaque: validar evidencia y aplicabilidad por categoría. El prefijo 750 no se considera prueba "
    "suficiente de acreditación.\n"
    "- Importación: confirmar el significado de LOA y la documentación que se acepta junto con la referencia al "
    "pedimento. Revisar excepciones de stickers para no contradecir el tratamiento de importados.\n"
    "- Certificado de calidad: la primera entrega se describió como requisito; las revisiones aleatorias posteriores no "
    "la sustituyen. La vida útil se define por categoría, sin un mínimo general inventado.\n"
    "- Las prácticas de riesgo relatadas no se convierten en excepciones regulatorias aprobadas. La lista de "
    "ingredientes y el alcance de permisos requieren revisión especialista."
)

# Reglas que el semáforo podría aplicar; entran sin usar hasta que Compras las confirme.
# (tipo, criterio, mínimo, máximo, unidad, meses, descripción)
REGLAS = [
    ("rechazo", "Proveedor sin acreditar su situación legal", None, None, None, None,
     "Política 1 del consolidado. Confirmar documentos por tipo de persona."),
    ("rechazo", "Sin aviso de funcionamiento", None, None, None, None,
     "Política 2 del consolidado (expresada como bloqueante)."),
    ("rechazo", "Sin código de barras con acreditación GS1", None, None, None, None,
     "Política 4 del consolidado (indispensable). El prefijo 750 no basta como prueba."),
    ("rechazo", "Suplemento con nombre, promesa o alusión terapéutica improcedente", None, None, None, None,
     "Política 15 del consolidado. Aplicabilidad a confirmar con Regulatorio."),
    ("rechazo", "Stickers en lote, caducidad o código, o para cubrir errores", None, None, None, None,
     "Política 16 del consolidado. Alcance y excepciones pendientes, incluidos importados."),
    ("rechazo", "Producto de la categoría mascotas", None, None, None, None,
     "Política 18 del consolidado: limitación actual por permisos, no prohibición perpetua."),
    ("exito", "Buena rotación de impulso", Decimal("6"), None, "piezas por sucursal al mes", None,
     "Política 34 del consolidado. Confirmar ventana y cálculo oficial; asignar a los departamentos de impulso."),
    ("exito", "Buena rotación del resto", Decimal("3"), Decimal("5"), "piezas por sucursal al mes", None,
     "Política 35 del consolidado. Excluye impulso y suplementos deportivos; falta criterio por categoría."),
    ("exito", "Buena rotación deportiva", Decimal("1.75"), Decimal("2.5"), "piezas por sucursal al mes", 6,
     "Política 36 del consolidado. Confirmar unidad temporal (se entendió mensual) y ventana de 6 meses."),
    ("umbral", "Permanencia del resto y deportivos", Decimal("0.75"), None, "piezas por sucursal al mes", None,
     "Política 38 del consolidado. Confirmar si es mínimo, promedio, redondeo y exclusiones."),
]

# Hojas «Mis puntos» que contestaron tres personas de Compras (en el orden del PDF)
RESPUESTAS = {
    "demanda": (20, 10, 20),
    "rentabilidad": (20, 25, 20),
    "precio": (15, 30, 20),
    "tendencia": (20, 10, 20),
    "categoria": (10, 15, 5),
    "proveedor": (15, 10, 15),
}


def promedio_entero(respuestas: dict[str, tuple[int, ...]]) -> dict[str, int]:
    """Promedio redondeado de modo que sume 100: se reparten los puntos que faltan a los de mayor residuo; si empatan,
    al que va primero en la lista (demanda, rentabilidad, precio...)."""
    exactos = {f: Fraction(sum(v), len(v)) for f, v in respuestas.items()}
    puntos = {f: int(x) for f, x in exactos.items()}
    orden = sorted(exactos, key=lambda f: -(exactos[f] - puntos[f]))  # sorted es estable: el empate respeta la lista
    for f in orden[: 100 - sum(puntos.values())]:
        puntos[f] += 1
    return puntos


def cargar(bd: Session, con_pesos: bool = True) -> dict:
    hechos = {"politicas": 0, "politicas_ya": 0, "reglas": 0, "reglas_ya": 0, "pesos": None}
    titulos = set(bd.scalars(select(ConocimientoPolitica.titulo)))
    for n, tema, titulo, texto, observacion, origen in POLITICAS:
        if titulo in titulos:
            hechos["politicas_ya"] += 1
            continue
        contenido = (f"{texto}\n\nEstado y precisión: {observacion}\n\nOrigen: juntas de Compras del {origen} de 2026. "
                     f"Fuente: {FUENTE}, política {n}.")
        bd.add(ConocimientoPolitica(tema=tema, titulo=titulo, contenido=contenido, estado="borrador"))
        hechos["politicas"] += 1
    titulo = "Precisiones pendientes del consolidado de políticas"
    if titulo not in titulos:
        bd.add(ConocimientoPolitica(tema="proceso", titulo=titulo, contenido=f"{PRECISIONES}\n\nFuente: {FUENTE}.",
                                    estado="borrador"))
        hechos["politicas"] += 1
    else:
        hechos["politicas_ya"] += 1

    criterios = set(bd.scalars(select(ConocimientoRegla.criterio)))
    for tipo, criterio, minimo, maximo, unidad, meses, descripcion in REGLAS:
        if criterio in criterios:
            hechos["reglas_ya"] += 1
            continue
        bd.add(ConocimientoRegla(tipo=tipo, criterio=criterio, minimo=minimo, maximo=maximo, unidad=unidad,
                                 periodo_meses=meses, descripcion=descripcion, activa=False))
        hechos["reglas"] += 1

    if con_pesos:
        puntos = promedio_entero(RESPUESTAS)
        for f, p in puntos.items():
            v = RESPUESTAS[f]
            peso = bd.get(ConocimientoPeso, f) or ConocimientoPeso(factor=f)
            peso.puntos = p
            peso.nota = (f"Promedio de las 3 respuestas de Compras del 28 oct 2026 ({', '.join(map(str, v))}): "
                         f"{sum(v) / len(v):.1f}.")
            bd.add(peso)
        hechos["pesos"] = puntos
    registrar(bd, "conocimiento_carga_consolidado", entidad="conocimiento_politica",
              detalle={"fuente": FUENTE, **{k: v for k, v in hechos.items() if k != "pesos"},
                       "pesos": hechos["pesos"]})
    return hechos


def volver_vigentes(bd: Session) -> int:
    """Marca vigentes las políticas del consolidado que sigan en borrador (cuando Compras ya las dio por buenas)."""
    titulos = [t for _, _, t, *_ in POLITICAS] + ["Precisiones pendientes del consolidado de políticas"]
    cambiadas = list(bd.scalars(select(ConocimientoPolitica).where(ConocimientoPolitica.titulo.in_(titulos),
                                                                   ConocimientoPolitica.estado == "borrador")))
    for p in cambiadas:
        p.estado, p.version = "vigente", p.version + 1
    registrar(bd, "conocimiento_consolidado_vigente", entidad="conocimiento_politica",
              detalle={"fuente": FUENTE, "politicas": len(cambiadas)})
    return len(cambiadas)


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--sin-pesos", action="store_true", help="no cambia los pesos del semáforo")
    a.add_argument("--revisar", action="store_true", help="solo dice qué haría, no guarda nada")
    a.add_argument("--vigentes", action="store_true",
                   help="además, marca vigentes las políticas del consolidado que sigan en borrador")
    args = a.parse_args()
    with Session(motor()) as bd:
        hechos = cargar(bd, con_pesos=not args.sin_pesos)
        bd.flush()
        vigentes = volver_vigentes(bd) if args.vigentes else 0
        if args.revisar:
            bd.rollback()
        else:
            bd.commit()
    print(("Revisión (no se guardó nada): " if args.revisar else "Listo: ")
          + f"{hechos['politicas']} políticas nuevas en borrador ({hechos['politicas_ya']} ya estaban), "
            f"{hechos['reglas']} reglas nuevas sin usar ({hechos['reglas_ya']} ya estaban).")
    if args.vigentes:
        print(f"{vigentes} políticas del consolidado pasaron a vigentes.")
    if hechos["pesos"]:
        print("Pesos del semáforo: " + ", ".join(f"{f} {p}" for f, p in hechos["pesos"].items()))


if __name__ == "__main__":
    main()
