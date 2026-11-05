"""Carga tres manuales FICTICIOS para probar Métodos y procedimientos antes de tener los reales.

Sus títulos empiezan con «EJEMPLO» y no describen procesos reales de SMN. Para quitarlos:
    python -m scripts.ejemplos_metodos --quitar
"""
import hashlib
import sys
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from modulos.metodos import documentos
from modulos.metodos.modelos import Documento, PruebaPregunta
from modulos.metodos.redaccion import word
from nucleo.archivos import _raiz
from nucleo.modelos import Archivo, Modulo, Permiso, RolPermiso, Usuario, UsuarioRol, ahora

PIE = "Documento FICTICIO para probar la plataforma. No describe un proceso real de SMN."
EJEMPLOS = [
    ("EJEMPLO Recepción de mercancía en tienda", "Tiendas", """# EJEMPLO Recepción de mercancía en tienda
## 1. Objetivo
Recibir la mercancía del proveedor revisando cantidades y caducidades antes de firmar la remisión.
## 2. Alcance
Aplica a todas las tiendas cuando llega mercancía directa del proveedor.
## 3. Responsables
- Encargado de tienda: recibe, revisa y firma la remisión.
- Auxiliar de almacén: cuenta las piezas.
## 6. Procedimiento
1. El auxiliar de almacén cuenta las piezas contra la remisión del proveedor.
2. El encargado de tienda revisa que la caducidad sea mayor a 6 meses.
3. Si falta mercancía o llega dañada, el encargado lo anota en la remisión antes de firmar.
4. El encargado captura la entrada en Intelisis el mismo día.
## 7. Excepciones
Mercancía con caducidad menor a 6 meses solo se recibe con autorización del comprador.
"""),
    ("EJEMPLO Alta de proveedor", "Compras", """# EJEMPLO Alta de proveedor
## 1. Objetivo
Registrar a un proveedor nuevo con sus documentos completos.
## 3. Responsables
- Comprador: pide los documentos y captura el alta.
- Jefe de Compras: autoriza el alta.
## 6. Procedimiento
1. El comprador pide al proveedor su constancia de situación fiscal y su estado de cuenta bancario.
2. El comprador revisa que los datos de la constancia coincidan con los de la factura.
3. El comprador captura el alta en Intelisis.
4. El jefe de Compras autoriza el alta en un máximo de 2 días hábiles.
"""),
    ("EJEMPLO Devoluciones de clientes", "Tiendas", """# EJEMPLO Devoluciones de clientes
## 1. Objetivo
Atender las devoluciones de clientes en caja.
## 6. Procedimiento
1. El cajero pide el ticket de compra.
2. Solo se aceptan devoluciones dentro de los 30 días posteriores a la compra.
3. El encargado de tienda autoriza la devolución en el punto de venta.
## 7. Excepciones
Los productos refrigerados no tienen devolución.
"""),
]
PREGUNTAS = [
    ("¿Qué caducidad mínima debe tener la mercancía al recibirla?", "Mayor a 6 meses.", 0),
    ("¿Qué documentos le pido a un proveedor nuevo?", "Constancia de situación fiscal y estado de cuenta bancario.", 1),
    ("¿Cuántos días tiene un cliente para devolver un producto?", "30 días con ticket.", 2),
    ("¿Cuál es el horario de la tienda en domingo?", None, None),
]


def _responsable(bd: Session) -> Usuario:
    uid = bd.scalar(select(UsuarioRol.usuario_id).join(RolPermiso, RolPermiso.rol_id == UsuarioRol.rol_id)
                    .join(Permiso, Permiso.permiso_id == RolPermiso.permiso_id)
                    .join(Usuario, Usuario.usuario_id == UsuarioRol.usuario_id)
                    .where(Permiso.codigo == "metodos.aprobar", Usuario.estatus == "activo"))
    if not uid:
        sys.exit("No hay un usuario activo con permiso de aprobar manuales. Corre primero scripts.semilla.")
    return bd.get(Usuario, uid)


def cargar(bd: Session) -> None:
    u = _responsable(bd)
    modulo = bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "metodos"))
    ids = []
    for titulo, area, texto in EJEMPLOS:
        if d := bd.scalar(select(Documento).where(Documento.titulo == titulo, Documento.estado == "vigente")):
            ids.append(d.documento_id)
            continue
        contenido = word(titulo, texto, PIE)
        relativa = f"{ahora():%Y/%m}/{uuid.uuid4().hex}.docx"
        destino = _raiz() / relativa
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)
        a = Archivo(modulo_id=modulo, entidad="metodos_documento", nombre_original=f"{titulo}.docx",
                    tipo_contenido="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    tamano_bytes=len(contenido), sha256=hashlib.sha256(contenido).hexdigest(),
                    ruta_almacenamiento=relativa, subido_por=u.usuario_id)
        bd.add(a)
        bd.flush()
        d, r = documentos.cargar(bd, archivo=a, titulo=titulo, tipo="manual", area=area, version="1.0",
                                 vigente_desde=date.today(), revisar_antes=None, clave=None, sistema="Intelisis",
                                 roles=[], usuario_id=u.usuario_id)
        ids.append(d.documento_id)
        print(f"  {titulo}: {r['fragmentos']} secciones, {r['con_huella']} con huella")
    for pregunta, esperada, n in PREGUNTAS:
        if not bd.scalar(select(PruebaPregunta).where(PruebaPregunta.pregunta == pregunta)):
            bd.add(PruebaPregunta(pregunta=pregunta, respuesta_esperada=esperada, documento_id=ids[n] if n is not None else None,
                                  debe_contestar=n is not None, area="EJEMPLO", creado_por=u.usuario_id))
    bd.commit()
    print("Listo. Para quitarlos: python -m scripts.ejemplos_metodos --quitar")


def quitar(bd: Session) -> None:
    for d in bd.scalars(select(Documento).where(Documento.titulo.like("EJEMPLO %"), Documento.estado == "vigente")):
        d.estado = "retirado"
    for p in bd.scalars(select(PruebaPregunta).where(PruebaPregunta.area == "EJEMPLO")):
        bd.delete(p)
    bd.commit()
    from modulos.metodos import indice

    indice.olvidar_cache()
    print("Ejemplos retirados.")


if __name__ == "__main__":
    with Session(motor()) as bd:
        quitar(bd) if "--quitar" in sys.argv else cargar(bd)
