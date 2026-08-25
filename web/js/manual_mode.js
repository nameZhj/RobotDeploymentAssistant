/**
 * 手动模式（控制台）前端交互逻辑
 */
const ManualMode = {
  commands: [
    {
      id: 'chk_serial',
      title: '1. 检查宿主机 CH341 串口',
      desc: '验证是否存在 /dev/ttyCH341USB0 串口设备',
      cmd: 'ls -l /dev/ttyCH34*',
      sudo: false
    },
    {
      id: 'install_ch341',
      title: '2. 编译并安装 CH341 驱动',
      desc: '拉取官方驱动源码，编译并加载 ch341 驱动模块，清除冲突的 brltty',
      cmd: 'sudo apt update && sudo apt install -y build-essential bc git dkms && (sudo apt install -y nvidia-l4t-kernel-headers || sudo apt install -y linux-headers-$(uname -r) || true) && cd /tmp && rm -rf ch341ser_linux && (git clone --depth 1 https://github.com/WCHSoftGroup/ch341ser_linux || git clone --depth 1 https://gitee.com/mirrors_WCHSoftGroup/ch341ser_linux.git) && cd ch341ser_linux/driver && make && sudo make install && sudo modprobe ch341 && sudo apt purge -y "brltty*"',
      sudo: true
    },
    {
      id: 'docker_run',
      title: '3. 启动固化参数 Docker 容器',
      desc: '完全固化参数，挂载 /dev/、开启 GPU 直通与特权模式',
      cmd: 'docker run -d --restart=on-failure --name vsis_g1 --cap-add=SYS_PTRACE --gpus all --shm-size=1024m --privileged --cap-add=NET_ADMIN --device /dev/:/dev/ -v /tmp/.X11-unix:/tmp/.X11-unix:rw -v /tmp:/tmp/ -v /run/udev/:/run/udev/ -p 400:22 -p 4001:4000 -p 4002:6006 rl_cu118:2.0',
      sudo: true
    },
    {
      id: 'write_startup',
      title: '4. 写入开机自启动钩子',
      desc: '写入 /docker_config/custom_startup.sh 自动拉起 run_bg.sh',
      cmd: 'echo -e "#!/bin/bash\\n/home/ubuntu/vsis_mimic_deploy/run_bg.sh" | sudo tee /docker_config/custom_startup.sh && sudo chmod +x /docker_config/custom_startup.sh',
      sudo: true
    },
    {
      id: 'write_id',
      title: '5. 写入 Robot ID (寻址标识)',
      desc: '写入 /home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt (A/B/C/D)',
      cmd: 'echo "A" | sudo tee /home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt',
      sudo: true
    },
    {
      id: 'read_mid',
      title: '6. 容器内读取 64 位机器码',
      desc: '执行 ./g1_ctrl_vsis --print-machine-id 读出硬件哈希',
      cmd: 'docker exec vsis_g1 bash -c "cd /home/ubuntu/vsis_mimic_deploy && ./g1_ctrl_vsis --print-machine-id"',
      sudo: true
    },
    {
      id: 'restart_proc',
      title: '7. 停止并重启运控与群控进程',
      desc: '杀掉旧进程并重新调用 run_bg.sh',
      cmd: 'docker exec vsis_g1 bash -c "pkill -f g1_ctrl_vsis ; pkill -f lora_recv_group" && docker exec -d vsis_g1 /home/ubuntu/vsis_mimic_deploy/run_bg.sh',
      sudo: true
    },
    {
      id: 'view_sec_log',
      title: '8. 查看主控运行日志',
      desc: '查看 sec_run.log 主控制器初始化与模型加载日志',
      cmd: 'docker exec vsis_g1 tail -n 50 /home/ubuntu/vsis_mimic_deploy/log/sec_run.log',
      sudo: true
    },
    {
      id: 'view_lora_log',
      title: '9. 查看群控接收日志',
      desc: '查看 lora_recv.log 无线指令接收与就绪状态',
      cmd: 'docker exec vsis_g1 tail -n 50 /home/ubuntu/vsis_mimic_deploy/log/lora_recv.log',
      sudo: true
    }
  ],

  init() {
    this.renderCommandCards();
    this.bindEvents();
  },

  renderCommandCards() {
    const container = document.getElementById('manual-cmd-list');
    if (!container) return;

    let html = '';
    for (const item of this.commands) {
      html += `
        <div class="card" style="margin-bottom: 14px;">
          <div class="card-header">
            <div class="card-title">${item.title}</div>
            <div style="display: flex; gap: 8px;">
              <button class="btn btn-secondary btn-sm" onclick="ManualMode.copyCmd('${item.id}')">📋 复制</button>
              <button class="btn btn-primary btn-sm" onclick="ManualMode.runCmd('${item.id}')">⚡ 执行</button>
            </div>
          </div>
          <div style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 8px;">${item.desc}</div>
          <div class="form-control" id="cmd-text-${item.id}" style="font-size: 0.78rem; background: rgba(0,0,0,0.5); overflow-x: auto; white-space: pre;">${this.escapeHtml(item.cmd)}</div>
        </div>
      `;
    }
    container.innerHTML = html;
  },

  bindEvents() {
    const btnCustomRun = document.getElementById('btn-manual-custom-run');
    const inputCustom = document.getElementById('input-manual-custom-cmd');
    if (btnCustomRun && inputCustom) {
      btnCustomRun.addEventListener('click', () => {
        const cmd = inputCustom.value.trim();
        const sudo = document.getElementById('chk-manual-sudo')?.checked || false;
        if (cmd) this.executeCustom(cmd, sudo);
      });

      inputCustom.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          btnCustomRun.click();
        }
      });
    }
  },

  copyCmd(id) {
    const item = this.commands.find(c => c.id === id);
    if (item) {
      copyToClipboard(item.cmd, `[${item.title}] 命令已复制`);
    }
  },

  async runCmd(id) {
    const item = this.commands.find(c => c.id === id);
    if (!item) return;

    this.logConsole(`\n>>> 正在执行: ${item.cmd}`, 'info');
    try {
      const res = await API.executeManual(item.cmd, item.sudo);
      if (res.exit_code === 0) {
        this.logConsole(res.stdout || '(执行成功，无输出)', 'success');
        showToast(`[${item.title}] 执行成功`, 'success');
      } else {
        this.logConsole(`[退出码 ${res.exit_code}]\n${res.stderr || res.stdout}`, 'error');
        showToast(`[${item.title}] 执行返回错误码 ${res.exit_code}`, 'error');
      }
    } catch (err) {
      this.logConsole(`[异常] ${err.message}`, 'error');
      showToast(`执行失败: ${err.message}`, 'error');
    }
  },

  async executeCustom(cmd, sudo = false) {
    this.logConsole(`\n>>> [自定义命令] ${cmd}`, 'info');
    try {
      const res = await API.executeManual(cmd, sudo);
      if (res.exit_code === 0) {
        this.logConsole(res.stdout || '(执行成功，无输出)', 'success');
      } else {
        this.logConsole(`[退出码 ${res.exit_code}]\n${res.stderr || res.stdout}`, 'error');
      }
    } catch (err) {
      this.logConsole(`[执行异常] ${err.message}`, 'error');
    }
  },

  logConsole(text, type = 'info') {
    const consoleEl = document.getElementById('manual-console-output');
    if (!consoleEl) return;
    const div = document.createElement('div');
    div.className = `log-${type}`;
    div.textContent = text;
    consoleEl.appendChild(div);
    consoleEl.scrollTop = consoleEl.scrollHeight;
  },

  clearConsole() {
    const consoleEl = document.getElementById('manual-console-output');
    if (consoleEl) consoleEl.innerHTML = '';
  },

  escapeHtml(str) {
    return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
};
