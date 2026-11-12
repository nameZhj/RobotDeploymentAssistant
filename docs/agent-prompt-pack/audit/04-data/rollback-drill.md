# 数据库恢复与回滚演练记录 (Database Rollback & Recovery Drill)

> 演练时间: 2026-11-12 | 依据: Prompt 04 | 目标: 验证 MigrationEngine 事务原子性与故障回滚机制

## 1. 演练目标与场景

验证 `MigrationEngine` 在以下异常情况下的韧性：
1. **中途异常回滚**：迁移脚本抛出未捕获异常或 SQL 语法错误时，数据库是否自动回滚并保持事务一致性；
2. **版本号隔离**：失败的迁移不得更新 `schema_migrations` 表与 `PRAGMA user_version`；
3. **安全恢复**：修复异常后再次执行迁移，可继续平滑升级至目标版本。

---

## 2. 演练执行过程

### 步骤 1: 构造故障迁移注入
- 构造破坏性测试用例 `test_migration_rollback_on_error`：
  - 注册前置有效迁移 `m0001` 与故障迁移 `m0002_broken`（包含无效 SQL 语法 `CRASH TABLE broken`）。
  - 执行 `MigrationEngine.apply_all()`。

### 步骤 2: 观察回滚行为
- `MigrationEngine` 捕获 `sqlite3.OperationalError: near "CRASH": syntax error`。
- 执行 `conn.rollback()`。
- 检查 `schema_migrations`：仅包含已成功提交的 `m0001`，无 `m0002_broken` 痕迹。
- 检查 `PRAGMA user_version`：维持在版本 1，未前进至版本 2。
- 检查表清单：未遗留任何垃圾临时表。

### 步骤 3: 恢复重试
- 使用合法的 `m0002_legacy_choreo_migration` 重新执行 `MigrationEngine.apply_all()`。
- 迁移成功完成，`PRAGMA user_version` 成功晋升至版本 2。

---

## 3. 演练结论

| 评估项 | 预期行为 | 实际观测 | 结论 |
| :--- | :--- | :--- | :--- |
| 异常中断 | 抛出错误并触发事务回滚 | `sqlite3.OperationalError` 捕获并回滚 | ✅ 通过 |
| 版本脏写防护 | 失败脚本不写入记录 | `schema_migrations` 仅存合规版本 | ✅ 通过 |
| 数据库一致性 | 回滚后无孤儿表或损坏索引 | 数据表结构完好，无残留脏结构 | ✅ 通过 |
| 幂等重试 | 修复后重复运行平滑恢复 | 再次执行无冲突，顺利完成晋级 | ✅ 通过 |

**状态**: 恢复与回滚能力演练通过，符合 Prompt 04 生产就绪要求。
