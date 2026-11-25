# @file: src/commands/system_ops_service.py
# @brief: Onboard system service for machine ID, license deployment, dance package hot-update, processes, and logs.
# @exports: SystemOpsService

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
import zipfile
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.config.robot_config_reader import RobotConfigReader
from src.config.ros_env_config import RosEnvConfig


ShellFn = Callable[[str, float], Tuple[int, str, str]]


def _default_shell(cmd: str, timeout_s: float) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_s, check=False)
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"系统命令执行超时 ({timeout_s:.1f}s)"
    except OSError as ex:
        return 127, "", f"系统命令调用失败: {ex}"


class SystemOpsService:
    """Handles authentic onboard deployment, license, dance update, process control, and log queries over HTTP."""

    def __init__(
        self,
        cfg: RosEnvConfig,
        config_reader: RobotConfigReader,
        shell_fn: Optional[ShellFn] = None,
    ) -> None:
        self.cfg = cfg
        self.reader = config_reader
        self._shell = shell_fn or _default_shell

    def run_precheck(self) -> Dict[str, Any]:
        rid = self.reader.read_robot_id()
        lic = self.reader.read_license_summary()
        reg = self.reader.read_dance_registry()
        mid = self.reader.read_machine_id_digest()
        ch341_exists = Path("/dev/ttyCH341USB0").exists()
        deploy_ok = self.cfg.deploy_root.exists()
        items = {
            "robot_id": {
                "name": "机器人唯一 ID", "status": "ok" if rid["configured"] else "warning",
                "version": rid["robot_id"], "msg": f"来源: {rid['source']}", "can_fix": False,
            },
            "license": {
                "name": "商业授权 License", "status": "ok" if lic["present"] else "warning",
                "version": f"{len(lic.get('dances', []))} 项动作" if lic["present"] else "未部署",
                "msg": lic.get("customer") or lic.get("reason", ""), "can_fix": False,
            },
            "dance_registry": {
                "name": "机载动作映射表", "status": "ok" if reg["available"] else "warning",
                "version": f"{reg['total_count']} 项", "msg": reg.get("source", ""), "can_fix": False,
            },
            "serial_ch341": {
                "name": "机载 LoRa 配网串口", "status": "ok" if ch341_exists else "warning",
                "version": "/dev/ttyCH341USB0" if ch341_exists else "未检测到",
                "msg": "仅用于无线 Wi-Fi 配网通道" if ch341_exists else "未挂载 ttyCH341USB0（不影响 Wi-Fi HTTP 控制）",
                "can_fix": not ch341_exists,
            },
            "deploy_root": {
                "name": "机载部署根目录", "status": "ok" if deploy_ok else "error",
                "version": str(self.cfg.deploy_root),
                "msg": "部署目录就绪" if deploy_ok else "未找到机载部署目录", "can_fix": False,
            },
        }
        return {
            "ok": True,
            "all_passed": all(v["status"] == "ok" for v in items.values()),
            "items": items,
            "robot_id": rid,
            "license": lic,
            "dance_registry_available": reg["available"],
            "dance_count": reg["total_count"],
            "machine_id": mid,
            "tty_ch341_present": ch341_exists,
            "deploy_root_exists": deploy_ok,
        }

    def configure_robot_id_and_autostart(self, robot_id: str, write_autostart: bool = True) -> Dict[str, Any]:
        clean = (robot_id or "").strip().upper()
        if not clean or clean == "ALL" or any(c in clean for c in "\r\n| "):
            return {"ok": False, "message": f"非法机器人 ID: '{robot_id}'（禁止为空或 ALL）"}
        self.cfg.robot_id_file.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.robot_id_file.write_text(f"{clean}\n", encoding="utf-8")
        autostart_path = Path("/docker_config/custom_startup.sh")
        autostart_written = False
        if write_autostart:
            try:
                autostart_path.parent.mkdir(parents=True, exist_ok=True)
                autostart_path.write_text("#!/bin/bash\n/home/ubuntu/vsis_mimic_deploy/run_bg.sh\n", encoding="utf-8")
                autostart_written = True
            except OSError:
                autostart_written = False
        return {
            "ok": True,
            "robot_id": clean,
            "robot_id_file": str(self.cfg.robot_id_file),
            "autostart_written": autostart_written,
            "message": f"已写入机器人 ID [{clean}] 至 {self.cfg.robot_id_file}",
        }

    def deploy_license(self, license_content: str | Dict[str, Any]) -> Dict[str, Any]:
        try:
            obj = json.loads(license_content) if isinstance(license_content, str) else dict(license_content)
        except Exception as ex:
            return {"ok": False, "message": f"License JSON 解析失败: {ex}"}
        if not isinstance(obj, dict) or not obj.get("machine_id"):
            return {"ok": False, "message": "License 缺少 machine_id 字段"}

        mid_info = self.reader.read_machine_id_digest()
        lic_mid = str(obj.get("machine_id", "")).strip()
        if mid_info["available"] and not lic_mid.startswith(mid_info["digest"]):
            return {
                "ok": False,
                "message": f"机器码不匹配: 实机前缀 {mid_info['digest']} != 授权 {lic_mid[:16]}",
            }
        self.cfg.license_file.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.license_file.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": True,
            "path": str(self.cfg.license_file),
            "summary": self.reader.read_license_summary(),
            "message": "License 授权已写入机载目录",
        }

    def register_dance_alias(self, alias: str, select_key: str, action_key: str, comment: str = "") -> Dict[str, Any]:
        clean_alias = (alias or "").strip().upper()
        k1, k2 = (select_key or "").strip().upper(), (action_key or "").strip().upper()
        if not clean_alias or not k1 or not k2:
            return {"ok": False, "message": "动作别名与按键映射 [select_key, action_key] 不能为空"}
        self.cfg.lora_yaml_file.parent.mkdir(parents=True, exist_ok=True)
        existing = self.cfg.lora_yaml_file.read_text(encoding="utf-8") if self.cfg.lora_yaml_file.exists() else "dance_map:\n"
        if "dance_map:" not in existing:
            existing = existing.rstrip() + "\ndance_map:\n"
        comment_suffix = f" # {comment.strip()}" if comment.strip() else ""
        new_line = f"  {clean_alias}: [{k1}, {k2}]{comment_suffix}\n"
        lines = [ln for ln in existing.splitlines(keepends=True) if not ln.strip().startswith(f"{clean_alias}:")]
        lines.append(new_line)
        self.cfg.lora_yaml_file.write_text("".join(lines), encoding="utf-8")
        return {
            "ok": True,
            "alias": clean_alias,
            "keys": [k1, k2],
            "registry": self.reader.read_dance_registry(),
            "message": f"已注册舞蹈别名 {clean_alias}: [{k1}, {k2}]",
        }

    def deploy_dance_zip_bytes(self, zip_bytes: bytes, dest_dir: Optional[Path] = None) -> Dict[str, Any]:
        target_dir = dest_dir or (self.cfg.deploy_root / "config_vsis")
        target_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_zip = self.cfg.cache_dir / f"dance_upload_{int(time.time())}.zip"
        tmp_zip.write_bytes(zip_bytes)
        extracted: List[str] = []
        try:
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                for member in zf.namelist():
                    if ".." in member or member.startswith("/"):
                        continue
                    zf.extract(member, target_dir)
                    extracted.append(member)
        except Exception as ex:
            return {"ok": False, "message": f"解压动作包失败: {ex}"}
        finally:
            if tmp_zip.exists():
                tmp_zip.unlink()
        return {
            "ok": True,
            "dest_dir": str(target_dir),
            "extracted_count": len(extracted),
            "extracted_files": extracted[:50],
            "message": f"成功解压 {len(extracted)} 个动作资源文件至 {target_dir}",
        }

    def get_process_status(self) -> Dict[str, Any]:
        targets = ("g1_ctrl_vsis", "lora_recv_group", "nav_gait_bridge", "nav_web_server.py", "roscore")
        status_map: Dict[str, bool] = {}
        rc, out, _ = self._shell("ps -ef", 3.0)
        for name in targets:
            status_map[name] = (rc == 0 and name in out)
        g1_on = status_map["g1_ctrl_vsis"]
        lora_on = status_map["lora_recv_group"]
        return {
            "ok": True,
            "processes": status_map,
            "g1_ctrl_running": g1_on,
            "lora_recv_running": lora_on,
            "all_running": g1_on and lora_on,
        }

    def get_docker_status(self) -> Dict[str, Any]:
        rc_c, out_c, _ = self._shell("docker ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}'", 4.0)
        containers: List[Dict[str, str]] = []
        if rc_c == 0 and out_c:
            for ln in out_c.splitlines():
                parts = ln.split("|")
                if len(parts) >= 3:
                    containers.append({"name": parts[0].strip(), "image": parts[1].strip(), "status": parts[2].strip()})
        rc_i, out_i, _ = self._shell("docker images --format '{{.Repository}}:{{.Tag}}|{{.ID}}|{{.Size}}'", 4.0)
        images: List[Dict[str, str]] = []
        if rc_i == 0 and out_i:
            for ln in out_i.splitlines():
                parts = ln.split("|")
                if len(parts) >= 3:
                    images.append({"name": parts[0].strip(), "id": parts[1].strip(), "size": parts[2].strip()})
        running = [c for c in containers if c["status"].lower().startswith("up")]
        rid = self.reader.read_robot_id()
        http_robot_id = str(rid.get("robot_id") or "").strip() if rid.get("configured") else ""
        return {
            "ok": rc_c == 0 or rc_i == 0, "containers": containers, "running_containers": running,
            "images": images, "is_container_running": bool(running), "running": bool(running),
            "container_exists": any(c["name"] == "vsis_g1" for c in containers),
            "autostart_configured": Path("/docker_config/custom_startup.sh").exists(),
            "robot_id": http_robot_id or "A",
        }

    def control_container(self, action: str, container_name: str = "vsis_g1") -> Dict[str, Any]:
        act = (action or "").strip().lower()
        name = (container_name or "vsis_g1").strip()
        if act not in ("start", "stop", "restart"):
            return {"ok": False, "message": f"不支持的容器操作: {action}"}
        if any(c in name for c in " ;|&$`'\""):
            return {"ok": False, "message": f"非法容器名: {container_name}"}
        rc, out, err_s = self._shell(f"docker {act} {name}", 15.0)
        return {
            "ok": rc == 0, "action": act, "container": name,
            "stdout": out, "stderr": err_s,
            "message": f"容器 {name} 执行 {act} 成功" if rc == 0 else (err_s or f"容器 {act} 失败"),
        }

    def control_processes(self, action: str) -> Dict[str, Any]:
        act = (action or "").strip().lower()
        if act == "start":
            run_bg = self.cfg.deploy_root / "run_bg.sh"
            if not run_bg.exists():
                return {"ok": False, "message": f"启动脚本不存在: {run_bg}"}
            rc, out, err_s = self._shell(f"bash {run_bg}", 10.0)
            return {"ok": rc == 0, "action": "start", "stdout": out, "stderr": err_s, "message": "已执行 run_bg.sh" if rc == 0 else err_s}
        if act == "stop":
            rc, out, err_s = self._shell("pkill -f g1_ctrl_vsis ; pkill -f lora_recv_group", 5.0)
            return {"ok": True, "action": "stop", "returncode": rc, "stdout": out, "stderr": err_s, "message": "已发送进程停止信号"}
        if act == "restart":
            self.control_processes("stop")
            return self.control_processes("start")
        return {"ok": False, "message": f"不支持的进程操作: {action}"}

    def fetch_logs(self, log_type: str = "sec_run", lines: int = 200, container: str = "vsis_g1") -> Dict[str, Any]:
        n = max(10, min(2000, int(lines)))
        lt = (log_type or "sec_run").strip().lower()
        if lt == "container":
            cname = (container or "vsis_g1").strip()
            rc, out, err_s = self._shell(f"docker logs --tail {n} {cname} 2>&1", 6.0)
            text = out or err_s
            return {"ok": rc == 0, "log_type": lt, "target_container": cname, "lines": text.splitlines(), "raw_text": text, "message": "" if rc == 0 else err_s}
        if lt == "dmesg":
            rc, out, err_s = self._shell(f"dmesg -T 2>/dev/null | tail -n {n}", 4.0)
            text = out or err_s
            return {"ok": rc == 0, "log_type": lt, "lines": text.splitlines(), "raw_text": text, "message": "" if rc == 0 else err_s}
        if lt in ("ros_nav", "navctl"):
            sections = []
            for label, cmd in (
                ("navctl status", f"sudo -n {self.cfg.navctl_bin} status 2>&1"),
                ("rosnode list", "rosnode list 2>&1"),
                ("rostopic list", "rostopic list 2>&1"),
                ("local_nav_status", "rostopic echo -n 1 /local_nav_status 2>&1"),
            ):
                _rc, so, se = self._shell(cmd, 3.0)
                sections.append(f"=== [{label}] ===\n{so or se or '(无输出)'}")
            text = "\n\n".join(sections)
            return {"ok": True, "log_type": lt, "lines": text.splitlines()[-n:], "raw_text": text}
        log_map = {
            "sec_run": self.cfg.deploy_root / "log" / "sec_run.log",
            "g1_ctrl": self.cfg.deploy_root / "log" / "sec_run.log",
            "lora_recv": self.cfg.deploy_root / "log" / "lora_recv.log",
        }
        path = log_map.get(lt, log_map["sec_run"])
        if not path.exists():
            return {"ok": False, "log_type": lt, "path": str(path), "lines": [], "raw_text": "", "message": f"日志文件不存在: {path}"}
        all_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:]
        return {"ok": True, "log_type": lt, "path": str(path), "lines": all_lines, "raw_text": "\n".join(all_lines)}

    def clock_status(self) -> Dict[str, Any]:
        now_ms = int(time.time() * 1000)
        return {"ok": True, "utc_ms": now_ms, "monotonic_s": round(time.monotonic(), 3)}
