"""
@file: backend/lora_wifi_tunnel.py
@brief: Dedicated LoRa wireless provisioning tunnel implementing docs/g1_wifi_setup(1).py ProxyCommand & LoRa serial Wi-Fi frames.
@exports: LORA_SSH_ALGORITHMS, LoraWifiTunnel, lora_wifi_tunnel
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

LORA_SSH_ALGORITHMS = (
    "KexAlgorithms=curve25519-sha256",
    "HostKeyAlgorithms=ssh-ed25519,ecdsa-sha2-nistp256",
    "Ciphers=chacha20-poly1305@openssh.com,aes128-ctr",
    "MACs=hmac-sha2-256-etm@openssh.com",
)


class LoraWifiTunnel:
    """Executes G1 wireless Wi-Fi configuration exclusively over LoRa (Serial Frame or LoRa SSH Proxy)."""

    def __init__(
        self,
        serial_port: str = "COM13",
        baudrate: int = 9600,
        target_id: str = "A",
        target_ip: str = "192.168.123.164",
        target_port: int = 22,
        ssh_user: str = "unitree",
        rto: float = 1.8,
        retries: int = 5,
        fast_link: bool = True,
    ) -> None:
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.target_id = target_id
        self.target_ip = target_ip
        self.target_port = target_port
        self.ssh_user = ssh_user
        self.rto = rto
        self.retries = retries
        self.fast_link = fast_link
        self.tx_history: List[str] = []

    def configure(
        self,
        serial_port: Optional[str] = None,
        baudrate: Optional[int] = None,
        target_id: Optional[str] = None,
        target_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        if serial_port:
            self.serial_port = serial_port.strip()
        if baudrate:
            self.baudrate = int(baudrate)
        if target_id:
            self.target_id = target_id.strip().upper() or "A"
        if target_ip:
            self.target_ip = target_ip.strip()
        return {
            "ok": True,
            "transport": "LoRa",
            "serial_port": self.serial_port,
            "baudrate": self.baudrate,
            "target_id": self.target_id,
            "target_ip": self.target_ip,
        }

    def build_proxy_command(self, proxy_script_path: Optional[Path] = None) -> str:
        """Build OpenSSH ProxyCommand string matching docs/g1_wifi_setup(1).py."""
        script = proxy_script_path or (Path(__file__).resolve().parents[1] / "docs" / "lora_ssh_proxy.py")
        argv = [
            sys.executable or "python",
            str(script),
            "--serial-port", self.serial_port,
            "--baud", str(self.baudrate),
            "--target-ip", self.target_ip,
            "--target-port", str(self.target_port),
            "--rto", str(self.rto),
            "--retries", str(self.retries),
            "--fast-link" if self.fast_link else "--legacy-link",
        ]
        return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)

    def build_lora_ssh_argv(self, remote_command: str, allocate_tty: bool = False) -> List[str]:
        """Build compact-KEX OpenSSH command line over LoRa ProxyCommand."""
        cmd = [
            "ssh",
            "-o", "TCPKeepAlive=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=6",
            "-o", f"ProxyCommand={self.build_proxy_command()}",
            "-o", "Compression=yes",
            "-p", str(self.target_port),
        ]
        for alg in LORA_SSH_ALGORITHMS:
            cmd.extend(["-o", alg])
        cmd.append("-tt" if allocate_tty else "-T")
        cmd.extend(["--", f"{self.ssh_user}@{self.target_ip}", remote_command])
        return cmd

    def emit_lora_wifi_frame(self, command: str, *params: str, serial_mgr: Optional[Any] = None) -> Dict[str, Any]:
        """Transmit `TARGET|WIFI_*` configuration frame over LoRa serial transmitter."""
        sm = serial_mgr
        if sm is None:
            try:
                from backend.serial_manager import serial_manager
                sm = serial_manager
            except Exception:
                sm = None
        clean_params = [str(p).strip() for p in params if str(p).strip()]
        cmd_body = f"{command.strip().upper()}" + (f",{','.join(clean_params)}" if clean_params else "")
        frame_str = f"{self.target_id}|{cmd_body}"
        self.tx_history.append(frame_str)
        if len(self.tx_history) > 100:
            self.tx_history = self.tx_history[-50:]

        if sm is not None and hasattr(sm, "is_connected"):
            is_conn = sm.is_connected() if callable(sm.is_connected) else bool(sm.is_connected)
            if is_conn and hasattr(sm, "send_command"):
                res = sm.send_command(self.target_id, cmd_body)
                return {"sent_over_serial": bool(res.get("success")), "frame": frame_str, "serial_result": res}
        return {"sent_over_serial": False, "frame": frame_str}

    def emit_and_wait_lora_ack(
        self, command: str, *params: str, serial_mgr: Optional[Any] = None, timeout_s: float = 6.0
    ) -> Dict[str, Any]:
        """Transmit `TARGET|WIFI_*` over LoRa serial and await authentic `WIFI_ACK|<id>|<json>` reply."""
        t0 = time.time()
        tx = self.emit_lora_wifi_frame(command, *params, serial_mgr=serial_mgr)
        if not tx.get("sent_over_serial"):
            return {"ok": False, "ack_received": False, **tx}
        sm = serial_mgr
        if sm is None:
            try:
                from backend.serial_manager import serial_manager
                sm = serial_manager
            except Exception:
                sm = None
        if sm is None or not hasattr(sm, "get_recent_messages"):
            return {"ok": False, "ack_received": False, **tx}

        deadline = time.monotonic() + max(0.5, timeout_s)
        want_cmd = command.strip().upper()
        while time.monotonic() < deadline:
            for item in sm.get_recent_messages(since_ts=t0 - 0.1):
                txt = str(item.get("text", "") if isinstance(item, dict) else item).strip()
                if "WIFI_ACK|" not in txt:
                    continue
                after = txt.split("WIFI_ACK|", 1)[1]
                parts = after.split("|", 1)
                if len(parts) == 2:
                    try:
                        parsed = json.loads(parts[1])
                        if str(parsed.get("cmd", "")).upper() == want_cmd:
                            return {"ok": bool(parsed.get("ok")), "ack_received": True, "ack_data": parsed, **tx}
                    except Exception:
                        pass
            time.sleep(0.08)
        return {"ok": False, "ack_received": False, "message": f"LoRa 串口已发送 {tx['frame']}，等待下位机 WIFI_ACK 超时", **tx}


lora_wifi_tunnel = LoraWifiTunnel()
