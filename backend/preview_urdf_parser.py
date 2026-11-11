import os
import json
import logging
import xml.etree.ElementTree as ET
import numpy as np
from typing import Any, Dict
from backend.npz_service import G1_30_LINK_NAMES, G1_30_BONE_PAIRS

logger = logging.getLogger("PreviewUrdfParser")


class PreviewUrdfParser:
    """URDF 解析与基于机械树正向运动学的 50fps 舞蹈姿态合成"""

    @staticmethod
    def parse_urdf_and_generate_motion(urdf_path: str, model_name: str, dest_folder: str, preview_dir: str) -> Dict[str, Any]:
        try:
            tree = ET.parse(urdf_path)
            root = tree.getroot()

            joints_dict = {}
            joints_list = []
            revolute_joint_names = []

            for j in root.findall("joint"):
                j_name = j.attrib.get("name", "")
                j_type = j.attrib.get("type", "fixed")
                p = j.find("parent").attrib["link"]
                c = j.find("child").attrib["link"]
                orig = j.find("origin")
                xyz = [float(v) for v in orig.attrib["xyz"].split()] if (orig is not None and "xyz" in orig.attrib) else [0.0, 0.0, 0.0]
                rpy = [float(v) for v in orig.attrib["rpy"].split()] if (orig is not None and "rpy" in orig.attrib) else [0.0, 0.0, 0.0]
                axis_el = j.find("axis")
                axis = [float(v) for v in axis_el.attrib["xyz"].split()] if (axis_el is not None and "xyz" in axis_el.attrib) else [0.0, 1.0, 0.0]

                joint_data = {
                    "name": j_name, "type": j_type, "parent": p, "child": c,
                    "origin_xyz": xyz, "origin_rpy": rpy, "axis": axis
                }
                joints_dict[c] = joint_data
                joints_list.append(joint_data)
                if j_type in ("revolute", "continuous"):
                    revolute_joint_names.append(j_name)

            links_list = []
            rel_folder = os.path.relpath(dest_folder, preview_dir).replace("\\", "/")

            for l in root.findall("link"):
                l_name = l.attrib.get("name", "")
                vis = l.find("visual")
                if vis is not None:
                    geom = vis.find("geometry")
                    if geom is not None and geom.find("mesh") is not None:
                        fn = geom.find("mesh").attrib.get("filename", "")
                        if fn:
                            clean_fn = fn.replace("\\", "/").lstrip("/")
                            links_list.append({
                                "name": l_name,
                                "link_name": l_name,
                                "mesh_url": f"/preview/{rel_folder}/{clean_fn}"
                            })

            fps = 50.0
            duration_sec = 6.0
            total_frames = int(duration_sec * fps)
            pelvis_trajectories = []
            joint_trajectories = []

            for t in range(total_frames):
                time_val = t / fps
                phase = time_val * 2.0 * np.pi * 1.0
                beat = time_val * 2.0 * np.pi * 2.0
                bounce = 0.016 * np.sin(beat) ** 2
                pelvis_trajectories.append([
                    round(0.02 * np.sin(phase), 4),
                    round(0.03 * np.sin(phase), 4),
                    round(0.770 - bounce, 4)
                ])

                q = {"waist_yaw_joint": round(0.18 * np.sin(phase), 4)}
                for jn in revolute_joint_names:
                    if jn not in q:
                        q[jn] = round(0.15 * np.sin(phase), 4)
                joint_trajectories.append(q)

            def rpy_to_mat(r, p, y):
                cr, sr = np.cos(r), np.sin(r)
                cp, sp = np.cos(p), np.sin(p)
                cy, sy = np.cos(y), np.sin(y)
                Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]], dtype=np.float32)
                Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]], dtype=np.float32)
                Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]], dtype=np.float32)
                return Rz @ Ry @ Rx

            def link_transform(xyz, rpy):
                T = np.eye(4, dtype=np.float32)
                T[:3, :3] = rpy_to_mat(*rpy)
                T[:3, 3] = xyz
                return T

            fk_cache = {}
            def get_link_fk(link_name):
                if link_name in fk_cache:
                    return fk_cache[link_name]
                if link_name == "pelvis" or link_name not in joints_dict:
                    T = np.eye(4, dtype=np.float32)
                    T[:3, 3] = [0.0, 0.0, 0.76]
                    fk_cache[link_name] = T
                    return T
                jd = joints_dict[link_name]
                p_T = get_link_fk(jd["parent"])
                j_T = link_transform(jd["origin_xyz"], jd["origin_rpy"])
                T = p_T @ j_T
                fk_cache[link_name] = T
                return T

            base_pose = np.zeros((30, 3), dtype=np.float32)
            for idx, name in enumerate(G1_30_LINK_NAMES):
                candidates = [k for k in joints_dict.keys() if name in k]
                target_link = candidates[0] if candidates else name
                base_pose[idx] = get_link_fk(target_link)[:3, 3]

            for item in links_list:
                item["base_pos"] = get_link_fk(item["name"])[:3, 3].round(4).tolist()

            frames = np.zeros((total_frames, 30, 3), dtype=np.float32)
            for t in range(total_frames):
                pt = pelvis_trajectories[t]
                frames[t] = base_pose + np.array([pt[0], pt[1], pt[2] - 0.76], dtype=np.float32)

            model_info = {
                "has_robot_model": True,
                "model_name": model_name,
                "root_link": "pelvis",
                "parts_count": len(links_list),
                "parts": links_list,
                "links": links_list,
                "joints": joints_list,
                "motion": {
                    "pelvis_trajectory": pelvis_trajectories,
                    "joint_trajectory": joint_trajectories
                },
                "base_pose": base_pose.round(4).tolist()
            }

            dance_id = f"{model_name}_dance"
            npz_save_path = os.path.join(preview_dir, f"{dance_id}.npz")
            np.savez_compressed(
                npz_save_path,
                positions=frames,
                fps=fps,
                dance_name=dance_id,
                joint_count=30,
                model_info=json.dumps(model_info)
            )

            frames_data = frames.round(4).tolist()
            return {
                "success": True,
                "dance_name": dance_id,
                "dance_id": dance_id,
                "filename": f"{dance_id}.npz",
                "fps": fps,
                "total_frames": total_frames,
                "duration_seconds": round(total_frames / fps, 2),
                "joint_count": 30,
                "joint_names": G1_30_LINK_NAMES,
                "bone_pairs": G1_30_BONE_PAIRS,
                "frames": frames_data,
                "model_info": model_info,
                "msg": "✓ 成功解析 URDF 机器人模型，生成 50fps 动捕舞蹈"
            }
        except Exception as e:
            logger.error(f"URDF 模型解析失败: {e}")
            return {"success": False, "msg": f"URDF 模型解析失败: {str(e)}"}


preview_urdf_parser = PreviewUrdfParser()
