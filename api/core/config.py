"""Configuración de la API, leída de variables de entorno (.env)."""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_entorno: str = "desarrollo"
    api_origenes_permitidos: str = "http://localhost:3000"
    # Dirección pública de la web; se usa para armar las ligas de invitación y de contraseña
    web_url: str = "http://localhost:3000"
    sesion_horas: int = 12
    # Para cifrar los secretos guardados desde la pantalla de Configuración. Vacío = se deriva de MSSQL_SA_PASSWORD.
    clave_cifrado: str = ""

    bd_servidor: str = "localhost"
    bd_puerto: int = 1433
    bd_nombre: str = "smn_td"
    bd_usuario: str = "sa"
    mssql_sa_password: str = ""
    # Contraseña de BD_USUARIO cuando no es sa (en el servidor la API usa su propio usuario). Vacía = MSSQL_SA_PASSWORD.
    bd_contrasena: str = ""
    # Versión publicada (la pone publicar.sh en el servidor); en tu equipo dice «local»
    plataforma_version: str = "local"
    bd_driver: str = "ODBC Driver 18 for SQL Server"

    # Correo saliente (SMTP). Vacío = no se envían correos; la liga se muestra en pantalla y en la consola.
    # En desarrollo se usa Mailpit (buzón de prueba en docker-compose): nada sale a internet.
    smtp_servidor: str = ""
    smtp_puerto: int = 1025
    smtp_usuario: str = ""
    smtp_contrasena: str = ""
    smtp_tls: bool = False
    smtp_remitente: str = "SMN Transformación digital <no-responder@smn.local>"

    # Archivos subidos (carpeta local o volumen de Docker)
    archivos_ruta: str = "./datos/archivos"
    archivos_mb_maximo: int = 10

    # Puerta de IA. Ollama (local) no tiene costo; la API externa solo se usa si hay llave,
    # tipo de cambio y un tope mensual de plataforma capturado en /admin/ia.
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_modelo: str = ""
    # Proveedor de la API externa: anthropic u openai. Cada uno con su llave.
    ia_proveedor_externo: str = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_admin_key: str = ""  # solo para leer el costo real (API de costos de la organización)
    openai_proyecto_id: str = ""  # si se da, solo cuenta el gasto de ese proyecto
    ia_modelo_externo: str = "claude-opus-5-5"
    # Precios en USD por millón de tokens del modelo externo. Verifícalos en la página de precios del proveedor.
    ia_precio_entrada_usd_mtok: float = 4.0
    ia_precio_salida_usd_mtok: float = 20.0
    # Precio en USD de cada búsqueda web que hace la IA (herramienta de búsqueda del proveedor)
    ia_precio_busqueda_usd: float = 0.01
    # Pesos por dólar para convertir el costo. Sin este dato la API externa queda apagada.
    ia_tipo_cambio_mxn: float | None = None

    # Tareas programadas dentro de la API (radar diario). Se apaga solo en pruebas.
    programador_activo: bool = True
    # Radar de tendencias (Compras): hora local en que corre solo cada día
    radar_activo: bool = True
    radar_hora: int = 8
    radar_frecuencia: str = "diario"  # diario / dias / cada_n
    radar_dias_semana: str = "1,2,3,4,5,6,7"  # 1 = lunes … 7 = domingo
    radar_cada_dias: int = 3
    radar_zona_horaria: str = "America/Mexico_City"
    radar_ventana_dias: int = 7
    radar_max_hallazgos: int = 5
    radar_busquedas_por_dia: int = 6

    # Catálogo de productos (Centro de datos): API de artículos de SMN (smnapps). Usuario y contraseña
    # se capturan en Configuración; sin dirección o sin usuario la carga queda apagada.
    catalogo_api_url: str = ""
    catalogo_api_usuario: str = ""
    catalogo_api_contrasena: str = ""
    # Tienda en línea (Shopify): solo páginas públicas, sin llaves. Vacío = no se carga.
    tienda_url: str = "https://supernaturista.com"
    catalogo_activo: bool = True
    catalogo_hora: int = 5
    catalogo_dias_semana: str = "1,2,3,4,5,6,7"
    catalogo_zona_horaria: str = "America/Mexico_City"

    # ETL de ventas desde SMNBI (base de Sistemas). Servidor, usuario y contraseña de solo lectura se capturan
    # en Configuración; sin ellos solo funciona la carga con archivo CSV.
    smnbi_servidor: str = ""
    smnbi_puerto: int = 1433
    smnbi_base: str = "SMNBI"
    smnbi_usuario: str = ""
    smnbi_contrasena: str = ""
    etl_primer_mes: str = "2026-01"  # desde dónde trae la primera carga
    etl_meses_refresco: int = 2  # las cargas siguientes repiten el mes en curso y los anteriores
    # Las facturas salen de almacenes de mayoreo (ALM-MEXICO, CORP, SANBORNS, GDL 1), no de tiendas: no repiten Notas
    # (consulta 13, 2026-10-26). Son ~22 % de la venta; quedan separadas por su almacén.
    etl_factura_electronica: bool = True
    etl_activo: bool = False
    etl_hora: int = 6
    etl_dias_semana: str = "1"

    # Kiosco Digital (TD002): Naturi, agente de ElevenLabs. La llave y el token se capturan en Configuración.
    elevenlabs_api_key: str = ""
    kiosco_agente_id: str = "agent_4501m55r5q41egxt9z919eh1bvmr"  # el agente de SMN_Direccion (identificador público)
    kiosco_token_herramienta: str = ""  # lo manda ElevenLabs al buscar productos; vacío = la búsqueda no responde
    kiosco_limite_usuario_hora: int = 30
    kiosco_limite_hora: int = 120

    # Radar de precios (Compras): Google Shopping con DataForSEO. Usuario y contraseña se capturan en
    # Configuración; sin ellos no corre. La dirección del API solo cambia en el .env (pruebas).
    dataforseo_url: str = "https://api.dataforseo.com"
    dataforseo_usuario: str = ""
    dataforseo_contrasena: str = ""
    precios_activo: bool = True
    precios_frecuencia: str = "dias"  # diario / dias / cada_n
    precios_hora: int = 7
    precios_dias_semana: str = "1"  # 1 = lunes … 7 = domingo
    precios_cada_dias: int = 7
    precios_zona_horaria: str = "America/Mexico_City"
    precios_ubicacion: str = "Mexico"
    precios_idioma: str = "Spanish"
    precios_profundidad: int = 20
    precios_max_publicaciones: int = 5  # publicaciones del mismo producto de las que se piden vendedores; 1 = solo la elegida
    precios_umbral: int = 85
    precios_buscar_siempre: bool = True  # cada corrida vuelve a buscar y cada resultado de Google que es el mismo producto cuenta como precio (Diego, 2026-10-19)
    precios_comparar_imagenes: bool = True  # variantes dudosas: la IA compara fotos (idea de Diego, 2026-10-20)
    precios_ia_siempre: bool = True  # la IA elige entre los resultados de Google (decisión de Diego, 2026-10-19)
    precios_tarifa_usd: float = 0.001  # por bloque de resultados, prioridad normal (DataForSEO, 2026-10-06)
    precios_tope_mensual_usd: float = 0.0  # 0 = no corre
    precios_tope_corrida_usd: float = 2.0
    precios_alerta_pct: float = 5.0
    precios_dominios_propios: str = "supernaturista.com"
    precios_tiendas_clave: str = "Walmart, Chedraui, San Pablo, Soriana"  # se muestran aparte (Diego, 2026-10-20)
    precios_tiendas_directas: str = "Walmart, Chedraui, San Pablo, Soriana"  # se buscan en su propio sitio (Diego, 2026-10-20)

    # Radar de productos (Compras): margen mínimo provisional mientras Compras no captura su regla de margen.
    radar_productos_margen_minimo: float = 30.0
    # Buscar el producto nuevo en Google Shopping (DataForSEO, con el tope del radar de precios) y en las tiendas clave
    radar_productos_buscar_mercado: bool = True
    # «Buscar oportunidades»: cuántas subcategorías se buscan en Google Shopping para ver lo que vende la competencia
    oportunidades_busquedas: int = 60

    @field_validator("ia_tipo_cambio_mxn", mode="before")
    @classmethod
    def _vacio_es_nulo(cls, v):
        return None if v in ("", None) else v

    @property
    def es_desarrollo(self) -> bool:
        return self.api_entorno == "desarrollo"

    @property
    def origenes(self) -> list[str]:
        return [o.strip() for o in self.api_origenes_permitidos.split(",") if o.strip()]

    def url_bd(self, base: str | None = None) -> str:
        """Cadena de conexión SQLAlchemy para SQL Server vía pyodbc."""
        from urllib.parse import quote_plus

        odbc = (
            f"DRIVER={{{self.bd_driver}}};SERVER={self.bd_servidor},{self.bd_puerto};"
            f"DATABASE={base or self.bd_nombre};UID={self.bd_usuario};"
            f"PWD={self.bd_contrasena or self.mssql_sa_password};TrustServerCertificate=yes;Encrypt=yes"
        )
        return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}"


@lru_cache
def configuracion() -> Configuracion:
    return Configuracion()
