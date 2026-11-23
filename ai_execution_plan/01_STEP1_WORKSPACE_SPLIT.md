# Step 1: 根目录三文件夹物理拆分与路径对齐计划 (01_STEP1_WORKSPACE_SPLIT)

## 1. 阶段目标
将仓库根目录拆分为同级的 `upper_computer/`、`lower_computer/` 与 `ai_execution_plan/`，并确保上位机迁移后所有内部路径解析 (`src/core/paths.py`, `app.py`, `main.py`, `scripts/verify_hygiene.py`) 100% 正常工作。

## 2. 执行清单
1. 创建 `upper_computer/`、`lower_computer/`、`ai_execution_plan/` 三个同级目录。
2. 将原上位机文件完整移入 `upper_computer/`。
3. 将 `下位机ros信息` 与 `群控商业化补充说明.md` 同步保存至 `lower_computer/` 与 `upper_computer/`。
4. 更新 `.gitignore` 以兼容 `upper_computer/` 与 `lower_computer/` 的缓存隔离。

## 3. 验证命令
```powershell
python upper_computer/scripts/verify_hygiene.py
```
