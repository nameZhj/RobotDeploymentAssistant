# 数据模型、持久化与迁移测试报告 (Test Results)

> 审计基准: Prompt 04 | 执行环境: Python 3.12, Windows 11

## 1. 测试概览

- **测试套件**: `tests/unit/test_data_models_and_migration.py` 与全量回归套件
- **测试结果**:
  - `test_data_models_and_migration.py`: 7/7 PASSED (100%)
  - 全量回归套件 `pytest tests -q --ignore=docs`: 391/391 PASSED (100%)
  - 端到端及历史契约 `python tests/verify_choreo_e2e.py`: 10/10 PASSED (100%)

---

## 2. 详细用例覆盖矩阵

| 测试用例 | 验证领域 | 判定条件 | 状态 |
| :--- | :--- | :--- | :--- |
| `test_schema_creation_on_empty_db` | 架构建立 | 空库从零创建 12 张核心规范表、启用外键、版本置 2 | ✅ PASSED |
| `test_migration_idempotency` | 迁移引擎 | 连续多次执行迁移脚本无报错且数据无重复插入 | ✅ PASSED |
| `test_migration_rollback_on_error` | 事务一致性 | 语法错误自动回滚事务，版本号不变更，无脏数据残留 | ✅ PASSED |
| `test_domain_entity_validation_finite_coords` | 领域契约 | 拒绝 NaN/Infinity 浮点坐标，保证物理数值有限 | ✅ PASSED |
| `test_domain_entity_units_and_time_checks` | 领域契约 | 校验时间戳 ISO-8601 格式与显式物理单位 | ✅ PASSED |
| `test_foreign_key_reference_protection` | 数据完整性 | PRAGMA foreign_keys 生效，阻止插入孤儿轨迹/外键约束生效 | ✅ PASSED |
| `test_trajectory_import_export_roundtrip_atomic` | 导入导出 | 验证原子写入 (`.tmp_*` 替换) 与 schema_version 校验 | ✅ PASSED |

---

## 3. 验收结论

所有数据模型、持久化、架构迁移、事务回滚与契约用例均无异常，全量测试套件零失败，Prompt 04 数据层工作满足验收标准。
