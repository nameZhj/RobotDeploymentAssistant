# PROMPT 01 — 旧功能兼容性基线与回归测试工程化

> **本 Prompt 的工作类型：测试工程化 + 兼容性保护。不是 UI 重画，也不是继续清理舞台编导。**  
> 本阶段必须在真实 RDA 仓库中建立可执行证据，证明 2026-10-01 之前已有的正确功能在后续重构期间不会退化。

## 1. 本阶段要交付的代码结果

你需要实际创建/修改测试代码和测试数据，不得只写报告。

优先建立以下测试目录（如果项目已经有等价目录，扩展现有目录，不要重复创建第二套）：

```text
tests/
├── compatibility/
│   ├── conftest.py
│   ├── test_homepage_entry_contract.py
│   ├── test_flask_api_contracts.py
│   ├── test_robot_transport_contracts.py
│   ├── test_ssh_sftp_contracts.py
│   ├── test_license_contracts.py
│   ├── test_map_data_contracts.py
│   ├── test_3d_preview_contracts.py
│   └── test_studio_launch_contracts.py
├── fixtures/
│   └── compatibility/
│       ├── README.md
│       ├── robot_status/
│       ├── map/
│       ├── trajectory/
│       └── license/
└── reports/
```

新路径是建议，不是要求机械创建；先检查真实 `tests/` 结构并复用已有测试框架。

## 2. Git 保护边界：按真实历史建立，不按压缩包猜

归档快照中的 Git 信息已经分析到：

- 分支：`master`
- 上传快照 HEAD：`a5973d498ea43ffe6d5dae56f715935a7ffefcfb`
- HEAD 日期：2026-09-11
- 归档中能看到 19 条提交
- 上传快照不是干净工作区，已有大量已跟踪修改及未跟踪文件

但你的实际工作区可能比 RAR 新。因此你必须在当前工作区重新执行命令，把当前结果写入 `docs/agent-prompt-pack/audit/01-compatibility/`：

```powershell
git rev-parse --show-toplevel
git status --short --branch
git branch -avv
git tag --list
git log --all --date=iso-strict --pretty=format:"%H|%ad|%D|%s"
git log --all --since="2026-10-01 00:00:00" --date=iso-strict --pretty=format:"%H|%ad|%D|%s"
git log --all --until="2026-10-01 23:59:59" --date=iso-strict --pretty=format:"%H|%ad|%D|%s"
git log --all --name-status --find-renames
git status --porcelain=v2
```

必须将 `2026-10-01` 当作**旧功能保护时间边界**，但判断功能是否正确还要看测试、实现、运行证据，不得把“旧 commit 存在”直接等同于“功能已正确”。

如果当前工作区没有 `.git`：
- 不得 `git init` 后伪造历史；
- 不能仅凭 RAR 内 `.git` 宣称已经核验当前工作区；
- 将归档 Git 作为参考证据，当前真实历史标记为 `UNAVAILABLE`；
- 继续建立行为测试，但不能生成伪造 commit hash。

## 3. 在任何改动前做可恢复备份

在项目根目录外创建唯一备份目录，例如：

```text
<项目根目录同级>/
└── RDA_compatibility_backup_YYYYMMDD_HHMMSS/
    ├── git-bundle/
    ├── tracked-diff.patch
    ├── staged-diff.patch
    ├── untracked-manifest.txt
    ├── dirty-files-copy/
    ├── database-copy/
    └── backup-sha256.txt
```

操作要求：

1. `git bundle create` 保存 Git 可达历史。
2. 保存 `git diff --binary` 和 `git diff --cached --binary`。
3. 把全部未跟踪文件按相对路径复制到备份。
4. 复制 `runtime/` 中所有数据库、用户上传地图、动作文件和项目文件。
5. 对备份清单计算 SHA-256。
6. 比较备份前后文件数量和 hash。
7. 不允许用 `git stash` 作为唯一备份；不允许 `reset --hard`、`clean -fd`、force push、自动 rebase。

只有备份验证通过，才允许建立测试文件或修改配置。

## 4. 建立旧功能保护矩阵

创建：

`docs/agent-prompt-pack/state/COMPATIBILITY_MATRIX.md`

如果不存在，先从 `templates/state/COMPATIBILITY_MATRIX.md` 创建。

每行至少包含：

| 字段 | 说明 |
|---|---|
| ID | 稳定编号，例如 `LEGACY-001` |
| 功能 | 用户可见功能 |
| 最早证据提交 | 2026-10-01 前的 commit |
| 主要入口文件 | 路由/按钮/窗口 |
| 核心实现文件 | Service/Controller/Adapter |
| 外部依赖 | HTTP、串口、SSH、数据库、模型文件等 |
| 输入契约 | 参数、文件格式、设备消息 |
| 输出契约 | 返回值、UI 状态、文件/数据库 |
| 当前状态 | PASS / FAIL / NOT TESTED / UNKNOWN |
| 测试方法 | 自动化测试或手工步骤 |
| 风险 | 重构时可能破坏的点 |

至少覆盖以下旧功能族；真实代码中不存在的功能应标记 `NOT_FOUND_IN_CURRENT_WORKTREE`，不能编造：

1. Flask Web 应用启动、主页加载和页面静态资源。
2. 主页“舞台编导”入口和 `/api/system/open-studio`。
3. 机器人设备发现、在线状态和状态数据刷新。
4. 远程控制/遥控命令入口。
5. 串口、LoRa、LRMP 通信。
6. SSH/SFTP 连接、文件上传下载。
7. License/授权校验。
8. 地图/PCD 读入与坐标转换。
9. URDF/STL 机器人模型载入。
10. 原有 3D 舞蹈/运动预览。
11. 设备部署/任务流程。
12. 用户数据、SQLite 文件和配置迁移。
13. 程序启动、关闭、日志、异常恢复和打包入口。

## 5. 为每种旧功能建立可执行行为契约

### 5.1 首页和舞台编导入口

新建/扩展 `test_homepage_entry_contract.py`：

- Flask `GET /` 返回 200。
- 主页响应中恰好存在一个 `id="btn-open-studio-window"`。
- 主页静态资源加载路径有效。
- `POST /api/system/open-studio` 返回 JSON。
- 正常启动时包含 `success: true` 和真实消息字段。
- 启动失败时返回 `success: false` 或项目既有错误结构，不得假成功。
- 连续调用 3 次不得创建 3 个 `StudioMainWindow`。
- 如果 Qt 环境不能 offscreen 创建窗口，测试必须明确 skip 原因，不能假装通过。

### 5.2 机器人通信

扩展 `test_robot_transport_contracts.py`：

- 为真实 serial/LoRa/LRMP adapter 定义 fake transport，不访问真实串口。
- 验证连接、发送、接收、超时、断开、重连、异常关闭。
- 验证现有命令字节、包头、校验、字段单位与历史实现一致。
- 测试应从现有协议实现读取常量，不要重新抄写另一套魔法数字。
- 不得在测试里 mock 掉被测业务逻辑本身；只 mock 物理端口。

### 5.3 SSH/SFTP

扩展 `test_ssh_sftp_contracts.py`：

- mock SSH server/client，测试连接失败、认证失败、上传、下载、目录创建、路径不存在、权限拒绝、连接中断。
- 检查远端路径拼接不会丢失 Windows/Linux 路径语义。
- 检查上传失败时本地文件不被删除。
- 检查凭据不写入日志。

### 5.4 License

扩展 `test_license_contracts.py`：

- 合法授权、过期授权、签名无效、文件缺失、机器码不匹配、网络不可用。
- 记录原有功能行为，不重写加密算法。
- 不允许把授权检查改成固定返回 true。
- 测试证书/授权 fixture 使用明确的测试密钥，不能复制真实生产密钥。

### 5.5 地图与 3D

扩展 `test_map_data_contracts.py` 和 `test_3d_preview_contracts.py`：

- PCD 文件能解析的既有格式必须继续能读。
- 原有坐标原点、轴向、单位和旋转约定要用 fixture 固定。
- URDF/STL 模型资源路径解析和缺失文件错误行为必须有测试。
- 3D 预览无模型时给出可解释错误，不能静默创建假机器人。
- 渲染测试不能只断言 QWidget 创建成功；至少断言解析出的关节/几何数量或场景对象数量。

## 6. 测试数据规则

所有虚构数据只能放在 `tests/fixtures/`，且文件名带 `fixture_` 或 `test_`。不要把测试数据写入 `runtime/` 的默认生产数据库。

每个 fixture 提供：
- 来源说明（合成/脱敏/真实格式样本）；
- schema 版本；
- 预期字段；
- 生成脚本（可复现）；
- SHA-256；
- 不得用于生产 UI 默认数据的声明。

## 7. 执行顺序

1. 保存 Git 和文件备份。
2. 运行当前完整测试，保存首轮失败报告。
3. 建立保护矩阵。
4. 为目前已有测试覆盖不到的旧功能补 characterization tests。
5. 只允许为测试注入依赖/隔离硬件访问，不改变业务算法。
6. 运行新增测试。
7. 逐项执行 1–13 功能族回归。
8. 检查测试没有误删或改写用户数据库。
9. 生成覆盖率报告；如果项目未配置 coverage，可以评估后再引入，不要把 coverage 当本阶段唯一质量指标。

## 8. 允许修改与不允许修改

允许：
- 新增测试文件、fixture、测试工具。
- 为硬件 adapter 增加可注入 transport seam，但不能改变现有协议行为。
- 为已有功能增加可观察日志。
- 修复被测试证明的回归缺陷，前提是修复范围最小且不改变成功路径契约。

暂不允许：
- 重新设计舞台编导 UI。
- 更换 Flask、PySide6、SQLite。
- 改写 serial/LoRa/LRMP 协议。
- 修改旧功能的默认参数/单位/错误语义而没有明确迁移兼容。
- 删除旧功能模块。
- 将测试环境中的 mock 行为带入生产运行路径。

## 9. 完成验收

本阶段结束时必须提供：

- `COMPATIBILITY_MATRIX.md` 已填充，不能留空白行。
- 每个旧功能族都有 PASS/FAIL/UNKNOWN 状态。
- 关键旧功能至少有自动化测试或有脚本化手工步骤。
- 备份可验证，恢复演练至少在临时目录执行一次。
- 当前旧功能基线测试可重复运行。
- 没有将 mock 数据写入生产 DB。
- 所有测试命令和输出保存至 `docs/agent-prompt-pack/audit/01-compatibility/`。
- 明确列出尚无法验证的硬件功能及原因。

结束时更新状态文件并写 SESSION_HANDOFF。此阶段只建立兼容性保障，不顺手启动 02 的架构重构。
