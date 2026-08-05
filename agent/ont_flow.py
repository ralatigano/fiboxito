"""Habilitación de ONTs en Wispro (cerrar la instalación domiciliaria).

Flujo conversacional con estado por chat, porque necesita varios datos y —como
toca el servicio real— confirmación explícita antes de autorizar:

  ciudad → nº de contrato → elegir la ONT que ve la OLT → confirmar → autorizar

La gracia es que el técnico NO tipea el serial ni la interfaz: Fiboxito los lee
de la OLT (onts_from_olt) y le muestra las ONT nuevas (authorized=false) para
que elija. Solo hace falta el número de contrato y una confirmación.
"""
import re

from logger import log_debug
from config import OLTS
from clients.wispro import (
    obtener_contrato_por_public_id, onts_de_olt, autorizar_ont,
)

# chat_id -> estado del flujo
#   {"step": "city"|"contract"|"pick"|"confirm",
#    "city": str, "olt_id": str,
#    "contract_id": str, "contract_public": str,
#    "onts": [ont...], "ont": ont}
_flujo: dict[int, dict] = {}

# Alias de ciudad → clave en OLTS.
_CIUDADES = {
    "coronel moldes": "moldes", "cnel moldes": "moldes",
    "cnel. moldes": "moldes", "moldes": "moldes",
    "cerrillos": "cerrillos",
}

_SI = {"si", "sí", "dale", "confirmo", "confirmá", "confirma", "ok", "okey",
       "hacelo", "procedé", "procede", "sip", "sisi", "afirmativo", "obvio"}
_CANCELAR = {"no", "cancelá", "cancela", "cancelar", "olvidalo", "nada",
             "negativo", "salir", "basta"}

_DISPARADOR_ONT = re.compile(r"\bont\b")


def es_disparador(texto: str) -> bool:
    """¿El mensaje pide habilitar/autorizar una ONT?"""
    t = texto.lower()
    if not _DISPARADOR_ONT.search(t):
        return False
    return any(w in t for w in ("habilit", "autoriz", "dar de alta", "alta de",
                                "instal", "cerr", "activar la ont", "activá la ont"))


def hay_flujo(chat_id) -> bool:
    return chat_id in _flujo


def _detectar_ciudad(t: str) -> str | None:
    for alias, key in _CIUDADES.items():
        if alias in t:
            return key
    return None


def _olts_configuradas() -> bool:
    return any(v for v in OLTS.values())


def _ciudades_disponibles() -> str:
    disp = [c for c, v in OLTS.items() if v]
    return " o ".join(disp) if disp else "—"


def _pedir_contrato(chat_id, city: str) -> str:
    _flujo[chat_id]["step"] = "contract"
    return (f"Habilitación de ONT en *{city.title()}*.\n"
            "¿Para qué número de contrato? (respondé solo el número, "
            "o \"cancelar\" para salir)")


def iniciar(chat_id, texto: str) -> str:
    """Arranca el flujo. Si el mensaje ya trae la ciudad, salta a pedir contrato."""
    _flujo.pop(chat_id, None)

    if not _olts_configuradas():
        return ("Todavía no están cargadas las OLT. Pedile a un admin que corra "
                "*/olts* para ver los UUID y los agregue al .env "
                "(OLT_MOLDES_ID / OLT_CERRILLOS_ID).")

    t = texto.lower()
    city = _detectar_ciudad(t)
    _flujo[chat_id] = {"step": "city"}

    if not city:
        return ("¿En qué ciudad vas a habilitar la ONT? "
                f"({_ciudades_disponibles()})")

    olt_id = OLTS.get(city)
    if not olt_id:
        return (f"No tengo cargada la OLT de *{city.title()}*. "
                f"Falta OLT_{city.upper()}_ID en el .env (corré /olts para el UUID).")

    _flujo[chat_id]["city"] = city
    _flujo[chat_id]["olt_id"] = olt_id
    return _pedir_contrato(chat_id, city)


def _fmt_ont(o: dict) -> str:
    return f"interfaz {o.get('interface', '?')} · serial {o.get('serial', '?')}"


def _no_autorizadas(onts: list) -> list:
    def _sin(o):
        a = o.get("authorized")
        return a in (False, "false", "False", 0, "0", None)
    return [o for o in onts if _sin(o)]


def _buscar_onts_y_seguir(chat_id) -> str:
    """Consulta la OLT, filtra las ONT sin autorizar y arma el próximo paso."""
    st = _flujo[chat_id]
    onts = onts_de_olt(st["olt_id"])
    nuevas = _no_autorizadas(onts)

    if not nuevas:
        _flujo.pop(chat_id, None)
        if onts:
            return ("La OLT no ve ninguna ONT *nueva* (sin autorizar) en este "
                    "momento. Verificá que la ONT esté encendida y enlazada, y "
                    "volvé a intentar.")
        return ("La OLT no devolvió ONTs. Puede estar tardando o sin ONTs "
                "conectadas. Probá de nuevo en un momento.")

    if len(nuevas) == 1:
        st["ont"] = nuevas[0]
        return _ir_a_confirmar(chat_id)

    st["onts"] = nuevas
    st["step"] = "pick"
    lineas = [f"La OLT ve {len(nuevas)} ONTs sin autorizar. ¿Cuál habilito? "
              "Respondé con el número:"]
    for i, o in enumerate(nuevas, 1):
        lineas.append(f"  {i}. {_fmt_ont(o)}")
    return "\n".join(lineas)


def _ir_a_confirmar(chat_id) -> str:
    st = _flujo[chat_id]
    st["step"] = "confirm"
    o = st["ont"]
    return (
        f"⚠️ Vas a habilitar esta ONT en *{st['city'].title()}*:\n"
        f"  • Contrato #{st['contract_public']}\n"
        f"  • Serial: {o.get('serial', '?')}\n"
        f"  • Interfaz: {o.get('interface', '?')}\n"
        "\nRespondé *sí* para confirmar o *no* para cancelar."
    )


def _ejecutar(chat_id) -> str:
    st = _flujo.pop(chat_id)
    o = st["ont"]
    ok, http, _ = autorizar_ont(
        st["olt_id"], st["contract_id"], o.get("serial", ""), o.get("interface", "")
    )
    if ok:
        return (f"✅ ONT habilitada para el contrato #{st['contract_public']} "
                f"(serial {o.get('serial', '?')}). Puede tardar unos minutos en "
                "levantar; verificá la navegación del cliente.")
    return (f"❌ No pude habilitar la ONT (HTTP {http}). Revisá en Wispro que el "
            "contrato y la ONT sean correctos, o intentá de nuevo.")


def continuar(chat_id, texto: str) -> str:
    """Procesa el próximo paso del flujo activo."""
    t = texto.lower().strip().strip(".!¡ ")
    st = _flujo.get(chat_id)
    if not st:
        return "No hay ninguna habilitación de ONT en curso."

    if t in _CANCELAR or t.split()[:1] == ["cancelar"]:
        _flujo.pop(chat_id, None)
        return "❌ Habilitación de ONT cancelada."

    step = st["step"]

    if step == "city":
        city = _detectar_ciudad(t)
        if not city:
            return f"No reconocí la ciudad. Opciones: {_ciudades_disponibles()}."
        olt_id = OLTS.get(city)
        if not olt_id:
            _flujo.pop(chat_id, None)
            return (f"No tengo cargada la OLT de *{city.title()}* "
                    f"(falta OLT_{city.upper()}_ID en el .env).")
        st["city"] = city
        st["olt_id"] = olt_id
        return _pedir_contrato(chat_id, city)

    if step == "contract":
        m = re.search(r"\d+", t)
        if not m:
            return "Decime el número de contrato (solo el número), o \"cancelar\"."
        pid = m.group(0)
        contrato = obtener_contrato_por_public_id(pid)
        if not contrato:
            return f"No encontré el contrato #{pid}. Probá con otro número."
        st["contract_public"] = str(contrato.get("public_id", pid))
        st["contract_id"] = str(contrato.get("id", ""))
        log_debug(f"[ONT] chat {chat_id}: contrato #{pid} → {st['contract_id']}; "
                  f"consultando OLT {st['city']}")
        return _buscar_onts_y_seguir(chat_id)

    if step == "pick":
        onts = st.get("onts", [])
        m = re.search(r"\d+", t)
        elegido = None
        if m:
            idx = int(m.group(0))
            if 1 <= idx <= len(onts):
                elegido = onts[idx - 1]
        if elegido is None:  # ¿la eligió por serial?
            for o in onts:
                if str(o.get("serial", "")).lower() in t:
                    elegido = o
                    break
        if elegido is None:
            return (f"Elegí una ONT con un número del 1 al {len(onts)} "
                    "(o pegá el serial).")
        st["ont"] = elegido
        return _ir_a_confirmar(chat_id)

    if step == "confirm":
        if t in _SI or t.split()[:1] and t.split()[0] in _SI:
            return _ejecutar(chat_id)
        _flujo.pop(chat_id, None)
        return "❌ Habilitación de ONT cancelada. No se tocó nada."

    _flujo.pop(chat_id, None)
    return "Se reinició el flujo de ONT. Volvé a empezar con \"habilitar una ONT\"."


def texto_lista_olts() -> str:
    """Para el comando /olts: lista las OLT con su UUID (para cargar en .env)."""
    from clients.wispro import listar_olts
    olts = listar_olts()
    if not olts:
        return "No pude obtener las OLT desde Wispro (revisá el token o la conexión)."
    lineas = ["🛰 OLTs en Wispro (UUID para el .env):"]
    for o in olts:
        lineas.append(
            f"\n• {o.get('name', '?')}  (#{o.get('public_id', '?')}, "
            f"{o.get('state', '?')})\n  {o.get('id', '?')}"
        )
    lineas.append("\nCargá en el .env: OLT_MOLDES_ID y OLT_CERRILLOS_ID con el UUID que corresponda.")
    return "\n".join(lineas)
