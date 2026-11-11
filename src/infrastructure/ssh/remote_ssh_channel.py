import os
import socket
import threading
from typing import Callable, Optional, Tuple
import paramiko

from src.core.logger import get_logger

logger = get_logger("RemoteSSHChannel")


class RemoteSSHChannel:
    """
    Manages SSH client connections and SFTP file operations to remote hosts.
    """

    def __init__(self) -> None:
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None
        self._lock = threading.Lock()
        self._host: str = ""
        self._port: int = 22
        self._username: str = ""

    @property
    def is_connected(self) -> bool:
        with self._lock:
            if not self._client:
                return False
            transport = self._client.get_transport()
            return transport is not None and transport.is_active()

    def connect(
        self, host: str, port: int = 22, username: str = "ubuntu", password: str = "123", timeout: float = 6.0
    ) -> Tuple[bool, str]:
        with self._lock:
            self.disconnect()
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password,
                    timeout=timeout,
                    banner_timeout=timeout,
                    auth_timeout=timeout,
                )
                self._client = client
                self._host = host
                self._port = port
                self._username = username
                logger.info(f"Connected to remote host {host}:{port} as {username}")
                return True, "Connected successfully"
            except Exception as e:
                logger.error(f"Failed to connect to {host}:{port}: {e}")
                return False, str(e)

    def disconnect(self) -> None:
        if self._sftp:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def execute_command(self, cmd: str, timeout: float = 30.0) -> Tuple[int, str, str]:
        with self._lock:
            if not self.is_connected or not self._client:
                return -1, "", "Not connected to remote host"
            try:
                stdin, stdout, stderr = self._client.exec_command(cmd, timeout=timeout)
                out = stdout.read().decode("utf-8", errors="replace")
                err = stderr.read().decode("utf-8", errors="replace")
                code = stdout.channel.recv_exit_status()
                return code, out, err
            except Exception as e:
                logger.error(f"SSH exec error for '{cmd[:40]}...': {e}")
                return -1, "", str(e)

    def upload_file(
        self, local_path: str, remote_path: str, callback: Optional[Callable[[int, int], None]] = None
    ) -> Tuple[bool, str]:
        with self._lock:
            if not self.is_connected or not self._client:
                return False, "Not connected"
            try:
                if not self._sftp:
                    self._sftp = self._client.open_sftp()
                self._sftp.put(local_path, remote_path, callback=callback)
                return True, "Upload completed"
            except Exception as e:
                logger.error(f"SFTP upload failed: {e}")
                return False, str(e)


ssh_channel = RemoteSSHChannel()
