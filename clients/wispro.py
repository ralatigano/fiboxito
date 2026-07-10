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


def buscar_cliente(termino: str) -> dict | None:
    if termino.isdigit():
        data = wispro_get("clients", {"public_id_eq": termino})
    else:
        data = wispro_get("clients", {"name_unaccent_cont": termino})
    if data.get("status") == 200 and data.get("data"):
        return data["data"][0]
    return None


def obtener_contratos(client_id: str) -> list:
    data = wispro_get("contracts", {"client_id_eq": client_id})
    if data.get("status") == 200:
        d = data.get("data", [])
        return d if isinstance(d, list) else [d]
    return []


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
