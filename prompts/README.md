# 舞台编导 Agent 工程执行包

适用项目：`E:\code\python\RobotDeploymentAssistant`；适用 Gemini / Antigravity 等具备本地终端和源码读写能力的 Agent。

## 文件
- `MASTER_PROMPT.md`：完整总控任务书，建议整篇一次交给 Agent。
- `.agent/skills/stage-director-delivery/SKILL.md`：项目级 Skill。
- `EXECUTION_PLAN.md`：按完整业务闭环安排阶段。
- `ACCEPTANCE_MATRIX.md`：功能、持久化、UI 和历史回归验收表。
- `AUDIT_FINDINGS_TO_VERIFY.md`：05A～05C 旧审计线索，全部需要重新验证。
- `HANDOVER_TEMPLATE.md`：最终交付报告模板。

## 使用
1. 将 `.agent/skills/stage-director-delivery/` 放入项目约定的 Skill 目录；若项目已有不同目录约定，遵循现有约定，不要建立冲突结构。
2. 在 Agent 中打开项目根目录。
3. 将 `MASTER_PROMPT.md` 全文作为一次完整任务发送，并要求遵循 Skill。
4. 允许 Agent 跨 UI、Controller、Service、Domain、Repository、数据库和启动入口修改，按完整业务模块推进，不按函数逐个审批。
5. 只有真实运行、真实交互、真实持久化、重启恢复和历史功能回归都有证据，才可标记完成。

## 最重要的保护规则
用户允许修改任意源代码，包括 `main.py`、`app.py`、Web 入口和既有模块；必须保护 Git 历史中 **2026-10-01 00:00（Asia/Taipei）之前**已经正确实现的功能行为。保护的是旧功能能力，不是旧文件或旧实现形式。

禁止 `git reset --hard`、`git clean`、`git checkout`、`git restore`、`git stash` 等可能丢弃用户工作的操作。不得覆盖用户未提交修改，不得将整个工作树回滚到旧提交。
