# Step 2: 下位机 ROS 1.17.4 导航桥接与运控指令核心开发计划 (02_STEP2_LOWER_ROS_AND_COMMANDS)

## 1. 阶段目标
严格参照 `lower_computer/下位机ros信息`、`群控商业化补充说明.md` 与 `LRMP V1.0-R3`，构建下位机底层核心模块（每个文件 `<= 300` 行，带标准 `@file`/`@brief`/`@exports` 头）。

## 2. 必建模块清单
1. `lower_computer/src/__init__.py`：下位机包导出标记。
2. `lower_computer/src/config/__init__.py` & `lower_computer/src/config/ros_env_config.py`：
   - 定义 `下位机ros信息` 全部组件版本（ROS 1.17.4, Catkin 0.8.12, TF 1.13.4/0.7.10, RViz 1.14.26, `livox_ros_driver2` 1.0.0, `fast_lio`, `open3d_loc` / Open3D 0.14.1, `mid360_to_velodyne`, `teb_polar`）。
   - 定义启动命令映射表（`roscore -p 11311`, `msg_MID360.launch`, `localization_3d_g1.launch`, `mid360_to_velodyne.launch`, `controller_planning.launch`, `mapping_mid360_g1.launch rviz:=false`, `rosbag record -a`, `python3 main.py single`, `python3 nav_web_server.py`, `nav_gait_bridge` -> DDS `rt/navvelocity`）。
   - 定义话题与服务常量：`/livox/lidar`, `/Odometry_loc`, `/localization_3d_confidence`, `/localization_3d_delay_ms`, `/cad_scan`, `/global_planner/path`, `/teb_polar_node/cmd_vel`, `/local_nav_status`, `/move_base_simple/goal`, `/initialpose`, `/teb_polar_node/cancel_planning`, `/teb_polar_node/set_parameters`, TF `map -> base_link`。
3. `lower_computer/src/ros_bridge/__init__.py` & `lower_computer/src/ros_bridge/navctl_runner.py`：
   - 真实调用 `sudo /opt/vsis_nav/navctl {status|start localization|restart localization|start mapping|restart mapping|finish-mapping|stop}`。
   - 支持注入自定义命令执行器 (`cmd_runner`) 以便在单元测试中验证命令拼装与真实返回码处理，无 ROS 宿主机上真实报告 `navctl_available=False`。
4. `lower_computer/src/ros_bridge/ros_topic_service_bridge.py`：
   - 真实读取 `/Odometry_loc`、`/localization_3d_confidence`、`/localization_3d_delay_ms`、`/local_nav_status`、`/cad_scan`、`/global_planner/path`、`/teb_polar_node/cmd_vel` 及 `tf_echo map base_link`。
   - 真实发布 `/move_base_simple/goal` (`geometry_msgs/PoseStamped`) 与 `/initialpose` (`geometry_msgs/PoseWithCovarianceStamped`)。
   - 真实调用 `rosservice call /teb_polar_node/cancel_planning` 与 `/teb_polar_node/set_parameters`。
5. `lower_computer/src/commands/__init__.py` & `lower_computer/src/commands/control_arbiter.py`：
   - 实现 `FREE` / `MANUAL` / `CHOREO` 控制权互斥状态机与 3 秒失联回 `PASSIVE` 保护。
6. `lower_computer/src/commands/motion_command_executor.py`：
   - 完整实现 `STAND`, `GAIT`, `PASSIVE`, `FORWARD`, `BACKWARD`/`BACK`, `MOVE_LEFT`, `MOVE_RIGHT`, `TURN_LEFT`, `TURN_RIGHT`, `MOVE`, `STOP`, `EMERGENCY`, `RELEASE`, `STATUS`, `GETDANCELIST` 逻辑。
   - 对无法直接调用底层 C++ 二进制的舞蹈/按键动作 (`DANCE,<alias>`, `BUTTON`, `MASK`) 实现真实 `lora_recv_group.yaml` 校验与标准化预留槽位 `execute_reserved_action_slot`（返回 `execution_mode="RESERVED_SLOT"` 及解析出的按键组合 `[select_key, action_key]`）。
