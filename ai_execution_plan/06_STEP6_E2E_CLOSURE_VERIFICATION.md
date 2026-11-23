# Step 6: 8 层深度闭环审计与上下位机端到端联调验收计划 (06_STEP6_E2E_CLOSURE_VERIFICATION)

## 1. 阶段目标
通过自动化脚本 `ai_execution_plan/verify_deep_closure.py` 与双端 E2E 测试套件 `ai_execution_plan/test_dual_computer_e2e.py`，验证上下位机所有功能 100% 深度闭环，无任何遗漏、无假数据回调、无超长文件。

## 2. 必验闭环项
1. **代码卫生门禁**：`upper_computer/src` 与 `lower_computer/src` 所有 `.py` 文件 `<= 300` 行，具备 `@file`/`@brief`/`@exports` 头，且双端 `.agent_workspace/INDEX.md` 自动同步。
2. **LoRa 配网 + 全 Wi-Fi HTTP 闭环**：
   - 验证无线配网走 LoRa 串口通道 (`G1WifiService` / `WifiWizardPanel`)。
   - 验证动作库同步、任务链上传/准备/启动/停止回原点、单指令控制、SLAM 建图与导航控制全部走 Wi-Fi HTTP 接口。
3. **任务链 (Task Chain) 呈现与执行闭环**：
   - 验证 UI 块标签格式为纯名称链 `"导航到点1" - "太极" - "街舞" - "导航到点2"`（不含 `s` 秒数，不含 `步骤#`）。
   - 验证下位机 `TaskChainExecutor` 在导航节点未到达目标点前绝不提前触发下一动作，真实到达目标点后立即触发下一动作并通过 Webhook 真实回调上位机。
4. **70:30 视口比例与停止即回原点闭环**：
   - 验证 `ChoreographyPage` 垂直分割器比例为 `70% : 30%` (`7:3`)。
   - 验证点击浮动播放栏或顶栏“停止”按钮后，上位机 2D/3D 机器人立即回到 `(init_x, init_y, init_yaw)` 原点，且下位机取消当前规划并向 `/move_base_simple/goal` 发送回原点导航目标。
