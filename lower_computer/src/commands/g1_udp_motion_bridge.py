# @file: src/commands/g1_udp_motion_bridge.py
# @brief: Thread-safe onboard UDP bridge to G1 receiver with non-blocking event dispatch, state/nav sync, and fault-aware waits.
# @exports: UdpSendResult, G1UdpMotionBridge, build_motion_udp_packet

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict, dataclass
import queue
import socket
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from src.commands.g1_udp_protocol import G1RobotStateTracker, build_motion_udp_packet, parse_udp_reply_line

UdpEventCallback = Callable[[str, Dict[str, Any]], None]
StatePredicate = Callable[[G1RobotStateTracker], bool]
_NO_ACK_CMDS = frozenset({"PING", "QUERY_STATE", "QUERY_NAV"})


@dataclass
class UdpSendResult:
    """Result envelope for a single UDP motion transmission and optional ACK/ERR reply."""

    ok: bool
    packet: str
    endpoint: str
    message: str
    ack_received: bool = False
    error_code: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class G1UdpMotionBridge:
    """Thread-safe onboard UDP bridge handling all G1 reply frames and asynchronous event queue dispatch."""

    def __init__(
        self, host: str = "127.0.0.1", port: int = 8899, source_ip: str = "127.0.0.1", source_port: int = 0,
        probe_timeout_s: float = 2.0, ack_timeout_s: float = 0.5, dance_grace_s: float = 10.0,
        default_dance_timeout_s: float = 60.0, on_event: Optional[UdpEventCallback] = None,
    ) -> None:
        self.host, self.port = host.strip() or "127.0.0.1", int(port)
        self.source_ip, self.source_port = source_ip.strip() or "127.0.0.1", int(source_port)
        self.probe_timeout_s, self.ack_timeout_s = max(0.2, float(probe_timeout_s)), max(0.0, float(ack_timeout_s))
        self.dance_grace_s, self.default_dance_timeout_s = max(0.0, float(dance_grace_s)), max(0.1, float(default_dance_timeout_s))
        self._on_event = on_event
        self.tracker = G1RobotStateTracker()
        self._ack_lock, self._send_lock, self._state_lock = threading.Lock(), threading.Lock(), threading.Lock()
        self._cmd_cond, self._dance_cond, self._state_cond = (
            threading.Condition(self._state_lock), threading.Condition(self._state_lock), threading.Condition(self._state_lock),
        )
        self._pong_event = threading.Event()
        self._event_queue: queue.Queue[Optional[Tuple[str, Dict[str, Any]]]] = queue.Queue(maxsize=256)
        self._closed, self._sock, self._rx_thread, self._event_thread = False, None, None, None
        self._cmd_reply: Optional[Tuple[str, bool, str]] = None
        self._dance_result: Optional[Tuple[str, bool, str]] = None
        self._open_socket()

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    def set_event_callback(self, callback: Optional[UdpEventCallback]) -> None:
        self._on_event = callback

    def _open_socket(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((self.source_ip, self.source_port))
            sock.settimeout(0.2)
            self._sock = sock
            self._event_thread = threading.Thread(target=self._event_loop, daemon=True, name="G1UdpEventWorker")
            self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True, name="G1UdpMotionRx")
            self._event_thread.start(); self._rx_thread.start()
        except OSError as ex:
            self.tracker.set_error(f"UDP bind 失败 ({self.source_ip}:{self.source_port}): {ex}")
            self._sock = None

    def _event_loop(self) -> None:
        while True:
            item = self._event_queue.get()
            if item is None: break
            if self._on_event is not None:
                try: self._on_event(item[0], item[1])
                except Exception: pass

    def _enqueue_event(self, ev_name: str, payload: Dict[str, Any]) -> None:
        try:
            self._event_queue.put_nowait((ev_name, payload))
        except queue.Full:
            try: self._event_queue.get_nowait(); self._event_queue.put_nowait((ev_name, payload))
            except queue.Empty: pass

    def _rx_loop(self) -> None:
        while not self._closed and self._sock is not None:
            try:
                raw, _ = self._sock.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                break
            for line in raw.decode("utf-8", errors="ignore").splitlines():
                self._handle_reply_line(line.strip())

    def _handle_reply_line(self, line: str) -> None:
        rep = parse_udp_reply_line(line)
        if rep is None:
            return
        ev_name, payload = self.tracker.apply(rep)
        if rep.kind == "PONG":
            self._pong_event.set()
            return
        with self._state_lock:
            if rep.kind in ("ACK", "ERR"):
                ok_ack = rep.kind == "ACK"
                self._cmd_reply = (rep.command, ok_ack, "" if ok_ack else rep.reason)
                self._cmd_cond.notify_all()
                if not ok_ack and rep.command == "DANCE":
                    self._dance_result = ("*", False, f"G1 拒绝舞蹈: {rep.reason}")
                    self._dance_cond.notify_all()
            elif rep.kind == "DANCE_DONE":
                ok = rep.result == "OK"
                self._dance_result = (rep.alias, ok, f"DANCE_DONE:{rep.result}" if ok else f"舞蹈中断 ({rep.result}): {rep.reason or rep.result}")
                self._dance_cond.notify_all()
                self._state_cond.notify_all()
            elif rep.kind in ("STATE", "NAV_STATUS", "FAULT", "DANCE_START"):
                self._state_cond.notify_all()
                if self.tracker.is_safety_locked:
                    self._dance_cond.notify_all()
        if ev_name and payload is not None:
            self._enqueue_event(ev_name, payload)

    def send_command(self, target: str, command: str, wait_ack: Optional[bool] = None) -> UdpSendResult:
        """Validate frame, send once via UDP, and optionally wait for ACK/ERR."""
        try:
            pkt = build_motion_udp_packet(target, command)
        except ValueError as ex:
            return UdpSendResult(False, "", self.endpoint, f"UDP 帧格式非法: {ex}", error_code="INVALID_FRAME")
        pkt_str, cmd_head = pkt.decode("ascii").rstrip(), command.strip().upper().split(",", 1)[0]
        if self._closed or self._sock is None:
            return UdpSendResult(False, pkt_str, self.endpoint, self.tracker.get_error() or "UDP socket 未就绪", error_code="SOCKET_CLOSED")
        should_wait = (cmd_head not in _NO_ACK_CMDS and self.ack_timeout_s > 0.0) if wait_ack is None else bool(wait_ack)
        with self._ack_lock if should_wait else nullcontext():
            try:
                with self._send_lock:
                    with self._state_lock:
                        if should_wait: self._cmd_reply = None
                        if cmd_head == "DANCE": self._dance_result = None
                    sent = self._sock.sendto(pkt, (self.host, self.port))
                if sent != len(pkt):
                    return UdpSendResult(False, pkt_str, self.endpoint, "UDP 未完整发送数据报", error_code="SEND_INCOMPLETE")
            except OSError as ex:
                self.tracker.set_error(f"UDP 发送失败: {ex}")
                return UdpSendResult(False, pkt_str, self.endpoint, f"UDP 发送失败: {ex}", error_code="SEND_FAILED")
            if not should_wait:
                return UdpSendResult(True, pkt_str, self.endpoint, f"已通过 UDP 发送至 {self.endpoint}")
            deadline = time.monotonic() + self.ack_timeout_s
            with self._cmd_cond:
                while not self._closed:
                    if self._cmd_reply is not None and self._cmd_reply[0] in (cmd_head, ""):
                        _, rep_ok, rep_reason = self._cmd_reply
                        self._cmd_reply = None
                        return UdpSendResult(rep_ok, pkt_str, self.endpoint, f"G1 已受理 {cmd_head}" if rep_ok else f"G1 拒绝 {cmd_head}: {rep_reason}", ack_received=rep_ok, error_code="" if rep_ok else (rep_reason or "ERR"))
                    rem = deadline - time.monotonic()
                    if rem <= 0.0:
                        self.tracker.set_error(f"G1 运控未回复 ACK ({cmd_head})")
                        return UdpSendResult(False, pkt_str, self.endpoint, f"G1 运控未回复 ACK ({self.endpoint})", error_code="ACK_TIMEOUT")
                    self._cmd_cond.wait(timeout=min(0.05, rem))
        return UdpSendResult(False, pkt_str, self.endpoint, "UDP 运控桥已关闭", error_code="SOCKET_CLOSED")

    def probe(self, target: str = "A", timeout_s: Optional[float] = None) -> Dict[str, Any]:
        """Probe G1 UDP receiver via TARGET|PING\\n and sync STATE/NAV upon PONG."""
        tgt = (target or "A").strip().upper()
        if not tgt or "," in tgt or tgt == "ALL":
            return {"ok": False, "reachable": False, "target": tgt, "endpoint": self.endpoint, "rtt_ms": 0.0, "message": "UDP 探测仅支持单个机器人 ID"}
        self.tracker.clear_pong_target()
        self._pong_event.clear()
        t0 = time.monotonic()
        res = self.send_command(tgt, "PING", wait_ack=False)
        if not res.ok:
            self.tracker.set_reachable(False)
            return {"ok": False, "reachable": False, "target": tgt, "endpoint": self.endpoint, "rtt_ms": 0.0, "message": res.message}
        wait_s = self.probe_timeout_s if timeout_s is None else max(0.1, float(timeout_s))
        deadline, matched = time.monotonic() + wait_s, False
        while time.monotonic() < deadline:
            if self._pong_event.wait(max(0.01, deadline - time.monotonic())):
                if self.tracker.get_pong_target() == tgt:
                    matched = True
                    break
                self._pong_event.clear()
        rtt_ms = round((time.monotonic() - t0) * 1000.0, 2)
        self.tracker.set_reachable(matched)
        if matched:
            self.sync_state(tgt, timeout_s=min(0.35, wait_s))
        else:
            self.tracker.set_error(f"UDP PING 超时 ({wait_s:.1f}s 无 PONG 回包)")
        msg = f"Robot {tgt} UDP 连通正常 ({rtt_ms} ms)" if matched else f"UDP 探测超时: {self.endpoint} 未回复 {tgt}|PONG"
        return {"ok": matched, "reachable": matched, "target": tgt, "endpoint": self.endpoint, "rtt_ms": rtt_ms, "message": msg, "state": self.tracker.snapshot()}

    def _await_query_seq(self, target: str, command: str, seq_idx: int, timeout_s: float) -> Tuple[bool, str, Dict[str, Any]]:
        prev_seq = self.tracker.get_seqs()[seq_idx]
        res = self.send_command(target, command, wait_ack=False)
        if not res.ok:
            return False, res.message, self.tracker.snapshot()
        deadline = time.monotonic() + max(0.1, float(timeout_s))
        with self._state_cond:
            while not self._closed and self.tracker.get_seqs()[seq_idx] == prev_seq:
                rem = deadline - time.monotonic()
                if rem <= 0.0: return False, f"{command} 超时", self.tracker.snapshot()
                self._state_cond.wait(timeout=min(0.05, rem))
        return True, "", self.tracker.snapshot()

    def query_state(self, target: str = "A", timeout_s: float = 0.5) -> Dict[str, Any]:
        ok, err, snap = self._await_query_seq(target, "QUERY_STATE", 0, timeout_s)
        return {"ok": ok, "state": snap["remote_state"], "active_dance": snap["remote_dance"], "nav_input": snap["nav_input"], "message": "已同步 G1 状态" if ok else err}

    def query_nav(self, target: str = "A", timeout_s: float = 0.5) -> Dict[str, Any]:
        ok, err, snap = self._await_query_seq(target, "QUERY_NAV", 1, timeout_s)
        return {"ok": ok, "nav_status": snap["nav_status"], "nav_reason": snap["nav_reason"], "message": "已同步 G1 导航状态" if ok else err}

    def sync_state(self, target: str = "A", timeout_s: float = 0.5) -> Dict[str, Any]:
        s0, n0 = self.tracker.get_seqs()
        r1 = self.send_command(target, "QUERY_STATE", wait_ack=False)
        r2 = self.send_command(target, "QUERY_NAV", wait_ack=False)
        if r1.ok or r2.ok:
            deadline = time.monotonic() + max(0.1, float(timeout_s))
            with self._state_cond:
                while not self._closed:
                    s, n = self.tracker.get_seqs()
                    rem = deadline - time.monotonic()
                    if (s > s0 and n > n0) or rem <= 0.0: break
                    self._state_cond.wait(timeout=min(0.05, rem))
        s, n = self.tracker.get_seqs()
        return {"ok": bool(s > s0 or n > n0), "state_synced": s > s0, "nav_synced": n > n0, **self.tracker.snapshot()}

    def wait_for_state(
        self, predicate: StatePredicate, timeout_s: float = 6.0, stop_event: Optional[threading.Event] = None, abort_on_lock: bool = True,
    ) -> Tuple[bool, str]:
        """Wait until tracker satisfies predicate, aborting immediately on stop_event or safety lock."""
        deadline = time.monotonic() + max(0.1, float(timeout_s))
        with self._state_cond:
            while not self._closed:
                if stop_event is not None and stop_event.is_set(): return False, "任务已中止"
                if abort_on_lock and self.tracker.is_safety_locked: return False, self.tracker.safety_lock_reason()
                if predicate(self.tracker): return True, ""
                rem = deadline - time.monotonic()
                if rem <= 0.0:
                    m_cur, nav_in = self.tracker.get_mode_summary()
                    return False, f"等待 G1 状态收敛超时 (当前: {m_cur or 'UNKNOWN'}/{nav_in or '-'})"
                self._state_cond.wait(timeout=min(0.05, rem))
        return False, "UDP 运控桥已关闭"

    def wait_dance_completion(self, alias: str, fallback_duration_s: float, stop_event: threading.Event) -> Tuple[bool, str]:
        """Wait for DANCE_DONE/ERR reply, aborting immediately on safety lock/ESTOP or stop_event."""
        target_alias = alias.strip().upper()
        wait_limit = (fallback_duration_s + self.dance_grace_s) if fallback_duration_s > 0.0 else self.default_dance_timeout_s
        deadline = time.monotonic() + max(0.05, float(wait_limit))
        with self._dance_cond:
            while not stop_event.is_set() and not self._closed:
                if self._dance_result is not None and self._dance_result[0] in (target_alias, "*"):
                    _, res_ok, res_reason = self._dance_result
                    self._dance_result = None
                    return res_ok, res_reason
                if self.tracker.is_safety_locked:
                    return False, f"安全联锁中断舞蹈: {self.tracker.safety_lock_reason()}"
                rem = deadline - time.monotonic()
                if rem <= 0.0: return True, "DURATION_ELAPSED"
                self._dance_cond.wait(timeout=min(0.05, rem))
        return False, "任务已中止"

    def status_summary(self) -> Dict[str, Any]:
        return {"enabled": self._sock is not None and not self._closed, "endpoint": self.endpoint, **self.tracker.snapshot()}

    def close(self) -> None:
        self._closed = True
        with self._state_lock:
            self._cmd_cond.notify_all(); self._dance_cond.notify_all(); self._state_cond.notify_all()
        if self._sock is not None:
            try: self._sock.close()
            except OSError: pass
            self._sock = None
        try: self._event_queue.put_nowait(None)
        except queue.Full: pass
        for th in (self._rx_thread, self._event_thread):
            if th is not None and th.is_alive(): th.join(timeout=0.5)
        self._rx_thread = self._event_thread = None
