import re
import csv
import io
import json
import asyncio
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ── Caché de NAPs: refresco cada 1 hora ──────────────────────

CACHE_TTL_HORAS = 1
_naps_lock = asyncio.Lock()


async def refrescar_naps_si_necesario():
    from agent_backend import wispro_get
    from db import get_naps_cache, set_naps_cache

    cache = get_naps_cache()
    if cache:
        age = datetime.utcnow() - datetime.fromisoformat(cache["updated_at"])
        if age < timedelta(hours=CACHE_TTL_HORAS):
            return cache["data"]

    # Fetch paginado
    all_naps = []
    page = 1
    while True:
        data = wispro_get("naps", {"page": page, "per_page": 20})
        if data.get("status") != 200:
            break
        all_naps.extend(data["data"])
        if page >= data["meta"]["pagination"]["total_pages"]:
            break
        page += 1

    result = []
    for nap in all_naps:
        lat = nap.get("latitude")
        lng = nap.get("longitude")
        if not lat or not lng:
            continue
        capacity = nap.get("capacity", 0)
        contracts = nap.get("contracts_count", 0)
        name = nap.get("name", "")
        result.append({
            "id":        nap["public_id"],
            "name":      name,
            "capacity":  capacity,
            "contracts": contracts,
            "available": capacity - contracts,
            "lat":       float(lat),
            "lng":       float(lng),
            "inactive":  capacity <= 1 or "no instal" in name.lower(),
        })

    set_naps_cache(result)
    return result


# Tarea background: refresca NAPs cada hora
async def naps_background_loop():
    while True:
        try:
            async with _naps_lock:
                await refrescar_naps_si_necesario()
        except Exception as e:
            print(f"[MAPA] Error refrescando NAPs: {e}")
        await asyncio.sleep(3600)


# Tarea background: sync clientes desde Wispro una vez por día
async def sync_clientes_loop():
    await asyncio.sleep(10)  # espera arranque inicial
    while True:
        try:
            await _sync_clientes_wispro()
        except Exception as e:
            print(f"[MAPA] Error sync clientes: {e}")
        await asyncio.sleep(86400)  # 24 hs


async def _sync_clientes_wispro():
    import requests as req_lib
    from db import sync_cliente_wispro
    WISPRO_URL_val = __import__('os').getenv("WISPRO_URL", "").rstrip("/")
    WISPRO_TOKEN_val = __import__('os').getenv("WISPRO_TOKEN", "")
    headers = {"Accept": "application/json", "Authorization": WISPRO_TOKEN_val}

    page = 1
    synced = 0
    while True:
        try:
            r = req_lib.get(
                f"{WISPRO_URL_val}/api/v1/clients",
                headers=headers,
                params={"page": page, "per_page": 50},
                timeout=15
            )
            data = r.json()
        except Exception as e:
            print(f"[MAPA] Error sync página {page}: {e}")
            break
        if data.get("status") != 200:
            break
        for c in data.get("data", []):
            wispro_id = c.get("public_id")
            nombre = c.get("name") or c.get("full_name", "")
            # El estado del cliente en Wispro viene del contrato activo,
            # por ahora solo actualizamos el nombre
            if wispro_id and nombre:
                sync_cliente_wispro(wispro_id, nombre, None)
                synced += 1
        pagination = data.get("meta", {}).get("pagination", {})
        if page >= pagination.get("total_pages", 1):
            break
        page += 1
    print(f"[MAPA] Sync clientes completado: {synced} nombres actualizados")


def inferir_tipo(nombre: str) -> str:
    n = (nombre or "").lower()
    if "troncal" in n:
        return "troncal"
    if "oval" in n:
        return "oval"
    return "drop"


def parsear_wkt_linestring(wkt: str) -> list[list[float]]:
    """Devuelve lista de [lat, lng] desde WKT LINESTRING."""
    coords_str = re.search(r'LINESTRING\s*\((.+)\)', wkt)
    if not coords_str:
        return []
    pairs = coords_str.group(1).split(",")
    result = []
    for pair in pairs:
        parts = pair.strip().split()
        if len(parts) >= 2:
            lng, lat = float(parts[0]), float(parts[1])
            result.append([lat, lng])
    return result


def parsear_wkt_point(wkt: str) -> list[float] | None:
    m = re.search(r'POINT\s*\((-?\d+\.?\d*)\s+(-?\d+\.?\d*)\)', wkt)
    if m:
        return [float(m.group(2)), float(m.group(1))]  # lat, lng
    return None


# ═══════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════

@router.get("/mapa", response_class=HTMLResponse)
async def mapa(request: Request):
    return templates.TemplateResponse(request=request, name="mapa.html")


# ── NAPs ──────────────────────────────────────────────────────

@router.get("/api/naps")
async def get_naps():
    async with _naps_lock:
        return await refrescar_naps_si_necesario()


@router.post("/api/naps/refrescar")
async def forzar_refresco_naps():
    from db import set_naps_cache
    set_naps_cache([])  # invalida caché
    async with _naps_lock:
        data = await refrescar_naps_si_necesario()
    return {"ok": True, "total": len(data)}


# ── Estados ───────────────────────────────────────────────────

@router.get("/api/estados")
async def get_estados():
    from db import get_estados
    return get_estados()


class EstadoBody(BaseModel):
    nombre: str
    color:  str = "#94a3b8"
    icono:  str = "circle"


@router.post("/api/estados")
async def crear_estado(body: EstadoBody):
    from db import upsert_estado
    id_ = upsert_estado(body.nombre, body.color, body.icono)
    return {"ok": True, "id": id_}


@router.delete("/api/estados/{estado_id}")
async def eliminar_estado(estado_id: int):
    from db import delete_estado
    delete_estado(estado_id)
    return {"ok": True}


# ── Clientes ──────────────────────────────────────────────────

@router.get("/api/clientes")
async def get_clientes():
    from db import get_clientes
    return get_clientes()


@router.post("/api/clientes/sync")
async def sync_clientes_manual():
    await _sync_clientes_wispro()
    return {"ok": True}


class ClienteEstadoBody(BaseModel):
    estado_nombre: str


@router.patch("/api/clientes/{cliente_id}/estado")
async def cambiar_estado_cliente(cliente_id: int, body: ClienteEstadoBody):
    from db import update_cliente_estado
    update_cliente_estado(cliente_id, body.estado_nombre)
    return {"ok": True}


@router.delete("/api/clientes/{cliente_id}")
async def eliminar_cliente(cliente_id: int):
    from db import delete_cliente
    delete_cliente(cliente_id)
    return {"ok": True}


@router.get("/api/clientes/{cliente_id}/detalle")
async def detalle_cliente_wispro(cliente_id: int):
    """Trae datos en tiempo real de Wispro para un cliente."""
    from agent_backend import wispro_get
    from db import get_conn
    with get_conn() as conn:
        row = conn.execute(
            "SELECT wispro_id FROM clientes_mapa WHERE id=?", (cliente_id,)
        ).fetchone()
    if not row or not row["wispro_id"]:
        raise HTTPException(404, "Cliente sin wispro_id")
    wid = row["wispro_id"]
    cliente = wispro_get(f"clients/{wid}")
    contratos = wispro_get(f"clients/{wid}/contracts")
    facturas = wispro_get(f"clients/{wid}/invoices", {"per_page": 3})
    return {
        "cliente":   cliente.get("data", {}),
        "contratos": contratos.get("data", []),
        "facturas":  facturas.get("data", []),
    }


# ── Importar CSV clientes ─────────────────────────────────────

@router.post("/api/clientes/importar")
async def importar_clientes(file: UploadFile = File(...)):
    from db import upsert_cliente
    raw = await file.read()
    # Intentar UTF-8 (con o sin BOM), luego latin-1 como fallback
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    ok = 0
    err = 0

    # El CSV tiene 7 valores por fila pero 6 headers porque WKT se expande en
    # dos columnas de coordenadas sueltas (lng, lat) desplazando todo.
    # Estrategia: leer crudamente por filas y mapear por posición fija.
    reader = csv.reader(io.StringIO(content))
    headers = next(reader, None)  # saltar header

    for raw in reader:
        try:
            # Posiciones fijas del CSV exportado por MyMaps:
            # 0: WKT_  "POINT (lng lat)"
            # 1: lng suelta  (ignorar)
            # 2: lat suelta  (ignorar)
            # 3: Cliente_ID  "Cliente 12"
            # 4: Nombre
            # 5: Descripción
            # 6: Estado
            if len(raw) < 5:
                err += 1
                continue

            wkt = raw[0].strip()
            punto = parsear_wkt_point(wkt)
            if not punto:
                err += 1
                continue
            lat, lng = punto

            wispro_raw = raw[3].replace(
                "Cliente", "").replace("cliente", "").strip()
            wispro_id = int(wispro_raw) if wispro_raw.isdigit() else None
            nombre = raw[4].strip() if len(raw) > 4 else ""
            descripcion = raw[5].strip() if len(raw) > 5 else ""
            estado_raw = raw[6].strip() if len(raw) > 6 else ""
            estado = estado_raw if estado_raw else "OK"

            upsert_cliente(wispro_id, lat, lng, nombre, descripcion, estado)
            ok += 1
        except Exception:
            err += 1
    return {"ok": ok, "errores": err}


# ── Red / Tramos ──────────────────────────────────────────────

@router.get("/api/tramos")
async def get_tramos():
    from db import get_tramos
    tramos = get_tramos()
    result = []
    for t in tramos:
        coords = parsear_wkt_linestring(t["wkt"])
        if coords:
            result.append({
                "id":     t["id"],
                "nombre": t["nombre"],
                "tipo":   t["tipo"],
                "coords": coords,
            })
    return result


class TramoBody(BaseModel):
    coords: list[list[float]]  # [[lat,lng], ...]
    nombre: str = ""
    tipo:   str = "drop"
    id:     int | None = None


@router.post("/api/tramos")
async def guardar_tramo(body: TramoBody):
    from db import upsert_tramo
    # Convertir coords a WKT: Leaflet usa [lat,lng], WKT usa lng lat
    wkt_inner = ", ".join(f"{c[1]} {c[0]}" for c in body.coords)
    wkt = f"LINESTRING ({wkt_inner})"
    id_ = upsert_tramo(wkt, body.nombre, body.tipo, body.id)
    return {"ok": True, "id": id_}


@router.delete("/api/tramos/{tramo_id}")
async def eliminar_tramo(tramo_id: int):
    from db import delete_tramo
    delete_tramo(tramo_id)
    return {"ok": True}


@router.post("/api/tramos/importar")
async def importar_tramos(file: UploadFile = File(...)):
    from db import upsert_tramo
    raw = await file.read()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    reader = csv.DictReader(io.StringIO(content))
    ok = 0
    err = 0
    for row in reader:
        try:
            wkt = row.get("WKT", "")
            nombre = row.get("nombre", row.get("Nombre", ""))
            if "LINESTRING" not in wkt.upper():
                err += 1
                continue
            tipo = inferir_tipo(nombre)
            upsert_tramo(wkt, nombre, tipo)
            ok += 1
        except Exception:
            err += 1
    return {"ok": ok, "errores": err}


# ── Prospectos ────────────────────────────────────────────────

class ProspectoBody(BaseModel):
    lat:      float
    lng:      float
    telefono: str = ""
    nota:     str = ""


class ProspectoEstadoBody(BaseModel):
    estado_nombre: str


@router.get("/api/prospectos")
async def get_prospectos():
    from db import get_prospectos
    return get_prospectos()


@router.post("/api/prospectos")
async def crear_prospecto(body: ProspectoBody):
    from db import crear_prospecto as db_crear
    id_ = db_crear(body.lat, body.lng, body.telefono, body.nota)
    return {"ok": True, "id": id_}


@router.patch("/api/prospectos/{prospecto_id}/convertir")
async def convertir_prospecto(prospecto_id: int, body: ProspectoEstadoBody):
    """Mueve el prospecto a clientes_mapa con el estado elegido y lo borra de prospectos."""
    from db import get_conn, upsert_cliente, delete_prospecto
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM prospectos WHERE id=?", (prospecto_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Prospecto no encontrado")
    upsert_cliente(
        wispro_id=None,
        lat=row["lat"], lng=row["lng"],
        nombre=row["telefono"] or f"Prospecto {prospecto_id}",
        descripcion=row["nota"] or "",
        estado_nombre=body.estado_nombre
    )
    delete_prospecto(prospecto_id)
    return {"ok": True}


@router.patch("/api/prospectos/{prospecto_id}/nota")
async def actualizar_nota_prospecto(prospecto_id: int, body: ProspectoEstadoBody):
    from db import update_prospecto_nota
    update_prospecto_nota(prospecto_id, body.estado_nombre)
    return {"ok": True}


@router.delete("/api/prospectos/{prospecto_id}")
async def eliminar_prospecto(prospecto_id: int):
    from db import delete_prospecto
    delete_prospecto(prospecto_id)
    return {"ok": True}
