# ADR-004: PCD 地图点云解析、降采样与占据栅格生成策略

- **状态**：APPROVED
- **日期**：2026-11-12
- **决策者**：RobotDeploymentAssistant 核心工程组

## 1. 背景与问题
舞台场景通常导入激光雷达 PCD 地图（包含数十万至数百万点），需进行边界包围盒计算、2D 占据栅格投射及 3D 视口轻量渲染。

## 2. 候选方案评估
- **方案 A（引入 Open3D / PCL 绑定）**：劣势：安装包体积激增 150MB+，且 Windows Python 3.12 wheel 依赖编译环境，存在分发风险。
- **方案 B（纯 Python + NumPy 高性能流式解析，推荐）**：优势：基于 `src/core/pcd_loader.py`，支持 ASCII 与 Binary 格式解析，结合步长体素抽稀与 2D 栅格投射，解析速度在 1 秒以内，零额外 C++ 扩展。

## 3. 决策内容
1. 采用 `PcdLoader` 作为核心 PCD 点云解析器，支持标准 ASCII 与 Binary 格式。
2. 采用 `MapGridProcessor` 生成 2D 占据栅格并膨胀障碍物。
3. 耗时解析与栅格化全部放置于 `StageMapImportWorker` 后台 QThread 中执行，禁止阻塞 Qt 主线程。

## 4. 后果与回滚计划
- **积极影响**：依赖极轻（仅依赖 NumPy），启动迅速，分发体积可控。
- **回滚方案**：`PcdLoader` 数据结构输出标准 NumPy ndarray，便于未来无缝对接高级点云滤波算法。
