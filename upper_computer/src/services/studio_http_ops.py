# @file: src/services/studio_http_ops.py
# @brief: Wi-Fi HTTP operations for action sync, fleet health, task-chain upload/prep/start, barrier, stop-to-origin, and commands (all blocking; run via BackgroundTaskRunner).
# @exports: sync_actions_from_http_op, fleet_health_op, dispatch_command_http_op, dispatch_targets_http_op, compile_and_upload_chains_http_op, start_task_chains_http_op, barrier_task_chains_http_op, stop_all_robots_to_origin_http_op

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from src.core.event_bus import StudioEvent
from src.protocol.robot_http_client import RobotHttpClient
from src.services.task_chain_normalizer import compile_track_chain_payload

if TYPE_CHECKING:
    from src.services.studio_state_service import StudioStateService


def sync_actions_from_http_op(svc: StudioStateService) -> Tuple[bool, int, str]:
    """Fetch onboard action/dance registry via Wi-Fi HTTP GET /api/v1/actions/list."""
    if not svc.tracks:
        msg = "请先添加至少一台机器人轨道并配置其无线 Wi-Fi IP"
        svc.notify(msg, "warn")
        return False, 0, msg

    groups: list = []
    last_err = ""
    for tr in svc.tracks:
        if not tr.robot_ip:
            continue
        resp = svc.http_rpc.fetch_actions(tr.robot_ip)
        if resp.ok and resp.data.get("groups"):
            groups = list(resp.data.get("groups") or [])
            break
        last_err = resp.message

    if not groups:
        svc.action_repo.clear_serial_actions()
        svc.bus.publish(StudioEvent.ACTION_LIB_UPDATED, None)
        msg = f"Wi-Fi HTTP 未获取到机载动作库 ({last_err or '请检查下位机 HTTP 服务'})"
        svc.notify(msg, "warn")
        return False, 0, msg

    cnt = svc.action_repo.replace_serial_actions(groups)
    svc.bus.publish(StudioEvent.ACTION_LIB_UPDATED, None)
    msg = f"已通过 Wi-Fi HTTP 同步 {cnt} 个真实机载动作"
    svc.notify(msg, "ok")
    return True, cnt, msg


def fleet_health_op(svc: StudioStateService, timeout_s: float = 1.2) -> Dict[str, RobotHttpResponse]:
    """Probe GET /api/v1/health on every configured track in parallel; keyed by upper-cased target_id."""
    fast_client = RobotHttpClient(timeout_s=timeout_s)
    targets = [tr for tr in svc.tracks if (tr.robot_ip or "").strip()]

    def _probe(tr):
        return tr.target_id.upper(), fast_client.health(tr.robot_ip)

    results: Dict[str, RobotHttpResponse] = {}
    if not targets:
        return results
    with ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool:
        for tid, resp in pool.map(_probe, targets):
            results[tid] = resp
    return results


def dispatch_command_http_op(
    svc: StudioStateService,
    target_id: str,
    command: str,
    params: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Send a single LRMP/control command to target robot over Wi-Fi HTTP."""
    norm = target_id.strip().upper()
    tr = next((t for t in svc.tracks if t.target_id.upper() == norm), None)
    if tr is None:
        return {"ok": False, "message": f"未找到目标机器人 [{norm}]"}
    resp = svc.http_rpc.send_command(tr.robot_ip, norm, command, params or [])
    return {
        "ok": resp.ok,
        "status_code": resp.status_code,
        "endpoint": resp.endpoint,
        "message": resp.message,
        "data": resp.data,
    }


def compile_and_upload_chains_http_op(
    svc: StudioStateService,
    plan_id: str = "8001",
    run_id: str = "9001",
    prep: bool = True,
) -> List[Dict[str, Any]]:
    """Upload sequential task chains and optionally PREP each active track via Wi-Fi HTTP."""
    actions_by_id = {a.id: a for a in svc.action_repo.list_actions() if a.id is not None}
    results: List[Dict[str, Any]] = []
    for tr in svc.tracks:
        if tr.muted:
            continue
        payload = compile_track_chain_payload(
            tr, svc.blocks, svc.trajectories, svc.sampled_trajs, actions_by_id,
            scene_id=svc.scene.id or 1, plan_id=plan_id,
        )
        up = svc.http_rpc.upload_task_chain(tr.robot_ip, tr.target_id, payload)
        item: Dict[str, Any] = {
            "target_id": tr.target_id,
            "robot_ip": tr.robot_ip,
            "upload_ok": up.ok,
            "prep_ok": False,
            "status_code": up.status_code,
            "message": up.message,
        }
        if up.ok and prep:
            cb_url = svc.callback_listener.callback_url_for(tr.robot_ip)
            pr = svc.http_rpc.prep_task_chain(tr.robot_ip, run_id, callback_url=cb_url)
            item["prep_ok"] = pr.ok
            item["status_code"] = pr.status_code
            item["message"] = pr.message
        results.append(item)
    return results


def start_task_chains_http_op(svc: StudioStateService, run_id: str = "9001") -> List[Dict[str, Any]]:
    """Start uploaded task chains on all active tracks over Wi-Fi HTTP with live callback URL."""
    results: List[Dict[str, Any]] = []
    for tr in svc.tracks:
        if tr.muted:
            continue
        cb_url = svc.callback_listener.callback_url_for(tr.robot_ip)
        res = svc.http_rpc.start_task_chain(tr.robot_ip, run_id, callback_url=cb_url)
        results.append({
            "target_id": tr.target_id,
            "robot_ip": tr.robot_ip,
            "ok": res.ok,
            "status_code": res.status_code,
            "message": res.message,
        })
    return results


def barrier_task_chains_http_op(svc: StudioStateService, run_id: str, barrier_id: str = "1") -> List[Dict[str, Any]]:
    """Release the named barrier on every unmuted track in parallel over Wi-Fi HTTP."""
    fast_client = RobotHttpClient(timeout_s=2.5)
    targets = [tr for tr in svc.tracks if not tr.muted]

    def _release(tr):
        res = fast_client.barrier_task_chain(tr.robot_ip, run_id, barrier_id=barrier_id)
        return {"target_id": tr.target_id, "robot_ip": tr.robot_ip, "ok": res.ok, "message": res.message}

    if not targets:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool:
        return list(pool.map(_release, targets))


def dispatch_targets_http_op(
    svc: StudioStateService, commands: List[Tuple[str, str, List[str]]]
) -> List[Dict[str, Any]]:
    """Send one LRMP command per target (e.g. EMERGENCY) in parallel; order inside the list is preserved."""
    fast_client = RobotHttpClient(timeout_s=2.5)

    def _send(item):
        target_id, cmd, params = item
        resp = fast_client.send_command(
            _robot_ip_of(svc, target_id), target_id.strip().upper(), cmd, params or []
        )
        return {
            "target_id": target_id,
            "robot_ip": _robot_ip_of(svc, target_id),
            "ok": resp.ok,
            "status_code": resp.status_code,
            "message": resp.message,
            "data": resp.data,
        }

    if not commands:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(commands))) as pool:
        return list(pool.map(_send, commands))


def _robot_ip_of(svc: StudioStateService, target_id: str) -> str:
    norm = target_id.strip().upper()
    tr = next((t for t in svc.tracks if t.target_id.upper() == norm), None)
    return (tr.robot_ip if tr else "") or ""


def stop_all_robots_to_origin_http_op(svc: StudioStateService) -> List[Dict[str, Any]]:
    """Send HTTP stop + return_to_origin=(init_x, init_y, init_yaw) to every robot track in parallel."""
    if not svc.tracks:
        return []
    fast_client = RobotHttpClient(timeout_s=1.5)

    def _stop_one(tr) -> Dict[str, Any]:
        origin = {"x": float(tr.init_x), "y": float(tr.init_y), "yaw": float(tr.init_yaw)}
        cb_url = svc.callback_listener.callback_url_for(tr.robot_ip)
        res = fast_client.stop_and_return_origin(tr.robot_ip, origin, callback_url=cb_url)
        return {
            "target_id": tr.target_id,
            "robot_ip": tr.robot_ip,
            "ok": res.ok,
            "status_code": res.status_code,
            "message": res.message,
        }

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(svc.tracks)))) as pool:
        return list(pool.map(_stop_one, svc.tracks))
