import os
import re
import json
import base64
import unicodedata
import anthropic
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/comprobantes", tags=["comprobantes"])

CLAUDE_API_KEY           = os.getenv("CLAUDE_API_KEY", "")
DESTINATARIO_NOMBRE      = os.getenv("DESTINATARIO_NOMBRE", "")
DESTINATARIO_CBU         = os.getenv("DESTINATARIO_CBU", "")
DIAS_VALIDEZ_COMPROBANTE = int(os.getenv("DIAS_VALIDEZ_COMPROBANTE", "30"))

PROMPT_EXTRACCION = (
    "Analizá esta imagen, que debería ser un comprobante de pago o transferencia bancaria. "
    "Extraé los datos y devolvé SOLO un JSON con esta estructura exacta, sin texto adicional:\n"
    "{\n"
    '  "es_comprobante": true/false,\n'
    '  "emisor_nombre": "nombre de quien ENVÍA el dinero (campo \'De\', \'Origen\', \'Nombre ordenante\', o nombre en cuenta debitada), o null si no aparece",\n'
    '  "destinatario_nombre": "nombre de quien RECIBE el dinero, o null",\n'
    '  "destinatario_cbu": "CBU o CVU de destino (solo dígitos), o null",\n'
    '  "monto": número sin símbolos ni separadores de miles (ej: 36794.35), o null,\n'
    '  "fecha": "fecha de la operación en formato YYYY-MM-DD, o null",\n'
    '  "numero_operacion": "identificador único de la transacción: N° operación, Nro° Trans, Código de identificación, N° de referencia, etc. Solo el valor, o null"\n'
    "}\n\n"
    "Reglas de interpretación:\n"
    '- "es_comprobante" es true si la imagen muestra una operación de pago/transferencia con monto y fecha, '
    "sin importar a quién esté dirigida.\n"
    '- El destinatario es quien recibe el dinero. Puede aparecer bajo etiquetas como "Para", "Nombre Beneficiario", '
    '"Destino", "Acreditar a", etc. NO confundir con el emisor ("De", "Cuenta a debitar", "Origen").\n'
    "- El monto puede aparecer como \"Importe\", \"Monto\", \"Pago\", \"$\", etc. Convertilo a número decimal con punto.\n"
    "- Interpretá la fecha al formato YYYY-MM-DD sin importar cómo esté escrita en el comprobante."
)


def _normalizar(texto: str) -> str:
    """Minúsculas sin tildes para comparaciones."""
    return unicodedata.normalize("NFD", texto.lower()).encode("ascii", "ignore").decode()


def _claude_extraer(imagen_b64: str) -> dict:
    cliente = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    msg = cliente.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": imagen_b64},
                },
                {"type": "text", "text": PROMPT_EXTRACCION},
            ],
        }],
    )
    respuesta = msg.content[0].text.strip()
    match = re.search(r"\{.*\}", respuesta, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"es_comprobante": False, "_raw": respuesta}


def _solo_digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _validar(datos: dict, monto_esperado: float | None) -> dict:
    hoy = datetime.now()

    # Destinatario: coincide por nombre (sin tildes/mayúsculas) o por CBU/CVU
    nombre_recibido = _normalizar(datos.get("destinatario_nombre") or "")
    cbu_recibido    = _solo_digitos(datos.get("destinatario_cbu"))
    dest_ok = bool(
        (DESTINATARIO_NOMBRE and _normalizar(DESTINATARIO_NOMBRE) in nombre_recibido) or
        (DESTINATARIO_CBU and _solo_digitos(DESTINATARIO_CBU) == cbu_recibido and cbu_recibido)
    )

    # Monto
    monto = datos.get("monto")
    try:
        monto = float(monto) if monto is not None else None
    except (ValueError, TypeError):
        monto = None
    monto_suficiente = (monto >= monto_esperado) if (monto_esperado and monto is not None) else None

    # Fecha: válida si está dentro de la ventana y NO es futura
    fecha_str = datos.get("fecha")
    fecha = None
    if fecha_str:
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
        except ValueError:
            fecha = None
    if fecha:
        dias = (hoy - fecha).days
        fecha_reciente = 0 <= dias <= DIAS_VALIDEZ_COMPROBANTE
    else:
        fecha_reciente = None

    return {
        "es_comprobante":   bool(datos.get("es_comprobante")),
        "emisor_nombre":    datos.get("emisor_nombre"),
        "numero_operacion": str(datos.get("numero_operacion") or "").strip() or None,
        "destinatario_ok":  dest_ok,
        "destinatario_detectado": datos.get("destinatario_nombre"),
        "monto_detectado":  f"${monto:,.2f}" if monto is not None else None,
        "monto_suficiente": monto_suficiente,
        "fecha_detectada":  fecha.strftime("%d/%m/%Y") if fecha else None,
        "fecha_reciente":   fecha_reciente,
    }


def _analizar_url(url: str, monto_esperado: float | None = None) -> dict:
    import httpx
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return _analizar_imagen(resp.content, monto_esperado)


def _analizar_imagen(contenido: bytes, monto_esperado: float | None = None) -> dict:
    import logging
    log = logging.getLogger("fiboxito")

    imagen_b64 = base64.b64encode(contenido).decode("utf-8")

    datos = _claude_extraer(imagen_b64)
    log.debug(f"[CLAUDE EXTRACCION]\n{datos}\n{'='*40}")

    analisis = _validar(datos, monto_esperado)
    log.debug(f"[VALIDACION PYTHON] {analisis}")
    return analisis


def _veredicto(analisis: dict, monto_esperado: float | None) -> tuple[str, str]:
    if not analisis.get("es_comprobante"):
        return "NO OK", "La imagen no parece un comprobante de pago."

    problemas = []
    if not analisis.get("destinatario_ok"):
        recibido = analisis.get("destinatario_detectado") or "no detectado"
        problemas.append(f"el destinatario ({recibido}) no coincide con {DESTINATARIO_NOMBRE}")
    if monto_esperado and analisis.get("monto_suficiente") is False:
        problemas.append(f"el monto {analisis.get('monto_detectado')} no cubre la deuda esperada")
    if analisis.get("fecha_reciente") is False:
        problemas.append(f"la fecha {analisis.get('fecha_detectada')} no es válida (futura o más de {DIAS_VALIDEZ_COMPROBANTE} días)")

    if problemas:
        return "NO OK", "Problemas: " + "; ".join(problemas) + "."
    return "OK", "Comprobante válido."


@router.post("/analizar")
async def analizar_comprobante(
    imagen: UploadFile = File(...),
    monto_esperado: float | None = Form(None),
):
    contenido = await imagen.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="La imagen está vacía.")

    analisis = _analizar_imagen(contenido, monto_esperado)
    resultado, motivo = _veredicto(analisis, monto_esperado)

    return JSONResponse({"resultado": resultado, "motivo": motivo, "detalle": analisis})
