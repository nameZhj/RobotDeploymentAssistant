# Step 3: 下位机任务链执行引擎、真实 Webhook 回调与 HTTP 服务端计划 (03_STEP3_LOWER_HTTP_AND_TASK_CHAIN)

## 1. 阶段目标
实现下位机顺序任务链执行器 (`TaskChainExecutor`)、“停止即回到原点”导航逻辑、真实 HTTP Webhook 回调发送器 (`WebhookCallbackDispatcher`) 以及符合 HTTP 标准规范的 REST 服务端。

## 2. 必建模块清单
1. `lower_computer/src/task_chain/__init__.py` & `lower_computer/src/task_chain/webhook_dispatcher.py`：
   - 向上位机 `callback_url` 发送标准 JSON 事件回调（`STEP_STARTED`, `STEP_PROGRESS`, `STEP_COMPLETED`, `CHAIN_COMPLETED`, `STOPPED_RETURNING_ORIGIN`, `RETURNED_TO_ORIGIN`, `TASK_ERROR`）。
   - 记录每一次真实 HTTP 回调的响应状态码与耗时，绝不伪造回调。
2. `lower_computer/src/task_chain/task_chain_executor.py`：
   - 管理上传的任务链方案 (`upload_chain`)、准备并导航回起点 (`prep_chain`)、按节点顺序执行 (`start_chain`)、停止并导航回原点 (`stop_and_return_origin`)。
   - **核心任务链到点触发逻辑**：
     - 当节点为 `trajectory`（如“导航到点1”）：发布目标点 `(target_x, target_y, target_yaw)` 至 `/move_base_simple/goal`，循环采样真实 ROS 位姿 `/Odometry_loc` 与 `/local_nav_status`，只有当机器人真实到达目标点（位置误差 `<= arrival_xy_tol` 且状态就绪）后，才推进到下一节点（如“太极”或“导航到点2”）。
     - 当收到 `stop` 指令时：立即中止当前任务链，调用 `/teb_polar_node/cancel_planning`，执行 `STOP`，并立即向 `/move_base_simple/goal` 发送初始原点 `(origin_x, origin_y, origin_yaw)` 触发回原点导航。
3. `lower_computer/src/api/__init__.py`, `lower_computer/src/api/routes.py`, `lower_computer/src/api/http_server.py` & `lower_computer/main.py`：
   - 提供标准 HTTP REST 接口（支持多线程并发请求处理、标准 HTTP 状态码 `200`/`202`/`400`/`404`/`409`/`503`）。
