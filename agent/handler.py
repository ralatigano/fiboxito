from config import MIKROTIKS
from logger import log_debug
from clients.wispro import (
    buscar_cliente, obtener_contratos, obtener_cuenta_corriente,
    obtener_facturas, descargar_pdf_factura,
    obtener_ultimos_clientes, obtener_ips_libres,
)
from clients.ollama import ask_ollama
from agent.intent import detectar_intencion, clasificar_intent_obs, extraer_termino_busqueda
from agent import acciones
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
    # 0) ¿Hay una acción sensible (corte/reconexión) esperando confirmación?
    if acciones.hay_pendiente(chat_id):
        resp = acciones.resolver_confirmacion(chat_id, user_message)
        if resp is not None:
            actualizar_historial(chat_id, "user", user_message)
            actualizar_historial(chat_id, "assistant", resp)
            return resp, None

    intencion = detectar_intencion(user_message, chat_id)
    log_debug(f"[INTENT] '{user_message}' → '{intencion}'")

    # Si el usuario cambió de tema, cerramos la sesión de navegación NAS.
    if intencion != "nas":
        from routers.nas.telegram_ops import cerrar_sesion
        cerrar_sesion(chat_id)

    actualizar_historial(chat_id, "user", user_message)
    ctx = contexto_reciente(chat_id)
    msg = user_message.lower()

    if intencion == "saludo":
        respuesta = ask_ollama(prompt_saludo(user_message, nombre_usuario))
        actualizar_historial(chat_id, "assistant", respuesta)
        return respuesta, None

    if intencion == "obs":
        respuesta, imagen = _procesar_obs(user_message)
        actualizar_historial(chat_id, "assistant", respuesta)
        return respuesta, imagen

    if intencion == "nas":
        respuesta, adjunto = _procesar_nas(chat_id, user_message)
        actualizar_historial(chat_id, "assistant", respuesta)
        return respuesta, adjunto

    if intencion == "consulta_cliente":

        # Acción sensible: cortar / reactivar servicio (requiere confirmación)
        accion = acciones.detectar_accion_contrato(msg)
        if accion:
            respuesta = acciones.preparar(chat_id, user_message, accion)
            actualizar_historial(chat_id, "assistant", respuesta)
            return respuesta, None

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


# ── NAS ────────────────────────────────────────────────────────

def _procesar_nas(chat_id: int, user_message: str):
    """Navegación conversacional del NAS (con estado por chat).

    Devuelve (texto, adjunto) donde adjunto puede ser None o la tupla
    (bytes, nombre, mime) que la capa de polling manda como documento.
    """
    from routers.nas import telegram_ops as nas_tg
    return nas_tg.navegar(chat_id, user_message)


# ── OBS ────────────────────────────────────────────────────────

def _procesar_obs(user_message: str) -> tuple[str, bytes | None]:
    from routers.obs import service as obs
    from routers.obs.config import OBS_SSH_HOST

    if not OBS_SSH_HOST:
        return "OBS no configurado. Falta OBS_SSH_HOST en el .env.", None

    intent = clasificar_intent_obs(user_message)
    accion = intent["accion"]
    param  = intent.get("param")
    log_debug(f"[OBS INTENT] accion={accion} param={param}")

    try:
        if accion == "status":
            st     = obs.get_status()
            stream = "🟢 ACTIVO" if st["stream_active"] else "🔴 INACTIVO"
            tc     = st.get("stream_timecode") or "--"
            scene  = st["current_scene"]
            wd     = st["watchdog_status"]
            fuente = st.get("current_source") or "?"
            return (
                f"📡 Stream: {stream}\n"
                f"⏱ Tiempo: {tc}\n"
                f"🎬 Escena: {scene}\n"
                f"🤖 Watchdog: {wd}\n"
                f"🎵 Fuente activa: {fuente}"
            ), None

        if accion == "start":
            obs.start_stream()
            return "✅ Stream iniciado.", None

        if accion == "stop":
            obs.stop_stream()
            return "⛔ Stream detenido.", None

        if accion == "restart_stream":
            obs.restart_stream()
            return "🔄 Stream reiniciado.", None

        if accion == "restart":
            obs.restart_obs()
            return "🔄 OBS reiniciado. Puede tardar unos segundos en volver al aire.", None

        if accion == "restart_camera":
            obs.restart_camera()
            return "📷 Reiniciando mpv con la señal de la cámara...", None

        if accion == "restart_watchdog":
            obs.restart_watchdog()
            return "🔄 Watchdog reiniciado.", None

        if accion == "enable_watchdog":
            obs.enable_watchdog()
            return "🟢 Watchdog habilitado.", None

        if accion == "disable_watchdog":
            obs.disable_watchdog()
            return (
                "🔴 Watchdog deshabilitado. Ojo: mientras esté apagado nadie "
                "va a levantar OBS ni la cámara si se caen."
            ), None

        if accion == "reboot_pc":
            obs.reboot_pc()
            return (
                "🔁 Reiniciando la PC del canal. Va a estar unos minutos fuera "
                "de línea; el watchdog levanta todo solo al volver."
            ), None

        if accion == "watchdog_status":
            wd = obs.get_watchdog_status()
            return f"🤖 Watchdog: {wd['status']}", None

        if accion == "mute":
            fuente = obs.set_mute(True)
            return f"🔇 Fuente '{fuente}' silenciada.", None

        if accion == "unmute":
            fuente = obs.set_mute(False)
            return f"🔊 Fuente '{fuente}' con audio activado.", None

        if accion == "fuentes":
            fuentes = obs.get_sources()
            lineas  = ["📡 Fuentes en escena:"]
            for f in fuentes:
                icono = "✅" if f["enabled"] else "⬜"
                lineas.append(f"  {icono} {f['name']}")
            return "\n".join(lineas), None

        if accion == "activar_fuente":
            if not param:
                return "No pude identificar la fuente. ¿Podés ser más específico?", None
            obs.set_source_enabled(param, True)
            return f"✅ Cambiado a '{param}'.", None

        if accion == "desactivar_fuente":
            if not param:
                return "No pude identificar la fuente. ¿Podés ser más específico?", None
            obs.set_source_enabled(param, False)
            return f"⬜ Fuente '{param}' desactivada.", None

        if accion == "logs":
            servicio = param or "watchdog"
            logs     = obs.get_logs(servicio, lines=30)
            return f"📋 Logs [{servicio}]:\n\n{logs[-3000:]}", None

        if accion == "screenshot":
            img = obs.get_screenshot()
            return "📷 Canal en vivo:", img

        return "No entendí qué querés hacer con OBS. Podés preguntarme por el estado, iniciar/detener el stream, cambiar la fuente de audio, etc.", None

    except Exception as e:
        log_debug(f"[OBS ERROR] {e}")
        return f"❌ Error al comunicarse con OBS: {e}", None
