# Hydrogen High 纯 AI 编程主协议与防遗忘工程规范 (00_MASTER_PROTOCOL_AND_SKILL)

## 1. 仓库根目录三分区契约

本仓库根目录 (`e:/code/python/RobotDeploymentAssistant`) 严格固定为三个同级文件夹：

1. `upper_computer/`：上位机工程（Flask 运维后台 + PySide6 舞台编导控制台）。
2. `lower_computer/`：下位机工程（基于 `下位机ros信息` 与 `LRMP V1.0-R3` 的机载 HTTP 服务端、ROS 导航桥接、任务链执行器与动作指令集）。
3. `ai_execution_plan/`：面向 **Hydrogen High** 模型的分步执行计划、`STATE_CHECKLIST.json` 防遗忘状态机、全局符号索引与自动化闭环验证脚本。

---

## 2. Hydrogen High 极速省 Token 代码定位与编码规范

1. **禁止盲目全库搜索**：
   - 定位上位机模块先读 `upper_computer/.agent_workspace/INDEX.md`。
   - 定位下位机模块先读 `lower_computer/.agent_workspace/INDEX.md`。
   - 定位跨端接口先读本文档第 4 节 HTTP 接口契约字典。
2. **单文件 `<= 300` 行硬性门禁**：
   - `upper_computer/src/` 与 `lower_computer/src/` 下所有 `.py` 文件严格不得超过 300 行（建议 250 行拆分）。
   - 每个 `.py` 文件前 5 行必须包含机器可解析契约头：
     ```python
     # @file: <相对于项目根的路径.py>
     # @brief: <单句模块职责>
     # @exports: <公开导出的类或函数列表>
     ```
3. **真实性铁律（零假数据 / 零 Demo 回调）**：
   - 下位机所有接口必须反映真实的 ROS 1.17.4 (`roscore`, `/opt/vsis_nav/navctl`, `rostopic`, `rosservice`, `rospy`) 与真实机载配置 (`lora_recv_group.yaml`, `lora_robot_id.txt`) 状态。
   - 当宿主机未启动 ROS Master 或 `navctl` 不存在时，必须真实返回 `ros_available: false` 与 HTTP `503 Service Unavailable`（或明确的真实诊断原因），**严禁生成随机数坐标或伪造虚假成功回调**。

---

## 3. 防遗忘 8 层深度闭环标准 (8-Layer Deep Closure Standard)

任何功能点必须穿透以下全部 8 层，缺一不可：

- **L1 UI 控件层**：控件可见、文案准确、无截断、无 `lambda: None`。
- **L2 Signal 信号层**：控件事件绑定到 Page / Panel 控制器槽函数。
- **L3 StateService 服务层**：调用 `StudioStateService` 业务方法并推送 `StudioUndoStack`（如适用）。
- **L4 SQLite 持久化层**：数据变更写入 SQLite 并可跨重启还原。
- **L5 上位机通信层**：
  - 无线 Wi-Fi 配置：**仅通过 LoRa 串口通道**完成 (`G1WifiService` / `G1WifiProvisioner`)。
  - 其它所有功能：**全部通过无线 Wi-Fi 的 HTTP 协议** (`RobotHttpClient`) 完成。
- **L6 下位机 HTTP 路由层**：校验 JSON 请求体、控制权状态 (`FREE`/`MANUAL`/`CHOREO`) 并返回标准 HTTP 状态码 (`200`/`202`/`400`/`404`/`409`/`503`)。
- **L7 下位机 ROS/运控执行与 Webhook 回调层**：调用真实 `navctl`/ROS 话题服务或运控指令集（未开放直调的复杂舞蹈触发 `RESERVED_SLOT` 预留槽位），并在状态变更/到达目标点时主动向 `callback_url` 发送真实 HTTP POST 回调。
- **L8 上位机回调监听与 EventBus 刷新层**：`HttpCallbackListener` 接收回调并通过 `StudioEventBus` 实时刷新 2D/3D 视口与状态表。

---

## 4. 上下位机标准 HTTP 协议接口契约字典 (Port 8090)

| 序号 | 方法与路径 | 用途 | 成功状态码 | 关键请求字段 | 关键响应/回调字段 |
|---|---|---|---|---|---|
| 1 | `GET /api/v1/health` | 健康与 ROS 环境诊断 | `200` | 无 | `robot_id, ros_available, navctl_available` |
| 2 | `GET /api/v1/status` | 综合状态（含 `STATUS,*`） | `200` | `?query=ALL\|NET\|ID\|LICENSE\|SHOW` | `authority, pose, localization_confidence, delay_ms, nav_status, task_chain` |
| 3 | `GET /api/v1/actions/list` | 获取机载真实动作库 | `200` | 无 | `groups, total_count, raw` |
| 4 | `POST /api/v1/task_chain/upload` | 上传机器人顺序任务链 | `200` | `target_id, plan_id, origin_pose, chain_nodes` | `sha256, node_count, saved_path` |
| 5 | `POST /api/v1/task_chain/prep` | 任务链准备并导航至起点 | `202` / `503` | `plan_id, run_id, callback_url` | `state="PREPARING"\|"READY", authority="CHOREO"` |
| 6 | `POST /api/v1/task_chain/start` | 启动任务链顺序到点执行 | `202` / `409` | `run_id, callback_url` | 异步回调 `STEP_STARTED`, `STEP_PROGRESS`, `STEP_COMPLETED`, `CHAIN_COMPLETED` |
| 7 | `POST /api/v1/task_chain/stop` | **停止任务链并导航回原点** | `200` | `return_to_origin=true, origin_pose, callback_url` | 取消当前规划并发布 `/move_base_simple/goal` 回原点 |
| 8 | `POST /api/v1/control/command` | 单条已知运控/舞蹈指令 | `200` / `409` | `target_id, command, params` | `executed, execution_mode ("REAL"\|"RESERVED_SLOT"), authority` |
| 9 | `POST /api/v1/navigation/navctl` | 执行 `/opt/vsis_nav/navctl` | `200` / `503` | `action ("status"\|"start localization"\|"start mapping"\|"finish-mapping"\|"stop")` | `returncode, stdout, stderr, mode` |
| 10 | `POST /api/v1/navigation/goal` | 发送 `/move_base_simple/goal` | `202` / `503` | `x, y, yaw, frame_id="map", callback_url` | 真实监控 `/local_nav_status` 与 `/Odometry_loc` 回调到达 |
| 11 | `POST /api/v1/navigation/initialpose` | 发送 `/initialpose` | `200` / `503` | `x, y, yaw` | `published` |
| 12 | `POST /api/v1/navigation/cancel` | 调用 `/teb_polar_node/cancel_planning` | `200` / `503` | 无 | `cancelled` |
| 13 | `GET /api/v1/slam/map.pcd` | 下载真实建图生成的 PCD 文件 | `200` / `404` | `?path=` | `application/octet-stream` (`.pcd`) |
