# VSISLAB 机器人部署助手与编排工作台 (ChoreoNexus)

> 面向机器人的一键部署、硬件环境预检、Docker 固化容器管理、开机自启守护、64 位硬件机器码与 License 授权校验、LoRa 广播串口群控与多机编队调度、3D 动捕仿真及实时日志诊断系统。

---

## 🌟 核心特性
1. **一键向导化部署**：涵盖网络直连握手、镜像加载、自启固化与授权激活 6 步闭环。
2. **多机编队与群控调度**：支持全机队拓扑监控、十字方向微操与 33 支舞蹈动作一键下发。
3. **分层无硬编码架构**：基于 `src/{core,infrastructure,domain,application,ui}` 严格单向分层。
4. **Clean-Room 隔离与安全互斥**：状态机严格维护 `FREE`、`MANUAL`、`CHOREO` 控制权互斥。
5. **3D 动作仿真视口**：支持动作骨骼动捕回放与 NPZ 动作包热更新。

---

## 🏗️ 架构分层体系 (DAG)
```
src/
├── core/            # 配置加载 (零硬编码)、常量枚举、通信审计日志
├── infrastructure/  # 串口底层通信、Paramiko SSH/SFTP 通道、系统网卡
├── domain/          # LRMP 协议编解码、控制权仲裁器、机群实体模型
├── application/     # 机群拓扑服务、运控下发用例、部署编排服务
└── ui/              # Flask 蓝图解耦 (control, fleet, deployment) 与 Web 界面
```

---

## 🚀 快速开始

### 1. 运行环境准备
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 启动服务
```bash
python main.py
# 或纯 Web 模式
python app.py
```

### 3. 一键合规检查
```bash
python scripts/verify_guardrails.py
```

---

## 📖 现场部署与协议规范
- 现场详细部署指南请参阅 [docs/deployment_guide.md](docs/deployment_guide.md)。
- 协议定义请参考 [configs/lrmp_protocol.yaml](configs/lrmp_protocol.yaml)。
