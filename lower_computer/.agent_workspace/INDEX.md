# lower_computer Module Index (Auto-Generated for Hydrogen High)

Format: `path | brief | exported_symbols`

src/__init__.py | Lower computer package root for ROS 1.17.4 navigation bridge, LRMP command executor, task chain engine, and HTTP server. | __version__
src/api/__init__.py | Exports for lower computer standard HTTP REST router and threaded server. | LowerComputerContext, dispatch_http_request, LowerComputerHttpServer
src/api/http_server.py | Standard HTTP/1.1 multi-threaded REST server hosting lower computer routes. | LowerComputerHttpServer
src/api/routes.py | Standard HTTP REST route dispatcher for lower computer ROS navigation, task chain, motion, and system ops. | LowerComputerContext, dispatch_http_request
src/api/system_routes.py | Sub-router handling /api/v1/system/*, /api/v1/license/*, /api/v1/dance/*, and /api/v1/lora_wifi/* routes. | dispatch_system_route
src/commands/__init__.py | Exports for lower computer LRMP V1.0-R3 control arbiter, motion executor, system ops, and LoRa Wi-Fi agent. | ControlAuthority, ArbiterDecision, ControlArbiter, CommandExecutionResult, MotionCommandExecutor, SystemOpsService, LoraWifiAgent
src/commands/control_arbiter.py | Enforces LRMP V1.0-R3 FREE/MANUAL/CHOREO authority mutual exclusion and timeout safety. | ControlAuthority, ArbiterDecision, ControlArbiter
src/commands/lora_serial_daemon.py | Onboard LoRa serial listener receiving TARGET|WIFI_* provisioning frames and replying with WIFI_ACK JSON. | LoraSerialWifiDaemon
src/commands/lora_wifi_agent.py | Lower-computer LoRa serial Wi-Fi provisioning receiver executing authentic nmcli probe/scan/connect/IPv4 commands. | LoraWifiAgent
src/commands/motion_command_executor.py | Implements known G1 LRMP/ROS commands and reserves structured extension slots for unexposed dances. | CommandExecutionResult, MotionCommandExecutor
src/commands/system_ops_service.py | Onboard system service for machine ID, license deployment, dance package hot-update, processes, and logs. | SystemOpsService
src/config/__init__.py | Exports for lower computer ROS environment constants and onboard configuration readers. | ROS_COMPONENTS, ROS_LAUNCH_COMMANDS, NAVCTL_BIN, NAVCTL_ACTIONS, ROS_TOPICS, ROS_SERVICES, RosEnvConfig, RobotConfigReader
src/config/robot_config_reader.py | Reads authentic onboard robot_id, lora_recv_group.yaml dance_map, license, and hardware machine ID. | RobotConfigReader
src/config/ros_env_config.py | Authoritative ROS 1.17.4, navctl, topic/service, and G1 deploy path definitions from 下位机ros信息. | ROS_COMPONENTS, ROS_LAUNCH_COMMANDS, NAVCTL_BIN, NAVCTL_ACTIONS, ROS_TOPICS, ROS_SERVICES, RosEnvConfig
src/ros_bridge/__init__.py | Exports for real ROS 1.17.4 navctl runner, topic/service/TF bridge, and ROS diagnostics inspector. | NavctlRunner, NavctlResult, RosTopicServiceBridge, RosTelemetrySnapshot, RosNavDiagnostics
src/ros_bridge/navctl_runner.py | Executes real /opt/vsis_nav/navctl commands and parses authentic process output. | NavctlResult, NavctlRunner
src/ros_bridge/ros_nav_diagnostics.py | Deep ROS 1.17.4 graph, topic rate, TF map->base_link, global path, and TEB parameter inspector. | RosNavDiagnostics
src/ros_bridge/ros_topic_service_bridge.py | Authentic ROS 1.17.4 topic/TF/service bridge without synthetic or demo telemetry. | RosTelemetrySnapshot, RosTopicServiceBridge
src/task_chain/__init__.py | Exports for lower computer sequential task chain executor and real HTTP webhook callback dispatcher. | CallbackReceipt, WebhookDispatcher, TaskChainState, TaskChainExecutor
src/task_chain/task_chain_executor.py | Arrival-driven sequential task chain executor with BARRIER gates, ROS pose telemetry, and return-to-origin tracking. | TaskChainState, TaskChainExecutor
src/task_chain/webhook_dispatcher.py | Sends authentic HTTP POST JSON callbacks to upper computer without synthetic or fake success. | CallbackReceipt, WebhookDispatcher
