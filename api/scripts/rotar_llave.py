"""Pone o cambia la llave de cifrado (CLAVE_CIFRADO) y vuelve a cifrar todo con ella.

Revisión de seguridad 2026-11-22, hallazgos A2 y A3. Qué se cifra con la llave:
- los secretos de Administración > Configuración (contraseñas SMTP, SMNBI, DataForSEO, llaves de API, …),
- las fórmulas de los expedientes de Innovación Vidanat y los archivos de fuentes «fórmula» (.cif),
- el texto de las fuentes de Innovación, el texto pegado, las descripciones de imágenes y las respuestas de la consulta.

Uso (dentro del contenedor de la API, así lee el mismo .env):
  python -m scripts.rotar_llave --nueva      genera una llave nueva para poner en CLAVE_CIFRADO (no cambia nada)
  python -m scripts.rotar_llave              revisa: cuenta qué se abre con cada llave y qué está sin cifrar (no cambia nada)
  python -m scripts.rotar_llave --aplicar    vuelve a cifrar todo con la llave vigente y comprueba que todo abre

Orden para pasar de la llave vieja (derivada de la contraseña de sa) a una propia:
  1. --nueva, poner la llave en CLAVE_CIFRADO del .env y reiniciar la API (lo viejo se sigue leyendo).
  2. --aplicar. Al final dice «Todo quedó con la llave vigente».
  3. Hasta entonces, cambiar la contraseña de sa.
Para cambiar CLAVE_CIFRADO por otra después: la actual va a CLAVE_CIFRADO_ANTERIOR, la nueva a CLAVE_CIFRADO, --aplicar y
se vacía CLAVE_CIFRADO_ANTERIOR.
"""
import argparse
import os
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from core import ajustes, cifrado
from core.bd import motor
from nucleo.archivos import _raiz

PREFIJO = "cif1:"
# (tabla, llave primaria, columna) de los textos protegidos de Innovación (modelos.TextoProtegido)
TEXTOS = [
    ("innovacion.fragmento", "fragmento_id", "texto"),
    ("innovacion.recurso_version", "version_id", "texto"),
    ("innovacion.recurso_archivo", "version_id, archivo_id", "descripcion"),
    ("innovacion.consulta", "consulta_id", "respuesta"),
    ("innovacion.consulta", "consulta_id", "citas"),
]


@dataclass
class Cuenta:
    nombre: str
    vigente: int = 0  # ya con la llave vigente
    anterior: int = 0  # se abre, pero con una llave anterior
    sin_cifrar: int = 0
    ilegibles: list[str] = field(default_factory=list)

    def linea(self) -> str:
        partes = [f"{self.vigente} con la llave vigente"]
        if self.anterior:
            partes.append(f"{self.anterior} con una llave anterior")
        if self.sin_cifrar:
            partes.append(f"{self.sin_cifrar} sin cifrar")
        if self.ilegibles:
            partes.append(f"{len(self.ilegibles)} NO SE ABREN ({', '.join(self.ilegibles[:5])})")
        return f"  {self.nombre}: " + ", ".join(partes)

    @property
    def pendientes(self) -> int:
        return self.anterior + self.sin_cifrar


def _estado(token: bytes, proposito: str) -> str:
    """vigente / anterior / ilegible"""
    try:
        cifrado.solo_vigente(proposito).decrypt(token)
        return "vigente"
    except cifrado.InvalidToken:
        pass
    try:
        cifrado.fernet(proposito).decrypt(token)
        return "anterior"
    except cifrado.InvalidToken:
        return "ilegible"


def _tabla_existe(bd: Session, tabla: str) -> bool:
    return bd.execute(text("SELECT OBJECT_ID(:t)"), {"t": tabla}).scalar() is not None


def secretos(bd: Session, aplicar: bool) -> Cuenta:
    c = Cuenta("Secretos de Configuración")
    claves = [a.clave for a in ajustes.CATALOGO if a.tipo == "secreto"]
    filas = bd.execute(text("SELECT clave, valor FROM nucleo.configuracion")).all()
    multi = cifrado.fernet(cifrado.AJUSTES)
    for clave, valor in filas:
        if clave not in claves or not valor:
            continue
        estado = _estado(valor.encode(), cifrado.AJUSTES)
        if estado == "ilegible":
            c.ilegibles.append(clave)
            continue
        if estado == "vigente":
            c.vigente += 1
            continue
        c.anterior += 1
        if aplicar:
            bd.execute(text("UPDATE nucleo.configuracion SET valor = :v WHERE clave = :c"),
                       {"v": multi.rotate(valor.encode()).decode(), "c": clave})
    return c


def formulas(bd: Session, aplicar: bool) -> Cuenta:
    c = Cuenta("Fórmulas de expedientes")
    if not _tabla_existe(bd, "innovacion.formula_version"):
        return c
    multi = cifrado.fernet(cifrado.INNOVACION)
    for fid, contenido in bd.execute(text("SELECT formula_id, contenido FROM innovacion.formula_version")).all():
        estado = _estado(bytes(contenido), cifrado.INNOVACION)
        if estado == "ilegible":
            c.ilegibles.append(f"fórmula {fid}")
        elif estado == "vigente":
            c.vigente += 1
        else:
            c.anterior += 1
            if aplicar:
                bd.execute(text("UPDATE innovacion.formula_version SET contenido = :v WHERE formula_id = :i"),
                           {"v": multi.rotate(bytes(contenido)), "i": fid})
    return c


def archivos(bd: Session, aplicar: bool) -> Cuenta:
    c = Cuenta("Archivos cifrados (.cif)")
    if not _tabla_existe(bd, "innovacion.recurso_archivo"):
        return c
    raiz = _raiz()
    multi = cifrado.fernet(cifrado.INNOVACION)
    filas = bd.execute(text("SELECT DISTINCT a.archivo_id, a.ruta_almacenamiento FROM innovacion.recurso_archivo ra "
                            "JOIN nucleo.archivo a ON a.archivo_id = ra.archivo_id WHERE ra.cifrado = 1")).all()
    for archivo_id, relativa in filas:
        ruta = (raiz / relativa).resolve()
        if raiz not in ruta.parents or not ruta.is_file():
            c.ilegibles.append(f"archivo {archivo_id} (no está en el almacén)")
            continue
        datos = ruta.read_bytes()
        estado = _estado(datos, cifrado.INNOVACION)
        if estado == "ilegible":
            c.ilegibles.append(f"archivo {archivo_id}")
        elif estado == "vigente":
            c.vigente += 1
        else:
            c.anterior += 1
            if aplicar:  # se escribe aparte y se cambia de un golpe: nunca queda un archivo a medias
                temporal = Path(f"{ruta}.rotando")
                temporal.write_bytes(multi.rotate(datos))
                os.replace(temporal, ruta)
    return c


def textos(bd: Session, aplicar: bool) -> Cuenta:
    c = Cuenta("Textos de Innovación (secciones, texto pegado, imágenes, consultas)")
    multi = cifrado.fernet(cifrado.INNOVACION)
    for tabla, llave, columna in TEXTOS:
        if not _tabla_existe(bd, tabla):
            continue
        columnas_llave = [k.strip() for k in llave.split(",")]
        filas = bd.execute(text(f"SELECT {llave}, {columna} FROM {tabla} WHERE {columna} IS NOT NULL")).all()
        for fila in filas:
            *ids, valor = fila
            donde = " AND ".join(f"{k} = :k{i}" for i, k in enumerate(columnas_llave))
            params = {f"k{i}": v for i, v in enumerate(ids)}
            if not valor.startswith(PREFIJO):
                c.sin_cifrar += 1
                nuevo = PREFIJO + multi.encrypt(valor.encode()).decode()
            else:
                token = valor[len(PREFIJO):].encode()
                estado = _estado(token, cifrado.INNOVACION)
                if estado == "ilegible":
                    c.ilegibles.append(f"{tabla}.{columna} {ids}")
                    continue
                if estado == "vigente":
                    c.vigente += 1
                    continue
                c.anterior += 1
                nuevo = PREFIJO + multi.rotate(token).decode()
            if aplicar:
                bd.execute(text(f"UPDATE {tabla} SET {columna} = :v WHERE {donde}"), {"v": nuevo, **params})
    return c


def revisar(bd: Session, aplicar: bool) -> list[Cuenta]:
    return [secretos(bd, aplicar), formulas(bd, aplicar), archivos(bd, aplicar), textos(bd, aplicar)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nueva", action="store_true", help="genera una llave nueva (no cambia nada)")
    p.add_argument("--aplicar", action="store_true", help="vuelve a cifrar todo con la llave vigente")
    a = p.parse_args(argv)
    if a.nueva:
        print(secrets.token_urlsafe(48))
        print("Ponla en CLAVE_CIFRADO del .env, reinicia la API y corre: python -m scripts.rotar_llave --aplicar")
        print("Guárdala también en un lugar seguro fuera del servidor (sin ella no se abren las fórmulas ni los respaldos).")
        return 0
    if a.aplicar and not cifrado.usa_llave_propia():
        print("ERROR: CLAVE_CIFRADO está vacía. Primero: python -m scripts.rotar_llave --nueva, ponla en el .env y "
              "reinicia la API.")
        return 2
    print("Llave vigente:", "CLAVE_CIFRADO" if cifrado.usa_llave_propia() else
          "derivada de la contraseña de sa (forma vieja; pon CLAVE_CIFRADO)")
    with Session(motor()) as bd:
        cuentas = revisar(bd, a.aplicar)
        print("\nAntes:" if a.aplicar else "\nEstado:")
        for c in cuentas:
            print(c.linea())
        if not a.aplicar:
            print("\nNo se cambió nada. Para volver a cifrar con la llave vigente: --aplicar")
            falta = cifrado.usa_llave_propia() and any(c.pendientes for c in cuentas)
            return 1 if falta or any(c.ilegibles for c in cuentas) else 0
        bd.commit()
        despues = revisar(bd, False)
    print("\nDespués:")
    for c in despues:
        print(c.linea())
    if any(c.pendientes for c in despues):
        print("\nERROR: algo quedó sin la llave vigente; no cambies la contraseña de sa y avisa.")
        return 1
    if any(c.ilegibles for c in despues):
        print("\nTodo lo que se podía abrir quedó con la llave vigente. Lo que NO SE ABRE ya estaba así antes "
              "(se cifró con una llave que ya no está); los secretos se vuelven a capturar en Configuración.")
        return 1
    print("\nTodo quedó con la llave vigente. Ya puedes cambiar la contraseña de sa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
