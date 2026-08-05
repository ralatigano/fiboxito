from datetime import datetime, timedelta

import requests

from config import WISPRO_URL, WISPRO_TOKEN, MIKROTIKS
from logger import log_debug, log_error

WISPRO_HEADERS = {
    "Accept": "application/json",
    "Authorization": WISPRO_TOKEN,
}


def wispro_get(endpoint: str, params: dict = None, timeout: int = 10) -> dict:
    url = f"{WISPRO_URL}/api/v1/{endpoint}"
    log_debug(f"[WISPRO] GET {url} params={params}")
    res = requests.get(url, headers=WISPRO_HEADERS, params=params, timeout=timeout)
    data = res.json()
    log_debug(f"[WISPRO] status={data.get('status')} registros={len(data.get('data', []))}")
    return data


def wispro_patch(endpoint: str, payload: dict, timeout: int = 15) -> tuple[int, dict]:
    url = f"{WISPRO_URL}/api/v1/{endpoint}"
    log_debug(f"[WISPRO] PATCH {url} payload={payload}")
    res = requests.patch(
        url,
        headers={**WISPRO_HEADERS, "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    try:
        data = res.json()
    except ValueError:
        data = {}
    log_debug(f"[WISPRO] PATCH http={res.status_code} body_status={data.get('status')}")
    return res.status_code, data


def wispro_post(endpoint: str, payload: dict, timeout: int = 60) -> tuple[int, dict]:
    url = f"{WISPRO_URL}/api/v1/{endpoint}"
    log_debug(f"[WISPRO] POST {url} payload={payload}")
    res = requests.post(
        url,
        headers={**WISPRO_HEADERS, "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    try:
        data = res.json()
    except ValueError:
        data = {}
    log_debug(f"[WISPRO] POST http={res.status_code}")
    return res.status_code, data


def _como_lista(data) -> list:
    """Normaliza respuestas Wispro que a veces vienen como lista pelada y a veces
    envueltas en {status, meta, data}."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        d = data.get("data", data)
        if isinstance(d, list):
            return d
        return [d] if d else []
    return []


def buscar_cliente(termino: str) -> dict | None:
    if termino.isdigit():
        data = wispro_get("clients", {"public_id_eq": termino})
    else:
        data = wispro_get("clients", {"name_unaccent_cont": termino})
    if data.get("status") == 200 and data.get("data"):
        return data["data"][0]
    return None


def obtener_cliente_por_id(client_id: str) -> dict | None:
    """Cliente por su UUID (para resolver el nombre a partir de un contrato)."""
    if not client_id:
        return None
    data = wispro_get(f"clients/{client_id}")
    if isinstance(data, dict) and data.get("status") == 200:
        d = data.get("data")
        if isinstance(d, list):
            return d[0] if d else None
        return d
    return None


def obtener_contratos(client_id: str) -> list:
    data = wispro_get("contracts", {"client_id_eq": client_id})
    if data.get("status") == 200:
        d = data.get("data", [])
        return d if isinstance(d, list) else [d]
    return []


def obtener_contratos_recientes(dias: int = 45, limite: int = 200) -> list:
    """Contratos creados en los últimos `dias`, ordenados del más nuevo primero.
    Sirve para ofrecer los altas recientes al habilitar una ONT (el filtro por
    ciudad se hace del lado del llamador con address_city/node_name)."""
    desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    data = wispro_get("contracts", {"created_at_after": desde, "per_page": limite})
    if data.get("status") != 200:
        return []
    d = data.get("data", [])
    contratos = d if isinstance(d, list) else [d]
    contratos.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return contratos


def obtener_contrato_por_public_id(public_id: str) -> dict | None:
    data = wispro_get("contracts", {"public_id_eq": public_id})
    if data.get("status") == 200 and data.get("data"):
        d = data["data"]
        return d[0] if isinstance(d, list) else d
    return None


def cambiar_estado_contrato(contract_id: str, estado: str) -> tuple[bool, dict]:
    """PATCH /contracts/{id} con {state}. estado ∈ {enabled, alerted, disabled}.
    Devuelve (ok, data)."""
    http, data = wispro_patch(f"contracts/{contract_id}", {"state": estado})
    ok = http == 200 and (data.get("status") in (200, None) if isinstance(data, dict) else False)
    if not ok:
        log_error(f"[WISPRO] No se pudo cambiar contrato {contract_id} a '{estado}': "
                  f"http={http} data={data}")
    return ok, data


def obtener_cuenta_corriente(client_id: str) -> dict | None:
    data = wispro_get(f"clients/{client_id}/current_account")
    if data.get("status") == 200:
        return data.get("data")
    return None


def obtener_facturas(client_id: str, limite: int = 3) -> list:
    data = wispro_get("invoicing/invoices", {
        "client_custom_id_eq": client_id,
        "per_page": 999
    }, timeout=50)
    if data.get("status") == 200:
        facturas = data.get("data", [])
        facturas = [f for f in facturas if f.get("state") != "void"]
        facturas.sort(key=lambda x: x.get("issued_at", ""), reverse=True)
        return facturas[:limite]
    return []


def descargar_pdf_factura(invoice_id: str) -> bytes | None:
    url = f"{WISPRO_URL}/api/v1/invoicing/invoices/{invoice_id}/download_pdf"
    log_debug(f"[WISPRO] Descargando PDF factura {invoice_id}")
    res = requests.get(url, headers=WISPRO_HEADERS, timeout=15)
    if res.status_code == 200:
        return res.content
    log_error(f"[WISPRO] Error descargando PDF: {res.status_code}")
    return None


def obtener_ultimos_clientes(cantidad: int = 10) -> list:
    data = wispro_get("clients", {"per_page": 20})
    if data.get("status") != 200:
        return []
    total_pages = data.get("meta", {}).get("pagination", {}).get("total_pages", 1)
    data = wispro_get("clients", {"per_page": 20, "page": total_pages})
    if data.get("status") == 200 and data.get("data"):
        clientes = data["data"]
        return list(reversed(clientes[-cantidad:]))
    return []


def obtener_ips_libres(zona: str = "moldes") -> list:
    mk = MIKROTIKS.get(zona.lower())
    if not mk or not mk["id"]:
        return []
    log_debug(f"[WISPRO] IPs libres zona={zona} rango={mk['rango']}")
    res = requests.get(
        f"{WISPRO_URL}/api/v1/mikrotiks/{mk['id']}/free_ips",
        headers=WISPRO_HEADERS,
        params={"ip_cont": mk["rango"]},
        timeout=15
    )
    if res.status_code == 200:
        return res.json()
    return []


# ── OLT / ONT ──────────────────────────────────────────────────

def listar_olts() -> list:
    """Lista las OLT del sistema (para descubrir sus UUID)."""
    data = wispro_get("olts", {"per_page": 100})
    return _como_lista(data)


def onts_de_olt(olt_id: str, timeout: int = 60) -> list:
    """ONTs que la OLT ve en este momento. Las recién instaladas aparecen con
    authorized=false, junto con su serial e interface. El tiempo de respuesta
    depende de la OLT (puede tardar)."""
    url = f"{WISPRO_URL}/api/v1/olts/{olt_id}/onts_from_olt"
    log_debug(f"[WISPRO] GET {url}")
    res = requests.get(url, headers=WISPRO_HEADERS, timeout=timeout)
    if res.status_code != 200:
        log_error(f"[WISPRO] onts_from_olt http={res.status_code} olt={olt_id}")
        return []
    try:
        return _como_lista(res.json())
    except ValueError:
        return []


def autorizar_ont(olt_id: str, contract_id: str, serial: str,
                  interface: str, timeout: int = 90) -> tuple[bool, int, dict]:
    """Autoriza/reconfigura una ONT contra un contrato. Devuelve (ok, http, data)."""
    payload = {
        "olt_id":      olt_id,
        "contract_id": contract_id,
        "serial":      serial,
        "interface":   interface,
    }
    http, data = wispro_post(
        f"olts/{olt_id}/authorize_or_reconfigure", payload, timeout=timeout
    )
    ok = http in (200, 201)
    if not ok:
        log_error(f"[WISPRO] No se pudo autorizar ONT serial={serial} "
                  f"iface={interface} http={http} data={data}")
    return ok, http, data


def estado_ont(contract_id: str, timeout: int = 30) -> dict | None:
    """Estado de la ONT de un contrato (para verificar que quedó online)."""
    data = wispro_get(f"contracts/{contract_id}/status_ont", timeout=timeout)
    if isinstance(data, dict) and data.get("status") == 200:
        return data.get("data")
    return data if isinstance(data, dict) else None
