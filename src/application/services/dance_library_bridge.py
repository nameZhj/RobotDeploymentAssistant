"""
@file: src/application/services/dance_library_bridge.py
@brief: 打通 backend 串口动态舞蹈模块与舞台编排动作库的业务桥接服务
@exports: DanceLibraryBridge, dance_library_bridge
"""
from typing import Any, Callable, Dict, List, Optional, Tuple
from backend.dance_updater import dance_updater
from backend.serial_dance_parser import intersect_dance_groups, parse_dance_map_yaml
from backend.serial_manager import serial_manager
from src.core.logger import get_logger

logger = get_logger("DanceLibraryBridge")


class DanceLibraryBridge:
    """提供动态动作获取、多机交集计算、实时同步与动作包热部署服务"""

    def __init__(self) -> None:
        self._action_no_map: Dict[str, int] = {}
        self._next_auto_no: int = 550001
        self._custom_durations: Dict[str, float] = {}

    def _assign_no(self, alias: str) -> int:
        if alias not in self._action_no_map:
            self._action_no_map[alias] = self._next_auto_no
            self._next_auto_no += 1
        return self._action_no_map[alias]

    def set_action_duration(self, alias: str, duration_s: float) -> None:
        self._custom_durations[alias.strip().upper()] = max(0.1, float(duration_s))

    def _format_action_item(self, item: Dict[str, Any], gid: str) -> Dict[str, Any]:
        alias = str(item.get("alias", "")).strip()
        alias_upper = alias.upper()
        no = self._assign_no(alias)
        name = str(item.get("name", "")).strip() or alias

        default_dur = self._custom_durations.get(
            alias_upper,
            12.0 if any(k in alias_upper for k in ["TAIJI", "TIKTOK", "POPPING", "BALLET"]) else 6.0
        )
        allow_move = any(k in alias_upper for k in ["RUN", "WALK", "STEP", "MOONWALK", "JUMP"])

        return {
            "id": no,
            "no": no,
            "name": name,
            "lora_alias": alias,
            "code_alias": alias,
            "key_combo": str(item.get("keys", "")),
            "type": str(item.get("type", "dance")),
            "time": float(item.get("time", default_dur)),
            "transition": float(item.get("transition", 0.0)),
            "allow_stretch": int(item.get("allow_stretch", 0)),
            "allow_move": int(item.get("allow_move", 1 if allow_move else 0)),
            "cmd": str(item.get("cmd", f"DANCE,{alias}")),
            "group_key": gid,
        }

    def list_available_actions(
        self,
        keyword: str = "",
        group_filter: str = "",
        filter_keyword: str = "",
        group_prefix: str = "",
        scene_id: int = 1
    ) -> List[Dict[str, Any]]:
        """动态合并 serial_manager 同步的全部动作与本地扩展元数据（零写死）"""
        data = serial_manager.get_dance_list()
        groups = data.get("groups", [])
        actions: List[Dict[str, Any]] = []

        kw = (keyword or filter_keyword).strip().lower()
        g_pre = (group_filter or group_prefix).strip().upper()

        for grp in groups:
            gid = str(grp.get("group_id", "G1")).strip()
            if g_pre and not gid.upper().startswith(g_pre):
                continue
            for item in grp.get("items", []):
                act = self._format_action_item(item, gid)
                if kw:
                    name_match = kw in act["name"].lower()
                    alias_match = kw in act["lora_alias"].lower()
                    if not (name_match or alias_match):
                        continue
                actions.append(act)
        return actions

    def sync_actions_from_robot(self, timeout: float = 3.0) -> Tuple[bool, List[Dict[str, Any]], str]:
        """从机器人实时同步最新 lora_recv_group.yaml 动作表并更新缓存"""
        ok, _, msg = serial_manager.sync_dance_list_from_robot(timeout=timeout)
        actions = self.list_available_actions()
        return ok, actions, msg

    def get_common_actions_for_robots(self, yaml_texts: List[str]) -> List[Dict[str, Any]]:
        """调用 intersect_dance_groups 动态提取多台机器人的动作交集"""
        if not yaml_texts:
            return []
        multi_dict = {f"Robot_{idx}": parse_dance_map_yaml(text) for idx, text in enumerate(yaml_texts)}
        common_groups = intersect_dance_groups(multi_dict)
        actions: List[Dict[str, Any]] = []
        for grp in common_groups:
            gid = str(grp.get("group_id", "G1"))
            for item in grp.get("items", []):
                actions.append(self._format_action_item(item, gid))
        return actions

    def upload_action_zip(
        self,
        zip_path: str,
        progress_cb: Optional[Callable[[str, bool], None]] = None
    ) -> Tuple[bool, str]:
        """上传 .zip 动作包至 /secure/config_vsis 并热重启机载进程"""
        cb = progress_cb or (lambda msg, err: None)
        ok_dep, msg_dep = dance_updater.deploy_zip_package(zip_path, cb)
        if not ok_dep:
            return False, f"部署动作包失败: {msg_dep}"
        ok_rst = dance_updater.restart_control_processes(cb)
        if not ok_rst:
            return False, "热重启机载进程失败"
        self.sync_actions_from_robot(timeout=2.0)
        return True, "动作包部署与进程热重启成功"

    # 兼容历史别名
    get_dynamic_actions = list_available_actions
    sync_from_robot_serial = sync_actions_from_robot
    get_multi_robot_common_actions = get_common_actions_for_robots
    deploy_and_reload_zip = upload_action_zip


dance_library_bridge = DanceLibraryBridge()
