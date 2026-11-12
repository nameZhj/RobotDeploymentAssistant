# PROMPT 08 — 动作/轨迹时间轴编排器与 Clip 编辑

> **类型：多轨时间轴业务功能。** 本阶段实现可保存、可撤销、可重载的动作和轨迹时间轴。时间轴只描述节目/编排数据，不执行真实机器人运动。3D 预演播放由 Prompt 09 提供。

## 0. 前置依赖

- Prompt 04：Timeline/Track/Clip schema、Repository、revision。
- Prompt 06：Trajectory 资源已可读取。
- Prompt 07：Formation/RobotGroup 资源可被时间轴引用（若 timeline 需要 group）。
- Prompt 02：单一 Facade、后台工作与 UI 线程边界。
- Prompt 03：时间轴容器与右侧资源库。

如果 timeline schema 缺少 track binding、source reference、offset 或 playback_rate，先提交 schema migration，不允许在 UI 对象上私自扩展无法持久化的属性。

## 1. 时间轴工作区布局

时间轴位于主工作台底部，支持独立放大/收起，但保持最小可操作高度 220 px。建议默认高度 280 px。

```text
┌─────────────────────────────────────────────────────────────────┐
│ [播放头] [缩小] [放大] [适配] [吸附] [100ms ▼] [保存] [更多]     │ 32px
├──────────────┬──────────────────────────────────────────────────┤
│ Track Header │ 时间尺 0s 1s 2s 3s ...                             │ 28px
├──────────────┼──────────────────────────────────────────────────┤
│ Robot A      │ [Trajectory Clip]       [Trajectory Clip]         │ 42px
│              │                                                  │
│ Robot A动作  │    [Action Clip-------]                           │ 42px
│ Robot B      │ [Trajectory Clip-----]                             │ 42px
│ Robot B动作  │               [Action Clip------]                  │ 42px
└──────────────┴──────────────────────────────────────────────────┘
```

尺寸：
- 左侧 track header 固定宽 160 px；
- ruler 高 28 px；
- toolbar 高 32 px；
- track row 高 42 px，允许用户按需调整但最小 32 px；
- clip 圆角 5 px；
- clip 文本 11 px；
- 时间刻度文字 10–11 px；
- 行间分割线使用 Theme border token。
- 横向滚动只影响 timeline content，不移动左侧 track headers；纵向滚动时 ruler 和 toolbar 固定。

## 2. Track 类型与绑定

最少支持：
- `ROBOT_TRAJECTORY`：绑定单个 robot 的轨迹 clip；
- `ROBOT_ACTION`：绑定单个 robot 的动作 clip；
- `GROUP_TRAJECTORY`：绑定 RobotGroup 的轨迹（只有现有 domain schema 支持时）；
- `EVENT`：仅当项目实际需要和实现事件语义时增加。

每个 track：
- 有稳定 track_id；
- 有 display_order；
- 有 `robot_id` 或 `group_id` 绑定；
- 可 muted/locked；
- 名称和颜色来自集中 Theme/track palette；
- 绑定机器人必须存在；
- track 不因机器人暂时离线而删除；
- 离线状态单独展示，不能伪装成在线。

默认轨道生成规则：
- 新建 timeline 时不创建假机器人轨道。
- 用户通过“添加轨道”选择真实机器人或 group 后创建。
- 已存在轨道的机器人被移除时显示 broken/missing binding 并阻止执行预演，不能自动绑定到另一个机器人。

## 3. Clip 数据和显示

每个 clip 对应 Prompt 04 的字段：
- clip_id；
- track_id；
- source_type；
- source_id；
- start_ms；
- duration_ms；
- offset_ms；
- playback_rate；
- enabled；
- revision。

Clip 还可提供只读派生值：
- source name；
- source availability；
- display color；
- trim start/end；
- warning list。

不要在 clip 中复制整份 Trajectory/Action 数据。Clip 引用 source resource。

颜色：
- trajectory clip：主蓝色系；
- action clip：青/紫等 Theme palette 的固定类别色；
- disabled clip：降低对比度并显示禁用标记；
- broken reference：危险色和错误图标；
- 选中 clip：蓝色边框/高亮，不只改变颜色。

## 4. 从资源库添加 Clip

右侧资源库选中一个动作/轨迹后：
- 提供“添加到时间轴”菜单项或拖拽到目标 track；
- 拖拽时显示半透明 ghost clip；
- drop 前校验 source、track type、robot/model compatibility；
- drop 命中 track 决定目标绑定；
- drop 的 X coordinate 转换成 timeline milliseconds；
- snap 开启时按当前时间吸附间隔取整；
- 未命中有效 track 时取消，不创建 clip；
- 拖入 action 到 trajectory track 或 trajectory 到 action track 必须拒绝并显示原因。

当用户双击资源：
- 默认只打开详情；
- 不自动创建 clip，除非用户在明确的“添加到时间轴”命令上触发。

Clip 起始时间：
- 不允许根据鼠标像素直接保存；
- 使用 `time_from_screen_x(x)` 的统一函数；
- 吸附间隔由 UI 当前选择决定，默认采用项目合理配置；用户可改 50/100/250/500 ms 等选项，但必须保证数值为正；
- 时间尺缩放只改变像素映射，不改变 clip.start_ms。

## 5. Clip 编辑手势

### 5.1 选择与移动

- 左键点击 clip：选中；
- 左键拖动 clip 中央区域：改变 start_ms；
- 拖动期间显示 ghost，不实时写 DB；
- mouse release 后校验并提交一次命令；
- locked track 不允许移动；
- 如果移动后超出 timeline 起点，clamp 到 0 或回滚，按统一策略并给出提示；
- 拖动期间按 Escape 取消，恢复原位置。

### 5.2 Trim

- clip 左/右边缘 6 px 区域为 trim handle；
- 向内拖动改变 clip duration 和 offset；
- 左侧 trim：offset_ms 增加，duration_ms 减少，start_ms 同时前移/后移必须按用户拖动方向定义并在数据契约中保持一致；
- 右侧 trim：只改变 duration_ms；
- duration_ms 必须大于 0；
- 不允许 trim 后超出 source 可用时长；source duration 未知时允许开放边界但显示 UNKNOWN，不伪造上限。

### 5.3 复制、删除、禁用

- Ctrl+C/Ctrl+V：复制选中 clip 到当前 playhead，生成新的 clip_id；
- Ctrl+D：复制 clip 并沿时间轴偏移一个吸附间隔；
- Delete：删除选中 clip，要求可撤销；
- Space 不在 timeline 内编辑文本时播放/暂停由 Prompt 09 scheduler 处理；Prompt 08 只发出命令，不自己创建 timer 播放。
- 禁用 clip：保留资源引用和位置，只是不参与 09 预演；
- 锁定 track：禁用其 clip 移动/trim/删除（删除需先解锁）。

### 5.4 多选

- Ctrl+单击多选；
- Shift+点击选择连续时间区间内 clips；
- 框选仅在空白处拖动时开始；
- 多选拖动保留相对时间偏移；
- 多选删除/移动均为单一可撤销命令；
- 不允许同一 clip 在一次操作中提交多次。

## 6. Track 管理

支持：
- 添加机器人轨道；
- 添加 group 轨道（若有 schema）；
- 重命名；
- 上移/下移；
- mute；
- lock；
- 删除空轨道；
- 非空轨道删除前提示 clip 数量，提供“取消”或“删除轨道及全部片段”；第二个选项需二次确认并作为一个 undoable transaction。

同一 robot 是否允许多个 action track、trajectory track，取决于当前 Timeline schema 与调度语义。先在 ADR 中定义，不得 UI 自行允许而 scheduler 无法解释。

## 7. 冲突检测与时间规则

定义统一的时间单位：整数毫秒。

必须验证：
- start_ms >= 0；
- duration_ms > 0；
- offset_ms >= 0；
- playback_rate > 0 且在配置的允许范围；
- source resource 存在并 READY；
- source_type 匹配 track_type；
- robot/group binding 与 source compatibility 相符；
- Clip 最终 source time 不超出资源范围（已知 duration 时）。

同一 track clip 重叠策略必须在本阶段通过 ADR 确定，并落实测试。候选策略：
1. 完全允许重叠；
2. 允许但显示冲突；
3. 禁止重叠并阻止 drop/move。
不允许按“先实现再说”混用多套规则。

不同 track 的时间重叠通常允许，但同一 robot 的动作/轨迹跨 track 重叠需定义：
- 是否允许动作和轨迹同步；
- 若允许，需要由 Prompt 09 的 binding/priority 处理；
- 若不允许，Prompt 08 必须在 save 前阻止。
不得用 clip 绘制顺序决定运行优先级。

## 8. 时间轴缩放与滚动

- zoom in/out 以 playhead 或鼠标位置为锚点，保持该时间点屏幕位置稳定；
- fit timeline 根据最大 clip end time 和最小可读时间尺计算；
- 横向 scrollbar 与时间尺/clip content 共用同一 transform；
- 垂直 scrollbar 不影响时间坐标；
- 时间轴 ruler 支持主/次刻度；
- 高 DPI 下 pointer hit-test 使用 device independent pixels；
- 不能用字符串格式化后的“1.5s”反向解析真实时间；模型一直存整数 ms。

## 9. Undo/Redo、保存与并发

实现 commands：
- AddTrack / RemoveTrack；
- AddClip / MoveClip；
- TrimClipLeft / TrimClipRight；
- DeleteClip / DuplicateClip；
- EnableClip / DisableClip；
- ReorderTrack；
- BatchMoveClips。

操作期间只改 timeline edit model，不直接 SQL。保存统一调用 Facade `save_timeline()`，使用 transaction。保存成功更新 revision 和 clean index；保存失败恢复存储状态但保留用户编辑态，并给出重试。revision 冲突时展示“时间轴已被其他操作修改”，允许重新载入比较，不自动覆盖。

## 10. Timeline Event Map

创建 `docs/agent-prompt-pack/audit/08-timeline/control-event-map.csv`，至少记录：
`widget_id,visible_text,event,handler,command,model_change,validation,error_feedback,test_id`

覆盖 toolbar、ruler、track menu、clip body、trim handles、search、拖放资源等所有输入。

每个控件都必须有 handler；无实现能力的按钮隐藏。

## 11. 测试验收

Domain：
- 时间单位和 ms<->pixel transform；
- start/duration/offset/rate validation；
- source duration trim validation；
- track/source type compatibility；
- robot binding mismatch；
- overlap policy；
- timeline save/load round-trip；
- revision conflict；
- deterministic clip order（start_ms 相同按稳定次序排序）。

Qt：
- 从资源拖入 timeline；
- drop 到无效轨道拒绝；
- move clip；
- trim left/right；
- duplicate；
- delete/undo/redo；
- multi-select batch move；
- zoom 锚点稳定；
- horizontal scroll alignment；
- locked/muted track；
- dirty/save/failure/conflict。
- 无资源、空时间轴和 broken clip 引用状态。

Regression：
- Prompt 06 轨迹编辑保存不受影响；
- Prompt 07 阵型数据不被时间轴拖动修改；
- 03 页面切换和 splitter 行为保持；
- Prompt 01 兼容性测试通过。

## 12. 交付

- Timeline domain validators；
- Track/Clip Application Use Cases；
- 单一 TimelineCanvas UI；
- ruler、tracks、clip、trim handles 和 drag/drop；
- command/undo stack；
- overlap ADR；
- control event map；
- 测试报告和截图存于 `docs/agent-prompt-pack/audit/08-timeline/`。

本阶段不实现 3D 播放时钟、机器人动作采样和 3D 视口联动，这些属于 Prompt 09。
