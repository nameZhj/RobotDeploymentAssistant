# 自动化测试矩阵与执行记录

> 最后更新：2026-11-12

---

## 1. 测试套件执行结果表

| 序号 | 测试套件 / 目标 | 触发命令 | 执行范围 | 退出码 | 结果 (Pass/Fail/Skip) | 未运行/跳过原因 |
|---|---|---|---|---|---|---|
| **T01** | 全量测试套件 (包含单元、契约、外壳、数据模型与地图管道) | `pytest tests -q --ignore=docs` | 全工程所有测试 (397 个用例) | 0 | **397 PASSED** | 无 |
| **T02** | 2026-10-01 前历史功能兼容性契约套件 | `pytest tests/compatibility -v` | 8 大兼容性契约模块 (20 个用例) | 0 | **20 PASSED** | 无 |
| **T03** | UI 外壳与控件事件映射套件 | `pytest tests/unit/test_ui_shell_controls.py -v` | Splitter、快捷键与离线渲染 (4 个用例) | 0 | **4 PASSED** | 无 |
| **T04** | 舞台编导 Facade 用例与生命周期套件 | `pytest tests/unit/test_studio_facade_use_cases.py -v` | 9 项用例接口与 Composition Root (4 个用例) | 0 | **4 PASSED** | 无 |
| **T05** | 全流程端到端与历史契约 | `python tests/verify_choreo_e2e.py` | 10 项端到端流程 | 0 | **10 PASSED** | 无 |
| **T06** | 主页入口与窗口生命周期 | `pytest tests/unit/test_task04c_d0_r_home_choreo_routing.py -v` | 主页路由与 Qt 启动 | 0 | **10 PASSED** | 无 |
| **T07** | 核心特性套件 (轨迹/阵型/时间轴) | `pytest tests/unit/test_feature_choreo_suite.py -v` | 核心算法与数据管道 | 0 | **6 PASSED** | 无 |
| **T08** | 数据模型、SQLite持久化与迁移套件 | `pytest tests/unit/test_data_models_and_migration.py -v` | 迁移引擎、外键、领域强校验 (7 个用例) | 0 | **7 PASSED** | 无 |
| **T09** | 地图管理与 PCD 导入渲染管道套件 | `pytest tests/unit/test_map_management_and_pcd_pipeline.py -v` | ASCII/Binary、路径安全、防重与活跃保护 (6 个用例) | 0 | **6 PASSED** | 无 |
| **T08** | 真实真机硬件通信与物理执行 | 无 | 真机硬件与现场设备 | N/A | **NOT RUN** | 当前处于离线/无真机接入的开发环境 |
| **T09** | 物理仿真动力学碰撞评测 | 无 | Gazebo/MuJoCo 物理引擎 | N/A | **NOT RUN** | 舞台编导使用运动学预演，暂未引入动力学仿真 |
