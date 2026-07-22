# Changelog — Fiboxito

Registro de cambios de Fiboxito, el asistente interno de Fibox (bot de Telegram).

Este documento está pensado para que cualquier persona que retome el proyecto
—o el propio equipo después de un tiempo— entienda **qué hace Fiboxito y cómo
fue creciendo**, sin necesidad de leer el código. Se describe el *para qué* de
cada función, no el *cómo* técnico.

Las fechas están en formato AAAA-MM-DD. Lo más nuevo va arriba.

---

## v1.2.0 — 2026-07-22

### Nuevas funcionalidades

- **Arranque automático y aviso de reactivación.**
  Si el equipo donde vive Fiboxito se reinicia (por ejemplo tras un corte de
  luz), Fiboxito **vuelve a ponerse en marcha solo** al iniciar sesión de
  Windows, sin que nadie tenga que abrir nada a mano. Al levantar, avisa por
  Telegram a los administradores con un mensaje de **"Fiboxito volvió a estar
  activo"** indicando el equipo y la hora, para que quede claro que ya está
  operando de nuevo.

---

## v1.1.0 — 2026-07-10

### Nuevas funcionalidades

- **Acceso al servidor de archivos interno (NAS).**
  Ahora Fiboxito puede entrar al servidor de archivos de la oficina para
  navegar carpetas, buscar y traer archivos, y guardar archivos nuevos.
  Se usa desde Telegram hablándole normal ("entrá a tal carpeta", "traeme tal
  archivo", "buscá tal cosa", "volvé atrás") o con el comando `/nas`.
  La conexión es privada y cifrada, y Fiboxito trabaja con un acceso
  **restringido**: solo ve las carpetas habilitadas y solo puede **guardar**
  archivos en una carpeta específica; en el resto es de solo lectura.

- **Planilla de comprobantes que se actualiza sola.**
  Cada comprobante de pago que Fiboxito evalúa queda registrado en una planilla
  de Excel dentro del servidor de archivos, con una fila por comprobante
  (los mismos datos que informa por Telegram, más fecha y mes para poder filtrar).
  La planilla se regenera sola con cada comprobante nuevo. Si en ese momento
  alguien la tiene abierta, Fiboxito no la pisa: espera y la pone al día cuando
  se libera, sin perder ningún dato ni arriesgar que el archivo se dañe.

- **Cortar y reactivar el servicio de un cliente.**
  Un administrativo puede pedirle a Fiboxito suspender la conexión de un cliente
  (por ejemplo, por falta de pago) y también reactivarla. Por tratarse de una
  acción que afecta el servicio real de una persona, **Fiboxito siempre pide
  confirmación antes de hacer nada**: primero avisa qué va a hacer y a quién, y
  recién ejecuta si se le responde que sí. Si el cliente tiene más de un
  contrato, los lista para que se elija cuál.

### Mejoras y correcciones

- **Conversación más natural en la navegación de archivos.**
  Fiboxito ahora aprovecha el contexto de los últimos mensajes: entiende
  referencias como "ese cliente" (tomándolo de lo que se venía hablando) y no
  reacciona de forma literal a cortesías como "gracias" o "perfecto" (antes,
  cualquier mensaje durante la navegación volvía a mostrar la carpeta).
  También mejoró el reconocimiento del nombre de archivo o carpeta cuando el
  pedido viene con palabras de relleno.

- **Convivencia entre las distintas funciones.**
  Se afinó la forma en que Fiboxito decide si un pedido es sobre clientes, sobre
  el canal de streaming (OBS) o sobre archivos, para que no se confundan entre
  sí (por ejemplo, un nombre de archivo que casualmente contenga una palabra
  usada en otro comando).

### Notas operativas

- El servidor de archivos se usa también como lugar para compartir material que
  no forma parte del código del proyecto. **Recomendación:** no dejar archivos
  con datos sensibles (contraseñas, credenciales) en las carpetas a las que
  Fiboxito tiene acceso.

---

## v1.0.0 — base del proyecto

Estado de Fiboxito antes de empezar este registro de cambios. Ya funcionaba
como bot de Telegram de uso interno, con acceso limitado a personas autorizadas,
y ofrecía:

- **Consultas de clientes** (por nombre o número): datos de contacto, saldo y
  cuenta corriente, estado del contrato y plan, y últimas facturas. Recuerda al
  cliente de la conversación para no repetir el número.

- **Facturas y PDF**: muestra las últimas facturas de un cliente y envía el PDF
  de la última directamente al chat.

- **IPs disponibles**: informa las direcciones libres por zona de red.

- **Análisis de comprobantes de pago**: al enviar la foto de un comprobante,
  verifica si es válido, si el destinatario es Fibox, y detecta monto y fecha,
  respondiendo OK / NO OK con el motivo. También funciona de forma automática
  cuando un cliente manda el comprobante por otro canal: Fiboxito lo evalúa,
  cierra la gestión correspondiente, detecta duplicados y avisa por Telegram.

- **Control del canal de streaming (OBS)**: iniciar/detener/reiniciar la
  transmisión, cambiar y silenciar fuentes de audio, reiniciar la cámara,
  sacar una captura del canal, ver registros, manejar el sistema de vigilancia
  que mantiene todo en línea, y reiniciar la PC del canal. Además envía alertas
  automáticas cuando la transmisión se cae o se recupera.
