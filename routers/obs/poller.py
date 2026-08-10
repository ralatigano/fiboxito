import asyncio
import os
from datetime import datetime

from logger import log_debug, log_error
from telegram.helpers import send_message
from routers.obs.config import OBS_SSH_HOST
from routers.obs import service as obs_service

POLL_INTERVAL        = int(os.getenv("OBS_POLL_INTERVAL", "30"))
# Tiempo mínimo que la cámara debe estar caída antes de notificar.
# La cron de reinicio tarda ~30-60s → con 120s los reinicios programados pasan silencio.
CAMERA_ALERT_DELAY   = int(os.getenv("OBS_CAMERA_ALERT_DELAY", "120"))
# Tiempo mínimo que la PC OBS debe estar inalcanzable (SSH caído) antes de avisar
# que está "caída". Un reboot normal tarda ~70s → con 120s los reinicios rápidos
# NO disparan este aviso, pero SÍ se detectan por el cambio de boot_id.
UNREACHABLE_ALERT_DELAY = int(os.getenv("OBS_UNREACHABLE_ALERT_DELAY", "120"))

# Guardián de GPU lockup (C): si el log del kernel muestra un cuelgue de GPU y
# eso rompió la transmisión, reinicia la PC — pero con un tope para no entrar en
# un loop de reinicios si la GPU está fallando de forma terminal.
GPU_GUARD_ENABLED = os.getenv("OBS_GPU_GUARD_ENABLED", "true").lower() in ("true", "1", "yes")
GPU_MAX_REBOOTS   = int(os.getenv("OBS_GPU_MAX_REBOOTS", "2"))
GPU_REBOOT_WINDOW = int(os.getenv("OBS_GPU_REBOOT_WINDOW", "1800"))  # segundos (30 min)

# Auto-recuperación de video: si la PC arrancó sin monitor (pantalla sin modo real) o
# la ventana de la cámara quedó sin mapear, `heal_video` lo corrige sin intervención.
VIDEO_HEAL_ENABLED = os.getenv("OBS_VIDEO_HEAL_ENABLED", "true").lower() in ("true", "1", "yes")

_ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").split(",")
    if x.strip()
]

_prev: dict = {
    "initialized":        False,
    "stream_active":      None,
    "current_source":     None,
    "camara_active":      None,
    "stream_was_down":    False,
    "camara_down_since":  None,
    "camara_alerted":     False,
    "boot_id":            None,
    "unreachable_since":  None,
    "unreachable_alerted": False,
    "gpu_lockup_active":  False,
    "gpu_reboot_times":   [],
    "video_healed_active": False,
}


def _notify(msg: str):
    ts  = datetime.now().strftime("%H:%M")
    txt = f"[{ts}] {msg}"
    for chat_id in _ADMIN_IDS:
        try:
            send_message(chat_id, txt)
        except Exception as e:
            log_error(f"[OBS POLLER] Error notificando {chat_id}: {e}")


def _poll_once():
    try:
        state = obs_service.get_poll_state()
    except Exception as e:
        # PC OBS inalcanzable (SSH caído): reiniciando, colgada o apagada.
        # Avisamos UNA vez si supera el umbral, para no spamear en cada poll.
        now = datetime.now()
        if _prev["unreachable_since"] is None:
            _prev["unreachable_since"] = now
        elapsed = (now - _prev["unreachable_since"]).total_seconds()
        if not _prev["unreachable_alerted"] and elapsed >= UNREACHABLE_ALERT_DELAY:
            _notify(
                f"⚠️ *PC OBS inalcanzable* hace {int(elapsed // 60)} min — "
                f"la transmisión puede estar caída."
            )
            _prev["unreachable_alerted"] = True
        log_error(f"[OBS POLLER] Sin conexión SSH: {e}")
        return

    stream_active  = state["stream_active"]
    current_source = state["current_source"]
    camara_active  = state["camara_active"]
    boot_id        = state.get("boot_id")

    # ── Primera ejecución: captura estado base, no notifica ──────
    if not _prev["initialized"]:
        _prev.update({
            "initialized":       True,
            "stream_active":     stream_active,
            "current_source":    current_source,
            "camara_active":     camara_active,
            "stream_was_down":   not stream_active,
            "camara_down_since": None if camara_active else datetime.now(),
            "camara_alerted":    False,
            "boot_id":           boot_id,
            "gpu_lockup_active": bool(state.get("gpu_lockup")),
        })
        log_debug(
            f"[OBS POLLER] Estado inicial → "
            f"stream={'ON' if stream_active else 'OFF'} "
            f"fuente={current_source} camara={'OK' if camara_active else 'FAIL'}"
        )
        return

    # ── PC OBS volvió / se reinició (SSH recuperado tras estar caído) ──
    # boot_id cambia en cada arranque → un solo aviso por reinicio (anti-catarata).
    rebooted = bool(_prev["boot_id"] and boot_id and boot_id != _prev["boot_id"])
    if _prev["unreachable_since"] is not None:
        down_min = int((datetime.now() - _prev["unreachable_since"]).total_seconds() // 60)
        if rebooted:
            _notify(f"🔄 *La PC OBS se reinició* — estuvo caída ~{down_min} min. Transmisión de vuelta.")
        elif _prev["unreachable_alerted"]:
            _notify(f"🟢 *PC OBS de vuelta* — estuvo inalcanzable ~{down_min} min.")
        _prev["unreachable_since"]   = None
        _prev["unreachable_alerted"] = False
    elif rebooted:
        # Reinicio tan rápido que ningún poll llegó a fallar, pero el boot_id cambió.
        _notify("🔄 *La PC OBS se reinició.*")
    _prev["boot_id"] = boot_id

    # ── Stream caído ─────────────────────────────────────────────
    if not stream_active and _prev["stream_active"]:
        _notify("🔴 *Stream caído* — La transmisión se interrumpió.")
        _prev["stream_was_down"] = True

    # ── Stream recuperado ─────────────────────────────────────────
    elif stream_active and not _prev["stream_active"]:
        if _prev["stream_was_down"]:
            _notify("🟢 *Transmisión recuperada* — El canal volvió al aire.")
        else:
            _notify("🟢 *Stream iniciado*.")
        _prev["stream_was_down"] = False

    _prev["stream_active"] = stream_active

    # ── Cambio de fuente (schedule_runner intervino) ─────────────
    if (
        current_source
        and _prev["current_source"] is not None
        and current_source != _prev["current_source"]
    ):
        _notify(
            f"🔄 *Cambio de fuente*\n"
            f"  Antes:  {_prev['current_source']}\n"
            f"  Ahora:  {current_source}"
        )
    _prev["current_source"] = current_source

    # ── Cámara: con delay para ignorar reinicios programados ─────
    if not camara_active and _prev["camara_active"]:
        # Cámara recién se cayó → arranca el temporizador
        _prev["camara_down_since"] = datetime.now()
        _prev["camara_alerted"]    = False

    elif not camara_active and not _prev["camara_active"]:
        # Cámara sigue caída → verificar si superó el delay
        if not _prev["camara_alerted"] and _prev["camara_down_since"]:
            elapsed = (datetime.now() - _prev["camara_down_since"]).total_seconds()
            if elapsed >= CAMERA_ALERT_DELAY:
                mins = int(elapsed // 60)
                _notify(
                    f"📷 *Error de cámara* — El servicio lleva {mins} min detenido.\n"
                    f"Puede estar afectando el video."
                )
                _prev["camara_alerted"] = True

    elif camara_active and not _prev["camara_active"]:
        # Cámara se recuperó
        if _prev["camara_alerted"]:
            _notify("📷 *Cámara recuperada* — El servicio volvió a estar activo.")
        # Si no alertamos, fue un reinicio rápido (cron) → silencio total
        _prev["camara_down_since"] = None
        _prev["camara_alerted"]    = False

    _prev["camara_active"] = camara_active

    # ── Auto-recuperación de video (arranque headless / ventana sin mapear) ──
    # Si el stream figura al aire pero la pantalla no tiene modo real (headless) o la
    # ventana de la cámara quedó IsUnMapped, el video sale en negro sin que se caiga el
    # stream ni la cámara. Lo corregimos solos y avisamos una vez por episodio.
    if VIDEO_HEAL_ENABLED and stream_active:
        screen_width = state.get("screen_width") or 0
        cam_mapped   = state.get("cam_window_mapped")
        video_broken = (0 < screen_width < 1920) or (cam_mapped is False)
        if video_broken and not _prev["video_healed_active"]:
            try:
                res = obs_service.heal_video()
                _notify(
                    "🩹 *Video degradado detectado* (arranque sin monitor o ventana de "
                    "cámara sin desplegar) — recuperado solo: "
                    + " · ".join(res.get("actions", []))
                )
                _prev["video_healed_active"] = True
            except Exception as e:
                log_error(f"[OBS POLLER] Error en auto-heal de video: {e}")
        elif not video_broken:
            _prev["video_healed_active"] = False

    # ── Guardián de GPU lockup (C) — híbrido con tope ────────────
    # Si el kernel reporta un cuelgue de GPU (lo que hoy congeló OBS por horas):
    #   · stream sano  → solo avisa (el cuelgue puede haberse recuperado solo).
    #   · stream roto  → reinicia limpio la PC, con tope anti-loop.
    #   · supera el tope → deja de reiniciar y pide intervención manual.
    # Un solo aviso/acción por episodio (se rearma cuando el log deja de mostrarlo).
    gpu_lockup = state.get("gpu_lockup")
    if GPU_GUARD_ENABLED and gpu_lockup and not _prev["gpu_lockup_active"]:
        _prev["gpu_lockup_active"] = True
        now = datetime.now()
        # descartar reinicios previos que ya salieron de la ventana
        _prev["gpu_reboot_times"] = [
            t for t in _prev["gpu_reboot_times"]
            if (now - t).total_seconds() < GPU_REBOOT_WINDOW
        ]
        if stream_active:
            _notify(
                "⚠️ *GPU lockup detectado* en la PC OBS, pero la transmisión "
                "sigue al aire. Vigilando."
            )
        elif len(_prev["gpu_reboot_times"]) >= GPU_MAX_REBOOTS:
            _notify(
                f"🛑 *GPU en falla recurrente* — ya hubo {len(_prev['gpu_reboot_times'])} "
                f"reinicios en {GPU_REBOOT_WINDOW // 60} min y el stream sigue caído. "
                f"NO reinicio más para evitar un loop; requiere intervención manual."
            )
        else:
            _prev["gpu_reboot_times"].append(now)
            _notify(
                f"🔧 *GPU lockup + stream caído* — reinicio la PC OBS "
                f"(intento {len(_prev['gpu_reboot_times'])}/{GPU_MAX_REBOOTS})."
            )
            try:
                obs_service.reboot_pc()
            except Exception as e:
                log_error(f"[OBS POLLER] Error al reiniciar por GPU lockup: {e}")
    elif not gpu_lockup:
        _prev["gpu_lockup_active"] = False


async def obs_polling_loop():
    if not OBS_SSH_HOST:
        log_debug("[OBS POLLER] OBS_SSH_HOST no configurado, poller deshabilitado.")
        return

    log_debug(f"=== OBS POLLER ACTIVO (cada {POLL_INTERVAL}s, delay cámara {CAMERA_ALERT_DELAY}s) ===")
    while True:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _poll_once)
        await asyncio.sleep(POLL_INTERVAL)
