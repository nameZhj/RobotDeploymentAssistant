---
name: stage-director-delivery
description: RobotDeploymentAssistant 舞台编导端到端开发、Qt/Web 生命周期修复、PCD 地图、轨迹、阵型、动作时间轴、3D 预演及 Git 历史功能回归。
---

# Stage Director Delivery Skill

- 以可运行产品为标准：必须真实修改源码、接入真实启动入口、运行交互、持久化、重启恢复。
- 用户允许修改任意文件；必须保护 Git 中 2026-10-01 00:00（Asia/Taipei）之前已正确实现的功能行为，而非禁止修改旧文件。
- 修改前记录 Git 状态，备份 staged/unstaged 补丁和可能受影响的未跟踪文件；不得覆盖用户现有工作。
- 禁止 `git reset --hard`、`git clean`、`git checkout`、`git restore`、`git stash` 和等价丢弃操作。查看历史文件用 `git show`，不切换工作树。
- 建立历史行为契约；公共入口、Qt 线程、Web、数据库、通信、地图和共享模型变更必须进行历史回归。
- P0：完整入口打开/关闭舞台编导窗口连续 10 次成功；检查 QObject 生命周期、Qt 线程、manager 引用、信号槽和 QApplication。
- PCD 地图必须是真实导入；不支持的格式明确报错；不得生成假地图。
- 2D 单/群体轨迹必须真实绘制、编辑、保存、重载。
- 阵型必须真实计算和持久化，群组 ID 必须存在。
- 时间轴素材拖放必须形成真实 Clip；保存后重载。禁止假 Clip、假编号和假成功提示。
- 3D 必须使用当前项目真实地图、轨迹、阵型和动作；没有真实姿态数据时明确静态/未配置，不伪造动作。
- 机器人端遥控建图/实时上传目前只预留接口，未接真实协议和设备不得声称完成。
- 检查数据库所有权，不得随意清库或创建新的平行数据库；迁移需备份、事务、版本、幂等和恢复。
- UI 必须从用户真实入口验收；Offscreen/Mock 只能补充，不能替代桌面 GUI。
- 最终逐项报告 PASS/FAIL/BLOCKED/N/A，附截图/录屏、SQL/持久化、测试日志和历史回归证据。
