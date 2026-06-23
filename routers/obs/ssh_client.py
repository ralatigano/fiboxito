import threading
import paramiko


class SSHClient:
    def __init__(self, config: dict):
        self.host     = config["host"]
        self.port     = config["port"]
        self.username = config["username"]
        self.password = config["password"]
        self.client   = None
        self._lock    = threading.Lock()

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=10,
        )

    def disconnect(self):
        if self.client:
            self.client.close()
            self.client = None

    def is_connected(self) -> bool:
        if self.client is None:
            return False
        transport = self.client.get_transport()
        return transport is not None and transport.is_active()

    def run_command(self, command: str, timeout: int = 15) -> tuple[str, str]:
        with self._lock:
            if not self.is_connected():
                raise ConnectionError("SSH no conectado")
            _, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            return stdout.read().decode().strip(), stderr.read().decode().strip()
