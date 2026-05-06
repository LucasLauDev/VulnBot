import paramiko

from actions.remote_shell import RemoteShell
from config.config import Configs


class ShellManager:
    _instance = None
    _ssh_client = None
    _shell = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_shell(self) -> RemoteShell:
        if self._shell is None:
            self._connect()
        return self._shell

    def _connect(self):
        if self._ssh_client is None:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(
                    hostname=Configs.basic_config.kali["hostname"],
                    username=Configs.basic_config.kali["username"],
                    password=Configs.basic_config.kali["password"],
                    port=int(Configs.basic_config.kali["port"]),
                    timeout=30,
                    banner_timeout=30,
                    auth_timeout=30,
                )
            except Exception:
                client.close()
                raise
            self._ssh_client = client
        if self._shell is None:
            try:
                self._shell = RemoteShell(self._ssh_client.invoke_shell())
            except Exception:
                self.close()
                raise

    def close(self):
        if self._shell:
            try:
                self._shell.shell.close()
            except Exception:
                pass
            self._shell = None

        if self._ssh_client:
            try:
                self._ssh_client.close()
            except Exception:
                pass
            self._ssh_client = None