# @file: src/api/slam_routes.py
# @brief: Dynamic ROS discovery, live SLAM telemetry, binary Float32 cloud, relocalization, and PCD map routes.
# @exports: dispatch_slam_route

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

if TYPE_CHECKING:
    from src.api.routes import LowerComputerContext


def _sync_tap_from_cli_if_idle(ctx: LowerComputerContext) -> None:
    st = ctx.slam_tap.get_live_state()
    if ctx.slam_tap.is_streaming() or (st.get("state_seq", 0) > 0 and st.get("tap_mode") == "external"):
        return
    if not ctx.ros_bridge.is_ros_master_reachable():
        if st.get("ros_available") is not False:
            ctx.slam_tap.push_external_frame(
                ros_available=False, tap_mode="offline", reason=f"ROS Master ({ctx.cfg.ros_master_uri}) 不可达"
            )
        return
    snap = ctx.ros_bridge.read_telemetry_snapshot()
    if not snap.ros_available:
        ctx.slam_tap.push_external_frame(ros_available=False, tap_mode="offline", reason=snap.reason)
        return
    pose_dict = {"x": snap.pose[0], "y": snap.pose[1], "yaw": snap.pose[2]} if snap.pose else None
    diag = ctx.ros_bridge.diagnostics
    gpath = [[p["x"], p["y"]] for p in diag.read_global_path()[:120]]
    scan_res = diag.read_cad_scan_summary(snap.pose)
    scan_xy = scan_res.get("points_xy", []) if scan_res.get("ok") else []
    ctx.slam_tap.push_external_frame(
        pose=pose_dict, confidence=snap.localization_confidence, delay_ms=snap.localization_delay_ms,
        nav_status=snap.local_nav_status, global_path=gpath, scan_xy=scan_xy,
        ros_available=True, tap_mode="cli_sync", reason=snap.reason,
    )


def _handle_pcd_upload(
    ctx: LowerComputerContext, query: Dict[str, list[str]], data: Dict[str, Any]
) -> Tuple[int, Dict[str, Any], str]:
    raw_bytes = data.get("_raw_bytes")
    if raw_bytes is None and isinstance(data.get("pcd_base64"), str):
        try:
            raw_bytes = base64.b64decode(data["pcd_base64"])
        except Exception as ex:
            return 400, {"ok": False, "message": f"pcd_base64 解码失败: {ex}"}, "application/json"
    if not isinstance(raw_bytes, (bytes, bytearray)) or len(raw_bytes) == 0:
        return 400, {"ok": False, "message": "未收到有效的 .pcd 二进制内容"}, "application/json"
    head_txt = bytes(raw_bytes[:1024]).decode("ascii", errors="ignore").upper()
    if "POINTS" not in head_txt and "FIELDS" not in head_txt and "VERSION" not in head_txt:
        return 400, {"ok": False, "message": "文件头不符合 PCD 格式（缺少 VERSION/FIELDS/POINTS 字段）"}, "application/json"

    raw_name = str(data.get("filename") or query.get("filename", ["uploaded_map.pcd"])[0] or "uploaded_map.pcd")
    safe_name = Path(raw_name).name
    if not safe_name.lower().endswith(".pcd"):
        safe_name += ".pcd"
    restart_flag = str(data.get("restart_localization", query.get("restart_localization", ["0"])[0])).lower() in ("1", "true", "yes")
    discovered = ctx.discovery.discover_pcd_maps()
    search_dirs = discovered.get("search_dirs") or []
    target_dir = Path(search_dirs[0]) if search_dirs else ctx.cfg.maps_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / safe_name
    tmp_path = target_dir / f".{safe_name}.uploading"
    tmp_path.write_bytes(bytes(raw_bytes))
    tmp_path.replace(target_path)
    digest = hashlib.sha256(raw_bytes).hexdigest()

    navctl_res = None
    if restart_flag:
        res = ctx.navctl.execute("restart localization")
        navctl_res = res.to_dict()
        if res.ok:
            ctx.discovery.discover_topics(force=True)
            ctx.slam_tap.start()
    return 200, {
        "ok": True, "saved_path": str(target_path), "filename": safe_name,
        "size_bytes": len(raw_bytes), "sha256": digest,
        "message": f"PCD 地图已写入机载目录: {target_path}" + ("（已触发重启定位）" if restart_flag else ""),
        "restarted": bool(restart_flag and navctl_res and navctl_res.get("ok")),
        "navctl_result": navctl_res,
    }, "application/json"


def _handle_relocalize(ctx: LowerComputerContext, data: Dict[str, Any]) -> Tuple[int, Dict[str, Any], str]:
    mode = str(data.get("mode", "auto") or "auto").strip().lower()
    pose: Optional[Tuple[float, float, float]] = None
    if "x" in data and "y" in data and data["x"] is not None and data["y"] is not None:
        try:
            pose = (float(data["x"]), float(data["y"]), float(data.get("yaw", 0.0)))
        except (ValueError, TypeError):
            return 400, {"ok": False, "message": "重定位坐标 x/y/yaw 必须为数值"}, "application/json"
    fb = data.get("fallback_pose")
    fb_pose: Optional[Tuple[float, float, float]] = None
    if isinstance(fb, dict) and "x" in fb and "y" in fb:
        try:
            fb_pose = (float(fb["x"]), float(fb["y"]), float(fb.get("yaw", 0.0)))
        except (ValueError, TypeError):
            fb_pose = None
    try:
        min_conf = float(data.get("min_confidence", 0.65))
        timeout_s = float(data.get("timeout_s", 6.0))
    except (ValueError, TypeError):
        return 400, {"ok": False, "message": "min_confidence/timeout_s 必须为数值"}, "application/json"
    allow_restart = bool(data.get("allow_restart", True))
    res = ctx.safety.trigger_relocalize(
        mode=mode, pose=pose, fallback_pose=fb_pose, min_confidence=min_conf,
        timeout_s=timeout_s, allow_restart=allow_restart, emit_webhook=True,
    )
    return int(res.get("status_code", 200)), res, "application/json"


def dispatch_slam_route(
    ctx: LowerComputerContext, method: str, path: str, query: Dict[str, list[str]], data: Dict[str, Any],
) -> Optional[Tuple[int, Dict[str, Any] | bytes, str]]:
    """Handle /api/v1/navigation/* (discovery, relocalize) and /api/v1/slam/* routes."""
    m = method.upper()
    if m == "POST" and path == "/api/v1/navigation/relocalize":
        return _handle_relocalize(ctx, data)
    if m == "POST" and path == "/api/v1/slam/map/upload":
        return _handle_pcd_upload(ctx, query, data)
    if m == "GET" and path == "/api/v1/navigation/discovery":
        ep = ctx.discovery.discover_topics(force=True)
        maps_info = ctx.discovery.discover_pcd_maps()
        return 200, {
            "ok": True, "ros_master_reachable": ctx.ros_bridge.is_ros_master_reachable(),
            "streaming_active": ctx.slam_tap.is_streaming(), "endpoints": ep.to_dict(), "maps": maps_info,
        }, "application/json"
    if m == "GET" and path == "/api/v1/slam/live_state":
        _sync_tap_from_cli_if_idle(ctx)
        st = ctx.slam_tap.get_live_state()
        return 200, {"ok": bool(st.get("ros_available", False)), **st}, "application/json"
    if m == "GET" and path == "/api/v1/slam/live_cloud":
        try:
            since_seq = int(query.get("since_seq", ["0"])[0] or "0")
            max_pts = int(query.get("max_points", ["30000"])[0] or "30000")
        except (ValueError, TypeError):
            return 400, {"ok": False, "message": "since_seq/max_points 必须为整数"}, "application/json"
        _seq, cnt, raw = ctx.slam_tap.get_live_cloud_bytes(since_seq=since_seq, max_points=max_pts)
        return (200, raw, "application/octet-stream") if (cnt > 0 and raw) else (204, b"", "application/octet-stream")
    if m == "GET" and path == "/api/v1/slam/maps":
        return 200, ctx.discovery.discover_pcd_maps(), "application/json"
    if m == "GET" and path == "/api/v1/slam/map.pcd":
        req_path = query.get("path", [""])[0]
        target = Path(req_path) if req_path else None
        if target is None or not target.exists():
            discovered = ctx.discovery.discover_pcd_maps().get("maps") or []
            target = Path(discovered[0]["path"]) if discovered else None
        if target is None or not target.exists():
            return 404, {"ok": False, "message": f"未在动态搜索目录 ({', '.join(ctx.discovery.current.map_search_dirs) or ctx.cfg.maps_dir}) 找到真实 .pcd 文件"}, "application/json"
        return 200, target.read_bytes(), "application/octet-stream"
    return None
