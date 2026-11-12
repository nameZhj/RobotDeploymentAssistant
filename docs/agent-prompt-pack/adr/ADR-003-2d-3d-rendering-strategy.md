# ADR-003: 2D 舞台平面与 3D 虚拟视口渲染技术路线

- **状态**：APPROVED
- **日期**：2026-11-12
- **决策者**：RobotDeploymentAssistant 核心工程组

## 1. 背景与问题
舞台编导需要 2D 平面样条拟合与控制点交互，同时需要 3D 多机骨骼姿态、点云底图与相机漫游。参考软件 UniUni 采用 Konva (2D) + Three.js (3D) 的 Web 栈。

## 2. 候选方案评估
- **方案 A（嵌入 QWebEngineView + Three.js）**：劣势：内存暴增 200MB+，进程间通信时序延迟高，在工控机或轻量笔记本上极易卡顿。
- **方案 B（QGraphicsScene 2D + Qt OpenGL 3D）**：中立：Qt 原生但样条平滑插值和拖拽变换逻辑较重。
- **方案 C（自绘 StageCanvas2D + StageViewport3D，推荐）**：优势：复用现有已验证的向心样条算法与 URDF 正向运动学，帧率稳定在 30–60 FPS，内存开销 < 50MB。

## 3. 决策内容
1. 2D 视口沿用 `StageCanvas2D`（基于 `QWidget + QPainter`），提供向心 Catmull-Rom 样条拟合与控制点拖拽编辑。
2. 3D 视口沿用 `StageViewport3D` 与 `RobotAvatar3DPainter`，复用本地 G1 URDF/STL 刚体网格。
3. 2D/3D 共享唯一的世界坐标系与弧长插值时间时钟。

## 4. 后果与回滚计划
- **积极影响**：性能轻量，零新增 Web 运行时开销，完全在 Qt 主窗口原生运行。
- **回滚方案**：保持视口接口稳定，后续阶段可无缝插拔或优化渲染底层。
