import threading

from logger import log_error
from .config import (
    NAS_SSH_HOST, NAS_SSH_PORT, NAS_SSH_USER, NAS_SSH_KEY,
    NAS_BASE_PATH, NAS_MAX_FILE_MB,
)
from .sftp_client import SFTPClient, NASError

_client: SFTPClient | None = None
_client_lock = threading.Lock()


def get_client() -> SFTPClient:
    """Devuelve el cliente SFTP compartido (lazy singleton)."""
    global _client
    if not NAS_SSH_HOST:
        raise NASError("NAS no configurado: falta NAS_SSH_HOST en el .env")
    with _client_lock:
        if _client is None:
            _client = SFTPClient({
                "host":      NAS_SSH_HOST,
                "port":      NAS_SSH_PORT,
                "username":  NAS_SSH_USER,
                "key_path":  NAS_SSH_KEY,
                "base_path": NAS_BASE_PATH,
            })
    return _client


def listar(path: str = ".") -> list[dict]:
    return get_client().listar(path)


def leer(path: str) -> bytes:
    return get_client().leer(path, NAS_MAX_FILE_MB * 1024 * 1024)


def escribir(path: str, contenido: bytes):
    return get_client().escribir(path, contenido)


def existe(path: str) -> bool:
    return get_client().existe(path)


def renombrar(origen: str, destino: str):
    return get_client().renombrar(origen, destino)


def buscar(termino: str, base: str = ".", max_depth: int = 4,
           max_result: int = 30) -> list[str]:
    """Busca archivos cuyo nombre contenga `termino` (case-insensitive) bajo
    `base`, recorriendo el árbol hasta `max_depth` niveles. Devuelve rutas
    relativas a la base del NAS. Ignora carpetas sin permiso de lectura."""
    termino_l = termino.lower()
    resultados: list[str] = []

    def _walk(rel: str, depth: int):
        if len(resultados) >= max_result or depth > max_depth:
            return
        try:
            entradas = listar(rel)
        except NASError:
            return  # sin permiso o no accesible: saltar
        for e in entradas:
            hijo = e["nombre"] if rel in (".", "") else f"{rel}/{e['nombre']}"
            if e["tipo"] == "archivo":
                if termino_l in e["nombre"].lower():
                    resultados.append(hijo)
                    if len(resultados) >= max_result:
                        return
            elif e["tipo"] == "dir":
                _walk(hijo, depth + 1)

    _walk(base or ".", 0)
    return resultados


def probar_conexion() -> dict:
    """Diagnóstico: intenta conectar y listar la raíz."""
    try:
        c = get_client()
        c.connect()
        entradas = c.listar(".")
        return {"ok": True, "host": NAS_SSH_HOST, "base": NAS_BASE_PATH,
                "entradas": len(entradas)}
    except NASError as e:
        log_error(f"[NAS] prueba de conexión falló: {e}")
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        log_error(f"[NAS] prueba de conexión error inesperado: {e}")
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
