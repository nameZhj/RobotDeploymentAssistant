# @file: src/config/robot_config_reader.py
# @brief: Reads authentic onboard robot_id, lora_recv_group.yaml dance_map, license, and hardware machine ID.
# @exports: RobotConfigReader

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from src.config.ros_env_config import RosEnvConfig


def _parse_dance_map_yaml(raw_text: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse dance_map and motion axis limits from lora_recv_group.yaml without external YAML deps."""
    motion: Dict[str, float] = {"forward_axis": 0.60, "lateral_axis": 0.50, "turn_axis": 0.70}
    for key in ("forward_axis", "lateral_axis", "turn_axis"):
        m = re.search(rf"^\s*{key}\s*:\s*([0-9.]+)", raw_text, re.MULTILINE)
        if m:
            try:
                motion[key] = float(m.group(1))
            except ValueError:
                pass

    pattern = re.compile(r"^\s*([A-Za-z0-9_]+)\s*:\s*\[([^\]]+)\](?:\s*#\s*(.*))?$")
    groups_map: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    cur_gid: Optional[str] = None
    seen = set()

    for line in raw_text.splitlines():
        s = line.strip()
        if not s or s.startswith("dance_map:"):
            continue
        if s.startswith("#") and ("group" in s.lower() or "组" in s):
            gm = re.search(r"Group\s*(\d+)", s, re.IGNORECASE)
            gid = f"G{gm.group(1)}" if gm else f"G{len(order) + 1}"
            cur_gid = gid
            if gid not in groups_map:
                groups_map[gid] = {"group_id": gid, "title": f"{gid} 动作组", "items": []}
                order.append(gid)
            continue
        m = pattern.match(line)
        if not m:
            continue
        alias = m.group(1).strip()
        if alias in seen:
            continue
        seen.add(alias)
        keys = [k.strip() for k in m.group(2).split(",") if k.strip()]
        comment = (m.group(3) or "").strip()
        name = comment.split(" RL_")[0].strip() if comment else alias
        gid = cur_gid or (alias.split("_", 1)[0] if alias.startswith(("G1_", "G2_", "G3_")) else "G1")
        if gid not in groups_map:
            groups_map[gid] = {"group_id": gid, "title": f"{gid} 动作组", "items": []}
            order.append(gid)
        groups_map[gid]["items"].append({
            "alias": alias,
            "name": name or alias,
            "keys": keys,
            "select_key": keys[0] if len(keys) > 0 else "",
            "action_key": keys[1] if len(keys) > 1 else "",
            "comment": comment,
            "cmd": f"DANCE,{alias}",
        })
    return [groups_map[g] for g in order if groups_map[g]["items"]], motion


class RobotConfigReader:
    """Reads real onboard files and hardware identity; returns honest unavailable metadata when absent."""

    def __init__(self, cfg: Optional[RosEnvConfig] = None) -> None:
        self.cfg = cfg or RosEnvConfig()

    def read_robot_id(self) -> Dict[str, Any]:
        env_id = os.environ.get("ROBOT_ID", "").strip().upper()
        if self.cfg.robot_id_file.exists():
            val = self.cfg.robot_id_file.read_text(encoding="utf-8", errors="ignore").strip().upper()
            if val and val != "ALL":
                return {"robot_id": val, "source": str(self.cfg.robot_id_file), "configured": True}
        if env_id and env_id != "ALL":
            return {"robot_id": env_id, "source": "ENV:ROBOT_ID", "configured": True}
        return {"robot_id": "UNCONFIGURED", "source": str(self.cfg.robot_id_file), "configured": False}

    def read_dance_registry(self) -> Dict[str, Any]:
        if not self.cfg.lora_yaml_file.exists():
            return {
                "available": False,
                "source": str(self.cfg.lora_yaml_file),
                "groups": [],
                "alias_map": {},
                "motion_limits": {"forward_axis": 0.60, "lateral_axis": 0.50, "turn_axis": 0.70},
                "total_count": 0,
                "raw": "",
                "reason": f"机载动作配置文件不存在: {self.cfg.lora_yaml_file}",
            }
        raw = self.cfg.lora_yaml_file.read_text(encoding="utf-8", errors="ignore")
        groups, motion = _parse_dance_map_yaml(raw)
        alias_map = {it["alias"]: it for g in groups for it in g.get("items", [])}
        return {
            "available": True,
            "source": str(self.cfg.lora_yaml_file),
            "groups": groups,
            "alias_map": alias_map,
            "motion_limits": motion,
            "total_count": len(alias_map),
            "raw": raw,
        }

    def read_license_summary(self) -> Dict[str, Any]:
        if not self.cfg.license_file.exists():
            return {"present": False, "path": str(self.cfg.license_file), "reason": "license.json 不存在"}
        try:
            data = json.loads(self.cfg.license_file.read_text(encoding="utf-8"))
            return {
                "present": True,
                "path": str(self.cfg.license_file),
                "customer": data.get("customer", ""),
                "machine_id_prefix": str(data.get("machine_id", ""))[:12],
                "dances": list(data.get("dances", [])) if isinstance(data.get("dances"), list) else [],
            }
        except Exception as ex:
            return {"present": False, "path": str(self.cfg.license_file), "reason": f"解析失败: {ex}"}

    def read_machine_id_digest(self) -> Dict[str, Any]:
        if not self.cfg.g1_ctrl_bin.exists():
            return {"available": False, "digest": "", "reason": f"未找到 {self.cfg.g1_ctrl_bin}"}
        try:
            proc = subprocess.run(
                [str(self.cfg.g1_ctrl_bin), "--print-machine-id"],
                capture_output=True, text=True, timeout=5.0, check=False,
            )
            val = proc.stdout.strip()
            if proc.returncode == 0 and val:
                return {"available": True, "digest": val[:16], "length": len(val)}
            return {"available": False, "digest": "", "reason": proc.stderr.strip() or f"rc={proc.returncode}"}
        except Exception as ex:
            return {"available": False, "digest": "", "reason": str(ex)}

    def read_network_summary(self) -> Dict[str, Any]:
        hostname = socket.gethostname()
        addrs: List[str] = []
        try:
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                if ip not in addrs:
                    addrs.append(ip)
        except Exception:
            pass
        return {"hostname": hostname, "ipv4_addresses": addrs}
