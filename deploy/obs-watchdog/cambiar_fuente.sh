#!/bin/bash

# cambiar_fuente.sh <fuente_actual> <fuente_nueva>
# Activa y desactiva fuentes dentro de una escena fija usando obs_ws.py
#
# FIX (audio mudo tras el swap): encender la fuente nueva NO recupera el audio si su
# conexión de red quedó muerta. Diagnóstico (probado por GetMediaInputStatus): la
# fuente reporta mediaState=PLAYING con el cursor avanzando, pero sin sonido real; el
# reconnect de ffmpeg reconecta el contenedor y NO devuelve el audio. Lo ÚNICO que lo
# recupera es un deactivate→reactivate completo de la fuente (el toggle de visibilidad).
# Un TriggerMediaInputAction RESTART NO alcanza: reinicia la reproducción pero mantiene
# la fuente activa, sin derribar la conexión muerta.
#
# Por eso, después de encender la fuente nueva, se le hace un toggle off→on (lo mismo
# que se hacía a mano desde el panel), que fuerza el ciclo activa→inactiva→activa y
# re-negocia la conexión con audio.

SCENE="Escena"   # escena fija donde están todas las fuentes
CURRENT="$1"
TARGET="$2"

LOG="/opt/obs-watchdog/logs/cambiar_fuente.log"
WS="/opt/obs-watchdog/modules/obs_ws.py"

# Margen entre pasos del toggle de recuperación, para que OBS registre el cambio de
# estado (activa/inactiva) antes del siguiente paso.
SETTLE=2

# Fuentes estables (no de red) que NO necesitan el toggle de recuperación: nunca
# quedan mudas. Se saltean para no meter un corte al aire innecesario. Separadas por espacio.
STABLE_SOURCES="musica"

is_stable() {  # $1=nombre de fuente → 0 si está en la lista de estables
    local s
    for s in $STABLE_SOURCES; do
        [ "$s" = "$1" ] && return 0
    done
    return 1
}

set_enabled() {  # $1=sceneItemId  $2=true|false
    python3 "$WS" SetSceneItemEnabled \
        "{\"sceneName\":\"$SCENE\",\"sceneItemId\":$1,\"sceneItemEnabled\":$2}" >> "$LOG" 2>&1
}

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cambio de fuente: $CURRENT -> $TARGET" >> "$LOG"

# ------------------------------------------------------------
# Obtener ID del item actual (para desactivarlo)
# ------------------------------------------------------------
if [ "$CURRENT" != "" ]; then
    OUT_CUR=$(python3 "$WS" GetSceneItemId "{\"sceneName\":\"$SCENE\",\"sourceName\":\"$CURRENT\"}" 2>&1)
    ID_CUR=$(echo "$OUT_CUR" | jq -r '.sceneItemId // empty')

    if [ "$ID_CUR" != "" ]; then
        set_enabled "$ID_CUR" false
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Advertencia: no se encontro ID para '$CURRENT'" >> "$LOG"
    fi
fi

# ------------------------------------------------------------
# Obtener ID del item nuevo (para activarlo)
# ------------------------------------------------------------
OUT_NEW=$(python3 "$WS" GetSceneItemId "{\"sceneName\":\"$SCENE\",\"sourceName\":\"$TARGET\"}" 2>&1)
ID_NEW=$(echo "$OUT_NEW" | jq -r '.sceneItemId // empty')

if [ "$ID_NEW" = "" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: no se encontro ID para '$TARGET'" >> "$LOG"
    exit 1
fi

# Encender la fuente nueva.
set_enabled "$ID_NEW" true

# ------------------------------------------------------------
# Toggle de recuperación de audio sobre la fuente nueva (solo si NO es estable):
# off → on fuerza el ciclo activa→inactiva→activa que re-negocia la conexión con audio.
# (Un RESTART del medio no alcanza; hace falta el deactivate/reactivate completo.)
# Las fuentes estables (musica) nunca quedan mudas → se saltea para no cortar al aire.
# ------------------------------------------------------------
if is_stable "$TARGET"; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] '$TARGET' es estable, sin toggle de recuperacion" >> "$LOG"
else
    sleep "$SETTLE"
    set_enabled "$ID_NEW" false
    sleep "$SETTLE"
    set_enabled "$ID_NEW" true
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Toggle de recuperacion de audio sobre '$TARGET' hecho" >> "$LOG"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cambio OK" >> "$LOG"
exit 0
