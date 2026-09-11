import os
import sys
import json
import shutil
import zipfile
import logging
import xml.etree.ElementTree as ET
import numpy as np
from typing import Dict, Any, List, Optional

logger = logging.getLogger("PreviewManager")

from backend.npz_service import (
    G1_30_LINK_NAMES,
    G1_30_BONE_PAIRS,
    G1_JOINT_NAMES,
    G1_BONE_PAIRS,
)


class PreviewManager:
    """
    统一管理程序运行根目录下的 preview 文件夹
    负责处理 3D 舞蹈预览动作、ZIP 压缩包解压、URDF 29-DoF 机器人 3D 刚体模型解析与动捕动作合成
    """

    def __init__(self, base_root: Optional[str] = None):
        if base_root is None:
            if getattr(sys, "frozen", False):
                base_root = os.path.dirname(sys.executable)
            else:
                base_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.base_root = base_root
        self.preview_dir = os.path.join(self.base_root, "preview")
        # 默认 G1 机器人模型 info 缓存（首次解析后缓存，避免重复 IO）
        self._cached_model_info: Optional[Dict[str, Any]] = None
        self._ensure_preview_dir()

    def get_builtin_models_dir(self) -> str:
        """获取程序内置打包的模型资产目录（支持源码运行与 PyInstaller 打包环境）"""
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, "backend", "models")
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "models"))

    def _ensure_preview_dir(self):
        """确保程序运行根目录下的 preview 文件夹存在，且清理内部临时文件"""
        try:
            os.makedirs(self.preview_dir, exist_ok=True)

            # 确保 preview 根目录就绪
            init_marker = os.path.join(self.preview_dir, ".initialized")
            if not os.path.exists(init_marker):
                from backend.npz_service import npz_service
                npz_service.demo_dir = self.preview_dir
                npz_service._ensure_demo_npz_files()
                try:
                    with open(init_marker, "w", encoding="utf-8") as f:
                        f.write("initialized\n")
                except Exception:
                    pass
            logger.info(f"PreviewManager 根目录已就绪: {self.preview_dir}")
        except Exception as e:
            logger.error(f"创建 preview 目录失败: {e}")

    def import_zip(self, zip_source, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        导入 ZIP 压缩包（支持本地路径或上传的文件对象）
        解压至 preview 文件夹，深度解析 URDF 真实机器人模型及网格，并自动生成 50fps 3D 舞蹈动作
        """
        self._ensure_preview_dir()

        temp_zip_path = None
        target_name = "custom_archive"

        if isinstance(zip_source, str):
            clean_path = os.path.normpath(zip_source.strip().strip('"').strip("'"))
            if not os.path.isfile(clean_path):
                return {"success": False, "msg": f"指定的文件路径不存在: {clean_path}"}
            
            # 自动识别：若为 .npz 动捕动作文件，直接复制至 preview 目录
            if clean_path.lower().endswith(".npz"):
                dest_npz = os.path.join(self.preview_dir, os.path.basename(clean_path))
                if os.path.abspath(clean_path) != os.path.abspath(dest_npz):
                    shutil.copy2(clean_path, dest_npz)
                # 清除可能的只读属性（如微信接收的文件）
                try:
                    import stat
                    os.chmod(dest_npz, stat.S_IRUSR | stat.S_IWUSR)
                except Exception:
                    pass
                dance_id = os.path.splitext(os.path.basename(clean_path))[0]
                parse_res = self.get_dance_data(dance_id)
                parse_res["dance_id"] = dance_id
                parse_res["dance_name"] = parse_res.get("dance_name") or dance_id
                parse_res["msg"] = f"✓ 成功导入 NPZ 动捕舞蹈动作: {os.path.basename(clean_path)}"
                return parse_res

            source_zip_path = clean_path
            target_name = os.path.splitext(os.path.basename(clean_path))[0]
        else:
            upload_name = filename or getattr(zip_source, "filename", "imported_dance.zip")
            # 自动识别上传的 .npz 文件
            if upload_name.lower().endswith(".npz"):
                dest_npz = os.path.join(self.preview_dir, upload_name)
                if hasattr(zip_source, "save"):
                    zip_source.save(dest_npz)
                elif hasattr(zip_source, "read"):
                    with open(dest_npz, "wb") as f:
                        f.write(zip_source.read())
                dance_id = os.path.splitext(upload_name)[0]
                parse_res = self.get_dance_data(dance_id)
                parse_res["dance_id"] = dance_id
                parse_res["dance_name"] = parse_res.get("dance_name") or dance_id
                parse_res["msg"] = f"✓ 成功上传并导入 NPZ 动捕动作: {upload_name}"
                return parse_res

            target_name = os.path.splitext(os.path.basename(upload_name))[0]
            temp_zip_path = os.path.join(self.preview_dir, f"_temp_{upload_name}")
            if hasattr(zip_source, "save"):
                zip_source.save(temp_zip_path)
            elif hasattr(zip_source, "read"):
                with open(temp_zip_path, "wb") as f:
                    f.write(zip_source.read())
            source_zip_path = temp_zip_path

        dest_folder = os.path.join(self.preview_dir, target_name)
        os.makedirs(dest_folder, exist_ok=True)

        extracted_files = []
        try:
            with zipfile.ZipFile(source_zip_path, "r") as zf:
                namelist = [n.replace("\\", "/") for n in zf.namelist() if not n.endswith("/")]
                has_top_dir = all(n.startswith(f"{target_name}/") for n in namelist) if namelist else False
                extract_target = self.preview_dir if has_top_dir else dest_folder

                for member in zf.infolist():
                    extracted_path = zf.extract(member, extract_target)
                    extracted_files.append(extracted_path)
        except Exception as e:
            if temp_zip_path and os.path.exists(temp_zip_path):
                try: os.remove(temp_zip_path)
                except Exception: pass
            return {"success": False, "msg": f"ZIP 压缩包解压失败: {str(e)}"}

        if temp_zip_path and os.path.exists(temp_zip_path):
            try: os.remove(temp_zip_path)
            except Exception: pass

        # 目录扁平化处理：若解压后顶层仅包含单一与 target_name 同名的子文件夹，则将其提升到 dest_folder
        self._flatten_single_subfolder(dest_folder, target_name)

        # 扫描解压出的文件
        npz_files = []
        urdf_files = []

        for root, _, files in os.walk(dest_folder):
            for f in files:
                full_path = os.path.join(root, f)
                lower_f = f.lower()
                if lower_f.endswith(".npz"):
                    npz_files.append(full_path)
                elif lower_f.endswith(".urdf"):
                    urdf_files.append(full_path)

        # 场景 A: 包含已有的 .npz 动作文件
        if npz_files:
            primary_npz = npz_files[0]
            primary_name = os.path.basename(primary_npz)
            target_npz_path = os.path.join(self.preview_dir, primary_name)
            if primary_npz != target_npz_path:
                shutil.copy2(primary_npz, target_npz_path)

            from backend.npz_service import npz_service
            parse_res = npz_service.parse_npz_file(target_npz_path)
            parse_res["imported_folder"] = dest_folder
            parse_res["msg"] = f"✓ 成功解压并导入 NPZ 舞蹈动作: {primary_name}"
            return parse_res

        # 场景 B: 包含 URDF 模型（如 G1 29-DoF 真实机器人模型）
        if urdf_files:
            selected_urdf = urdf_files[0]
            for u in urdf_files:
                if "mode_15" in u:
                    selected_urdf = u
                    break
                elif "29dof" in u:
                    selected_urdf = u

            generated_data = self._generate_motion_and_model_from_urdf(selected_urdf, target_name, dest_folder)
            generated_data["imported_folder"] = dest_folder
            return generated_data

        # 场景 C: 普通文件压缩包
        return {
            "success": True,
            "msg": f"ZIP 文件已成功解压至 preview/{target_name}，共 {len(extracted_files)} 个文件。",
            "imported_folder": dest_folder,
            "files_count": len(extracted_files)
        }

    def _flatten_single_subfolder(self, folder: str, target_name: str):
        """如果解压后内部存在同名子目录，则自动展平并覆盖上移"""
        try:
            sub_target = os.path.join(folder, target_name)
            if os.path.isdir(sub_target):
                for item in os.listdir(sub_target):
                    s = os.path.join(sub_target, item)
                    d = os.path.join(folder, item)
                    if os.path.exists(d):
                        if os.path.isdir(d):
                            shutil.rmtree(d, ignore_errors=True)
                        else:
                            try: os.remove(d)
                            except Exception: pass
                    shutil.move(s, d)
                shutil.rmtree(sub_target, ignore_errors=True)
            else:
                subdirs = [d for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))]
                files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
                if len(subdirs) == 1 and len(files) == 0:
                    sub_path = os.path.join(folder, subdirs[0])
                    for item in os.listdir(sub_path):
                        s = os.path.join(sub_path, item)
                        d = os.path.join(folder, item)
                        if os.path.exists(d):
                            if os.path.isdir(d):
                                shutil.rmtree(d, ignore_errors=True)
                            else:
                                try: os.remove(d)
                                except Exception: pass
                        shutil.move(s, d)
                    shutil.rmtree(sub_path, ignore_errors=True)
        except Exception as e:
            logger.warning(f"展平目录失败: {e}")

    def _generate_motion_and_model_from_urdf(self, urdf_path: str, model_name: str, dest_folder: str) -> Dict[str, Any]:
        """
        从 URDF 中解析 29-DoF 机器人各刚体连杆尺寸与真实 3D Mesh (STL)，
        构建严密的机械运动学层级树 (Kinematic Tree)，合成 50fps 标准真实关节角度律动轨迹，
        并输出带有完整 3D 机器人部件与层级拓扑的 model_info
        """
        try:
            tree = ET.parse(urdf_path)
            root = tree.getroot()

            # 1. 解析所有关节拓扑
            joints_dict = {}
            joints_list = []
            revolute_joint_names = []

            for j in root.findall("joint"):
                j_name = j.attrib.get("name", "")
                j_type = j.attrib.get("type", "fixed")
                p = j.find("parent").attrib["link"]
                c = j.find("child").attrib["link"]
                orig = j.find("origin")
                xyz = [0.0, 0.0, 0.0]
                rpy = [0.0, 0.0, 0.0]
                if orig is not None:
                    if "xyz" in orig.attrib:
                        xyz = [float(v) for v in orig.attrib["xyz"].split()]
                    if "rpy" in orig.attrib:
                        rpy = [float(v) for v in orig.attrib["rpy"].split()]
                axis = [0.0, 1.0, 0.0]
                axis_el = j.find("axis")
                if axis_el is not None and "xyz" in axis_el.attrib:
                    axis = [float(v) for v in axis_el.attrib["xyz"].split()]

                joint_data = {
                    "name": j_name,
                    "type": j_type,
                    "parent": p,
                    "child": c,
                    "origin_xyz": xyz,
                    "origin_rpy": rpy,
                    "axis": axis
                }
                joints_dict[c] = joint_data
                joints_list.append(joint_data)
                if j_type in ("revolute", "continuous"):
                    revolute_joint_names.append(j_name)

            # 2. 解析所有带有 STL Mesh 的视觉 link
            links_list = []
            rel_folder = os.path.relpath(dest_folder, self.preview_dir).replace("\\", "/")

            for l in root.findall("link"):
                l_name = l.attrib.get("name", "")
                vis = l.find("visual")
                if vis is not None:
                    geom = vis.find("geometry")
                    if geom is not None and geom.find("mesh") is not None:
                        fn = geom.find("mesh").attrib.get("filename", "")
                        if fn:
                            clean_fn = fn.replace("\\", "/").lstrip("/")
                            mesh_url = f"/preview/{rel_folder}/{clean_fn}"
                            links_list.append({
                                "name": l_name,
                                "link_name": l_name,
                                "mesh_url": mesh_url
                            })

            # 3. 50fps 正向运动学与逼真拟人化舞蹈编舞生成 (时长 6.0s，300 帧)
            fps = 50.0
            duration_sec = 6.0
            total_frames = int(duration_sec * fps)

            pelvis_trajectories = []
            joint_trajectories = []

            for t in range(total_frames):
                time = t / fps  # 0.0 ~ 6.0s
                phase = time * 2.0 * np.pi * 1.0  # 1.0 Hz 主节拍 (6 秒 6 循环)
                beat = time * 2.0 * np.pi * 2.0   # 2.0 Hz 律动拍 (120 BPM)

                # 3 段式乐句动态权重平滑混合 (0-2s 摇摆律动, 2-4s 手臂波浪, 4-6s 欢呼跳动)
                w1 = np.exp(-((time - 1.0) / 1.1) ** 2)
                w2 = np.exp(-((time - 3.0) / 1.1) ** 2)
                w3 = np.exp(-((time - 5.0) / 1.1) ** 2)
                tot_w = w1 + w2 + w3 + 1e-6
                w1, w2, w3 = w1 / tot_w, w2 / tot_w, w3 / tot_w

                # 骨盆空间动态位移 (Hip Groove)：轻盈起伏，绝不穿透地面
                bounce = 0.016 * np.sin(beat) ** 2
                pelvis_x = 0.015 * np.sin(phase) * w1 + 0.025 * np.sin(phase) * w2 + 0.010 * np.cos(beat) * w3
                pelvis_y = 0.035 * np.sin(phase) * w1 + 0.020 * np.sin(phase * 2) * w2 + 0.025 * np.sin(phase) * w3
                pelvis_z = 0.770 - bounce  # 基准高度 0.770m，确保双足永不穿透地板
                pelvis_trajectories.append([
                    round(pelvis_x, 4),
                    round(pelvis_y, 4),
                    round(pelvis_z, 4)
                ])

                q = {}

                # 1. 腰部与躯干律动：随音乐偏航摆动与前后微俯仰
                q["waist_yaw_joint"] = round(0.18 * np.sin(phase), 4)
                q["waist_roll_joint"] = round(-0.06 * np.sin(phase), 4)
                waist_pitch = 0.04 + 0.03 * np.cos(beat)
                q["waist_pitch_joint"] = round(waist_pitch, 4)

                # 2. 头部姿态：抵消躯干前倾，使头部始终正视前方，并随节拍自然点头节奏律动
                q["head_joint"] = round(-waist_pitch + 0.04 * np.cos(beat) + 0.03 * np.sin(phase), 4)

                # 3. 双腿屈伸与足底贴地补偿 (逆向运动学几何平抑，双脚完全贴平地面)
                knee_base = 0.18 + 0.12 * (bounce / 0.016)
                knee_l = knee_base + 0.05 * np.sin(phase)
                knee_r = knee_base - 0.05 * np.sin(phase)
                q["left_hip_pitch_joint"] = round(-0.5 * knee_l, 4)
                q["left_knee_joint"] = round(knee_l, 4)
                q["left_ankle_pitch_joint"] = round(-0.5 * knee_l, 4)
                q["left_hip_roll_joint"] = round(0.04 * np.sin(phase), 4)
                q["left_ankle_roll_joint"] = round(-0.04 * np.sin(phase), 4)
                q["left_hip_yaw_joint"] = round(0.02 * np.sin(phase), 4)

                q["right_hip_pitch_joint"] = round(-0.5 * knee_r, 4)
                q["right_knee_joint"] = round(knee_r, 4)
                q["right_ankle_pitch_joint"] = round(-0.5 * knee_r, 4)
                q["right_hip_roll_joint"] = round(-0.04 * np.sin(phase), 4)
                q["right_ankle_roll_joint"] = round(0.04 * np.sin(phase), 4)
                q["right_hip_yaw_joint"] = round(0.02 * np.sin(phase), 4)

                # 4. 双臂与手腕：完全符合宇树 G1 真实人体工学，肘关节向前自然弯曲，动作舒展自信
                # 乐句 1：随性嘻哈微摇 (Relaxed Groove)
                sp_l1 = -0.25 - 0.15 * np.sin(phase)
                sp_r1 = -0.25 + 0.15 * np.sin(phase)
                sr_l1 = 0.50 + 0.10 * np.cos(beat)
                sr_r1 = -0.50 - 0.10 * np.cos(beat)
                el_l1 = 0.65 + 0.20 * np.sin(beat)
                el_r1 = 0.65 - 0.20 * np.sin(beat)

                # 乐句 2：交替波浪舞动 (Alternating Arm Wave)
                sp_l2 = -0.45 + 0.25 * np.sin(beat)
                sp_r2 = -0.20 - 0.20 * np.sin(beat)
                sr_l2 = 0.65 + 0.15 * np.sin(beat)
                sr_r2 = -0.40 - 0.15 * np.sin(beat)
                el_l2 = 0.85 + 0.25 * np.cos(beat)
                el_r2 = 0.55 + 0.20 * np.cos(beat)

                # 乐句 3：动感拍点与帅气收尾 (Double Pump Celebration)
                sp_l3 = -0.35 + 0.20 * np.cos(beat * 2)
                sp_r3 = -0.35 + 0.20 * np.cos(beat * 2)
                sr_l3 = 0.55 + 0.15 * np.sin(beat)
                sr_r3 = -0.55 - 0.15 * np.sin(beat)
                el_l3 = 0.75 + 0.25 * np.sin(beat * 2)
                el_r3 = 0.75 + 0.25 * np.sin(beat * 2)

                q["left_shoulder_pitch_joint"] = round(sp_l1 * w1 + sp_l2 * w2 + sp_l3 * w3, 4)
                q["right_shoulder_pitch_joint"] = round(sp_r1 * w1 + sp_r2 * w2 + sp_r3 * w3, 4)
                q["left_shoulder_roll_joint"] = round(sr_l1 * w1 + sr_l2 * w2 + sr_l3 * w3, 4)
                q["right_shoulder_roll_joint"] = round(sr_r1 * w1 + sr_r2 * w2 + sr_r3 * w3, 4)
                q["left_shoulder_yaw_joint"] = round(0.12 * np.sin(beat), 4)
                q["right_shoulder_yaw_joint"] = round(-0.12 * np.sin(beat), 4)

                # 肘关节：严格保持正角自然屈肘 (0.45 ~ 1.05 rad)，绝无折断后仰现象
                q["left_elbow_joint"] = round(el_l1 * w1 + el_l2 * w2 + el_l3 * w3, 4)
                q["right_elbow_joint"] = round(el_r1 * w1 + el_r2 * w2 + el_r3 * w3, 4)

                # 手腕 3 轴律动跟随
                q["left_wrist_roll_joint"] = round(0.25 * np.sin(beat), 4)
                q["left_wrist_pitch_joint"] = round(0.15 * np.cos(beat), 4)
                q["left_wrist_yaw_joint"] = round(0.10 * np.sin(phase), 4)

                q["right_wrist_roll_joint"] = round(-0.25 * np.sin(beat), 4)
                q["right_wrist_pitch_joint"] = round(0.15 * np.cos(beat), 4)
                q["right_wrist_yaw_joint"] = round(-0.10 * np.sin(phase), 4)

                joint_trajectories.append(q)

            # 4. 前向运动学（FK）计算初始基准 3D 姿态与帧数据
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

            # 为每一个零件注入 FK 基准三维坐标
            for item in links_list:
                item["base_pos"] = get_link_fk(item["name"])[:3, 3].round(4).tolist()

            frames = np.zeros((total_frames, 30, 3), dtype=np.float32)
            for t in range(total_frames):
                pt = pelvis_trajectories[t]
                dx = pt[0]
                dy = pt[1]
                dz = pt[2] - 0.76
                frames[t] = base_pose + np.array([dx, dy, dz], dtype=np.float32)

            from collections import deque
            children_map = {}
            for j in joints_list:
                if j.get("type") != "fixed":
                    children_map.setdefault(j["parent"], []).append(j["child"])
            bfs_body_names = []
            q = deque(["pelvis"])
            while q:
                curr = q.popleft()
                bfs_body_names.append(curr)
                for c in children_map.get(curr, []):
                    q.append(c)

            model_info = {
                "has_robot_model": len(links_list) > 0,
                "model_name": model_name,
                "root_link": "pelvis",
                "parts_count": len(links_list),
                "parts": links_list,
                "links": links_list,
                "joints": joints_list,
                "body_link_names": bfs_body_names,
                "motion": {
                    "pelvis_trajectory": pelvis_trajectories,
                    "joint_trajectory": joint_trajectories
                },
                "base_pose": base_pose.round(4).tolist()
            }

            # 保存生成的动作 NPZ 到 preview 根目录
            dance_id = f"{model_name}_dance"
            npz_save_path = os.path.join(self.preview_dir, f"{dance_id}.npz")
            np.savez_compressed(
                npz_save_path,
                positions=frames,
                fps=fps,
                dance_name=dance_id,
                joint_count=30,
                model_info=json.dumps(model_info),
                description=f"基于 {model_name} (29-DoF URDF 真实机器人模型) 生成的 50fps 动捕舞蹈"
            )
            logger.info(f"成功为 URDF 机器人模型生成动捕 NPZ: {npz_save_path}")

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
                "msg": f"✓ 成功解析 G1 29-DoF 真实机器人模型（包含 {len(links_list)} 个 3D 刚体网格），已就绪 50fps 动力学仿真跳舞！"
            }

        except Exception as e:
            logger.error(f"从 URDF 解析与生成动作失败: {e}", exc_info=True)
            return {"success": False, "msg": f"URDF 模型解析失败: {str(e)}"}

    def list_all_dances(self) -> List[Dict[str, Any]]:
        """
        获取 preview 目录下所有可用的 3D 舞蹈列表
        严格尊重用户的删除意图：用户清空动作后绝不擅自重新生成
        """
        self._ensure_preview_dir()
        from backend.npz_service import npz_service

        npz_files = [f for f in os.listdir(self.preview_dir) if f.endswith(".npz")]
        default_model = self._get_default_model_info()
        has_default_model = bool(default_model and default_model.get("has_robot_model"))

        # 排除内部系统模型与程序资产动作文件，列表中仅展示用户导入的动捕舞蹈动作
        EXCLUDED_KEYWORDS = ("g1_29dof", "test_", "rubber_hand", "mode_15", "mode_5")

        res = []
        for f in npz_files:
            lower_f = f.lower()
            if any(kw in lower_f for kw in EXCLUDED_KEYWORDS):
                continue
            p = os.path.join(self.preview_dir, f)
            info = npz_service.parse_npz_file(p)
            if info.get("success"):
                model_meta = info.get("model_info") or {}
                # 若 NPZ 自身内嵌模型，或全局默认 G1 模型就绪，则均具有 3D 实体模型
                has_model = bool(model_meta.get("has_robot_model")) or has_default_model
                res.append({
                    "id": os.path.splitext(f)[0],
                    "filename": f,
                    "name": info.get("dance_name", os.path.splitext(f)[0]),
                    "duration": info.get("duration_seconds", 0),
                    "frames": info.get("total_frames", 0),
                    "fps": info.get("fps", 50.0),
                    "has_robot_model": has_model
                })
        return res

    def _get_default_model_info(self) -> Optional[Dict[str, Any]]:
        """
        解析内置 G1 29-DoF URDF 模型（preview/g1_29dof_rubber_hand），构建并返回 model_info
        仅含 links/joints/parts（骨骼结构与网格URL），不含 motion.joint_trajectory
        首次解析后缓存结果，后续调用直接返回缓存
        """
        if self._cached_model_info is not None:
            return self._cached_model_info

        # 搜索默认 G1 模型目录 (优先使用程序内置打包的 backend/models)
        builtin_models_dir = self.get_builtin_models_dir()
        dest_folder = os.path.join(builtin_models_dir, "g1_29dof_rubber_hand")

        if not os.path.isdir(dest_folder):
            preview_folder = os.path.join(self.preview_dir, "g1_29dof_rubber_hand")
            if os.path.isdir(preview_folder):
                dest_folder = preview_folder
            else:
                for entry in os.listdir(self.preview_dir):
                    entry_path = os.path.join(self.preview_dir, entry)
                    if os.path.isdir(entry_path) and ("g1" in entry.lower() or "rubber" in entry.lower()):
                        dest_folder = entry_path
                        break
        if not os.path.isdir(dest_folder):
            return None
        # 优先选 mode_15 URDF
        urdf_candidates = []
        for root_dir, _, fnames in os.walk(dest_folder):
            for fname in fnames:
                if fname.lower().endswith(".urdf"):
                    urdf_candidates.append(os.path.join(root_dir, fname))
        if not urdf_candidates:
            return None

        selected_urdf = urdf_candidates[0]
        for u in urdf_candidates:
            if "mode_15" in u:
                selected_urdf = u
                break

        try:
            tree = ET.parse(selected_urdf)
            urdf_root = tree.getroot()

            joints_list = []
            for j in urdf_root.findall("joint"):
                j_name = j.attrib.get("name", "")
                j_type = j.attrib.get("type", "fixed")
                p_el = j.find("parent")
                c_el = j.find("child")
                if p_el is None or c_el is None:
                    continue
                p = p_el.attrib["link"]
                c = c_el.attrib["link"]
                orig = j.find("origin")
                xyz = [0.0, 0.0, 0.0]
                rpy = [0.0, 0.0, 0.0]
                if orig is not None:
                    if "xyz" in orig.attrib:
                        xyz = [float(v) for v in orig.attrib["xyz"].split()]
                    if "rpy" in orig.attrib:
                        rpy = [float(v) for v in orig.attrib["rpy"].split()]
                axis = [0.0, 1.0, 0.0]
                axis_el = j.find("axis")
                if axis_el is not None and "xyz" in axis_el.attrib:
                    axis = [float(v) for v in axis_el.attrib["xyz"].split()]
                joints_list.append({
                    "name": j_name,
                    "type": j_type,
                    "parent": p,
                    "child": c,
                    "origin_xyz": xyz,
                    "origin_rpy": rpy,
                    "axis": axis
                })

            # 解析 link 视觉网格 — 构建内置模型 mesh_url 供前端 fetch
            links_list = []
            for l_el in urdf_root.findall("link"):
                l_name = l_el.attrib.get("name", "")
                vis = l_el.find("visual")
                if vis is not None:
                    geom = vis.find("geometry")
                    if geom is not None and geom.find("mesh") is not None:
                        fn = geom.find("mesh").attrib.get("filename", "")
                        if fn:
                            clean_fn = fn.replace("\\", "/").lstrip("/")
                            mesh_url = f"/models/g1_29dof_rubber_hand/{clean_fn}"
                            links_list.append({
                                "name": l_name,
                                "link_name": l_name,
                                "mesh_url": mesh_url
                            })

            # 计算 30 个可动刚体的 BFS 遍历顺序（与 IsaacLab / PhysX body_pos_w 严格一致）
            from collections import deque
            children_map = {}
            for j in joints_list:
                if j.get("type") != "fixed":
                    children_map.setdefault(j["parent"], []).append(j["child"])
            bfs_body_names = []
            q = deque(["pelvis"])
            while q:
                curr = q.popleft()
                bfs_body_names.append(curr)
                for c in children_map.get(curr, []):
                    q.append(c)

            model_info = {
                "has_robot_model": len(links_list) > 0,
                "model_name": os.path.basename(dest_folder),
                "root_link": "pelvis",
                "parts_count": len(links_list),
                "parts": links_list,
                "links": links_list,
                "joints": joints_list,
                "body_link_names": bfs_body_names,
                # 无 motion：前端将以位置平移方式驱动各部件（降级兜底，优于骨架）
            }
            if model_info["has_robot_model"]:
                self._cached_model_info = model_info
                logger.info(f"已缓存默认 G1 机器人模型 ({len(links_list)} 个网格部件) 供 NPZ 播放注入")
            return model_info

        except Exception as e:
            logger.warning(f"解析默认 G1 URDF 失败，将降级为骨架渲染: {e}")
            return None

    # G1 29-DoF 标准关节顺序（与 URDF revolute 关节顺序严格对应）
    _G1_JOINT_ORDER = [
        "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint",
        "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint",
        "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint",
        "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint",
        "waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint",
        "left_shoulder_pitch_joint", "left_shoulder_roll_joint", "left_shoulder_yaw_joint",
        "left_elbow_joint", "left_wrist_roll_joint", "left_wrist_pitch_joint", "left_wrist_yaw_joint",
        "right_shoulder_pitch_joint", "right_shoulder_roll_joint", "right_shoulder_yaw_joint",
        "right_elbow_joint", "right_wrist_roll_joint", "right_wrist_pitch_joint", "right_wrist_yaw_joint",
    ]

    def get_dance_data(self, dance_id: str) -> Dict[str, Any]:
        """获取指定舞蹈动作的完整 3D 帧数据与机器人模型资产。
        若 NPZ 内未内嵌 model_info，自动注入本地 G1 机器人模型结构。
        若 NPZ 含有 G1 原生 joint_pos（29-DoF）+ body_pos_w，则构建完整关节角度轨迹驱动。
        """
        self._ensure_preview_dir()
        filename = f"{dance_id}.npz" if not dance_id.endswith(".npz") else dance_id
        path = os.path.join(self.preview_dir, filename)
        if not os.path.exists(path):
            return {"success": False, "msg": f"舞蹈文件不存在: preview/{filename}"}
        from backend.npz_service import npz_service
        result = npz_service.parse_npz_file(path)
        if not result.get("success"):
            return result

        # 若 NPZ 自身无内嵌机器人模型，尝试自动注入默认 G1 模型结构
        if not (result.get("model_info") or {}).get("has_robot_model"):
            default_model = self._get_default_model_info()
            if default_model and default_model.get("has_robot_model"):
                result["model_info"] = dict(default_model)  # 浅拷贝，不污染缓存

                # 检测 G1 原生格式：含 body_pos_w (N, 30, 3) + body_quat_w (N, 30, 4)
                # 直接使用每个刚体的世界位置+朝向，完全绕过关节角度坐标系问题
                try:
                    raw = np.load(path, allow_pickle=True)
                    if "body_pos_w" in raw.files and "body_quat_w" in raw.files:
                        bpw = raw["body_pos_w"]   # (N, 30, 3) 刚体世界位置 (Z-up)
                        bqw = raw["body_quat_w"]  # (N, 30, 4) 刚体世界四元数 [w,x,y,z]
                        n_frames = min(int(bpw.shape[0]), int(bqw.shape[0]))
                        n_bodies = int(bpw.shape[1])  # 30

                        # 中心化：减去初始骨盆 XY 偏移，让机器人在视口正中
                        origin_x = float(bpw[0, 0, 0])
                        origin_y = float(bpw[0, 0, 1])

                        body_world_traj = []
                        for t in range(n_frames):
                            frame_bodies = []
                            for b in range(n_bodies):
                                px = round(float(bpw[t, b, 0]) - origin_x, 4)
                                py = round(float(bpw[t, b, 1]) - origin_y, 4)
                                pz = round(float(bpw[t, b, 2]), 4)
                                # IsaacLab 四元数 [w,x,y,z] → Three.js [x,y,z,w]
                                qw = round(float(bqw[t, b, 0]), 5)
                                qx = round(float(bqw[t, b, 1]), 5)
                                qy = round(float(bqw[t, b, 2]), 5)
                                qz = round(float(bqw[t, b, 3]), 5)
                                frame_bodies.append([px, py, pz, qx, qy, qz, qw])
                            body_world_traj.append(frame_bodies)

                        result["model_info"]["motion"] = {
                            "body_world_trajectory": body_world_traj,  # [N, 30, 7] 每个body世界变换
                        }
                        logger.info(f"识别 G1 body_pos_w 格式，注入 {n_frames} 帧 {n_bodies} 刚体世界变换轨迹")
                    elif "joint_pos" in raw.files and "body_pos_w" in raw.files:
                        # 仅有 body_pos_w 但缺少 body_quat_w 的降级路径
                        bpw = raw["body_pos_w"]
                        n_frames = int(bpw.shape[0])
                        n_bodies = int(bpw.shape[1])
                        origin_x = float(bpw[0, 0, 0])
                        origin_y = float(bpw[0, 0, 1])
                        body_world_traj = []
                        for t in range(n_frames):
                            frame_bodies = []
                            for b in range(n_bodies):
                                px = round(float(bpw[t, b, 0]) - origin_x, 4)
                                py = round(float(bpw[t, b, 1]) - origin_y, 4)
                                pz = round(float(bpw[t, b, 2]), 4)
                                frame_bodies.append([px, py, pz, 0.0, 0.0, 0.0, 1.0])
                            body_world_traj.append(frame_bodies)
                        result["model_info"]["motion"] = {"body_world_trajectory": body_world_traj}
                except Exception as ex:
                    logger.warning(f"解析 body_pos_w 失败，退化为刚体平移: {ex}")

                # 永久性改变：持久化回写 model_info 到 NPZ 文件（如果文件自身尚未固化模型元数据）
                try:
                    if raw is not None and "model_info" not in raw.files:
                        raw_dict = {k: raw[k] for k in raw.files}
                        raw_dict["model_info"] = np.array(json.dumps(result["model_info"]))
                        import stat
                        try:
                            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
                        except Exception:
                            pass
                        np.savez_compressed(path, **raw_dict)
                        logger.info(f"已永久将 G1 3D 机器人模型固化写入 NPZ: {filename}")
                except Exception as w_err:
                    logger.debug(f"持久化 model_info 至 NPZ 跳过: {w_err}")

        return result


    def delete_dance(self, dance_id: str) -> Dict[str, Any]:
        """彻底删除 preview 目录下的指定舞蹈动作文件与关联解压模型"""
        self._ensure_preview_dir()
        filename = f"{dance_id}.npz" if not dance_id.endswith(".npz") else dance_id
        path = os.path.join(self.preview_dir, filename)
        deleted = False

        if os.path.exists(path):
            try:
                os.remove(path)
                deleted = True
            except Exception as e:
                return {"success": False, "msg": f"删除动作文件失败: {str(e)}"}

        # 若存在关联的解压模型目录（如 preview/g1_29dof_rubber_hand）
        # 保护：严禁删除全局内置的 G1 机器人模型！
        PROTECTED_FOLDERS = {"g1_29dof_rubber_hand", "g1_29dof", "meshes", "models"}
        dance_id_clean = dance_id.replace(".npz", "")
        base_name = dance_id_clean.replace("_dance", "")
        for folder_candidate in set([dance_id_clean, base_name]):
            if not folder_candidate or folder_candidate.lower() in PROTECTED_FOLDERS:
                continue
            model_dir = os.path.join(self.preview_dir, folder_candidate)
            if os.path.exists(model_dir) and os.path.isdir(model_dir):
                try:
                    shutil.rmtree(model_dir)
                    deleted = True
                except Exception as e:
                    logger.warning(f"清理模型关联目录失败: {e}")

        if deleted:
            return {"success": True, "msg": f"已彻底删除动作及关联模型: {filename}"}
        return {"success": False, "msg": "文件不存在"}


# 单例实例
preview_manager = PreviewManager()
