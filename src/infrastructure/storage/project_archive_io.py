"""
编排工程包与 LRMP 不可变任务包归档/解归档 I/O 模块
提供 .zip 工程打包解压与 SHA-256 签名的不可变 plan_id 编译
"""
import hashlib
import json
import os
import shutil
import time
import zipfile
from typing import Any, Dict, List, Optional, Tuple


def export_project_archive(zip_path: str, db_path: str,
                           extra_files: Optional[List[str]] = None,
                           project_meta: Optional[Dict[str, Any]] = None) -> str:
    """将 SQLite 数据库与关联资源打包为 .zip 工程包"""
    out_dir = os.path.dirname(os.path.abspath(zip_path))
    os.makedirs(out_dir, exist_ok=True)
    meta = project_meta.copy() if project_meta else {}
    meta.setdefault("version", "1.0.0")
    meta.setdefault("exported_at", time.time())

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project_meta.json", json.dumps(meta, indent=2, ensure_ascii=False))
        if os.path.exists(db_path):
            zf.write(db_path, arcname="studio_data.db")
        if extra_files:
            for f in extra_files:
                if f and os.path.exists(f):
                    rel_name = os.path.join("assets", os.path.basename(f))
                    zf.write(f, arcname=rel_name)
    return os.path.abspath(zip_path)


def import_project_archive(zip_path: str, extract_dir: str) -> Dict[str, Any]:
    """安全解压 .zip 工程包，拦截路径穿越漏洞并读取元数据"""
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"工程包不存在: {zip_path}")
    os.makedirs(extract_dir, exist_ok=True)
    abs_extract_dir = os.path.abspath(extract_dir)

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            target_path = os.path.abspath(os.path.join(abs_extract_dir, member.filename))
            if not target_path.startswith(abs_extract_dir + os.sep) and target_path != abs_extract_dir:
                raise ValueError(f"检测到非法路径穿越文件: {member.filename}")
        zf.extractall(abs_extract_dir)

    meta_file = os.path.join(abs_extract_dir, "project_meta.json")
    meta: Dict[str, Any] = {}
    if os.path.exists(meta_file):
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
    meta["extracted_dir"] = abs_extract_dir
    meta["db_path"] = os.path.join(abs_extract_dir, "studio_data.db")
    return meta


def compile_lrmp_plan(task_name: str,
                      clips: List[Dict[str, Any]],
                      trajectories: Dict[str, Dict[str, Any]],
                      bgm_path: str = "",
                      output_dir: str = os.path.join("runtime", "shows")) -> Tuple[str, Dict[str, Any], str]:
    """
    编译生成带 SHA-256 校验的不可变 LRMP 任务包
    返回 (plan_id, plan_dict, plan_file_path)
    """
    os.makedirs(output_dir, exist_ok=True)
    robots_map: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    for c in clips:
        rid = str(c.get("robot_id", "1"))
        if rid not in robots_map:
            robots_map[rid] = {"actions": [], "trajectories": []}
        layer = c.get("track_layer", "")
        ref_id = c.get("ref_id", "")
        item = {
            "ref_id": ref_id,
            "start_ms": int(c.get("start_ms", 0)),
            "duration_ms": int(c.get("duration_ms", 0))
        }
        if layer == "UPPER_ACTION":
            robots_map[rid]["actions"].append(item)
        elif layer == "LOWER_TRAJ":
            traj_data = trajectories.get(ref_id, {})
            wp_str = traj_data.get("waypoints_json", "[]")
            try:
                item["waypoints"] = json.loads(wp_str) if isinstance(wp_str, str) else wp_str
            except Exception:
                item["waypoints"] = []
            robots_map[rid]["trajectories"].append(item)

    for rid in robots_map:
        robots_map[rid]["actions"].sort(key=lambda x: x["start_ms"])
        robots_map[rid]["trajectories"].sort(key=lambda x: x["start_ms"])

    payload: Dict[str, Any] = {
        "task_name": task_name,
        "protocol_version": "LRMP-1.0-R3",
        "bgm_path": bgm_path,
        "robots": robots_map
    }

    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sha256_hash = hashlib.sha256(canonical_bytes).hexdigest()
    plan_id = f"plan_{sha256_hash[:12]}"

    final_document = {
        "plan_id": plan_id,
        "sha256": sha256_hash,
        "compiled_at": time.time(),
        "payload": payload
    }

    out_file = os.path.join(output_dir, f"{plan_id}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_document, f, indent=2, ensure_ascii=False)

    return plan_id, final_document, os.path.abspath(out_file)


def verify_lrmp_plan(plan_doc: Dict[str, Any]) -> bool:
    """验证不可变 LRMP plan_id 数据包的 SHA-256 签名完整性"""
    expected_hash = plan_doc.get("sha256", "")
    payload = plan_doc.get("payload", {})
    if not expected_hash or not payload:
        return False
    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    actual_hash = hashlib.sha256(canonical_bytes).hexdigest()
    return actual_hash == expected_hash
