#!/bin/bash
# publicidad.sh -- muestra el bloque de publicidad SIN tocar la cámara.
#
# Antes, este script mataba mpv (`pkill`) y lo reiniciaba al final, usando la
# tanda de publicidad como "refresco" de la cámara para limpiar congelamientos.
# El problema: en la PC arrancada sin monitor, cada reinicio de mpv crea una
# ventana nueva que queda IsUnMapped -> OBS la captura en negro. Como los
# congelamientos ya no se están viendo, se desacopló: la publicidad NO toca la
# cámara, y el refresco real quedó en un job aparte 1x/día (camara_refresh.sh).
#
# Cron (usuario obs-moldes): 29,59 * * * *  (dos veces por hora).

LOG="/opt/obs-watchdog/logs/watchdog.log"
OBS_WS="/opt/obs-watchdog/modules/obs_ws.py"
ESCENA_NORMAL="Escena"
ESCENA_PUBLICIDAD="Escena_publicidad"
VIDEO_DURACION=58  # segundos (57s del video + 1s de margen)

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [publicidad] $1" >> "$LOG"
}

log "Iniciando bloque de publicidad..."

# 1. Cambiar a la escena de publicidad (la cámara/mpv sigue corriendo de fondo).
python3 "$OBS_WS" SetCurrentProgramScene "{\"sceneName\":\"$ESCENA_PUBLICIDAD\"}" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    log "ERROR: no se pudo cambiar a escena de publicidad. Abortando."
    exit 1
fi
log "Cambiado a $ESCENA_PUBLICIDAD"

# 2. Reiniciar el video de publicidad para que empiece desde el principio.
sleep 1
python3 "$OBS_WS" TriggerMediaInputAction \
    '{"inputName":"video_publicidad","mediaAction":"OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART"}' \
    > /dev/null 2>&1

# 3. Esperar que termine el video.
log "Esperando $VIDEO_DURACION segundos..."
sleep $VIDEO_DURACION

# 4. Volver a la escena normal (la cámara ya estaba viva y mapeada).
python3 "$OBS_WS" SetCurrentProgramScene "{\"sceneName\":\"$ESCENA_NORMAL\"}" > /dev/null 2>&1
log "Vuelto a $ESCENA_NORMAL. Bloque de publicidad finalizado."
