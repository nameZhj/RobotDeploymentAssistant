# @file: src/task_chain/task_chain_executor.py
# @brief: Arrival-driven sequential task chain executor with BARRIER gates, safety interlocks, UDP nav sync, and return-to-origin.
# @exports: TaskChainState, TaskChainExecutor

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import threading
import time
from typing import Any, Dict, List, Optional, Set

from src.commands.control_arbiter import ControlArbiter
from src.commands.motion_command_executor import MotionCommandExecutor
from src.config.ros_env_config import RosEnvConfig
from src.ros_bridge.ros_topic_service_bridge import RosTopicServiceBridge
from src.task_chain.webhook_dispatcher import WebhookDispatcher


@dataclass
class TaskChainState:
    status: str = "IDLE"
    plan_id: str = ""
    run_id: str = ""
    target_id: str = ""
    current_step_index: int = 0
    current_node_title: str = ""
    total_nodes: int = 0
    waiting_barrier_id: str = ""
    origin_pose: Dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "yaw": 0.0})
    last_error: str = ""
    sha256: str = ""
    saved_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskChainExecutor:
    """Executes uploaded robot task chains node-by-node waiting for real goal arrival before next step."""

    def __init__(self, cfg: RosEnvConfig, arbiter: ControlArbiter, ros_bridge: RosTopicServiceBridge, motion_exec: MotionCommandExecutor, webhook: WebhookDispatcher) -> None:
        self.cfg, self.arbiter, self.ros_bridge, self.motion_exec, self.webhook = cfg, arbiter, ros_bridge, motion_exec, webhook
        self._lock, self._stop_event = threading.Lock(), threading.Event()
        self._barrier_cond = threading.Condition(self._lock)
        self._released_barriers: Set[str] = set()
        self._worker: Optional[threading.Thread] = None
        self._nodes: List[Dict[str, Any]] = []
        self._callback_url, self._safety_coordinator = "", None
        self.state = TaskChainState()

    def set_safety_coordinator(self, coordinator: Any) -> None:
        self._safety_coordinator = coordinator

    def _bind_callback_url(self, callback_url: str) -> str:
        cb = (callback_url or "").strip() or self._callback_url
        if cb:
            self._callback_url = cb
            if self._safety_coordinator is not None: self._safety_coordinator.set_callback_url(cb)
        return cb

    def upload_chain(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._worker is not None and self._worker.is_alive(): raise RuntimeError("任务链正在运行，请先停止后再上传新任务链")
        nodes = payload.get("chain_nodes") or payload.get("taskChain") or []
        if not isinstance(nodes, list): raise ValueError("chain_nodes 必须为数组")
        origin = payload.get("origin_pose") or payload.get("originPose") or {"x": 0.0, "y": 0.0, "yaw": 0.0}
        target_id = str(payload.get("target_id") or payload.get("targetId") or "A").strip().upper()
        plan_id = str(payload.get("plan_id") or payload.get("planId") or "8001")
        raw_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self.cfg.cache_dir / f"chain_{target_id}_{plan_id}.json"
        cache_file.write_text(raw_bytes.decode("utf-8"), encoding="utf-8")
        with self._lock:
            self._nodes = list(nodes); self._released_barriers.clear()
            self.state = TaskChainState(
                status="UPLOADED", plan_id=plan_id, target_id=target_id, total_nodes=len(nodes),
                origin_pose={"x": float(origin.get("x", 0.0)), "y": float(origin.get("y", 0.0)), "yaw": float(origin.get("yaw", 0.0))},
                sha256=hashlib.sha256(raw_bytes).hexdigest(), saved_path=str(cache_file),
            )
        return self.state.to_dict()

    def prep_chain(self, run_id: str, callback_url: str = "") -> Dict[str, Any]:
        if self.arbiter.is_safety_locked:
            return {"ok": False, "status_code": 409, "message": f"安全联锁生效，禁止 PREP: {self.arbiter.safety_lock_reason}"}
        dec = self.arbiter.evaluate_and_apply("PREP")
        if not dec.allowed: return {"ok": False, "status_code": 409, "message": dec.reason}
        cb = self._bind_callback_url(callback_url)
        with self._lock:
            self.state.run_id, self.state.status = run_id, "PREPARING"; self._released_barriers.clear()
        ok_g, err_g = self.motion_exec.ensure_gait_for_nav(allow_stand_from_passive=True)
        if not ok_g:
            self.arbiter.release_choreo_on_finish()
            with self._lock: self.state.status, self.state.last_error = "ERROR", err_g
            code = 503 if ("超时" in err_g or "未回复" in err_g or "socket" in err_g.lower()) else 409
            return {"ok": False, "status_code": code, "message": f"PREP 切换 GAIT 失败: {err_g}", "state": self.state.to_dict()}
        ox, oy, oyaw = self.state.origin_pose["x"], self.state.origin_pose["y"], self.state.origin_pose["yaw"]
        goal_res = self.ros_bridge.publish_nav_goal(ox, oy, oyaw)
        if not goal_res.get("ok"):
            self.arbiter.release_choreo_on_finish()
            with self._lock: self.state.status, self.state.last_error = "ERROR", str(goal_res.get("reason", "ROS 不可用"))
            return {"ok": False, "status_code": 503, "message": self.state.last_error, "state": self.state.to_dict()}
        with self._lock: self.state.status = "READY"
        self.webhook.emit(cb, "TASK_CHAIN_READY", self.state.to_dict())
        return {"ok": True, "status_code": 202, "message": "已下发初始原点 PREP 定位导航", "state": self.state.to_dict()}

    def start_chain(self, run_id: str, callback_url: str = "") -> Dict[str, Any]:
        if self.arbiter.is_safety_locked:
            return {"ok": False, "status_code": 409, "message": f"安全联锁生效，禁止启动任务链: {self.arbiter.safety_lock_reason}"}
        if self._worker is not None and self._worker.is_alive():
            return {"ok": False, "status_code": 409, "message": "任务链正在运行中"}
        if not self._nodes:
            return {"ok": False, "status_code": 400, "message": "尚未上传任何任务链节点"}
        if self.arbiter.state.value != "CHOREO":
            dec = self.arbiter.evaluate_and_apply("PREP")
            if not dec.allowed:
                return {"ok": False, "status_code": 409, "message": dec.reason}
        dec_play = self.arbiter.evaluate_and_apply("PLAY")
        if not dec_play.allowed:
            return {"ok": False, "status_code": 409, "message": dec_play.reason}
        self._bind_callback_url(callback_url)
        self._stop_event.clear()
        with self._lock:
            self.state.run_id, self.state.status, self.state.last_error, self.state.current_step_index = run_id, "RUNNING", "", 0
        self._worker = threading.Thread(target=self._run_chain_loop, daemon=True, name="TaskChainRunner")
        self._worker.start()
        return {"ok": True, "status_code": 202, "message": "顺序任务链已启动", "state": self.state.to_dict()}

    def release_barrier(self, run_id: str, barrier_id: str, release_ms: int = 0) -> Dict[str, Any]:
        dec = self.arbiter.evaluate_and_apply("BARRIER")
        if not dec.allowed:
            return {"ok": False, "status_code": 409, "message": dec.reason}
        bid = str(barrier_id).strip()
        with self._barrier_cond:
            if self.state.run_id and str(run_id) != str(self.state.run_id):
                return {"ok": False, "status_code": 409, "message": f"run_id 不匹配 ({run_id} != {self.state.run_id})"}
            self._released_barriers.add(bid)
            if self.state.waiting_barrier_id == bid:
                self.state.waiting_barrier_id, self.state.status = "", "RUNNING"
            self._barrier_cond.notify_all()
        self.webhook.emit(self._callback_url, "BARRIER_RELEASED", {"barrier_id": bid, "release_ms": release_ms, "state": self.state.to_dict()})
        return {"ok": True, "status_code": 200, "message": f"同步屏障 {bid} 已放行", "state": self.state.to_dict()}

    def abort_running_chain(self, reason: str = "STOP", emit_terminal: bool = True) -> None:
        """Immediately signal and join any running chain worker (used by EMERGENCY/STOP/FAULT)."""
        self._stop_event.set()
        with self._barrier_cond:
            self._barrier_cond.notify_all()
        worker = self._worker
        if worker is not None and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=1.5)
        with self._lock:
            aborted = self.state.status in ("RUNNING", "WAITING_BARRIER", "PREPARING", "READY")
            if aborted:
                self.state.status, self.state.waiting_barrier_id, self.state.last_error = "STOPPED", "", reason
        self.arbiter.release_choreo_on_finish()
        if emit_terminal and aborted:
            st = self.state.to_dict()
            self.webhook.emit_async(self._callback_url, "CHAIN_ABORTED", {"target_id": st["target_id"], "reason": reason, "state": st}, urgent=True)

    def stop_and_return_origin(self, origin_pose: Optional[Dict[str, Any]] = None, callback_url: str = "") -> Dict[str, Any]:
        self.abort_running_chain("STOP_RETURN_ORIGIN", emit_terminal=False)
        cb = self._bind_callback_url(callback_url)
        with self._lock:
            if origin_pose:
                self.state.origin_pose = {k: float(origin_pose.get(k, 0.0)) for k in ("x", "y", "yaw")}
            ox, oy, oyaw = self.state.origin_pose["x"], self.state.origin_pose["y"], self.state.origin_pose["yaw"]
        cancel_res, stop_res = self.ros_bridge.cancel_planning(), self.motion_exec.execute("STOP")
        if self.arbiter.is_safety_locked:
            lock_msg = f"安全联锁生效，仅停机未回原点: {self.arbiter.safety_lock_reason}"
            goal_res: Dict[str, Any] = {"ok": False, "skipped": True, "reason": lock_msg}
            st_name, title, err_s = "STOPPED", "安全停机", lock_msg
        else:
            ok_g, err_g = self.motion_exec.ensure_gait_for_nav(allow_stand_from_passive=True)
            if ok_g:
                goal_res = self.ros_bridge.publish_nav_goal(ox, oy, oyaw)
                st_name, title, err_s = ("RETURNING_TO_ORIGIN" if goal_res.get("ok") else "STOPPED"), "返回原点", ("" if goal_res.get("ok") else str(goal_res.get("reason", "")))
            else:
                goal_res = {"ok": False, "skipped": True, "reason": f"切换 GAIT 失败: {err_g}"}
                st_name, title, err_s = "STOPPED", "返回原点失败", str(goal_res["reason"])
        with self._lock:
            self.state.status, self.state.current_step_index, self.state.current_node_title, self.state.waiting_barrier_id, self.state.last_error = st_name, 0, title, "", err_s
        self.arbiter.release_choreo_on_finish()
        self.webhook.emit(cb, "STOPPED_RETURNING_ORIGIN", {"state": self.state.to_dict(), "cancel_result": cancel_res, "return_goal_result": goal_res})
        return {"ok": True, "status_code": 200, "message": "已中止任务链" + ("（安全联锁仅停机）" if self.arbiter.is_safety_locked else ("并下发回到原点指令" if goal_res.get("ok") else "（未能下发回原点）")), "cancel_result": cancel_res, "stop_result": stop_res.to_dict(), "return_goal_result": goal_res, "state": self.state.to_dict()}

    def _wait_barrier_if_required(self, node: Dict[str, Any]) -> bool:
        bid = str(node.get("barrier_id") or ("1" if node.get("node_type") == "barrier" else "")).strip()
        if not bid:
            return True
        with self._barrier_cond:
            if bid in self._released_barriers:
                return True
            self.state.waiting_barrier_id, self.state.status = bid, "WAITING_BARRIER"
        self.webhook.emit(self._callback_url, "BARRIER_WAITING", {"barrier_id": bid, "state": self.state.to_dict()})
        with self._barrier_cond:
            while bid not in self._released_barriers and not self._stop_event.is_set():
                self._barrier_cond.wait(timeout=0.2)
            return not self._stop_event.is_set()

    def _run_chain_loop(self) -> None:
        try:
            for idx, node in enumerate(list(self._nodes), start=1):
                if self._stop_event.is_set() or not self._wait_barrier_if_required(node):
                    return
                title = str(node.get("title") or node.get("name") or f"Node_{idx}")
                ntype = str(node.get("node_type") or node.get("type") or "trajectory").lower()
                with self._lock:
                    self.state.current_step_index, self.state.current_node_title = idx, title
                self.webhook.emit(self._callback_url, "STEP_STARTED", {"step_index": idx, "title": title, "node_type": ntype, "state": self.state.to_dict()})
                if ntype == "trajectory":
                    ok, err = self._execute_nav_node(idx, title, node)
                else:
                    ok, err = (True, "") if ntype == "barrier" else self._execute_action_node(idx, title, node)
                if self._stop_event.is_set():
                    return
                if not ok:
                    with self._lock:
                        self.state.status, self.state.last_error = "ERROR", err
                    self.webhook.emit(self._callback_url, "TASK_ERROR", {"step_index": idx, "title": title, "error": err, "state": self.state.to_dict()})
                    return
                self.webhook.emit(self._callback_url, "STEP_COMPLETED", {"step_index": idx, "title": title, "node_type": ntype, "state": self.state.to_dict()})
            with self._lock:
                self.state.status = "COMPLETED"
            self.webhook.emit(self._callback_url, "CHAIN_COMPLETED", {"state": self.state.to_dict()})
        finally:
            self.arbiter.release_choreo_on_finish()

    def _navigate_to_pose(
        self, idx: int, title: str, tx: float, ty: float, tyaw: float,
        tol: float, is_final: bool, wp_i: int, wp_n: int, deadline: float,
    ) -> tuple[bool, str]:
        udp = self.motion_exec.motion_udp
        nav_seq0 = udp.tracker.get_nav_state()[0] if udp is not None else 0
        pub_res = self.ros_bridge.publish_nav_goal(tx, ty, tyaw)
        if not pub_res.get("ok"): return False, str(pub_res.get("reason", "发布导航目标点失败"))
        while not self._stop_event.is_set():
            if self.arbiter.is_safety_locked:
                self.ros_bridge.cancel_planning()
                return False, f"安全联锁中断导航: {self.arbiter.safety_lock_reason}"
            cur_seq, cur_nst, cur_nrsn = udp.tracker.get_nav_state() if udp is not None else (0, "", "")
            if cur_seq > nav_seq0 and cur_nst in ("FAILED", "CANCELLED"):
                self.ros_bridge.cancel_planning()
                return False, f"G1 导航{'失败' if cur_nst == 'FAILED' else '已取消'}: {cur_nrsn or cur_nst}"
            snap = self.ros_bridge.read_telemetry_snapshot()
            if self._stop_event.is_set(): return False, "任务已中止"
            if not snap.ros_available: return False, snap.reason or "ROS 连接中断"
            ros_st = (snap.local_nav_status or "").upper()
            if ros_st in ("FAILED", "ABORTED", "ERROR"):
                self.ros_bridge.cancel_planning()
                return False, f"ROS 导航异常: {snap.local_nav_status}"
            if snap.pose is not None:
                dist = math.hypot(snap.pose[0] - tx, snap.pose[1] - ty)
                m = self.motion_exec.get_state()["motion"]
                self.webhook.emit_async(self._callback_url, "STEP_PROGRESS", {
                    "step_index": idx, "title": title, "waypoint_index": wp_i + 1, "waypoint_total": wp_n,
                    "target_id": self.state.target_id, "state": self.state.to_dict(),
                    "pose": {"x": snap.pose[0], "y": snap.pose[1], "yaw": snap.pose[2]},
                    "localization_confidence": snap.localization_confidence, "localization_delay_ms": snap.localization_delay_ms,
                    "remaining_distance_m": round(dist, 3), "local_nav_status": snap.local_nav_status,
                    "motion_state": m.get("state", ""), "nav_input": m.get("nav_input", ""), "nav_status": m.get("nav_status", ""),
                })
                paused = cur_seq > nav_seq0 and cur_nst == "PAUSED"
                nav_ok = True if not is_final else (ros_st in ("", "SUCCEEDED", "REACHED", "ARRIVED", "IDLE") and not paused)
                if dist <= tol and nav_ok: return True, ""
            if time.monotonic() >= deadline: return False, f"导航至 '{title}' ({tx:.2f}, {ty:.2f}) 超时"
            time.sleep(self.cfg.nav_poll_interval_s)
        return False, "任务已中止"

    def _execute_nav_node(self, idx: int, title: str, node: Dict[str, Any]) -> tuple[bool, str]:
        ok_g, err_g = self.motion_exec.ensure_gait_for_nav(self._stop_event, allow_stand_from_passive=True)
        if not ok_g:
            return False, f"导航前切换 GAIT 失败: {err_g}"
        tx, ty, tyaw = (float(node.get(k1, node.get(k2, 0.0))) for k1, k2 in (("target_x", "targetX"), ("target_y", "targetY"), ("target_yaw", "targetYaw")))
        raw_wps = node.get("waypoints") if isinstance(node.get("waypoints"), list) else []
        targets = [(float(w["x"]), float(w["y"]), float(w.get("yaw", 0.0))) for w in raw_wps if isinstance(w, dict) and "x" in w and "y" in w]
        if not targets or math.hypot(targets[-1][0] - tx, targets[-1][1] - ty) > 0.05:
            targets.append((tx, ty, tyaw))
        deadline = time.monotonic() + self.cfg.nav_goal_timeout_s
        for wi, (wx, wy, wyaw) in enumerate(targets):
            is_final = wi == len(targets) - 1
            tol = self.cfg.arrival_xy_tolerance_m if is_final else max(0.45, self.cfg.arrival_xy_tolerance_m * 1.8)
            ok, err = self._navigate_to_pose(idx, title, wx, wy, wyaw, tol, is_final, wi, len(targets), deadline)
            if not ok:
                return False, err
        return True, ""

    def _execute_action_node(self, _idx: int, title: str, node: Dict[str, Any]) -> tuple[bool, str]:
        return self.motion_exec.execute_chain_action({**node, "title": title} if not node.get("title") else node, self._stop_event)
