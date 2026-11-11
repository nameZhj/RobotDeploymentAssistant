"""
@file: src/application/choreo/dynamic_dance_bridge.py
@brief: 对接现有串口与机载动态舞蹈模块，无缝映射为舞台编排动作库对象
@exports: DynamicDanceBridge, ChoreoActionItem, dynamic_dance_bridge
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from backend.dance_updater import dance_updater
from backend.serial_dance_parser import DEFAULT_DANCE_GROUPS, parse_dance_map_yaml
from backend.serial_manager import serial_manager
from src.core.logger import get_logger

logger = get_logger("DynamicDanceBridge")


@dataclass
class ChoreoActionItem:
    no: int
    name: str
    alias: str
    time: float
    transition: float
    allow_move: bool
    allow_stretch: bool
    cmd: str
    keys: str
    group_id: str = "G1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "no": self.no,
            "name": self.name,
            "alias": self.alias,
            "time": self.time,
            "transition": self.transition,
            "allowMove": self.allow_move,
            "allowStretch": self.allow_stretch,
            "cmd": self.cmd,
            "keys": self.keys,
            "groupId": self.group_id,
        }


class DynamicDanceBridge:
    """桥接原有串口动态舞蹈上传与同步模块，提供动作库映射与动态刷新监听"""

    def __init__(self) -> None:
        self._listeners: List[Callable[[List[ChoreoActionItem]], None]] = []
        self._action_cache: List[ChoreoActionItem] = []
        self._alias_to_no: Dict[str, int] = {}
        self._next_auto_no: int = 550001
        self.reload_from_manager()

    def register_listener(self, listener: Callable[[List[ChoreoActionItem]], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unregister_listener(self, listener: Callable[[List[ChoreoActionItem]], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            try:
                listener(self.get_action_library())
            except Exception as e:
                logger.error(f"Listener notification error: {e}")

    def _map_dance_item_to_action(self, item: Dict[str, Any], group_id: str, index: int) -> ChoreoActionItem:
        alias = item.get("alias", f"ACTION_{index}").strip()
        if alias not in self._alias_to_no:
            self._alias_to_no[alias] = self._next_auto_no
            self._next_auto_no += 1
        no = self._alias_to_no[alias]
        name = item.get("name") or alias
        keys = item.get("keys", "")
        cmd = item.get("cmd", f"DANCE,{alias}")

        alias_upper = alias.upper()
        allow_move = any(kw in alias_upper for kw in ["RUN", "WALK", "STEP", "MOONWALK", "JUMP"])
        default_dur = 12.0 if "TAIJI" in alias_upper or "TIKTOK" in alias_upper else 6.0

        return ChoreoActionItem(
            no=no,
            name=name,
            alias=alias,
            time=float(item.get("time", default_dur)),
            transition=float(item.get("transition", 0.5)),
            allow_move=bool(item.get("allowMove", allow_move)),
            allow_stretch=bool(item.get("allowStretch", False)),
            cmd=cmd,
            keys=keys,
            group_id=group_id,
        )

    def _rebuild_cache_from_groups(self, groups: List[Dict[str, Any]]) -> List[ChoreoActionItem]:
        actions: List[ChoreoActionItem] = []
        idx = 1
        for grp in groups:
            gid = grp.get("group_id", "G1")
            for item in grp.get("items", []):
                act = self._map_dance_item_to_action(item, gid, idx)
                actions.append(act)
                idx += 1
        self._action_cache = actions
        self._notify_listeners()
        return list(self._action_cache)

    def reload_from_manager(self) -> List[ChoreoActionItem]:
        data = serial_manager.get_dance_list()
        groups = data.get("groups") or DEFAULT_DANCE_GROUPS
        return self._rebuild_cache_from_groups(groups)

    def get_action_library(self) -> List[ChoreoActionItem]:
        if not self._action_cache:
            self.reload_from_manager()
        return list(self._action_cache)

    def sync_from_yaml_text(self, raw_yaml: str) -> List[ChoreoActionItem]:
        parsed = parse_dance_map_yaml(raw_yaml)
        serial_manager.set_dance_list_raw(raw_yaml)
        return self._rebuild_cache_from_groups(parsed)

    def sync_from_robot_serial(self, timeout: float = 3.0) -> Tuple[bool, List[ChoreoActionItem], str]:
        ok, groups, msg = serial_manager.sync_dance_list_from_robot(timeout=timeout)
        actions = self._rebuild_cache_from_groups(groups)
        return ok, actions, msg

    def deploy_zip_and_reload(
        self,
        local_zip_path: str,
        stream_callback: Optional[Callable[[str, bool], None]] = None,
        dest_path: str = "/secure/config_vsis",
    ) -> Tuple[bool, str]:
        cb = stream_callback or (lambda msg, err: None)
        ok, msg = dance_updater.deploy_zip_package(local_zip_path, cb, dest_path=dest_path)
        if ok:
            dance_updater.restart_control_processes(cb)
            self.sync_from_robot_serial(timeout=2.0)
        return ok, msg


dynamic_dance_bridge = DynamicDanceBridge()

