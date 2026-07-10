"""Acciones sensibles sobre contratos de Wispro (cortar/reactivar servicio).

Como estas acciones afectan el servicio real de un cliente, SIEMPRE requieren
confirmación explícita: primero se arma un "pendiente" por chat y recién con un
"sí" se ejecuta. Cualquier otra respuesta lo cancela.
"""

import re

from logger import log_debug, log_error
from clients.wispro import (
    buscar_cliente, obtener_contratos, obtener_contrato_por_public_id,
    cambiar_estado_contrato,
)
from agent.intent import extraer_termino_busqueda
from agent.history import historial

# chat_id -> {"accion": "disabled"|"enabled", "contratos": [..], "cliente": str}
_pendiente: dict[int, dict] = {}

# "deshabilitar" contiene "habilitar": SIEMPRE chequear suspender antes.
_SUSPEND = ["suspender", "suspendé", "suspende", "cortar", "cortá", "corta",
            "cortale", "deshabilitar", "deshabilitá", "deshabilita",
            "dar de baja", "dale de baja", "baja el servicio"]
_ENABLE = ["habilitar", "habilitá", "habilita", "reactivar", "reactivá",
           "reactiva", "reconectar", "reconectá", "reconecta", "restablecer",
           "restablecé", "dar de alta", "reconexión", "reconexion",
           "volver a habilitar"]

_SI_TOKENS = {"si", "sí", "dale", "confirmo", "confirmá", "confirma", "ok",
              "oka", "okey", "hacelo", "procedé", "procede", "sip", "sisi",
              "afirmativo", "obvio"}
_NO_TOKENS = {"no", "cancelá", "cancela", "cancelar", "olvidalo", "nada",
              "negativo", "pará", "para"}

_ESTADO_LABEL = {"enabled": "activo", "disabled": "cortado",
                 "alerted": "alertado", "degraded": "degradado"}


# Referencias que NO son un cliente concreto ("ese cliente", "el mismo"...).
_REFERENCIAS = {"ese", "esa", "este", "esta", "mismo", "dicho", "aquel", "lo", "le"}


def _es_referencia(termino: str) -> bool:
    tl = termino.lower().strip()
    if tl in ("cliente", "el cliente", "ese cliente", "este cliente", "el mismo"):
        return True
    return any(w in _REFERENCIAS for w in tl.split())


def _resolver_termino(chat_id, user_message: str) -> str | None:
    """Devuelve el término de búsqueda del cliente. Si el mensaje usa una
    referencia ("ese cliente"), lo resuelve mirando hacia atrás en el historial
    (contexto de los últimos turnos)."""
    termino = extraer_termino_busqueda(user_message)
    if termino and not _es_referencia(termino):
        return termino
    for turno in reversed(historial.get(chat_id, [])):
        if turno.get("content") == user_message:
            continue  # saltar el mensaje actual
        t = extraer_termino_busqueda(turno.get("content", ""))
        if t and not _es_referencia(t):
            return t
    return termino


def detectar_accion_contrato(texto: str) -> str | None:
    """Devuelve 'disabled' (cortar), 'enabled' (reactivar) o None."""
    t = texto.lower()
    if any(w in t for w in _SUSPEND):
        return "disabled"
    if any(w in t for w in _ENABLE):
        return "enabled"
    return None


def hay_pendiente(chat_id) -> bool:
    return chat_id in _pendiente


def _slim(c: dict) -> dict:
    plan = c.get("plan_name") or (c.get("plan") or {}).get("name") or "?"
    return {
        "id": c.get("id"),
        "public_id": c.get("public_id"),
        "plan": plan,
        "estado": c.get("state"),
    }


def _accion_txt(accion: str) -> str:
    return "CORTAR el servicio" if accion == "disabled" else "REACTIVAR el servicio"


def _texto_confirmacion(accion: str, cliente: str, contratos: list) -> str:
    verbo = _accion_txt(accion)
    lineas = [f"⚠️ Vas a {verbo} de {cliente}:"]
    for c in contratos:
        est = _ESTADO_LABEL.get(c["estado"], c["estado"])
        lineas.append(f"  • Contrato #{c['public_id']} — {c['plan']} — hoy: {est}")
    lineas.append("\nRespondé *sí* para confirmar o *no* para cancelar.")
    return "\n".join(lineas)


def preparar(chat_id, user_message: str, accion: str) -> str:
    """Busca el/los contrato(s) objetivo y deja la acción pendiente de confirmar.
    Devuelve el texto a enviar (confirmación, listado o error)."""
    # ¿Referencia explícita a un contrato? "contrato 1240"
    m = re.search(r"contrato\s+#?(\d+)", user_message, re.IGNORECASE)
    if m:
        pid = m.group(1)
        contrato = obtener_contrato_por_public_id(pid)
        if not contrato:
            return f"No encontré el contrato #{pid}."
        contratos = [_slim(contrato)]
        cliente = f"contrato #{pid}"
    else:
        termino = _resolver_termino(chat_id, user_message)
        if not termino:
            return ("¿A qué cliente? Indicá el nombre o número. "
                    "Ej: \"suspendé al cliente 1240\".")
        cli = buscar_cliente(termino)
        if not cli:
            return f"No encontré al cliente \"{termino}\"."
        cliente = cli.get("name", termino)
        crudos = obtener_contratos(str(cli.get("id", "")))
        if not crudos:
            return f"{cliente} no tiene contratos registrados."
        if len(crudos) > 1:
            lineas = [f"{cliente} tiene {len(crudos)} contratos. "
                      f"Decime cuál con \"contrato <número>\":"]
            for c in crudos:
                s = _slim(c)
                est = _ESTADO_LABEL.get(s["estado"], s["estado"])
                lineas.append(f"  • #{s['public_id']} — {s['plan']} — {est}")
            return "\n".join(lineas)
        contratos = [_slim(crudos[0])]

    # ¿Ya están en el estado deseado?
    if all(c["estado"] == accion for c in contratos):
        est = _ESTADO_LABEL.get(accion, accion)
        return f"El servicio de {cliente} ya está {est}. No hay nada que cambiar."

    _pendiente[chat_id] = {"accion": accion, "contratos": contratos, "cliente": cliente}
    log_debug(f"[ACCION] Pendiente {accion} para chat {chat_id}: {cliente}")
    return _texto_confirmacion(accion, cliente, contratos)


def _ejecutar(pend: dict) -> str:
    accion = pend["accion"]
    cliente = pend["cliente"]
    verbo_ok = "cortado" if accion == "disabled" else "reactivado"
    ok_list, err_list = [], []
    for c in pend["contratos"]:
        ok, _ = cambiar_estado_contrato(c["id"], accion)
        (ok_list if ok else err_list).append(c)

    partes = []
    if ok_list:
        ids = ", ".join(f"#{c['public_id']}" for c in ok_list)
        emoji = "🔴" if accion == "disabled" else "🟢"
        detalle = "" if cliente.lower().startswith("contrato") else f" (contrato {ids})"
        partes.append(f"{emoji} Servicio {verbo_ok} — {cliente}{detalle}.")
    if err_list:
        ids = ", ".join(f"#{c['public_id']}" for c in err_list)
        partes.append(f"❌ No pude cambiar el contrato {ids}. Revisá en Wispro.")
    log_debug(f"[ACCION] Ejecutado {accion} {cliente}: ok={len(ok_list)} err={len(err_list)}")
    return "\n".join(partes)


def resolver_confirmacion(chat_id, user_message: str) -> str | None:
    """Si hay una acción pendiente, interpreta el mensaje como sí/no.
    - Afirmativo → ejecuta y devuelve el resultado.
    - Negativo   → cancela y devuelve aviso.
    - Otra cosa  → cancela por seguridad y devuelve None (se procesa normal).
    Devuelve None si no había nada pendiente."""
    if chat_id not in _pendiente:
        return None

    t = user_message.lower().strip().strip(".!¡ ")
    primer = t.split()[0] if t.split() else ""

    if primer in _SI_TOKENS or t in _SI_TOKENS:
        pend = _pendiente.pop(chat_id)
        return _ejecutar(pend)

    # No afirmativo → cancelar el pendiente
    _pendiente.pop(chat_id, None)
    if primer in _NO_TOKENS or t in _NO_TOKENS or "mejor no" in t:
        return "❌ Acción cancelada. No se tocó ningún servicio."
    # No era una confirmación: se cancela por seguridad y sigue el flujo normal.
    return None
