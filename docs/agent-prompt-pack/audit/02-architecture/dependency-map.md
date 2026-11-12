# 舞台编导依赖拓扑与调用链审计 (Dependency Map)

> 审计日期：2026-11-12  
> 审计范围：RobotDeploymentAssistant 舞台编导 UI、Application、Domain 与 Infrastructure 全调用路径

---

## 1. 主窗口组件装配与依赖拓扑

```
[ main.py::StudioWindowManager ]
       │ 唤起 / 复用单例
       ▼
[ MainStudioWindow (QMainWindow) ] ── 注入 StudioDependencies / Facade
       ├── TopShowHeader (顶部导航与工程操作)
       ├── ChoreoToolbar (2D绘制、PCD加载、急停控制)
       ├── QSplitter (Vertical)
       │     ├── QSplitter (Horizontal)
       │     │     ├── LeftDockTabs (QFrame, 280px)
       │     │     │     ├── MapManagerPanel (PCD管理与导入) ──> StageMapController
       │     │     │     ├── FormationPanel (几何阵型设计) ────> FormationCalculator
       │     │     │     └── AssetLibraryPanel (素材拖放) ──────> AssetRegistry / Facade
       │     │     ├── Central Viewport Container
       │     │     │     └── QStackedWidget (2D / 3D 视口)
       │     │     │           ├── StageCanvas2D (自绘样条交互画布)
       │     │     │           └── StageViewport3D (3D 孪生透视视口)
       │     │     └── RightDockPanel (属性监视与通信监视, 260px)
       │     └── Timeline Container (底部时间轴, ≥220px)
       │           ├── TimelineLeftToolbar (轨道头与播放滑块)
       │           └── DualLayerTimelineCanvas (双子层素材放置与时序编辑)
       └── GroupTrajectoryWorkspace (群组轨迹展开工作区) ──> GroupTrajectoryController
```

---

## 2. 核心调用路径审计

### 2.1 PCD 点云从磁盘到视口的调用链路
```
用户选择 PCD 路径
  → MapManagerPanel / StageMapDialog
  → StageMapController.import_map_pcd(path)
  → PcdLoader.load_pcd(path) [纯 Python 解析，计算点集与 bounds]
  → MapGridProcessor.generate_2d_occupancy_grid(points) [生成 2D 占据栅格]
  → StageCanvas2D.set_grid_data(img, info, meta) [2D 画布底图渲染]
  → StageViewport3D.set_point_cloud(points) [3D 视口三维散点渲染]
```

### 2.2 轨迹/阵型/时间轴编排与编译调用链路
```
画布/面板完成编排
  → TimelineCanvas / FormationPanel
  → StudioFacade / LRMPCompiler
  → TrajectoryModel / FormationModel (严格世界坐标与弧长归一化)
  → StorageManager.save_trajectory / save_project
  → 写入 data/trajectories/*.json & data/projects/*.json
  → 事务写入 data/choreo_database.db (六核心表)
```

---

## 3. 架构规范合规性核验 [OBSERVED]

1. **UI 直连 SQL 审查**：全量检索 `src/ui/`，未发现任何 `import sqlite3` 或直接执行 SQL 行为（0 违规）。
2. **多库冲突处置**：旧 `studio_data.db` 演示注入代码已从 `StudioController._init_sqlite()` 彻底移除；全部持久化收敛至 `StorageManager` 与 `data/choreo_database.db`。
3. **循环依赖审查**：Domain 层实体纯粹，无 PySide6/Flask 引用，无循环 import。
