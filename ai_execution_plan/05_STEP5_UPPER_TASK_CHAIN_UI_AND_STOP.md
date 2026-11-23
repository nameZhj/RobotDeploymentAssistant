# Step 5: 舞台编导任务链重构、70:30 视口比例与停止即回原点计划 (05_STEP5_UPPER_TASK_CHAIN_UI_AND_STOP)

## 1. 阶段目标
满足需求一.2 与 一.3：
- **任务链替代时间轴**：保持现有动态播放视觉效果，不再用时间（秒）表示，也**不显示“步骤几”**，直接以 **`“导航到点1” - “太极” - “街舞” - “导航到点2”`** 纯动作/导航名称链格式呈现；前序导航到达目标点后再执行下一动作。
- **视口比例 (`70% : 30%`)**：调高上方舞台预览视口高度，降低底部任务链播放视口高度，精确按 `7 : 3` 比例分配。
- **增加停止按钮（停止即回到原点）**：在舞台底部浮动播放栏与任务链顶栏同时增加“停止”按钮，点击后立即停止播放并让所有机器人回到初始原点 `(init_x, init_y, init_yaw)`（同时通过 HTTP 通知下位机取消规划并导航回原点）。

## 2. 精确修改文件清单
1. `upper_computer/src/services/task_chain_normalizer.py` [NEW]：
   - 将同一轨道上的任务块按顺序归一化为连续任务链节点（自动维护节点顺序与视觉紧凑链槽位，支持拖拽重排顺序、插入、删除）。
   - 实现任务链动态位姿与动作求值：当机器人执行“导航到点1”到达终点后，保持在该终点位置执行“太极”、“街舞”，随后从该点出发执行“导航到点2”。
2. `upper_computer/src/ui/choreography/timeline_block_painter.py` & `timeline_lane_view.py` [MODIFY]：
   - 移除顶部标尺的 `0s, 1s, 2s...` 秒数刻度，改为简洁的任务链流向标尺（不显示“步骤几”和“秒”）。
   - 单轨统一绘制任务链节点，相邻节点间绘制链式连接符 **`-`**，块内仅显示纯净名称（如 `导航到点1`、`太极`、`街舞`、`导航到点2`，无 `· 5.0s` 时长后缀，无 `步骤#1` 前缀）。
3. `upper_computer/src/ui/choreography/choreography_page.py` [MODIFY]：
   - `left_split.setStretchFactor(0, 7)`，`left_split.setStretchFactor(1, 3)`，`left_split.setSizes([560, 240])`（精确 `70% : 30%` 比例）。
4. `upper_computer/src/services/playback_coordinator.py`, `upper_computer/src/ui/choreography/playback_progress_bar.py`, `upper_computer/src/ui/choreography/timeline_header.py` [MODIFY]：
   - `PlaybackCoordinator.stop_and_return_origin()`：停止播放定时器，游标归零回到原点 `(init_x, init_y, init_yaw)`，并触发 `state.stop_all_robots_and_return_origin_http()`。
   - `PlaybackProgressBar` 与 `TimelineHeader` 增加显式 **“停止回原点”** 按钮（带 `stop` 图标），并将进度条文字由秒数时间码改为当前任务链节点名称显示。
