import re

# Frases que disparan el intent OBS (se chequean ANTES que cliente para evitar
# colisiones con palabras como "estado" o "servicio").
_PALABRAS_OBS = [
    # estado general
    "transmisión", "transmision", "canal", "stream", "obs", "aire",
    "en vivo", "broadcasting",
    # fuentes de audio
    "radioFMEspacio", "radiofmespacio", "fm espacio", "radio san nicol",
    "radiosannicolas", "radio pop", "radiopop", "trasnoche",
    "fuente de audio", "fuentes", "fuente", "san nicol",
    # acciones stream
    "iniciá el stream", "inicia el stream", "arrancá el stream",
    "arranca el stream", "encendé el canal", "enciende el canal",
    "pará el stream", "para el stream", "cortá el canal", "corta el canal",
    "cortá la transmisión", "corta la transmision",
    "reiniciá obs", "reinicia obs", "reiniciá el canal", "reinicia el canal",
    "reiniciá la transmisión", "reinicia la transmision",
    # mute
    "silenciá", "silencia", "muteá", "mutea", "silencio",
    "quitá el silencio", "quita el silencio", "desilencia",
    # cámara
    "reiniciá la cámara", "reinicia la camara", "camara", "cámara",
    # watchdog
    "watchdog",
    # PC / servidor
    "la pc", "computadora", "reboot",
    "reiniciá la máquina", "reinicia la maquina", "reiniciar la maquina",
    # logs
    "log ", "logs",
    # screenshot
    "foto del canal", "captura", "screenshot", "pantalla del canal", "mandame una foto",
]


# Intent NAS (navegar/traer archivos del servidor).
# "factura/pdf/boleta" desactivan NAS para no chocar con el PDF de facturas.
_PALABRAS_NAS = [
    "nas", "carpeta", "carpetas", "directorio", "connelec",
    "archivo", "archivos", "servidor de archivos",
]
# Sustantivos inequívocos de NAS.
_NAS_NOUN = ["carpeta", "carpetas", "directorio", "connelec", "nas",
             "servidor de archivos"]
# Verbos de navegación (no existen en OBS): entrar/subir/raíz.
_NAV_VERBS = ["entrá", "entra", "abrí", "abri", "andá", "anda", "navegá",
              "navega", "volvé", "volve", "retrocedé", "retrocede", "subí",
              "subi", "atrás", "atras", "raíz", "raiz"]
_SEARCH_VERBS = ["buscá", "busca", "buscar", "encontrá", "encontra"]
_TRAER_VERBS = ["traeme", "traé", "descargá", "descarga", "bajá", "baja",
                "pasame", "mandame"]

# Palabras que indican una ACCIÓN/estado de OBS (no un nombre de archivo). Sirven
# para que, aun dentro de una sesión de navegación NAS, un comando real de OBS
# gane igual.
_OBS_ACCION = [
    "iniciá", "inicia", "arrancá", "arranca", "encendé", "enciende",
    "empezá", "empieza", "pará", "para", "cortá", "corta", "detené", "detene",
    "frená", "frena", "stop", "reiniciá", "reinicia", "reboot", "restart",
    "activá", "activa", "desactivá", "desactiva", "habilitá", "deshabilitá",
    "prendé", "prende", "apagá", "apaga", "silenciá", "silencia", "muteá",
    "mutea", "silencio", "foto", "captura", "screenshot", "logs", "estado",
    "status", "fuente", "fuentes", "aire", "watchdog",
]


def _es_nas_fuerte(t: str) -> bool:
    # Nota: acá NO filtramos por "factura/pdf" porque un archivo puede llamarse
    # así ("buscá el archivo factura"); el guard vive en el _es_nas débil.
    if any(w in t for w in _NAS_NOUN):
        return True
    if "/" in t and any(w in t for w in ["archivo"] + _TRAER_VERBS + ["entrá", "abrí"]):
        return True
    if any(w in t for w in _NAV_VERBS):
        return True
    # Buscar un ARCHIVO (search a secas es de clientes: "buscame a González").
    if any(w in t for w in _SEARCH_VERBS) and "archivo" in t:
        return True
    return False


def _es_nas(t: str) -> bool:
    if any(w in t for w in ["factura", "pdf", "boleta"]):
        return False
    return any(w in t for w in _PALABRAS_NAS)


def _obs_accion(t: str) -> bool:
    return any(w in t for w in _OBS_ACCION)


def detectar_intencion(texto: str, chat_id=None) -> str:
    t = texto.lower().strip()

    saludos = {
        "hola", "buenas", "qué tal", "que tal", "hey",
        "hola fiboxito", "buenos días", "buenas tardes", "buenas noches",
    }
    # Señales FUERTES de cliente (sustantivos/acciones propias del dominio):
    # ganan incluso durante una sesión de navegación NAS.
    palabras_cliente_fuerte = [
        "cliente", "saldo", "factura", "facturas",
        "cuenta corriente", "contrato", "dni", "pdf", "última factura",
        "último cliente", "ultimo cliente", "últimos clientes", "ultimos clientes",
        "ip libre", "ips libres", "ip disponible", "ips disponibles",
        # Acciones de servicio (cortar/reactivar) — todas sus conjugaciones
        "habilitar", "habilitá", "suspender", "suspendé", "suspende",
        "deshabilitar", "deshabilitá", "cortar", "cortá", "cortale",
        "reactivar", "reactivá", "reconectar", "reconectá", "restablecer",
        "restablecé", "dar de baja", "dar de alta", "reconexión",
    ]
    # Verbos genéricos (también sirven para navegar): solo derivan a cliente si
    # NO hay una sesión NAS abierta.
    palabras_cliente = palabras_cliente_fuerte + [
        "número", "pasame", "dame", "mostrame", "buscame", "busca",
    ]

    # ¿Hay una sesión de navegación NAS abierta para este chat?
    en_sesion_nas = False
    if chat_id is not None:
        try:
            from routers.nas.telegram_ops import en_sesion
            en_sesion_nas = en_sesion(chat_id)
        except Exception:  # noqa: BLE001
            en_sesion_nas = False

    if t in saludos:
        return "saludo"
    # NAS fuerte va antes que OBS (un path puede contener "stream", "canal", etc.)
    if _es_nas_fuerte(t):
        return "nas"
    # OBS gana si es un comando/estado real de OBS. Dentro de una sesión NAS,
    # solo gana si hay una ACCIÓN de OBS (para no robar nombres de archivo).
    if any(p in t for p in _PALABRAS_OBS) and (not en_sesion_nas or _obs_accion(t)):
        return "obs"
    # Señales fuertes de cliente ganan siempre (saldo, factura, contrato...).
    if any(p in t for p in palabras_cliente_fuerte):
        return "consulta_cliente"
    if _es_nas(t):
        return "nas"
    # Mientras se navega el NAS, los verbos genéricos siguen la navegación.
    if en_sesion_nas:
        return "nas"
    if any(p in t for p in palabras_cliente):
        return "consulta_cliente"
    return "general"


_FUENTES_ALIAS: dict[str, str] = {
    "fm espacio":       "RadioFMEspacio",
    "espacio":          "RadioFMEspacio",
    "san nicolas":      "RadioSanNicolas",
    "san nicolás":      "RadioSanNicolas",
    "radio san":        "RadioSanNicolas",
    "radio pop":        "RadioPop",
    "pop":              "RadioPop",
    "trasnoche":        "RadioPop",
    "trasnoche paranormal": "RadioPop",
    "camara":           "camara",
    "cámara":           "camara",
    "carrusel":         "carrusel",
}


def clasificar_intent_obs(texto: str) -> dict:
    """
    Analiza el texto y retorna {"accion": str, "param": str|None}.

    Acciones posibles:
      status | start | stop | restart | restart_stream | restart_camera |
      restart_watchdog | enable_watchdog | disable_watchdog | reboot_pc |
      mute | unmute | logs | fuentes |
      activar_fuente | desactivar_fuente | watchdog_status
    """
    t = texto.lower().strip()

    # Palabras que indican apagar/deshabilitar (se reusan para watchdog y fuentes).
    # Nota: "desactivá" contiene "activá", por eso SIEMPRE hay que chequear estas
    # antes que las de activar para no confundir desactivar con activar.
    _OFF = ["desactivá", "desactiva", "deshabilitá", "deshabilita",
            "apagá", "apaga", "pausá", "pausa", "detené", "detene",
            "frená", "frena", "ocultá", "oculta"]
    _ON  = ["activá", "activa", "habilitá", "habilita",
            "prendé", "prende", "encendé", "enciende", "reanudá", "reanuda"]

    # ── Mute / Unmute ────────────────────────────────────────────
    if any(p in t for p in ["silenciá", "silencia", "muteá", "mutea", "silencio"]):
        if any(p in t for p in ["quitá", "quita", "des", "activ"]):
            return {"accion": "unmute", "param": None}
        return {"accion": "mute", "param": None}
    if any(p in t for p in ["quitá el silencio", "quita el silencio", "desilencia"]):
        return {"accion": "unmute", "param": None}

    # ── Reiniciar la PC ──────────────────────────────────────────
    # Va antes que el bloque de restart genérico para no confundirse con el stream.
    if any(p in t for p in ["reinici", "reboot", "rebootea", "restart"]) and \
       any(p in t for p in ["la pc", "computadora", "compu", "máquina", "maquina", "servidor"]):
        return {"accion": "reboot_pc", "param": None}

    # ── Watchdog: habilitar / deshabilitar ───────────────────────
    # Antes que restart y que start/stop, porque "desactivá" colisiona con start.
    if "watchdog" in t:
        if any(p in t for p in _OFF):
            return {"accion": "disable_watchdog", "param": None}
        if any(p in t for p in _ON):
            return {"accion": "enable_watchdog", "param": None}

    # ── Restart ──────────────────────────────────────────────────
    if any(p in t for p in ["reinici", "restart"]):
        if any(p in t for p in ["camara", "cámara"]):
            return {"accion": "restart_camera", "param": None}
        if "watchdog" in t:
            return {"accion": "restart_watchdog", "param": None}
        if any(p in t for p in ["obs", "programa", "aplicacion", "aplicación"]):
            return {"accion": "restart", "param": None}
        # "reiniciá la transmisión/el stream/el canal" → restart stream, no OBS
        return {"accion": "restart_stream", "param": None}

    # ── Desactivar fuente ────────────────────────────────────────
    # SIEMPRE antes de activar (ver nota sobre "desactivá"/"activá") y antes de
    # start/stop, para que "desactivá la fuente X" no se confunda con otra acción.
    if any(p in t for p in _OFF):
        for alias, nombre in _FUENTES_ALIAS.items():
            if alias in t:
                return {"accion": "desactivar_fuente", "param": nombre}

    # ── Start / Stop stream ──────────────────────────────────────
    if any(p in t for p in ["iniciá", "inicia", "arrancá", "arranca", "encendé", "enciende", "empezá", "empieza"]):
        return {"accion": "start", "param": None}
    if any(p in t for p in ["pará", "para", "cortá", "corta", "detené", "detene", "stop"]):
        return {"accion": "stop", "param": None}

    # ── Logs ─────────────────────────────────────────────────────
    if any(p in t for p in ["log", "logs"]):
        if any(p in t for p in ["camara", "cámara"]):
            return {"accion": "logs", "param": "camara"}
        if "watchdog" in t:
            return {"accion": "logs", "param": "watchdog"}
        return {"accion": "logs", "param": "obs"}

    # ── Watchdog status ──────────────────────────────────────────
    if "watchdog" in t:
        return {"accion": "watchdog_status", "param": None}

    # ── Activar fuente ───────────────────────────────────────────
    if any(p in t for p in ["cambiá", "cambia", "poné", "pon", "activá", "activa", "pasá a", "pasa a", "cambiá a", "cambia a"]):
        for alias, nombre in _FUENTES_ALIAS.items():
            if alias in t:
                return {"accion": "activar_fuente", "param": nombre}

    # ── Screenshot ───────────────────────────────────────────────
    if any(p in t for p in ["foto", "captura", "screenshot", "pantalla"]):
        return {"accion": "screenshot", "param": None}

    # ── Fuentes / estado ─────────────────────────────────────────
    if any(p in t for p in ["fuentes", "fuente de audio", "qué fuente", "que fuente", "qué está sonando", "que esta sonando"]):
        return {"accion": "fuentes", "param": None}

    # ── Status (fallback para todo lo que mencione transmisión/canal/stream) ─
    return {"accion": "status", "param": None}


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
