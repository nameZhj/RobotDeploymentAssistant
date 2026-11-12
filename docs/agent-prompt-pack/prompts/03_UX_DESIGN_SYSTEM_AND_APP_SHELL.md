# PROMPT 03 — 舞台编导主工作台 UI 实装（UniUni 风格）

> **本阶段交付一套真正可用的 PySide6 舞台编导工作台外壳。**  
> 不是做静态原型，不是画一个漂亮但不可操作的页面。每个可见按钮都必须有真实动作；暂未实现的后续业务控件不显示。严格使用 UniUni 1.0.2 已解析的真实设计 token 和布局逻辑，并保留 RDA 现有 Qt 项目技术栈。

## 1. 使用的设计依据

先读取：
- `references/UNIUNI_1.0.2_界面与交互逆向分析.md`
- `references/UNIUNI_DESIGN_TOKENS.json`
- `references/RDA_舞台编导现状代码审计.md`

禁止要求本地 Agent 再次解析 UniUni，也禁止假设使用 Vue/Electron/Konva。RDA 页面必须用 PySide6 实现。

### 1.1 UniUni 真实 CSS Token

把这些值集中到单一 Qt Theme，而不是散落在每个 widget 的 styleSheet：

| 语义 | 颜色 |
|---|---|
| Window base | `#0b0c0f` |
| Canvas | `#060708` |
| Panel | `#101114` |
| Card | `#15161a` |
| Control | `#191a20` |
| Control hover | `#20222a` |
| Text primary | `#e4e6ea` |
| Text secondary | `#9ba0aa` |
| Text muted | `#6a6f78` |
| Accent | `#2e7bf7` |
| Accent hover | `#4a8df9` |
| Accent pressed | `#2268db` |
| Success | `#2bb673` |
| Warning | `#f0a228` |
| Danger | `#ee4d5a` |
| Border | `rgba(236,239,243,0.1)` |

尺寸 token：

| 控件 | 尺寸 |
|---|---:|
| UniUni 主标题栏 | 40 px |
| UniUni 状态栏 | 24 px |
| 工具栏 | 40 px |
| 标准按钮 | 32 px 高 |
| 紧凑按钮 | 28 px 高 |
| 图标小按钮 | 24 px 高 |
| 输入框 | 28–30 px 高 |
| 面板圆角 | 8 px |
| 按钮圆角 | 6 px |
| 输入控件圆角 | 4 px |
| 间距 | 4 / 8 / 12 / 16 / 24 / 32 px |

字体：
`"Helvetica Neue", Helvetica, "PingFang SC", "Microsoft YaHei", Arial, sans-serif`
Qt Windows 下优先使用 Microsoft YaHei/Segoe UI fallback；字号 11–13 px，页面标题 15 px。

## 2. 目标窗口与主布局

真实入口必须仍为 `StudioMainWindow`，不新建独立应用。

窗口：
- 默认大小：`1440×900`
- 最小尺寸：`1200×720`
- 主标题栏：40 px
- 页面工具栏：40 px
- 底部状态栏：24 px
- 中央内容区 margin：8 px
- 主面板间距：8 px

`StudioMainWindow` 的 central layout 使用垂直 `QSplitter`：
- 上部 workspace：默认约 620 px；
- 下部 timeline：默认约 220 px；
- splitter handle：6 px；
- timeline min height：220 px。

上部 workspace 使用水平 `QSplitter`，从左到右：

```text
┌──────────────────┬──────────────────────────────────────┬──────────────────────┐
│ 机器人面板       │              中央画布                │ 资源库               │
│ 宽 260 px        │              stretch=1               │ 宽 310 px            │
│                  │                                      │                      │
│ 机器人列表       │ 2D / 3D 视图                          │ 动作库 / 轨迹库       │
│                  │                                      │ 搜索 + 列表 + 详情   │
└──────────────────┴──────────────────────────────────────┴──────────────────────┘
```

Splitter 初始尺寸 `[260, 1, 310]`，最小宽：
- 左侧 220 px；
- 中央 480 px；
- 右侧 280 px。

窗口变窄时由用户拖动 splitter 调整，不允许中央画布缩到 300 px 以下。窗口最小宽 1200 px 是底线。

## 3. 顶部全局栏：`StudioHeaderBar`

文件：`src/ui/shell/header_and_footer.py`。若当前类已移动，修改真实被 `StudioMainWindow` 使用的类。

### 左侧品牌区

- 高 40 px，宽度约 118 px。
- 主标识文字：`RDA`，14 px、700、字距 0.3 px，颜色 `#e4e6ea`。
- 次文字：`舞台编导`，12 px，颜色 `#9ba0aa`。
- 不复制 UniUni Logo 或商标。

### 中央主导航

用单选互斥的 `QToolButton`/`QPushButton`，按钮高 28 px：

1. `舞蹈编排`
2. `表演监测`
3. `导航地图`

样式：
- 默认透明背景、文字 `#9ba0aa`、左右 padding 10 px；
- hover 背景 `#20222a`，文字 `#e4e6ea`；
- active 背景 `rgba(46,123,247,0.18)`，边框 `rgba(46,123,247,0.45)`，文字 `#6fa3ff`；
- 圆角 6 px；
- 三个导航按钮互斥，不能同时 active。

点击行为：
- `舞蹈编排` -> `QStackedWidget.setCurrentWidget(MainStudioWindow)`。
- `表演监测` -> 切换到现有 `MonitorPageView`。
- `导航地图` -> 切换到现有 `NavigationMapPage`。
- 切换前若当前页面有 dirty state，弹出 `保存 / 不保存 / 取消`；取消后保持当前页面。
- 导航状态必须由当前 stacked widget index 驱动，不允许按钮 active 与实际页面不同步。

### 右侧场景区

- 标签“场景”，字号 11 px、颜色 `#9ba0aa`。
- `QComboBox`：宽 180 px、高 28 px。
- 只加载 repository 返回的真实场景。
- `userData` 存真实 scene_id，禁止用显示文本作为数据库主键。
- 空场景时显示“未创建场景”，不能添加虚构“现场舞台/实验室展厅”。
- 更换场景：若 dirty，先确认保存/放弃/取消；加载失败时恢复原选择并显示错误。

右侧只允许放有真实功能的入口。帮助、设备、设置若没有实际页面或 handler，就不要显示图标占位。

## 4. 页面顶部操作栏：`TopShowHeader`

文件：`src/ui/header/top_show_header.py`。

高度 40 px；背景 `#101114`；底部分割线 `rgba(236,239,243,0.1)`；左右 padding 10 px。

从左至右：

| 控件 | 尺寸 | 文案 | 点击动作 |
|---|---:|---|---|
| 新建 | 64×28 | 新建 | 新建空编排工程；dirty 时先询问保存 |
| 导入 | 64×28 | 导入 | 打开文件对话框，只接受项目支持的格式；校验成功后加载 |
| 保存 | 64×28 | 保存 | 调用唯一 application service/repository 保存；成功后清 dirty |
| 分隔符 | 1×22 | — | 纯视觉 |
| 当前工程名 | 自适应 | 未命名编排/真实工程名 | 只读显示 |
| Dirty 标签 | 48×20 | 未保存 | 有修改才出现；保存成功消失 |
| 视图模式 | 120×28 | 编辑/预览 | 只显示当前已实现的模式；切换状态由 controller 驱动 |

按钮颜色：
- 新建/导入：控制底色 `#191a20`，边框 `#20222a`；
- 保存：主色 `#2e7bf7`，hover `#4a8df9`，pressed `#2268db`；
- disabled：文字 `#6a6f78`，不响应点击。

动作要求：
- 新建：创建空 Scene/Show，不自动生成机器人、轨迹和 clips。
- 导入：文件格式过滤器必须对应真实 parser；非法文件展示错误原因，不销毁当前工程。
- 保存：保存后从 repository 重新读回关键字段做轻量一致性检查；只有成功才 toast“已保存”。
- 所有操作一次点击只能调用一次 use case；禁止按钮 clicked 和自定义 signal 双重调用。

快捷键：
- Ctrl+N：新建。
- Ctrl+O：导入。
- Ctrl+S：保存。
- 快捷键必须在菜单/tooltip 中展示，并且测试实际触发。

## 5. 左侧机器人面板：260 px

创建/改造一个唯一 `RobotPanel`，建议文件位置 `src/ui/choreo_page/robot_panel.py`；若已有真实机器人列表，直接扩展。

布局：
- 根宽 260 px。
- 背景 `#101114`。
- 右边框 `1px solid rgba(236,239,243,0.1)`。
- 标题行高 36 px，左右 padding 10 px。
- 标题 `机器人`，13 px/600。
- 数量徽标 `0`，11 px，灰色胶囊。
- 刷新按钮 `24×24 px`，图标 `refresh-cw`，tooltip `刷新机器人状态`；只有存在真实 refresh service 时出现。
- 搜索输入框高 28 px、margin `6px 8px`、placeholder `搜索机器人 ID 或名称`；输入后对当前真实列表做即时过滤，清空恢复列表。
- 机器人列表使用 `QListView + QAbstractListModel` 或项目已有 model/view。
- 行高 56 px，padding 8 px，行间距 4 px，圆角 6 px。

每行内容：
- 在线状态点 8×8 px：在线 `#2bb673`，离线 `#6a6f78`，异常 `#ee4d5a`。
- 第一行：机器人显示名 12 px/600；右侧机器人 ID 11 px `#9ba0aa`。
- 第二行：机型 + 电量（有真实值才显示）；没有电量字段时不显示 `0%`。
- 左侧选择 checkbox 16×16 px，仅用于当前编排的参与者选择。
- 离线机器人可以被查看，但默认不能添加到执行集合；点击选择时弹提示“机器人离线，无法加入可执行集合”。

交互：
- 单击行：选中单个机器人，中央视图高亮其模型/轨迹。
- checkbox：加入/移出当前参与者集合。
- Ctrl+A：选择当前过滤列表中的在线机器人。
- 双击行：若 pose 有效，中央画布居中到该机器人；无 pose 时只显示设备详情。
- 右键菜单只提供已实现的“查看详情”“复制 ID”；不得显示“自动编队”等未实现选项。
- 无数据时显示空状态：“未发现机器人。请连接设备或导入真实机器人配置。”
- 刷新期间按钮转 loading，刷新失败显示错误但保留上一次状态（标记 stale）。

## 6. 中央画布区域

中央宽度占剩余空间，最小 480 px。必须复用当前的 `StageCanvas2D` 与 `StageViewport3D`。

### 6.1 画布顶部工具栏

高 40 px，背景 `#101114`，下边框 1 px。

左侧：
- `2D` / `3D` segmented control，总宽 88 px，高 28 px。
- active 蓝色背景 `#2e7bf7`，inactive 控件底 `#191a20`。
- 点击 2D/3D 仅切换现有 stack 页面，不重建 renderer，不丢失相机/缩放状态。

中部：
- 显示当前地图名（没有地图则“未加载地图”）。
- 显示坐标系/单位（未知显示“坐标系未标定”）。
- 文字 11 px，颜色 `#9ba0aa`。

右侧：
- `适配视图` 图标按钮 28×28，tooltip“适配当前地图和对象到视口”；调用当前 renderer 的 fit-to-content 方法。
- `网格` checkable 28×28，tooltip“显示/隐藏坐标网格”；只有画布真正支持网格时显示。
- 不允许添加无实际 handler 的截图、刷新、正视、原点重置等装饰性图标。

### 6.2 2D 画布

- 背景 `#060708`。
- 网格线低对比度 `rgba(236,239,243,0.06)`。
- 主坐标轴 `rgba(111,163,255,0.55)`。
- 左上角放小状态 chip：`2D 视图`，11 px。
- 左下角显示比例尺和缩放率；缩放率仅按 renderer 的真实 transform 计算。
- 鼠标 hover 有坐标时，右下角显示世界坐标 X/Y 和当前 frame；没有坐标时不显示虚构数字。
- 没有地图时在中央显示：标题“尚未加载地图”、说明“导入 PCD 地图或选择已有地图后开始编辑”；不显示合成点云和固定障碍物。
- 没有机器人时不画机器人。
- 没有轨迹时不画路径。
- 当前页面 toolbar 不显示尚未在 06 实现的“自动规划”“阵型生成”等操作。

### 6.3 3D 画布

复用 `StageViewport3D`。
- 默认背景与 2D 一致。
- 显示 XYZ 轴和地面网格（若 renderer 支持）。
- 无地图时只显示坐标辅助，不创建假点云。
- 无 URDF/STL 时不创建假机器狗；显示“未加载机器人模型”小提示。
- 相机旋转/缩放/平移遵循当前 3D renderer 的真实鼠标绑定。
- `适配视图` 调用 3D renderer 对当前有效对象 fit。
- 不在 03 实现新模拟算法；播放和 seek 的完整功能属于 09。

## 7. 右侧资源库：310 px

创建/改造唯一 `LibraryPanel`，复用 `LibPanelsController`/`ActionLibraryPanel`/`TrajectoryLibraryPanel` 中已经被审计为活跃的实现。

根宽 310 px，背景 `#101114`，左边框 1px。

- 标题行高 40 px，标题 `资源库`。
- Tabs 高 32 px：`动作`、`轨迹`。
- 搜索框高 30 px，左右 margin 8 px。
- 列表行高 52 px，左右 padding 8 px。
- 详情区高度由剩余空间决定，顶部边框 1 px。

动作列表：
- 只读真实仓储动作。
- 每行显示名称、适用机型、时长；来源不是内置真实数据时显示来源标签。
- 双击只打开详情，不在本阶段自动创建 timeline clip。
- 搜索按名称/编号/机型过滤。
- 空状态：“暂无可用动作。请导入动作文件或从已连接设备同步。”
- 没有真实导入 service 时不显示导入按钮。

轨迹列表：
- 只读真实 repository trajectories。
- 每行显示名称、点数、总长度或时长（缺字段不显示）。
- 点击行选中轨迹；中央画布高亮轨迹（如果当前 viewer 支持）。
- 双击打开轨迹详情，不自动开始执行。
- 搜索按名称/ID/机器人组过滤。
- 空状态：“暂无轨迹。完成轨迹绘制或导入轨迹 JSON 后会显示在这里。”
- 导出/删除按钮仅在当前选中项具备真实 handler 时显示；删除必须检查 clip 引用并确认。

禁止保留双列表实现：不能同时创建一个隐藏 tree 和可见 table，再让按钮操作隐藏控件。

## 8. 底部时间轴区域

保留当前 `DualLayerTimelineCanvas` 的单一活跃实现，位置在 workspace 下方。

- 时间轴最小高度 220 px；默认高度 260 px。
- 顶部工具栏 32 px。
- 轨道标签区域宽 160 px。
- 时间刻度区最小宽度 300 px。
- 空场景时不自动创建机器人轨道。
- 没有 clip 时显示居中空状态“当前编排还没有动作或轨迹片段”。
- 03 不创建假 clip，不增加假轨道，也不实现完整拖放编排；拖放落点创建 clip 属于 Prompt 08。
- 播放/暂停按钮仅当现有播放 service 可正确驱动 playhead 时显示；否则隐藏，不能显示无响应按钮。
- 当前时间、总时长必须从 timeline model 读取；无 clip 时总时长为 0，不显示 60 秒等默认数字。

## 9. 全局状态栏

高度 24 px，背景 `#101114`，上边框 1 px，字号 11 px。

从左到右：
- 当前工程名称；
- 保存状态（已保存/未保存/保存失败）；
- 地图加载状态；
- 在线机器人数量；
- 网络状态；
- 后台任务状态。

只有真实值显示；无值用 `--`。点击状态项只有在有明确的详情页面/弹窗动作时才允许可点击。

## 10. 所有可见控件的事件契约

建立 `docs/agent-prompt-pack/audit/03-ui/control-event-map.csv`，字段：

`widget_id,visible_text,container,position,size,enabled_condition,event,handler,use_case,state_change,error_feedback,test_id`

每个可见按钮/ComboBox/Tab/Search/CheckBox 都有一条记录。不存在 `handler` 的控件从界面删除；不能用 lambda None 占位。

必须验证：
- 新建/导入/保存各调用一次。
- 主导航和页面 stack 状态一致。
- 场景切换先询问 dirty。
- Robot selection 更新同一 application state。
- 搜索即时过滤，不修改数据库。
- Action/Trajectory 双击不创建 clip。
- 2D/3D 切换保留 camera/zoom。
- 网格切换只影响网格层，不清空地图。
- 关闭窗口释放后台任务和 signal connection。

## 11. 样式落地方式

- 创建/扩展单一 Theme 入口，例如当前项目已有的 `src/ui/theme/`；若没有，则建议 `src/ui/theme/uniuni_inspired_theme.py`。
- 通过集中 token 定义颜色、字号、圆角、间距、按钮高度。
- 不允许在每个控件文件里复制整段 QSS。
- hover、pressed、checked、disabled 四种状态必须有独立样式。
- 图标使用已有资源；若现有资源无对应图标，优先使用文字/标准 Qt icon，不安装新的图标库来填充。
- 所有图标按钮必须有 tooltip 和 accessibleName。
- 不复制 UniUni Logo、图像资源或商标。

## 12. 测试和视觉验收

新增/扩展 Qt UI tests。至少检查：
- 1440×900 全窗口截图。
- 1200×720 最小窗口截图。
- 3 栏 splitter 初始比例。
- 导航 active 与 Stack 页面同步。
- 真实场景 ComboBox 只含真实 scene_id。
- 机器人列表空/在线/离线/异常三种数据状态。
- 动作库空/有数据。
- 轨迹库空/有数据。
- 2D 无地图、2D 有地图。
- 3D 无模型、3D 有模型。
- dirty/save/error 状态。
- 所有可见控件都有 event map 行和测试 ID。
- 截图中不得出现假 IP、假机器人、假任务、假 clip 和虚构在线数量。

实际运行项目并保存截图至：
`docs/agent-prompt-pack/audit/03-ui/screenshots/`

如果本机 Qt 环境不能截图，记录具体错误和受阻步骤，但仍要运行能够完成的 widget tests。不能只输出静态 HTML 原型。

## 13. 完成定义

- 舞台编导仍从主页原按钮打开。
- 新 UI 基于 PySide6，不迁移 Electron/Vue。
- 页面结构和交互接近 UniUni 已验证的分区与工具布局。
- 所有按钮都能产生明确业务结果。
- 不存在虚构数据显示。
- 布局在 1440×900 和 1200×720 都可用。
- 所有控件样式来自集中 Theme。
- 真实运行截图和测试报告已保存。

**本 Prompt 完成后，更新状态文件和 SESSION_HANDOFF。**
