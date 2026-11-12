# PROMPT 06 — 2D 轨迹编辑器：绘制、航点编辑、撤销重做与 JSON 持久化

> **类型：真实 2D 编辑器开发。** 本阶段将地图上的轨迹从“画布装饰线”升级为有领域 ID、可编辑 waypoint、可保存、可导入导出的业务资源。必须基于真实地图坐标，不得只存屏幕像素。

## 0. 前置条件

- Prompt 04：Trajectory/Waypoint schema、repository、validator 已完成。
- Prompt 05：地图能够作为独立 layer 加载到 2D canvas。
- Prompt 02：统一 Application Facade 和 UI/Domain 边界有效。
- Prompt 03：中央画布、工具栏和左右面板骨架已经建立。

若 `StageCanvas2D` 已被更名或替换，沿真实 active implementation 修改；禁止再创建第二个互不相连的轨迹画布。

## 1. 编辑器页面结构

复用主工作台中央 2D 视口。工具栏位于画布顶部 40 px toolbar 内；属性面板可作为中央视图右侧 inspector 或右侧资源详情子面板，但必须确保地图可视区域至少 420 px 宽。

顶部工具分组：

### A. 编辑模式

| 控件 | 文案/图标 | 尺寸 | 行为 |
|---|---|---:|---|
| 选择 | `鼠标箭头` | 28×28 | 选中/拖动现有路径和 waypoint |
| 绘制路径 | `折线` | 28×28 | 单击画布逐点添加 waypoint |
| 平移 | `手掌` | 28×28 | 拖动画布，不修改轨迹 |
| 删除选中 | `删除` | 28×28 | 删除当前选中 waypoint/path；必须可撤销 |

所有模式互斥。当前模式按钮显示 active 背景 `rgba(46,123,247,0.18)` 和蓝色边框。

### B. 编辑操作

| 控件 | 行为 |
|---|---|
| 撤销 | `QUndoStack.undo()` |
| 重做 | `QUndoStack.redo()` |
| 完成路径 | 结束当前绘制会话，保留未保存状态 |
| 取消绘制 | 丢弃当前尚未提交的绘制会话，不能删除此前已保存的路径 |
| 删除全部路径 | 只有当前场景确有路径时显示；二次确认；一个 undo command 可恢复所有删除 |

Undo/Redo disabled 状态必须由 `QUndoStack.canUndo/canRedo` 驱动，不可通过点击次数猜测。

### C. 视图与捕捉

| 控件 | 行为 |
|---|---|
| 适配地图 | fit 当前 map bounds |
| 网格 | 显示/隐藏 grid layer |
| 网格捕捉 | 开/关 snap-to-grid |
| 捕捉间距 | 从场景单位和地图分辨率提供有效选项；默认不得硬编码一个不符合坐标单位的数值 |
| 显示航向 | 开/关 waypoint yaw marker |

如果现有坐标系/分辨率未知：
- snap 默认关闭；
- 捕捉间距显示“未标定”并禁用；
- 不可按像素当作米。

## 2. 画布交互契约

所有轨迹数据储存世界坐标，不储存 screen x/y。实现并测试双向 transform：

```python
world_to_screen(world_xy) -> QPointF
screen_to_world(screen_xy) -> WorldPoint
```

该 transform 由当前 map coordinate frame、viewport size、pan offset、zoom scale 和 DPR 统一决定；禁止在不同 mouse handler 中重复计算。

### 2.1 选择模式

左键按下：
1. 先 hit-test waypoint（优先级最高）。
2. 再 hit-test path segment/path body。
3. 再检查机器人/地图对象（仅当项目允许选择）。
4. 最后取消选择。

命中容差按屏幕像素定义，默认半径 9 px；不能按固定世界距离定义，否则 zoom 后选中难度变化。

Waypoint 选中：
- 显示 8–10 px 可见锚点；
- 显示 1.5 px 描边；
- 属性面板加载该 waypoint；
- mouse move 拖动时预览更新；
- mouse release 只提交一个 undo command；
- 失败或取消拖动恢复原坐标。

Path 选中：
- 高亮整条路径；
- 选中状态不修改几何数据；
- 双击路径可在命中 segment 插入 waypoint，插入点取鼠标世界坐标，并放入一个 undo command；
- 单击路径只选中，不自动执行或放入时间轴。

### 2.2 绘制路径模式

鼠标左键：
- 每次单击放置一个 waypoint；
- waypoint 按点击顺序生成稳定 ID；
- 当前路径以折线即时预览；
- 鼠标移动时显示最后一个 waypoint 到光标位置的临时 segment；
- 临时 segment 不写 DB、不进入导出数据。

鼠标操作：
- 左键单击：新增 waypoint；
- Backspace：撤销当前绘制会话中最后一个 waypoint；
- Enter / 点击“完成路径”：完成路径；
- Escape / 点击“取消绘制”：取消当前绘制会话；
- 双击最后一点：结束绘制，但不能重复添加第二个几乎重合点；
- 右键：打开当前绘制上下文菜单（删除最后一点/完成/取消），不能同时再触发 `finish_current_trajectory()` 的第二条隐藏存储路径。

完成规则：
- 至少 2 个不同坐标 waypoint。
- 不满足时显示“轨迹至少需要两个不同的航点”，不创建资源。
- 完成后打开轻量命名对话框，默认名称 `轨迹 YYYYMMDD-HHmmss`，名称可编辑。
- 选择目标 robot 或 robot group；至少一项要满足 Prompt 04 的 trajectory 关联规则。
- 若没有可关联机器人/组，允许保存为场景级未绑定轨迹的前提是 Domain schema 已明确支持；否则禁用保存并说明原因。
- 点击确认后调用一次 `save_trajectory`。
- 成功：添加到轨迹库、清 dirty、显示成功提示。
- 失败：绘制结果保留在编辑态，不创建假资源，显示错误码和原因。

### 2.3 平移与缩放

- 中键拖动：平移 viewport。
- Space + 左键拖动：临时平移。
- 滚轮：以鼠标当前 screen position 为锚点缩放，不以视口中心缩放。
- 缩放范围必须由 renderer 配置限制；超出范围 clamp。
- 平移和缩放不能改变 waypoint 世界坐标。
- 选择模式中拖动 waypoint 时不允许触发 pan。
- 视口平移操作不进 trajectory undo stack。

### 2.4 网格吸附

当 snap enabled：
1. 将 screen point 转 world point；
2. 按 grid spacing 对 world x/y 取最近网格；
3. 再将吸附后的 world point 显示到 screen。
禁止在 screen pixel 空间吸附。
捕捉间距必须与 distance_unit 一致；场景单位未知时禁用 snap。

## 3. Waypoint 数据与属性编辑器

选中单个 waypoint 后显示属性面板：

| 属性 | 控件 | 校验 |
|---|---|---|
| Waypoint ID | 只读 | 唯一 ID |
| X | DoubleSpinBox | finite，单位随场景显示 |
| Y | DoubleSpinBox | finite，单位随场景显示 |
| 航向 yaw | DoubleSpinBox | 可空；角度单位明确 |
| 速度 | DoubleSpinBox | 可空；不得擅自给默认值 |
| 到达时间 | SpinBox/只读 | 只有时间参数模型已启用时可编辑 |
| Frame | 只读 | 当前 trajectory frame |
| 序号 | 只读/排序操作 | 0-based 或 1-based 明确一致 |

编辑规则：
- X/Y 字段改值时先在编辑态预览，不要每输入一个字符就写 DB。
- Enter/焦点离开时 validate，再提交一个 undo command。
- Escape 恢复修改前值。
- yaw 可空；清空即 None。
- 单位转换只在 view-model 层呈现，domain 中统一存储单位。
- 不允许将空 yaw 自动转换为 0。
- 速度必须大于等于 0；最大值依据项目真实运动配置，不得猜测机器人性能上限。
- 若用户输入超出允许运动范围，显示 validator 的错误原因。

多选 waypoint：
- Shift + 单击添加/取消选择；
- 属性面板只显示共同可编辑项；
- 删除多选生成一个 undo command；
- 拖动多选 waypoint 保持相对位移。

## 4. 轨迹列表和生命周期

复用 Prompt 03 右侧轨迹库：
- 双击轨迹加载到画布作为当前编辑对象；
- 单击仅选中，不替换画布当前轨迹；
- 加载另一条轨迹时，当前轨迹 dirty 则询问保存/放弃/取消；
- 当前轨迹名称和状态在画布顶部显示；
- dirty 标记跟随模型 revision；
- 保存成功后使用 repository 返回的 revision 更新本地模型；
- 外部 revision 已变化时出现并发冲突，不能覆盖更新版本。

支持：
- 新建空轨迹；
- 加载轨迹；
- 重命名；
- 保存；
- 另存为；
- 导入 JSON；
- 导出 JSON；
- 删除（有 TimelineClip 引用时禁止直接删除，提供跳转查看引用的入口）。

另存为必须生成新的 trajectory_id 和新的 waypoint_id，不得复用对象 ID 后造成两个资源互相污染。

## 5. 编辑命令与 Undo/Redo

必须使用 Qt `QUndoStack` 或 02 ADR 已批准的等价命令栈。

至少实现以下命令：
- `AddWaypointCommand`
- `MoveWaypointCommand`
- `UpdateWaypointAttributesCommand`
- `DeleteWaypointCommand`
- `InsertWaypointCommand`
- `DeleteTrajectoryCommand`（仅内存编辑态或已确认的资源生命周期）
- `ReverseTrajectoryCommand`（若实现）
- `BatchMoveWaypointsCommand`

每个命令：
- 保存 before/after 状态；
- redo/undo 可重复调用且结果一致；
- 不直接写 SQL；
- 不修改原始用户文件；
- 批量命令原子执行，不能只撤销一半。

Undo stack dirty state：
- 保存成功后设置 clean index。
- 从 clean index 继续编辑时 dirty。
- undo 回到 clean index 后 dirty 清除。
- redo 离开 clean index 后 dirty 恢复。
- 另存为后新轨迹 clean index 设置为当前状态。

## 6. 几何算法与指标

必须提供可测试的纯 Domain 函数：
- waypoint polyline length；
- consecutive duplicate detection；
- waypoint index insertion；
- waypoint deletion；
- yaw derivation（仅在用户请求“自动计算航向”时生成，不覆盖明确 yaw）；
- screen/world transform（视口层函数）；
- hit-test（以屏幕像素容差）；
- snap-to-grid。

长度计算：
\[
L=\sum_{i=1}^{n-1}\sqrt{(x_{i+1}-x_i)^2+(y_{i+1}-y_i)^2}
\]
单位跟随 distance_unit。
如果轨迹只有 0 或 1 个点，长度为 0，但不能作为可保存的有效路径。
重复点容差必须是配置化的世界距离阈值，且与场景单位一致；不得把 pixel tolerance 混用。

## 7. JSON 导入和导出

导入流程：
1. 打开文件，限制支持扩展名为 `.json`；
2. parse JSON；
3. 读取 schema_version；
4. 调用 version adapter；
5. validate 所有 waypoint；
6. 预览名称、点数、长度、坐标系和单位；
7. 确认后保存为新轨迹；
8. 不覆盖同 ID 资源，不覆盖当前编辑态。

导出格式沿用 Prompt 04 的 versioned schema。必须包含：
- schema_version；
- trajectory_id；
- name；
- scene_id；
- map_id（可空）；
- robot_id/group_id；
- coordinate_frame_id；
- distance_unit/angle_unit；
- geometry_type；
- waypoints；
- revision/created_at/updated_at（按 schema 规定）。

导出使用 UTF-8 和原子文件写入。导出当前编辑态是否包含未保存修改必须明确提示；默认导出当前编辑态，但导出成功不代表 DB 已保存。

## 8. 画布渲染规范

- 轨迹 layer 与地图 layer、robot layer 分离。
- 当前编辑轨迹使用 accent `#2e7bf7`。
- 非选中轨迹使用低对比 `#6a8bbd` 或 Theme 中定义的 secondary path token。
- waypoint 默认半径 4 px，selected radius 6 px。
- 起点、终点使用不同 shape，不只靠颜色区分。
- yaw marker 使用方向短线/箭头；yaw 为 None 时不绘制。
- 选中 waypoint 显示 9 px hit marker。
- 线宽按 screen pixel 固定，缩放时不让线变得过粗/不可见。
- 大于 renderer 性能阈值时可做显示简化，但编辑和保存始终保留全部 waypoint。
- 无地图时仍可在明确的场景坐标系中编辑；坐标 frame 不存在则提示需要先加载地图或定义 frame。
- 不得将屏幕坐标作为存储坐标。
- 不得把固定假 Robot1/Robot2 或默认路径当成编辑器默认内容。

## 9. 与时间轴的边界

Prompt 06 只负责保存几何轨迹资源。它不负责将轨迹自动拖到时间轴，也不负责执行机器人。

- 完成路径后只写入 Trajectory Repository。
- 时间轴引用创建属于 Prompt 08。
- 预演调度器属于 Prompt 09。
- 任何“执行轨迹”按钮在对应执行能力完成前不得显示。
- 轨迹保存不能自动触发真实机器人运动。

## 10. 自动化测试

### Domain tests
- 有效/无效 waypoint 校验；
- NaN/Infinity 拒绝；
- waypoint ID 唯一；
- 2 点/多点 polyline length；
- 删除/插入/反转；
- yaw 自动推导不覆盖已存在 yaw；
- 不同单位转换；
- schema version adapter。

### Coordinate tests
- world -> screen -> world round-trip；
- pan 不改变 world coordinate；
- zoom anchor 位置稳定；
- DPR=1 和高 DPI 下命中容差一致；
- 网格吸附只在世界坐标执行。

### Undo tests
- 每个命令 redo/undo；
- 多次 redo/undo；
- batch command 原子性；
- clean index 行为；
- 保存后再次编辑/undo/redo dirty state。

### Qt UI tests
用 `pytest-qt`（若项目当前环境已批准）或 Qt `QTest`：
- 绘制模式点击三次创建三个点；
- Enter 完成路径；
- 只有一个 repository save call；
- Escape 取消当前草稿；
- 拖动 waypoint 修改世界坐标；
- 双击 segment 插点；
- 右键菜单不触发双重 finish；
- 中键平移、滚轮缩放；
- 属性面板修改坐标；
- 保存失败保留编辑态；
- 加载另一轨迹时 dirty guard 生效；
- JSON 导入失败不改变当前轨迹；
- 另存为 ID 不重复。

### Regression
- 首页入口仍可打开 Studio；
- 2D/3D 切换仍工作；
- 地图 layer 未被轨迹编辑覆盖；
- Robot selection 不会改变轨迹 waypoint；
- 旧轨迹 JSON fixture 可导入；
- Prompt 01 的兼容性测试全部执行。

## 11. 验收交付

必须提交：
- 真实 2D 轨迹编辑器；
- toolbar 控件与 event map；
- waypoint inspector；
- QUndoStack commands；
- versioned JSON import/export；
- Domain geometry functions；
- Repository integration；
- Qt/Domain/regression tests；
- 操作录屏或截图（环境允许时）；
- `docs/agent-prompt-pack/audit/06-trajectory-editor/` 测试和验收记录。

必须以真实地图/真实用户导入数据验证，不能用 `generate_default_point_cloud()` 或固定 Robot1/Robot2 做验收。完成后更新 PROJECT_STATE、TEST_MATRIX、COMPATIBILITY_MATRIX、PROMPT_EXECUTION_LOG、SESSION_HANDOFF。
