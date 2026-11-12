# UniUni 1.0.2 界面与交互逆向分析（基于已上传资料）

> 分析对象：资料库中的 `UniUni-1.0.2-setup.exe`，以及 `RobotDeploymentAssistant.rar` 内的 `.agent_workspace/asar_out/` 编译后渲染层文件。  
> 本报告由 ChatGPT 直接读取和分析生成，不要求本地 Agent 再次逆向 UniUni。  
> 证据等级：`已验证` = 可从上传文件/编译组件直接读取；`推断` = 由组件结构和事件绑定推断；`未验证` = 缺少运行截图、原始 CSS 或运行环境，不能伪称实测。

## 1. 结论先行

UniUni 1.0.2 的安装程序 PE 版本资源包含：

- `ProductName`: UniUni
- `ProductVersion`: 1.0.2
- `CompanyName`: unitree.com
- `FileDescription`: An Electron application with Vue and TypeScript
- 安装器类型：NSIS

RAR 中同时存在大量 `out_renderer_assets_*.js.txt`、`out_main_*.js.txt` 文件，包含 UniUni 的 Vue 编译组件、路由片段、事件处理、业务组件名称和模板渲染逻辑。文件中出现 `map-workspace`、`trajectory_planning_page`、`PreviewMapPanel`、`ActionManageDialog`、`timeline_editor_wrapper` 等真实组件/页面标识。由此可以对页面信息架构和交互链路进行代码级分析。

**限制：** 当前执行环境不是 Windows，没有启动安装程序，也没有获得实时运行截图。但 RAR 内不只有 JavaScript：` .agent_workspace/out_src/out/renderer/assets/` 还包含 188 个编译 JS 文件和 83 个 CSS 文件，其中包括应用外壳、地图工作区、轨迹规划、地图预览和时间轴相关 CSS。因此本报告已经读取真实 CSS 变量、布局宽度、控件高度、颜色和间距；这些值可以作为 UniUni 1.0.2 的源码级视觉证据。唯一不能声称的是“在 Windows 上亲自运行并截屏观察”。

## 2. UniUni 技术与应用外壳

### 2.1 已验证技术结构

| 项目 | 结论 | 证据 |
|---|---|---|
| 桌面容器 | Electron | 安装程序及主进程/预加载 chunk |
| 前端 | Vue 3 + TypeScript | 编译组件中的 Vue `defineComponent`、TS 编译痕迹 |
| 构建 | Electron-Vite | 安装程序字符串含 `electron-vite.org` |
| UI | 自定义 U 组件 + Element Plus 组件 | `UPanel`、`UButton`、`UDialog`、`ElInputNumber` 等 |
| 图标 | Lucide Vue 图标 | 编译 chunk 中 `lucide-vue-next` |
| 2D 画布 | Konva | `Konva.Stage`、`Konva.Layer`、Konva timeline/canvas 组件 |
| 3D | Three.js 生态 | `WebGLRenderer`、`OrbitControls`、`URDFLoader`、`EffectComposer` |
| 本地状态 | Pinia 风格 Store / composable | `useMainStore`、`useDeviceStore` 等 |
| 地图 | PCD、点云、栅格地图、空间标定 | `PointCloudViewer`、`pcdGridWorker`、`Stage3Localization` |
| 时间轴 | Konva 分层时间轴 | timeline layer、playhead、scale、task layer、beat marker 代码 |

### 2.2 全局应用外壳

编译组件 `out_renderer_assets_index-DRkqKZBV.js.txt` 中的主布局包含以下结构：

1. 顶部 `app_titlebar`
   - 左侧品牌标识 `Uni`。
   - 中间主导航 `tb_nav`。
   - 导航项根据系统配置过滤；窗口宽度不足时通过 `ResizeObserver` 计算溢出数量，将剩余入口放进“更多”菜单，而不是让导航换行挤压。
   - 右侧场景选择器 `SceneSelector`。
   - 帮助菜单、视图菜单。
   - 设备概览、用户资料、系统设置图标按钮。
   - Windows/Linux 窗口最小化、最大化、关闭按钮；macOS 使用不同平台布局。
2. 中间 `app_body`
   - `app_main` 承载路由页面。
   - `router-view` 使用 `KeepAlive`，页面切换时保留页面状态。
3. 底部 `app_statusbar`
   - 用户账号/登录状态。
   - 订阅等级。
   - 系统版本。
   - 当前场景。
   - 初始化点配置入口。
   - 音乐配置状态。
   - 网络状态、消息数量等状态信息。

**对 RDA 的可借鉴点：** 全局导航只放跨页面操作；项目/场景上下文始终可见；设备、账号、设置使用统一入口；底栏只展示真实状态；窄窗口下导航进入“更多”，不堆叠重复按钮。

## 3. 地图工作区

来源组件：`out_renderer_assets_index-D8V4tJoK.js.txt`。

### 3.1 已验证布局

- 页面根容器：`map-workspace`。
- 左侧导航使用 `UPanel`，明确设置 `width: 220`。
- 左侧导航按用途分组，而不是将所有操作平铺在工具条中。
- 右侧主体 `map-body` / `pane-body` 根据 active pane 切换页面。
- 默认 pane 为 `radar`。
- 页面挂载时调用 `mainStore.initializeScene()`。
- URL query `pane` 可指定 pane；只接受有效 pane key。

### 3.2 左侧导航分组和真实入口

| 分组 | 入口 key | 图标 | 对应功能 |
|---|---|---|---|
| 地图生成 | `radar` | MapPin | 雷达建图 |
| 地图生成 | `grid` | Grid3x3 | 栅格地图生成 |
| 地图管理 | `version` | FolderOpen | 地图版本 |
| 地图管理 | `distribute` | Share2 | 地图分发 |
| 地图对齐 | `calibration` | Crosshair | 坐标标定 |

导航项是按钮，点击后仅切换 active pane；Grid 页面可跳转 Calibration/Version，Radar 页面可跳转 Version。地图版本和分发页面不是一个没有行为的装饰入口。

### 3.3 右侧地图子页面组件

`index-D8V4tJoK` 的页面组件包括：

- `RadarMappingPane`
- `GridMapPane`
- `MapVersionPane`
- `DistributePane`
- `CalibrationPane`
- `PointCloudDisplaySettings`
- `RobotPicker`
- `ThreeViewport`
- `CanvasViewport`
- `PcdPreview`

因此 UniUni 地图模块不是单一“上传地图”按钮，而是把采集、栅格生成、版本管理、分发、标定拆成清晰工作流。

## 4. 轨迹规划页面

来源组件：`out_renderer_assets_index-Bzj1CuRc.js.txt`。页面根 class 为 `trajectory_planning_page`。

### 4.1 页面结构（从 Vue render tree 读取）

```text
trajectory_planning_page
└── canvas_panel
    ├── panel_header
    │   ├── toolbar_row（第一行：编队/运动/坐标/播放参数）
    │   └── toolbar_row（第二行：字符/阵型/平移/执行参数）
    └── panel_body
        ├── robot_panel
        │   ├── robot_panel_header
        │   └── robot_panel_list
        ├── canvas_wrapper
        │   ├── konva_stage
        │   ├── status_overlay
        │   ├── zoom_controls
        │   ├── robot_tooltip
        │   └── stats_overlay
        └── task_panel
            ├── task_panel_header
            ├── task_panel_create
            └── task_panel_list
```

### 4.2 第一行参数控件（已验证字段及限制）

| 控件 | 绑定状态/参数 | 约束或选项 |
|---|---|---|
| 编队列数 | `gridCols` | 2–15 |
| 编队行数 | `gridRows` | 2–15 |
| 初始间距 | `gridSpacing` | 最小 1，步长 0.1，精度 1 位 |
| 初始偏移 X/Y | `initialOffsetX/Y` | -50 至 50，步长 0.5 |
| 最大加速度 | `trajMaxAcc` | 0.1–50 m/s²，步长 0.5 |
| 最大速度 | `trajMaxSpeed` | 0.5–10 m/s，步长 0.5 |
| 原点 X/Y/Yaw | `originX/Y/Yaw` | 三个坐标输入 |
| 目标终点朝向 | `targetFinalYaw` | rad |
| 预览速度 | `playbackSpeed` | 1x、2x、3x、5x、10x |

### 4.3 第二行参数与动作

- 字符/图案生成模式：`single`、`multi-seq`、`multi-sim`。
- 字符输入框：单字符模式最多 1 个字符，多字符模式最多 20 个字符。
- 清空字符后不重置编号选项。
- 字符尺寸、目标偏移 X/Y。
- 轨迹速度、连续模式、统一速度、同步到达等控制状态。
- 目标间距输入和“调整间距”按钮；不是纯 UI，按钮绑定 `handleAdjustSpacing`。
- 平移 X/Y 输入、XY 联动复选框和“平移”按钮；绑定预览与应用动作。
- 所有禁用状态由业务状态计算，不是视觉禁用。

### 4.4 机器人列表

- “全选/取消全选”按钮。
- “发送指令”按钮：无选中机器人时禁用；执行中显示 loading。
- “紧急停止”按钮：无选中机器人时禁用；执行中显示 loading。
- 每个机器人行包含：在线点、机器人 ID、别名、定位状态、X/Y/Yaw、SOC 电量。
- 离线机器人呈 disabled/offline 状态，不能继续被误选。
- 列表为空时显示明确的 `noRobots` 空状态。

### 4.5 中央画布

- Konva canvas 容器。
- 缩放 +、缩放比例、缩放 -、非 100% 时出现重置按钮。
- 状态徽标。
- 悬停机器人 tooltip：X、Y、Yaw。
- 统计浮层：目标点数量、最小机器人间距、最长/最短路径、总时长、仿真帧数、播放进度。
- 状态和统计数据来自实际响应式状态，不用固定演示数字。

### 4.6 任务面板

- 任务列表标题和任务录制状态。
- 选中任务时出现“预览/退出预览”等上下文操作。
- 每个任务可展开/收起。
- 录制状态下提供“采集”动作；没有仿真帧时禁用采集。
- 每条记录显示序号、来源字符/操作、记录类型、持续时间、校验警告、路径数据查看、加速度和保持时间。
- 任务支持创建、删除、录制、采集、预览、执行和中止。
- 无任务、无记录分别有独立空状态。

**对 RDA 的可借鉴点：** 中央画布必须是主视觉区域；机器人选择、任务管理和资源库不能互相混成一排按钮；危险动作与普通编辑动作分组；按钮根据选择和执行状态禁用/显示 loading；统计只在有真实数据时显示。

## 5. 2D/3D 地图预览和绘制工具

来源组件：`out_renderer_assets_PreviewMapPanel-CNqgEJoF.js.txt`。

已识别子组件：

- `DisplaySettings`
- `Instructions`
- `DrawingTools`
- `OnlineRobotMonitor`
- `PlaybackThreeViewer`
- `CustomMapModal`
- `PreviewMapPanel`

代码中可见的交互包括：

- 2D/3D 视图切换。
- 点云显示/隐藏、点云高度裁剪、体素显示参数。
- 机器人可见性和机器人选择。
- 绘制轨迹、草图类型、草图颜色、清空、撤销、重做。
- 航向角调整。
- 轨迹命名。
- 地图自定义导入、读取、保存、删除。
- 2D 预览和 3D 播放视口切换。
- 播放进度、播放控制、碰撞层显示。
- 全屏和预览开关。
- 对地图未准备、未选场景、无在线设备等状态有提示，而不是继续显示假数据。

## 6. 时间轴和动作编辑

### 6.1 Konva 时间轴

来源组件：`out_renderer_assets_Index-C9SDLLs9.js.txt`。

代码可见的时间轴机制：

- 固定左侧轨道标签区和右侧可横向滚动时间区域。
- 时间刻度层、轨道内容层、任务内容层、播放指针。
- 支持时间轴缩放、横向拖动、滚动定位。
- 可添加/删除时间标记；标记有时间和描述。
- 轨道区域与播放指针同步，超出视口时进行边界修正。
- 使用 Konva layer/group 分层绘制，不能把时间轴做成一张不可交互图片。

### 6.2 动作数据裁剪编辑器

来源组件：`out_renderer_assets_index-w2E8kWQ3.js.txt`。

已验证控件：

- 频率选择：5、10、20、30、50、60 Hz。
- 时间轴放大、缩小。
- 固定间隔开关和间隔输入。
- 起始/结束裁剪指针。
- 右键/上下文菜单设置裁剪起点或终点。
- 显示裁剪时长。
- 导出裁剪后的数据。
- 数据为空、读取失败、裁剪范围非法时有错误提示。

### 6.3 动作库

来源组件 `out_renderer_assets_index-Cv2Z0aI0.js.txt` 和 `out_renderer_assets_ActionManageDialog-DRZWDPpU.js.txt`。

组件包括：

- `ActionLibrary`
- `ActionDetailPanel`
- `RobotLibrary`
- `RobotDetailPanel`
- `ActionStoreList`
- `ActionPreviewModal`
- `ActionStoreDrawer`
- `BatchTaskPanel`
- `ActionManageDialog`
- `ActionTrialDialog`
- `MotionProfileChart`
- `MotionEnvelopeDetailDialog`
- `MotionEnvelopeBatchDialog`

可见的设计原则：动作列表、动作详情、机器人列表、动作商店、批量任务和动作试运行是不同职责；动作能力与机器人型号相关，不能把所有动作无差别展示给所有机器人。

## 7. 对 RDA 的具体设计转译

### 7.1 应保留的 UniUni 工作流原则

1. 先选择场景/地图，再进入地图/轨迹编辑。
2. 先选择真实机器人，再执行面向机器人的动作。
3. 中央画布负责空间编辑；资源列表负责选取；属性面板负责精确数值；时间轴负责时间编排。
4. 2D 和 3D 共享同一份场景/轨迹/机器人状态。
5. 轨迹库、动作库、任务列表是有明确数据源的资源面板。
6. 预览和真机执行严格区分。
7. 没有数据时显示空状态，不注入虚构机器人、动作、轨迹或在线状态。
8. 危险操作必须二次确认，执行中显示进度和可中止状态。
9. 导航入口必须能到达真实页面；无实现的功能不应作为可点击按钮出现。

### 7.2 UniUni 已验证设计 Token（来自 `index-BLeFS3an.css`）

以下是 CSS 中直接读取的实际值，不是根据截图估计：

| Token | UniUni 实际值 |
|---|---|
| 主窗口底色 `--u-base` | `#0b0c0f` |
| 画布底色 `--u-canvas` | `#060708` |
| 面板底色 `--u-panel` | `#101114` |
| 卡片底色 `--u-card` | `#15161a` |
| 控件底色 `--u-control` | `#191a20` |
| 控件 hover `--u-control-hover` | `#20222a` |
| 一级文字 `--u-text-1` | `#e4e6ea` |
| 二级文字 `--u-text-2` | `#9ba0aa` |
| 三级文字 `--u-text-3` | `#6a6f78` |
| 主强调色 `--u-accent` | `#2e7bf7` |
| 强调 hover `--u-accent-hover` | `#4a8df9` |
| 强调激活 `--u-accent-active` | `#2268db` |
| 强调亮色 `--u-accent-bright` | `#6fa3ff` |
| 成功 `--u-ok` | `#2bb673` |
| 警告 `--u-warn` | `#f0a228` |
| 危险 `--u-danger` | `#ee4d5a` |
| 细边框 `--u-line` | `rgba(236,239,243,0.1)` |
| 强边框 `--u-line-strong` | `rgba(236,239,243,0.18)` |
| 字体族 | `"Helvetica Neue", Helvetica, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", Arial, sans-serif` |
| 字号 XS/SM/MD/LG | 11 / 12 / 13 / 15 px |
| 标准按钮高度 | 32 px |
| 小按钮高度 | 28 px |
| 超小按钮高度 | 24 px |
| 标题栏高度 | 40 px |
| 状态栏高度 | 24 px |
| 工具栏高度 | 40 px |
| 紧凑行高 | 28 px |
| 标准行高 | 32 px |
| 圆角控件/按钮/卡片 | 4 / 6 / 8 px |
| 间距等级 | 4 / 8 / 12 / 16 / 24 / 32 px |

### 7.3 UniUni 各页面真实尺寸

| 页面/区域 | CSS/组件证据 | 实际尺寸/规则 |
|---|---|---|
| 全局标题栏 | `.app_titlebar` in `index-jE8MMGdA.css` | 高 40 px；左右 padding 12/8 px |
| 顶部导航项 | `.tb_nav_item` | 高 28 px；水平 padding 10 px；字号 12 px |
| 品牌字标 | `.tb_logo` | 14 px、700 字重、字距 0.3 px |
| 全局状态栏 | `.app_statusbar` | 高 24 px；左右 padding 12 px；字号 12 px |
| 地图左导航 | `MapNav` + `UPanel(width=220)` | 固定宽 220 px；图标 16 px |
| 轨迹页机器人列表 | `.robot_panel` in `index-CWOiJc7g.css` | 宽 260 px |
| 轨迹页任务列表 | `.task_panel` | 宽 310 px |
| 轨迹页主内容 | `.panel_body` | flex 剩余宽；gap 8 px；外边距 8px 12px 12px |
| 轨迹页参数栏 | `.panel_header` | padding 5px 10px；纵向 gap 4 px |
| 参数工具行 | `.toolbar_row` | gap 6 px；允许换行 |
| 参数分组 | `.ctrl_group` | padding 3px 8px；gap 4 px；圆角 6 px |
| 轨迹页机器人行 | `.rp_item` | padding 6px 8px；下边距 4 px；圆角 6 px |
| 任务面板标题 | `.task_panel_header` | 高 40 px；padding 8px 10px |
| 任务创建行 | `.task_panel_create` | padding 8px 10px；gap 6 px |
| 任务项 | `.task_item` | padding 6px 8px；圆角 6 px |
| 动作裁剪工具栏 | `.timeline_editor_wrapper .editor_operation` in `index-5z7WROpT.css` | 宽 90 px；背景 `#2a2b2e`；padding 8 px；gap 8 px |
| 动作裁剪频率选择 | `.freq_select` | 高 26 px；全宽；字号 11 px |
| 轨迹统计浮层 | `.stats_overlay` | 绝对定位右下 12 px；条目 gap 12 px |

### 7.5 将 UniUni 视觉系统落到 RDA 的规则

后续 RDA UI Prompt 必须优先复用 7.2 的 `--u-*` 值，而不是上一版自创的 `#0f172a/#1e6fff` 色板。建议在 Qt 中建立 `UniUniInspiredTheme` 集中样式表/Token 表，不要每个 QWidget 内写互相冲突的 inline stylesheet。

- 页面底色 `#060708`；主容器 `#0b0c0f`；面板 `#101114`；卡片 `#15161a`；输入控件 `#191a20`。
- 主文字 `#e4e6ea`，次文字 `#9ba0aa`，弱化文字 `#6a6f78`。
- 选中/主要动作使用 `#2e7bf7`，hover `#4a8df9`，active `#2268db`。
- 成功/警告/危险分别用 `#2bb673`、`#f0a228`、`#ee4d5a`。
- 常规按钮 32 px 高；紧凑工具按钮 28 px；超紧凑按钮 24 px。
- 控件圆角 4 px、按钮 6 px、卡片 8 px。
- 面板分组优先用 8 px gap，组内控件 4–6 px gap；保持留白，不堆叠多个相同功能入口。
- 选中态使用低透明度蓝色底和清晰边框；hover 只改变背景/文字，不改变控件尺寸。
- 禁用态降低不透明度并禁用点击；不要用灰色但仍可点击的假禁用状态。

### 7.6 RDA 当前窗口尺寸基准

RDA 已有 Qt 窗口实际设置：

- 主窗口默认 `1440×900`。
- 最小窗口 `1200×720`。
- 全局顶部导航高 `50 px`。
- 编排页内部 `TopShowHeader` 高 `56 px`。
- 全局底栏高 `30 px`。
- 编排页左/中/右 splitter 初始比例 `[280, 860, 360]`。
- 右侧 dock 最小宽度 `320 px`。
- 底部时间轴容器最小高 `220 px`，初始上下 splitter `[600, 280]`。

后续重构应以 1440×900 为设计基准，同时在 1200×720 下保证可用；不要把 1440×900 的像素值误当成 UniUni 原始窗口实测值。

## 8. 参考代码证据索引

| 证据文件 | 可验证内容 |
|---|---|
| `UniUni-1.0.2-setup.exe` PE VersionInfo | 产品名、版本、Electron + Vue + TypeScript |
| `.agent_workspace/out_src/out/renderer/assets/index-DRkqKZBV.js` + `index-jE8MMGdA.css` | 应用外壳、导航、状态栏、场景选择及真实 CSS |
| `.agent_workspace/out_src/out/renderer/assets/index-D8V4tJoK.js` + `index-DDpCtjMU.css` | 地图工作区、220px MapNav、地图子页面 |
| `.agent_workspace/out_src/out/renderer/assets/index-Bzj1CuRc.js` + `index-CWOiJc7g.css` | 轨迹规划页面、260px 机器人栏、310px 任务栏、参数工具条 |
| `.agent_workspace/out_src/out/renderer/assets/PreviewMapPanel-CNqgEJoF.js` + `PreviewMapPanel-CUMp5ZWI.css` | 2D/3D 地图预览、绘制、播放、地图自定义 |
| `.agent_workspace/out_src/out/renderer/assets/Index-C9SDLLs9.js` | Konva 时间轴分层、缩放、滚动、时间标记 |
| `.agent_workspace/out_src/out/renderer/assets/index-w2E8kWQ3.js` + `index-5z7WROpT.css` | 动作轨迹裁剪、90px 工具栏、频率、裁剪指针、导出 |
| `.agent_workspace/out_src/out/renderer/assets/index-Cv2Z0aI0.js` | 动作库、机器人库、动作详情、批量任务 |
| `.agent_workspace/out_src/out/renderer/assets/ActionManageDialog-DRZWDPpU.js` | 动作试运行、动作包络、曲线和批量操作 |
| `.agent_workspace/out_src/out/renderer/assets/index-BLeFS3an.css` | UniUni 完整 `--u-*` 设计 Token |

## 9. 禁止本地 Agent 再做的重复工作

- 不要让 Agent 再次逆向 UniUni 安装包。
- 不要让 Agent 重新发明 UniUni 的页面分区和工作流。
- 不要把本报告中 `已验证` 的组件树、导航分组和控件行为当成未知。
- Agent 只需要根据本项目实际窗口尺寸、Qt 控件能力，把本报告的交互结构实现到 RDA；若遇到本报告明确标记未验证的视觉细节，使用第 7.2 节 RDA 设计 token，不要阻塞开发。
