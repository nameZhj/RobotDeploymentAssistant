/**
 * Tab Panel 独立功能处理器
 * 每个 Tab 独立调用 API 并操作自己专属的 DOM 元素，
 * 与向导弹窗 (Wizard) 共用 API 但不共用 DOM 元素 ID。
 */

// ===========================================
// Tab 网络扫描与网卡配置
// ===========================================
const TabNetwork = {
  async init() {
    await this.loadNics();
    await this.loadWindowsCh341();
  },

  async autoConnect() {
    showToast('⚡ 正在执行断网自愈与自动连接...', 'info', 3000);
    try {
      const res = await API.autoConnect(true);
      if (res.connected) {
        showToast(res.msg, 'success', 3500);
        App.updateStatus();
        this.loadNics();
      } else {
        showToast(res.msg || '未探测到在线机器人', 'warning', 3500);
      }
    } catch (err) {
      showToast(`自愈连接异常: ${err.message}`, 'error');
    }
  },

  async loadWindowsCh341() {
    const statusEl = document.getElementById('tp-win-ch341-status');
    if (!statusEl) return;
    try {
      const res = await API.checkWindowsCh341();
      if (res.success && res.data) {
        const data = res.data;
        if (data.ports && data.ports.length > 0) {
          const portNames = data.ports.map(p => `${p.port} (${p.device.replace('\\Device\\', '')})`).join(', ');
          statusEl.innerHTML = `<span style="color: var(--accent-green); font-weight: bold;">✅ 已识别串口：${portNames}</span>`;
        } else {
          statusEl.innerHTML = `<span style="color: var(--text-muted);">未插入 USB 串口模块（若已插入但未识别，请点击右侧安装驱动）</span>`;
        }
      }
    } catch (e) {
      console.error('检测 Windows 串口失败:', e);
    }
  },

  async installWindowsCh341() {
    try {
      const res = await API.installWindowsCh341();
      if (res.success) {
        alert(res.msg || 'Windows CH341 驱动安装程序已启动，请在弹窗中点击【安装】完成驱动安装。');
        setTimeout(() => this.loadWindowsCh341(), 4000);
      } else {
        alert(`启动驱动安装程序失败: ${res.msg}`);
      }
    } catch (err) {
      alert(`安装驱动异常: ${err.message}`);
    }
  },

  async loadNics() {
    const select = document.getElementById('tp-nic-select');
    if (!select) return;
    try {
      const res = await API.getInterfaces();
      select.innerHTML = '';
      if (!res.interfaces || res.interfaces.length === 0) {
        select.innerHTML = '<option value="">未找到可用网卡</option>';
        return;
      }
      for (const nic of res.interfaces) {
        if (nic.is_loopback) continue;
        const opt = document.createElement('option');
        opt.value = nic.name;
        opt.textContent = `${nic.name}  (${nic.ip || '未分配IP'} / ${nic.is_up ? '已连接' : '未连接'})`;
        if (nic.is_unitree_subnet) opt.selected = true;
        select.appendChild(opt);
      }
    } catch (err) {
      console.error('获取网卡列表失败:', err);
    }
  },

  async scan() {
    const btn = document.getElementById('tp-btn-scan');
    const listEl = document.getElementById('tp-scan-results');
    if (btn) btn.disabled = true;
    if (listEl) listEl.innerHTML = '<div style="padding: 12px; color: var(--accent-cyan);">🔍 正在扫描局域网 (192.168.123.1~254) ...</div>';

    try {
      const res = await API.scanNetwork('192.168.123.');
      if (btn) btn.disabled = false;
      if (!res.devices || res.devices.length === 0) {
        if (listEl) listEl.innerHTML = `
          <div style="padding: 12px; color: var(--accent-yellow);">
            ⚠️ 未发现活跃设备。请确认：网线已连接、电脑网卡已配置为 192.168.123.x 网段、机器人电源已开启。
          </div>
        `;
        return;
      }
      let html = '';
      for (const dev of res.devices) {
        html += `
          <div class="card" style="margin-bottom: 8px; padding: 12px; display: flex; align-items: center; justify-content: space-between;">
            <div>
              <div style="font-weight: 700; color: #ffffff; font-family: monospace; font-size: 1rem;">${dev.ip}:${dev.port}</div>
              <div style="font-size: 0.78rem; color: #9ca3af;">${dev.device_type} - ${dev.default_hint}</div>
            </div>
            <button class="btn btn-primary btn-sm" onclick="TabNetwork.connectDevice('${dev.ip}', ${dev.port})">🔗 连接此设备</button>
          </div>
        `;
      }
      if (listEl) listEl.innerHTML = html;
    } catch (err) {
      if (btn) btn.disabled = false;
      if (listEl) listEl.innerHTML = `<div style="padding: 12px; color: var(--accent-red);">扫描失败: ${err.message}</div>`;
    }
  },

  connectDevice(ip, port) {
    const hostInput = document.getElementById('input-host');
    const portInput = document.getElementById('input-port');
    if (hostInput) hostInput.value = ip;
    if (portInput) portInput.value = port;
    App.connect();
  },

  async setStatic() {
    const select = document.getElementById('tp-nic-select');
    const nicName = select ? select.value : '';
    if (!nicName) {
      showToast('请先选择需要配置的以太网卡', 'warning');
      return;
    }
    showToast(`正在将网卡 [${nicName}] 设为 192.168.123.200 ...`, 'info');
    try {
      const res = await API.configureNic(nicName, '192.168.123.200');
      if (res.success) {
        showToast(res.msg, 'success');
        await this.loadNics();
      } else {
        showToast(`配置失败: ${res.msg}`, 'error');
      }
    } catch (err) {
      showToast(`网卡配置异常: ${err.message}`, 'error');
    }
  },

  async setDhcp() {
    const select = document.getElementById('tp-nic-select');
    const nicName = select ? select.value : '';
    if (!nicName) return;
    showToast(`正在将网卡 [${nicName}] 恢复为 DHCP ...`, 'info');
    try {
      const res = await API.restoreDhcp(nicName);
      showToast(res.success ? res.msg : `恢复失败: ${res.msg}`, res.success ? 'success' : 'error');
      if (res.success) await this.loadNics();
    } catch (err) {
      showToast(`恢复异常: ${err.message}`, 'error');
    }
  },

  clearConsole() {
    const el = document.getElementById('tp-license-result');
    if (el) {
      el.innerHTML = '<div class="log-info">控制台已清空。就绪。</div>';
    }
  }
};


// ===========================================
// Tab 环境预检与修复
// ===========================================
const TabPrecheck = {
  async run() {
    const container = document.getElementById('tp-precheck-items');
    if (!container) return;
    container.innerHTML = '<div style="padding: 20px; color: var(--accent-cyan);">⏳ 正在执行环境预检，请稍候...</div>';

    try {
      const res = await API.getPrecheck();
      if (!res.success || !res.data) {
        container.innerHTML = `<div style="padding: 20px; color: var(--accent-red);">预检失败: ${res.msg || '未知错误'}</div>`;
        return;
      }
      const items = res.data.items;
      let html = '';
      for (const key in items) {
        const item = items[key];
        let statusIcon = '✅';
        if (item.status === 'error') statusIcon = '❌';
        else if (item.status === 'warning') statusIcon = '⚠️';

        const copyText = `【${item.name}】状态: ${item.status}\n指标/版本: ${item.version}\n说明: ${item.msg}`;
        html += `
          <div class="precheck-item-card" style="background: rgba(0, 0, 0, 0.25); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 7px 10px; display: flex; flex-direction: column; justify-content: space-between; min-height: 52px; transition: border-color 0.2s;">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
              <div style="display: flex; align-items: center; gap: 6px; min-width: 0; overflow: hidden;">
                <span style="font-size: 0.95rem; line-height: 1;">${statusIcon}</span>
                <span style="font-weight: 700; font-size: 0.82rem; color: #ffffff; white-space: nowrap;">${item.name}</span>
                <span style="font-family: monospace; font-size: 0.72rem; color: var(--accent-cyan); background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.2); padding: 1px 6px; border-radius: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${item.version || ''}">${item.version || '已就绪'}</span>
              </div>
              <div style="display: flex; gap: 4px; align-items: center; flex-shrink: 0;">
                <button class="btn-copy-mini" onclick="copyToClipboard(${JSON.stringify(copyText)}, '指标信息已复制')" style="font-size: 0.68rem; padding: 1px 5px;" title="复制指标信息">📋 复制</button>
                ${item.can_fix ? `<button class="btn btn-primary btn-xs" onclick="TabPrecheck.fixItem('${key}')" style="font-size: 0.7rem; font-weight: 700; padding: 2px 6px; white-space: nowrap;">🛠️ 修复</button>` : ''}
              </div>
            </div>
            <div style="font-size: 0.72rem; color: var(--text-secondary); line-height: 1.3; user-select: text; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 3px;" title="${item.msg || ''}">
              ${item.msg}
            </div>
          </div>
        `;
      }
      container.innerHTML = html || '<div style="color: var(--text-muted); padding: 20px;">没有预检数据</div>';

      // 控制顶部快速修复按钮：仅在驱动缺失且可修复时显示，已就绪则隐藏
      const btnHeaderFix = document.getElementById('btn-tp-fix-ch341');
      if (btnHeaderFix) {
        if (items.serial_ch341 && items.serial_ch341.can_fix) {
          btnHeaderFix.style.display = 'inline-block';
        } else {
          btnHeaderFix.style.display = 'none';
        }
      }

      if (res.data.all_passed) {
        // 静默通过，仅在 UI 上显示绿勾，不再弹出 toast
      } else {
        showToast('⚠️ 检测到部分环境指标异常，请使用【一键修复】按钮解决', 'warning', 4000);
      }
    } catch (err) {
      container.innerHTML = `<div style="padding: 20px; color: var(--accent-red);">预检异常: ${err.message}</div>`;
    }
  },

  async fixItem(key) {
    if (key === 'serial_ch341') {
      this.fixCh341();
    } else if (key === 'docker') {
      this.fixDocker();
    }
  },

  async fixCh341() {
    const allFixBtns = document.querySelectorAll('#btn-wizard-fix-ch341, #btn-tp-fix-ch341, .btn-fix-ch341-item');
    allFixBtns.forEach(btn => {
      btn.disabled = true;
      if (!btn.dataset.origText) btn.dataset.origText = btn.innerHTML;
      btn.innerHTML = '⏳ 正在修复 LoRa 通信环境...';
      btn.classList.add('loading');
    });

    showToast('正在启动 LoRa 串口与群控通信环境全面自愈修复...', 'info');
    const modal = document.getElementById('fix-stream-modal');
    const consoleEl = document.getElementById('fix-stream-console');
    const progressBar = document.getElementById('fix-step-progress-bar');
    const progressPct = document.getElementById('fix-step-percent');
    const progressTxt = document.getElementById('fix-step-status-text');
    const modalTitle = document.getElementById('fix-modal-title');
    const modalIcon = document.getElementById('fix-modal-icon');

    if (modalTitle) modalTitle.textContent = '正在执行 LoRa 串口驱动与群控通信环境深度自愈修复';
    if (modalIcon) modalIcon.textContent = '🛠️';
    if (progressBar) progressBar.style.width = '10%';
    if (progressPct) progressPct.textContent = '10%';
    if (progressTxt) progressTxt.textContent = '⏳ 正在连接机器人并初始化修复环境...';

    if (modal) modal.style.display = 'flex';
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">[INFO] 准备开始 LoRa 通信自愈修复，下发指令并监听输出...</div>';

    const updateProgress = (line) => {
      if (!progressBar || !progressPct || !progressTxt) return;
      const l = line.toLowerCase();
      if (l.includes('step 1') || l.includes('检查 ch341 内核驱动')) {
        progressBar.style.width = '20%';
        progressPct.textContent = '20%';
        progressTxt.textContent = '🔍 [1/6] 检查与加载 CH341 Linux 内核驱动模块...';
      } else if (l.includes('step 2') || l.includes('配置 udev') || l.includes('权限')) {
        progressBar.style.width = '35%';
        progressPct.textContent = '35%';
        progressTxt.textContent = '🛡️ [2/6] 配置 udev 规则并放行 0666 设备读写权限...';
      } else if (l.includes('step 3') || l.includes('lora_recv_group.yaml')) {
        progressBar.style.width = '50%';
        progressPct.textContent = '50%';
        progressTxt.textContent = '⚙️ [3/6] 优化 lora_recv_group.yaml 串口稳定参数...';
      } else if (l.includes('step 4') || l.includes('热补丁') || l.includes('make.sh')) {
        progressBar.style.width = '70%';
        progressPct.textContent = '70%';
        progressTxt.textContent = '🔧 [4/6] 注入多端口自适应热补丁并编译 lora_recv_group...';
      } else if (l.includes('step 5') || l.includes('run_bg.sh')) {
        progressBar.style.width = '85%';
        progressPct.textContent = '85%';
        progressTxt.textContent = '📝 [5/6] 写入自适应多节点扫描 run_bg.sh 启动与守护脚本...';
      } else if (l.includes('step 6') || l.includes('拉起 lora')) {
        progressBar.style.width = '95%';
        progressPct.textContent = '95%';
        progressTxt.textContent = '🚀 [6/6] 校验并守护拉起机载 LoRa 接收程序...';
      }
    };

    try {
      const res = await API.fixCh341();
      if (res.success && res.task_id) {
        API.listenStream(res.task_id, (line, isErr) => {
          if (consoleEl) {
            const div = document.createElement('div');
            div.className = isErr ? 'log-error' : 'log-info';
            div.textContent = line;
            consoleEl.appendChild(div);
            consoleEl.scrollTop = consoleEl.scrollHeight;
          }
          updateProgress(line);
        }, (ok) => {
          allFixBtns.forEach(btn => {
            btn.disabled = false;
            btn.innerHTML = btn.dataset.origText || '🛠️ 一键修复 LoRa 通信';
            btn.classList.remove('loading');
          });

          if (ok) {
            if (progressBar) progressBar.style.width = '100%';
            if (progressPct) progressPct.textContent = '100%';
            if (progressTxt) progressTxt.textContent = '✅ LoRa 串口与群控通信环境自愈修复成功！';
            showToast('✅ LoRa 通信环境修复完成！', 'success', 3000);
            setTimeout(() => {
              const m = document.getElementById('fix-stream-modal');
              if (m) m.style.display = 'none';
              TabPrecheck.run();
            }, 1200);
          } else {
            if (progressTxt) progressTxt.textContent = '❌ 修复遇到问题，请检查日志输出';
            showToast('❌ 修复遇到问题，请检查日志', 'error', 4000);
            TabPrecheck.run();
          }
        });
      } else {
        allFixBtns.forEach(btn => {
          btn.disabled = false;
          btn.innerHTML = btn.dataset.origText || '🛠️ 一键修复 LoRa 通信';
          btn.classList.remove('loading');
        });
        showToast('启动修复任务失败: ' + (res.msg || '未知错误'), 'error');
      }
    } catch (err) {
      allFixBtns.forEach(btn => {
        btn.disabled = false;
        btn.innerHTML = btn.dataset.origText || '🛠️ 一键修复 LoRa 通信';
        btn.classList.remove('loading');
      });
      showToast('调用修复接口异常: ' + err.message, 'error');
    }
  },

  async fixDocker() {
    showToast('正在修复 Docker 环境...', 'info');
    const modal = document.getElementById('fix-stream-modal');
    const consoleEl = document.getElementById('fix-stream-console');
    if (modal) modal.style.display = 'flex';
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">正在修复 Docker...</div>';
    try {
      const res = await API.fixDocker();
      if (res.success && res.task_id) {
        API.listenStream(res.task_id, (line, isErr) => {
          if (consoleEl) {
            const div = document.createElement('div');
            div.className = isErr ? 'log-error' : 'log-info';
            div.textContent = line;
            consoleEl.appendChild(div);
            consoleEl.scrollTop = consoleEl.scrollHeight;
          }
        }, (ok) => {
          showToast(ok ? 'Docker 修复完成' : 'Docker 修复遇到问题', ok ? 'success' : 'error');
          TabPrecheck.run();
        });
      }
    } catch (err) {
      showToast(`修复异常: ${err.message}`, 'error');
    }
  }
};


// ===========================================
// Tab 镜像与容器管理
// ===========================================
const TabImage = {
  uploadInterval: null,
  processPollInterval: null,

  async init() {
    await this.loadImages();
    await this.checkStatus();
    await this.checkProcessStatus();
    this.bindEvents();
    this.startProcessPolling();
  },

  async checkStatus() {
    try {
      const res = await API.getContainerStatus();
      if (res.success && res.data) {
        const d = res.data;
        const btnStart = document.getElementById('tp-btn-start-container');
        const btnAutostart = document.getElementById('tp-btn-write-autostart');
        if (btnStart) {
          btnStart.disabled = false;
          btnStart.classList.add('btn-primary');
          btnStart.classList.remove('btn-secondary');
          if (d.running) {
            btnStart.textContent = `🔄 重新固化启动 / 更新 vsis_g1 (当前运行中)`;
          } else {
            btnStart.textContent = `⚡ 固化启动容器 (vsis_g1)`;
          }
        }

        const inputRobotId = document.getElementById('tp-robot-id-select');
        if (inputRobotId && d.robot_id) {
          inputRobotId.value = d.robot_id;
        }

        this.isIdConfigured = !!d.autostart_configured;
        this.updateWriteIdButtonText();
      }
    } catch (e) {
      console.warn('Check container/autostart status failed:', e);
    }
  },

  setRobotId(id) {
    const inputEl = document.getElementById('tp-robot-id-select');
    if (inputEl) {
      inputEl.value = id;
    }
    this.validateInputId(false);
    this.updateWriteIdButtonText();
  },

  validateInputId(showIfInvalid = false) {
    const inputEl = document.getElementById('tp-robot-id-select');
    const errEl = document.getElementById('tp-robot-id-error');
    const rawValue = inputEl ? inputEl.value : '';
    const valResult = window.validateRobotId ? window.validateRobotId(rawValue) : { valid: true, cleanId: rawValue.trim().toUpperCase(), error: '' };

    if (!valResult.valid) {
      if (showIfInvalid) {
        if (errEl) {
          errEl.innerHTML = `⚠️ ${valResult.error}`;
          errEl.style.display = 'block';
        }
        if (inputEl) {
          inputEl.classList.add('input-invalid');
        }
      }
      return valResult;
    }

    if (errEl) {
      errEl.innerHTML = '';
      errEl.style.display = 'none';
    }
    if (inputEl) {
      inputEl.classList.remove('input-invalid');
    }
    return valResult;
  },

  updateWriteIdButtonText() {
    const inputEl = document.getElementById('tp-robot-id-select');
    const val = inputEl ? inputEl.value.trim().toUpperCase() : '';
    const btn = document.getElementById('tp-btn-write-autostart');
    const errEl = document.getElementById('tp-robot-id-error');

    if (errEl && errEl.style.display !== 'none') {
      this.validateInputId(true);
    }

    if (!btn) return;
    const idLabel = val ? ` [${val}]` : '';
    btn.disabled = false;
    btn.classList.remove('btn-secondary');
    btn.classList.add('btn-success');
    if (this.isIdConfigured) {
      btn.textContent = `⚙️ 重新写入 ID${idLabel}`;
    } else {
      btn.textContent = `💾 写入 ID${idLabel}`;
    }
  },

  bindEvents() {
    // 监听本地文件输入框变动回显
    const localInput = document.getElementById('tp-local-tar-path');
    if (localInput) {
      localInput.addEventListener('input', (e) => {
        const val = e.target.value.trim();
        const label = document.getElementById('tp-image-file-label');
        if (label) {
          label.textContent = val ? `已指定文件: ${val}` : '未选择文件';
        }
      });
    }
  },

  async browseTarFile() {
    try {
      showToast('正在打开文件选择器...', 'info');
      const res = await API.selectFile();
      if (res.success && res.file_path) {
        const localInput = document.getElementById('tp-local-tar-path');
        const remoteInput = document.getElementById('tp-remote-path-input');
        const label = document.getElementById('tp-image-file-label');
        if (localInput) localInput.value = res.file_path;
        if (label) label.textContent = `已选: ${res.filename} (${res.size_gb} GB)`;
        if (remoteInput) {
          const curVal = remoteInput.value.trim();
          const dir = curVal && curVal.includes('/') ? curVal.substring(0, curVal.lastIndexOf('/')) : '/home/ubuntu';
          remoteInput.value = `${dir}/${res.filename}`;
        }
        showToast(`已选择镜像文件: ${res.filename} (${res.size_gb} GB)`, 'success');
      } else if (res.msg && !res.msg.includes('取消')) {
        showToast(res.msg, 'error');
      }
    } catch (err) {
      showToast(`打开文件选择器异常: ${err.message}`, 'error');
    }
  },

  async cancelUpload() {
    try {
      showToast('正在取消上传...', 'warning');
      await API.cancelUpload();
      if (this.uploadInterval) {
        clearInterval(this.uploadInterval);
        this.uploadInterval = null;
      }
      this._resetUploadButtons();
      this.appendLog('上传已被用户取消。', true, '🛑');
      showToast('已取消上传任务', 'info');
    } catch (err) {
      showToast(`取消上传失败: ${err.message}`, 'error');
    }
  },

  _resetUploadButtons() {
    const btnStart = document.getElementById('tp-btn-start-upload');
    const btnCancel = document.getElementById('tp-btn-cancel-upload');
    if (btnStart) {
      btnStart.disabled = false;
      btnStart.style.display = 'block';
    }
    if (btnCancel) {
      btnCancel.style.display = 'none';
    }
  },

  renderRunningContainers(containers, targetElId = 'tp-running-containers-list') {
    const listEl = document.getElementById(targetElId);
    if (!listEl) return;
    if (!containers || containers.length === 0) {
      listEl.innerHTML = '<div style="font-size: 0.8rem; color: var(--text-muted); padding: 4px 0;">⚪ 暂无正在运行中的容器</div>';
      return;
    }
    let html = '<div style="display: flex; flex-direction: column; gap: 6px;">';
    for (const c of containers) {
      const isUp = c.is_running;
      const statusBadge = isUp 
        ? `<span class="container-status-badge running">🟢 运行中</span>`
        : `<span class="container-status-badge stopped">⚪ ${c.status || '已停止'}</span>`;
      
      const isWizard = targetElId.includes('wizard');
      const stopHandler = isWizard ? `Wizard.stopContainer('${c.name}')` : `TabImage.stopContainer('${c.name}')`;

      const stopBtn = isUp 
        ? `<button class="btn btn-danger btn-xs" style="padding: 4px 10px; font-size: 0.75rem; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px; font-weight: 600; cursor: pointer; flex-shrink: 0;" onclick="${stopHandler}" title="停止并关闭该容器">⏹️ 关闭容器</button>`
        : '';

      const portInfo = c.ports ? `<div style="font-size: 0.72rem; color: var(--text-muted); font-family: monospace; word-break: break-all; margin-top: 2px;">端口: ${c.ports}</div>` : '';
      html += `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 7px 10px; background: rgba(0, 0, 0, 0.25); border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.05); gap: 12px;">
          <div style="min-width: 0; flex: 1;">
            <div style="font-weight: 700; font-size: 0.85rem; color: #ffffff; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
              <span>📦 ${c.name}</span>
              <span style="font-size: 0.75rem; color: var(--accent-cyan); font-family: monospace; font-weight: normal; word-break: break-all;">[${c.image}]</span>
            </div>
            ${portInfo}
          </div>
          <div style="flex-shrink: 0; display: flex; align-items: center; gap: 8px; white-space: nowrap;">
            ${statusBadge}
            ${stopBtn}
          </div>
        </div>
      `;
    }
    html += '</div>';
    listEl.innerHTML = html;
  },

  async loadImages() {
    const select = document.getElementById('tp-docker-image-select');
    try {
      const res = await API.listImages();
      
      if (res && res.running_containers) {
        this.renderRunningContainers(res.running_containers, 'tp-running-containers-list');
      }

      if (!select) return;

      select.innerHTML = '';
      const availableImgs = res.available_images || res.images || [];
      if (availableImgs.length === 0) {
        select.innerHTML = '<option value="">(所有可用镜像均已在容器中运行)</option>';
        return;
      }

      // 优先将 vsis_dancer 镜像排在首位
      availableImgs.sort((a, b) => {
        const aName = `${a.repository}:${a.tag}`.toLowerCase();
        const bName = `${b.repository}:${b.tag}`.toLowerCase();
        const aMatch = aName.includes('vsis_dancer') || (aName.includes('vsis') && aName.includes('dancer'));
        const bMatch = bName.includes('vsis_dancer') || (bName.includes('vsis') && bName.includes('dancer'));
        if (aMatch && !bMatch) return -1;
        if (!aMatch && bMatch) return 1;
        return 0;
      });

      for (const img of availableImgs) {
        const opt = document.createElement('option');
        const tag = `${img.repository}:${img.tag}`;
        opt.value = tag;
        opt.textContent = `${tag} (${img.size})`;
        select.appendChild(opt);
      }
    } catch (err) {
      console.error('获取镜像列表失败:', err);
    }
  },

  async uploadImage() {
    const localInput = document.getElementById('tp-local-tar-path');
    const remoteInput = document.getElementById('tp-remote-path-input');
    const localPath = localInput ? localInput.value.trim() : '';
    const remotePath = remoteInput ? remoteInput.value.trim() : '';

    if (!localPath) {
      showToast('请点击【📁 浏览本地镜像文件】选取镜像，或输入本机文件完整绝对路径', 'warning');
      return;
    }

    const reqData = { local_path: localPath, remote_path: remotePath };

    showToast('正在检查远端镜像并准备传输...', 'info');
    const progressBox = document.getElementById('tp-upload-progress-box');
    const btnStart = document.getElementById('tp-btn-start-upload');
    const btnCancel = document.getElementById('tp-btn-cancel-upload');

    if (progressBox) progressBox.style.display = 'block';
    this.appendLog('正在校验远端镜像状态...', false, '📤');
    if (btnStart) btnStart.disabled = true;
    if (btnCancel) btnCancel.style.display = 'block';

    try {
      const res = await API.uploadImage(reqData);
      if (!res.success) {
        showToast(`上传失败: ${res.msg}`, 'error');
        this.appendLog(`上传失败: ${res.msg}`, true);
        this._resetUploadButtons();
        return;
      }
      if (remoteInput && res.remote_path) remoteInput.value = res.remote_path;

      if (res.skipped) {
        this._resetUploadButtons();
        this._updateProgress({ percent: 100, transferred_bytes: 1, total_bytes: 1, speed_mbps: 0, eta_seconds: 0 });
        showToast('远端已存在同名同大小镜像包，正在自动执行 Docker 镜像安装...', 'success');
        this.appendLog(`✅ 检测到远端已存在完全一致的镜像文件 (${res.remote_path})，无需重复上传，立即自动安装镜像！`, false);
        setTimeout(() => this.dockerLoad(), 500);
        return;
      }

      if (this.uploadInterval) clearInterval(this.uploadInterval);
      this.uploadInterval = setInterval(async () => {
        const prog = await API.getUploadProgress();
        this._updateProgress(prog);
        if (prog.status === 'completed') {
          clearInterval(this.uploadInterval);
          this.uploadInterval = null;
          this._resetUploadButtons();
          showToast('镜像上传成功！正在自动执行 Docker 镜像安装...', 'success');
          this.appendLog(`✅ 文件上传成功 (${res.remote_path})，立即自动执行 docker load 安装镜像...`, false);
          setTimeout(() => this.dockerLoad(), 600);
        } else if (prog.status === 'error' || prog.status === 'canceled') {
          clearInterval(this.uploadInterval);
          this.uploadInterval = null;
          this._resetUploadButtons();
          showToast(`上传异常: ${prog.error_msg}`, 'error');
          this.appendLog(`传输已终止: ${prog.error_msg}`, true);
        }
      }, 500);
    } catch (err) {
      this._resetUploadButtons();
      showToast(`上传请求异常: ${err.message}`, 'error');
      this.appendLog(`请求异常: ${err.message}`, true);
    }
  },

  _updateProgress(p) {
    const bar = document.getElementById('tp-upload-bar');
    const pctText = document.getElementById('tp-upload-pct');
    const infoText = document.getElementById('tp-upload-info');
    if (bar) bar.style.width = `${p.percent || 0}%`;
    if (pctText) pctText.textContent = `${p.percent || 0}%`;
    if (infoText) {
      const mbTrans = ((p.transferred_bytes || 0) / (1024*1024)).toFixed(1);
      const mbTotal = ((p.total_bytes || 0) / (1024*1024)).toFixed(1);
      infoText.textContent = `${mbTrans} MB / ${mbTotal} MB | 速率: ${p.speed_mbps || 0} MB/s | 剩余: ${p.eta_seconds || '--'}s`;
    }
  },

  async dockerLoad() {
    const pathInput = document.getElementById('tp-remote-path-input');
    const remotePath = pathInput ? pathInput.value.trim() : '/home/ubuntu/vsis_dancer_cpu_1.0.tar.gz';
    if (!remotePath) {
      showToast('请填写远端镜像文件路径', 'warning');
      return;
    }

    const btnLoad = document.getElementById('tp-btn-docker-load');
    if (btnLoad && btnLoad.disabled) return;
    if (btnLoad) {
      btnLoad.disabled = true;
      btnLoad.classList.add('loading');
      btnLoad.textContent = '⏳ 安装中 (1~3分钟)...';
    }

    const pBox = document.getElementById('tp-docker-load-progress-box');
    const pBar = document.getElementById('tp-docker-load-progress-bar');
    const pPct = document.getElementById('tp-docker-load-pct');
    const pText = document.getElementById('tp-docker-load-stage-text');
    const pSub = document.getElementById('tp-docker-load-subtext');
    if (pBox) pBox.style.display = 'block';

    let currentPct = 15;
    const setProgress = (pct, stage, sub) => {
      currentPct = Math.max(currentPct, pct);
      if (pBar) {
        pBar.style.width = `${currentPct}%`;
        pBar.style.background = currentPct >= 100 ? '#10b981' : 'linear-gradient(90deg, #0ea5e9, #10b981)';
      }
      if (pPct) pPct.textContent = `${Math.round(currentPct)}%`;
      if (pText && stage) pText.textContent = stage;
      if (pSub && sub) pSub.textContent = sub;
    };
    setProgress(15, '⏳ 检查镜像包压缩状态与磁盘空间...', '准备文件解压与 Docker 归档导入...');

    let ticker = setInterval(() => {
      if (currentPct < 92) {
        currentPct += 0.6;
        setProgress(currentPct);
      }
    }, 800);

    this.appendLog(`正在执行 docker load -i ${remotePath} ...`, false, '⚡');

    try {
      const res = await API.loadImage(remotePath);
      if (res.success && res.task_id) {
        API.listenStream(res.task_id, (line, isErr) => {
          this.appendLog(line, isErr);

          const text = String(line || '');
          if (text.includes('[STEP 1/3]')) {
            setProgress(20, '🔍 步骤 1/3: 检查镜像包格式与磁盘...', '检测 GZIP / TAR 压缩状态与 NVMe 剩余空间');
          } else if (text.includes('[STEP 2/3]') || text.includes('解压') || text.includes('pigz') || text.includes('gzip')) {
            setProgress(45, '📦 步骤 2/3: 正在物理完整解压镜像 TAR 归档...', '利用多核 pigz/gzip 高速解压缩 (预计 30~60 秒)');
          } else if (text.includes('解压完成')) {
            setProgress(65, '✅ TAR 归档解压完成，准备导入 Docker 引擎...', '已落盘，正在调用 docker load 引擎');
          } else if (text.includes('[STEP 3/3]') || text.includes('docker load')) {
            setProgress(75, '⚡ 步骤 3/3: 正在向 Docker 引擎加载镜像层...', '写入 Layer 分层数据与 OCI 格式元数据');
          } else if (text.includes('Loaded image') || text.includes('ctr') || text.includes('skopeo')) {
            setProgress(90, '🎉 镜像层加载成功，正在巡检环境权限...', '执行权限配置与开机环境适配');
          } else if (text.includes('[SUCCESS]') || text.includes('🎉')) {
            setProgress(100, '✅ Docker 镜像导入与环境适配全部完成！', '镜像已成功注册至 Docker，可选择镜像并固化启动');
          }
        }, async (ok) => {
          if (ticker) clearInterval(ticker);
          if (btnLoad) {
            btnLoad.disabled = false;
            btnLoad.classList.remove('loading');
            btnLoad.textContent = '⚡ 执行 docker load';
          }
          if (ok) {
            setProgress(100, '✅ Docker 镜像安装与导入成功！', '已成功加载至宿主机，请在下方选择镜像固化启动。');
            this.appendLog('✅ Docker 镜像导入成功！请在左侧选择镜像并点击【固化启动容器】。', false);
            showToast('✅ Docker 镜像导入成功！', 'success');
            await this.loadImages();
            await this.checkAndFixEnvironment();
          } else {
            setProgress(currentPct, '❌ 镜像安装遇到异常', '请查看右侧控制台详细错误日志');
            if (pBar) pBar.style.background = '#f87171';
            showToast('❌ 镜像导入异常，请查看右侧终端输出', 'error');
          }
        });
      } else {
        if (ticker) clearInterval(ticker);
        if (btnLoad) {
          btnLoad.disabled = false;
          btnLoad.classList.remove('loading');
          btnLoad.textContent = '⚡ 执行 docker load';
        }
        showToast(`启动失败: ${res?.msg || '未知错误'}`, 'error');
      }
    } catch (err) {
      if (ticker) clearInterval(ticker);
      if (btnLoad) {
        btnLoad.disabled = false;
        btnLoad.classList.remove('loading');
        btnLoad.textContent = '⚡ 执行 docker load';
      }
      showToast(`执行异常: ${err.message}`, 'error');
      this.appendLog(`执行异常: ${err.message}`, true);
    }
  },

  async startContainer() {
    const select = document.getElementById('tp-docker-image-select');
    const imageName = select && select.value ? select.value : 'rl_cu118:2.0';

    const btnStart = document.getElementById('tp-btn-start-container');
    if (btnStart) {
      btnStart.disabled = true;
      btnStart.classList.add('loading');
      btnStart.textContent = '⏳ 正在启动 vsis_g1 容器...';
    }

    try {
      // 步骤 1 (优先): 优先配置开机自启并写入 Robot ID
      this.appendLog('【步骤 1/2 优先执行】正在配置开机自启并写入 Robot ID...', false, '⚙️');
      const inputEl = document.getElementById('tp-robot-id-select');
      const valResult = this.validateInputId(true);
      if (!valResult.valid) {
        this.appendLog(`❌ 校验失败: ${valResult.error}`, true);
        showToast(valResult.error, 'error');
        if (inputEl) inputEl.focus();
        if (btnStart) { btnStart.disabled = false; btnStart.classList.remove('loading'); btnStart.textContent = '⚡ 固化启动 vsis_g1 容器'; }
        return;
      }
      const robotId = valResult.cleanId;
      if (inputEl) inputEl.value = robotId;

      const autostartRes = await API.configAutostart(robotId);
      if (!autostartRes.success) {
        this.appendLog(`❌ 写入 Robot ID 失败: ${autostartRes.msg}`, true);
        showToast(`写入失败: ${autostartRes.msg}`, 'error');
        if (btnStart) { btnStart.disabled = false; btnStart.classList.remove('loading'); btnStart.textContent = '⚡ 固化启动 vsis_g1 容器'; }
        return;
      }
      this.isIdConfigured = true;
      this.appendLog(`✅ Robot ID [${robotId}] 与开机自启动钩子写入成功！`, false);

      // 步骤 2 (然后): 固化启动容器 vsis_g1 (不自动执行 run_bg.sh)
      this.appendLog(`【步骤 2/2 然后执行】正在固化启动容器 vsis_g1 (镜像: ${imgName})...`, false, '🚀');
      const res = await API.startContainer(imgName);
      if (res.success && res.task_id) {
        API.listenStream(res.task_id, (line, isErr) => {
          this.appendLog(line, isErr);
        }, async (ok) => {
          if (ok) {
            this.appendLog('✅ 容器 vsis_g1 已固化启动完成！已就绪。', false);
            showToast('✓ 容器 vsis_g1 已固化启动就绪！', 'success');
            await this.loadImages();
          } else {
            showToast('容器启动失败，请查看右侧日志', 'error');
          }
          if (btnStart) {
            btnStart.disabled = false;
            btnStart.classList.remove('loading');
            btnStart.textContent = '⚡ 固化启动 vsis_g1 容器';
          }
        });
      } else {
        if (btnStart) {
          btnStart.disabled = false;
          btnStart.classList.remove('loading');
          btnStart.textContent = '⚡ 固化启动 vsis_g1 容器';
        }
        showToast(`启动失败: ${res?.msg || '未知错误'}`, 'error');
      }
    } catch (err) {
      if (btnStart) {
        btnStart.disabled = false;
        btnStart.classList.remove('loading');
        btnStart.textContent = '⚡ 固化启动 vsis_g1 容器';
      }
      showToast(`启动异常: ${err.message}`, 'error');
      this.appendLog(`启动异常: ${err.message}`, true);
    }
  },

  async writeAutostart() {
    const inputEl = document.getElementById('tp-robot-id-select');
    const valResult = this.validateInputId(true);
    if (!valResult.valid) {
      showToast(valResult.error, 'error');
      if (inputEl) inputEl.focus();
      return;
    }
    const robotId = valResult.cleanId;

    if (inputEl) inputEl.value = robotId;
    this.updateWriteIdButtonText();

    const btn = document.getElementById('tp-btn-write-autostart');
    if (btn) {
      btn.disabled = true;
      btn.textContent = `⏳ 正在写入 ID [${robotId}] ...`;
    }

    this.appendLog(`正在配置开机自启并写入 Robot ID [${robotId}] ...`, false, '⚙️');
    showToast(`正在配置开机自启并写入 Robot ID [${robotId}] ...`, 'info');

    try {
      // 1. 写入 ID 与自启钩子
      const res = await API.configAutostart(robotId);
      if (!res.success) {
        this.appendLog(`❌ 写入失败: ${res.msg}`, true);
        showToast(`写入失败: ${res.msg}`, 'error');
        if (btn) btn.disabled = false;
        this.updateWriteIdButtonText();
        return;
      }

      this.isIdConfigured = true;
      this.appendLog(`✅ Robot ID [${robotId}] 与自启动钩子写入成功！`, false);

      // 2. 检查宿主机当前容器状态，若 vsis_g1 已存在/运行，自动重启容器
      const cStatus = await API.getContainerStatus();
      const hasContainer = cStatus.success && cStatus.data && (cStatus.data.running || cStatus.data.container_exists);

      if (hasContainer) {
        this.appendLog(`[INFO] 检测到 vsis_g1 容器已就绪，正在自动重启容器以应用新 ID [${robotId}] ...`, false, '🔄');
        showToast(`已写入 ID [${robotId}]，正在自动重启 vsis_g1 容器...`, 'info');
        if (btn) btn.textContent = '⏳ 正在重启容器 vsis_g1 ...';

        const restartRes = await API.restartContainer('vsis_g1');
        if (restartRes.success) {
          this.appendLog(`[SUCCESS] ✅ 容器 vsis_g1 已重启，新 ID [${robotId}] 已应用生效！`, false);
          showToast(`🎉 Robot ID [${robotId}] 已写入，容器已重启就绪！`, 'success');
        } else {
          this.appendLog(`❌ 重启容器失败: ${restartRes.msg}`, true);
          showToast(`重启容器失败: ${restartRes.msg}`, 'error');
        }
      } else {
        this.appendLog(`[INFO] 容器尚未创建。Robot ID [${robotId}] 已就绪，请在上方点击【⚡ 固化启动 vsis_g1 容器】。`, false);
        showToast(`✅ Robot ID [${robotId}] 写入成功！请启动容器`, 'success');
      }

      if (btn) btn.disabled = false;
      this.updateWriteIdButtonText();
    } catch (err) {
      showToast(`写入失败: ${err.message}`, 'error');
      this.appendLog(`写入异常: ${err.message}`, true);
      if (btn) btn.disabled = false;
      this.updateWriteIdButtonText();
    }
  },

  async stopContainer(containerName) {
    if (!containerName) return;
    if (!confirm(`确定要关闭/停止正在运行的容器 [${containerName}] 吗？\n停止后该容器内的运控程序将退出，且该镜像将重新在待启动镜像列表中可选。`)) {
      return;
    }
    this.appendLog(`正在关闭容器 [${containerName}] ...`, false, '⏹️');
    showToast(`正在关闭容器 [${containerName}] ...`, 'info');
    try {
      const res = await API.stopContainer(containerName);
      if (res.success) {
        this.appendLog(`✅ ${res.msg}`, false);
        showToast(`✅ ${res.msg}`, 'success');
        await this.loadImages();
      } else {
        this.appendLog(`❌ 关闭失败: ${res.msg}`, true);
        showToast(`关闭失败: ${res.msg}`, 'error');
      }
    } catch (err) {
      showToast(`关闭容器异常: ${err.message}`, 'error');
      this.appendLog(`关闭异常: ${err.message}`, true);
    }
  },

  startProcessPolling() {
    if (this.processPollInterval) clearInterval(this.processPollInterval);
    this.processPollInterval = setInterval(() => {
      const panel = document.getElementById('tab-image');
      if (panel && panel.classList.contains('active')) {
        this.checkProcessStatus();
      }
    }, 4000);
  },

  async checkProcessStatus() {
    const badgeEl = document.getElementById('tp-robot-process-badge');
    const dotEl = document.getElementById('tp-process-dot');
    const textEl = document.getElementById('tp-process-status-text');
    const ctrlSub = document.getElementById('tp-ctrl-sub-badge');
    const loraSub = document.getElementById('tp-lora-sub-badge');

    try {
      const res = await API.getRobotProcessStatus();
      if (!res || !res.connected) {
        if (dotEl) { dotEl.style.background = '#94a3b8'; dotEl.className = 'pulse-dot'; }
        if (textEl) textEl.textContent = '未连接';
        if (badgeEl) { badgeEl.style.borderColor = 'rgba(255,255,255,0.1)'; badgeEl.style.background = 'rgba(255,255,255,0.05)'; }
        if (ctrlSub) { ctrlSub.className = 'container-status-badge stopped'; ctrlSub.textContent = '未连接'; }
        if (loraSub) { loraSub.className = 'container-status-badge stopped'; loraSub.textContent = '未连接'; }
        return;
      }

      if (ctrlSub) {
        ctrlSub.className = res.g1_ctrl_running ? 'container-status-badge running' : 'container-status-badge stopped';
        ctrlSub.textContent = res.g1_ctrl_running ? '🟢 运行中' : '⚪ 未运行';
      }
      if (loraSub) {
        loraSub.className = res.lora_recv_running ? 'container-status-badge running' : 'container-status-badge stopped';
        loraSub.textContent = res.lora_recv_running ? '🟢 运行中' : '⚪ 未运行';
      }

      if (dotEl && textEl && badgeEl) {
        if (res.all_running) {
          dotEl.style.background = '#34d399';
          dotEl.className = 'pulse-dot active';
          textEl.textContent = '运行中';
          badgeEl.style.borderColor = 'rgba(52, 211, 153, 0.4)';
          badgeEl.style.background = 'rgba(16, 185, 129, 0.12)';
        } else if (res.g1_ctrl_running && !res.lora_recv_running) {
          dotEl.style.background = '#fbbf24';
          dotEl.className = 'pulse-dot active';
          textEl.textContent = '仅运控';
          badgeEl.style.borderColor = 'rgba(251, 191, 36, 0.4)';
          badgeEl.style.background = 'rgba(245, 158, 11, 0.12)';
        } else if (!res.g1_ctrl_running && res.lora_recv_running) {
          dotEl.style.background = '#fbbf24';
          dotEl.className = 'pulse-dot active';
          textEl.textContent = '仅通信';
          badgeEl.style.borderColor = 'rgba(251, 191, 36, 0.4)';
          badgeEl.style.background = 'rgba(245, 158, 11, 0.12)';
        } else {
          dotEl.style.background = '#f87171';
          dotEl.className = 'pulse-dot';
          textEl.textContent = '未运行';
          badgeEl.style.borderColor = 'rgba(239, 68, 68, 0.3)';
          badgeEl.style.background = 'rgba(239, 68, 68, 0.08)';
        }
      }
    } catch (_) {}
  },

  async startRobotProcesses() {
    const btnStart = document.getElementById('tp-btn-start-process');
    this.appendLog('正在远程拉起机器人机载程序 (run_bg.sh)...', false, '🤖');
    if (btnStart) {
      btnStart.disabled = true;
      btnStart.textContent = '⏳ 正在启动机载程序...';
    }

    try {
      const res = await API.startRobotProcesses();
      if (res && res.success && res.task_id) {
        API.listenStream(res.task_id, (line, isErr) => {
          this.appendLog(line, isErr);
        }, async (ok) => {
          if (btnStart) {
            btnStart.disabled = false;
            btnStart.textContent = '🚀 启动机载程序 (run_bg.sh)';
          }
          if (ok) {
            this.appendLog('✅ 机载程序 (run_bg.sh) 启动完成，正在后台运行。', false);
          } else {
            this.appendLog('⚠️ 机载程序启动遇到异常，请检查上方日志输出。', true);
          }
          await this.checkProcessStatus();
        });
      } else {
        if (btnStart) {
          btnStart.disabled = false;
          btnStart.textContent = '🚀 启动机载程序 (run_bg.sh)';
        }
        this.appendLog(`启动失败: ${res?.msg || '未知错误'}`, true);
      }
    } catch (err) {
      if (btnStart) {
        btnStart.disabled = false;
        btnStart.textContent = '🚀 启动机载程序 (run_bg.sh)';
      }
      this.appendLog(`请求异常: ${err.message || err}`, true);
    }
  },

  async stopRobotProcesses() {
    if (!confirm('确定要停止机器人机载跳舞运控与 LoRa 接收进程 (pkill) 吗？')) return;
    this.appendLog('正在发送停止机载进程指令 (pkill -f g1_ctrl_vsis ; pkill -f lora_recv_group)...', false, '⏹️');

    try {
      const res = await API.stopRobotProcesses();
      if (res && res.success) {
        this.appendLog('⚠️ 机器人机载运控与 LoRa 接收进程已停止。', false);
        setTimeout(() => this.checkProcessStatus(), 1000);
      } else {
        this.appendLog(`停止失败: ${res?.msg || '未知错误'}`, true);
      }
    } catch (err) {
      this.appendLog(`请求异常: ${err.message || err}`, true);
    }
  },

  appendLog(msg, isErr = false, prefix = '') {
    const consoleEl = document.getElementById('tp-unified-console');
    if (!consoleEl) return;

    if (consoleEl.children.length === 1 && consoleEl.firstElementChild.classList.contains('log-info') && consoleEl.firstElementChild.textContent.includes('就绪。')) {
      consoleEl.innerHTML = '';
    }

    const div = document.createElement('div');
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    const prefixStr = prefix ? `${prefix} ` : '';
    const textMsg = String(msg || '');

    if (isErr || textMsg.includes('ERROR') || textMsg.includes('failed') || textMsg.includes('失败') || textMsg.includes('Permission denied')) {
      div.className = 'log-error';
      div.textContent = `[${timeStr}] ${prefixStr}${textMsg}`;
    } else if (textMsg.includes('WARN') || textMsg.includes('警告') || textMsg.includes('warning') || textMsg.includes('⚠️')) {
      div.className = 'log-warn';
      div.textContent = `[${timeStr}] ${prefixStr}${textMsg}`;
    } else if (textMsg.includes('SUCCESS') || textMsg.includes('✅') || textMsg.includes('成功') || textMsg.includes('🎉') || textMsg.includes('就绪')) {
      div.className = 'log-success';
      div.textContent = `[${timeStr}] ${prefixStr}${textMsg}`;
    } else {
      div.className = 'log-line';
      div.textContent = `[${timeStr}] ${prefixStr}${textMsg}`;
    }

    consoleEl.appendChild(div);
    consoleEl.scrollTop = consoleEl.scrollHeight;
  },

  clearConsole() {
    const consoleEl = document.getElementById('tp-unified-console');
    if (consoleEl) {
      consoleEl.innerHTML = '<div class="log-info">控制台日志已清空。就绪。</div>';
    }
  },

  async checkAndFixEnvironment() {
    this.appendLog('正在对机器人环境与底层权限进行检测并自动修复...', false, '🛠️');
    showToast('正在检测并修复机器人运行环境...', 'info');

    try {
      const res = await API.checkRobotEnv();
      if (res && res.success && res.task_id) {
        API.listenStream(res.task_id, (line, isErr) => {
          this.appendLog(line, isErr);
        }, async (ok) => {
          if (ok) {
            showToast('✅ 机器人环境与权限修复已完成', 'success');
            await this.checkStatus();
            await this.checkProcessStatus();
          } else {
            showToast('环境修复检测发现警告，请查看日志', 'warning');
          }
        });
      } else {
        this.appendLog(`环境修复请求失败: ${res?.msg || '未知错误'}`, true);
      }
    } catch (e) {
      this.appendLog(`环境修复异常: ${e.message || e}`, true);
    }
  }
};



// ===========================================
// Tab 机器码与 License
// ===========================================
const TabLicense = {
  machineId: null,
  licenseContent: null,

  init() {
    this.bindDropzone();
    this.fetchMachineId();
  },

  bindDropzone() {
    const dropzone = document.getElementById('tp-license-dropzone');
    const fileInput = document.getElementById('tp-license-file-input');
    const deployBtn = document.getElementById('tp-deploy-btn');

    if (dropzone && fileInput) {
      dropzone.addEventListener('click', (e) => {
        if (e.target !== fileInput) {
          fileInput.click();
        }
      });

      ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropzone.classList.add('dragover');
          if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
        });
      });

      ['dragleave', 'dragend'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropzone.classList.remove('dragover');
        });
      });

      dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('dragover');
        const files = e.dataTransfer ? e.dataTransfer.files : null;
        if (files && files.length > 0) {
          this.handleFile(files[0]);
        }
      });

      fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
          this.handleFile(e.target.files[0]);
        }
      });
    }

    if (deployBtn) {
      deployBtn.addEventListener('click', () => this.deploy());
    }
  },

  async fetchMachineId() {
    const midEl = document.getElementById('tp-machine-id-val');
    if (midEl) midEl.textContent = '正在读取硬件机器码...';
    try {
      const res = await API.getMachineId();
      if (res.success && res.machine_id) {
        this.machineId = res.machine_id;
        if (midEl) midEl.textContent = res.machine_id;
        // 静默更新，不弹 toast
      } else {
        if (midEl) midEl.textContent = '未能读取到机器码（请先确保容器已启动）';
        showToast(`读取失败: ${res.msg}`, 'warning');
      }
    } catch (err) {
      if (midEl) midEl.textContent = '读取机器码异常';
      showToast(`机器码接口异常: ${err.message}`, 'error');
    }
  },

  copyMachineId() {
    if (!this.machineId) {
      showToast('暂无机器码可复制', 'warning');
      return;
    }
    copyToClipboard(this.machineId, '64位机器码已复制到剪贴板！');
  },

  handleFileInput(input) {
    if (input && input.files && input.files.length > 0) {
      this.handleFile(input.files[0]);
    }
  },

  handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    const dropzone = document.getElementById('tp-license-dropzone');
    if (dropzone) dropzone.classList.remove('dragover');
    const dt = e.dataTransfer;
    if (dt && dt.files && dt.files.length > 0) {
      this.handleFile(dt.files[0]);
    }
  },

  async handleFile(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (e) => {
      this.licenseContent = e.target.result;
      const deployBtn = document.getElementById('tp-deploy-btn');
      const nameEl = document.getElementById('tp-license-filename');
      if (nameEl) nameEl.textContent = `已选择: ${file.name}`;
      if (deployBtn) deployBtn.disabled = false;

      // 自动解析 License 并展示信息
      try {
        const res = await API.verifyLicense(this.licenseContent, this.machineId);
        if (res.success && res.parsed) {
          const p = res.parsed;
          let dancesHtml = (p.dances || []).map(d => `<span class="card-badge" style="margin: 2px;">${d}</span>`).join(' ');
          this._showResult(`
            <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); padding: 12px; border-radius: 6px; color: #38bdf8; font-weight: 600; margin-bottom: 12px;">
              📄 License 文件已加载，点击下方【部署 License 至机器人】开始写入并重启校验。
            </div>
            <div class="card" style="padding: 14px;">
              <div style="font-size: 0.85rem; margin-bottom: 6px; user-select: text;"><b>授权客户:</b> ${p.customer || '商业客户'} | <b>适用机型:</b> ${p.model || 'Unitree G1'}</div>
              <div style="font-size: 0.85rem; margin-bottom: 6px; user-select: text;"><b>有效期至:</b> <span style="color: var(--accent-cyan); font-weight: 600;">${p.expire_date || '永久授权'}</span></div>
              ${p.dance_count > 0 ? `<div style="font-size: 0.85rem; margin-bottom: 8px; user-select: text;"><b>包含舞蹈清单 (${p.dance_count} 支):</b></div>
              <div style="display: flex; flex-wrap: wrap; gap: 4px; max-height: 120px; overflow-y: auto; user-select: text;">${dancesHtml}</div>` : ''}
            </div>
          `);
        } else {
          this._showResult(`<div style="color: var(--accent-cyan); padding: 12px; background: rgba(56,189,248,0.08); border-radius: 8px; border: 1px solid rgba(56,189,248,0.3);">
            📄 <b>${file.name}</b> 已就绪，点击【部署 License 至机器人】写入并重启校验。
          </div>`);
        }
      } catch (_) {
        this._showResult(`<div style="color: var(--accent-cyan); padding: 12px; background: rgba(56,189,248,0.08); border-radius: 8px; border: 1px solid rgba(56,189,248,0.3);">
          📄 <b>${file.name}</b> 已就绪，点击【部署 License 至机器人】写入并重启校验。
        </div>`);
      }

      showToast('License 文件已读取，点击【部署 License】开始校验', 'info');
    };
    reader.readAsText(file);
  },

  _showResult(html) {
    const resEl = document.getElementById('tp-license-result');
    if (resEl) resEl.innerHTML = html;
  },

  async deploy() {
    if (!this.licenseContent) {
      showToast('请先选择或拖入 license.json 文件', 'warning');
      return;
    }
    const btn = document.getElementById('tp-deploy-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ 正在部署 License...'; }

    showToast('正在写入 License 并校验授权...', 'info');
    try {
      const res = await API.deployLicense(this.licenseContent);
      if (res.success) {
        showToast('✓ License 部署成功！正在自动拉起机载程序 (run_bg.sh)...', 'success', 3000);
        let html = `
          <div style="background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.3); border-radius: 8px; padding: 16px; margin-bottom: 12px;">
            <div style="color: #34d399; font-weight: 700; margin-bottom: 8px;">✅ 授权与生效校验成功！</div>
            <div style="font-size: 0.85rem; color: #a7f3d0;">${res.msg}</div>
            ${res.log_snippet ? `<div style="margin-top: 8px; font-family: monospace; font-size: 0.75rem; color: #a7f3d0; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 4px; white-space: pre-wrap; max-height: 120px; overflow-y: auto;">${res.log_snippet}</div>` : ''}
          </div>
          <div id="tp-license-process-box" style="background: rgba(14, 165, 233, 0.08); border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 8px; padding: 14px;">
            <div style="font-weight: 700; color: var(--accent-cyan); margin-bottom: 6px;" id="tp-lic-proc-title">🚀 正在拉起机载运控与通信程序 (run_bg.sh)...</div>
            <div style="font-size: 0.78rem; color: var(--text-secondary);" id="tp-lic-proc-desc">正在启动跳舞运控 (g1_ctrl_vsis) 与 LoRa 接收程序，请稍候...</div>
            <div style="display: flex; gap: 8px; margin-top: 8px;">
              <span id="tp-lic-ctrl-badge" class="container-status-badge stopped" style="font-size: 0.72rem; padding: 2px 8px;">🦾 运控: 启动中</span>
              <span id="tp-lic-lora-badge" class="container-status-badge stopped" style="font-size: 0.72rem; padding: 2px 8px;">📡 LoRa: 启动中</span>
            </div>
          </div>
        `;
        this._showResult(html);

        // 自动拉起机载程序 run_bg.sh 并实时监听真实运控日志
        try {
          const startRes = await API.startRobotProcesses();
          if (startRes && startRes.success && startRes.task_id) {
            API.listenStream(startRes.task_id, (line) => {
              const procDesc = document.getElementById('tp-lic-proc-desc');
              const procTitle = document.getElementById('tp-lic-proc-title');
              if (line.includes('[PROGRESS')) {
                const match = line.match(/\[PROGRESS\s+(\d+)%\]\s*(.*)/i);
                if (match && procTitle) {
                  procTitle.textContent = `🚀 启动进度 [${match[1]}%]: ${match[2] || ''}`;
                }
              } else if (line.includes('[运控日志]')) {
                const clean = line.replace('[运控日志]', '').trim();
                if (clean && procDesc) procDesc.textContent = `[运控] ${clean}`;
              } else if (line.includes('[LoRa日志]')) {
                const clean = line.replace('[LoRa日志]', '').trim();
                if (clean && procDesc) procDesc.textContent = `[LoRa] ${clean}`;
              }
            }, async (ok) => {
              const pRes = await API.getRobotProcessStatus();
              const ctrlB = document.getElementById('tp-lic-ctrl-badge');
              const loraB = document.getElementById('tp-lic-lora-badge');
              const procTitle = document.getElementById('tp-lic-proc-title');
              const procDesc = document.getElementById('tp-lic-proc-desc');

              if (ctrlB) {
                ctrlB.className = pRes?.g1_ctrl_running ? 'container-status-badge running' : 'container-status-badge stopped';
                ctrlB.textContent = pRes?.g1_ctrl_running ? '🦾 运行中' : '🦾 未运行';
              }
              if (loraB) {
                loraB.className = pRes?.lora_recv_running ? 'container-status-badge running' : 'container-status-badge stopped';
                loraB.textContent = pRes?.lora_recv_running ? '📡 运行中' : '📡 未运行';
              }

              if (ok && pRes?.all_running) {
                if (procTitle) procTitle.textContent = '🎉 机载程序已启动就绪！';
                if (procDesc) procDesc.textContent = '✅ 运控与通信服务运行正常。';
                showToast('🎉 机载程序启动成功！', 'success');
              } else {
                if (procTitle) procTitle.textContent = '⚠️ 启动指令已完成';
                if (procDesc) procDesc.textContent = '服务正在后台运行，可刷新查看最新状态。';
                showToast('机载程序已拉起', 'info');
              }
              this.syncAllStates();
            });
          }
        } catch (e) {
          console.warn('拉起机载程序异常:', e);
        }

      } else {
        showToast(`❌ 机器端校验失败: ${res.msg}`, 'error');
        let html = `<div style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; padding: 16px;">
          <div style="color: #f87171; font-weight: 700; margin-bottom: 8px;">❌ 校验失败: ${res.msg}</div>`;
        if (res.log_snippet) {
          html += `<div style="margin-top: 8px; font-family: monospace; font-size: 0.75rem; color: #fca5a5; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 4px; white-space: pre-wrap; max-height: 120px; overflow-y: auto;">${res.log_snippet}</div>`;
        }
        html += '</div>';
        this._showResult(html);
        this.syncAllStates();
      }
    } catch (err) {
      showToast(`部署 License 异常: ${err.message}`, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '🚀 重新部署 License 至机器人'; }
    }
  },

  syncAllStates() {
    if (window.App) {
      if (typeof App.runStartupCheck === 'function') App.runStartupCheck();
      if (typeof App.refreshLicenseStatus === 'function') App.refreshLicenseStatus();
    }
    if (window.TabImage && typeof TabImage.checkProcessStatus === 'function') {
      TabImage.checkProcessStatus();
    }
    if (window.TabImage && typeof TabImage.loadImages === 'function') {
      TabImage.loadImages();
    }
    if (window.Wizard && typeof Wizard.checkProcessStatus === 'function') {
      Wizard.checkProcessStatus();
    }
    if (window.TabDanceUpdate && typeof TabDanceUpdate.loadDances === 'function') {
      TabDanceUpdate.loadDances();
    }
  }
};

// 暴露到全局 window
window.TabNetwork = TabNetwork;
window.TabPrecheck = TabPrecheck;
window.TabImage = TabImage;
window.TabManual = TabManual;
window.TabTutorials = TabTutorials;
window.TabDanceUpdate = TabDanceUpdate;
window.TabLicense = TabLicense;

// ===========================================
// DOM就绪时全局初始化
// ===========================================
document.addEventListener('DOMContentLoaded', () => {
  TabLicense.init();

  // 绑定 tab 切换时的懒初始化
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tabId = btn.dataset.tab;
      if (tabId === 'tab-network') {
        TabNetwork.init();
      } else if (tabId === 'tab-precheck') {
        TabPrecheck.run();
      } else if (tabId === 'tab-image') {
        TabImage.init();
      } else if (tabId === 'tab-license') {
        TabLicense.init();
      }
    });
  });
});
