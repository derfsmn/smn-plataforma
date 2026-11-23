"""Llaves de cifrado de la plataforma (Fernet), en un solo lugar.

- La llave vigente sale de CLAVE_CIFRADO. Si está vacía, de MSSQL_SA_PASSWORD (la forma vieja).
- Para leer, además se prueban las llaves anteriores: CLAVE_CIFRADO_ANTERIOR y, si ya hay CLAVE_CIFRADO, la derivada de
  MSSQL_SA_PASSWORD. Así poner o cambiar CLAVE_CIFRADO no deja nada sin abrir; scripts/rotar_llave.py vuelve a cifrar todo
  con la vigente, y después ya se puede cambiar la contraseña de sa (Revisión de seguridad 2026-11-22, hallazgo A2).
- Cada uso tiene su propia llave (`proposito`): lo de Configuración no se abre con la de Innovación y viceversa.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from core.config import configuracion

AJUSTES = "smn-td-ajustes"
INNOVACION = "smn-td-innovacion"
__all__ = ["AJUSTES", "INNOVACION", "InvalidToken", "fernet", "usa_llave_propia"]


def _llave(proposito: str, semilla: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(f"{proposito}:{semilla}".encode()).digest()))


def _semillas() -> list[str]:
    cfg = configuracion()
    vigente = cfg.clave_cifrado or cfg.mssql_sa_password
    otras = [cfg.clave_cifrado_anterior] + ([cfg.mssql_sa_password] if cfg.clave_cifrado else [])
    semillas = [vigente]
    for s in otras:
        if s and s not in semillas:
            semillas.append(s)
    return semillas


def fernet(proposito: str) -> MultiFernet:
    """Cifra con la llave vigente y lee con la vigente o cualquiera de las anteriores."""
    return MultiFernet([_llave(proposito, s) for s in _semillas()])


def solo_vigente(proposito: str) -> Fernet:
    return _llave(proposito, _semillas()[0])


def usa_llave_propia() -> bool:
    return bool(configuracion().clave_cifrado)
