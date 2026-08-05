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

# Patrones de cuelgue de GPU en el log del kernel (radeon/AMD Bonaire).
# Validados contra los incidentes reales del 02/08 y 03/08.
_GPU_LOCKUP_RE = r"GPU lockup|ring [0-9].*stalled|couldn.t schedule ib|radeon.*Oops"


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

        # ¿Hay cámara corriendo? (para verificar el "reiniciar cámara" del panel)
        cam_out, _ = ssh.run_command(
            "pgrep -f 'title=CAMARA' > /dev/null && echo active || echo inactive"
        )
        camara_active = cam_out.strip() == "active"

        wd        = WatchdogController(ssh)
        wd_status = wd.get_status()
        try:
            wd_state = json.loads(wd.get_state_json())
        except Exception:
            wd_state = {}

        return {
            "ssh_ok":          True,
            "stream_active":   stream_data.get("outputActive", False),
            "stream_reconnecting": stream_data.get("outputReconnecting", False),
            "stream_bytes":    stream_data.get("outputBytes", 0) or 0,
            "stream_timecode": stream_data.get("outputTimecode"),
            "current_scene":   current_scene,
            "current_source":  current_source,
            "camara_active":   camara_active,
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
    """Captura un frame del display :0 vía ffmpeg y lo retorna como PNG.
    Muestra la PANTALLA REAL de la PC (sirve aunque OBS esté trabado)."""
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


def get_screenshot_program(width: int = 960) -> bytes:
    """Captura el PROGRAMA compuesto de OBS vía WebSocket (GetSourceScreenshot).
    Es "lo que sale al aire": rápido (~0.2s) y limpio, sin artefactos de grab.
    Requiere OBS/WebSocket vivo → si OBS está trabado, usar get_screenshot()."""
    import base64
    with _ssh() as ssh:
        scene = _ws(ssh, "GetCurrentProgramScene").get("currentProgramSceneName", OBS_SCENE_NAME)
        resp  = _ws(ssh, "GetSourceScreenshot", {
            "sourceName":              scene,
            "imageFormat":             "jpg",
            "imageWidth":              width,
            "imageCompressionQuality": 80,
        })
        data = resp.get("imageData", "")
        if not isinstance(data, str) or "," not in data:
            raise ValueError("OBS no devolvió imagen (WebSocket caído o OBS sin responder)")
        return base64.b64decode(data.split(",", 1)[1])


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

        # boot_id: cambia en cada arranque del kernel → detecta reinicios de la PC
        boot_out, _ = ssh.run_command("cat /proc/sys/kernel/random/boot_id")

        # Síntomas de cuelgue de GPU en el log del kernel (ventana reciente).
        # obs-moldes está en el grupo 'adm' → puede leer journalctl -k sin sudo.
        gpu_out, _ = ssh.run_command(
            "journalctl -k --since '90 sec ago' --no-pager 2>/dev/null | "
            f"grep -Ei '{_GPU_LOCKUP_RE}' | tail -3"
        )

        return {
            "stream_active":  stream_active,
            "current_source": current_source,
            "camara_active":  camara_active,
            "boot_id":        boot_out.strip(),
            "gpu_lockup":     gpu_out.strip(),
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


# ── Diagnóstico determinístico ─────────────────────────────────
# Chequeo de salud que corre las firmas de falla YA catalogadas (sin LLM) y las
# traduce a castellano llano con su nivel 🔴/🟡/🟢 y qué botón tocar.

_LEVEL_ORDER = {"error": 3, "warn": 2, "info": 1, "ok": 0}

# Botones que ya existen en el panel, para ofrecer la acción dentro del hallazgo.
# `confirm` (opcional) → el front abre el modal de confirmación antes de ejecutar.
_BTN_START_STREAM = {"label": "▶ Iniciar transmisión", "path": "stream/start", "kind": "green"}
_BTN_RESTART_OBS  = {"label": "🔄 Reiniciar OBS", "path": "stream/restart", "kind": "amber",
                     "confirm": {"title": "Reiniciar OBS",
                                 "msg": "Mata OBS; el watchdog lo vuelve a levantar en unos segundos."}}
_BTN_RESTART_CAM  = {"label": "📷 Reiniciar cámara", "path": "camera/restart", "kind": "slate"}
_BTN_WD_ENABLE    = {"label": "🟢 Habilitar watchdog", "path": "watchdog/enable", "kind": "green"}
_BTN_WD_RESTART   = {"label": "🔄 Reiniciar watchdog", "path": "watchdog/restart", "kind": "slate"}
_BTN_REBOOT_PC    = {"label": "🔁 Reiniciar la PC", "path": "system/reboot", "kind": "red",
                     "confirm": {"title": "Reiniciar la PC del canal",
                                 "msg": "La PC queda unos minutos fuera de línea. Al volver, "
                                        "el watchdog levanta todo solo."}}


def _fnd(level: str, titulo: str, detalle: str,
         accion: str | None = None, boton: dict | None = None) -> dict:
    return {"level": level, "titulo": titulo, "detalle": detalle,
            "accion": accion, "boton": boton}


def _clip(s: str, n: int = 320) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "…"


def _safe(ssh: SSHClient, cmd: str, timeout: int = 15) -> str:
    """Corre un comando y devuelve stdout limpio; nunca lanza (para sondas del diagnóstico)."""
    try:
        out, _ = ssh.run_command(cmd, timeout=timeout)
        return out.strip()
    except Exception:
        return ""


def _collect_diagnostics(ssh: SSHClient) -> dict:
    """Junta todas las señales de salud en una sola sesión SSH."""
    import time
    raw: dict = {}

    # Transmisión: dos muestras para ver si outputBytes crece (data saliendo de verdad).
    s1 = _ws(ssh, "GetStreamStatus")
    time.sleep(2.5)
    s2 = _ws(ssh, "GetStreamStatus")
    raw["stream"] = {
        "active":       s2.get("outputActive", False),
        "reconnecting": s2.get("outputReconnecting", False),
        "bytes":        s2.get("outputBytes", 0) or 0,
        "bytes_prev":   s1.get("outputBytes", 0) or 0,
        "timecode":     s2.get("outputTimecode"),
        "skipped":      s2.get("outputSkippedFrames", 0) or 0,
        "total":        s2.get("outputTotalFrames", 0) or 0,
    }

    # Escena / fuente activa + fuentes encendidas (para no gritar por radios apagadas).
    raw["scene"]  = _ws(ssh, "GetCurrentProgramScene").get("currentProgramSceneName")
    items = _ws(ssh, "GetSceneItemList", {"sceneName": OBS_SCENE_NAME}).get("sceneItems", [])
    raw["enabled_sources"] = [it.get("sourceName") for it in items if it.get("sceneItemEnabled")]
    raw["source"] = _get_current_source(ssh)

    # OBS: cantidad de instancias y estado (D = trabado en el driver, Z = zombie).
    obs_pids = _safe(ssh, "pgrep -x obs")
    raw["obs_count"] = len([l for l in obs_pids.splitlines() if l.strip()])
    obs_stat = _safe(ssh, "ps -eo stat=,comm= | awk '$2==\"obs\"{print $1}'")
    raw["obs_stuck"] = any(st[:1] in ("D", "Z") for st in obs_stat.split())

    # Watchdog: servicio de sistema + duplicados (bug del watchdog de usuario).
    # El patrón ancla al final para no contar el propio wrapper `sh -c` de este comando.
    raw["wd_active"]  = _safe(ssh, "systemctl is-active obs-watchdog")
    raw["wd_dupes"]   = _safe(ssh, "pgrep -fc 'watchdog\\.sh$'") or "0"
    raw["state_json"] = _safe(ssh, f"cat {OBS_STATE_FILE}")

    # Cámara: mpv corriendo + conexión establecida al puerto RTSP (554).
    raw["mpv_count"] = _safe(ssh, "pgrep -xc mpv") or "0"
    raw["cam_estab"] = _safe(ssh, "ss -tn state established 2>/dev/null | grep -c ':554'") or "0"

    # GPU lockup en el log del kernel (ventana amplia para diagnóstico on-demand).
    raw["gpu_lockup"] = _safe(
        ssh,
        "journalctl -k --since '15 min ago' --no-pager 2>/dev/null | "
        f"grep -Ei '{_GPU_LOCKUP_RE}' | tail -3",
    )

    # Audio: error de autenticación (HTTP 401) en el log de OBS → radio caída.
    raw["audio_401"] = _safe(
        ssh,
        "f=$(ls -t ~/.config/obs-studio/logs/*.txt 2>/dev/null | head -1); "
        "[ -n \"$f\" ] && grep -iE '401|authentication failed' \"$f\" | tail -2",
    )

    # Sistema: carga, núcleos y disco.
    raw["loadavg"] = _safe(ssh, "cat /proc/loadavg")
    raw["nproc"]   = _safe(ssh, "nproc") or "1"
    raw["disk"]    = _safe(ssh, "df -P / | tail -1 | awk '{print $5}'")

    return raw


def _evaluate_diagnostics(raw: dict) -> list[dict]:
    """Aplica las reglas sobre las señales crudas y arma los hallazgos en castellano."""
    f: list[dict] = []
    st = raw.get("stream", {})

    # ── Transmisión ─────────────────────────────────────────────
    if not st.get("active"):
        f.append(_fnd(
            "error", "La transmisión está fuera del aire",
            "OBS no está transmitiendo.",
            "Iniciá la transmisión. Si no arranca, revisá OBS y la cámara acá abajo.",
            _BTN_START_STREAM,
        ))
    elif st.get("reconnecting"):
        f.append(_fnd(
            "warn", "La transmisión está reconectando",
            "OBS figura al aire pero está reintentando conectar con el servidor: "
            "se puede ver cortado o congelado.",
            "Esperá unos segundos y volvé a diagnosticar. Si sigue, reiniciá OBS.",
            _BTN_RESTART_OBS,
        ))
    elif st.get("bytes", 0) <= st.get("bytes_prev", 0):
        f.append(_fnd(
            "warn", "Dice al aire pero no está saliendo data",
            "OBS figura activo pero los datos enviados no aumentan: probablemente "
            "el servidor de streaming no está recibiendo la señal.",
            "Reiniciá OBS y volvé a diagnosticar para ver que los datos suban.",
            _BTN_RESTART_OBS,
        ))
    else:
        f.append(_fnd(
            "ok", "Transmisión al aire y saliendo data",
            f"Enviando datos con normalidad (tiempo al aire {st.get('timecode') or '—'}).",
        ))

    # Frames perdidos (PC exigida).
    total, skipped = st.get("total", 0) or 0, st.get("skipped", 0) or 0
    if total > 0 and skipped / total > 0.05:
        pct = round(skipped / total * 100, 1)
        f.append(_fnd(
            "warn", "Se están perdiendo cuadros de video",
            f"{pct}% de cuadros omitidos ({skipped}/{total}): la PC no da abasto para "
            "codificar el video (CPU o GPU al límite).",
            "Puede venir de la mano de un problema de GPU; revisá los puntos de abajo.",
        ))

    # ── GPU lockup ──────────────────────────────────────────────
    if raw.get("gpu_lockup"):
        f.append(_fnd(
            "error", "Se colgó la placa de video (GPU)",
            "El registro del sistema muestra un cuelgue de la placa de video. Esto es lo "
            "que en el pasado dejó OBS congelado por horas.\n" + _clip(raw["gpu_lockup"]),
            "Reiniciá la PC del canal. Si el reinicio se cuelga, el watchdog de hardware "
            "la recupera sola.",
            _BTN_REBOOT_PC,
        ))

    # ── OBS (proceso) ───────────────────────────────────────────
    n_obs = raw.get("obs_count", 0)
    if n_obs == 0:
        f.append(_fnd(
            "error", "OBS no está corriendo",
            "No hay ningún proceso de OBS en la PC del canal.",
            "El watchdog debería levantarlo solo. Si no aparece, reiniciá el watchdog.",
            _BTN_WD_RESTART,
        ))
    elif n_obs > 1:
        f.append(_fnd(
            "error", f"Hay {n_obs} OBS corriendo a la vez",
            "Dos instancias de OBS pelean por la placa de video y por el mismo destino de "
            "transmisión → imagen entrecortada y fallas de conexión.",
            "Reiniciá OBS para que quede una sola.",
            _BTN_RESTART_OBS,
        ))
    elif raw.get("obs_stuck"):
        f.append(_fnd(
            "error", "OBS está trabado y no responde",
            "El proceso de OBS quedó en un estado del que no sale ni cerrándolo "
            "(trabado en el driver de video). Suele ser secuela de un cuelgue de GPU.",
            "Reiniciá la PC del canal.",
            _BTN_REBOOT_PC,
        ))
    else:
        f.append(_fnd("ok", "OBS corriendo con una sola instancia", "Proceso único y respondiendo."))

    # ── Watchdog ────────────────────────────────────────────────
    wd    = raw.get("wd_active", "")
    dupes = int(raw.get("wd_dupes", "0") or 0)
    if wd != "active":
        f.append(_fnd(
            "warn", "El watchdog no está activo",
            f"El servicio del watchdog figura «{wd or 'desconocido'}». Mientras esté apagado, "
            "nadie levanta OBS ni la cámara si se caen.",
            "Habilitá el watchdog. (Un «failed» justo después de pararlo a mano es esperable; "
            "en ese caso alcanza con reiniciarlo.)",
            _BTN_WD_ENABLE,
        ))
    elif dupes > 1:
        f.append(_fnd(
            "error", f"Hay {dupes} watchdogs corriendo a la vez",
            "Watchdogs duplicados (el de sistema y uno de usuario) se pisan entre sí y "
            "duplican OBS y la cámara. Es la causa raíz de varios problemas viejos.",
            "Hay que deshabilitar el watchdog de usuario por SSH: "
            "`systemctl --user disable --now obs-watchdog`.",
        ))
    else:
        try:
            le = json.loads(raw.get("state_json") or "{}").get("last_error", "none")
        except Exception:
            le = "none"
        if le and le not in ("none", ""):
            f.append(_fnd(
                "warn", "El watchdog anotó un error reciente",
                f"Último error registrado por el watchdog: «{le}».",
                "Mirá los logs del watchdog (abajo) para el detalle.",
            ))
        else:
            f.append(_fnd("ok", "Watchdog activo y sin errores", "Vigilando OBS y la cámara."))

    # ── Cámara ──────────────────────────────────────────────────
    mpv   = int(raw.get("mpv_count", "0") or 0)
    estab = int(raw.get("cam_estab", "0") or 0)
    if mpv == 0:
        f.append(_fnd(
            "warn", "La cámara no está corriendo",
            "No hay ningún reproductor de cámara activo en la PC.",
            "Reiniciá la cámara.",
            _BTN_RESTART_CAM,
        ))
    elif mpv > 1:
        f.append(_fnd(
            "warn", f"Hay {mpv} reproductores de cámara",
            "Varios reproductores compiten por la misma cámara → imagen entrecortada.",
            "Reiniciá la cámara para que quede uno solo.",
            _BTN_RESTART_CAM,
        ))
    elif estab == 0:
        f.append(_fnd(
            "warn", "La cámara no tiene conexión con el equipo",
            "El reproductor está abierto pero sin conexión establecida a la cámara "
            "(puede estar apagada, colgada o sin red).",
            "Reiniciá la cámara. Si sigue, revisá la cámara y la red.",
            _BTN_RESTART_CAM,
        ))
    else:
        f.append(_fnd("ok", "Cámara conectada", "Reproductor activo y conectado al equipo."))

    # ── Audio ───────────────────────────────────────────────────
    # El 401 queda en el log de OBS aunque la radio ya esté apagada. Solo es un
    # problema ACTUAL si hay una radio encendida (las radios apagadas a esta hora
    # son lo normal; sale la fuente 'musica').
    enabled   = raw.get("enabled_sources") or []
    radios_on = [n for n in enabled if n and "radio" in n.lower()]
    if raw.get("audio_401") and radios_on:
        f.append(_fnd(
            "warn", "Una radio encendida falló por autenticación",
            "Hay una radio encendida (" + ", ".join(radios_on) + ") y el log de OBS muestra "
            "un error de autenticación (401): esa radio puede estar saliendo sin sonido. "
            "No corta el video.",
            "Revisá la URL o las credenciales de la radio, o apagala y usá otra fuente de audio.",
        ))

    # ── Sistema (carga / disco) ─────────────────────────────────
    try:
        load1 = float((raw.get("loadavg") or "0").split()[0])
        ncpu  = max(int(raw.get("nproc", "1") or 1), 1)
        if load1 / ncpu > 2.0:
            f.append(_fnd(
                "warn", "La PC del canal está muy cargada",
                f"Carga {load1:.1f} para {ncpu} núcleos: el equipo está exigido y puede "
                "entrecortar el video.",
                "Suele venir junto con problemas de GPU o cámara; revisá los puntos de arriba.",
            ))
    except Exception:
        pass
    disk = (raw.get("disk") or "").rstrip("%")
    if disk.isdigit() and int(disk) >= 90:
        f.append(_fnd(
            "warn", "Queda poco espacio en disco",
            f"El disco de la PC del canal está al {disk}%.",
            "Conviene liberar espacio para que no se corten los logs ni la grabación.",
        ))

    return f


def run_diagnostics() -> dict:
    """Corre el diagnóstico completo y devuelve veredicto + hallazgos ordenados por severidad."""
    from datetime import datetime
    with _ssh() as ssh:
        raw = _collect_diagnostics(ssh)

    findings = _evaluate_diagnostics(raw)
    findings.sort(key=lambda x: _LEVEL_ORDER.get(x["level"], 0), reverse=True)

    n_err  = sum(1 for x in findings if x["level"] == "error")
    n_warn = sum(1 for x in findings if x["level"] == "warn")
    if n_err:
        verdict = "error"
        resumen = f"{n_err} problema(s) serio(s)" + (f" y {n_warn} advertencia(s)" if n_warn else "")
    elif n_warn:
        verdict = "warn"
        resumen = f"{n_warn} advertencia(s), sin problemas graves"
    else:
        verdict = "ok"
        resumen = "Todo en orden"

    return {
        "verdict":  verdict,
        "resumen":  resumen,
        "findings": findings,
        "ts":       datetime.now().strftime("%H:%M:%S"),
    }


_DIAG_ICON = {"error": "🔴", "warn": "🟡", "ok": "🟢", "info": "ℹ️"}


def format_diagnostics_telegram(r: dict, include_ok: bool = False) -> str:
    """Arma el mensaje de Telegram a partir del resultado de run_diagnostics().
    Por defecto omite los ítems 🟢 (solo muestra lo que conviene mirar)."""
    icon  = _DIAG_ICON.get(r.get("verdict"), "ℹ️")
    lines = [
        f"🩺 Diagnóstico del canal — {icon} {r.get('resumen', '')}",
        f"🕓 Ejecutado a las {r.get('ts', '')}",
    ]
    shown = [f for f in r.get("findings", []) if include_ok or f.get("level") != "ok"]
    if not shown:
        lines.append("\n✅ Sin observaciones para reportar.")
    else:
        lines.append("")
        for f in shown:
            lines.append(f"{_DIAG_ICON.get(f.get('level'), 'ℹ️')} {f.get('titulo', '')}")
            det = (f.get("detalle") or "").strip()
            if det:
                lines.append(f"   {det}")
            if f.get("accion"):
                lines.append(f"   👉 {f['accion']}")
    return "\n".join(lines)
