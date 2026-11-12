# P04 — 多机器人阵型设计、预览、保存与应用

**阶段目标**：将现有 `FormationPanel` 的计算能力接入当前工程 RobotInstance 和 StageCanvas2D，形成可交互、可持久化、可重现的阵型编辑器。

**前置**：P00–P03 COMPLETE。

## 1. 现有代码检查

重点文件：

- `src/ui/formation_panel.py`
- `src/ui/choreo_page/left_dock_tabs.py`
- `src/core/models.py`
- 阵型计算器源码（搜索 `FormationCalculator`）
- `src/ui/choreo_page/stage_canvas_2d.py`
- P01 的 Project/Formation Repository
- P03 的 RobotInstance Repository

当前 GitHub `main` 快照中 `FormationPanel._get_robot_ids()` 如果输入为空会退回 `A/B/C/D`；`_on_group_changed()` 也会把固定组别写入输入框。必须先确认本地版本并取消这种隐式假数据。阵型成员只能来自当前工程的真实 RobotInstance；用户可以在阵型编辑器临时添加/移除成员，但应用阵型时必须清楚地将其与项目机器人匹配。

## 2. 阵型模型

阵型是可复用模板/工程资源，不是运行中的机器人状态。字段至少包括：

- `formation_id`、`project_id`、`schema_version`
- `name`、`description`、`formation_type`
- `center_pose`：x/y/yaw（m/deg）
- `parameters`：spacing、rows、columns、radius、arc_angle、facing 等（仅保存当前类型使用的字段）
- `members[]`：robot_id、sequence、offset_x、offset_y、offset_yaw
- `created_at`、`updated_at`

明确区分：

- 阵型局部坐标偏移（相对于阵型中心/朝向）；
- 世界坐标成员位姿（由计算器派生）；
- 屏幕显示坐标（只由视图变换计算）。

持久化时保留局部成员偏移和中心位姿；世界坐标可缓存，但必须能重新计算。

## 3. 阵型类型和参数

至少支持仓库现有 `FormationCalculator` 已实现的所有类型；不得只在 UI 放选项却没有计算分支。若实现不足，补齐并测试以下常见类型：

- 单列/横排（Line）
- 纵列（Column）
- 矩形网格（Grid）
- 圆形/环形（Circle/Ring）
- 弧形（Arc）

每种类型定义准确参数：

- Grid：rows、columns、水平间距、垂直间距、行列排列顺序。
- Line：成员数量、成员间距、排列方向。
- Column：成员数量、纵向间距。
- Circle：半径、起始角、方向、朝向模式。
- Arc：半径、圆心角、起始角、方向。

朝向模式可包括：统一朝向、面向阵型中心、沿队形切线；只有确实实现后才能显示在 ComboBox。

成员数量不能超过工程内可选 RobotInstance；当机器人数量不足时显示明确约束，不要自动创建临时机器人。

## 4. 实时计算和可视化预览

- 用户编辑任一参数时，计算器立即更新成员局部偏移和世界位姿。
- 预览结果在 2D StageCanvas2D 中同步显示成员点、ID、朝向箭头和阵型轮廓。
- 阵型中心、朝向、成员间距变化后，画布位置实时更新。
- 选中成员时右侧 Inspector 显示 robot_id、offset、world pose。
- 无地图时仍可在空舞台网格上编辑；有地图时使用统一 world transform。
- 不要把阵型预览写入正式 RobotInstance 初始位姿，除非用户显式点击 Apply。

## 5. 安全间距提示（仅本地几何检查）

继续复用现有安全距离计算能力，但明确这是基于简化占地半径的几何间距校验，不是机器人动力学/避障保证。

- 检查所有成员两两距离。
- 使用每个 RobotInstance 的 footprint 参数；缺省值必须在 UI 中标明为“估算默认值”，不得伪装成真实尺寸。
- 输出违反间距的成员对、实际距离、阈值。
- 状态分级：正常、警告、冲突。
- 不允许因计算失败显示“安全”。
- 可一键定位画布中的冲突成员。

## 6. 保存、加载、复制、删除

- 保存到当前工程 FormationRepository。
- 保存前验证成员 ID 存在、ID 唯一、偏移有限、间距参数合法。
- 加载阵型后参数和成员选择恢复；没有成员映射时显示 unresolved member，不得悄悄丢弃。
- “复制阵型”生成新 ID。
- 删除前检查时间轴 Clip/工程引用；若被引用，提示并遵循 P01 删除策略。
- 对已有 `storage_manager.formations_dir/*.json` 文件提供兼容导入；不能自动删除或覆盖旧 JSON。
- 导入/导出格式包含 schema_version 和单位。

## 7. 应用到舞台

点击“应用到舞台”必须有真实行为：

1. 校验阵型当前成员都能匹配到 Project RobotInstance。
2. 计算每个 RobotInstance 的新 world pose。
3. 展示差异预览（可选但推荐）。
4. 用户确认后，更新本项目 RobotInstance 的位置/朝向，或建立一个阵型实例状态；具体选择写 ADR。
5. StageCanvas2D 立即刷新机器人位置和朝向。
6. 右侧 Inspector/对象列表同步。
7. Project 标记 dirty，Save 后重启可恢复。

“应用阵型”不能只发一个 `formationApplied` signal 然后更新右侧文本；必须能在主舞台看到成员位置真正变化。

## 8. 与时间轴的关系

阵型本身不等于轨迹 Clip。P06 如需阵型变化动画，应定义 `FORMATION` 类型 Clip 或生成明确的 GroupTrajectory；不得把静态阵型直接伪装成普通轨迹。

本阶段只需保证 FormationAsset 稳定 ID、工程归属、序列化格式和成员关系，供 P05/P06 使用。

## 9. UI/可用性

- 阵型参数区、成员列表/表格、校验反馈、保存阵型列表和 Apply 操作清晰分组。
- 对成员表格提供添加/移除、顺序调整和单成员偏移微调。
- 所有数值输入有单位、范围、精度和合理步进。
- 选择阵型模板后可看到预览，不需要先保存。
- 空工程无机器人时显示“先在机器人面板创建 RobotInstance”，阵型保存/应用处于合理禁用状态。
- 深色 UI 使用统一主题，不再在组件里散落大量独立颜色值。

## 10. 测试

至少测试：

1. 机器人为空时不自动生成 A/B/C/D。
2. Line/Grid/Circle/Arc 等每种类型计算点数、中心、间距和方向。
3. yaw 旋转后成员 world pose 计算正确。
4. 所有成员机器人 ID 唯一且有效。
5. 保存/加载往返数据一致。
6. JSON 导出/导入数据一致；非法数据拒绝。
7. 冲突距离阈值边界值测试。
8. Apply 后 RobotInstance 和 StageCanvas2D 位置一致。
9. 保存重开后阵型仍可加载，且项目隔离。

## 11. 用户手工验收

- 为一个有 4 个 RobotInstance 的项目分别生成 Grid、Line、Circle 阵型。
- 调整间距、中心、朝向，观察成员标记实时变化。
- 制造两个成员重叠，确认冲突提示定位到对应成员。
- 保存、关闭、重开，重新加载阵型。
- 点击应用到舞台，确认地图上的机器人标记位置发生实际变化。

## 12. 交付

Formation model/Repository/Calculator/UI 实际实现、兼容旧阵型导入、测试、截图、`P04_TEST_REPORT.md` 和 HANDOFF。完成后可进入 P05。
