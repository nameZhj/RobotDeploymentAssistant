# P05 — 统一本地素材库、动作资源元数据与拖放数据契约

**阶段目标**：完善现有 `AssetLibraryPanel + AssetRegistry`，让动作/舞蹈/轨迹/阵型有稳定 ID、清晰的分类与来源，并能无歧义地拖入时间轴。此阶段不实现真实设备动作下发，只实现本地素材管理和预览所需数据。

**前置**：P00–P04 COMPLETE。

## 1. 先审计现有素材来源

阅读：

- `src/ui/asset_library.py`
- `src/core/asset_registry.py`
- `src/domain/simulation/dance_motion_library.py`
- `backend/serial_dance_parser.py`（只读取本地静态舞蹈目录/元数据的来源，不修改其设备通信逻辑）
- `src/infrastructure/storage/choreo_sqlite_store.py`
- `src/domain/trajectory/trajectory_asset.py`
- P01/P03/P04 的 Repository、资产 schema 和工程目录。

当前 GitHub `main` 静态快照中 `AssetRegistry`：

- 舞蹈来自 `DEFAULT_DANCE_GROUPS`；
- 基础动作来自 `DEFAULT_BASIC_ACTIONS`；
- 轨迹来自 `storage_manager.trajectories_dir/*.json`；
- 阵型来自 `storage_manager.formations_dir/*.json`；
- 输出以 `category` 标识类型。

`DraggableAssetListWidget.startDrag()` 将整个 dict 写入 MIME；但 `TimelineChoreoController.create_clip_from_dropped_asset()` 先读取 `asset_type`。如果没有适配，dance/action 可能被误分类成 trajectory。必须在代码中建立单一转换层，不能让时间轴再去猜字段。

## 2. 统一 Asset 模型

定义一个 canonical Asset Envelope（可用 dataclass/Pydantic/TypedDict，但必须适配项目实际依赖）：

```json
{
  "schema_version": 1,
  "asset_id": "stable-id",
  "asset_type": "DANCE",
  "name": "舞蹈/动作名称",
  "project_id": "project-id-or-null-for-bundled",
  "duration_ms": 5000,
  "source": {
    "kind": "BUNDLED|PROJECT_FILE|DATABASE",
    "ref": "resource-reference"
  },
  "preview": {
    "preview_kind": "JOINT_KEYS|TRAJECTORY|FORMATION|NONE"
  },
  "capabilities": {
    "timeline_action_layer": true,
    "timeline_trajectory_layer": false,
    "stretch_allowed": false
  },
  "metadata": {}
}
```

类型枚举至少：

- `DANCE`
- `ACTION`
- `TRAJECTORY`
- `GROUP_TRAJECTORY`
- `FORMATION`

禁止通过名称、图标、文件扩展名猜测类型。禁止 `category` 与 `asset_type` 同时作为两个独立真值。旧格式由一个 `AssetEnvelopeAdapter` 归一化。

每类素材的关键数据：

- Dance：alias、时长、可预览动作帧/动作源文件、适用 robot model。
- Action：名称、动作类型、duration、joint keyframe source 或明确 `preview_not_available`。
- Trajectory：trajectory_id、机器人目标信息、长度/时长、坐标单位、文件/DB ref。
- Group Trajectory：group_trajectory_id、成员 ID、群组轨迹数据引用。
- Formation：formation_id、成员数量、阵型类型；除非明确实现“阵型变换 Clip”，否则不直接作为普通时间轴轨迹 Clip。

## 3. 素材来源分类

区分三类：

1. **Bundled Assets**：仓库/安装包自带且有明确本地来源的静态舞蹈/动作目录。可只读，不归当前工程所有。
2. **Project Assets**：用户在当前项目创建/导入的轨迹、阵型、动作资源，归当前工程。
3. **Cached/Derived Assets**：预览帧缓存、缩略图、采样曲线，随时可重建，不作为数据真源。

AssetRegistry 不应把无法定位真实帧/模型的占位记录伪装为可预览资产。若动作仅有命令字符串而无本地关节帧，标记 `preview_not_available`；本轮不要执行该命令。命令字符串只作为历史 metadata 保存，不连接设备。

`DEFAULT_BASIC_ACTIONS` 是否保留由本地审计确定：若确实是产品内置动作定义，可保留为只读本地目录项；但不能因存在 `cmd` 字段而显示“执行”按钮，或把它们当作可供 3D 播放的真实关节动画。动作帧缺失时显示资源缺失状态。

## 4. 素材库 UI

沿用 `AssetLibraryPanel` 和左侧素材 Tab。完善：

- 顶部搜索框：名称、别名、ID、标签、动作类型。
- 分类 Tab：舞蹈、动作、单机轨迹、群组轨迹、阵型。
- 列表每项显示名称、分类、时长/成员数、来源标记、是否可预览。
- 右侧或下方详情区域：完整 metadata、资源路径/引用、模型适配、预览状态。
- 刷新按钮：仅刷新本地目录/Repository；错误时保留上次列表并显示告警。
- 空状态、无搜索结果、资源缺失、格式错误、加载中均有对应 UI。
- 项目切换后，Project Assets 只显示当前工程资源；Bundled Assets 保持只读全局资源。

所有条目使用稳定 `asset_id`，不能依赖排序后的列表下标。

## 5. 本地预览

- 若 Dance/Action 有真实 joint keyframe，显示动作缩略预览或打开预览弹窗；复用 P07 统一动作采样器。
- Trajectory 展示 2D 缩略图/控制点摘要；单击可在主舞台定位并选择该轨迹。
- Formation 显示阵型示意缩略图；单击载入阵型面板。
- 无帧数据时显示“没有本地预览帧”，不能生成随机骨架动画或伪造缩略图。
- 预览不写数据库，不改变当前项目数据；明确区分“选择素材”和“应用到工程”。

## 6. Drag & Drop：建立无歧义的单一数据流

`DraggableAssetListWidget.startDrag()` 仅调用一个统一 `serialize_asset_envelope()`，使用一个正式 MIME 类型，例如：

`application/x-rda-stage-asset+json`

旧 MIME `application/x-robo-choreo-asset`、`application/x-choreo-asset` 可在迁移期只读兼容，但新写入只使用 canonical schema。

时间轴收到 drop 后：

1. 检查 MIME 类型和 schema_version。
2. JSON parse。
3. `AssetEnvelopeAdapter.from_legacy()` 只负责兼容旧字段；不能吞异常。
4. 校验 asset_id 和 source ref 在当前工程/内置素材库中真实存在。
5. 校验素材类型与目标轨道的兼容性。
6. 生成 `TimelineClipAsset`（P06 中完善）。
7. 业务持久化成功后接受 drop；失败时拒绝并提示原因。

轨道规则：

| asset_type | ACTION 子层 | TRAJECTORY 子层 | GROUP 轨道 |
|---|---|---|---|
| DANCE | 允许 | 禁止 | 禁止，除非明确设计群组同步动作 Clip |
| ACTION | 允许 | 禁止 | 按模型/群组能力明确，不得默认允许 |
| TRAJECTORY | 禁止 | 允许 | 禁止 |
| GROUP_TRAJECTORY | 禁止 | 禁止 | 允许 |
| FORMATION | 默认禁止 | 默认禁止 | 仅在实现专属 Formation Clip 后允许 |

禁止一个 DANCE 因没有 `asset_type` 而落入 TRAJECTORY。禁止单机器人轨迹落入 GROUP，禁止群组轨迹落到个人机器人轨道。

## 7. 轨道绑定和目标解析

- `asset_id` 是素材库 ID；`ref_id` 是领域资源 ID；两者不能混用。
- 时间轴 Clip 必须保存 asset_type、asset_id/ref_id、target robot/group、duration、start_ms、layer、schema_version。
- 轨迹素材放入轨道时，根据轨迹的 target metadata 校验当前轨道是否匹配；支持用户明确重新绑定目标机器人，但必须在 drop 前/后给出预览确认。
- Dance/Action 可指定 robot model compatibility。当前 RobotInstance 的 `model_id` 不支持该动作时提示，不可静默放入。
- 资源改名不应破坏 Clip 引用；删除素材前检查是否被 Clip 引用。

## 8. 测试

至少测试：

1. Registry 四/五类素材返回稳定 ID、category/type 统一。
2. 已知内置舞蹈的真实来源 metadata 及预览能力正确。
3. 没有本地帧的动作不会显示“可预览”。
4. `DANCE` drop 到 ACTION layer 成功；drop 到 TRAJECTORY layer 失败。
5. `TRAJECTORY` drop 到 TRAJECTORY layer 成功；ACTION layer 失败。
6. `GROUP_TRAJECTORY` 只能进入 GROUP track。
7. 缺 asset_id、错误 schema_version、未知 source ref、损坏 JSON 拒绝。
8. 旧 MIME/旧 category 数据可被兼容转换，转换结果不会误分类。
9. 项目切换后素材引用不会跨工程串用。
10. 删除被 Clip 引用的资源会按约定阻止或安全解除引用。

## 9. 用户手工验收

- 打开素材库，确认分类、搜索、详情和来源标记正确。
- 选一个真实有动作帧的舞蹈进行本地预览；选一个无帧的基础动作，确认显示不可预览原因。
- 拖入舞蹈到 ACTION 子层，应生成正确的动作 Clip。
- 故意拖入轨迹到 ACTION 子层，应明确拒绝。
- 切换工程后确认只显示当前工程轨迹/阵型。

## 10. 交付

统一 Asset Envelope、Registry/Repository、UI 详情与预览、MIME 适配器、拖放测试、`P05_TEST_REPORT.md`。完成后进入 P06。
