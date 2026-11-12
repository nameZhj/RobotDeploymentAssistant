from flask import Blueprint, jsonify, request
from src.application.fleet_service import fleet_service

bp_fleet = Blueprint("fleet", __name__, url_prefix="/api/fleet")


@bp_fleet.route("/list", methods=["GET"])
def list_fleet():
    robots = fleet_service.list_robots()
    data = [
        {
            "alias": r.alias,
            "ip": r.ip,
            "is_online": r.is_online,
            "authority": r.authority.value,
        }
        for r in robots
    ]
    return jsonify({"success": True, "robots": data})


@bp_fleet.route("/add", methods=["POST"])
def add_fleet_robot():
    data = request.get_json() or {}
    alias = data.get("alias", "")
    ip = data.get("ip", "")
    if not alias:
        return jsonify({"success": False, "msg": "Alias is required"}), 400

    ok = fleet_service.add_robot(alias, ip)
    return jsonify({
        "success": ok,
        "msg": f"Added robot [{alias}]" if ok else "Failed to add robot",
    })


@bp_fleet.route("/remove", methods=["POST"])
def remove_fleet_robot():
    data = request.get_json() or {}
    alias = data.get("alias", "")
    if not alias:
        return jsonify({"success": False, "msg": "Alias is required"}), 400

    ok = fleet_service.remove_robot(alias)
    return jsonify({"success": ok, "msg": f"Removed {alias}" if ok else "Not found"})
