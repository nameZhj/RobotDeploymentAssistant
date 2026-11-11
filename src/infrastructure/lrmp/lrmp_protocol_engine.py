"""
@file: src/infrastructure/lrmp/lrmp_protocol_engine.py
@brief: LRMP V1.0-R3 协议编解码、目标展开、CRC校验与真实 SRC_ID 审计引擎
@exports: LrmpProtocolEngine, lrmp_protocol_engine
"""
import re
import time
import zlib
from typing import Any, Dict, List, Optional, Tuple
from src.core.logger import comm_logger


class LrmpProtocolEngine:
    """LRMP 传输帧编解码、目标地址展开与严格真实 SRC_ID 审计引擎"""

    def __init__(self) -> None:
        self._seq = 0

    def next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFF
        return self._seq

    @staticmethod
    def compute_crc32(text: str) -> str:
        return f"{zlib.crc32(text.encode('utf-8')) & 0xFFFFFFFF:08X}"

    @classmethod
    def parse_command_line(cls, cmd_line: str) -> Tuple[str, str, List[str]]:
        """解析 TARGET|COMMAND[,PARAM1,...] 并校验目标合法性"""
        raw = cmd_line.strip()
        if "|" not in raw:
            raise ValueError(f"指令缺少管道分隔符 '|': {raw}")
        target_part, cmd_part = raw.split("|", 1)
        target = target_part.strip().upper()
        if not re.match(r"^(ALL|[A-Z]|GW_[0-9A-Fa-f]{4,8})$", target):
            raise ValueError(f"目标 TARGET 格式非法: '{target}', 仅支持 A~Z, GW_xxxx, ALL")
        parts = [p.strip() for p in cmd_part.split(",") if p.strip()]
        if not parts:
            raise ValueError(f"指令 COMMAND 为空: {raw}")
        return target, parts[0].upper(), parts[1:]

    @classmethod
    def expand_targets(
        cls,
        target_str: str,
        command: str,
        known_targets: Optional[List[str]] = None
    ) -> List[str]:
        """目标展开规则：除 DISCOVER 外严禁 ALL 广播，多选目标拆分为单播定向列表"""
        target = target_str.strip().upper()
        if target == "ALL":
            if command.upper() == "DISCOVER":
                return ["ALL"]
            if known_targets:
                return [t.strip().upper() for t in known_targets if t.strip()]
            raise ValueError(f"LRMP 协议层严禁非 DISCOVER 指令进行 ALL 广播: {target_str}|{command}")
        return [t.strip().upper() for t in target.split(",") if t.strip()]

    def build_frame(
        self,
        frame_type: str,
        src_id: str,
        dst_id: str,
        payload: str,
        req_id: Optional[str] = None
    ) -> str:
        """封装 REQ/RSP/EVT/ACK 二进制通信帧并记录真实 SRC_ID 日志"""
        clean_src = src_id.strip().upper()
        clean_dst = dst_id.strip().upper()
        if not clean_src:
            raise ValueError("SRC_ID 不能为空，严禁仅标示 CTRL 匿名设备")

        seq = self.next_seq()
        rid = req_id or f"REQ_{int(time.time() * 1000) & 0xFFFFFF:06X}"
        ftype = frame_type.strip().upper()
        body = f"{ftype}:{seq}:{rid}:{clean_src}:{clean_dst}:{payload.strip()}"
        crc = self.compute_crc32(body)
        wire_frame = f"{body}#{crc}"

        comm_logger.log_frame(
            src_id=clean_src,
            dst_id=clean_dst,
            frame_type=ftype,
            payload=payload.strip(),
            status="SENT",
            seq=seq,
        )
        return wire_frame

    def parse_frame(self, wire_str: str) -> Dict[str, Any]:
        """解析网络线上传输帧并强校验 CRC32 完整性"""
        if "#" not in wire_str:
            raise ValueError(f"帧格式缺少 CRC 校验符 #: {wire_str}")
        body, crc = wire_str.strip().rsplit("#", 1)
        expected = self.compute_crc32(body)
        if crc.upper() != expected.upper():
            raise ValueError(f"CRC32 校验失败: 期望 {expected}, 实际 {crc}")

        parts = body.split(":", 5)
        if len(parts) < 6:
            raise ValueError(f"帧字段数不足 6: {wire_str}")

        res = {
            "frame_type": parts[0],
            "seq": int(parts[1]),
            "request_id": parts[2],
            "src_id": parts[3],
            "dst_id": parts[4],
            "payload": parts[5],
            "checksum": crc,
        }
        comm_logger.log_frame(
            src_id=res["src_id"],
            dst_id=res["dst_id"],
            frame_type=res["frame_type"],
            payload=res["payload"],
            status="RECV",
            seq=res["seq"],
        )
        return res


lrmp_protocol_engine = LrmpProtocolEngine()
