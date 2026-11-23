# Step 4: 上位机 LoRa 无线配网与全功能 Wi-Fi HTTP 化改造计划 (04_STEP4_UPPER_LORA_WIFI_AND_HTTP)

## 1. 阶段目标
满足需求一.1：**“当前配置无线功能是通过lora完成。其它所有功能都通过无线wifi的http协议完成。”**

## 2. 精确修改文件清单
1. `upper_computer/backend/g1_wifi_service.py` & `upper_computer/src/services/g1_wifi_provisioner.py`：
   - 无线配网功能 (`probe_network`, `scan_wifi`, `connect_wifi`, `configure_ipv4`) 绑定 LoRa 串口通道（支持选择/自动连接本机 CH340/CH341 LoRa 串口 `COMx`、波特率、LoRa SSH Proxy / LoRa 配网帧，严格对应 `docs/g1_wifi_setup(1).py`）。
2. `upper_computer/src/ui/network/wifi_wizard_panel.py` & `upper_computer/web/components/ops_tabs/tab_network.html`：
   - 配网面板显示 LoRa 串口选择、刷新串口、连接 LoRa 配网通道，并通过 LoRa 完成探测、扫网、连 Wi-Fi、设置静态 IPv4 并同步到机器人轨道的无线 HTTP IP。
3. `upper_computer/src/protocol/robot_http_client.py` & `upper_computer/src/protocol/http_callback_listener.py`：
   - 新增全功能无线 Wi-Fi HTTP 客户端 (`RobotHttpClient`) 与本地 Webhook 回调监听服务 (`HttpCallbackListener`)。
   - 覆盖动作库获取 (`/api/v1/actions/list`)、任务链上传 (`/api/v1/task_chain/upload`)、任务链准备 (`/api/v1/task_chain/prep`)、任务链启动 (`/api/v1/task_chain/start`)、任务链停止回原点 (`/api/v1/task_chain/stop`)、单步运控指令 (`/api/v1/control/command`)、ROS 导航管理 (`/api/v1/navigation/navctl`, `/goal`, `/initialpose`, `/cancel`)、状态查询 (`/api/v1/status`) 及 SLAM PCD 地图拉取 (`/api/v1/slam/map.pcd`)。
4. `upper_computer/src/services/studio_state_service.py`, `upper_computer/src/services/studio_state_ops.py`, `upper_computer/src/protocol/slam_mapping_client.py`, `upper_computer/src/ui/monitoring/performance_monitor_page.py`, `upper_computer/src/ui/choreography/action_lib_panel.py`：
   - 将动作库同步、舞台编导下发与控制、遥控建图、演出控制台（PREP/BARRIER/PLAY/STOP/EMERGENCY）与雷达状态遥测全部切换为调用无线 Wi-Fi HTTP 接口，并接收下位机真实 HTTP 回调。
