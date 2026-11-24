"""Compara dos etiquetas Vidanat. Python 3.10+, sin paquetes adicionales."""

import argparse
import base64
import json
import math
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PRODUCTOS = (
    {
        "sku": "55527",
        "nombre": "Glicinato de Magnesio",
        "foto": "https://supernaturista.com/cdn/shop/files/55527B.jpg?v=1776424549&width=2000",
        "transcripcion": {
            "tabletas_por_porcion": 2,
            "compuestos_mg_por_porcion": [500],
            "magnesio_elemental_mg_por_porcion": 70,
        },
    },
    {
        "sku": "55541",
        "nombre": "8 Magnesios",
        "foto": "https://supernaturista.com/cdn/shop/files/55541B.jpg?v=1777597443&width=2000",
        "transcripcion": {
            "tabletas_por_porcion": 2,
            "compuestos_mg_por_porcion": [50] * 8,
            "magnesio_elemental_mg_por_porcion": None,
        },
    },
)

CAMPOS = {
    "tabletas_por_porcion": {"type": ["integer", "null"], "minimum": 1},
    "compuestos_mg_por_porcion": {
        "type": "array",
        "items": {"type": "number", "minimum": 0},
    },
    "magnesio_elemental_mg_por_porcion": {
        "type": ["number", "null"],
        "minimum": 0,
    },
}

LIMITE_INICIAL = 2048
LIMITE_REINTENTO = 4096


def recortar_tabla(imagen):
    """Aísla la tabla de estas dos fotos si Pillow está disponible."""
    try:
        from PIL import Image
    except ImportError:
        return imagen
    with Image.open(BytesIO(imagen)) as foto:
        ancho, alto = foto.size
        bordes = (
            round(ancho * 0.29), round(alto * 0.39),
            round(ancho * 0.69), round(alto * 0.71),
        )
        salida = BytesIO()
        foto.crop(bordes).save(salida, format="PNG")
        return salida.getvalue()



def consultar_ollama(peticion):
    solicitud = Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(peticion).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(solicitud, timeout=180) as respuesta:
            cuerpo = respuesta.read()
    except HTTPError as error:
        detalle = error.read(1024).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Ollama devolvió HTTP {error.code}: {detalle}") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"No se pudo consultar Ollama local: {error}") from error

    try:
        respuesta = json.loads(cuerpo)
    except (ValueError, UnicodeError) as error:
        raise RuntimeError(
            "El servidor local devolvió un cuerpo vacío o inválido en /api/chat."
        ) from error
    if not isinstance(respuesta, dict):
        raise RuntimeError("Respuesta inesperada de /api/chat. Se esperaba un objeto JSON.")
    if respuesta.get("error"):
        raise RuntimeError(f"Ollama devolvió un error: {respuesta['error']}")
    return respuesta


def validar_extraccion(respuesta):
    mensaje = respuesta.get("message") or {}
    contenido = mensaje.get("content") if isinstance(mensaje, dict) else None
    motivo = respuesta.get("done_reason") or "sin motivo informado"
    tokens = respuesta.get("eval_count", "desconocidos")
    diagnostico = f"motivo={motivo}, tokens generados={tokens}"
    if not isinstance(contenido, str) or not contenido.strip():
        detalle = " La respuesta solo contiene razonamiento." if (
            isinstance(mensaje, dict) and mensaje.get("thinking")
        ) else ""
        raise ValueError(f"Ollama devolvió message.content vacío ({diagnostico}).{detalle}")

    contenido = contenido.strip()
    lineas = contenido.splitlines()
    if lineas[0].lower() in ("```json", "```") and lineas[-1] == "```":
        contenido = "\n".join(lineas[1:-1])
    try:
        datos = json.loads(contenido)
    except ValueError as error:
        raise ValueError(f"Qwen devolvió JSON inválido o incompleto ({diagnostico}).") from error

    if not isinstance(datos, dict) or datos.keys() != CAMPOS.keys():
        raise ValueError("El JSON de Qwen no tiene los tres campos esperados.")
    tabletas = datos["tabletas_por_porcion"]
    compuestos = datos["compuestos_mg_por_porcion"]
    elemental = datos["magnesio_elemental_mg_por_porcion"]
    if tabletas is not None and (type(tabletas) is not int or tabletas < 1):
        raise ValueError("El número de tabletas debe ser un entero positivo o null.")
    if not isinstance(compuestos, list):
        raise ValueError("El campo de compuestos debe ser una lista.")
    cantidades = compuestos if elemental is None else [*compuestos, elemental]
    if any(type(valor) not in (int, float) or not math.isfinite(valor) or valor < 0
           for valor in cantidades):
        raise ValueError("Las cantidades en mg deben ser números finitos y no negativos.")
    return datos


def leer_con_ollama(foto, modelo):
    """Descarga la foto pública y la entrega exclusivamente a Ollama local."""
    try:
        with urlopen(foto, timeout=20) as respuesta:
            imagen = respuesta.read()
    except OSError as error:
        raise RuntimeError(f"No se pudo descargar la foto de la etiqueta: {error}") from error
    peticion = {
        "model": modelo,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": LIMITE_INICIAL},
        "format": {
            "type": "object",
            "properties": CAMPOS,
            "required": list(CAMPOS),
            "additionalProperties": False,
        },
        "messages": [{
            "role": "user",
            "content": (
                "Devuelve solo un objeto JSON, sin explicaciones. "
                "Claves: tabletas_por_porcion, compuestos_mg_por_porcion, "
                "magnesio_elemental_mg_por_porcion. "
                "Transcribe exclusivamente la columna Porción de la etiqueta. "
                "Extrae el número de tabletas y los mg de cada compuesto de magnesio "
                "mostrado en la tabla, en orden. Excluye otros nutrimentos y "
                "la fila de equivalente a magnesio de la lista de compuestos. "
                "Registra el magnesio elemental solo si existe una fila explícita "
                "como 'Equivalente a Magnesio'. Nunca lo calcules. Usa null si "
                "el valor escalar no aparece o es ilegible y [] si no puedes "
                "leer los compuestos. No uses la columna de 100 g."
            ),
            "images": [base64.b64encode(imagen).decode("ascii")],
        }],
    }
    primera_respuesta = consultar_ollama(peticion)
    try:
        return validar_extraccion(primera_respuesta)
    except ValueError as primer_error:
        # Un decodificador con formato forzado puede agotar el presupuesto
        # de salida. El reintento conserva la validación en Python.
        del peticion["format"]
        peticion["options"]["num_predict"] = LIMITE_REINTENTO
        try:
            tabla = recortar_tabla(imagen)
        except OSError:
            tabla = imagen
        peticion["messages"][0]["images"] = [base64.b64encode(tabla).decode("ascii")]
        try:
            return validar_extraccion(consultar_ollama(peticion))
        except (ValueError, RuntimeError) as segundo_error:
            raise RuntimeError(
                f"Extracción fallida con {modelo}. "
                f"Primer intento: {primer_error} Segundo intento: {segundo_error}"
            ) from segundo_error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama", metavar="MODELO", help="Ejemplo: qwen3-vl:8b")
    args = parser.parse_args()

    print("Fuente de los datos:", "Ollama (leer y verificar)" if args.ollama
          else "transcripción de las fotos públicas")
    coincidencias = []
    for producto in PRODUCTOS:
        esperado = producto["transcripcion"]
        try:
            datos = leer_con_ollama(producto["foto"], args.ollama) if args.ollama else esperado
        except RuntimeError as error:
            raise RuntimeError(f"SKU {producto['sku']}: {error}") from error
        coinciden = datos == esperado
        coincidencias.append(coinciden)

        print(f"\n{producto['sku']} | {producto['nombre']}")
        print(f"  Tabletas por porción: {datos['tabletas_por_porcion']}")
        compuestos = datos["compuestos_mg_por_porcion"]
        total = f"{sum(compuestos):g} mg" if compuestos else "sin dato"
        print(f"  Suma de los compuestos leídos por porción: {total}")
        elemental = datos["magnesio_elemental_mg_por_porcion"]
        if args.ollama and not coinciden:
            print("  Resultado: revisar extracción. Difiere de la transcripción.")
            print("  Extraído:", json.dumps(datos, ensure_ascii=False))
        elif elemental is None:
            print("  Magnesio elemental: no declarado en la foto.")
        else:
            print(f"  Magnesio elemental declarado: {elemental:g} mg por porción.")

    if all(coincidencias):
        print("\nComparación pendiente: falta el magnesio elemental del SKU 55541.")
        return 0
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        raise SystemExit(f"No se pudo completar la prueba: {error}") from None
