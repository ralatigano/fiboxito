import json
from contextlib import contextmanager

from routers.obs.config import (
    OBS_SSH_HOST, OBS_SSH_PORT, OBS_SSH_USER, OBS_SSH_PASSWORD,
    OBS_SCENE_NAME, OBS_DEFAULT_SOURCE, OBS_WS_SCRIPT, OBS_STATE_FILE, OBS_PROGRAMS_FILE,
    OBS_REBOOT_CMD,
)
from routers.obs.ssh_client import SSHClient
from routers.obs.watchdog_ctrl import WatchdogController

_LOG_UNITS = {
    "obs":        "obs-watchdog",
    "obs-studio": "obs-watchdog",
    "watchdog":   "obs-watchdog",
    "camara":     "camara",
    "camera":     "camara",
}


@contextmanager
def _ssh():
    if not OBS_SSH_HOST:
        raise ValueError("OBS_SSH_HOST no configurado en .env")
    client = SSHClient({
        "host":     OBS_SSH_HOST,
        "port":     OBS_SSH_PORT,
        "username": OBS_SSH_USER,
        "password": OBS_SSH_PASSWORD,
    })
    client.connect()
    try:
        yield client
    finally:
        client.disconnect()


def _ws(ssh: SSHClient, request_type: str, data: dict = {}) -> dict:
    """
    Ejecuta un request OBS WebSocket vía script remoto.
    obs_ws.py retorna directamente el responseData desenvuelto.
    """
    from logger import log_debug
    cmd = f"python3 {OBS_WS_SCRIPT} {request_type} '{json.dumps(data)}'"
    out, err = ssh.run_command(cmd)
    if err:
        log_debug(f"[OBS WS stderr] {request_type}: {err}")
    if out:
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            log_debug(f"[OBS WS parse error] {request_type}: {out!r}")
            return {"_raw": out}
    return {}


def _load_known_sources(ssh: SSHClient) -> set[str]:
    """Lee programs.json y retorna el conjunto de fuentes conocidas + la fuente por defecto."""
    out, _ = ssh.run_command(f"cat {OBS_PROGRAMS_FILE}")
    try:
        programs = json.loads(out)
        return {p["source"] for p in programs} | {OBS_DEFAULT_SOURCE}
    except Exception:
        return set()


def _get_current_source(ssh: SSHClient) -> str | None:
    """
    Retorna la fuente programable activa en la escena.
    Solo considera fuentes que estén en programs.json o sean la fuente por defecto,
    ignorando otros items de la escena (overlays, reloj, etc.).
    """
    known = _load_known_sources(ssh)
    resp  = _ws(ssh, "GetSceneItemList", {"sceneName": OBS_SCENE_NAME})
    items = resp.get("sceneItems", [])
    for item in items:
        if item.get("sceneItemEnabled", False):
            name = item.get("sourceName")
            if not known or name in known:
                return name
    return None


# ── Estado general ─────────────────────────────────────────────

def get_status() -> dict:
    with _ssh() as ssh:
        stream_data    = _ws(ssh, "GetStreamStatus")
        scene_resp     = _ws(ssh, "GetCurrentProgramScene")
        current_scene  = scene_resp.get("currentProgramSceneName", "?")
        current_source = _get_current_source(ssh)

        wd        = WatchdogController(ssh)
        wd_status = wd.get_status()
        try:
            wd_state = json.loads(wd.get_state_json())
        except Exception:
            wd_state = {}

        return {
            "ssh_ok":          True,
            "stream_active":   stream_data.get("outputActive", False),
            "stream_timecode": stream_data.get("outputTimecode"),
            "current_scene":   current_scene,
            "current_source":  current_source,
            "watchdog_status": wd_status,
            "watchdog_state":  wd_state,
        }


# ── Fuentes de audio ───────────────────────────────────────────

def get_sources() -> list[dict]:
    with _ssh() as ssh:
        resp  = _ws(ssh, "GetSceneItemList", {"sceneName": OBS_SCENE_NAME})
        items = resp.get("sceneItems", [])
        return [
            {
                "name":    item.get("sourceName"),
                "id":      item.get("sceneItemId"),
                "enabled": item.get("sceneItemEnabled", False),
            }
            for item in items
        ]


def set_source_enabled(source_name: str, enabled: bool):
    with _ssh() as ssh:
        id_resp = _ws(ssh, "GetSceneItemId", {
            "sceneName":  OBS_SCENE_NAME,
            "sourceName": source_name,
        })
        item_id = id_resp.get("sceneItemId")
        if item_id is None:
            raise ValueError(f"Fuente '{source_name}' no encontrada en escena '{OBS_SCENE_NAME}'")

        _ws(ssh, "SetSceneItemEnabled", {
            "sceneName":        OBS_SCENE_NAME,
            "sceneItemId":      item_id,
            "sceneItemEnabled": enabled,
        })


# ── Stream ─────────────────────────────────────────────────────

def start_stream():
    with _ssh() as ssh:
        _ws(ssh, "StartStream")


def stop_stream():
    with _ssh() as ssh:
        _ws(ssh, "StopStream")


def restart_stream():
    """Detiene y reinicia el stream. No toca OBS ni mpv."""
    import time
    with _ssh() as ssh:
        _ws(ssh, "StopStream")
        time.sleep(2)
        _ws(ssh, "StartStream")


def restart_obs():
    """
    Mata OBS. El watchdog detecta que se cayó y lo reinicia con las variables
    de entorno correctas (DISPLAY, XAUTHORITY, PULSE_SERVER).
    """
    with _ssh() as ssh:
        ssh.run_command("pkill obs")


# ── Mute ───────────────────────────────────────────────────────

def set_mute(muted: bool) -> str:
    """Mutea/desmutea la fuente activa en la escena. Retorna el nombre de la fuente."""
    with _ssh() as ssh:
        current_source = _get_current_source(ssh)
        if not current_source:
            raise ValueError("No se encontró ninguna fuente habilitada en la escena")
        _ws(ssh, "SetInputMute", {"inputName": current_source, "inputMuted": muted})
        return current_source


# ── Cámara ─────────────────────────────────────────────────────

def restart_camera():
    """Reinicia mpv sourcando el script del watchdog (camara.service está disabled)."""
    with _ssh() as ssh:
        ssh.run_command(
            "bash -c 'source /opt/obs-watchdog/modules/mpv_restart.sh && mpv_restart'",
            timeout=20,
        )


def get_screenshot() -> bytes:
    """Captura un frame del display :0 vía ffmpeg y lo retorna como PNG."""
    import io
    with _ssh() as ssh:
        ssh.run_command(
            "DISPLAY=:0 XAUTHORITY=/home/obs-moldes/.Xauthority "
            "ffmpeg -f x11grab -i :0 -vframes 1 /tmp/obs_cap.png -y -loglevel quiet",
            timeout=20,
        )
        sftp = ssh.client.open_sftp()
        buf = io.BytesIO()
        try:
            sftp.getfo("/tmp/obs_cap.png", buf)
        finally:
            sftp.close()
        buf.seek(0)
        return buf.read()


# ── Logs ───────────────────────────────────────────────────────

def get_logs(service: str, lines: int = 100) -> str:
    unit = _LOG_UNITS.get(service.lower(), service)
    with _ssh() as ssh:
        out, _ = ssh.run_command(f"journalctl -u {unit} -n {lines} --no-pager")
        return out


# ── Watchdog ───────────────────────────────────────────────────

def get_watchdog_status() -> dict:
    with _ssh() as ssh:
        wd = WatchdogController(ssh)
        try:
            state = json.loads(wd.get_state_json())
        except Exception:
            state = {}
        return {"status": wd.get_status(), "state": state}


def restart_watchdog():
    with _ssh() as ssh:
        WatchdogController(ssh).restart()


def enable_watchdog():
    """Habilita (arranca) el servicio del watchdog."""
    with _ssh() as ssh:
        WatchdogController(ssh).start()


def disable_watchdog():
    """Deshabilita (detiene) el servicio del watchdog."""
    with _ssh() as ssh:
        WatchdogController(ssh).stop()


# ── PC ─────────────────────────────────────────────────────────

def reboot_pc():
    """Reinicia la PC que hostea OBS. El watchdog vuelve a levantar todo al arrancar."""
    with _ssh() as ssh:
        ssh.run_command(OBS_REBOOT_CMD)


# ── Estado para poller de notificaciones ───────────────────────

def get_poll_state() -> dict:
    """Una sola conexión SSH, retorna todo lo que necesita el poller."""
    with _ssh() as ssh:
        stream_data    = _ws(ssh, "GetStreamStatus")
        stream_active  = stream_data.get("outputActive", False)
        current_source = _get_current_source(ssh)

        # camara.service está disabled; mpv lo gestiona el watchdog directamente
        cam_out, _ = ssh.run_command("pgrep -f 'title=CAMARA' > /dev/null && echo active || echo inactive")
        camara_active = cam_out.strip() == "active"

        return {
            "stream_active":  stream_active,
            "current_source": current_source,
            "camara_active":  camara_active,
        }


# ── Programación ───────────────────────────────────────────────

def get_programs() -> list:
    with _ssh() as ssh:
        out, _ = ssh.run_command(f"cat {OBS_PROGRAMS_FILE}")
        return json.loads(out)


def set_programs(programs: list):
    payload = json.dumps(programs, ensure_ascii=False)
    safe    = payload.replace("'", "'\\''")
    with _ssh() as ssh:
        ssh.run_command(f"echo '{safe}' > {OBS_PROGRAMS_FILE}")
