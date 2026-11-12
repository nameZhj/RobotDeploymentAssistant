# Prompt 00 基线与清理验证测试报告

> 执行时间：2026-11-12  
> 环境：Windows 11, Python 3.12.0, PySide6 6.12.0, Flask 3.1.3, pytest 9.1.1

---

## 1. 测试套件汇总

| 测试类别 | 命令 | 测试数量 | 结果 | 耗时 |
|---|---|---|---|---|
| **全量单元与集成测试** | `pytest tests/unit -q` | 356 | **356 PASSED (100%)** | 11.22s |
| **端到端流程与历史契约** | `python tests/verify_choreo_e2e.py` | 10 核心项 | **10 PASSED (100%)** | 1.85s |
| **主页与窗口路由生命周期** | `pytest tests/unit/test_task04c_d0_r_home_choreo_routing.py -v` | 10 | **10 PASSED (100%)** | 1.18s |
| **2026-10-01 前历史兼容性** | `pytest tests/unit/test_legacy_pre_2026_10_01_contracts.py -v` | 6 | **6 PASSED (100%)** | 0.45s |
| **核心特性集成验证** | `pytest tests/unit/test_feature_choreo_suite.py -v` | 6 | **6 PASSED (100%)** | 0.38s |

---

## 2. 关键验收项验证结果

### 2.1 真实入口与生命周期 (Prompt 00 I1)
- [x] 主页按钮 `btn-open-studio-window` 正常渲染且样式符合蓝紫渐变规范。
- [x] `POST /api/system/open-studio` 正确触发并返回状态。
- [x] 打开窗口为标准 `MainStudioWindow`。
- [x] 历史错误页面 `StudioMainWindow`、`page_monitor`、`page_map` 均未加载。
- [x] 连续点击 3 次复用单例窗口，不重复创建多个实例。
- [x] 关闭后再次唤起正常响应，无二次打开崩溃与内存悬空。

### 2.2 演示数据与伪造状态消除 (Prompt 00 I2)
- [x] 新建工程初始化时不自动注入 POPPING1/2/3、中华武术等硬编码动作。
- [x] 画布未连接设备时不生成固定 `(-2, 0) / (2, 0)` 虚假机器人点位。
- [x] 顶栏与底栏移除写死之 IP (`172.18.0.1`) 与假在线设备数字 (`在线 2`)。
- [x] 时间轴移除虚构障碍物 `BARRIER_9001` 与固定默认片段。

### 2.3 信号接线与持久化安全 (Prompt 00 I3 & I4)
- [x] 移除 `lambda: None` 伪按钮处理器，所有可见按钮均有对应 slot。
- [x] 移除重复 `clicked` / `toggled` 双重连接。
- [x] 保存按钮连接至原子事务与 LRMP 编译器，无伪造成功弹窗。
- [x] SQLite schema 冲突彻底解决，统一由 `storage_manager` 操作 `choreo_database.db`。
