# @file: src/api/system_routes.py
# @brief: Sub-router handling /api/v1/system/*, /api/v1/license/*, /api/v1/dance/*, and /api/v1/lora_wifi/* routes.
# @exports: dispatch_system_route

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

if TYPE_CHECKING:
    from src.api.routes import LowerComputerContext


def dispatch_system_route(
    ctx: LowerComputerContext,
    method: str,
    path: str,
    query: Dict[str, list[str]],
    data: Dict[str, Any],
) -> Optional[Tuple[int, Dict[str, Any] | bytes, str]]:
    """Handle system, license, dance package, and LoRa Wi-Fi routes; return None if path not matched."""
    m = method.upper()

    if m == "GET" and path == "/api/v1/system/precheck":
        return 200, ctx.system_ops.run_precheck(), "application/json"

    if m == "GET" and path == "/api/v1/system/machine_id":
        mid = ctx.config_reader.read_machine_id_digest()
        return (200 if mid["available"] else 503), {"ok": mid["available"], **mid}, "application/json"

    if m == "GET" and path == "/api/v1/system/processes":
        return 200, ctx.system_ops.get_process_status(), "application/json"

    if m == "POST" and path == "/api/v1/system/processes":
        res = ctx.system_ops.control_processes(str(data.get("action", "status")))
        return (200 if res["ok"] else 503), res, "application/json"

    if m == "POST" and path == "/api/v1/system/robot_id":
        res = ctx.system_ops.configure_robot_id_and_autostart(
            str(data.get("robot_id", "")), bool(data.get("write_autostart", True))
        )
        return (200 if res["ok"] else 400), res, "application/json"

    if m == "GET" and path == "/api/v1/system/docker":
        return 200, ctx.system_ops.get_docker_status(), "application/json"

    if m == "POST" and path == "/api/v1/system/container":
        res = ctx.system_ops.control_container(
            str(data.get("action", "")), str(data.get("container_name", "vsis_g1"))
        )
        return (200 if res["ok"] else 400), res, "application/json"

    if m == "GET" and path == "/api/v1/system/logs":
        log_type = query.get("type", ["sec_run"])[0]
        container = query.get("container", ["vsis_g1"])[0]
        try:
            lines = int(query.get("lines", ["200"])[0] or "200")
        except (ValueError, TypeError):
            return 400, {"ok": False, "message": "lines 参数必须为整数"}, "application/json"
        res = ctx.system_ops.fetch_logs(log_type=log_type, lines=lines, container=container)
        return (200 if res["ok"] else 404), res, "application/json"

    if m == "GET" and path == "/api/v1/system/clock":
        return 200, ctx.system_ops.clock_status(), "application/json"

    if m == "GET" and path == "/api/v1/license/status":
        lic = ctx.config_reader.read_license_summary()
        return 200, {"ok": lic["present"], **lic}, "application/json"

    if m == "POST" and path == "/api/v1/license/deploy":
        content = data.get("content") or data.get("license") or ""
        res = ctx.system_ops.deploy_license(content)
        return (200 if res["ok"] else 400), res, "application/json"

    if m == "POST" and path == "/api/v1/actions/register":
        res = ctx.system_ops.register_dance_alias(
            str(data.get("alias", "")),
            str(data.get("select_key", "")),
            str(data.get("action_key", "")),
            str(data.get("comment", "")),
        )
        return (200 if res["ok"] else 400), res, "application/json"

    if m == "POST" and path == "/api/v1/dance/deploy":
        b64 = str(data.get("zip_base64", "")).strip()
        if not b64:
            return 400, {"ok": False, "message": "缺少 zip_base64 动作压缩包数据"}, "application/json"
        try:
            raw_zip = base64.b64decode(b64)
        except Exception as ex:
            return 400, {"ok": False, "message": f"Base64 解码失败: {ex}"}, "application/json"
        res = ctx.system_ops.deploy_dance_zip_bytes(raw_zip)
        return (200 if res["ok"] else 400), res, "application/json"

    if m == "POST" and path == "/api/v1/lora_wifi/command":
        cmd = str(data.get("command", ""))
        params = [str(p) for p in (data.get("params") or [])]
        res = ctx.lora_wifi.handle_lora_wifi_command(cmd, params)
        return (200 if res["ok"] else 400), res, "application/json"

    return None
