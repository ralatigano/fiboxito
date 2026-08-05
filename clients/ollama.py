import requests

from config import OLLAMA_URL, MODEL
from logger import log_debug, log_error


def ask_ollama(prompt: str) -> str:
    log_debug(f"[OLLAMA] Enviando prompt:\n{prompt}")
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.5,
            "num_predict": 250,
        },
        "stop": [
            "\nMensaje del usuario:",
            "\nMensaje del empleado:",
            "\nConsulta del empleado:",
            "\nEmpleado:",
            "\nUsuario:",
            "\n###",
        ],
    }
    response = requests.post(OLLAMA_URL, json=payload)
    data = response.json()
    if "response" not in data:
        log_error(f"[OLLAMA] Respuesta inesperada: {data}")
        return "Lo siento, no pude generar una respuesta en este momento."
    result = data["response"].strip()
    log_debug(f"[OLLAMA] Respuesta:\n{result}")
    return result


def classify_ollama(prompt: str, timeout: int = 12) -> str:
    """Clasificación rápida (routing de intención). Temperatura 0 y salida mínima:
    NO redacta, solo devuelve una etiqueta. Nunca lanza: ante cualquier error
    devuelve '' para que el llamador aplique su fallback determinístico."""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 8},
    }
    try:
        data = requests.post(OLLAMA_URL, json=payload, timeout=timeout).json()
        return data.get("response", "").strip()
    except Exception as e:  # noqa: BLE001
        log_error(f"[OLLAMA] classify falló: {e}")
        return ""
