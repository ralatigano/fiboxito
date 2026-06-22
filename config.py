import os
from dotenv import load_dotenv

# Debe ejecutarse antes de que cualquier otro módulo lea os.getenv()
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL          = os.getenv("MODEL", "llama3.2:3b")
WISPRO_URL     = os.getenv("WISPRO_URL", "").rstrip("/")
WISPRO_TOKEN   = os.getenv("WISPRO_TOKEN", "")
MIKROTIKS = {
    "moldes":  {"id": os.getenv("MIKROTIK_MOLDES_ID"),  "rango": os.getenv("MIKROTIK_MOLDES_RANGO",  "172.19.102")},
    "pinares": {"id": os.getenv("MIKROTIK_PINARES_ID"), "rango": os.getenv("MIKROTIK_PINARES_RANGO", "172.18.100")},
    "sta fe":  {"id": os.getenv("MIKROTIK_STAFE_ID"),   "rango": os.getenv("MIKROTIK_STAFE_RANGO",   "172.19.102")},
}
TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
LOGS_DIR       = os.getenv("LOGS_DIR", "logs")
WHITELIST_FILE = os.getenv("WHITELIST_FILE", "whitelist.json")
MEMORIA_TURNOS = int(os.getenv("MEMORIA_TURNOS", "5"))
MANUAL_FILE    = os.getenv("MANUAL_FILE", "manual_fiboxito.txt")
DEBUG          = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

if not TELEGRAM_TOKEN:
    raise ValueError("Falta TELEGRAM_TOKEN en el archivo .env")
if not WISPRO_URL or not WISPRO_TOKEN:
    raise ValueError("Faltan WISPRO_URL o WISPRO_TOKEN en el archivo .env")
