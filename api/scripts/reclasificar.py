"""Reclasificar ya (sin esperar a la noche) las evaluaciones vigentes del radar de productos (v0.5.4).

Uso en el servidor:
    docker exec smn-api-1 python -m scripts.reclasificar --solo-ver     # lista qué cambiaría, sin tocar nada
    docker exec smn-api-1 python -m scripts.reclasificar                # recalcula las que cambian de subcategoría
"""
import argparse

from sqlalchemy.orm import Session

from core.bd import motor
from modulos.compras import reclasificar as rc


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--solo-ver", action="store_true")
    a.add_argument("--limite", type=int, default=None)
    args = a.parse_args()
    with Session(motor(), expire_on_commit=False) as bd:
        cambios = rc.revisar(bd, aplicar=not args.solo_ver, limite=args.limite,
                             avance=lambda i, n: print(f"  {i} de {n}", flush=True) if i % 10 == 0 or i == n else None)
    print(f"\n{len(cambios)} cambian de subcategoría{' (no se tocó nada)' if args.solo_ver else ' y se recalcularon'}:")
    for c in cambios:
        print(f"- [{c['evaluacion']}] {c['producto']}: {c['antes'] or '—'} ({c['origen_antes']}) -> {c['ahora'] or '—'} "
              f"({c['seguridad']})")


if __name__ == "__main__":
    main()
