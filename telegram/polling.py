import asyncio
import requests
from datetime import datetime

from config import TELEGRAM_API, MANUAL_FILE
from logger import log_debug, log_error, log_conversacion
from telegram.whitelist import es_autorizado, agregar_a_whitelist
from telegram.helpers import send_message, send_document, analizar_foto_telegram
from agent.handler import procesar_mensaje

AYUDA_TEMAS: dict[str, str] = {
    "cliente": (
        "Consultas de clientes\n"
        "──────────────────────\n"
        "Buscá por número de ID o por nombre:\n\n"
        '  "Dame el estado del cliente 1234"\n'
        '  "Buscame a González"\n'
        '  "Saldo de Martínez"\n'
        '  "Email y teléfono del 850"\n\n'
        "Datos disponibles: nombre, email, teléfono, dirección,\n"
        "saldo, contrato, plan y facturas recientes.\n\n"
        "Si en los siguientes mensajes preguntás más datos del\n"
        "mismo cliente, Fiboxito lo recuerda sin que repitas el ID."
    ),
    "factura": (
        "Facturas\n"
        "─────────\n"
        "Para ver las últimas facturas de un cliente:\n\n"
        '  "Facturas del 1234"\n'
        '  "¿Pagó Rodríguez?"\n'
        '  "Cobros de Martínez"\n\n'
        "Muestra las últimas 3 facturas con: número, período,\n"
        "monto, estado y fecha de vencimiento."
    ),
    "pdf": (
        "PDF de factura\n"
        "───────────────\n"
        "Para descargar el PDF de la última factura:\n\n"
        '  "Última factura de 1234"\n'
        '  "Dame el PDF del cliente González"\n'
        '  "Descargar factura del 850"\n\n'
        "El bot descarga el PDF desde Wispro y te lo envía\n"
        "como archivo adjunto directamente en este chat."
    ),
    "ip": (
        "IPs disponibles\n"
        "────────────────\n"
        "Consultá IPs libres por zona de red:\n\n"
        '  "IPs libres moldes"\n'
        '  "IPs disponibles pinares"\n'
        '  "IPs libres sta fe"\n\n'
        "Si no indicás zona, usa Moldes por defecto.\n"
        "Devuelve hasta 10 IPs disponibles del Mikrotik de la zona."
    ),
    "comprobante": (
        "Análisis de comprobantes\n"
        "─────────────────────────\n"
        "Mandá una foto de un comprobante de pago al chat.\n"
        "No hace falta escribir nada, solo enviá la imagen.\n\n"
        "Fiboxito verifica:\n"
        "  · ¿Es un comprobante válido?\n"
        "  · ¿El destinatario es Fibox?\n"
        "  · Monto y fecha detectados\n\n"
        "También funciona de forma automática desde Hola Suite:\n"
        "cuando un cliente comparte un comprobante, el bot lo\n"
        "analiza, cierra el ticket y te avisa por Telegram."
    ),
    "agregar": (
        "Agregar usuarios autorizados\n"
        "─────────────────────────────\n"
        "Solo admins. Ejecutá desde un chat ya autorizado:\n\n"
        "  /agregar 1024169379\n\n"
        "Para grupos (el ID es negativo):\n"
        "  /agregar -1001234567890\n\n"
        "El chat_id de un usuario aparece en el mensaje\n"
        "de 'acceso denegado' cuando intenta usar el bot."
    ),
    "manual": (
        "Manual completo\n"
        "────────────────\n"
        "Para descargar el manual completo de Fiboxito:\n\n"
        "  /manual\n\n"
        "El bot te envía el archivo con toda la documentación."
    ),
}

AYUDA_ALIAS: dict[str, str] = {
    "clientes":     "cliente",
    "facturas":     "factura",
    "boleta":       "factura",
    "ips":          "ip",
    "comprobantes": "comprobante",
    "pago":         "comprobante",
}


async def drain_pending_updates() -> int | None:
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None,
        lambda: requests.get(
            f"{TELEGRAM_API}/getUpdates",
            params={"timeout": 0},
            timeout=15
        ).json()
    )
    if "result" in res and res["result"]:
        last_id = res["result"][-1]["update_id"]
        log_debug(f"[DRAIN] {len(res['result'])} updates descartados. Arrancando desde {last_id + 1}")
        return last_id + 1
    log_debug("[DRAIN] Sin updates pendientes.")
    return None


async def polling_loop():
    offset = await drain_pending_updates()
    log_debug("=== POLLING ACTIVO ===")

    while True:
        try:
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(
                None,
                lambda o=offset: requests.get(
                    f"{TELEGRAM_API}/getUpdates",
                    params={"timeout": 5, "offset": o},
                    timeout=10
                ).json()
            )

            if "result" in res:
                for update in res["result"]:
                    offset = update["update_id"] + 1

                    if "message" not in update:
                        continue

                    msg_obj       = update["message"]
                    chat_id       = msg_obj["chat"]["id"]
                    text          = msg_obj.get("text", "").strip()
                    from_obj      = msg_obj.get("from", {})
                    nombre_usuario = from_obj.get("first_name", "").strip() or "empleado"

                    # --- FOTO: análisis de comprobante ---
                    if "photo" in msg_obj:
                        if not es_autorizado(chat_id):
                            await loop.run_in_executor(None, lambda: send_message(
                                chat_id,
                                f"Hola {nombre_usuario}, no tenés acceso a Fiboxito.\n"
                                f"Pedile a un admin que ejecute:\n/agregar {chat_id}"
                            ))
                            continue

                        log_debug(f"[TELEGRAM IN] chat_id={chat_id} ({nombre_usuario}) → foto recibida")
                        respuesta_foto = await loop.run_in_executor(
                            None, lambda: analizar_foto_telegram(msg_obj)
                        )
                        await loop.run_in_executor(None, lambda r=respuesta_foto: send_message(chat_id, r))
                        log_conversacion(chat_id, nombre_usuario, "[foto]", respuesta_foto)
                        continue

                    if not text:
                        continue

                    log_debug(f"[TELEGRAM IN] chat_id={chat_id} ({nombre_usuario}) → '{text}'")

                    # --- COMANDO /agregar ---
                    if text.startswith("/agregar"):
                        if not es_autorizado(chat_id):
                            await loop.run_in_executor(None, lambda: send_message(
                                chat_id, "No tenés permiso para usar este comando."
                            ))
                            continue

                        partes = text.strip().split()
                        try:
                            nuevo_id = int(partes[1]) if len(partes) == 2 else None
                            if nuevo_id is None:
                                raise ValueError
                        except ValueError:
                            await loop.run_in_executor(None, lambda: send_message(
                                chat_id, "Uso: /agregar <chat_id>\nEjemplo: /agregar 1024169379"
                            ))
                            continue

                        agregado  = agregar_a_whitelist(nuevo_id)
                        msg_resp  = (
                            f"✅ chat_id {nuevo_id} agregado correctamente." if agregado
                            else f"⚠️ El chat_id {nuevo_id} ya estaba en la lista."
                        )
                        await loop.run_in_executor(None, lambda m=msg_resp: send_message(chat_id, m))
                        log_debug(f"[WHITELIST] {msg_resp}")
                        continue

                    # --- CONTROL DE ACCESO ---
                    if not es_autorizado(chat_id):
                        await loop.run_in_executor(None, lambda: send_message(
                            chat_id,
                            f"Hola {nombre_usuario}, no tenés acceso a Fiboxito.\n"
                            f"Pedile a un admin que ejecute:\n/agregar {chat_id}"
                        ))
                        log_debug(f"[ACCESO DENEGADO] chat_id={chat_id} ({nombre_usuario})")
                        continue

                    # --- COMANDO /manual ---
                    if text.startswith("/manual"):
                        try:
                            with open(MANUAL_FILE, "rb") as f:
                                manual_bytes = f.read()
                            await loop.run_in_executor(
                                None,
                                lambda: send_document(chat_id, manual_bytes, "manual_fiboxito.txt", "text/plain")
                            )
                        except FileNotFoundError:
                            await loop.run_in_executor(None, lambda: send_message(
                                chat_id, "No encontré el archivo del manual. Avisale al admin."
                            ))
                        log_debug(f"[CMD] /manual → chat_id={chat_id}")
                        continue

                    # --- COMANDO /help ---
                    if text.startswith("/help"):
                        partes = text.strip().split(maxsplit=1)
                        if len(partes) == 1:
                            temas_lista = " · ".join(AYUDA_TEMAS.keys())
                            resp_help = (
                                f"Uso: /help [tema]\n\n"
                                f"Temas disponibles:\n{temas_lista}\n\n"
                                f"Ejemplo: /help cliente"
                            )
                        else:
                            tema      = partes[1].strip().lower()
                            tema      = AYUDA_ALIAS.get(tema, tema)
                            resp_help = AYUDA_TEMAS.get(
                                tema,
                                f"No encontré ayuda para '{tema}'.\n"
                                f"Temas disponibles: {' · '.join(AYUDA_TEMAS.keys())}"
                            )
                        await loop.run_in_executor(None, lambda r=resp_help: send_message(chat_id, r))
                        log_debug(f"[CMD] /help → chat_id={chat_id} tema='{text}'")
                        continue

                    # --- MENSAJE NORMAL ---
                    texto, pdf = await loop.run_in_executor(
                        None, lambda t=text, n=nombre_usuario: procesar_mensaje(chat_id, t, n)
                    )
                    await loop.run_in_executor(None, lambda: send_message(chat_id, texto))

                    if pdf:
                        periodo  = datetime.now().strftime("%Y-%m")
                        filename = f"factura_{periodo}.pdf"
                        await loop.run_in_executor(
                            None, lambda: send_document(chat_id, pdf, filename)
                        )

                    log_conversacion(chat_id, nombre_usuario, text, texto)

        except Exception as e:
            import traceback
            log_error(f"[ERROR en polling] {e}\n{traceback.format_exc()}")

        await asyncio.sleep(1)
