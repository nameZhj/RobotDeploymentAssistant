import os
from flask import Blueprint, jsonify, request
from backend.ssh_client import ssh_manager
from backend.network_manager import network_manager
from backend.deployment_core import deployment_core

bp_system = Blueprint("system_legacy", __name__)


@bp_system.route("/api/status", methods=["GET"])
@bp_system.route("/api/ssh/status", methods=["GET"])
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


@bp_system.route("/api/connect", methods=["POST"])
@bp_system.route("/api/ssh/connect", methods=["POST"])
def connect_robot():
    data = request.json or {}
    host = data.get("host", "192.168.123.164")
    port = int(data.get("port", 22))
    username = data.get("username", "ubuntu")
    password = data.get("password", "123")
    ssh_manager.set_credentials(host, port, username, password)
    ok, msg = ssh_manager.connect(timeout=3.5)
    return jsonify({"success": ok, "msg": msg, "connected": ok})


@bp_system.route("/api/disconnect", methods=["POST"])
def disconnect_robot():
    network_manager.pause_auto_reconnect(15.0)
    ssh_manager.disconnect()
    return jsonify({"success": True, "msg": "已断开与机器人的连接", "connected": False})


@bp_system.route("/api/startup_check", methods=["GET", "POST"])
def startup_check():
    return jsonify({"success": True, "status": "running"})


@bp_system.route("/api/network/interfaces", methods=["GET"])
@bp_system.route("/api/system/interfaces", methods=["GET"])
def get_interfaces():
    return jsonify({"success": True, "interfaces": network_manager.get_local_interfaces()})


@bp_system.route("/api/network/configure_nic", methods=["POST"])
@bp_system.route("/api/system/configure_nic", methods=["POST"])
def configure_nic():
    data = request.get_json() or {}
    nic = data.get("nic_name", "")
    ip = data.get("ip", "192.168.123.200")
    res = network_manager.configure_nic_static(nic, ip=ip)
    return jsonify(res)


@bp_system.route("/api/network/restore_dhcp", methods=["POST"])
@bp_system.route("/api/system/restore_dhcp", methods=["POST"])
def restore_dhcp():
    data = request.get_json() or {}
    nic = data.get("nic_name", "")
    res = network_manager.restore_nic_dhcp(nic)
    return jsonify(res)


@bp_system.route("/api/network/auto_connect", methods=["POST"])
def auto_connect_network():
    data = request.get_json() or {}
    target_ip = data.get("target_ip", "192.168.123.200")
    res = network_manager.auto_heal_nic(target_ip=target_ip)
    return jsonify(res)


@bp_system.route("/api/network/auto_status", methods=["GET"])
def get_network_auto_status():
    return jsonify({
        "success": True,
        "auto_detecting": network_manager.auto_detecting,
        "auto_status_msg": network_manager.last_auto_status_msg,
        "auto_connect_enabled": network_manager.auto_connect_enabled
    })


@bp_system.route("/api/network/toggle_auto", methods=["POST"])
def toggle_auto_detect():
    data = request.get_json() or {}
    enabled = bool(data.get("enabled", True))
    network_manager.set_auto_detect_enabled(enabled)
    return jsonify({"success": True, "enabled": enabled})


@bp_system.route("/api/network/scan", methods=["POST"])
def scan_network_api():
    devices = network_manager.scan_network(timeout=2.0)
    return jsonify({"success": True, "devices": devices, "count": len(devices)})


@bp_system.route("/api/system/check_windows_ch341", methods=["GET"])
def check_win_ch341():
    res = deployment_core.check_windows_ch341()
    return jsonify({"success": True, "data": res})


@bp_system.route("/api/system/install_windows_ch341", methods=["POST"])
def install_win_ch341():
    res = deployment_core.install_windows_ch341()
    return jsonify(res)


@bp_system.route("/api/system/select_file", methods=["POST", "GET"])
def select_local_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected_file = filedialog.askopenfilename(
            title="选择 Docker 镜像文件 (.tar / .tar.gz)",
            filetypes=[("Docker 镜像压缩包", "*.tar.gz;*.tar;*.gz;*.tgz"), ("所有文件", "*.*")]
        )
        root.destroy()
        if selected_file:
            norm_path = os.path.normpath(selected_file)
            size_bytes = os.path.getsize(norm_path)
            return jsonify({
                "success": True, "file_path": norm_path, "filename": os.path.basename(norm_path),
                "size_bytes": size_bytes, "size_gb": round(size_bytes / (1024 * 1024 * 1024), 2)
            })
        return jsonify({"success": False, "msg": "已取消选择文件"})
    except Exception as e:
        return jsonify({"success": False, "msg": f"打开文件选择器失败: {str(e)}"})


@bp_system.route("/api/system/select_folder", methods=["POST", "GET"])
def select_local_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected_dir = filedialog.askdirectory(title="选择舞蹈动作文件夹")
        root.destroy()
        if selected_dir:
            norm_path = os.path.normpath(selected_dir)
            files_count = sum(len(files) for _, _, files in os.walk(norm_path))
            return jsonify({
                "success": True, "folder_path": norm_path, "folder_name": os.path.basename(norm_path),
                "files_count": files_count
            })
        return jsonify({"success": False, "msg": "已取消选择文件夹"})
    except Exception as e:
        return jsonify({"success": False, "msg": f"打开文件夹选择器失败: {str(e)}"})


@bp_system.route("/api/logs", methods=["GET"])
def get_logs():
    return jsonify({"success": True, "logs": []})


@bp_system.route("/api/system/open-studio", methods=["POST", "GET"])
def launch_studio_gui():
    try:
        import subprocess, sys
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(base_dir, "studio.py")
        subprocess.Popen([sys.executable, script], cwd=base_dir)
        return jsonify({"success": True, "msg": "正在启动专业演播控制台..."})
    except Exception as e:
        return jsonify({"success": False, "msg": f"启动演播控制台失败: {str(e)}"})
