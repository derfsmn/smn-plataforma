"""Examen de la clasificación del radar de productos contra el catálogo (plan aprobado por Diego, 24 nov 2026).

A cada producto activo con venta se le esconde del catálogo y se le clasifica como si fuera nuevo; se compara contra la
subcategoría que ya tiene. Usa la IA local (Ollama) igual que el radar. No escribe en la base.

Uso con Docker (de noche, porque usa Ollama):
    docker compose exec api python -m scripts.examen_clasificacion            # muestra de 300 + lanzamientos 2026
    docker compose exec api python -m scripts.examen_clasificacion --todos    # todo el catálogo (horas)
    docker compose cp api:/app/examen_clasificacion.xlsx .
Opciones: --n 300   --todos   --sin-ia (sin Ollama: solo para ver que corre)   --xlsx /app/examen_clasificacion.xlsx
"""
import argparse
import time

from sqlalchemy.orm import Session

from core.bd import motor
from ia import puerta
from modulos.compras import examen_clasificacion as ex


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--n", type=int, default=300)
    a.add_argument("--todos", action="store_true")
    a.add_argument("--sin-ia", action="store_true")
    a.add_argument("--xlsx", default="/app/examen_clasificacion.xlsx")
    args = a.parse_args()
    if args.sin_ia:
        def sin_ia(*_a, **_k):
            raise puerta.ErrorIA("examen sin IA")
        puerta.ejecutar = sin_ia
        puerta.vectores = sin_ia
    inicio = time.time()

    def avance(i: int, total: int, rs: list) -> None:
        bien = sum(r.bien_sub for r in rs if not r.error)
        print(f"  {i} de {total} · subcategoría bien {bien} de {len(rs)} · {(time.time() - inicio) / 60:.0f} min",
              flush=True)

    # expire_on_commit=False: la IA guarda su bitácora y, si no, cada guardado volvería a leer el catálogo completo
    with Session(motor(), expire_on_commit=False) as bd:
        print("Examinando...", flush=True)
        resultados, universo = ex.examinar(bd, None if args.todos else args.n, avance)
        print("Revisando los casos que ya fallaron...", flush=True)
        lista_casos = ex.casos(bd)
        res = ex.resumen(resultados, lista_casos)
        version = ex.version_actual() + (" · sin IA" if args.sin_ia else "")
        ex.a_excel(args.xlsx, version, resultados, res, lista_casos, universo)
    print("")
    for k, v in res["medidos"].items():
        ok = res["pasa"][k]
        print(f"{ex.NOMBRES[k]}: {'—' if v is None else v} (meta {ex.UMBRAL[k]}) {'' if ok is None else 'OK' if ok else 'NO'}")
    print(f"\nListo en {(time.time() - inicio) / 60:.0f} min: {args.xlsx}")


if __name__ == "__main__":
    main()
