import asyncio
import os
import re
import logging
import httpx
from datetime import datetime

from db import get_conn
from routers.comprobantes import _analizar_url, _veredicto

WISPRO_URL    = os.getenv("WISPRO_URL", "").rstrip("/")
WISPRO_TOKEN  = os.getenv("WISPRO_TOKEN", "")
WISPRO_CAT_ID = os.getenv("WISPRO_COMPROBANTE_CATEGORY_ID", "")
POLL_SECS     = int(os.getenv("OPA_POLL_INTERVAL", "120"))
TG_TOKEN          = os.getenv("TELEGRAM_TOKEN", "")
TG_REPORT_TARGETS = [x.strip() for x in os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").split(",") if x.strip()]

IMG_PATTERN      = r"https://[^\s\"']*holasuite\.com/atendente/services/download[^\s\n\"']*"
CONTACTO_PATTERN = r"Contacto:\s*(.+)"

log = logging.getLogger("fiboxito")


# ── Base de datos ────────────────────────────────────────────────────────────

def init_tabla_comprobantes():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS comprobantes_procesados (
                issue_id      TEXT PRIMARY KEY,
                protocolo     TEXT,
                url_imagen    TEXT,
                resultado     TEXT,
                motivo        TEXT,
                procesado_at  TEXT NOT NULL
            )
        """)


def _ya_procesado(issue_id: str) -> bool:
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM comprobantes_procesados WHERE issue_id=?", (issue_id,)
        ).fetchone() is not None


def _marcar_procesado(issue_id, protocolo, url, resultado, motivo):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO comprobantes_procesados
              (issue_id, protocolo, url_imagen, resultado, motivo, procesado_at)
            VALUES (?,?,?,?,?,?)
        """, (issue_id, protocolo, url, resultado, motivo,
               datetime.utcnow().isoformat()))


def init_tabla_operaciones():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operaciones_registradas (
                numero_operacion TEXT PRIMARY KEY,
                issue_id         TEXT,
                protocolo        TEXT,
                registrado_at    TEXT NOT NULL
            )
        """)


def _operacion_ya_usada(numero: str) -> bool:
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM operaciones_registradas WHERE numero_operacion=?", (numero,)
        ).fetchone() is not None


def _registrar_operacion(numero: str, issue_id: str, protocolo: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO operaciones_registradas
              (numero_operacion, issue_id, protocolo, registrado_at)
            VALUES (?,?,?,?)
        """, (numero, issue_id, protocolo, datetime.utcnow().isoformat()))


# ── Wispro ──────────────────────────────────────────────────────────────────

def _headers():
    return {"Accept": "application/json", "Authorization": WISPRO_TOKEN}


async def _get_issues_pendientes(client: httpx.AsyncClient) -> list:
    # category_id_eq no filtra server-side; filtramos por state y validamos categoría en Python
    all_issues = []
    page = 1
    while True:
        resp = await client.get(
            f"{WISPRO_URL}/api/v1/help_desk/issues",
            headers=_headers(),
            params={"state_eq": "pending", "per_page": 50, "page": page},
        )
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", [])
        all_issues.extend(i for i in data if i.get("category_id") == WISPRO_CAT_ID)
        pagination = body.get("meta", {}).get("pagination", {})
        if page >= pagination.get("total_pages", 1):
            break
        page += 1
    return all_issues


async def _finalizar_issue(client: httpx.AsyncClient, issue_id: str, comentario: str):
    try:
        await client.patch(
            f"{WISPRO_URL}/api/v1/help_desk/issues/{issue_id}",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"state": "finalized", "description": comentario},
        )
    except Exception as e:
        log.error(f"[POLLER] Error finalizando issue {issue_id}: {e}")


# ── Telegram ────────────────────────────────────────────────────────────────

async def _notificar_telegram(texto: str):
    if not TG_TOKEN or not TG_REPORT_TARGETS:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        for target in TG_REPORT_TARGETS:
            try:
                await client.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    json={"chat_id": target, "text": texto, "parse_mode": "HTML"},
                )
            except Exception as e:
                log.error(f"[POLLER] Error Telegram (destino {target}): {e}")


# ── Loop principal ───────────────────────────────────────────────────────────

async def opa_polling_loop():
    init_tabla_comprobantes()
    init_tabla_operaciones()
    if not WISPRO_URL or not WISPRO_TOKEN or not WISPRO_CAT_ID:
        log.warning("[POLLER] Faltan WISPRO_URL / WISPRO_TOKEN / WISPRO_COMPROBANTE_CATEGORY_ID — poller deshabilitado.")
        return

    log.info(f"[POLLER] Iniciado — Wispro help_desk categoría {WISPRO_CAT_ID} (cada {POLL_SECS}s)")
    while True:
        try:
            await _ciclo()
        except Exception as e:
            log.error(f"[POLLER] Error en ciclo: {e}")
        await asyncio.sleep(POLL_SECS)


async def _ciclo():
    async with httpx.AsyncClient(timeout=30) as client:
        issues = await _get_issues_pendientes(client)

        for issue in issues:
            issue_id  = issue.get("id")
            protocolo = issue.get("title", "?")
            desc      = issue.get("description", "")

            if not issue_id or _ya_procesado(issue_id):
                continue

            m = re.search(IMG_PATTERN, desc)
            if not m:
                continue

            url_img  = m.group()
            mc = re.search(CONTACTO_PATTERN, desc)
            contacto_wa = mc.group(1).strip() if mc else None
            log.info(f"[POLLER] Comprobante nuevo: {protocolo} (issue {issue_id})")

            analisis  = {}
            resultado = "ERROR"
            motivo    = "Sin resultado"
            numero_op = None
            try:
                loop = asyncio.get_event_loop()
                analisis  = await loop.run_in_executor(None, _analizar_url, url_img)
                numero_op = analisis.get("numero_operacion")

                if numero_op and _operacion_ya_usada(numero_op):
                    resultado = "NO OK"
                    motivo    = f"Comprobante duplicado: el N° de operación {numero_op} ya fue registrado."
                else:
                    resultado, motivo = _veredicto(analisis, None)
                    if numero_op and resultado == "OK":
                        _registrar_operacion(numero_op, issue_id, protocolo)

            except Exception as e:
                resultado, motivo = "ERROR", str(e)
                log.error(f"[POLLER] Error analizando imagen de {protocolo}: {e}")

            _marcar_procesado(issue_id, protocolo, url_img, resultado, motivo)
            log.info(f"[POLLER] {protocolo} → {resultado}: {motivo}")

            notif = (
                f"🧾 <b>Comprobante {protocolo}</b>\n"
                f"Resultado: <b>{resultado}</b>\n"
                f"{motivo}"
            )
            if contacto_wa:
                notif += f"\n📱 Envió: {contacto_wa}"
            monto = analisis.get("monto_detectado")
            if monto:
                notif += f"\n💰 Monto: {monto}"
            emisor = analisis.get("emisor_nombre")
            if emisor:
                notif += f"\n👤 Pagó: {emisor}"
            if numero_op:
                notif += f"\n🔑 N° op: {numero_op}"
            notif += f'\n🔗 <a href="{url_img}">Descargá el comprobante aquí</a>'

            desc_ticket = f"[Fiboxito] {resultado}: {motivo}"
            if emisor:
                desc_ticket += f"\nPagó: {emisor}"
            if monto:
                desc_ticket += f"\nMonto: {monto}"
            fecha_det = analisis.get("fecha_detectada")
            if fecha_det:
                desc_ticket += f"\nFecha: {fecha_det}"
            if numero_op:
                desc_ticket += f"\nN° operación: {numero_op}"
            if contacto_wa:
                desc_ticket += f"\nContacto: {contacto_wa}"
            desc_ticket += f"\nComprobante: {url_img}"

            await _finalizar_issue(client, issue_id, desc_ticket)
            await _notificar_telegram(notif)
