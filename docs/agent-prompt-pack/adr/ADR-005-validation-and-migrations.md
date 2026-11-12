# ADR-005: 领域模型数据校验、版本契约与安全迁移策略

- **状态**：APPROVED
- **日期**：2026-11-12
- **决策者**：RobotDeploymentAssistant 核心工程组

## 1. 背景与问题
地图、轨迹、阵型与工程数据必须保证跨版本稳定性，杜绝 `NaN`、`Infinity` 或未定义字段导致运行崩溃。

## 2. 候选方案评估
- **方案 A（引入 Pydantic V2）**：劣势：增加编译依赖，对当前轻量脚本模式有一定性能损耗。
- **方案 B（标准库 dataclasses + 显式业务 Validator，推荐）**：优势：零外部依赖，严格执行强类型与守卫断言（Guard Clauses），明确 `schema_version`。

## 3. 决策内容
1. 采用 `dataclass` 定义领域模型（`TrajectoryModel`、`FormationModel`、`ProjectChoreoModel`）。
2. 反序列化统一执行：`parse -> validate -> normalize -> persist` 管道。
3. 坐标数值严格拒绝 `NaN` / `Inf`，未知状态统一使用 `None` / `UNKNOWN`，严禁伪造默认值 `0.0`。
4. 数据库演进采用 `PRAGMA user_version` 与前置只读备份机制。

## 4. 后果与回滚计划
- **积极影响**：数据安全性达到工业级标准，无隐式类型漂移。
- **回滚方案**：保持数据模型 `to_dict` / `from_dict` 双向序列化契约，确保向后兼容。
