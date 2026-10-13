"""Crea la base de datos si no existe. Se ejecuta antes de las migraciones."""
import sys
import time

from sqlalchemy import create_engine, text

from core.config import configuracion


def main() -> None:
    cfg = configuracion()
    motor = create_engine(cfg.url_bd("master"), isolation_level="AUTOCOMMIT")
    for intento in range(30):
        try:
            with motor.connect() as conexion:
                existe = conexion.execute(
                    text("SELECT 1 FROM sys.databases WHERE name = :n"), {"n": cfg.bd_nombre}
                ).scalar()
                if not existe:
                    conexion.execute(text(f"CREATE DATABASE [{cfg.bd_nombre}]"))
                    print(f"Base de datos {cfg.bd_nombre} creada.")
                else:
                    print(f"Base de datos {cfg.bd_nombre} ya existe.")
                return
        except Exception as error:  # SQL Server tarda en arrancar
            print(f"Esperando a SQL Server ({intento + 1}/30): {error.__class__.__name__}")
            time.sleep(3)
    sys.exit("No se pudo conectar a SQL Server.")


if __name__ == "__main__":
    main()
