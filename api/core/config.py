"""Configuración de la API, leída de variables de entorno (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_entorno: str = "desarrollo"
    api_origenes_permitidos: str = "http://localhost:3000"

    bd_servidor: str = "localhost"
    bd_puerto: int = 1433
    bd_nombre: str = "smn_td"
    bd_usuario: str = "sa"
    mssql_sa_password: str = ""
    bd_driver: str = "ODBC Driver 18 for SQL Server"

    @property
    def origenes(self) -> list[str]:
        return [o.strip() for o in self.api_origenes_permitidos.split(",") if o.strip()]

    def url_bd(self, base: str | None = None) -> str:
        """Cadena de conexión SQLAlchemy para SQL Server vía pyodbc."""
        from urllib.parse import quote_plus

        odbc = (
            f"DRIVER={{{self.bd_driver}}};SERVER={self.bd_servidor},{self.bd_puerto};"
            f"DATABASE={base or self.bd_nombre};UID={self.bd_usuario};"
            f"PWD={self.mssql_sa_password};TrustServerCertificate=yes;Encrypt=yes"
        )
        return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}"


@lru_cache
def configuracion() -> Configuracion:
    return Configuracion()
