"""
@file: src/domain/trajectory/formation_matrix_planner.py
@brief: 多机网格方阵、中英文字符点阵提取与队形变换轨迹规划器
@exports: FormationMatrixPlanner, formation_matrix_planner
"""
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from src.domain.trajectory.spline_builder import SplineTrajectoryBuilder


class FormationMatrixPlanner:
    """多机器人网格方阵排布、字符点阵自适应提取与队形重构算法引擎"""

    @staticmethod
    def generate_grid_formation(
        num_robots: int, rows: int, cols: int, spacing: float = 1.2,
        center_x: float = 0.0, center_y: float = 0.0, heading_deg: float = 0.0
    ) -> List[Tuple[float, float, float]]:
        num = max(1, min(int(num_robots), 144))
        r, c = max(1, int(rows)), max(1, int(cols))
        if r * c < num:
            c = math.ceil(num / r)
        start_x = center_x - ((c - 1) * spacing) / 2.0
        start_y = center_y + ((r - 1) * spacing) / 2.0
        poses: List[Tuple[float, float, float]] = []
        for i in range(r):
            for j in range(c):
                if len(poses) >= num:
                    break
                poses.append((round(start_x + j * spacing, 4), round(start_y - i * spacing, 4), round(heading_deg, 2)))
            if len(poses) >= num:
                break
        return poses

    @classmethod
    def generate_line_formation(
        cls, num_robots: int, spacing: float = 1.2, center_x: float = 0.0,
        center_y: float = 0.0, heading_deg: float = 0.0
    ) -> List[Tuple[float, float, float]]:
        return cls.generate_grid_formation(num_robots, rows=1, cols=num_robots, spacing=spacing, center_x=center_x, center_y=center_y, heading_deg=heading_deg)

    @classmethod
    def generate_column_formation(
        cls, num_robots: int, spacing: float = 1.2, center_x: float = 0.0,
        center_y: float = 0.0, heading_deg: float = 0.0
    ) -> List[Tuple[float, float, float]]:
        return cls.generate_grid_formation(num_robots, rows=num_robots, cols=1, spacing=spacing, center_x=center_x, center_y=center_y, heading_deg=heading_deg)

    @staticmethod
    def generate_circle_formation(
        num_robots: int, radius_m: float = 2.0, center_x: float = 0.0,
        center_y: float = 0.0, heading_deg: float = 0.0
    ) -> List[Tuple[float, float, float]]:
        num = max(1, int(num_robots))
        poses: List[Tuple[float, float, float]] = []
        for i in range(num):
            angle_rad = (2.0 * math.pi * i) / num
            x = center_x + radius_m * math.cos(angle_rad)
            y = center_y + radius_m * math.sin(angle_rad)
            poses.append((round(x, 4), round(y, 4), round(heading_deg, 2)))
        return poses

    @classmethod
    def _get_font(cls, size: int) -> ImageFont.ImageFont:
        fonts = ["msyh.ttc", "simhei.ttf", "simsun.ttc", "arial.ttf",
                 "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/arial.ttf"]
        for f in fonts:
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
        return ImageFont.load_default()

    @classmethod
    def _sample_char_dots(cls, char: str, num_points: int) -> List[Tuple[float, float]]:
        sz = 96
        img = Image.new("1", (sz, sz), 0)
        draw = ImageDraw.Draw(img)
        font = cls._get_font(sz - 16)
        bbox = draw.textbbox((0, 0), char, font=font)
        bx, by = (sz - (bbox[2] - bbox[0])) // 2 - bbox[0], (sz - (bbox[3] - bbox[1])) // 2 - bbox[1]
        draw.text((bx, by), char, fill=1, font=font)
        raw = [(c, sz - 1 - r) for r in range(sz) for c in range(sz) if img.getpixel((c, r)) > 0]
        if not raw:
            angles = np.linspace(0, 2 * math.pi, num_points, endpoint=False)
            return [(round(float(math.cos(a) * 0.4), 4), round(float(math.sin(a) * 0.4), 4)) for a in angles]
        arr = np.array(raw, dtype=np.float32)
        span = max(float(np.max(np.max(arr, axis=0) - np.min(arr, axis=0))), 1.0)
        norm = (arr - (np.min(arr, axis=0) + np.max(arr, axis=0)) / 2.0) / span
        sampled = norm[np.linspace(0, len(norm) - 1, num_points, dtype=int)]
        return [(round(float(p[0]), 4), round(float(p[1]), 4)) for p in sampled]

    @classmethod
    def extract_char_dot_matrix(
        cls, text: str, mode: str = "single", font_size_m: float = 4.0, spacing_m: float = 1.0,
        center_x: float = 0.0, center_y: float = 0.0, num_points: int = 16
    ) -> Union[List[Tuple[float, float]], List[List[Tuple[float, float]]]]:
        chars = [c for c in text if not c.isspace()] or ["G"]
        n_pts = max(4, int(num_points))
        m = mode.lower()
        if m == "single":
            dots = cls._sample_char_dots(chars[0], n_pts)
            return [(round(center_x + dx * font_size_m, 4), round(center_y + dy * font_size_m, 4)) for dx, dy in dots]
        if m == "sequential":
            return [
                [(round(center_x + dx * font_size_m, 4), round(center_y + dy * font_size_m, 4))
                 for dx, dy in cls._sample_char_dots(ch, n_pts)]
                for ch in chars
            ]
        cnt = len(chars)
        tot_w = cnt * font_size_m + (cnt - 1) * spacing_m
        st_x = center_x - tot_w / 2.0 + font_size_m / 2.0
        combined: List[Tuple[float, float]] = []
        for idx, ch in enumerate(chars):
            cx = st_x + idx * (font_size_m + spacing_m)
            dots = cls._sample_char_dots(ch, n_pts)
            combined.extend([(round(cx + dx * font_size_m, 4), round(center_y + dy * font_size_m, 4)) for dx, dy in dots])
        return combined

    @staticmethod
    def compute_min_pairwise_distance(points: List[Union[Tuple[float, float], Tuple[float, float, float]]]) -> float:
        if len(points) < 2:
            return float("inf")
        arr = np.array([p[:2] for p in points], dtype=np.float32)
        diff = arr[:, np.newaxis, :] - arr[np.newaxis, :, :]
        dist_mat = np.linalg.norm(diff, axis=-1)
        np.fill_diagonal(dist_mat, float("inf"))
        return round(float(np.min(dist_mat)), 4)

    @classmethod
    def assign_targets_optimal(
        cls, start_positions: List[Union[Tuple, List]], target_positions: List[Union[Tuple, List]]
    ) -> Dict[int, int]:
        n_s, n_t = len(start_positions), len(target_positions)
        if n_s == 0 or n_t == 0:
            return {}
        try:
            from scipy.optimize import linear_sum_assignment
            cost = np.zeros((n_s, n_t), dtype=np.float64)
            for i, sp in enumerate(start_positions):
                for j, tp in enumerate(target_positions):
                    cost[i, j] = (sp[0] - tp[0]) ** 2 + (sp[1] - tp[1]) ** 2
            r_idx, c_idx = linear_sum_assignment(cost)
            return {int(r): int(c) for r, c in zip(r_idx, c_idx)}
        except Exception:
            return cls.assign_targets_greedy(start_positions, target_positions)

    @staticmethod
    def assign_targets_greedy(
        start_positions: List[Union[Tuple, List]], target_positions: List[Union[Tuple, List]]
    ) -> Dict[int, int]:
        mapping: Dict[int, int] = {}
        avail = set(range(len(target_positions)))
        for r_idx, s in enumerate(start_positions):
            if not avail:
                break
            best = min(avail, key=lambda t: (target_positions[t][0] - s[0]) ** 2 + (target_positions[t][1] - s[1]) ** 2)
            mapping[r_idx] = best
            avail.remove(best)
        return mapping

    @staticmethod
    def swap_robot_targets(mapping: Dict[int, int], robot_a: int, robot_b: int) -> Dict[int, int]:
        res = dict(mapping)
        if robot_a in res and robot_b in res:
            res[robot_a], res[robot_b] = res[robot_b], res[robot_a]
        return res

    @classmethod
    def generate_formation_transition_trajectories(
        cls, current_poses: List[Tuple[float, float, float]], target_poses: List[Tuple[float, float, float]],
        max_acc: float = 1.5, v_max: float = 1.2
    ) -> Dict[int, List[Tuple[float, float, float, float]]]:
        trajs: Dict[int, List[Tuple[float, float, float, float]]] = {}
        for idx in range(min(len(current_poses), len(target_poses))):
            curr, tgt = current_poses[idx], target_poses[idx]
            pts, _ = SplineTrajectoryBuilder.compile_waypoints(
                waypoints=[(curr[0], curr[1]), (tgt[0], tgt[1])],
                mode="uniform", max_acc=max_acc, v_max=v_max, end_turn=True, end_turn_yaw=tgt[2]
            )
            trajs[idx] = pts
        return trajs

    @classmethod
    def plan_multi_word_sequence(
        cls, text: str, initial_poses: List[Tuple[float, float, float]], font_size_m: float = 4.0,
        dwell_time: float = 3.0, max_acc: float = 1.5, v_max: float = 1.2, end_turn_yaw: float = 0.0
    ) -> List[Dict[str, Any]]:
        chars = [c for c in text if not c.isspace()] or ["G"]
        n_rob = len(initial_poses)
        curr = list(initial_poses)
        stages: List[Dict[str, Any]] = []

        for s_idx, ch in enumerate(chars):
            dots = cls._sample_char_dots(ch, n_rob)
            tgt_pts = [(dx * font_size_m, dy * font_size_m) for dx, dy in dots]
            mapping = cls.assign_targets_optimal(curr, tgt_pts)
            ordered: List[Tuple[float, float, float]] = [
                (tgt_pts[mapping[i]][0], tgt_pts[mapping[i]][1], end_turn_yaw) for i in range(n_rob)
            ]
            min_dist = cls.compute_min_pairwise_distance(ordered)
            trajs = cls.generate_formation_transition_trajectories(curr, ordered, max_acc=max_acc, v_max=v_max)
            dur = max((t[-1][0] for t in trajs.values() if t), default=0.0)
            stages.append({
                "stage_index": s_idx, "char": ch, "min_distance": min_dist,
                "duration": round(float(dur), 2), "dwell_time": float(dwell_time),
                "trajectories": trajs, "target_poses": ordered
            })
            curr = ordered
        return stages


formation_matrix_planner = FormationMatrixPlanner()
