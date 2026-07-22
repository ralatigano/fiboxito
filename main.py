import asyncio
import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import config  # ejecuta load_dotenv() antes que cualquier otro módulo
from config import DEBUG, OBS_POLLER_ENABLED
from logger import log_debug, log_error
from db import init_db
from telegram.helpers import send_message
from routers import mapa as mapa_router
from routers import comprobantes as comprobantes_router
from routers import opa_poller
from routers.obs import router as obs_router
from routers.obs.poller import obs_polling_loop
from routers.nas import router as nas_router
from telegram.polling import polling_loop


def _notificar_arranque():
    """Avisa a los admin que Fiboxito volvió a estar activo (p. ej. tras un
    reinicio del HOST). Se dispara en cada arranque exitoso del backend.
    Silenciable con STARTUP_NOTIFY=false en el .env."""
    if os.getenv("STARTUP_NOTIFY", "true").lower() not in ("true", "1", "yes"):
        return
    admin_ids = [
        int(x.strip())
        for x in os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").split(",")
        if x.strip()
    ]
    if not admin_ids:
        return
    host  = socket.gethostname()
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    texto = f"🟢 Fiboxito volvió a estar activo.\nHost: {host}\n{ahora}"
    for chat_id in admin_ids:
        try:
            send_message(chat_id, texto)
        except Exception as e:
            log_error(f"[STARTUP] Error notificando arranque a {chat_id}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if DEBUG:
        log_debug("=== APP INICIADA [MODO DEBUG] — opa_poller deshabilitado ===")
    else:
        log_debug("=== APP INICIADA: arrancando polling en background ===")
    init_db()
    asyncio.create_task(polling_loop())
    if not DEBUG:
        asyncio.create_task(opa_poller.opa_polling_loop())
    if not DEBUG or OBS_POLLER_ENABLED:
        asyncio.create_task(obs_polling_loop())
    _notificar_arranque()
    yield
    log_debug("=== APP DETENIDA ===")


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(mapa_router.router)
app.include_router(comprobantes_router.router)
app.include_router(obs_router.router)
app.include_router(nas_router.router)
