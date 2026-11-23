"""Motor de reglas de Vidanat: función pura, sin IA y sin base de datos.

Recibe los datos estructurados de la ficha (y de la fórmula, si la hay) y la condición de una regla guardada como JSON,
y regresa cumple / incumple / pendiente / no_aplica con el motivo, los datos que leyó y los que faltan.

Lógica de tres valores (más «no aplica»):
- todas: si alguna incumple, incumple; si no, y alguna está pendiente, pendiente; si no, cumple.
- alguna: si alguna cumple, cumple; si no, y alguna está pendiente, pendiente; si no, incumple.
- no: invierte cumple ↔ incumple; pendiente sigue pendiente.
Un dato faltante nunca se convierte en «cumple». Las UI solo se convierten con el factor del ingrediente.

Operadores (sección 5.2 del plan): existe, igual, en_lista, no_en_lista, rango, comparar, unidades_compatibles,
documento, texto_no_contiene, coherente_fraccion, para_cada, todas, alguna, no, y.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

VERSION = "1.0"

CUMPLE, INCUMPLE, PENDIENTE, NO_APLICA = "cumple", "incumple", "pendiente", "no_aplica"

# unidad: (dimensión, factor a la unidad base de la dimensión)
UNIDADES: dict[str, tuple[str, Decimal]] = {
    "µg": ("masa", Decimal("0.000001")), "ug": ("masa", Decimal("0.000001")), "mcg": ("masa", Decimal("0.000001")),
    "mg": ("masa", Decimal("0.001")), "g": ("masa", Decimal(1)), "kg": ("masa", Decimal(1000)),
    "ml": ("volumen", Decimal("0.001")), "l": ("volumen", Decimal(1)),
    "%": ("fraccion", Decimal("0.01")), "mg/g": ("fraccion", Decimal("0.001")),
    "ui": ("ui", Decimal(1)),
    "cápsula": ("conteo_capsula", Decimal(1)), "capsula": ("conteo_capsula", Decimal(1)),
    "tableta": ("conteo_tableta", Decimal(1)), "porción": ("conteo_porcion", Decimal(1)),
    "porcion": ("conteo_porcion", Decimal(1)), "pieza": ("conteo_pieza", Decimal(1)),
    "ufc": ("conteo_ufc", Decimal(1)),
}
OPERADORES = {"existe", "igual", "en_lista", "no_en_lista", "rango", "comparar", "unidades_compatibles", "documento",
              "texto_no_contiene", "coherente_fraccion", "para_cada", "todas", "alguna", "no", "y"}
COMPARADORES = {"<", "<=", "=", ">=", ">", "!="}
ALCANCE = ("jurisdiccion", "categoria_sanitaria", "categoria_comercial", "presentacion", "tipo_ingrediente",
           "etapa_destino")
RESTRINGIDO = "dato restringido"


class CondicionInvalida(ValueError):
    """La condición no se puede evaluar: el mensaje es para quien arma la regla."""


@dataclass
class Resultado:
    valor: str
    motivos: list[str] = field(default_factory=list)
    faltantes: list[str] = field(default_factory=list)
    usados: dict[str, str] = field(default_factory=dict)

    def motivo(self) -> str:
        vistos = list(dict.fromkeys(m for m in self.motivos if m))
        return "; ".join(vistos)[:1000] or {CUMPLE: "Cumple", INCUMPLE: "No cumple", PENDIENTE: "Faltan datos",
                                             NO_APLICA: "No aplica"}[self.valor]


# ---------------------------------------------------------------- unidades

def normaliza_unidad(u: str | None) -> str | None:
    if u is None:
        return None
    u = str(u).strip().lower().replace("μ", "µ")
    return {"mcg": "mcg", "iu": "ui", "u.i.": "ui", "ui": "ui", "cápsulas": "cápsula", "capsulas": "capsula",
            "tabletas": "tableta", "porciones": "porción"}.get(u, u)


def dimension(u: str | None) -> str | None:
    u = normaliza_unidad(u)
    return UNIDADES[u][0] if u in UNIDADES else None


def convertir(cantidad: Decimal, de: str, a: str, *, factor_ui_ug: Decimal | None = None) -> Decimal | None:
    """Convierte dentro de la misma dimensión. UI ↔ masa solo con el factor del ingrediente (µg por UI)."""
    de, a = normaliza_unidad(de), normaliza_unidad(a)
    if de not in UNIDADES or a not in UNIDADES:
        return None
    d1, f1 = UNIDADES[de]
    d2, f2 = UNIDADES[a]
    if d1 == d2:
        return cantidad * f1 / f2
    if {d1, d2} == {"ui", "masa"}:
        if not factor_ui_ug:
            return None
        if d1 == "ui":  # UI → µg → unidad destino
            return cantidad * factor_ui_ug * UNIDADES["µg"][1] / f2
        return cantidad * f1 / UNIDADES["µg"][1] / factor_ui_ug
    return None


def _numero(v) -> Decimal | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _bonito(d: Decimal) -> str:
    return f"{d.normalize():f}" if d == d.to_integral() else f"{d.quantize(Decimal('0.0001')).normalize():f}"


# ---------------------------------------------------------------- lectura de campos

@dataclass
class Ambito:
    raiz: dict
    item: dict | None = None
    ruta_item: str = ""  # «ingredientes[2]»
    nombre_item: str | None = None

    def leer(self, campo: str):
        """(valor, ruta). Primero en el renglón actual (ingrediente), luego en la ficha."""
        if self.item is not None and not campo.startswith("$."):
            v = _bajar(self.item, campo)
            if v is not _NADA:
                return v, f"{self.ruta_item}.{campo}"
            v = _bajar(self.raiz, campo)
            if v is not _NADA and not _falta(v):
                return v, campo
            return None, f"{self.ruta_item}.{campo}"
        campo = campo.removeprefix("$.")
        v = _bajar(self.raiz, campo)
        return (None if v is _NADA else v), campo

    def etiqueta(self, ruta: str) -> str:
        return f"{ruta} ({self.nombre_item})" if self.nombre_item and ruta.startswith(self.ruta_item) else ruta


_NADA = object()


def _bajar(d, campo: str):
    actual = d
    for parte in campo.split("."):
        if isinstance(actual, dict) and parte in actual:
            actual = actual[parte]
        else:
            return _NADA
    return actual


def _falta(v) -> bool:
    return v is None or v == "" or v == []


def _unidad_de(campo: str) -> str:
    return campo.replace("cantidad", "unidad", 1) if "cantidad" in campo else f"unidad_{campo}"


# ---------------------------------------------------------------- evaluación

def evaluar(condicion: dict, datos: dict, *, hoy: date | None = None) -> Resultado:
    """Evalúa una condición contra los datos de la ficha. Lanza CondicionInvalida si la condición está mal armada."""
    validar(condicion)
    return _eval(condicion, Ambito(datos), hoy or date.today())


def validar(condicion) -> None:
    if not isinstance(condicion, dict) or not condicion:
        raise CondicionInvalida("La condición debe ser un objeto con al menos un operador.")
    desconocidos = [k for k in condicion if k not in OPERADORES and k not in ("convertir_a", "dimension", "tolerancia")]
    if desconocidos:
        raise CondicionInvalida(f"Operador desconocido: {', '.join(desconocidos)}.")
    for k, v in condicion.items():
        if k in ("todas", "alguna"):
            if not isinstance(v, list) or not v:
                raise CondicionInvalida(f"«{k}» necesita una lista de condiciones.")
            for c in v:
                validar(c)
        elif k in ("no", "y"):
            validar(v)
        elif k == "para_cada":
            if not isinstance(v, dict) or "lista" not in v:
                raise CondicionInvalida("«para_cada» necesita «lista».")
            if "donde" in v:
                validar(v["donde"])
            resto = {x: y for x, y in condicion.items() if x != "para_cada"}
            if not any(x in OPERADORES for x in resto):
                raise CondicionInvalida("«para_cada» necesita la condición que debe cumplir cada renglón.")
        elif k == "comparar":
            if not (isinstance(v, list) and len(v) == 3 and v[1] in COMPARADORES):
                raise CondicionInvalida("«comparar» va como [campo, operador, campo o número].")
        elif k == "rango":
            if not isinstance(v, dict) or "campo" not in v or ("min" not in v and "max" not in v):
                raise CondicionInvalida("«rango» necesita «campo» y «min» o «max».")
            if v.get("unidad") and dimension(v["unidad"]) is None:
                raise CondicionInvalida(f"Unidad desconocida en «rango»: {v['unidad']}.")
        elif k in ("igual", "en_lista", "no_en_lista", "unidades_compatibles"):
            if not (isinstance(v, list) and len(v) == 2):
                raise CondicionInvalida(f"«{k}» va como [campo, valor].")
        elif k == "texto_no_contiene":
            if not (isinstance(v, list) and len(v) == 2 and isinstance(v[1], list)):
                raise CondicionInvalida("«texto_no_contiene» va como [campo, [términos]].")


def _combinar_todas(partes: list[Resultado]) -> Resultado:
    utiles = [p for p in partes if p.valor != NO_APLICA]
    r = Resultado(CUMPLE if utiles else NO_APLICA)
    for p in partes:
        r.usados.update(p.usados)
    if any(p.valor == INCUMPLE for p in utiles):
        r.valor = INCUMPLE
        r.motivos = [m for p in utiles if p.valor == INCUMPLE for m in p.motivos]
    elif any(p.valor == PENDIENTE for p in utiles):
        r.valor = PENDIENTE
        r.motivos = [m for p in utiles if p.valor == PENDIENTE for m in p.motivos]
    else:
        r.motivos = [m for p in partes for m in p.motivos]
    r.faltantes = list(dict.fromkeys(f for p in utiles for f in p.faltantes)) if r.valor == PENDIENTE else []
    return r


def _combinar_alguna(partes: list[Resultado]) -> Resultado:
    utiles = [p for p in partes if p.valor != NO_APLICA]
    r = Resultado(INCUMPLE if utiles else NO_APLICA)
    for p in partes:
        r.usados.update(p.usados)
    if any(p.valor == CUMPLE for p in utiles):
        r.valor = CUMPLE
        r.motivos = [m for p in utiles if p.valor == CUMPLE for m in p.motivos][:1]
    elif any(p.valor == PENDIENTE for p in utiles):
        r.valor = PENDIENTE
        r.motivos = [m for p in utiles if p.valor == PENDIENTE for m in p.motivos]
        r.faltantes = list(dict.fromkeys(f for p in utiles for f in p.faltantes))
    else:
        r.motivos = [m for p in utiles for m in p.motivos]
    return r


def _eval(c: dict, amb: Ambito, hoy: date) -> Resultado:
    if "para_cada" in c:
        return _para_cada(c, amb, hoy)
    partes = []
    for k, v in c.items():
        if k in ("convertir_a", "dimension", "tolerancia"):
            continue
        partes.append(_operador(k, v, c, amb, hoy))
    return partes[0] if len(partes) == 1 else _combinar_todas(partes)


def _para_cada(c: dict, amb: Ambito, hoy: date) -> Resultado:
    spec = c["para_cada"]
    lista = amb.raiz.get(spec["lista"]) or []
    resto = {k: v for k, v in c.items() if k != "para_cada"}
    partes = []
    for i, item in enumerate(lista, start=1):
        sub = Ambito(amb.raiz, item, f"{spec['lista']}[{i}]", item.get("nombre"))
        if "donde" in spec:
            filtro = _eval(spec["donde"], sub, hoy)
            if filtro.valor != CUMPLE:  # el filtro decide a quién aplica; si le falta el dato, no se supone
                if filtro.valor == PENDIENTE:
                    partes.append(Resultado(PENDIENTE, [f"No se sabe si aplica a {item.get('nombre') or sub.ruta_item}: "
                                                        + filtro.motivo()], filtro.faltantes, filtro.usados))
                continue
        partes.append(_eval(resto, sub, hoy))
    if not partes:
        nombre = spec.get("nombre") or spec["lista"]
        return Resultado(NO_APLICA, [spec.get("motivo_vacio") or f"Ningún renglón de {nombre} entra en esta regla"])
    return _combinar_todas(partes)


def _faltante(amb: Ambito, ruta: str, texto: str | None = None) -> Resultado:
    return Resultado(PENDIENTE, [texto or f"Falta {amb.etiqueta(ruta)}"], [ruta])


def _cantidad(amb: Ambito, campo: str, c: dict):
    """(Decimal, unidad, ruta) o un Resultado pendiente si falta el número o la unidad."""
    valor, ruta = amb.leer(campo)
    if _falta(valor):
        return _faltante(amb, ruta)
    n = _numero(valor)
    if n is None:
        return _faltante(amb, ruta, f"{amb.etiqueta(ruta)} no es un número")
    campo_u = c.get("campo_unidad") or _unidad_de(campo)
    unidad, ruta_u = amb.leer(campo_u)
    if _falta(unidad):
        return _faltante(amb, ruta_u)
    return n, normaliza_unidad(unidad), ruta, ruta_u


def _operador(k: str, v, c: dict, amb: Ambito, hoy: date) -> Resultado:
    if k == "todas":
        return _combinar_todas([_eval(x, amb, hoy) for x in v])
    if k == "alguna":
        return _combinar_alguna([_eval(x, amb, hoy) for x in v])
    if k == "y":
        return _eval(v, amb, hoy)
    if k == "no":
        r = _eval(v, amb, hoy)
        if r.valor in (CUMPLE, INCUMPLE):
            r.valor = INCUMPLE if r.valor == CUMPLE else CUMPLE
            r.motivos = [f"No debe: {r.motivo()}"] if r.valor == INCUMPLE else []
        return r

    if k == "existe":
        valor, ruta = amb.leer(v)
        if _falta(valor):
            return _faltante(amb, ruta)
        return Resultado(CUMPLE, [], [], {ruta: _texto(valor)})

    if k in ("igual", "en_lista", "no_en_lista"):
        campo, esperado = v
        valor, ruta = amb.leer(campo)
        if _falta(valor):
            return _faltante(amb, ruta)
        usados = {ruta: _texto(valor)}
        if k == "igual":
            ok = _igual(valor, esperado)
            return Resultado(CUMPLE if ok else INCUMPLE, [] if ok else [f"{amb.etiqueta(ruta)} es «{_texto(valor)}», "
                                                                       f"debe ser «{_texto(esperado)}»"], [], usados)
        dentro = any(_igual(valor, e) for e in esperado)
        ok = dentro if k == "en_lista" else not dentro
        return Resultado(CUMPLE if ok else INCUMPLE, [] if ok else [
            f"{amb.etiqueta(ruta)} es «{_texto(valor)}», " + ("no está en la lista" if k == "en_lista" else "está en la lista no permitida")],
            [], usados)

    if k == "rango":
        x = _cantidad(amb, v["campo"], v)
        if isinstance(x, Resultado):
            return x
        n, unidad, ruta, ruta_u = x
        destino = normaliza_unidad(v.get("unidad")) or unidad
        conv = convertir(n, unidad, destino, factor_ui_ug=_numero((amb.item or {}).get("factor_ui_ug")))
        usados = {ruta: f"{_bonito(n)} {unidad}"}
        if conv is None:
            if dimension(unidad) == "ui" or dimension(destino) == "ui":
                return Resultado(PENDIENTE, [f"Falta factor UI→µg de {amb.nombre_item or 'el ingrediente'}"],
                                 [f"{amb.ruta_item}.factor_ui_ug" if amb.item is not None else "factor_ui_ug"], usados)
            return Resultado(PENDIENTE, [f"No se puede convertir {unidad} a {destino}"], [ruta_u], usados)
        mn, mx = _numero(v.get("min")), _numero(v.get("max"))
        if (mn is not None and conv < mn) or (mx is not None and conv > mx):
            limite = (f"entre {_bonito(mn)} y {_bonito(mx)}" if mn is not None and mx is not None
                      else f"mínimo {_bonito(mn)}" if mn is not None else f"máximo {_bonito(mx)}")
            return Resultado(INCUMPLE, [f"{amb.etiqueta(ruta)} = {_bonito(conv)} {destino}; {limite} {destino}"], [], usados)
        return Resultado(CUMPLE, [], [], usados)

    if k == "comparar":
        a, op, b = v
        xa = _cantidad(amb, a, {})
        if isinstance(xa, Resultado):
            return xa
        if not isinstance(b, str):
            if _numero(b) is None:
                raise CondicionInvalida("«comparar» necesita un campo o un número a la derecha.")
            nb, ub, ruta_b = _numero(b), xa[1], str(b)
        else:
            xb = _cantidad(amb, b, {})
            if isinstance(xb, Resultado):
                return xb
            nb, ub, ruta_b, _ = xb
        na, ua, ruta_a, _ = xa
        destino = normaliza_unidad(c.get("convertir_a")) or ua
        factor = _numero((amb.item or {}).get("factor_ui_ug"))
        ca, cb = convertir(na, ua, destino, factor_ui_ug=factor), convertir(nb, ub, destino, factor_ui_ug=factor)
        usados = {ruta_a: f"{_bonito(na)} {ua}"}
        if ruta_b != str(b):
            usados[ruta_b] = f"{_bonito(nb)} {ub}"
        if ca is None or cb is None:
            if "ui" in (dimension(ua), dimension(ub)):
                return Resultado(PENDIENTE, [f"Falta factor UI→µg de {amb.nombre_item or 'el ingrediente'}"],
                                 [f"{amb.ruta_item}.factor_ui_ug"], usados)
            return Resultado(PENDIENTE, [f"Unidades que no se pueden comparar: {ua} y {ub}"], [], usados)
        ok = {"<": ca < cb, "<=": ca <= cb, "=": ca == cb, ">=": ca >= cb, ">": ca > cb, "!=": ca != cb}[op]
        return Resultado(CUMPLE if ok else INCUMPLE, [] if ok else [
            f"{amb.etiqueta(ruta_a)} ({_bonito(ca)} {destino}) debe ser {op} {amb.etiqueta(ruta_b)} ({_bonito(cb)} {destino})"],
            [], usados)

    if k == "unidades_compatibles":
        ua_c, ub_c = v
        ua, ra = amb.leer(ua_c)
        ub, rb = amb.leer(ub_c)
        faltan = [r for u, r in ((ua, ra), (ub, rb)) if _falta(u)]
        if faltan:
            return Resultado(PENDIENTE, [f"Falta {amb.etiqueta(r)}" for r in faltan], faltan)
        da, db = dimension(ua), dimension(ub)
        usados = {ra: str(ua), rb: str(ub)}
        esperada = c.get("dimension")
        ok = da is not None and da == db and (esperada is None or da == esperada)
        return Resultado(CUMPLE if ok else INCUMPLE, [] if ok else [
            f"Unidades incompatibles: {ua} y {ub}" + (f" (deben ser de {esperada})" if esperada else "")], [], usados)

    if k == "coherente_fraccion":
        tol = _numero(c.get("tolerancia")) or Decimal("0.02")
        xc = _cantidad(amb, "cantidad_compuesto", {})
        xa = _cantidad(amb, "cantidad_activa", {})
        if isinstance(xc, Resultado):
            return xc
        if isinstance(xa, Resultado):
            return xa
        fr, ruta_f = amb.leer("fraccion_activa")
        if _falta(fr):
            return Resultado(NO_APLICA, ["Sin fracción de la ficha técnica: no hay contra qué revisar"])
        esperado = convertir(xc[0], xc[1], xa[1])
        if esperado is None:
            return Resultado(PENDIENTE, [f"Unidades incompatibles: {xc[1]} y {xa[1]}"], [])
        esperado *= _numero(fr)
        usados = {xc[2]: f"{_bonito(xc[0])} {xc[1]}", xa[2]: f"{_bonito(xa[0])} {xa[1]}", ruta_f: str(fr)}
        if esperado and abs(xa[0] - esperado) / esperado > tol:
            return Resultado(INCUMPLE, [f"{amb.etiqueta(xa[2])} = {_bonito(xa[0])} {xa[1]}, pero compuesto × fracción da "
                                        f"{_bonito(esperado)} {xa[1]}"], [], usados)
        return Resultado(CUMPLE, [], [], usados)

    if k == "documento":
        tipo = v.get("tipo")
        docs, ruta = amb.leer(v.get("campo", "documentos"))
        docs = docs or []
        quien = amb.nombre_item or "el expediente"
        validos = [d for d in docs if d.get("tipo") == tipo and d.get("estado") == "revisado"
                   and (not v.get("vigente") or not d.get("vigente_hasta") or str(d["vigente_hasta"]) >= hoy.isoformat())]
        if not validos:
            return Resultado(INCUMPLE, [f"Falta {tipo.replace('_', ' ')} revisada y vigente de {quien}"], [], {ruta: f"{len(docs)} documentos"})
        return Resultado(CUMPLE, [], [], {ruta: f"{len(validos)} {tipo.replace('_', ' ')}"})

    if k == "texto_no_contiene":
        campo, terminos = v
        valor, ruta = amb.leer(campo)
        if _falta(valor):
            return _faltante(amb, ruta, f"No hay {campo} capturadas")
        textos = valor if isinstance(valor, list) else [valor]
        from nucleo.busqueda import sin_acentos
        hallados = []
        for t in textos:
            limpio = f" {sin_acentos(str(t))} "
            for termino in terminos:
                if f" {sin_acentos(termino)}" in limpio or sin_acentos(termino) in limpio.split():
                    hallados.append((str(t), termino))
        if hallados:
            return Resultado(INCUMPLE, [f"«{t}» usa el término «{term}»" for t, term in hallados], [], {ruta: "; ".join(textos)[:300]})
        return Resultado(CUMPLE, [], [], {ruta: f"{len(textos)} revisadas"})

    raise CondicionInvalida(f"Operador desconocido: {k}.")


def _igual(a, b) -> bool:
    na, nb = _numero(a), _numero(b)
    if na is not None and nb is not None and not isinstance(a, bool) and not isinstance(b, bool):
        return na == nb
    if isinstance(a, str) and isinstance(b, str):
        from nucleo.busqueda import sin_acentos
        return sin_acentos(a.strip()) == sin_acentos(b.strip())
    return a == b


def _texto(v) -> str:
    if isinstance(v, bool):
        return "sí" if v else "no"
    if isinstance(v, list):
        return ", ".join(_texto(x) for x in v)
    return str(v)


# ---------------------------------------------------------------- alcance, vigencia y choques

def en_alcance(alcance: dict | None, datos: dict) -> tuple[bool, str]:
    """Un campo de alcance vacío significa «todos». Regresa (aplica, motivo si no aplica)."""
    for clave, valor in (alcance or {}).items():
        if clave == "etapa_destino" or valor in (None, "", []):
            continue
        permitidos = valor if isinstance(valor, list) else [valor]
        if clave == "tipo_ingrediente":
            tipos = {i.get("tipo") for i in datos.get("ingredientes") or []}
            if not tipos & set(permitidos):
                return False, f"La fórmula no tiene ingredientes de tipo {', '.join(permitidos)}"
            continue
        actual = datos.get(clave)
        if _falta(actual):
            continue  # sin el dato no se descarta: la regla aplica y sus condiciones dirán qué falta
        if not any(_igual(actual, p) for p in permitidos):
            return False, f"Fuera de alcance: {clave.replace('_', ' ')} es «{actual}»"
    return True, ""


def vigente(desde: date | None, hasta: date | None, dia: date) -> bool:
    return desde is not None and desde <= dia and (hasta is None or dia <= hasta)


def rangos(condicion: dict) -> list[dict]:
    """Todos los «rango» de una condición, para buscar choques entre reglas."""
    salida = []
    if isinstance(condicion, dict):
        for k, v in condicion.items():
            if k == "rango":
                salida.append(v)
            elif isinstance(v, dict):
                salida += rangos(v)
            elif isinstance(v, list):
                for x in v:
                    salida += rangos(x)
    return salida


def alcances_se_cruzan(a: dict | None, b: dict | None) -> bool:
    a, b = a or {}, b or {}
    for clave in set(a) | set(b):
        va, vb = a.get(clave), b.get(clave)
        if va in (None, "", []) or vb in (None, "", []):
            continue
        la = va if isinstance(va, list) else [va]
        lb = vb if isinstance(vb, list) else [vb]
        if not any(_igual(x, y) for x in la for y in lb):
            return False
    return True


def choque(r1: dict, r2: dict) -> str | None:
    """Dos rangos sobre el mismo campo que no se pueden cumplir a la vez. Regresa el motivo o None."""
    if r1.get("campo") != r2.get("campo"):
        return None
    u = normaliza_unidad(r1.get("unidad")) or normaliza_unidad(r2.get("unidad")) or "mg"

    def lim(r, k):
        n = _numero(r.get(k))
        if n is None:
            return None
        return convertir(n, normaliza_unidad(r.get("unidad")) or u, u)

    min1, max1, min2, max2 = lim(r1, "min"), lim(r1, "max"), lim(r2, "min"), lim(r2, "max")
    if (min1 is not None and max2 is not None and min1 > max2) or (min2 is not None and max1 is not None and min2 > max1):
        return (f"«{r1['campo']}»: un rango pide {_txt_rango(min1, max1, u)} y otro {_txt_rango(min2, max2, u)}")
    return None


def _txt_rango(mn, mx, u) -> str:
    if mn is not None and mx is not None:
        return f"entre {_bonito(mn)} y {_bonito(mx)} {u}"
    return f"mínimo {_bonito(mn)} {u}" if mn is not None else f"máximo {_bonito(mx)} {u}"


def enmascarar(usados: dict[str, str], puede_formula: bool) -> dict[str, str]:
    """Los datos leídos de la fórmula técnica se ocultan a quien no puede verla."""
    if puede_formula:
        return usados
    return {k: (RESTRINGIDO if k.startswith("formula") else v) for k, v in usados.items()}
