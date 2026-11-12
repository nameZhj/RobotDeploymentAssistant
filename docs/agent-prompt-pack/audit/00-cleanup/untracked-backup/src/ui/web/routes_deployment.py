from flask import Blueprint, jsonify, request
from src.application.deployment_service import deployment_service
from src.infrastructure.drivers.ch341_installer import ch341_installer
from src.infrastructure.network.interface_tool import interface_tool
from src.infrastructure.ssh.remote_ssh_channel import ssh_channel

bp_deployment = Blueprint("deployment", __name__, url_prefix="/api/deployment")


@bp_deployment.route("/ssh_connect", methods=["POST"])
def ssh_connect():
    data = request.get_json() or {}
    host = data.get("host", "192.168.123.164")
    port = int(data.get("port", 22))
    username = data.get("username", "ubuntu")
    password = data.get("password", "123")

    ok, msg = ssh_channel.connect(host, port, username, password)
    return jsonify({"success": ok, "msg": msg})


@bp_deployment.route("/ssh_status", methods=["GET"])
def ssh_status():
    return jsonify({"connected": ssh_channel.is_connected})


@bp_deployment.route("/env_check", methods=["GET"])
def env_check():
    info = deployment_service.check_remote_environment()
    return jsonify({"success": True, "data": info})


@bp_deployment.route("/configure_autostart", methods=["POST"])
def configure_autostart():
    data = request.get_json() or {}
    robot_id = data.get("robot_id", "A")
    ok, msg = deployment_service.configure_autostart_hook(robot_id)
    return jsonify({"success": ok, "msg": msg})


@bp_deployment.route("/network_interfaces", methods=["GET"])
def network_interfaces():
    ifs = interface_tool.list_network_interfaces()
    return jsonify({"success": True, "interfaces": ifs})


@bp_deployment.route("/driver_status", methods=["GET"])
def driver_status():
    ports = ch341_installer.detect_driver_ports()
    return jsonify({"success": True, "ports": ports, "has_driver": len(ports) > 0})
