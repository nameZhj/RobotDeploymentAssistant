from flask import Blueprint, jsonify, request
from src.application.motion_service import motion_service
from src.infrastructure.serial.lora_serial_port import lora_port

bp_control = Blueprint("control", __name__, url_prefix="/api/serial")


@bp_control.route("/ports", methods=["GET"])
def get_serial_ports():
    ports = lora_port.list_available_ports()
    return jsonify({"success": True, "ports": ports})


@bp_control.route("/connect", methods=["POST"])
def connect_serial():
    data = request.get_json() or {}
    port = data.get("port", "")
    baud = int(data.get("baud", 9600))
    if not port:
        return jsonify({"success": False, "msg": "Port is required"}), 400

    ok = lora_port.open(port, baudrate=baud)
    return jsonify({
        "success": ok,
        "msg": f"Connected to {port}" if ok else f"Failed to connect to {port}",
        "port": port,
    })


@bp_control.route("/disconnect", methods=["POST"])
def disconnect_serial():
    lora_port.close()
    return jsonify({"success": True, "msg": "Disconnected"})


@bp_control.route("/status", methods=["GET"])
def get_serial_status():
    return jsonify({
        "connected": lora_port.is_open,
        "port": lora_port.port_name,
    })


@bp_control.route("/send", methods=["POST"])
def send_command():
    data = request.get_json() or {}
    targets = data.get("targets", ["ALL"])
    command = data.get("command", "")
    params = data.get("params", None)

    if not command:
        return jsonify({"success": False, "msg": "Command is required"}), 400

    ok, msg = motion_service.send_motion_command(targets, command, params)
    return jsonify({"success": ok, "msg": msg})


@bp_control.route("/release", methods=["POST"])
def release_authority():
    data = request.get_json() or {}
    targets = data.get("targets", ["ALL"])
    ok, msg = motion_service.release_control(targets)
    return jsonify({"success": ok, "msg": msg})
