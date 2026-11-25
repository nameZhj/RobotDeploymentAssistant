# Web 控制台与 Flask 开发规范

> 何时阅读：修改 `upper_computer/web/` 下 HTML/CSS/JS 或 `upper_computer/app.py` 路由时必读。
> 前置文档：[01 仓库结构](01_REPO_MAP_AND_ENTRYPOINTS.md)、[02 检索阅读](02_RETRIEVAL_AND_READING.md)。
> 要点速览：1) 基线文件实行最小增量修改，新逻辑优先独立成文件并规范注册；2) 使用 `.help-tooltip-wrapper.align-right` 实现单层 `?` 悬浮气泡；3) 严禁破坏测试锁定的 DOM ID、文本及安全转义规则。

---

## 1. 基线保护与文件组织

- **最小增量原则**：`app.py`、`web/index.html`、`web/js/main.js`、`web/css/style.css` 及基线 Web/安全测试（`test_all_features.py`、`test_robot_id_and_target.py`）受 `a5973d4` 保护；对上述历史大文件 **MUST** 仅做精准局部增删，**MUST NOT** 擅自重写既有路由或 DOM 骨架。
- **职责位置约定**：
  - 页面与弹窗模板：`upper_computer/web/components/`（运维页签位于 `ops_tabs/`）；
  - HTTP 请求封装：**MUST** 统一写在 `upper_computer/web/js/api.js`，页面 JS 仅消费 API 封装；
  - 交互脚本与样式：对应模块 `web/js/*.js` 及 `web/css/style.css`（复用 `--accent-cyan`、`--text-muted` 等既有 CSS 变量）。
- **新增 JS/CSS 注册**：较为独立的新前端脚本或样式 **SHOULD** 建为新文件，并按现有方式在 `web/components/scripts.html` 或 `web/components/head.html` 中注册（修改前 **MUST** 先读取这两个文件确认加载顺序）。

---

## 2. 右上角 `?` 悬浮提示与文案规则

- **布局定位**：卡片、横幅或弹窗的操作提示 **MUST** 置于头部右侧（而非标题左侧），使用 `web/css/style.css` 既定结构：
  ```html
  <div class="help-tooltip-wrapper align-right">
    <span class="help-icon-circle" tabindex="0" role="button" aria-label="操作说明">?</span>
    <div class="help-tooltip-bubble">...</div>
  </div>
  ```
- **单一提示铁律**：使用了 `.help-tooltip-bubble` 的 `?` 按钮及其内部元素 **MUST NOT** 再添加原生 `title` 属性或第二套 JS tooltip，防止出现双弹窗。
- **商业级极简文案**：遵循与 [04 桌面端规范](04_DESKTOP_UI_UX_RULES.md) 同等精简原则——标题短、按钮动词化、空状态单行、正文禁放长段说明或 `.modal-note-box` 说明框；所有用户可见界面文案 **MUST** 使用简洁中文。

---

## 3. 测试锁定的 DOM ID 与标识（禁止误删/误改）

修改 Web 模板前，**MUST** 保护以下已被既有自动化测试断言锁定的元素与文本：
- 错误提示容器 ID：**MUST** 完整保留 `id="tp-robot-id-error"`、`id="select-robot-id-error"`、`id="add-robot-id-error"`（`tests/test_robot_id_and_target.py` 强依赖）。
- 导航按钮与黑名单：**MUST** 保留 `data-type="ros_nav"` 按钮，且 HTML 中 **MUST NOT** 出现 `tab-3d-player` 与 `wxid_` 字符串（`tests/test_all_features.py` 强依赖）。

---

## 4. 安全与后端边界

- **无硬编码凭据**：前端 JS/HTML 与 `app.py` **MUST NOT** 硬编码真实密码、私钥、License 签名或敏感内网凭据（如非用户显式输入的示例默认配置须清晰界定）。
- **防 XSS 注入**：将设备返回值、错误信息或用户输入插入 DOM 时 **SHOULD** 使用 `textContent`；若必须拼接 `innerHTML`，**MUST** 先执行 HTML 转义，严禁直接插值未过滤的后端/外部字符串。

## 自检清单

- [ ] 历史大文件仅做局部增量修改；新前端脚本/样式已按 `scripts.html` / `head.html` 规范注册
- [ ] `?` 提示位于头部最右侧且带 `.align-right`，未叠加 `title` 属性造成双弹窗
- [ ] `tp-robot-id-error` 等测试锁定 ID 与 `data-type="ros_nav"` 完整保留
- [ ] 动态渲染已做转义或使用 `textContent`，无硬编码密钥
