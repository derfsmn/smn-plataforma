"""Catálogos iniciales del núcleo: módulos, permisos, roles y tareas de IA. Se puede correr varias veces.

No crea usuarios. El primer administrador se crea con: python -m scripts.crear_admin
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from nucleo.modelos import IaTarea, Modulo, Permiso, Rol, RolPermiso

MODULOS = [
    dict(codigo="compras", codigo_iniciativa="TD001", nombre="Inteligencia de Compras", area="Compras",
         descripcion="Semáforo con IA para decidir si un producto nuevo entra al catálogo.",
         tiene_portal_externo=True, orden_menu=10, icono="carrito"),
    dict(codigo="kiosco", codigo_iniciativa="TD002", nombre="Kiosco Digital", area="Tiendas",
         descripcion="Naturi, agente virtual con voz y texto que ayuda a encontrar productos en tienda.",
         tiene_portal_externo=False, orden_menu=30, icono="tienda"),
    dict(codigo="contraloria", codigo_iniciativa="TD003", nombre="Contraloría y Fiscal", area="Contraloría / Fiscal",
         descripcion="Procesos de Contraloría y obligaciones fiscales. Primer proceso: la DIOT.",
         tiene_portal_externo=False, orden_menu=40, icono="fiscal", estado="piloto"),
    dict(codigo="metodos", codigo_iniciativa="TD004", nombre="Métodos y procedimientos", area="Métodos y procedimientos",
         descripcion="Pregunta cómo se hace algo y recibe la respuesta con la cita del manual vigente; la IA local "
                     "redacta borradores de manuales.",
         tiene_portal_externo=False, orden_menu=50, icono="libro", estado="piloto"),
]

# (código, descripción, módulo o None si es de plataforma)
PERMISOS = [
    ("nucleo.usuarios.administrar", "Dar de alta, editar y desactivar usuarios", None),
    ("nucleo.roles.administrar", "Asignar permisos a los roles", None),
    ("nucleo.modulos.administrar", "Registrar módulos y cambiar su estado", None),
    ("nucleo.bitacora.ver", "Consultar la bitácora de acciones", None),
    ("nucleo.configuracion.administrar", "Cambiar la configuración de la plataforma (correo, archivos, IA)", None),
    ("nucleo.ia.administrar", "Configurar la puerta de IA, sus topes de gasto y ver su consumo", None),
    ("datos.productos.ver", "Ver el catálogo de productos del Centro de datos", None),
    ("datos.catalogo.administrar", "Cargar el catálogo de productos desde sus fuentes", None),
    ("datos.etl.ver", "Ver el ETL de ventas: avance de las cargas, historial y cuadre", None),
    ("datos.etl.correr", "Correr, detener y probar el ETL de ventas y cargar ventas con archivo", None),
    ("datos.proveedores.ver", "Ver los proveedores con su calificación y su ficha", None),
    ("datos.proveedores.calcular", "Recalcular la calificación de los proveedores", None),
    ("datos.tiendas.ver", "Ver el mapa de tiendas con su ubicación y su venta", None),
    ("datos.tiendas.calcular", "Recalcular los grupos de tiendas que venden parecido", None),
    ("datos.inventario.ver", "Ver la salud del inventario: dinero detenido, exceso y posibles faltantes", None),
    ("compras.solicitud.ver", "Ver solicitudes de producto nuevo", "compras"),
    ("compras.solicitud.evaluar", "Evaluar solicitudes y confirmar datos", "compras"),
    ("compras.semaforo.ajustar", "Ajustar el color sugerido con motivo", "compras"),
    ("compras.comite.decidir", "Registrar la decisión del Comité", "compras"),
    ("compras.comite.ver", "Ver el Comité de producto nuevo: reuniones, ciclo, decisiones y peticiones", "compras"),
    ("compras.comite.subir", "Subir productos al ciclo de una reunión del comité", "compras"),
    ("compras.comite.prefiltrar", "Abrir y cerrar reuniones del comité, hacer el pre-filtro y registrar las revisiones posteriores", "compras"),
    ("compras.solicitud.enviar", "Enviar propuestas de producto (proveedor)", "compras"),
    ("compras.radar.ver", "Ver el Radar de tendencias: reportes, histórico y tendencias", "compras"),
    ("compras.radar.decidir", "Decidir sobre hallazgos del radar: abrir iniciativa, vigilar o descartar", "compras"),
    ("compras.radar.administrar", "Administrar el radar: fuentes, temas, destinatarios, base de conocimiento y corridas", "compras"),
    ("compras.precios.ver", "Ver el Radar de precios: comparación con la competencia, productos y corridas", "compras"),
    ("compras.precios.administrar", "Administrar el Radar de precios: productos vigilados, coincidencias, vendedores y corridas", "compras"),
    ("compras.conocimiento.ver", "Ver la Base de conocimiento de Compras: políticas, reglas, pesos y casos", "compras"),
    ("compras.conocimiento.editar", "Escribir en la Base de conocimiento de Compras: políticas, reglas, pesos y casos", "compras"),
    ("compras.propuestas.ver", "Ver la bandeja de propuestas de productos nuevos que mandan los proveedores", "compras"),
    ("compras.propuestas.revisar", "Revisar propuestas de proveedores: marcarlas listas, regresarlas o rechazarlas", "compras"),
    ("compras.proveedores.invitar", "Invitar proveedores al portal para que propongan productos nuevos", "compras"),
    ("compras.productos.ver", "Ver el Radar de productos: evaluaciones con semáforo e ideas de producto", "compras"),
    ("compras.productos.evaluar", "Capturar ideas de producto, recalcular y corregir clasificación y parecidos", "compras"),
    ("compras.productos.ajustar", "Cambiar el color final del semáforo con motivo", "compras"),
    ("kiosco.naturi.usar", "Conversar con Naturi en el kiosco de la tienda", "kiosco"),
    ("contraloria.diot.ver", "Ver el proceso de la DIOT", "contraloria"),
    ("contraloria.diot.operar", "Preparar, revisar y cerrar la DIOT del mes", "contraloria"),
    ("contraloria.criterios.aprobar", "Aprobar criterios fiscales y cambiar catálogos y layout de la DIOT",
     "contraloria"),
    ("metodos.consultar", "Preguntar a los manuales de métodos y procedimientos y ver los vigentes", "metodos"),
    ("metodos.cargar", "Cargar manuales y versiones, pedir borradores a la IA, ver avisos, reporte y prueba", "metodos"),
    ("metodos.aprobar", "Aprobar borradores y retirar manuales (del área dueña) y correr la prueba de preguntas",
     "metodos"),
]

# (código, nombre, descripción, para, módulo, permisos)
ROLES = [
    ("admin", "Administrador de plataforma", "Administra usuarios, roles y módulos.", "interno", None,
     ["nucleo.usuarios.administrar", "nucleo.roles.administrar", "nucleo.modulos.administrar",
      "nucleo.bitacora.ver", "nucleo.ia.administrar", "nucleo.configuracion.administrar",
      "datos.productos.ver", "datos.catalogo.administrar", "datos.etl.ver", "datos.etl.correr",
      "datos.proveedores.ver", "datos.proveedores.calcular", "datos.tiendas.ver", "datos.tiendas.calcular",
      "datos.inventario.ver",
      "compras.radar.ver", "compras.radar.decidir", "compras.radar.administrar",
      "compras.precios.ver", "compras.precios.administrar", "compras.conocimiento.ver", "compras.conocimiento.editar",
      "compras.propuestas.ver", "compras.propuestas.revisar", "compras.proveedores.invitar",
      "compras.productos.ver", "compras.productos.evaluar", "compras.productos.ajustar",
      "compras.comite.ver", "compras.comite.subir", "compras.comite.prefiltrar", "compras.comite.decidir",
      "kiosco.naturi.usar", "contraloria.diot.ver", "contraloria.diot.operar", "contraloria.criterios.aprobar",
      "metodos.consultar", "metodos.cargar", "metodos.aprobar"]),
    ("compras_responsable", "Responsable de Compras", "Evalúa solicitudes y ajusta el semáforo.", "interno", "compras",
     ["compras.solicitud.ver", "compras.solicitud.evaluar", "compras.semaforo.ajustar",
      "compras.radar.ver", "compras.radar.decidir", "compras.precios.ver", "compras.conocimiento.ver",
      "compras.conocimiento.editar", "compras.propuestas.ver", "compras.propuestas.revisar", "compras.proveedores.invitar",
      "compras.productos.ver", "compras.productos.evaluar", "compras.productos.ajustar",
      "compras.comite.ver", "compras.comite.subir", "compras.comite.prefiltrar", "compras.comite.decidir",
      "datos.proveedores.ver", "datos.proveedores.calcular", "datos.tiendas.ver", "datos.tiendas.calcular",
      "datos.inventario.ver", "metodos.consultar"]),
    ("compras_comite", "Comité de Compras", "Revisa candidatos y registra la decisión.", "interno", "compras",
     ["compras.solicitud.ver", "compras.comite.decidir", "compras.radar.ver", "compras.radar.decidir",
      "compras.precios.ver", "compras.conocimiento.ver", "compras.conocimiento.editar",
      "compras.propuestas.ver", "compras.proveedores.invitar", "compras.productos.ver", "datos.proveedores.ver", "datos.tiendas.ver", "datos.inventario.ver",
      "compras.comite.ver",
      "metodos.consultar"]),
    ("compras_consulta", "Consulta de Compras", "Solo puede ver.", "interno", "compras",
     ["compras.solicitud.ver", "compras.radar.ver", "compras.precios.ver", "compras.conocimiento.ver",
      "compras.propuestas.ver", "compras.productos.ver", "datos.proveedores.ver", "datos.tiendas.ver", "datos.inventario.ver",
      "compras.comite.ver", "metodos.consultar"]),
    ("kiosco_tienda", "Kiosco de tienda", "Usuario del kiosco: solo conversa con Naturi.", "interno", "kiosco",
     ["kiosco.naturi.usar"]),
    ("contraloria_fiscal", "Contraloría / Fiscal", "Prepara, revisa y cierra la DIOT.", "interno", "contraloria",
     ["contraloria.diot.ver", "contraloria.diot.operar", "contraloria.criterios.aprobar", "metodos.consultar"]),
    ("metodos_consulta", "Consulta de manuales", "Pregunta a los manuales y ve los vigentes.", "interno", "metodos",
     ["metodos.consultar"]),
    ("metodos_responsable", "Responsable de manuales", "Carga y aprueba los manuales de su área y pide borradores a la IA.",
     "interno", "metodos", ["metodos.consultar", "metodos.cargar", "metodos.aprobar"]),
    ("proveedor", "Proveedor", "Envía propuestas y ve solo las suyas.", "externo", "compras",
     ["compras.solicitud.enviar"]),
]

# (código, descripción, módulo, proveedor[, modelo al crearla]). Cada módulo agrega aquí sus tareas al construirse.
TAREAS_IA = [
    ("nucleo.prueba", "Prueba de conexión desde Administración > IA", None, "ollama"),
    ("compras.radar_buscar", "Radar: buscar notas en internet (sitios sin RSS y temas)", "compras", "api"),
    ("compras.radar_clasificar", "Radar: decidir si una nota es relevante y clasificarla", "compras", "ollama_y_api_respaldo"),
    ("compras.radar_resumen", "Radar: agrupar en señales, elegir los hallazgos del día y redactar el reporte", "compras", "api"),
    ("compras.precios_coincidencia", "Radar de precios: elegir nuestro producto entre los resultados de Google Shopping", "compras", "ollama_y_api_respaldo"),
    ("compras.productos_clasificar", "Radar de productos: ubicar un producto nuevo en rama, subcategoría y segmento", "compras", "ollama_y_api_respaldo"),
    ("compras.productos_explicar", "Radar de productos: explicar en palabras simples el color del semáforo", "compras", "ollama_y_api_respaldo"),
    ("compras.productos_tendencia", "Radar de productos: elegir las señales del radar de tendencias que hablan de un producto nuevo", "compras", "ollama_y_api_respaldo"),
    ("compras.productos_politicas", "Radar de productos: revisar un producto nuevo contra las políticas y reglas de Compras", "compras", "api"),
    ("compras.oportunidades", "Radar de productos: recomendar productos que no tenemos y ya se venden (más vendidos, descontinuados, competencia)", "compras", "api"),
    ("compras.oportunidades_novedades", "Radar de productos: agente que busca en internet los más vendidos en México con su prueba de venta", "compras", "api"),
    ("datos.tiendas_grupos", "Grupos de tiendas: nombrar y explicar cada grupo de tiendas que venden parecido (solo IA local)", None, "ollama"),
    ("compras.precios_imagenes", "Radar de precios: comparar la foto de nuestro producto con las de Google para distinguir variantes (modelo con visión)", "compras", "ollama"),
    ("metodos.huella", "Métodos y procedimientos: huella de significado de cada sección de los manuales y de cada pregunta (solo IA local)", "metodos", "ollama", "bge-m3"),
    ("metodos.responder", "Métodos y procedimientos: contestar con cita usando solo los manuales vigentes (solo IA local)", "metodos", "ollama"),
    ("metodos.redactar", "Métodos y procedimientos: redactar borradores de manuales nuevos, versiones nuevas y formato estándar (solo IA local)", "metodos", "ollama"),
    ("metodos.contradicciones", "Métodos y procedimientos: avisar cuando dos manuales dicen cosas distintas sobre lo mismo (solo IA local)", "metodos", "ollama"),
]


def sembrar(bd: Session) -> None:
    modulos: dict[str, Modulo] = {}
    for datos in MODULOS:
        m = bd.scalar(select(Modulo).where(Modulo.codigo == datos["codigo"]))
        if not m:  # si ya existe no se toca: su estado lo administra la plataforma
            m = Modulo(**datos)
            bd.add(m)
        modulos[datos["codigo"]] = m
    bd.flush()

    permisos: dict[str, Permiso] = {}
    nuevos: set[str] = set()
    for codigo, descripcion, modulo in PERMISOS:
        p = bd.scalar(select(Permiso).where(Permiso.codigo == codigo))
        if not p:
            p = Permiso(codigo=codigo, descripcion=descripcion, modulo_id=modulos[modulo].modulo_id if modulo else None)
            bd.add(p)
            nuevos.add(codigo)
        permisos[codigo] = p
    bd.flush()

    for codigo, nombre, descripcion, para, modulo, suyos in ROLES:
        if existente := bd.scalar(select(Rol).where(Rol.codigo == codigo)):
            # Los permisos de un rol existente se administran desde la plataforma;
            # solo se le agregan los permisos que acaban de crearse y que este catálogo le da.
            bd.add_all(RolPermiso(rol_id=existente.rol_id, permiso_id=permisos[c].permiso_id) for c in suyos if c in nuevos)
            continue
        r = Rol(codigo=codigo, nombre=nombre, descripcion=descripcion, para_tipo_usuario=para,
                modulo_id=modulos[modulo].modulo_id if modulo else None)
        bd.add(r)
        bd.flush()
        bd.add_all(RolPermiso(rol_id=r.rol_id, permiso_id=permisos[c].permiso_id) for c in suyos)

    for codigo, descripcion, modulo, proveedor, *modelo in TAREAS_IA:
        if not (t := bd.scalar(select(IaTarea).where(IaTarea.codigo == codigo))):
            bd.add(IaTarea(codigo=codigo, descripcion=descripcion, proveedor_ia=proveedor,
                           modulo_id=modulos[modulo].modulo_id if modulo else None, modelo=modelo[0] if modelo else None))
        else:
            t.descripcion = descripcion  # la descripción la mantiene el código; el proveedor lo administra la plataforma
    bd.commit()

    from modulos.compras.semilla import sembrar_precios, sembrar_radar

    sembrar_radar(bd)
    sembrar_precios(bd)

    from modulos.contraloria.conocimiento_fiscal import sembrar as sembrar_fiscal

    sembrar_fiscal(bd)


def main() -> None:
    with Session(motor()) as bd:
        sembrar(bd)
    print("Catálogos del núcleo listos.")


if __name__ == "__main__":
    main()
