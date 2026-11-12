# Skill 安装位置

将 ZIP 根目录中的 `.agents/skills/robot-deployment-assistant/SKILL.md` 放到 RDA 仓库根目录下相同位置：

```text
RobotDeploymentAssistant/
└── .agents/
    └── skills/
        └── robot-deployment-assistant/
            └── SKILL.md
```

若使用支持 Agent Skills 自动发现的开发工具，应确保当前 workspace 以 RobotDeploymentAssistant 仓库根目录打开，并检查 Skill 是否被工具发现。若工具要求额外在 Agent 配置中启用该 Skill，按该工具的配置方式启用；SKILL.md 本身不负责修改 IDE 配置。

本 Skill 也可在 Agent 对话开头显式指定读取路径。不要把 Skill 文件只留在下载目录而未放入项目仓库。
