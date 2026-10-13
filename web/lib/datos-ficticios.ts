// DATOS FICTICIOS para el prototipo visual (etapa 2). No representan personas ni cifras reales de SMN.
// En la etapa 3 se reemplazan por la API (/api/nucleo/...).

export type EstadoModulo = "en_diseno" | "piloto" | "activo" | "retirado";

export type Modulo = {
  codigo: string;
  iniciativa: string;
  nombre: string;
  area: string;
  descripcion: string;
  estado: EstadoModulo;
  responsable: string;
  tienePortalExterno: boolean;
  icono: "carrito" | "personas" | "radar" | "mas";
};

export const modulos: Modulo[] = [
  {
    codigo: "compras",
    iniciativa: "TD001",
    nombre: "Inteligencia de Compras",
    area: "Compras",
    descripcion: "Semáforo con IA para decidir si un producto nuevo entra al catálogo.",
    estado: "en_diseno",
    responsable: "Diego Rodríguez",
    tienePortalExterno: true,
    icono: "carrito",
  },
  {
    codigo: "rrhh",
    iniciativa: "Por asignar",
    nombre: "Reclutamiento digital",
    area: "Recursos Humanos",
    descripcion: "Postulación a vacantes por tienda con QR y seguimiento.",
    estado: "en_diseno",
    responsable: "Diego Rodríguez",
    tienePortalExterno: true,
    icono: "personas",
  },
];

export const estadoModulo: Record<EstadoModulo, { texto: string; clase: string }> = {
  en_diseno: { texto: "En diseño", clase: "bg-smn-gris-100 text-smn-gris-700" },
  piloto: { texto: "Piloto", clase: "bg-smn-naranja/15 text-aviso-texto" },
  activo: { texto: "Activo", clase: "bg-tinta text-superficie" },
  retirado: { texto: "Retirado", clase: "bg-smn-gris-100 text-smn-gris-500 line-through" },
};

export type Rol = { id: string; nombre: string; descripcion: string; para: "interno" | "externo"; permisos: string[] };

export const permisos: { codigo: string; descripcion: string; modulo: string }[] = [
  { codigo: "nucleo.usuarios.administrar", descripcion: "Dar de alta, editar y desactivar usuarios", modulo: "Plataforma" },
  { codigo: "nucleo.roles.administrar", descripcion: "Crear roles y asignar permisos", modulo: "Plataforma" },
  { codigo: "nucleo.modulos.administrar", descripcion: "Registrar módulos y cambiar su estado", modulo: "Plataforma" },
  { codigo: "compras.solicitud.ver", descripcion: "Ver solicitudes de producto nuevo", modulo: "Compras" },
  { codigo: "compras.solicitud.evaluar", descripcion: "Evaluar solicitudes y confirmar datos", modulo: "Compras" },
  { codigo: "compras.semaforo.ajustar", descripcion: "Ajustar el color sugerido con motivo", modulo: "Compras" },
  { codigo: "compras.comite.decidir", descripcion: "Registrar la decisión del Comité", modulo: "Compras" },
  { codigo: "compras.solicitud.enviar", descripcion: "Enviar propuestas de producto (proveedor)", modulo: "Compras" },
];

export const roles: Rol[] = [
  {
    id: "admin",
    nombre: "Administrador de plataforma",
    descripcion: "Administra usuarios, roles y módulos.",
    para: "interno",
    permisos: ["nucleo.usuarios.administrar", "nucleo.roles.administrar", "nucleo.modulos.administrar"],
  },
  {
    id: "resp-compras",
    nombre: "Responsable de Compras",
    descripcion: "Evalúa solicitudes y ajusta el semáforo.",
    para: "interno",
    permisos: ["compras.solicitud.ver", "compras.solicitud.evaluar", "compras.semaforo.ajustar"],
  },
  {
    id: "comite",
    nombre: "Comité de Compras",
    descripcion: "Revisa candidatos y registra la decisión.",
    para: "interno",
    permisos: ["compras.solicitud.ver", "compras.comite.decidir"],
  },
  {
    id: "consulta",
    nombre: "Consulta",
    descripcion: "Solo puede ver.",
    para: "interno",
    permisos: ["compras.solicitud.ver"],
  },
  {
    id: "proveedor",
    nombre: "Proveedor",
    descripcion: "Envía propuestas y ve solo las suyas.",
    para: "externo",
    permisos: ["compras.solicitud.enviar"],
  },
];

export type Usuario = {
  id: number;
  nombre: string;
  correo: string;
  tipo: "interno" | "externo";
  area: string;
  roles: string[];
  estatus: "activo" | "invitado" | "inactivo";
  ultimoAcceso: string;
};

export const usuarios: Usuario[] = [
  { id: 1, nombre: "Diego Rodríguez", correo: "diego@ejemplo.mx", tipo: "interno", area: "Transformación Digital", roles: ["admin"], estatus: "activo", ultimoAcceso: "Hoy" },
  { id: 2, nombre: "Laura Méndez (ficticia)", correo: "laura@ejemplo.mx", tipo: "interno", area: "Compras", roles: ["resp-compras"], estatus: "activo", ultimoAcceso: "Ayer" },
  { id: 3, nombre: "Jorge Salas (ficticio)", correo: "jorge@ejemplo.mx", tipo: "interno", area: "Dirección", roles: ["comite"], estatus: "invitado", ultimoAcceso: "Nunca" },
  { id: 4, nombre: "Ana Torres (ficticia)", correo: "ana@ejemplo.mx", tipo: "interno", area: "Compras", roles: ["consulta"], estatus: "inactivo", ultimoAcceso: "Hace 95 días" },
  { id: 5, nombre: "Proveedor Ejemplo S.A. de C.V.", correo: "contacto@proveedor-ejemplo.mx", tipo: "externo", area: "Proveedor", roles: ["proveedor"], estatus: "activo", ultimoAcceso: "Hace 3 días" },
];

export const rolPorId = (id: string) => roles.find((r) => r.id === id);
