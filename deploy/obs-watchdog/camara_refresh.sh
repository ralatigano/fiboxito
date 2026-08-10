#!/bin/bash
# camara_refresh.sh -- refresco real de la cámara, 1x/día.
#
# Reinicia mpv para limpiar posibles congelamientos "conectado pero frozen" (que
# el chequeo de conexión del watchdog no detecta), y RE-DESPLIEGA la ventana: en
# la PC arrancada sin monitor la ventana nueva de mpv queda IsUnMapped y hay que
# pasarla a IsViewable (windowactivate) para que OBS la capture.
#
# Reemplaza al "refresco" que antes hacía publicidad.sh dos veces por hora.
# Cron sugerido (usuario obs-moldes): 0 5 * * *  (05:00, bajo impacto).
#
# Red de seguridad: aunque acá el re-despliegue fallara, el poller de Fiboxito
# (que corre por SSH) detecta la ventana sin desplegar y la recupera en <=30s.

LOG="/opt/obs-watchdog/logs/watchdog.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [camara_refresh] $1" >> "$LOG"
}

source /opt/obs-watchdog/modules/mpv_restart.sh
source /opt/obs-watchdog/modules/display_heal.sh

log "Refresco diario de cámara: reiniciando mpv..."
mpv_restart
sleep 3
display_heal
log "Refresco diario de cámara: hecho."
