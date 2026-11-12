# PROMPT 05 — 地图资源管理、PCD 导入解析与 2D/3D 地图加载

> **类型：地图功能完整实现。** 本阶段让用户能管理真实地图文件，并把同一份地图可靠地加载到现有 2D/3D 视口。不得生成默认点云，不得把“导入成功”做成只写一条数据库记录。

## 0. 前置条件

Prompt 04 的 MapAsset 模型、canonical DB、Repository、schema version 与文件存储根目录必须已经落地。Prompt 02 的地图 service 和 worker 线程策略必须已确定。

先读取当前 PCD parser、地图资源目录、3D renderer、坐标转换代码和兼容性矩阵。不得按文档猜测坐标轴或 PCD 格式能力。

## 1. 本阶段交付范围

必须完成：
1. 地图资源列表与详情；
2. `.pcd` 导入流程（其他格式仅当当前 parser 已支持，或 ADR 批准后加入）；
3. 文件头预览、格式校验、异步解析、进度与取消；
4. 地图元数据、hash、磁盘资源的可靠保存；
5. 地图加载到 2D 画布；
6. 地图加载到现有 3D 视口；
7. 设置/取消场景当前地图；
8. 重命名、导出副本、删除（引用保护）；
9. 缺失文件检测与修复提示；
10. 对大地图进行显示降采样，但原始文件必须完整保留。

不做：
- 远程云端地图同步；
- 自动 SLAM；
- 遥控机器人在线建图；
- 机器人导航路径规划；
- PCD 上传到远端服务器；
- 自动把用户地图重采样并覆盖原始数据。

## 2. 现有 PCD parser 能力核实

先检查 `PcdParserEngine` 与所有调用点：
- 支持的 header fields；
- `DATA ascii`；
- `DATA binary`；
- `DATA binary_compressed`；
- FIELDS/SIZE/TYPE/COUNT；
- WIDTH/HEIGHT/POINTS；
- VIEWPOINT；
- XYZ、intensity、rgb/rgba 等字段；
- NaN/Inf 处理；
- endian；
- 压缩算法；
- 大文件内存占用。

对每种格式建立独立 fixture。只有实测 parser 成功、数据值正确，才允许 UI 声称支持。不得把不支持格式的错误吞掉后创建空地图。

如果当前 parser 只支持 ASCII：
- 本阶段先完整实现 ASCII 导入；
- binary/binary_compressed 显示明确“不支持此编码”；
- 可在 ADR 中评估补充支持，但不能用错误解析作为临时实现。
如果 parser 支持更多编码，逐项加回归测试。

## 3. 地图管理页面布局

入口使用 03 已完成的 `导航地图` 页面或项目现有 Map Management 入口。不得另开第二个地图管理窗口，除非当前交互明确需要模态对话框。

建议区域：

```text
┌──────────────────────────────────────────────────────────────────┐
│ 地图资源                                        [导入 PCD] [刷新] │ 40px
├──────────────────────────────────────────────────────────────────┤
│ 搜索地图...   [场景过滤] [状态过滤]                               │ 36px
├──────────────────────────────────────────────────────────────────┤
│ 地图名称 | 文件 | 点数 | 格式 | 大小 | 状态 | 更新时间 | 操作     │
│ ...                                                              │
├──────────────────────────────────────────────────────────────────┤
│ 选中地图详情：元数据、坐标系、边界、文件 hash、错误信息           │
└──────────────────────────────────────────────────────────────────┘
```

控件规格：
- 标题栏高 40 px。
- 操作按钮高 28 px。
- 搜索框高 30 px，宽 240 px。
- 表格行高 36 px。
- 列宽按内容分配：名称 20%、文件名 18%、点数 10%、格式 8%、大小 10%、状态 10%、更新时间 16%、操作 8%。
- 主背景/字体/token 复用 Prompt 03 的 Theme。
- 不得显示没有 handler 的按钮。

列表列字段：
1. 地图名称；
2. 源文件名；
3. 点数（未知显示 `--`）；
4. 编码（ASCII/BINARY/BINARY_COMPRESSED/UNKNOWN，按解析器结果）；
5. 文件大小；
6. 状态；
7. 更新时间；
8. 操作菜单。

状态显示：
- READY：绿色状态点 + “可用”；
- IMPORTING：蓝色 spinner + “导入中”；
- FAILED：红色状态点 + “导入失败”，详情含 error code；
- MISSING：橙色状态点 + “文件缺失”；
- UNKNOWN：灰色状态点 + “状态未知”。

筛选只作用于查询视图，不修改 DB：
- 场景；
- 状态；
- 名称/源文件名。

空状态：
- 无地图：“尚无地图。点击导入 PCD 添加一张地图。”
- 无搜索结果：“没有符合条件的地图。”
- 加载失败：“地图文件无法读取。查看详情中的具体错误。”

## 4. 导入 PCD 流程

点击 `[导入 PCD]` 后：

### Step A：选择文件

`QFileDialog.getOpenFileName`：
- 默认目录：上次使用目录（存在并可读时）；否则用户文档目录。
- filter 只包括经验证支持的格式；如果只支持 PCD，使用 `Point Cloud (*.pcd)`。
- 取消选择不改变 UI 或 DB。
- 选择文件后验证文件存在、可读、非空。

### Step B：文件预检

在 worker 中读取 header，不要一次性将大文件读进 UI 主线程。

展示预检信息：
- 文件名、绝对文件大小；
- PCD VERSION；
- FIELDS / SIZE / TYPE / COUNT；
- WIDTH / HEIGHT / POINTS；
- DATA 编码；
- VIEWPOINT；
- parser 是否支持；
- 警告（字段缺失、点数与宽高不一致、无 XYZ）。

错误情况：
- header 结束标记缺失；
- FIELDS/SIZE/TYPE 不匹配；
- WIDTH/HEIGHT/POINTS 为非法负数；
- 文件截断；
- XYZ 不存在；
- 所有 XYZ 都无效；
- 编码不支持；
- 超过可配置内存预算。

不支持的 header 必须停止导入，不能写入 MapAsset READY。

### Step C：导入确认对话框

显示：
- 地图名称（默认文件名去扩展名，可编辑）；
- 来源文件名；
- 编码与点数；
- 文件大小；
- 坐标原点/VIEWPOINT（存在才显示）；
- 场景归属；
- “导入后设为当前场景地图” checkbox（仅在有场景时可选）。

按钮：
- 取消：不写正式资源。
- 导入：进入后台导入任务。

### Step D：后台处理和持久化

1. 创建 import job id。
2. DB 插入 MapAsset，状态 IMPORTING。
3. 文件复制到项目配置的 managed map directory 的 staging 子目录。
4. 计算 SHA-256。
5. 解析点云并做完整性核验。
6. 根据显示预算生成 preview/downsample cache；不能修改源文件。
7. 将文件从 staging 原子移动到正式资源路径。
8. 更新 DB 元数据，状态 READY。
9. 若用户勾选，调用 `set_scene_active_map`。
10. 发出 Qt signal 通知 UI 刷新列表和视口。

失败时：
- 删除本次 job 创建的 staging/cache 临时文件；
- MapAsset 状态设 FAILED，保留错误码与用户可读原因；
- 不删除此前已存在的正式地图；
- 不改变当前场景地图；
- 不显示“导入成功”。

取消时：
- 检查 worker cancellation token；
- 停止后续处理；
- 清理 staging 文件；
- job 标记 CANCELLED 或项目明确的取消状态；不得假装 READY。

### Step E：重复地图检查

SHA-256 已存在：
- 弹出“该地图文件已存在”；
- 显示已有地图名称和创建日期；
- 操作：取消 / 使用已有地图 / 仍导入副本。
- 使用已有地图不得复制文件，不得生成重复资源记录；只可切换当前 active map。
- 仍导入副本要使用新 map_id，文件内容可去重引用，但不能覆盖现有文件。

## 5. 大地图性能与内存要求

- 主线程不执行大文件解析、复制、hash、降采样。
- worker 有明确进度阶段：header / copy / hash / parse / preview / persist。
- 进度可为 indeterminate，不得编造百分比。
- 取消在每个可中断阶段检查。
- 根据实际可用内存和项目性能评估制定 preview 点数预算，写入 ADR/配置；不能在代码中散落固定 12000 点常量。
- 原始地图始终保留全部点和原始 encoding。
- preview cache 必须带 map SHA-256/算法版本，地图文件变化后自动失效。
- 降采样不能改变原始地图 metadata。
- 解析结果应避免创建 Python 对象列表保存数百万点；优先采用 NumPy 连续数组/分块。
- 若 renderer 接收的数组有 dtype/shape 限制，集中在 adapter 转换，不在多个 UI 中重复转换。

## 6. 2D 与 3D 加载契约

定义/复用 `MapLoadResult`，至少包括：
- map_id；
- source_sha256；
- point_count_original；
- point_count_rendered；
- coordinate_frame_id；
- distance_unit；
- bounds；
- preview_data 或渲染层可消费的 handle；
- warning list。

2D：
- 加载当前地图时，先清除旧地图渲染层，再显示新地图；失败不得留下“旧地图 + 新地图标题”的不一致状态。
- fit-to-content 使用实际 bounds。
- 鼠标坐标按坐标变换显示。
- 地图显示与机器人/轨迹是独立 layer；隐藏地图不能清除轨迹。
- map layer 的可见性与数据加载状态分离。

3D：
- 复用现有 `StageViewport3D`。
- 以 MapLoadResult 的真实点数据或 render handle 更新地图层。
- 不能因切换 2D/3D 重新解析原始 PCD。
- 切换视图保留当前 map_id、相机状态和可见性配置。
- 3D 加载失败时保持当前视图可用并显示明确错误。

## 7. 地图详情与操作

详情面板显示：
- 名称；
- 源文件名；
- 格式/编码；
- 文件大小；
- 点数；
- WIDTH × HEIGHT；
- fields；
- VIEWPOINT；
- 坐标系/单位；
- bounds；
- SHA-256；
- 导入时间；
- import state 和 error。

操作：
- 加载：设置工作区当前地图。
- 设为场景地图：写 active_map_id。
- 重命名：仅改 display_name，不改 source_filename/hash。
- 导出副本：复制原始文件到用户指定位置，不能导出 downsample cache 代替源文件。
- 删除：确认后检查 Scene、Trajectory 等引用；若仍被引用，提供“取消”或先解除引用的明确流程；不能 cascade delete。
- 定位文件：仅当操作系统打开文件位置实现可用时显示。
- 修复文件：允许用户重新定位源文件；校验 SHA-256 或提供“文件内容不同，作为新地图导入”，不得默默替换。

## 8. 地图存储安全与路径规范

- DB 存相对 managed URI，路径由一个 MapStorage service 解析。
- 禁止直接信任 JSON/DB 中的任意绝对路径；解析后必须确保路径仍在 managed root 内，防止 `../` 路径逃逸。
- 文件写入 staging，再 atomic replace。
- 用户指定导出路径前不覆盖；覆盖前显式确认。
- 不在日志记录地图绝对路径中的敏感用户名信息（可记录脱敏后的 relative path）。
- 同时处理 Windows 路径分隔符和 Unicode 文件名。
- 删除地图记录与物理文件分成有审计的两个动作；物理删除失败时保留 MISSING/DELETE_PENDING 之类明确状态，不能留下 DB 假成功。

## 9. 测试验收

### Parser tests
- 至少针对当前声明支持的每一种 PCD encoding 建立真实格式 fixture。
- 各 fixture 测试 point count、XYZ 数值、bounds、VIEWPOINT、字段 dtype。
- 文件截断、坏 header、缺 XYZ、全 NaN、binary length 不足都应报稳定错误。
- 同一个 fixture 多次解析结果一致。

### Import tests
- 成功导入后文件存在、hash 正确、DB READY。
- 中途取消清理 staging。
- 磁盘写入失败时不切换 active map。
- 重复 hash 三种用户选择行为正确。
- 用户文件被移动/删除后列表显示 MISSING。
- 恶意 `../` URI 被拒绝。
- Unicode 路径可用。

### UI tests
- 导入取消无副作用。
- 预检信息准确显示。
- 导入期间 UI 可拖动、可关闭；关闭窗口取消/释放 worker。
- 导入进度状态准确，不伪造百分比。
- 导入成功后列表和当前 map header 同步。
- 地图列表过滤不修改 DB。
- 删除有引用地图时不能静默删除。

### Rendering tests
- 2D/3D 加载相同 map_id 和 source hash。
- 2D fit bounds 正确。
- 切换 2D/3D 不重复解析。
- 显示/隐藏地图不影响机器人层和轨迹层。
- 空地图和无效地图不能生成默认点云。

## 10. 交付

- MapAsset repository/service；
- PCD header parser 与实际支持矩阵；
- 异步 import worker；
- managed map storage；
- 地图管理 UI；
- 2D/3D MapLayer adapter；
- preview cache 与版本/hash 机制；
- parser/import/UI/render tests；
- `docs/agent-prompt-pack/audit/05-maps/` 下测试数据和截图；
- 对未支持 encoding 和性能限制的明确说明。

本阶段不实现新的轨迹编辑交互。完成后更新状态文件和 SESSION_HANDOFF。
