# deploy/obs-watchdog/ — piezas del watchdog de la PC de OBS

El watchdog **no vive en este repo**: corre en la PC de OBS (Linux) en
`/opt/obs-watchdog/`, arrancado por systemd (`obs-watchdog.service`, usuario
`obs-moldes`, `DISPLAY=:0`). Acá versionamos las piezas que agrega Fiboxito para
poder revisarlas en git y volver a aplicarlas si hace falta.

## `display_heal.sh`

Recupera el video cuando la PC arranca **sin monitor** (pantalla sin resolución
real + ventana de la cámara sin mapear → transmisión en negro con audio OK). Ver
el encabezado del script para el detalle. Es idempotente.

> El fix permanente REAL es el parámetro de kernel `video=DVI-D-1:1920x1080e` en
> GRUB (botón **"Fijar display permanente"** del panel, o `apply_display_grub_fix`
> en `routers/obs/service.py`). `display_heal.sh` queda como red de seguridad y
> como recuperación inmediata al boot, antes de que ese parámetro tome efecto.

### Instalación en la PC de OBS

1. Copiar `display_heal.sh` a `/opt/obs-watchdog/modules/display_heal.sh`
   (owner `obs-moldes`, `chmod +x`).
2. Enganchar en `/opt/obs-watchdog/watchdog.sh` (hacer backup antes):
   - Junto a los demás `source ...` de módulos:
     ```bash
     source /opt/obs-watchdog/modules/display_heal.sh
     ```
   - **Al arrancar**, antes del `while true` (cubre el arranque headless):
     ```bash
     display_heal   # recupera pantalla + ventana de cámara si booteó sin monitor
     ```
   - **Dentro del loop**, dentro del bloque `if [ "$USE_MPV_MODE" = "true" ]`,
     después de `mpv_check`/`mpv_restart` (red de seguridad en runtime):
     ```bash
     display_heal
     ```
3. Reiniciar el watchdog: `systemctl restart obs-watchdog` (o el botón del panel).

### Por qué el watchdog no lo agarraba solo

- `mpv_check.sh` valida que la ventana **exista** (`xdotool search`), no que esté
  **mapeada** → una ventana `IsUnMapped` pasaba el chequeo.
- `obs_video_check.sh` valida la conexión RTSP, que en el incidente estaba OK.

`display_heal.sh` tapa esos dos huecos.

## `publicidad.sh` (reemplazo)

Corre por cron (`29,59 * * * *`, usuario `obs-moldes`) y mete el bloque de
publicidad. **Ya no mata ni reinicia la cámara**: solo cambia a
`Escena_publicidad`, reproduce el video y vuelve a `Escena`. Antes usaba la tanda
como "refresco" de cámara (kill+restart de mpv), y eso dejaba la cámara en negro
dos veces por hora en la PC sin monitor (ventana nueva IsUnMapped).

Instalación: reemplazar `/opt/obs-watchdog/publicidad.sh` (backup del anterior).
El cron no cambia.

## `cambiar_fuente.sh` (fix de audio mudo tras el swap)

Es el script que hace el **cambio de fuente** por horario: lo llama
`schedule_runner.sh` (cron cada minuto) con `<fuente_vieja> <fuente_nueva>` cuando
un programa empieza o termina. Antes solo apagaba la fuente vieja y encendía la
nueva (`SetSceneItemEnabled`).

**Problema:** encender (hacer visible) una fuente de red no recupera el audio si su
conexión de red quedó muerta → la transmisión salía **muda** hasta togglearla a
mano. Diagnóstico (probado con `GetMediaInputStatus`): la fuente reporta
`mediaState=PLAYING` con el cursor avanzando, pero sin sonido real; el `reconnect`
de ffmpeg reconecta el contenedor y **no** devuelve el audio. Todo el estado de
audio (mute, volumen, monitor, tracks) es correcto e idéntico entre el estado mudo
y el sano, así que **no** es ruteo ni mezclador. No era un problema de tiempos del
swap (cada llamada a `obs_ws.py` ya tarda un par de segundos).

**Fix:** después de encender la fuente nueva, hacerle un **toggle off→on de
visibilidad** (lo mismo que se hacía a mano). Eso fuerza el ciclo
activa→inactiva→activa, que es lo ÚNICO que re-negocia la conexión con audio. Un
`TriggerMediaInputAction RESTART` **no** alcanza: reinicia la reproducción pero
mantiene la fuente activa, sin derribar la conexión muerta.

Las fuentes de la lista `STABLE_SOURCES` (por defecto `musica`) se saltean el
toggle: son estables (no de red) y nunca quedan mudas, así que no tiene sentido
meterles un corte al aire. Los swaps siempre son `musica ↔ programa`, o sea que en
la práctica el toggle solo corre al entrar a una radio. Si alguna radio se agregara
como estable por error, quedaría sin la recuperación; mantené la lista solo con
fuentes que de verdad nunca fallan.

Instalación en la PC de OBS: reemplazar `/opt/obs-watchdog/modules/cambiar_fuente.sh`
(backup del anterior, `owner obs-moldes`, `chmod +x`). No cambia el cron ni
`schedule_runner.sh`.

## `camara_refresh.sh` (nuevo, reemplaza el "refresco" de la publicidad)

Refresco real de la cámara **1x/día**: reinicia mpv (limpia congelamientos
"conectado pero frozen") y re-despliega la ventana con `display_heal`. Cubre lo
que antes hacía el kill de la publicidad, pero sin el negro recurrente.

Instalación en la PC de OBS:

1. Copiar a `/opt/obs-watchdog/camara_refresh.sh` (owner `obs-moldes`, `chmod +x`).
2. Agregar al crontab de `obs-moldes`:
   ```cron
   0 5 * * * /opt/obs-watchdog/camara_refresh.sh >> /opt/obs-watchdog/logs/publicidad-test.log 2>&1
   ```

> Nota: el refresco depende de que `display_heal` (windowactivate) funcione desde
> cron. Si fallara, el poller de Fiboxito (que corre por SSH, contexto probado)
> recupera la ventana en ≤30s igual.
