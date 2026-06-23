from routers.obs.ssh_client import SSHClient
from routers.obs.config import OBS_STATE_FILE, OBS_LOG_FILE


class WatchdogController:
    def __init__(self, ssh: SSHClient):
        self.ssh = ssh

    def get_status(self) -> str:
        out, _ = self.ssh.run_command("systemctl is-active obs-watchdog.service")
        return out

    def start(self):
        self.ssh.run_command("systemctl start obs-watchdog.service")

    def stop(self):
        self.ssh.run_command("systemctl stop obs-watchdog.service")

    def restart(self):
        self.ssh.run_command("systemctl restart obs-watchdog.service")

    def get_state_json(self) -> str:
        out, _ = self.ssh.run_command(f"cat {OBS_STATE_FILE}")
        return out

    def get_logs(self, lines: int = 100) -> str:
        out, _ = self.ssh.run_command(f"tail -n {lines} {OBS_LOG_FILE}")
        return out
