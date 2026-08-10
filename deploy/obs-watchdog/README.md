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
