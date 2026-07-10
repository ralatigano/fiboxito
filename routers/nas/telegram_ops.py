"""Capa Telegram del NAS: navegación conversacional con estado por chat.

Cada chat tiene un "directorio actual" (cwd). El usuario navega con verbos
naturales y el bot responde con el listado de la carpeta donde queda parado:
  - "mostrame" / "listá"           → ls del directorio actual
  - "entrá a X" / "abrí X"          → baja a la carpeta X (+ ls)
  - "mostrame el contenido de X"    → idem (navega a X)
  - "volvé atrás" / "subí"          → sube un nivel
  - "andá a la raíz" / "inicio"     → vuelve a la raíz
  - "buscá el archivo X"            → busca recursivamente bajo el actual
  - "traeme X" / "descargá X"       → envía el archivo (relativo al actual)

También el comando `/nas` (ls/cd/get/up/root) usa el mismo estado.

Los mensajes van por send_message (texto plano, SIN HTML). Un "adjunto" de
descarga es la tupla (bytes, nombre, mime); polling la manda con sendDocument.
"""

import re
import posixpath
import mimetypes

from . import service
from .config import NAS_SSH_HOST, NAS_MAX_FILE_MB
from .sftp_client import NASError

# Directorio actual por chat (relativo a NAS_BASE_PATH). "." = raíz.
# La presencia de una clave indica además "sesión de navegación activa".
_cwd: dict[int, str] = {}


def en_sesion(chat_id) -> bool:
    return chat_id in _cwd


def cerrar_sesion(chat_id):
    _cwd.pop(chat_id, None)


def _get_cwd(chat_id) -> str:
    return _cwd.get(chat_id, ".")


def _set_cwd(chat_id, path: str):
    _cwd[chat_id] = path or "."


HELP = (
    "📁 Navegación del servidor (NAS)\n"
    "─────────────────────────────\n"
    "Hablale natural y te va mostrando dónde estás:\n"
    '  "mostrame la raíz"        → lista la carpeta actual\n'
    '  "entrá a Connelec1"       → baja a esa carpeta\n'
    '  "volvé atrás"             → sube un nivel\n'
    '  "buscá el archivo X"      → busca bajo la carpeta actual\n'
    '  "traeme streamFibox.txt"  → te envía el archivo\n\n'
    "O con comando:\n"
    "  /nas ls [carpeta] · /nas cd <carpeta> · /nas up · /nas root\n"
    "  /nas get <archivo> · /nas buscar <texto>\n\n"
    "Tip: Fiboxito lee toda la estructura y escribe solo en Fibox."
)


# ── Utilidades ──────────────────────────────────────────────────────────────

def _humanizar(n) -> str:
    if n is None:
        return "?"
    tam = float(n)
    for unidad in ("B", "KB", "MB", "GB"):
        if tam < 1024 or unidad == "GB":
            return f"{int(tam)} {unidad}" if unidad == "B" else f"{tam:.1f} {unidad}"
        tam /= 1024
    return f"{tam:.1f} GB"


def _etiqueta(path: str) -> str:
    return "raíz" if path in (".", "") else path


def _sin_configurar() -> str | None:
    if not NAS_SSH_HOST:
        return "El NAS no está configurado (falta NAS_SSH_HOST en el .env)."
    return None


def _resolver(cwd: str, target: str | None) -> str | None:
    """Resuelve `target` (relativo al cwd, o absoluto si empieza con '/') a una
    ruta normalizada relativa a la base. Devuelve None si escapa de la base."""
    if not target:
        return cwd
    target = target.strip()
    if target.startswith("/"):
        cand = posixpath.normpath(target.lstrip("/"))
    else:
        cand = posixpath.normpath(posixpath.join(cwd, target))
    if cand in ("", "."):
        return "."
    if cand == ".." or cand.startswith("../"):
        return None
    return cand


def _formato_listado(path: str, entradas: list[dict]) -> str:
    if not entradas:
        return f"📂 {_etiqueta(path)} (vacía)\n\nEstás en: {_etiqueta(path)}"
    lineas = [f"📂 {_etiqueta(path)}"]
    for e in entradas:
        if e["tipo"] == "dir":
            lineas.append(f"  📁 {e['nombre']}/")
        else:
            lineas.append(f"  📄 {e['nombre']}  ({_humanizar(e['tamano'])})")
    lineas.append(f"\n📍 Estás en: {_etiqueta(path)}")
    return "\n".join(lineas)


def _ls(path: str) -> str:
    aviso = _sin_configurar()
    if aviso:
        return f"❌ {aviso}"
    try:
        entradas = service.listar(path)
    except NASError as e:
        return f"❌ {e}"
    return _formato_listado(path, entradas)


# Compat: listado directo por ruta (sin estado), usado por otros módulos.
def listar_texto(path: str = ".") -> str:
    return _ls((path or ".").strip() or ".")


def traer_archivo(path: str):
    """Devuelve (texto, adjunto) con adjunto=(bytes, nombre, mime) o None."""
    aviso = _sin_configurar()
    if aviso:
        return f"❌ {aviso}", None
    path = (path or "").strip()
    if not path:
        return "Decime qué archivo traer. Ej: \"traeme streamFibox.txt\".", None
    try:
        contenido = service.leer(path)
    except NASError as e:
        if "demasiado grande" in str(e):
            return f"❌ El archivo supera el límite de {NAS_MAX_FILE_MB} MB.", None
        return f"❌ {e}", None
    nombre = posixpath.basename(path) or "archivo"
    mime = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
    return f"📎 {nombre}", (contenido, nombre, mime)


# ── Ejecutor compartido (comando y lenguaje natural) ────────────────────────

def _ejecutar(chat_id, accion: str, target: str | None):
    """Aplica una acción de navegación y devuelve (texto, adjunto|None)."""
    aviso = _sin_configurar()
    if aviso:
        return f"❌ {aviso}", None

    cwd = _get_cwd(chat_id)

    if accion == "raiz":
        _set_cwd(chat_id, ".")
        return _ls("."), None

    if accion == "subir":
        if cwd in (".", ""):
            return "Ya estás en la raíz.\n\n" + _ls("."), None
        padre = posixpath.normpath(posixpath.join(cwd, ".."))
        padre = "." if padre in ("", ".") else padre
        _set_cwd(chat_id, padre)
        return _ls(padre), None

    if accion == "nada":
        return ("👍 Dale. Si querés seguir: \"entrá a <carpeta>\", "
                "\"traeme <archivo>\", \"buscá <texto>\", \"volvé atrás\" o "
                "\"raíz\"."), None

    if accion == "traer":
        if not target:
            return ("¿Qué archivo te traigo? Ej: \"traeme Comprobantes.xlsx\"."), None
        destino = _resolver(cwd, target)
        if destino is None:
            return "❌ Esa ruta sale de la carpeta permitida.", None
        texto, adj = traer_archivo(destino)
        # Fallback: si no se encontró y el target traía ruta, probar solo el
        # nombre del archivo dentro de la carpeta actual.
        if adj is None and "/" in target:
            base = _resolver(cwd, posixpath.basename(target))
            if base:
                t2, a2 = traer_archivo(base)
                if a2 is not None:
                    return t2, a2
        return texto, adj

    if accion == "buscar":
        return _buscar_texto(cwd, target), None

    if accion == "entrar":
        destino = _resolver(cwd, target)
        if destino is None:
            return "❌ Esa ruta sale de la carpeta permitida.", None
        try:
            entradas = service.listar(destino)
        except NASError:
            return (f"❌ No encontré la carpeta \"{target}\" dentro de "
                    f"{_etiqueta(cwd)}."), None
        _set_cwd(chat_id, destino)
        return _formato_listado(destino, entradas), None

    # listar (por defecto): asegura sesión activa mostrando el actual
    if chat_id not in _cwd:
        _set_cwd(chat_id, cwd)
    return _ls(cwd), None


def _buscar_texto(cwd: str, termino: str | None) -> str:
    if not termino:
        return "¿Qué archivo busco? Ej: \"buscá el archivo factura\"."
    try:
        encontrados = service.buscar(termino, cwd)
    except NASError as e:
        return f"❌ {e}"
    if not encontrados:
        return f"🔍 No encontré archivos con \"{termino}\" bajo {_etiqueta(cwd)}."
    lineas = [f"🔍 Resultados para \"{termino}\" (bajo {_etiqueta(cwd)}):"]
    lineas += [f"  📄 {p}" for p in encontrados]
    lineas.append("\nPara traer uno: \"traeme <ruta>\".")
    return "\n".join(lineas)


# ── Comando /nas ────────────────────────────────────────────────────────────

def manejar_comando(chat_id, text: str):
    partes = text.strip().split(maxsplit=2)
    sub = partes[1].lower() if len(partes) > 1 else ""
    resto = partes[2].strip() if len(partes) > 2 else ""

    if sub in ("ls", "listar", "dir", "l"):
        # /nas ls X → navega a X; /nas ls → actual
        if resto:
            return _ejecutar(chat_id, "entrar", resto)
        return _ejecutar(chat_id, "listar", None)
    if sub in ("cd", "entrar", "abrir"):
        return _ejecutar(chat_id, "entrar", resto)
    if sub in ("up", "subir", "atras", "..", "volver"):
        return _ejecutar(chat_id, "subir", None)
    if sub in ("root", "raiz", "inicio", "home"):
        return _ejecutar(chat_id, "raiz", None)
    if sub in ("get", "traer", "descargar", "bajar", "g"):
        return _ejecutar(chat_id, "traer", resto)
    if sub in ("buscar", "busca", "find", "search"):
        return _ejecutar(chat_id, "buscar", resto)
    return HELP, None


# ── Lenguaje natural ────────────────────────────────────────────────────────

_ROOT_WORDS   = ["raíz", "raiz", "inicio", "principio", "empezar de nuevo",
                 "al principio", "home"]
_UP_WORDS     = ["volvé", "volve", "volver", "atrás", "atras", "subí", "subi",
                 "retrocedé", "retrocede", "salí", "sali", "un nivel", "para atrás"]
_TRAER_WORDS  = ["traeme", "traé", "trae", "traer", "descargá", "descarga",
                 "descargar", "bajá", "baja", "bajar", "pasame", "mandame",
                 "enviame", "envíame", "quiero el archivo", "dame el archivo"]
_BUSCAR_WORDS = ["buscá", "busca", "buscar", "encontrá", "encontra", "encontrar",
                 "dónde está", "donde esta", "hay algún", "hay algun"]
# Pedidos EXPLÍCITOS de ver la carpeta actual. Sin uno de estos (ni target ni
# otro verbo), un mensaje NO re-lista: se toma como charla/cortesía.
_LISTAR_WORDS = ["mostrame", "mostrá", "mostra", "mostrar", "listá", "lista",
                 "listar", "ver ", "qué hay", "que hay", "contenido",
                 "dónde estoy", "donde estoy", "dir", " ls", "actual", "acá"]

# Relleno inicial que hay que descartar del nombre extraído.
_FILLER_LEAD = ["el archivo", "la carpeta", "ese archivo", "este archivo",
                "ese", "esa", "este", "esta", "el", "la", "los", "las",
                "un", "una", "mi", "archivo", "carpeta", "directorio"]


def _limpiar(s: str) -> str:
    s = s.strip(" .?!¿¡\"'\t")
    low = s.lower()
    for cola in (" por favor", " porfa", " gracias", " dale", " ok"):
        if low.endswith(cola):
            s = s[: -len(cola)].strip()
            low = s.lower()
    # Sacar relleno inicial repetido ("ese archivo Foo" → "Foo").
    cambio = True
    while cambio:
        cambio = False
        for lead in _FILLER_LEAD:
            if s.lower().startswith(lead + " "):
                s = s[len(lead):].strip()
                cambio = True
                break
    return s.strip(" ,.;")


def _extraer_target(texto: str) -> str | None:
    """Best-effort para el nombre de carpeta/archivo mencionado."""
    # 1) Ruta explícita con "/".
    m = re.search(r"([^\s,;]+/[^\s,;]+)", texto)
    if m:
        return _limpiar(m.group(1))
    # 2) Un nombre de archivo con extensión (lo más confiable p/ traer).
    m = re.search(r"([^\s,;]+\.[A-Za-z0-9]{2,5})\b", texto)
    if m:
        return _limpiar(m.group(1))
    # 3) Tras un sustantivo (soporta nombres con espacios tomando hasta el fin).
    for anchor in (r"contenido de", r"carpeta", r"directorio", r"ruta"):
        m = re.search(anchor + r"\s+(?:la\s+|el\s+|los\s+|las\s+)?(.+)$", texto, re.I)
        if m:
            cand = _limpiar(m.group(1))
            if cand and cand.lower() not in ("la", "el", "los", "las"):
                return cand
    # 4) Tras un verbo de navegación/traer/búsqueda.
    verbos = (r"entrá|entra|abrí|abri|andá|anda|navegá|navega|meté|mete|ir|"
              r"traeme|traé|trae|descargá|descarga|bajá|baja|pasame|mandame|"
              r"buscá|busca|buscar|encontrá|encontra")
    m = re.search(r"(?:" + verbos + r")\s+(?:a\s+)?(?:la\s+|el\s+|los\s+|las\s+)?(.+)$",
                  texto, re.I)
    if m:
        cand = _limpiar(m.group(1))
        if cand and cand.lower() not in ("a", "la", "el", "los", "las", "al"):
            return cand
    return None


def clasificar_nl(texto: str) -> dict:
    t = texto.lower()
    if any(w in t for w in _ROOT_WORDS) and not any(
            w in t for w in ["entrá", "entra", "abrí", "abri", "traeme"]):
        return {"accion": "raiz", "param": None}
    if any(w in t for w in _UP_WORDS):
        return {"accion": "subir", "param": None}
    target = _extraer_target(texto)
    if any(w in t for w in _TRAER_WORDS):
        return {"accion": "traer", "param": target}
    if any(w in t for w in _BUSCAR_WORDS):
        return {"accion": "buscar", "param": target}
    if target:
        return {"accion": "entrar", "param": target}
    if any(w in t for w in _LISTAR_WORDS):
        return {"accion": "listar", "param": None}
    # Nada reconocible (p.ej. "gracias", "perfecto"): NO re-listar.
    return {"accion": "nada", "param": None}


def navegar(chat_id, texto: str):
    """Entrada de lenguaje natural: clasifica y ejecuta con estado."""
    intent = clasificar_nl(texto)
    return _ejecutar(chat_id, intent["accion"], intent.get("param"))
