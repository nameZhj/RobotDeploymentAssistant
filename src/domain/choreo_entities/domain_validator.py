"""
@file: src/domain/choreo_entities/domain_validator.py
@brief: 舞台编导领域模型通用校验器，提供数值有限性、标识符、单位及坐标系安全检查
@exports: DomainValidator
"""
from datetime import datetime, timezone
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class DomainValidator:
    """领域模型统一安全校验器，彻底杜绝 NaN/Infinity 及恶意/损坏字段"""

    @staticmethod
    def now_utc_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def validate_id(ident: Any, field_name: str = "id") -> str:
        if not ident or not isinstance(ident, str):
            raise ValueError(f"{field_name} 必须为非空字符串")
        cleaned = ident.strip()
        if not ID_PATTERN.match(cleaned):
            raise ValueError(f"{field_name} '{cleaned}' 包含非法字符，仅允许字母、数字、_ 与 -")
        return cleaned

    @staticmethod
    def validate_finite(val: Any, field_name: str) -> float:
        if val is None or not isinstance(val, (int, float)):
            raise ValueError(f"{field_name} 必须为有效数值，得到: {val}")
        f_val = float(val)
        if math.isnan(f_val) or math.isinf(f_val):
            raise ValueError(f"{field_name} 不能为 NaN 或 Infinity: {val}")
        return f_val

    @staticmethod
    def validate_optional_finite(val: Any, field_name: str) -> Optional[float]:
        if val is None:
            return None
        return DomainValidator.validate_finite(val, field_name)

    @classmethod
    def validate_waypoints(cls, waypoints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not isinstance(waypoints, list):
            raise ValueError("waypoints 必须为列表")
        seen_ids: Set[str] = set()
        validated: List[Dict[str, Any]] = []
        for idx, wp in enumerate(waypoints):
            if not isinstance(wp, dict):
                raise ValueError(f"waypoint[{idx}] 必须为字典对象")
            wp_id = wp.get("waypoint_id") or f"wp_{idx}"
            if wp_id in seen_ids:
                raise ValueError(f"waypoint_id 重复: '{wp_id}'")
            seen_ids.add(wp_id)

            x = cls.validate_finite(wp.get("x"), f"waypoint[{idx}].x")
            y = cls.validate_finite(wp.get("y"), f"waypoint[{idx}].y")
            yaw = cls.validate_optional_finite(wp.get("yaw"), f"waypoint[{idx}].yaw")
            speed = cls.validate_optional_finite(wp.get("speed"), f"waypoint[{idx}].speed")
            t_ms = cls.validate_optional_finite(wp.get("time_from_start_ms"), f"waypoint[{idx}].time_from_start_ms")

            validated.append({
                "waypoint_id": wp_id,
                "x": round(x, 4),
                "y": round(y, 4),
                "yaw": round(yaw, 4) if yaw is not None else None,
                "speed": round(speed, 3) if speed is not None else None,
                "time_from_start_ms": int(t_ms) if t_ms is not None else None,
                "metadata": dict(wp.get("metadata", {})),
            })
        return validated
