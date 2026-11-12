# 项目审计基线（GitHub main 静态代码审计）

**检查日期**：2026-11-12  
**仓库**：`nameZhj/RobotDeploymentAssistant`  
**读取来源**：GitHub `main` 分支文件；未在本次审计环境中启动 Windows Qt 应用。以下是源码观察，不是运行时验证。

## 1. Skill 路径更正

已重新成功读取：

`.agent_workspace/skills/robot-deployment-assistant/SKILL.md`

Blob SHA：`b826e79af37d65d5fe92505b6ec7cb7cf2337871`

此前检查 `.agents/skills/...` 是路径写错；不能再声称 Skill 未进入仓库。

## 2. 舞台编导实际入口

- `main.py` 的 `StudioWindowManager` 延迟创建 `QApplication`，并实例化 `src.ui.windows.main_studio_window.MainStudioWindow`。
- 舞台编导使用 PySide6，不是 `AGENT_GUIDE.md` 中所描述的 pywebview 渲染窗口。
- `AGENT_GUIDE.md` 的系统总览混合了过时/其他系统结构，执行舞台编导任务时应先以真实 import、调用栈和当前源码为准；不要直接按文档重建。

## 3. 当前确认的问题（必须在本地分支复核）

### 3.1 MainStudioWindow 的依赖未统一注入

文件：`src/ui/windows/main_studio_window.py`

- `__init__` 创建 `self.store = ChoreoSqliteStore()` 和 `self.map_controller = StageMapController(...)`。
- `_build_layout()` 创建 `LeftDockTabs(..., controller=self.controller)`，而不是显式传 `self.map_controller` 和本地 Store/Project Context。
- `_init_choreo_studio()` 创建 `StageCanvas2D(..., controller=self.controller)`，没有传 `store=self.store`。
- `LeftDockTabs.__init__` 只有 `controller` 参数；内部通过 `getattr(self.controller, "map_controller", None)` 找地图控制器。如果 `controller` 为 `None`（`main.py` 当前创建 MainStudioWindow 时没有传这个 controller），`MapManagerPanel` 会自行构造新的 `StageMapController`。
- `StageCanvas2D` 的 `self.store` 只取显式 `store` 或 `controller.store`；当前主窗口调用没有显式注入 store。

结论：主窗口创建的 `self.map_controller` 未形成明确共享链路；地图面板、画布、时间轴和预览服务的依赖来源不够明确。P00 必须修复。

### 3.2 时间轴控制器单独创建

文件：
- `src/ui/choreo_page/dual_layer_timeline_canvas.py`
- `src/application/stage_director/timeline_choreo_controller.py`
- `src/infrastructure/storage/timeline_clip_sqlite_adapter.py`

`DualLayerTimelineCanvas.__init__` 内部执行 `TimelineChoreoController()`，无法由 MainStudioWindow 传入统一 Project/Store。它当前使用默认 `data/choreo_database.db`，虽然路径与 `ChoreoSqliteStore.DEFAULT_DB_PATH` 一致，但控制器实例、任务名、项目上下文和数据生命周期都没有显式统一。

### 3.3 素材拖放的数据类型存在不匹配风险

文件：
- `src/ui/asset_library.py`
- `src/core/asset_registry.py`
- `src/ui/choreo_page/dual_layer_timeline_canvas.py`
- `src/application/stage_director/timeline_choreo_controller.py`

`AssetRegistry` 输出字段使用 `category`（`dance`、`action`、`trajectory`、`formation`）；`DraggableAssetListWidget.startDrag()` 将完整 dict 写入 MIME；时间轴控制器 `create_clip_from_dropped_asset()` 首先读取 `asset_type` 并转大写，用其判断 ACTION/DANCE/TRAJECTORY。若拖入的数据没有 `asset_type`，动作/舞蹈可能走默认轨迹分支。必须建立一个显式、版本化的 MIME/Clip 适配契约，不允许依赖偶然字段。

### 3.4 时间轴编辑状态可能与持久化状态脱节

`DualLayerTimelineCanvas.mouseMoveEvent()` 直接修改 `_dragged_block.start_ms` 或 `_resizing_block.duration_ms`；`mouseReleaseEvent()` 再调用控制器 `move_clip()` / `resize_clip()`，但当前调用方没有依据返回值进行 UI 回滚。数据库更新失败时，需要恢复旧值、提示用户并重载真实状态。

### 3.5 默认演示机器人数据

文件：
- `src/ui/stage3d/stage_viewport_3d.py`
- `src/application/services/virtual_show_player.py`
- `src/application/stage_director/stage_preview_coordinator.py`

当前 3D 视口构造时初始化 `Robot_1`、`Robot_2` 的颜色与位姿；`VirtualShowPlayer._init_default_tracks()` 初始化两台机器人轨迹和动作；`StagePreviewCoordinator` 默认 `load_defaults=True` 并生成相似数据。即使主窗口后面清空部分 UI 轨道，预览对象仍可能从内部默认值显示出来。正式空项目必须真实为空。

### 3.6 右侧面板含通信/运控功能

文件：`src/ui/choreo_page/right_dock_panel.py`

`RightDockPanel` 除对象属性 Inspector 外，还包含 HTTP 轨迹上传、通信状态、串口状态和 STAND/GAIT/STOP/PASSIVE 基础指令按钮，并调用 `robot_trajectory_http_gateway`。这与用户当前的纯本地创作范围不符。应在舞台编导窗口内替换为本地属性 Inspector / Clip 属性面板；不要删除项目其他页面的运维能力。

### 3.7 保存行为写死场景并读取 UI 私有数据

文件：`src/ui/windows/main_studio_window.py`

`_on_save_button_clicked()` 读取 `timeline_canvas._blocks`、`_tracks` 等 UI 私有字段，保存固定 `scene_001` / `主舞台默认场景`，并直接弹出“SQLite 与 data/projects/ 已同步保存”成功提示。它没有表现出明确的当前工程对象/工程选择流程；必须由 ProjectService/Use Case 接管保存行为，只有持久化真实成功后才提示成功。

### 3.8 3D 视口目前不是完整 3D 场景引擎

文件：`src/ui/stage3d/stage_viewport_3d.py`

视口继承 `QWidget`，通过 `QPainter` 和 `_project(x,y,z)` 绘制投影网格、点云、轨迹和机器人骨骼；`RobotAvatar3DPainter` 进一步用 `QPainter` 绘制骨架。该方案可以作为轻量投影预览，但不能直接称为完整 3D 场景/网格模型视口。用户需求是完整 3D 预览，因此 P07 必须评估并落地真正支持 3D 相机、点云/网格、URDF Visual Mesh 和时间轴驱动姿态的视口。

### 3.9 本地地图已有可复用基础

文件：
- `src/ui/map_manager_panel.py`
- `src/application/stage_director/stage_map_controller.py`

已经存在 `MapManagerPanel`、`StageMapController`、PCD 校验、SHA-256 判重、文件复制、SQLite 元数据、active map、地图删除保护、2D 栅格转换等实现。不要另起炉灶重写地图子系统；先查清现有 loader、数据库适配器和 UI 事件连接，再补齐真实工作流。

### 3.10 阵型与轨迹也有现存基础

- `src/ui/formation_panel.py` 已有参数化阵型、计算、安全距离检查、JSON 文件列表和保存/加载方法。
- `src/ui/choreo_page/stage_canvas_2d.py` 已有屏幕/舞台坐标转换、轨迹编辑状态、控制点编辑、保存/删除、地图栅格和群组轨迹预览接口。
- 这些模块不应被全新平行控件替换；要修复与 Project/Robot Registry 的真实数据绑定和 UI 闭环。

## 4. 主要审计入口链接

- [main.py](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/main.py)
- [MainStudioWindow](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/windows/main_studio_window.py)
- [LeftDockTabs](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/choreo_page/left_dock_tabs.py)
- [StageCanvas2D](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/choreo_page/stage_canvas_2d.py)
- [MapManagerPanel](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/map_manager_panel.py)
- [StageMapController](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/application/stage_director/stage_map_controller.py)
- [DualLayerTimelineCanvas](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/choreo_page/dual_layer_timeline_canvas.py)
- [TimelineChoreoController](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/application/stage_director/timeline_choreo_controller.py)
- [AssetLibraryPanel](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/asset_library.py)
- [AssetRegistry](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/core/asset_registry.py)
- [FormationPanel](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/formation_panel.py)
- [StageViewport3D](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/ui/stage3d/stage_viewport_3d.py)
- [VirtualShowPlayer](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/application/services/virtual_show_player.py)
- [StagePreviewCoordinator](https://github.com/nameZhj/RobotDeploymentAssistant/blob/main/src/application/stage_director/stage_preview_coordinator.py)

## 5. 需要 Agent 在本地复核的事项

- GitHub `main` 代码不是用户本地 Prompt 00–05 执行后的工作区快照；本地可能有额外改动。P00 必须先比较本地差异。
- 本次未在 Windows 上启动 Qt UI，因此不能断言当前具体屏幕布局、运行时异常、PCD 加载耗时或视觉效果。
- `StageMapController`、`MapManagerPanel` 使用的 PCD Loader 具体实现和数据结构需在本地完整调用链中复核，不能仅凭类名推断等价。
- `ChoreoSqliteStore`、各 SQLite Adapter 和 `lrmp_compiler` 的历史数据结构需要通过真实数据库 schema / Git 历史 / 测试复核后迁移。
- 机器人 URDF、mesh、舞蹈帧和动作资源目录是否完整，需扫描真实仓库与用户资源后确认；不得用虚构模型/帧填充缺失资源。
