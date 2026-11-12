# 数据契约与领域规范 (Data Contracts)

> 最后更新：2026-11-12

---

## 1. 坐标系与物理单位规范

- **世界坐标系 (World Frame)**：
  - 右手坐标系：X 轴向前（或向右视约定），Y 轴向左，Z 轴垂直向上。
  - 长度单位：严格使用国际单位制**米 (m)**。
  - 角度单位：数据模型与存储严格使用**弧度 (rad)**，UI 显示可格式化为度 (°)。
  - 时间单位：数据模型与导出严格使用**秒 (s)**，时间轴画布内部使用**整数毫秒 (ms)**。
- **屏幕像素分离原则**：
  - 画布缩放 `scale` 与平移 `offset` 仅作为 View 视图层瞬态属性。
  - 持久化（JSON/SQLite）严禁存储任何屏幕像素 (pixel) 坐标，必须为纯粹的世界坐标。
- **数值安全性**：
  - 严禁出现 `NaN`、`Infinity` 或 `-Infinity`；浮点反序列化前必须进行严格校验。
  - 未知电量、未知坐标使用 `None` 或显式 `UNKNOWN`，严禁伪造为 `0.0`。

---

## 2. 核心数据实体契约

### 2.1 轨迹模型 (`TrajectoryModel`)
- `schema_version`: `"1.0.0"`
- `trajectory_id`: 唯一字符串 ID
- `control_points`: 航点列表 `[{"x": float, "y": float, "t": float, "yaw": float, "is_stop": bool}]`
- `sampled_points`: 样条密集采样点列表（0.05m 步长）
- `interpolation`: `"catmull_rom"` / `"cubic_spline"`
- `max_velocity`: 最大线速度，默认 1.2 m/s

### 2.2 几何阵型模型 (`FormationModel`)
- `formation_id`: 唯一字符串 ID
- `layout_type`: `"line"` / `"circle"` / `"grid"` / `"custom"`
- `members`: 阵型成员列表 `[{"robot_id": int, "local_x": float, "local_y": float, "heading": float}]`
- `min_spacing`: 机器人间最小防撞安全间距，默认 0.8m

### 2.3 时间轴片段 (`TimelineClip`)
- `clip_id`: 唯一 ID
- `robot_id`: 目标机器人轨道 ID
- `layer`: `"action"` (上层动作) / `"trajectory"` (下层轨迹)
- `start_time`: 起始时间 (s)
- `duration`: 持续时长 (s)
- `asset_id`: 引用的真实动作 NPZ 或轨迹 JSON ID，严禁复制冗余数据。
