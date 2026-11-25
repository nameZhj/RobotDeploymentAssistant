# 通信协议与实机真实性规范

> 何时阅读：涉及上下位机 HTTP 通信、下位机 UDP `:8899` 运控桥、LoRa 配网、LRMP 或 ROS 桥接时必读。
> 前置文档：[01 仓库结构](01_REPO_MAP_AND_ENTRYPOINTS.md)。
> 要点速览：1) 零假数据铁律，ROS/运控不可达须诚实返回 `ros_available: false` 与 HTTP `503`；2) 仅 Wi-Fi 配网走 LoRa，跨端业务全走 HTTP `:8090`，下位机本机转 UDP `:8899` 驱动 G1；3) 统一单次发送不自动重发动作，急停发 `STOP`。

---

## 1. 真实性铁律（零假数据 / 零 Demo 回调）

- 下位机所有状态、遥测、建图与运控接口 **MUST** 反映宿主机真实 ROS 1.17.4（`roscore`, `/opt/vsis_nav/navctl`, `rostopic`, `rosservice`, `rospy`）与真实运控连通性。
- ROS 不可达时 **MUST** 返回 `ros_available: false` 与 HTTP `503 Service Unavailable`；运控 UDP 桥未启用或 `PING` 超时时，`GET /api/v1/control/probe` **MUST** 返回 HTTP `503`（`reachable: false`），**MUST NOT** 伪造坐标或假回调。

---

## 2. 通道分工与 HTTP/UDP 契约

- **LoRa 仅用于 Wi-Fi 配网**：扫描 AP / 连 SSID / 配静态 IP 通过 LoRa 完成（`g1_wifi_service` / `LoraWifiTunnel` ↔ `LoraWifiAgent`）。
- **跨端全走 Wi-Fi HTTP（Port `8090`）**：`RobotHttpClient` ↔ 下位机 `src/api/routes.py`；上位机 **MUST NOT** 绕过下位机直发 UDP `:8899`。
- **SSH 通道豁免边界（例外清单，显式登记制）**：SSH 仅限两类用途——**Wi-Fi 配网通道**与下列**部署运维通道**；其余业务面一律收敛 Wi-Fi HTTP（Port `8090`）为唯一主通道。下列 SSH 通道为**已登记豁免**（退出条件满足前保持现状运行，满足后 **MUST** 回收至 HTTP 主通道）：
  - **Wi-Fi 配网 SSH 隧道**：`upper_computer/backend/g1_wifi_service.py`（LoRa 串口 + SSH Proxy 执行机载网卡探测、Wi-Fi 扫描、热点连接与静态 IP 配置）；退出条件＝下位机提供配网 HTTP 端点并实机验证后切换。
  - **镜像部署 SSH-only**：`upper_computer/app.py` `/api/images/upload`（经 `ssh_manager` 传包与 `docker load`，无 HTTP 端点）；退出条件＝HTTP 镜像上传/仓库通道实机验证通过后下线 SSH 上传。
  - **HTTP 失败回退 SSH**：`app.py` 中 `/api/license/status`、`/api/machine_id`（优先调用下位机 `GET /api/v1/system/machine_id`，失败回退 `deployment_core.read_machine_id`）、`/api/robot/process*`、`/api/logs`、`/api/dance/update`（调 `dance_updater.deploy_zip_package`）及容器启停（仅无 HTTP 目标或 HTTP 失败时回退 SSH）；退出条件＝对应 HTTP 端点在无 SSH 凭据部署形态下实机验证稳定后移除回退分支。
  - **登记义务**：新增任何 SSH 依赖 **MUST** 先在本清单登记通道、理由与退出条件；未登记即新增视为违反通道分工。
- **下位机本机 UDP 运控桥（Port `8899`）**：`G1UdpMotionBridge` 将 `STAND`/`GAIT`/`PASSIVE`/`STOP`/速度指令/`DANCE,<alias>` 打包为 `TARGET|COMMAND\n`（ASCII、`<= 192` 字节、禁 `|` 与 `GETDANCELIST`）发送至同机 G1 运控接收器，**单次发送绝不自动重发**。
- **连通探测端点**：新增 `GET /api/v1/control/probe`（返回 `200`/`503`、`PING/PONG` RTT 与可达状态）；新增或修改任意端点时 **MUST** 同步客户端、下位机路由与测试。

---

## 3. LRMP 帧规范、控制权与回包协议

- **安全与故障闭环**：`ControlArbiter` 与 `AuthorityStateMachine` 强制 `FREE`/`MANUAL`/`CHOREO` 互斥，越权返回 `409 Conflict`；`SafetyCoordinator` 对 `FAULT,ERROR`/`FAULT,FATAL` 及 `ESTOP`/`FAULT`/`MANUAL_OVERRIDE` 模式执行立即熔断（取消 ROS 规划、清零 `cmd_vel`、中止任务链、锁定仲裁器），待 `FAULT,CLEAR` 且状态脱离异常态后自动解锁；`FAULT,WARN` 仅告警不熔断；`NAV_STATUS,FAILED,LOC_LOST` 快速中止当前导航、不锁手动控制权并触发下位机自动重定位优先三阶段流程（`POST /api/v1/navigation/relocalize`：ROS 服务 → 先验 `/initialpose` → `navctl restart localization` 兜底，未收敛切换上位机 2D 手动设初始位姿）。
- **急停规则**：触发 `EMERGENCY` 时下位机 **MUST** 取消 ROS 规划、清零 `cmd_vel` 并向 UDP 发送 `STOP`（**MUST NOT** 发送 `PASSIVE`）。
- **G1 UDP 完整回包与事件流**：`g1_udp_protocol.py` 与 `G1UdpMotionBridge` 解析 `TARGET|PONG`、`ACK,<CMD>[,<DETAIL>]`、`ERR,<CMD>,<REASON>`、`DANCE_START,<ALIAS>`、`DANCE_DONE,<ALIAS>,<RESULT>[,<REASON>]`、`STATE,<MODE>,<ACTIVE_DANCE>[,<NAV_INPUT>]`（兼容 3/2 参数）、`NAV_STATUS,<STATUS>[,<REASON>]`、`FAULT,<LEVEL>,<CODE>[,<DETAIL>]`（兼容 `FAULT,CLEAR,CLEAR,<CODE>`）；`PROBE` 后同步 `QUERY_STATE`/`QUERY_NAV`；`RX` 线程通过独立队列分发异步事件至 `SafetyCoordinator`，绝不阻塞 `ACK`/`PONG` 接收。
- **Webhook 与 SSE 实时推送**：`TaskChainExecutor` 与 `SafetyCoordinator` 将任务与故障/状态/重定位事件推送至 `WebhookDispatcher`，`RosLiveSlamTap.set_robot_state()` 同步唤醒 `/api/v1/slam/stream` 刷新 UI。

---

## 4. ROS 速率、PCD 资产、Virtual 边界与零 Demo 播种

- 上位机实时刷新频率 **MUST** 跟随 ROS 实际发布频率；保留用户上传 `.pcd` 作为地图资产，优先消费真实机载 ROS 数据。
- `Virtual*` 仿真组件仅用于离线单测（如 `HttpTrajectoryClient` 虚拟回退），**MUST NOT** 冒充真机；`ensure_seeded(db)` **MUST** 默认创建 `0` 轨道、`0` 假动作的空白舞台。

## 自检清单

- [ ] ROS/UDP 不可达时均返回真实 `503` 诊断，无假数据或自动重发动作帧
- [ ] Wi-Fi 配网走 LoRa，跨端业务走 HTTP `:8090`，运控动作经下位机本机 UDP `:8899` 下发
- [ ] `EMERGENCY` 固定发送 `STOP`，任务链兼容有/无 `DANCE_DONE` 回包场景
