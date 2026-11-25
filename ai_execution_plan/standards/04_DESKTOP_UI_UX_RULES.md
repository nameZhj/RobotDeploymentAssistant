# 桌面端 UI/UX 开发规范 (PySide6)

> 何时阅读：在 `upper_computer/src/ui/` 或 `src/viewport3d/` 开发面板、弹窗、绘图或交互时必读。
> 前置文档：[03 Python 编码规范](03_PYTHON_CODING_RULES.md)。
> 要点速览：1) 复用 `design_system` 原语与 `tokens.py`，严禁文本截断；2) 商业级极简文案，必要操作说明收拢至右上角 `?`；3) 严格单一提示机制、离屏安全及定时器/控件生命周期清理。

---

## 1. 设计系统组件与视觉令牌

- **控件统一复用**：构建界面 **MUST** 优先采用 `src/ui/design_system/` 原语，保持与 UniUni v3 规范一致：
  - 按钮/标签/提示：`UButton`, `UIconButton`, `USegmented`, `UBadge`, `UHelpIcon`（`u_buttons.py`）
  - 容器与表格：`UPanel`, `UCollapsibleGroup`, `UTable`, `UEmpty`（`u_panels.py`）
  - 浮层与输入：`UDialog`, `UDrawer`, `UFloatBar`（`u_dialog.py`）、`UInputNumber`, `UTimeInput`, `USearchInput`, `USelect`（`u_inputs.py`）
- **色彩令牌**：颜色、边框与字体常量 **MUST** 从 `src/ui/design_system/tokens.py` 导入（如 `C_CANVAS`, `C_BASE`, `C_PANEL`, `C_CARD`, `C_ACCENT`, `C_OK`, `C_WARN`, `C_DANGER`, `C_TEXT_1`, `C_TEXT_2`, `LINE`），**MUST NOT** 自行硬编码色值。
- **零文本截断**：所有按钮与标签尺寸 **MUST** 满足内容宽度（`width() >= sizeHint().width()`），不得出现省略号或文字裁切。

---

## 2. 商业级极简文案与右上角 `?` 提示

- **标题简洁**：面板与弹窗标题 **SHOULD** 控制在 `<= 10` 个汉字内，**MUST NOT** 在标题中堆砌通信协议、端点路径、端口或调试备注（例如写“动作库”而非“动作库 (Wi-Fi HTTP 同步)”）。
- **按钮与空状态**：按钮文本 **SHOULD** 以动词开头且尽量 `<= 8` 字；空状态文案（`UEmpty` 或画布占位）**MUST** 精简为单行短句。
- **消除正文说明块**：卡片、抽屉或弹窗主体内 **MUST NOT** 放置多行操作说明 `QLabel` 或底部文字横幅；必要操作指南 **MUST** 放入标题栏**最右侧圆形 `?` 悬浮提示**：
  - `UPanel(..., help_text="...")` 或在标题栏右侧按钮全部加入后调用 `panel.set_help_text("...", title="...")`（确保 `?` 始终位于最右上角）；
  - `UDialog(..., help_text="...")` / `UDrawer(..., help_text="...")` / 独立 `UHelpIcon`。
- **单一提示机制（防双弹窗）**：同一控件 **MUST NOT** 同时绑定系统原生 `setToolTip` 与自定义悬浮弹窗；`UHelpIcon` **MUST NOT** 调用 `self.setToolTip(...)`，否则悬停会触发双弹窗。

---

## 3. 性能、内存释放与离屏安全

- **数据节流与降采样**：实时轮询或 `QTimer` 刷新周期 **MUST** 匹配下位机 ROS 真实发布频率，**MUST NOT** 人为高频空转或伪造插帧；大点云渲染 **MUST** 先体素/步长降采样（`pcd_parser.py` / `stage_viewport_3d.py`）防内存溢出与卡顿。
- **生命周期清理**：动态移除列表子项时 **MUST** 调用 `widget.deleteLater()`；页面/弹窗关闭或隐藏时 **MUST** 停止 `QTimer`、取消事件订阅并在 `leaveEvent` / `hideEvent` / `destroyed` 时隐藏并清理悬浮层（如 `_HelpPopupCard`）；**MUST NOT** 维护无边界增长缓存。
- **离屏安全**：所有弹窗定位逻辑 **MUST** 兼容 `QT_QPA_PLATFORM=offscreen`；调用 `self.screen()` 或 `QGuiApplication.screenAt(...)` **MUST** 判空，当返回 `None` 时跳过屏幕裁剪而非崩溃。

---

## 4. 状态修改闭环

任何改变场景、轨迹、轨道、时间线节点或初始位姿的用户交互，**MUST** 经由 `StudioStateService` 并推入 `StudioUndoStack`（支持撤销/重做）且落盘 SQLite，禁止仅改内存属性导致刷新后丢失。

## 自检清单

- [ ] 全部控件与配色出自 `design_system/` 与 `tokens.py`，无按钮文本截断
- [ ] 正文无冗长说明文字，操作提示收拢至标题栏最右上角 `UHelpIcon`，且未叠加 `setToolTip`
- [ ] 已验证 offscreen 模式下 `screen() is None` 安全与关闭时的定时器/弹窗清理
- [ ] 可编辑操作已接通 `StudioUndoStack` 与持久化层
