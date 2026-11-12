# PROMPT 09 — 3D 可视化预演、时间调度器与 Timeline Playback

> **类型：3D 预演运行时。** 本阶段把 Prompt 08 的 Timeline 转换为确定性、可暂停、可 seek、可重复的 3D 可视化预演。默认不向真实机器人发送任何运动命令。若没有真实的动力学/碰撞模型，只能称为“可视化预演/运动学预览”，不能称为物理仿真。

## 0. 前置条件

- Prompt 04：Robot/Map/Trajectory/Formation/Action/Timeline 数据契约和 revision 已完成。
- Prompt 05：地图已可加载到 3D viewport。
- Prompt 06：Trajectory geometry 和可选 waypoint timing 可读取。
- Prompt 07：Formation local offsets 和机器人绑定可读取。
- Prompt 08：TimelineClip、track binding、overlap policy、clip timing 已确定。
- Prompt 02：Qt worker 和 service 生命周期明确。

不能用一套独立虚构 sample data 绕过上述数据层。

## 1. 预演系统的职责边界

输入：
- 当前 scene；
- 当前 map；
- robot configuration + model assets；
- formation；
- timeline tracks/clips；
- action assets 和 trajectory assets；
- preview configuration。

输出：
- 给定 timeline time `t_ms` 时，每个机器人模型的目标 pose；
- 每个模型可显示关节的关节位置/角度（仅动作文件确实有对应数据时）；
- 当前 clip 状态、缺失资源和 validation warning；
- 视口的 render state。

绝对禁止：
- 本阶段向机器人发送真实运动指令；
- 自动调用真实遥控接口；
- 未获用户确认就调用部署/下发 API；
- 将预演 pose 写回 Robot persistent/live pose；
- 把 preview 当作机器人执行状态。

必须建立清晰 Preview Mode 标识：
- `PREVIEW / LOCAL ONLY`；
- 如果数据来源包含模拟设备，标注 `SIMULATION DATA`；
- 任何真实设备连接状态单独显示，不能混为预演运行状态。

## 2. 3D 主视图布局和控件

复用 `StageViewport3D`。不得创建独立的另一个 3D 引擎进程或 WebView，除非 02 ADR 已批准。

画布上方保留：
- 3D 视图切换；
- 当前 map 名称；
- `适配内容`；
- `网格`；
- `机器人模型显示`；
- `轨迹显示`；
- `阵型辅助显示`。

右上角 display settings popover：
- 地图可见性；
- 轨迹可见性；
- waypoint marker；
- robot model；
- joint axes（仅 renderer 支持时）；
- frame axes；
- floor/grid；
- label；
- ghost path。

每个选项必须真正控制独立 render layer，不能通过清空 scene 再全部重画来达到隐藏效果。

播放控制条位于时间轴 toolbar 或其上方，最少包括：
- 播放；
- 暂停；
- 停止/回到 0；
- 前一帧；
- 下一帧；
- 当前时间输入/显示；
- 总时长；
- 播放速度；
- 循环（若有实现）；
- 预演状态提示。

播放速度选项建议：0.25×、0.5×、1×、2×、4×。速度调整只改变播放时钟推进速率，不改变源数据采样定义和 clip 时长。

按钮高 28 px；时间显示 100–130 px；状态文字 11 px。遵循 Prompt 03 Theme。

## 3. Preview Runtime 架构

实现单一 `PreviewScheduler` 或沿用已有 scheduler。不要让 TimelineCanvas、MainStudioWindow、3D Viewport 各自启动 QTimer。

推荐边界：

```text
Timeline UI ── Playback Commands ──> PreviewController
                                          │
                                          ▼
                                    PreviewScheduler
                                          │  t_ms
                                          ▼
                                    PreviewEvaluator
                                          │
                     ┌────────────────────┼───────────────────┐
                     ▼                    ▼                   ▼
               TrajectorySampler     ActionSampler      FormationResolver
                     │                    │                   │
                     └────────────── RenderState ─────────────┘
                                          │
                                          ▼
                                    Qt 3D Viewport
```

职责：
- `PreviewController`：play/pause/stop/seek/speed/frame-step/loop 状态机。
- `PreviewScheduler`：驱动时间，单实例 timer；不计算几何。
- `PreviewEvaluator`：纯函数/可重复服务，输入 `timeline + t_ms + resources` 输出 RenderState。
- `TrajectorySampler`：根据轨迹资源和 clip timing 计算机器人 pose。
- `ActionSampler`：解析动作时间采样并映射到模型关节。
- `FormationResolver`：在轨迹或动作未明确覆盖位置时，按场景/track 规则提供 formation-relative pose。
- `RenderStateAdapter`：把 domain poses 映射到现有 Qt 3D renderer。

Domain evaluators 不 import QWidget，不依赖墙上时间。

## 4. 确定性时间模型

统一时间单位：整数 milliseconds。

PreviewController 状态：
- `STOPPED`
- `PLAYING`
- `PAUSED`
- `ENDED`
- `ERROR`

必须定义状态转移：
- STOPPED -> PLAYING：从当前 playhead（默认 0）开始；
- PLAYING -> PAUSED：保持当前时间；
- PAUSED -> PLAYING：从暂停时刻继续；
- 任意非 ERROR 状态 -> STOPPED：playhead 回 0，视图刷新到 t=0；
- PLAYING 到达 duration：状态 ENDED；若 loop 开启则按明确策略回绕；
- ERROR：资源缺失/数据无效时停止并显示原因，不能继续假播放。

Scheduler：
- 使用 Qt 单一 QTimer 驱动 UI 更新，或项目批准的统一 clock。
- 基于 monotonic elapsed time 计算经过量，不能简单每次 `t += 16` 假定每次 timer 都准时。
- `t_ms = start_ms + elapsed_monotonic_ms * playback_rate`，并 clamp 至 timeline duration。
- 播放速度和 frame rate 是不同概念：rate 改变时间流逝，frame stepping 根据预演采样间隔改变当前 t。
- UI 刷新可以节流，但 evaluator 在相同输入下必须得到相同输出。
- `seek(t_ms)` clamp 到 `[0, duration]`，更新全部模型状态，不依赖从上次状态累积变换。
- Pause/Resume 不能累计偏移误差。
- 长时间运行需考虑 integer precision；时间模型始终用 int ms 或高精度内部单调计时。

### 帧步进

- 如果 timeline 有固定 frame_rate，frame step 为 `1000/frame_rate` 的最近整数 ms，并保留 frame index 以避免累计舍入漂移。
- 如果 timeline 无 frame_rate，使用预览配置中的采样间隔；UI 显示真实采样间隔。
- 上一帧/下一帧在 start/end 时 clamp。

## 5. Clip 时间映射

给定 clip：
- `start_ms`；
- `duration_ms`；
- `offset_ms`；
- `playback_rate`；
- 当前 timeline time `t_ms`。

若 clip disabled 或 `t_ms` 不在 `[start_ms, start_ms + duration_ms)`，不参与本时刻的 sample。

clip local time：

\[
t_{local} = offset_{ms} + (t_{ms} - start_{ms}) \times playback\_rate
\]

再根据 source duration clamp 或结束。若资源 duration 未知：
- 不能猜测；
- 使用 clip duration 作为展示时窗；
- 若 source 无法提供 sample，返回 `SOURCE_DURATION_UNKNOWN`/`UNSAMPLEABLE`，不伪造最后姿态。

TimelineClip 与 source 资源的 revision/hash 不匹配时：
- 标记 `SOURCE_CHANGED`；
- 要求重新校验或刷新引用；
- 不可 silently playback 新版本替代旧版本，除非 domain contract 明确支持 pinned revision。

## 6. TrajectorySampler

输入：
- trajectory waypoints；
- 当前 clip local time；
- 可用的 waypoint `time_from_start_ms` 或稳定速度配置；
- 坐标 frame；
- track robot binding。

算法分两种：

### A. 轨迹包含明确时间参数

- 按 `time_from_start_ms` 找到时间区间；
- 对 x/y 使用线性插值；
- yaw 使用最短角距离插值并 normalize；
- 明确处理 duplicate timestamp：若 schema 不允许则预先验证拒绝，不在 sampler 中猜测；
- 超出轨迹 duration 按 clip 规则停止或保持末端 pose。

### B. 轨迹没有时间参数

禁止凭空假设机器人速度。
可选策略：
1. 使用用户明确设置的 preview speed（带单位，且标注 `Preview Assumption`）；
2. 如果没有预览速度，轨迹可在 3D 场景显示为静态路径，但不能让机器人沿路径自动移动。

如使用预览速度：
- 计算 polyline arc length；
- 使用 speed 估计沿线位置；
- 在 preview UI 明确显示速度假设；
- 不把预览速度写回真实机器人配置或原轨迹默认字段；
- 预演结果不代表实际执行时间。

对于路径方向、frame transform、yaw 轴向，必须经过 DATA_CONTRACTS 中的 coordinate adapter。

## 7. ActionSampler 与模型关节映射

只支持当前真实 action parser 能解析的格式。先分析 action asset：
- sample rate；
- timestamp/frame index；
- joint names；
- angle unit；
- channel layout；
- interpolation rule；
- file duration；
- model compatibility metadata。

如果动作只有一个黑盒文件，无法解析 joint channels：
- 可以在时间轴显示 ActionClip；
- 3D 预演中显示“动作文件尚无可采样关节数据”；
- 不得用随机摆动、sin 波、默认动作填充。

对可解析动作：
1. 用 clip local time 转换为 sample index 和 fractional alpha；
2. 根据 joint name 映射至当前 URDF/model joint；
3. 对 revolute joint 处理角度单位和最短角距离；
4. 对 prismatic joint 使用模型单位；
5. clamp 到 URDF joint limits；超限给 warning；
6. 不存在的 joint 标记为 mapping warning，不把其他关节错位套用；
7. 采样器纯函数测试同一输入输出稳定。

## 8. 多机器人位置合成与轨道优先级

必须在 ADR 中定义同一 robot 同一时间被多个 clip 影响时的组合策略。不得按 UI 绘制顺序决定优先级。

至少考虑：
- Robot Trajectory clip：提供 base pose；
- Formation：提供组成员的相对基准 pose；
- Action clip：提供关节角度/姿态通道，不默认覆盖根位姿；
- 无轨迹 clip 时：使用 formation preview pose 或真实配置初始 pose（若已定义）；
- 不同 clips 时间重叠：按 Prompt 08 决定的规则报错/显示冲突/明确合成。

对同一机器人多个 position source 同时 active：
- 若策略未确定，PreviewEvaluator 返回 `AMBIGUOUS_POSITION_SOURCE` 并停止该 robot 的预演；
- 不允许静默选择一个。

输出 `RobotPreviewState`：
- robot_id；
- world pose；
- joint_values；
- active_clip_ids；
- source_revision/hash；
- warnings；
- sample_time_ms；
- state quality（VALID/STATIC/ASSUMED/UNAVAILABLE）。

## 9. 3D 渲染器接线

复用现有 `StageViewport3D`：
- map renderer 不因 timeline playhead 改变而重新解析 PCD；
- robot model instances 按 robot_id 缓存；
- joint update 只更新对应关节 transform；
- trajectory/formation overlays 各自独立 layer；
- playhead 变化时通过一个 RenderState 更新入口批量刷新，避免每个 evaluator 多次重绘；
- 删除/关闭 scene 时释放 geometry、buffers、textures 和 model references；
- renderer 不持有 Repository 或 SQL connection；
- renderer 不自行启动 Playback timer；
- 切换 2D/3D 保留 playhead 和 playback state，回到 3D 时渲染当前时间状态。

如果当前 renderer 不支持 skeleton/joint update：
- 先建立具体能力差距和 ADR；
- 不得用移动整个机器人模型冒充关节动作；
- 允许先完成轨迹根位姿预览，但动作采样能力标记 `NOT_AVAILABLE`。

## 10. 可视化辅助与冲突提示

显示选项：
- 地图；
- 机器人模型；
- 轨迹路径；
- waypoint；
- formation anchor；
- formation slots；
- robot labels；
- coordinate frame；
- ground grid；
- active clip outline。

Warnings 至少：
- 缺地图；
- 地图 frame 不匹配；
- robot model missing；
- action source unsupported；
- joint mapping incomplete；
- trajectory has no timing and no preview speed；
- clip overlap conflict；
- ambiguous position source；
- source revision changed；
- out-of-range joint value；
- missing robot binding。

警告可以按 robot/clip 过滤。预演 UI 必须区分：
- ERROR：不能生成该 robot 的有效预览；
- WARNING：可以显示，但存在假设/缺失；
- INFO：正常状态。

不能把几何线段距离检查说成物理碰撞检测。如果只是 footprint overlap，标记为 `GEOMETRIC_OVERLAP_WARNING`。

## 11. UI 交互和状态一致性

播放按钮状态由 `PreviewController.state` 决定：
- STOPPED/PAUSED：显示播放；
- PLAYING：显示暂停；
- ENDED：显示重新播放；
- ERROR：禁用播放并显示错误原因。

其他操作：
- Stop：回到 t=0；
- Seek：用户拖动 playhead 时暂停或按明确策略临时 seek；
- 手动输入时间：validate 后 seek；
- speed selector：播放中即时改变 clock rate；
- loop：只有完整 loop behavior 实现才显示；
- frame step：按采样间隔精确移动；
- 点击 clip：定位至 clip start；
- 点击 warning：选中对应 clip/robot 并显示详情。

关闭窗口：
- 停止 timer；
- 断开 signal；
- 取消 worker；
- 不留下后台播放；
- 再次打开时从 STOPPED 开始，除非产品明确要求恢复 playhead 且状态持久化已设计。

## 12. 性能和可预测性

- evaluator 与 renderer 更新分开。
- timeline 时间相同、资源 revision 相同时，RenderState 必须一致。
- 对固定轨迹/action 预取采样索引，但 cache key 必须包括资源 hash/revision、clip parameters 和采样器版本。
- 不要每个 timer tick 从 SQLite 读取全部 clip。
- 不要每帧重新解析 URDF/PCD/action 文件。
- 超过一定机器人数量或关节数量时进行性能 profiling；阈值应来自实测，不可写虚构 FPS。
- UI 保持可响应，刷新频率可节流；时间精度和渲染刷新率分离。
- 发生一帧迟滞时按真实 monotonic elapsed time 更新，不积累 timer tick 漂移。
- 长 timeline seek 使用缓存/二分定位，不从 t=0 顺序回放所有事件。

## 13. 自动化测试

### Scheduler state tests
- play/pause/resume/stop；
- reach end；
- loop wrap；
- speed changes；
- seek；
- previous/next frame；
- timer drift simulation；
- no negative time or overshoot；
- error transition；
- close stops timer。

### Evaluator determinism
- same timeline/resources/time -> identical RenderState；
- clips outside active interval ignored；
- clip local time conversion；
- offset/playback_rate；
- broken source；
- source revision changed；
- ambiguous multiple position sources；
- multiple robot tracks；
- formation fallback；
- disabled clip ignored。

### Trajectory sampling
- explicit waypoint timing interpolation；
- angle wrap interpolation；
- duplicate timestamps invalid；
- no timing + no preview speed => static path only；
- configured preview speed => distance/time mapping；
- end behavior and out-of-range.

### Action sampling
- sample index interpolation；
- joint name mapping；
- rad/degree conversion；
- revolute/prismatic joint handling；
- URDF limit warning/clamp；
- unsupported file returns explicit unsupported status, never random pose.

### Qt integration
- playback updates 3D view;
- seek updates all robot models;
- play speed changes do not change timeline data;
- switching 2D/3D preserves playhead;
- model missing does not crash viewport;
- rendering warning links to proper asset;
- no network/serial send method called during preview.

### Regression
- Prompt 05 map remains loaded without repeated PCD parsing;
- Prompt 06 trajectory edit/reload is not altered by preview;
- Prompt 07 formation local offsets are not overwritten;
- Prompt 08 clip data is read-only during preview;
- all Prompt 01 compatibility tests run.

## 14. 完成验收和交付

提交：
- PreviewController；
- PreviewScheduler；
- PreviewEvaluator；
- TrajectorySampler；
- ActionSampler（如果现有 action parser 具备数据）；
- FormationResolver；
- RenderState data model；
- StageViewport3D adapter；
- playback controls；
- overlap/position-source ADR；
- scheduler/evaluator/Qt/regression tests；
- screenshots and performance profiles in `docs/agent-prompt-pack/audit/09-preview/`。

交付报告必须明确：
- 当前支持的动作文件格式；
- 当前可采样的关节通道；
- 轨迹是否有时间参数；
- 需要假设的 preview speed；
- 3D renderer 的真实能力；
- 未完成的物理/碰撞能力；
- 是否有任何真实硬件接口被触发（本阶段应为否）。

本阶段的最终状态名称使用“3D 可视化预演”，不要写“物理仿真完成”。完成后更新所有状态文档和 SESSION_HANDOFF。
