# @file: src/protocol/http_trajectory_client.py
# @brief: Dual-mode HTTP client for uploading trajectory/choreography JSON packages to robots with virtual fallback.
# @exports: HttpTrajectoryClient

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, List, Optional
from urllib import request as urlrequest

from src.core.settings import get_settings
from src.protocol.virtual_robot_server import HttpUploadReceipt, VirtualRobotServer


class HttpTrajectoryClient:
    """Uploads per-robot or cluster trajectory JSON packages via HTTP or VirtualRobotServer."""

    ENDPOINT_PATH = "/api/v1/lrmp/choreography/upload"

    def __init__(self, virtual_server: Optional[VirtualRobotServer] = None) -> None:
        self.virtual_server = virtual_server or VirtualRobotServer()

    def upload_payload(
        self,
        robot_ip: str,
        target_id: str,
        payload: Dict[str, Any],
        port: Optional[int] = None,
        prefer_virtual: Optional[bool] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> HttpUploadReceipt:
        """Attempt HTTP POST upload or route cleanly through reserved VirtualRobotServer."""
        cfg = get_settings().virtual_interfaces
        use_port = port or cfg.http_default_port
        use_virtual = cfg.http_upload_virtual_fallback if prefer_virtual is None else prefer_virtual
        endpoint = f"http://{robot_ip}:{use_port}{self.ENDPOINT_PATH}"

        if progress_cb:
            progress_cb(20, f"打包轨迹与 SHA-256 校验 ({target_id})...")

        raw_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(raw_bytes).hexdigest()

        if not use_virtual:
            try:
                req = urlrequest.Request(
                    endpoint,
                    data=raw_bytes,
                    headers={"Content-Type": "application/json", "X-LRMP-Target": target_id},
                    method="POST",
                )
                with urlrequest.urlopen(req, timeout=cfg.http_upload_timeout_s) as resp:
                    if progress_cb:
                        progress_cb(100, f"实机 HTTP 响应 {resp.status}")
                    return HttpUploadReceipt(
                        success=200 <= resp.status < 300,
                        mode="HTTP_REAL",
                        robot_ip=robot_ip,
                        target_id=target_id,
                        endpoint=endpoint,
                        sha256=digest,
                        payload_bytes=len(raw_bytes),
                        saved_path="",
                        message=f"实机 HTTP 上传成功 (HTTP {resp.status})",
                    )
            except Exception as ex:
                if not cfg.http_upload_virtual_fallback:
                    return HttpUploadReceipt(
                        success=False,
                        mode="HTTP_REAL",
                        robot_ip=robot_ip,
                        target_id=target_id,
                        endpoint=endpoint,
                        sha256=digest,
                        payload_bytes=len(raw_bytes),
                        saved_path="",
                        message=f"实机 HTTP 接口暂不可达（{ex}）",
                    )

        if progress_cb:
            progress_cb(65, f"路由至预留虚拟 HTTP 接口 ({robot_ip}:{use_port})...")
        receipt = self.virtual_server.receive_upload(robot_ip, target_id, endpoint, payload)
        if progress_cb:
            progress_cb(100, receipt.message)
        return receipt

    def upload_cluster_payloads(
        self,
        per_robot_items: List[Dict[str, Any]],
        prefer_virtual: Optional[bool] = None,
    ) -> List[HttpUploadReceipt]:
        """Sequentially upload payloads for multiple robot tracks and collect receipts."""
        receipts: List[HttpUploadReceipt] = []
        for entry in per_robot_items:
            receipts.append(
                self.upload_payload(
                    robot_ip=str(entry.get("robotIp", "192.168.123.101")),
                    target_id=str(entry.get("targetId", "A")),
                    payload=entry.get("payload", {}),
                    prefer_virtual=prefer_virtual,
                )
            )
        return receipts
