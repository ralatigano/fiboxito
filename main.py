import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import config  # ejecuta load_dotenv() antes que cualquier otro módulo
from config import DEBUG
from logger import log_debug
from db import init_db
from routers import mapa as mapa_router
from routers import comprobantes as comprobantes_router
from routers import opa_poller
from telegram.polling import polling_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    if DEBUG:
        log_debug("=== APP INICIADA [MODO DEBUG] — pollers externos deshabilitados ===")
    else:
        log_debug("=== APP INICIADA: arrancando polling en background ===")
    init_db()
    asyncio.create_task(polling_loop())
    if not DEBUG:
        asyncio.create_task(opa_poller.opa_polling_loop())
    yield
    log_debug("=== APP DETENIDA ===")


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(mapa_router.router)
app.include_router(comprobantes_router.router)
