import os
from flask import Blueprint, jsonify, request, send_from_directory
from backend.preview_manager import preview_manager

bp_preview = Blueprint("preview_api", __name__)


@bp_preview.route("/models/<path:filename>")
@bp_preview.route("/preview/<path:filename>")
def serve_preview_asset(filename):
    models_dir = preview_manager.get_builtin_models_dir()
    clean_subpath = filename.replace("preview/", "").replace("models/", "").lstrip("/")
    in_models = os.path.join(models_dir, clean_subpath)
    if os.path.exists(in_models):
        return send_from_directory(models_dir, clean_subpath)

    target = os.path.join(preview_manager.preview_dir, filename)
    if os.path.exists(target):
        return send_from_directory(preview_manager.preview_dir, filename)

    return send_from_directory(models_dir, clean_subpath)


@bp_preview.route("/api/dance/list_3d", methods=["GET"])
def list_3d_dances():
    dances = preview_manager.list_all_dances()
    return jsonify({"success": True, "dances": dances})


@bp_preview.route("/api/dance/get_3d/<dance_id>", methods=["GET"])
def get_3d_dance(dance_id):
    data = preview_manager.get_dance_data(dance_id)
    return jsonify(data)


@bp_preview.route("/api/dance/upload_npz", methods=["POST"])
def upload_npz():
    if "file" not in request.files:
        return jsonify({"success": False, "msg": "未检测到上传文件"})
    f = request.files["file"]
    save_path = os.path.join(preview_manager.preview_dir, f.filename)
    f.save(save_path)
    dance_id = os.path.splitext(f.filename)[0]
    data = preview_manager.get_dance_data(dance_id)
    return jsonify(data)


@bp_preview.route("/api/dance/import_zip", methods=["POST"])
@bp_preview.route("/api/dance/import_file", methods=["POST"])
def import_dance_zip():
    if "file" in request.files:
        f = request.files["file"]
        if not f.filename:
            return jsonify({"success": False, "msg": "上传的文件名为空"})
        res = preview_manager.import_zip(f, filename=f.filename)
        return jsonify(res)

    data = request.json if request.is_json else request.form.to_dict()
    data = data or {}
    path = data.get("path", "").strip().strip('"').strip("'")
    if not path:
        return jsonify({"success": False, "msg": "未提供文件或本地绝对路径"})

    res = preview_manager.import_zip(path)
    return jsonify(res)


@bp_preview.route("/api/dance/browse_zip", methods=["POST"])
@bp_preview.route("/api/dance/browse_file", methods=["POST"])
def browse_dance_zip():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
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
            return jsonify({"success": True, "path": file_path.replace("/", "\\")})
        return jsonify({"success": False, "msg": "用户取消了选择"})
    except Exception as e:
        return jsonify({"success": False, "msg": f"打开选择窗口失败: {str(e)}"})


@bp_preview.route("/api/dance/delete_3d/<dance_id>", methods=["DELETE", "POST"])
def delete_3d_dance(dance_id):
    res = preview_manager.delete_dance(dance_id)
    return jsonify(res)

