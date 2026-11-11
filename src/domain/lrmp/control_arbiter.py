"""
@file: src/domain/lrmp/control_arbiter.py
@brief: FREE/MANUAL/CHOREO 三态控制权互斥仲裁器与任务租约调度中枢
@exports: ControlArbiter, PlanIdCompiler, control_arbiter
"""
import hashlib
import json
import time
from typing import Any, Dict, Optional, Tuple


class ControlArbiter:
    """机器人控制权三态状态机：维护 FREE、MANUAL、CHOREO 互斥与租约"""

    MANUAL_CMDS = {
        "STAND", "GAIT", "PASSIVE", "FORWARD", "BACK", "BACKWARD",
        "MOVE_LEFT", "MOVE_RIGHT", "TURN_LEFT", "TURN_RIGHT",
        "MOVE", "DANCE", "BUTTON", "MASK"
    }

    def __init__(self, default_ttl_s: float = 5.0) -> None:
        self.default_ttl = default_ttl_s
        self._states: Dict[str, str] = {}
        self._leases: Dict[str, Tuple[str, str, float]] = {}  # robot_id -> (requester, lease_id, expire_at)
        self._lease_seq = 1000

    def _next_lease_id(self) -> str:
        self._lease_seq += 1
        return f"LEASE_{self._lease_seq}"

    def get_state(self, robot_id: str) -> str:
        self._check_expiry(robot_id)
        return self._states.get(robot_id, "FREE")

    def get_lease_id(self, robot_id: str) -> Optional[str]:
        self._check_expiry(robot_id)
        lease_info = self._leases.get(robot_id)
        return lease_info[1] if lease_info else None

    def _check_expiry(self, robot_id: str) -> None:
        if robot_id in self._leases:
            _, _, expire_at = self._leases[robot_id]
            if time.time() > expire_at:
                self._states[robot_id] = "FREE"
                self._leases.pop(robot_id, None)

    def handle_command(
        self,
        robot_id: str,
        command: str,
        requester: str = "CTRL"
    ) -> Tuple[bool, str, str]:
        """根据命令语义智能判定状态流转、自动提权与互斥拦截"""
        self._check_expiry(robot_id)
        cmd = command.strip().upper()
        curr = self.get_state(robot_id)

        if cmd in self.MANUAL_CMDS:
            if curr == "FREE":
                lease_id = self._next_lease_id()
                self._states[robot_id] = "MANUAL"
                self._leases[robot_id] = (requester, lease_id, time.time() + self.default_ttl)
                return True, "MANUAL", f"机器人 {robot_id} 自动获取 MANUAL 控制权 (租约 {lease_id})"
            if curr == "MANUAL":
                lease_id = self.get_lease_id(robot_id) or self._next_lease_id()
                self._leases[robot_id] = (requester, lease_id, time.time() + self.default_ttl)
                return True, "MANUAL", f"机器人 {robot_id} MANUAL 控制权续期成功"
            return False, curr, f"冲突: 机器人 {robot_id} 处于 {curr} 状态，拒绝执行 MANUAL 指令 {cmd}"

        if cmd == "PREP":
            if curr in ("FREE", "CHOREO"):
                lease_id = self._next_lease_id()
                self._states[robot_id] = "CHOREO"
                self._leases[robot_id] = (requester, lease_id, time.time() + self.default_ttl * 60)
                return True, "CHOREO", f"机器人 {robot_id} 成功进入 CHOREO 任务态 (租约 {lease_id})"
            return False, curr, f"冲突: 机器人 {robot_id} 处于 {curr} 状态，请先 RELEASE 再执行 PREP"

        if cmd == "RELEASE":
            return self.release_authority(robot_id, requester)

        if cmd == "STOP":
            new_st, msg = self.handle_stop(robot_id)
            return True, new_st, msg

        return True, curr, f"指令 {cmd} 放行 (当前状态 {curr})"

    def release_authority(self, robot_id: str, requester: str = "CTRL") -> Tuple[bool, str, str]:
        """释放控制权：MANUAL 释放转 FREE，正在 CHOREO 时严词拒绝"""
        self._check_expiry(robot_id)
        curr = self.get_state(robot_id)
        if curr == "CHOREO":
            return False, "CHOREO", f"严词拒绝: 机器人 {robot_id} 正在执行 CHOREO 任务，严禁通过 RELEASE 释放控制权！"
        if curr == "MANUAL":
            self._states[robot_id] = "FREE"
            self._leases.pop(robot_id, None)
            return True, "FREE", f"机器人 {robot_id} 成功释放 MANUAL 控制权，恢复 FREE"
        return True, "FREE", f"机器人 {robot_id} 当前已处于 FREE 状态"

    def handle_stop(self, robot_id: str) -> Tuple[str, str]:
        """STOP 统一语义：MANUAL 停动保权，CHOREO 安全中断并释放"""
        self._check_expiry(robot_id)
        curr = self.get_state(robot_id)
        if curr == "MANUAL":
            return "MANUAL", f"机器人 {robot_id} 停动保权（保持 MANUAL）"
        if curr == "CHOREO":
            self._states[robot_id] = "FREE"
            self._leases.pop(robot_id, None)
            return "FREE", f"机器人 {robot_id} 触发安全中断编排，重置为 FREE"
        return "FREE", f"机器人 {robot_id} 处于 FREE 状态，执行停动确认"


class PlanIdCompiler:
    """不可变编排任务包编译与 plan_id 递增分配器"""

    def __init__(self, initial_plan_id: int = 8001) -> None:
        self._current_plan_id = initial_plan_id

    def compile_plan(self, plan_name: str, task_manifest: Dict[str, Any]) -> Tuple[int, str]:
        plan_id = self._current_plan_id
        self._current_plan_id += 1
        dumped = json.dumps(task_manifest, sort_keys=True, ensure_ascii=False)
        plan_hash = hashlib.sha256(f"{plan_id}:{plan_name}:{dumped}".encode("utf-8")).hexdigest()
        return plan_id, plan_hash


control_arbiter = ControlArbiter()
