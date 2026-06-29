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


def detectar_intencion(texto: str) -> str:
    t = texto.lower().strip()

    saludos = {
        "hola", "buenas", "qué tal", "que tal", "hey",
        "hola fiboxito", "buenos días", "buenas tardes", "buenas noches",
    }
    palabras_cliente = [
        "cliente", "saldo", "factura", "facturas",
        "cuenta corriente", "contrato", "habilitar", "suspender",
        "deshabilitar", "cortar", "dni", "número", "pasame", "dame",
        "mostrame", "buscame", "busca", "pdf", "última factura",
        "último cliente", "ultimo cliente", "últimos clientes", "ultimos clientes",
        "ip libre", "ips libres", "ip disponible", "ips disponibles",
    ]

    if t in saludos:
        return "saludo"
    if any(p in t for p in _PALABRAS_OBS):
        return "obs"
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
