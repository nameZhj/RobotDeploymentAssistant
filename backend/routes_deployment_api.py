import os
import time
import queue
import threading
from flask import Blueprint, jsonify, request
from backend.ssh_client import ssh_manager
from backend.deployment_core import deployment_core
from backend.license_service import license_service
from backend.task_stream import stream_queues, push_stream_msg, stream_events_handler

bp_deployment_api = Blueprint("deployment_api", __name__)


@bp_deployment_api.route("/api/precheck", methods=["GET"])
def run_precheck():
    res = deployment_core.run_environment_precheck()
    return jsonify({"success": True, "data": res})


@bp_deployment_api.route("/api/fix/ch341", methods=["POST"])
@bp_deployment_api.route("/api/fix/lora", methods=["POST"])
def fix_lora():
    task_id = f"fix_lora_{int(time.time())}"
    stream_queues[task_id] = queue.Queue()

    def _worker():
        ok = deployment_core.fix_lora_environment(lambda l, e: push_stream_msg(task_id, l, e))
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@bp_deployment_api.route("/api/fix/docker", methods=["POST"])
def fix_docker():
    task_id = f"fix_docker_{int(time.time())}"
    stream_queues[task_id] = queue.Queue()

    def _worker():
        ok = deployment_core.fix_lora_environment(lambda l, e: push_stream_msg(task_id, l, e))
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@bp_deployment_api.route("/api/images/list", methods=["GET"])
def list_images():
    code, out, _ = ssh_manager.execute_command("docker images --format '{{.Repository}}:{{.Tag}}'", sudo=True)
    imgs = [i.strip() for i in out.strip().splitlines() if i.strip()] if code == 0 else []
    return jsonify({"success": True, "images": imgs, "available_images": imgs, "all_images": imgs})


@bp_deployment_api.route("/api/containers/list", methods=["GET"])
def list_containers():
    code, out, _ = ssh_manager.execute_command("docker ps -a --format '{{.Names}}|{{.Status}}'", sudo=True)
    clist = [line.strip().split("|")[0] for line in out.strip().splitlines() if line.strip()] if code == 0 else []
    return jsonify({"success": True, "containers": clist})


@bp_deployment_api.route("/api/images/upload", methods=["POST"])
def upload_image():
    data = request.json if request.is_json else request.form.to_dict()
    data = data or {}
    local_path = data.get("local_path", "").strip().strip('"').strip("'")
    if not local_path and "file" in request.files:
        f = request.files["file"]
        if f and f.filename:
            up_dir = os.path.join(os.path.dirname(__file__), "..", "runtime", "cache")
            os.makedirs(up_dir, exist_ok=True)
            local_path = os.path.join(up_dir, f.filename)
            f.save(local_path)

    if not local_path or not os.path.exists(local_path):
        return jsonify({"success": False, "msg": "本地镜像文件不存在"})

    filename = os.path.basename(local_path)
    remote_path = data.get("remote_path") or f"/home/ubuntu/{filename}"
    threading.Thread(target=lambda: ssh_manager.upload_file(local_path, remote_path), daemon=True).start()
    return jsonify({"success": True, "msg": "镜像上传已开始", "remote_path": remote_path})


@bp_deployment_api.route("/api/images/cancel_upload", methods=["POST"])
def cancel_upload():
    return jsonify(ssh_manager.cancel_upload())


@bp_deployment_api.route("/api/images/upload_progress", methods=["GET"])
def get_upload_progress():
    return jsonify(ssh_manager.upload_progress)


@bp_deployment_api.route("/api/images/load", methods=["POST"])
def load_image():
    data = request.json or {}
    remote_path = data.get("remote_tar_path", "/home/ubuntu/rl_cu118.tar.gz")
    task_id = f"docker_load_{int(time.time())}"
    stream_queues[task_id] = queue.Queue()

    def _worker():
        ok, msg = deployment_core.load_docker_image(remote_path, lambda l, e: push_stream_msg(task_id, l, e))
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@bp_deployment_api.route("/api/container/status", methods=["GET"])
def get_container_status():
    return jsonify({"success": True, "data": deployment_core.check_container_and_autostart_status()})


@bp_deployment_api.route("/api/container/start", methods=["POST"])
def start_container_route():
    data = request.json or {}
    img = data.get("image_name", "rl_cu118:2.0")
    task_id = f"docker_start_{int(time.time())}"
    stream_queues[task_id] = queue.Queue()

    def _worker():
        ok, msg = deployment_core.start_container(img, lambda l, e: push_stream_msg(task_id, l, e))
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@bp_deployment_api.route("/api/container/stop", methods=["POST"])
def stop_container_route():
    code, _, _ = ssh_manager.execute_command("docker stop vsis_g1", sudo=True)
    return jsonify({"success": code == 0, "msg": "容器已停止" if code == 0 else "停止容器失败"})


@bp_deployment_api.route("/api/container/restart", methods=["POST"])
def restart_container_route():
    code, _, _ = ssh_manager.execute_command("docker restart vsis_g1", sudo=True)
    return jsonify({"success": code == 0, "msg": "容器已重启" if code == 0 else "重启容器失败"})


@bp_deployment_api.route("/api/container/autostart", methods=["POST"])
def config_autostart():
    data = request.json or {}
    robot_id = data.get("robot_id", "A")
    res = deployment_core.configure_autostart_and_robot_id(robot_id)
    return jsonify(res)


@bp_deployment_api.route("/api/robot/check_env", methods=["POST"])
def check_robot_env():
    task_id = f"check_env_{int(time.time())}"
    stream_queues[task_id] = queue.Queue()

    def _worker():
        res = deployment_core.check_and_fix_robot_environment(lambda l, e: push_stream_msg(task_id, l, e))
        ok = res.get("success", False) and res.get("has_valid_id", False)
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@bp_deployment_api.route("/api/robot/process_status", methods=["GET"])
def get_robot_proc_status():
    return jsonify(deployment_core.get_robot_process_status())


@bp_deployment_api.route("/api/robot/start_processes", methods=["POST"])
@bp_deployment_api.route("/api/robot/start_process", methods=["POST"])
def start_robot_processes_route():
    task_id = f"robot_proc_start_{int(time.time())}"
    stream_queues[task_id] = queue.Queue()

    def _worker():
        ok, msg = deployment_core.start_robot_processes(lambda l, e: push_stream_msg(task_id, l, e))
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@bp_deployment_api.route("/api/robot/stop_processes", methods=["POST"])
@bp_deployment_api.route("/api/robot/stop_process", methods=["POST"])
def stop_robot_processes_route():
    ok, msg = deployment_core.stop_robot_processes()
    return jsonify({"success": ok, "msg": msg})


@bp_deployment_api.route("/api/license/status", methods=["GET"])
def get_license_status():
    if not ssh_manager.is_connected():
        return jsonify({"connected": False, "has_license": False, "license_valid": False, "msg": "未连接至机器人"})
    return jsonify(license_service.check_remote_license_status())


@bp_deployment_api.route("/api/machine_id", methods=["GET"])
def get_machine_id():
    return jsonify(deployment_core.read_machine_id())


@bp_deployment_api.route("/api/license/parse_and_verify", methods=["POST"])
def verify_license():
    data = request.json or {}
    content = data.get("content", "")
    if "file" in request.files:
        content = request.files["file"].read().decode("utf-8", errors="ignore")
    parsed = license_service.parse_license_content(content)
    if not parsed.get("success"):
        return jsonify(parsed)
    verified = license_service.verify_license(parsed["data"], data.get("current_machine_id", ""))
    return jsonify({"success": True, "parsed": parsed["data"], "verification": verified})


@bp_deployment_api.route("/api/license/deploy", methods=["POST"])
def deploy_license():
    data = request.json or {}
    content = data.get("content", "")
    if "file" in request.files:
        content = request.files["file"].read().decode("utf-8", errors="ignore")
    return jsonify(license_service.deploy_license_to_robot(content))


@bp_deployment_api.route("/api/stream/<task_id>")
def stream_events(task_id):
    return stream_events_handler(task_id)

