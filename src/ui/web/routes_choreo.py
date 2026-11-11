import json
import time
from pathlib import Path
from flask import Blueprint, jsonify, request
from src.core.config_loader import config_loader
from src.domain.arbitration.control_arbiter import control_arbiter
from src.core.constants import ControlAuthority
from src.domain.choreo.plan_manifest_model import (
    ChoreoPlanManifest, RobotChoreoTrack, MotionClipSegment, BarrierSyncMarker
)
from src.domain.choreo.immutable_plan_compiler import ImmutablePlanCompiler
from src.infrastructure.serial.lora_serial_port import lora_port

bp_choreo = Blueprint("choreo_v2", __name__, url_prefix="/api/v2/choreo")


def _get_projects_dir() -> Path:
    paths = config_loader.get_paths()
    p = Path(paths.get("projects_dir", "runtime/choreo_projects"))
    p.mkdir(parents=True, exist_ok=True)
    return p


@bp_choreo.route("/compile", methods=["POST"])
def compile_choreo_plan():
    """Compile choreography plan into immutable artifact with plan_id."""
    data = request.get_json() or {}
    plan_name = data.get("name", "UntitledPlan")
    locked_robots = tuple(data.get("locked_robots", ["A", "B"]))

    manifest = ChoreoPlanManifest(plan_name=plan_name, locked_robot_aliases=locked_robots)

    tracks_data = data.get("tracks", {})
    for alias, track_info in tracks_data.items():
        if alias in manifest.tracks:
            t = manifest.tracks[alias]
            for c in track_info.get("clips", []):
                t.add_clip(MotionClipSegment(
                    clip_id=c.get("clip_id", f"c_{len(t.clips)}"),
                    action_name=c.get("action", "WAVE"),
                    start_ms=int(c.get("start_ms", 0)),
                    duration_ms=int(c.get("duration_ms", 3000)),
                    speed_scale=float(c.get("speed", 1.0))
                ))

    for b in data.get("barriers", []):
        manifest.barriers.append(BarrierSyncMarker(
            barrier_id=b.get("barrier_id", f"b_{len(manifest.barriers)}"),
            target_time_ms=int(b.get("time_ms", 5000)),
            participating_aliases=tuple(b.get("robots", list(locked_robots))),
            timeout_ms=int(b.get("timeout_ms", 5000))
        ))

    try:
        compiled = ImmutablePlanCompiler.compile(manifest)
        return jsonify({
            "success": True,
            "plan_id": compiled.plan_id,
            "content_hash": compiled.content_hash,
            "total_duration_ms": manifest.total_duration_ms,
            "steps": {k: list(v) for k, v in compiled.robot_steps.items()}
        })
    except Exception as exc:
        return jsonify({"success": False, "msg": str(exc)}), 400


@bp_choreo.route("/prep", methods=["POST"])
def prepare_choreo_cohort():
    """Dispatch PREP command and acquire CHOREO authority for locked robots."""
    data = request.get_json() or {}
    robots = data.get("robots", ["A", "B"])
    plan_id = data.get("plan_id", "PLAN_0001")

    for r in robots:
        control_arbiter.request_authority(r, ControlAuthority.CHOREO, "CHOREO_PREP")
        cmd = f"{r}|PREP,{plan_id}"
        lora_port.send_raw(cmd, src_id="CTRL", dst_id=r)

    return jsonify({"success": True, "msg": f"Dispatched PREP for {robots}"})


@bp_choreo.route("/play", methods=["POST"])
def execute_synchronized_play():
    """Broadcast synchronized T0 PLAY command to locked robots."""
    data = request.get_json() or {}
    robots = data.get("robots", ["A", "B"])
    delay_ms = int(data.get("delay_ms", 3000))
    t0_ms = int(time.time() * 1000) + delay_ms

    for r in robots:
        cmd = f"{r}|PLAY,{t0_ms}"
        lora_port.send_raw(cmd, src_id="CTRL", dst_id=r)

    return jsonify({
        "success": True,
        "t0_ms": t0_ms,
        "delay_ms": delay_ms,
        "msg": f"Synchronized PLAY scheduled at T0={t0_ms}"
    })


@bp_choreo.route("/stop", methods=["POST"])
def emergency_stop_choreo():
    """Broadcast STOP and release choreo control."""
    data = request.get_json() or {}
    robots = data.get("robots", ["ALL"])

    for r in robots:
        lora_port.send_raw(f"{r}|STOP", src_id="CTRL", dst_id=r)
        control_arbiter.handle_stop(r)

    return jsonify({"success": True, "msg": "Emergency STOP dispatched, control revoked."})


@bp_choreo.route("/projects", methods=["GET"])
def list_choreo_projects():
    """List saved choreo projects from runtime directory."""
    p_dir = _get_projects_dir()
    files = [f.name for f in p_dir.glob("*.json")]
    return jsonify({"success": True, "projects": files})


@bp_choreo.route("/save", methods=["POST"])
def save_choreo_project():
    """Save choreo project manifest to disk."""
    data = request.get_json() or {}
    name = (data.get("name") or "project").strip().replace(" ", "_")
    filepath = _get_projects_dir() / f"{name}.json"
    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify({"success": True, "filename": filepath.name})


@bp_choreo.route("/load", methods=["GET"])
def load_choreo_project():
    """Load choreo project manifest from disk."""
    filename = request.args.get("name", "")
    if not filename:
        return jsonify({"success": False, "msg": "Name required"}), 400
    filepath = _get_projects_dir() / filename
    if not filepath.exists():
        return jsonify({"success": False, "msg": "File not found"}), 404
    data = json.loads(filepath.read_text(encoding="utf-8"))
    return jsonify({"success": True, "project": data})
