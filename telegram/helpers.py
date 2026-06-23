import requests

from config import TELEGRAM_TOKEN, TELEGRAM_API  # noqa: F401 (TELEGRAM_TOKEN used in descargar_foto_telegram)
from logger import log_debug


def send_message(chat_id: int, text: str):
    log_debug(f"[TELEGRAM OUT] texto → chat_id={chat_id}")
    requests.post(f"{TELEGRAM_API}/sendMessage", data={"chat_id": chat_id, "text": text})


def send_document(chat_id: int, doc_bytes: bytes, filename: str, mime_type: str = "application/pdf"):
    log_debug(f"[TELEGRAM OUT] doc '{filename}' → chat_id={chat_id}")
    requests.post(
        f"{TELEGRAM_API}/sendDocument",
        data={"chat_id": chat_id},
        files={"document": (filename, doc_bytes, mime_type)}
    )


def send_photo(chat_id: int, photo_bytes: bytes, caption: str = ""):
    log_debug(f"[TELEGRAM OUT] foto → chat_id={chat_id}")
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    requests.post(
        f"{TELEGRAM_API}/sendPhoto",
        data=data,
        files={"photo": ("screenshot.png", photo_bytes, "image/png")},
        timeout=30,
    )


def descargar_foto_telegram(file_id: str) -> bytes | None:
    res = requests.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id}, timeout=10)
    file_path = res.json().get("result", {}).get("file_path")
    if not file_path:
        return None
    url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    r = requests.get(url, timeout=15)
    return r.content if r.status_code == 200 else None


def analizar_foto_telegram(msg_obj: dict) -> str:
    from routers.comprobantes import _analizar_imagen, _veredicto

    fotos = msg_obj.get("photo", [])
    file_id = fotos[-1]["file_id"]

    contenido = descargar_foto_telegram(file_id)
    if not contenido:
        return "No pude descargar la imagen. Intentá de nuevo."

    analisis = _analizar_imagen(contenido)
    resultado, motivo = _veredicto(analisis, monto_esperado=None)

    monto   = analisis.get("monto_detectado") or "no detectado"
    fecha   = analisis.get("fecha_detectada") or "no detectada"
    dest_ok = "si" if analisis.get("destinatario_ok") else "NO"

    return (
        f"Comprobante analizado: {resultado}\n"
        f"Destinatario correcto: {dest_ok}\n"
        f"Monto: {monto}\n"
        f"Fecha: {fecha}\n"
        f"Motivo: {motivo}"
    )
