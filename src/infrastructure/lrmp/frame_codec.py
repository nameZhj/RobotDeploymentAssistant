import binascii
import hashlib
import hmac
import threading
from dataclasses import dataclass
from typing import Optional
from src.core.config_loader import config_loader
from src.core.constants import FrameType


@dataclass(frozen=True)
class LRMPFrame:
    """Immutable representation of an LRMP V1.0-R3 transport protocol frame."""
    frame_type: str
    seq: int
    request_id: str
    src_id: str
    dst_id: str
    payload: str
    checksum: str = ""

    def is_valid(self, calculated_checksum: str) -> bool:
        return bool(self.checksum and self.checksum.upper() == calculated_checksum.upper())


class FrameCodec:
    """
    Encodes and decodes LRMP binary/text frames with SEQ, REQUEST_ID, and CRC16/HMAC verification.
    Wire format: [FRAME_TYPE]:[SEQ]:[REQUEST_ID]:[SRC_ID]:[DST_ID]:[PAYLOAD]#[CHECKSUM]
    """

    def __init__(self, hmac_key: str = "LRMP_SECRET_V1") -> None:
        self._lock = threading.Lock()
        self._seq_counter = 0
        self._hmac_key = hmac_key.encode("utf-8")

    def next_seq(self) -> int:
        with self._lock:
            self._seq_counter = (self._seq_counter + 1) & 0xFFFF
            return self._seq_counter

    @staticmethod
    def compute_crc16(content: str) -> str:
        """Calculate standard CRC-16/CCITT checksum string."""
        data = content.encode("utf-8")
        crc = 0xFFFF
        for b in data:
            crc = ((crc >> 8) | (crc << 8)) & 0xFFFF
            crc ^= b
            crc ^= ((crc & 0xFF) >> 4)
            crc ^= ((crc << 12) & 0xFFFF)
            crc ^= (((crc & 0xFF) << 5) & 0xFFFF)
        return f"{crc:04X}"

    def compute_hmac(self, content: str) -> str:
        """Calculate HMAC-SHA256 digest truncated to 8 hex characters."""
        digest = hmac.new(self._hmac_key, content.encode("utf-8"), hashlib.sha256).hexdigest()
        return digest[:8].upper()

    def encode(self, frame: LRMPFrame, use_hmac: bool = False) -> str:
        """Serialize frame to wire string with trailing CRC16 or HMAC checksum."""
        body = (
            f"{frame.frame_type}:{frame.seq}:{frame.request_id}:"
            f"{frame.src_id}:{frame.dst_id}:{frame.payload}"
        )
        checksum = self.compute_hmac(body) if use_hmac else self.compute_crc16(body)
        return f"{body}#{checksum}"

    def decode(self, raw_line: str, use_hmac: bool = False) -> Optional[LRMPFrame]:
        """Deserialize wire string and verify checksum integrity."""
        if not raw_line or "#" not in raw_line:
            return None

        body, checksum = raw_line.strip().rsplit("#", 1)
        expected = self.compute_hmac(body) if use_hmac else self.compute_crc16(body)
        if checksum.upper() != expected:
            return None

        parts = body.split(":", 5)
        if len(parts) < 6:
            return None

        try:
            ftype, seq_str, req_id, src_id, dst_id, payload = parts
            return LRMPFrame(
                frame_type=ftype.upper(),
                seq=int(seq_str),
                request_id=req_id,
                src_id=src_id,
                dst_id=dst_id,
                payload=payload,
                checksum=checksum,
            )
        except Exception:
            return None

    def build_request(self, src_id: str, dst_id: str, payload: str, req_id: Optional[str] = None) -> LRMPFrame:
        """Construct standard REQ frame with auto-incremented SEQ and generated REQUEST_ID."""
        seq = self.next_seq()
        request_id = req_id or f"REQ_{seq:04X}_{binascii.hexlify(payload[:4].encode()).decode()}"
        frame_type = FrameType.REQ.value if hasattr(FrameType, "REQ") else "REQ"
        body = f"{frame_type}:{seq}:{request_id}:{src_id}:{dst_id}:{payload}"
        return LRMPFrame(
            frame_type=frame_type,
            seq=seq,
            request_id=request_id,
            src_id=src_id,
            dst_id=dst_id,
            payload=payload,
            checksum=self.compute_crc16(body),
        )

    def build_response(self, src_id: str, dst_id: str, payload: str, req_id: str, ref_seq: int) -> LRMPFrame:
        """Construct RSP frame corresponding to a request."""
        frame_type = FrameType.RSP.value if hasattr(FrameType, "RSP") else "RSP"
        body = f"{frame_type}:{ref_seq}:{req_id}:{src_id}:{dst_id}:{payload}"
        return LRMPFrame(
            frame_type=frame_type,
            seq=ref_seq,
            request_id=req_id,
            src_id=src_id,
            dst_id=dst_id,
            payload=payload,
            checksum=self.compute_crc16(body),
        )

    def build_event(self, src_id: str, dst_id: str, payload: str, req_id: Optional[str] = None) -> LRMPFrame:
        """Construct EVT asynchronous notification frame."""
        seq = self.next_seq()
        request_id = req_id or f"EVT_{seq:04X}"
        frame_type = FrameType.EVT.value if hasattr(FrameType, "EVT") else "EVT"
        body = f"{frame_type}:{seq}:{request_id}:{src_id}:{dst_id}:{payload}"
        return LRMPFrame(
            frame_type=frame_type,
            seq=seq,
            request_id=request_id,
            src_id=src_id,
            dst_id=dst_id,
            payload=payload,
            checksum=self.compute_crc16(body),
        )

    def build_ack(self, src_id: str, dst_id: str, ref_seq: int, req_id: str) -> LRMPFrame:
        """Construct ACK frame."""
        frame_type = FrameType.ACK.value if hasattr(FrameType, "ACK") else "ACK"
        body = f"{frame_type}:{ref_seq}:{req_id}:{src_id}:{dst_id}:ACK"
        return LRMPFrame(
            frame_type=frame_type,
            seq=ref_seq,
            request_id=req_id,
            src_id=src_id,
            dst_id=dst_id,
            payload="ACK",
            checksum=self.compute_crc16(body),
        )


frame_codec = FrameCodec()
