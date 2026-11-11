import os
import time
import queue
import threading
import zipfile
from flask import Blueprint, jsonify, request
from backend.serial_manager import serial_manager, parse_dance_map_yaml
from backend.fleet_manager import fleet_manager
from backend.dance_updater import dance_updater
from backend.task_stream import stream_queues, push_stream_msg

bp_motion = Blueprint("motion_legacy", __name__)


@bp_motion.route("/api/serial/ports", methods=["GET"])
def get_serial_ports():
    ports = serial_manager.list_ports()
    return jsonify({"success": True, "ports": ports, "count": len(ports)})


@bp_motion.route("/api/serial/auto_connect", methods=["POST"])
def auto_connect_serial():
    data = request.json or {}
    baud = int(data.get("baudrate", 9600))
    return jsonify(serial_manager.auto_connect_best_port(baudrate=baud))


@bp_motion.route("/api/serial/connect", methods=["POST"])
def connect_serial():
    data = request.json or {}
    port = data.get("port", "")
    baud = int(data.get("baudrate") or data.get("baud") or 9600)
    if not port:
        return jsonify({"success": False, "msg": "未指定串口名称"})
    return jsonify(serial_manager.connect_port(port, baudrate=baud))


@bp_motion.route("/api/serial/disconnect", methods=["POST"])
def disconnect_serial():
    data = request.json or {}
    safety = bool(data.get("safety_stop", True))
    return jsonify(serial_manager.disconnect(safety_stop=safety))


@bp_motion.route("/api/serial/send", methods=["POST"])
def send_serial_cmd():
    data = request.json or {}
    target = data.get("target", "ALL")
    cmd = data.get("command", "")
    if not cmd:
        return jsonify({"success": False, "msg": "指令不能为空"})
    return jsonify(serial_manager.send_command(target, cmd))


@bp_motion.route("/api/serial/status", methods=["GET"])
def get_serial_status():
    return jsonify({"success": True, "data": serial_manager.get_status()})


@bp_motion.route("/api/serial/messages", methods=["GET"])
def get_serial_messages():
    since = float(request.args.get("since", 0.0))
    msgs = serial_manager.get_recent_messages(since_ts=since)
    return jsonify({"success": True, "messages": msgs, "count": len(msgs)})


@bp_motion.route("/api/serial/dance_list", methods=["GET", "POST"])
def get_serial_dance_list():
    target = request.args.get("target") or (request.get_json(silent=True) or {}).get("target")
    data = request.get_json(silent=True) if request.method == "POST" else {}
    force = request.args.get("refresh", "0") in ["1", "true", "True"] or bool(data and data.get("refresh"))
    if force and serial_manager.ser is not None and getattr(serial_manager.ser, "is_open", False):
        return jsonify(serial_manager.request_dance_list(timeout=2.5, force=True, target=target or "ALL"))

    raw = serial_manager.latest_dance_list_raw
    if target and target.upper() != "ALL" and "|" in raw:
        from backend.serial_dance_parser import parse_multi_robot_dance_map, intersect_dance_groups
        multi = parse_multi_robot_dance_map(raw)
        targets = [t.strip().upper() for t in target.split(",") if t.strip()]
        if len(targets) == 1:
            r_groups = multi.get(targets[0], [])
        else:
            subset = {t: multi.get(t, []) for t in targets if t in multi}
            r_groups = intersect_dance_groups(subset) if subset else []
        total = sum(len(g.get("items", [])) for g in r_groups)
        return jsonify({"success": True, "groups": r_groups, "total_count": total, "raw": raw})

    return jsonify(serial_manager.get_dance_list())


@bp_motion.route("/api/serial/refresh_dance_list", methods=["POST"])
def refresh_serial_dance_list():
    data = request.get_json(silent=True) or {}
    timeout = float(data.get("timeout", 2.5))
    return jsonify(serial_manager.request_dance_list(timeout=timeout, force=True))


@bp_motion.route("/api/serial/parse_dances", methods=["POST"])
def parse_dances_api():
    data = request.get_json(silent=True) or {}
    raw_text = data.get("content", "").strip()
    if not raw_text:
        return jsonify({"success": False, "msg": "内容为空", "groups": []})
    groups = parse_dance_map_yaml(raw_text)
    total_count = sum(len(g.get("items", [])) for g in groups)
    serial_manager.latest_dance_list_raw = raw_text
    serial_manager.latest_dance_list_parsed = groups
    return jsonify({"success": True, "groups": groups, "total_count": total_count, "raw": raw_text})


@bp_motion.route("/api/fleet", methods=["GET", "POST"])
def fleet_endpoint():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        robots = data.get("robots", [])
        selected = data.get("selected", [])
        res = fleet_manager.save_fleet(robots, selected)
        return jsonify(res)
    res = fleet_manager.load_fleet()
    return jsonify(res)


@bp_motion.route("/api/dance/update", methods=["POST"])
def update_dance():
    upload_file = request.files.get("zip_file") or request.files.get("file")
    folder_files = request.files.getlist("files")
    local_path = (request.form.get("local_path") or (request.get_json(silent=True) or {}).get("local_path") or "").strip()
    if not upload_file and not folder_files and (not local_path or not os.path.exists(local_path)):
        return jsonify({"success": False, "msg": "未检测到上传文件或指定路径"})

    task_id = f"dance_update_{int(time.time())}"
    stream_queues[task_id] = queue.Queue()
    dest_path = request.form.get("dest_path", "/secure/config_vsis").strip() if request.form else "/secure/config_vsis"

    temp_dir = os.path.join(os.path.dirname(__file__), "..", "runtime", "cache")
    os.makedirs(temp_dir, exist_ok=True)
    temp_zip_path = None

    if upload_file and upload_file.filename:
        temp_zip_path = os.path.join(temp_dir, upload_file.filename)
        upload_file.save(temp_zip_path)
    elif local_path and os.path.exists(local_path):
        if os.path.isdir(local_path):
            temp_zip_path = os.path.join(temp_dir, f"{os.path.basename(local_path)}.zip")
            with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root_dir, _, files in os.walk(local_path):
                    for f in files:
                        fp = os.path.join(root_dir, f)
                        zf.write(fp, os.path.relpath(fp, local_path))
        elif local_path.lower().endswith(".zip"):
            temp_zip_path = local_path

    def _worker():
        try:
            if not temp_zip_path or not os.path.exists(temp_zip_path):
                push_stream_msg(task_id, "[ERROR] 动作包不存在\n", True)
                push_stream_msg(task_id, "__TASK_DONE__:False\n", False)
                return
            ok_zip, _ = dance_updater.deploy_zip_package(temp_zip_path, lambda l, e: push_stream_msg(task_id, l, e), dest_path)
            if ok_zip:
                dance_updater.restart_control_processes(lambda l, e: push_stream_msg(task_id, l, e))
                push_stream_msg(task_id, "__TASK_DONE__:True\n", False)
            else:
                push_stream_msg(task_id, "__TASK_DONE__:False\n", False)
        finally:
            if temp_zip_path and os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except Exception:
                    pass

    threading.Thread(target=_worker, daemon=True).start()
    fname = os.path.basename(temp_zip_path) if temp_zip_path else ""
    return jsonify({"success": True, "task_id": task_id, "filename": fname})
