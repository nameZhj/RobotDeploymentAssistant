# 测试与验证规范

> 何时阅读：变更代码后确定必跑范围、编写高价值测试用例或交付验收时必读。
> 前置文档：[01 仓库结构](01_REPO_MAP_AND_ENTRYPOINTS.md)、[03 Python 编码规范](03_PYTHON_CODING_RULES.md)。
> 要点速览：1) 坚持最小必要验证，按改动域精准跑对应核心测试以节约 Token；2) 严禁编写无意义的样式/getter/纯 Mock 自嗨测试；3) Qt 离屏与本地 HTTP 替身隔离真机，汇报只引用实测结果。

---

## 1. 核心原则：最小必要验证（节约 Token）

- **MUST NOT** 每次改动都盲目执行全量 `run_all_validation.ps1` 或整目录 `pytest`。
- **纯文档 / 注释 / 静态样式与文案微调**（未改动业务逻辑、DOM ID 与测试锁定文本）：**MUST NOT** 运行无关 Python/Qt 测试，仅执行文档格式/链接或语法检查。
- **日常开发与 Bug 修复**：**MUST** 依据下表仅运行受影响域的 `1–2` 个核心测试文件或 `-k` 单用例。
- **全量脚本时机**：`powershell -ExecutionPolicy Bypass -File ai_execution_plan/run_all_validation.ps1` **SHOULD** 仅在跨端协议大改、架构级重构或合并主干/发版前执行一次。

---

## 2. 改动域 → 精准必跑核心测试映射表（保留的 12 个测试文件）

| 改动域 | 核心测试命令 |
|---|---|
| **异步任务 / 跨线程 EventBus / 非阻塞流** | `python -m pytest -q upper_computer/tests/test_background_tasks.py` |
| **Web 控制台 / Flask 安全校验** | `python -m pytest -q upper_computer/tests/test_all_features.py upper_computer/tests/test_robot_id_and_target.py` |
| **SQLite / 领域实体 / UniUni JSON** | `python -m pytest -q upper_computer/tests/test_phase2_persistence.py` |
| **LRMP 协议 / 控制权 / HTTP 客户端** | `python -m pytest -q upper_computer/tests/test_phase3_protocol.py` |
| **数学样条 / 编队避障 / 碰撞计算** | `python -m pytest -q upper_computer/tests/test_phase4_math_algorithms.py` |
| **PCD 解析 / 栅格 / Kabsch SVD** | `python -m pytest -q upper_computer/tests/test_phase11_pcd_and_svd.py` |
| **导航地图 / 建图 / 演出实时监控页** | `python -m pytest -q upper_computer/tests/test_phase11_mapping_monitoring.py` |
| **任务链规范 / 70:30 视口 / 急停回原点** | `python -m pytest -q upper_computer/tests/test_task_chain_and_ui.py` |
| **桌面端核心业务闭环集成** | `python -m pytest -q upper_computer/tests/test_closure_audit_e2e.py` |
| **下位机 ROS 桥接 / 路由 / 任务链** | `python -m pytest -q lower_computer/tests/test_lower_computer.py` |
| **双机 HTTP 联调与跨端大改验收** | `python -m pytest -q ai_execution_plan/test_dual_computer_e2e.py` |
| **单用例精准调试 / 仅查 300 行门禁** | `python -m pytest -q <测试文件> -k <case>` / `python ai_execution_plan/verify_deep_closure.py` |

---

## 3. 测试准入与禁写门槛（辩证取舍）

- **值得写 / MUST 保留的高价值测试**：安全与注入拦截、协议编解码与控制权互斥、数学/避障/SVD 精度不变量、SQLite/JSON 往返持久化、真实 HTTP 跨端闭环、ROS 缺失诚实 `503`、防 OOM/卡死/线程泄漏。
- **严禁写 / 应清理的无效测试**：静态 QSS/CSS 色值或像素宽高、纯 getter/setter、硬编码命令字符串常量复读、全 `MagicMock` 复读内部调用、重复覆盖已有闭环的阶段脚手架、硬编码个人本机路径的测试。
- **按风险补测**：小范围文案与样式微调不强制补测试；确需新增用例时 **SHOULD** 直接追加到上表对应的归属核心测试文件中，**MUST NOT** 随意新建零碎测试文件。

---

## 4. 离屏 Qt、无真机隔离与汇报纪律

- **环境隔离**：涉及 PySide6 的测试 **MUST** 在顶部或 fixture 设置 `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")` 并复用模块级 `QApplication`；所有测试 **MUST** 离线无真机运行，网络/回调验证采用本地 `ThreadingHTTPServer` 替身（参照 `lower_computer/tests/test_lower_computer.py`），结束时清理窗口与弹窗句柄。
- **断言诚信与节约运行**：**MUST NOT** 弱化断言凑绿灯（注意 `test_task_chain_and_ui.py` 依赖 `任务链 4 项`、`test_robot_id_and_target.py` 依赖 `*-error` 容器 ID）；未作新编辑 **MUST NOT** 空转重跑；汇报 **MUST** 原样引用末次编辑后实际观测到的通过条数与输出。

## 自检清单

- [ ] 本轮只运行了改动域映射的核心测试或轻量校验，未无原则浪费 Token 全量重跑
- [ ] 新增用例聚焦协议/安全/算法/持久/闭环，未写纯样式或全 Mock 形式主义测试
- [ ] 最终汇报中引用的测试结果均为末次编辑后亲眼观测到的真实输出
