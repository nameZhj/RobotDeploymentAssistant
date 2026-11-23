# @file: src/protocol/timeline_lrmp_compiler.py
# @brief: Compiles multi-track timeline blocks into LRMP V1.0-R3 PREP/PLAY/DANCE/BARRIER/STOP schedules and validates safety.
# @exports: ScheduledLrmpCommand, CompiledShowPlan, PreDanceCheckReport, TimelineLrmpCompiler

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Dict, List, Optional, Sequence

from src.domain.timeline_entities import TimelineBlockEntity
from src.domain.track_entities import TrackEntity
from src.protocol.lrmp_codec import LrmpCodec


@dataclass
class ScheduledLrmpCommand:
    """Single timestamped LRMP command emitted for execution or audit preview."""

    offset_s: float
    target: str
    command: str
    params: List[str] = field(default_factory=list)
    ascii_frame: str = ""


@dataclass
class CompiledShowPlan:
    """Complete compiled sequence adhering to LRMP V1.0-R3 PREP -> BARRIER -> PLAY(T0) -> STOP."""

    plan_id: str
    run_id: str
    targets: List[str]
    commands: List[ScheduledLrmpCommand]
    prep_frames: List[str]
    play_frames: List[str]
    stop_frames: List[str]


@dataclass
class PreDanceCheckReport:
    """Safety validation summary executed before HTTP upload or T0 choreography launch."""

    passed: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    active_target_count: int = 0
    total_duration_s: float = 0.0


class TimelineLrmpCompiler:
    """Translates visual timeline blocks into verifiable LRMP V1.0-R3 schedule tables."""

    @staticmethod
    def validate_before_launch(
        tracks: Sequence[TrackEntity],
        blocks: Sequence[TimelineBlockEntity],
        collision_intervals: Sequence[Dict[str, object]] = (),
    ) -> PreDanceCheckReport:
        issues: List[str] = []
        warnings: List[str] = []
        if not tracks:
            issues.append("未配置任何机器人轨道")

        seen_targets = set()
        for tr in tracks:
            t_id = tr.target_id.strip().upper()
            if not t_id or t_id == "ALL":
                issues.append(f"轨道 {tr.track_no} 目标标识 '{tr.target_id}' 非法（禁止为空或 ALL）")
            if t_id in seen_targets:
                issues.append(f"存在重复的机器人寻址标识: {t_id}")
            seen_targets.add(t_id)

        active_blocks = [b for b in blocks if not b.is_ignored]
        if not active_blocks:
            warnings.append("时间轴当前无有效编排块（将仅执行空等待）")

        for i in range(len(active_blocks)):
            for j in range(i + 1, len(active_blocks)):
                if active_blocks[i].overlaps(active_blocks[j]):
                    issues.append(
                        f"时间轴同轨时间重叠: '{active_blocks[i].title}' 与 '{active_blocks[j].title}'"
                    )

        for seg in collision_intervals:
            issues.append(
                f"空间安全距离冲突 [{seg.get('start', 0):.2f}s - {seg.get('end', 0):.2f}s]: {seg.get('robots', '')}"
            )

        max_end = max((b.end_time for b in active_blocks), default=0.0)
        return PreDanceCheckReport(
            passed=len(issues) == 0,
            issues=issues,
            warnings=warnings,
            active_target_count=len(tracks),
            total_duration_s=round(max_end, 3),
        )

    @staticmethod
    def compile_plan(
        tracks: Sequence[TrackEntity],
        blocks: Sequence[TimelineBlockEntity],
        plan_id: str = "8001",
        run_id: Optional[str] = None,
        lead_time_ms: int = 3000,
    ) -> CompiledShowPlan:
        """Compile tracks and non-ignored blocks into LRMP V1.0-R3 ASCII frames."""
        rid = run_id or str(int(time.time()) % 100000)
        t0_ms = int(time.time() * 1000) + max(500, lead_time_ms)
        track_by_id = {t.id: t for t in tracks if t.id is not None}
        targets = [t.target_id.strip().upper() for t in tracks if not t.muted]

        prep_frames = [
            LrmpCodec.encode(tgt, "PREP", plan_id, rid).decode("utf-8").strip() for tgt in targets
        ]
        play_frames = [
            LrmpCodec.encode(tgt, "PLAY", rid, str(t0_ms)).decode("utf-8").strip() for tgt in targets
        ]
        stop_frames = [LrmpCodec.encode(tgt, "STOP").decode("utf-8").strip() for tgt in targets]

        commands: List[ScheduledLrmpCommand] = []
        for blk in sorted((b for b in blocks if not b.is_ignored), key=lambda x: x.start_time):
            tr = track_by_id.get(blk.track_id)
            if tr is None or tr.muted:
                continue
            tgt = tr.target_id.strip().upper()
            if blk.block_type == "action":
                raw_code = str(blk.extra.get("lrmpCode") or blk.code_no or blk.title)
                cmd_name = raw_code.upper()
                if cmd_name in ("STAND", "GAIT", "PASSIVE", "STOP"):
                    frame = LrmpCodec.encode(tgt, cmd_name).decode("utf-8").strip()
                    commands.append(ScheduledLrmpCommand(blk.start_time, tgt, cmd_name, [], frame))
                else:
                    alias = LrmpCodec.resolve_dance_alias(raw_code)
                    frame = LrmpCodec.encode(tgt, "DANCE", alias).decode("utf-8").strip()
                    commands.append(ScheduledLrmpCommand(blk.start_time, tgt, "DANCE", [alias], frame))

        return CompiledShowPlan(
            plan_id=plan_id,
            run_id=rid,
            targets=targets,
            commands=commands,
            prep_frames=prep_frames,
            play_frames=play_frames,
            stop_frames=stop_frames,
        )
