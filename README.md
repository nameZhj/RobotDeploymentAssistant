# VSISLAB 机器人部署助手 (Robot Deployment Assistant)

> 面向宇树 **Unitree G1 / Go2** 机器人的商业化快速部署、硬件环境预检、容器自启固化、License 授权校验、实时日志诊断与 3D 动捕动作仿真系统。

---

## 📌 架构与技术栈

- **后端架构**：`Python 3.10+` + `Flask` + `Paramiko` (SSH/SFTP 高并发远端通信与实时流式输出) + `PyWebview` (现代化原生独立桌面窗口) + `Numpy` (3D 运动学解析)
- **前端架构**：原生 `HTML5` + `Vanilla CSS`  + `Vanilla JS` (模块化单页应用) + `Three.js r128` (WebGL 50fps 真实骨骼物理仿真与轨道相机控制器)
- **打包分发**：`PyInstaller` (便携绿色运行包) + `Inno Setup` (Windows 标准安装引导包)

---

## 🚀 快速开始

### 1. 运行环境准备
```bash
# 推荐使用 Python 3.10 ~ 3.12 虚拟环境
python -m venv venv
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 启动与本地开发
- **调试启动**：双击运行项目根目录下的 **`run_test.bat`**（或执行 `python test_tool.py`），自动挂载 Flask 服务并启动桌面客户端。
- **浏览器直连**：启动后可直接访问 `http://127.0.0.1:8088` 进行前端热调试。

### 3. 编译打包与发布
- **一键打包**：运行 **`build.bat`**（或 `python build_package.py`），自动清理并生成单目录绿色客户端至 `dist/VSISLAB机器人部署助手`。
- **生成安装包**：使用 Inno Setup 编译 `setup_installer.iss` 即可生成一键安装向导 `.exe`。

---

## 🧩 核心功能与模块索引

```
RobotDeploymentAssistant/
├── backend/                  # 后端核心业务层
│   ├── deployment_core.py    # 容器启动、开机自启固化、环境预检与修复引擎
│   ├── ssh_client.py         # SSH/SFTP 连接池、命令流式执行与心跳探测
│   ├── network_manager.py    # Windows netsh 本机网卡直连切换与局域网并发扫描
│   ├── license_service.py    # 机器码读取、RSA 授权解析与有效期校验
│   ├── npz_service.py        # 3D 动作 NPZ 数据多维度解析与骨骼拓扑适配
│   ├── dance_updater.py      # 舞蹈动作包解压与远端部署管理
│   └── log_diagnostics.py    # Docker/主机日志拉取与正则智能诊断引擎
├── web/                      # 前端静态资源
│   ├── index.html            # 主界面与部署向导弹窗模板
│   ├── css/style.css         # 统一暗黑设计系统与动效规范
│   └── js/
│       ├── api.js            # RESTful API 通信层与错误封装
│       ├── app.js            # 顶层状态机、事件中心与拖拽批量上传
│       ├── wizard.js         # 一键部署向导状态机与全流程自动化执行
│       ├── dance_player3d.js # Three.js 3D 骨骼渲染器与相机跟随引擎
│       ├── log_viewer.js     # 实时日志轮询与智能诊断告警看板
│       ├── manual_mode.js    # 交互式远端 Shell 终端控制台
│       └── tab_panels.js     # 独立功能页签（网卡/预检/镜像/动作等）
├── app.py                    # Flask 路由服务入口
├── main.py                   # PyWebview 桌面客户端启动入口
├── test_tool.py              # 开发调试启动与进程监听
└── run_test.bat              # 便捷调试批处理脚本
```

---

## ⚙️ 关键技术规范与协议

### 1. 默认通信与网络配置
- **机器人默认参数**：`192.168.123.164` / 端口 `22` / 用户名 `unitree` / 密码 `123`
- **本机网卡直连**：调用 Windows `netsh` 将本机指定有线网卡一键设为 `192.168.123.200/24`；支持一键切回 DHCP。

### 2. 部署流程与容器规范
- **运行容器名称**：`vsis_g1`
- **群控通信端口**：`400`（UDP/TCP 接收服务）
- **开机自启写入**：配置 systemd 单元或写入 rc.local，包含 `--restart=always` 参数。
- **自动跳步机制**：每次程序连接到机器人时，后台静默执行 `startup_check`，若 License 校验有效且 400 端口容器正常运行，则不打扰用户，静默进入主监控面板。

### 3. 3D 动作回放与 NPZ 骨骼拓扑
- **关节支持**：
  - **21 关节**：通用人形骨骼模型；
  - **30 刚体连杆**：**Unitree G1 29-DOF 真实机器人**（基于 `body_pos_w` 矩阵精确映射 28 组刚性骨骼链与头部球体）。
- **导入机制**：支持多文件并发选择、外部文件/文件夹直接拖拽入列表或画布区域，自动提取 `fps` 与动作帧数据。

---

## 🔒 授权管理规范 (License)
- 远端路径：`/home/ubuntu/vsis_mimic_deploy/license.json`
- 机器码结构：结合主板 UUID、网卡 MAC 地址生成机器指纹。
- 校验机制：启动与部署阶段通过公钥验签，校验有效期及授权模块权限。
