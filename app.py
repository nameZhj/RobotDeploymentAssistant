import os
import sys
import json
import time
import queue
import logging
import threading
from flask import Flask, request, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS

from backend.ssh_client import ssh_manager
from backend.network_manager import network_manager
from backend.deployment_core import deployment_core
from backend.license_service import license_service
from backend.dance_updater import dance_updater
from backend.npz_service import npz_service
from backend.log_diagnostics import log_diagnostics


# 禁用 Werkzeug 频繁的 HTTP Access 请求日志输出，避免控制台刷屏
werkzeug_log = logging.getLogger("werkzeug")
werkzeug_log.setLevel(logging.ERROR)
werkzeug_log.disabled = True

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
WEB_DIR = os.path.join(BASE_DIR, "web")

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")
CORS(app)

# 动态任务事件输出队列
stream_queues = {}


def push_stream_msg(task_id: str, text: str, is_err: bool = False):
    if task_id in stream_queues:
        stream_queues[task_id].put({"text": text, "is_err": is_err, "time": time.time()})


# ==========================================
# 静态资源与前端页面路由
# ==========================================
@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(WEB_DIR, path)


# ==========================================
# 1. 状态与连接管理 API
# ==========================================
@app.route("/api/status", methods=["GET"])
def get_status():
    is_conn = ssh_manager.is_connected()
    latency = ssh_manager.test_latency() if is_conn else -1.0
    return jsonify({
        "connected": is_conn,
        "host": ssh_manager.host,
        "port": ssh_manager.port,
        "username": ssh_manager.username,
        "latency_ms": latency
    })


@app.route("/api/connect", methods=["POST"])
def connect_robot():
    data = request.json or {}
    host = data.get("host", "192.168.123.164")
    port = int(data.get("port", 22))
    username = data.get("username", "unitree")
    password = data.get("password", "123")

    ssh_manager.set_credentials(host, port, username, password)
    ok, msg = ssh_manager.connect(timeout=3.5)
    return jsonify({"success": ok, "msg": msg, "connected": ok})


@app.route("/api/disconnect", methods=["POST"])
def disconnect_robot():
    ssh_manager.disconnect()
    return jsonify({"success": True, "msg": "已断开连接"})


@app.route("/api/startup_check", methods=["GET", "POST"])
def startup_check():
    """
    启动自检：
    1. 若未连接，自动尝试连接默认预置参数 (192.168.123.164:22, unitree, 123)
    2. 检查远端 License 授权与机器码是否匹配，以及容器是否正常运行
    3. 返回 first_time 判定结果（True=进入一键部署向导，False=直接进入群控运行模式）
    """
    if not ssh_manager.is_connected():
        ssh_manager.connect(timeout=2.5)

    status_res = license_service.check_remote_license_status()
    latency = ssh_manager.test_latency() if ssh_manager.is_connected() else -1.0
    status_res["latency_ms"] = latency
    status_res["host"] = ssh_manager.host
    status_res["port"] = ssh_manager.port
    status_res["username"] = ssh_manager.username
    return jsonify(status_res)


# ==========================================
# 2. 网络扫描与 Windows 网卡直连配置 API
# ==========================================
@app.route("/api/network/interfaces", methods=["GET"])
def get_interfaces():
    nics = network_manager.get_local_interfaces()
    return jsonify({"success": True, "interfaces": nics})


@app.route("/api/network/configure_nic", methods=["POST"])
def configure_nic():
    data = request.json or {}
    nic_name = data.get("nic_name", "")
    ip = data.get("ip", "192.168.123.200")
    netmask = data.get("netmask", "255.255.255.0")
    gateway = data.get("gateway", "192.168.123.1")
    if not nic_name:
        return jsonify({"success": False, "msg": "未指定网卡名称"})

    res = network_manager.configure_nic_static(nic_name, ip, netmask, gateway)
    return jsonify(res)


@app.route("/api/network/restore_dhcp", methods=["POST"])
def restore_dhcp():
    data = request.json or {}
    nic_name = data.get("nic_name", "")
    if not nic_name:
        return jsonify({"success": False, "msg": "未指定网卡名称"})

    res = network_manager.configure_nic_dhcp(nic_name)
    return jsonify(res)


@app.route("/api/network/scan", methods=["POST"])
def scan_network():
    data = request.json or {}
    subnet = data.get("subnet", "192.168.123.")
    devices = network_manager.scan_network(target_subnet=subnet)
    return jsonify({"success": True, "devices": devices, "count": len(devices)})


# ==========================================
# 3. 环境预检与一键修复 API
# ==========================================
@app.route("/api/precheck", methods=["GET"])
def run_precheck():
    res = deployment_core.run_environment_precheck()
    return jsonify({"success": True, "data": res})


@app.route("/api/fix/ch341", methods=["POST"])
def fix_ch341():
    task_id = f"fix_ch341_{int(time.time())}"
    q = queue.Queue()
    stream_queues[task_id] = q

    def _worker():
        def _cb(line, is_err):
            push_stream_msg(task_id, line, is_err)

        ok = deployment_core.fix_ch341_driver(_cb)
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@app.route("/api/fix/docker", methods=["POST"])
def fix_docker():
    task_id = f"fix_docker_{int(time.time())}"
    q = queue.Queue()
    stream_queues[task_id] = q

    def _worker():
        def _cb(line, is_err):
            push_stream_msg(task_id, line, is_err)

        ok = deployment_core.fix_docker(_cb)
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


# ==========================================
# 4. 镜像管理、固化容器启动与自启动 API
# ==========================================
@app.route("/api/images/list", methods=["GET"])
def list_images():
    imgs = deployment_core.list_docker_images()
    return jsonify({"success": True, "images": imgs})


@app.route("/api/images/upload", methods=["POST"])
def upload_image():
    """接收上传镜像文件或指定本地绝对路径"""
    data = request.form
    local_path = data.get("local_path", "").strip()

    # 若通过 HTTP 表单文件上传
    if "file" in request.files:
        f = request.files["file"]
        upload_temp_dir = os.path.join(os.path.dirname(__file__), "temp_uploads")
        os.makedirs(upload_temp_dir, exist_ok=True)
        local_path = os.path.join(upload_temp_dir, f.filename)
        f.save(local_path)

    if not local_path or not os.path.exists(local_path):
        return jsonify({"success": False, "msg": "本地镜像文件不存在，请检查路径"})

    filename = os.path.basename(local_path)
    remote_path = f"/tmp/{filename}"

    def _worker():
        ssh_manager.upload_file(local_path, remote_path)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "msg": "镜像上传任务已启动", "remote_path": remote_path, "local_path": local_path})


@app.route("/api/images/upload_progress", methods=["GET"])
def get_upload_progress():
    return jsonify(ssh_manager.upload_progress)


@app.route("/api/images/load", methods=["POST"])
def load_image():
    data = request.json or {}
    remote_tar_path = data.get("remote_tar_path", "/tmp/rl_cu118_v2.tar.gz")
    task_id = f"docker_load_{int(time.time())}"
    q = queue.Queue()
    stream_queues[task_id] = q

    def _worker():
        def _cb(line, is_err):
            push_stream_msg(task_id, line, is_err)

        ok, msg = deployment_core.load_docker_image(remote_tar_path, _cb)
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@app.route("/api/container/status", methods=["GET"])
def get_container_status():
    res = deployment_core.check_container_and_autostart_status()
    return jsonify({"success": True, "data": res})


@app.route("/api/container/start", methods=["POST"])
def start_container():
    data = request.json or {}
    image_name = data.get("image_name", "rl_cu118:2.0")
    task_id = f"docker_start_{int(time.time())}"
    q = queue.Queue()
    stream_queues[task_id] = q

    def _worker():
        def _cb(line, is_err):
            push_stream_msg(task_id, line, is_err)

        ok, msg = deployment_core.start_container(image_name, _cb)
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@app.route("/api/container/autostart", methods=["POST"])
def config_autostart():
    data = request.json or {}
    robot_id = data.get("robot_id", "A")
    res = deployment_core.configure_autostart_and_robot_id(robot_id)
    return jsonify(res)


# ==========================================
# 5. 机器码与 License 管理 API
# ==========================================
@app.route("/api/machine_id", methods=["GET"])
def get_machine_id():
    res = deployment_core.read_machine_id()
    return jsonify(res)


@app.route("/api/license/parse_and_verify", methods=["POST"])
def verify_license():
    data = request.json or {}
    content_str = data.get("content", "")
    curr_mid = data.get("current_machine_id", "")

    if "file" in request.files:
        f = request.files["file"]
        content_str = f.read().decode("utf-8", errors="ignore")

    parsed = license_service.parse_license_content(content_str)
    if not parsed.get("success"):
        logging.error(f"[API License 校验失败] {parsed.get('msg')}")
        return jsonify(parsed)

    verified = license_service.verify_license(parsed["data"], curr_mid)
    if not verified.get("is_match"):
        logging.error(f"[API License 比对未通过] {verified.get('msg')} (实机: {curr_mid} vs 授权: {verified.get('license_machine_id')})")
    else:
        logging.info(f"[API License 比对通过] 授权有效，客户: {verified.get('customer')}, 舞蹈: {verified.get('dance_count')} 支")

    return jsonify({
        "success": True,
        "parsed": parsed["data"],
        "verification": verified
    })


@app.route("/api/license/deploy", methods=["POST"])
def deploy_license():
    data = request.json or {}
    content_str = data.get("content", "")
    if "file" in request.files:
        f = request.files["file"]
        content_str = f.read().decode("utf-8", errors="ignore")

    if not content_str.strip():
        return jsonify({"success": False, "msg": "License 内容为空"})

    res = license_service.deploy_license_to_robot(content_str)
    return jsonify(res)


# ==========================================
# 6. 舞蹈更新与热重启 API
# ==========================================
@app.route("/api/dance/update", methods=["POST"])
def update_dance():
    dance_alias = request.form.get("dance_alias", "").strip().upper()
    button_group = request.form.get("button_group", "R1").strip().upper()
    button_action = request.form.get("button_action", "SELECT").strip().upper()
    dest_path = request.form.get("dest_path", "/secure/config_vsis/mimic_exp2").strip()

    # 处理 .vsis 文件上传
    if "vsis_file" in request.files:
        vsis_f = request.files["vsis_file"]
        temp_path = os.path.join(os.path.dirname(__file__), "temp_uploads", vsis_f.filename)
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        vsis_f.save(temp_path)
        ok_vsis, msg_vsis = dance_updater.deploy_vsis_file(temp_path, dest_path)
        if not ok_vsis:
            return jsonify({"success": False, "msg": msg_vsis})

    # 处理新 license.json
    if "license_file" in request.files:
        lic_f = request.files["license_file"]
        lic_content = lic_f.read().decode("utf-8", errors="ignore")
        license_service.deploy_license_to_robot(lic_content)

    # 更新 YAML dance_map
    if dance_alias:
        dance_updater.update_dance_map(dance_alias, button_group, button_action)

    return jsonify({
        "success": True,
        "msg": f"舞蹈 [{dance_alias}] 更新包已部署完毕！"
    })


@app.route("/api/dance/restart_processes", methods=["POST"])
def restart_dance_processes():
    task_id = f"restart_dance_{int(time.time())}"
    q = queue.Queue()
    stream_queues[task_id] = q

    def _worker():
        def _cb(line, is_err):
            push_stream_msg(task_id, line, is_err)

        ok = dance_updater.restart_control_processes(_cb)
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


# ==========================================
# 7. 3D 舞蹈回放与 NPZ 解析 API
# ==========================================
@app.route("/api/dance/list_3d", methods=["GET"])
def list_3d_dances():
    dances = npz_service.list_demo_dances()
    return jsonify({"success": True, "dances": dances})


@app.route("/api/dance/get_3d/<dance_id>", methods=["GET"])
def get_3d_dance(dance_id):
    filename = f"{dance_id}.npz" if not dance_id.endswith(".npz") else dance_id
    npz_path = os.path.join(npz_service.demo_dir, filename)
    data = npz_service.parse_npz_file(npz_path)
    return jsonify(data)


@app.route("/api/dance/upload_npz", methods=["POST"])
def upload_npz():
    if "file" not in request.files:
        return jsonify({"success": False, "msg": "未检测到上传文件"})
    f = request.files["file"]
    save_path = os.path.join(npz_service.demo_dir, f.filename)
    f.save(save_path)
    data = npz_service.parse_npz_file(save_path)
    return jsonify(data)


@app.route("/api/dance/delete_3d/<dance_id>", methods=["DELETE", "POST"])
def delete_3d_dance(dance_id):
    filename = f"{dance_id}.npz" if not dance_id.endswith(".npz") else dance_id
    npz_path = os.path.join(npz_service.demo_dir, filename)
    if os.path.exists(npz_path):
        try:
            os.remove(npz_path)
            return jsonify({"success": True, "msg": f"已删除舞蹈动作: {filename}"})
        except Exception as e:
            return jsonify({"success": False, "msg": f"删除失败: {str(e)}"})
    return jsonify({"success": False, "msg": "文件不存在"})


# ==========================================
# 8. 实时日志与智能诊断 API
# ==========================================
@app.route("/api/logs", methods=["GET"])
def get_logs():
    log_type = request.args.get("type", "container")
    lines = int(request.args.get("lines", 150))
    res = log_diagnostics.fetch_logs(log_type, lines)
    return jsonify(res)


# ==========================================
# 9. 手动模式与命令执行 API
# ==========================================
@app.route("/api/manual/execute", methods=["POST"])
def execute_manual_command():
    data = request.json or {}
    cmd = data.get("command", "")
    sudo = bool(data.get("sudo", False))
    if not cmd.strip():
        return jsonify({"success": False, "msg": "命令为空"})

    code, out, err = ssh_manager.execute_command(cmd, sudo=sudo, timeout=60.0)
    return jsonify({
        "success": (code == 0),
        "exit_code": code,
        "stdout": out,
        "stderr": err
    })


# ==========================================
# 9.1 Windows 本机 CH341 串口驱动 API
# ==========================================
@app.route("/api/system/check_windows_ch341", methods=["GET"])
def check_windows_ch341():
    res = deployment_core.check_windows_ch341()
    return jsonify({"success": True, "data": res})


@app.route("/api/system/install_windows_ch341", methods=["POST"])
def install_windows_ch341():
    res = deployment_core.install_windows_ch341()
    return jsonify(res)


# ==========================================
# 10. SSE 流式任务执行输出
# ==========================================
@app.route("/api/stream/<task_id>")
def stream_events(task_id):
    if task_id not in stream_queues:
        return Response("Task not found", status=404)

    def event_stream():
        q = stream_queues[task_id]
        while True:
            try:
                msg = q.get(timeout=30.0)
                text = msg["text"]
                is_err = msg["is_err"]
                yield f"data: {json.dumps({'text': text, 'is_err': is_err})}\n\n"
                if "__TASK_DONE__" in text:
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'text': '', 'ping': True})}\n\n"

        # 清理队列
        stream_queues.pop(task_id, None)

    return Response(event_stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8088, debug=False)
