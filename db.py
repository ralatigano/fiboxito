import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "fibox.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS naps_cache (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            data        TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS estados_cliente (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT NOT NULL UNIQUE,
            color       TEXT NOT NULL DEFAULT '#94a3b8',
            icono       TEXT NOT NULL DEFAULT 'circle'
        );

        CREATE TABLE IF NOT EXISTS clientes_mapa (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wispro_id   INTEGER,
            lat         REAL NOT NULL,
            lng         REAL NOT NULL,
            nombre      TEXT,
            descripcion TEXT,
            estado_id   INTEGER REFERENCES estados_cliente(id),
            updated_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS red_tramos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            wkt         TEXT NOT NULL,
            nombre      TEXT,
            tipo        TEXT NOT NULL DEFAULT 'drop',
            updated_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS prospectos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lat         REAL NOT NULL,
            lng         REAL NOT NULL,
            telefono    TEXT,
            nota        TEXT,
            tiene_caja  INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT
        );
        """)

        # Estados por defecto si la tabla está vacía
        count = conn.execute(
            "SELECT COUNT(*) FROM estados_cliente").fetchone()[0]
        if count == 0:
            estados = [
                ("OK",                  "#22c55e", "check"),
                ("A confirmar",         "#3b82f6", "question"),
                ("Baja",                "#94a3b8", "minus"),
                ("Deuda",               "#f97316", "alert"),
                ("Cancelada",           "#ef4444", "x"),
                ("En espera de puerto", "#a855f7", "clock"),
                ("Tarea",               "#eab308", "star"),
                ("Miércoles",           "#06b6d4", "calendar"),
                ("Jueves",              "#06b6d4", "calendar"),
            ]
            conn.executemany(
                "INSERT INTO estados_cliente (nombre, color, icono) VALUES (?,?,?)",
                estados
            )


# ── NAPs cache ──────────────────────────────────────────────

def get_naps_cache() -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT data, updated_at FROM naps_cache WHERE id=1").fetchone()
        if not row:
            return None
        return {"data": json.loads(row["data"]), "updated_at": row["updated_at"]}


def set_naps_cache(data: list):
    now = datetime.utcnow().isoformat()
    payload = json.dumps(data)
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO naps_cache (id, data, updated_at) VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at
        """, (payload, now))


# ── Estados ──────────────────────────────────────────────────

def get_estados() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM estados_cliente ORDER BY nombre").fetchall()
        return [dict(r) for r in rows]


def upsert_estado(nombre: str, color: str, icono: str) -> int:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO estados_cliente (nombre, color, icono) VALUES (?,?,?)
            ON CONFLICT(nombre) DO UPDATE SET color=excluded.color, icono=excluded.icono
        """, (nombre, color, icono))
        return conn.execute("SELECT id FROM estados_cliente WHERE nombre=?", (nombre,)).fetchone()["id"]


def delete_estado(estado_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE clientes_mapa SET estado_id=NULL WHERE estado_id=?", (estado_id,))
        conn.execute("DELETE FROM estados_cliente WHERE id=?", (estado_id,))


# ── Clientes ─────────────────────────────────────────────────

def get_clientes() -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT c.*, e.nombre as estado_nombre, e.color as estado_color, e.icono as estado_icono
            FROM clientes_mapa c
            LEFT JOIN estados_cliente e ON c.estado_id = e.id
            ORDER BY c.id
        """).fetchall()
        return [dict(r) for r in rows]


def upsert_cliente(wispro_id: int | None, lat: float, lng: float,
                   nombre: str, descripcion: str, estado_nombre: str) -> int:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        estado_row = conn.execute(
            "SELECT id FROM estados_cliente WHERE nombre=?", (estado_nombre,)
        ).fetchone()
        if estado_row:
            estado_id = estado_row["id"]
        else:
            conn.execute(
                "INSERT INTO estados_cliente (nombre, color, icono) VALUES (?,?,?)",
                (estado_nombre, "#94a3b8", "circle")
            )
            estado_id = conn.execute(
                "SELECT id FROM estados_cliente WHERE nombre=?", (
                    estado_nombre,)
            ).fetchone()["id"]

        if wispro_id:
            existing = conn.execute(
                "SELECT id FROM clientes_mapa WHERE wispro_id=?", (wispro_id,)
            ).fetchone()
        else:
            existing = None

        if existing:
            conn.execute("""
                UPDATE clientes_mapa
                SET lat=?, lng=?, nombre=?, descripcion=?, estado_id=?, updated_at=?
                WHERE id=?
            """, (lat, lng, nombre, descripcion, estado_id, now, existing["id"]))
            return existing["id"]
        else:
            cur = conn.execute("""
                INSERT INTO clientes_mapa (wispro_id, lat, lng, nombre, descripcion, estado_id, updated_at)
                VALUES (?,?,?,?,?,?,?)
            """, (wispro_id, lat, lng, nombre, descripcion, estado_id, now))
            return cur.lastrowid


def update_cliente_estado(cliente_id: int, estado_nombre: str):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        estado_row = conn.execute(
            "SELECT id FROM estados_cliente WHERE nombre=?", (estado_nombre,)
        ).fetchone()
        if not estado_row:
            conn.execute(
                "INSERT INTO estados_cliente (nombre, color, icono) VALUES (?,?,?)",
                (estado_nombre, "#94a3b8", "circle")
            )
            estado_id = conn.execute(
                "SELECT id FROM estados_cliente WHERE nombre=?", (
                    estado_nombre,)
            ).fetchone()["id"]
        else:
            estado_id = estado_row["id"]
        conn.execute(
            "UPDATE clientes_mapa SET estado_id=?, updated_at=? WHERE id=?",
            (estado_id, now, cliente_id)
        )


def delete_cliente(cliente_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM clientes_mapa WHERE id=?", (cliente_id,))


def sync_cliente_wispro(wispro_id: int, nombre: str, estado_nombre: str):
    """Actualiza solo nombre y estado de un cliente existente por wispro_id."""
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM clientes_mapa WHERE wispro_id=?", (wispro_id,)
        ).fetchone()
        if not existing:
            return
        estado_row = conn.execute(
            "SELECT id FROM estados_cliente WHERE nombre=?", (estado_nombre,)
        ).fetchone()
        if estado_row:
            estado_id = estado_row["id"]
        else:
            conn.execute(
                "INSERT INTO estados_cliente (nombre, color, icono) VALUES (?,?,?)",
                (estado_nombre, "#94a3b8", "circle")
            )
            estado_id = conn.execute(
                "SELECT id FROM estados_cliente WHERE nombre=?", (
                    estado_nombre,)
            ).fetchone()["id"]
        conn.execute(
            "UPDATE clientes_mapa SET nombre=?, estado_id=?, updated_at=? WHERE wispro_id=?",
            (nombre, estado_id, now, wispro_id)
        )


# ── Red / Tramos ─────────────────────────────────────────────

def get_tramos() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM red_tramos ORDER BY tipo, nombre").fetchall()
        return [dict(r) for r in rows]


def upsert_tramo(wkt: str, nombre: str, tipo: str, tramo_id: int | None = None) -> int:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        if tramo_id:
            conn.execute(
                "UPDATE red_tramos SET wkt=?, nombre=?, tipo=?, updated_at=? WHERE id=?",
                (wkt, nombre, tipo, now, tramo_id)
            )
            return tramo_id
        else:
            cur = conn.execute(
                "INSERT INTO red_tramos (wkt, nombre, tipo, updated_at) VALUES (?,?,?,?)",
                (wkt, nombre, tipo, now)
            )
            return cur.lastrowid


def delete_tramo(tramo_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM red_tramos WHERE id=?", (tramo_id,))


# ── Prospectos ────────────────────────────────────────────────

def get_prospectos() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM prospectos ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def crear_prospecto(lat: float, lng: float, telefono: str, nota: str,
                    tiene_caja: bool = False) -> int:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO prospectos (lat, lng, telefono, nota, tiene_caja, created_at) VALUES (?,?,?,?,?,?)",
            (lat, lng, telefono, nota, int(tiene_caja), now)
        )
        return cur.lastrowid


def update_prospecto_nota(prospecto_id: int, nota: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE prospectos SET nota=? WHERE id=?", (nota, prospecto_id)
        )


def update_prospecto_caja(prospecto_id: int, tiene_caja: bool):
    with get_conn() as conn:
        conn.execute(
            "UPDATE prospectos SET tiene_caja=? WHERE id=?",
            (int(tiene_caja), prospecto_id)
        )


def delete_prospecto(prospecto_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM prospectos WHERE id=?", (prospecto_id,))
