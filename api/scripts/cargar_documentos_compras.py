"""Carga a la Base de conocimiento de Compras los 4 documentos que compartió Compras el 29 de octubre de 2026 (pedido de
Diego: «quiero ver dónde iría cada cosa»; análisis en el documento «Documentos de Compras: dónde va cada cosa»):
«Principales condiciones comerciales y requisitos operativos» (Word), «Márgenes para cálculo de precios» (Excel),
«Parámetros de clasificación» (PDF) y «Documentos corporativo proveedores» (PDF).

- Las políticas entran como **borrador**; Compras las revisa y marca «vigente» las que ya aplican.
- Reglas activas solo las que no tienen duda abierta:
  - margen mínimo de la lista A para todos los departamentos (Diego, 29 oct: «ahorita todos entran en la A para poder
    avanzar»);
  - baja a los 6 meses con menos de 3 piezas por sucursal (Diego, 29 oct: «la regla de baja es la que nos pusieron en
    los doctos»);
  - pago de la primera orden en consignación (50 % vendido a 60 días, 80 % a 90 días);
  - máximo de 30 piezas por caja.
- Sin usar: rechazo por no ser titular de la marca (Compras decide si bloquea) y máximo de 25 kg por caja (la propuesta
  del portal no pide el peso).
- La clasificación AA a E queda solo como política: falta confirmar la unidad y qué versión aplica.
- No se capturan nombres, correos ni teléfonos de personas que vienen en los documentos.

No borra ni cambia lo que ya exista: una política o regla con el mismo título se salta.

Uso con Docker:  docker compose exec api python -m scripts.cargar_documentos_compras
Opciones:        --revisar  (solo dice qué haría)
"""
import argparse
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from modulos.compras.modelos_conocimiento import ConocimientoPolitica, ConocimientoRegla
from nucleo.bitacora import registrar

FUENTE = "Documentos compartidos por Compras el 29 oct 2026"
WORD = "«Principales condiciones comerciales y requisitos operativos»"
EXCEL = "«Márgenes para cálculo de precios»"
CLASIFICACION = "«Parámetros de clasificación»"
CORPORATIVO = "«Documentos corporativo proveedores»"

MARGENES = """Margen sobre el precio: precio = costo de reposición ÷ (1 − margen). En todas las listas: intercompañía =
costo + 3.7 %; mayoreo (P3) 22 %; soyas (P7) = P3 − 7 %; tienda virtual = precio lista; tienda virtual membresía =
precio membresía (P2); mayoreo frontera (MF8) igual a MF sin IVA y 31 % con IVA.

| Lista | Tipo de artículo | Lista (PL) | Membresía (P2) | Competencia lista / membresía (P4 / P6) | Frontera lista / membresía (P9 / P10) | Frontera sin IVA (P11 / P12) | Frontera con IVA de 8 % (P11 / P12) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | Autoservicio de renombre | 31 % | 28 % | 31 % / 28 % | 36 % / 33 % | 36 % / 33 % | 39 % / 36 % |
| B | Margen general | 45 % | 35 % | 40 % / 32 % | 48 % / 38 % | 48 % / 38 % | 53 % / 43 % |
| C | 80/20 (revisar con gerencia) | 39 % | 31 % | 34 % / 26 % | 44 % / 36 % | 44 % / 36 % | 47 % / 39 % |
| D | Nutrición deportiva nacional | 36 % | 31 % | 36 % / 31 % | 41 % / 36 % | 41 % / 36 % | 44 % / 39 % |
| E | Nutrición deportiva de importación | 31 % | 26 % | 31 % / 26 % | 31 % / 26 % | 31 % / 26 % | 35 % / 32 % |
| F | Margen específico | 41 % | 34 % | 41 % / 34 % | 46 % / 39 % | 46 % / 39 % | 49 % / 43 % |

Notas del documento: no redondear P3, P7, MF8 ni intercompañía; consultar la asignación de margen con gerencia; en
alimentos de autoservicio, consultar con gerencia.

Mientras Compras define qué departamentos van en cada lista, todos usan la lista A (decisión de Diego, 29 oct 2026).
Pendiente: si el margen mínimo del Word de condiciones comerciales es el de precio lista o el de membresía."""

CLASES = """Cortes para clasificar artículos de AA a E. El documento no dice la unidad; por los valores parecen piezas por
sucursal al mes (pendiente de confirmar, igual que la ventana de tiempo).

Propuesta de abril de 2026 (el documento la llama «propuesta»):

| Clase | Impulso | Resto de productos | Suplementos deportivos |
| --- | --- | --- | --- |
| AA | 11 o más | 10 o más | 5 o más |
| A | 8 a menos de 11 | 5 a menos de 10 | 2.5 a menos de 5 |
| B | 6 a menos de 8 | 3 a menos de 5 | 1.75 a menos de 2.5 |
| C | 3 a menos de 6 | 1.25 a menos de 2.99 | 1 a menos de 1.75 |
| D | 1.5 a menos de 3 | 0.75 a menos de 1.25 | 0.75 a menos de 1 |
| E | menos de 1.5 | menos de 0.75 | menos de 0.75 |

Versión de marzo de 2026:

| Clase | Impulso | Resto de productos | Suplementos deportivos |
| --- | --- | --- | --- |
| AA | 11 o más | 10 o más | 5 o más |
| A | 7 a menos de 11 | 5 a menos de 10 | 2 a menos de 4 |
| B | 4 a menos de 7 | 2 a menos de 5 | 1.25 a menos de 2 |
| C | 2 a menos de 4 | 0.75 a menos de 2 | 0.75 a menos de 1.25 |
| D | 1 a menos de 2 | 0.5 a menos de 0.75 | 0.5 a menos de 0.75 |
| E | menos de 1 | menos de 0.5 | menos de 0.5 |

Artículos por clase en el «Ejercicio 1» del resto de productos: AA 113, A 231, B 332, C 1,118, D 1,014, E 899, nuevos 169
(3,876 en total); con la propuesta de abril cambian B a E.

La clase B coincide con la buena rotación del consolidado (6 impulso, 3 a 5 resto, 1.75 a 2.5 deportivos) y la clase E
con la permanencia (menos de 1.5 impulso, menos de 0.75 resto y deportivos).

Dudas para Compras: unidad y ventana; si ya aplica la versión de abril; huecos entre clases (abril, resto: de 2.99 a 3;
marzo, deportivos: de 4 a 5); la columna «Ejercicio 1» de deportivos repite los conteos del resto."""

DOCUMENTOS = """Documentación completa y actualizada, en PDF en posición vertical (no fotos), enviada al área Jurídica.
La lista es enunciativa: se puede pedir algún otro requisito.

Persona física: acta de nacimiento; comprobante de domicilio de no más de 2 meses; identificación oficial vigente;
constancia del RFC actualizada; CURP; giro o actividad; currículum actualizado; opinión de cumplimiento de obligaciones
(32D) actual; 2 referencias comerciales en hoja membretada con el tiempo de la relación; REPSE (en promotoría, si lo
proporciona); título o registro de marca, o licencia o cesión de derechos; carátula bancaria actualizada; licencia
sanitaria y/o aviso de funcionamiento.

Persona moral: acta constitutiva con inscripción en el registro público; RFC de la persona moral con consulta de fecha
actual; comprobante de domicilio de no más de 2 meses; movimientos corporativos si los hay (cambio de razón social,
domicilio, transformación, escisión); carátula bancaria; opinión de cumplimiento (32D); RFC del representante legal con
fecha actual; poder del representante legal; identificación vigente del representante legal; 2 referencias comerciales
en hoja membretada; título de marca, o licencia o cesión de derechos; licencia sanitaria y/o aviso de funcionamiento;
REPSE (en promotoría, si lo proporciona).

Del producto o mercancía: consulta de COFEPRIS; cumplimiento de NOM aplicables; ejercicios aleatorios de trazabilidad;
reporte y resultado de investigación ante desviaciones de calidad e inocuidad; fichas técnicas y reporte de cambios de
imagen; certificado de producto terminado; certificado de fumigación de las unidades de transporte.

Complementa la política 1 del consolidado («Situación legal del proveedor»)."""

# (tema, título, contenido, documento de origen)
POLITICAS = [
    ("proveedores", "Primera orden en consignación",
     "La primera orden de compra se maneja en consignación a 90 días. A los 60 días naturales de recibida la mercancía "
     "se evalúa su desplazamiento: si vendió al menos el 50 % de lo comprado en la primera orden, se paga el 50 % de la "
     "factura. A los 90 días se paga el total si lo vendido acumulado es al menos el 80 % de la primera orden.\n\n"
     "Complementa la política 33 del consolidado («Apoyos y devoluciones»).", WORD),
    ("proveedores", "Crédito desde la segunda orden",
     "A partir de la segunda orden de compra se manejan 60 días de crédito.\n\n"
     "Complementa la política 32 del consolidado («Condiciones comerciales»).", WORD),
    ("alta_productos", "Evaluación a 6 meses y baja de artículos",
     "A los seis meses de operación se evalúa el desempeño de los artículos. Los que no registren una venta mínima de 3 "
     "piezas por sucursal pueden darse de baja del catálogo activo.\n\n"
     "Diego confirmó el 29 oct 2026 que esta es la regla de baja. Se lee como 3 piezas por sucursal acumuladas en los 6 "
     "meses; el 0.75 piezas por sucursal al mes del consolidado queda como corte de la clase E.", WORD),
    ("proveedores", "Baja y remate de artículos",
     "Si un artículo se da de baja, la mercancía en CEDIS se devuelve al proveedor y la existencia en sucursales va a "
     "remate comercial. En el remate, Súper Mayoreo Naturista absorbe 15 % de descuento y el proveedor otorga 15 % "
     "adicional con nota de crédito.", WORD),
    ("precios", "Descuento logístico",
     "Sobre cada orden de compra se aplica un descuento logístico de 5 %.\n\n"
     "Pendiente: si se resta al costo antes de calcular el margen.", WORD),
    ("precios", "Márgenes por lista de precios", MARGENES, EXCEL),
    ("regulatorio", "Documentos de producto y de importación",
     "El proveedor debe presentar vigentes: consulta sanitaria y/o aviso de funcionamiento, registros de marca, "
     "certificado de calidad por lote y certificado de fumigación de la unidad de reparto. Para productos importados: "
     "LOA (Letter of Authorization, carta de autorización) y factura con el número de pedimento.\n\n"
     "Resuelve qué es LOA (política 7 del consolidado). Pendiente: qué documento sanitario se pide según el tipo de "
     "producto (el Word dice «consulta sanitaria», el documento de Jurídico «licencia sanitaria»).", WORD),
    ("proveedores", "Documentos para alta de proveedor", DOCUMENTOS, CORPORATIVO),
    ("proveedores", "Titular de la marca",
     "El proveedor que se da de alta debe ser única y exclusivamente el titular de la(s) marca(s) del producto. Si no "
     "tiene los derechos vigentes, debe presentar la licencia, autorización de explotación o cesión de derechos que lo "
     "faculte para usarla o comercializarla.\n\n"
     "Resuelve la política 6 del consolidado («Titularidad y comercialización»).", CORPORATIVO),
    ("alta_productos", "Condiciones logísticas de empaque",
     "Peso máximo de 25 kg por caja, máximo 30 piezas por caja y códigos de barras regulados por GS1.", WORD),
    ("alta_productos", "Clasificación de artículos AA a E", CLASES, CLASIFICACION),
]

# (tipo, criterio, mínimo, máximo, unidad, meses, activa, descripción)
REGLAS = [
    ("umbral", "Margen mínimo (lista A, precio lista)", Decimal("31"), None, "%", None, True,
     f"Lista A de {EXCEL}: margen sobre el precio de lista. Todos los departamentos usan la lista A mientras Compras "
     "define cuál le toca a cada uno (Diego, 29 oct 2026)."),
    ("umbral", "Baja a 6 meses: mínimo de piezas por sucursal", Decimal("3"), None,
     "piezas por sucursal en 6 meses", 6, True,
     f"{WORD}. Confirmada por Diego el 29 oct 2026; se lee como acumulado de los 6 meses."),
    ("exito", "Primera orden: vendido a los 60 días", Decimal("50"), None, "% de la primera orden", 2, True,
     f"{WORD}: si se alcanza, se paga el 50 % de la factura."),
    ("exito", "Primera orden: vendido a los 90 días", Decimal("80"), None, "% de la primera orden", 3, True,
     f"{WORD}: si se alcanza, se paga la factura completa."),
    ("umbral", "Máximo de piezas por caja", None, Decimal("30"), "piezas", None, True,
     f"{WORD}, condiciones logísticas."),
    ("umbral", "Máximo de kilos por caja", None, Decimal("25"), "kg", None, False,
     f"{WORD}, condiciones logísticas. Sin usar: la propuesta del portal todavía no pide el peso por caja."),
    ("rechazo", "Proveedor sin titularidad ni licencia de la marca", None, None, None, None, False,
     f"{CORPORATIVO}: solo se da de alta al titular o a quien tenga licencia o cesión. Compras decide si bloquea."),
]


def cargar(bd: Session) -> dict:
    hechos = {"politicas": 0, "politicas_ya": 0, "reglas": 0, "reglas_ya": 0}
    titulos = set(bd.scalars(select(ConocimientoPolitica.titulo)))
    for tema, titulo, texto, documento in POLITICAS:
        if titulo in titulos:
            hechos["politicas_ya"] += 1
            continue
        bd.add(ConocimientoPolitica(tema=tema, titulo=titulo, estado="borrador",
                                    contenido=f"{texto}\n\nFuente: {documento}. {FUENTE}."))
        hechos["politicas"] += 1
    criterios = set(bd.scalars(select(ConocimientoRegla.criterio)))
    for tipo, criterio, minimo, maximo, unidad, meses, activa, descripcion in REGLAS:
        if criterio in criterios:
            hechos["reglas_ya"] += 1
            continue
        bd.add(ConocimientoRegla(tipo=tipo, criterio=criterio, minimo=minimo, maximo=maximo, unidad=unidad,
                                 periodo_meses=meses if tipo == "exito" else None, descripcion=descripcion,
                                 activa=activa))
        hechos["reglas"] += 1
    registrar(bd, "conocimiento_carga_documentos", entidad="conocimiento_politica", detalle={"fuente": FUENTE, **hechos})
    return hechos


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--revisar", action="store_true", help="solo dice qué haría, no guarda nada")
    args = a.parse_args()
    with Session(motor()) as bd:
        hechos = cargar(bd)
        if args.revisar:
            bd.rollback()
        else:
            bd.commit()
    activas = sum(1 for r in REGLAS if r[6])
    print(("Revisión (no se guardó nada): " if args.revisar else "Listo: ")
          + f"{hechos['politicas']} políticas nuevas en borrador ({hechos['politicas_ya']} ya estaban), "
            f"{hechos['reglas']} reglas nuevas ({hechos['reglas_ya']} ya estaban; {activas} de las "
            f"{len(REGLAS)} entran activas).")


if __name__ == "__main__":
    main()
