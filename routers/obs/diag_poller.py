"""Diagnóstico periódico del canal.

Corre el chequeo de salud (routers.obs.service.run_diagnostics) cada cierta
cantidad de horas y manda el resultado por Telegram a los administradores.
Separado de poller.py (que vigila eventos en tiempo real): este es un resumen
programado para MEDIR la salud del stream a lo largo del día.

Config (.env):
  OBS_DIAG_ENABLED         → prende/apaga el poller (default true)
  OBS_DIAG_INTERVAL_HOURS  → cada cuántas horas corre (default 4)
  OBS_DIAG_INITIAL_DELAY   → segundos antes de la 1era corrida (default 120)
  OBS_DIAG_ONLY_PROBLEMS   → si true, solo avisa cuando hay 🟡/🔴 (default false)
"""
import asyncio
import os

from logger import log_debug, log_error
from telegram.helpers import send_message
from routers.obs.config import OBS_SSH_HOST
from routers.obs import service as obs_service

INTERVAL_HOURS = float(os.getenv("OBS_DIAG_INTERVAL_HOURS", "4"))
INITIAL_DELAY  = int(os.getenv("OBS_DIAG_INITIAL_DELAY", "120"))
ONLY_PROBLEMS  = os.getenv("OBS_DIAG_ONLY_PROBLEMS", "false").lower() in ("true", "1", "yes")

_ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").split(",")
    if x.strip()
]


def _run_and_notify():
    """Corre el diagnóstico y lo manda por Telegram. Nunca lanza."""
    try:
        result = obs_service.run_diagnostics()
    except Exception as e:  # noqa: BLE001
        # La PC del canal puede estar inalcanzable; el poller de eventos ya avisa
        # de eso, así que acá solo lo registramos para no duplicar alarmas.
        log_error(f"[DIAG POLLER] No se pudo ejecutar el diagnóstico: {e}")
        return

    if ONLY_PROBLEMS and result.get("verdict") == "ok":
        log_debug("[DIAG POLLER] Todo en orden; no se notifica (OBS_DIAG_ONLY_PROBLEMS).")
        return

    msg = obs_service.format_diagnostics_telegram(result)
    for chat_id in _ADMIN_IDS:
        try:
            send_message(chat_id, msg)
        except Exception as e:  # noqa: BLE001
            log_error(f"[DIAG POLLER] Error notificando a {chat_id}: {e}")


async def diag_polling_loop():
    if not OBS_SSH_HOST:
        log_debug("[DIAG POLLER] OBS_SSH_HOST no configurado, poller deshabilitado.")
        return
    if not _ADMIN_IDS:
        log_debug("[DIAG POLLER] Sin TELEGRAM_ADMIN_CHAT_ID, poller deshabilitado.")
        return

    interval = max(INTERVAL_HOURS, 0.05) * 3600
    log_debug(f"=== DIAG POLLER ACTIVO (cada {INTERVAL_HOURS}h, 1era en {INITIAL_DELAY}s) ===")
    await asyncio.sleep(INITIAL_DELAY)
    loop = asyncio.get_event_loop()
    while True:
        await loop.run_in_executor(None, _run_and_notify)
        await asyncio.sleep(interval)
