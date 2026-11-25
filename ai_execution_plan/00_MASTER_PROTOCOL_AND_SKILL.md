# 双端协同工程主协议与接口契约 (00_MASTER_PROTOCOL_AND_SKILL)

> 通用 AI 开发规范已拆分至 `standards/README.md`，冲突时以 `standards/` 为准。

## 1. 仓库根目录三分区契约

本仓库根目录 (`e:/code/python/RobotDeploymentAssistant`) 固定为三个同级文件夹：

1. `upper_computer/`：上位机工程（Flask 运维后台 + PySide6 舞台编导控制台）。
2. `lower_computer/`：下位机工程（基于真实 ROS 1.17.4 与 LRMP V1.0-R3 的机载 HTTP 服务端、UDP `:8899` 运控桥、ROS 导航桥接、任务链执行器与动作指令集）。
3. `ai_execution_plan/`：通用 AI 规范分册 (`standards/`)、全局符号索引 (`GLOBAL_SYMBOL_INDEX.md`)、闭环门禁 (`verify_deep_closure.py`) 与双端 E2E 测试 (`test_dual_computer_e2e.py`)。

---

## 2. 通用代码定位与硬性门禁概要

1. **检索顺序（禁止盲目全库搜索）**：
   - 定位上位机模块先读 `upper_computer/.agent_workspace/INDEX.md`。
   - 定位下位机模块先读 `lower_computer/.agent_workspace/INDEX.md`。
   - 定位跨端接口先读本文档第 4 节 HTTP 接口契约字典。
2. **单文件 `<= 300` 行硬性门禁**：
   - `upper_computer/src/` 与 `lower_computer/src/` 下所有 `.py` 文件严格不得超过 300 行（建议 250 行拆分）。
   - 每个 `.py` 文件前 5 行必须包含机器可解析契约头（`# @file:`、`# @brief:`、`# @exports:`）。
3. **真实性铁律（零假数据 / 零 Demo 回调）**：
   - 下位机所有接口必须反映真实的 ROS 1.17.4 (`roscore`, `/opt/vsis_nav/navctl`, `rostopic`, `rosservice`, `rospy`) 与真实机载配置 (`lora_recv_group.yaml`, `lora_robot_id.txt`) 状态。
   - 当宿主机未启动 ROS Master 或 `navctl` 不存在时，必须真实返回 `ros_available: false` 与 HTTP `503 Service Unavailable`，**严禁伪造成功回调或虚假坐标**。

---

## 3. 8 层深度闭环标准 (L1–L8)

任何跨端功能必须穿透以下全部 8 层，缺一不可：

- **L1 UI 控件层**：控件可见、文案精简准确、无截断、无死按钮。
- **L2 Signal 信号层**：控件事件绑定到 Page / Panel 控制器槽函数。
- **L3 StateService 服务层**：调用 `StudioStateService` 业务方法并推送 `StudioUndoStack`（如适用）。
- **L4 SQLite 持久化层**：数据变更写入 SQLite 并可跨重启还原。
- **L5 上位机通信层**：
  - 无线 Wi-Fi 配置：通过 LoRa 串口 + SSH Proxy 完成 (`g1_wifi_service` / `LoraWifiTunnel`)。
  - 其它控制与演出业务：全部通过 Wi-Fi HTTP (`RobotHttpClient`) 完成，严禁绕过下位机直发 UDP `:8899`。
- **L6 下位机 HTTP 路由层**：校验 JSON 请求体、控制权状态 (`FREE`/`MANUAL`/`CHOREO`) 并返回标准 HTTP 状态码 (`200`/`202`/`400`/`404`/`409`/`503`)。
- **L7 下位机 ROS/UDP 运控与 Webhook 回调层**：调用真实 `navctl`/ROS 话题服务或经本机 UDP `:8899` (`G1UdpMotionBridge`) 单次下发运控/舞蹈指令（无直接映射时触发 `RESERVED_SLOT`），并在状态变更/到位/故障时向 `callback_url` 发送真实 HTTP POST 回调。
- **L8 上位机回调监听与 EventBus 刷新层**：`HttpCallbackListener` 接收回调并通过 `StudioEventBus` 实时刷新 2D/3D 视口与状态表。

---

## 4. 上下位机标准 HTTP 协议接口契约字典 (Port 8090)

| 序号 | 方法与路径 | 用途 | 成功/失败状态码 | 关键请求字段 | 关键响应/回调字段 |
|---|---|---|---|---|---|
| 1 | `GET /api/v1/health` | 健康、ROS 与 UDP 运控诊断 | `200` | 无 | `robot_id, ros_master_reachable, navctl_available, authority, motion_state, active_faults, safety_locked, motion_udp` |
| 2 | `GET /api/v1/status` | 综合状态（含 `STATUS,*`） | `200` | `?query=ALL\|NET\|ID\|LICENSE\|SHOW` | `authority, details, task_chain, ros_spec` |
| 3 | `GET /api/v1/actions/list` | 获取机载真实动作库 | `200` / `404` | 无 | `groups, total_count, raw` |
| 4 | `POST /api/v1/task_chain/upload` | 上传机器人顺序任务链 | `200` / `400` / `409` | `target_id, plan_id, origin_pose, chain_nodes` | `state (sha256, total_nodes, saved_path)` |
| 5 | `POST /api/v1/task_chain/prep` | 任务链准备并导航至起点 | `202` / `409` / `503` | `run_id, callback_url` | 回调 `TASK_CHAIN_READY`；`state.status="READY"` |
| 6 | `POST /api/v1/task_chain/start` | 启动任务链顺序到点执行 | `202` / `400` / `409` | `run_id, callback_url` | 异步回调 `STEP_STARTED`, `STEP_PROGRESS`, `STEP_COMPLETED`, `CHAIN_COMPLETED`, `TASK_ERROR` |
| 7 | `POST /api/v1/task_chain/barrier` | 放行同步屏障 | `200` / `400` / `409` | `run_id, barrier_id, release_ms` | 回调 `BARRIER_RELEASED` |
| 8 | `POST /api/v1/task_chain/stop` | 停止任务链并导航回原点 | `200` | `origin_pose, callback_url` | 取消当前规划、发送 `STOP` 并回原点；回调 `STOPPED_RETURNING_ORIGIN` |
| 9 | `POST /api/v1/control/command` | 单条 LRMP/UDP 控制指令 | `200` / `409` / `503` | `command, params` | `ok, execution_mode ("REAL"\|"RESERVED_SLOT"\|"REJECTED"\|"UNAVAILABLE"), authority` |
| 10 | `GET/POST /api/v1/control/probe` | 探测 G1 UDP `:8899` 连通并同步状态 | `200` / `503` | `target_id` | `reachable, rtt_ms, state` |
| 11 | `GET /api/v1/control/state` | 查询/同步 UDP 运控状态 | `200` | `?sync=1` | `authority, motion, relocalize_status, motion_udp, task_chain` |
| 12 | `POST /api/v1/control/posture` \| `/velocity` \| `/dance` \| `/stop` | 结构化姿态、速度、舞蹈与急停 (`STOP`) | `200` / `400` / `409` / `503` | `posture`/`vx,vy,vyaw`/`alias`/`emergency` | `ok, execution_mode, authority, details`；中止时回调 `CHAIN_ABORTED` |
| 13 | `POST /api/v1/navigation/navctl` | 执行 `/opt/vsis_nav/navctl` | `200` / `400` / `503` | `action` | `returncode, stdout, stderr, available` |
| 14 | `POST /api/v1/navigation/goal` | 发送 `/move_base_simple/goal` | `202` / `400` / `409` / `503` | `x, y, yaw` | 503 时含 `ros_available: false` |
| 15 | `POST /api/v1/navigation/initialpose` \| `/relocalize` | 发送 `/initialpose` 与自动优先重定位 | `200` / `400` / `503` | `mode ("auto"\|"manual"), x, y, yaw` | `ok, converged, strategy_used, confidence, needs_manual` |
| 16 | `POST /api/v1/navigation/cancel` \| `GET /diagnostics` \| `GET/POST /teb_params` | 取消导航、图诊断与 TEB 参数读写 | `200` / `400` / `503` | `params` | 503 时含 `ros_available: false` |
| 17 | `GET /api/v1/slam/stream` \| `live_state` \| `live_cloud` \| `map.pcd` \| `discovery` \| `maps` \| `POST /map/upload` \| `GET /scan` | SSE 实时流、二进制点云、PCD 上传下载与 ROS 自省 | `200` / `400` / `404` / `503` | `since_seq`, `filename`, `?path=` | `text/event-stream`, `Float32 XYZ` + `X-Cloud-Seq`, `.pcd` |
| 18 | `GET /api/v1/system/*` \| `POST /api/v1/actions/register` \| `POST /api/v1/dance/deploy` \| `GET/POST /api/v1/license/*` \| `POST /api/v1/lora_wifi/command` | 预检、机器码 (`machine_id`)、进程/Docker/日志、ID 配置、授权与动作部署 | `200` / `400` / `404` / `503` | 视端点而定 | 真实宿主机系统与配置状态 |
