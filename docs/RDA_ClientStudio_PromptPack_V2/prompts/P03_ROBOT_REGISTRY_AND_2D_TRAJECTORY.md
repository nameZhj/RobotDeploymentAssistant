# P03 — 工程内机器人实例管理与 2D 单机/多机轨迹工作台

**阶段目标**：将现有 `StageCanvas2D` 从“可绘制的画布控件”完善为真正的本地轨迹编辑器，并且有明确的工程机器人实例来源。轨迹支持 JSON 保存、重现和多机器人归属。

**前置**：P00、P01、P02 COMPLETE。

## 1. 先查清现有实现

检查：

- `src/ui/choreo_page/stage_canvas_2d.py`
- `src/ui/choreo_page/map_canvas_renderer.py`
- `src/ui/choreo_page/stage_dock_left_panel.py`
- `src/ui/choreo_page/left_dock_tabs.py`
- `src/domain/trajectory/trajectory_asset.py`
- `src/domain/trajectory/trajectory_draft_validator.py`
- `src/domain/trajectory/spline_builder.py`
- `src/infrastructure/storage/trajectory_sqlite_adapter.py`
- `src/infrastructure/storage/choreo_sqlite_store.py`
- `src/core/models.py`
- P01 创建的 Robot/Trajectory Repository 和 DATA_CONTRACTS。

对 `StageCanvas2D` 已存在的方法逐个建立映射：`set_robots`、`select_robot`、`get_robot_pose`、`validate_trajectory_draft`、`select_trajectory`、`cancel_edit`、`insert_waypoint_to_trajectory`、`delete_waypoint_from_trajectory`、`finish_trajectory`、`save_current_trajectory`、`delete_trajectory`、`load_trajectories_from_store`、`clear_active_trajectory`、`clear_all`、`set_grid_data`、鼠标/键盘事件。

不得删除已有能力，只能在查清行为后修复和扩展。

## 2. RobotInstance：明确是本地项目对象

目前 `StageCanvas2D.set_robots()` 支持接收 dict 列表，但必须找到真实来源；FormationPanel 现有 `_get_robot_ids()` 会退回默认 `A/B/C/D`，这不是当前项目中真实配置的机器人实例。

为当前工程建立 RobotInstance 管理能力。字段至少包括：

- `robot_id`：稳定唯一 ID（UUID 或项目稳定 ID），不是列表下标。
- `display_name`：画布显示名称。
- `model_id`：引用本地模型库中的型号；未知时允许 null。
- `color`：可视化颜色。
- `initial_pose`：x/y/z/yaw，单位 m / deg。
- `footprint_radius` 或用于视觉区分的占地参数；若用于冲突提示，必须注明是估算参数。
- `enabled`：是否参与当前场景编辑。
- `metadata`：用户可扩展的本地备注。
- `schema_version`、`project_id`。

提供本地 UI 操作：添加机器人实例、编辑名称/颜色/型号/初始位姿、复制、删除、选择。新工程默认机器人数量为 0。不得从串口/HTTP/SSH 获取设备列表，也不得伪装这些机器人在线。

如果模型库没有某型号资源，仍可让用户建立抽象 RobotInstance，但在 Inspector/3D 中明确标记“模型资源未配置”；不要绘制假模型。

## 3. 画布对象和编辑状态

把 2D 舞台交互整理为明确状态机，至少包含：

- `SELECT`：选择机器人/轨迹/控制点。
- `DRAW_TRAJECTORY`：新增轨迹控制点。
- `EDIT_TRAJECTORY`：编辑选中轨迹。
- `PAN`：平移视口。
- `PLACE_ROBOT`：放置/修改机器人初始位姿（若采用独立模式）。

每个模式下定义：鼠标左键、右键、中键、滚轮、Delete、Esc、Ctrl+Z/Ctrl+Y 行为。不能在绘制模式误选机器人，不能在平移模式添加控制点。

轨迹对象至少包含：

- `trajectory_id`
- `project_id`
- `name`
- `robot_id` 或 `target_type/group_id`
- `schema_version`
- `coordinate_frame = stage_world`
- `position_unit = m`
- `angle_unit = deg`
- `points`：按顺序保存 x/y/可选 z/heading/time 或显式的 control point 数据
- `spline_type` / sampling 参数
- `created_at` / `updated_at`

区分控制点与采样曲线：持久化控制点和曲线参数；采样点是可重建数据，除非有性能需求和版本策略，不要将屏幕像素采样数组作为主数据。

## 4. 轨迹绘制和编辑的真实行为

### 绘制

1. 用户选择目标 RobotInstance。
2. 切换 DRAW_TRAJECTORY。
3. 在舞台上点击添加控制点；画布显示编号/节点和实时预览曲线。
4. 状态栏显示当前点数、轨迹长度/估计时长（估计值必须标注）。
5. 点击 Finish 完成草稿，输入轨迹名称并保存。
6. 保存成功后进入已保存轨迹列表，自动选中该轨迹。

若没有机器人实例，绘制轨迹操作应提示先创建/选择机器人，而不是自动创建 A/B/C/D。

### 控制点编辑

- 选择已有轨迹后显示控制点。
- 拖动控制点时实时更新曲线。
- 支持选中点插入前/后、删除点、撤销、取消修改。
- 最小控制点数与轨迹合法性由 Domain Validator 决定；不足时阻止保存并显示具体原因。
- 取消编辑恢复数据库中的原始版本。
- 删除轨迹前检查时间轴 Clip/阵型/项目引用；存在引用时提示并执行明确策略。

### 多机器人

- 每条单机轨迹绑定一个真实 `robot_id`。
- 画布上同时显示项目内多个 RobotInstance 与各自轨迹，可独立选中/隐藏。
- 支持多机轨迹组（若已有 `GroupTrajectoryWorkspace`，复用其 Domain/Compiler），不复制出第二套群组数据模型。
- 多机器人轨迹编辑不得把不同机器人控制点混成一条无归属轨迹。

## 5. 世界坐标与视图交互

使用 P02 的地图 origin/resolution/calibration。当前 `StageCanvas2D.screen_to_stage()` 与 `stage_to_screen()` 基于 widget 中心、offset、scale，必须确认这套局部舞台坐标如何与地图世界坐标一致。

要求：

- 持久化数据只存米制世界坐标。
- 缩放/平移只改变 View Transform。
- 地图存在时，根据地图边界提供 Fit Map / Reset View。
- 无地图时提供合理的空舞台网格，坐标原点清晰。
- 滚轮缩放围绕鼠标位置，不应让视口突然跳向中心。
- 坐标转换可往返：world → screen → world 的误差应在测试阈值内（例如 1e-4 m，按浮点和绘制精度调整并写清）。
- 舞台坐标转换逻辑放入单独的可测试对象/工具，不在多个 paint/mouse handler 中散落重复公式。

## 6. 本地保存与 JSON 重现

实现正式 TrajectoryRepository / Service：

- 新建、更新、复制、删除轨迹。
- 查询某工程所有轨迹、按机器人筛选。
- JSON 导出单条或多条轨迹。
- JSON 导入前显示摘要，支持选择导入到当前工程的机器人。
- 导入时验证 schema_version、坐标单位、点数、ID 冲突、机器人引用。
- 提供向后兼容解析器，将旧格式转换成当前模型；原文件不覆盖。

JSON 文件示例仅用于说明，真实字段以 DATA_CONTRACTS 为准：

```json
{
  "schema_version": 1,
  "trajectory_id": "UUID",
  "project_id": "UUID",
  "name": "示例轨迹",
  "target": {"type": "robot", "robot_id": "UUID"},
  "coordinate_frame": "stage_world",
  "position_unit": "m",
  "angle_unit": "deg",
  "points": [
    {"x": 0.0, "y": 0.0, "yaw": 0.0},
    {"x": 1.0, "y": 0.5, "yaw": 30.0}
  ]
}
```

JSON 保存采用临时文件 + fsync/flush（平台能力允许时）+ atomic replace；DB 事务和文件系统操作要能处理失败回滚。

## 7. 左侧对象列表和右侧 Inspector

左侧对象/机器人面板必须展示当前工程真实 RobotInstance：

- 名称、ID、型号配置状态、颜色、初始坐标；
- 选择后同步画布选择、右侧 Inspector；
- 新增/编辑/删除入口；
- 没有机器人时显示空状态。

右侧 Inspector 随当前选择对象切换：

- Robot：ID、名称、model_id、x/y/yaw、颜色、备注。
- Trajectory：ID、名称、目标机器人、点数、长度、估计时间。
- Control Point：索引、x/y/yaw/time（可编辑字段由功能定义）。

任何编辑都通过应用服务保存，不允许 UI 直接改 JSON 文件。

## 8. 自动化测试

必须至少包括：

1. 空项目无机器人；添加后持久化、重启恢复、删除后不再出现。
2. 机器人选择同步到画布与 Inspector。
3. 绘制轨迹并保存，DB/JSON 均可恢复。
4. 编辑控制点、撤销、取消、保存后的几何数据符合预期。
5. JSON 导出再导入，控制点坐标一致。
6. 非法 JSON、未知机器人 ID、NaN、Infinity、缺字段、过少点数会被拒绝。
7. 缩放/平移前后同一世界坐标不变。
8. 两台机器人分别拥有轨迹，互不覆盖，列表筛选正确。
9. 删除被时间轴 Clip 引用的轨迹按既定策略阻止或安全处理。
10. 真实 Qt 鼠标/键盘事件测试或 Windows UI 实测覆盖核心绘制流程。

## 9. 用户手工验收

1. 新建空项目，左侧机器人列表应为空。
2. 添加两个 RobotInstance（例如 Dog-A、Dog-B），调整初始位置和朝向。
3. 分别为两个机器人绘制不同轨迹，保存。
4. 选择轨迹并拖动中间控制点，确认曲线变化；Esc 取消后恢复。
5. 导出其中一条 JSON，再导入到另一个机器人，检查坐标和归属。
6. 缩放和平移地图，轨迹与地图不发生相对漂移。
7. 关闭重开工程，机器人和轨迹全部恢复。

## 10. 交付

真实代码、机器人实例数据模型/Repository、轨迹 CRUD 与 JSON 导入导出、Qt 自动化测试、截图、`P03_TEST_REPORT.md`。完成后进入 P04。
