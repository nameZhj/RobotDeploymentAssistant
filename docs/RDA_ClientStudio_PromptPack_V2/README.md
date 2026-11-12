# RobotDeploymentAssistant：客户端舞台编导功能 Prompt Pack V2

**版本**：2.0  
**审计基线**：GitHub `nameZhj/RobotDeploymentAssistant` 的 `main` 分支，2026-11-12 重新读取  
**目标**：把现有 PySide6 舞台编导窗口改造成真正可用的本地创作工具，而不是另起一个 Demo、只写设计文档，或只修改颜色和标题。

## 本包解决什么问题

本包针对当前仓库中已经存在的舞台编导模块编写。它不是通用软件需求模板。Prompt 直接引用现有类、构造函数、方法和调用路径，并要求 Agent 对现有代码进行增量修复和功能实现。

最终本地客户端应当支持：

1. 本地工程创建、打开、保存、另存为、导入、导出和最近工程恢复。
2. 本地 PCD 地图导入、校验、解析、管理、加载、卸载、重命名、导出、删除；同一张地图同时进入 2D 舞台和 3D 视口。
3. 单机器人/多机器人实例管理与 2D 轨迹绘制、控制点编辑、样条预览、保存、JSON 导入导出和重现。
4. 阵型模板设计、机器人成员配置、位置/朝向计算、安全间距提示、保存和应用到舞台。
5. 舞蹈/动作/轨迹/阵型素材的统一本地素材库、搜索、详情、预览和拖放。
6. 双层时间轴：按机器人/群组分轨，动作层与轨迹层分层，拖放、移动、拉伸、吸附、播放头、撤销/重做、保存。
7. 基于项目真实数据的 3D 可视化预演和确定性播放；不把可视化预演宣传成动力学仿真。
8. 统一的 UniUni 1.0.2 深色工作台观感，以及完整的交互、数据持久化和回归验收。

## 当前执行范围的特别说明

**本轮只开发舞台编导客户端的纯本地功能。** 不开发、不联调、不审查、不重构机器人端或服务端通信，不做 LoRa/串口/MQTT/HTTP 上传/SSH/SFTP/认证/授权/安全下发/远程建图/设备遥测/机器人指令派发。不得把这些内容重新引入舞台编导工作区作为本轮验收项。

项目原有 Flask Web 部署与运维功能属于既有系统，原则上保持不变。本轮只允许解除舞台编导页面对运维通信组件的耦合；不得顺带删除、重写或破坏系统其他页面已有的设备管理能力。

## 重要：Skill 路径已重新确认

项目中的 Skill 正确路径是：

`/.agent_workspace/skills/robot-deployment-assistant/SKILL.md`

不是 `/.agents/skills/...`。请 Agent 每次开始时读取正确路径。该 Skill 是工程保护规则；如其中“机器人适配、通信与安全下发”等通用长期路线与本包的当前项目范围冲突，以用户本轮明确的“只做客户端纯本地创作功能”为本轮范围约束，记录为 Scope Override，不执行通信相关阶段。

## 推荐执行顺序

按编号顺序逐个执行，一次只执行一个 Prompt：

- `P00`：接管已执行 00–05 的工作区，修复主窗口数据注入、职责边界和核心链路。
- `P01`：本地工程、项目数据模型和持久化。
- `P02`：地图管理与 PCD 工作区。
- `P03`：机器人实例管理与 2D 轨迹编辑。
- `P04`：阵型设计与舞台应用。
- `P05`：统一素材库与拖放数据契约。
- `P06`：双层时间轴、播放头、撤销重做和持久化。
- `P07`：真实 3D 可视化预演。
- `P08`：端到端集成、视觉验收、回归和发布检查。

不要跳过 P00，也不要把多个 Prompt 合并成一个大重构。每个 Prompt 必须实际修改代码、执行测试、写入证据并更新 handoff，不得只输出分析报告。

## 目录结构

```text
RDA_ClientStudio_PromptPack_V2/
├── README.md
├── PROMPT_INDEX.md
├── GLOBAL_EXECUTION_CONTRACT.md
├── PROJECT_AUDIT_BASELINE.md
├── RELEASE_ACCEPTANCE_CHECKLIST.md
├── prompts/
│   ├── P00_WORKSPACE_RECOVERY_AND_WIRING.md
│   ├── P01_LOCAL_PROJECT_AND_DATA_MODEL.md
│   ├── P02_LOCAL_MAP_AND_PCD_WORKSPACE.md
│   ├── P03_ROBOT_REGISTRY_AND_2D_TRAJECTORY.md
│   ├── P04_FORMATION_DESIGN.md
│   ├── P05_ASSET_LIBRARY_AND_DRAG_DROP_CONTRACT.md
│   ├── P06_DUAL_LAYER_TIMELINE.md
│   ├── P07_REAL_3D_PREVIEW.md
│   └── P08_END_TO_END_INTEGRATION_AND_ACCEPTANCE.md
└── references/
    └── UNIUNI_DESIGN_TOKENS.md
```

## 如何使用

1. 在 Windows 开发机打开真实 `RobotDeploymentAssistant` Git 仓库，而不是 Prompt Pack 解压目录。
2. 确认 Prompt Pack 已经放在可访问的位置；不需要把 Prompt Pack 自动复制进仓库，除非你希望自行纳入版本管理。
3. 将 `GLOBAL_EXECUTION_CONTRACT.md` 和当前阶段 Prompt 一起交给 Coding Agent，或让 Agent 明确读取这两个文件。
4. 每完成一个 Prompt，先检查 Agent 生成的 `SESSION_HANDOFF.md`、测试报告和 Git diff，再执行下一个阶段。
5. 若本地工作区与 GitHub `main` 已不同，以本地真实工作区和用户未提交修改为准；GitHub 审计只作为定位线索，不是覆盖本地代码的理由。

## 不要接受的“完成”

- 只改 CSS、颜色、标题、图标，却没有接通真实功能。
- 只新增一套平行窗口/平行数据模型，旧窗口仍然坏着。
- 使用固定 `Robot_1/Robot_2`、固定轨迹、固定时间轴 Clip 假装项目已经有数据。
- 拖拽时能看到一个色块，但保存后重启消失，或 3D 播放器读取的不是同一份 Clip。
- 地图只显示在某一视图，而 2D/3D 使用不同地图数据或不同坐标变换。
- 测试只覆盖 Domain 函数，却声称 Qt 真实交互通过。
- 以“当前环境没安装 PySide6”为由不做静态、单元和可运行的替代验证；也不得把未运行的 Qt 集成测试标成通过。
- 只交付审计报告或架构设计，没有实际实现代码。
