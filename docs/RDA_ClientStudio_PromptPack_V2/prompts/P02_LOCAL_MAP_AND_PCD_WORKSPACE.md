# P02 — 本地地图资产管理与 PCD 场地工作区

**阶段目标**：完善现有 `MapManagerPanel + StageMapController`，使地图成为当前工程可管理、可恢复、可在 2D/3D 一致显示的本地资源。

**前置**：P00、P01 COMPLETE。必须使用当前打开工程的项目 DB 和资源目录。

## 1. 先检查现有实现，优先修补而不是重写

本地逐项读取：

- `src/ui/map_manager_panel.py`
- `src/application/stage_director/stage_map_controller.py`
- `src/domain/map/stage_map_asset.py`
- `src/domain/map/grid_and_calibration.py`
- `src/domain/map/map_storage_service.py`
- `src/infrastructure/map/pcd_io_engine.py`
- `src/infrastructure/storage/stage_map_sqlite_adapter.py`
- `src/ui/choreo_page/stage_canvas_2d.py`
- `src/ui/choreo_page/map_canvas_renderer.py`
- `src/ui/stage3d/stage_viewport_3d.py`
- `src/core/storage_manager.py`

重点核对 MapManagerPanel 的 PCD loader 与 StageMapController 的 loader 是否为不同 API/不同数据结构。当前审计快照中 `StageMapController.import_pcd_file()` 使用 `PcdMapLoader`，而 `MapManagerPanel._load_selected_map()` 使用 `PcdLoader.load_pcd()` / `downsample()`；必须检查这两个类的实现，不能只根据名称推断兼容。

建立 `P02_MAP_PIPELINE_AUDIT.md`：记录导入、校验、复制、解析、数据库保存、列表刷新、加载、2D 栅格化、3D 点云显示、卸载和删除每一步具体调用的方法与数据类型。

## 2. 地图数据的权威契约

地图资产使用稳定 `map_id`，至少包含：

- `schema_version`
- `map_id`
- `project_id`
- `name`
- `file_path`（项目相对路径；绝对路径仅可作为运行时解析结果）
- `file_size_bytes`
- `point_count`
- `sha256`
- `pcd_encoding`（ASCII / binary / binary_compressed 等按实际支持范围）
- `bounds`：min/max x/y/z，单位 m
- `origin`：x/y/yaw
- `resolution`：m/cell
- `width` / `height`
- `created_at` / `updated_at`
- `is_valid` 或可计算的资源状态

点云数据统一为 `N×3` 浮点数组（如果仓库实际支持 intensity 等其他字段，应另外定义，不要丢失原始信息）。原始 PCD 文件必须保留；用于 3D 展示的下采样点云只是可重建的缓存，不能覆盖原始地图。

坐标契约必须在 2D 与 3D 两边一致：

- X/Y 是舞台世界坐标，单位米。
- Z 是高度，单位米。
- 2D 屏幕 Y 轴方向可能与世界 Y 轴相反，但只能在视图变换时转换。
- `origin`、`resolution`、栅格上下翻转和图像像素中心定义必须统一。
- 地图加载之后，2D 点击/轨迹绘制坐标必须落在正确世界坐标；3D 点云必须与 2D 同一位置/朝向。

将最终契约写入 `DATA_CONTRACTS.md`，不要在多个文件中各写一套隐含坐标变换。

## 3. 地图管理 UI

在 `MapManagerPanel` 内完善，而不是新建另一个地图管理页。左侧 Dock 的地图 Tab 必须展示项目内真实地图资产。

### 地图列表

每项至少显示：名称、点数、尺寸、更新时间、状态。状态区分：

- 已导入 / 可用
- 当前已加载
- 文件缺失
- 元数据不完整
- 校验失败
- 正在导入/解析

支持名称搜索/排序/刷新。没有地图时显示可操作空状态：“当前工程还没有地图，导入 PCD 文件以开始”。不能放入示例地图。

### 操作

必须实现并验证：

1. 导入本地 PCD。
2. 输入/修改地图显示名称。
3. 查看详情（路径、文件大小、编码、点数、边界、分辨率、hash）。
4. 预览地图范围/缩略图（可使用轻量 2D 预览图）。
5. 加载到 2D/3D 工作区。
6. 卸载当前地图。
7. 重命名。
8. 导出原始 PCD 到用户指定路径。
9. 删除地图。

删除前检查：是否是活动地图、是否被轨迹/场景/工程资源引用。禁止静默解除引用。若当前 Project 只允许删除未引用地图，则明确提示先解除引用；若提供“连同引用清理”则必须有确认和事务/备份。

### 导入流程

`选择文件 → 头部校验 → 编码/字段支持校验 → 文件 hash → 重复项检查 → 异步解析 → 展示解析摘要 → 用户确认名称 → 项目目录原子复制 → DB 元数据写入 → 地图列表刷新`。

- 重复文件必须区分“同一 PCD 文件已存在”和“允许作为副本导入”。
- 解析失败或 DB 写入失败时删除临时复制文件，不留下孤儿记录；原始源文件不动。
- 重命名不修改原始数据内容。
- 导入任务可取消；取消后不应将半截文件标为可用。
- 不允许 UI 冻结；PCD 读取、解析、下采样和 2D 栅格生成在 worker 中执行。

## 4. 2D 地图加载链路

使用当前工程唯一 `StageMapController`。`MapManagerPanel` 发出加载事件后，由应用层协调：

1. 传递 `map_id`，不要只传无法追溯的点数组。
2. 加载真实点云和元数据。
3. 使用 canonical `MapGridProcessor` 生成占据栅格。
4. 将 QImage + grid metadata + map identity 注入 `StageCanvas2D`。
5. 在视口中显示地图名称、分辨率、范围和当前坐标状态。
6. 轨迹编辑时，`screen_to_world` / `world_to_screen` 与地图 origin/resolution 一致。
7. 卸载地图必须清除 2D 视口地图缓存，但不能删除地图资产和已保存轨迹。

必须查清 `StageCanvas2D.set_grid_data()`、`load_map()`、`MapCanvasRenderer` 的实际坐标实现，消除重复转换或上下翻转两次的问题。

## 5. 3D 点云数据链路

加载同一 `map_id` 时，把点云和 metadata 传给 3D Viewport。不得另外扫描目录或从另一数据库读取地图。

- 原始点数与显示点数分开显示。
- 限制 UI 最大显示点数时，使用可重复的 voxel/downsample 策略；保存原文件原样。
- 视口可显示地图范围、原点、XYZ 轴和地面网格。
- 地图加载/卸载事件要同步 2D、3D、Inspector 与当前工程状态。
- 如果某个视图渲染失败，地图资产仍保持有效；错误应在 UI 显示，不能让地图 DB 记录被误删。

真正的高质量 3D 视口技术选型在 P07 完成；本 Prompt 只要让当前 3D 组件接收同一份地图数据并形成可验证接口。

## 6. PCD 格式与性能

1. 扫描仓库当前 loader 能力，明确支持的 `DATA` 编码、字段（x/y/z/intensity 等）、尺寸限制。
2. 对 `FIELDS`、`SIZE`、`TYPE`、`COUNT`、`WIDTH`、`HEIGHT`、`POINTS`、`DATA` 头部做严格验证。
3. 对 header 的 point count 与实际解码点数不一致情况给出错误/警告策略。
4. 处理空点云、NaN/Infinity、异常字段、截断文件、超大文件。
5. 使用 chunk / bounded memory；不得一次复制多份大数组导致内存翻倍。
6. worker 支持 progress、cancel、error；窗口退出时安全清理。
7. 下采样结果必须可追溯到源 map hash 与参数。

不要擅自宣称支持未实现的 PCD encoding。不能通过“try/except 然后返回空点数组”掩盖损坏文件。

## 7. 数据库与文件一致性

- Map metadata 和资源文件一致性要有校验服务。
- 导入顺序采用临时文件 → 验证 → 原子 rename → DB transaction；失败清理临时文件。
- 删除顺序要防止 DB 记录消失但文件仍残留或文件先删而 DB 留孤儿记录；必要时采用回收站/待清理记录。
- 工程导出时打包 map 相对路径及 hash；导入后更新路径引用，不允许引用原电脑绝对路径。
- 同一个 map_id 不得指向多个不同 hash 文件。

## 8. 测试矩阵

至少准备：合法 ASCII PCD、小型 binary PCD（若 loader 宣称支持）、空文件、头部损坏、字段缺失、点数不匹配、截断文件、NaN/Infinity、重复 hash、大文件取消。

### Must Pass

1. 导入合法 PCD 后 DB 记录和原始复制文件存在，hash 一致。
2. 重开工程后地图列表恢复。
3. 加载后 2D 和 3D 的 map_id、origin、bounds 一致。
4. 已加载地图不能被误删；卸载后按引用规则决定能否删除。
5. 导出 PCD 与源文件 SHA-256 完全一致（若导出定义为原始副本）。
6. 导入失败不产生孤儿文件/DB 记录。
7. 取消大文件导入后 UI 恢复可操作，临时文件清理。
8. 2D 世界坐标转换有单元测试，至少测试原点、边界、正负坐标与屏幕往返误差。
9. 重新打开工程和地图后数据没有串用其他工程。

## 9. 用户手工验收

- 导入一张真实 PCD，确认列表中的点数/尺寸/编码合理。
- 加载地图，观察 2D 栅格和 3D 点云是否在同一原点/方向。
- 在 2D 视图中记录地图内一个点的世界坐标；缩放/平移/切换视图后确认坐标仍一致。
- 卸载再加载，数据应恢复。
- 导出并计算 hash，与原始 PCD 比较。
- 删除仍被引用的地图，必须提示原因且数据保留。

## 10. 交付

提交代码、PCD 测试样本生成器/fixture、`P02_MAP_PIPELINE_AUDIT.md`、`P02_TEST_REPORT.md`、界面截图和更新后的 `SESSION_HANDOFF.md`。完成后进入 P03。
