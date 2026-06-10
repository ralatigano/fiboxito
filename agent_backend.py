import asyncio
import logging
import os
import re
import requests
from contextlib import asynccontextmanager
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI
from logging.handlers import TimedRotatingFileHandler
import json

# --- CONFIGURACIÓN ---
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("MODEL", "llama3.2:3b")
WISPRO_URL = os.getenv("WISPRO_URL", "").rstrip("/")
WISPRO_TOKEN = os.getenv("WISPRO_TOKEN", "")
MIKROTIKS = {
    "moldes":   {"id": os.getenv("MIKROTIK_MOLDES_ID"),  "rango": os.getenv("MIKROTIK_MOLDES_RANGO",  "172.19.102")},
    "pinares":  {"id": os.getenv("MIKROTIK_PINARES_ID"), "rango": os.getenv("MIKROTIK_PINARES_RANGO", "172.18.100")},
    "sta fe":   {"id": os.getenv("MIKROTIK_STAFE_ID"),   "rango": os.getenv("MIKROTIK_STAFE_RANGO",   "172.19.102")},
}
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
LOGS_DIR = os.getenv("LOGS_DIR", "logs")

if not TELEGRAM_TOKEN:
    raise ValueError("Falta TELEGRAM_TOKEN en el archivo .env")
if not WISPRO_URL or not WISPRO_TOKEN:
    raise ValueError("Faltan WISPRO_URL o WISPRO_TOKEN en el archivo .env")


# ---------------------------
# LOGGING
# ---------------------------

os.makedirs(LOGS_DIR, exist_ok=True)


def get_logger() -> logging.Logger:
    logger = logging.getLogger("fiboxito")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Archivo rotado por día: logs/fiboxito_2026-06-01.log
    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(LOGS_DIR, "fiboxito.log"),
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    # Consola (mínimo, solo errores)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(logging.Formatter("[ERROR] %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


log = get_logger()


def log_conversacion(chat_id: int, nombre_usuario: str, mensaje: str, respuesta: str):
    ts = datetime.now().strftime("%H:%M:%S")
    log.info(f"[{ts}] chat_id:{chat_id} ({nombre_usuario}): {mensaje}")
    log.info(f"[{ts}] Fiboxito: {respuesta}")
    log.info("")   # línea en blanco entre turnos


def log_debug(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    log.debug(f"[{ts}] {msg}")


def log_error(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    log.error(f"[{ts}] {msg}")


WHITELIST_FILE = os.getenv("WHITELIST_FILE", "whitelist.json")
MEMORIA_TURNOS = int(os.getenv("MEMORIA_TURNOS", "5")
                     )  # turnos por usuario a recordar
historial: dict[int, list[dict]] = {}  # chat_id → lista de {role, content}


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
# ---------------------------
# LIFESPAN
# ---------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_debug("=== APP INICIADA: arrancando polling en background ===")
    asyncio.create_task(polling_loop())
    yield
    log_debug("=== APP DETENIDA ===")


app = FastAPI(lifespan=lifespan)


# ---------------------------
# WISPRO API
# ---------------------------

WISPRO_HEADERS = {
    "Accept": "application/json",
    "Authorization": WISPRO_TOKEN,
}


def wispro_get(endpoint: str, params: dict = None, timeout: int = 10) -> dict:
    url = f"{WISPRO_URL}/api/v1/{endpoint}"
    log_debug(f"[WISPRO] GET {url} params={params}")
    res = requests.get(url, headers=WISPRO_HEADERS,
                       params=params, timeout=timeout)
    data = res.json()
    log_debug(
        f"[WISPRO] status={data.get('status')} registros={len(data.get('data', []))}")
    return data


def buscar_cliente(termino: str) -> dict | None:
    if termino.isdigit():
        data = wispro_get("clients", {"public_id_eq": termino})
    else:
        data = wispro_get("clients", {"name_unaccent_cont": termino})
    if data.get("status") == 200 and data.get("data"):
        return data["data"][0]
    return None


def obtener_contratos(client_id: str) -> list:
    data = wispro_get("contracts", {"client_id_eq": client_id})
    if data.get("status") == 200:
        return data.get("data", [])
    return []


def obtener_cuenta_corriente(client_id: str) -> dict | None:
    data = wispro_get(f"clients/{client_id}/current_account")
    if data.get("status") == 200:
        return data.get("data")
    return None


def obtener_facturas(client_id: str, limite: int = 3) -> list:
    data = wispro_get("invoicing/invoices", {
        "client_custom_id_eq": client_id,
        "per_page": 999
    }, timeout=50)
    if data.get("status") == 200:
        facturas = data.get("data", [])
        facturas = [f for f in facturas if f.get("state") != "void"]
        facturas.sort(key=lambda x: x.get("issued_at", ""), reverse=True)
        return facturas[:limite]
    return []


def descargar_pdf_factura(invoice_id: str) -> bytes | None:
    url = f"{WISPRO_URL}/api/v1/invoicing/invoices/{invoice_id}/download_pdf"
    log_debug(f"[WISPRO] Descargando PDF factura {invoice_id}")
    res = requests.get(url, headers=WISPRO_HEADERS, timeout=15)
    if res.status_code == 200:
        return res.content
    log_error(f"[WISPRO] Error descargando PDF: {res.status_code}")
    return None


def obtener_ultimos_clientes(cantidad: int = 10) -> list:
    data = wispro_get("clients", {"per_page": 20})
    if data.get("status") != 200:
        return []
    total_pages = data.get("meta", {}).get(
        "pagination", {}).get("total_pages", 1)
    data = wispro_get("clients", {"per_page": 20, "page": total_pages})
    if data.get("status") == 200 and data.get("data"):
        clientes = data["data"]
        # últimos N, más reciente primero
        return list(reversed(clientes[-cantidad:]))
    return []


def obtener_ips_libres(zona: str = "moldes") -> list:
    mk = MIKROTIKS.get(zona.lower())
    if not mk or not mk["id"]:
        return []
    url = f"mikrotiks/{mk['id']}/free_ips"
    log_debug(f"[WISPRO] IPs libres zona={zona} rango={mk['rango']}")
    res = requests.get(
        f"{WISPRO_URL}/api/v1/{url}",
        headers=WISPRO_HEADERS,
        params={"ip_cont": mk["rango"]},
        timeout=15
    )
    if res.status_code == 200:
        return res.json()
    return []
# ---------------------------
# TELEGRAM
# ---------------------------


def send_message(chat_id: int, text: str):
    log_debug(f"[TELEGRAM OUT] texto → chat_id={chat_id}")
    requests.post(f"{TELEGRAM_API}/sendMessage",
                  data={"chat_id": chat_id, "text": text})


def send_document(chat_id: int, pdf_bytes: bytes, filename: str):
    log_debug(f"[TELEGRAM OUT] PDF '{filename}' → chat_id={chat_id}")
    requests.post(
        f"{TELEGRAM_API}/sendDocument",
        data={"chat_id": chat_id},
        files={"document": (filename, pdf_bytes, "application/pdf")}
    )


# ---------------------------
# OLLAMA
# ---------------------------

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
    result = response.json()["response"].strip()
    log_debug(f"[OLLAMA] Respuesta:\n{result}")
    return result


# ---------------------------
# CLASIFICACIÓN DE INTENCIÓN
# ---------------------------

def detectar_intencion(texto: str) -> str:
    t = texto.lower().strip()

    saludos = {
        "hola", "buenas", "qué tal", "que tal", "hey",
        "hola fiboxito", "buenos días", "buenas tardes", "buenas noches",
    }
    palabras_cliente = [
        "cliente", "estado", "saldo", "factura", "facturas", "servicio",
        "cuenta", "corriente", "contrato", "habilitar", "suspender",
        "deshabilitar", "cortar", "dni", "número", "pasame", "dame",
        "mostrame", "buscame", "busca", "pdf", "última factura",
        "último cliente", "ultimo cliente", "últimos clientes", "ultimos clientes",
        "ip", "ips", "ip libre", "ips libres", "ip disponible", "ips disponibles",
    ]

    if t in saludos:
        return "saludo"
    if any(p in t for p in palabras_cliente):
        return "consulta_cliente"
    return "general"


def extraer_termino_busqueda(texto: str) -> str | None:
    match = re.search(r'\b(\d+)\b', texto)
    if match:
        return match.group(1)

    patrones_nombre = [
        r'cliente\s+([A-Za-záéíóúÁÉÍÓÚñÑ\s]+)',
        r'de\s+([A-Za-záéíóúÁÉÍÓÚñÑ\s]{3,})',
        r'buscame\s+(?:a\s+)?([A-Za-záéíóúÁÉÍÓÚñÑ\s]{3,})',
        r'pasame\s+(?:a\s+)?([A-Za-záéíóúÁÉÍÓÚñÑ\s]{3,})',
    ]
    for patron in patrones_nombre:
        m = re.search(patron, texto, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


# ---------------------------
# PROMPTS
# ---------------------------

def prompt_saludo(user_message: str, nombre_usuario: str) -> str:
    return (
        "Sos Fiboxito, asistente interno de Fibox. Tratás a los empleados de forma amable y cercana.\n"
        f"El empleado se llama {nombre_usuario}. Usá su nombre en el saludo.\n"
        "PROHIBIDO mencionar clientes, nombres de clientes, saldos, servicios o cualquier dato de gestión.\n"
        "Respondé en una sola oración.\n\n"
        f"Mensaje: {user_message}\n"
        "Respuesta (solo el saludo):"
    )


def prompt_cliente_no_encontrado(user_message: str, termino: str, nombre_usuario: str) -> str:
    return (
        "Sos Fiboxito, asistente interno de Fibox. Tratás a los empleados de forma amable y cercana.\n"
        f"El empleado se llama {nombre_usuario}.\n"
        f"Buscaste el cliente '{termino}' en Wispro pero no se encontró ningún resultado.\n"
        "Informale amablemente e indicale que verifique el ID o el nombre.\n"
        "Respondé en una sola oración.\n\n"
        f"Consulta: {user_message}\n"
        "Respuesta:"
    )


def prompt_cliente_sin_termino(user_message: str, nombre_usuario: str) -> str:
    return (
        "Sos Fiboxito, asistente interno de Fibox. Tratás a los empleados de forma amable y cercana.\n"
        f"El empleado se llama {nombre_usuario}.\n"
        "Quiere consultar un cliente pero no especificó ID ni nombre.\n"
        "Pedile amablemente que especifique el ID o el nombre del cliente.\n"
        "Respondé en una sola oración.\n\n"
        f"Consulta: {user_message}\n"
        "Respuesta:"
    )


def prompt_general(user_message: str, nombre_usuario: str, contexto: str = "") -> str:
    ctx_bloque = f"\n{contexto}\n" if contexto else ""
    return (
        "Sos Fiboxito, asistente interno de Fibox. Tratás a los empleados de forma amable y cercana.\n"
        f"El empleado se llama {nombre_usuario}. Usá su nombre ocasionalmente.\n"
        "Respondé de forma profesional, breve y amigable.\n"
        "NO inventes datos de clientes ni menciones saldos o servicios.\n"
        f"{ctx_bloque}\n"
        f"Mensaje de {nombre_usuario}: {user_message}\n"
        "Respuesta:"
    )


# ---------------------------
# RESPUESTA DIRECTA DESDE WISPRO
# Retorna (texto, pdf_bytes | None)
# ---------------------------

def respuesta_directa(
    cliente: dict,
    contratos: list,
    facturas: list,
    cuenta: dict | None,
    user_message: str,
    nombre_usuario: str,
) -> tuple[str, bytes | None]:

    msg = user_message.lower()
    nombre = cliente.get("name", "N/A")
    email = cliente.get("email", "N/A")
    telefono = cliente.get("phone") or "No registrado"
    direccion = f"{cliente.get('street', '')} {cliente.get('number', '')}".strip(
    ) or "No registrada"
    public_id = cliente.get("public_id", "N/A")

    # --- PDF de última factura ---
    if any(p in msg for p in ["pdf", "última factura", "ultima factura", "descargar"]):
        if not facturas:
            return f"No encontré facturas para {nombre}, {nombre_usuario}.", None
        ultima = facturas[0]
        invoice_id = ultima.get("id")
        pdf = descargar_pdf_factura(invoice_id)
        if pdf:
            periodo = f"{ultima.get('from', '?')} al {ultima.get('to', '?')}"
            filename = f"factura_{nombre.replace(' ', '_')}_{periodo}.pdf"
            return f"Acá va la última factura de {nombre} ({periodo}).", pdf
        return f"No pude descargar el PDF de la última factura de {nombre}.", None

    # --- Consultas puntuales de texto ---
    if any(p in msg for p in ["nombre", "quién es", "quien es"]):
        return f"El cliente #{public_id} es {nombre}.", None

    if any(p in msg for p in ["email", "correo", "mail"]):
        return f"El email de {nombre} es {email}.", None

    if any(p in msg for p in ["teléfono", "telefono", "cel"]):
        return f"El teléfono de {nombre} es {telefono}.", None

    if any(p in msg for p in ["dirección", "direccion", "domicilio", "vive"]):
        return f"La dirección de {nombre} es {direccion}.", None

    if any(p in msg for p in ["saldo", "cuenta", "balance", "debe", "deuda"]):
        if cuenta:
            saldo = cuenta.get("balance", "N/A")
            credito = cuenta.get("available_credit", "N/A")
            return f"Cuenta corriente de {nombre}: saldo {saldo}, crédito disponible {credito}.", None
        return f"No se pudo obtener la cuenta corriente de {nombre}.", None

    if any(p in msg for p in ["contrato", "plan", "servicio", "estado"]):
        if contratos:
            c = contratos[0]
            estado = c.get("state", "N/A")
            plan = c.get("plan_name", c.get("plan", {}).get("name", "N/A"))
            return f"Contrato de {nombre}: plan {plan}, estado {estado}.", None
        return f"{nombre} no tiene contratos registrados.", None

    if any(p in msg for p in ["factura", "facturas", "boleta", "cobro", "pagó", "pago"]):
        if not facturas:
            return f"{nombre} no tiene facturas registradas.", None
        lineas = [f"Últimas facturas de {nombre}:"]
        for f in facturas:
            estado = f.get("state", "N/A")
            monto = f.get("amount", "N/A")
            periodo = f"{f.get('from', '?')} → {f.get('to', '?')}"
            vence = f.get("first_due_date", "N/A")
            lineas.append(
                f"  • #{f.get('invoice_number')} | {periodo} | ${monto} | {estado} | vence {vence}")
        return "\n".join(lineas), None

    # --- Ficha completa ---
    lineas = [f"📋 Cliente #{public_id}: {nombre}"]
    lineas.append(f"📧 Email: {email}")
    lineas.append(f"📞 Teléfono: {telefono}")
    lineas.append(f"📍 Dirección: {direccion}")
    if cuenta:
        lineas.append(f"💰 Saldo: {cuenta.get('balance', 'N/A')}")
    if contratos:
        c = contratos[0]
        estado = c.get("state", "N/A")
        plan = c.get("plan_name", c.get("plan", {}).get("name", "N/A"))
        lineas.append(f"📄 Contrato: plan {plan} | estado {estado}")
    return "\n".join(lineas), None


# ---------------------------
# LÓGICA PRINCIPAL DEL AGENTE
# ---------------------------

def procesar_mensaje(chat_id: int, user_message: str, nombre_usuario: str) -> tuple[str, bytes | None]:
    intencion = detectar_intencion(user_message)
    log_debug(f"[INTENT] '{user_message}' → '{intencion}'")

    actualizar_historial(chat_id, "user", user_message)
    ctx = contexto_reciente(chat_id)
    msg = user_message.lower()

    if intencion == "saludo":
        respuesta = ask_ollama(prompt_saludo(user_message, nombre_usuario))
        actualizar_historial(chat_id, "assistant", respuesta)
        return respuesta, None

    if intencion == "consulta_cliente":

        # Últimos clientes
        if any(p in msg for p in ["último cliente", "ultimo cliente", "últimos clientes", "ultimos clientes", "último id", "nuevo cliente"]):
            clientes = obtener_ultimos_clientes()
            if not clientes:
                return "No pude obtener los últimos clientes.", None
            lineas = ["Últimos clientes registrados:"]
            for c in clientes:
                pid = c.get("public_id", "N/A")
                nombre = c.get("name", "N/A")
                fecha = c.get("created_at", "")[:10]
                username = f"client{pid}"
                lineas.append(f"  #{pid} — {nombre} ({fecha}) → {username}")
            respuesta = "\n".join(lineas)
            actualizar_historial(chat_id, "assistant", respuesta)
            return respuesta, None

        # IPs libres
        if any(p in msg for p in ["ip", "ips", "ip libre", "ips libres", "ip disponible", "ips disponibles"]):
            zona = "pinares" if "pinares" in msg else "sta fe" if "sta fe" in msg else "moldes"
            mk = MIKROTIKS.get(zona, {})
            ips = obtener_ips_libres(zona)
            if not ips:
                respuesta = f"No encontré IPs libres para {zona} o hubo un error."
            else:
                lista = "\n".join(f"  {ip}" for ip in ips[:10])
                respuesta = f"IPs libres en {zona.title()} ({mk.get('rango', '')}.X):\n{lista}"
            actualizar_historial(chat_id, "assistant", respuesta)
            return respuesta, None

        # Búsqueda de cliente
        termino = extraer_termino_busqueda(user_message)
        log_debug(f"[WISPRO] Buscando término: '{termino}'")

        if not termino:
            termino = cliente_del_historial(chat_id)
            if termino:
                log_debug(
                    f"[MEMORIA] Usando cliente del historial: '{termino}'")

        if not termino:
            respuesta = ask_ollama(prompt_cliente_sin_termino(
                user_message, nombre_usuario))
            actualizar_historial(chat_id, "assistant", respuesta)
            return respuesta, None

        cliente = buscar_cliente(termino)

        if not cliente:
            respuesta = ask_ollama(prompt_cliente_no_encontrado(
                user_message, termino, nombre_usuario))
            actualizar_historial(chat_id, "assistant", respuesta)
            return respuesta, None

        client_id = str(cliente.get("id", ""))
        contratos = obtener_contratos(client_id)
        cuenta = obtener_cuenta_corriente(client_id)
        custom_id = str(cliente.get("custom_id", "")).zfill(4)
        facturas = obtener_facturas(custom_id)

        texto, pdf = respuesta_directa(
            cliente, contratos, facturas, cuenta, user_message, nombre_usuario)
        log_debug(f"[RESPUESTA DIRECTA]\n{texto}")
        actualizar_historial(chat_id, "assistant", texto)
        return texto, pdf

    respuesta = ask_ollama(prompt_general(user_message, nombre_usuario, ctx))
    actualizar_historial(chat_id, "assistant", respuesta)
    return respuesta, None


def actualizar_historial(chat_id: int, rol: str, contenido: str):
    if chat_id not in historial:
        historial[chat_id] = []
    historial[chat_id].append({"role": rol, "content": contenido})
    # Mantener solo los últimos N turnos (un turno = 1 user + 1 assistant)
    if len(historial[chat_id]) > MEMORIA_TURNOS * 2:
        historial[chat_id] = historial[chat_id][-(MEMORIA_TURNOS * 2):]


def contexto_reciente(chat_id: int) -> str:
    """Formatea el historial como texto para incluir en el prompt."""
    turnos = historial.get(chat_id, [])
    if not turnos:
        return ""
    lineas = ["Conversación reciente:"]
    for t in turnos:
        prefijo = "Empleado" if t["role"] == "user" else "Fiboxito"
        lineas.append(f"{prefijo}: {t['content']}")
    return "\n".join(lineas)


def cliente_del_historial(chat_id: int) -> str | None:
    """
    Busca en el historial si se mencionó un cliente recientemente.
    Retorna el ID o nombre encontrado, o None.
    """
    turnos = historial.get(chat_id, [])
    # Recorremos del más reciente al más viejo
    for turno in reversed(turnos):
        termino = extraer_termino_busqueda(turno["content"])
        if termino:
            return termino
    return None
# ---------------------------
# LOOP DE POLLING (async)
# ---------------------------


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
        log_debug(
            f"[DRAIN] {len(res['result'])} updates descartados. Arrancando desde {last_id + 1}")
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
                    params={"timeout": 10, "offset": o},
                    timeout=15
                ).json()
            )

            if "result" in res:
                for update in res["result"]:
                    offset = update["update_id"] + 1

                    if "message" not in update:
                        continue

                    msg_obj = update["message"]
                    chat_id = msg_obj["chat"]["id"]
                    text = msg_obj.get("text", "").strip()
                    from_obj = msg_obj.get("from", {})
                    nombre_usuario = from_obj.get(
                        "first_name", "").strip() or "empleado"

                    if not text:
                        continue

                    log_debug(
                        f"[TELEGRAM IN] chat_id={chat_id} ({nombre_usuario}) → '{text}'")

                    # --- COMANDO /agregar ---
                    if text.startswith("/agregar"):
                        if not es_autorizado(chat_id):
                            await loop.run_in_executor(None, lambda: send_message(
                                chat_id, "No tenés permiso para usar este comando."
                            ))
                            continue

                        partes = text.strip().split()
                        if len(partes) != 2 or not partes[1].isdigit():
                            await loop.run_in_executor(None, lambda: send_message(
                                chat_id, "Uso: /agregar <chat_id>\nEjemplo: /agregar 1024169379"
                            ))
                            continue

                        nuevo_id = int(partes[1])
                        agregado = agregar_a_whitelist(nuevo_id)
                        msg_resp = f"✅ chat_id {nuevo_id} agregado correctamente." if agregado \
                            else f"⚠️ El chat_id {nuevo_id} ya estaba en la lista."
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
                        log_debug(
                            f"[ACCESO DENEGADO] chat_id={chat_id} ({nombre_usuario})")
                        continue

                    texto, pdf = await loop.run_in_executor(
                        None, lambda t=text, n=nombre_usuario: procesar_mensaje(
                            chat_id, t, n)
                    )

                    await loop.run_in_executor(None, lambda: send_message(chat_id, texto))

                    if pdf:
                        periodo = datetime.now().strftime("%Y-%m")
                        filename = f"factura_{periodo}.pdf"
                        await loop.run_in_executor(
                            None, lambda: send_document(chat_id, pdf, filename)
                        )

                    log_conversacion(chat_id, nombre_usuario, text, texto)

        except Exception as e:
            import traceback
            log_error(f"[ERROR en polling] {e}\n{traceback.format_exc()}")

        await asyncio.sleep(1)
