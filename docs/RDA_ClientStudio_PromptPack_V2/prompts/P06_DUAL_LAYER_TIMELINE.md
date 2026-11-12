# P06 — 双层时间轴、轨道管理、Clip 编辑与本地播放调度

**阶段目标**：把现有 `DualLayerTimelineCanvas` 从“可绘制和拖动矩形块”完善为真实时间轴编辑器。动作、舞蹈、轨迹和群组轨迹来自 P05 的素材契约；Clip 保存在当前工程，并被 3D 播放器直接消费。

**前置**：P00–P05 COMPLETE。

## 1. 现有代码审计

逐项检查：

- `src/ui/choreo_page/dual_layer_timeline_canvas.py`
- `src/ui/choreo_page/timeline_left_toolbar.py`
- `src/ui/choreo_page/timeline_canvas_renderer.py`
- `src/application/stage_director/timeline_choreo_controller.py`
- `src/domain/timeline/timeline_clip_asset.py`
- `src/infrastructure/storage/timeline_clip_sqlite_adapter.py`
- `src/application/stage_director/stage_preview_engine.py`
- `src/application/services/virtual_show_player.py`
- `src/application/stage_director/stage_preview_coordinator.py`
- `src/ui/windows/main_studio_window.py`
- P01/P03/P05 的 Project、Robot、Asset、Trajectory Repository。

当前快照中 `DualLayerTimelineCanvas.__init__()` 内部直接创建 `TimelineChoreoController()`；`load_from_store()` 读取控制器的 Clip；dropEvent 将素材 dict 直接交给控制器；`TimelineChoreoController` 先读 `asset_type`；mouseMoveEvent 直接改 `TimelineBlock` 内存对象，mouseReleaseEvent 持久化但不根据 bool 结果回滚。必须修复。

## 2. Timeline Domain Model

每个 Clip 至少包括：

- `clip_id`：稳定 ID。
- `project_id`。
- `task_id` 或当前工程内部的 show/sequence ID；不能所有工程共用硬编码“默认任务1”。
- `asset_id`：素材库稳定 ID。
- `asset_type`：DANCE/ACTION/TRAJECTORY/GROUP_TRAJECTORY/FORMATION（实际允许的类型）。
- `ref_id`：底层资源 ID。
- `target_type`：robot/group。
- `target_id`：RobotInstance ID 或 Group ID。
- `track_id`：对应 TimelineTrack ID。
- `track_layer`：ACTION / TRAJECTORY。
- `start_ms`、`duration_ms`、`offset_ms`、`rate`。
- `allow_stretch`。
- `name`、`schema_version`、更新时间。

字段语义要写入 DATA_CONTRACTS。时间一律毫秒；UI 显示秒/帧只是格式化。Clip 引用资源，不复制整份 Trajectory/Action 内容。

区分 `TimelineTrack` 和 RobotInstance：轨道是编排通道，不代表在线机器人。轨道可以是机器人轨道或群组轨道。

## 3. 轨道生成和视图布局

- 根据当前工程真实 RobotInstance 动态生成轨道；用户可隐藏/展开轨道，但不能凭空 seed。
- 提供明确的 GROUP 轨道（若工程启用群组编排）。
- 每个 Robot Track 包含上层 ACTION lane 和下层 TRAJECTORY lane。
- 轨道名称、Robot ID、颜色来自 RobotInstance。
- 对没有机器人时显示空状态，并引导先添加 RobotInstance；空状态不能出现 A/B/C/D。
- 支持轨道高度/时间轴缩放，长工程横向滚动。
- 时间刻度、吸附刻度、playhead 和 Clip 绘制必须使用同一坐标换算函数。

## 4. 拖放编排

使用 P05 的 canonical `AssetEnvelope`。禁止 timeline canvas 直接解析多种隐含 dict 结构并猜测类型。

流程：

1. `dragEnterEvent` 检查 canonical MIME。
2. `dragMoveEvent` 实时显示目标轨道和 ACTION/TRAJECTORY 子层预览高亮。
3. `dropEvent` 获取轨道 ID、layer、目标时间。
4. 使用统一时间换算和 snap 规则得到 start_ms。
5. 校验目标轨道与素材类型、机器人型号、轨迹归属、群组类型兼容。
6. 生成 Clip。
7. Repository 事务保存成功后，画布新增 Clip；失败不更新画布并显示可读原因。

drop 结果消息至少区分：非法 MIME、素材不存在、项目不匹配、轨道类型不匹配、目标机器人不匹配、素材引用丢失、保存失败。

## 5. Clip 交互

### 选择

- 单击选中 Clip，显示选中边框并更新 Inspector。
- 点空白取消选择。
- 双击可打开素材详情或 Clip 属性编辑器。

### 移动

- 按下记录原始 start_ms；拖动显示临时位置。
- 按 snap_ms（默认 100ms，可在 UI 调整）吸附。
- 同一项目允许重叠的规则由业务校验明确；不能无提示覆盖其他 Clip。
- mouse release 才向 Controller 提交。
- DB 更新成功后更新正式状态；失败回滚位置并提示。

### 时长拉伸

- 只允许 `allow_stretch=True` 的 Clip。
- 最短时长由 Domain 校验；不允许低于 200ms（或产品明确值）。
- 拖动右边缘改变 duration_ms；显示吸附和时长预览。
- 持久化失败时恢复原 duration_ms。
- 对动作帧有固定时长的素材，默认不允许拉伸；要拉伸必须定义 rate/time-scale 语义，不能简单拉大矩形而仍以原速度采样。

### 删除 / 复制 / 拆分

- Delete 删除选中 Clip，确认是否影响后续动作。
- Ctrl+C/Ctrl+V 可复制（若实现），复制产生新 clip_id。
- Split 只有在定义资源 offset/时间裁剪语义后才能启用。
- 删除后资源本身仍存在；Clip 不是 Asset。

## 6. Undo / Redo

当前 `TimelineChoreoController` 有 snapshot undo/redo；需验证其数据库事务、并发和 project/task 隔离。

- 所有创建/移动/拉伸/删除操作记录可逆命令或快照。
- Undo/Redo 必须同时更新 Repository 和 UI。
- DB 事务失败时不推进 undo/redo 栈。
- undo/redo 栈只属于当前工程/当前时间轴会话；切换项目清空或切换到独立栈。
- 至少保留 50 步（或配置化）。
- Ctrl+Z / Ctrl+Y、工具栏按钮状态一致。

## 7. 播放头、时间刻度和播放器时钟

- Playhead 单一权威时间值 `current_time_ms`。
- 时间轴拖动播放头 → VirtualShowPlayer.seek → StagePreviewCoordinator/3D viewport 更新。
- 播放器 tick → TimelineCanvas 更新播放头，但必须避免 signal loop。
- 播放、暂停、停止、循环、倍速、跳转统一由一个应用服务管理。
- 使用 monotonic clock / elapsed timer 校正实际经过时间，不要仅用固定 16ms 累加而忽略 timer 误差；若仍用 fixed step，必须证明长时间播放漂移满足阈值。
- 有效总时长根据当前工程 Clips 的最大 end_ms 计算；不使用硬编码 10 秒作为工程总时长。
- 空时间轴不得进入播放状态。
- 到达末尾后按 Loop 设置回到 0 或停止；UI 状态按钮同步。

## 8. 预演数据编译

`StagePreviewEngine.build_preview_tracks()` 当前快照以默认 task_name 查询；必须改为接收当前 Project/Sequence ID。

- 只从当前工程数据库读取 Clip 和引用素材。
- 每个 Clip 解析其 Asset/Trajectory/Action 数据；资源缺失列出具体 ID。
- 输出 Preview Snapshot：`project_id`、`sequence_id`、`duration_ms`、`robot_tracks`、`trajectory_lines`、`validation_errors`、`unplayable_items`、`schema_version`。
- 不允许缺失轨迹或动作时生成默认路线/默认姿势并仍标记有效。
- 保持编译纯函数/可测试，播放时不直接从 UI 私有 `_blocks` 读取。
- 不要让 VirtualShowPlayer 和 StagePreviewCoordinator 各自编译两套不同数据；协调器应消费播放器的 pose snapshot 或同一编译结果。

## 9. 时间轴 UI 和 Inspector

- 底部时间轴区域可在 220–450px 左右调整高度，横向滚动性能可接受。
- 时间刻度、Clip、Playhead 颜色层次清晰。
- ACTION lane 与 TRAJECTORY lane 视觉区分。
- 当前选中 Clip 右侧属性 Inspector 显示素材类型、名称、目标机器人/群组、start、duration、offset、rate、stretch。
- 显示当前时间、总时长、缩放百分比、snap 状态、循环状态。
- 所有工具按钮有 toolTip、禁用条件、快捷键和测试 ID。

## 10. 测试

至少覆盖：

1. DANCE/ACTION/TRAJECTORY/GROUP_TRAJECTORY MIME type 到目标层映射。
2. 不匹配的 drop 拒绝，数据库无新记录。
3. 成功 drop 后 Clip 数据库和 UI 完全一致。
4. 移动、拉伸、删除、撤销、重做保存重启后仍一致。
5. Mock DB failure 时 UI 状态回滚。
6. 时间轴 snap 边界、负坐标、最大 duration 和水平滚动坐标换算。
7. Project A/B Clips 完全隔离。
8. 无机器人/无 Clip 时播放禁用。
9. 预览引擎读取的 Clip 与时间轴展示完全相同（数量、ID、start、duration）。
10. 播放、暂停、seek、loop、speed、stop 同步时间轴播放头和预览 Pose。
11. 60Hz 长时间播放漂移测量；写出测量时长、平均 FPS、P95 tick 间隔、最大漂移。

## 11. 用户手工验收

1. 新建项目并添加至少两台 RobotInstance。
2. 把舞蹈拖到 Robot A 的 ACTION lane，把轨迹拖到 Robot A 的 TRAJECTORY lane。
3. 把第二条轨迹拖到 Robot B 的 TRAJECTORY lane。
4. 移动/拉伸 Clip，保存，关闭重开，确认位置和时长恢复。
5. 删除一个 Clip，Undo，再 Redo，数据库和画面同步。
6. 播放、暂停、拖动 playhead、倍速、循环和停止，确认 3D 视口时间同步。
7. 切换另一个工程，确认不出现上一工程的轨道/Clip。

## 12. 交付

Timeline Domain/Controller/Adapter/UI 真实实现、统一 Preview Snapshot、测试和性能报告、`P06_TEST_REPORT.md`。完成后进入 P07。
