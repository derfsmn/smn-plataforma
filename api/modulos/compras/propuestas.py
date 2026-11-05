"""Reglas de las propuestas de productos nuevos (cuestionario v4 de Compras con los ajustes del plan del 2026-10-22).

Aquí vive todo lo que decide si una propuesta está completa y qué revisiones automáticas se le hacen:
- `Respuestas`: la forma del JSON que guarda el portal. Todo es texto mientras es borrador, para que el guardado
  automático nunca se rechace; los números y formatos se revisan en `faltantes`.
- `faltantes`: lo que impide enviarla, por sección y campo, con el mensaje que ve el proveedor.
- `revisar`: revisiones automáticas para Compras (código ya en el catálogo, ya propuesto, margen, RFC). No califican
  ni rechazan: solo avisan.
"""
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datos.modelos import Producto
from modulos.compras.modelos_propuestas import Propuesta, PropuestaAdjunto, PropuestaPresentacion
from nucleo.modelos import Archivo, OrganizacionExterna

Texto = Annotated[str, StringConstraints(max_length=1000)] | None
Lista = Annotated[list[Annotated[str, StringConstraints(max_length=60)]], Field(max_length=20)]

ESTADOS = {
    "borrador": "Borrador",
    "recibida": "Recibida",
    "en_revision": "En revisión",
    "devuelta": "Regresada al proveedor",
    "lista": "Lista para evaluar",
    "rechazada": "Rechazada",
}
# El proveedor edita mientras es suya; Compras la mueve después del envío
EDITABLES = {"borrador", "devuelta"}
# Desde cada estado, a cuáles puede pasar Compras
TRANSICIONES = {
    "recibida": {"en_revision", "devuelta", "lista", "rechazada"},
    "en_revision": {"devuelta", "lista", "rechazada"},
    "lista": {"en_revision", "devuelta", "rechazada"},
    "rechazada": {"en_revision"},
    "devuelta": {"en_revision"},
}

# Opciones del cuestionario v4. (valor, texto). En los desplegables de texto libre el valor es el mismo texto.
def _iguales(*textos: str) -> list[tuple[str, str]]:
    return [(t, t) for t in textos]


OPCIONES: dict[str, list[tuple[str, str]]] = {
    "si_no": [("si", "Sí"), ("no", "No")],
    "publico_objetivo": [("general", "Público general"), ("deportistas", "Deportistas"), ("adultos_mayores", "Adultos mayores"),
                         ("ninos", "Niños"), ("preferencias_alimentarias", "Preferencias alimentarias específicas"), ("otro", "Otro")],
    "pais_origen": _iguales("México", "Estados Unidos", "Canadá", "España", "Otro"),
    "diferenciador": _iguales("Formulación o ingredientes", "Precio", "Calidad o certificaciones", "Presentación", "Innovación",
                              "Reconocimiento de marca", "Otro"),
    "necesidad_atendida": _iguales("Necesidad no atendida", "Ampliar variedad", "Alternativa de precio", "Innovación",
                                   "Nuevo segmento", "Otra"),
    "forma": _iguales("Cápsula", "Tableta", "Capleta", "Líquido", "Polvo", "Gomita", "Pieza", "Sobres", "Otro"),
    "unidad_medida": _iguales("gramos", "kilos", "mililitros", "litros", "piezas", "paquetes"),
    "tasa_iva": [("0", "0 %"), ("8", "8 %"), ("16", "16 %")],
    "canal_actual": [("no_se_comercializa", "Aún no se comercializa"), ("fisico", "Solo tiendas físicas"),
                     ("digital", "Solo canales digitales"), ("ambos", "Ambos")],
    "comercios_actuales": [("walmart", "Walmart"), ("soriana", "Soriana"), ("chedraui", "Chedraui"),
                           ("san_pablo", "Farmacias San Pablo"), ("amazon", "Amazon"), ("mercado_libre", "Mercado Libre"),
                           ("iherb", "iHerb"), ("tienda_propia", "Tienda propia"), ("otro", "Otro")],
    "desempeno": [("unidades_mes", "Unidades vendidas al mes"), ("unidades_sucursal_mes", "Unidades por sucursal al mes"),
                  ("posicion_categoria", "Posición en categoría")],
    "manejo_especial": [("no_requiere", "No requiere"), ("temperatura", "Temperatura controlada"),
                        ("luz_humedad", "Protección de luz o humedad"), ("fragil", "Frágil"), ("otro", "Otro")],
    "apoyos": [("bonificacion", "Bonificación"), ("capacitacion", "Capacitación"), ("descuento_introduccion", "Descuento de introducción"),
               ("promociones", "Promociones"), ("muestras", "Muestras o degustaciones"), ("pop", "Material POP"),
               ("contenido_digital", "Contenido digital"), ("campanas", "Campañas"), ("inversion", "Inversión"), ("otro", "Otro")],
    "argumento_principal": _iguales("Demanda comprobada", "Diferenciación", "Precio competitivo", "Nueva necesidad o segmento",
                                    "Innovación"),
    "etiqueta_producto": _iguales("Frente", "Reverso", "Lateral", "Otra"),
    "etiqueta_etiquetado": _iguales("Tabla nutrimental", "Sellos u octágonos", "Certificación", "Ingredientes", "Otra"),
}

SECCIONES = [
    ("aviso", "Aviso de privacidad"),
    ("proveedor", "Datos del proveedor"),
    ("presentaciones", "Presentaciones y precio"),
    ("imagenes", "Imágenes del producto"),
    ("mercado", "Mercado y competencia"),
    ("logistica", "Entrega y vida útil"),
    ("lanzamiento", "Lanzamiento y respaldo"),
]

# tipo de adjunto: (sección, tipos de contenido aceptados, MB máximos, mínimo, máximo)
IMAGEN = {"image/jpeg", "image/png", "image/webp"}
PDF = {"application/pdf"}
OFIMATICA = PDF | {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/csv"}
ADJUNTOS = {
    "imagen_producto": ("imagenes", IMAGEN, 5, 2, 12),
    "imagen_etiquetado": ("imagenes", IMAGEN, 5, 2, 12),
    "carta_gs1": ("proveedor", IMAGEN | PDF, 5, 0, 1),
    "evidencia_registro_funcionamiento": ("proveedor", IMAGEN | PDF, 5, 0, 1),
    "evidencia_titulo_marca": ("proveedor", IMAGEN | PDF, 5, 0, 1),
    "ficha_tecnica": ("lanzamiento", PDF, 10, 1, 1),
    "documento_adicional": ("lanzamiento", OFIMATICA, 10, 0, 10),
}
# Documentos de la empresa: pasan solos a la siguiente propuesta del mismo proveedor
ADJUNTOS_DE_EMPRESA = {"carta_gs1", "evidencia_registro_funcionamiento", "evidencia_titulo_marca"}
MAX_PRESENTACIONES = 10
MAX_COMPETIDORES = 3


# ---------------------------------------------------------------- forma del JSON

class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Aviso(_Base):
    acepta_aviso_privacidad: bool = False
    declara_veracidad: bool = False


class DatosProveedor(_Base):
    marca: Texto = None
    razon_social: Texto = None
    nombre_comercial: Texto = None
    rfc: Texto = None
    es_proveedor_smn: Texto = None
    publico_objetivo: Lista = []
    publico_objetivo_otro: Texto = None
    inscrito_gs1: Texto = None
    cuenta_registro_marca: Texto = None
    contacto_nombre: Texto = None
    contacto_cargo: Texto = None
    contacto_correo: Texto = None
    contacto_telefono: Texto = None
    contacto_alterno_nombre: Texto = None
    contacto_alterno_telefono: Texto = None
    contacto_alterno_correo: Texto = None


class General(_Base):
    fabricante: Texto = None
    pais_origen: Texto = None
    pais_origen_otro: Texto = None
    diferenciador: Texto = None
    diferenciador_otro: Texto = None
    necesidad_atendida: Texto = None
    necesidad_atendida_otro: Texto = None
    departamento: Texto = None


class Presentacion(_Base):
    codigo_barras: Texto = None
    registro_sanitario: Texto = None
    forma: Texto = None
    forma_otro: Texto = None
    ingrediente_principal: Texto = None
    descripcion: Texto = None
    contenido_neto: Texto = None
    unidad_medida: Texto = None
    piezas_caja_master: Texto = None
    costo_neto_sin_iva: Texto = None
    pvp_sugerido: Texto = None
    margen_propuesto_pct: Texto = None
    tasa_iva: Texto = None
    tasa_ieps: Texto = None


class Desempeno(_Base):
    tipo: Texto = None
    cifra: Texto = None
    canal: Texto = None
    periodo: Texto = None
    fuente: Texto = None


class Competidor(_Base):
    producto: Texto = None
    presentacion: Texto = None
    precio: Texto = None
    comercio: Texto = None


class Mercado(_Base):
    canal_actual: Texto = None
    comercios_actuales: Lista = []
    comercios_actuales_otro: Texto = None
    sin_datos_desempeno: bool = False
    desempeno: Annotated[list[Desempeno], Field(max_length=5)] = []
    sin_comparables: bool = False
    competidores: Annotated[list[Competidor], Field(max_length=MAX_COMPETIDORES)] = []
    similares_en_smn: Texto = None
    similares_cuales: Texto = None


class Logistica(_Base):
    manejo_especial: Lista = []
    manejo_especial_otro: Texto = None
    vida_util_total_dias: Texto = None
    vida_util_minima_no_aplica: bool = False
    vida_util_minima_dias: Texto = None


class Apoyo(_Base):
    tipo: Texto = None
    detalle: Texto = None
    inicio: Texto = None
    fin: Texto = None


class Lanzamiento(_Base):
    apoyos: Annotated[list[Apoyo], Field(max_length=12)] = []
    apoyos_otro: Texto = None
    argumento_principal: Texto = None
    sustento: Texto = None


class Respuestas(_Base):
    aviso: Aviso = Aviso()
    proveedor: DatosProveedor = DatosProveedor()
    general: General = General()
    presentaciones: Annotated[list[Presentacion], Field(max_length=MAX_PRESENTACIONES)] = [Presentacion()]
    mercado: Mercado = Mercado()
    logistica: Logistica = Logistica()
    lanzamiento: Lanzamiento = Lanzamiento()


# ---------------------------------------------------------------- formatos

RFC = re.compile(r"^[A-ZÑ&]{3,4}(\d{6})[A-Z0-9]{3}$")
CORREO = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def limpio(v: str | None) -> str:
    return (v or "").strip()


def _espacios(v: str | None) -> str | None:
    if v is None:
        return None
    t = re.sub(r"[ \t]+", " ", v).strip()
    return t or None


def normalizar(r: Respuestas) -> Respuestas:
    """Deja cada dato en su forma canónica antes de guardarlo como enviado (el portal ya pone máscaras;
    esto cubre lo que llegue de otro lado): sin espacios de más, RFC y registro en mayúsculas, correos en
    minúsculas, teléfonos y códigos solo con dígitos, números sin separadores de miles ni símbolos."""
    def limpiar(m: BaseModel) -> None:
        for nombre, valor in list(m.__dict__.items()):
            if isinstance(valor, str):
                setattr(m, nombre, _espacios(valor))
            elif isinstance(valor, BaseModel):
                limpiar(valor)
            elif isinstance(valor, list):
                for x in valor:
                    if isinstance(x, BaseModel):
                        limpiar(x)
                setattr(m, nombre, [_espacios(x) if isinstance(x, str) else x for x in valor])

    def solo(v: str | None, patron: str) -> str | None:
        return re.sub(patron, "", v) or None if v else None

    def cifra(v: str | None) -> str | None:
        return solo(v, r"[\s,$%]") if v else None

    limpiar(r)
    p = r.proveedor
    p.rfc = solo(p.rfc.upper(), r"[^A-ZÑ&0-9]") if p.rfc else None
    p.contacto_correo = p.contacto_correo.lower().replace(" ", "") if p.contacto_correo else None
    p.contacto_alterno_correo = p.contacto_alterno_correo.lower().replace(" ", "") if p.contacto_alterno_correo else None
    p.contacto_telefono = solo(p.contacto_telefono, r"\D")
    p.contacto_alterno_telefono = solo(p.contacto_alterno_telefono, r"\D")
    for x in r.presentaciones:
        x.codigo_barras = solo(x.codigo_barras, r"\D")
        x.registro_sanitario = x.registro_sanitario.upper() if x.registro_sanitario else None
        for campo in ("contenido_neto", "piezas_caja_master", "costo_neto_sin_iva", "pvp_sugerido", "margen_propuesto_pct", "tasa_ieps"):
            setattr(x, campo, cifra(getattr(x, campo)))
    for d in r.mercado.desempeno:
        d.cifra = cifra(d.cifra)
    for c in r.mercado.competidores:
        c.precio = cifra(c.precio)
    r.logistica.vida_util_total_dias = cifra(r.logistica.vida_util_total_dias)
    r.logistica.vida_util_minima_dias = cifra(r.logistica.vida_util_minima_dias)
    return r


def rfc_valido(v: str | None) -> bool:
    """Persona moral (12) o física (13), con fecha AAMMDD posible en medio."""
    m = RFC.match(limpio(v).upper())
    if not m:
        return False
    mes, dia = int(m.group(1)[2:4]), int(m.group(1)[4:6])
    return 1 <= mes <= 12 and 1 <= dia <= 31


def correo_valido(v: str | None) -> bool:
    return bool(CORREO.match(limpio(v)))


def telefono_valido(v: str | None) -> bool:
    return len(re.sub(r"\D", "", v or "")) == 10


def codigo_valido(v: str | None) -> bool:
    """EAN-8, UPC-12, EAN-13 o GTIN-14 con su dígito verificador (misma regla que el cuestionario v4)."""
    v = limpio(v)
    if not re.fullmatch(r"\d{8}|\d{12}|\d{13}|\d{14}", v):
        return False
    digitos = [int(c) for c in v]
    verificador = digitos.pop()
    suma = sum(n * (3 if i % 2 == 0 else 1) for i, n in enumerate(reversed(digitos)))
    return (10 - suma % 10) % 10 == verificador


def numero(v: str | None) -> Decimal | None:
    try:
        n = Decimal(limpio(v).replace(",", ""))
    except InvalidOperation:
        return None
    return n if n.is_finite() else None


def entero(v: str | None) -> int | None:
    n = numero(v)
    return int(n) if n is not None and n == n.to_integral_value() else None


def fecha(v: str | None) -> date | None:
    try:
        return date.fromisoformat(limpio(v))
    except ValueError:
        return None


def margen(p: Presentacion) -> Decimal | None:
    """Margen sobre el precio sin impuestos si SMN vende al precio sugerido. El IEPS se cobra sobre el precio y el IVA
    sobre precio más IEPS, así que el precio sin impuestos es pvp / (1 + IVA) / (1 + IEPS)."""
    costo, pvp, iva, ieps = numero(p.costo_neto_sin_iva), numero(p.pvp_sugerido), numero(p.tasa_iva), numero(p.tasa_ieps)
    if not costo or not pvp or iva is None or ieps is None or pvp <= 0:
        return None
    base = pvp / (1 + iva / 100) / (1 + ieps / 100)
    return ((base - costo) / base * 100).quantize(Decimal("0.01"))


# ---------------------------------------------------------------- qué falta para enviar

@dataclass
class Falta:
    seccion: str
    campo: str
    mensaje: str


def faltantes(r: Respuestas, adjuntos: list[tuple[str, str | None]], compras: bool = False) -> list[Falta]:
    """Todo lo que impide enviar. `adjuntos` son (tipo, etiqueta) de los archivos ya agregados.
    `compras`: la capturó Compras por el proveedor (Diego, 2026-11-03: «de momento no tengo los contactos»). Entonces el
    aviso de privacidad, el RFC y los contactos no son obligatorios; si se escriben, se revisa que estén bien."""
    f: list[Falta] = []

    def requerido(seccion: str, campo: str, valor, mensaje: str = "Campo obligatorio.") -> bool:
        if not (limpio(valor) if isinstance(valor, str | None) else valor):
            f.append(Falta(seccion, campo, mensaje))
            return False
        return True

    def opcion(seccion: str, campo: str, valor: str | None, catalogo: str, otro: str | None = None, otro_campo: str = "",
               mensaje: str = "Selecciona una opción.") -> None:
        validos = {v for v, _ in OPCIONES[catalogo]}
        if limpio(valor) not in validos:
            f.append(Falta(seccion, campo, mensaje))
        elif limpio(valor).lower() in {"otro", "otra"}:
            requerido(seccion, otro_campo or f"{campo}_otro", otro, "Especifica la otra opción.")

    def varias(seccion: str, campo: str, valores: list[str], catalogo: str, otro: str | None,
               mensaje: str = "Selecciona al menos una opción.") -> None:
        validos = {v for v, _ in OPCIONES[catalogo]}
        if not valores or any(v not in validos for v in valores):
            f.append(Falta(seccion, campo, mensaje))
        elif "otro" in valores:
            requerido(seccion, f"{campo}_otro", otro, "Especifica la otra opción.")

    def cuantos(tipo: str, etiqueta: str | None = None) -> int:
        return sum(1 for t, e in adjuntos if t == tipo and (etiqueta is None or e == etiqueta))

    # 1. Aviso de privacidad y declaración
    if not compras and not r.aviso.acepta_aviso_privacidad:
        f.append(Falta("aviso", "aviso.acepta_aviso_privacidad", "Acepta el aviso de privacidad."))
    if not compras and not r.aviso.declara_veracidad:
        f.append(Falta("aviso", "aviso.declara_veracidad", "Declara que la información es verídica."))

    # 2. Datos del proveedor
    p, s = r.proveedor, "proveedor"
    requerido(s, "proveedor.marca", p.marca)
    requerido(s, "proveedor.razon_social", p.razon_social)
    if (limpio(p.rfc) if compras else requerido(s, "proveedor.rfc", p.rfc)) and not rfc_valido(p.rfc):
        f.append(Falta(s, "proveedor.rfc", "RFC no válido (12 o 13 caracteres)."))
    opcion(s, "proveedor.es_proveedor_smn", p.es_proveedor_smn, "si_no")
    varias(s, "proveedor.publico_objetivo", p.publico_objetivo, "publico_objetivo", p.publico_objetivo_otro)
    opcion(s, "proveedor.inscrito_gs1", p.inscrito_gs1, "si_no")
    if p.inscrito_gs1 == "si" and not cuantos("carta_gs1"):
        f.append(Falta(s, "adjunto.carta_gs1", "Adjunta la carta de incorporación al GS1."))
    opcion(s, "proveedor.cuenta_registro_marca", p.cuenta_registro_marca, "si_no")
    if p.cuenta_registro_marca == "si":
        if not cuantos("evidencia_registro_funcionamiento"):
            f.append(Falta(s, "adjunto.evidencia_registro_funcionamiento", "Adjunta el registro de funcionamiento."))
        if not cuantos("evidencia_titulo_marca"):
            f.append(Falta(s, "adjunto.evidencia_titulo_marca", "Adjunta el título de marca."))
    if compras:  # sin contactos todavía: solo se revisa lo que sí se escribió
        for campo, valor, valido, mensaje in (
                ("contacto_correo", p.contacto_correo, correo_valido, "Correo no válido."),
                ("contacto_telefono", p.contacto_telefono, telefono_valido, "Teléfono de 10 dígitos."),
                ("contacto_alterno_telefono", p.contacto_alterno_telefono, telefono_valido, "Ingresa un teléfono de 10 dígitos."),
                ("contacto_alterno_correo", p.contacto_alterno_correo, correo_valido, "Ingresa un correo válido.")):
            if limpio(valor) and not valido(valor):
                f.append(Falta(s, f"proveedor.{campo}", mensaje))
    else:
        requerido(s, "proveedor.contacto_nombre", p.contacto_nombre)
        requerido(s, "proveedor.contacto_cargo", p.contacto_cargo)
        if not correo_valido(p.contacto_correo):
            f.append(Falta(s, "proveedor.contacto_correo", "Correo no válido."))
        if not telefono_valido(p.contacto_telefono):
            f.append(Falta(s, "proveedor.contacto_telefono", "Teléfono de 10 dígitos."))
        requerido(s, "proveedor.contacto_alterno_nombre", p.contacto_alterno_nombre)
        if not telefono_valido(p.contacto_alterno_telefono):
            f.append(Falta(s, "proveedor.contacto_alterno_telefono", "Ingresa un teléfono de 10 dígitos."))
        if not correo_valido(p.contacto_alterno_correo):
            f.append(Falta(s, "proveedor.contacto_alterno_correo", "Ingresa un correo válido."))

    # 3. Presentaciones y precio
    g, s = r.general, "presentaciones"
    requerido(s, "general.fabricante", g.fabricante)
    opcion(s, "general.pais_origen", g.pais_origen, "pais_origen", g.pais_origen_otro, mensaje="Selecciona un país.")
    opcion(s, "general.diferenciador", g.diferenciador, "diferenciador", g.diferenciador_otro)
    opcion(s, "general.necesidad_atendida", g.necesidad_atendida, "necesidad_atendida", g.necesidad_atendida_otro)
    requerido(s, "general.departamento", g.departamento, "Elige el departamento.")
    if not r.presentaciones:
        f.append(Falta(s, "presentaciones", "Agrega al menos una presentación."))
    codigos: set[str] = set()
    for i, pr in enumerate(r.presentaciones):
        c = f"presentaciones.{i}."
        if requerido(s, c + "codigo_barras", pr.codigo_barras, "Escribe el código de barras."):
            if not codigo_valido(pr.codigo_barras):
                f.append(Falta(s, c + "codigo_barras", "Código de barras no válido: revisa los dígitos (8, 12, 13 o 14)."))
            elif limpio(pr.codigo_barras) in codigos:
                f.append(Falta(s, c + "codigo_barras", "Este código ya está en otra presentación de esta propuesta."))
            codigos.add(limpio(pr.codigo_barras))
        requerido(s, c + "registro_sanitario", pr.registro_sanitario, "Ingresa el número de registro o aviso sanitario.")
        opcion(s, c + "forma", pr.forma, "forma", pr.forma_otro, mensaje="Selecciona una forma.")
        requerido(s, c + "ingrediente_principal", pr.ingrediente_principal)
        if requerido(s, c + "descripcion", pr.descripcion) and len(limpio(pr.descripcion)) > 180:
            f.append(Falta(s, c + "descripcion", "Máximo 180 caracteres."))
        if not (n := numero(pr.contenido_neto)) or n <= 0:
            f.append(Falta(s, c + "contenido_neto", "Obligatorio."))
        opcion(s, c + "unidad_medida", pr.unidad_medida, "unidad_medida", mensaje="Obligatorio.")
        if not (n := entero(pr.piezas_caja_master)) or n < 1:
            f.append(Falta(s, c + "piezas_caja_master", "Obligatorio: número entero de piezas."))
        for campo in ("costo_neto_sin_iva", "pvp_sugerido"):
            if not (n := numero(getattr(pr, campo))) or n <= 0:
                f.append(Falta(s, c + campo, "Obligatorio."))
        if limpio(pr.margen_propuesto_pct) and not (0 <= (numero(pr.margen_propuesto_pct) or Decimal(-1)) <= 100):
            f.append(Falta(s, c + "margen_propuesto_pct", "Entre 0 y 100."))
        opcion(s, c + "tasa_iva", pr.tasa_iva, "tasa_iva", mensaje="Obligatorio.")
        if (n := numero(pr.tasa_ieps)) is None or n < 0:
            f.append(Falta(s, c + "tasa_ieps", "Obligatorio (0 si no aplica)."))

    # 4. Imágenes
    s = "imagenes"
    if not 2 <= cuantos("imagen_producto") <= 12:
        f.append(Falta(s, "adjunto.imagen_producto", "Sube de 2 a 12 fotos del producto."))
    elif not (cuantos("imagen_producto", "Frente") and cuantos("imagen_producto", "Reverso")):
        f.append(Falta(s, "adjunto.imagen_producto", "Marca una foto como Frente y otra como Reverso."))
    if not 2 <= cuantos("imagen_etiquetado") <= 12:
        f.append(Falta(s, "adjunto.imagen_etiquetado", "Sube de 2 a 12 fotos del etiquetado."))

    # 5. Mercado y competencia
    m, s = r.mercado, "mercado"
    opcion(s, "mercado.canal_actual", m.canal_actual, "canal_actual")
    if m.canal_actual and m.canal_actual != "no_se_comercializa":
        varias(s, "mercado.comercios_actuales", m.comercios_actuales, "comercios_actuales", m.comercios_actuales_otro,
               "Selecciona al menos un comercio.")
    tipos_desempeno = {v for v, _ in OPCIONES["desempeno"]}
    for i, d in enumerate(m.desempeno):
        if d.tipo not in tipos_desempeno:
            f.append(Falta(s, f"mercado.desempeno.{i}", "Tipo de dato no válido."))
        elif limpio(d.cifra) and (numero(d.cifra) is None or numero(d.cifra) < 0):
            f.append(Falta(s, f"mercado.desempeno.{i}.cifra", "Escribe la cifra como número."))
    if not m.sin_comparables:
        for i, comp in enumerate(m.competidores):
            requerido(s, f"mercado.competidores.{i}.producto", comp.producto, "Escribe la marca y el producto.")
            if limpio(comp.precio) and (numero(comp.precio) is None or numero(comp.precio) < 0):
                f.append(Falta(s, f"mercado.competidores.{i}.precio", "Escribe el precio como número."))
    opcion(s, "mercado.similares_en_smn", m.similares_en_smn, "si_no")

    # 6. Entrega y vida útil (ajuste del plan: días como número; la mínima no pasa de la total)
    lg, s = r.logistica, "logistica"
    varias(s, "logistica.manejo_especial", lg.manejo_especial, "manejo_especial", lg.manejo_especial_otro)
    total = entero(lg.vida_util_total_dias)
    if not total or total <= 0:
        f.append(Falta(s, "logistica.vida_util_total_dias", "Escribe la vida útil total en días."))
    if not lg.vida_util_minima_no_aplica:
        minima = entero(lg.vida_util_minima_dias)
        if not minima or minima <= 0:
            f.append(Falta(s, "logistica.vida_util_minima_dias", "Escribe los días o marca «No aplica»."))
        elif total and minima > total:
            f.append(Falta(s, "logistica.vida_util_minima_dias", "No puede ser mayor que la vida útil total."))

    # 7. Lanzamiento y respaldo
    la, s = r.lanzamiento, "lanzamiento"
    tipos_apoyo = {v for v, _ in OPCIONES["apoyos"]}
    if not la.apoyos or any(a.tipo not in tipos_apoyo for a in la.apoyos):
        f.append(Falta(s, "lanzamiento.apoyos", "Selecciona al menos una opción."))
    else:
        if any(a.tipo == "otro" for a in la.apoyos):
            requerido(s, "lanzamiento.apoyos_otro", la.apoyos_otro, "Especifica la otra opción.")
        for i, a in enumerate(la.apoyos):
            inicio, fin = fecha(a.inicio), fecha(a.fin)
            if (limpio(a.inicio) and not inicio) or (limpio(a.fin) and not fin):
                f.append(Falta(s, f"lanzamiento.apoyos.{i}", "Revisa las fechas."))
            elif inicio and fin and fin < inicio:
                f.append(Falta(s, f"lanzamiento.apoyos.{i}", "La fecha de fin es antes del inicio."))
    opcion(s, "lanzamiento.argumento_principal", la.argumento_principal, "argumento_principal", mensaje="Obligatorio.")
    if requerido(s, "lanzamiento.sustento", la.sustento, "Obligatorio.") and len(limpio(la.sustento)) > 220:
        f.append(Falta(s, "lanzamiento.sustento", "Máximo 220 caracteres."))
    if not cuantos("ficha_tecnica"):
        f.append(Falta(s, "adjunto.ficha_tecnica", "Adjunta la ficha técnica en PDF."))
    return f


# ---------------------------------------------------------------- revisiones automáticas para Compras

@dataclass
class Revision:
    nivel: str  # alerta / info
    texto: str


def revisar(bd: Session, propuesta: Propuesta, r: Respuestas) -> list[Revision]:
    """Avisos para Compras. Ninguno detiene la propuesta: los decide una persona."""
    revisiones: list[Revision] = []
    org = bd.get(OrganizacionExterna, propuesta.organizacion_id)
    org_rfc = limpio(org.rfc).upper() if org else ""
    rfc = limpio(r.proveedor.rfc).upper()
    if org_rfc and rfc and rfc != org_rfc:
        revisiones.append(Revision("alerta", f"El RFC capturado ({rfc}) no es el de la empresa invitada ({org_rfc})."))
    for i, pr in enumerate(r.presentaciones, start=1):
        nombre = f"Presentación {i}" if len(r.presentaciones) > 1 else "El producto"
        codigo = limpio(pr.codigo_barras)
        if codigo:
            existente = bd.scalar(select(Producto).where(Producto.codigo_barras == codigo, Producto.activo))
            if existente:
                revisiones.append(Revision("alerta", f"{nombre}: el código {codigo} ya está en el catálogo SMN "
                                                     f"(SKU {existente.sku}, {existente.descripcion})."))
            otra = bd.scalar(
                select(Propuesta.folio).join(PropuestaPresentacion, PropuestaPresentacion.propuesta_id == Propuesta.propuesta_id)
                .where(PropuestaPresentacion.codigo_barras == codigo, Propuesta.propuesta_id != propuesta.propuesta_id,
                       Propuesta.folio.is_not(None), Propuesta.estado != "rechazada"))
            if otra:
                revisiones.append(Revision("alerta", f"{nombre}: el código {codigo} ya viene en la propuesta {otra}."))
        if (m := margen(pr)) is not None:
            texto = f"{nombre}: margen de {m} % sobre el precio sin impuestos si se vende a {pr.pvp_sugerido} MXN"
            if limpio(pr.margen_propuesto_pct):
                texto += f" (el proveedor propone {pr.margen_propuesto_pct} %)"
            revisiones.append(Revision("alerta" if m <= 0 else "info",
                                       texto + (". El costo es igual o mayor al precio." if m <= 0 else ".")))
    return revisiones


def resumen_producto(r: Respuestas) -> tuple[str | None, str | None]:
    """(marca, nombre corto) para la bandeja: marca + descripción de la primera presentación."""
    marca = limpio(r.proveedor.marca) or None
    desc = limpio(r.presentaciones[0].descripcion) if r.presentaciones else ""
    nombre = " ".join(x for x in (marca, desc) if x)[:300] or None
    return marca, nombre


def filas_presentacion(bd: Session, r: Respuestas) -> list[PropuestaPresentacion]:
    """Las presentaciones como filas: lo que lee el radar de productos."""
    filas = []
    for i, pr in enumerate(r.presentaciones):
        codigo = limpio(pr.codigo_barras)[:14] or None
        filas.append(PropuestaPresentacion(
            orden=i + 1, codigo_barras=codigo, descripcion=limpio(pr.descripcion)[:180] or None,
            forma=(limpio(pr.forma_otro) if limpio(pr.forma).lower() == "otro" else limpio(pr.forma))[:60] or None,
            contenido_neto=numero(pr.contenido_neto), unidad_medida=limpio(pr.unidad_medida)[:20] or None,
            costo_sin_iva=numero(pr.costo_neto_sin_iva), pvp_sugerido=numero(pr.pvp_sugerido),
            tasa_iva=numero(pr.tasa_iva), tasa_ieps=numero(pr.tasa_ieps), margen_calculado=margen(pr),
            ya_en_catalogo=bool(codigo and codigo_valido(codigo) and bd.scalar(
                select(Producto.producto_id).where(Producto.codigo_barras == codigo, Producto.activo))),
        ))
    return filas


def adjunto_aceptado(tipo: str, archivo: Archivo) -> str | None:
    """Motivo por el que ese archivo no sirve para ese tipo de adjunto, o None si sirve."""
    if tipo not in ADJUNTOS:
        return "Ese tipo de documento no existe."
    _, tipos, mb, _, _ = ADJUNTOS[tipo]
    if archivo.tipo_contenido not in tipos:
        return {"imagen_producto": "Las fotos deben ser JPG, PNG o WEBP.", "imagen_etiquetado": "Las fotos deben ser JPG, PNG o WEBP.",
                "ficha_tecnica": "La ficha técnica debe ser PDF."}.get(tipo, "Ese formato no se acepta para este documento.")
    if archivo.tamano_bytes > mb * 1024 * 1024:
        return f"El archivo pasa de {mb} MB."
    return None


def maximo_adjuntos(tipo: str) -> int:
    return ADJUNTOS[tipo][4]


def adjuntos_de(p: Propuesta) -> list[tuple[str, str | None]]:
    return [(a.tipo, a.etiqueta) for a in p.adjuntos]


def nuevo_folio(bd: Session, anio: int) -> str:
    prefijo = f"PN-{anio}-"
    ultimo = bd.scalar(select(func.max(Propuesta.folio)).where(Propuesta.folio.like(f"{prefijo}%")))
    n = int(ultimo.rsplit("-", 1)[1]) + 1 if ultimo else 1
    return f"{prefijo}{n:04d}"


def adjunto_de_empresa(a: PropuestaAdjunto) -> bool:
    return a.tipo in ADJUNTOS_DE_EMPRESA
