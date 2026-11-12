# RobotDeploymentAssistant 架构与技术边界规范

> 最后更新：2026-11-12  
> 状态：Clean Architecture 分层边界与 StudioFacade 用例规范已固化 (Prompt 02)

---

## 1. 真实技术栈 [OBSERVED]

- **宿主语言**：Python 3.12+
- **Web 服务端**：Flask 3.1.3 + CORS，服务于主页导航、部署向导、API 转发
- **编导工作台**：PySide6 6.12.0 (Qt6 Widgets)，由主页 API 触发唤起独立进程/窗口
- **本地持久化**：SQLite 3 (`data/choreo_database.db`) + 原子 JSON 快照 (`data/`)
- **硬件与通信**：PySerial (串口下发)、LoRa/LRMP 协议包、Paramiko (SSH/SFTP 运维)
- **空间与模型计算**：NumPy, PCD ASCII/Binary 点云解析器, URDF/STL 关节运动学

严禁在未经过 ADR 批准的情况下引入 Electron/Vue 替换 Python+PySide6 架构。

---

## 2. 模块拓扑与依赖方向规范

```
[ UI Layer: PySide6 Widgets ]
       │
       ▼ (Strictly signals / slots; NO SQL, NO hardware direct calls)
[ Application Layer: StudioFacade / StudioDependencies / Coordinators ]
       │
       ▼ (Calls Pure Domain Services and Ports)
[ Domain Layer: Entities, Interpolators, Formations, LRMP Compiler ]
       │
       ▼
[ Infrastructure / Storage Layer: StorageManager, Serial, SSH ]
```

### 核心约束与合规审计 [OBSERVED]：
1. **Domain 独立性**：`src/core/models.py`、`src/core/formation_calc.py` 等领域纯计算模块严禁依赖 PySide6、Flask 或底层通信 SDK。
2. **UI 零 SQL**：全量扫描确认 `src/ui/` 目录下 0 处直接连接 SQLite。所有 UI 界面必须通过 `StudioFacade`（`src/application/studio/studio_facade.py`）调用标准 Use Cases。
3. **唯一 Composition Root**：`src/application/studio/studio_dependencies.py` 统管依赖创建、单例生命周期与窗口关闭时的 `dispose()` 资源释放。
4. **单例与无假数据**：运行时状态严格绑定真机连接与真实导入数据，禁止在启动时注入假机器人、假轨迹或演示片段。
