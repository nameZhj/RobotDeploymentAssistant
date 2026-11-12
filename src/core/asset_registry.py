"""
@file: src/core/asset_registry.py
@brief: 统一动作、舞蹈、轨迹与阵型素材动态注册与检索服务
@exports: AssetRegistry, asset_registry
"""
import glob
import json
import logging
import os
from typing import Any, Dict, List, Optional
from backend.serial_dance_parser import DEFAULT_DANCE_GROUPS
from src.core.storage_manager import storage_manager

logger = logging.getLogger("AssetRegistry")

DEFAULT_BASIC_ACTIONS: List[Dict[str, Any]] = [
    {"alias": "STAND", "name": "站立(FixStand)", "cmd": "STAND", "duration": 3.0, "category": "action", "color": "#3b82f6"},
    {"alias": "GAIT", "name": "步态就绪(RL_MJAMP)", "cmd": "GAIT", "duration": 2.0, "category": "action", "color": "#2563eb"},
    {"alias": "FORWARD", "name": "前进", "cmd": "FORWARD,2", "duration": 2.0, "category": "action", "color": "#0ea5e9"},
    {"alias": "BACKWARD", "name": "后退", "cmd": "BACKWARD,2", "duration": 2.0, "category": "action", "color": "#0284c7"},
    {"alias": "MOVE_LEFT", "name": "左横移", "cmd": "MOVE_LEFT,2", "duration": 2.0, "category": "action", "color": "#06b6d4"},
    {"alias": "MOVE_RIGHT", "name": "右横移", "cmd": "MOVE_RIGHT,2", "duration": 2.0, "category": "action", "color": "#0891b2"},
    {"alias": "TURN_LEFT", "name": "左转", "cmd": "TURN_LEFT,1", "duration": 1.0, "category": "action", "color": "#14b8a6"},
    {"alias": "TURN_RIGHT", "name": "右转", "cmd": "TURN_RIGHT,1", "duration": 1.0, "category": "action", "color": "#0d9488"},
    {"alias": "STOP", "name": "软停(减速归零)", "cmd": "STOP", "duration": 1.0, "category": "action", "color": "#64748b"},
    {"alias": "EMERGENCY", "name": "硬停急停", "cmd": "EMERGENCY", "duration": 0.5, "category": "action", "color": "#ef4444"},
    {"alias": "PASSIVE", "name": "被动阻尼", "cmd": "PASSIVE", "duration": 2.0, "category": "action", "color": "#475569"},
]


class AssetRegistry:
    """素材注册表：聚合真实33支舞蹈、运控基础动作、本地持久化轨迹与阵型模板"""

    def __init__(self) -> None:
        self._dances: List[Dict[str, Any]] = []
        self._actions: List[Dict[str, Any]] = []
        self._trajectories: List[Dict[str, Any]] = []
        self._formations: List[Dict[str, Any]] = []
        self._asset_map: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        self._load_dances()
        self._load_actions()
        self._load_trajectories()
        self._load_formations()
        self._rebuild_map()

    def _load_dances(self) -> None:
        self._dances.clear()
        for group in DEFAULT_DANCE_GROUPS:
            gid = group.get("group_id", "G1")
            for item in group.get("items", []):
                alias = item.get("alias", "")
                self._dances.append({
                    "asset_id": f"dance_{alias}",
                    "alias": alias,
                    "name": item.get("name", alias),
                    "cmd": item.get("cmd", f"DANCE,{alias}"),
                    "keys": item.get("keys", ""),
                    "group": gid,
                    "duration": 5.0,  # 舞蹈默认时长 5s
                    "category": "dance",
                    "color": "#a855f7",
                })

    def _load_actions(self) -> None:
        self._actions.clear()
        for act in DEFAULT_BASIC_ACTIONS:
            self._actions.append({
                "asset_id": f"act_{act['alias']}",
                "alias": act["alias"],
                "name": act["name"],
                "cmd": act["cmd"],
                "keys": "",
                "duration": float(act["duration"]),
                "category": "action",
                "color": act.get("color", "#3b82f6"),
            })

    def _load_trajectories(self) -> None:
        self._trajectories.clear()
        pattern = os.path.join(storage_manager.trajectories_dir, "*.json")
        for f in glob.glob(pattern):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    tid = data.get("trajectory_id", os.path.splitext(os.path.basename(f))[0])
                    cps = data.get("control_points", [])
                    dur = float(cps[-1].get("t", 3.0)) if cps else float(data.get("duration", 3.0))
                    self._trajectories.append({
                        "asset_id": f"traj_{tid}",
                        "alias": tid,
                        "name": data.get("name", tid),
                        "cmd": tid,
                        "target_type": data.get("target_type", "single"),
                        "target_id": data.get("target_id", "A"),
                        "formation_id": data.get("formation_id", ""),
                        "duration": max(0.5, dur),
                        "category": "trajectory",
                        "color": "#f59e0b",
                        "file_path": f,
                    })
            except Exception as ex:
                logger.warning(f"读取轨迹文件 {f} 失败: {ex}")

    def _load_formations(self) -> None:
        self._formations.clear()
        pattern = os.path.join(storage_manager.formations_dir, "*.json")
        for f in glob.glob(pattern):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    fid = data.get("formation_id", os.path.splitext(os.path.basename(f))[0])
                    self._formations.append({
                        "asset_id": f"form_{fid}",
                        "alias": fid,
                        "name": data.get("name", fid),
                        "cmd": fid,
                        "type": data.get("type", "grid"),
                        "member_count": len(data.get("members", [])),
                        "duration": 0.0,
                        "category": "formation",
                        "color": "#10b981",
                        "file_path": f,
                    })
            except Exception as ex:
                logger.warning(f"读取阵型文件 {f} 失败: {ex}")

    def _rebuild_map(self) -> None:
        self._asset_map.clear()
        for coll in (self._dances, self._actions, self._trajectories, self._formations):
            for item in coll:
                self._asset_map[item["asset_id"]] = item

    def get_dances(self) -> List[Dict[str, Any]]:
        return list(self._dances)

    def get_actions(self) -> List[Dict[str, Any]]:
        return list(self._actions)

    def get_trajectories(self) -> List[Dict[str, Any]]:
        return list(self._trajectories)

    def get_formations(self) -> List[Dict[str, Any]]:
        return list(self._formations)

    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        return self._asset_map.get(asset_id)


asset_registry = AssetRegistry()
