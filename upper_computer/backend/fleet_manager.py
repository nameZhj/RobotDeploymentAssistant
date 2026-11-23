"""
VSISLAB 机器人助手 - 机队配置持久化管理器
确保用户添加的机器人 ID 列表与选中状态在程序关闭、重启、打包 EXE 后均永久本地保存
"""
import os
import sys
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("FleetManager")


def get_app_storage_dir() -> str:
    """获取程序持久化数据存储根目录（打包 EXE 所在目录或源码根目录）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class FleetManager:
    """受控机器人机队配置持久化服务"""

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir or get_app_storage_dir()
        self.cache_dir = os.path.join(self.storage_dir, "cache")
        self.config_path = os.path.join(self.cache_dir, "robot_fleet.json")

    def load_fleet(self) -> Dict[str, Any]:
        """读取本地持久化的机队配置（优先读取 cache/robot_fleet.json，兼容根目录遗留配置）"""
        target_path = self.config_path
        if not os.path.exists(target_path):
            legacy_path = os.path.join(self.storage_dir, "robot_fleet.json")
            if os.path.exists(legacy_path):
                target_path = legacy_path
            else:
                return {"success": True, "robots": [], "selected": []}

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    robots = [str(r).strip().upper() for r in data if r and str(r).strip().upper() != "ALL"]
                    selected = [robots[0]] if len(robots) == 1 else ["ALL"] if len(robots) > 1 else []
                    return {"success": True, "robots": robots, "selected": selected}
                elif isinstance(data, dict):
                    robots = [str(r).strip().upper() for r in data.get("robots", []) if r and str(r).strip().upper() != "ALL"]
                    selected = [str(s).strip().upper() for s in data.get("selected", []) if s]
                    return {"success": True, "robots": robots, "selected": selected}
        except Exception as e:
            logger.error(f"读取机器人机队配置失败: {e}")

        return {"success": True, "robots": [], "selected": []}

    def save_fleet(self, robots: List[str], selected: Optional[List[str]] = None) -> Dict[str, Any]:
        """持久化保存机队配置到本地 cache/robot_fleet.json 文件"""
        clean_robots = []
        for r in robots or []:
            cr = str(r).strip().upper()
            if cr and cr != "ALL" and cr not in clean_robots:
                clean_robots.append(cr)

        clean_selected = []
        for s in selected or []:
            cs = str(s).strip().upper()
            if cs and cs not in clean_selected:
                clean_selected.append(cs)

        payload = {
            "robots": clean_robots,
            "selected": clean_selected
        }

        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.info(f"成功保存机队配置: {clean_robots} 至 {self.config_path}")
            return {"success": True, "msg": "机队配置已保存", "data": payload}
        except Exception as e:
            logger.error(f"保存机队配置失败: {e}")
            return {"success": False, "msg": f"保存失败: {str(e)}"}


fleet_manager = FleetManager()
