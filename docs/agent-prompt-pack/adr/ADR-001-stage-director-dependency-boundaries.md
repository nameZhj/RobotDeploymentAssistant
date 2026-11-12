# ADR-001: 舞台编导依赖边界与分层架构规范

- **状态**：APPROVED
- **日期**：2026-11-12
- **决策者**：RobotDeploymentAssistant 核心工程组

## 1. 背景与问题
舞台编导桌面窗口过去存在 UI 控件直接连接数据库、硬编码假数据和跨层调用的情况，导致业务逻辑与界面高度耦合，且测试难以隔离硬件。

## 2. 候选方案评估
- **方案 A（维持现状）**：控件内部自行管理存储与状态。劣势：数据多份、测试困难、容易崩溃。
- **方案 B（迁移 Electron/Vue）**：模仿 UniUni 界面。劣势：技术栈断层，原 Python+Qt 算法与 URDF 模型无法复用，改造成本不可控。
- **方案 C（Clean Architecture 分层架构，推荐）**：严格定义 UI -> Application -> Domain -> Infrastructure 单向依赖，通过 `StudioFacade` 提供统一 Use Case 接口。

## 3. 决策内容
采用方案 C。确立四层架构：
1. **UI 层**（PySide6）：负责用户交互渲染，不写 SQL，不直连硬件。
2. **Application 层**（`StudioFacade`、`StudioDependencies`）：业务用例编排与跨子系统协调。
3. **Domain 层**（Entities、Calculators、Compilers）：纯数学、几何与协议逻辑，无框架依赖。
4. **Infrastructure 层**（`StorageManager`、Serial、SSH）：设备与持久化适配器。

## 4. 后果与回滚计划
- **积极影响**：业务层可实现 100% 离线单元测试，UI 无状态污染。
- **回滚方案**：如有适配异常，可通过 `docs/agent-prompt-pack/audit/01-compatibility/backup/` 恢复原始补丁。
