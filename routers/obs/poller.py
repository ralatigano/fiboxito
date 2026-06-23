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

_ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").split(",")
    if x.strip()
]

_prev: dict = {
    "initialized":       False,
    "stream_active":     None,
    "current_source":    None,
    "camara_active":     None,
    "stream_was_down":   False,
    "camara_down_since": None,
    "camara_alerted":    False,
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
        log_error(f"[OBS POLLER] Sin conexión SSH: {e}")
        return

    stream_active  = state["stream_active"]
    current_source = state["current_source"]
    camara_active  = state["camara_active"]

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
        })
        log_debug(
            f"[OBS POLLER] Estado inicial → "
            f"stream={'ON' if stream_active else 'OFF'} "
            f"fuente={current_source} camara={'OK' if camara_active else 'FAIL'}"
        )
        return

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


async def obs_polling_loop():
    if not OBS_SSH_HOST:
        log_debug("[OBS POLLER] OBS_SSH_HOST no configurado, poller deshabilitado.")
        return

    log_debug(f"=== OBS POLLER ACTIVO (cada {POLL_INTERVAL}s, delay cámara {CAMERA_ALERT_DELAY}s) ===")
    while True:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _poll_once)
        await asyncio.sleep(POLL_INTERVAL)
