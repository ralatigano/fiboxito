import re


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
