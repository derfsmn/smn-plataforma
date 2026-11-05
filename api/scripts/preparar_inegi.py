"""Reduce el Censo 2020 del INEGI (ITER nacional) a las localidades urbanas que usan los Grupos de tiendas.

Uso: docker compose exec api python -m scripts.preparar_inegi --zip /app/docs/datos/iter_00_cpv2020_csv.zip
El .zip se descarga a mano de https://www.inegi.org.mx (datos abiertos del Censo 2020). Escribe
datos/inegi/localidades_2020.csv; después se vuelve a calcular los grupos.
"""
import argparse
from pathlib import Path

from datos import demografia


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zip", required=True, help="iter_00_cpv2020_csv.zip o el CSV que viene dentro")
    a = p.parse_args()
    r = demografia.preparar(Path(a.zip))
    print(f"Listo: {r['localidades']:,} localidades urbanas en {demografia.ARCHIVO} "
          f"({r['sin_coordenadas']} sin coordenadas, descartadas).")


if __name__ == "__main__":
    main()
