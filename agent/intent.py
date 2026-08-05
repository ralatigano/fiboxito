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

# ── Router de intención por niveles de confianza ────────────────────────────
# En vez de una escalera de keywords donde el ORDEN define la corrección (frágil,
# parche sobre parche), clasificamos por confianza:
#   Nivel 0  comando /obs, /nas… → ya se resuelve en telegram/polling.py.
#   Nivel 1  señal FUERTE y única de un dominio → determinístico (sin LLM).
#   Nivel 2  ambiguo (señales de 2+ dominios en conflicto) → se consulta a Ollama.
#   Fallback charla sin señales → "general" (respuesta conversacional, sin clasificar).
# Así una frase nueva ambigua NO exige una regla nueva: cae al Nivel 2.

# Verbos de ACCIÓN inequívocamente operables sobre OBS (encender/apagar/reiniciar…).
# Ojo: varios ("activá", "cortá", "habilitá") también sirven para el servicio de un
# cliente; por eso solos NO alcanzan: necesitan un OBJETO de OBS (fuente, stream…).
_OBS_ACTION_VERBS = [
    # imperativos (voseo) + infinitivos, para cubrir "reiniciá" y "reiniciar/-la".
    "iniciá", "inicia", "iniciar", "arrancá", "arranca", "arrancar",
    "encendé", "enciende", "encender", "empezá", "empieza", "empezar",
    "pará", "para", "parar", "cortá", "corta", "cortar",
    "detené", "detene", "detener", "frená", "frena", "frenar", "stop",
    "reiniciá", "reinicia", "reiniciar", "reboot", "restart",
    "activá", "activa", "activar", "desactivá", "desactiva", "desactivar",
    "habilitá", "habilita", "habilitar", "deshabilitá", "deshabilita", "deshabilitar",
    "prendé", "prende", "prender", "apagá", "apaga", "apagar",
    "silenciá", "silencia", "silenciar", "muteá", "mutea", "mutear",
    "reanudá", "reanuda", "reanudar", "pausá", "pausa", "pausar",
    "ocultá", "oculta", "ocultar",
]
# Tokens que solo aparecen en el dominio OBS (una fuente conocida o jerga del canal).
_OBS_SOURCE_TOKENS = [
    "radiofmespacio", "fm espacio", "radiosannicolas", "radio san nicol",
    "san nicol", "radiopop", "radio pop", "trasnoche", "carrusel",
]
_OBS_STRONG_NOUNS = ["watchdog", "transmisión", "transmision", "broadcasting",
                     "stream", "al aire"]
# Sustantivos de OBS que también podrían ser un nombre de archivo: solo cuentan
# como OBS si van con un verbo de acción.
_OBS_SHARED_NOUNS = ["fuente", "fuentes", "cámara", "camara", "canal", "escena",
                     "micrófono", "microfono"]

# Sustantivos inequívocos de cliente + verbos de servicio que OBS nunca usa.
_CLIENTE_NOUNS = [
    "cliente", "clientes", "factura", "facturas", "boleta", "saldo", "deuda",
    "cuenta corriente", "contrato", "contratos", "dni", "pdf",
    "última factura", "ultima factura",
    "último cliente", "ultimo cliente", "últimos clientes", "ultimos clientes",
    "ip libre", "ips libres", "ip disponible", "ips disponibles",
]
_CLIENTE_VERBS_STRONG = [
    "suspender", "suspendé", "suspende", "reactivar", "reactivá",
    "reconectar", "reconectá", "reconexión", "reconexion", "restablecer",
    "restablecé", "cortale", "dar de baja", "dar de alta",
]
# Verbos genéricos que sugieren cliente sin ser terminantes (buscar/traer datos).
# "servicio" es ambiguo (OBS no lo usa, pero "cortá el servicio" es de cliente):
# como débil, si aparece junto a un verbo de acción manda el caso al Nivel 2 (LLM).
_CLIENTE_WEAK = ["número", "numero", "pasame", "dame", "mostrame", "buscame",
                 "busca", "servicio", "abonado"]

# Match por LÍMITE DE PALABRA (para no confundir "activaciones"→"activa" o
# "paranormal"→"para"), con un grupo ENCLÍTICO opcional que sí admite el pronombre
# pegado ("activarla", "prendelo", "reinicialo"). Los infinitivos van en la lista.
_ENCLITICOS = "me|te|se|lo|la|le|nos|los|las|les|selo|sela|melo|mela"
_OBS_ACTION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(v) for v in _OBS_ACTION_VERBS) +
    r")(?:" + _ENCLITICOS + r")?\b"
)


def _obs_action_verb(t: str) -> bool:
    return bool(_OBS_ACTION_RE.search(t))


def _obs_strong(t: str) -> bool:
    if any(s in t for s in _OBS_SOURCE_TOKENS):
        return True
    if re.search(r"\bobs\b", t):
        return True
    if any(n in t for n in _OBS_STRONG_NOUNS):
        return True
    if _obs_action_verb(t) and any(n in t for n in _OBS_SHARED_NOUNS):
        return True
    return False


def _cliente_strong(t: str) -> bool:
    return (any(n in t for n in _CLIENTE_NOUNS)
            or any(v in t for v in _CLIENTE_VERBS_STRONG))


def _nas_strong(t: str) -> bool:
    # Nota: NO filtramos "factura/pdf" acá (un archivo puede llamarse así); el
    # guard vive en el _es_nas débil. Los verbos de NAVEGACIÓN ("volvé", "subí")
    # ya NO cuentan como fuertes: solos son ambiguos y solo valen dentro de una
    # sesión NAS abierta (ver detectar_intencion).
    if any(w in t for w in _NAS_NOUN):
        return True
    if "/" in t and any(w in t for w in ["archivo"] + _TRAER_VERBS + ["entrá", "abrí", "entra", "abri"]):
        return True
    if any(w in t for w in _SEARCH_VERBS) and "archivo" in t:
        return True
    return False


def _es_nas(t: str) -> bool:
    if any(w in t for w in ["factura", "pdf", "boleta"]):
        return False
    return any(w in t for w in _PALABRAS_NAS)


_LABELS_LLM = {"obs": "obs", "nas": "nas", "cliente": "consulta_cliente",
               "general": "general"}


def _clasificar_intencion_llm(texto: str, en_sesion_nas: bool) -> str:
    """Nivel 2: desempate por LLM (Ollama) para frases genuinamente ambiguas.
    Devuelve una etiqueta del set fijo. Ante fallo del modelo, cae a 'general'."""
    from clients.ollama import classify_ollama
    sesion = ("El usuario está navegando carpetas del servidor (NAS) en este momento.\n"
              if en_sesion_nas else "")
    prompt = (
        "Clasificá el mensaje de un empleado de un ISP en UNA sola categoría.\n"
        "- obs: controlar el canal/streaming (transmisión, fuentes de audio, "
        "cámara, watchdog, reiniciar la PC del canal).\n"
        "- cliente: consultar o gestionar clientes (datos, saldo, facturas, "
        "contratos, cortar o reactivar el servicio, IPs).\n"
        "- nas: navegar carpetas o traer archivos del servidor de archivos.\n"
        "- general: saludo o charla que no encaja en las anteriores.\n"
        f"{sesion}"
        "Respondé SOLO con una palabra: obs, cliente, nas o general.\n\n"
        f"Mensaje: {texto}\n"
        "Categoría:"
    )
    raw = classify_ollama(prompt).lower()
    for key, label in _LABELS_LLM.items():
        if key in raw:
            return label
    return "general"


def detectar_intencion(texto: str, chat_id=None) -> str:
    t = texto.lower().strip()

    saludos = {
        "hola", "buenas", "qué tal", "que tal", "hey",
        "hola fiboxito", "buenos días", "buenas tardes", "buenas noches",
    }
    if t in saludos:
        return "saludo"

    # ¿Hay una sesión de navegación NAS abierta para este chat?
    en_sesion_nas = False
    if chat_id is not None:
        try:
            from routers.nas.telegram_ops import en_sesion
            en_sesion_nas = en_sesion(chat_id)
        except Exception:  # noqa: BLE001
            en_sesion_nas = False

    obs_s = _obs_strong(t)
    cli_s = _cliente_strong(t)
    nas_s = _nas_strong(t)

    # NAS con sustantivo/ruta/navegación es inequívoco (aunque un nombre de archivo
    # contenga "stream" o "canal"). Solo un VERBO DE ACCIÓN de OBS lo destrona
    # ("pará el stream" mientras navegás corta la navegación).
    if nas_s and not _obs_action_verb(t):
        return "nas"

    # ── Nivel 1: señal fuerte y única ───────────────────────────
    if obs_s and cli_s:
        return _clasificar_intencion_llm(texto, en_sesion_nas)   # conflicto → LLM
    if obs_s:
        return "obs"
    if cli_s:
        return "consulta_cliente"

    # ── Señales débiles ─────────────────────────────────────────
    weak_obs = any(p in t for p in _PALABRAS_OBS) or _obs_action_verb(t)
    weak_cli = any(p in t for p in _CLIENTE_WEAK)
    weak_nas = _es_nas(t)

    # Dentro de una sesión NAS, la navegación sigue en NAS salvo señal clara de
    # otro dominio (el caso fuerte ya se resolvió arriba: una acción real corta).
    if en_sesion_nas:
        if weak_obs and not weak_nas:
            return "obs"
        if weak_cli and not weak_nas:
            return "consulta_cliente"
        return "nas"

    activos = [d for d, v in (("obs", weak_obs),
                              ("consulta_cliente", weak_cli),
                              ("nas", weak_nas)) if v]
    if len(activos) >= 2:                      # ── Nivel 2: ambiguo → LLM ──
        return _clasificar_intencion_llm(texto, en_sesion_nas)
    if len(activos) == 1:
        return activos[0]
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
