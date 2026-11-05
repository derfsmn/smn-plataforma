"""Ajustes que el administrador cambia desde la pantalla de Configuración.

Lo que se guarda en nucleo.configuracion se sobrepone a lo del .env sin reiniciar. Si se borra
un ajuste en la pantalla, vuelve el valor del .env. Los secretos (contraseña SMTP, llave de la API)
se guardan cifrados (Fernet) con una llave derivada de CLAVE_CIFRADO; si no existe, de MSSQL_SA_PASSWORD.
La base de datos, el entorno y los orígenes permitidos solo se cambian en el .env.
"""
import base64
import hashlib
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import Configuracion, configuracion


@dataclass(frozen=True)
class Ajuste:
    clave: str  # mismo nombre que el atributo de Configuracion
    grupo: str
    etiqueta: str
    tipo: str  # texto / url / entero / decimal / booleano / secreto / opcion / dias
    ayuda: str = ""
    minimo: float | None = None
    maximo: float | None = None
    opciones: tuple[tuple[str, str], ...] = ()  # (valor, texto) para tipo opcion


GRUPOS = {
    "general": "General",
    "correo": "Correo de salida",
    "archivos": "Archivos",
    "ia": "Inteligencia artificial",
    "radar": "Radar de tendencias (Compras)",
    "catalogo": "Catálogo de productos (Centro de datos)",
    "precios": "Radar de precios (Compras)",
    "kiosco": "Kiosco Digital (Tiendas)",
    "etl": "ETL de ventas (SMNBI)",
    "productos": "Radar de productos (Compras)",
}

CATALOGO = [
    Ajuste("web_url", "general", "Dirección de la web", "url",
           "Con ella se arman las ligas de los correos. Ej. https://td.supernaturista.mx"),
    Ajuste("sesion_horas", "general", "Duración de la sesión (horas)", "entero",
           "Después de este tiempo hay que volver a entrar. Aplica a sesiones nuevas.", 1, 24),
    Ajuste("smtp_servidor", "correo", "Servidor SMTP", "texto", "Vacío = no se envían correos. En local: correo (Mailpit)."),
    Ajuste("smtp_puerto", "correo", "Puerto", "entero", "Normalmente 587 con TLS; 1025 en Mailpit.", 1, 65535),
    Ajuste("smtp_usuario", "correo", "Usuario", "texto", "Vacío si el servidor no pide usuario."),
    Ajuste("smtp_contrasena", "correo", "Contraseña", "secreto"),
    Ajuste("smtp_tls", "correo", "Usar TLS (STARTTLS)", "booleano"),
    Ajuste("smtp_remitente", "correo", "Remitente", "texto", "Ej. SMN Transformación digital <no-responder@supernaturista.mx>"),
    Ajuste("archivos_mb_maximo", "archivos", "Tamaño máximo por archivo (MB)", "entero", "", 1, 100),
    Ajuste("ollama_url", "ia", "Dirección de Ollama", "url", "Donde corre Ollama, p. ej. http://host.docker.internal:11434"),
    Ajuste("ollama_modelo", "ia", "Modelo de Ollama", "texto", "Nombre de un modelo descargado. Vacío = Ollama apagado."),
    Ajuste("ia_proveedor_externo", "ia", "Proveedor de la API externa", "opcion",
           "Al cambiarlo, revisa el modelo y los precios.", opciones=(("anthropic", "Anthropic"), ("openai", "OpenAI"))),
    Ajuste("anthropic_api_key", "ia", "Llave de Anthropic", "secreto",
           "Solo se usa si el proveedor es Anthropic. Sin llave la API externa queda apagada."),
    Ajuste("openai_api_key", "ia", "Llave de OpenAI", "secreto",
           "Solo se usa si el proveedor es OpenAI. Sin llave la API externa queda apagada."),
    Ajuste("openai_admin_key", "ia", "Llave de administrador de OpenAI (costo real)", "secreto",
           "Opcional. Solo lee lo que OpenAI cobró por día; con ella el tope mensual usa el costo real. "
           "Se crea en platform.openai.com > Settings > Organization > Admin keys."),
    Ajuste("openai_proyecto_id", "ia", "Proyecto de OpenAI de la plataforma", "texto",
           "Opcional. Empieza con proj_. Así solo se cuenta el gasto de ese proyecto y no otros usos de la cuenta."),
    Ajuste("ia_modelo_externo", "ia", "Modelo de la API externa", "texto",
           "Del proveedor elegido. Ej. claude-opus-5-5 (Anthropic) o gpt-5.4-mini (OpenAI)."),
    Ajuste("ia_precio_entrada_usd_mtok", "ia", "Precio de entrada (USD por millón de tokens)", "decimal",
           "Confírmalo en la página de precios del proveedor.", 0, 1000),
    Ajuste("ia_precio_salida_usd_mtok", "ia", "Precio de salida (USD por millón de tokens)", "decimal", "", 0, 1000),
    Ajuste("ia_precio_busqueda_usd", "ia", "Precio por búsqueda web (USD)", "decimal",
           "Lo que cobra el proveedor por cada búsqueda en internet que hace la IA.", 0, 10),
    Ajuste("ia_tipo_cambio_mxn", "ia", "Tipo de cambio (pesos por dólar)", "decimal",
           "Lo captura quien administra; sin él la API externa queda apagada.", 1, 100),
    Ajuste("radar_activo", "radar", "Correr el radar automáticamente", "booleano",
           "Apagado, el radar solo corre con el botón Correr ahora."),
    Ajuste("radar_frecuencia", "radar", "¿Qué días corre?", "opcion",
           "Cada N días se cuenta desde la última corrida que terminó bien.",
           opciones=(("diario", "Todos los días"), ("dias", "Días de la semana que elija"), ("cada_n", "Cada N días"))),
    Ajuste("radar_hora", "radar", "Hora en que corre (0 a 23)", "entero",
           "Hora local. Si la plataforma estaba apagada a esa hora, corre en cuanto vuelve.", 0, 23),
    Ajuste("radar_dias_semana", "radar", "Días de la semana", "dias",
           "Solo aplica si eligió «Días de la semana que elija»."),
    Ajuste("radar_cada_dias", "radar", "Cada cuántos días", "entero",
           "Solo aplica si eligió «Cada N días».", 2, 30),
    Ajuste("radar_zona_horaria", "radar", "Zona horaria", "texto", "Ej. America/Mexico_City"),
    Ajuste("radar_ventana_dias", "radar", "Antigüedad máxima de una nota (días)", "entero",
           "Las notas más viejas se guardan, pero no salen en el reporte.", 1, 60),
    Ajuste("radar_max_hallazgos", "radar", "Hallazgos por reporte", "entero", "", 1, 10),
    Ajuste("radar_busquedas_por_dia", "radar", "Búsquedas abiertas por día", "entero",
           "Una por tema activo, hasta este número. Cada una cuesta (ver precio por búsqueda). 0 = sin búsqueda abierta.", 0, 30),
    Ajuste("catalogo_api_url", "catalogo", "Dirección del API de artículos (smnapps)", "url",
           "La dirección completa de la lista de artículos que da Sistemas. Vacío = carga apagada."),
    Ajuste("catalogo_api_usuario", "catalogo", "Usuario del API de artículos", "texto"),
    Ajuste("catalogo_api_contrasena", "catalogo", "Contraseña del API de artículos", "secreto"),
    Ajuste("tienda_url", "catalogo", "Dirección de la tienda en línea", "url",
           "De aquí salen código de barras, imagen y precio publicado. Solo lee páginas públicas. Vacío = no se carga."),
    Ajuste("catalogo_activo", "catalogo", "Cargar el catálogo automáticamente", "booleano",
           "Carga primero el API de artículos y después la tienda en línea. Apagado, solo se carga con los botones."),
    Ajuste("catalogo_hora", "catalogo", "Hora en que se carga (0 a 23)", "entero",
           "Hora local. Si la plataforma estaba apagada a esa hora, carga en cuanto vuelve.", 0, 23),
    Ajuste("catalogo_dias_semana", "catalogo", "Días en que se carga", "dias"),
    Ajuste("catalogo_zona_horaria", "catalogo", "Zona horaria", "texto", "Ej. America/Mexico_City"),
    Ajuste("smnbi_servidor", "etl", "Servidor de SMNBI", "texto",
           "Nombre o IP del servidor SQL de Sistemas. Vacío = solo carga con archivo."),
    Ajuste("smnbi_puerto", "etl", "Puerto", "entero", "Normalmente 1433.", 1, 65535),
    Ajuste("smnbi_base", "etl", "Base de datos", "texto", "SMNBI"),
    Ajuste("smnbi_usuario", "etl", "Usuario de solo lectura", "texto", "El que dé Sistemas para la plataforma."),
    Ajuste("smnbi_contrasena", "etl", "Contraseña", "secreto"),
    Ajuste("etl_primer_mes", "etl", "Primer mes que se trae (AAAA-MM)", "texto",
           "La primera carga trae desde este mes hasta el mes pasado."),
    Ajuste("etl_meses_refresco", "etl", "Meses que repite cada carga", "entero",
           "Las cargas siguientes vuelven a traer el mes en curso y los anteriores hasta este número, por si hubo correcciones.", 1, 12),
    Ajuste("etl_factura_electronica", "etl", "Contar «Factura Electronica» como venta", "booleano",
           "Prendido: las facturas son venta de mayoreo y canales (Almacén México, Corporativos, Sanborns, Mayoreo Guadalajara), no repiten las Notas de tienda."),
    Ajuste("etl_activo", "etl", "Correr el ETL automáticamente", "booleano",
           "Apagado, solo corre con el botón «Correr ahora»."),
    Ajuste("etl_hora", "etl", "Hora en que corre (0 a 23)", "entero", "Hora local (zona del catálogo).", 0, 23),
    Ajuste("etl_dias_semana", "etl", "Días en que corre", "dias"),
    Ajuste("elevenlabs_api_key", "kiosco", "Llave de ElevenLabs", "secreto",
           "Con permiso para leer el agente y crear conversaciones. Sin llave, Naturi queda en vista previa."),
    Ajuste("kiosco_agente_id", "kiosco", "Agente de Naturi en ElevenLabs", "texto",
           "Identificador del agente (agent_…)."),
    Ajuste("kiosco_token_herramienta", "kiosco", "Token de la herramienta de productos", "secreto",
           "El mismo que se pone en ElevenLabs en la herramienta buscar_productos_smn (Authorization: Bearer …)."),
    Ajuste("kiosco_limite_usuario_hora", "kiosco", "Conversaciones por persona por hora", "entero", "", 1, 1000),
    Ajuste("kiosco_limite_hora", "kiosco", "Conversaciones en total por hora", "entero", "", 1, 10000),
    Ajuste("dataforseo_usuario", "precios", "Usuario de DataForSEO", "texto",
           "El login de la cuenta (app.dataforseo.com > API Dashboard). Sin usuario y contraseña el radar no corre."),
    Ajuste("dataforseo_contrasena", "precios", "Contraseña del API de DataForSEO", "secreto",
           "La contraseña del API (no la de entrar a la página)."),
    Ajuste("precios_tope_mensual_usd", "precios", "Tope de gasto al mes (USD)", "decimal",
           "Antes de cada envío se revisa que no se pase. 0 = el radar no corre.", 0, 10000),
    Ajuste("precios_tope_corrida_usd", "precios", "Tope de gasto por corrida (USD)", "decimal",
           "Si una corrida llega a este monto, los productos que falten quedan para la siguiente.", 0, 1000),
    Ajuste("precios_tarifa_usd", "precios", "Tarifa de DataForSEO (USD por bloque de resultados)", "decimal",
           "Con ella se calcula el máximo antes de enviar. 0.001 en prioridad normal (revisado el 2026-10-06 en dataforseo.com/pricing).", 0, 1),
    Ajuste("precios_activo", "precios", "Correr el radar automáticamente", "booleano",
           "Apagado, solo corre con el botón Correr ahora."),
    Ajuste("precios_frecuencia", "precios", "¿Qué días corre?", "opcion",
           "Cada N días se cuenta desde la última corrida que terminó.",
           opciones=(("diario", "Todos los días"), ("dias", "Días de la semana que elija"), ("cada_n", "Cada N días"))),
    Ajuste("precios_hora", "precios", "Hora en que corre (0 a 23)", "entero",
           "Hora local. Si la plataforma estaba apagada a esa hora, corre en cuanto vuelve.", 0, 23),
    Ajuste("precios_dias_semana", "precios", "Días de la semana", "dias",
           "Solo aplica si eligió «Días de la semana que elija»."),
    Ajuste("precios_cada_dias", "precios", "Cada cuántos días", "entero", "Solo aplica si eligió «Cada N días».", 2, 60),
    Ajuste("precios_zona_horaria", "precios", "Zona horaria", "texto", "Ej. America/Mexico_City"),
    Ajuste("precios_alerta_pct", "precios", "Semáforo: rojo si estamos más caros que el mercado por más de (%)", "decimal",
           "Compara nuestro precio lista con impuestos contra la mediana de la competencia. Verde: igual o más barato. "
           "Amarillo: más caro hasta este %. Rojo: más caro que este %, y se avisa en la campana.", 0, 100),
    Ajuste("precios_ia_siempre", "precios", "La IA elige el producto entre los resultados de Google", "booleano",
           "Encendido: la IA revisa siempre lo que regresa Google y elige; las reglas solo quitan otra marca, otra presentación y "
           "paquetes. Apagado: eligen las reglas y la IA solo revisa lo dudoso. Si la IA no contesta, deciden las reglas."),
    Ajuste("precios_comparar_imagenes", "precios", "Comparar fotos cuando Google trae varias variantes", "booleano",
           "Encendido: si Google trae varias variantes de la marca (Premier, Clásico, Plus...) y nuestra descripción no dice cuál "
           "es la nuestra, Ollama compara la foto de nuestro producto con las de Google. Necesita un modelo con visión en la "
           "tarea «compras.precios_imagenes» (Administración → IA), por ejemplo qwen3-vl."),
    Ajuste("precios_buscar_siempre", "precios", "Buscar en Google Shopping en cada corrida", "booleano",
           "Encendido: cada corrida vuelve a buscar cada producto y cada resultado que la IA marca como el mismo producto cuenta "
           "como un precio (tienda, publicación y precio), además de los vendedores. Cuesta una búsqueda más por producto en "
           "cada corrida. Apagado: se reutiliza la coincidencia y solo se piden vendedores."),
    Ajuste("precios_umbral", "precios", "Calificación mínima para aceptar una coincidencia (0 a 100)", "entero",
           "Más alto = menos coincidencias, pero más seguras. Lo dudoso lo revisa la IA; si no queda segura, se deja fuera.", 50, 100),
    Ajuste("precios_max_publicaciones", "precios", "Publicaciones del mismo producto que se consultan", "entero",
           "Google suele tener el mismo producto en varias publicaciones, cada una con sus tiendas. Se piden los vendedores "
           "de hasta este número por producto (cada una es una consulta a DataForSEO). 1 = solo la publicación elegida, como Radar Precios.", 1, 10),
    Ajuste("precios_profundidad", "precios", "Resultados de Google Shopping por búsqueda", "entero",
           "Más resultados cuestan más (se cobra por cada 40).", 10, 120),
    Ajuste("precios_ubicacion", "precios", "Ubicación de la búsqueda", "texto", "Como la nombra DataForSEO. Ej. Mexico"),
    Ajuste("precios_idioma", "precios", "Idioma de la búsqueda", "texto", "Como lo nombra DataForSEO. Ej. Spanish"),
    Ajuste("precios_dominios_propios", "precios", "Dominios propios", "texto",
           "Separados por coma. Los precios de estos sitios no cuentan como competencia."),
    Ajuste("precios_tiendas_clave", "precios", "Tiendas clave", "texto",
           "Separadas por coma. Su precio se muestra aparte en cada producto y se mide en cuántos productos aparecen."),
    Ajuste("precios_tiendas_directas", "precios", "Tiendas que se buscan en su propio sitio", "texto",
           "Separadas por coma; vacío = ninguna. Hoy se puede: Walmart, Chedraui, San Pablo, Soriana. Cada corrida busca cada "
           "producto en su página (sin costo de DataForSEO) y su precio cuenta como un vendedor más."),
    Ajuste("radar_productos_margen_minimo", "productos", "Margen mínimo provisional (%)", "decimal",
           "Se usa solo mientras la Base de conocimiento de Compras no tenga una regla de margen. Provisional: "
           "no es una política de Compras.", 0, 100),
    Ajuste("radar_productos_buscar_mercado", "productos", "Buscar el producto nuevo en internet", "booleano",
           "Al evaluar, lo busca en Google Shopping y en el sitio de las tiendas clave, igual que el radar de precios. "
           "Cuesta unos centavos de dólar de DataForSEO por evaluación y cuenta para el tope del mes. La búsqueda se "
           "reusa 7 días."),
    Ajuste("oportunidades_busquedas", "productos", "Subcategorías a buscar en la competencia", "entero",
           "Al «Buscar oportunidades» con la competencia, cuántas de las subcategorías que más venden se buscan en Google "
           "Shopping. Cada una cuesta una búsqueda de DataForSEO y cuenta para el tope del mes.", 1, 300),
]
POR_CLAVE = {a.clave: a for a in CATALOGO}

# Valores del .env (o por omisión) antes de aplicar lo guardado en la base
_ORIGINALES: dict[str, object] = {}
_DESDE_ENV: set[str] = set()


def _originales() -> dict[str, object]:
    if not _ORIGINALES:
        cfg = configuracion()
        _ORIGINALES.update({a.clave: getattr(cfg, a.clave) for a in CATALOGO})
        _DESDE_ENV.update(a.clave for a in CATALOGO if a.clave in cfg.model_fields_set)
    return _ORIGINALES


def _fernet() -> Fernet:
    cfg = configuracion()
    semilla = cfg.clave_cifrado or cfg.mssql_sa_password
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(f"smn-td-ajustes:{semilla}".encode()).digest()))


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(texto: str) -> str | None:
    try:
        return _fernet().decrypt(texto.encode()).decode()
    except InvalidToken:
        return None  # la llave de cifrado cambió: el secreto hay que capturarlo de nuevo


def convertir(a: Ajuste, valor):
    """Valida y convierte lo que llega de la pantalla. Lanza ValueError con mensaje para la persona."""
    if a.tipo == "booleano":
        if not isinstance(valor, bool):
            raise ValueError(f"{a.etiqueta}: elige sí o no.")
        return valor
    texto = str(valor).strip()
    if a.tipo in ("entero", "decimal"):
        try:
            numero = int(texto) if a.tipo == "entero" else float(texto)
        except ValueError:
            raise ValueError(f"{a.etiqueta}: escribe un número.") from None
        if (a.minimo is not None and numero < a.minimo) or (a.maximo is not None and numero > a.maximo):
            raise ValueError(f"{a.etiqueta}: debe estar entre {a.minimo:g} y {a.maximo:g}.")
        return numero
    if a.tipo == "opcion":
        if texto not in {v for v, _ in a.opciones}:
            raise ValueError(f"{a.etiqueta}: elige una de las opciones.")
        return texto
    if a.tipo == "dias":
        partes = {p.strip() for p in texto.split(",") if p.strip()}
        if not partes or not partes <= {str(i) for i in range(1, 8)}:
            raise ValueError(f"{a.etiqueta}: elige al menos un día.")
        return ",".join(sorted(partes))
    if a.tipo == "url":
        if not texto.startswith(("http://", "https://")):
            raise ValueError(f"{a.etiqueta}: debe empezar con http:// o https://")
        return texto.rstrip("/")
    if len(texto) > 500:
        raise ValueError(f"{a.etiqueta}: es demasiado largo.")
    if a.clave == "etl_primer_mes":
        if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", texto):
            raise ValueError(f"{a.etiqueta}: escribe año y mes, p. ej. 2026-01.")
    if a.clave.endswith("zona_horaria"):
        try:
            ZoneInfo(texto)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"{a.etiqueta}: no es una zona horaria válida (ej. America/Mexico_City).") from None
    return texto


def _de_texto(a: Ajuste, guardado: str):
    if a.tipo == "secreto":
        return descifrar(guardado)
    if a.tipo == "booleano":
        return guardado == "1"
    if a.tipo == "entero":
        return int(guardado)
    if a.tipo == "decimal":
        return float(guardado)
    return guardado


def a_texto(a: Ajuste, valor) -> str:
    if a.tipo == "secreto":
        return cifrar(valor)
    if a.tipo == "booleano":
        return "1" if valor else "0"
    return str(valor)


def guardados(bd: Session) -> dict[str, str]:
    from nucleo.modelos import ConfiguracionAjuste

    return {c.clave: c.valor for c in bd.scalars(select(ConfiguracionAjuste)).all() if c.clave in POR_CLAVE}


def aplicar(bd: Session) -> None:
    """Pone en la configuración en memoria lo guardado en la base; lo demás vuelve al .env."""
    cfg: Configuracion = configuracion()
    originales = _originales()
    en_base = guardados(bd)
    for a in CATALOGO:
        valor = _de_texto(a, en_base[a.clave]) if a.clave in en_base else None
        setattr(cfg, a.clave, originales[a.clave] if valor is None else valor)


def origen(clave: str, en_base: dict[str, str]) -> str:
    _originales()
    if clave in en_base:
        return "pantalla"
    return "archivo" if clave in _DESDE_ENV else "omision"
