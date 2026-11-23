# @file: src/protocol/virtual_robot_server.py
# @brief: Local virtual robot HTTP receiver simulating robot-side choreography upload verification and storage.
# @exports: HttpUploadReceipt, VirtualRobotServer

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.paths import get_paths


@dataclass(frozen=True)
class HttpUploadReceipt:
    """Standard receipt returned by either real robot HTTP daemon or local VirtualRobotServer."""

    success: bool
    mode: str  # "VIRTUAL" | "HTTP_REAL"
    robot_ip: str
    target_id: str
    endpoint: str
    sha256: str
    payload_bytes: int
    saved_path: str
    message: str


class VirtualRobotServer:
    """Handles unimplemented robot-side HTTP trajectory upload requests offline."""

    def __init__(self, uploads_dir: Optional[Path] = None) -> None:
        self.uploads_dir = Path(uploads_dir) if uploads_dir else get_paths().http_uploads_dir
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def receive_upload(
        self,
        robot_ip: str,
        target_id: str,
        endpoint: str,
        payload: Dict[str, Any],
    ) -> HttpUploadReceipt:
        """Validate JSON payload schema, persist under runtime/http_uploads, and issue SHA-256 receipt."""
        raw_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        digest = hashlib.sha256(raw_bytes).hexdigest()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_ip = robot_ip.replace(":", "_").replace(".", "_")
        file_path = self.uploads_dir / f"upload_{target_id}_{safe_ip}_{stamp}.json"
        file_path.write_text(raw_bytes.decode("utf-8"), encoding="utf-8")

        return HttpUploadReceipt(
            success=True,
            mode="VIRTUAL",
            robot_ip=robot_ip,
            target_id=target_id,
            endpoint=endpoint,
            sha256=digest,
            payload_bytes=len(raw_bytes),
            saved_path=str(file_path),
            message=f"[虚拟预留接口已确认] 轨迹包已校验并缓存至 {file_path.name}",
        )
