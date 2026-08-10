#!/bin/bash
# display_heal.sh -- recupera el video cuando la PC de OBS arranca SIN monitor.
#
# Contexto: sin monitor la GPU no engancha resolución (no hay EDID) y X queda en un
# framebuffer fantasma de baja resolución que no renderiza -> la transmisión sale en
# negro (con audio OK). Además la ventana de la cámara (mpv) puede quedar IsUnMapped
# -> OBS captura por XComposite y una ventana sin mapear no tiene pixmap -> negro,
# aunque la cámara esté conectada.
#
# Este módulo:
#   1) fuerza un modo 1080p en una salida si la pantalla no tiene resolución real.
#   2) mapea la ventana de la cámara si quedó sin desplegar.
# Es idempotente: si ya está sano, no toca nada.
#
# OJO: es un parche en runtime. El fix permanente REAL es el parámetro de kernel
# `video=DVI-D-1:1920x1080e` en GRUB (botón "Fijar display permanente" del panel, o
# `apply_display_grub_fix` en routers/obs/service.py). Con eso el arranque headless ya
# no necesita este módulo. Se mantiene como red de seguridad.
#
# Se instala en /opt/obs-watchdog/modules/ en la PC de OBS y lo llama watchdog.sh.
# Ver README.md de este directorio.

DH_LOG="/opt/obs-watchdog/logs/watchdog.log"
DH_MODE="1920x1080_60"
DH_MODELINE="173.00 1920 2048 2248 2576 1080 1083 1088 1125 -hsync +vsync"
DH_OUTPUTS="DVI-D-1 HDMI-1 DP-1 DVI-I-1"
DH_CAM="CAMARA"

export DISPLAY=:0
export XAUTHORITY=/home/obs-moldes/.Xauthority

_dh_log() { echo "$(date '+%Y-%m-%d %H:%M:%S') display_heal: $1" >> "$DH_LOG"; }

_dh_width() { xrandr --query 2>/dev/null | sed -n 's/.*current \([0-9]\+\) x .*/\1/p'; }

display_heal() {
    # 1) Modo de pantalla: si el ancho no llega a 1920, forzar 1080p.
    local w; w=$(_dh_width)
    if [ -z "$w" ] || [ "$w" -lt 1920 ]; then
        _dh_log "pantalla sin modo real (ancho=${w:-?}); forzando 1080p..."
        xrandr --newmode "$DH_MODE" $DH_MODELINE 2>/dev/null   # error si ya existe: ok
        for o in $DH_OUTPUTS; do
            xrandr --addmode "$o" "$DH_MODE" 2>/dev/null
            xrandr --output "$o" --mode "$DH_MODE" 2>/dev/null
            w=$(_dh_width)
            if [ -n "$w" ] && [ "$w" -ge 1920 ]; then
                _dh_log "modo 1080p forzado en $o"
                break
            fi
        done
    fi

    # 2) Ventana de la cámara: si existe pero está IsUnMapped, desplegarla.
    #    windowmap a secas NO alcanza en esta PC (queda IsUnMapped igual);
    #    windowactivate+windowraise sí la pasan a IsViewable.
    local wid; wid=$(xdotool search --name "$DH_CAM" 2>/dev/null | head -1)
    if [ -n "$wid" ]; then
        if xwininfo -id "$wid" 2>/dev/null | grep -q "IsUnMapped"; then
            _dh_log "ventana $DH_CAM sin desplegar (wid=$wid); desplegando..."
            xdotool windowactivate "$wid" 2>/dev/null
            xdotool windowraise "$wid" 2>/dev/null
        fi
    fi
}

# Permite correrlo suelto para probar: `bash display_heal.sh`
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    display_heal
fi
