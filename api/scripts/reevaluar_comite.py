"""Vuelve a evaluar todos los productos de una reunión del comité (pedido de Diego, 2026-11-11: «volver a evaluar»
los productos cargados en el servidor después de publicar el radar recalibrado).

Qué hace y qué no:
- Cada producto recibe una evaluación nueva; la anterior queda en el historial (no se borra nada).
- Se conservan la clasificación y los parecidos que confirmó Compras.
- No toca el pre-filtro, las decisiones del comité, las fotos ni la reunión (su estado sigue igual).
- Los productos a los que Compras les cambió el color final se SALTAN, salvo con --incluir-con-color.
- No crea búsquedas de proveedor ni manda avisos, salvo con --con-busquedas.
- Los que siguen en el portal del proveedor (sin enviar) o rechazados se saltan.

Uso en el servidor:
    docker exec -it smn-api-1 python -m scripts.reevaluar_comite --probar      (solo lista, no cambia nada)
    docker exec -it smn-api-1 python -m scripts.reevaluar_comite               (la reunión abierta más reciente)
Opciones: --reunion N   --paralelo 2   --incluir-con-color   --con-busquedas
"""
import argparse
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import select

from core.bd import _fabrica
from modulos.compras import rutas_comite  # noqa: F401  (registra todos los modelos relacionados)
from modulos.compras import radar_productos as rp
from modulos.compras.modelos_comite import ComiteProducto, ComiteReunion
from modulos.compras.modelos_propuestas import Propuesta

NO_EVALUAR = ("borrador", "devuelta", "rechazada")  # como EN_PORTAL de rutas_comite, más rechazadas


def nombre(bd, i: ComiteProducto) -> str:
    e = rp.vigente(bd, propuesta_id=i.propuesta_id) if i.propuesta_id else rp.vigente(bd, idea_id=i.idea_id)
    return f"#{i.orden} ({'propuesta ' + str(i.propuesta_id) if i.propuesta_id else 'idea ' + str(i.idea_id)})", e


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--reunion", type=int)
    a.add_argument("--paralelo", type=int, default=2)
    a.add_argument("--probar", action="store_true")
    a.add_argument("--incluir-con-color", action="store_true")
    a.add_argument("--con-busquedas", action="store_true")
    args = a.parse_args()
    if not args.con_busquedas:
        from modulos.compras import busquedas
        busquedas.despues_de_evaluar = lambda *_, **__: None

    fabrica = _fabrica()
    with fabrica() as bd:
        q = select(ComiteReunion)
        q = q.where(ComiteReunion.reunion_id == args.reunion) if args.reunion else \
            q.where(ComiteReunion.estado != "cerrada").order_by(ComiteReunion.fecha.desc(), ComiteReunion.reunion_id.desc())
        r = bd.scalar(q)
        if not r:
            raise SystemExit("No encontré la reunión (o no hay ninguna sin cerrar). Usa --reunion N.")
        print(f"Reunión {r.reunion_id} del {r.fecha} · estado «{r.estado}» · {len(r.productos)} productos\n")
        cola, saltados = [], Counter()
        for i in r.productos:
            n, e = nombre(bd, i)
            if i.propuesta_id:
                p = bd.get(Propuesta, i.propuesta_id)
                if p.estado in NO_EVALUAR or p.estado in ("recibida", "en_revision"):
                    saltados[f"propuesta en «{p.estado}» (se evalúa desde la pantalla)"] += 1
                    continue
            if e and e.estado == "en_curso":
                saltados["evaluación en curso"] += 1
                continue
            if e and e.color_final and not args.incluir_con_color:
                saltados["Compras le cambió el color final"] += 1
                print(f"  se salta {n}: color final de Compras «{e.color_final}»")
                continue
            cola.append((i.item_id, i.propuesta_id, i.idea_id, n, (e.color_final or e.color) if e else None))
        print(f"A evaluar: {len(cola)} · saltados: {sum(saltados.values())} {dict(saltados) or ''}")
        if args.probar:
            print("\n--probar: no se cambió nada.")
            return
        # se crean todas las evaluaciones nuevas primero (cada una deja la anterior como historial)
        trabajos = []
        for item_id, pid, iid, n, antes in cola:
            nueva = rp.iniciar(bd, propuesta_id=pid, idea_id=iid, usuario_id=r.creada_por)
            trabajos.append((nueva.evaluacion_id, n, antes))

    def correr(eid: int):
        with fabrica() as s:
            e = rp.evaluar(s, eid)
            return e.estado, e.color, e.puntaje, e.error

    t0, cambio, hechos = time.time(), Counter(), 0
    with ThreadPoolExecutor(max_workers=max(1, args.paralelo)) as ex:
        futuros = {ex.submit(correr, eid): (eid, n, antes) for eid, n, antes in trabajos}
        for f in as_completed(futuros):
            eid, n, antes = futuros[f]
            hechos += 1
            try:
                estado, color, puntaje, error = f.result()
            except Exception as err:  # noqa: BLE001
                estado, color, puntaje, error = "fallida", None, None, str(err)
            cambio[(antes, color if estado == "lista" else "falló")] += 1
            fin = f"{color} {puntaje}" if estado == "lista" else f"FALLÓ: {(error or '')[:150]}"
            print(f"[{hechos}/{len(trabajos)} · {int(time.time() - t0)} s] {n}: antes {antes or '-'} → {fin}", flush=True)

    print("\nResumen (antes → ahora):")
    for (antes, ahora_), k in sorted(cambio.items(), key=lambda x: -x[1]):
        print(f"  {antes or 'sin evaluar'} → {ahora_}: {k}")
    print(f"Listo en {int(time.time() - t0) // 60} min. Las que fallaron se pueden volver a evaluar con el botón.")


if __name__ == "__main__":
    main()
