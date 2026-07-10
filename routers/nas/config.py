import os

# Conexión SSH/SFTP al NAS OpenMediaVault (por ZeroTier).
# Autenticación por CLAVE (no password): más seguro y sin credencial en texto.
NAS_SSH_HOST = os.getenv("NAS_SSH_HOST", "")          # IP ZeroTier del NAS
NAS_SSH_PORT = int(os.getenv("NAS_SSH_PORT", "22"))
NAS_SSH_USER = os.getenv("NAS_SSH_USER", "fiboxito")  # usuario dedicado en OMV
NAS_SSH_KEY  = os.getenv("NAS_SSH_KEY", "keys/fiboxito_nas")  # ruta a la clave privada

# Carpeta base a la que Fiboxito tiene acceso. Con SFTP chroot en el NAS el
# usuario ya queda encerrado; esto es defensa en profundidad del lado Python.
# "." = home del usuario (raíz del chroot).
NAS_BASE_PATH = os.getenv("NAS_BASE_PATH", ".")

# Límite de tamaño para traer/leer archivos (MB). Evita traer un ISO por error.
NAS_MAX_FILE_MB = int(os.getenv("NAS_MAX_FILE_MB", "50"))
