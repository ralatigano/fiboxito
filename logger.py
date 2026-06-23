import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

from config import LOGS_DIR

os.makedirs(LOGS_DIR, exist_ok=True)


def get_logger() -> logging.Logger:
    logger = logging.getLogger("fiboxito")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(LOGS_DIR, "fiboxito.log"),
        when="midnight",
        backupCount=30,
        encoding="utf-8",
        delay=True,
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    from config import DEBUG
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if DEBUG else logging.ERROR)
    fmt = "%(message)s" if DEBUG else "[ERROR] %(message)s"
    console_handler.setFormatter(logging.Formatter(fmt))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


log = get_logger()


def log_conversacion(chat_id: int, nombre_usuario: str, mensaje: str, respuesta: str):
    ts = datetime.now().strftime("%H:%M:%S")
    log.info(f"[{ts}] chat_id:{chat_id} ({nombre_usuario}): {mensaje}")
    log.info(f"[{ts}] Fiboxito: {respuesta}")
    log.info("")


def log_debug(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    log.debug(f"[{ts}] {msg}")


def log_error(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    log.error(f"[{ts}] {msg}")
