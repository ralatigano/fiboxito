import os
import stat
import threading
import posixpath

import paramiko

from logger import log_debug, log_error


class NASError(Exception):
    """Error de operación contra el NAS (conexión, permisos, ruta inválida)."""


class SFTPClient:
    """Wrapper Paramiko/SFTP para el NAS OMV. Autenticación por clave.

    Todas las rutas se resuelven RELATIVAS a `base_path` y se valida que no
    escapen de ella (defensa contra path traversal, además del chroot en OMV).
    Reconecta de forma perezosa si el transport se cayó.
    """

    def __init__(self, config: dict):
        self.host      = config["host"]
        self.port      = config["port"]
        self.username  = config["username"]
        self.key_path  = config["key_path"]
        self.base_path = config.get("base_path", ".")
        self.client    = None
        self.sftp      = None
        self._lock     = threading.Lock()

    # ---- conexión -------------------------------------------------------

    def connect(self):
        key_file = os.path.abspath(self.key_path)
        if not os.path.isfile(key_file):
            raise NASError(f"No se encontró la clave privada: {key_file}")
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            key_filename=key_file,
            timeout=10,
            allow_agent=False,
            look_for_keys=False,
        )
        self.sftp = self.client.open_sftp()
        # Fijar el "cwd" del canal en la carpeta base para que las rutas
        # relativas cuelguen de ahí.
        try:
            self.sftp.chdir(self.base_path)
        except IOError as e:
            raise NASError(f"No se pudo acceder a la carpeta base '{self.base_path}': {e}")
        log_debug(f"[NAS] Conectado a {self.username}@{self.host}:{self.port} base={self.base_path}")

    def disconnect(self):
        if self.sftp:
            self.sftp.close()
            self.sftp = None
        if self.client:
            self.client.close()
            self.client = None

    def is_connected(self) -> bool:
        if self.client is None:
            return False
        transport = self.client.get_transport()
        return transport is not None and transport.is_active()

    def _ensure(self):
        if not self.is_connected():
            self.connect()

    # ---- validación de rutas -------------------------------------------

    def _safe(self, path: str) -> str:
        """Normaliza una ruta relativa y garantiza que no escape de la base."""
        p = posixpath.normpath(posixpath.join("/", path or "."))
        # p arranca con "/" tras normpath; lo volvemos relativo al cwd del sftp.
        rel = p.lstrip("/")
        if rel.startswith("..") or "/../" in f"/{rel}/":
            raise NASError(f"Ruta fuera de la carpeta permitida: {path}")
        return rel or "."

    # ---- operaciones ----------------------------------------------------

    def listar(self, path: str = ".") -> list[dict]:
        rel = self._safe(path)
        with self._lock:
            self._ensure()
            try:
                entries = self.sftp.listdir_attr(rel)
            except IOError as e:
                raise NASError(f"No se pudo listar '{path}': {e}")
        resultado = []
        for a in entries:
            es_dir = stat.S_ISDIR(a.st_mode) if a.st_mode else False
            resultado.append({
                "nombre":    a.filename,
                "tipo":      "dir" if es_dir else "archivo",
                "tamano":    a.st_size,
                "modificado": a.st_mtime,
            })
        resultado.sort(key=lambda x: (x["tipo"] != "dir", x["nombre"].lower()))
        return resultado

    def _stat(self, rel: str):
        try:
            return self.sftp.stat(rel)
        except IOError as e:
            raise NASError(f"No se pudo acceder a '{rel}': {e}")

    def leer(self, path: str, max_bytes: int) -> bytes:
        rel = self._safe(path)
        with self._lock:
            self._ensure()
            st = self._stat(rel)
            if st.st_size and st.st_size > max_bytes:
                raise NASError(
                    f"Archivo demasiado grande ({st.st_size} bytes > límite {max_bytes})."
                )
            try:
                with self.sftp.open(rel, "rb") as f:
                    return f.read()
            except IOError as e:
                raise NASError(f"No se pudo leer '{path}': {e}")

    def escribir(self, path: str, contenido: bytes):
        rel = self._safe(path)
        with self._lock:
            self._ensure()
            try:
                self._mkdirs(posixpath.dirname(rel))
                with self.sftp.open(rel, "wb") as f:
                    f.write(contenido)
            except IOError as e:
                raise NASError(f"No se pudo escribir '{path}': {e}")
        log_debug(f"[NAS] Escrito {path} ({len(contenido)} bytes)")

    def existe(self, path: str) -> bool:
        rel = self._safe(path)
        with self._lock:
            self._ensure()
            try:
                self.sftp.stat(rel)
                return True
            except IOError:
                return False

    def renombrar(self, origen: str, destino: str):
        """Renombra/mueve dentro de la base. Usa posix_rename (atómico y
        sobrescribe el destino) si el server lo soporta; si no, cae a rename."""
        rel_o = self._safe(origen)
        rel_d = self._safe(destino)
        with self._lock:
            self._ensure()
            try:
                self.sftp.posix_rename(rel_o, rel_d)
            except (IOError, AttributeError):
                try:
                    try:
                        self.sftp.remove(rel_d)
                    except IOError:
                        pass
                    self.sftp.rename(rel_o, rel_d)
                except IOError as e:
                    raise NASError(f"No se pudo renombrar '{origen}'→'{destino}': {e}")

    def _mkdirs(self, rel_dir: str):
        """Crea directorios intermedios (relativo a la base), tipo mkdir -p."""
        if not rel_dir or rel_dir in (".", "/"):
            return
        partes = rel_dir.strip("/").split("/")
        acum = ""
        for parte in partes:
            acum = f"{acum}/{parte}" if acum else parte
            try:
                self.sftp.stat(acum)
            except IOError:
                try:
                    self.sftp.mkdir(acum)
                except IOError as e:
                    raise NASError(f"No se pudo crear directorio '{acum}': {e}")
