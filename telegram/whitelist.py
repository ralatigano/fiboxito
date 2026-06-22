import json
import os

from config import WHITELIST_FILE


def cargar_whitelist() -> list[int]:
    if not os.path.exists(WHITELIST_FILE):
        return []
    with open(WHITELIST_FILE, "r") as f:
        return json.load(f)


def guardar_whitelist(whitelist: list[int]):
    with open(WHITELIST_FILE, "w") as f:
        json.dump(whitelist, f, indent=2)


def es_autorizado(chat_id: int) -> bool:
    return chat_id in cargar_whitelist()


def agregar_a_whitelist(chat_id: int) -> bool:
    """Retorna True si se agregó, False si ya existía."""
    whitelist = cargar_whitelist()
    if chat_id in whitelist:
        return False
    whitelist.append(chat_id)
    guardar_whitelist(whitelist)
    return True
