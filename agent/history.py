from config import MEMORIA_TURNOS
from agent.intent import extraer_termino_busqueda

historial: dict[int, list[dict]] = {}


def actualizar_historial(chat_id: int, rol: str, contenido: str):
    if chat_id not in historial:
        historial[chat_id] = []
    historial[chat_id].append({"role": rol, "content": contenido})
    if len(historial[chat_id]) > MEMORIA_TURNOS * 2:
        historial[chat_id] = historial[chat_id][-(MEMORIA_TURNOS * 2):]


def contexto_reciente(chat_id: int) -> str:
    turnos = historial.get(chat_id, [])
    if not turnos:
        return ""
    lineas = ["Conversación reciente:"]
    for t in turnos:
        prefijo = "Empleado" if t["role"] == "user" else "Fiboxito"
        lineas.append(f"{prefijo}: {t['content']}")
    return "\n".join(lineas)


def cliente_del_historial(chat_id: int) -> str | None:
    turnos = historial.get(chat_id, [])
    for turno in reversed(turnos):
        termino = extraer_termino_busqueda(turno["content"])
        if termino:
            return termino
    return None
