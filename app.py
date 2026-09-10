import os
import sys
import json
import time
import queue
import logging
import threading
import zipfile
from flask import Flask, request, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS

from backend.ssh_client import ssh_manager
from backend.network_manager import network_manager
from backend.deployment_core import deployment_core
from backend.license_service import license_service
from backend.dance_updater import dance_updater
from backend.npz_service import npz_service
from backend.preview_manager import preview_manager
from backend.log_diagnostics import log_diagnostics
from backend.serial_manager import serial_manager


# 禁用 Werkzeug 频繁的 HTTP Access 请求日志输出，避免控制台刷屏
werkzeug_log = logging.getLogger("werkzeug")
werkzeug_log.setLevel(logging.ERROR)
werkzeug_log.disabled = True

logger = logging.getLogger("app")

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
WEB_DIR = os.path.join(BASE_DIR, "web")

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="", template_folder=WEB_DIR)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
CORS(app)


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

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
    return render_template("index.html")


@app.route("/preview/<path:filename>")
def serve_preview_asset(filename):
    return send_from_directory(preview_manager.preview_dir, filename)


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
        "latency_ms": latency,
        "auto_detecting": network_manager.auto_detecting,
        "auto_status_msg": network_manager.last_auto_status_msg,
        "auto_connect_enabled": network_manager.auto_connect_enabled
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
    network_manager.pause_auto_reconnect(15.0)
    ssh_manager.disconnect()
    return jsonify({"success": True, "msg": "已断开连接（已暂停自动重连 15 秒）"})


@app.route("/api/startup_check", methods=["GET", "POST"])
def startup_check():
    """
    启动自检：
    1. 若未连接，自动尝试连接默认预置参数 (192.168.123.164:22, unitree, 123)
    2. 检查远端 License 授权与机器码是否匹配，以及容器是否正常运行
    3. 返回 first_time 判定结果（True=进入一键部署向导，False=直接进入群控运行模式）
    """
    if not ssh_manager.is_connected():
        network_manager.auto_detect_and_connect(force_configure_nic=True, timeout=2.0)

    status_res = license_service.check_remote_license_status()
    latency = ssh_manager.test_latency() if ssh_manager.is_connected() else -1.0
    status_res["latency_ms"] = latency
    status_res["host"] = ssh_manager.host
    status_res["port"] = ssh_manager.port
    status_res["username"] = ssh_manager.username
    status_res["auto_detecting"] = network_manager.auto_detecting
    status_res["auto_status_msg"] = network_manager.last_auto_status_msg
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


@app.route("/api/network/auto_connect", methods=["POST"])
def auto_detect_and_connect_api():
    """
    一键断网自愈与自动连接机器人网络：
    1. 自愈本地网卡（若未配置 192.168.123.x 则自动将直连网卡设为 192.168.123.200）
    2. 并发探测并自动连接机器人
    """
    data = request.json or {}
    force_nic = data.get("force_nic", True)
    res = network_manager.auto_detect_and_connect(force_configure_nic=force_nic, timeout=2.5)
    return jsonify(res)


@app.route("/api/network/auto_status", methods=["GET"])
def get_auto_network_status():
    return jsonify({
        "auto_connect_enabled": network_manager.auto_connect_enabled,
        "auto_detecting": network_manager.auto_detecting,
        "last_msg": network_manager.last_auto_status_msg,
        "connected": ssh_manager.is_connected(),
        "host": ssh_manager.host
    })


@app.route("/api/network/toggle_auto", methods=["POST"])
def toggle_auto_network():
    data = request.json or {}
    enabled = data.get("enabled", True)
    network_manager.auto_connect_enabled = bool(enabled)
    return jsonify({"success": True, "auto_connect_enabled": network_manager.auto_connect_enabled})


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
@app.route("/api/fix/lora", methods=["POST"])
def fix_lora():
    task_id = f"fix_lora_{int(time.time())}"
    q = queue.Queue()
    stream_queues[task_id] = q

    def _worker():
        def _cb(line, is_err):
            push_stream_msg(task_id, line, is_err)

        ok = deployment_core.fix_lora_environment(_cb)
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
    res = deployment_core.list_docker_images()
    return jsonify({
        "success": True,
        "images": res.get("available_images", []),
        "available_images": res.get("available_images", []),
        "all_images": res.get("all_images", []),
        "running_containers": res.get("running_containers", [])
    })


@app.route("/api/containers/list", methods=["GET"])
def list_containers():
    containers = deployment_core.list_containers()
    return jsonify({"success": True, "containers": containers})


@app.route("/api/images/upload", methods=["POST"])
def upload_image():
    """接收上传镜像文件或指定本地绝对路径"""
    user_remote_path = ""
    if request.is_json:
        data = request.json or {}
        local_path = data.get("local_path", "").strip()
        user_remote_path = data.get("remote_path", "").strip()
    else:
        data = request.form
        local_path = data.get("local_path", "").strip()
        user_remote_path = data.get("remote_path", "").strip()

    local_path = local_path.strip('"').strip("'")
    user_remote_path = user_remote_path.strip('"').strip("'")

    # 若通过 HTTP 表单文件上传
    if not local_path and "file" in request.files:
        f = request.files["file"]
        if f and f.filename:
            upload_temp_dir = os.path.join(os.path.dirname(__file__), "temp_uploads")
            os.makedirs(upload_temp_dir, exist_ok=True)
            local_path = os.path.join(upload_temp_dir, f.filename)
            f.save(local_path)

    if not local_path or not os.path.exists(local_path):
        return jsonify({"success": False, "msg": f"本地镜像文件不存在: {local_path or '未选择文件'}，请检查路径"})

    if not ssh_manager.is_connected():
        conn_ok, msg = ssh_manager.connect()
        if not conn_ok:
            return jsonify({"success": False, "msg": f"未连接至机器人 (192.168.123.164): {msg}，请先在顶部连接机器人"})

    filename = os.path.basename(local_path)
    file_size = os.path.getsize(local_path)

    # 优先采用用户指定或文档要求的精确路径，未指定时默认存放于 /home/ubuntu/{filename}
    remote_path = user_remote_path if user_remote_path else f"/home/ubuntu/{filename}"

    # 确保远端父目录存在并具备完全读写权限
    remote_dir = os.path.dirname(remote_path).replace("\\", "/")
    if remote_dir and remote_dir != "/":
        ssh_manager.execute_command(f"mkdir -p '{remote_dir}' && chmod a+rwx '{remote_dir}' 2>/dev/null", sudo=True)

    # 上传前精确检查远端目标路径下是否存在完全相同的镜像包 (大小与文件名一致)
    code_stat, out_stat, _ = ssh_manager.execute_command(f"stat -c %s '{remote_path}' 2>/dev/null", sudo=True)
    if code_stat == 0 and out_stat.strip().isdigit() and int(out_stat.strip()) == file_size:
        logger.info(f"远端已存在完全同名同大小镜像包 ({round(file_size/(1024*1024), 2)} MB): {remote_path}，跳过重复上传，直接就绪")
        ssh_manager.upload_progress.update({
            "is_uploading": False,
            "filename": filename,
            "transferred_bytes": file_size,
            "total_bytes": file_size,
            "percent": 100.0,
            "speed_mbps": 0.0,
            "eta_seconds": 0,
            "status": "completed",
            "error_msg": "",
        })
        return jsonify({
            "success": True,
            "msg": f"远端已存在完全同名同大小的镜像包 ({round(file_size/(1024*1024), 2)} MB)，已自动跳过上传直接就绪！",
            "remote_path": remote_path,
            "local_path": local_path,
            "skipped": True
        })

    # 重置取消标记并预设上传中状态
    ssh_manager.cancel_upload_flag = False
    ssh_manager.upload_progress.update({
        "is_uploading": True,
        "filename": filename,
        "transferred_bytes": 0,
        "total_bytes": file_size,
        "percent": 0.0,
        "speed_mbps": 0.0,
        "eta_seconds": 0,
        "status": "uploading",
        "error_msg": "",
    })

    def _worker():
        ssh_manager.upload_file(local_path, remote_path)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "msg": "镜像上传任务已启动", "remote_path": remote_path, "local_path": local_path})


@app.route("/api/system/select_file", methods=["POST", "GET"])
def select_local_file():
    """打开 Windows 原生文件选择器获取镜像文件的真实绝对路径"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected_file = filedialog.askopenfilename(
            title="选择机器人 Docker 镜像文件 (.tar / .tar.gz)",
            filetypes=[
                ("Docker 镜像压缩包", "*.tar.gz;*.tar;*.gz;*.tgz"),
                ("所有文件", "*.*")
            ]
        )
        root.destroy()
        if selected_file:
            norm_path = os.path.normpath(selected_file)
            size_bytes = os.path.getsize(norm_path)
            return jsonify({
                "success": True,
                "file_path": norm_path,
                "filename": os.path.basename(norm_path),
                "size_bytes": size_bytes,
                "size_gb": round(size_bytes / (1024 * 1024 * 1024), 2)
            })
        return jsonify({"success": False, "msg": "已取消选择文件"})
    except Exception as e:
        return jsonify({"success": False, "msg": f"打开文件选择器失败: {str(e)}"})


@app.route("/api/system/select_folder", methods=["POST", "GET"])
def select_local_folder():
    """打开 Windows 原生文件夹选择器获取动作文件夹的绝对路径"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected_dir = filedialog.askdirectory(
            title="选择舞蹈动作文件夹 (包含 .vsis 动作模型与配置文件)"
        )
        root.destroy()
        if selected_dir:
            norm_path = os.path.normpath(selected_dir)
            files_count = 0
            total_size = 0
            for root_dir, _, files in os.walk(norm_path):
                for f in files:
                    fp = os.path.join(root_dir, f)
                    total_size += os.path.getsize(fp)
                    files_count += 1
            return jsonify({
                "success": True,
                "folder_path": norm_path,
                "folder_name": os.path.basename(norm_path),
                "files_count": files_count,
                "size_bytes": total_size,
                "size_mb": round(total_size / (1024 * 1024), 2)
            })
        return jsonify({"success": False, "msg": "已取消选择文件夹"})
    except Exception as e:
        return jsonify({"success": False, "msg": f"打开文件夹选择器失败: {str(e)}"})



@app.route("/api/images/cancel_upload", methods=["POST"])
def cancel_upload():
    """取消正在进行的镜像上传"""
    res = ssh_manager.cancel_upload()
    return jsonify(res)


@app.route("/api/images/upload_progress", methods=["GET"])
def get_upload_progress():
    return jsonify(ssh_manager.upload_progress)


@app.route("/api/images/load", methods=["POST"])
def load_image():
    data = request.json or {}
    remote_tar_path = data.get("remote_tar_path", "/home/ubuntu/vsis_dancer_cpu_1.0.tar.gz")
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


@app.route("/api/container/stop", methods=["POST"])
def stop_container_route():
    data = request.json or {}
    container_name = data.get("container_name", "vsis_g1")
    ok, msg = deployment_core.stop_container(container_name)
    return jsonify({"success": ok, "msg": msg})


@app.route("/api/container/restart", methods=["POST"])
def restart_container_route():
    data = request.json or {}
    container_name = data.get("container_name", "vsis_g1")
    ok, msg = deployment_core.restart_container(container_name)
    return jsonify({"success": ok, "msg": msg})


@app.route("/api/container/autostart", methods=["POST"])
def config_autostart():
    data = request.json or {}
    robot_id = data.get("robot_id", "A")
    res = deployment_core.configure_autostart_and_robot_id(robot_id)
    return jsonify(res)


@app.route("/api/robot/check_env", methods=["POST"])
def check_robot_env():
    task_id = f"check_env_{int(time.time())}"
    q = queue.Queue()
    stream_queues[task_id] = q

    def _worker():
        def _cb(line, is_err):
            push_stream_msg(task_id, line, is_err)

        res = deployment_core.check_and_fix_robot_environment(_cb)
        ok = res.get("success", False) and res.get("has_valid_id", False)
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@app.route("/api/robot/process_status", methods=["GET"])
def get_robot_process_status():
    res = deployment_core.get_robot_process_status()
    return jsonify(res)


@app.route("/api/robot/start_processes", methods=["POST"])
@app.route("/api/robot/start_process", methods=["POST"])
def start_robot_processes_route():
    task_id = f"robot_proc_start_{int(time.time())}"
    q = queue.Queue()
    stream_queues[task_id] = q

    def _worker():
        def _cb(line, is_err=False):
            push_stream_msg(task_id, line, is_err)

        ok, msg = deployment_core.start_robot_processes(_cb)
        push_stream_msg(task_id, f"__TASK_DONE__:{ok}\n", False)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id})


@app.route("/api/robot/stop_processes", methods=["POST"])
@app.route("/api/robot/stop_process", methods=["POST"])
def stop_robot_processes_route():
    ok, msg = deployment_core.stop_robot_processes()
    return jsonify({"success": ok, "msg": msg})




# ==========================================
# 5. 机器码与 License 管理 API
# ==========================================
@app.route("/api/license/status", methods=["GET"])
def get_license_status():
    if not ssh_manager.is_connected():
        return jsonify({
            "connected": False,
            "has_license": False,
            "license_valid": False,
            "msg": "未连接至机器人",
            "license_data": {}
        })
    res = license_service.check_remote_license_status()
    return jsonify(res)


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
    task_id = f"dance_update_{int(time.time())}"
    q = queue.Queue()
    stream_queues[task_id] = q

    dest_path = request.form.get("dest_path", "/secure/config_vsis").strip() if request.form else "/secure/config_vsis"
    local_path = ""

    # 1. 检查是否有上传的 .zip 文件或文件夹多文件
    temp_zip_path = None
    upload_file = request.files.get("zip_file") or request.files.get("file") or request.files.get("vsis_file")
    folder_files = request.files.getlist("files")

    temp_dir = os.path.join(os.path.dirname(__file__), "temp_uploads")
    os.makedirs(temp_dir, exist_ok=True)

    if upload_file and upload_file.filename:
        if upload_file.filename.lower().endswith(".zip"):
            temp_zip_path = os.path.join(temp_dir, upload_file.filename)
            upload_file.save(temp_zip_path)
        else:
            # 单个非 zip 文件（如单个 .vsis），打包成 zip
            temp_zip_path = os.path.join(temp_dir, f"{os.path.splitext(upload_file.filename)[0]}.zip")
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(upload_file.filename, upload_file.read())
    elif folder_files and len(folder_files) > 0:
        # 拖拽或选择的整个动作文件夹（包含多个文件）
        paths_list = request.form.getlist("paths")
        temp_zip_path = os.path.join(temp_dir, f"dance_folder_{int(time.time())}.zip")
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for idx, f in enumerate(folder_files):
                if f and f.filename:
                    rel_path = paths_list[idx] if (idx < len(paths_list) and paths_list[idx]) else f.filename
                    rel_path = rel_path.replace("\\", "/").lstrip("/")
                    # 去除多余的顶层包装文件夹名（若有），直接放置模型与配置文件
                    parts = rel_path.split("/")
                    if len(parts) > 1 and parts[0] in ("config_vsis", "mimic_exp2", "mimic", "dances", "secure"):
                        rel_path = "/".join(parts[1:])
                    zf.writestr(rel_path, f.read())
    elif request.is_json:
        data = request.json or {}
        local_path = data.get("local_path", "").strip()
    elif request.form:
        local_path = request.form.get("local_path", "").strip()

    if not temp_zip_path and local_path and os.path.exists(local_path):
        if os.path.isdir(local_path):
            temp_zip_path = os.path.join(temp_dir, f"dance_folder_{int(time.time())}.zip")
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root_dir, _, files in os.walk(local_path):
                    for f in files:
                        abs_f = os.path.join(root_dir, f)
                        rel_path = os.path.relpath(abs_f, local_path).replace("\\", "/")
                        parts = rel_path.split("/")
                        if len(parts) > 1 and parts[0] in ("config_vsis", "mimic_exp2", "mimic", "dances", "secure"):
                            rel_path = "/".join(parts[1:])
                        zf.write(abs_f, rel_path)
        else:
            temp_zip_path = local_path

    if not temp_zip_path or not os.path.exists(temp_zip_path):
        return jsonify({"success": False, "msg": "未检测到上传的动作压缩包或动作文件夹，请选择文件后重试"})



    def _worker():
        def _cb(line, is_err=False):
            push_stream_msg(task_id, line, is_err)

        try:
            if not ssh_manager.is_connected():
                _cb("[ERROR] 未连接至机器人，请先在顶部连接 SSH！\n", True)
                push_stream_msg(task_id, "__TASK_DONE__:False\n", False)
                return

            _cb(f"[STEP 1/2] 🚀 开始导入舞蹈动作包 [{os.path.basename(temp_zip_path)}] ...\n", False)

            # 1. 解压并覆盖至目标目录 /secure/config_vsis
            ok_zip, msg_zip = dance_updater.deploy_zip_package(temp_zip_path, _cb, dest_path=dest_path)
            if not ok_zip:
                _cb(f"[ERROR] 动作包部署失败: {msg_zip}\n", True)
                push_stream_msg(task_id, "__TASK_DONE__:False\n", False)
                return

            # 2. 自动热重启机载进程
            _cb("[STEP 2/2] 🔄 正在自动热重启机载运控与跳舞进程使新配置生效...\n", False)
            ok_restart = dance_updater.restart_control_processes(_cb)
            if ok_restart:
                _cb("[SUCCESS] 🎉 舞蹈动作压缩包导入、解压覆盖与跳舞程序自动热重启已全部圆满完成！\n", False)
                _cb("[READY] 💡 新舞蹈动作已就绪，可随时在群控页面下发指令进行测试。\n", False)
                push_stream_msg(task_id, "__TASK_DONE__:True\n", False)
            else:
                _cb("[WARN] 机载进程重启遇到异常，请在【镜像与容器管理】页面检查运行状态。\n", True)
                push_stream_msg(task_id, "__TASK_DONE__:False\n", False)

        except Exception as e:
            _cb(f"[ERROR] 执行异常: {str(e)}\n", True)
            push_stream_msg(task_id, "__TASK_DONE__:False\n", False)
        finally:
            # 清理临时上传的本地文件
            if temp_zip_path and "temp_uploads" in temp_zip_path and os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except Exception:
                    pass

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"success": True, "task_id": task_id, "filename": os.path.basename(temp_zip_path)})



# 6. 机器人机载运控与通信程序控制 API (已在前文统一声明)



# ==========================================
# 7. 3D 舞蹈回放、模型解析与 preview 管理 API
# ==========================================
@app.route("/api/dance/list_3d", methods=["GET"])
def list_3d_dances():
    dances = preview_manager.list_all_dances()
    return jsonify({"success": True, "dances": dances})


@app.route("/api/dance/get_3d/<dance_id>", methods=["GET"])
def get_3d_dance(dance_id):
    data = preview_manager.get_dance_data(dance_id)
    return jsonify(data)


@app.route("/api/dance/upload_npz", methods=["POST"])
def upload_npz():
    if "file" not in request.files:
        return jsonify({"success": False, "msg": "未检测到上传文件"})
    f = request.files["file"]
    save_path = os.path.join(preview_manager.preview_dir, f.filename)
    f.save(save_path)
    data = npz_service.parse_npz_file(save_path)
    return jsonify(data)


@app.route("/api/dance/import_zip", methods=["POST"])
@app.route("/api/dance/import_file", methods=["POST"])
def import_dance_zip():
    """
    统一导入 3D 舞蹈动捕文件与机器人模型包 (支持 .zip 与 .npz)
    保存/解压至程序运行根目录 preview 文件夹，深度解析模型或动作轨迹并就绪 50fps 仿真播放
    """
    # 场景 1: 上传的文件对象
    if "file" in request.files:
        f = request.files["file"]
        if not f.filename:
            return jsonify({"success": False, "msg": "上传的文件名为空"})
        res = preview_manager.import_zip(f, filename=f.filename)
        return jsonify(res)

    # 场景 2: 本地绝对路径 (如 "E:\\myfile\\...\\g1_29dof_rubber_hand.zip" 或 ".npz")
    data = request.json if request.is_json else request.form.to_dict()
    data = data or {}
    path = data.get("path", "").strip().strip('"').strip("'")
    if not path:
        return jsonify({"success": False, "msg": "未提供文件或本地绝对路径"})

    res = preview_manager.import_zip(path)
    return jsonify(res)


@app.route("/api/dance/browse_zip", methods=["POST"])
@app.route("/api/dance/browse_file", methods=["POST"])
def browse_dance_zip():
    """打开本地文件选择器选取 .zip 或 .npz 舞蹈模型/动捕文件"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        file_path = filedialog.askopenfilename(
            title="选择 3D 机器人模型包 (.zip) 或动作文件 (.npz)",
            filetypes=[
                ("动作或模型文件 (*.zip;*.npz)", "*.zip;*.npz;*.ZIP;*.NPZ"),
                ("ZIP 压缩包 (*.zip)", "*.zip;*.ZIP"),
                ("NPZ 动捕文件 (*.npz)", "*.npz;*.NPZ"),
                ("所有文件", "*.*")
            ]
        )
        root.destroy()
        if file_path:
            norm_path = os.path.normpath(file_path)
            return jsonify({"success": True, "file_path": norm_path, "filename": os.path.basename(norm_path)})
        return jsonify({"success": False, "msg": "用户取消了选择"})
    except Exception as e:
        return jsonify({"success": False, "msg": f"打开文件选择器异常: {str(e)}"})


@app.route("/api/dance/delete_3d/<dance_id>", methods=["DELETE", "POST"])
def delete_3d_dance(dance_id):
    res = preview_manager.delete_dance(dance_id)
    return jsonify(res)


# ==========================================
# 8. 实时日志与智能诊断 API
# ==========================================
@app.route("/api/logs", methods=["GET"])
def get_logs():
    log_type = request.args.get("type", "container")
    container_name = request.args.get("container", "").strip()
    lines = int(request.args.get("lines", 200))
    res = log_diagnostics.fetch_logs(log_type, container_name, lines)
    return jsonify(res)


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
# 9.2 LoRa 广播串口通信与自动检测 API
# ==========================================
@app.route("/api/serial/ports", methods=["GET"])
def get_serial_ports():
    ports = serial_manager.list_ports()
    return jsonify({"success": True, "ports": ports, "count": len(ports)})


@app.route("/api/serial/auto_connect", methods=["POST"])
def auto_connect_serial():
    data = request.json or {}
    baudrate = int(data.get("baudrate", 9600))
    res = serial_manager.auto_connect_best_port(baudrate=baudrate)
    return jsonify(res)


@app.route("/api/serial/connect", methods=["POST"])
def connect_serial():
    data = request.json or {}
    port_name = data.get("port", "")
    baudrate = int(data.get("baudrate", 9600))
    if not port_name:
        return jsonify({"success": False, "msg": "未指定串口名称"})
    res = serial_manager.connect_port(port_name, baudrate=baudrate)
    return jsonify(res)


@app.route("/api/serial/send", methods=["POST"])
def send_serial_cmd():
    data = request.json or {}
    target = data.get("target", "ALL")
    command = data.get("command", "")
    if not command:
        return jsonify({"success": False, "msg": "指令不能为空"})
    res = serial_manager.send_command(target, command)
    return jsonify(res)


@app.route("/api/serial/disconnect", methods=["POST"])
def disconnect_serial():
    data = request.json or {}
    safety = bool(data.get("safety_stop", True))
    res = serial_manager.disconnect(safety_stop=safety)
    return jsonify(res)


@app.route("/api/serial/status", methods=["GET"])
def get_serial_status():
    status = serial_manager.get_status()
    return jsonify({"success": True, "data": status})


@app.route("/api/serial/messages", methods=["GET"])
def get_serial_messages():
    """获取最近由串口产生并接收到的实时 TX/RX 消息字符串"""
    since = float(request.args.get("since", 0.0))
    msgs = serial_manager.get_recent_messages(since_ts=since)
    return jsonify({"success": True, "messages": msgs, "count": len(msgs)})


@app.route("/api/serial/dance_list", methods=["GET", "POST"])
def get_serial_dance_list():
    """获取从串口同步到的最新舞蹈列表"""
    data = request.get_json(silent=True) if request.method == "POST" else {}
    force_refresh = request.args.get("refresh", "0") in ["1", "true", "True"] or bool(data and data.get("refresh"))
    
    if force_refresh and serial_manager.ser is not None and serial_manager.ser.is_open:
        res = serial_manager.request_dance_list(timeout=2.5, force=True)
        return jsonify(res)
        
    res = serial_manager.get_dance_list()
    return jsonify(res)


@app.route("/api/serial/refresh_dance_list", methods=["POST"])
def refresh_serial_dance_list():
    """向串口重新发送 ALL|GETDANCELIST 并返回解析后的舞蹈列表"""
    data = request.get_json(silent=True) or {}
    timeout = float(data.get("timeout", 2.5))
    res = serial_manager.request_dance_list(timeout=timeout, force=True)
    return jsonify(res)


@app.route("/api/serial/parse_dances", methods=["POST"])
def parse_dances_api():
    """解析传入的 YAML 舞蹈配置字符串并返回标准结构化数据"""
    data = request.get_json(silent=True) or {}
    raw_text = data.get("content", "").strip()
    if not raw_text:
        return jsonify({"success": False, "msg": "内容为空", "groups": []})
    
    from backend.serial_manager import parse_dance_map_yaml
    groups = parse_dance_map_yaml(raw_text)
    total_count = sum(len(g.get("items", [])) for g in groups)
    
    # 缓存解析结果
    serial_manager.latest_dance_list_raw = raw_text
    serial_manager.latest_dance_list_parsed = groups
    
    return jsonify({
        "success": True,
        "groups": groups,
        "total_count": total_count,
        "raw": raw_text
    })



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

