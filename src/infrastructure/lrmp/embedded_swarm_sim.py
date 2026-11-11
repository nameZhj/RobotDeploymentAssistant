"""
内置多机集群模拟器 (Embedded Swarm Simulator)
在无硬件环境下按 LRMP V1.0-R3 规范模拟网关与机器人节点的握手、建链、PREP-READY 状态机与遥测
"""
import time
from typing import Any, Dict, List, Optional, Tuple


class EmbeddedSwarmSim:
    """本地虚拟机器人集群仿真应答器"""

    def __init__(self) -> None:
        self.enabled = True
        self.gateways = {"GW_8C2F": {"bound_alias": "A", "sn": "G1_GW_8C2F"}}
        self.robots: Dict[str, Dict[str, Any]] = {
            "A": {"id": 1, "model": "A2-W", "state": "STAND", "battery": 88, "temp": 36.2, "x": -2.0, "y": 0.0, "step": 0},
            "B": {"id": 2, "model": "A2-W", "state": "STAND", "battery": 92, "temp": 35.5, "x": 2.0, "y": 0.0, "step": 0},
        }
        self.active_plan_id: Optional[str] = None
        self.active_run_id: Optional[str] = None

    def handle_command(self, raw_cmd: str) -> List[Tuple[str, str]]:
        """
        处理 LRMP 指令帧，返回响应列表 [(SRC_ID, PAYLOAD), ...]
        格式：TARGET|CMD,arg1,arg2...
        """
        if not self.enabled or not raw_cmd:
            return []
        parts = raw_cmd.strip().split("|", 1)
        if len(parts) < 2:
            return [("SIM", "ERR,INVALID_FORMAT")]

        target, cmd_body = parts[0].strip(), parts[1].strip()
        cmd_tokens = [t.strip() for t in cmd_body.split(",")]
        action = cmd_tokens[0].upper()
        responses: List[Tuple[str, str]] = []

        if target == "ALL" and action == "DISCOVER":
            responses.append(("GW_8C2F", "ANNOUNCE,GW_8C2F,G1_GW_8C2F,AVAILABLE"))
            for alias, r in self.robots.items():
                responses.append((alias, f"ANNOUNCE,{alias},ID:{r['id']},STATE:{r['state']},BAT:{r['battery']}"))
            return responses

        if target in self.gateways:
            if action == "BIND":
                alias = cmd_tokens[1] if len(cmd_tokens) > 1 else "A"
                self.gateways[target]["bound_alias"] = alias
                responses.append((target, f"BIND_OK,{target},{alias}"))
            else:
                responses.append((target, f"ACK,{action}"))
            return responses

        # 机器人节点单机处理
        robot = self.robots.get(target)
        src_id = target
        if not robot:
            return [(src_id, f"ERR,UNKNOWN_TARGET_{target}")]

        if action == "SETUP":
            job_id = cmd_tokens[1] if len(cmd_tokens) > 1 else "601"
            robot["state"] = "READY"
            responses.append((src_id, f"ACCEPTED,SETUP,{job_id}"))
            responses.append((src_id, f"EVT,SETUP_SUCCESS,JOB:{job_id}"))

        elif action == "PREP":
            plan_id = cmd_tokens[1] if len(cmd_tokens) > 1 else "plan_default"
            run_id = cmd_tokens[2] if len(cmd_tokens) > 2 else "run_001"
            self.active_plan_id, self.active_run_id = plan_id, run_id
            robot["state"] = "PREP"
            responses.append((src_id, f"ACCEPTED,PREP,{plan_id},{run_id}"))
            robot["state"] = "READY"
            responses.append((src_id, f"EVT,READY,{plan_id},{run_id}"))

        elif action == "STATUS" and len(cmd_tokens) > 1 and cmd_tokens[1].upper() == "CLOCK":
            now_ms = int(time.time() * 1000)
            responses.append((src_id, f"CLOCK,SYNCED,{now_ms},DRIFT_MS:0"))

        elif action == "PLAY":
            run_id = cmd_tokens[1] if len(cmd_tokens) > 1 else "run_001"
            t0_ms = cmd_tokens[2] if len(cmd_tokens) > 2 else "0"
            robot["state"] = "PLAYING"
            responses.append((src_id, f"ACCEPTED,PLAY,{run_id},{t0_ms}"))

        elif action == "BARRIER":
            run_id = cmd_tokens[1] if len(cmd_tokens) > 1 else "run_001"
            barrier_id = cmd_tokens[2] if len(cmd_tokens) > 2 else "B1"
            responses.append((src_id, f"EVT,BARRIER_RELEASED,{run_id},{barrier_id}"))

        elif action == "STOP":
            robot["state"] = "STAND"
            responses.append((src_id, "ACK,STOPPED,EMERGENCY_BRAKE_LOCKED"))

        elif action in ("STAND", "GAIT", "PASSIVE", "RELEASE"):
            robot["state"] = action
            responses.append((src_id, f"ACK,{action},OK"))

        elif action == "MOVE":
            dur = float(cmd_tokens[4]) if len(cmd_tokens) > 4 else 1.0
            robot["state"] = "MOVING"
            responses.append((src_id, f"ACCEPTED,MOVE,DUR:{dur}"))

        elif action == "DANCE":
            dance_name = cmd_tokens[1] if len(cmd_tokens) > 1 else "POPPING1"
            robot["state"] = "DANCING"
            responses.append((src_id, f"ACCEPTED,DANCE,{dance_name}"))

        else:
            responses.append((src_id, f"ACK,{action}"))

        return responses

    def get_telemetry(self, alias: str) -> Dict[str, Any]:
        """获取机器人的遥测物理数据快照"""
        r = self.robots.get(alias, {})
        return {
            "alias": alias, "id": r.get("id", 1), "model": r.get("model", "A2-W"),
            "state": r.get("state", "STAND"), "battery": r.get("battery", 90),
            "temp": r.get("temp", 36.0), "x": r.get("x", 0.0), "y": r.get("y", 0.0)
        }

