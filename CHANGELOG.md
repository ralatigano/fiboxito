# Changelog — Fiboxito

Registro de cambios de Fiboxito, el asistente interno de Fibox (bot de Telegram).

Este documento está pensado para que cualquier persona que retome el proyecto
—o el propio equipo después de un tiempo— entienda **qué hace Fiboxito y cómo
fue creciendo**, sin necesidad de leer el código. Se describe el *para qué* de
cada función, no el *cómo* técnico.

Las fechas están en formato AAAA-MM-DD. Lo más nuevo va arriba.

---

## v1.7.0 — 2026-09-07

### El panel ya administra las radios y muestra la agenda del canal

- **Se pueden dar de alta radios nuevas desde el panel.** Hasta ahora, para sumar
  una radio (como FM Espacio o Radio San Nicolás) había que sentarse en la PC del
  canal y crear la fuente a mano dentro de OBS. Ahora la tarjeta **"Radios"** del
  panel tiene un botón **"Agregar"**: se carga el nombre y la dirección del stream,
  y la radio queda lista para usarse y para programarse. También se pueden **editar**
  (cambiar la dirección o el nombre) y **eliminar**.
- **Antes de guardar se puede probar la dirección.** El botón **"Probar URL"** hace
  que la PC del canal se conecte de verdad a esa radio y avise si suena, con qué
  calidad y en cuántos canales. Sirve para no descubrir recién al aire que la
  dirección estaba mal. Es la única prueba confiable: una vez creada, la fuente
  puede "figurar" reproduciendo aunque no salga sonido.
- **Si se le cambia el nombre a una radio, los programas la siguen.** Los horarios
  identifican a la radio por su nombre, así que renombrarla desde OBS rompía la
  programación en silencio. El panel ahora actualiza solo los programas que la usan.
- **Eliminar una radio programada pide confirmación.** El panel avisa en qué
  programas está usada y, si se confirma igual, los saca de la agenda junto con
  la radio. La radio por defecto (la que suena cuando no hay ningún programa al
  aire) no se puede borrar. Si la radio estaba al aire en ese momento, el canal
  vuelve a la fuente por defecto antes de eliminarla, para no quedarse mudo.

- **Nueva vista de agenda semanal.** El panel suma una grilla de lunes a domingo
  con los programas dibujados en su horario, cada uno con el color de su radio.
  Es la misma vista de calendario que tenía el panel de escritorio viejo, ahora en
  el navegador. Se ve de un vistazo qué suena cada día y a qué hora, con una línea
  roja marcando el momento actual. Los programas que cruzan la medianoche se
  muestran partidos entre los dos días, que es como realmente funcionan.
- **Los programas se administran desde ahí mismo.** Tocando un bloque se abre el
  formulario para cambiarle el nombre, la radio, los horarios o los días, o para
  eliminarlo; y el botón "Nuevo programa" agrega uno. Los cambios se guardan
  directo en la PC del canal.
- **El panel no deja guardar una programación que rompería el canal.** El cambio de
  radio lo hace la PC del canal en el minuto exacto en que un programa empieza o
  termina, así que dos programas pegados o superpuestos la dejaban en la radio
  equivocada. Ahora avisa antes de guardar si dos programas se pisan (contemplando
  los que cruzan la medianoche y los que arrancan un domingo y siguen el lunes), si
  falta un dato, o si apunta a una radio que ya no existe en OBS.
- **La programación se guarda de forma segura.** El archivo de horarios de la PC del
  canal se escribe de una sola vez y se verifica antes de reemplazar el anterior,
  del que además queda una copia. Antes, una escritura a medias podía dejar el
  canal sin cambios de radio automáticos sin que nadie se enterara.
- **La lista de fuentes quedó más clara.** Las radios tienen su propia tarjeta, con
  la dirección de cada una y sus acciones; el resto de los elementos de la escena
  (cámara, reloj, clima, carrusel) pasó a una sección aparte que se despliega.

---

## v1.6.5 — 2026-09-01

### Se destraba la habilitación de ONT (autorización)

- **Ya se puede cerrar la instalación autorizando la ONT desde Fiboxito.** El paso
  final —autorizar la ONT contra el contrato— venía fallando y había quedado en
  pausa esperando a soporte de Wispro. Se confirmó que **no era un problema de la
  cuenta, sino un error en la documentación**: la dirección a la que había que
  pedirlo estaba mal publicada. Con la dirección correcta, la autorización ya se
  envía bien. El resto del flujo (elegir ciudad, contrato, ONT y confirmar) ya
  venía funcionando. Queda por validar en una instalación real.

---

## v1.6.4 — 2026-09-01

### Se corrige el audio mudo al cambiar de fuente

- **Al cambiar de programa, la radio entrante podía quedar sin sonido.** Cuando el
  canal pasaba automáticamente de la música a una radio (o entre programas), a veces
  la radio salía **muda al aire**, y había que apagar y volver a prender esa fuente
  a mano para que el sonido volviera. Se descubrió que la radio "creía" estar
  sonando, pero su conexión con el stream se había cortado sin avisar; reiniciar la
  reproducción no alcanzaba: solo apagar y prender la fuente la reconectaba de verdad.
- **Ahora el cambio de fuente hace esa reconexión solo.** Al encender una radio, el
  sistema repite automáticamente el "apagar y prender" que antes se hacía a mano, así
  que la radio arranca siempre con sonido. La música, que nunca se queda muda, se
  saltea este paso para no meter un corte innecesario al aire.

---

## v1.6.3 — 2026-08-26

### Se corrige el falso aviso de "radio sin sonido"

- **El aviso de radio con error saltaba en falso.** El diagnóstico buscaba la
  palabra "401" en el registro de OBS para detectar una radio caída, pero "401"
  es demasiado corto y aparecía por casualidad en números internos del registro
  (puertos y milisegundos de las propias conexiones del diagnóstico). Resultado:
  la advertencia aparecía una y otra vez aunque **nunca hubiera un problema real**
  de audio. Ahora la búsqueda es precisa: solo detecta errores HTTP de verdad
  (autenticación/acceso al stream), así que el aviso deja de aparecer por ruido.
- **Además, solo avisa por fallas *nuevas*.** Fiboxito recuerda hasta dónde había
  mirado el registro la última vez y solo reporta lo que pasó **desde el
  diagnóstico anterior**, para no repetir un aviso por algo viejo ya resuelto.
  Vale tanto para el chequeo automático como para el que se pide a mano.
- **El aviso muestra la hora exacta de la falla**, tomada del registro.

---

## v1.6.2 — 2026-08-13

### La habilitación de ONT ya ve la lista en tiempo real

- **Se resolvió el problema del "listado viejo" al habilitar una ONT.** Wispro
  entregaba la lista de ONT desde una copia guardada (caché), así que la ONT
  recién instalada podía tardar en aparecer o directamente no figurar hasta que
  alguien apretaba "actualizar" en el panel. Ahora Fiboxito le pide a Wispro que
  vuelva a mirar la OLT en el momento (igual que ese botón "actualizar"), de modo
  que la lista siempre está al día. Puede tardar unos segundos más, pero muestra
  lo que la OLT ve de verdad.

- **Confirmación automática después de habilitar.** Una vez enviada la
  autorización, Fiboxito responde al toque ("la mandé, estoy verificando") y
  sigue chequeando la OLT en segundo plano —porque la OLT tarda cerca de un
  minuto en reflejar el cambio—. Cuando la ONT queda autorizada, avisa con un
  segundo mensaje; si después de un rato todavía no figura, lo dice y sugiere
  revisar con `/onts`. Mientras verifica, el bot sigue atendiendo normalmente al
  resto.

---

## v1.6.1 — 2026-08-11

### Diagnóstico cuando una ONT no aparece al habilitarla

- **Nuevo comando `/onts <ciudad>` para ver TODAS las ONT que ve la OLT.** Al
  habilitar una instalación, a veces la ONT que se busca no figura en la lista
  porque quedó autorizada en la OLT pero sin vincular a un contrato (un intento
  anterior que se cortó a la mitad). El paso normal solo muestra las ONT *sin
  autorizar*, así que esas quedaban invisibles. Ahora, con `/onts moldes` (o
  `/onts moldes <parte del serial>`) se puede ver la lista completa, separando
  autorizadas de no autorizadas, para confirmar si la OLT la está viendo y con
  qué estado. Cuando el flujo no encuentra ONT nueva, Fiboxito sugiere este
  comando.

- **Más detalle en el registro interno** durante la habilitación de ONT, para
  poder revisar después qué respondió la OLT en cada intento.

---

## v1.6.0 — 2026-08-10

### Recuperar el canal cuando hay audio pero la imagen sale negra

- **Nuevo botón "Recuperar video" en el panel de OBS.** A veces la PC del canal
  se reinicia y arranca sin un monitor conectado; cuando eso pasa, la
  transmisión sigue al aire con sonido pero **la imagen sale en negro**. Ahora,
  con un toque, Fiboxito vuelve a poner la pantalla en orden y re-muestra la
  cámara, sin tener que ir hasta la PC ni conectarle un monitor.

- **Fiboxito lo detecta y lo corrige solo.** Aunque nadie toque el botón, el
  monitoreo del canal reconoce esta falla de "imagen en negro" y la recupera
  automáticamente, avisando por Telegram que lo resolvió.

- **Nuevo botón "Fijar display permanente".** Deja la PC del canal preparada
  para que **nunca más** quede sin imagen si arranca sin monitor. Se aplica una
  sola vez y queda listo a partir del próximo reinicio. (La solución más a
  prueba de todo sigue siendo dejar enchufado un monitor o un adaptador que lo
  simule.)

- **La tanda de publicidad ya no interrumpe la cámara.** Antes, cada bloque de
  publicidad reiniciaba la cámara por detrás (un viejo truco para destrabar
  congelamientos); en la PC sin monitor eso dejaba la imagen en negro al volver.
  Ahora la publicidad solo cambia de escena y vuelve, sin tocar la cámara. El
  refresco de cámara pasó a hacerse **una vez por día** en horario de bajo
  impacto.

---

## v1.5.1 — 2026-08-06

### La lista de contratos recientes ahora sí coincide con Wispro

- **Al habilitar una ONT, los altas que ofrece Fiboxito son los mismos que se
  ven en el panel.** Antes, la lista de "contratos recientes" de una ciudad se
  quedaba con altas de hace semanas y **no mostraba los más nuevos** (por
  ejemplo, un cliente dado de alta ese mismo día no aparecía y había que tipear
  el número a mano). Se corrigieron dos cosas: Fiboxito ahora **recorre toda la
  ventana de altas** en vez de una sola tanda, y **reconoce a qué ciudad
  pertenece cada contrato por el servidor/OLT que tiene asignado** —un dato que
  el sistema completa solo— en lugar de fiarse del texto de la dirección, que a
  veces viene incompleto o cargado como "Salta". Resultado: la lista de altas
  recientes coincide con la del panel de Wispro.

---

## v1.5.0 — 2026-08-05

### Habilitar una ONT al cerrar la instalación

- **El técnico habilita la ONT desde Telegram, sin tocar Wispro.**
  Cuando se termina de instalar el servicio en el domicilio, ahora se puede
  cerrar la instalación pidiéndole a Fiboxito "vamos a habilitar una ONT en
  Moldes" (o `/habilitar_ont moldes`). Para no tener que recordar números,
  Fiboxito **muestra los altas recientes de esa ciudad** (nombre del cliente y
  número de contrato) para elegir con un toque —o se puede escribir el nombre
  del cliente—. Después **lee de la OLT las ONT nuevas** (las que todavía no
  están autorizadas) y muestra cuál ve, así **no** hay que copiar a mano el
  serial ni la interfaz (se comparan con la foto del técnico). Antes de autorizar
  muestra un resumen y **pide confirmación**. Funciona para las OLT de Coronel
  Moldes y Cerrillos.

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
