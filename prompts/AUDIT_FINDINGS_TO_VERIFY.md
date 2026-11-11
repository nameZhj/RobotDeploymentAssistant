# 05A～05C 审计线索（全部待重新验证）

下列内容来自此前专项审计摘要，仅为核查线索，不是当前事实。必须检查现有源码、真实调用链和运行时行为，不能直接照抄结论或批量修改。

| 线索 | 涉及位置 | 验证方式 |
|---|---|---|
| `GroupTrajectorySqliteAdapter().list_groups()` 可能漏传 `store`，且异常被吞掉 | `lib_panels_controller.py` | 查签名、调用栈、真实数据库查询和 UI |
| 轨迹保存信号可能只发出 `saveProjectRequested`，没有持久化接收槽 | `main_studio_window.py` | 从 UI 绘制，核查 Repository/SQL，关闭重开 |
| 时间轴保存可能显示固定编号（如 8001）但不落盘 | 时间轴 Controller/按钮 | 创建真实 Clip，查 SQL 并重载 |
| `stage_performance_sampler.py` 可能用 `math.sin()` 伪造动作 | 3D 预演 | 追踪动作输入；缺数据时改为明确静态状态 |
| 时间轴可能默认注入 4 个假 Clip 和 `grp_001` | `dual_layer_timeline_canvas.py` | 搜索 seed/default，检查空库启动 |
| 3D 预览可能隐藏在 2D 之下或没有首帧姿态 | `stage_viewport_3d.py` | 真 GUI 检查层级、可见性、首帧 |
| `StudioMainWindow` 与 `MainStudioWindow` 可能并存且一个旁路 | 窗口启动链路 | 从实际入口反向追踪实例化和状态所有权 |
| `src/ui/choreo/` 可能无引用，实际实现位于 `src/ui/choreo_page/` | UI 模块 | 查静态/动态导入、插件和运行调用 |
| `studio_data.db`、`studio_core.db`、`choreo_studio.db` 可能并存 | DB/Repository | 查当前连接、SQL trace、运行时数据写入 |
| PCD 解析器可能不支持 `binary_compressed` | PCD 引擎 | 用真实文件验证；不支持则明确报错 |
| 执行引擎可能使用设备命令表不存在的 `TRAJECTORY_START` | 通信/执行引擎 | 对照真实协议和设备端实现 |
| 单向 LoRa 可能不支持双向 ACK | 通信层 | 核查物理链路，不得伪称 ACK |
| 3D 可能宣称 G1 URDF 29-DoF FK | 机器人 3D painter | 核查实际 URDF、映射、输入，不按类名认定 |
| 地图/群组等表可能为空 | 活跃 DB | 对本次实际数据库只读检查，不沿用旧统计 |

## 处理原则
- 先验证实际入口和数据所有权，再修复。
- 不得为填满页面自动创建示例地图、假动作、假群组。
- 不得为了绕开原有 Repository 创建新的平行数据库。
- 确认旧目录无动态引用后才可清理。
- 每项修复必须接入用户实际调用链并做持久化/重开验证。
