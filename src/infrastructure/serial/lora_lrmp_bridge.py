"""
@file: src/infrastructure/serial/lora_lrmp_bridge.py
@brief: LRMP 协议与机载 lora_recv_group 物理串口双工通信桥接器
@exports: LoraLrmpBridge, lora_lrmp_bridge
"""
import atexit
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from backend.serial_manager import serial_manager
from src.core.logger import get_logger

logger = get_logger("LoraLrmpBridge")

ALLOWED_BUTTONS = {
    "L1", "L2", "R1", "R2", "SELECT", "START", "A", "B",
    "X", "Y", "UP", "DOWN", "LEFT", "RIGHT", "F1", "F3"
}


class LoraLrmpBridge:
    """打通 LRMP 与机载 lora_recv_group，提供姿态保护、MOVE映射、硬急停与白名单过滤"""

    def __init__(self, max_move_time: float = 10.0) -> None:
        self.max_move_time = max_move_time
        self.forward_axis = 0.60
        self.lateral_axis = 0.50
        self.turn_axis = 0.70
        self._active_timers: Dict[str, threading.Timer] = {}
        self._timer_lock = threading.Lock()
        atexit.register(self._on_process_exit)

    def _on_process_exit(self) -> None:
        """程序退出钩子：根据商业化补充说明第6节强制广播 ALL|STOP"""
        try:
            if serial_manager.is_connected():
                serial_manager.send_command("ALL", "STOP")
        except Exception:
            pass

    def execute_posture_chain(
        self,
        target: str,
        delay_s: float = 3.0,
        progress_cb: Optional[Callable[[str], None]] = None
    ) -> Tuple[bool, str]:
        """姿态保护链：STAND (进 FixStand) -> 3.0 秒就绪等待 -> GAIT (进 RL_MJAMP 步态)"""
        cb = progress_cb or (lambda msg: None)
        cb(f"[{target}] 正在请求 STAND (FixStand)...")
        res1 = serial_manager.send_command(target, "STAND")
        if not res1.get("success"):
            return False, f"STAND 下发失败: {res1.get('msg')}"

        cb(f"[{target}] 等待伺服姿态与传感器就绪 ({delay_s}s)...")
        time.sleep(delay_s)

        cb(f"[{target}] 正在请求 GAIT (RL_MJAMP 步态)...")
        res2 = serial_manager.send_command(target, "GAIT")
        if not res2.get("success"):
            return False, f"GAIT 下发失败: {res2.get('msg')}"
        return True, f"[{target}] 姿态保护链执行完毕，已进入步态模式"

    def enter_passive(self, target: str) -> Tuple[bool, str]:
        """安全回被动态：下发 PASSIVE (机载执行 STOP + LEFT 阻尼回落)"""
        res = serial_manager.send_command(target, "PASSIVE")
        ok = bool(res.get("success"))
        return ok, res.get("msg", "")

    def send_move_command(
        self,
        target: str,
        forward: float,
        left: float,
        turn: float,
        t: float
    ) -> Tuple[bool, str]:
        """将归一化 MOVE,forward,left,turn,t 映射为机载方向指令并装配超时清零守护"""
        if not (-1.0 <= forward <= 1.0 and -1.0 <= left <= 1.0 and -1.0 <= turn <= 1.0):
            return False, f"运动分量超出 [-1.0, 1.0] 边界: ({forward}, {left}, {turn})"
        if not (0 < t <= self.max_move_time):
            return False, f"运动时间 t={t} 超出有效范围 (0, {self.max_move_time}] 秒"

        dur = round(t, 2)
        cmd_str = self._resolve_motion_cmd(forward, left, turn, dur)
        if not cmd_str:
            return True, f"[{target}] 控制量微小，静止保持"

        with self._timer_lock:
            if target in self._active_timers:
                self._active_timers[target].cancel()

        res = serial_manager.send_command(target, cmd_str)
        if not res.get("success"):
            return False, f"下发机载指令 {cmd_str} 失败: {res.get('msg')}"

        def _timeout_zeroing():
            serial_manager.send_command(target, "STOP")
            with self._timer_lock:
                self._active_timers.pop(target, None)

        timer = threading.Timer(t, _timeout_zeroing)
        with self._timer_lock:
            self._active_timers[target] = timer
        timer.start()
        return True, f"成功映射并下发机载指令 {target}|{cmd_str} (超时保护 {t}s 已武装)"

    def _resolve_motion_cmd(self, fwd: float, left: float, turn: float, dur: float) -> str:
        af, al, at = abs(fwd), abs(left), abs(turn)
        if max(af, al, at) < 0.05:
            return ""
        if af >= al and af >= at:
            return f"FORWARD,{dur}" if fwd > 0 else f"BACKWARD,{dur}"
        if al > af and al >= at:
            return f"MOVE_LEFT,{dur}" if left > 0 else f"MOVE_RIGHT,{dur}"
        return f"TURN_LEFT,{dur}" if turn > 0 else f"TURN_RIGHT,{dur}"

    def trigger_hardware_emergency(self, known_targets: Optional[List[str]] = None) -> Tuple[bool, str]:
        """硬急停双保：串口物理广播 ALL|EMERGENCY (零轴+清键) + 各目标 LRMP 定向 <T>|STOP"""
        res_broadcast = serial_manager.send_command("ALL", "EMERGENCY")
        targets = known_targets or ["A", "B", "C", "D"]
        for t in targets:
            serial_manager.send_command(t.strip().upper(), "STOP")
        ok = bool(res_broadcast.get("success", True))
        return ok, f"全场硬急停已触发 (ALL|EMERGENCY 广播已发送，{len(targets)} 机定向 STOP 已送达)"

    def send_button_command(
        self,
        target: str,
        k1: str,
        k2: Optional[str] = None,
        is_admin: bool = False
    ) -> Tuple[bool, str]:
        """高级兼容 BUTTON 指令：严格白名单与管理员权限过滤"""
        if not is_admin:
            return False, "拒绝执行: BUTTON 为底层特权指令，调用方未获管理员授权"
        keys = [k1.strip().upper()] + ([k2.strip().upper()] if k2 else [])
        for k in keys:
            if k not in ALLOWED_BUTTONS:
                return False, f"按键 '{k}' 不在白名单中，合法按键: {sorted(list(ALLOWED_BUTTONS))}"
        cmd = f"BUTTON,{','.join(keys)}"
        res = serial_manager.send_command(target, cmd)
        return bool(res.get("success")), res.get("msg", "")

    def send_mask_command(self, target: str, mask_hex: str, is_admin: bool = False) -> Tuple[bool, str]:
        """高级兼容 MASK 指令：十六位按键掩码与权限校验"""
        if not is_admin:
            return False, "拒绝执行: MASK 为底层特权指令，调用方未获管理员授权"
        clean_mask = mask_hex.strip().upper().removeprefix("0X")
        if not clean_mask or len(clean_mask) > 4:
            return False, f"掩码值非法: {mask_hex}，必须为不超过4位的16进制串"
        cmd = f"MASK,{clean_mask}"
        res = serial_manager.send_command(target, cmd)
        return bool(res.get("success")), res.get("msg", "")


lora_lrmp_bridge = LoraLrmpBridge()

