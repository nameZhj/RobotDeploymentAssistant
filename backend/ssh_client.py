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
        self.cancel_upload_flag = False

        # 进度追踪
        self.upload_progress = {
            "is_uploading": False,
            "filename": "",
            "transferred_bytes": 0,
            "total_bytes": 0,
            "percent": 0.0,
            "speed_mbps": 0.0,
            "eta_seconds": 0,
            "status": "idle",  # idle, uploading, completed, error, canceled
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

            last_err = ""
            for attempt in range(2):
                try:
                    client = paramiko.SSHClient()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    client.connect(
                        hostname=self.host,
                        port=self.port,
                        username=self.username,
                        password=self.password,
                        timeout=max(timeout, 4.0),
                        banner_timeout=15.0,
                        auth_timeout=15.0,
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
                    last_err = str(e)
                    time.sleep(0.3)

            self._is_connected = False
            return False, f"连接失败: {last_err}"

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
        try:
            start = time.perf_counter()
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            res = s.connect_ex((self.host, self.port))
            s.close()
            if res == 0:
                return round((time.perf_counter() - start) * 1000, 1)
        except Exception:
            pass
        return 1.0

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
            if sudo:
                escaped_command = command.replace("'", "'\\''")
                cmd = f"echo '{self.password}' | sudo -S -p '' bash -c '{escaped_command}'"

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
            if sudo:
                escaped_command = command.replace("'", "'\\''")
                cmd = f"echo '{self.password}' | sudo -S -p '' bash -c '{escaped_command}'"

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
        通过独立 SFTP 会话上传本地文件至机器人，彻底避免与主命令/心跳通道竞争导致 Socket 10054
        """
        if not os.path.exists(local_path):
            err_msg = f"本地文件不存在: {local_path}"
            self.upload_progress["status"] = "error"
            self.upload_progress["error_msg"] = err_msg
            self.upload_progress["is_uploading"] = False
            return False, err_msg

        total_bytes = os.path.getsize(local_path)
        filename = os.path.basename(local_path)

        if not self.is_connected():
            conn_ok, msg = self.connect()
            if not conn_ok:
                err_msg = f"连接未就绪: {msg}"
                self.upload_progress["status"] = "error"
                self.upload_progress["error_msg"] = err_msg
                self.upload_progress["is_uploading"] = False
                return False, err_msg

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
            if dt >= 0.25 or transferred >= total:
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

        upload_client = None
        sftp = None
        try:
            # 建立独立的 SFTP 上传专用连接，彻底与主界面的常规命令/状态心跳轮询解耦，杜绝 Socket 10054
            upload_client = paramiko.SSHClient()
            upload_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            upload_client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=15.0,
                banner_timeout=15.0,
                auth_timeout=15.0,
                look_for_keys=False,
                allow_agent=False
            )
            transport = upload_client.get_transport()
            if transport:
                transport.set_keepalive(15)

            # 确保远端父目录存在并授予完全写入权限（避免因用户权限问题报 Errno 13 Permission denied）
            remote_dir = os.path.dirname(remote_path).replace("\\", "/")
            if remote_dir and remote_dir != "/":
                self.execute_command(f"mkdir -p {remote_dir} && chmod a+rwx {remote_dir}", sudo=True)

            sftp = upload_client.open_sftp()

            # 远端存储空间前置检查 (预留 200MB 安全裕量)
            code_df, df_out, _ = self.execute_command(f"df -k {remote_dir or '/tmp'} | tail -n 1")
            if code_df == 0 and df_out.strip():
                parts = df_out.strip().split()
                if len(parts) >= 4:
                    try:
                        avail_kb = int(parts[3])
                        avail_bytes = avail_kb * 1024
                        if avail_bytes < total_bytes + 200 * 1024 * 1024:
                            err_space = f"机器人远端存储空间不足 (可用: {round(avail_bytes/(1024*1024*1024), 2)} GB, 需: {round(total_bytes/(1024*1024*1024), 2)} GB)"
                            logger.error(err_space)
                            self.upload_progress["status"] = "error"
                            self.upload_progress["error_msg"] = err_space
                            self.upload_progress["is_uploading"] = False
                            return False, err_space
                    except Exception:
                        pass

            # 检查如果远端已存在完全一致大小的文件，可直接跳过重复传输
            try:
                rstat = sftp.stat(remote_path)
                if rstat.st_size == total_bytes:
                    logger.info(f"远端已存在完全同名且大小一致的文件 ({round(total_bytes/(1024*1024), 2)} MB)，跳过重复传输")
                    self.upload_progress.update({
                        "transferred_bytes": total_bytes,
                        "percent": 100.0,
                        "speed_mbps": 0.0,
                        "eta_seconds": 0,
                        "status": "completed",
                        "is_uploading": False,
                    })
                    if progress_callback:
                        progress_callback(self.upload_progress)
                    return True, f"文件已在远端存在且大小完整: {remote_path}"
            except Exception:
                pass

            logger.info(f"开始独立 SFTP 管道高速上传: {local_path} -> {remote_path} ({round(total_bytes/(1024*1024), 2)} MB)")

            # 使用 512KB 分块 + 管道化流式写入
            chunk_size = 512 * 1024
            transferred = 0
            with open(local_path, "rb") as fl:
                with sftp.file(remote_path, "wb") as fr:
                    try:
                        fr.set_pipelined(True)
                    except Exception:
                        pass
                    while True:
                        if self.cancel_upload_flag:
                            logger.info(f"用户已取消 SFTP 上传任务: {remote_path}")
                            self.upload_progress.update({
                                "status": "canceled",
                                "error_msg": "上传已由用户手动取消",
                                "is_uploading": False
                            })
                            # 异步清理残缺文件
                            threading.Thread(target=lambda: self.execute_command(f"rm -f {remote_path}", sudo=True), daemon=True).start()
                            return False, "上传已由用户手动取消"

                        chunk = fl.read(chunk_size)
                        if not chunk:
                            break
                        fr.write(chunk)
                        transferred += len(chunk)
                        _sftp_callback(transferred, total_bytes)

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
        finally:
            if sftp:
                try:
                    sftp.close()
                except Exception:
                    pass
            if upload_client:
                try:
                    upload_client.close()
                except Exception:
                    pass

    def cancel_upload(self) -> Dict[str, Any]:
        """取消当前的 SFTP 上传"""
        self.cancel_upload_flag = True
        self.upload_progress["is_uploading"] = False
        self.upload_progress["status"] = "canceled"
        self.upload_progress["error_msg"] = "上传已取消"
        logger.info("已触发 SFTP 上传任务取消指令")
        return {"success": True, "msg": "已触发取消上传"}

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
