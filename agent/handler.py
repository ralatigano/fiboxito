from config import MIKROTIKS
from logger import log_debug
from clients.wispro import (
    buscar_cliente, obtener_contratos, obtener_cuenta_corriente,
    obtener_facturas, descargar_pdf_factura,
    obtener_ultimos_clientes, obtener_ips_libres,
)
from clients.ollama import ask_ollama
from agent.intent import detectar_intencion, extraer_termino_busqueda
from agent.prompts import (
    prompt_saludo, prompt_cliente_no_encontrado,
    prompt_cliente_sin_termino, prompt_general,
)
from agent.history import actualizar_historial, contexto_reciente, cliente_del_historial


def respuesta_directa(
    cliente: dict,
    contratos: list,
    facturas: list,
    cuenta: dict | None,
    user_message: str,
    nombre_usuario: str,
) -> tuple[str, bytes | None]:

    msg = user_message.lower()
    nombre    = cliente.get("name", "N/A")
    email     = cliente.get("email", "N/A")
    telefono  = cliente.get("phone") or "No registrado"
    direccion = f"{cliente.get('street', '')} {cliente.get('number', '')}".strip() or "No registrada"
    public_id = cliente.get("public_id", "N/A")

    if any(p in msg for p in ["pdf", "última factura", "ultima factura", "descargar"]):
        if not facturas:
            return f"No encontré facturas para {nombre}, {nombre_usuario}.", None
        ultima = facturas[0]
        pdf = descargar_pdf_factura(ultima.get("id"))
        if pdf:
            periodo = f"{ultima.get('from', '?')} al {ultima.get('to', '?')}"
            return f"Acá va la última factura de {nombre} ({periodo}).", pdf
        return f"No pude descargar el PDF de la última factura de {nombre}.", None

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
            saldo   = cuenta.get("balance", "N/A")
            credito = cuenta.get("available_credit", "N/A")
            return f"Cuenta corriente de {nombre}: saldo {saldo}, crédito disponible {credito}.", None
        return f"No se pudo obtener la cuenta corriente de {nombre}.", None

    if any(p in msg for p in ["contrato", "plan", "servicio", "estado"]):
        if contratos:
            c     = contratos[0]
            estado = c.get("state", "N/A")
            plan   = c.get("plan_name", c.get("plan", {}).get("name", "N/A"))
            return f"Contrato de {nombre}: plan {plan}, estado {estado}.", None
        return f"{nombre} no tiene contratos registrados.", None

    if any(p in msg for p in ["factura", "facturas", "boleta", "cobro", "pagó", "pago"]):
        if not facturas:
            return f"{nombre} no tiene facturas registradas.", None
        lineas = [f"Últimas facturas de {nombre}:"]
        for f in facturas:
            periodo = f"{f.get('from', '?')} → {f.get('to', '?')}"
            lineas.append(
                f"  • #{f.get('invoice_number')} | {periodo} | ${f.get('amount', 'N/A')} "
                f"| {f.get('state', 'N/A')} | vence {f.get('first_due_date', 'N/A')}"
            )
        return "\n".join(lineas), None

    # Ficha completa
    lineas = [f"📋 Cliente #{public_id}: {nombre}"]
    lineas.append(f"📧 Email: {email}")
    lineas.append(f"📞 Teléfono: {telefono}")
    lineas.append(f"📍 Dirección: {direccion}")
    if cuenta:
        lineas.append(f"💰 Saldo: {cuenta.get('balance', 'N/A')}")
    if contratos:
        c     = contratos[0]
        estado = c.get("state", "N/A")
        plan   = c.get("plan_name", c.get("plan", {}).get("name", "N/A"))
        lineas.append(f"📄 Contrato: plan {plan} | estado {estado}")
    return "\n".join(lineas), None


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

        if any(p in msg for p in ["último cliente", "ultimo cliente", "últimos clientes", "ultimos clientes", "último id", "nuevo cliente"]):
            clientes = obtener_ultimos_clientes()
            if not clientes:
                return "No pude obtener los últimos clientes.", None
            lineas = ["Últimos clientes registrados:"]
            for c in clientes:
                pid    = c.get("public_id", "N/A")
                nombre = c.get("name", "N/A")
                fecha  = c.get("created_at", "")[:10]
                lineas.append(f"  #{pid} — {nombre} ({fecha}) → client{pid}")
            respuesta = "\n".join(lineas)
            actualizar_historial(chat_id, "assistant", respuesta)
            return respuesta, None

        if any(p in msg for p in ["ip", "ips", "ip libre", "ips libres", "ip disponible", "ips disponibles"]):
            zona = "pinares" if "pinares" in msg else "sta fe" if "sta fe" in msg else "moldes"
            mk   = MIKROTIKS.get(zona, {})
            ips  = obtener_ips_libres(zona)
            if not ips:
                respuesta = f"No encontré IPs libres para {zona} o hubo un error."
            else:
                lista     = "\n".join(f"  {ip}" for ip in ips[:10])
                respuesta = f"IPs libres en {zona.title()} ({mk.get('rango', '')}.X):\n{lista}"
            actualizar_historial(chat_id, "assistant", respuesta)
            return respuesta, None

        termino = extraer_termino_busqueda(user_message)
        log_debug(f"[WISPRO] Buscando término: '{termino}'")

        if not termino:
            termino = cliente_del_historial(chat_id)
            if termino:
                log_debug(f"[MEMORIA] Usando cliente del historial: '{termino}'")

        if not termino:
            respuesta = ask_ollama(prompt_cliente_sin_termino(user_message, nombre_usuario))
            actualizar_historial(chat_id, "assistant", respuesta)
            return respuesta, None

        cliente = buscar_cliente(termino)
        if not cliente:
            respuesta = ask_ollama(prompt_cliente_no_encontrado(user_message, termino, nombre_usuario))
            actualizar_historial(chat_id, "assistant", respuesta)
            return respuesta, None

        client_id = str(cliente.get("id", ""))
        contratos = obtener_contratos(client_id)
        cuenta    = obtener_cuenta_corriente(client_id)
        custom_id = str(cliente.get("custom_id", "")).zfill(4)
        facturas  = obtener_facturas(custom_id)

        texto, pdf = respuesta_directa(cliente, contratos, facturas, cuenta, user_message, nombre_usuario)
        log_debug(f"[RESPUESTA DIRECTA]\n{texto}")
        actualizar_historial(chat_id, "assistant", texto)
        return texto, pdf

    respuesta = ask_ollama(prompt_general(user_message, nombre_usuario, ctx))
    actualizar_historial(chat_id, "assistant", respuesta)
    return respuesta, None
