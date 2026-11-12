"""
@file: src/core/lrmp_compiler.py
@brief: LRMP V1.0-R3 协议帧编译、时序指令调度与时间轴编排工程持久化引擎
@exports: LrmpCompiler, lrmp_compiler
"""
import copy
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from src.core.models import ProjectChoreoModel
from src.core.storage_manager import storage_manager
from src.infrastructure.lrmp.lrmp_protocol_engine import LrmpProtocolEngine

logger = logging.getLogger("LrmpCompiler")


class LrmpCompiler:
    """时间轴编排到 LRMP V1.0-R3 二进制协议帧序列编译器与工程快照管理器"""

    def __init__(self) -> None:
        self.protocol_engine = LrmpProtocolEngine()

    def compile_timeline_to_lrmp_frames(
        self,
        clips: List[Dict[str, Any]],
        known_groups: Optional[Dict[str, List[str]]] = None,
        src_id: str = "CTRL_STATION",
    ) -> List[Dict[str, Any]]:
        """将时间轴所有 Clip 编译为带绝对时间戳、目标展开与 CRC32 校验的标准协议帧序列"""
        sorted_clips = sorted(clips, key=lambda c: float(c.get("start_time", 0.0)))
        groups = known_groups or {"group_1": ["A", "B", "C", "D"], "group_2": ["E", "F", "G", "H"]}
        compiled_frames: List[Dict[str, Any]] = []

        for clip in sorted_clips:
            target_id = str(clip.get("robot_id", "A")).strip().upper()
            start_t = float(clip.get("start_time", 0.0))
            dur = float(clip.get("duration", 3.0))
            cmd_raw = str(clip.get("cmd", "STAND")).strip()

            # 目标展开（群组轨道展开为多机定向单播）
            if target_id in groups:
                expanded_targets = groups[target_id]
            elif target_id.startswith("GROUP_") and target_id.lower() in groups:
                expanded_targets = groups[target_id.lower()]
            elif target_id == "ALL":
                expanded_targets = groups.get("group_1", ["A", "B"])
            else:
                expanded_targets = [target_id]

            for tgt in expanded_targets:
                seq = self.protocol_engine.next_seq()
                req_id = f"REQ_{seq:04X}"
                payload = cmd_raw

                # 标准 LRMP 帧体: REQ:seq:request_id:src_id:dst_id:payload#CRC32
                body = f"REQ:{seq}:{req_id}:{src_id}:{tgt}:{payload}"
                crc = self.protocol_engine.compute_crc32(body)
                wire_str = f"{body}#{crc}"

                compiled_frames.append({
                    "seq": seq,
                    "request_id": req_id,
                    "frame_type": "REQ",
                    "src_id": src_id,
                    "target_id": tgt,
                    "cmd": payload,
                    "scheduled_time": round(start_t, 3),
                    "duration": round(dur, 3),
                    "wire_frame": wire_str,
                    "checksum": crc,
                    "clip_id": clip.get("clip_id", ""),
                    "asset_type": clip.get("asset_type", "action"),
                })

        return compiled_frames

    def save_project(
        self,
        scene_id: str,
        name: str,
        tracks: List[Dict[str, Any]],
        clips: List[Dict[str, Any]],
        map_id: str = "sample_stage",
    ) -> str:
        """将完整编排工程（场景、多机轨道、Clip片段）保存至 SQLite 并导出 JSON 快照"""
        fragments: List[Dict[str, Any]] = []
        track_state: List[Dict[str, Any]] = []

        for idx, c in enumerate(clips):
            cid = c.get("clip_id", f"clip_{idx}_{int(time.time())}")
            c_copy = copy.deepcopy(c)
            fragments.append({
                "fragment_id": cid,
                "scene_id": scene_id,
                "name": c.get("name", "未命名片段"),
                "start_time": float(c.get("start_time", 0.0)),
                "duration": float(c.get("duration", 3.0)),
                "content_json": c_copy,
            })
            track_state.append({
                "id": cid,
                "scene_id": scene_id,
                "robot_id": idx + 1,
                "group_id": 0,
                "no": idx,
                "type": c.get("asset_type", "action"),
                "name": c.get("name", ""),
                "time": float(c.get("start_time", 0.0)),
                "start_time": float(c.get("start_time", 0.0)),
                "end_time": float(c.get("start_time", 0.0)) + float(c.get("duration", 3.0)),
                "content": c_copy,
            })

        project = ProjectChoreoModel(
            scene_id=scene_id,
            name=name,
            map_id=map_id,
            tracks=tracks,
            init_points=[],
            track_state=track_state,
            fragments=fragments,
        )

        storage_manager.save_project_choreo(project)
        return scene_id

    def load_project(self, scene_id: str) -> Optional[Dict[str, Any]]:
        """从本地磁盘或 SQLite 加载编排工程并还原为字典"""
        model = storage_manager.load_project_choreo(scene_id)
        if not model:
            return None
        return model.to_dict()


lrmp_compiler = LrmpCompiler()
