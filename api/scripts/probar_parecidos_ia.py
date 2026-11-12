"""Prueba la revisión de parecidos con IA sobre los productos de una reunión del comité, sin cambiar ninguna evaluación
(v0.4, Diego eligió «Solo revisar parecidos» el 12 nov 2026). Para cada producto toma los parecidos de su evaluación
vigente, le pregunta a la IA local cuáles son de verdad el mismo tipo de producto y lista los que quitaría.
Solo queda registrada cada llamada a la IA en su bitácora.

Uso:  docker exec smn-api-1 python -u -m scripts.probar_parecidos_ia [--reunion N] [--limite 10]
"""
import argparse
import time

from sqlalchemy import select

from core.bd import _fabrica
from datos.modelos import Producto
from modulos.compras import rutas_comite  # noqa: F401  (registra todos los modelos relacionados)
from modulos.compras import radar_productos as rp
from modulos.compras.modelos_comite import ComiteReunion
from modulos.compras.modelos_productos import ProductoIdea
from modulos.compras.modelos_propuestas import Propuesta


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--reunion", type=int)
    a.add_argument("--limite", type=int, help="solo los primeros N productos")
    args = a.parse_args()
    with _fabrica()() as bd:
        from core import ajustes
        ajustes.aplicar(bd)
        if not ajustes.configuracion().ollama_modelo:
            raise SystemExit("No hay modelo de Ollama en Administración > Configuración.")
        q = select(ComiteReunion)
        q = q.where(ComiteReunion.reunion_id == args.reunion) if args.reunion else \
            q.where(ComiteReunion.estado != "cerrada").order_by(ComiteReunion.fecha.desc(), ComiteReunion.reunion_id.desc())
        r = bd.scalar(q)
        if not r:
            raise SystemExit("No encontré la reunión. Usa --reunion N.")
        productos = sorted(r.productos, key=lambda i: i.orden)[:args.limite]
        print(f"Reunión {r.reunion_id} · {len(productos)} productos · modelo {ajustes.configuracion().ollama_modelo}\n")
        total = con_cambio = quitados_total = 0
        inicio = time.monotonic()
        for i in productos:
            if i.propuesta_id:
                e = rp.vigente(bd, propuesta_id=i.propuesta_id)
                s = rp.sujeto_de_propuesta(bd.get(Propuesta, i.propuesta_id))  # noqa: E501
            else:
                e = rp.vigente(bd, idea_id=i.idea_id)
                s = rp.sujeto_de_idea(bd.get(ProductoIdea, i.idea_id))
            if not e or not e.comparables:
                print(f"#{i.orden} {s.nombre[:60]}: sin parecidos")
                continue
            if any(c.origen == "compras" for c in e.comparables):
                print(f"#{i.orden} {s.nombre[:60]}: parecidos fijados por Compras, no se revisan")
                continue
            parecidos = [(bd.get(Producto, c.producto_id), c.similitud) for c in sorted(e.comparables, key=lambda c: c.rango)]
            quedan, quitados = rp.revisar_parecidos(bd, s, parecidos)
            total += 1
            quitados_total += len(quitados)
            if quitados:
                con_cambio += 1
                print(f"#{i.orden} {s.nombre[:60]}: quedan {len(quedan)} de {len(parecidos)}")
                for p, motivo in quitados:
                    print(f"    quita: {p.descripcion}" + (f"  ({motivo})" if motivo else ""))
            else:
                print(f"#{i.orden} {s.nombre[:60]}: quedan todos ({len(parecidos)})")
            bd.commit()  # solo la bitácora de la IA
        minutos = (time.monotonic() - inicio) / 60
        print(f"\nRevisados {total}: a {con_cambio} les quitaría parecidos ({quitados_total} en total). "
              f"Tardó {minutos:.1f} min ({minutos * 60 / max(total, 1):.0f} s por producto).")


if __name__ == "__main__":
    main()
