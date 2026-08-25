import os
import time
import socket
import threading
import logging
from typing import Callable, Optional, Tuple, Dict, Any

try:
    import paramiko
except ImportError:
    paramiko = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SSHManager")


class SSHManager:
    """SSH & SFTP 管理类，负责与宇树机器人进行通信与文件传输"""

    def __init__(self):
        self.host = "192.168.123.164"
        self.port = 22
        self.username = "unitree"
        self.password = "123"
        self.client: Optional[paramiko.SSHClient] = None
        self._is_connected = False
        self._lock = threading.Lock()

        # 进度追踪
        self.upload_progress = {
            "is_uploading": False,
            "filename": "",
            "transferred_bytes": 0,
            "total_bytes": 0,
            "percent": 0.0,
            "speed_mbps": 0.0,
            "eta_seconds": 0,
            "status": "idle",  # idle, uploading, completed, error
            "error_msg": "",
        }

    def set_credentials(self, host: str = "192.168.123.164", port: int = 22, username: str = "unitree", password: str = "123"):
        self.host = host.strip()
        self.port = int(port)
        self.username = username.strip()
        self.password = password

    def connect(self, timeout: float = 4.0) -> Tuple[bool, str]:
        """建立 SSH 连接"""
        with self._lock:
            if self._is_connected and self.client:
                return True, "已连接"

            if paramiko is None:
                return False, "Python 环境缺少 paramiko 库，请安装 paramiko"

            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                logger.info(f"正在尝试连接机器人 {self.username}@{self.host}:{self.port} ...")
                client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    timeout=timeout,
                    banner_timeout=timeout,
                    auth_timeout=timeout,
                    look_for_keys=False,
                    allow_agent=False
                )
                self.client = client
                self._is_connected = True
                logger.info(f"成功连接至机器人 {self.host}")
                return True, f"成功连接至 {self.host}"
            except socket.timeout:
                self._is_connected = False
                return False, f"连接超时：无法访问 {self.host}:{self.port}，请检查网线与网段"
            except paramiko.AuthenticationException:
                self._is_connected = False
                return False, f"认证失败：用户名或密码错误 ({self.username}/{self.password})"
            except Exception as e:
                self._is_connected = False
                return False, f"连接失败: {str(e)}"

    def disconnect(self):
        """断开连接"""
        with self._lock:
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
            self.client = None
            self._is_connected = False
            logger.info("SSH 连接已断开")

    def is_connected(self) -> bool:
        if not self._is_connected or self.client is None:
            return False
        # 检测底层 transport 状态
        try:
            transport = self.client.get_transport()
            if transport and transport.is_active():
                return True
        except Exception:
            pass
        self._is_connected = False
        return False

    def test_latency(self) -> float:
        """测试与机器人的连接延迟 (ms)"""
        if not self.is_connected():
            return -1.0
        start = time.perf_counter()
        code, out, err = self.execute_command("echo ping", timeout=3.0)
        if code == 0:
            return round((time.perf_counter() - start) * 1000, 1)
        return -1.0

    def execute_command(self, command: str, sudo: bool = False, timeout: float = 30.0) -> Tuple[int, str, str]:
        """
        执行单条命令并同步返回 (exit_code, stdout_str, stderr_str)
        """
        if not self.is_connected():
            conn_ok, msg = self.connect(timeout=2.0)
            if not conn_ok:
                return -1, "", f"未连接至机器人: {msg}"

        try:
            cmd = command
            if sudo and not command.strip().startswith("sudo"):
                cmd = f"echo '{self.password}' | sudo -S -p '' {command}"
            elif sudo and command.strip().startswith("sudo"):
                cmd = command.replace("sudo", f"echo '{self.password}' | sudo -S -p ''", 1)

            stdin, stdout, stderr = self.client.exec_command(cmd, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            out_str = stdout.read().decode("utf-8", errors="replace")
            err_str = stderr.read().decode("utf-8", errors="replace")
            return exit_code, out_str, err_str
        except Exception as e:
            logger.error(f"执行命令 '{command}' 异常: {e}")
            return -1, "", str(e)

    def execute_command_stream(self, command: str, callback: Callable[[str, bool], None], sudo: bool = False, timeout: float = 600.0) -> int:
        """
        流式执行命令，实时回调输出 (line, is_stderr)
        """
        if not self.is_connected():
            conn_ok, msg = self.connect()
            if not conn_ok:
                callback(f"[ERROR] 连接机器人失败: {msg}\n", True)
                return -1

        try:
            cmd = command
            if sudo and not command.strip().startswith("sudo"):
                cmd = f"echo '{self.password}' | sudo -S -p '' {command}"
            elif sudo and command.strip().startswith("sudo"):
                cmd = command.replace("sudo", f"echo '{self.password}' | sudo -S -p ''", 1)

            stdin, stdout, stderr = self.client.exec_command(cmd, get_pty=True, timeout=timeout)

            # 读取输出
            while True:
                line = stdout.readline()
                if not line:
                    break
                callback(line, False)

            exit_code = stdout.channel.recv_exit_status()
            return exit_code
        except Exception as e:
            callback(f"[EXCEPTION] 命令执行异常: {str(e)}\n", True)
            return -1

    def upload_file(self, local_path: str, remote_path: str, progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Tuple[bool, str]:
        """
        通过 SFTP 上传本地文件至机器人，提供实时速率与进度计算
        """
        if not os.path.exists(local_path):
            return False, f"本地文件不存在: {local_path}"

        total_bytes = os.path.getsize(local_path)
        filename = os.path.basename(local_path)

        if not self.is_connected():
            conn_ok, msg = self.connect()
            if not conn_ok:
                return False, f"连接未就绪: {msg}"

        start_time = time.time()
        last_time = start_time
        last_bytes = 0

        self.upload_progress.update({
            "is_uploading": True,
            "filename": filename,
            "transferred_bytes": 0,
            "total_bytes": total_bytes,
            "percent": 0.0,
            "speed_mbps": 0.0,
            "eta_seconds": 0,
            "status": "uploading",
            "error_msg": "",
        })

        def _sftp_callback(transferred: int, total: int):
            nonlocal last_time, last_bytes
            now = time.time()
            dt = now - last_time
            if dt >= 0.3 or transferred >= total:
                dbytes = transferred - last_bytes
                speed = (dbytes / (1024 * 1024)) / dt if dt > 0 else 0.0
                percent = round((transferred / total) * 100.0, 1) if total > 0 else 0.0
                remaining_bytes = total - transferred
                eta = int(remaining_bytes / (speed * 1024 * 1024)) if speed > 0 else 0

                self.upload_progress.update({
                    "transferred_bytes": transferred,
                    "percent": percent,
                    "speed_mbps": round(speed, 2),
                    "eta_seconds": eta,
                })
                last_time = now
                last_bytes = transferred
                if progress_callback:
                    progress_callback(self.upload_progress)

        try:
            sftp = self.client.open_sftp()
            # 确保远端父目录存在
            remote_dir = os.path.dirname(remote_path).replace("\\", "/")
            if remote_dir and remote_dir != "/":
                self.execute_command(f"mkdir -p {remote_dir}", sudo=True)

            logger.info(f"开始 SFTP 上传: {local_path} -> {remote_path} ({round(total_bytes/(1024*1024), 2)} MB)")
            sftp.put(local_path, remote_path, callback=_sftp_callback)
            sftp.close()

            self.upload_progress["status"] = "completed"
            self.upload_progress["percent"] = 100.0
            self.upload_progress["is_uploading"] = False
            if progress_callback:
                progress_callback(self.upload_progress)
            return True, f"文件成功上传至 {remote_path}"
        except Exception as e:
            err_msg = f"SFTP 上传失败: {str(e)}"
            logger.error(err_msg)
            self.upload_progress["status"] = "error"
            self.upload_progress["error_msg"] = err_msg
            self.upload_progress["is_uploading"] = False
            return False, err_msg

    def write_remote_text_file(self, content: str, remote_path: str, sudo: bool = True) -> Tuple[bool, str]:
        """向远程写入文本文件"""
        if not self.is_connected():
            return False, "未连接至机器人"

        temp_remote = f"/tmp/_vsis_tmp_{int(time.time()*1000)}.tmp"
        try:
            sftp = self.client.open_sftp()
            with sftp.file(temp_remote, "w") as f:
                f.write(content)
            sftp.close()

            remote_dir = os.path.dirname(remote_path).replace("\\", "/")
            self.execute_command(f"mkdir -p {remote_dir}", sudo=True)
            code, out, err = self.execute_command(f"cp {temp_remote} {remote_path} && rm -f {temp_remote}", sudo=sudo)
            if code == 0:
                return True, "文件写入成功"
            return False, f"写入失败: {err}"
        except Exception as e:
            return False, f"写入文件异常: {str(e)}"

    def read_remote_text_file(self, remote_path: str) -> Tuple[bool, str]:
        """读取远程文本文件"""
        if not self.is_connected():
            return False, "未连接至机器人"
        code, out, err = self.execute_command(f"cat {remote_path}", sudo=False)
        if code == 0:
            return True, out
        return False, err


# 全局单例
ssh_manager = SSHManager()
