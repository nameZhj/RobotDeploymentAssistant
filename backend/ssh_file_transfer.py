import os
import socket
import threading
import time
import logging
from typing import Any, Callable, Dict, Optional, Tuple
import paramiko

logger = logging.getLogger("SSHFileTransfer")


class SSHFileTransfer:
    """管理独立 SFTP 通道与断点传输、进度追踪"""

    def __init__(self, manager):
        self.mgr = manager

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Tuple[bool, str]:
        self.mgr.cancel_upload_flag = False
        if not os.path.exists(local_path):
            err_msg = f"本地文件不存在: {local_path}"
            self.mgr.upload_progress.update({"status": "error", "error_msg": err_msg, "is_uploading": False})
            return False, err_msg

        total_bytes = os.path.getsize(local_path)
        filename = os.path.basename(local_path)

        if not self.mgr.is_connected():
            conn_ok, msg = self.mgr.connect()
            if not conn_ok:
                err_msg = f"连接未就绪: {msg}"
                self.mgr.upload_progress.update({"status": "error", "error_msg": err_msg, "is_uploading": False})
                return False, err_msg

        start_time = time.time()
        last_time = start_time
        last_bytes = 0

        self.mgr.upload_progress.update({
            "is_uploading": True, "filename": filename, "transferred_bytes": 0,
            "total_bytes": total_bytes, "percent": 0.0, "speed_mbps": 0.0,
            "eta_seconds": 0, "status": "uploading", "error_msg": "",
        })

        def _sftp_callback(transferred: int, total: int):
            nonlocal last_time, last_bytes
            now = time.time()
            dt = now - last_time
            if dt >= 0.25 or transferred >= total:
                dbytes = transferred - last_bytes
                speed = (dbytes / (1024 * 1024)) / dt if dt > 0 else 0.0
                percent = round((transferred / total) * 100.0, 1) if total > 0 else 0.0
                remaining = total - transferred
                eta = int(remaining / (speed * 1024 * 1024)) if speed > 0 else 0
                self.mgr.upload_progress.update({
                    "is_uploading": True, "filename": filename, "transferred_bytes": transferred,
                    "total_bytes": total, "percent": percent, "speed_mbps": round(speed, 2),
                    "eta_seconds": eta, "status": "uploading", "error_msg": "",
                })
                last_time = now
                last_bytes = transferred
                if progress_callback:
                    progress_callback(self.mgr.upload_progress)

        upload_client = None
        sftp = None
        try:
            remote_dir = os.path.dirname(remote_path).replace("\\", "/")
            if remote_dir and remote_dir != "/":
                self.mgr.execute_command(f"mkdir -p '{remote_dir}' && chmod 777 '{remote_dir}'", sudo=True)

            upload_client = paramiko.SSHClient()
            upload_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            upload_client.connect(
                hostname=self.mgr.host, port=self.mgr.port, username=self.mgr.username,
                password=self.mgr.password, timeout=25.0, banner_timeout=25.0, auth_timeout=25.0,
                look_for_keys=False, allow_agent=False,
            )
            up_transport = upload_client.get_transport()
            if up_transport:
                up_transport.set_keepalive(15)
                try:
                    up_transport.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    up_transport.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2 * 1024 * 1024)
                    up_transport.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
                except Exception:
                    pass
            sftp = upload_client.open_sftp()

            try:
                rstat = sftp.stat(remote_path)
                if rstat.st_size == total_bytes:
                    self.mgr.upload_progress.update({
                        "transferred_bytes": total_bytes, "percent": 100.0, "speed_mbps": 0.0,
                        "eta_seconds": 0, "status": "completed", "is_uploading": False,
                    })
                    return True, f"文件已在远端存在且大小完整: {remote_path}"
            except Exception:
                pass

            chunk_size = 32 * 1024
            max_in_flight = 64
            transferred = 0
            with open(local_path, "rb") as fl:
                with sftp.file(remote_path, "wb") as fr:
                    fr.set_pipelined(True)
                    while True:
                        if self.mgr.cancel_upload_flag:
                            self.mgr.upload_progress.update({"status": "canceled", "error_msg": "上传已取消", "is_uploading": False})
                            return False, "上传已由用户手动取消"
                        chunk = fl.read(chunk_size)
                        if not chunk:
                            break
                        fr.write(chunk)
                        transferred += len(chunk)
                        while len(fr._reqs) > max_in_flight:
                            req = fr._reqs.popleft()
                            sftp._read_response(req)
                        _sftp_callback(transferred, total_bytes)

            self.mgr.upload_progress.update({"percent": 100.0, "status": "completed", "is_uploading": False})
            return True, f"上传成功: {remote_path}"
        except Exception as e:
            logger.error(f"SFTP upload exception: {e}")
            self.mgr.upload_progress.update({"status": "error", "error_msg": str(e), "is_uploading": False})
            return False, str(e)
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

