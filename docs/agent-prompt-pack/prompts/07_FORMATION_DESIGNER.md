# PROMPT 07 — 多机器人阵型设计器与可复现队形数据

> **类型：阵型业务功能。** 本阶段实现从机器人参与者选择、阵型参数编辑、相对位姿计算到 2D 预览和保存的完整闭环。阵型预览不是机器人真实移动，也不是自动下发。

## 0. 前置依赖和实施边界

必须确认：
- Prompt 02 Application Facade 和 UI/Domain 边界已落地；
- Prompt 04 `RobotGroup`、`Formation`、`member_offsets_json`、`parameters_json` 契约已落地；
- Prompt 05 地图坐标 frame 已明确；
- Prompt 06 的 world/screen transform 和 2D scene layer 可复用。

本阶段只做阵型设计与可视化预览。不做真实机器人编队下发、不做多机器人路径规划、不宣称避障安全。

阵型编辑不允许通过修改机器人实时 pose 来展示预览；必须放在独立 `FormationPreviewLayer`。

## 1. 核心用户流程

设计一个可完成以下流程的界面：

1. 选择场景；
2. 从真实机器人清单选择参与者；
3. 选择阵型模板（直线、网格、圆形、自定义）；
4. 设置锚点、朝向、间距、行列数或自定义偏移；
5. 预览机器人相对位置和编号；
6. 对单个成员微调相对偏移；
7. 校验并显示警告；
8. 保存阵型；
9. 重新加载后得到相同的成员顺序和相对位姿；
10. 可另存为模板或复制现有阵型。

流程中每一步都以真实机器人和场景数据为来源。没有在线机器人时，允许选择已持久化的机器人配置进行离线设计，但 UI 必须显示“离线设计”，不得显示实时状态。

## 2. 工作台布局

入口：主工作台 `舞蹈编排` 中的“阵型”子功能或已存在的阵型页面。不得新增独立的第二套主窗口。

建议布局：

```text
┌───────────────────────────────────────────────────────────────┐
│ 阵型设计  [新建] [打开] [保存] [另存为]                       │ 40px
├────────────────┬───────────────────────────────┬──────────────┤
│ 成员机器人     │ 2D 阵型预览                   │ 参数/属性    │
│ 260px          │ flex                          │ 300px        │
│ 搜索/筛选      │ 地图 layer + formation layer   │ 模板          │
│ 已选成员       │ 锚点/方向/编号                 │ 间距/行列      │
│ 未选成员       │                                 │ 成员偏移      │
├────────────────┴───────────────────────────────┴──────────────┤
│ 校验结果 / 设计说明 / 保存状态                                │ 24–80px
└───────────────────────────────────────────────────────────────┘
```

风格复用 Prompt 03 Theme：背景 `#0b0c0f`，面板 `#101114`，控件 `#191a20`，文字 `#e4e6ea`，辅助文字 `#9ba0aa`，accent `#2e7bf7`。

## 3. 成员机器人选择

左侧列表只读取 `list_robots(scene_id)` 返回的机器人配置，并可附加实时 provider 的连接状态。

每行显示：
- 在线状态（实时 provider 有值时）；
- display name；
- robot_id；
- model_type；
- 是否加入当前设计。

交互：
- checkbox 选择/移除成员；
- 搜索按名称、ID、机型过滤；
- “全选”只选中当前场景内符合筛选条件的机器人；
- 排序支持名称、ID、手动顺序；排序必须持久化；
- 拖动成员行调整 formation member order；
- 双击成员显示机器人配置详情；
- 不能在此处直接修改机器人真实 pose 或设备状态。

校验：
- 一个成员不得重复；
- robot_id 必须存在于场景有效配置中；
- 禁用机器人默认不可加入，需要用户明确启用或显示禁用原因；
- 无模型 footprint 信息时标记为未知，不用虚构半径参与安全判断；
- 离线不妨碍离线设计，但保存的 formation 必须标记设计来源/状态，不标为“已部署”。

## 4. 阵型模板与参数面板

阵型模板必须真实实现以下四种。若 UI 资源无法显示预览缩略图，可用简洁线框图，不使用不明来源图片。

### 4.1 直线 LINE

参数：
- `spacing_m`：成员之间沿局部 X 轴的间距；
- `centered`：是否以锚点为中心；
- `orientation_mode`：沿锚点 yaw 或沿世界轴；
- `row_offset_m`：可选平行偏移，仅在 model 支持时显示。

生成规则：
- N 个成员沿局部 X 均匀排列；
- centered=true 时位置为 `((i - (N-1)/2) * spacing, 0)`；
- centered=false 时第一个成员位于局部原点，其余依次递增。
- 不得按当前机器人列表随机顺序分配；使用保存的 member order。

### 4.2 网格 GRID

参数：
- `rows`、`columns`；
- `row_spacing_m`、`column_spacing_m`；
- `centered`；
- `orientation_mode`。

约束：
- `rows >= 1`、`columns >= 1`；
- `rows * columns` 必须等于成员数，或显示空位策略；
- 用户可选择“按成员数自动调整列数”，但必须在 UI 展示最终行列值；
- 默认填充顺序 row-major，并在 UI 说明；
- 空位仅在显式开启 partial grid 时允许；
- 每个 robot_id 对应的 slot index 必须稳定保存。

### 4.3 圆形 CIRCLE

参数：
- `radius_m`；
- `start_angle_rad`；
- `clockwise`；
- `orientation_mode`：朝向圆心、切线方向、固定朝向锚点。

生成规则：
- N 个成员均匀分布 `2π/N`；
- 角度计算和保存统一使用 rad；
- N=1 时成员位于锚点，不执行除零；
- radius=0 仅允许单成员或明确警告重叠；
- 顺/逆时针改变 slot order，不只改变渲染顺序。

### 4.4 自定义 CUSTOM

- 每个成员有 local x/y/yaw；
- local pose 相对于 formation anchor；
- 支持画布拖动和属性面板数值输入；
- 拖动期间只更新 preview；
- mouse release / Enter 提交一个 undo command；
- 不允许直接将世界坐标写进 member_offsets_json 而不做 anchor inverse transform。

## 5. 坐标和变换规范

所有阵型参数都存储为 anchor-relative local pose。显示到场景时：

\[
p_{world}=p_{anchor}+R(\theta_{anchor})p_{local}
\]

\[
\theta_{world}=\theta_{anchor}+\theta_{local}
\]

其中：
- `p_anchor` 是场景坐标中的锚点；
- `p_local` 是阵型成员局部偏移；
- `R` 是二维旋转矩阵；
- 单位由 Prompt 04 的 `distance_unit`/`angle_unit` 确定。

必须实现并测试：
- local_to_world_pose；
- world_to_local_pose；
- yaw_normalize；
- template_generate_slots。

不允许在 UI、画布、Repository 中各自实现不同的旋转公式。

如果当前项目坐标轴正方向与上述表达的默认数学坐标不同，应由统一 coordinate adapter 处理并在 DATA_CONTRACTS 中说明，禁止悄悄反转 X/Y 或 yaw。

## 6. 锚点与画布交互

画布绘制对象分层：
- MapLayer；
- RobotLiveLayer（仅真实遥测）；
- FormationPreviewLayer；
- SelectionOverlay。

FormationPreviewLayer 的成员使用机器人模型图标或统一简洁形状：
- 成员编号/slot；
- robot display name；
- heading 箭头；
- 选中高亮；
- 拖动时显示 ghost position。

交互：
- 选择“设置锚点”后点击画布，写入 anchor pose；
- 拖动锚点移动整组，不改变 member local offsets；
- 旋转锚点只改变 anchor yaw；
- 拖动单个成员改变该成员 local offset；
- 对齐工具包括水平对齐、垂直对齐、等间距（只有对应操作可用时显示）；
- Delete 删除选中成员 slot，但不删除 Robot 配置；
- Escape 取消当前拖动；
- 每个操作使用一个可撤销命令。

## 7. 校验和风险提示

至少实现以下 validation：

硬错误（禁止保存）：
- formation_id/name 不合法；
- scene_id 不存在；
- robot_id 不存在；
- 重复 robot_id；
- member_offsets 缺少必需成员；
- 数值非 finite；
- 未知 schema_version；
- 坐标 frame 不一致且没有转换策略；
- 模板参数超出合法范围。

警告（允许保存但必须显示）：
- 成员位置过近（仅当机器人 footprint/radius 已知）；
- 成员位置完全重叠；
- 阵型超出当前地图 bounds；
- 某些成员离线；
- 部分机器人未配置模型；
- 成员间距小于 robot metadata 提供的安全建议；
- formation slot 数与 selected robots 不一致（partial grid）。

不得把简单的 2D 距离检查宣称为碰撞安全认证。警告必须区分“几何重叠检查”和“真实机器人安全间距”。

## 8. 持久化和操作

调用 Prompt 04 的 `save_formation`/等价 Facade 方法。若缺失，先补充 Application Use Case，禁止 UI 直接 SQL。

必须支持：
- 创建；
- 加载；
- 保存；
- 另存为；
- 重命名；
- 删除；
- 导出 JSON；
- 导入 JSON（parse/validate/preview/confirm）。

JSON 必须包含：
- schema_version；
- formation_id；
- scene_id；
- name；
- layout_type；
- anchor_pose；
- coordinate_frame_id；
- distance_unit/angle_unit；
- parameters；
- member order；
- 每个 robot_id 对应 slot_id 和 local pose；
- created_at/updated_at/revision。

保存并重载后必须得到相同：
- 成员集合；
- 成员顺序；
- 模板参数；
- 每个成员 local pose；
- 世界预览位置（浮点容差按统一测试配置）。

并发 revision 不一致时返回 CONFLICT，不覆盖已有最新版本。

## 9. Undo/Redo 与 dirty state

使用 `QUndoStack` 或 Prompt 02 已批准的命令体系：
- Add/Remove formation member；
- Change layout type；
- Change formation parameter；
- Move anchor；
- Rotate anchor；
- Move member slot；
- Reorder members；
- Align members；
- Delete/restore selected slots。

撤销/重做不写 DB。保存成功后 clean index 更新。放弃更改要恢复 repository 最近保存版本。

## 10. 测试

Domain：
- LINE 1/2/N members；
- GRID square/rectangular/partial/invalid；
- CIRCLE 1/2/N、clockwise/counter-clockwise；
- CUSTOM local/world transform；
- rotation round-trip；
- duplicate/missing member；
- non-finite；
- bounds and overlap warnings；
- deterministic generation: identical inputs produce identical slot IDs/poses/order。

Qt：
- 搜索、选中、排序和拖动排序；
- 模板切换；
- anchor set/move/rotate；
- member drag；
- inspector value edit；
- undo/redo/dirty；
- save/reload round-trip；
- import invalid JSON doesn't modify current design；
- offline design indicator is visible；
- no real robot command is sent.

Regression：
- existing Robot list selection remains intact；
- map visibility and map layer remain independent；
- trajectory layer is not modified by formation preview；
- Prompt 01 compatibility tests still pass.

## 11. 完成验收

提交：
- Formation Domain model/service/validator；
- deterministic template generator；
- coordinate transform utilities；
- 2D FormationPreviewLayer；
- formation editor UI；
- JSON import/export；
- undo command set；
- test report and screenshots in `docs/agent-prompt-pack/audit/07-formation/`。

UI 不出现“下发编队/执行阵型”按钮；该能力属于后续机器人适配和安全下发阶段。结束后更新状态文档和 handoff。
