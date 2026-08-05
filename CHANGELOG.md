# Changelog — Fiboxito

Registro de cambios de Fiboxito, el asistente interno de Fibox (bot de Telegram).

Este documento está pensado para que cualquier persona que retome el proyecto
—o el propio equipo después de un tiempo— entienda **qué hace Fiboxito y cómo
fue creciendo**, sin necesidad de leer el código. Se describe el *para qué* de
cada función, no el *cómo* técnico.

Las fechas están en formato AAAA-MM-DD. Lo más nuevo va arriba.

---

## v1.5.0 — 2026-08-05

### Habilitar una ONT al cerrar la instalación

- **El técnico habilita la ONT desde Telegram, sin tocar Wispro.**
  Cuando se termina de instalar el servicio en el domicilio, ahora se puede
  cerrar la instalación pidiéndole a Fiboxito "vamos a habilitar una ONT en
  Moldes" (o `/habilitar_ont moldes`). Fiboxito pregunta el número de contrato
  y **lee de la OLT las ONT nuevas** (las que todavía no están autorizadas),
  mostrando cuál ve para que el técnico elija —así **no** tiene que copiar a mano
  el serial ni la interfaz—. Antes de autorizar muestra un resumen y **pide
  confirmación**. Funciona para las OLT de Coronel Moldes y Cerrillos.

- **Nuevo comando `/olts`.** Lista las OLT del sistema para la configuración
  inicial (uso de administrador).

### Diagnóstico del canal por Telegram (automático y a pedido)

- **Fiboxito revisa la salud del canal solo, cada tanto.**
  Además del botón "Diagnóstico" del panel, ahora Fiboxito ejecuta ese mismo
  chequeo **automáticamente cada cierta cantidad de horas** (arranca en 4) y
  manda el resultado a los administradores por Telegram, con el semáforo y el
  detalle en castellano. La idea es **medir la salud de la transmisión** a lo
  largo del día sin que nadie tenga que acordarse de mirar. La frecuencia (y si
  se avisa siempre o solo cuando hay algo para mirar) se ajusta desde la config.

- **También se puede pedir el diagnóstico en cualquier momento.**
  Con `/obs diagnostico` o pidiéndolo en lenguaje natural ("chequeá el canal",
  "¿está todo bien?"), Fiboxito corre la revisión al toque y la devuelve por
  chat.

### Fiboxito entiende mejor las frases mixtas

- **Menos confusiones al interpretar un pedido.**
  Antes, ciertas frases se malinterpretaban por una sola palabra: por ejemplo,
  "volvé a activar la fuente RadioFMEspacio" se tomaba como "volver atrás" en la
  navegación de archivos y Fiboxito respondía con la lista de carpetas del
  servidor, en vez de reactivar la fuente. Ahora Fiboxito **pesa la frase
  completa**: si algo es claramente del canal (una fuente, la transmisión, la
  cámara), gana eso aunque haya una palabra de navegación; y si un pedido queda
  genuinamente ambiguo, **lo desambigua con ayuda del modelo** en vez de acumular
  reglas fijas. Los pedidos claros siguen resolviéndose al instante, sin costo
  extra. También se ajustó la navegación de archivos para que una orden clara del
  canal o de un cliente **corte** la navegación en curso.

### Mejoras del panel de OBS

- **Reloj de fecha y hora en el panel.**
  El encabezado ahora muestra la **fecha y hora actual**, actualizándose segundo
  a segundo. Sirve de referencia para leer los demás datos con hora que muestra
  la pantalla (como el momento en que se corrió el diagnóstico o los registros).

- **El diagnóstico indica a qué hora se ejecutó.**
  El resultado del diagnóstico ahora dice **"ejecutado a las HH:MM:SS"**, para
  saber con certeza a qué momento corresponde la revisión.

- **Ampliar y descartar la captura de pantalla.**
  La captura del canal se veía muy chica. Ahora se puede **ampliar a pantalla
  completa** (tocando la imagen o el botón "Ampliar") para apreciarla bien, y
  **descartarla** para dejar limpia la tarjeta cuando ya no se necesita.

---

## v1.4.0 — 2026-08-03

### Nuevas funcionalidades

- **Botón "Diagnóstico" en el panel de OBS.**
  El panel ya mostraba el estado y botones para operar la transmisión, pero
  cuando algo fallaba había que interpretar registros técnicos para entender
  qué pasaba. Ahora hay un botón **"Diagnóstico"** que revisa la PC del canal
  y devuelve, **en castellano claro**, un resumen con semáforo: qué está bien
  (🟢), qué conviene mirar (🟡) y qué es un problema serio (🔴), junto con
  **qué botón tocar** en cada caso. Chequea de una sola pasada la transmisión
  (si está realmente saliendo al aire o solo "figura" activa), si hay OBS o
  cámara duplicados o trabados, si el vigilante (watchdog) está activo, si la
  cámara está conectada, si alguna radio se quedó sin audio y si la PC está
  sobrecargada o sin espacio. No cambia nada en la PC: solo mira y traduce.
  Pensado para que cualquiera pueda entender qué pasa sin saber de consolas.

- **Los hallazgos del diagnóstico traen el botón para resolverlos.**
  Cuando el diagnóstico detecta algo que se arregla con una acción que el panel
  ya sabe hacer (reiniciar OBS, la cámara, el watchdog o la PC), muestra ese
  **botón dentro del mismo aviso**, para resolverlo ahí sin buscar en otra
  parte. Al usarlo, vuelve a diagnosticar solo para mostrar el resultado.

- **Confirmación real de cada botón del panel (no solo "enviado").**
  Antes, al tocar un botón, el panel confirmaba que el comando **se había
  mandado**, pero no si la PC del canal realmente lo había hecho. Ahora el
  feedback es en dos pasos: primero avisa "enviado, verificando…" y unos
  segundos después vuelve a mirar el estado real y muestra el resultado con
  semáforo — 🟢 salió bien, 🟡 quedó a medias (por ejemplo, al aire pero
  reconectando) o 🔴 no se pudo confirmar. Además, el estado del canal ahora
  distingue "al aire" de "reconectando", que antes se veían igual.

- **Visor de logs "en vivo" con controles de reproductor.**
  El visor de logs del panel pasó de sacar una "foto" por clic a un modo en
  vivo con botones ▶ / ⏸ / ⏹. Elegís qué log ver (watchdog, OBS o cámara) y
  con ▶ se actualiza solo cada pocos segundos, mostrando un indicador
  "● EN VIVO"; ⏸ lo congela y ⏹ lo detiene. Para no cargar de más la conexión
  con la PC del canal, solo consulta mientras la ventana está abierta y a la
  vista, y se frena al pausar, detener o cambiar de pestaña.

- **Captura de "lo que sale al aire", más rápida y limpia.**
  Además de la captura del escritorio de la PC (la que ya existía), el panel
  suma una captura del **programa de OBS** —es decir, lo que realmente se está
  transmitiendo—, que sale al instante y sin los cortes o "ventanas dobles" que
  a veces tenía la anterior. Quedan los dos botones: **"Ver al aire"** (rápida
  y limpia, para el día a día) y **"Ver pantalla real"** (el escritorio de la
  PC, que sigue sirviendo aunque OBS esté trabado y no responda).

---

## v1.3.0 — 2026-08-03

### Nuevas funcionalidades

- **Aviso cuando la PC de transmisión se cae o se reinicia.**
  Hasta ahora, si la PC que hace el streaming se apagaba, reiniciaba o quedaba
  colgada, Fiboxito **no avisaba nada** (solo detectaba problemas si podía
  contactarla). Ahora, si la PC queda **inalcanzable** por unos minutos, manda
  un aviso por Telegram de que la transmisión puede estar caída, y otro cuando
  **vuelve**. Además detecta cuando la PC **se reinició** (aunque haya sido un
  reinicio rápido) y lo informa. Está pensado para no llenar de mensajes: avisa
  una sola vez por evento. Esto da visibilidad si alguna vez la PC entrara en un
  ciclo de reinicios.

- **Auto-recuperación ante fallas de la placa de video.**
  La placa de video de la PC de streaming puede "colgarse" y dejar la
  transmisión congelada (fue la causa de una caída larga). Ahora Fiboxito
  **vigila los síntomas** de ese cuelgue en la PC y, si además la transmisión
  se cortó, **reinicia la PC solo** para recuperarla, avisando por Telegram. Si
  la transmisión sigue al aire, solo avisa (no reinicia de más). Tiene un
  **tope de seguridad**: si hiciera falta reiniciar demasiadas veces en poco
  tiempo (señal de una falla más seria), deja de reiniciar y pide intervención
  manual, para no entrar en un ciclo de reinicios.

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
