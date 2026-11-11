"""
@file: src/infrastructure/storage/project_archiver.py
@brief: 编排工程 .zip 打包导出与安全解包还原归档器
@exports: ProjectArchiver
"""
import json
import os
import shutil
import sqlite3
import time
import zipfile
from typing import Any, Dict, List, Optional


class ProjectArchiver:
    """提供工程全量资源与 SQLite 数据库的双向 .zip 归档及解包还原"""

    @staticmethod
    def _find_associated_files(db_path: str, scene_id: str) -> List[str]:
        files: List[str] = []
        if not os.path.exists(db_path):
            return files
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT active_map_id, music_path FROM scenes WHERE scene_id = ?", (scene_id,))
            s_row = cur.fetchone()
            if not s_row:
                return files
            if s_row["music_path"] and os.path.exists(s_row["music_path"]):
                files.append(s_row["music_path"])
            map_id = s_row["active_map_id"]
            if map_id:
                cur.execute("SELECT pcd_path FROM nav_maps WHERE map_id = ?", (map_id,))
                m_row = cur.fetchone()
                if m_row and m_row["pcd_path"] and os.path.exists(m_row["pcd_path"]):
                    files.append(m_row["pcd_path"])
        return files

    @classmethod
    def export_archive(cls, zip_path: str, db_path: str,
                       scene_id: str = "123",
                       extra_files: Optional[List[str]] = None) -> str:
        out_dir = os.path.dirname(os.path.abspath(zip_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        assoc_files = cls._find_associated_files(db_path, scene_id)
        if extra_files:
            assoc_files.extend([f for f in extra_files if f and os.path.exists(f)])

        manifest = {
            "version": "1.0.0",
            "scene_id": scene_id,
            "created_at": time.time(),
            "included_files": [os.path.basename(f) for f in assoc_files]
        }

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            if os.path.exists(db_path):
                zf.write(db_path, arcname="choreo_studio.db")
            for f in set(assoc_files):
                zf.write(f, arcname=os.path.join("assets", os.path.basename(f)))
        return os.path.abspath(zip_path)

    @staticmethod
    def import_archive(zip_path: str, extract_dir: str,
                       target_db_path: Optional[str] = None) -> Dict[str, Any]:
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"归档包不存在: {zip_path}")
        abs_extract = os.path.abspath(extract_dir)
        os.makedirs(abs_extract, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                target = os.path.abspath(os.path.join(abs_extract, member.filename))
                if not target.startswith(abs_extract + os.sep) and target != abs_extract:
                    raise ValueError(f"检测到非法路径穿越攻击文件: {member.filename}")
            zf.extractall(abs_extract)

        extracted_db = os.path.join(abs_extract, "choreo_studio.db")
        if target_db_path and os.path.exists(extracted_db):
            t_dir = os.path.dirname(os.path.abspath(target_db_path))
            if t_dir:
                os.makedirs(t_dir, exist_ok=True)
            shutil.copy2(extracted_db, target_db_path)

        manifest_path = os.path.join(abs_extract, "manifest.json")
        manifest_data: Dict[str, Any] = {}
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as mf:
                manifest_data = json.load(mf)
        manifest_data["extracted_dir"] = abs_extract
        manifest_data["db_path"] = target_db_path if target_db_path else extracted_db
        return manifest_data
