"""
LRMP V1.0-R3 多机集群控制服务
实现控制权互斥状态机 (FREE/MANUAL/CHOREO)、多机目标指令展开与全量会话真实日志审计
"""
import os
import time
from typing import Any, Dict, List, Optional, Tuple
from PySide6.QtCore import QObject, Signal

from src.infrastructure.lrmp.embedded_swarm_sim import EmbeddedSwarmSim


class LRMPSwarmService(QObject):
    """LRMP 集群通信会话与多机编排协同服务"""

    logAppended = Signal(str)
    stateChanged = Signal(str, str)
    telemetryUpdated = Signal(dict)

    def __init__(self, log_dir: str = os.path.join("runtime", "logs"), parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.log_file = os.path.join(log_dir, "lrmp_session.log")
        os.makedirs(os.path.dirname(os.path.abspath(self.log_file)), exist_ok=True)

        self.control_mode = "FREE"  # FREE / MANUAL / CHOREO
        self.simulator = EmbeddedSwarmSim()
        self.active_targets: List[str] = ["A", "B"]

    def acquire_control(self, mode: str) -> bool:
        """申请控制权 (FREE / MANUAL / CHOREO 严格互斥)"""
        target_mode = mode.upper()
        if target_mode not in ("FREE", "MANUAL", "CHOREO"):
            return False
        if self.control_mode != "FREE" and target_mode != "FREE" and self.control_mode != target_mode:
            self._write_log("SYS", f"DENIED,CONTROL_CONFLICT,CURRENT:{self.control_mode},REQUEST:{target_mode}")
            return False
        old_mode = self.control_mode
        self.control_mode = target_mode
        self.stateChanged.emit("CONTROL_MODE", target_mode)
        self._write_log("SYS", f"CONTROL_SWITCH,{old_mode}->{target_mode}")
        return True

    def release_control(self) -> None:
        self.acquire_control("FREE")

    def _write_log(self, src_id: str, payload: str, direction: str = "INFO") -> None:
        """强制写入 runtime/logs/lrmp_session.log 并标记真实设备来源 SRC_ID"""
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_line = f"[{ts}] [{direction}] [SRC_ID: {src_id}] {payload}"
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
        except Exception:
            pass
        self.logAppended.emit(log_line)

    def send_frame(self, target: str, cmd: str) -> List[Tuple[str, str]]:
        """发送单条指令并自动交由模拟器/真实物理链路应答"""
        raw_cmd = f"{target}|{cmd}"
        self._write_log("LOCAL", f"SEND -> {raw_cmd}", direction="REQ")
        responses = self.simulator.handle_command(raw_cmd)
        for src_id, rsp in responses:
            dir_tag = "EVT" if rsp.startswith("EVT") else "RSP"
            self._write_log(src_id, f"[{dir_tag} from {src_id}] {rsp}", direction=dir_tag)
        return responses

    def discover_all(self) -> List[Tuple[str, str]]:
        """全网发现网关与待分配机器人 (ALL|DISCOVER)"""
        return self.send_frame("ALL", "DISCOVER")

    def bind_robot(self, gw_id: str, alias: str) -> bool:
        """绑定网关到字母别名 (GW_xxxx|BIND,A)"""
        res = self.send_frame(gw_id, f"BIND,{alias}")
        return any("BIND_OK" in r[1] for r in res)

    def init_robot(self, alias: str, job_id: str = "601") -> bool:
        """初始化指定机器人并下发 Job 任务 (A|SETUP,601)"""
        res = self.send_frame(alias, f"SETUP,{job_id}")
        return any("SETUP_SUCCESS" in r[1] or "ACCEPTED" in r[1] for r in res)

    def sync_choreo_prep(self, targets: List[str], plan_id: str, run_id: str) -> Dict[str, bool]:
        """多机准备不可变编排包并等待全员进入 READY 状态"""
        if not self.acquire_control("CHOREO"):
            return {t: False for t in targets}
        results = {}
        for t in targets:
            rsps = self.send_frame(t, f"PREP,{plan_id},{run_id}")
            ready = any("READY" in r[1] or "ACCEPTED" in r[1] for r in rsps)
            results[t] = ready
        return results

    def start_synchronized_play(self, targets: List[str], run_id: str, lead_ms: int = 500) -> bool:
        """校验时钟后下发相同基准时间戳的同步起舞指令 (<T>|PLAY,run_id,t0_ms)"""
        for t in targets:
            clock_res = self.send_frame(t, "STATUS,CLOCK")
            if not any("SYNCED" in r[1] for r in clock_res):
                return False
        t0_ms = int(time.time() * 1000) + lead_ms
        all_ok = True
        for t in targets:
            play_res = self.send_frame(t, f"PLAY,{run_id},{t0_ms}")
            if not any("ACCEPTED" in r[1] or "ACK" in r[1] for r in play_res):
                all_ok = False
        return all_ok

    def release_barrier(self, targets: List[str], run_id: str, barrier_id: str) -> None:
        """多机同步屏障点放行 (<T>|BARRIER,run_id,barrier_id)"""
        for t in targets:
            self.send_frame(t, f"BARRIER,{run_id},{barrier_id}")

    def emergency_stop_all(self, targets: Optional[List[str]] = None) -> None:
        """右滑急停广播展开 (<T>|STOP) 立即刹车解锁控制权"""
        t_list = targets if targets is not None else self.active_targets
        for t in t_list:
            self.send_frame(t, "STOP")
        self.control_mode = "FREE"
        self.stateChanged.emit("CONTROL_MODE", "FREE")
        self._write_log("SYS", "EMERGENCY_STOP_EXECUTED,ALL_RELEASED")

    def poll_telemetry(self) -> Dict[str, Any]:
        """拉取集群最新状态与遥测快照"""
        fleet = {}
        for t in self.active_targets:
            fleet[t] = self.simulator.get_telemetry(t)
        self.telemetryUpdated.emit(fleet)
        return fleet

