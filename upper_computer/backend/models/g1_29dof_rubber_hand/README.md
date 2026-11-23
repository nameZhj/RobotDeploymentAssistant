# 宇树 G1 29-DoF（带橡胶假手）URDF 模型

来源：`/home/ubuntu/vsis_amp_release/robots/`（V-SIS AMP release，该目录为只读源，本文件夹为其完整副本，可自由使用）。

## 内容

| 文件 | 说明 |
|---|---|
| `g1_29dof_mode_5.urdf` | G1 29 自由度 + 左右橡胶假手（rubber hand），mode_5 电机配置 |
| `g1_29dof_mode_15.urdf` | 同上，mode_15 电机配置 |
| `meshes/` | 165 个 STL 网格（两个 URDF 共引用 41 个，已验证全部存在，103 MB） |
| `g1.py` | 原 V-SIS 项目的 IsaacLab ArticulationCfg（G1_M5_IA / G1_M15_IA，含 Unitree 电机刚臂/阻尼参数） |
| `unitree_actuators.py` | Unitree 电机 actuator 配置（W4010_25 / N5010_16 / N5020_16 / N7520_14p3 / N7520_22p5） |

## 关节构成（已验证）

- **29 个 revolute 关节**：身体 23 个（12 腿 + 3 腰 + 8 臂）+ 橡胶假手 6 个（每手 3 DoF）
- 1 个 floating 根关节、9 个 fixed 关节（含 `left/right_hand_palm_joint` 固定假手安装、`left/right_rubber_hand` 假手本体）
- 假手为**固定式橡胶手**（无独立可动关节的灵巧手，手整体挂在手掌上，自由度来自臂部），非 Unitree 官方 dexterous hand

## 两个变体的差异

| 位置 | mode_5 | mode_15 |
|---|---|---|
| 髋俯仰（左右） | effort 88 N·m, 32 rad/s | effort 139 N·m, 20 rad/s |
| 腕部 mesh | `*_wrist_*_link.STL`（0.484 kg） | `*_wrist_*_link_5010.STL`（0.684 kg，N5010） |
| 腕俯仰 | effort 5, 22 rad/s | effort 13.4, 27 rad/s |

## 使用注意

- 网格路径为相对路径 `meshes/...`，URDF 须与 `meshes/` 保持同级目录结构（本文件夹已满足）。
- `g1.py` 中的 `from robots import ASSET_DIR` 是 V-SIS 包内相对导入，单独使用时需调整路径或直接取其中的 `UrdfFileCfg` 参数。
- 与 TeamHOI 项目中使用的 G1（28-DoF 资产替换）不同：本模型为 29-DoF 且带假手，即 V-SIS 原始人形资产。
