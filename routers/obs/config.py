import os

# LOCAL=True → usa la IP de red interna (port 22)
# LOCAL=False → usa la IP pública/remota (port 9922)
_local = os.getenv("LOCAL", "false").lower() in ("true", "1", "yes")

OBS_SSH_HOST = os.getenv(
    "OBS_SSH_LOCAL_HOST" if _local else "OBS_SSH_REMOTE_HOST", ""
)
OBS_SSH_PORT = int(os.getenv(
    "OBS_SSH_LOCAL_PORT" if _local else "OBS_SSH_REMOTE_PORT",
    "22" if _local else "9922"
))
OBS_SSH_USER     = os.getenv("OBS_SSH_USER", "obs-moldes")
OBS_SSH_PASSWORD = os.getenv("OBS_SSH_PASSWORD", "")

OBS_SCENE_NAME    = os.getenv("OBS_SCENE_NAME", "Escena")
OBS_DEFAULT_SOURCE = os.getenv("OBS_DEFAULT_SOURCE", "musica")
OBS_WS_SCRIPT     = "/opt/obs-watchdog/modules/obs_ws.py"
# Script del watchdog que hace el swap de fuente (incluye el toggle que recupera
# el audio de las radios). Lo reusa el panel para no duplicar esa lógica.
OBS_SWITCH_SCRIPT = "/opt/obs-watchdog/modules/cambiar_fuente.sh"
OBS_STATE_FILE    = "/opt/obs-watchdog/state.json"
OBS_LOG_FILE      = "/opt/obs-watchdog/logs/watchdog.log"
OBS_PROGRAMS_FILE = "/opt/obs-watchdog/data/programs.json"

# Tipo de input de OBS con el que se dan de alta las radios (fuentes de audio de
# red). Todas las radios existentes (RadioFMEspacio, RadioSanNicolas, RadioPop,
# musica) son `ffmpeg_source` apuntando a una URL de streaming.
OBS_AUDIO_INPUT_KIND = "ffmpeg_source"

# Comando que reinicia la PC remota. Configurable por si el host necesita sudo
# con contraseña o un binario distinto. Default: sudo sin contraseña.
OBS_REBOOT_CMD    = os.getenv("OBS_REBOOT_CMD", "sudo reboot")
