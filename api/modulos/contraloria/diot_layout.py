"""DIOT: archivo TXT de carga al SAT y comparación contra un TXT de referencia.

Layout observado en los TXT que Fiscal cargó para ODP (agosto y septiembre de 2026): 54 campos separados por «|»,
renglones con CRLF. Solo se llenan los campos que esos TXT usan; los demás quedan vacíos. No es una regla universal:
cualquier importe que caiga en un campo sin confirmar (8 %, exento) bloquea la generación.
"""
from dataclasses import dataclass

from modulos.contraloria import diot_criterios as crit
from modulos.contraloria.diot_motor import Tercero

CAMPOS_TXT = crit.CAMPOS_LAYOUT
# campo del TXT (1 = primero) -> qué lleva (el vigente está en la Base de conocimiento fiscal)
MAPA = dict(crit.MAPA_LAYOUT)
NOMBRES = {1: "Tipo de tercero", 2: "Tipo de operación", 3: "RFC", 12: "Base 16 %", 22: "IVA 16 %",
           48: "IVA retenido", 51: "Base 0 %", 52: "Base no objeto", 54: "Campo 54"}
EFECTOS = crit.VALOR_EFECTOS


class ErrorLayout(Exception):
    pass


def _cfg(cfg: crit.Config | None) -> crit.Config:
    return cfg or crit.inicial()


def renglon(t: Tercero, cfg: crit.Config | None = None) -> str:
    cfg = _cfg(cfg)
    campos = [""] * cfg.campos_layout
    for n, clave in cfg.mapa.items():
        if clave == "efectos":
            v = cfg.efectos
        elif clave in ("tipo_tercero", "tipo_operacion", "rfc"):
            v = getattr(t, clave)
        else:
            v = str(t.redondeados[clave])
        campos[n - 1] = v
    return "|".join(campos)


def generar(terceros: list[Tercero], cfg: crit.Config | None = None) -> str:
    malos = [t.rfc for t in terceros if t.estado != "ok"]
    if malos:
        raise ErrorLayout(f"Hay {len(malos)} tercero(s) por revisar: {', '.join(malos[:10])}.")
    return "".join(renglon(t, cfg) + "\r\n" for t in terceros)


TIPOS_TERCERO = tuple(crit.TIPOS_TERCERO)
TIPOS_OPERACION = tuple(crit.TIPOS_OPERACION)
IMPORTES = (12, 22, 48, 51, 52)


def nombre_campo(cfg: crit.Config, n: int) -> str:
    return crit.QUE_LLEVA.get(cfg.mapa.get(n, ""), NOMBRES.get(n, "campo"))


def validar(txt: str, terceros: list[Tercero], cfg: crit.Config | None = None) -> list[dict]:
    """Las revisiones del archivo antes de entregarlo (estructura, importes y registros). Cada una dice qué revisó."""
    cfg = _cfg(cfg)
    total = cfg.campos_layout
    campo = {n: c for n, c in cfg.mapa.items() if c in crit.QUE_LLEVA and c not in (
        "tipo_tercero", "tipo_operacion", "rfc", "efectos")}
    importes = tuple(sorted(campo))
    pos = {c: n for n, c in cfg.mapa.items()}
    tt, to, rf = pos.get("tipo_tercero", 1) - 1, pos.get("tipo_operacion", 2) - 1, pos.get("rfc", 3) - 1
    lineas = txt.split("\r\n")
    renglones = [x.split("|") for x in lineas[:-1]]
    v = []

    def chk(nombre: str, malos: list, bien: str, mal: str) -> None:
        v.append({"verificacion": nombre, "ok": not malos,
                  "detalle": bien if not malos else f"{mal}: {', '.join(str(m) for m in malos[:10])}"})

    chk("Fin de renglón", [] if txt.endswith("\r\n") and "\n" not in txt.replace("\r\n", "") else ["LF suelto"],
        "todos los renglones terminan en CRLF, incluido el último", "hay renglones sin CRLF")
    try:
        txt.encode("ascii")
        no_ascii = []
    except UnicodeEncodeError:
        no_ascii = [n for n, x in enumerate(lineas, 1) if not x.isascii()]
    chk("Caracteres", no_ascii, "solo ASCII (sin acentos ni ñ)", "renglones con caracteres fuera de ASCII")
    chk("Número de campos", [n for n, r in enumerate(renglones, 1) if len(r) != total],
        f"los {len(renglones)} renglones tienen {total} campos", f"renglones sin {total} campos")
    renglones = [r for r in renglones if len(r) == total]
    chk("Renglones contra consolidado", [] if len(renglones) == len(terceros) else [len(renglones)],
        f"{len(renglones)} renglones = {len(terceros)} terceros del consolidado", "no coincide el número de renglones")
    chk("Tipo de tercero", [r[rf] for r in renglones if r[tt] not in cfg.tipos_tercero],
        f"todos en el catálogo ({', '.join(cfg.tipos_tercero)})", "tipo de tercero fuera del catálogo")
    chk("Tipo de operación", [r[rf] for r in renglones if r[to] not in cfg.tipos_operacion],
        f"todos en el catálogo ({', '.join(cfg.tipos_operacion)})", "tipo de operación fuera del catálogo")
    import re
    patron = re.compile(r"[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}")
    chk("RFC", [r[rf] for r in renglones if r[tt] == "04" and not patron.fullmatch(r[rf])],
        "todos los proveedores nacionales con RFC de formato válido", "RFC con formato inválido")
    vistos, dobles = set(), []
    for r in renglones:
        k = (r[rf], r[to])
        if k in vistos:
            dobles.append(r[rf])
        vistos.add(k)
    chk("Registros únicos", dobles, "un renglón por RFC y tipo de operación", "RFC repetidos")
    chk("Importes", [f"{r[rf]} campo {n}" for r in renglones for n in importes
                     if r[n - 1] and not r[n - 1].isdigit()],
        "enteros, sin decimales ni signos", "importes no enteros o negativos")
    chk("Renglones con importe", [r[rf] for r in renglones if not any(r[n - 1] not in ("", "0") for n in importes)],
        "ningún renglón va en ceros", "renglones sin ningún importe")
    malos_iva = []
    for base, iva, tasa in (("base16", "iva16", 0.16), ("base8", "iva8", 0.08)):
        if base in pos and iva in pos:
            b, i = pos[base] - 1, pos[iva] - 1
            malos_iva += [r[rf] for r in renglones if r[b].isdigit()
                          and abs(int(r[i] or 0) - round(int(r[b]) * tasa)) > 1]
    chk("IVA contra base", malos_iva, "en cada renglón el IVA es la base × la tasa (±1 peso por redondeo)",
        "IVA que no corresponde a su base")
    sumas = {n: sum(int(r[n - 1]) for r in renglones if r[n - 1].isdigit()) for n in importes}
    esperado = {n: sum(t.redondeados[campo[n]] for t in terceros) for n in importes}
    chk("Totales", [nombre_campo(cfg, n) for n in importes if sumas[n] != esperado[n]],
        "; ".join(f"{nombre_campo(cfg, n)} {sumas[n]:,}" for n in importes) + " = consolidado",
        "totales del TXT distintos al consolidado")
    return v


@dataclass
class Diferencia:
    rfc: str
    campo: str
    generado: str | None
    referencia: str | None


def _leer(txt: str, rf: int = 2) -> dict[str, list[str]]:
    filas = {}
    for linea in txt.replace("\r\n", "\n").split("\n"):
        if linea.strip():
            c = linea.split("|")
            filas[c[rf] if len(c) > rf else linea] = c
    return filas


def comparar(generado: str, referencia: str, cfg: crit.Config | None = None) -> dict:
    cfg = _cfg(cfg)
    pos = {c: n for n, c in cfg.mapa.items()}
    g, r = _leer(generado, pos.get("rfc", 3) - 1), _leer(referencia, pos.get("rfc", 3) - 1)
    difs: list[Diferencia] = []
    for rfc in sorted(set(g) | set(r)):
        a, b = g.get(rfc), r.get(rfc)
        if a is None or b is None:
            difs.append(Diferencia(rfc, "renglón", "sí" if a else None, "sí" if b else None))
            continue
        if len(a) != len(b):
            difs.append(Diferencia(rfc, "número de campos", str(len(a)), str(len(b))))
        for n in range(1, max(len(a), len(b)) + 1):
            x = a[n - 1] if n <= len(a) else None
            y = b[n - 1] if n <= len(b) else None
            if (x or "") != (y or ""):
                difs.append(Diferencia(rfc, f"{n} · {nombre_campo(cfg, n)}", x, y))
    totales = {}
    for n, que in sorted(cfg.mapa.items()):
        if que in ("tipo_tercero", "tipo_operacion", "rfc", "efectos"):
            continue
        sg = sum(int(c[n - 1] or 0) for c in g.values() if len(c) >= n and (c[n - 1] or "0").lstrip("-").isdigit())
        sr = sum(int(c[n - 1] or 0) for c in r.values() if len(c) >= n and (c[n - 1] or "0").lstrip("-").isdigit())
        totales[nombre_campo(cfg, n)] = {"generado": sg, "referencia": sr, "diferencia": sg - sr}
    iguales = sum(1 for k in set(g) & set(r) if g[k] == r[k])
    return {"renglones_generados": len(g), "renglones_referencia": len(r), "renglones_iguales": iguales,
            "formato_igual": generado.endswith("\r\n") == referencia.endswith("\r\n"),
            "diferencias": [d.__dict__ for d in difs], "totales": totales}
