# P07 — 真正的 3D 舞台视口、地图点云、机器人模型与时间轴预演

**阶段目标**：将现有 `StageViewport3D` 从 QPainter 投影绘制视图升级为真正的 3D 视口；加载当前工程地图点云、机器人模型/URDF、轨迹和动作姿态，并与 P06 的时间轴播放头严格同步。

**前置**：P00–P06 COMPLETE。P01/P02/P03/P05/P06 的数据契约必须已稳定。

## 1. 明确当前基础与目标差异

检查：

- `src/ui/stage3d/stage_viewport_3d.py`
- `src/ui/stage3d/robot_avatar_3d_painter.py`
- `src/ui/stage3d/preview_performance_monitor.py`
- `src/domain/simulation/urdf_fk_solver.py`
- `src/domain/simulation/dance_motion_library.py`
- `src/domain/simulation/stage_performance_sampler.py`
- `src/application/stage_director/stage_preview_engine.py`
- `src/application/stage_director/stage_preview_coordinator.py`
- `src/application/services/virtual_show_player.py`
- `assets/models/`、URDF、mesh、舞蹈帧和动作资源目录。

当前 GitHub `main` 快照中 `StageViewport3D` 继承 `QWidget`，在 `paintEvent()` 中通过 QPainter 和 `_project()` 画投影网格、点云、轨迹和骨骼；`RobotAvatar3DPainter` 同样以 QPainter 画线段和关节点。它适合作为轻量投影，但不等同于支持网格模型、真实 3D 相机和 3D 场景对象的完整视口。

本阶段必须交付真正的 3D 相机/场景/对象渲染能力。仅提高 QPainter 细节、增加阴影或把类名改成 Renderer 均不算完成。

## 2. 3D 技术选型：先做可运行 Spike，不允许盲目添加依赖

在当前 Windows + Python + PySide6 的真实环境中，评估至少两个可嵌入 Qt 的渲染方案。可评估但不限于：

- PyVista + VTK Qt Interactor；
- pyqtgraph.opengl / Qt OpenGL widget；
- Qt3D（若当前 PySide6 发行环境确实提供并可打包）；
- 现有项目已经安装/使用的其他可行库。

为每个候选写入 ADR 对比：

- PySide6 版本兼容；
- Windows wheel 可用性和安装步骤；
- 运行时性能、点云渲染能力和 mesh 支持；
- 相机 orbit/pan/zoom 能力；
- URDF link mesh/transform 的实现复杂度；
- 与 Qt signal/slot 和线程模型的兼容；
- PyInstaller 打包大小与 DLL 依赖；
- 许可证和长期维护状态；
- 对现有 2D 主窗口的嵌入风险。

先构建一个最小独立 Spike：创建真实 QApplication、Qt 主窗口、渲染 3D 坐标轴、一个 mesh、一个点云，并验证 orbit/pan/zoom。将启动命令、环境、截图和退出码保存到 `P07_SPIKE/`。

选型后新增依赖必须固定兼容版本并更新 requirements/build configuration。禁止在未运行 Spike 的情况下宣称已验证兼容。

## 3. 统一视口接口

保持上层 `MainStudioWindow` 不感知具体图形库；通过 `StageViewport3D` 或明确定义的 Renderer Adapter 暴露统一接口：

- `set_project_context(context)`
- `set_map(map_id, points, metadata)` / `clear_map()`
- `set_robot_instances(robots)` / `clear_robots()`
- `set_robot_models(model_assets)`
- `set_trajectories(trajectory_snapshot)`
- `set_preview_snapshot(snapshot)`
- `set_playhead(time_ms)`
- `update_robot_poses(poses)` / `set_robot_poses(poses)`
- `set_grid_visible(bool)`
- `set_render_mode(mode)`（只展示实际支持的模式）
- `focus_robot(robot_id)`
- `reset_camera()`
- `capture_screenshot(path)`（用于测试证据）

对已有方法保持兼容，更新调用者和测试。禁止组件内部创建默认机器人或从默认数据库读取数据。

## 4. 真实地图点云与舞台环境

- 加载 P02 提供的原始地图点云或其派生 LOD；不能重复从文件系统私自加载第二张地图。
- 显示原点、XYZ 坐标轴、地面网格和地图边界。
- 支持点大小、点颜色、背景和可视化质量等级。
- 相机 Reset/Fit Map 自动适应地图边界；无地图时回到空舞台范围。
- 大点云需要 voxel/LOD/视锥裁剪或其它受控策略；保留原始 PCD 完整点数和 hash。
- 点云解析、LOD 生成和模型资源加载使用 worker；UI 线程只接收可显示结果。
- 加载新地图时释放旧 GPU buffer/scene actor，避免内存累积。
- 2D 和 3D 使用完全一致的 map_id、origin、单位和坐标方向。

## 5. URDF 和真实机器人 Mesh

当前 `UrdfFkSolver` 已具备 URDF Joint/Link 解析和 FK 基础，但必须检查：

- URDF 文件是否真实存在；
- `<visual>` / `<geometry>` / `<mesh>` / `<origin>` / `<material>` 解析是否实现；
- `package://`、相对路径、绝对路径如何解析；
- mesh 文件格式（STL/OBJ/DAE/GLTF 等）的实际支持情况；
- `compute_fk()` 返回 link transform 是否与视口世界坐标约定一致。

必须实现可验证的 RobotModelAsset 管理：

- `model_id`、model name、URDF path、mesh refs、link/joint 列表、scale、source hash。
- URDF 路径解析使用可配置模型根目录；拒绝不安全越界路径。
- 缺少 mesh/link/joint 时给出具体日志和模型状态。
- 不得因 URDF 缺失而静默生成“看起来像真的”模型。

3D 视口应按 URDF visual geometry 显示真实 mesh；将每个 visual origin、scale 和 link FK transform 正确组合后渲染。

如果某 RobotInstance 没有 model_id 或模型文件不存在：

- 显示明确的缺失模型图标/占位标签，说明“无模型资源”；
- 可选显示坐标点/朝向箭头作为抽象对象，但必须和真实 mesh 区分；
- 不允许把 QPainter 线条骨架描述为真实机器人 mesh。

## 6. 动作姿态和轨迹采样

复用 `StagePerformanceSampler`、`DanceMotionLibrary`、`UrdfFkSolver`。不要在 3D Viewport 中另外实现一套独立时间轴算法。

每个 Robot Pose 至少包括：

- base position x/y/z 和 yaw；
- active action/dance asset ID；
- 关节角度（单位明确）；
- 当前 Clip ID、Clip local time；
- pose status：VALID / POSE_UNAVAILABLE / MODEL_MISSING / STAND_FALLBACK（名字可按现有规范统一）。

对于每个 timeline tick：

1. 根据 P06 Preview Snapshot 和 `current_time_ms` 找到当前机器人所在轨迹段。
2. 采样 base pose，包含轨迹段衔接和 heading 插值。
3. 找到当前动作 Clip，按 Clip offset/rate 映射到动作帧时间。
4. 采样真实 joint keyframe，插值关节角度。
5. FK 计算每个 link 的 world transform。
6. 更新各机器人 mesh transform。

轨迹不应有位置突跳或角度 ±180° 跳变；heading 插值应使用 wrap-aware shortest-angle。动作 Clip 没有真实帧时不得随机生成 joint angles；显示姿态不可用并列出素材缺失。

## 7. 相机和视口交互

至少支持：

- 左键拖动 Orbit；
- 中键或 Shift+左键 Pan；
- 滚轮 Zoom；
- Home/Reset Camera；
- Fit Map；
- 双击机器人聚焦；
- 选中机器人高亮、显示名称/ID；
- 切换 Ground Grid/Point Cloud/Trajectory/Robot Model 可见性。

具体鼠标映射可按选用的渲染库适配，但必须写入帮助提示，并且和现有 2D 鼠标行为不冲突。

## 8. 3D/2D/时间轴联动

- 2D 点击机器人 → 3D 同一 robot_id 高亮并聚焦。
- 3D 点击机器人 → 2D 同一 robot_id 选中；右侧 Inspector 同步。
- 2D 轨迹变化后，3D 轨迹线刷新。
- 阵型 Apply 后，3D 机器人起始位姿刷新。
- 时间轴拖动 Playhead 后，3D 立即显示准确时刻的 Pose。
- 播放/暂停/停止/循环/倍速必须与 P06 一个时钟一致。
- 3D 视口关闭/切回 2D 时不得重复创建多个播放 Timer。
- `VirtualShowPlayer` 和 `StagePreviewCoordinator` 不得各自保留不同默认数据。建议由单一 PreviewPlaybackService 计算 Pose，并通过信号推送给两个视图。

## 9. 性能目标和降级策略

在用户真实地图/模型资源规模下测试，不允许只用 100 个点的小样本声称性能达标。

至少测量：

- 点云总点数/显示点数；
- 点云载入时间与峰值内存；
- 3D 帧率平均值、P95 frame time；
- 同屏 1/5/10 个 RobotInstance 的渲染表现；
- 动作姿态采样开销；
- 切换工程/地图后的 GPU/CPU 内存回收。

建议交付目标：普通地图下交互相机操作保持流畅；播放时稳定接近目标 30/60 FPS（按实际硬件设定）；如果无法达到，明确给出点云 LOD、模型 LOD 和预览质量设置。不要将固定 FPS 数字当作未测量的承诺。

## 10. 本阶段测试

### 自动化

1. 无地图、无机器人时场景正常且无假模型。
2. 加载 PCD 后点数、bounds、origin 正确。
3. URDF 解析的 joints/links 与原始文件一致。
4. FK 的已知关节角度结果通过数值单元测试。
5. visual mesh path 解析正确，缺文件产生 MODEL_MISSING 状态。
6. base trajectory sample 时间插值和 yaw wrap 测试正确。
7. action keyframe 插值边界和 Clip rate/offset 正确。
8. P06 playhead → Preview Pose → 3D transform 数据一致。
9. 2D 与 3D 选中状态同步。
10. 连续加载/卸载地图和模型 20 次无明显内存持续增长。

### Windows GUI

实际运行 Qt 应用并截取：

- 空舞台；
- 有地图点云；
- 有一台真实模型；
- 多台模型和轨迹；
- 动作播放中的姿态；
- 轨道相机、平移、缩放视角。

## 11. 用户手工验收

1. 打开包含 PCD 的项目，切换 3D，地图点云与 2D 方向一致。
2. 加载真实 URDF/mesh 模型，旋转相机从不同角度观察机器人结构。
3. 为 Robot A 绑定轨迹和有真实帧的舞蹈 Clip，播放时间轴。
4. 拖动 playhead，机器人 base pose 和关节姿态同步变化。
5. 暂停、单步 seek、停止、循环；姿态可重复、无随机闪动。
6. 切换 2D/3D，选中机器人和当前时间不丢失。

## 12. 交付

- 3D 技术选型 ADR 和 Spike 源码/截图。
- 真正的 3D Qt 视口实现。
- URDF Visual Mesh 解析与 RobotModelAsset。
- 轨迹/动作时序采样和统一播放服务。
- 性能数据、测试和 Windows GUI 验收截图。
- `P07_TEST_REPORT.md` 与 HANDOFF。

未完成真正 3D 场景、真实模型加载或时间轴姿态同步中的任一核心项时，只能标记 PARTIAL，不得将原 QPainter 透视视图标记为“完整 3D 已完成”。
